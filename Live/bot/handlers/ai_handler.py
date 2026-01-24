"""
AI Handler Module

Handles AI integration, rate limiting, and response processing for the Discord bot.
Supports both Gemini and Hugging Face APIs with automatic fallback functionality.
"""

import asyncio
import json
import logging
import os
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..config import (
    GUILD_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    MAX_DAILY_REQUESTS,
    MAX_HOURLY_REQUESTS,
    MEMBER_ROLE_IDS,
    MIN_REQUEST_INTERVAL,
    POPS_ARCADE_USER_ID,
    PRIORITY_INTERVALS,
    RATE_LIMIT_COOLDOWN,
    RATE_LIMIT_COOLDOWNS,
)
from ..database_module import get_database
from ..persona.context_builder import build_ash_context
from ..persona.examples import ASH_FEW_SHOT_EXAMPLES
from ..persona.prompts import ASH_SYSTEM_INSTRUCTION


# Configure user-friendly logging for AI libraries
class UserFriendlyAILogFilter(logging.Filter):
    """Custom filter to make google-genai and httpx logs more readable"""

    def filter(self, record):
        # Keep all non-INFO messages unchanged (warnings, errors)
        if record.levelno != logging.INFO:
            return True

        # Format google-genai messages
        if record.name == "google_genai.models":
            if "AFC is enabled" in record.getMessage():
                # Extract max calls if present
                msg = record.getMessage()
                if "max remote calls:" in msg:
                    max_calls = msg.split("max remote calls:")[-1].strip().rstrip('.')
                    record.msg = f"🤖 Gemini: AFC enabled (max calls: {max_calls})"
                else:
                    record.msg = "🤖 Gemini: AFC enabled"
                record.args = ()

        # Format httpx HTTP request messages
        elif record.name == "httpx":
            msg = record.getMessage()
            if "HTTP Request: POST" in msg and "generateContent" in msg:
                # Extract model name and status
                if "gemini-" in msg:
                    model_start = msg.find("gemini-")
                    model_end = msg.find(":", model_start)
                    model_name = msg[model_start:model_end]

                    if '"HTTP/1.1 200 OK"' in msg:
                        record.msg = f"✅ API Success: {model_name} responded (200 OK)"
                    elif '"HTTP/1.1' in msg:
                        # Extract status code for errors
                        status_start = msg.find('"HTTP/1.1') + 9
                        status_end = msg.find('"', status_start)
                        status = msg[status_start:status_end].strip()
                        record.msg = f"⚠️ API Response: {model_name} returned ({status})"
                    else:
                        record.msg = f"🌐 API Call: {model_name}"
                    record.args = ()

        return True


# Apply the filter to google-genai and httpx loggers
for logger_name in ["google_genai.models", "httpx"]:
    logger = logging.getLogger(logger_name)
    logger.addFilter(UserFriendlyAILogFilter())


# LAZY DATABASE INITIALIZATION - Prevent blocking during module import
# Database connection is established on first use, not at import time
db = None  # type: ignore


def _get_db():
    """Lazy database initialization - only connect when first needed"""
    global db
    if db is None:
        db = get_database()  # type: ignore
    return db


# Import cache system
CACHE_AVAILABLE = False
get_cache = None  # type: ignore


def _init_cache():
    """Initialize cache system at runtime"""
    global CACHE_AVAILABLE, get_cache
    try:
        from . import ai_cache as _ai_cache_module  # type: ignore
        get_cache = _ai_cache_module.get_cache  # type: ignore
        CACHE_AVAILABLE = True
        print("✅ AI cache system loaded")
    except ImportError as e:
        print(f"⚠️ AI cache module not available: {e}")
        CACHE_AVAILABLE = False


# Initialize cache on module load
_init_cache()

# Try to import discord for role detection
try:
    import discord
    DISCORD_AVAILABLE = True
except ImportError:
    discord = None  # type: ignore
    DISCORD_AVAILABLE = False

# Try to import AI modules
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GENAI_AVAILABLE = False

# AI Configuration
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')

# Gemini model cascade configuration (priority order)
# These models are tested on startup and used with automatic fallback
GEMINI_MODEL_CASCADE = [
    'gemini-2.5-flash',       # Primary: Latest, fastest
    'gemini-2.0-flash',       # Secondary: Stable version
    'gemini-2.0-flash-lite'   # Backup: Stable version
]

# AI instances (google-genai v1.56+ API)
gemini_client = None  # Client instance with API key
ai_enabled = False
ai_status_message = "Offline"
primary_ai = None
backup_ai = None  # Legacy variable - no longer used but kept for compatibility

# Model cascade tracking (Phase 2)
current_gemini_model: Optional[str] = None  # Currently active Gemini model
working_gemini_models: List[str] = []   # List of working models in priority order
model_failure_counts: Dict[str, int] = {}    # Track failures per model
last_model_switch: Optional[datetime] = None     # Timestamp of last model switch

# Model testing state (lazy initialization - Phase 3)
models_tested = False  # Track if we've tested models yet
model_test_in_progress = False  # Prevent concurrent testing

# AI Usage Tracking and Rate Limiting
try:
    # Try US/Pacific first, fallback to America/Los_Angeles if not available
    pacific_tz = ZoneInfo("US/Pacific")
except BaseException:
    try:
        pacific_tz = ZoneInfo("America/Los_Angeles")
    except BaseException:
        # Ultimate fallback - use UTC if timezone data is unavailable
        from datetime import timezone
        pacific_tz = timezone.utc
        print("⚠️ Pacific timezone not available, using UTC for AI rate limiting")

ai_usage_stats = {
    "daily_requests": 0,
    "hourly_requests": 0,
    "last_request_time": None,
    "last_hour_reset": datetime.now(pacific_tz).hour,
    "last_day_reset": datetime.now(pacific_tz).date(),
    "consecutive_errors": 0,
    "last_error_time": None,
    "rate_limited_until": None,
    "quota_exhausted": False,
    "quota_exhausted_time": None,
    "backup_active": False,
    "last_backup_attempt": None,
    "primary_ai_errors": 0,
    "backup_ai_errors": 0,
}


async def detect_user_context(user_id: int, member_obj=None, bot=None) -> Dict[str, Any]:
    """
    Detect user context from Discord member object with hierarchical priority and DM handling.

    Priority order:
    1. Alias Override (for testing) - checks user_alias_state - HIGHEST PRIORITY
    2. Special User IDs (hardcoded personalities) - Jonesy, JAM, Pops
    3. Discord Moderator Roles (dynamic role-based detection)
    4. Discord Member Roles (paid vs regular members)
    5. Default (standard member)

    Args:
        user_id: Discord user ID
        member_obj: Discord Member object (contains roles) - None for DMs
        bot: Bot instance (for fetching member in DMs)

    Returns:
        Dict with user_name, user_roles, clearance_level, relationship_type, is_pops_arcade
    """

    # TIER 1: Alias Override Check (HIGHEST PRIORITY - for testing)
    # This must come FIRST so test aliases override even hardcoded user IDs
    try:
        from ..utils.permissions import cleanup_expired_aliases_sync, user_alias_state
        cleanup_expired_aliases_sync()

        if user_id in user_alias_state:
            alias_type = user_alias_state[user_id].get("alias_type", "standard")

            # Map alias types to context
            # Use role-based names only (no username) to avoid AI confusion
            alias_context_map = {
                "captain": {
                    'user_name': 'Captain (Test Mode)',
                    'user_roles': ['Captain', 'Owner'],
                    'clearance_level': 'COMMANDING_OFFICER',
                    'relationship_type': 'COMMANDING_OFFICER',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_captain'
                },
                "creator": {
                    'user_name': 'Creator (Test Mode)',
                    'user_roles': ['Creator', 'Admin'],
                    'clearance_level': 'CREATOR',
                    'relationship_type': 'CREATOR',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_creator'
                },
                "moderator": {
                    'user_name': 'Moderator (Test Mode)',
                    'user_roles': ['Moderator', 'Staff'],
                    'clearance_level': 'MODERATOR',
                    'relationship_type': 'COLLEAGUE',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_moderator'
                },
                "member": {
                    'user_name': 'Member (Test Mode)',
                    'user_roles': ['Member', 'Crew'],
                    'clearance_level': 'STANDARD_MEMBER',
                    'relationship_type': 'PERSONNEL',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_member'
                },
                "standard": {
                    'user_name': 'Standard Personnel (Test Mode)',
                    'user_roles': ['Standard User'],
                    'clearance_level': 'RESTRICTED',
                    'relationship_type': 'PERSONNEL',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_standard'
                }
            }

            if alias_type in alias_context_map:
                return alias_context_map[alias_type]
    except ImportError:
        pass  # Continue without alias handling

    # TIER 2: Special User ID Overrides
    # Hardcoded personalities - only apply if no alias is active
    if user_id == JONESY_USER_ID:
        return {
            'user_name': 'Captain Jonesy',
            'user_roles': ['Captain', 'Owner', 'Commanding Officer'],
            'clearance_level': 'COMMANDING_OFFICER',
            'relationship_type': 'COMMANDING_OFFICER',
            'is_pops_arcade': False,
            'detection_method': 'user_id_override_jonesy'
        }

    if user_id == JAM_USER_ID:
        return {
            'user_name': 'Sir Decent Jam',
            'user_roles': ['Creator', 'Admin', 'Moderator'],
            'clearance_level': 'CREATOR',
            'relationship_type': 'CREATOR',
            'is_pops_arcade': False,
            'detection_method': 'user_id_override_jam'
        }

    if user_id == POPS_ARCADE_USER_ID:
        return {
            'user_name': 'Pops Arcade',
            'user_roles': ['Moderator', 'Antagonist'],
            'clearance_level': 'MODERATOR',
            'relationship_type': 'ANTAGONISTIC',
            'is_pops_arcade': True,
            'detection_method': 'user_id_override_pops'
        }

    # TIER 3: DM Handling - Try to fetch member from guild if in DM
    if not member_obj and bot and DISCORD_AVAILABLE:
        try:
            guild = bot.get_guild(GUILD_ID)
            if guild:
                # Use cached member lookup (fast)
                member_obj = guild.get_member(user_id)

                if not member_obj:
                    # Fallback to API call if not cached (slower but necessary)
                    try:
                        member_obj = await guild.fetch_member(user_id)
                    except Exception as e:
                        # Handle both NotFound and Forbidden errors
                        error_str = str(type(e).__name__)
                        if 'NotFound' in error_str:
                            # User not in guild - treat as standard personnel
                            return {
                                'user_name': 'Personnel',
                                'user_roles': ['Standard User'],
                                'clearance_level': 'RESTRICTED',
                                'relationship_type': 'PERSONNEL',
                                'is_pops_arcade': False,
                                'detection_method': 'dm_not_in_guild'
                            }
                        elif 'Forbidden' in error_str:
                            # No permission to fetch - shouldn't happen but handle gracefully
                            return {
                                'user_name': 'Personnel',
                                'user_roles': ['Standard User'],
                                'clearance_level': 'RESTRICTED',
                                'relationship_type': 'PERSONNEL',
                                'is_pops_arcade': False,
                                'detection_method': 'dm_fetch_forbidden'
                            }
                        else:
                            # Other errors - re-raise
                            raise
        except Exception as e:
            print(f"⚠️ Error fetching member for DM: {e}")
            # Fallback to default
            return {
                'user_name': 'Personnel',
                'user_roles': ['Standard User'],
                'clearance_level': 'RESTRICTED',
                'relationship_type': 'PERSONNEL',
                'is_pops_arcade': False,
                'detection_method': 'dm_fetch_error'
            }

    # TIER 4: Discord Role Detection (if we have member object)
    if member_obj and DISCORD_AVAILABLE and hasattr(member_obj, 'roles'):
        role_ids = [role.id for role in member_obj.roles]

        # Check for moderator permissions (most reliable method)
        if hasattr(member_obj, 'guild_permissions') and member_obj.guild_permissions.manage_messages:
            return {
                'user_name': member_obj.display_name,
                'user_roles': ['Moderator', 'Staff'],
                'clearance_level': 'MODERATOR',
                'relationship_type': 'COLLEAGUE',
                'is_pops_arcade': False,
                'detection_method': 'discord_permissions_moderator'
            }

        # Check for member roles (paid/senior members)
        if any(role_id in MEMBER_ROLE_IDS for role_id in role_ids):
            return {
                'user_name': member_obj.display_name,
                'user_roles': ['Member', 'Crew'],
                'clearance_level': 'STANDARD_MEMBER',
                'relationship_type': 'PERSONNEL',
                'is_pops_arcade': False,
                'detection_method': 'discord_role_member'
            }

    # TIER 5: Default (no special roles or member object)
    return {
        'user_name': member_obj.display_name if member_obj else 'Personnel',
        'user_roles': ['Standard User'],
        'clearance_level': 'RESTRICTED',
        'relationship_type': 'PERSONNEL',
        'is_pops_arcade': False,
        'detection_method': 'default'
    }


