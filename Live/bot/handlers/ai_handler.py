"""
AI Handler Module

Handles AI integration, rate limiting, and response processing for the Discord bot.
Supports both Gemini and Hugging Face APIs with automatic fallback functionality.
"""

import json
import logging
import os
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
from ..database import get_database
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


# Get database instance
db = get_database()  # type: ignore

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
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    GENAI_AVAILABLE = False

# AI Configuration
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')

# Gemini model cascade configuration (priority order)
# These models are tested on startup and used with automatic fallback
GEMINI_MODEL_CASCADE = [
    'gemini-2.5-flash',       # Primary: Latest, fastest
    'gemini-2.0-flash-001',   # Backup: Stable version
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
    1. Special User IDs (hardcoded personalities) - Jonesy, JAM, Pops
    2. Alias Override (for testing) - checks user_alias_state
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

    # TIER 1: Special User ID Overrides (highest priority)
    # These override everything else - even if they're in a DM or have different roles
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

    # TIER 2: Alias Override Check (for testing)
    try:
        from ..utils.permissions import cleanup_expired_aliases, user_alias_state
        cleanup_expired_aliases()

        if user_id in user_alias_state:
            alias_type = user_alias_state[user_id].get("alias_type", "standard")

            # Map alias types to context
            alias_context_map = {
                "captain": {
                    'user_name': f'{member_obj.display_name if member_obj else "User"} (Testing as Captain)',
                    'user_roles': ['Captain', 'Owner'],
                    'clearance_level': 'COMMANDING_OFFICER',
                    'relationship_type': 'COMMANDING_OFFICER',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_captain'
                },
                "creator": {
                    'user_name': f'{member_obj.display_name if member_obj else "User"} (Testing as Creator)',
                    'user_roles': ['Creator', 'Admin'],
                    'clearance_level': 'CREATOR',
                    'relationship_type': 'CREATOR',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_creator'
                },
                "moderator": {
                    'user_name': f'{member_obj.display_name if member_obj else "User"} (Testing as Moderator)',
                    'user_roles': ['Moderator', 'Staff'],
                    'clearance_level': 'MODERATOR',
                    'relationship_type': 'COLLEAGUE',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_moderator'
                },
                "member": {
                    'user_name': f'{member_obj.display_name if member_obj else "User"} (Testing as Member)',
                    'user_roles': ['Member', 'Crew'],
                    'clearance_level': 'STANDARD_MEMBER',
                    'relationship_type': 'PERSONNEL',
                    'is_pops_arcade': False,
                    'detection_method': 'alias_override_member'
                },
                "standard": {
                    'user_name': f'{member_obj.display_name if member_obj else "User"} (Testing as Standard)',
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


async def call_ai_with_rate_limiting(
        prompt: str, user_id: int, context: str = "", member_obj=None, bot=None) -> Tuple[Optional[str], str]:
    """
    Make an AI call with proper rate limiting and error handling.

    Args:
        prompt: The prompt text to send to AI
        user_id: Discord user ID
        context: Context string for priority/logging
        member_obj: Discord Member object (for role detection)
        bot: Bot instance (for DM member lookup)

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
        from ..utils.permissions import cleanup_expired_aliases, update_alias_activity, user_alias_state

        # Improved alias rate limiting with better UX
        cleanup_expired_aliases()
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
                    "max_output_tokens": 1000,  # Increased to allow complete responses (~750 words)
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
                    system_instruction = _build_full_system_instruction(user_id, prompt, member_obj, bot)

                    # For now, include system instruction in the prompt
                    full_prompt = f"{system_instruction}\n\nUser: {prompt}"

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
        import traceback
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
        import traceback
        traceback.print_exc()
        return []


def _build_full_system_instruction(user_id: int, user_input: str = "", member_obj=None, bot=None) -> str:
    """
    Build complete system instruction with dynamic context using role detection system.

    Args:
        user_id: Discord user ID
        user_input: User's message (for simulate_pops detection)
        member_obj: Discord Member object (optional, for role detection)
        bot: Bot instance (optional, for DM member lookup)

    Returns:
        Complete system instruction with persona and context
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
                # TIER 2: Check alias state
                try:
                    from ..utils.permissions import cleanup_expired_aliases, user_alias_state
                    cleanup_expired_aliases()

                    if user_id in user_alias_state:
                        alias_type = user_alias_state[user_id].get("alias_type", "standard")
                        alias_name = member_obj.display_name if member_obj else "User"

                        alias_map = {
                            "captain": {
                                'user_name': f'{alias_name} (Testing as Captain)',
                                'clearance_level': 'COMMANDING_OFFICER',
                                'relationship_type': 'COMMANDING_OFFICER'},
                            "creator": {
                                'user_name': f'{alias_name} (Testing as Creator)',
                                'clearance_level': 'CREATOR',
                                'relationship_type': 'CREATOR'},
                            "moderator": {
                                'user_name': f'{alias_name} (Testing as Moderator)',
                                'clearance_level': 'MODERATOR',
                                'relationship_type': 'COLLEAGUE'},
                            "member": {
                                'user_name': f'{alias_name} (Testing as Member)',
                                'clearance_level': 'STANDARD_MEMBER',
                                'relationship_type': 'PERSONNEL'},
                            "standard": {
                                'user_name': f'{alias_name} (Testing as Standard)',
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
                        else:
                            raise ValueError("Unknown alias type")
                    else:
                        # No alias, use role detection
                        raise ImportError  # Fall through to role detection

                except (ImportError, ValueError):
                    # TIER 3-5: Discord role detection (synchronous version)
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
                                # Default
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

        # Combine base system instruction with dynamic context
        full_instruction = f"{ASH_SYSTEM_INSTRUCTION}\n\n{dynamic_context}"

        return full_instruction

    except Exception as e:
        print(f"⚠️ Error building system instruction: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to base instruction only
        return ASH_SYSTEM_INSTRUCTION


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

    # Limit to maximum 4 sentences for conciseness
    final_sentences = final_sentences[:4]

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
    """Get diverse question templates organized by category - now with more engaging varieties!"""
    return {
        "playtime_champion": [
            {
                "template": "What game has Jonesy spent the most time playing?",
                "answer_logic": "max_playtime",
                "type": "single_answer",
                "weight": 2.0  # Highest weight - most common interpretation of "most played"
            },
            {
                "template": "Which game has the highest total playtime in Jonesy's collection?",
                "answer_logic": "max_playtime",
                "type": "single_answer",
                "weight": 1.9
            },
            {
                "template": "What's Jonesy's most played game by time spent?",
                "answer_logic": "max_playtime",
                "type": "single_answer",
                "weight": 1.8
            }
        ],
        "genre_adventures": [
            {
                "template": "What horror game did Jonesy play most recently?",
                "answer_logic": "latest_genre_game",
                "type": "single_answer",
                "weight": 1.8,  # High weight - very engaging
                "genre_filter": "horror"
            },
            {
                "template": "Which RPG took Jonesy the most episodes to complete?",
                "answer_logic": "longest_episodes_by_genre",
                "type": "single_answer",
                "weight": 1.6,
                "genre_filter": "rpg"
            },
            {
                "template": "How many different horror games has Jonesy played?",
                "answer_logic": "count_games_by_genre",
                "type": "single_answer",
                "weight": 1.5,
                "genre_filter": "horror"
            }
        ],
        "gaming_milestones": [
            {
                "template": "Which was Jonesy's first completed game?",
                "answer_logic": "first_completed_game",
                "type": "single_answer",
                "weight": 1.9  # Very interesting milestone
            },
            {
                "template": "What's the shortest game Jonesy has completed?",
                "answer_logic": "shortest_completed_game",
                "type": "single_answer",
                "weight": 1.7
            },
            {
                "template": "Which game did Jonesy abandon after the fewest episodes?",
                "answer_logic": "earliest_dropped_game",
                "type": "single_answer",
                "weight": 1.4
            }
        ],
        "series_explorer": [
            {
                "template": "How many games has Jonesy played in the {series} series?",
                "answer_logic": "count_series_games",
                "type": "single_answer",
                "weight": 1.6
            },
            {
                "template": "Which series has Jonesy spent the most time playing?",
                "answer_logic": "series_most_time",
                "type": "single_answer",
                "weight": 1.5
            },
            {
                "template": "What's the largest game series in Jonesy's collection?",
                "answer_logic": "largest_series",
                "type": "single_answer",
                "weight": 1.3
            }
        ],
        "gaming_stories": [
            {
                "template": "What game took Jonesy the most episodes to finish?",
                "answer_logic": "max_episodes",
                "type": "single_answer",
                "weight": 1.2  # Improved weight, more story-focused phrasing
            },
            {
                "template": "Which completed game had Jonesy's longest individual episodes?",
                "answer_logic": "longest_avg_episode_completed",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "What's the most recent game Jonesy completed?",
                "answer_logic": "most_recent_completion",
                "type": "single_answer",
                "weight": 1.6
            }
        ],
        "timeline_fun": [
            {
                "template": "Which game did Jonesy complete first - {game1} or {game2}?",
                "answer_logic": "compare_completion_order",
                "type": "single_answer",
                "weight": 1.5
            },
            {
                "template": "Did Jonesy play {game1} before or after {game2}?",
                "answer_logic": "compare_play_order",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "Which came first in Jonesy's gaming journey - {game1} or {game2}?",
                "answer_logic": "compare_first_played",
                "type": "single_answer",
                "weight": 1.3
            }
        ],
        "fun_facts": [
            {
                "template": "What percentage of Jonesy's games are completed?",
                "answer_logic": "completion_percentage",
                "type": "single_answer",
                "weight": 1.4  # More engaging phrasing
            },
            {
                "template": "How many different genres has Jonesy explored?",
                "answer_logic": "unique_genres_count",
                "type": "single_answer",
                "weight": 1.7
            },
            {
                "template": "What's Jonesy's most played genre?",
                "answer_logic": "most_common_genre",
                "type": "single_answer",
                "weight": 1.5
            }
        ],
        "multiple_choice_fun": [
            {
                "template": "Which of these games did Jonesy complete?",
                "answer_logic": "mc_completed_game",
                "type": "multiple_choice",
                "weight": 1.8  # Very engaging
            },
            {
                "template": "Which horror game has Jonesy played?",
                "answer_logic": "mc_genre_game",
                "type": "multiple_choice",
                "weight": 1.7,
                "genre_filter": "horror"
            },
            {
                "template": "Which of these is a series Jonesy has explored?",
                "answer_logic": "mc_series_played",
                "type": "multiple_choice",
                "weight": 1.6
            }
        ],
        # Keep some of the old ones with reduced weights
        "legacy_stats": [
            {
                "template": "Which game took the longest to complete?",
                "answer_logic": "max_playtime",
                "type": "single_answer",
                "weight": 0.2  # Very low weight - legacy/backup
            },
            {
                "template": "What game has the most episodes?",
                "answer_logic": "max_episodes",
                "type": "single_answer",
                "weight": 0.3  # Low weight - backup only
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


async def generate_ai_trivia_question(context: str = "trivia") -> Optional[Dict[str, Any]]:
    """Generate a diverse trivia question using template-based system with AI fallback"""
    if not ai_enabled:
        print("❌ AI not enabled for trivia question generation")
        return None

    # Check if database is available
    if db is None:
        print("❌ Database not available for AI trivia generation")
        return None

    try:
        print(f"🧠 Generating diverse trivia question with context: {context}")

        # Get all available games data
        all_games = db.get_all_played_games()

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
                        duplicate_info = db.check_question_duplicate(
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
        stats = db.get_played_games_stats()
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

        content_prompt = f"""Generate a trivia question about Captain Jonesy's gaming experiences. Use your analytical voice but be CONCISE - minimal preamble, direct question delivery.

CRITICAL TERMINOLOGY - READ CAREFULLY:
⚠️ "most played" = game with HIGHEST total_playtime_minutes (time spent playing)
⚠️ "most episodes" = game with MOST episode count (number of episodes)
⚠️ These are DIFFERENT metrics! Episode count ≠ playtime!

DATABASE SCHEMA:
- total_playtime_minutes: Actual time spent playing in minutes (THIS IS "MOST PLAYED")
- total_episodes: Number of recorded episodes

AVOID these overused categories: {avoid_categories}

PREFERRED QUESTION TYPES (pick one):
🎮 **Genre Adventures**: "What horror game did Jonesy play most recently?"
🏆 **Gaming Milestones**: "Which was Jonesy's first completed RPG?"
📚 **Series Explorer**: "How many Resident Evil games has Jonesy played?"
🎯 **Gaming Stories**: "What game took Jonesy the most episodes to finish?" (use "episodes" not "played")
🕐 **Timeline Fun**: "Which game did Jonesy complete first - [Game A] or [Game B]?"
⭐ **Playtime Champion**: "What game has Jonesy spent the most time playing?" (use "time" for playtime)

AVAILABLE GAMES: {game_context}
Total games: {stats.get('total_games', 0)}

CRITICAL: Keep the question CONCISE. Use your analytical voice but avoid lengthy preambles or game lists. A brief greeting like "Personnel, analysis indicates:" followed by a direct question is ideal.

GOOD EXAMPLES:
✅ "Personnel, what game has Jonesy spent the most time playing?" (uses playtime)
✅ "What game took Jonesy the most episodes to complete?" (uses episode count)
❌ "What is Jonesy's most played game?" (AMBIGUOUS - specify time OR episodes)

RETURN ONLY JSON:
{{
    "question_text": "Your concise, direct question with minimal preamble",
    "question_type": "single_answer",
    "correct_answer": "The answer",
    "is_dynamic": false,
    "category": "ai_generated"
}}

Focus on direct questions about Captain Jonesy's gaming journey - no verbose analysis."""

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
                    duplicate_info = db.check_question_duplicate(
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
        import traceback
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
    """Async initialize AI providers with model cascade (Phase 2)"""
    global ai_enabled, ai_status_message, primary_ai, backup_ai

    print("🤖 Starting async AI initialization with model cascade...")

    try:
        # Initialize Gemini with model cascade testing
        if GEMINI_API_KEY and GENAI_AVAILABLE and genai:
            # New SDK doesn't need configure() - models are created with API key directly
            gemini_ok = await initialize_gemini_models()

            if gemini_ok:
                primary_ai = "gemini"
                model_info = f"{current_gemini_model}"
                if len(working_gemini_models) > 1:
                    model_info += f" (+ {len(working_gemini_models)-1} backup)"
                print(f"✅ Gemini AI initialized: {model_info}")
            else:
                print("❌ No working Gemini models found")
        else:
            gemini_ok = False
            print("⚠️ Gemini AI not available - missing API key or module")

        # Set AI status
        if gemini_ok:
            primary_ai = "gemini"
            ai_enabled = True
            if backup_ai:
                ai_status_message = f"Online ({primary_ai.title()} + {backup_ai.title()} backup)"
            else:
                model_count = f" ({len(working_gemini_models)} models)" if working_gemini_models else ""
                ai_status_message = f"Online ({primary_ai.title()}{model_count})"
            print(f"✅ AI initialization complete: {ai_status_message}")
        else:
            ai_status_message = "No AI available"
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
    try:
        await initialize_ai_async()
        return True
    except Exception as e:
        print(f"⚠️ Safe async AI initialization caught error: {e}")
        global ai_enabled, ai_status_message
        ai_enabled = False
        ai_status_message = "Async AI initialization failed (safe mode)"
        return False


# Export list for proper module interface
__all__ = [
    'call_ai_with_rate_limiting',
    'filter_ai_response',
    'generate_ai_trivia_question',
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