def reset_daily_usage():
    """Reset daily usage counter at 8am BST (Google's actual reset time)"""
    global ai_usage_stats

    # Use UK time since Google resets at 8am BST (7am GMT)
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Check if it's past 8am UK time on a new day
    reset_time_today = uk_now.replace(
        hour=8, minute=0, second=0, microsecond=0)

    # If it's a new day and past 8am, or if we haven't reset today yet
    should_reset = False
    if uk_now.date() > ai_usage_stats["last_day_reset"]:
        if uk_now >= reset_time_today:
            should_reset = True
    elif uk_now.date() == ai_usage_stats["last_day_reset"]:
        # Same day, check if we crossed 8am threshold
        last_reset = ai_usage_stats.get("last_reset_time", None)
        if not last_reset or (
                uk_now >= reset_time_today and last_reset < reset_time_today):
            should_reset = True

    if should_reset:
        ai_usage_stats["daily_requests"] = 0
        ai_usage_stats["last_day_reset"] = uk_now.date()
        ai_usage_stats["last_reset_time"] = uk_now

        # Reset quota exhaustion status and warning flags
        ai_usage_stats["quota_exhausted"] = False
        ai_usage_stats["quota_exhausted_time"] = None
        ai_usage_stats["backup_active"] = False
        ai_usage_stats["primary_ai_errors"] = 0
        ai_usage_stats["backup_ai_errors"] = 0
        reset_quota_warnings()

        dst_offset = uk_now.dst()
        is_bst = dst_offset is not None and dst_offset.total_seconds() > 0
        timezone_name = "BST" if is_bst else "GMT"

        print(
            f"🔄 Daily AI usage reset at {uk_now.strftime(f'%Y-%m-%d %H:%M:%S {timezone_name}')} (Google quota reset)")
        print("✅ AI quota status fully reset - primary AI available")


def reset_hourly_usage():
    """Reset hourly usage counter"""
    global ai_usage_stats
    pt_now = datetime.now(pacific_tz)

    if pt_now.hour != ai_usage_stats["last_hour_reset"]:
        ai_usage_stats["hourly_requests"] = 0
        ai_usage_stats["last_hour_reset"] = pt_now.hour
        print(f"🔄 Hourly AI usage reset at {pt_now.strftime('%H:00 PT')}")


def determine_request_priority(
        prompt: str,
        user_id: int,
        context: str = "") -> str:
    """Determine the priority level of an AI request based on context"""
    prompt_lower = prompt.lower()
    context_lower = context.lower()

    # Startup priority: Bypass all rate limiting for critical startup tasks
    startup_contexts = ["startup", "validation", "bootstrap", "initialization"]
    if any(keyword in context_lower for keyword in startup_contexts):
        return "startup"

    # Low priority: Auto-actions, background tasks, announcements (check first
    # for efficiency)
    low_priority_contexts = ["auto", "background", "scheduled", "announcement"]
    if any(keyword in context_lower for keyword in low_priority_contexts):
        return "low"
    if "announcement" in prompt_lower or "rewrite" in prompt_lower:
        return "low"

    # High priority: Trivia, direct questions, critical interactions
    high_priority_contexts = ["trivia", "question", "urgent", "critical"]
    if any(keyword in context_lower for keyword in high_priority_contexts):
        return "high"
    if any(
        keyword in prompt_lower for keyword in [
            "trivia",
            "question?",
            "what is",
            "who is",
            "when is",
            "where is",
            "how is"]):
        return "high"

    # Medium priority: General chat responses, routine interactions
    if any(
        keyword in prompt_lower for keyword in [
            "hello",
            "hi",
            "thank",
            "help",
            "explain"]):
        return "medium"

    # Default to medium priority
    return "medium"


def get_progressive_penalty_duration(consecutive_errors: int) -> int:
    """Get progressive penalty duration based on error count"""
    if consecutive_errors < 3:
        return 0  # No penalty for first few errors
    elif consecutive_errors == 3:
        return RATE_LIMIT_COOLDOWNS["first"]   # 30 seconds
    elif consecutive_errors == 4:
        return RATE_LIMIT_COOLDOWNS["second"]  # 60 seconds
    elif consecutive_errors == 5:
        return RATE_LIMIT_COOLDOWNS["third"]   # 120 seconds
    else:
        return RATE_LIMIT_COOLDOWNS["persistent"]  # 300 seconds


def check_rate_limits(priority: str = "medium") -> Tuple[bool, str]:
    """Check if we can make an AI request without hitting rate limits with priority support"""
    global ai_usage_stats

    # Startup priority bypasses ALL rate limiting
    if priority == "startup":
        print(f"🔥 STARTUP priority request - bypassing all rate limits")
        return True, "OK"

    # Reset counters if needed
    reset_daily_usage()
    reset_hourly_usage()

    pt_now = datetime.now(pacific_tz)

    # Check if we're in a rate limit cooldown
    if ai_usage_stats["rate_limited_until"]:
        if pt_now < ai_usage_stats["rate_limited_until"]:
            remaining = (
                ai_usage_stats["rate_limited_until"] -
                pt_now).total_seconds()
            return False, f"Rate limited for {int(remaining)} more seconds"
        else:
            ai_usage_stats["rate_limited_until"] = None

    # Check daily limit
    if ai_usage_stats["daily_requests"] >= MAX_DAILY_REQUESTS:
        penalty_duration = get_progressive_penalty_duration(
            ai_usage_stats["consecutive_errors"])
        ai_usage_stats["rate_limited_until"] = pt_now + \
            timedelta(seconds=penalty_duration)
        return False, f"Daily request limit reached ({MAX_DAILY_REQUESTS})"

    # Check hourly limit
    if ai_usage_stats["hourly_requests"] >= MAX_HOURLY_REQUESTS:
        penalty_duration = get_progressive_penalty_duration(
            ai_usage_stats["consecutive_errors"])
        ai_usage_stats["rate_limited_until"] = pt_now + \
            timedelta(seconds=penalty_duration)
        return False, f"Hourly request limit reached ({MAX_HOURLY_REQUESTS})"

    # Check priority-based minimum interval between requests
    if ai_usage_stats["last_request_time"]:
        time_since_last = (
            pt_now - ai_usage_stats["last_request_time"]).total_seconds()
        required_interval = PRIORITY_INTERVALS.get(
            priority, MIN_REQUEST_INTERVAL)

        if time_since_last < required_interval:
            remaining = required_interval - time_since_last
            return False, f"Too soon since last {priority} priority request, wait {remaining:.1f}s"

    return True, "OK"


def record_ai_request():
    """Record that an AI request was made"""
    global ai_usage_stats
    pt_now = datetime.now(pacific_tz)

    ai_usage_stats["daily_requests"] += 1
    ai_usage_stats["hourly_requests"] += 1
    ai_usage_stats["last_request_time"] = pt_now
    ai_usage_stats["consecutive_errors"] = 0

    # Check for quota usage warnings
    check_quota_warnings()


def record_ai_error():
    """Record that an AI request failed"""
    global ai_usage_stats
    pt_now = datetime.now(pacific_tz)

    ai_usage_stats["consecutive_errors"] += 1
    ai_usage_stats["last_error_time"] = pt_now

    # If we have too many consecutive errors, apply temporary cooldown
    if ai_usage_stats["consecutive_errors"] >= 3:
        ai_usage_stats["rate_limited_until"] = pt_now + \
            timedelta(seconds=RATE_LIMIT_COOLDOWN)
        print(
            f"⚠️ Too many consecutive AI errors, applying {RATE_LIMIT_COOLDOWN}s cooldown")


def check_quota_warnings():
    """Check for quota usage warnings and send notifications if needed"""
    daily_usage = ai_usage_stats["daily_requests"]
    daily_percentage = (daily_usage / MAX_DAILY_REQUESTS) * 100

    # Track if we've already sent warnings to avoid spam
    if not hasattr(ai_usage_stats, 'warning_80_sent'):
        ai_usage_stats['warning_80_sent'] = False
    if not hasattr(ai_usage_stats, 'warning_95_sent'):
        ai_usage_stats['warning_95_sent'] = False

    # Send 80% warning
    if daily_percentage >= 80 and not ai_usage_stats.get('warning_80_sent', False):
        ai_usage_stats['warning_80_sent'] = True
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        print(
            f"⚠️ AI quota warning: {daily_usage}/{MAX_DAILY_REQUESTS} requests used ({daily_percentage:.1f}%) at {uk_now.strftime('%H:%M:%S')}")
        # Note: DM notification handled by bot instance when available

    # Send 95% warning
    if daily_percentage >= 95 and not ai_usage_stats.get('warning_95_sent', False):
        ai_usage_stats['warning_95_sent'] = True
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        print(
            f"🚨 AI quota critical: {daily_usage}/{MAX_DAILY_REQUESTS} requests used ({daily_percentage:.1f}%) at {uk_now.strftime('%H:%M:%S')}")
        # Note: DM notification handled by bot instance when available


def reset_quota_warnings():
    """Reset quota warning flags when daily usage resets"""
    ai_usage_stats['warning_80_sent'] = False
    ai_usage_stats['warning_95_sent'] = False
    print("🔄 Quota warning flags reset")


async def send_quota_notification(bot, quota_type: str, current_usage: int, max_usage: int):
    """Send quota notifications to administrators"""
    try:
        if quota_type == "warning_80":
            message = (f"⚠️ **AI Quota Warning (80%)**\n\n"
                       f"Current usage: {current_usage}/{max_usage} requests\n"
                       f"Backup AI will automatically engage if quota is exhausted.\n\n"
                       f"*This is an automated notification from Ash Bot's proactive monitoring system.*")
        elif quota_type == "warning_95":
            message = (f"🚨 **AI Quota Critical (95%)**\n\n"
                       f"Current usage: {current_usage}/{max_usage} requests\n"
                       f"Only {max_usage - current_usage} requests remaining before backup AI activation.\n\n"
                       f"*This is an automated notification from Ash Bot's proactive monitoring system.*")
        elif quota_type == "exhausted":
            backup_status = "Backup AI active" if backup_ai else "No backup AI available"
            message = (f"🚫 **AI Quota Exhausted**\n\n"
                       f"Daily limit reached: {max_usage}/{max_usage} requests\n"
                       f"Status: {backup_status}\n"
                       f"Reset time: 8:00 AM UK time\n\n"
                       f"*Automated notification from Ash Bot's monitoring system.*")
        elif quota_type == "reset":
            message = (f"✅ **AI Quota Reset**\n\n"
                       f"Daily quota has been reset to 0/{max_usage}\n"
                       f"Primary AI ({primary_ai.title() if primary_ai else 'Unknown'}) is now available\n\n"
                       f"*Automated notification from Ash Bot's monitoring system.*")
        else:
            return

        # Send to JAM only (as requested)
        success = await send_dm_notification(bot, JAM_USER_ID, message)
        if success:
            print(f"✅ Quota notification sent to JAM ({JAM_USER_ID})")

    except Exception as e:
        print(f"❌ Error sending quota notification: {e}")


def get_quota_reset_countdown():
    """Get time remaining until next quota reset"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Next reset is at 8:00 AM UK time
    reset_time_today = uk_now.replace(hour=8, minute=0, second=0, microsecond=0)

    # If it's already past 8 AM today, next reset is tomorrow at 8 AM
    if uk_now >= reset_time_today:
        next_reset = reset_time_today + timedelta(days=1)
    else:
        next_reset = reset_time_today

    time_remaining = next_reset - uk_now
    hours_remaining = int(time_remaining.total_seconds() // 3600)
    minutes_remaining = int((time_remaining.total_seconds() % 3600) // 60)

    return hours_remaining, minutes_remaining, next_reset


async def send_dm_notification(bot, user_id: int, message: str) -> bool:
    """Send a DM notification to a specific user"""
    try:
        user = await bot.fetch_user(user_id)
        if user:
            await user.send(message)
            print(f"✅ DM notification sent to user {user_id}")
            return True
    except Exception as e:
        print(f"❌ Failed to send DM to user {user_id}: {e}")
    return False


def check_quota_exhaustion(error_message: str) -> bool:
    """Check if the error indicates quota exhaustion"""
    error_lower = str(error_message).lower()
    quota_indicators = [
        "quota", "exceeded", "rate limit", "429", "limit reached",
        "generativelanguage.googleapis.com/generate_content_free_tier_requests"
    ]
    return any(indicator in error_lower for indicator in quota_indicators)


def handle_quota_exhaustion():
    """Handle quota exhaustion by setting appropriate flags and timestamps"""
    global ai_usage_stats
    current_time = datetime.now(pacific_tz)

    ai_usage_stats["quota_exhausted"] = True
    ai_usage_stats["quota_exhausted_time"] = current_time
    ai_usage_stats["primary_ai_errors"] += 1

    print(f"🚫 Primary AI quota exhausted at {current_time.strftime('%H:%M:%S')} - backup AI will be used if available")


async def test_gemini_model(model_name: str, timeout: float = 10.0) -> bool:
    """Test if a specific Gemini model works using new Client API (google-genai v1.56+)"""
    try:
        # Validate API key is present
        if not GEMINI_API_KEY:
            print(f"❌ CRITICAL: GOOGLE_API_KEY environment variable not set! Cannot test model '{model_name}'")
            return False

        if not gemini_client:
            print(f"❌ CRITICAL: Gemini client not initialized!")
            return False

        # Use thread executor to avoid blocking
        import asyncio
        import concurrent.futures

        def sync_test():
            # New API: use client.models.generate_content()
            # Type assertion for Pylance - we already checked gemini_client is not None
            assert gemini_client is not None
            return gemini_client.models.generate_content(
                model=model_name,
                contents="Test",
                config={"max_output_tokens": 5}
            )

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = loop.run_in_executor(executor, sync_test)
            response = await asyncio.wait_for(future, timeout=timeout)

        # Check response format from new API
        if response and hasattr(response, 'text') and response.text:
            print(f"✅ Gemini model '{model_name}' is working")
            return True
        return False

    except Exception as e:
        error_str = str(e).lower()
        if "not found" in error_str or "404" in error_str:
            print(f"❌ Gemini model '{model_name}' not found (invalid name)")
        elif "quota" in error_str or "429" in error_str:
            if "limit: 0" in error_str or "limit:0" in error_str:
                print(f"❌ Gemini model '{model_name}' not available on your tier")
            else:
                print(f"⚠️ Gemini model '{model_name}' quota exhausted")
        else:
            print(f"❌ Gemini model '{model_name}' test failed: {str(e)[:100]}")
        return False


async def initialize_gemini_models() -> bool:
    """Test all Gemini models and build priority list (NEW CLIENT API)"""
    global working_gemini_models, current_gemini_model

    working_gemini_models = []

    print("🔍 Testing Gemini model cascade...")
    for model_name in GEMINI_MODEL_CASCADE:
        if await test_gemini_model(model_name):
            working_gemini_models.append(model_name)

    if working_gemini_models:
        current_gemini_model = working_gemini_models[0]
        # NEW API: No model object creation - just track the model name
        print(f"✅ Primary Gemini model: {current_gemini_model}")
        if len(working_gemini_models) > 1:
            print(f"🔄 Backup Gemini models: {working_gemini_models[1:]}")
        return True
    else:
        print("❌ No working Gemini models found")
        return False


async def switch_to_backup_gemini_model() -> bool:
    """Switch to next available Gemini model after failure (NEW CLIENT API)"""
    global current_gemini_model, working_gemini_models, last_model_switch

    if not current_gemini_model or not working_gemini_models:
        return False

    try:
        current_index = working_gemini_models.index(current_gemini_model)
        if current_index + 1 < len(working_gemini_models):
            next_model = working_gemini_models[current_index + 1]

            # Test the backup before switching
            if await test_gemini_model(next_model, timeout=5.0):
                current_gemini_model = next_model
                # NEW API: Just update the model name, no object creation needed
                last_model_switch = datetime.now(ZoneInfo("Europe/London"))
                print(f"🔄 Switched to backup Gemini model: {next_model}")
                return True
    except Exception as e:
        print(f"❌ Error switching Gemini model: {e}")

    return False


async def lazy_test_models_if_needed() -> bool:
    """
    Test models on first actual use (lazy initialization - Phase 3)

    This function only runs once, when the first AI request is made.
    It tests all models in the cascade to verify which ones actually work.
    """
    global models_tested, model_test_in_progress, working_gemini_models, current_gemini_model

    # Already tested? Skip
    if models_tested:
        return True

    # Another call already testing? Wait for it
    if model_test_in_progress:
        # Wait up to 10 seconds for other test to complete
        for _ in range(20):
            await asyncio.sleep(0.5)
            if models_tested:
                return True
        print("⚠️ LAZY INIT: Timeout waiting for concurrent test")
        return False  # Timeout waiting

    model_test_in_progress = True
    print("🧪 LAZY INIT: Testing models on first use (saves startup API calls)...")

    try:
        # Test models now
        tested_models = []
        for model_name in GEMINI_MODEL_CASCADE:
            print(f"   Testing {model_name}...")
            if await test_gemini_model(model_name, timeout=10.0):
                tested_models.append(model_name)

        if tested_models:
            working_gemini_models = tested_models
            current_gemini_model = tested_models[0]
            models_tested = True
            print(f"✅ LAZY INIT: Confirmed {len(tested_models)} working model(s): {', '.join(tested_models)}")
            return True
        else:
            print("❌ LAZY INIT: No working models found")
            models_tested = True  # Mark as tested even if failed, to avoid repeated attempts
            return False
    except Exception as e:
        print(f"❌ LAZY INIT: Error during model testing: {e}")
        models_tested = True  # Mark as tested to avoid repeated failures
        return False
    finally:
        model_test_in_progress = False


async def call_ai_with_rate_limiting(prompt: str,
                                     user_id: int,
                                     context: str = "",
                                     member_obj=None,
                                     bot=None,
                                     channel_id=None,
                                     is_dm: bool = False) -> Tuple[Optional[str],
                                                                   str]:
    """
    Make an AI call with proper rate limiting and error handling.

    Args:
        prompt: The prompt text to send to AI
        user_id: Discord user ID
        context: Context string for priority/logging
        member_obj: Discord Member object (for role detection)
        bot: Bot instance (for DM member lookup)
        channel_id: Channel ID for conversation context isolation (None for DMs)
        is_dm: Whether this is a DM conversation

    Returns:
        Tuple of (response_text, status_message)
    """
    global ai_usage_stats

    # Check if this is a time-related query and handle it specially
    if is_time_query(prompt):
        return handle_time_query(user_id), "time_response"

    # Determine request priority based on context
    priority = determine_request_priority(prompt, user_id, context)

    # Check rate limits first with priority consideration
    can_request, reason = check_rate_limits(priority)
    if not can_request:
        print(f"⚠️ AI request blocked ({priority} priority): {reason}")
        return None, f"rate_limit:{reason}"

    # Import user alias state from utils module
    try:
        from ..utils.permissions import cleanup_expired_aliases_sync, update_alias_activity, user_alias_state

        # Improved alias rate limiting with better UX
        cleanup_expired_aliases_sync()
        if user_id in user_alias_state:
            # Check for alias-specific cooldown
            alias_data = user_alias_state[user_id]
            alias_type = alias_data.get("alias_type", "unknown")

            if alias_data.get("last_ai_request"):
                time_since_alias_request = (
                    datetime.now(
                        ZoneInfo("Europe/London")) -
                    alias_data["last_ai_request"]).total_seconds()

                # Reduced cooldown and progressive restrictions - more
                # user-friendly
                base_cooldown = 2.0  # Reduced from 4 to 2 seconds for better testing UX

                # Apply progressive cooldowns based on recent usage (less
                # aggressive)
                recent_requests = alias_data.get("recent_request_count", 0)
                if recent_requests > 8:  # Increased threshold from 5 to 8
                    base_cooldown = 4.0  # Reduced from 8 to 4 seconds
                elif recent_requests > 15:  # Increased threshold from 10 to 15
                    base_cooldown = 8.0  # Reduced from 15 to 8 seconds

                if time_since_alias_request < base_cooldown:
                    remaining_time = base_cooldown - time_since_alias_request
                    print(
                        f"⚠️ Alias AI request blocked: {alias_type} testing cooldown ({remaining_time:.1f}s remaining)")
                    return None, f"alias_cooldown:{alias_type}:{remaining_time:.1f}"

            # Update alias AI request tracking
            current_time = datetime.now(ZoneInfo("Europe/London"))
            user_alias_state[user_id]["last_ai_request"] = current_time

            # Track recent requests for progressive cooldowns
            recent_count = alias_data.get("recent_request_count", 0)
            user_alias_state[user_id]["recent_request_count"] = recent_count + 1

    except ImportError:
        pass  # Continue without alias handling if utils not available

    try:
        response_text = None

        # PHASE 3: LAZY INIT - Test models on first use if not tested yet
        if not models_tested and ai_enabled:
            print("🔄 First AI call detected - triggering lazy model initialization...")
            test_success = await lazy_test_models_if_needed()
            if not test_success:
                print("❌ Lazy model testing failed - AI may be unavailable")
                # Continue anyway and let error handling deal with it

        # PHASE 1: Check cache first (NEW OPTIMIZATION) with conversation context
        if CACHE_AVAILABLE and get_cache is not None:
            cache = get_cache()

            # Try to get cached response with conversation context isolation
            cached_response = cache.get(prompt, user_id, channel_id=channel_id, is_dm=is_dm)

            if cached_response:
                # Cache hit! Return immediately without API call
                context_type = "DM" if is_dm else f"channel_{channel_id}"
                print(
                    f"💰 API call saved via cache in {context_type} (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")
                return cached_response, "cache_hit"

            # Cache miss - will need to call API and cache result

        # Reset backup active flag if we're trying primary AI again
        if ai_usage_stats.get("backup_active", False) and not ai_usage_stats.get("quota_exhausted", False):
            ai_usage_stats["backup_active"] = False
            print("🔄 Attempting to resume primary AI usage")

        # Try primary AI first (unless quota is exhausted)
        if primary_ai == "gemini" and gemini_client is not None and current_gemini_model and not ai_usage_stats.get(
                "quota_exhausted", False):
            try:
                print(
                    f"Making Gemini request (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")
                generation_config = {
                    "max_output_tokens": 3000,  # Increased to allow complete responses (~750 words)
                    "temperature": 0.7}

                # Determine timeout based on context priority
                # Increased startup timeout to 25s to prevent premature failures on cold starts
                timeout_duration = 25.0 if context == "startup_validation" else 30.0

                # Create truly async wrapper using thread pool to prevent blocking
                import asyncio
                import concurrent.futures

                def sync_gemini_call():
                    """Synchronous Gemini call using NEW CLIENT API"""
                    if not current_gemini_model:
                        raise ValueError("No Gemini model available")

                    if not gemini_client:
                        raise ValueError("Gemini client not initialized")

                    # NEW API: Use client.models.generate_content() directly
                    # Note: System instructions and chat history handled differently in new API
                    # Pass the user's prompt to enable context features like "simulate_pops"
                    # Also pass member_obj and bot for role detection
                    base_instruction, operational_context = _build_full_system_instruction(
                        user_id, prompt, member_obj, bot)

                    # Convert few-shot examples to string format for inclusion
                    examples_text = ""
                    if ASH_FEW_SHOT_EXAMPLES:
                        examples_text = "\n\n--- BEHAVIORAL EXAMPLES ---\n"
                        examples_text += "These examples demonstrate proper response patterns:\n\n"
                        for idx, example in enumerate(ASH_FEW_SHOT_EXAMPLES, 1):
                            user_text = example.get('user_input', example.get('user', ''))
                            ash_text = example.get('ash_response', example.get('assistant', ''))
                            context_note = example.get('context', '')

                            if context_note:
                                examples_text += f"Example {idx} [{context_note}]:\n"
                            else:
                                examples_text += f"Example {idx}:\n"
                            examples_text += f"User: {user_text}\n"
                            examples_text += f"Ash: {ash_text}\n\n"

                        examples_text += "--- END EXAMPLES ---\n"
                        print(f"✅ Including {len(ASH_FEW_SHOT_EXAMPLES)} few-shot examples in prompt")

                    # Build full prompt with OPERATIONAL CONTEXT first (most important for addressing)
                    # Then base instruction, then examples, then user prompt
                    full_prompt = f"{operational_context}\n\n{base_instruction}{examples_text}\n\nUser: {prompt}"

                    # DEBUG: Enhanced logging to find where User Designation appears
                    # Search for the OPERATIONAL CONTEXT section
                    op_context_start = full_prompt.find("--- CURRENT OPERATIONAL CONTEXT ---")
                    if op_context_start >= 0:
                        # Show the OPERATIONAL CONTEXT section (about 400 chars should cover it)
                        op_context_section = full_prompt[op_context_start:op_context_start + 400]
                        print(f"🐛 DEBUG - OPERATIONAL CONTEXT FOUND at position {op_context_start}:")
                        print(op_context_section)
                    else:
                        print(f"🚨 DEBUG - OPERATIONAL CONTEXT NOT FOUND IN PROMPT!")
                        print(f"🐛 DEBUG - Base instruction length: {len(base_instruction)}")
                        print(f"🐛 DEBUG - Operational context length: {len(operational_context)}")

                    response = gemini_client.models.generate_content(
                        model=current_gemini_model,
                        contents=full_prompt,
                        config=generation_config
                    )

                    return response

                try:
                    # Use thread pool executor to prevent blocking the event loop
                    loop = asyncio.get_event_loop()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = loop.run_in_executor(executor, sync_gemini_call)
                        response = await asyncio.wait_for(future, timeout=timeout_duration)

                    if response and hasattr(response, "text") and response.text:
                        response_text = response.text
                        record_ai_request()
                        print(f"✅ Gemini request successful (timeout: {timeout_duration}s)")

                        # PHASE 1: Cache the successful response (NEW OPTIMIZATION) with conversation context
                        if CACHE_AVAILABLE and get_cache is not None and response_text:
                            cache = get_cache()
                            cache.set(prompt, response_text, user_id, channel_id=channel_id, is_dm=is_dm)

                        # Reset quota exhausted flag if successful
                        if ai_usage_stats.get("quota_exhausted", False):
                            ai_usage_stats["quota_exhausted"] = False
                            print("✅ Primary AI quota restored")

                except asyncio.TimeoutError:
                    print(f"❌ Gemini AI request timed out after {timeout_duration}s")
                    record_ai_error()

                    # Phase 3: Try backup Gemini model on timeout
                    if len(working_gemini_models) > 1 and current_gemini_model:
                        print("🔄 Attempting to switch to backup Gemini model after timeout...")
                        if await switch_to_backup_gemini_model():
                            print("✅ Switched to backup model, retrying request...")
                            # Retry with backup model (recursive call with limited depth)
                            if not hasattr(call_ai_with_rate_limiting, '_retry_count'):
                                call_ai_with_rate_limiting._retry_count = 0  # type: ignore

                            if call_ai_with_rate_limiting._retry_count < 2:  # type: ignore
                                call_ai_with_rate_limiting._retry_count += 1  # type: ignore
                                result = await call_ai_with_rate_limiting(prompt, user_id, context)
                                call_ai_with_rate_limiting._retry_count = 0  # type: ignore
                                return result

                    # No backup available or retry failed
                    return None, f"timeout_error:{timeout_duration}s"

            except Exception as e:
                error_str = str(e)
                print(f"❌ Gemini AI error: {error_str}")

                # Phase 3: Track model-specific failures
                global model_failure_counts
                if current_gemini_model is not None:
                    model_key: str = current_gemini_model
                    model_failure_counts[model_key] = model_failure_counts.get(model_key, 0) + 1
                    print(
                        f"📊 Model failure count for {model_key}: {model_failure_counts[model_key]}")

                # Check if this is a quota exhaustion error
                if check_quota_exhaustion(error_str):
                    handle_quota_exhaustion()
                    # Don't attempt backup for deployment safety
                    return None, "quota_exhausted_no_backup"

                # Phase 3: Check for model-specific errors that warrant switching
                should_switch_model = False
                error_lower = error_str.lower()

                # Errors that indicate model-specific issues
                model_error_indicators = [
                    "not found", "404", "invalid model", "model not available",
                    "limit: 0", "limit:0", "not supported on your tier"
                ]

                if any(indicator in error_lower for indicator in model_error_indicators):
                    print(f"⚠️ Model-specific error detected: {error_str[:100]}")
                    should_switch_model = True

                # Also switch if we have too many failures on current model
                if current_gemini_model and model_failure_counts.get(current_gemini_model, 0) >= 3:
                    print(f"⚠️ Too many failures on {current_gemini_model}, attempting switch...")
                    should_switch_model = True

                # Phase 3: Try backup Gemini model if appropriate
                if should_switch_model and len(working_gemini_models) > 1:
                    print("🔄 Attempting to switch to backup Gemini model...")
                    if await switch_to_backup_gemini_model():
                        print("✅ Switched to backup model, retrying request...")
                        # Reset failure count for new model
                        if current_gemini_model is not None:
                            model_failure_counts[current_gemini_model] = 0

                        # Retry with backup model (with limit)
                        if not hasattr(call_ai_with_rate_limiting, '_retry_count'):
                            call_ai_with_rate_limiting._retry_count = 0  # type: ignore

                        if call_ai_with_rate_limiting._retry_count < 2:  # type: ignore
                            call_ai_with_rate_limiting._retry_count += 1  # type: ignore
                            result = await call_ai_with_rate_limiting(prompt, user_id, context)
                            call_ai_with_rate_limiting._retry_count = 0  # type: ignore
                            return result

                record_ai_error()

        # Return response or error
        if response_text:
            return response_text, "success"
        else:
            return None, "no_ai_available"

    except Exception as e:
        print(f"❌ AI call error: {e}")
        record_ai_error()
        return None, f"error:{str(e)}"


def _convert_few_shot_examples_to_gemini_format(examples: list) -> list:
    """Convert our few-shot examples to Gemini's Content format"""
    try:
        gemini_history = []
        for example in examples:
            # User message - handle both old and new format
            user_text = example.get('user') or example.get('user_input', '')
            if user_text:
                gemini_history.append({
                    'role': 'user',
                    'parts': [{'text': user_text}]
                })

            # Model response - handle both old and new format
            model_text = example.get('assistant') or example.get('ash_response', '')
            if model_text:
                gemini_history.append({
                    'role': 'model',
                    'parts': [{'text': model_text}]
                })

        print(f"✅ Converted {len(gemini_history)//2} few-shot examples successfully")
        return gemini_history
    except Exception as e:
        print(f"🚨 CRITICAL ERROR converting few-shot examples: {e}")
        traceback.print_exc()
        return []


def _build_full_system_instruction(user_id: int, user_input: str = "", member_obj=None, bot=None) -> Tuple[str, str]:
    """
    Build complete system instruction with dynamic context using role detection system.

    Args:
        user_id: Discord user ID
        user_input: User's message (for simulate_pops detection)
        member_obj: Discord Member object (optional, for role detection)
        bot: Bot instance (optional, for DM member lookup)

    Returns:
        Tuple of (base_instruction, operational_context) for proper prompt ordering
    """
    try:
        # Check for simulate_pops test trigger
        if "simulate_pops" in user_input.lower():
            print("🧪 TEST MODE: Simulating Pops Arcade persona via simulate_pops trigger")
            # Use legacy format with Pops override for testing
            user_name = "Pops Arcade (Test Mode)"
            user_roles = ["Moderator"]
            is_pops_arcade = True
            dynamic_context = build_ash_context(user_name, user_roles, is_pops_arcade)
        else:
            # Use new role detection system (can't use await in sync function)
            # For now, detect synchronously using basic logic
            # This will be replaced when we make this function async

            # TIER 0: Alias Override Check (HIGHEST PRIORITY - must come before special user IDs!)
            user_context = None
            try:
                from ..utils.permissions import cleanup_expired_aliases_sync, user_alias_state
                cleanup_expired_aliases_sync()

                if user_id in user_alias_state:
                    alias_type = user_alias_state[user_id].get("alias_type", "standard")
                    alias_name = member_obj.display_name if member_obj else "User"

                    # Use role-based names only (no username) to avoid AI confusion
                    alias_map = {
                        "captain": {
                            'user_name': 'Captain (Test Mode)',
                            'clearance_level': 'COMMANDING_OFFICER',
                            'relationship_type': 'COMMANDING_OFFICER'},
                        "creator": {
                            'user_name': 'Creator (Test Mode)',
                            'clearance_level': 'CREATOR',
                            'relationship_type': 'CREATOR'},
                        "moderator": {
                            'user_name': 'Moderator (Test Mode)',
                            'clearance_level': 'MODERATOR',
                            'relationship_type': 'COLLEAGUE'},
                        "member": {
                            'user_name': 'Member (Test Mode)',
                            'clearance_level': 'STANDARD_MEMBER',
                            'relationship_type': 'PERSONNEL'},
                        "standard": {
                            'user_name': 'Standard Personnel (Test Mode)',
                            'clearance_level': 'RESTRICTED',
                            'relationship_type': 'PERSONNEL'}}

                    if alias_type in alias_map:
                        alias_data = alias_map[alias_type]
                        user_context = {
                            'user_name': alias_data['user_name'],
                            'user_roles': [alias_type.title()],
                            'clearance_level': alias_data['clearance_level'],
                            'relationship_type': alias_data['relationship_type'],
                            'is_pops_arcade': False,
                            'detection_method': f'sync_alias_override_{alias_type}'
                        }
                        print(f"🎭 ALIAS ACTIVE: Testing as {alias_type.title()} (overriding user ID detection)")
            except (ImportError, ValueError):
                pass  # Continue to normal detection if alias handling fails

            # Only proceed with normal detection if NO alias was active
            if user_context is None:
                # TIER 1: Special User ID Overrides
                if user_id == JONESY_USER_ID:
                    user_context = {
                        'user_name': 'Captain Jonesy',
                        'user_roles': ['Captain', 'Owner', 'Commanding Officer'],
                        'clearance_level': 'COMMANDING_OFFICER',
                        'relationship_type': 'COMMANDING_OFFICER',
                        'is_pops_arcade': False,
                        'detection_method': 'sync_user_id_override_jonesy'
                    }
                elif user_id == JAM_USER_ID:
                    user_context = {
                        'user_name': 'Sir Decent Jam',
                        'user_roles': ['Creator', 'Admin', 'Moderator'],
                        'clearance_level': 'CREATOR',
                        'relationship_type': 'CREATOR',
                        'is_pops_arcade': False,
                        'detection_method': 'sync_user_id_override_jam'
                    }
                elif user_id == POPS_ARCADE_USER_ID:
                    user_context = {
                        'user_name': 'Pops Arcade',
                        'user_roles': ['Moderator', 'Antagonist'],
                        'clearance_level': 'MODERATOR',
                        'relationship_type': 'ANTAGONISTIC',
                        'is_pops_arcade': True,
                        'detection_method': 'sync_user_id_override_pops'
                    }
                else:
                    # TIER 2: Discord role detection
                    if member_obj and DISCORD_AVAILABLE and hasattr(member_obj, 'roles'):
                        # Check for moderator permissions
                        if hasattr(member_obj, 'guild_permissions') and member_obj.guild_permissions.manage_messages:
                            user_context = {
                                'user_name': member_obj.display_name,
                                'user_roles': ['Moderator', 'Staff'],
                                'clearance_level': 'MODERATOR',
                                'relationship_type': 'COLLEAGUE',
                                'is_pops_arcade': False,
                                'detection_method': 'sync_discord_permissions_moderator'
                            }
                        else:
                            # Check for member roles
                            role_ids = [role.id for role in member_obj.roles]
                            if any(role_id in MEMBER_ROLE_IDS for role_id in role_ids):
                                user_context = {
                                    'user_name': member_obj.display_name,
                                    'user_roles': ['Member', 'Crew'],
                                    'clearance_level': 'STANDARD_MEMBER',
                                    'relationship_type': 'PERSONNEL',
                                    'is_pops_arcade': False,
                                    'detection_method': 'sync_discord_role_member'
                                }
                            else:
                                # Default with member
                                user_context = {
                                    'user_name': member_obj.display_name,
                                    'user_roles': ['Standard User'],
                                    'clearance_level': 'RESTRICTED',
                                    'relationship_type': 'PERSONNEL',
                                    'is_pops_arcade': False,
                                    'detection_method': 'sync_default_with_member'
                                }
                    else:
                        # No member object - default
                        user_context = {
                            'user_name': 'Personnel',
                            'user_roles': ['Standard User'],
                            'clearance_level': 'RESTRICTED',
                            'relationship_type': 'PERSONNEL',
                            'is_pops_arcade': False,
                            'detection_method': 'sync_default_no_member'
                        }

            # Build dynamic context using new structured format
            dynamic_context = build_ash_context(user_context)

            # === ENHANCEMENT: Add gaming timeline context for temporal questions ===
            current_db = _get_db()
            if current_db and hasattr(current_db, 'get_gaming_timeline'):
                try:
                    # Get first 3 and last 3 games chronologically for temporal awareness
                    timeline_asc = current_db.get_gaming_timeline(order='ASC')[:3]
                    timeline_desc = current_db.get_gaming_timeline(order='DESC')[:3]

                    if timeline_asc or timeline_desc:
                        timeline_text = "\n\n--- GAMING TIMELINE DATA ---\n"

                        if timeline_asc:
                            timeline_text += "First games played chronologically:\n"
                            for game in timeline_asc:
                                played_date = game.get('first_played_date', 'Unknown')
                                release_year = game.get('release_year', 'Unknown')
                                timeline_text += f"  • {game['canonical_name']} (played: {played_date}, released: {release_year})\n"

                        if timeline_desc:
                            timeline_text += "\nMost recently played games:\n"
                            for game in timeline_desc:
                                played_date = game.get('first_played_date', 'Unknown')
                                release_year = game.get('release_year', 'Unknown')
                                timeline_text += f"  • {game['canonical_name']} (played: {played_date}, released: {release_year})\n"

                        timeline_text += "\nYou can answer temporal questions like 'what game did Jonesy play first' or 'oldest game by release year'.\n"
                        timeline_text += "--- END TIMELINE DATA ---\n"

                        # Append timeline data to operational context
                        dynamic_context += timeline_text
                except Exception as timeline_error:
                    # Silently fail if timeline data unavailable - not critical
                    pass

            # === ENHANCEMENT: Add engagement metrics context for view queries ===
            current_db = _get_db()
            if current_db:
                try:
                    engagement_context = "\n\n--- ENGAGEMENT METRICS AVAILABLE ---\n"
                    engagement_context += "The database tracks cross-platform engagement analytics:\n\n"

                    # Get platform statistics
                    if hasattr(current_db, 'get_platform_comparison_stats'):
                        platform_stats = current_db.get_platform_comparison_stats()
                        if platform_stats:
                            yt_stats = platform_stats.get('youtube', {})
                            tw_stats = platform_stats.get('twitch', {})

                            engagement_context += "📊 Platform Metrics:\n"
                            engagement_context += f"  • YouTube: {yt_stats.get('game_count', 0)} games, {yt_stats.get('total_views', 0):,} total views\n"
                            engagement_context += f"  • Twitch: {tw_stats.get('game_count', 0)} games, {tw_stats.get('total_views', 0):,} total views\n"
                            engagement_context += f"  • Cross-platform titles: {platform_stats.get('cross_platform_count', 0)}\n\n"

                    # Get top games by different metrics
                    engagement_context += "🎮 Top Performers by Metric:\n"

                    if hasattr(current_db, 'get_games_by_twitch_views'):
                        top_twitch = current_db.get_games_by_twitch_views(limit=3)
                        if top_twitch:
                            engagement_context += "  • Twitch Leaders: "
                            engagement_context += ", ".join(
                                [f"{g['canonical_name']} ({g.get('twitch_views', 0):,} views)" for g in top_twitch])
                            engagement_context += "\n"

                    if hasattr(current_db, 'get_games_by_total_views'):
                        top_total = current_db.get_games_by_total_views(limit=3)
                        if top_total:
                            engagement_context += "  • Combined Leaders: "
                            engagement_context += ", ".join(
                                [f"{g['canonical_name']} ({g.get('total_views', 0):,} views)" for g in top_total])
                            engagement_context += "\n"

                    if hasattr(current_db, 'get_engagement_metrics'):
                        top_efficiency = current_db.get_engagement_metrics(limit=3)
                        if top_efficiency:
                            engagement_context += "  • Engagement Efficiency: "
                            engagement_context += ", ".join(
                                [f"{g['canonical_name']} ({g.get('views_per_hour', 0):,.0f} views/hr)" for g in top_efficiency])
                            engagement_context += "\n"

                    engagement_context += "\n📌 Query Capabilities:\n"
                    engagement_context += "  • Twitch-specific analytics (views, VOD counts)\n"
                    engagement_context += "  • Cross-platform comparisons (YouTube vs Twitch)\n"
                    engagement_context += "  • Engagement efficiency (views per episode/hour)\n"
                    engagement_context += "  • Platform performance analysis\n"
                    engagement_context += "\nUse this data to answer engagement and popularity questions naturally.\n"
                    engagement_context += "--- END ENGAGEMENT METRICS ---\n"

                    # Append engagement data to operational context
                    dynamic_context += engagement_context
                except Exception as engagement_error:
                    # Silently fail if engagement data unavailable - not critical
                    print(f"⚠️ Could not load engagement metrics context: {engagement_error}")
                    pass

        # Return as tuple: (base_instruction, operational_context)
        # This allows the calling code to order them properly (context first for better addressing)
        return ASH_SYSTEM_INSTRUCTION, dynamic_context

    except Exception as e:
        print(f"⚠️ Error building system instruction: {e}")
        traceback.print_exc()
        # Fallback to base instruction with empty context
        return ASH_SYSTEM_INSTRUCTION, ""


def filter_ai_response(response_text: str) -> str:
    """Filter AI responses to remove verbosity and repetitive content"""
    if not response_text:
        return response_text

    # Split into sentences
    sentences = [s.strip() for s in response_text.split('.') if s.strip()]

    # Remove duplicate sentences (case-insensitive)
    seen_sentences = set()
    filtered_sentences = []
    for sentence in sentences:
        sentence_lower = sentence.lower()
        if sentence_lower not in seen_sentences:
            seen_sentences.add(sentence_lower)
            filtered_sentences.append(sentence)

    # Remove repetitive character phrases if they appear multiple times
    repetitive_phrases = [
        "you have my sympathies",
        "fascinating",
        "i do take directions well",
        "that's quite all right",
        "efficiency is paramount",
        "analysis complete",
        "mission parameters"
    ]

    # Remove sentences with overused phrases (keep only first occurrence)
    final_sentences = []
    phrase_used = set()

    for sentence in filtered_sentences:
        sentence_lower = sentence.lower()
        should_keep = True

        for phrase in repetitive_phrases:
            if phrase in sentence_lower:
                if phrase in phrase_used:
                    should_keep = False
                    break
                phrase_used.add(phrase)

        if should_keep:
            final_sentences.append(sentence)

    # Limit to maximum 10 sentences for conciseness
    final_sentences = final_sentences[:10]

    # Reconstruct response
    result = '. '.join(final_sentences)
    if result and not result.endswith('.'):
        result += '.'

    return result


def setup_ai_provider(
        name: str,
        api_key: Optional[str],
        module: Optional[Any],
        is_available: bool) -> bool:
    """Synchronous wrapper for AI provider setup - used during module import."""
    try:
        # For module import time, just do basic setup without testing
        # Full async testing will happen during initialize_ai_async()
        if not api_key:
            print(f"⚠️ {name.upper()}_API_KEY not found - {name.title()} features disabled")
            return False
        if not is_available or module is None:
            print(f"⚠️ {name} module not available - {name.title()} features disabled")
            return False

        if name == "gemini":
            global gemini_client, gemini_model
            # New SDK uses client-based architecture
            gemini_client = module.Client(api_key=api_key)
            print(f"✅ Gemini client created (testing deferred to async initialization)")
            return True
        elif name == "huggingface":
            print("⚠️ Hugging Face AI disabled to prevent deployment hangs")
            return False

        return False
    except Exception as e:
        print(f"❌ {name.title()} AI configuration failed: {e}")
        return False


def robust_json_parse(response_text: str) -> Optional[Dict[str, Any]]:
    """Robustly parse JSON from AI response with multiple fallback strategies"""
    if not response_text or not response_text.strip():
        return None

    original_text = response_text
    print(f"🔍 Raw AI response length: {len(response_text)} chars")

    # Strategy 1: Basic cleanup and parse
    try:
        # Remove common markdown formatting
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        print(f"🔍 After basic cleanup: {len(cleaned)} chars")
        result = json.loads(cleaned)
        print("✅ Strategy 1 (basic cleanup) successful")
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Strategy 1 failed: {e}")

    # Strategy 2: Find JSON block in response
    try:
        # Look for { ... } block
        start_idx = response_text.find('{')
        if start_idx == -1:
            print("⚠️ Strategy 2: No opening brace found")
            return None

        # Find matching closing brace
        brace_count = 0
        end_idx = -1
        for i in range(start_idx, len(response_text)):
            if response_text[i] == '{':
                brace_count += 1
            elif response_text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break

        if end_idx == -1:
            print("⚠️ Strategy 2: No matching closing brace found")
            return None

        json_block = response_text[start_idx:end_idx + 1]
        print(f"🔍 Strategy 2 extracted JSON block: {len(json_block)} chars")
        result = json.loads(json_block)
        print("✅ Strategy 2 (JSON block extraction) successful")
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Strategy 2 failed: {e}")

    # Strategy 3: Line-by-line reconstruction
    try:
        lines = response_text.split('\n')
        json_lines = []
        in_json = False

        for line in lines:
            line = line.strip()
            if line.startswith('{') or ('"' in line and ':' in line):
                in_json = True
            if in_json:
                json_lines.append(line)
            if line.endswith('}') and in_json:
                break

        if json_lines:
            reconstructed = '\n'.join(json_lines)
            print(f"🔍 Strategy 3 reconstructed: {len(reconstructed)} chars")
            result = json.loads(reconstructed)
            print("✅ Strategy 3 (line reconstruction) successful")
            return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Strategy 3 failed: {e}")

    # Strategy 4: Character-by-character cleaning
    try:
        # Remove all non-JSON characters before first {
        start_idx = response_text.find('{')
        if start_idx > 0:
            response_text = response_text[start_idx:]

        # Remove all non-JSON characters after last }
        end_idx = response_text.rfind('}')
        if end_idx != -1 and end_idx < len(response_text) - 1:
            response_text = response_text[:end_idx + 1]

        # Fix common JSON issues
        cleaned = response_text

        # Fix single quotes to double quotes (but be careful with content)
        # Only fix quotes around keys and simple string values
        import re
        cleaned = re.sub(r"'(\w+)':", r'"\1":', cleaned)  # 'key': -> "key":
        cleaned = re.sub(r':\s*\'([^\']*?)\'', r': "\1"', cleaned)  # : 'value' -> : "value"

        # Fix trailing commas
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)

        print(f"🔍 Strategy 4 cleaned: {len(cleaned)} chars")
        result = json.loads(cleaned)
        print("✅ Strategy 4 (character cleaning) successful")
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Strategy 4 failed: {e}")

    # All strategies failed
    print(f"❌ All JSON parsing strategies failed for response:")
    print(f"   First 200 chars: {original_text[:200]}...")
    print(f"   Last 200 chars: ...{original_text[-200:]}")
    return None


# Question diversity tracking
question_history = {
    "used_patterns": [],
    "category_cooldowns": {},
    "template_usage": {},
    "last_questions": [],
    "pattern_weights": {}
}


def get_question_templates() -> Dict[str, List[Dict[str, Any]]]:
    """Get diverse question templates organized by category - IMPROVED for variety!"""
    return {
        # REMOVED: "most played" pattern (redundant and ambiguous)
        # Users found this question uninteresting and potentially confusing

        # ENHANCED: More genre variety
        "genre_insights": [
            {
                "template": "What horror game did Jonesy play most recently?",
                "answer_logic": "latest_genre_game",
                "type": "single_answer",
                "weight": 1.4,
                "genre_filter": "horror"
            },
            {
                "template": "Which RPG took Jonesy the most episodes to complete?",
                "answer_logic": "longest_episodes_by_genre",
                "type": "single_answer",
                "weight": 1.3,
                "genre_filter": "rpg"
            },
            {
                "template": "How many different horror games has Jonesy played?",
                "answer_logic": "count_games_by_genre",
                "type": "single_answer",
                "weight": 1.3,
                "genre_filter": "horror"
            },
            {
                "template": "What genre has Jonesy played the most games in?",
                "answer_logic": "most_common_genre",
                "type": "single_answer",
                "weight": 1.4
            }
        ],

        # NEW: Platform distinction (YouTube vs Twitch)
        "platform_detective": [
            {
                "template": "Which game has the most YouTube views?",
                "answer_logic": "most_youtube_views",
                "type": "single_answer",
                "weight": 1.5  # High engagement - real metrics
            },
            {
                "template": "What's Jonesy's longest YouTube playthrough by episodes?",
                "answer_logic": "most_youtube_episodes",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "How many games has Jonesy played on both YouTube and Twitch?",
                "answer_logic": "count_both_platforms",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # NEW: Temporal questions using release_year and first_played_date
        "temporal_gaming": [
            {
                "template": "What's the oldest game (by release year) that Jonesy has played?",
                "answer_logic": "oldest_game_by_release",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "What's the newest game in Jonesy's collection?",
                "answer_logic": "newest_game_by_release",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "Which game did Jonesy play first chronologically?",
                "answer_logic": "first_played_game",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # NEW: Completion status focus
        "completion_tracker": [
            {
                "template": "What percentage of Jonesy's games are completed?",
                "answer_logic": "completion_percentage",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "What's Jonesy's longest abandoned game (by episodes)?",
                "answer_logic": "longest_dropped_game",
                "type": "single_answer",
                "weight": 1.2
            },
            {
                "template": "How many games are currently ongoing?",
                "answer_logic": "count_ongoing_games",
                "type": "single_answer",
                "weight": 1.1
            }
        ],

        # ENHANCED: Series questions with more depth
        "series_master": [
            {
                "template": "Which series has Jonesy spent the most total time on?",
                "answer_logic": "series_most_time",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "What series has the most games in Jonesy's collection?",
                "answer_logic": "largest_series",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "How many different game series has Jonesy explored?",
                "answer_logic": "unique_series_count",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # IMPROVED: Gaming milestones (no playtime redundancy)
        "gaming_milestones": [
            {
                "template": "Which was Jonesy's first completed game?",
                "answer_logic": "first_completed_game",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "What's the shortest completed game by playtime?",
                "answer_logic": "shortest_completed_game",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # REFINED: Gaming stories (episode-focused, NOT playtime)
        "gaming_stories": [
            {
                "template": "What game took Jonesy the most episodes to complete?",
                "answer_logic": "max_episodes",
                "type": "single_answer",
                "weight": 1.3  # Clear distinction: episodes, not time
            },
            {
                "template": "What's the most recent game Jonesy completed?",
                "answer_logic": "most_recent_completion",
                "type": "single_answer",
                "weight": 1.4
            }
        ],

        # KEPT: Timeline comparisons (still engaging)
        "timeline_fun": [
            {
                "template": "Which game did Jonesy complete first - {game1} or {game2}?",
                "answer_logic": "compare_completion_order",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "Did Jonesy play {game1} before or after {game2}?",
                "answer_logic": "compare_play_order",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # KEPT: Multiple choice variety
        "multiple_choice_fun": [
            {
                "template": "Which of these games did Jonesy complete?",
                "answer_logic": "mc_completed_game",
                "type": "multiple_choice",
                "weight": 1.5
            },
            {
                "template": "Which horror game has Jonesy played?",
                "answer_logic": "mc_genre_game",
                "type": "multiple_choice",
                "weight": 1.4,
                "genre_filter": "horror"
            }
        ]
    }


def calculate_template_weights(templates: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """Calculate dynamic weights based on usage history and cooldowns"""
    current_time = datetime.now(pacific_tz)

    # Apply cooldowns and usage penalties
    for category, template_list in templates.items():
        # Category cooldown check
        category_cooldown = question_history["category_cooldowns"].get(category, None)
        if category_cooldown and current_time < category_cooldown:
            # Reduce weights for category in cooldown
            for template in template_list:
                template["weight"] *= 0.3

        # Individual template usage penalties
        for template in template_list:
            template_id = template.get("template", "")[:20]  # Use first 20 chars as ID
            usage_count = question_history["template_usage"].get(template_id, 0)

            # Apply usage penalty (more usage = lower weight)
            if usage_count > 0:
                penalty = max(0.2, 1.0 - (usage_count * 0.2))
                template["weight"] *= penalty

    return templates


def select_best_template(games_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Select the best template based on data availability and weights"""
    templates = get_question_templates()
    weighted_templates = calculate_template_weights(templates)

    viable_templates = []

    # Check each template for data viability
    for category, template_list in weighted_templates.items():
        for template in template_list:
            # Check if we have enough data for this template
            if is_template_viable(template, games_data):
                viable_templates.append((template, category))

    if not viable_templates:
        print("⚠️ No viable templates found for current data")
        return None

    # Weight-based selection
    total_weight = sum(template["weight"] for template, _ in viable_templates)
    import random

    if total_weight > 0:
        # Weighted random selection
        target = random.uniform(0, total_weight)
        current_weight = 0

        for template, category in viable_templates:
            current_weight += template["weight"]
            if current_weight >= target:
                return {**template, "category": category}

    # Fallback to random selection
    template, category = random.choice(viable_templates)
    return {**template, "category": category}


def is_template_viable(template: Dict[str, Any], games_data: List[Dict[str, Any]]) -> bool:
    """Check if template can be answered with available data"""
    answer_logic = template.get("answer_logic", "")

    # Comparison templates need at least 2 games
    if answer_logic.startswith("compare_") and len(games_data) < 2:
        return False

    # Multiple choice needs at least 3 games for good options
    if template.get("type") == "multiple_choice" and len(games_data) < 3:
        return False

    # Episode-based questions need games with episode data
    if "episode" in answer_logic:
        if not any(game.get("total_episodes", 0) > 0 for game in games_data):
            return False

    # Playtime questions need games with playtime data
    if "playtime" in answer_logic or "hours" in answer_logic:
        if not any(game.get("total_playtime_minutes", 0) > 0 for game in games_data):
            return False

    # Genre questions need games with genre data
    if "genre" in answer_logic:
        if not any(game.get("genre") for game in games_data):
            return False

    return True


def execute_answer_logic(logic: str, games_data: List[Dict[str, Any]], template: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the answer logic and return question data"""
    import random
    from collections import Counter

    if logic == "compare_episodes":
        # Pick two games with episode data
        games_with_episodes = [g for g in games_data if g.get("total_episodes", 0) > 0]
        if len(games_with_episodes) >= 2:
            game1, game2 = random.sample(games_with_episodes, 2)
            winner = game1 if game1.get("total_episodes", 0) > game2.get("total_episodes", 0) else game2
            return {
                "question_text": template["template"].format(
                    game1=game1["canonical_name"],
                    game2=game2["canonical_name"]),
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"}

    elif logic == "compare_playtime":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if len(games_with_playtime) >= 2:
            game1, game2 = random.sample(games_with_playtime, 2)
            winner = game1 if game1.get("total_playtime_minutes", 0) > game2.get("total_playtime_minutes", 0) else game2
            return {
                "question_text": template["template"].format(
                    game1=game1["canonical_name"],
                    game2=game2["canonical_name"]),
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"}

    elif logic == "max_episodes":
        games_with_episodes = [g for g in games_data if g.get("total_episodes", 0) > 0]
        if games_with_episodes:
            winner = max(games_with_episodes, key=lambda x: x.get("total_episodes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "max_playtime":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if games_with_playtime:
            winner = max(games_with_playtime, key=lambda x: x.get("total_playtime_minutes", 0))
            playtime_minutes = winner.get("total_playtime_minutes", 0)
            playtime_hours = round(playtime_minutes / 60, 1)
            episodes = winner.get("total_episodes", 0)

            return {
                "question_text": template["template"],
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer",
                "context_data": {  # Add context for better responses
                    "playtime_minutes": playtime_minutes,
                    "playtime_hours": playtime_hours,
                    "total_episodes": episodes
                }
            }

    elif logic == "completion_percentage":
        completed = len([g for g in games_data if g.get("completion_status") == "completed"])
        percentage = round((completed / len(games_data)) * 100) if games_data else 0
        return {
            "question_text": template["template"],
            "correct_answer": f"{percentage}%",
            "question_type": "single_answer"
        }

    elif logic == "most_common_genre":
        genres = [g.get("genre") for g in games_data if g.get("genre")]
        if genres:
            most_common = Counter(genres).most_common(1)[0][0]
            return {
                "question_text": template["template"],
                "correct_answer": most_common,
                "question_type": "single_answer"
            }

    elif logic == "unique_genres_count":
        genres = [g.get("genre") for g in games_data if g.get("genre")]
        unique_count = len(set(genres)) if genres else 0
        return {
            "question_text": template["template"],
            "correct_answer": str(unique_count),
            "question_type": "single_answer"
        }

    elif logic == "first_completed_game":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        if completed_games:
            # Use the first game in the list as a simple implementation
            first_completed = completed_games[0]
            return {
                "question_text": template["template"],
                "correct_answer": first_completed["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "shortest_completed_game":
        completed_games = [
            g for g in games_data if g.get("completion_status") == "completed" and g.get(
                "total_playtime_minutes", 0) > 0]
        if completed_games:
            shortest = min(completed_games, key=lambda x: x.get("total_playtime_minutes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": shortest["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "most_recent_completion":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        if completed_games:
            # Use last game in list as most recent (simple implementation)
            most_recent = completed_games[-1]
            return {
                "question_text": template["template"],
                "correct_answer": most_recent["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "largest_series":
        series_counts = Counter([g.get("series_name") for g in games_data if g.get("series_name")])
        if series_counts:
            largest_series = series_counts.most_common(1)[0][0]
            return {
                "question_text": template["template"],
                "correct_answer": largest_series,
                "question_type": "single_answer"
            }

    elif logic == "mc_longest_game":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if len(games_with_playtime) >= 3:
            # Pick the longest game and 3 others for choices
            longest = max(games_with_playtime, key=lambda x: x.get("total_playtime_minutes", 0))
            others = [g for g in games_with_playtime if g != longest]
            choices = [longest] + random.sample(others, min(3, len(others)))
            random.shuffle(choices)

            choice_names = [g["canonical_name"] for g in choices]
            correct_letter = chr(65 + choice_names.index(longest["canonical_name"]))  # A, B, C, D

            return {
                "question_text": template["template"],
                "correct_answer": correct_letter,
                "question_type": "multiple_choice",
                "multiple_choice_options": choice_names
            }

    elif logic == "mc_completed_game":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        incomplete_games = [g for g in games_data if g.get("completion_status") != "completed"]

        if len(completed_games) >= 1 and len(incomplete_games) >= 2:
            correct_game = random.choice(completed_games)
            wrong_games = random.sample(incomplete_games, min(3, len(incomplete_games)))
            choices = [correct_game] + wrong_games
            random.shuffle(choices)

            choice_names = [g["canonical_name"] for g in choices]
            correct_letter = chr(65 + choice_names.index(correct_game["canonical_name"]))

            return {
                "question_text": template["template"],
                "correct_answer": correct_letter,
                "question_type": "multiple_choice",
                "multiple_choice_options": choice_names
            }

    # === TEMPORAL GAMING TIMELINE LOGIC ===
    elif logic == "oldest_game_by_release":
        # Find oldest game by release year
        games_with_release = [g for g in games_data if g.get("release_year")]
        if games_with_release:
            oldest = min(games_with_release, key=lambda x: x.get("release_year", 9999))
            return {
                "question_text": template["template"],
                "correct_answer": oldest["canonical_name"],
                "question_type": "single_answer",
                "context_data": {
                    "release_year": oldest.get("release_year"),
                    "first_played_date": oldest.get("first_played_date")
                }
            }

    elif logic == "newest_game_by_release":
        # Find newest game by release year
        games_with_release = [g for g in games_data if g.get("release_year")]
        if games_with_release:
            newest = max(games_with_release, key=lambda x: x.get("release_year", 0))
            return {
                "question_text": template["template"],
                "correct_answer": newest["canonical_name"],
                "question_type": "single_answer",
                "context_data": {
                    "release_year": newest.get("release_year"),
                    "first_played_date": newest.get("first_played_date")
                }
            }

    elif logic == "first_played_game":
        # Find first game by first_played_date using get_gaming_timeline
        current_db = _get_db()
        if current_db and hasattr(current_db, 'get_gaming_timeline'):
            timeline = current_db.get_gaming_timeline(order='ASC')
            if timeline:
                first_game = timeline[0]
                return {
                    "question_text": template["template"],
                    "correct_answer": first_game["canonical_name"],
                    "question_type": "single_answer",
                    "context_data": {
                        "first_played_date": first_game.get("first_played_date"),
                        "release_year": first_game.get("release_year")
                    }
                }

    elif logic == "last_played_game":
        # Find most recently played game using get_gaming_timeline
        current_db = _get_db()
        if current_db and hasattr(current_db, 'get_gaming_timeline'):
            timeline = current_db.get_gaming_timeline(order='DESC')
            if timeline:
                last_game = timeline[0]
                return {
                    "question_text": template["template"],
                    "correct_answer": last_game["canonical_name"],
                    "question_type": "single_answer",
                    "context_data": {
                        "first_played_date": last_game.get("first_played_date"),
                        "release_year": last_game.get("release_year")
                    }
                }

    # Fallback - return empty dict if logic couldn't execute
    return {}


def update_question_history(question_data: Dict[str, Any], category: str):
    """Update question history to track usage and implement cooldowns"""
    current_time = datetime.now(pacific_tz)

    # Add to recent questions list (keep last 10)
    question_history["last_questions"].append({
        "question": question_data.get("question_text", "")[:50],
        "category": category,
        "timestamp": current_time
    })
    if len(question_history["last_questions"]) > 10:
        question_history["last_questions"].pop(0)

    # Update template usage count
    template_id = question_data.get("question_text", "")[:20]
    question_history["template_usage"][template_id] = question_history["template_usage"].get(template_id, 0) + 1

    # Set category cooldown if used too recently
    recent_usage = sum(1 for q in question_history["last_questions"][-3:] if q["category"] == category)
    if recent_usage >= 2:  # Used 2 times in last 3 questions
        cooldown_duration = 30 * 60  # 30 minutes
        question_history["category_cooldowns"][category] = current_time + timedelta(seconds=cooldown_duration)
        print(f"⏰ Category '{category}' on cooldown for 30 minutes due to recent usage")


async def generate_ai_trivia_question(context: str = "trivia", avoid_questions: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Generate a diverse trivia question using template-based system with AI fallback
    
    Args:
        context: Context string for rate limiting and logging
        avoid_questions: List of recently generated question texts to avoid repeating patterns
    """
    if not ai_enabled:
        print("❌ AI not enabled for trivia question generation")
        return None

    # Check if database is available (lazy init)
    current_db = _get_db()
    if current_db is None:
        print("❌ Database not available for AI trivia generation")
        return None

    try:
        print(f"🧠 Generating diverse trivia question with context: {context}")
        if avoid_questions:
            print(f"   Avoiding {len(avoid_questions)} recent pattern(s)")

        # Get all available games data
        all_games = current_db.get_all_played_games()

        if not all_games:
            print("❌ No games data available for question generation")
            return None

        print(f"📊 Available games data: {len(all_games)} games")

        # Try template-based generation first (more reliable and diverse)
        max_template_attempts = 3
        for attempt in range(max_template_attempts):
            try:
                selected_template = select_best_template(all_games)

                if selected_template:
                    question_data = execute_answer_logic(
                        selected_template["answer_logic"],
                        all_games,
                        selected_template
                    )

                    if question_data and question_data.get("question_text"):
                        # Check for duplicates before accepting this question
                        duplicate_info = current_db.check_question_duplicate(
                            question_data["question_text"],
                            similarity_threshold=0.8
                        )

                        if duplicate_info:
                            print(
                                f"🔍 Template question duplicate detected (attempt {attempt+1}/{max_template_attempts}): {duplicate_info['similarity_score']:.2f} similarity to question #{duplicate_info['duplicate_id']}")
                            if attempt < max_template_attempts - 1:
                                continue  # Try generating a different template question
                        else:
                            # Add metadata
                            question_data.update({
                                "is_dynamic": False,
                                "category": selected_template.get("category", "template_generated"),
                                "generation_method": "template"
                            })

                            # Update history
                            update_question_history(question_data, selected_template.get("category", "unknown"))

                            print(f"✅ Template-generated question (unique): {question_data['question_text'][:50]}...")
                            return question_data

            except Exception as template_error:
                print(f"⚠️ Template generation attempt {attempt+1} failed: {template_error}")
                if attempt == max_template_attempts - 1:
                    print(f"❌ All template generation attempts failed")

        # Fallback to AI generation (with improved prompt)
        stats = current_db.get_played_games_stats()
        sample_games = all_games[:5]  # Use first 5 games for context

        # Create detailed game context
        game_context = ""
        if sample_games:
            game_details = []
            for game in sample_games:
                episodes_info = f" ({game.get('total_episodes', 0)} eps)" if game.get('total_episodes', 0) > 0 else ""
                status = game.get('completion_status', 'unknown')
                playtime = game.get('total_playtime_minutes', 0)
                genre = game.get('genre', 'unknown')
                game_details.append(
                    f"{game['canonical_name']}{episodes_info} - {status} - {playtime//60}h {playtime%60}m - {genre}")

            game_context = f"Available games: {'; '.join(game_details)}"

        # Enhanced AI prompt with Ash's analytical persona but engaging content
        recent_categories = [q["category"] for q in question_history["last_questions"][-5:]]
        avoid_categories = list(set(recent_categories)) if recent_categories else []

        # Build avoid-patterns section if we have recent questions
        avoid_patterns_text = ""
        if avoid_questions:
            avoid_patterns_text = f"""

🚫 RECENTLY GENERATED - DO NOT REPEAT THESE PATTERNS:
{chr(10).join([f"   ❌ {q[:80]}..." if len(q) > 80 else f"   ❌ {q}" for q in avoid_questions])}

CRITICAL: Generate a DIFFERENT question with DIFFERENT phrasing and DIFFERENT focus area."""

        content_prompt = f"""Generate a trivia question for the CREW about Captain Jonesy's gaming data.

🎯 AUDIENCE CLARITY:
- You are asking the CREW about Jonesy's gaming (Jonesy is the SUBJECT, not the AUDIENCE)
- DO NOT address Jonesy directly with "Captain" or "you"
- The crew is answering questions ABOUT Jonesy's data
- Phrasing: "What game did Jonesy..." NOT "Captain, what game took you..."

CRITICAL TERMINOLOGY:
⚠️ "most played" = game with HIGHEST total_playtime_minutes (time spent playing)
⚠️ "most episodes" = game with MOST episode count (number of episodes)
⚠️ These are DIFFERENT metrics! Episode count ≠ playtime!

DATABASE SCHEMA:
- total_playtime_minutes: Actual time spent playing in minutes (THIS IS "MOST PLAYED")
- total_episodes: Number of recorded episodes

🚫 BANNED PATTERNS (too boring/overused):
❌ "What percentage of..." - too statistical, not engaging
❌ "How many X does Jonesy have?" - too generic
❌ "Captain, analysis indicates:" - addressing wrong audience
❌ "Which game required the most..." - use "took" or "needed" for variety

AVOID these overused categories: {avoid_categories}{avoid_patterns_text}

✅ PREFERRED QUESTION TYPES (pick one with variety):
🎮 **Genre Adventures**: "What horror game did Jonesy play most recently?"
🏆 **Gaming Milestones**: "Which was Jonesy's first completed RPG?"
📚 **Series Explorer**: "How many Resident Evil games has Jonesy played?"
🎯 **Gaming Stories**: "What game took Jonesy the most episodes to finish?"
🕐 **Timeline Fun**: "Which game did Jonesy complete first - [Game A] or [Game B]?"
⭐ **Playtime Champion**: "What game has Jonesy spent the most time playing?"
📺 **Platform Detective**: "Which game has the most YouTube views?"

AVAILABLE GAMES: {game_context}
Total games: {stats.get('total_games', 0)}

RETURN ONLY JSON:
{{
    "question_text": "Direct question about Jonesy's gaming (crew is audience)",
    "question_type": "single_answer",
    "correct_answer": "The answer",
    "is_dynamic": false,
    "category": "ai_generated"
}}

Generate an engaging, unique question with correct audience (crew, not Jonesy)."""

        # For now, use the content_prompt directly
        # TODO: Will be replaced with proper system_instruction integration
        prompt = content_prompt

        # Call AI with rate limiting
        max_ai_attempts = 3
        for ai_attempt in range(max_ai_attempts):
            response_text, status_message = await call_ai_with_rate_limiting(prompt, JONESY_USER_ID, context)

            if response_text:
                print(
                    f"✅ AI fallback response received: {len(response_text)} characters (attempt {ai_attempt+1}/{max_ai_attempts})")

                # Parse AI response
                ai_question = robust_json_parse(response_text)

                if ai_question and all(
                    key in ai_question for key in [
                        "question_text",
                        "question_type",
                        "correct_answer"]):
                    # Check for duplicates before accepting this AI question
                    duplicate_info = current_db.check_question_duplicate(
                        ai_question["question_text"],
                        similarity_threshold=0.8
                    )

                    if duplicate_info:
                        print(
                            f"🔍 AI question duplicate detected (attempt {ai_attempt+1}/{max_ai_attempts}): {duplicate_info['similarity_score']:.2f} similarity to question #{duplicate_info['duplicate_id']}")
                        if ai_attempt < max_ai_attempts - 1:
                            continue  # Try generating a different AI question
                    else:
                        ai_question["generation_method"] = "ai_fallback"
                        print(f"✅ AI fallback question generated (unique): {ai_question['question_text'][:50]}...")
                        return ai_question
            else:
                print(f"❌ AI fallback attempt {ai_attempt+1} failed: {status_message}")
                break  # Don't retry on rate limits or API failures

        print(f"❌ All AI generation attempts failed")
        return None

    except Exception as e:
        print(f"❌ Error in diverse trivia generation: {e}")
        traceback.print_exc()
        return None


async def create_ai_announcement_content(
        user_content: str,
        target_channel: str,
        user_id: int) -> str:
    """Create AI-enhanced announcement content in Ash's style based on user input"""
    try:
        if not ai_enabled:
            print("AI not enabled, returning original content")
            return user_content

        # Determine the author for context
        if user_id == JONESY_USER_ID:
            author = "Captain Jonesy"
            author_context = "the commanding officer"
        else:
            author = "Sir Decent Jam"
            author_context = "the bot creator and systems architect"

        # Create AI prompt based on target channel using centralized persona
        if target_channel == 'mod':
            content_prompt = f"""Rewrite this announcement content in your analytical, technical style for a moderator briefing.

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a technical briefing for moderators. Be analytical, precise, and focus on:
- Technical implementation details
- Operational efficiency improvements
- System functionality enhancements
- Mission-critical parameters

Use phrases like "Analysis indicates", "System diagnostics confirm", "Operational parameters enhanced", etc.
Keep it professional but maintain your clinical, analytical personality.
Write 2-4 sentences maximum. Be concise but comprehensive."""

            # For now, use the content_prompt directly
            # TODO: Will be replaced with proper system_instruction integration
            prompt = content_prompt

        else:  # user channel
            content_prompt = f"""Rewrite this announcement content in a user-friendly way while maintaining some of your analytical personality.

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a community announcement that's accessible to regular users but still has your analytical undertones. Focus on:
- User benefits and improvements
- How features enhance the user experience
- Clear, helpful explanations
- Practical usage information

Be helpful and informative, but keep subtle hints of your analytical nature.
Write 2-4 sentences maximum. Make it engaging and user-focused."""

            # For now, use the content_prompt directly
            # TODO: Will be replaced with proper system_instruction integration
            prompt = content_prompt

        # Call AI with rate limiting
        response_text, status_message = await call_ai_with_rate_limiting(prompt, user_id)

        if response_text:
            enhanced_content = filter_ai_response(response_text)
            print(
                f"AI content enhancement successful: {len(enhanced_content)} characters")
            return enhanced_content
        else:
            print(f"AI content enhancement failed: {status_message}")
            return user_content  # Fallback to original content

    except Exception as e:
        print(f"Error in AI content enhancement: {e}")
        return user_content  # Fallback to original content


async def initialize_ai_async():
    """Async initialize AI providers WITHOUT testing (lazy initialization - Phase 3)"""
    global ai_enabled, ai_status_message, primary_ai, current_gemini_model, working_gemini_models

    print("🤖 Starting async AI initialization (lazy mode - no startup tests)...")

    try:
        # Initialize Gemini WITHOUT testing - just set up model list
        if GEMINI_API_KEY and GENAI_AVAILABLE and genai and gemini_client:
            # Set up model cascade WITHOUT testing - assume all models work initially
            working_gemini_models = GEMINI_MODEL_CASCADE.copy()  # Copy the full cascade
            current_gemini_model = working_gemini_models[0]  # Use first model as default

            primary_ai = "gemini"
            ai_enabled = True
            ai_status_message = f"Configured (lazy init, {len(working_gemini_models)} models untested)"
            print(f"✅ Gemini AI configured: {current_gemini_model} (will test on first use)")
            print(f"   Available models: {', '.join(working_gemini_models)}")
        else:
            ai_enabled = False
            ai_status_message = "No AI available"
            print("⚠️ Gemini AI not available - missing API key or module")

        if ai_enabled:
            print(f"✅ AI initialization complete (lazy mode): {ai_status_message}")
            print(f"💡 Models will be tested on first actual AI request")
        else:
            print("❌ No AI systems available - all AI features disabled")

    except Exception as e:
        print(f"❌ Error during async AI initialization: {e}")
        ai_enabled = False
        ai_status_message = "AI initialization failed"


def initialize_ai():
    """Synchronous initialize AI providers - for backward compatibility"""
    global ai_enabled, ai_status_message, primary_ai

    print("🤖 Starting synchronous AI initialization (basic setup only)...")

    # Setup Gemini AI provider (testing done in async version)
    gemini_ok = setup_ai_provider(
        "gemini", GEMINI_API_KEY, genai, GENAI_AVAILABLE)

    # Set basic AI status (will be updated by async init if called)
    if gemini_ok:
        primary_ai = "gemini"
        ai_enabled = True
        ai_status_message = f"Configured ({primary_ai.title()} only) - testing pending"
        print(f"🔧 Basic AI setup complete: {ai_status_message}")
    else:
        ai_enabled = False
        ai_status_message = "No AI available"
        print("❌ No AI systems available - all AI features disabled")


def get_ai_status() -> Dict[str, Any]:
    """Get current AI status and usage statistics"""
    return {
        "enabled": ai_enabled,
        "status_message": ai_status_message,
        "primary_ai": primary_ai,
        "backup_ai": backup_ai,
        "usage_stats": ai_usage_stats.copy()
    }


def is_time_query(prompt: str) -> bool:
    """Check if the prompt is asking for the current time"""
    prompt_lower = prompt.lower()
    time_keywords = [
        "what time is it",
        "current time",
        "what's the time",
        "tell me the time",
        "time is it",
        "chronometer",
        "time check"
    ]

    return any(keyword in prompt_lower for keyword in time_keywords)


def handle_time_query(user_id: int) -> str:
    """Handle time queries with proper current time"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Determine DST status for proper timezone naming
    dst_offset = uk_now.dst()
    is_bst = dst_offset is not None and dst_offset.total_seconds() > 0
    timezone_name = "BST" if is_bst else "GMT"

    formatted_time = uk_now.strftime(f"%A, %B %d, %Y at %H:%M:%S {timezone_name}")

    # Determine the appropriate salutation based on user
    if user_id == JONESY_USER_ID:
        salutation = "Captain Jonesy"
    else:
        salutation = "Sir Decent Jam"

    # Return the proper time response without placeholder text
    return f"{salutation}, my internal chronometer indicates the current time is {formatted_time}. I await further instructions."


# Initialize AI on module import
initialize_ai()

# Deployment Safety: Add graceful degradation for missing dependencies


def safe_initialize_ai():
    """Safe AI initialization that won't crash on missing dependencies"""
    try:
        initialize_ai()
        return True
    except Exception as e:
        print(f"⚠️ Safe AI initialization caught error: {e}")
        global ai_enabled, ai_status_message
        ai_enabled = False
        ai_status_message = "AI initialization failed (safe mode)"
        return False


async def safe_initialize_ai_async():
    """Safe async AI initialization that won't crash on missing dependencies"""
    global ai_enabled, ai_status_message

    try:
        await initialize_ai_async()
        # Return the actual AI status, not just whether the function completed
        if ai_enabled:
            print(f"✅ AI initialization successful: {primary_ai} ready")
            return True
        else:
            print(f"⚠️ AI initialization completed but no AI systems available")
            return False
    except Exception as e:
        print(f"⚠️ Safe async AI initialization caught error: {e}")
        print("📋 Full error traceback:")
        traceback.print_exc()
        ai_enabled = False
        ai_status_message = "Async AI initialization failed (safe mode)"
        return False


async def generate_trivia_batch(batch_size: int = 10, context: str = "batch_generation") -> Dict[str, Any]:
    """
    PHASE 2: Generate multiple trivia questions in a single API call.

    This is the key optimization - instead of 10 API calls for 10 questions,
    we make 1 API call that generates all 10 at once.

    Args:
        batch_size: Number of questions to generate (default 10)
        context: Context string for logging

    Returns:
        Dict with generation results and statistics
    """
    if not ai_enabled:
        print("❌ AI not enabled for trivia batch generation")
        return {"success": False, "generated": 0, "error": "AI not enabled"}

    current_db = _get_db()
    if current_db is None:
        print("❌ Database not available for trivia batch generation")
        return {"success": False, "generated": 0, "error": "Database not available"}

    try:
        print(f"🎲 PHASE 2: Generating batch of {batch_size} trivia questions in single API call...")

        # Get game statistics for context
        stats = current_db.get_played_games_stats()
        sample_games = current_db.get_all_played_games()[:10]

        # Build game context
        game_context = ""
        if sample_games:
            game_details = []
            for game in sample_games[:5]:
                name = game['canonical_name']
                episodes = game.get('total_episodes', 0)
                status = game.get('completion_status', 'unknown')
                game_details.append(f"{name} ({episodes} eps, {status})")
            game_context = f"Sample games: {'; '.join(game_details)}"

        # Create batch generation prompt
        batch_prompt = f"""Generate exactly {batch_size} diverse trivia questions about Captain Jonesy's gaming experiences.

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {batch_size} questions
2. Use DIVERSE question types and categories
3. Each question must be UNIQUE and different from others
4. Be CONCISE - minimal preamble

TERMINOLOGY RULES:
⚠️ "most played" = HIGHEST total_playtime_minutes (time)
⚠️ "most episodes" = MOST episode count (episodes)
⚠️ These are DIFFERENT metrics!

DIVERSITY GUIDELINES:
- Mix genres, series, platforms, temporal questions
- Vary between completion status, playtime, episodes
- Include both easy and challenging questions
- Focus on engaging, interesting facts

AVAILABLE DATA:
{game_context}
Total games: {stats.get('total_games', 0)}

RETURN ONLY JSON ARRAY:
[
  {{
    "question_text": "Concise question here?",
    "question_type": "single_answer",
    "correct_answer": "Answer here",
    "category": "category_name",
    "difficulty_level": 1
  }},
  ... ({batch_size} total questions)
]

Generate diverse, engaging questions about Jonesy's gaming journey."""

        # Call AI with rate limiting
        print(f"📞 Making single API call for {batch_size} questions...")
        response_text, status_message = await call_ai_with_rate_limiting(batch_prompt, JONESY_USER_ID, context)

        if not response_text:
            print(f"❌ Batch generation failed: {status_message}")
            return {"success": False, "generated": 0, "error": status_message}

        print(f"✅ Received batch response: {len(response_text)} characters")

        # Parse the JSON array
        parsed_response = robust_json_parse(response_text)

        # Type check: must be a list
        if not parsed_response or not isinstance(parsed_response, list):
            print(f"❌ Failed to parse batch response as JSON array")
            return {"success": False, "generated": 0, "error": "Invalid JSON response"}

        # Now we know it's a list, type hint for Pylance
        questions_array: List[Any] = parsed_response

        print(f"📊 Parsed {len(questions_array)} questions from batch")

        # Store each question in the database
        stored_count = 0
        duplicate_count = 0
        error_count = 0

        for idx, question_data in enumerate(questions_array):
            try:
                # Type check: must be a dict
                if not isinstance(question_data, dict):
                    print(f"⚠️ Question {idx+1} is not a dict, skipping")
                    error_count += 1
                    continue

                # Type cast for Pylance after type check
                question_dict: Dict[str, Any] = question_data

                # Validate question structure
                if not all(key in question_dict for key in ["question_text", "question_type", "correct_answer"]):
                    print(f"⚠️ Question {idx+1} missing required fields, skipping")
                    error_count += 1
                    continue

                # Extract fields using .get() for Pylance compatibility
                question_text = question_dict.get("question_text", "")
                correct_answer = question_dict.get("correct_answer", "")

                if not question_text or not correct_answer:
                    print(f"⚠️ Question {idx+1} has empty required fields, skipping")
                    error_count += 1
                    continue

                # Check for duplicates
                duplicate_info = current_db.check_question_duplicate(
                    question_text,
                    similarity_threshold=0.8
                )

                if duplicate_info:
                    print(
                        f"🔍 Question {idx+1} is duplicate (similarity: {duplicate_info['similarity_score']:.2f}), skipping")
                    duplicate_count += 1
                    continue

                # Store question in database with 'available' status
                question_id = current_db.safe_add_trivia_question(
                    question_text=question_text,
                    question_type=question_dict.get("question_type", "single_answer"),
                    correct_answer=correct_answer,
                    multiple_choice_options=question_dict.get("multiple_choice_options"),
                    is_dynamic=False,
                    category=question_dict.get("category", "batch_generated"),
                    difficulty_level=question_dict.get("difficulty_level", 1),
                    submitted_by_user_id=None  # AI-generated
                )

                if question_id:
                    stored_count += 1
                    print(f"✅ Stored question {idx+1}/{len(questions_array)}: ID {question_id}")
                else:
                    error_count += 1
                    print(f"❌ Failed to store question {idx+1}")

            except Exception as e:
                print(f"❌ Error storing question {idx+1}: {e}")
                error_count += 1

        # Calculate efficiency
        efficiency = f"{stored_count}x" if stored_count > 0 else "0x"
        api_calls_saved = stored_count - 1 if stored_count > 1 else 0

        result = {
            "success": stored_count > 0,
            "generated": stored_count,
            "duplicates": duplicate_count,
            "errors": error_count,
            "total_attempted": len(questions_array),
            "api_calls_used": 1,
            "api_calls_saved": api_calls_saved,
            "efficiency": efficiency
        }

        print(
            f"🎉 PHASE 2 COMPLETE: Generated {stored_count} questions in 1 API call (saved {api_calls_saved} calls, {efficiency} efficiency)")

        return result

    except Exception as e:
        print(f"❌ Error in batch trivia generation: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "generated": 0, "error": str(e)}


# Export list for proper module interface
__all__ = [
    'call_ai_with_rate_limiting',
    'filter_ai_response',
    'generate_ai_trivia_question',
    'generate_trivia_batch',  # NEW: Phase 2 batch generation
    'create_ai_announcement_content',
    'initialize_ai',
    'initialize_ai_async',
    'safe_initialize_ai',
    'safe_initialize_ai_async',
    'get_ai_status',
    'reset_daily_usage',
    'ai_enabled',
    'ai_status_message',
    'primary_ai',
    'backup_ai',
    'ai_usage_stats'
]
