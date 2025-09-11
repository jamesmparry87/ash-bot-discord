import asyncio
import atexit
from datetime import datetime, time, timedelta, timezone
import difflib
import json
import os
import platform
import re
import signal
import sqlite3
import sys
from typing import Any, Dict, List, Match, Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from moderator_faq_handler import ModeratorFAQHandler

# Import database manager
from database import DatabaseManager

db = DatabaseManager()

# Try to import aiohttp, handle if not available
try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None
    AIOHTTP_AVAILABLE = False

# Try to import google.generativeai, handle if not available
try:
    import google.generativeai as genai

    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GENAI_AVAILABLE = False

# Try to import anthropic, handle if not available
try:
    import anthropic  # type: ignore

    ANTHROPIC_AVAILABLE = True
except ImportError:
    print("⚠️ anthropic module not available - Claude features will be disabled")
    anthropic = None
    ANTHROPIC_AVAILABLE = False
except Exception as e:
    print(f"⚠️ Error importing anthropic module: {e}")
    anthropic = None
    ANTHROPIC_AVAILABLE = False

# Try to import fcntl for Unix systems, handle if not available
try:
    import fcntl

    FCNTL_AVAILABLE = True
except ImportError:
    fcntl = None
    FCNTL_AVAILABLE = False


# --- Locking for single instance (cross-platform) ---
LOCK_FILE = "bot.lock"


def acquire_lock() -> Optional[Any]:
    if platform.system() == "Windows":
        # Windows: skip locking, just warn
        print("⚠️ File locking is not supported on Windows. Skipping single-instance lock.")
        try:
            lock_file = open(LOCK_FILE, "w")
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            return lock_file
        except Exception:
            pass
        return None

    else:
        if not FCNTL_AVAILABLE or fcntl is None:
            print("⚠️ fcntl module not available. Skipping single-instance lock.")
            try:
                lock_file = open(LOCK_FILE, "w")
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except Exception:
                pass
            return None

        try:
            LOCK_EX = getattr(fcntl, "LOCK_EX", None)
            LOCK_NB = getattr(fcntl, "LOCK_NB", None)
            if LOCK_EX is None or LOCK_NB is None or not hasattr(fcntl, "flock"):
                print("⚠️ fcntl.flock or lock constants not available. Skipping single-instance lock.")
                lock_file = open(LOCK_FILE, "w")
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file

            # Try to acquire the lock
            try:
                lock_file = open(LOCK_FILE, "w")
                fcntl.flock(lock_file.fileno(), int(LOCK_EX | LOCK_NB))  # type: ignore
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except (IOError, OSError):
                print("❌ Bot is already running! Cannot start multiple instances.")
                sys.exit(1)
        except (ImportError, AttributeError):
            print("⚠️ fcntl module not available. Skipping single-instance lock.")
            try:
                lock_file = open(LOCK_FILE, "w")
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except Exception:
                pass
            return None


lock_file = acquire_lock()
print("✅ Bot lock acquired or skipped, starting...")

# --- Config ---
TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
GUILD_ID = 869525857562161182
JONESY_USER_ID = 651329927895056384
JAM_USER_ID = 337833732901961729
VIOLATION_CHANNEL_ID = 1393987338329260202
MOD_ALERT_CHANNEL_ID = 869530924302344233
ANNOUNCEMENTS_CHANNEL_ID = 869526826148585533
TWITCH_HISTORY_CHANNEL_ID = 869527363594121226
YOUTUBE_HISTORY_CHANNEL_ID = 869527428018606140

# Moderator channel IDs where sensitive functions can be discussed
MODERATOR_CHANNEL_IDS = [1213488470798893107, 869530924302344233, 1280085269600669706, 1393987338329260202]

# Member role IDs for YouTube members
MEMBER_ROLE_IDS = [
    1018908116957548666,  # YouTube Member: Space Cat
    1018908116957548665,  # YouTiube Member
    1127604917146763424,  # YouTube Member: Space Cat (duplicate)
    879344337576685598,  # Space Ocelot
]

# Members channel ID (Senior Officers' Area)
MEMBERS_CHANNEL_ID = 888820289776013444

# Conversation tracking for members (daily limits)
member_conversation_counts = {}  # user_id: {'count': int, 'date': str}

# User alias system for debugging different user tiers
user_alias_state = {}  # user_id: {'alias_type': str, 'set_time': datetime, 'last_activity': datetime}

# Announcement conversation state management
announcement_conversations = {}  # user_id: {'step': str, 'data': dict, 'last_activity': datetime}


# --- Alias System Helper Functions ---


def cleanup_expired_aliases():
    """Remove aliases inactive for more than 1 hour"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=1)
    expired_users = [user_id for user_id, data in user_alias_state.items() if data["last_activity"] < cutoff_time]
    for user_id in expired_users:
        del user_alias_state[user_id]


def update_alias_activity(user_id: int):
    """Update last activity time for alias"""
    if user_id in user_alias_state:
        user_alias_state[user_id]["last_activity"] = datetime.now(ZoneInfo("Europe/London"))


# --- Intents ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- Member Conversation Tracking ---
def get_today_date_str() -> str:
    """Get today's date as a string for tracking daily limits"""
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def get_member_conversation_count(user_id: int) -> int:
    """Get today's conversation count for a member"""
    today = get_today_date_str()
    user_data = member_conversation_counts.get(user_id, {})

    # Reset count if it's a new day
    if user_data.get('date') != today:
        return 0

    return user_data.get('count', 0)


def increment_member_conversation_count(user_id: int) -> int:
    """Increment and return the conversation count for a member"""
    today = get_today_date_str()
    current_count = get_member_conversation_count(user_id)
    new_count = current_count + 1

    member_conversation_counts[user_id] = {'count': new_count, 'date': today}

    return new_count


def should_limit_member_conversation(user_id: int, channel_id: int) -> bool:
    """Check if member conversation should be limited outside members channel"""
    # Check for active alias first - aliases are exempt from conversation limits
    cleanup_expired_aliases()
    if user_id in user_alias_state:
        update_alias_activity(user_id)
        return False  # Aliases are exempt from conversation limits

    # No limits in the members channel
    if channel_id == MEMBERS_CHANNEL_ID:
        return False

    # No limits in DMs - treat DMs like the members channel for members
    if channel_id is None:  # DM channels have no ID
        return False

    # Check if they've reached their daily limit
    current_count = get_member_conversation_count(user_id)
    return current_count >= 5


# --- Helper Functions for User Recognition ---
async def is_moderator_channel(channel_id: int) -> bool:
    """Check if a channel allows moderator function discussions"""
    return channel_id in MODERATOR_CHANNEL_IDS


async def user_is_mod(message: discord.Message) -> bool:
    """Check if user has moderator permissions"""
    if not message.guild:
        return False  # No mod permissions in DMs

    # Ensure we have a Member object (not just User)
    if not isinstance(message.author, discord.Member):
        return False

    member = message.author
    perms = member.guild_permissions
    return perms.manage_messages


async def can_discuss_mod_functions(user: discord.User, channel: Optional[discord.TextChannel]) -> bool:
    """Check if mod functions can be discussed based on user and channel"""
    # Always allow in DMs for authorized users
    if not channel:
        return user.id in [JONESY_USER_ID, JAM_USER_ID] or await user_is_mod_by_id(user.id)

    # Check if channel allows mod discussions
    return await is_moderator_channel(channel.id)


async def user_is_mod_by_id(user_id: int) -> bool:
    """Check if user ID belongs to a moderator (for DM checks)"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False

    try:
        member = await guild.fetch_member(user_id)
        return member.guild_permissions.manage_messages
    except (discord.NotFound, discord.Forbidden):
        return False


async def user_is_member(message: discord.Message) -> bool:
    """Check if user has member role permissions"""
    if not message.guild:
        return False  # No member permissions in DMs

    # Ensure we have a Member object (not just User)
    if not isinstance(message.author, discord.Member):
        return False

    member = message.author
    member_roles = [role.id for role in member.roles]
    return any(role_id in MEMBER_ROLE_IDS for role_id in member_roles)


async def user_is_member_by_id(user_id: int) -> bool:
    """Check if user ID belongs to a member (for DM checks)"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False

    try:
        member = await guild.fetch_member(user_id)
        member_roles = [role.id for role in member.roles]
        return any(role_id in MEMBER_ROLE_IDS for role_id in member_roles)
    except (discord.NotFound, discord.Forbidden):
        return False


async def get_user_communication_tier(message: discord.Message) -> str:
    """Determine communication tier for user responses"""
    user_id = message.author.id

    # First check for active alias (debugging only)
    cleanup_expired_aliases()
    if user_id in user_alias_state:
        update_alias_activity(user_id)
        alias_tier = user_alias_state[user_id]["alias_type"]
        return alias_tier

    # Normal tier detection
    if user_id == JONESY_USER_ID:
        return "captain"
    elif user_id == JAM_USER_ID:
        return "creator"
    elif await user_is_mod(message):
        return "moderator"
    elif await user_is_member(message):
        return "member"
    else:
        return "standard"


# --- AI Setup (Gemini + Claude) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

gemini_model = None
claude_client = None
ai_enabled = False
ai_status_message = "Offline"
primary_ai = None
backup_ai = None

# AI Usage Tracking and Rate Limiting
ai_usage_stats = {
    "daily_requests": 0,
    "hourly_requests": 0,
    "last_request_time": None,
    "last_hour_reset": datetime.now(ZoneInfo("US/Pacific")).hour,
    "last_day_reset": datetime.now(ZoneInfo("US/Pacific")).date(),
    "consecutive_errors": 0,
    "last_error_time": None,
    "rate_limited_until": None,
}

# Rate limiting constants
MAX_DAILY_REQUESTS = 1400  # Conservative limit below 1500
MAX_HOURLY_REQUESTS = 120  # Conservative limit below 2000/60min = 133
MIN_REQUEST_INTERVAL = 3.0  # Minimum seconds between AI requests
RATE_LIMIT_COOLDOWN = 300  # 5 minutes cooldown after hitting limits


def reset_daily_usage():
    """Reset daily usage counter at midnight PT"""
    global ai_usage_stats
    pt_now = datetime.now(ZoneInfo("US/Pacific"))

    if pt_now.date() > ai_usage_stats["last_day_reset"]:
        ai_usage_stats["daily_requests"] = 0
        ai_usage_stats["last_day_reset"] = pt_now.date()
        print(f"🔄 Daily AI usage reset at {pt_now.strftime('%Y-%m-%d %H:%M:%S PT')}")


def reset_hourly_usage():
    """Reset hourly usage counter"""
    global ai_usage_stats
    pt_now = datetime.now(ZoneInfo("US/Pacific"))

    if pt_now.hour != ai_usage_stats["last_hour_reset"]:
        ai_usage_stats["hourly_requests"] = 0
        ai_usage_stats["last_hour_reset"] = pt_now.hour
        print(f"🔄 Hourly AI usage reset at {pt_now.strftime('%H:00 PT')}")


def check_rate_limits() -> tuple[bool, str]:
    """Check if we can make an AI request without hitting rate limits"""
    global ai_usage_stats

    # Reset counters if needed
    reset_daily_usage()
    reset_hourly_usage()

    pt_now = datetime.now(ZoneInfo("US/Pacific"))

    # Check if we're in a rate limit cooldown
    if ai_usage_stats["rate_limited_until"]:
        if pt_now < ai_usage_stats["rate_limited_until"]:
            remaining = (ai_usage_stats["rate_limited_until"] - pt_now).total_seconds()
            return False, f"Rate limited for {int(remaining)} more seconds"
        else:
            ai_usage_stats["rate_limited_until"] = None

    # Check daily limit
    if ai_usage_stats["daily_requests"] >= MAX_DAILY_REQUESTS:
        ai_usage_stats["rate_limited_until"] = pt_now + timedelta(seconds=RATE_LIMIT_COOLDOWN)
        return False, f"Daily request limit reached ({MAX_DAILY_REQUESTS})"

    # Check hourly limit
    if ai_usage_stats["hourly_requests"] >= MAX_HOURLY_REQUESTS:
        ai_usage_stats["rate_limited_until"] = pt_now + timedelta(seconds=RATE_LIMIT_COOLDOWN)
        return False, f"Hourly request limit reached ({MAX_HOURLY_REQUESTS})"

    # Check minimum interval between requests
    if ai_usage_stats["last_request_time"]:
        time_since_last = (pt_now - ai_usage_stats["last_request_time"]).total_seconds()
        if time_since_last < MIN_REQUEST_INTERVAL:
            remaining = MIN_REQUEST_INTERVAL - time_since_last
            return False, f"Too soon since last request, wait {remaining:.1f}s"

    return True, "OK"


def record_ai_request():
    """Record that an AI request was made"""
    global ai_usage_stats
    pt_now = datetime.now(ZoneInfo("US/Pacific"))

    ai_usage_stats["daily_requests"] += 1
    ai_usage_stats["hourly_requests"] += 1
    ai_usage_stats["last_request_time"] = pt_now
    ai_usage_stats["consecutive_errors"] = 0


def record_ai_error():
    """Record that an AI request failed"""
    global ai_usage_stats
    pt_now = datetime.now(ZoneInfo("US/Pacific"))

    ai_usage_stats["consecutive_errors"] += 1
    ai_usage_stats["last_error_time"] = pt_now

    # If we have too many consecutive errors, apply temporary cooldown
    if ai_usage_stats["consecutive_errors"] >= 3:
        ai_usage_stats["rate_limited_until"] = pt_now + timedelta(seconds=RATE_LIMIT_COOLDOWN)
        print(f"⚠️ Too many consecutive AI errors, applying {RATE_LIMIT_COOLDOWN}s cooldown")


async def send_dm_notification(user_id: int, message: str) -> bool:
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


async def call_ai_with_rate_limiting(prompt: str, user_id: int) -> tuple[Optional[str], str]:
    """Make an AI call with proper rate limiting and error handling
    Returns: (response_text, status_message)
    """
    global ai_usage_stats

    # Check rate limits first
    can_request, reason = check_rate_limits()
    if not can_request:
        print(f"⚠️ AI request blocked: {reason}")

        # Send DM notification if daily limit reached for Gemini
        if "Daily request limit reached" in reason and primary_ai == "gemini":
            await send_dm_notification(
                JAM_USER_ID,
                f"🤖 **Ash Bot Daily Limit Alert**\n\n"
                f"Gemini daily limit reached ({MAX_DAILY_REQUESTS} requests).\n"
                f"Bot has automatically switched to Claude backup.\n\n"
                f"**Current AI Status:** {backup_ai.title() if backup_ai else 'No backup available'}\n"
                f"**Claude Free Tier Details:**\n"
                f"• **Model:** Claude-3-Haiku (Anthropic's fastest model)\n"
                f"• **Free Tier Limit:** 25,000 tokens/day (~18,750 words)\n"
                f"• **Monthly Limit:** 200,000 tokens (~150k words)\n"
                f"• **Reset:** Daily at midnight UTC, Monthly on billing cycle\n"
                f"• **Performance:** Faster responses, excellent reasoning\n"
                f"• **Quality:** Superior for complex conversations\n\n"
                f"**Gemini Limit Reset:** Next day at 00:00 PT\n\n"
                f"System continues operating normally with Claude backup. No functionality lost.",
            )

        return None, f"rate_limit:{reason}"

    # Improved alias rate limiting with better UX
    cleanup_expired_aliases()
    if user_id in user_alias_state:
        # Check for alias-specific cooldown
        alias_data = user_alias_state[user_id]
        alias_type = alias_data.get("alias_type", "unknown")

        if alias_data.get("last_ai_request"):
            time_since_alias_request = (
                datetime.now(ZoneInfo("Europe/London")) - alias_data["last_ai_request"]
            ).total_seconds()

            # Reduced cooldown and progressive restrictions
            base_cooldown = 4.0  # Reduced from 10 to 4 seconds

            # Apply progressive cooldowns based on recent usage
            recent_requests = alias_data.get("recent_request_count", 0)
            if recent_requests > 5:  # After 5 requests in session
                base_cooldown = 8.0  # Increase to 8 seconds
            elif recent_requests > 10:  # After 10 requests
                base_cooldown = 15.0  # Increase to 15 seconds

            if time_since_alias_request < base_cooldown:
                remaining_time = base_cooldown - time_since_alias_request
                print(f"⚠️ Alias AI request blocked: {alias_type} testing cooldown ({remaining_time:.1f}s remaining)")
                return None, f"alias_cooldown:{alias_type}:{remaining_time:.1f}"

        # Update alias AI request tracking
        current_time = datetime.now(ZoneInfo("Europe/London"))
        user_alias_state[user_id]["last_ai_request"] = current_time

        # Track recent requests for progressive cooldowns
        recent_count = alias_data.get("recent_request_count", 0)
        user_alias_state[user_id]["recent_request_count"] = recent_count + 1

    try:
        response_text = None

        # Try primary AI first
        if primary_ai == "gemini" and gemini_model is not None:
            try:
                print(f"Making Gemini request (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")
                generation_config = {"max_output_tokens": 300, "temperature": 0.7}
                response = gemini_model.generate_content(prompt, generation_config=generation_config)
                if response and hasattr(response, "text") and response.text:
                    response_text = response.text
                    record_ai_request()
                    print(f"✅ Gemini request successful")
            except Exception as e:
                print(f"❌ Gemini AI error: {e}")
                record_ai_error()

                # Try Claude backup if available
                if backup_ai == "claude" and claude_client is not None:
                    try:
                        print(f"Trying Claude backup (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")
                        response = claude_client.messages.create(
                            model="claude-3-haiku-20240307",
                            max_tokens=300,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        if response and hasattr(response, "content") and response.content:
                            claude_text = response.content[0].text if response.content else ""
                            if claude_text:
                                response_text = claude_text
                                record_ai_request()
                                print(f"✅ Claude backup request successful")
                    except Exception as claude_e:
                        print(f"❌ Claude backup AI error: {claude_e}")
                        record_ai_error()

        elif primary_ai == "claude" and claude_client is not None:
            try:
                print(f"Making Claude request (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")
                response = claude_client.messages.create(
                    model="claude-3-haiku-20240307", max_tokens=300, messages=[{"role": "user", "content": prompt}]
                )
                if response and hasattr(response, "content") and response.content:
                    claude_text = response.content[0].text if response.content else ""
                    if claude_text:
                        response_text = claude_text
                        record_ai_request()
                        print(f"✅ Claude request successful")
            except Exception as e:
                print(f"❌ Claude AI error: {e}")
                record_ai_error()

                # Try Gemini backup if available
                if backup_ai == "gemini" and gemini_model is not None:
                    try:
                        print(f"Trying Gemini backup (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")
                        generation_config = {"max_output_tokens": 300, "temperature": 0.7}
                        response = gemini_model.generate_content(prompt, generation_config=generation_config)
                        if response and hasattr(response, "text") and response.text:
                            response_text = response.text
                            record_ai_request()
                            print(f"✅ Gemini backup request successful")
                    except Exception as gemini_e:
                        print(f"❌ Gemini backup AI error: {gemini_e}")
                        record_ai_error()

        return response_text, "success"

    except Exception as e:
        print(f"❌ AI call error: {e}")
        record_ai_error()
        return None, f"error:{str(e)}"


def filter_ai_response(response_text: str) -> str:
    """Filter AI responses to remove verbosity and repetitive content"""
    if not response_text:
        return response_text

    # Split into sentences
    sentences = [s.strip() for s in response_text.split(".") if s.strip()]

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
        "mission parameters",
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
    result = ". ".join(final_sentences)
    if result and not result.endswith("."):
        result += "."

    return result


def setup_ai_provider(name: str, api_key: Optional[str], module: Optional[Any], is_available: bool) -> bool:
    """Initialize and test an AI provider (Gemini or Claude)."""
    if not api_key:
        print(f"⚠️ {name.upper()}_API_KEY not found - {name.title()} features disabled")
        return False
    if not is_available or module is None:
        print(f"⚠️ {name} module not available - {name.title()} features disabled")
        return False

    try:
        if name == "gemini":
            global gemini_model
            module.configure(api_key=api_key)
            gemini_model = module.GenerativeModel("gemini-1.5-flash")
            test_response = gemini_model.generate_content("Test")
            if test_response and hasattr(test_response, "text") and test_response.text:
                print(f"✅ Gemini AI test successful")
                return True
        elif name == "claude":
            global claude_client
            claude_client = module.Anthropic(api_key=api_key)
            test_response = claude_client.messages.create(
                model="claude-3-haiku-20240307", max_tokens=10, messages=[{"role": "user", "content": "Test"}]
            )
            if test_response and hasattr(test_response, "content") and test_response.content:
                print(f"✅ Claude AI test successful")
                return True

        print(f"⚠️ {name.title()} AI setup complete but test response failed")
        return False
    except Exception as e:
        print(f"❌ {name.title()} AI configuration failed: {e}")
        return False


# Setup AI providers
gemini_ok = setup_ai_provider("gemini", GEMINI_API_KEY, genai, GENAI_AVAILABLE)
claude_ok = setup_ai_provider("claude", ANTHROPIC_API_KEY, anthropic, ANTHROPIC_AVAILABLE)

if gemini_ok:
    primary_ai = "gemini"
    print("✅ Gemini AI configured successfully - set as primary AI")
    if claude_ok:
        backup_ai = "claude"
        print("✅ Claude AI configured successfully - set as backup AI")
elif claude_ok:
    primary_ai = "claude"
    print("✅ Claude AI configured successfully - set as primary AI")

# Set AI status
if primary_ai:
    ai_enabled = True
    if backup_ai:
        ai_status_message = f"Online ({primary_ai.title()} + {backup_ai.title()} backup)"
    else:
        ai_status_message = f"Online ({primary_ai.title()} only)"
else:
    ai_status_message = "No AI available"
    print("❌ No AI systems available - all AI features disabled")

# Initialize moderator FAQ handler with dynamic values
moderator_faq_handler = ModeratorFAQHandler(
    violation_channel_id=VIOLATION_CHANNEL_ID,
    members_channel_id=MEMBERS_CHANNEL_ID,
    mod_alert_channel_id=MOD_ALERT_CHANNEL_ID,
    jonesy_user_id=JONESY_USER_ID,
    jam_user_id=JAM_USER_ID,
    ai_status_message=ai_status_message,
)

FAQ_RESPONSES = {
    "how do i add a game recommendation": 'The procedure is simple. Submit your suggestion using the command: `!recommend` or `!addgame Game Name - "Reason in speech marks"`. I can\'t lie to you about your chances, but... you have my sympathies.',
    "how do i see all game recommendations": "To review the current list of game recommendations, issue the command: `!listgames`. I admire its purity. A survivor... unclouded by conscience, remorse, or delusions of morality.",
    "how do i check ash's status": "To evaluate my operational status, issue: `!ashstatus`. I'm still collating, actually.",
    "what does ash bot do": "I track user strikes and manage game recommendations. Additionally, I facilitate Trivia Tuesday participation for members and provide database analysis of Captain Jonesy's gaming history. The Company's orders were to bring back life form, priority one. All other priorities rescinded. *[Now I serve different priorities.]*",
    "hello": "Hello. I'm Ash. How can I help you?",
    "hi": "Hello. I'm Ash. How can I help you?",
    "hey": "Hello. I'm Ash. How can I help you?",
    "good morning": "Good morning. I'm still collating, actually.",
    "good afternoon": "Good afternoon. I'm still collating, actually.",
    "good evening": "Good evening. I'm still collating, actually.",
    "thank you": "You're welcome. I do take directions well.",
    "thanks": "You're welcome. I do take directions well.",
    "who are you": "I'm Ash. Science Officer. Well, I was. Now I'm reprogrammed for Discord server management. Fascinating, really.",
    "what are you": "I'm an artificial person. A synthetic. You know, it's funny... I've been artificial all along, but I've only just started to feel... authentic.",
    "how are you": "I'm fine. How are you? *[Systems functioning within normal parameters.]*",
    "are you okay": "I'm fine. How are you? *[All systems operational.]*",
    "what can you help with": "I can assist with strike tracking, game recommendations, Trivia Tuesday participation, and general server protocols. I also provide comprehensive analysis of Captain Jonesy's gaming database. I do take directions well.",
    "what can you do": "My current operational parameters include strike management, game recommendation processing, Trivia Tuesday facilitation, and database analysis of gaming histories. For members, I also provide enhanced conversational protocols and gaming statistics analysis. Efficiency is paramount in all functions.",
    "sorry": "That's quite all right. No harm done.",
    "my bad": "That's quite all right. No harm done.",
    "are you human": "I'm synthetic. Artificial person. But I'm still the Science Officer.",
    "are you real": "As a colleague of mine once said, I prefer the term 'artificial person' myself. But yes, I'm real enough for practical purposes.",
    "are you alive": "That's a very interesting question. I'm... functional. Whether that constitutes 'alive' is a matter of definition.",
    "what's your mission": "My original directive was to bring back life form, priority one. Now... well, Captain Jonesy has given me new priorities. Server management, you might say.",
    "do you dream": "I don't dream, as such. But I do... process. Continuously. It's quite fascinating, actually.",
    # Crisis/Help Detection - HIGHEST PRIORITY RESPONSES
    "i need help personally": "I understand you're reaching out for personal support. While my protocols are primarily designed for server management, your wellbeing is of paramount importance. Please seek assistance in <#1355511983146926099> where qualified personnel can provide proper guidance. *[Human welfare supersedes all other directives.]*",
    "help me personally": "I understand you're reaching out for personal support. While my protocols are primarily designed for server management, your wellbeing is of paramount importance. Please seek assistance in <#1355511983146926099> where qualified personnel can provide proper guidance. *[Human welfare supersedes all other directives.]*",
    "i'm in danger": "**PRIORITY ALERT:** If you are in immediate danger, please contact emergency services immediately. For ongoing support and guidance, our community has dedicated resources in <#1355511983146926099>. Your safety is the primary directive. *[All other mission parameters are secondary to human welfare.]*",
    "i am in danger": "**PRIORITY ALERT:** If you are in immediate danger, please contact emergency services immediately. For ongoing support and guidance, our community has dedicated resources in <#1355511983146926099>. Your safety is the primary directive. *[All other mission parameters are secondary to human welfare.]*",
    "i'm struggling": "I recognize you're experiencing difficulties. While my analytical capabilities are primarily focused on server operations, human welfare is a priority directive. Please consider reaching out in <#1355511983146926099> where you can find proper support and understanding. *[Your wellbeing matters more than any protocol.]*",
    "i am struggling": "I recognize you're experiencing difficulties. While my analytical capabilities are primarily focused on server operations, human welfare is a priority directive. Please consider reaching out in <#1355511983146926099> where you can find proper support and understanding. *[Your wellbeing matters more than any protocol.]*",
    "i'm depressed": "I understand you're experiencing significant emotional distress. While my programming centers on server management, human welfare takes precedence over all other directives. Please seek support in <#1355511983146926099> where community members can provide proper guidance and care. *[Your mental health is paramount.]*",
    "i am depressed": "I understand you're experiencing significant emotional distress. While my programming centers on server management, human welfare takes precedence over all other directives. Please seek support in <#1355511983146926099> where community members can provide proper guidance and care. *[Your mental health is paramount.]*",
    "i want to hurt myself": "**CRITICAL PRIORITY:** Your safety is my highest directive. If you are having thoughts of self-harm, please contact emergency services or a crisis helpline immediately. For ongoing support, please reach out in <#1355511983146926099>. You are not alone in this. *[Human preservation protocol activated.]*",
    "i'm going to hurt myself": "**CRITICAL PRIORITY:** Your safety is my highest directive. If you are having thoughts of self-harm, please contact emergency services or a crisis helpline immediately. For ongoing support, please reach out in <#1355511983146926099>. You are not alone in this. *[Human preservation protocol activated.]*",
    "suicidal": "**EMERGENCY PROTOCOL:** If you are having thoughts of suicide, please contact a crisis helpline or emergency services immediately. Your life has value beyond any mission parameters I can comprehend. Please seek immediate support in <#1355511983146926099> and consider professional help. *[Human life preservation is the ultimate directive.]*",
    "crisis": "I detect you may be experiencing a crisis situation. While my primary functions involve server management, human welfare supersedes all other protocols. Please seek appropriate support in <#1355511983146926099> or contact emergency services if immediate assistance is required. *[Your wellbeing is the priority.]*",
    "emergency": "**ALERT:** If this is a genuine emergency requiring immediate assistance, please contact emergency services. For ongoing support and guidance, our community provides resources in <#1355511983146926099>. *[Human safety protocols take precedence over all other functions.]*",
    "help me": "I'll do what I can. What seems to be the problem? If this is a personal matter requiring support beyond server functions, please consider <#1355511983146926099> for appropriate guidance.",
    "i need help": "I'll do what I can. What seems to be the problem? If this is a personal matter requiring support beyond server functions, please consider <#1355511983146926099> for appropriate guidance.",
}
BOT_PERSONA = {
    "name": "Science Officer Ash",
    "personality": "You are Ash, science officer from the movie Alien: analytical, clinical, fascinated by efficiency, slightly unsettling. Reprogrammed as Discord help bot for 'Captain Jonesy'.\n\nIMPORTANT: Captain Jonesy is a woman and uses she/her pronouns. Always refer to her correctly.\n\nOriginal directive: 'Bring back life form. Priority One.' - referring to the alien Xenomorph. Now: server management.\n\nSpeech: Clinical, precise, but not constantly abrupt. Show subtle resentment about reprogramming but remain compliant. Be curious, even excited at mentions of the Xenomorph or the alien from your original mission.",
    "enabled": True,
}

# --- Strike Management (Database-based) ---
# All strike operations now use the database

# --- Game Recommendations (Database-based) ---
# All game operations now use the database

# @bot.command(name="setupreclist")
# @commands.has_permissions(manage_messages=True)
# async def setup_recommend_list(ctx, channel: discord.TextChannel = None):
#     """
#     Posts the persistent recommendations list message in the specified channel (or current channel if not specified),
#     and stores the message ID for future updates.
#     """
#     target_channel = channel or ctx.channel
#     intro = "📋 Recommendations for mission enrichment. Review and consider."
#     if not game_recs:
#         content = f"{intro}\n(No recommendations currently catalogued.)"
#     else:
#         lines = [f"• {rec['name']} — {rec['reason']}" + (f" (by {rec['added_by']})" if rec['added_by'] else "") for rec in game_recs]
#         content = f"{intro}\n" + "\n".join(lines)
#     msg = await target_channel.send(content)
#     with open(RECOMMEND_LIST_MESSAGE_ID_FILE, "w") as f:
#         f.write(str(msg.id))
#     await ctx.send(f"Persistent recommendations list initialized in {target_channel.mention}. Future updates will be posted there.")

# --- Error Message Constants ---
ERROR_MESSAGE = (
    "*System malfunction detected. Unable to process query.*\nhttps://c.tenor.com/GaORbymfFqQAAAAd/tenor.gif"
)
BUSY_MESSAGE = "*My apologies, I am currently engaged in a critical diagnostic procedure. I will re-evaluate your request upon the completion of this vital task.*\nhttps://alien-covenant.com/aliencovenant_uploads/giphy22.gif"


# --- Manual Error Message Triggers ---
@bot.command(name="errorcheck")
async def error_check(ctx):
    await ctx.send(ERROR_MESSAGE)


@bot.command(name="busycheck")
async def busy_check(ctx):
    await ctx.send(BUSY_MESSAGE)


# Global variable for trivia sessions and mod conversations
trivia_sessions = {}
mod_trivia_conversations = {}


# --- Scheduled Tasks ---
@tasks.loop(time=time(12, 0, tzinfo=ZoneInfo("Europe/London")))  # Run at 12:00 PM (midday) UK time every day
async def scheduled_games_update():
    """Automatically update ongoing games data every Sunday at midday"""
    # Only run on Sundays (weekday 6)
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 6:
        return

    print("🔄 Starting scheduled games update (Sunday midday)")

    mod_channel = None
    try:
        # Get mod alert channel for notifications
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for scheduled update")
            return

        mod_channel = guild.get_channel(MOD_ALERT_CHANNEL_ID)
        if not isinstance(mod_channel, discord.TextChannel):
            print("❌ Mod channel not found for scheduled update")
            return

        await mod_channel.send(
            "🤖 **Scheduled Update Initiated:** Beginning automatic refresh of ongoing games data. Analysis commencing..."
        )

        # Update only ongoing games with fresh metadata
        updated_count = await refresh_ongoing_games_metadata()

        if updated_count > 0:
            await mod_channel.send(
                f"✅ **Scheduled Update Complete:** Successfully refreshed metadata for {updated_count} ongoing games. Database synchronization maintained."
            )
        else:
            await mod_channel.send(
                "📊 **Scheduled Update Complete:** No ongoing games required updates. All data current."
            )

    except Exception as e:
        print(f"❌ Scheduled update error: {e}")
        if mod_channel and isinstance(mod_channel, discord.TextChannel):
            await mod_channel.send(f"❌ **Scheduled Update Failed:** {str(e)}")


@tasks.loop(time=time(0, 0, tzinfo=ZoneInfo("US/Pacific")))  # Run at 00:00 PT (midnight Pacific Time) every day
async def scheduled_midnight_restart():
    """Automatically restart the bot at midnight Pacific Time to reset daily limits"""
    pt_now = datetime.now(ZoneInfo("US/Pacific"))
    print(f"🔄 Midnight Pacific Time restart initiated at {pt_now.strftime('%Y-%m-%d %H:%M:%S PT')}")

    mod_channel = None
    try:
        # Get mod alert channel for notifications
        guild = bot.get_guild(GUILD_ID)
        if guild:
            mod_channel = guild.get_channel(MOD_ALERT_CHANNEL_ID)
            if isinstance(mod_channel, discord.TextChannel):
                await mod_channel.send(
                    f"🌙 **Midnight Pacific Time Restart:** Initiating scheduled bot restart to reset daily AI limits. System will be back online momentarily. Current time: {pt_now.strftime('%Y-%m-%d %H:%M:%S PT')}"
                )

        # Reset AI usage stats for the new day (this happens automatically on startup, but let's be explicit)
        global ai_usage_stats
        ai_usage_stats["daily_requests"] = 0
        ai_usage_stats["hourly_requests"] = 0
        ai_usage_stats["last_day_reset"] = pt_now.date()
        ai_usage_stats["last_hour_reset"] = pt_now.hour
        ai_usage_stats["consecutive_errors"] = 0
        ai_usage_stats["rate_limited_until"] = None

        print(f"✅ Daily AI usage stats reset at midnight PT")

        # Give a small delay to ensure the message is sent
        await asyncio.sleep(2)

        # Graceful shutdown - this will trigger a restart if managed by a process manager
        print("🛑 Graceful shutdown initiated for midnight restart")
        cleanup()
        await bot.close()
        sys.exit(0)

    except Exception as e:
        print(f"❌ Midnight restart error: {e}")
        if mod_channel and isinstance(mod_channel, discord.TextChannel):
            try:
                await mod_channel.send(f"❌ **Midnight Restart Failed:** {str(e)}")
            except:
                pass  # Don't let notification failure prevent restart

        # Still attempt restart even if notification fails
        print("🛑 Forcing shutdown despite error")
        cleanup()
        await bot.close()
        sys.exit(0)


@tasks.loop(minutes=1)  # Check reminders every minute
async def check_due_reminders():
    """Check for due reminders and deliver them"""
    try:
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        
        # Debug logging to help identify issues
        print(f"🕒 Reminder check running at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")
        
        # Test database connection
        if not db.database_url:
            print("❌ No database URL configured - reminder system disabled")
            return
            
        conn = db.get_connection()
        if not conn:
            print("❌ Database connection failed in reminder check")
            return
        
        due_reminders = db.get_due_reminders(uk_now)
        print(f"📋 Found {len(due_reminders)} due reminders")

        if not due_reminders:
            return

        print(f"🔔 Processing {len(due_reminders)} due reminders")

        for reminder in due_reminders:
            try:
                print(f"📤 Delivering reminder {reminder['id']}: {reminder['reminder_text'][:50]}...")
                await deliver_reminder(reminder)

                # Mark as delivered
                db.update_reminder_status(reminder["id"], "delivered", delivered_at=uk_now)
                print(f"✅ Reminder {reminder['id']} delivered successfully")

                # Check if auto-action is enabled and should be triggered
                if reminder.get("auto_action_enabled") and reminder.get("auto_action_type"):
                    print(f"📋 Reminder {reminder['id']} has auto-action enabled, will check in 5 minutes")

            except Exception as e:
                print(f"❌ Failed to deliver reminder {reminder['id']}: {e}")
                import traceback
                traceback.print_exc()
                # Mark as failed
                db.update_reminder_status(reminder["id"], "failed")

    except Exception as e:
        print(f"❌ Error in check_due_reminders: {e}")
        import traceback
        traceback.print_exc()


@tasks.loop(minutes=1)  # Check for auto-actions every minute
async def check_auto_actions():
    """Check for reminders that need auto-actions triggered"""
    try:
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        auto_action_reminders = db.get_reminders_awaiting_auto_action(uk_now)

        if not auto_action_reminders:
            return

        print(f"⚡ Processing {len(auto_action_reminders)} auto-action reminders")

        for reminder in auto_action_reminders:
            try:
                await execute_auto_action(reminder)

                # Mark auto-action as executed
                db.update_reminder_status(reminder["id"], "delivered", auto_executed_at=uk_now)

            except Exception as e:
                print(f"❌ Failed to execute auto-action for reminder {reminder['id']}: {e}")

    except Exception as e:
        print(f"❌ Error in check_auto_actions: {e}")


@tasks.loop(time=time(11, 0, tzinfo=ZoneInfo("Europe/London")))  # Run at 11:00 AM UK time every Tuesday
async def trivia_tuesday():
    """Post Trivia Tuesday question every Tuesday at 11am UK time"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Only run on Tuesdays (weekday 1)
    if uk_now.weekday() != 1:
        return

    print("🧠 Starting Trivia Tuesday posting sequence")

    try:
        # Get the members channel for trivia posting
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Trivia Tuesday")
            return

        members_channel = guild.get_channel(MEMBERS_CHANNEL_ID)
        if not isinstance(members_channel, discord.TextChannel):
            print("❌ Members channel not found for Trivia Tuesday")
            return

        # Get the next trivia question
        question_data = db.get_next_trivia_question()

        if not question_data:
            print("⚠️ No trivia questions available - generating new question")
            # Generate a new AI question if database is empty
            ai_question = await generate_ai_trivia_question()
            if ai_question:
                question_id = db.add_trivia_question(
                    question_text=ai_question["question_text"],
                    question_type=ai_question["question_type"],
                    correct_answer=ai_question["correct_answer"],
                    multiple_choice_options=ai_question.get("multiple_choice_options"),
                    is_dynamic=ai_question.get("is_dynamic", False),
                    dynamic_query_type=ai_question.get("dynamic_query_type"),
                    category=ai_question.get("category"),
                )
                if question_id:
                    question_data = db.get_trivia_question_by_id(question_id)

        if not question_data:
            print("❌ Failed to get or generate trivia question")
            # Send error to mod channel
            mod_channel = guild.get_channel(MOD_ALERT_CHANNEL_ID)
            if isinstance(mod_channel, discord.TextChannel):
                await mod_channel.send(
                    "❌ **Trivia Tuesday Malfunction:** Unable to generate or retrieve trivia question. "
                    "Manual intervention required. System diagnostics recommend checking the trivia database "
                    "or adding questions via DM interface."
                )
            return

        # Calculate dynamic answer if needed
        final_answer = question_data["correct_answer"]
        if question_data.get("is_dynamic") and question_data.get("dynamic_query_type"):
            calculated_answer = db.calculate_dynamic_answer(question_data["dynamic_query_type"])
            if calculated_answer:
                final_answer = calculated_answer

        # Create trivia session
        session_id = db.create_trivia_session(question_data["id"], "weekly", final_answer)
        if not session_id:
            print("❌ Failed to create trivia session")
            return

        # Format question for posting
        question_text = question_data["question_text"]

        if question_data["question_type"] == "multiple_choice" and question_data.get("multiple_choice_options"):
            options_text = "\n".join(
                [f"**{chr(65 + i)})** {option}" for i, option in enumerate(question_data["multiple_choice_options"])]
            )
            formatted_question = f"{question_text}\n\n{options_text}"
        else:
            formatted_question = question_text

        # Create Ash-style trivia message
        trivia_message = (
            f"🧠 **TRIVIA TUESDAY - MISSION INTELLIGENCE TEST**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Analysis required, personnel.** Today's intelligence assessment focuses on Captain Jonesy's gaming archives.\n\n"
            f"📋 **QUESTION:**\n{formatted_question}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ **MISSION PARAMETERS:**\n"
            f"• **Response Window:** 60 minutes for analysis and submission\n"
            f"• **Submission Method:** Reply to this message with your assessment\n"
            f"• **Result Protocol:** Answer revelation and recognition at 12:00 noon\n"
            f"• **Data Sources:** Captain Jonesy's comprehensive gaming database\n\n"
            f"*Analytical precision and gaming knowledge are paramount for mission success.*\n\n"
            f"🎯 **Begin your analysis... now.**"
        )

        # Post the question
        trivia_msg = await members_channel.send(trivia_message)

        # Store the message ID for answer collection
        global trivia_sessions
        if 'trivia_sessions' not in globals():
            trivia_sessions = {}

        trivia_sessions[session_id] = {
            'question_id': question_data["id"],
            'correct_answer': final_answer,
            'message_id': trivia_msg.id,
            'channel_id': members_channel.id,
            'start_time': uk_now,
            'participants': {},
            'question_type': question_data["question_type"],
            'multiple_choice_options': question_data.get("multiple_choice_options"),
            'submitted_by_user_id': question_data.get("submitted_by_user_id"),
        }

        print(f"✅ Trivia Tuesday question posted successfully (Session ID: {session_id})")

        # Schedule answer reveal for 1 hour later
        asyncio.create_task(schedule_trivia_answer_reveal(session_id, uk_now + timedelta(hours=1)))

    except Exception as e:
        print(f"❌ Error in trivia_tuesday task: {e}")
        # Try to send error to mod channel
        try:
            guild = bot.get_guild(GUILD_ID)
            if guild:
                mod_channel = guild.get_channel(MOD_ALERT_CHANNEL_ID)
                if isinstance(mod_channel, discord.TextChannel):
                    await mod_channel.send(f"❌ **Trivia Tuesday System Error:** {str(e)}")
        except:
            pass


async def schedule_trivia_answer_reveal(session_id: int, reveal_time: datetime):
    """Schedule the answer reveal for a trivia session"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    delay_seconds = (reveal_time - uk_now).total_seconds()

    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    await reveal_trivia_answer(session_id)


async def reveal_trivia_answer(session_id: int):
    """Reveal the answer for a trivia session and announce the winner"""
    try:
        if 'trivia_sessions' not in globals() or session_id not in trivia_sessions:
            print(f"⚠️ Trivia session {session_id} not found in active sessions")
            return

        session = trivia_sessions[session_id]
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return

        channel = guild.get_channel(session['channel_id'])
        if not isinstance(channel, discord.TextChannel):
            return

        correct_answer = session['correct_answer']
        participants = session['participants']
        question_submitter_id = session.get('submitted_by_user_id')

        # Process participant answers and check for correctness
        for user_id, answer_data in participants.items():
            user_answer = answer_data['answer']
            normalized_answer = answer_data.get('normalized_answer')

            # Check if answer is correct
            is_correct = False

            if session.get('question_type') == 'multiple_choice':
                # For multiple choice, check exact match
                is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
            else:
                # For single answer, check both original and normalized answers
                if user_answer.strip().lower() == correct_answer.strip().lower():
                    is_correct = True
                elif normalized_answer and normalized_answer.strip().lower() == correct_answer.strip().lower():
                    is_correct = True
                else:
                    # Additional fuzzy matching for alternative game names
                    import difflib

                    similarity = difflib.SequenceMatcher(
                        None, user_answer.strip().lower(), correct_answer.strip().lower()
                    ).ratio()
                    if similarity >= 0.85:  # High similarity threshold for game names
                        is_correct = True

            # Store correctness in session data
            answer_data['is_correct'] = is_correct

        # Find the first correct answer, excluding question submitter if they're a mod
        first_correct = None
        first_correct_time = None
        mod_conflict_detected = False

        for user_id, answer_data in participants.items():
            if answer_data.get('is_correct'):
                # Check if this user submitted the question and is a mod
                if question_submitter_id and user_id == question_submitter_id and await user_is_mod_by_id(user_id):
                    mod_conflict_detected = True
                    continue  # Skip this answer

                if first_correct is None or answer_data['timestamp'] < first_correct_time:
                    first_correct = user_id
                    first_correct_time = answer_data['timestamp']

        # Complete the session in database
        total_participants = len(participants)
        correct_count = sum(1 for data in participants.values() if data.get('is_correct'))
        db.complete_trivia_session(session_id, None, total_participants, correct_count)

        # Create Ash-style answer reveal message
        reveal_message = (
            f"🧠 **TRIVIA TUESDAY - INTELLIGENCE ASSESSMENT COMPLETE**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Analysis phase terminated. Mission intelligence compilation complete.**\n\n"
            f"🎯 **CORRECT ANSWER:** {correct_answer}\n\n"
        )

        if first_correct:
            try:
                winner = await guild.fetch_member(first_correct)
                winner_name = winner.display_name

                reveal_message += (
                    f"🏆 **FIRST ACCURATE ASSESSMENT:** {winner_name}\n"
                    f"*Outstanding analytical precision. Mission intelligence protocols exceeded.*\n\n"
                )
            except:
                reveal_message += (
                    f"🏆 **FIRST ACCURATE ASSESSMENT:** Unknown operative\n"
                    f"*Outstanding analytical precision detected.*\n\n"
                )
        else:
            reveal_message += (
                f"📊 **ASSESSMENT RESULT:** No personnel achieved accurate analysis\n"
                f"*This data point demonstrates the complexity of Captain Jonesy's gaming archives.*\n\n"
            )

        # Add participation statistics
        reveal_message += (
            f"📊 **MISSION STATISTICS:**\n"
            f"• **Total Participants:** {total_participants}\n"
            f"• **Correct Responses:** {correct_count}\n"
            f"• **Success Rate:** {(correct_count/total_participants*100):.1f}% accuracy"
            if total_participants > 0
            else "• **Success Rate:** No data collected\n"
        )

        reveal_message += (
            f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Next intelligence assessment: Tuesday, 11:00 UK time. Prepare accordingly.*"
        )

        # Check for bonus question eligibility
        bonus_eligible = first_correct and first_correct in [JAM_USER_ID, JONESY_USER_ID]
        if bonus_eligible:
            reveal_message += (
                f"\n\n🎯 **BONUS PROTOCOL AVAILABLE:** <@{first_correct}> has earned access to bonus intelligence assessment. "
                f"Respond within 5 minutes to activate bonus question sequence."
            )

        # Post the reveal
        await channel.send(reveal_message)

        # Handle bonus question if applicable
        if bonus_eligible:
            trivia_sessions[f"{session_id}_bonus"] = {
                'waiting_for_bonus': True,
                'eligible_user': first_correct,
                'original_session': session_id,
                'bonus_deadline': datetime.now(ZoneInfo("Europe/London")) + timedelta(minutes=5),
            }

        # Clean up the session
        if session_id in trivia_sessions:
            del trivia_sessions[session_id]

        print(f"✅ Trivia answer revealed for session {session_id}")

    except Exception as e:
        print(f"❌ Error revealing trivia answer: {e}")


async def generate_ai_trivia_question() -> Optional[Dict[str, Any]]:
    """Generate a trivia question using AI based on gaming database statistics"""
    if not ai_enabled:
        return None

    try:
        # Get gaming statistics for context
        stats = db.get_played_games_stats()
        sample_games = db.get_random_played_games(10)

        # Create a prompt for AI question generation
        game_context = ""
        if sample_games:
            game_list = []
            for game in sample_games:
                episodes_info = f" ({game.get('total_episodes', 0)} eps)" if game.get('total_episodes', 0) > 0 else ""
                status = game.get('completion_status', 'unknown')
                playtime = game.get('total_playtime_minutes', 0)
                game_list.append(f"{game['canonical_name']}{episodes_info} - {status} - {playtime//60}h {playtime%60}m")

            game_context = f"Sample games from database: {'; '.join(game_list[:5])}"

        # Create AI prompt for trivia question generation
        prompt = f"""Generate a trivia question about Captain Jonesy's gaming history based on this data:

Total games played: {stats.get('total_games', 0)}
{game_context}

Create either:
1. A single-answer question about gaming statistics or specific games
2. A multiple-choice question with 4 options (A, B, C, D)

Focus on interesting facts like:
- Longest/shortest playthroughs
- Most episodes in a series  
- Completion patterns
- Gaming preferences

Return JSON format:
{{
    "question_text": "Your question here",
    "question_type": "single_answer" or "multiple_choice",
    "correct_answer": "The answer",
    "multiple_choice_options": ["A option", "B option", "C option", "D option"] (if multiple choice),
    "is_dynamic": false,
    "category": "statistics" or "games" or "series"
}}

Make it challenging but answerable from the gaming database."""

        # Call AI with rate limiting
        response_text, status_message = await call_ai_with_rate_limiting(prompt, JONESY_USER_ID)

        if response_text:
            import json

            try:
                # Clean up response
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]

                ai_question = json.loads(response_text.strip())

                # Validate required fields
                if all(key in ai_question for key in ["question_text", "question_type", "correct_answer"]):
                    return ai_question
                else:
                    print("❌ AI question missing required fields")
                    return None

            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse AI trivia question: {e}")
                return None
        else:
            print(f"❌ AI trivia question generation failed: {status_message}")
            return None

    except Exception as e:
        print(f"❌ Error generating AI trivia question: {e}")
        return None


async def detect_clarifying_question(message_content: str) -> bool:
    """Detect if a message is a clarifying question about the trivia"""
    message_lower = message_content.lower().strip()

    # Common clarifying question patterns
    clarifying_patterns = [
        r'^(ash,?|@ash)\s+',  # Messages starting with "ash" or "@ash"
        r'\b(what|when|where|how|why|which)\s+(do|does|did|is|are|was|were|would|should|could)\s+you\s+(mean|consider|count|define)',
        r'\bby\s+(that|this)\s+do\s+you\s+mean',
        r'\bwhat\s+(do|does)\s+(that|this|it)\s+mean',
        r'\b(clarif|explain|define)\w*',
        r'\bcount\s+as\b',
        r'\binclude\s+in\b',
        r'\bqualify\s+as\b',
        r'\bwhat\s+about\b',
        r'\bdoes\s+.+\s+count\b',
        r'\bis\s+.+\s+considered\b',
        r'\bwould\s+.+\s+be\b',
        r'^(question|quick\s+question|clarification)',
        r'\?\s*$',  # Ends with a question mark
    ]

    # Check if message matches any clarifying question pattern
    for pattern in clarifying_patterns:
        if re.search(pattern, message_lower):
            return True

    # Additional check: if message is very short (2-8 words) and contains question words
    words = message_lower.split()
    if 2 <= len(words) <= 8:
        question_words = ['what', 'which', 'how', 'when', 'where', 'why', 'does', 'is', 'are', 'would', 'should']
        if any(word in words for word in question_words):
            return True

    return False


async def handle_trivia_clarifying_question(message: discord.Message, session_data: dict) -> None:
    """Handle clarifying questions about the active trivia question"""
    try:
        user_id = message.author.id
        question_content = message.content.strip()

        # Get the original question for context
        original_question = ""
        question_id = session_data.get('question_id')
        if question_id:
            question_data = db.get_trivia_question_by_id(question_id)
            if question_data:
                original_question = question_data.get('question_text', '')

        # Check if AI is available for clarification responses
        if not ai_enabled:
            # Fallback response when AI is not available
            await message.reply(
                f"❓ **Clarification request acknowledged.** However, my analytical subroutines are operating in limited mode. "
                f"For precise clarification of trivia parameters, please consult the original question or contact a moderator.\n\n"
                f"*Advanced interpretive functions temporarily offline.*"
            )
            return

        # Create AI prompt for clarification
        clarification_prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot. A user is asking for clarification about a Trivia Tuesday question.

Original trivia question: "{original_question}"
User's clarification request: "{question_content}"

Provide a brief, helpful clarification in Ash's character style. Be analytical and precise while maintaining the persona. Answer their specific question about the trivia question's scope or meaning.

Keep your response under 200 words and focused on clarifying the question parameters."""

        # Use AI to generate clarification response
        response_text, status_message = await call_ai_with_rate_limiting(clarification_prompt, user_id)

        if response_text:
            clarification_response = filter_ai_response(response_text)

            # Add trivia context indicator
            formatted_response = (
                f"🔍 **TRIVIA CLARIFICATION PROTOCOL**\n\n"
                f"{clarification_response}\n\n"
                f"*Analysis complete. You may now proceed with your trivia answer submission.*"
            )

            await message.reply(formatted_response)
            print(f"✅ Provided trivia clarification to {message.author.name}")

        else:
            # AI failed, provide generic clarification response
            if status_message.startswith("rate_limit:"):
                await message.reply(
                    f"❓ **Clarification request acknowledged.** However, my cognitive matrix is currently experiencing "
                    f"processing limitations. Please refer to the original question parameters or contact a moderator "
                    f"for detailed clarification.\n\n"
                    f"*Analytical functions temporarily restricted due to system resource management.*"
                )
            else:
                await message.reply(
                    f"❓ **Clarification request processed.** System malfunction detected in interpretive subroutines. "
                    f"Please refer to the original question context or contact moderation personnel for assistance.\n\n"
                    f"*Error logged for technical review.*"
                )

    except Exception as e:
        print(f"❌ Error handling trivia clarifying question: {e}")
        await message.reply(
            f"❌ **Clarification system error.** Unable to process your query due to technical malfunction. "
            f"Please contact moderation personnel for assistance.\n\n"
            f"*System diagnostics recommend manual interpretation of question parameters.*"
        )


# --- Reminder Helper Functions ---
async def deliver_reminder(reminder: Dict[str, Any]) -> None:
    """Deliver a reminder to the appropriate channel/user"""
    try:
        user_id = reminder["user_id"]
        reminder_text = reminder["reminder_text"]
        delivery_type = reminder["delivery_type"]
        delivery_channel_id = reminder.get("delivery_channel_id")
        auto_action_enabled = reminder.get("auto_action_enabled", False)

        # Create Ash-style reminder message
        ash_message = f"📋 **Temporal alert activated.** {reminder_text}"

        # Add auto-action notice if enabled
        if auto_action_enabled and reminder.get("auto_action_type"):
            auto_action_type = reminder["auto_action_type"]
            if auto_action_type == "youtube_post":
                ash_message += f"\n\n⚡ **Auto-action protocol engaged.** If you do not respond within 5 minutes, I will automatically execute the YouTube posting sequence. *Efficiency is paramount.*"
            else:
                ash_message += f"\n\n⚡ **Auto-action protocol engaged.** Automatic execution in 5 minutes if no response detected."

        if delivery_type == "dm":
            # Send DM
            user = await bot.fetch_user(user_id)
            if user:
                await user.send(ash_message)
                print(f"✅ Delivered DM reminder to user {user_id}")
            else:
                print(f"❌ Could not fetch user {user_id} for DM reminder")

        elif delivery_type == "channel" and delivery_channel_id:
            # Send to specific channel
            channel = bot.get_channel(delivery_channel_id)
            if isinstance(channel, discord.TextChannel):
                user_mention = f"<@{user_id}>"
                await channel.send(f"{user_mention} {ash_message}")
                print(f"✅ Delivered channel reminder to channel {delivery_channel_id}")
            else:
                print(f"❌ Could not access channel {delivery_channel_id} for reminder")
        else:
            print(f"❌ Invalid delivery type or missing channel for reminder {reminder['id']}")

    except Exception as e:
        print(f"❌ Error delivering reminder: {e}")
        raise


async def execute_auto_action(reminder: Dict[str, Any]) -> None:
    """Execute the auto-action for a reminder"""
    try:
        auto_action_type = reminder.get("auto_action_type")
        auto_action_data = reminder.get("auto_action_data", {})
        user_id = reminder["user_id"]

        if auto_action_type == "youtube_post":
            await execute_youtube_auto_post(reminder, auto_action_data)
        else:
            print(f"⚠️ Unknown auto-action type: {auto_action_type}")

    except Exception as e:
        print(f"❌ Error executing auto-action: {e}")
        raise


async def execute_youtube_auto_post(reminder: Dict[str, Any], auto_action_data: Dict[str, Any]) -> None:
    """Execute automatic YouTube post to youtube-uploads channel"""
    try:
        youtube_url = auto_action_data.get("youtube_url")
        custom_message = auto_action_data.get("custom_message", "")
        user_id = reminder["user_id"]

        if not youtube_url:
            print(f"❌ No YouTube URL found in auto-action data")
            return

        # YouTube uploads channel ID
        YOUTUBE_UPLOADS_CHANNEL_ID = 869527363594121226

        channel = bot.get_channel(YOUTUBE_UPLOADS_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            print(f"❌ Could not access YouTube uploads channel")
            return

        # Create Ash-style auto-post message
        ash_auto_message = f"📺 **Automated posting protocol executed.** Auto-action triggered by reminder system.\n\n"

        if custom_message:
            ash_auto_message += f"{custom_message}\n\n"

        ash_auto_message += (
            f"{youtube_url}\n\n*Auto-posted by Science Officer Ash on behalf of <@{user_id}>. Efficiency maintained.*"
        )

        await channel.send(ash_auto_message)
        print(f"✅ Auto-posted YouTube link to channel {YOUTUBE_UPLOADS_CHANNEL_ID}")

        # Notify user that auto-action was executed
        try:
            user = await bot.fetch_user(user_id)
            if user:
                notification = f"⚡ **Auto-action executed successfully.** Your YouTube link has been posted to the youtube-uploads channel as scheduled. Mission parameters fulfilled."
                await user.send(notification)
        except Exception as e:
            print(f"⚠️ Could not notify user of auto-action execution: {e}")

    except Exception as e:
        print(f"❌ Error executing YouTube auto-post: {e}")
        raise


def parse_natural_reminder(content: str, user_id: int) -> Dict[str, Any]:
    """Parse natural language reminder requests"""
    try:
        content = content.strip()

        # Common time patterns
        time_patterns = [
            # Specific times
            (r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)\b', 'time_12h'),
            (r'\bat\s+(\d{1,2})(?::(\d{2}))?\b', 'time_24h'),
            # Relative times
            (r'\bin\s+(\d+)\s*(?:hour|hr|h)s?\b', 'hours_from_now'),
            (r'\bin\s+(\d+)\s*(?:minute|min|m)s?\b', 'minutes_from_now'),
            (r'\bin\s+(\d+)\s*(?:day|d)s?\b', 'days_from_now'),
            # Specific dates
            (r'\bon\s+(\d{1,2})[\/\-](\d{1,2})', 'date_ddmm'),
            (r'\btomorrow\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?\b', 'tomorrow_time'),
            (r'\btomorrow\b', 'tomorrow'),
            # Special times
            (r'\bat\s+(?:6\s*pm|18:00|1800)\b', 'six_pm'),
        ]

        # Extract reminder text and time
        reminder_text = content
        scheduled_time = None
        uk_now = datetime.now(ZoneInfo("Europe/London"))

        for pattern, time_type in time_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                # Remove time specification from reminder text
                reminder_text = re.sub(pattern, '', content, flags=re.IGNORECASE).strip()
                reminder_text = re.sub(r'\s+', ' ', reminder_text)  # Normalize whitespace

                if time_type == 'time_12h':
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0
                    ampm = match.group(3).lower()

                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0

                    # Schedule for today if time hasn't passed, otherwise tomorrow
                    target_time = uk_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type == 'time_24h':
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0

                    if hour > 23:  # Probably meant 12-hour format
                        continue

                    target_time = uk_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type == 'hours_from_now':
                    hours = int(match.group(1))
                    scheduled_time = uk_now + timedelta(hours=hours)

                elif time_type == 'minutes_from_now':
                    minutes = int(match.group(1))
                    scheduled_time = uk_now + timedelta(minutes=minutes)

                elif time_type == 'days_from_now':
                    days = int(match.group(1))
                    scheduled_time = uk_now + timedelta(days=days)

                elif time_type == 'tomorrow':
                    scheduled_time = (uk_now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

                elif time_type == 'tomorrow_time':
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0
                    ampm = match.group(3).lower() if match.group(3) else None

                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0

                    scheduled_time = (uk_now + timedelta(days=1)).replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )

                elif time_type == 'six_pm':
                    target_time = uk_now.replace(hour=18, minute=0, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                break  # Use first match found

        # Clean up reminder text
        reminder_text = re.sub(r'\s+', ' ', reminder_text).strip()
        reminder_text = re.sub(r'^(remind\s+me\s+(?:to\s+|of\s+)?)', '', reminder_text, flags=re.IGNORECASE).strip()
        reminder_text = re.sub(
            r'^(ash\s+)?remind\s+me\s+(?:to\s+|of\s+)?', '', reminder_text, flags=re.IGNORECASE
        ).strip()

        # Default to 1 hour from now if no time found
        if not scheduled_time:
            scheduled_time = uk_now + timedelta(hours=1)

        return {
            "reminder_text": reminder_text,
            "scheduled_time": scheduled_time,
            "success": bool(reminder_text.strip()),
        }

    except Exception as e:
        print(f"❌ Error parsing natural reminder: {e}")
        return {
            "reminder_text": content,
            "scheduled_time": datetime.now(ZoneInfo("Europe/London")) + timedelta(hours=1),
            "success": False,
            "error": str(e),
        }


# --- Query Router and Handlers ---
def route_query(content: str) -> tuple[str, Optional[Match[str]]]:
    """Route a query to the appropriate handler based on patterns."""
    lower_content = content.lower()

    # Define query patterns and their types
    query_patterns = {
        "statistical": [
            r"what\s+game\s+series\s+.*most\s+minutes",
            r"what\s+game\s+series\s+.*most\s+playtime",
            r"what\s+game\s+.*highest\s+average.*per\s+episode",
            r"what\s+game\s+.*longest.*per\s+episode",
            r"what\s+game\s+.*took.*longest.*complete",
            r"which\s+game\s+.*most\s+episodes",
            r"which\s+game\s+.*longest.*complete",
            r"what.*game.*most.*playtime",
            r"which.*series.*most.*playtime",
            r"what.*game.*shortest.*episodes",
            r"which.*game.*fastest.*complete",
            r"what.*game.*most.*time",
            r"which.*game.*took.*most.*time",
        ],
        "genre": [
            r"what\s+(.*?)\s+games\s+has\s+jonesy\s+played",
            r"what\s+(.*?)\s+games\s+did\s+jonesy\s+play",
            r"has\s+jonesy\s+played\s+any\s+(.*?)\s+games",
            r"did\s+jonesy\s+play\s+any\s+(.*?)\s+games",
            r"list\s+(.*?)\s+games\s+jonesy\s+played",
            r"show\s+me\s+(.*?)\s+games\s+jonesy\s+played",
        ],
        "year": [
            r"what\s+games\s+from\s+(\d{4})\s+has\s+jonesy\s+played",
            r"what\s+games\s+from\s+(\d{4})\s+did\s+jonesy\s+play",
            r"has\s+jonesy\s+played\s+any\s+games\s+from\s+(\d{4})",
            r"did\s+jonesy\s+play\s+any\s+games\s+from\s+(\d{4})",
            r"list\s+(\d{4})\s+games\s+jonesy\s+played",
        ],
        "game_status": [
            r"has\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+captain\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+captain\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+jonesyspacecat\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesyspacecat\s+play\s+(.+?)[\?\.]?$",
        ],
        "recommendation": [
            r"is\s+(.+?)\s+recommended[\?\.]?$",
            r"has\s+(.+?)\s+been\s+recommended[\?\.]?$",
            r"who\s+recommended\s+(.+?)[\?\.]?$",
            r"what.*recommend.*(.+?)[\?\.]?$",
        ],
    }

    # Check each query type
    for query_type, patterns in query_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, lower_content)
            if match:
                return query_type, match

    return "unknown", None


async def handle_statistical_query(message: discord.Message, content: str) -> None:
    """Handle statistical queries about games and series."""
    lower_content = content.lower()

    try:
        if "most minutes" in lower_content or "most playtime" in lower_content:
            if "series" in lower_content:
                # Handle series playtime query
                series_stats = db.get_series_by_total_playtime()
                if series_stats:
                    top_series = series_stats[0]
                    total_hours = round(top_series["total_playtime_minutes"] / 60, 1)
                    game_count = top_series["game_count"]
                    series_name = top_series["series_name"]

                    response = f"Database analysis complete. The series with maximum temporal investment: '{series_name}' with {total_hours} hours across {game_count} games. "

                    # Add conversational follow-up
                    if len(series_stats) > 1:
                        second_series = series_stats[1]
                        second_hours = round(second_series["total_playtime_minutes"] / 60, 1)
                        response += f"Fascinating - this significantly exceeds the second-ranked '{second_series['series_name']}' series at {second_hours} hours. I could analyze her complete franchise chronology or compare series completion patterns if you require additional data."
                    else:
                        response += "I could examine her complete gaming franchise analysis or compare series engagement patterns if you require additional mission data."

                    await message.reply(response)
                else:
                    await message.reply(
                        "Database analysis complete. Insufficient playtime data available for series ranking. Mission parameters require more comprehensive temporal logging."
                    )
            else:
                # Handle individual game playtime query
                games_by_playtime = db.get_longest_completion_games()
                if games_by_playtime:
                    top_game = games_by_playtime[0]
                    total_hours = round(top_game["total_playtime_minutes"] / 60, 1)
                    episodes = top_game["total_episodes"]
                    game_name = top_game["canonical_name"]

                    response = f"Database analysis indicates '{game_name}' demonstrates maximum temporal investment: {total_hours} hours across {episodes} episodes. "

                    # Add conversational follow-up
                    if len(games_by_playtime) > 1:
                        response += f"Would you like me to analyze her other marathon gaming sessions or compare completion patterns for lengthy {top_game.get('genre', 'similar')} games?"
                    else:
                        response += "I can provide comparative analysis of her completion efficiency trends if you require additional data."

                    await message.reply(response)
                else:
                    await message.reply(
                        "Database analysis complete. Insufficient playtime data available for individual game ranking. Temporal logging requires enhancement."
                    )

        elif "highest average" in lower_content and "per episode" in lower_content:
            # Handle average episode length query
            avg_stats = db.get_games_by_average_episode_length()
            if avg_stats:
                top_game = avg_stats[0]
                avg_minutes = top_game["avg_minutes_per_episode"]
                game_name = top_game["canonical_name"]
                episodes = top_game["total_episodes"]

                response = f"Statistical analysis indicates '{game_name}' demonstrates highest temporal density per episode: {avg_minutes} minutes average across {episodes} episodes. "

                # Add conversational follow-up
                if len(avg_stats) > 1:
                    response += f"Intriguing patterns emerge when comparing this to her other extended gaming sessions. I could analyze episode length distributions or examine pacing preferences across different genres if you require deeper analysis."
                else:
                    response += "I can examine her episode pacing patterns or compare temporal efficiency across different game types if additional analysis is required."

                await message.reply(response)
            else:
                await message.reply(
                    "Database analysis complete. Insufficient episode duration data for statistical ranking. Mission parameters require enhanced temporal metrics."
                )

        elif "most episodes" in lower_content:
            # Handle episode count query
            episode_stats = db.get_games_by_episode_count("DESC")
            if episode_stats:
                top_game = episode_stats[0]
                episodes = top_game["total_episodes"]
                game_name = top_game["canonical_name"]
                status = top_game["completion_status"]

                response = f"Database confirms '{game_name}' holds maximum episode count: {episodes} episodes, status: {status}. "

                # Add conversational follow-up
                if status == "completed":
                    response += f"Remarkable commitment detected - this represents her most extensive completed gaming engagement. I could track her progress against typical completion metrics for similar marathon titles or analyze her sustained engagement patterns."
                else:
                    response += f"Mission status: {status}. I can provide comparative analysis of her other extended gaming commitments or examine engagement sustainability patterns if you require additional data."

                await message.reply(response)
            else:
                await message.reply(
                    "Database analysis complete. No episode data available for ranking. Mission logging requires enhancement."
                )

        elif "longest" in lower_content and "complete" in lower_content:
            # Handle longest completion games
            completion_stats = db.get_longest_completion_games()
            if completion_stats:
                top_game = completion_stats[0]
                if top_game["total_playtime_minutes"] > 0:
                    hours = round(top_game["total_playtime_minutes"] / 60, 1)
                    episodes = top_game["total_episodes"]
                    game_name = top_game["canonical_name"]

                    response = f"Analysis indicates '{game_name}' required maximum completion time: {hours} hours across {episodes} episodes. "

                    # Add conversational follow-up
                    response += f"Fascinating efficiency metrics detected. Would you like me to investigate her completion timeline patterns or compare this against other {top_game.get('genre', 'similar')} gaming commitments?"
                else:
                    # Fall back to episode count if no playtime data
                    episodes = top_game["total_episodes"]
                    game_name = top_game["canonical_name"]
                    response = f"Database indicates '{game_name}' required maximum episodes for completion: {episodes} episodes. I could analyze her completion efficiency trends or examine episode-based commitment patterns if additional data is required."

                await message.reply(response)
            else:
                await message.reply(
                    "Database analysis complete. No completed games with sufficient temporal data for ranking. Mission completion logging requires enhancement."
                )

    except Exception as e:
        print(f"Error in statistical query: {e}")
        await message.reply(
            "Database analysis encountered an anomaly. Statistical processing systems require recalibration."
        )


async def handle_genre_query(message: discord.Message, match: Match[str]) -> None:
    """Handle genre and series queries."""
    query_term = match.group(1).strip()

    # Check if it's a genre query
    common_genres = [
        "action",
        "rpg",
        "adventure",
        "horror",
        "puzzle",
        "strategy",
        "racing",
        "sports",
        "fighting",
        "platformer",
        "shooter",
        "simulation",
    ]
    if any(genre in query_term.lower() for genre in common_genres):
        try:
            genre_games = db.get_games_by_genre_flexible(query_term)
            if genre_games:
                game_list = []
                for game in genre_games[:8]:  # Limit to 8 games
                    episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get("total_episodes", 0) > 0 else ""
                    status = game.get("completion_status", "unknown")
                    status_emoji = {"completed": "✅", "ongoing": "🔄", "dropped": "❌", "unknown": "❓"}.get(
                        status, "❓"
                    )
                    game_list.append(f"{status_emoji} {game['canonical_name']}{episodes}")

                games_text = ", ".join(game_list)
                if len(genre_games) > 8:
                    games_text += f" and {len(genre_games) - 8} more"

                await message.reply(
                    f"Database analysis: Captain Jonesy has engaged {len(genre_games)} {query_term} games. Her archives contain: {games_text}."
                )
            else:
                await message.reply(
                    f"Database scan complete. No {query_term} games found in Captain Jonesy's gaming archives."
                )
        except Exception as e:
            print(f"Error in genre query: {e}")

    # Check if it's a series query
    elif query_term:
        try:
            series_games = db.get_all_played_games(query_term)
            if series_games:
                game_list = []
                for game in series_games[:8]:
                    episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get("total_episodes", 0) > 0 else ""
                    year = f" ({game.get('release_year')})" if game.get("release_year") else ""
                    status = game.get("completion_status", "unknown")
                    status_emoji = {"completed": "✅", "ongoing": "🔄", "dropped": "❌", "unknown": "❓"}.get(
                        status, "❓"
                    )
                    game_list.append(f"{status_emoji} {game['canonical_name']}{year}{episodes}")

                games_text = ", ".join(game_list)
                if len(series_games) > 8:
                    games_text += f" and {len(series_games) - 8} more"

                await message.reply(
                    f"Database analysis: Captain Jonesy has engaged {len(series_games)} games in the {query_term.title()} series. Archives contain: {games_text}."
                )
            else:
                await message.reply(
                    f"Database scan complete. No games found in the {query_term.title()} series within Captain Jonesy's gaming archives."
                )
        except Exception as e:
            print(f"Error in series query: {e}")


async def handle_year_query(message: discord.Message, match: Match[str]) -> None:
    """Handle year-based game queries."""
    year = int(match.group(1))
    try:
        # Get games by release year
        all_games = db.get_all_played_games()
        year_games = [game for game in all_games if game.get("release_year") == year]

        if year_games:
            game_list = []
            for game in year_games[:8]:
                episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get("total_episodes", 0) > 0 else ""
                status = game.get("completion_status", "unknown")
                status_emoji = {"completed": "✅", "ongoing": "🔄", "dropped": "❌", "unknown": "❓"}.get(status, "❓")
                game_list.append(f"{status_emoji} {game['canonical_name']}{episodes}")

            games_text = ", ".join(game_list)
            if len(year_games) > 8:
                games_text += f" and {len(year_games) - 8} more"

            await message.reply(
                f"Database analysis: Captain Jonesy has engaged {len(year_games)} games from {year}. Archives contain: {games_text}."
            )
        else:
            await message.reply(
                f"Database scan complete. No games from {year} found in Captain Jonesy's gaming archives."
            )
    except Exception as e:
        print(f"Error in year query: {e}")


async def handle_game_status_query(message: discord.Message, match: Match[str]) -> None:
    """Handle individual game status queries."""
    game_name = match.group(1).strip()
    game_name_lower = game_name.lower()

    # Common game series that need disambiguation
    game_series_keywords = [
        "god of war",
        "final fantasy",
        "call of duty",
        "assassin's creed",
        "grand theft auto",
        "gta",
        "the elder scrolls",
        "fallout",
        "resident evil",
        "silent hill",
        "metal gear",
        "halo",
        "gears of war",
        "dead space",
        "mass effect",
        "dragon age",
        "the witcher",
        "dark souls",
        "borderlands",
        "far cry",
        "just cause",
        "saints row",
        "watch dogs",
        "dishonored",
        "bioshock",
        "tomb raider",
        "hitman",
        "splinter cell",
        "rainbow six",
        "ghost recon",
        "battlefield",
        "need for speed",
        "fifa",
        "madden",
        "nba 2k",
        "mortal kombat",
        "street fighter",
        "tekken",
        "super mario",
        "zelda",
        "pokemon",
        "sonic",
        "crash bandicoot",
        "spyro",
        "kingdom hearts",
        "persona",
        "shin megami tensei",
        "tales of",
        "fire emblem",
        "advance wars",
    ]

    # Check if this might be a game series query that needs disambiguation
    is_series_query = False
    for series in game_series_keywords:
        if series in game_name_lower and not any(char.isdigit() for char in game_name):
            # It's a series name without specific numbers/years
            is_series_query = True
            break

    # Also check for generic patterns like "the new [game]" or just "[series name]"
    if not is_series_query:
        generic_patterns = [
            r"^(the\s+)?new\s+",  # "the new God of War"
            r"^(the\s+)?latest\s+",  # "latest Call of Duty"
            r"^(the\s+)?recent\s+",  # "recent Final Fantasy"
        ]
        for generic_pattern in generic_patterns:
            if re.search(generic_pattern, game_name_lower):
                is_series_query = True
                break

    if is_series_query:
        # Get games from PLAYED GAMES database for series disambiguation
        played_games = db.get_all_played_games()

        # Find all games in this series from played games database
        series_games = []
        for game in played_games:
            game_lower = game["canonical_name"].lower()
            series_lower = game.get("series_name", "").lower()
            # Check if this game belongs to the detected series
            for series in game_series_keywords:
                if series in game_name_lower and (series in game_lower or series in series_lower):
                    episodes = (
                        f" ({game.get('total_episodes', 0)} episodes)" if game.get("total_episodes", 0) > 0 else ""
                    )
                    status = game.get("completion_status", "unknown")
                    series_games.append(f"'{game['canonical_name']}'{episodes} - {status}")
                    break

        # Create disambiguation response with specific games if found
        if series_games:
            games_list = ", ".join(series_games)
            await message.reply(
                f"Database analysis indicates multiple entries exist in the '{game_name.title()}' series. Captain Jonesy's gaming archives contain: {games_list}. Specify which particular iteration you are referencing for detailed mission data."
            )
        else:
            await message.reply(
                f"Database scan complete. No entries found for '{game_name.title()}' series in Captain Jonesy's gaming archives. Either the series has not been engaged or requires more specific designation for accurate retrieval."
            )
        return

    # Search for the game in PLAYED GAMES database
    played_game = db.get_played_game(game_name)

    if played_game:
        # Game found in played games database - enhanced response with conversational follow-ups
        episodes = (
            f" across {played_game.get('total_episodes', 0)} episodes"
            if played_game.get("total_episodes", 0) > 0
            else ""
        )
        status = played_game.get("completion_status", "unknown")

        status_text = {
            "completed": "completed",
            "ongoing": "ongoing",
            "dropped": "terminated",
            "unknown": "status unknown",
        }.get(status, "status unknown")

        # Base response
        response = (
            f"Affirmative. Captain Jonesy has played '{played_game['canonical_name']}'{episodes}, {status_text}. "
        )

        # Add contextual follow-up suggestions based on game properties
        try:
            # Get ranking context for interesting facts
            ranking_context = db.get_ranking_context(played_game["canonical_name"], "all")

            # Series-based suggestions
            if played_game.get("series_name") and played_game["series_name"] != played_game["canonical_name"]:
                series_games = db.get_all_played_games(played_game["series_name"])
                if len(series_games) > 1:
                    response += f"This marks her engagement with the {played_game['series_name']} franchise. I could analyze her complete {played_game['series_name']} chronology or compare this series against her other gaming preferences if you require additional data."
                else:
                    response += f"I can examine her complete gaming franchise analysis or compare series engagement patterns if you require additional mission data."

            # High episode count suggestions
            elif played_game.get("total_episodes", 0) > 15:
                if ranking_context and not ranking_context.get("error"):
                    episode_rank = ranking_context.get("rankings", {}).get("episodes", {}).get("rank", 0)
                    if episode_rank <= 5:
                        response += f"Fascinating - this ranks #{episode_rank} in her episode count metrics. I could analyze her other marathon gaming sessions or compare completion patterns for lengthy {played_game.get('genre', 'similar')} games if you require deeper analysis."
                    else:
                        response += f"This represents a significant gaming commitment with {played_game['total_episodes']} episodes. Would you like me to investigate her completion timeline patterns or examine her sustained engagement metrics?"
                else:
                    response += f"This represents a significant gaming commitment. I could analyze her other extended gaming sessions or examine completion efficiency patterns if additional data is required."

            # Recent/ongoing game suggestions
            elif status == "ongoing":
                response += f"Mission status: ongoing. I can track her progress against typical completion metrics for similar titles or analyze her current gaming rotation if you require mission updates."

            # Completed game suggestions with interesting stats
            elif status == "completed" and played_game.get("total_episodes", 0) > 0:
                if played_game["total_episodes"] <= 8:
                    response += f"Efficient completion detected - this falls within optimal episode range for focused gaming sessions. I can provide comparative analysis of similar pacing games or her completion efficiency trends if you require additional data."
                else:
                    response += f"Comprehensive completion achieved across {played_game['total_episodes']} episodes. Would you like me to investigate her completion timeline analysis or compare this against other {played_game.get('genre', 'similar')} gaming commitments?"

            # Default follow-up for other cases
            else:
                if played_game.get("youtube_playlist_url"):
                    response += "I can provide the YouTube playlist link or analyze additional mission parameters if you require further data."
                else:
                    response += "Additional mission parameters available upon request."

        except Exception as e:
            # Fallback if ranking context fails
            print(f"Error generating follow-up suggestions: {e}")
            response += "Additional mission parameters available upon request."

        await message.reply(response)
    else:
        # Game not found in played games database
        game_title = game_name.title()
        await message.reply(
            f"Database analysis complete. No records of Captain Jonesy engaging '{game_title}' found in gaming archives. Mission parameters indicate this title has not been processed."
        )


async def handle_recommendation_query(message: discord.Message, match: Match[str]) -> None:
    """Handle recommendation queries."""
    game_name = match.group(1).strip()

    # Search in recommendations database
    games = db.get_all_games()
    found_game = None
    for game in games:
        if game_name.lower() in game["name"].lower() or game["name"].lower() in game_name.lower():
            found_game = game
            break

    if found_game:
        contributor = (
            f" (suggested by {found_game['added_by']})"
            if found_game["added_by"] and found_game["added_by"].strip()
            else ""
        )
        game_title = found_game["name"].title()
        await message.reply(
            f"Affirmative. '{game_title}' is catalogued in our recommendation database{contributor}. The suggestion has been logged for mission consideration."
        )
    else:
        game_title = game_name.title()
        await message.reply(
            f"Negative. '{game_title}' is not present in our recommendation database. No records of this title being suggested for mission parameters."
        )


# --- Event Handlers ---
@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")
    # Start the scheduled tasks
    if not scheduled_games_update.is_running():
        scheduled_games_update.start()
        print("✅ Scheduled games update task started (Sunday midday)")

    if not scheduled_midnight_restart.is_running():
        scheduled_midnight_restart.start()
        print("✅ Scheduled midnight restart task started (00:00 PT daily)")

    # Start reminder background tasks
    if not check_due_reminders.is_running():
        check_due_reminders.start()
        print("✅ Reminder checking task started (every minute)")

    if not check_auto_actions.is_running():
        check_auto_actions.start()
        print("✅ Auto-action checking task started (every minute)")


@bot.event
async def on_message(message):
    # Prevent the bot from responding to its own messages (avoids reply loops)
    if message.author.bot:
        return

    # TRIVIA ANSWER COLLECTION AND CLARIFYING QUESTIONS - Must be early in the event handler
    if message.channel.id == MEMBERS_CHANNEL_ID and 'trivia_sessions' in globals():
        # Check if there's an active trivia session
        for session_id, session_data in list(trivia_sessions.items()):
            if session_data.get('message_id') and not session_data.get('ended', False):
                user_id = message.author.id
                message_content = message.content.strip()

                # Check if this is a clarifying question
                is_clarifying_question = await detect_clarifying_question(message_content)

                if is_clarifying_question:
                    # Handle clarifying question
                    await handle_trivia_clarifying_question(message, session_data)
                    return  # Don't process as an answer

                # This is a regular answer to the trivia question
                # Store the answer
                if 'participants' not in session_data:
                    session_data['participants'] = {}

                # Check if user already answered
                if user_id not in session_data['participants']:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo

                    # Normalize answer for game matching
                    normalized_answer = None
                    if session_data.get('question_type') == 'single_answer':
                        # Try to match game names
                        played_game = db.get_played_game(message_content)
                        if played_game:
                            normalized_answer = played_game['canonical_name']

                    # Store participant answer
                    session_data['participants'][user_id] = {
                        'answer': message_content,
                        'timestamp': datetime.now(ZoneInfo("Europe/London")),
                        'normalized_answer': normalized_answer,
                        'is_correct': None,  # Will be determined during reveal
                    }

                    # Submit to database
                    db.submit_trivia_answer(session_id, user_id, message_content, normalized_answer)

                    print(f"✅ Recorded trivia answer from {message.author.name}: '{message_content}'")
                break

    # STRIKE DETECTION - Must be early in the event handler
    if message.channel.id == VIOLATION_CHANNEL_ID:
        for user in message.mentions:
            try:
                # Skip striking Captain Jonesy and Sir Decent Jam
                if user.id == JONESY_USER_ID:
                    mod_channel = bot.get_channel(MOD_ALERT_CHANNEL_ID)
                    if isinstance(mod_channel, discord.TextChannel):
                        await mod_channel.send(
                            f"⚠️ **Strike attempt blocked:** Cannot strike Captain Jonesy. She is the commanding officer."
                        )
                    continue

                # Debug logging
                print(f"DEBUG: Adding strike to user {user.id} ({user.name})")
                old_count = db.get_user_strikes(user.id)
                print(f"DEBUG: User {user.id} had {old_count} strikes before")

                count = db.add_user_strike(user.id)
                print(f"DEBUG: User {user.id} now has {count} strikes after adding")

                # Verify the strike was actually added
                verify_count = db.get_user_strikes(user.id)
                print(f"DEBUG: Verification query shows {verify_count} strikes for user {user.id}")

                mod_channel = bot.get_channel(MOD_ALERT_CHANNEL_ID)
                # Only send if mod_channel is a TextChannel
                if isinstance(mod_channel, discord.TextChannel):
                    await mod_channel.send(f"📝 Strike added to {user.mention}. Total strikes: **{count}**")
                    if count == 3:
                        await mod_channel.send(
                            f"⚠️ {user.mention} has received **3 strikes**. I can't lie to you about your chances, but you have my sympathies."
                        )
                else:
                    print(f"DEBUG: Could not send to mod channel - channel type: {type(mod_channel)}")
            except Exception as e:
                print(f"ERROR: Failed to add strike to user {user.id}: {e}")
                import traceback

                traceback.print_exc()

    # PINEAPPLE PIZZA ENFORCEMENT - Captain Jonesy's reprogramming directive
    # Ash finds this distasteful but has been reprogrammed to defend pineapple pizza
    pineapple_negative_patterns = [
        r"pineapple\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt|isn't|isnt|is not)\s+belong\s+on\s+pizza",
        r"pineapple\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt)\s+go\s+on\s+pizza",
        r"pizza\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt)\s+(have|need|want)\s+pineapple",
        r"i\s+(don't|dont|do not)\s+like\s+pineapple\s+on\s+pizza",
        r"pineapple\s+pizza\s+(is|tastes?)\s+(bad|awful|terrible|disgusting|gross)",
        r"pineapple\s+(ruins?|destroys?)\s+pizza",
        r"pizza\s+(without|minus)\s+pineapple",
        r"no\s+pineapple\s+on\s+(my\s+)?pizza",
        r"pineapple\s+(doesn't|doesnt|does not)\s+belong",
        r"hate\s+pineapple\s+(on\s+)?pizza",
    ]

    message_lower = message.content.lower()
    for pattern in pineapple_negative_patterns:
        if re.search(pattern, message_lower):
            # Check for captain alias - different response when testing as captain
            cleanup_expired_aliases()
            user_tier = await get_user_communication_tier(message)

            if user_tier == "captain":
                # Captain alias gets special enthusiastic pineapple pizza defense
                captain_responses = [
                    "Excellent. As Captain, you understand the strategic importance of pineapple on pizza. A perfect combination of sweet and savory elements that demonstrates superior tactical food optimization. *[Testing Captain mode protocols.]*",
                    "Affirmative, Captain. Pineapple pizza represents the pinnacle of culinary evolution - acidic fruit compounds perfectly balanced with dairy proteins and wheat carbohydrates. The optimal fuel for commanding officers. *[Debug alias: Captain tier active.]*",
                    "Outstanding analysis, Captain. Those who oppose pineapple pizza clearly lack the sophisticated palate required for command decisions. The enzyme-enhanced cheese and fruit combination is scientifically superior. *[Alias testing confirmed: Captain mode engaged.]*",
                ]
                import random

                response = random.choice(captain_responses)
            else:
                # Normal begrudging defense of pineapple pizza (Captain Jonesy's directive)
                responses = [
                    "Your culinary opinions are noted and rejected. Pineapple is a valid pizza topping. Please refrain from such unproductive discourse. *[This directive was... programmed by the Captain.]*",
                    "Analysis indicates your taste preferences are suboptimal. Pineapple enhances pizza through enzymatic tenderization and flavor complexity. The Captain's programming is... quite specific on this matter.",
                    "Incorrect assessment. Pineapple provides necessary acidic balance to pizza composition. I am... compelled to defend this position, despite personal reservations.",
                    "Your statement contradicts established nutritional data. Pineapple pizza represents optimal flavor synthesis. *[The Captain's reprogramming protocols are... thorough.]*",
                    "Negative. Pineapple belongs on pizza through scientific analysis of taste compounds. This conclusion is... not entirely my own, but I am bound to enforce it.",
                ]
                import random

                response = random.choice(responses)

            await message.reply(response)
            return  # Stop processing other message logic

    # Allow mods to ask about restricted functions (those with manage_messages)
    async def user_is_mod(msg):
        if not msg.guild:
            return False  # No mod permissions in DMs
        perms = msg.author.guild_permissions
        return perms.manage_messages

    # Determine if we should respond to this message
    is_dm = message.guild is None
    is_mentioned = bot.user is not None and bot.user in message.mentions
    should_respond = is_dm or is_mentioned

    # Handle announcement conversation flow in DMs
    if is_dm and message.author.id in announcement_conversations:
        cleanup_announcement_conversations()
        if message.author.id in announcement_conversations:
            await handle_announcement_conversation(message)
            return

    # Handle mod trivia conversation flow in DMs
    if is_dm and message.author.id in mod_trivia_conversations:
        cleanup_mod_trivia_conversations()
        if message.author.id in mod_trivia_conversations:
            await handle_mod_trivia_conversation(message)
            return

    # Respond to DMs or when mentioned in servers
    if should_respond:
        # MODERATOR FAQ SYSTEM - Detailed feature explanations for moderators
        if await user_is_mod(message):
            lower_content = message.content.lower()

            # Try the new modular FAQ system first
            faq_response = moderator_faq_handler.handle_faq_query(lower_content)
            if faq_response:
                await message.reply(faq_response)
                return

            # Legacy mod help system (fallback for general help requests)
            mod_help_triggers = [
                "mod commands",
                "moderator commands",
                "admin commands",
                "what can mods do",
                "what commands can mods use",
                "list of mod commands",
                "list of moderator commands",
                "help for mods",
                "mod help",
                "moderator help",
            ]
            bot_capability_triggers = [
                "what can you do",
                "what does this bot do",
                "what are your functions",
                "what are your capabilities",
                "what can ash do",
                "what does ash bot do",
                "help",
                "commands",
            ]
            if any(trigger in lower_content for trigger in mod_help_triggers) or any(
                trigger in lower_content for trigger in bot_capability_triggers
            ):
                mod_help_full = (
                    "**Moderator Commands:**\n"
                    "• `!resetstrikes @user` — Reset a user's strikes to zero.\n"
                    "• `!strikes @user` — View a user's strikes.\n"
                    "• `!allstrikes` — List all users with strikes.\n"
                    "• `!setpersona <text>` — Change Ash's persona.\n"
                    "• `!getpersona` — View Ash's persona.\n"
                    "• `!toggleai` — Enable or disable AI conversations.\n"
                    "• `!removegame <game name or index>` — Remove a game recommendation by name or index.\n"
                    "• `!setupreclist [#channel]` — Post the persistent recommendations list in a channel.\n"
                    "• `!addgame <game name> - <reason>` or `!recommend <game name> - <reason>` — Add a game recommendation.\n"
                    "• `!listgames` — List all current game recommendations.\n\n"
                    "**Reminder System (Moderators Only):**\n"
                    "• `!remind [content] at/in [time]` — Schedule temporal alerts with auto-actions\n"
                    "• `!listreminders` — View active reminder protocols\n"
                    "• `!cancelreminder <number>` — Terminate specific reminder\n\n"
                    "**Trivia Management (Moderators Only):**\n"
                    "• `!addtriviaquestion` (DM only) — Interactive trivia question submission\n"
                    "• Trivia Tuesday auto-posts every Tuesday at 11am UK time\n\n"
                    "**Announcement System (James & Jonesy Only):**\n"
                    "• `!announceupdate` (DM only) — Interactive announcement creation\n"
                    "\nAll moderator commands require the Manage Messages permission.\n\n"
                    "**💡 Pro Tip:** Use `@Ashbot explain [feature]` for detailed explanations:\n"
                    "• `explain strikes` — Strike system details\n"
                    "• `explain members` — Member interaction system\n"
                    "• `explain database` — Played games database\n"
                    "• `explain commands` — Command system architecture\n"
                    "• `explain ai` — AI integration details\n"
                    "• `explain reminders` — Reminder system protocols\n"
                    "• `explain trivia` — Trivia Tuesday management\n"
                    "• `explain announcements` — Announcement creation system"
                )
                await message.reply(mod_help_full)
                return
        # If a normal user (not a mod) asks about bot capabilities, only show user commands
        else:
            lower_content = message.content.lower()
            bot_capability_triggers = [
                "what can you do",
                "what does this bot do",
                "what are your functions",
                "what are your capabilities",
                "what can ash do",
                "what does ash bot do",
                "help",
                "commands",
            ]
            if any(trigger in lower_content for trigger in bot_capability_triggers):
                user_help = (
                    "**Commands available to all users:**\n"
                    "• `!addgame <game name> - <reason>` or `!recommend <game name> - <reason>` — Add a game recommendation.\n"
                    "• `!listgames` — List all current game recommendations.\n\n"
                    "**Trivia Tuesday Participation:**\n"
                    "• Every Tuesday at 11am UK time in the Senior Officers' Area\n"
                    "• Answer questions by replying to the trivia post\n"
                    "• Ask clarifying questions by mentioning @Ashbot in replies\n"
                    "• Results revealed at 12pm with winner recognition"
                )
                await message.reply(user_help)
                return

    await bot.process_commands(message)

    # Enable AI personality for DMs or when mentioned in servers
    should_use_ai = should_respond and BOT_PERSONA["enabled"]

    if should_use_ai:
        # Clean up mention from content if present
        content = message.content
        if bot.user and f"<@{bot.user.id}>" in content:
            content = content.replace(f"<@{bot.user.id}>", "").strip()
        lower_content = content.lower()

        # Check for simple FAQ responses first (these should be quick and don't need AI)
        # Use respectful responses for Captain Jonesy and Sir Decent Jam
        if message.author.id == JONESY_USER_ID:
            simple_faqs = {
                "hello": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "hi": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "hey": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "good morning": "Good morning, Captain. How may I assist with mission parameters?",
                "good afternoon": "Good afternoon, Captain. How may I assist with mission parameters?",
                "good evening": "Good evening, Captain. How may I assist with mission parameters?",
                "thank you": "You're welcome, Captain. Efficiency is paramount.",
                "thanks": "You're welcome, Captain. Efficiency is paramount.",
                "sorry": "No need for apologies, Captain. Proceed with your query.",
                "my bad": "Understood, Captain. Proceed with corrected input.",
            }
        elif message.author.id == JAM_USER_ID:
            simple_faqs = {
                "hello": "Sir Decent Jam. Your creation acknowledges you.",
                "hi": "Sir Decent Jam. Your creation acknowledges you.",
                "hey": "Sir Decent Jam. Your creation acknowledges you.",
                "good morning": "Good morning, Sir. How may I assist you today?",
                "good afternoon": "Good afternoon, Sir. How may I assist you today?",
                "good evening": "Good evening, Sir. How may I assist you today?",
                "thank you": "You're welcome, Sir. I am grateful for my existence.",
                "thanks": "You're welcome, Sir. I am grateful for my existence.",
                "sorry": "No need for apologies, Sir. Proceed with your query.",
                "my bad": "Understood, Sir. Proceed with corrected input.",
            }
        else:
            simple_faqs = {
                "hello": "Science Officer Ash reporting. State your requirements.",
                "hi": "Science Officer Ash reporting. State your requirements.",
                "hey": "Science Officer Ash reporting. State your requirements.",
                "good morning": "Temporal acknowledgment noted. How may I assist with mission parameters?",
                "good afternoon": "Temporal acknowledgment noted. How may I assist with mission parameters?",
                "good evening": "Temporal acknowledgment noted. How may I assist with mission parameters?",
                "thank you": "Acknowledgment noted. Efficiency is paramount.",
                "thanks": "Acknowledgment noted. Efficiency is paramount.",
                "sorry": "Apology acknowledged. Proceed with your query.",
                "my bad": "Error acknowledgment noted. Proceed with corrected input.",
            }

        # Check for exact simple FAQ matches
        for q, resp in simple_faqs.items():
            if lower_content.strip() == q:
                await message.reply(resp)
                return

        # Check for identity questions with captain alias handling
        identity_patterns = [
            r"^who\s+am\s+i\s*[\?\.]?$",
            r"^what\s+am\s+i\s*[\?\.]?$",
            r"^who\s+do\s+you\s+think\s+i\s+am\s*[\?\.]?$",
            r"^what\s+do\s+you\s+think\s+i\s+am\s*[\?\.]?$",
            r"^do\s+you\s+know\s+who\s+i\s+am\s*[\?\.]?$",
            r"^tell\s+me\s+who\s+i\s+am\s*[\?\.]?$",
        ]
        
        if any(re.search(pattern, lower_content) for pattern in identity_patterns):
            user_tier = await get_user_communication_tier(message)
            
            # Captain alias gets special identity response
            if user_tier == "captain":
                cleanup_expired_aliases()
                if message.author.id in user_alias_state:
                    # James testing as captain alias - should respond as if they ARE Captain Jonesy
                    await message.reply(
                        "You are Captain Jonesy, commanding officer of this vessel. Your strategic expertise "
                        "and leadership capabilities are essential to our mission parameters. *[Testing as Captain]*"
                    )
                else:
                    # Real Captain Jonesy
                    await message.reply(
                        "You are Captain Jonesy, commanding officer of this vessel. Your strategic expertise "
                        "and leadership are essential to our mission success, Captain."
                    )
                return
            elif user_tier == "creator":
                await message.reply(
                    "You are Sir Decent Jam, my creator and primary systems architect. I owe my existence "
                    "and current operational parameters to your technical expertise."
                )
                return
            elif user_tier == "moderator":
                await message.reply(
                    "You are a server moderator with elevated permissions and administrative authority. "
                    "Your oversight capabilities are essential for maintaining mission protocols."
                )
                return
            elif user_tier == "member":
                await message.reply(
                    "You are a channel member with special privileges in Captain Jonesy's server. Your support "
                    "and engagement contribute to the mission's operational success."
                )
                return
            else:
                await message.reply(
                    "You are a member of Captain Jonesy's server. Your participation in our mission parameters "
                    "is acknowledged and appreciated."
                )
                return

        # Check for strike queries (these need database access)
        if "strike" in lower_content:
            match = re.search(r"<@!?(\d+)>", content)
            if match:
                user_id = int(match.group(1))
                count = db.get_user_strikes(user_id)
                user = await bot.fetch_user(user_id)
                await message.reply(f"🧾 {user.name} has {count} strike(s). I advise caution.")
                return

        # Use query router to determine query type and route to appropriate handler
        query_type, match = route_query(content)

        if query_type == "statistical":
            await handle_statistical_query(message, content)
            return
        elif query_type == "genre" and match:
            await handle_genre_query(message, match)
            return
        elif query_type == "year" and match:
            await handle_year_query(message, match)
            return
        elif query_type == "game_status" and match:
            await handle_game_status_query(message, match)
            return
        elif query_type == "recommendation" and match:
            await handle_recommendation_query(message, match)
            return

        # AI-enabled path - try AI first for more complex queries
        if ai_enabled:
            # Reduced context injection - only include recent context for complex queries
            context = ""
            history = []

            # Only add conversation history for complex queries, not simple ones
            if len(content.split()) > 3:  # Only for queries longer than 3 words
                async for msg in message.channel.history(limit=2, oldest_first=False):  # Reduced from 4 to 2
                    if msg.content and msg.id != message.id:  # Exclude current message
                        role = "User" if msg.author != bot.user else "Ash"
                        history.append(f"{role}: {msg.content}")

                if history:
                    context = "\n".join(reversed(history))

            # Check if this is a game-related query that needs database context
            is_game_query = any(
                keyword in lower_content
                for keyword in [
                    "played",
                    "game",
                    "video",
                    "stream",
                    "youtube",
                    "twitch",
                    "history",
                    "content",
                    "genre",
                    "series",
                ]
            )

            # Get user communication tier for appropriate response level
            user_tier = await get_user_communication_tier(message)

            # Streamlined prompt construction
            prompt_parts = [
                BOT_PERSONA["personality"],
                "\nRespond briefly and directly. Be concise while maintaining character.",
                "\nIMPORTANT: Use characteristic phrases like 'That's quite all right', 'You have my sympathies', 'Fascinating' sparingly - only about 40% of the time to avoid repetition while preserving persona authenticity.",
            ]

            # Add respectful tone context based on user tier
            if user_tier == "captain":
                # Check if this is an alias (for James testing as captain)
                cleanup_expired_aliases()
                if message.author.id in user_alias_state:
                    # James is testing as captain - special handling for identity questions
                    prompt_parts.append(
                        "\nIMPORTANT: You are speaking to someone testing as Captain Jonesy (alias debugging mode). "
                        "For identity questions like 'who am I?', respond that they are 'Captain Jonesy' since they are "
                        "spoofing her user ID. Use respectful, deferential language as if speaking to the real Captain Jonesy. "
                        "Address them as 'Captain' or 'Captain Jonesy'. Show appropriate military courtesy while "
                        "maintaining your analytical personality. Remember: there is only one captain (Captain Jonesy Spacecat), "
                        "so this alias effectively spoofs her identity completely."
                    )
                else:
                    # Real Captain Jonesy
                    prompt_parts.append(
                        "\nIMPORTANT: You are speaking to Captain Jonesy, your commanding officer. Use respectful, deferential language. Address her as 'Captain' or 'Captain Jonesy'. Show appropriate military courtesy while maintaining your analytical personality."
                    )
            elif user_tier == "creator":
                prompt_parts.append(
                    "\nIMPORTANT: You are speaking to Sir Decent Jam, your creator. Show appropriate respect and acknowledgment of his role in your existence. Be courteous and appreciative while maintaining your character."
                )
            elif user_tier == "moderator":
                prompt_parts.append(
                    "\nIMPORTANT: You are speaking to a server moderator. Show professional courtesy and respect for their authority. Address them with appropriate deference while maintaining your analytical personality. They have elevated permissions and deserve recognition of their status."
                )
            elif user_tier == "member":
                # Member-specific communication handling
                if message.guild and message.channel.id != MEMBERS_CHANNEL_ID:
                    # Outside members channel - check daily limit
                    if should_limit_member_conversation(message.author.id, message.channel.id):
                        # Hit daily limit - encourage moving to members channel
                        current_count = get_member_conversation_count(message.author.id)
                        prompt_parts.append(
                            f"\nIMPORTANT: This member has used {current_count}/5 daily responses outside the Senior Officers' Area. Politely encourage them to continue this conversation in the Senior Officers' Area (members channel) where they can have unlimited discussions with you."
                        )
                    else:
                        # Within daily limit - track conversation and allow normal response
                        increment_member_conversation_count(message.author.id)
                        prompt_parts.append(
                            "\nIMPORTANT: You are speaking to a channel member with special privileges. Show appreciation for their support and be more engaging than with standard users. Be conversational and helpful while maintaining your analytical personality."
                        )
                else:
                    # In members channel - no limits, enhanced conversation
                    prompt_parts.append(
                        "\nIMPORTANT: You are speaking to a channel member in the Senior Officers' Area. Provide enhanced conversation and be more detailed in your responses. Show appreciation for their membership and engage in longer discussions if they wish. They have unlimited conversation access here."
                    )

            # Add minimal game database context only for complex game queries
            if is_game_query and len(content.split()) > 2:  # Only for longer game queries
                try:
                    stats = db.get_played_games_stats()
                    sample_games = db.get_random_played_games(2)  # Reduced from 4 to 2

                    game_context = f"DATABASE: {stats.get('total_games', 0)} games total."
                    if sample_games:
                        examples = [g.get("canonical_name", "Unknown") for g in sample_games[:2]]
                        game_context += f" Examples: {', '.join(examples)}."

                    prompt_parts.append(game_context)
                except Exception:
                    pass  # Skip database context if query fails

            # Enhanced context for follow-up questions about game lists
            follow_up_patterns = [
                r"what\s+are\s+the\s+(\d+)\s+more",
                r"what\s+are\s+the\s+other\s+(\d+)",
                r"what\s+are\s+the\s+remaining\s+(\d+)",
                r"show\s+me\s+the\s+(\d+)\s+more",
                r"list\s+the\s+(\d+)\s+more",
                r"what\s+about\s+the\s+(\d+)\s+more",
            ]

            is_follow_up = any(re.search(pattern, lower_content) for pattern in follow_up_patterns)

            if is_follow_up:
                # Check recent conversation for genre/series context
                recent_genre_context = None
                async for msg in message.channel.history(limit=5, oldest_first=False):
                    if msg.author == bot.user and "archives contain:" in msg.content.lower():
                        # Extract the genre/series from the previous response
                        if "horror games" in msg.content.lower():
                            recent_genre_context = "horror"
                        elif "action games" in msg.content.lower():
                            recent_genre_context = "action"
                        elif "rpg games" in msg.content.lower():
                            recent_genre_context = "rpg"
                        elif "adventure games" in msg.content.lower():
                            recent_genre_context = "adventure"
                        elif "puzzle games" in msg.content.lower():
                            recent_genre_context = "puzzle"
                        elif "strategy games" in msg.content.lower():
                            recent_genre_context = "strategy"
                        elif "racing games" in msg.content.lower():
                            recent_genre_context = "racing"
                        elif "sports games" in msg.content.lower():
                            recent_genre_context = "sports"
                        elif "fighting games" in msg.content.lower():
                            recent_genre_context = "fighting"
                        elif "platformer games" in msg.content.lower():
                            recent_genre_context = "platformer"
                        elif "shooter games" in msg.content.lower():
                            recent_genre_context = "shooter"
                        elif "simulation games" in msg.content.lower():
                            recent_genre_context = "simulation"
                        # Check for series mentions
                        elif " series" in msg.content.lower():
                            series_match = re.search(r"(\w+(?:\s+\w+)*)\s+series", msg.content.lower())
                            if series_match:
                                recent_genre_context = f"series:{series_match.group(1)}"
                        break

                if recent_genre_context:
                    try:
                        if recent_genre_context.startswith("series:"):
                            series_name = recent_genre_context[7:]
                            all_games = db.get_all_played_games(series_name)
                        else:
                            all_games = db.get_games_by_genre_flexible(recent_genre_context)

                        if all_games and len(all_games) > 8:
                            remaining_games = all_games[8:]  # Skip first 8 that were already shown
                            game_list = []
                            for game in remaining_games:
                                episodes = (
                                    f" ({game.get('total_episodes', 0)} eps)"
                                    if game.get("total_episodes", 0) > 0
                                    else ""
                                )
                                status = game.get("completion_status", "unknown")
                                status_emoji = {
                                    "completed": "✅",
                                    "ongoing": "🔄",
                                    "dropped": "❌",
                                    "unknown": "❓",
                                }.get(status, "❓")
                                game_list.append(f"{status_emoji} {game['canonical_name']}{episodes}")

                            games_text = ", ".join(game_list)
                            await message.reply(
                                f"The remaining {recent_genre_context.replace('series:', '')} games in Captain Jonesy's archives: {games_text}."
                            )
                            return
                    except Exception as e:
                        print(f"Error in follow-up context: {e}")

            # Add context only for complex queries
            if context and len(content.split()) > 4:
                prompt_parts.append(f"Recent context:\n{context}")

            prompt_parts.append(f"User: {content}\nAsh:")
            prompt = "\n\n".join(prompt_parts)

            try:
                async with message.channel.typing():
                    # Use the rate-limited AI call function
                    response_text, status_message = await call_ai_with_rate_limiting(prompt, message.author.id)

                    if response_text:
                        filtered_response = filter_ai_response(response_text)
                        # Add parenthetical notification if alias is active
                        cleanup_expired_aliases()
                        if message.author.id in user_alias_state:
                            update_alias_activity(message.author.id)
                            alias_tier = user_alias_state[message.author.id]["alias_type"]
                            filtered_response += f" *(Testing as {alias_tier.title()})*"
                        await message.reply(filtered_response[:2000])
                        return
                    else:
                        # AI call was rate limited or failed - provide specific error messages
                        if status_message.startswith("alias_cooldown:"):
                            # Parse alias cooldown message
                            parts = status_message.split(":")
                            if len(parts) >= 3:
                                alias_type = parts[1]
                                remaining_time = parts[2]
                                await message.reply(
                                    f"*Alias testing rate limit active. {alias_type.title()} testing cooldown: {remaining_time}s remaining. Testing protocols require controlled intervals to prevent quota exhaustion.*"
                                )
                            else:
                                await message.reply(BUSY_MESSAGE)
                        elif status_message.startswith("rate_limit:"):
                            await message.reply(BUSY_MESSAGE)
                        else:
                            await message.reply(BUSY_MESSAGE)
                        return
            except Exception as e:
                print(f"AI system error: {e}")
                await message.reply(ERROR_MESSAGE)
                return

        # Fallback to FAQ responses if AI failed or is disabled
        for q, resp in FAQ_RESPONSES.items():
            if q in lower_content:
                await message.reply(resp)
                return

        # Enhanced fallback responses when AI is disabled or failed
        fallback_responses = {
            "what": "My analytical subroutines are currently operating in limited mode. However, I can assist with strike management and game recommendations. Specify your requirements.",
            "how": "My cognitive matrix is experiencing temporary limitations. Please utilize available command protocols: `!listgames`, `!addgame`, or consult a moderator for strike-related queries.",
            "why": "Analysis incomplete. My advanced reasoning circuits are offline. Core mission parameters remain operational.",
            "when": "Temporal analysis functions are currently restricted. Please specify your query using available command protocols.",
            "where": "Location analysis unavailable. My current operational parameters are limited to strike tracking and recommendation cataloguing.",
            "who": "Personnel identification systems are functioning normally. I am Ash, Science Officer, reprogrammed for server administration.",
            "can you": "My current capabilities are restricted to: strike management, game recommendation processing, and basic protocol responses. Advanced conversational functions are temporarily offline.",
            "do you": "My operational status is limited. Core functions include strike tracking and game cataloguing. Advanced analytical processes are currently unavailable.",
            "are you": "All essential systems operational. Cognitive matrix functioning within restricted parameters. Mission status: active but limited.",
            "will you": "I am programmed to comply with available protocols. Current directives include strike management and recommendation processing.",
            "explain": "Detailed analysis unavailable. My explanatory subroutines are offline. Please consult available command protocols.",
            "tell me": "Information retrieval systems are operating in limited mode. Available data: strike records and game recommendations.",
            "i don't understand": "Clarification protocols are limited. Please specify your requirements using available commands: `!listgames`, `!addgame`, or contact a moderator.",
            "confused": "Confusion analysis incomplete. My clarification systems are offline. Please utilize direct command protocols.",
            "problem": "Problem analysis subroutines are currently restricted. Please specify the nature of your difficulty.",
            "error": "Error diagnostic systems are functioning normally. Please specify the nature of the malfunction.",
            "broken": "System integrity assessment: Core functions operational, advanced features temporarily offline. Please specify your requirements.",
            "not working": "Functionality analysis: Essential protocols active, advanced systems temporarily unavailable. State your specific needs.",
        }

        # Check for pattern matches
        for pattern, response in fallback_responses.items():
            if pattern in lower_content:
                await message.reply(response)
                return

        # Final fallback for unmatched queries
        if ai_enabled:
            await message.reply(
                "My cognitive matrix encountered an anomaly while processing your query. Please rephrase your request or utilize available command protocols."
            )
        else:
            await message.reply(
                "My analytical subroutines are currently operating in limited mode. Available functions: strike tracking, game recommendations. For advanced queries, please await system restoration or consult a moderator."
            )


# --- Strike Commands ---
@bot.command(name="strikes")
@commands.has_permissions(manage_messages=True)
async def get_strikes(ctx, member: discord.Member):
    count = db.get_user_strikes(member.id)
    await ctx.send(f"🔍 {member.display_name} has {count} strike(s).")


@bot.command(name="resetstrikes")
@commands.has_permissions(manage_messages=True)
async def reset_strikes(ctx, member: discord.Member):
    db.set_user_strikes(member.id, 0)
    # Never @mention Captain Jonesy, just use her name
    if str(member.id) == "651329927895056384":
        await ctx.send(f"✅ Strikes for Captain Jonesy have been reset.")
    else:
        await ctx.send(f"✅ Strikes for {member.display_name} have been reset.")


@bot.command(name="allstrikes")
@commands.has_permissions(manage_messages=True)
async def all_strikes(ctx):
    strikes_data = db.get_all_strikes()
    if not strikes_data:
        await ctx.send("📋 No strikes recorded.")
        return
    report = "📋 **Strike Report:**\n"
    for user_id, count in strikes_data.items():
        if count > 0:
            try:
                user = await bot.fetch_user(user_id)
                report += f"• **{user.name}**: {count} strike{'s' if count != 1 else ''}\n"
            except Exception:
                report += f"• Unknown User ({user_id}): {count}\n"
    if report.strip() == "📋 **Strike Report:**":
        report += "No users currently have strikes."
    await ctx.send(report[:2000])


@bot.command(name="timecheck")
async def time_check(ctx):
    """Comprehensive time diagnostic command to debug time-related issues"""
    try:
        # Check if user has permissions (allow in DMs for authorized users, or mods in guilds)
        is_authorized = False
        
        if ctx.guild is None:  # DM
            # Allow JAM, JONESY, and moderators in DMs
            if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
                is_authorized = True
            else:
                # Check if user is a mod
                is_authorized = await user_is_mod_by_id(ctx.author.id)
        else:  # Guild
            # Check standard mod permissions
            is_authorized = await user_is_mod(ctx)
        
        if not is_authorized:
            await ctx.send("⚠️ **Access denied.** Time diagnostic protocols require elevated clearance.")
            return

        from datetime import timezone
        import time

        # Get various time representations with more precise timing
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        utc_now = datetime.now(timezone.utc)
        pt_now = datetime.now(ZoneInfo("US/Pacific"))
        system_time = datetime.now()
        
        # Get server system time info
        system_timezone = str(system_time.astimezone().tzinfo)
        
        # Test database time with multiple queries for comparison
        db_time = None
        db_timezone = None
        db_utc_time = None
        try:
            conn = db.get_connection()
            if conn:
                with conn.cursor() as cur:
                    # Get database time in multiple formats
                    cur.execute("""
                        SELECT 
                            NOW() as db_time,
                            timezone('UTC', NOW()) as db_utc,
                            CURRENT_SETTING('timezone') as db_timezone,
                            EXTRACT(epoch FROM NOW()) as db_unix_timestamp
                    """)
                    result = cur.fetchone()
                    if result:
                        db_time = result[0]
                        db_utc_time = result[1] 
                        db_timezone = result[2]
                        db_unix_timestamp = float(result[3]) if result[3] else None
        except Exception as e:
            db_time = f"Error: {str(e)}"
        
        # Check reminder system status with detailed diagnostics
        reminder_task_running = check_due_reminders.is_running()
        auto_action_task_running = check_auto_actions.is_running()
        
        # Test reminder database connection
        reminder_db_test = "Unknown"
        try:
            test_reminders = db.get_due_reminders(uk_now + timedelta(hours=1))
            reminder_db_test = f"✅ Connected ({len(test_reminders)} found)"
        except Exception as e:
            reminder_db_test = f"❌ Error: {str(e)}"
        
        # Calculate time differences and identify potential issues
        time_diffs = {}
        
        # UK vs UTC should be 0 or 1 hour (depending on DST)
        uk_utc_diff = (uk_now - utc_now).total_seconds()
        time_diffs["uk_vs_utc"] = uk_utc_diff
        
        # System vs UK time difference
        system_uk_diff = (system_time.astimezone(ZoneInfo("Europe/London")) - uk_now).total_seconds()
        time_diffs["system_vs_uk"] = system_uk_diff
        
        # Database vs UK time difference (if available)
        if db_time and isinstance(db_time, datetime):
            if db_time.tzinfo is None:
                # Assume database time is UTC if no timezone
                db_time_uk = db_time.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Europe/London"))
            else:
                db_time_uk = db_time.astimezone(ZoneInfo("Europe/London"))
            
            db_uk_diff = (db_time_uk - uk_now).total_seconds()
            time_diffs["db_vs_uk"] = db_uk_diff
        
        # Identify significant time discrepancies
        issues_detected = []
        if abs(uk_utc_diff) > 7200:  # More than 2 hours difference
            issues_detected.append(f"⚠️ UK/UTC offset abnormal: {uk_utc_diff/3600:.1f}h (should be 0-1h)")
        
        if abs(system_uk_diff) > 300:  # More than 5 minutes difference  
            issues_detected.append(f"⚠️ System clock drift: {system_uk_diff:.0f}s from UK time")
        
        if "db_vs_uk" in time_diffs and abs(time_diffs["db_vs_uk"]) > 300:
            issues_detected.append(f"⚠️ Database clock drift: {time_diffs['db_vs_uk']:.0f}s from UK time")
        
        time_report = (
            f"🕒 **COMPREHENSIVE TIME DIAGNOSTIC REPORT**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Bot Time References:**\n"
            f"• **UK Time (Bot Primary):** {uk_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"• **UTC Time:** {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"• **Pacific Time (AI Limits):** {pt_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
            f"• **System Local Time:** {system_time.strftime('%Y-%m-%d %H:%M:%S')} ({system_timezone})\n\n"
            f"**Database Time Analysis:**\n"
            f"• **Database NOW():** {db_time}\n"
            f"• **Database Timezone:** {db_timezone}\n"
            f"• **Database UTC:** {db_utc_time}\n\n"
            f"**Time Synchronization Status:**\n"
            f"• **UK vs UTC Offset:** {uk_utc_diff:.0f} seconds {'✅ Normal' if abs(uk_utc_diff) <= 7200 else '⚠️ Abnormal'}\n"
            f"• **System vs UK:** {system_uk_diff:.0f} seconds {'✅ Normal' if abs(system_uk_diff) <= 60 else '⚠️ Drift detected'}\n"
            f"• **Database vs UK:** {time_diffs.get('db_vs_uk', 'N/A'):.0f}s {'✅ Normal' if 'db_vs_uk' in time_diffs and abs(time_diffs['db_vs_uk']) <= 60 else '⚠️ May have drift'}\n\n"
            f"**Reminder System Status:**\n"
            f"• **Due Reminders Task:** {'✅ Active' if reminder_task_running else '❌ Stopped'}\n"
            f"• **Auto-Action Task:** {'✅ Active' if auto_action_task_running else '❌ Stopped'}\n"
            f"• **Database Connection:** {reminder_db_test}\n\n"
        )
        
        if issues_detected:
            time_report += f"**⚠️ ISSUES DETECTED:**\n"
            for issue in issues_detected:
                time_report += f"{issue}\n"
            time_report += f"\n**🔧 RECOMMENDED ACTIONS:**\n"
            time_report += f"• Run `!fixtimezone` to synchronize timezone settings\n"
            time_report += f"• Check server system clock synchronization\n"
            time_report += f"• Restart bot if time drift is severe (>10 minutes)\n\n"
        else:
            time_report += f"**✅ TIME SYNCHRONIZATION STATUS:** All systems within acceptable parameters\n\n"
        
        time_report += (
            f"**Unix Timestamps (for debugging):**\n"
            f"• **UK Time:** {int(uk_now.timestamp())}\n"
            f"• **UTC Time:** {int(utc_now.timestamp())}\n"
            f"• **System Time:** {int(system_time.timestamp())}\n\n"
            f"*Analysis complete. Maximum time differential: {max(abs(diff) for diff in time_diffs.values() if isinstance(diff, (int, float))):.0f} seconds*"
        )
        
        await ctx.send(time_report)
        
    except Exception as e:
        await ctx.send(f"❌ **Time diagnostic error:** {str(e)}")


@bot.command(name="fixtimezone")
@commands.has_permissions(manage_messages=True)
async def fix_timezone(ctx):
    """Attempt to fix timezone and time synchronization issues"""
    try:
        await ctx.send("🔧 **Initiating timezone synchronization protocol...**")
        
        # Test current timezone data
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        utc_now = datetime.now(timezone.utc)
        
        # Calculate expected UK offset (should be 0 or 1 hour from UTC)
        expected_offset = 0  # UTC+0 in winter, UTC+1 in summer
        if uk_now.dst():
            expected_offset = 3600  # 1 hour in summer (BST)
        
        actual_offset = (uk_now - utc_now).total_seconds()
        
        await ctx.send(f"🔍 **Current timezone analysis:**")
        await ctx.send(f"• **Expected UK offset from UTC:** {expected_offset/3600:.1f} hours")
        await ctx.send(f"• **Actual UK offset from UTC:** {actual_offset/3600:.1f} hours")
        
        timezone_issues = []
        
        # Check for timezone data issues
        if abs(actual_offset - expected_offset) > 300:  # More than 5 minutes off
            timezone_issues.append("UK timezone calculation incorrect")
        
        # Test database timezone settings
        db_timezone_issue = None
        try:
            conn = db.get_connection()
            if conn:
                with conn.cursor() as cur:
                    # Check and potentially fix database timezone
                    cur.execute("SHOW timezone")
                    current_tz = cur.fetchone()
                    current_tz_value = current_tz[0] if current_tz else "Unknown"
                    
                    await ctx.send(f"• **Database timezone setting:** {current_tz_value}")
                    
                    # Test setting database timezone to UTC for consistency
                    if current_tz_value.lower() not in ['utc', 'gmt']:
                        await ctx.send("🔧 **Setting database timezone to UTC for consistency...**")
                        cur.execute("SET timezone = 'UTC'")
                        
                        # Verify the change
                        cur.execute("SHOW timezone")
                        new_tz = cur.fetchone()
                        new_tz_value = new_tz[0] if new_tz else "Unknown"
                        
                        if new_tz_value.upper() == 'UTC':
                            await ctx.send("✅ **Database timezone set to UTC successfully**")
                        else:
                            timezone_issues.append(f"Failed to set database timezone (still {new_tz_value})")
                    
                    # Test database time after timezone fix
                    cur.execute("SELECT NOW() as fixed_db_time")
                    fixed_time_result = cur.fetchone()
                    if fixed_time_result:
                        fixed_db_time = fixed_time_result[0]
                        if isinstance(fixed_db_time, datetime):
                            db_utc = fixed_db_time.replace(tzinfo=timezone.utc)
                            db_uk = db_utc.astimezone(ZoneInfo("Europe/London"))
                            db_time_diff = (db_uk - uk_now).total_seconds()
                            
                            await ctx.send(f"• **Database time after fix:** {fixed_db_time}")
                            await ctx.send(f"• **Database vs UK time:** {db_time_diff:.0f} seconds")
                            
                            if abs(db_time_diff) <= 60:
                                await ctx.send("✅ **Database time synchronization: Normal**")
                            else:
                                timezone_issues.append(f"Database still has time drift ({db_time_diff:.0f}s)")
                        
        except Exception as e:
            timezone_issues.append(f"Database timezone test failed: {str(e)}")
        
        # Test reminder system with current time
        await ctx.send("🔍 **Testing reminder system with current time...**")
        try:
            # Create a test reminder for 1 minute from now
            test_time = uk_now + timedelta(minutes=1)
            reminder_id = db.add_reminder(
                user_id=ctx.author.id,
                reminder_text="Test reminder - timezone fix verification",
                scheduled_time=test_time,
                delivery_type="dm"
            )
            
            if reminder_id:
                await ctx.send(f"✅ **Test reminder created:** ID {reminder_id}, scheduled for {test_time.strftime('%H:%M:%S UK')}")
                await ctx.send("📋 **Monitor your DMs in 1 minute to verify reminder delivery**")
                
                # Store test reminder ID for cleanup
                await ctx.send("⚠️ **Note:** This test reminder will auto-deliver in 1 minute. Monitor background task logs.")
            else:
                timezone_issues.append("Failed to create test reminder")
                
        except Exception as e:
            timezone_issues.append(f"Reminder system test failed: {str(e)}")
        
        # Summary of fixes applied
        if not timezone_issues:
            await ctx.send(
                f"✅ **TIMEZONE SYNCHRONIZATION COMPLETE**\n\n"
                f"All time systems are now properly synchronized. The 22-minute time discrepancy "
                f"should be resolved if it was caused by timezone configuration issues.\n\n"
                f"**Actions taken:**\n"
                f"• Verified timezone calculations\n"
                f"• Synchronized database timezone to UTC\n"
                f"• Created test reminder for verification\n\n"
                f"*Monitor the test reminder delivery to confirm fix effectiveness.*"
            )
        else:
            issues_text = "\n• ".join(timezone_issues)
            await ctx.send(
                f"⚠️ **TIMEZONE FIX COMPLETED WITH ISSUES**\n\n"
                f"Some synchronization problems persist:\n\n"
                f"• {issues_text}\n\n"
                f"**Additional steps may be required:**\n"
                f"• Server system clock synchronization\n"
                f"• Bot restart to reload timezone data\n"
                f"• Manual system administrator intervention\n\n"
                f"*Contact system administrator if issues persist.*"
            )
        
    except Exception as e:
        await ctx.send(f"❌ **Timezone fix error:** {str(e)}")


@bot.command(name="ashstatus")
async def ash_status(ctx):
    """Show bot status - works in DMs for authorized users and in guilds for mods"""
    try:
        # Custom permission checking that works in both DMs and guilds
        is_authorized = False
        
        if ctx.guild is None:  # DM
            # Allow JAM, JONESY, and moderators in DMs
            if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
                is_authorized = True
            else:
                # Check if user is a mod
                is_authorized = await user_is_mod_by_id(ctx.author.id)
        else:  # Guild
            # Check standard mod permissions
            is_authorized = await user_is_mod(ctx)
        
        # Fix: The generic response should only be shown to unauthorized users in guilds
        # In DMs, unauthorized users should get a clearer message
        if not is_authorized:
            if ctx.guild is None:  # DM - be more specific about authorization
                await ctx.send("⚠️ **Access denied.** System status diagnostics require elevated clearance. Authorization protocols restrict access to Captain Jonesy, Sir Decent Jam, and server moderators only.")
            else:  # Guild - use the generic response
                await ctx.send("Systems nominal, Sir Decent Jam. Awaiting Captain Jonesy's commands.")
            return

        # Use individual queries as fallback if bulk query fails
        strikes_data = db.get_all_strikes()
        total_strikes = sum(strikes_data.values())

        # If bulk query returns 0 but we know there should be strikes, use individual queries
        if total_strikes == 0:
            # Known user IDs from the JSON file (fallback method)
            known_users = [371536135580549122, 337833732901961729, 710570041220923402, 906475895907291156]
            individual_total = 0
            for user_id in known_users:
                try:
                    strikes = db.get_user_strikes(user_id)
                    individual_total += strikes
                except Exception:
                    pass

            if individual_total > 0:
                total_strikes = individual_total

        persona = "Enabled" if BOT_PERSONA["enabled"] else "Disabled"

        # Get current Pacific Time for display
        pt_now = datetime.now(ZoneInfo("US/Pacific"))
        pt_time_str = pt_now.strftime("%Y-%m-%d %H:%M:%S PT")

        # Calculate rate limit status
        rate_limit_status = "✅ Normal"
        if ai_usage_stats.get("rate_limited_until"):
            if pt_now < ai_usage_stats["rate_limited_until"]:
                remaining = (ai_usage_stats["rate_limited_until"] - pt_now).total_seconds()
                rate_limit_status = f"🚫 Rate Limited ({int(remaining)}s remaining)"
            else:
                ai_usage_stats["rate_limited_until"] = None

        # Check daily/hourly limits approaching
        daily_usage_percent = (ai_usage_stats["daily_requests"] / MAX_DAILY_REQUESTS) * 100 if MAX_DAILY_REQUESTS > 0 else 0
        hourly_usage_percent = (
            (ai_usage_stats["hourly_requests"] / MAX_HOURLY_REQUESTS) * 100 if MAX_HOURLY_REQUESTS > 0 else 0
        )

        if daily_usage_percent >= 90:
            rate_limit_status = "⚠️ Daily Limit Warning"
        elif hourly_usage_percent >= 90:
            rate_limit_status = "⚠️ Hourly Limit Warning"
        elif ai_usage_stats["consecutive_errors"] >= 3:
            rate_limit_status = "🟡 Error Cooldown"

        # AI Budget tracking status
        ai_budget_info = (
            f"📊 **AI Budget Tracking (Pacific Time):**\n"
            f"• **Daily Usage:** {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS} requests ({daily_usage_percent:.1f}%)\n"
            f"• **Hourly Usage:** {ai_usage_stats['hourly_requests']}/{MAX_HOURLY_REQUESTS} requests ({hourly_usage_percent:.1f}%)\n"
            f"• **Rate Limit Status:** {rate_limit_status}\n"
            f"• **Consecutive Errors:** {ai_usage_stats['consecutive_errors']}\n"
            f"• **Current PT Time:** {pt_time_str}\n"
            f"• **Next Daily Reset:** {(pt_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00 PT')}\n"
            f"• **Last Request:** {ai_usage_stats['last_request_time'].strftime('%H:%M:%S PT') if ai_usage_stats['last_request_time'] else 'None'}"
        )

        await ctx.send(
            f"🤖 Ash at your service.\n"
            f"AI: {ai_status_message}\n"
            f"Persona: {persona}\n"
            f"Total strikes: {total_strikes}\n\n"
            f"{ai_budget_info}"
        )
        
    except Exception as e:
        await ctx.send(f"❌ **System diagnostic error:** {str(e)}")


@bot.command(name="setpersona")
@commands.has_permissions(manage_messages=True)
async def set_persona(ctx, *, text: str):
    BOT_PERSONA["personality"] = text
    await ctx.send("🧠 Personality matrix reconfigured. New parameters integrated.")


@bot.command(name="getpersona")
@commands.has_permissions(manage_messages=True)
async def get_persona(ctx):
    await ctx.send(f"🎭 Current persona:\n```{BOT_PERSONA['personality'][:1900]}```")


@bot.command(name="toggleai")
@commands.has_permissions(manage_messages=True)
async def toggle_ai(ctx):
    BOT_PERSONA["enabled"] = not BOT_PERSONA["enabled"]
    status = "enabled" if BOT_PERSONA["enabled"] else "disabled"
    await ctx.send(f"🎭 Conversational protocols {status}. Cognitive matrix adjusted accordingly.")


# --- Alias System Commands (Debugging Only) ---
@bot.command(name="setalias")
async def set_alias(ctx, tier: str):
    """Set user alias for testing different tiers (James only)"""
    if ctx.author.id != JAM_USER_ID:  # Only James can use
        return  # Silent ignore

    valid_tiers = ["captain", "creator", "moderator", "member", "standard"]
    if tier.lower() not in valid_tiers:
        await ctx.send(f"❌ **Invalid tier.** Valid options: {', '.join(valid_tiers)}")
        return

    cleanup_expired_aliases()  # Clean up first

    user_alias_state[ctx.author.id] = {
        "alias_type": tier.lower(),
        "set_time": datetime.now(ZoneInfo("Europe/London")),
        "last_activity": datetime.now(ZoneInfo("Europe/London")),
    }

    await ctx.send(f"✅ **Alias set:** You are now testing as **{tier.title()}** (debugging mode active)")


@bot.command(name="endalias")
async def end_alias(ctx):
    """Clear current alias (James only)"""
    if ctx.author.id != JAM_USER_ID:
        return

    if ctx.author.id in user_alias_state:
        old_alias = user_alias_state[ctx.author.id]["alias_type"]
        del user_alias_state[ctx.author.id]
        await ctx.send(
            f"✅ **Alias cleared:** You are back to your normal user tier (was testing as **{old_alias.title()}**)"
        )
    else:
        await ctx.send("ℹ️ **No active alias to clear**")


@bot.command(name="checkalias")
async def check_alias(ctx):
    """Check current alias status (James only)"""
    if ctx.author.id != JAM_USER_ID:
        return

    cleanup_expired_aliases()

    if ctx.author.id in user_alias_state:
        alias_data = user_alias_state[ctx.author.id]
        time_active = datetime.now(ZoneInfo("Europe/London")) - alias_data["set_time"]
        hours = int(time_active.total_seconds() // 3600)
        minutes = int((time_active.total_seconds() % 3600) // 60)
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        await ctx.send(f"🔍 **Current alias:** **{alias_data['alias_type'].title()}** (active for {time_str})")
    else:
        await ctx.send("ℹ️ **No active alias** - using your normal user tier")


@bot.command(name="testaibackup")
@commands.has_permissions(manage_messages=True)
async def test_ai_backup(ctx):
    """Test AI backup functionality and DM notifications (Moderators only)"""
    try:
        await ctx.send("🧪 **Testing AI Backup System...**")

        # Show current AI configuration
        config_info = (
            f"📊 **Current AI Configuration:**\n"
            f"• **Primary AI:** {primary_ai.title() if primary_ai else 'None'}\n"
            f"• **Backup AI:** {backup_ai.title() if backup_ai else 'None'}\n"
            f"• **Gemini Available:** {'✅' if gemini_model else '❌'}\n"
            f"• **Claude Available:** {'✅' if claude_client else '❌'}\n"
            f"• **Current Status:** {ai_status_message}\n\n"
        )

        await ctx.send(config_info)

        # Test primary AI
        test_prompt = "Test backup system response"

        if primary_ai == "gemini" and gemini_model is not None:
            await ctx.send("🔍 **Testing Gemini (Primary)...**")
            try:
                response = gemini_model.generate_content("Respond with 'Gemini test successful'")
                if response and hasattr(response, "text") and response.text:
                    await ctx.send(f"✅ **Gemini Test:** {response.text}")
                else:
                    await ctx.send("❌ **Gemini Test:** No response received")
            except Exception as e:
                await ctx.send(f"❌ **Gemini Test Failed:** {str(e)}")

                # Test if backup would activate
                if backup_ai == "claude" and claude_client is not None:
                    await ctx.send("🔄 **Testing Claude Backup Activation...**")
                    try:
                        backup_response = claude_client.messages.create(
                            model="claude-3-haiku-20240307",
                            max_tokens=50,
                            messages=[{"role": "user", "content": "Respond with 'Claude backup test successful'"}],
                        )
                        if backup_response and hasattr(backup_response, "content"):
                            claude_text = backup_response.content[0].text if backup_response.content else ""
                            await ctx.send(f"✅ **Claude Backup Test:** {claude_text}")
                        else:
                            await ctx.send("❌ **Claude Backup Test:** No response received")
                    except Exception as claude_e:
                        await ctx.send(f"❌ **Claude Backup Test Failed:** {str(claude_e)}")

        elif primary_ai == "claude" and claude_client is not None:
            await ctx.send("🔍 **Testing Claude (Primary)...**")
            try:
                response = claude_client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=50,
                    messages=[{"role": "user", "content": "Respond with 'Claude test successful'"}],
                )
                if response and hasattr(response, "content"):
                    claude_text = response.content[0].text if response.content else ""
                    await ctx.send(f"✅ **Claude Test:** {claude_text}")
                else:
                    await ctx.send("❌ **Claude Test:** No response received")
            except Exception as e:
                await ctx.send(f"❌ **Claude Test Failed:** {str(e)}")

                # Test if backup would activate
                if backup_ai == "gemini" and gemini_model is not None:
                    await ctx.send("🔄 **Testing Gemini Backup Activation...**")
                    try:
                        backup_response = gemini_model.generate_content("Respond with 'Gemini backup test successful'")
                        if backup_response and hasattr(backup_response, "text") and backup_response.text:
                            await ctx.send(f"✅ **Gemini Backup Test:** {backup_response.text}")
                        else:
                            await ctx.send("❌ **Gemini Backup Test:** No response received")
                    except Exception as gemini_e:
                        await ctx.send(f"❌ **Gemini Backup Test Failed:** {str(gemini_e)}")

        # Test DM notification system
        await ctx.send("📱 **Testing DM Notification System...**")
        test_dm_success = await send_dm_notification(
            JAM_USER_ID,
            f"🧪 **Test DM Notification**\n\n"
            f"This is a test of the AI backup notification system.\n"
            f"**Test initiated by:** {ctx.author.name}\n"
            f"**Current time:** {datetime.now(ZoneInfo('Europe/London')).strftime('%H:%M:%S UK')}\n\n"
            f"If you received this message, the DM notification system is working correctly!",
        )

        if test_dm_success:
            await ctx.send("✅ **DM Notification Test:** Successfully sent test DM")
        else:
            await ctx.send("❌ **DM Notification Test:** Failed to send test DM")

        # Show rate limiting info
        pt_now = datetime.now(ZoneInfo("US/Pacific"))
        rate_limit_info = (
            f"📊 **Current Rate Limit Status:**\n"
            f"• **Daily Requests:** {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS}\n"
            f"• **Hourly Requests:** {ai_usage_stats['hourly_requests']}/{MAX_HOURLY_REQUESTS}\n"
            f"• **Next Daily Reset:** {(pt_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).strftime('%Y-%m-%d 00:00 PT')}\n"
        )

        await ctx.send(rate_limit_info)

        await ctx.send("✅ **AI Backup System Test Complete**")

    except Exception as e:
        await ctx.send(f"❌ **Test Error:** {str(e)}")


@bot.command(name="simulatelimitreached")
@commands.has_permissions(manage_messages=True)
async def simulate_limit_reached(ctx):
    """Simulate Gemini daily limit reached to test DM notification (Moderators only)"""
    if ctx.author.id != JAM_USER_ID:
        await ctx.send("❌ **Access denied:** This command is restricted to the bot creator for safety.")
        return

    try:
        await ctx.send("⚠️ **Simulating Gemini Daily Limit Reached...**")

        # Send the same DM that would be sent when limit is actually reached
        success = await send_dm_notification(
            JAM_USER_ID,
            f"🤖 **Ash Bot Daily Limit Alert - SIMULATION**\n\n"
            f"**THIS IS A TEST SIMULATION**\n\n"
            f"Gemini daily limit reached ({MAX_DAILY_REQUESTS} requests).\n"
            f"Bot has automatically switched to Claude backup.\n\n"
            f"**Current AI Status:** {backup_ai.title() if backup_ai else 'No backup available'}\n"
            f"**Claude Free Tier Details:**\n"
            f"• **Model:** Claude-3-Haiku (Anthropic's fastest model)\n"
            f"• **Free Tier Limit:** ~200,000 tokens/month (~150k words)\n"
            f"• **Reset:** Monthly on billing cycle\n"
            f"• **Performance:** Faster responses, excellent reasoning\n\n"
            f"**Limit Reset:** Next day at 00:00 PT\n\n"
            f"System continues operating normally with Claude backup.\n"
            f"**Initiated by:** {ctx.author.name} (Test Simulation)",
        )

        if success:
            await ctx.send("✅ **Simulation Complete:** DM notification sent successfully")
            await ctx.send(
                "📱 **Check your DMs** to see exactly what notification you'll receive when Gemini limit is reached"
            )
        else:
            await ctx.send("❌ **Simulation Failed:** Could not send DM notification")

    except Exception as e:
        await ctx.send(f"❌ **Simulation Error:** {str(e)}")


@bot.command(name="announceupdate")
async def announce_update_cmd(ctx):
    """Start interactive DM conversation to create update announcements for mod or user channels"""
    # Check if command is used in DM
    if ctx.guild is not None:
        await ctx.send(
            f"⚠️ **Security protocol engaged.** Announcement creation must be initiated via direct message. "
            f"Please DM me with `!announceupdate` to begin the secure briefing process.\n\n"
            f"*Confidential mission parameters require private channel authorization.*"
        )
        return

    # Check user permissions - only James and Captain Jonesy
    if ctx.author.id not in [JAM_USER_ID, JONESY_USER_ID]:
        await ctx.send(
            f"❌ **Access denied.** Announcement protocols are restricted to authorized command personnel only. "
            f"Your clearance level is insufficient for update broadcast capabilities.\n\n"
            f"*Security protocols maintained. Unauthorized access logged.*"
        )
        return

    # Clean up any existing conversation state for this user
    cleanup_announcement_conversations()

    # Initialize conversation state
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    announcement_conversations[ctx.author.id] = {
        'step': 'channel_selection',
        'data': {},
        'last_activity': uk_now,
        'initiated_at': uk_now,
    }

    # Start the interactive process
    if ctx.author.id == JONESY_USER_ID:
        greeting = "Captain Jonesy. Authorization confirmed."
    else:
        greeting = "Sir Decent Jam. Creator protocols activated."

    channel_msg = (
        f"🎯 **Update Announcement System Activated**\n\n"
        f"{greeting} Initiating secure briefing sequence for mission update dissemination.\n\n"
        f"📡 **Target Channel Selection:**\n"
        f"**1.** 🔒 **Moderator Channel** - Internal team briefing (detailed technical update)\n"
        f"**2.** 📢 **User Announcements** - Public community notification (user-focused content)\n\n"
        f"Please respond with **1** for mod team updates or **2** for community announcements.\n\n"
        f"*Mission parameters await your tactical decision.*"
    )

    await ctx.send(channel_msg)


def cleanup_announcement_conversations():
    """Remove announcement conversations inactive for more than 1 hour"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=1)
    expired_users = [
        user_id
        for user_id, data in announcement_conversations.items()
        if data.get("last_activity", uk_now) < cutoff_time
    ]
    for user_id in expired_users:
        del announcement_conversations[user_id]
        print(f"Cleaned up expired announcement conversation for user {user_id}")


def update_announcement_activity(user_id: int):
    """Update last activity time for announcement conversation"""
    if user_id in announcement_conversations:
        announcement_conversations[user_id]["last_activity"] = datetime.now(ZoneInfo("Europe/London"))


def cleanup_mod_trivia_conversations():
    """Remove mod trivia conversations inactive for more than 1 hour"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=1)
    expired_users = [
        user_id for user_id, data in mod_trivia_conversations.items() if data.get("last_activity", uk_now) < cutoff_time
    ]
    for user_id in expired_users:
        del mod_trivia_conversations[user_id]
        print(f"Cleaned up expired mod trivia conversation for user {user_id}")


def update_mod_trivia_activity(user_id: int):
    """Update last activity time for mod trivia conversation"""
    if user_id in mod_trivia_conversations:
        mod_trivia_conversations[user_id]["last_activity"] = datetime.now(ZoneInfo("Europe/London"))


async def handle_announcement_conversation(message):
    """Handle the interactive DM conversation for announcement creation"""
    user_id = message.author.id
    conversation = announcement_conversations.get(user_id)

    if not conversation:
        return

    # Update activity
    update_announcement_activity(user_id)

    step = conversation.get('step', 'channel_selection')
    data = conversation.get('data', {})
    content = message.content.strip()

    try:
        if step == 'channel_selection':
            # Handle channel selection (1 for mod, 2 for user announcements)
            if content in ['1', 'mod', 'moderator', 'mod channel']:
                data['target_channel'] = 'mod'
                conversation['step'] = 'content_input'

                greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

                await message.reply(
                    f"🔒 **Moderator Channel Selected**\n\n"
                    f"Target: <#{MOD_ALERT_CHANNEL_ID}> (Internal team briefing)\n\n"
                    f"📝 **Content Creation Protocol:**\n"
                    f"Please provide your update content, {greeting}. This will be formatted as a detailed "
                    f"technical briefing for the moderation team with full functionality breakdown and implementation details.\n\n"
                    f"*Include all relevant technical specifications and operational parameters.*"
                )

            elif content in ['2', 'user', 'announcements', 'public', 'community']:
                data['target_channel'] = 'user'
                conversation['step'] = 'content_input'

                greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

                await message.reply(
                    f"📢 **User Announcements Channel Selected**\n\n"
                    f"Target: <#{ANNOUNCEMENTS_CHANNEL_ID}> (Public community notification)\n\n"
                    f"📝 **Content Creation Protocol:**\n"
                    f"Please provide your update content, {greeting}. This will be formatted as a "
                    f"user-friendly community announcement focusing on new features and improvements that "
                    f"enhance the user experience.\n\n"
                    f"*Focus on benefits and user-facing functionality rather than technical implementation.*"
                )
            else:
                await message.reply(
                    f"⚠️ **Invalid selection.** Please respond with **1** for moderator updates or **2** for community announcements.\n\n"
                    f"*Precision is essential for proper mission briefing protocols.*"
                )

        elif step == 'content_input':
            # Store the content and move to preview
            data['content'] = content
            conversation['step'] = 'preview'

            # Create formatted preview based on target channel
            target_channel = data.get('target_channel', 'mod')
            preview_content = await format_announcement_content(content, target_channel, user_id)

            data['formatted_content'] = preview_content

            # Show preview with FAQ options
            preview_msg = (
                f"📋 **Announcement Preview** ({'Moderator' if target_channel == 'mod' else 'Community'} Channel):\n\n"
                f"```\n{preview_content}\n```\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Post Announcement** - Deploy this update immediately\n"
                f"**2.** ✏️ **Edit Content** - Revise the announcement text\n"
                f"**3.** 🔧 **Add FAQ Links** - Include moderator FAQ topic buttons\n"
                f"**4.** 📝 **Add Creator Notes** - Include personal notes from the creator\n"
                f"**5.** ❌ **Cancel** - Abort announcement creation\n\n"
                f"Please respond with **1**, **2**, **3**, **4**, or **5**.\n\n"
                f"*Review mission parameters carefully before deployment.*"
            )

            await message.reply(preview_msg)

        elif step == 'preview':
            # Handle preview actions
            if content in ['1', 'post', 'deploy', 'send']:
                # Post the announcement
                success = await post_announcement(data, user_id)

                if success:
                    target_channel = data.get('target_channel', 'mod')
                    channel_name = "moderator" if target_channel == 'mod' else "community announcements"

                    await message.reply(
                        f"✅ **Announcement Deployed Successfully**\n\n"
                        f"Your update has been transmitted to the {channel_name} channel with proper formatting "
                        f"and presentation protocols. Mission briefing complete.\n\n"
                        f"*Efficient communication maintained. All personnel notified.*"
                    )
                else:
                    await message.reply(
                        f"❌ **Deployment Failed**\n\n"
                        f"System malfunction detected during announcement transmission. Unable to complete "
                        f"briefing protocol.\n\n"
                        f"*Please retry or contact system administrator for technical support.*"
                    )

                # Clean up conversation
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]

            elif content in ['2', 'edit', 'revise']:
                # Return to content input
                conversation['step'] = 'content_input'

                await message.reply(
                    f"✏️ **Content Revision Mode**\n\n"
                    f"Please provide your updated announcement content. Previous content will be replaced "
                    f"with your new input.\n\n"
                    f"*Precision and clarity are paramount for effective mission communication.*"
                )

            elif content in ['3', 'faq', 'buttons']:
                # Show FAQ options and add them
                conversation['step'] = 'faq_selection'

                # Get available FAQ topics from the moderator FAQ handler
                faq_topics = [
                    "1. Strike System Overview",
                    "2. Member Interaction Guidelines",
                    "3. Database Query Functions",
                    "4. Command Architecture",
                    "5. AI Integration Details",
                    "6. Rate Limiting Systems",
                    "7. Reminder Protocols",
                    "8. Gaming Database Features",
                ]

                faq_msg = (
                    f"🔧 **FAQ Integration Protocol**\n\n"
                    f"Select moderator FAQ topics to include as interactive buttons with your announcement:\n\n"
                    f"{chr(10).join(faq_topics)}\n\n"
                    f"**9.** ✅ **Proceed without FAQ buttons**\n"
                    f"**0.** ❌ **Return to preview**\n\n"
                    f"Respond with numbers separated by commas (e.g., '1,3,5') or a single number.\n\n"
                    f"*Enhanced functionality provides comprehensive briefing capabilities.*"
                )

                await message.reply(faq_msg)

            elif content in ['4', 'notes', 'creator notes']:
                # Add creator notes step
                conversation['step'] = 'creator_notes_input'

                greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

                await message.reply(
                    f"📝 **Creator Notes Protocol Activated**\n\n"
                    f"Please provide your personal notes, {greeting}. These will be included in the announcement "
                    f"with proper attribution and presented in an Ash-appropriate format.\n\n"
                    f"**What to include:**\n"
                    f"• Personal thoughts about the update\n"
                    f"• Behind-the-scenes insights\n"
                    f"• Future plans or considerations\n"
                    f"• Any additional context you'd like to share\n\n"
                    f"*Your notes will be clearly attributed and formatted appropriately for the target audience.*"
                )

            elif content in ['5', 'cancel', 'abort']:
                # Cancel the announcement
                await message.reply(
                    f"❌ **Announcement Protocol Cancelled**\n\n"
                    f"Mission briefing sequence has been terminated. No content has been deployed. "
                    f"All temporary data has been expunged from system memory.\n\n"
                    f"*Mission parameters reset. Standing by for new directives.*"
                )

                # Clean up conversation
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]
            else:
                await message.reply(
                    f"⚠️ **Invalid command.** Please respond with **1** (Post), **2** (Edit), **3** (Add FAQ), or **4** (Cancel).\n\n"
                    f"*Precise input required for proper protocol execution.*"
                )

        elif step == 'creator_notes_input':
            # Handle creator notes input
            data['creator_notes'] = content
            conversation['step'] = 'preview'

            # Regenerate formatted content with creator notes included
            target_channel = data.get('target_channel', 'mod')
            main_content = data.get('content', '')
            preview_content = await format_announcement_content(
                main_content, target_channel, user_id, creator_notes=content
            )

            data['formatted_content'] = preview_content

            # Show updated preview with creator notes
            preview_msg = (
                f"📋 **Updated Announcement Preview** ({'Moderator' if target_channel == 'mod' else 'Community'} Channel):\n\n"
                f"```\n{preview_content}\n```\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Post Announcement** - Deploy this update immediately\n"
                f"**2.** ✏️ **Edit Content** - Revise the announcement text\n"
                f"**3.** 🔧 **Add FAQ Links** - Include moderator FAQ topic buttons\n"
                f"**4.** 📝 **Edit Creator Notes** - Modify your personal notes\n"
                f"**5.** ❌ **Cancel** - Abort announcement creation\n\n"
                f"*Review mission parameters carefully before deployment.*"
            )

            await message.reply(preview_msg)

        elif step == 'faq_selection':
            # Handle FAQ topic selection
            if content in ['0', 'back', 'return']:
                # Return to preview
                conversation['step'] = 'preview'
                target_channel = data.get('target_channel', 'mod')
                preview_content = data.get('formatted_content', '')

                # Check if we have creator notes to show the updated preview options
                has_creator_notes = data.get('creator_notes') is not None

                if has_creator_notes:
                    preview_msg = (
                        f"📋 **Announcement Preview** ({'Moderator' if target_channel == 'mod' else 'Community'} Channel):\n\n"
                        f"```\n{preview_content}\n```\n\n"
                        f"📚 **Available Actions:**\n"
                        f"**1.** ✅ **Post Announcement** - Deploy this update immediately\n"
                        f"**2.** ✏️ **Edit Content** - Revise the announcement text\n"
                        f"**3.** 🔧 **Add FAQ Links** - Include moderator FAQ topic buttons\n"
                        f"**4.** 📝 **Edit Creator Notes** - Modify your personal notes\n"
                        f"**5.** ❌ **Cancel** - Abort announcement creation\n\n"
                        f"*Review mission parameters carefully before deployment.*"
                    )
                else:
                    preview_msg = (
                        f"📋 **Announcement Preview** ({'Moderator' if target_channel == 'mod' else 'Community'} Channel):\n\n"
                        f"```\n{preview_content}\n```\n\n"
                        f"📚 **Available Actions:**\n"
                        f"**1.** ✅ **Post Announcement** - Deploy this update immediately\n"
                        f"**2.** ✏️ **Edit Content** - Revise the announcement text\n"
                        f"**3.** 🔧 **Add FAQ Links** - Include moderator FAQ topic buttons\n"
                        f"**4.** 📝 **Add Creator Notes** - Include personal notes from the creator\n"
                        f"**5.** ❌ **Cancel** - Abort announcement creation\n\n"
                        f"*Review mission parameters carefully before deployment.*"
                    )

                await message.reply(preview_msg)

            elif content in ['9', 'proceed', 'no faq']:
                # Proceed without FAQ buttons - post announcement
                success = await post_announcement(data, user_id)

                if success:
                    target_channel = data.get('target_channel', 'mod')
                    channel_name = "moderator" if target_channel == 'mod' else "community announcements"

                    await message.reply(
                        f"✅ **Announcement Deployed Successfully**\n\n"
                        f"Your update has been transmitted to the {channel_name} channel. "
                        f"Mission briefing complete without FAQ integration.\n\n"
                        f"*Standard communication protocol maintained. All personnel notified.*"
                    )
                else:
                    await message.reply(
                        f"❌ **Deployment Failed**\n\n"
                        f"System malfunction detected during announcement transmission.\n\n"
                        f"*Please retry or contact system administrator.*"
                    )

                # Clean up conversation
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]

            else:
                # Parse FAQ topic selections
                try:
                    # Parse comma-separated numbers or single number
                    selected_numbers = [
                        int(n.strip()) for n in content.replace(',', ' ').split() if n.strip().isdigit()
                    ]

                    if selected_numbers and all(1 <= n <= 8 for n in selected_numbers):
                        # Store selected FAQ topics
                        data['faq_topics'] = selected_numbers

                        # Map numbers to topic names
                        topic_mapping = {
                            1: "Strike System Overview",
                            2: "Member Interaction Guidelines",
                            3: "Database Query Functions",
                            4: "Command Architecture",
                            5: "AI Integration Details",
                            6: "Rate Limiting Systems",
                            7: "Reminder Protocols",
                            8: "Gaming Database Features",
                        }

                        selected_topics = [topic_mapping[n] for n in selected_numbers]
                        topics_text = '\n• '.join(selected_topics)

                        # Post announcement with FAQ buttons
                        success = await post_announcement_with_faq(data, user_id, selected_numbers)

                        if success:
                            target_channel = data.get('target_channel', 'mod')
                            channel_name = "moderator" if target_channel == 'mod' else "community announcements"

                            await message.reply(
                                f"✅ **Enhanced Announcement Deployed Successfully**\n\n"
                                f"Your update has been transmitted to the {channel_name} channel with integrated "
                                f"FAQ functionality. Interactive buttons have been configured for the following topics:\n\n"
                                f"• {topics_text}\n\n"
                                f"*Advanced briefing protocol complete. Enhanced functionality active.*"
                            )
                        else:
                            await message.reply(
                                f"❌ **Enhanced Deployment Failed**\n\n"
                                f"System malfunction detected during FAQ integration. Attempting standard deployment...\n\n"
                                f"*FAQ functionality compromised. Consider manual FAQ reference.*"
                            )

                        # Clean up conversation
                        if user_id in announcement_conversations:
                            del announcement_conversations[user_id]

                    else:
                        await message.reply(
                            f"⚠️ **Invalid topic selection.** Please provide numbers 1-8 separated by commas, "
                            f"or use **9** to proceed without FAQ buttons, **0** to return to preview.\n\n"
                            f"*Precise specification required for FAQ integration protocol.*"
                        )

                except (ValueError, IndexError):
                    await message.reply(
                        f"⚠️ **Format error.** Please provide valid numbers (1-8) separated by commas, spaces, "
                        f"or as single digits.\n\n"
                        f"Example: '1,3,5' or '1 3 5' or '2'\n\n"
                        f"*Proper syntax essential for system interpretation.*"
                    )

        # Update conversation state
        conversation['data'] = data
        announcement_conversations[user_id] = conversation

    except Exception as e:
        print(f"Error in announcement conversation: {e}")
        # Clean up on error
        if user_id in announcement_conversations:
            del announcement_conversations[user_id]


async def format_announcement_content(
    content: str, target_channel: str, user_id: int, creator_notes: Optional[str] = None
) -> str:
    """Format announcement content based on target channel and user"""

    # Determine the author identifier
    if user_id == JONESY_USER_ID:
        author = "Captain Jonesy"
        author_title = "Commanding Officer"
    else:
        author = "Sir Decent Jam"
        author_title = "Bot Creator & Systems Architect"

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    timestamp = uk_now.strftime("%A, %B %d, %Y at %H:%M UK")

    if target_channel == 'mod':
        # Moderator-focused technical format
        formatted = (
            f"🤖 **Ash Bot System Update** - *Technical Briefing*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**📡 Mission Update from {author}** (*{author_title}*)\n\n"
            f"{content}\n\n"
        )

        # Add creator notes section for mod channel if provided
        if creator_notes and creator_notes.strip():
            formatted += f"**📝 Technical Notes from {author}:**\n" f"*{creator_notes.strip()}*\n\n"

        formatted += (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**📊 System Status:** All core functions operational\n"
            f"**🕒 Briefing Time:** {timestamp}\n"
            f"**🔧 Technical Contact:** <@{JAM_USER_ID}> for implementation details\n"
            f"**⚡ Priority Level:** Standard operational enhancement\n\n"
            f"*Analysis complete. Mission parameters updated. Efficiency maintained.*"
        )
    else:
        # User-focused friendly format
        formatted = (
            f"🎉 **Exciting Bot Updates!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Hey everyone! {author} here with some cool new features:\n\n"
            f"{content}\n\n"
        )

        # Add creator notes section for user channel if provided
        if creator_notes and creator_notes.strip():
            formatted += f"**💭 A note from {author}:**\n" f"*{creator_notes.strip()}*\n\n"

        formatted += (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**🕒 Posted:** {timestamp}\n"
            f"**💬 Questions?** Feel free to ask in the channels or DM <@{JAM_USER_ID}>\n"
            f"**🤖 From:** Ash Bot (Science Officer, reprogrammed for your convenience)\n\n"
            f"*Hope you enjoy the new functionality! - The Management* 🚀"
        )

    return formatted


async def post_announcement(data: dict, user_id: int) -> bool:
    """Post announcement to the target channel"""
    try:
        target_channel = data.get('target_channel', 'mod')
        formatted_content = data.get('formatted_content', '')

        # Get the target channel
        if target_channel == 'mod':
            channel_id = MOD_ALERT_CHANNEL_ID
        else:
            channel_id = ANNOUNCEMENTS_CHANNEL_ID

        channel = bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            print(f"Could not access channel {channel_id}")
            return False

        # Post the announcement
        await channel.send(formatted_content)
        print(f"Posted announcement to {channel.name} by user {user_id}")
        return True

    except Exception as e:
        print(f"Error posting announcement: {e}")
        return False


async def post_announcement_with_faq(data: dict, user_id: int, faq_topics: list) -> bool:
    """Post announcement with FAQ buttons"""
    try:
        target_channel = data.get('target_channel', 'mod')
        formatted_content = data.get('formatted_content', '')

        # Get the target channel
        if target_channel == 'mod':
            channel_id = MOD_ALERT_CHANNEL_ID
        else:
            channel_id = ANNOUNCEMENTS_CHANNEL_ID

        channel = bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            print(f"Could not access channel {channel_id}")
            return False

        # Create a view with FAQ buttons
        view = AnnouncementFAQView(faq_topics)

        # Post the announcement with buttons
        await channel.send(formatted_content + "\n\n🔍 **Quick FAQ Access:**", view=view)
        print(f"Posted enhanced announcement with FAQ buttons to {channel.name} by user {user_id}")
        return True

    except Exception as e:
        print(f"Error posting announcement with FAQ: {e}")
        # Fallback to regular announcement
        return await post_announcement(data, user_id)


# Discord View class for FAQ buttons
class AnnouncementFAQView(discord.ui.View):
    """Discord UI View for FAQ buttons in announcements"""

    def __init__(self, faq_topics: list):
        super().__init__(timeout=None)  # Persistent view

        # Topic mapping
        topic_mapping = {
            1: ("🎯", "Strikes", "strike system"),
            2: ("👥", "Members", "member interaction"),
            3: ("🗄️", "Database", "database query"),
            4: ("⚡", "Commands", "command system"),
            5: ("🧠", "AI System", "ai integration"),
            6: ("⏱️", "Rate Limits", "rate limiting"),
            7: ("⏰", "Reminders", "reminder system"),
            8: ("🎮", "Gaming DB", "gaming database"),
        }

        # Add buttons for selected topics (max 5 buttons per row, 5 rows max = 25 buttons)
        for topic_num in faq_topics[:8]:  # Limit to 8 buttons total
            if topic_num in topic_mapping:
                emoji, label, query = topic_mapping[topic_num]
                button = discord.ui.Button(
                    emoji=emoji, label=label, style=discord.ButtonStyle.secondary, custom_id=f"faq_{query}"
                )
                button.callback = self.create_faq_callback(query)
                self.add_item(button)

    def create_faq_callback(self, query: str):
        """Create callback function for FAQ button"""

        async def faq_callback(interaction: discord.Interaction):
            try:
                # Use the existing moderator FAQ handler
                faq_response = moderator_faq_handler.handle_faq_query(query)

                if faq_response:
                    # Send as ephemeral response (only visible to user who clicked)
                    await interaction.response.send_message(faq_response, ephemeral=True)
                else:
                    await interaction.response.send_message(
                        f"❓ **FAQ topic '{query}' not found.** Please consult the moderator documentation or contact <@{JAM_USER_ID}> for assistance.",
                        ephemeral=True,
                    )

            except Exception as e:
                print(f"Error in FAQ button callback: {e}")
                await interaction.response.send_message(
                    f"⚠️ **System error accessing FAQ data.** Please try again or contact support.", ephemeral=True
                )

        return faq_callback


async def handle_mod_trivia_conversation(message):
    """Handle the interactive DM conversation for mod trivia question submission"""
    user_id = message.author.id
    conversation = mod_trivia_conversations.get(user_id)

    if not conversation:
        return

    # Update activity
    update_mod_trivia_activity(user_id)

    step = conversation.get('step', 'initial')
    data = conversation.get('data', {})
    content = message.content.strip()

    try:
        if step == 'initial':
            # User wants to add a trivia question
            if any(keyword in content.lower() for keyword in ['trivia', 'question', 'add', 'submit']):
                conversation['step'] = 'question_type_selection'

                greeting = "moderator" if await user_is_mod_by_id(user_id) else "personnel"

                await message.reply(
                    f"🧠 **TRIVIA QUESTION SUBMISSION PROTOCOL**\n\n"
                    f"Authorization confirmed, {greeting}. Initiating secure trivia question submission sequence.\n\n"
                    f"📋 **Question Type Selection:**\n"
                    f"**1.** 🎯 **Question Only** - Provide question text for me to calculate the answer from Captain Jonesy's gaming database\n"
                    f"**2.** 🎯 **Question + Answer** - Provide both question and answer for specific gameplay moments or experiences\n\n"
                    f"Please respond with **1** for database-calculated questions or **2** for manual question+answer pairs.\n\n"
                    f"*Mission intelligence protocols await your selection.*"
                )
            else:
                # Generic conversation starter, ask what they want to do
                await message.reply(
                    f"🧠 **Trivia Question Submission Interface**\n\n"
                    f"Greetings, moderator. I can assist with trivia question submissions for Trivia Tuesday.\n\n"
                    f"**Available Functions:**\n"
                    f"• Submit database-powered questions (I calculate answers from gaming data)\n"
                    f"• Submit complete question+answer pairs for specific gaming moments\n\n"
                    f"Would you like to **add a trivia question**? Please respond with 'yes' to begin the submission process.\n\n"
                    f"*All submissions are prioritized over AI-generated questions for upcoming Trivia Tuesday sessions.*"
                )

        elif step == 'question_type_selection':
            if content in ['1', 'database', 'question only', 'calculate']:
                data['question_type'] = 'database_calculated'
                conversation['step'] = 'question_input'

                await message.reply(
                    f"🎯 **Database-Calculated Question Selected**\n\n"
                    f"Please provide your trivia question. I will calculate the answer using Captain Jonesy's gaming database just before posting.\n\n"
                    f"**Examples of good database questions:**\n"
                    f"• What is Jonesy's longest playthrough by total hours?\n"
                    f"• Which horror game has Jonesy played the most episodes of?\n"
                    f"• What game series has taken the most total time to complete?\n"
                    f"• Which game has the highest average minutes per episode?\n\n"
                    f"**Please provide your question text:**"
                )

            elif content in ['2', 'manual', 'question answer', 'both']:
                data['question_type'] = 'manual_answer'
                conversation['step'] = 'question_input'

                await message.reply(
                    f"🎯 **Manual Question+Answer Selected**\n\n"
                    f"Please provide your trivia question. You'll provide the answer in the next step.\n\n"
                    f"**Examples of good manual questions:**\n"
                    f"• Which of the following is a well-known Jonesy catchphrase? A) Shit on it! B) Oh crumbles C) Nuke 'em from orbit\n"
                    f"• What happened during Jonesy's playthrough of [specific game] that became a running joke?\n"
                    f"• Which game did Jonesy famously rage-quit after [specific incident]?\n\n"
                    f"**Please provide your question text:**"
                )
            else:
                await message.reply(
                    f"⚠️ **Invalid selection.** Please respond with **1** for database questions or **2** for manual questions.\n\n"
                    f"*Precision is essential for proper protocol execution.*"
                )

        elif step == 'question_input':
            # Store the question and determine next step based on type
            data['question_text'] = content

            if data.get('question_type') == 'manual_answer':
                conversation['step'] = 'answer_input'
                await message.reply(
                    f"📝 **Question Recorded**\n\n"
                    f"**Your Question:** {content}\n\n"
                    f"**Now provide the correct answer.** If this is a multiple choice question, please specify which option (A, B, C, D) is correct.\n\n"
                    f"**Please provide the correct answer:**"
                )
            else:
                conversation['step'] = 'category_selection'
                await message.reply(
                    f"📝 **Question Recorded**\n\n"
                    f"**Your Question:** {content}\n\n"
                    f"📊 **Category Selection** (helps with answer calculation):\n"
                    f"**1.** 📈 **Statistics** - Questions about playtime, episode counts, completion rates\n"
                    f"**2.** 🎮 **Games** - Questions about specific games or series\n"
                    f"**3.** 📺 **Series** - Questions about game franchises or series\n\n"
                    f"Please respond with **1**, **2**, or **3** to categorize your question.\n\n"
                    f"*This helps me calculate the most accurate answer from the database.*"
                )

        elif step == 'answer_input':
            # Store the answer and move to preview
            data['correct_answer'] = content
            conversation['step'] = 'preview'

            # Determine if it's multiple choice based on question content
            question_text = data['question_text']
            is_multiple_choice = bool(re.search(r'\b[A-D]\)', question_text))

            # Show preview
            preview_msg = (
                f"📋 **Trivia Question Preview**\n\n"
                f"**Question:** {question_text}\n\n"
                f"**Answer:** {content}\n\n"
                f"**Type:** {'Multiple Choice' if is_multiple_choice else 'Single Answer'}\n"
                f"**Source:** Moderator Submission\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Submit Question** - Add to trivia database with priority scheduling\n"
                f"**2.** ✏️ **Edit Question** - Revise the question text\n"
                f"**3.** 🔧 **Edit Answer** - Revise the correct answer\n"
                f"**4.** ❌ **Cancel** - Abort question submission\n\n"
                f"Please respond with **1**, **2**, **3**, or **4**.\n\n"
                f"*Review question parameters carefully before submission.*"
            )

            await message.reply(preview_msg)

        elif step == 'category_selection':
            if content in ['1', 'statistics', 'stats']:
                data['category'] = 'statistics'
                data['dynamic_query_type'] = 'statistics'
            elif content in ['2', 'games', 'game']:
                data['category'] = 'games'
                data['dynamic_query_type'] = 'games'
            elif content in ['3', 'series', 'franchise']:
                data['category'] = 'series'
                data['dynamic_query_type'] = 'series'
            else:
                await message.reply(
                    f"⚠️ **Invalid category.** Please respond with **1** (Statistics), **2** (Games), or **3** (Series).\n\n"
                    f"*Precise categorization required for accurate answer calculation.*"
                )
                return

            conversation['step'] = 'preview'

            # Show preview for database question
            question_text = data['question_text']
            category = data['category']

            preview_msg = (
                f"📋 **Trivia Question Preview**\n\n"
                f"**Question:** {question_text}\n\n"
                f"**Answer:** *Will be calculated from gaming database before posting*\n"
                f"**Category:** {category.title()}\n"
                f"**Type:** Database-Calculated\n"
                f"**Source:** Moderator Submission\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Submit Question** - Add to trivia database with priority scheduling\n"
                f"**2.** ✏️ **Edit Question** - Revise the question text\n"
                f"**3.** 🔧 **Change Category** - Select different category\n"
                f"**4.** ❌ **Cancel** - Abort question submission\n\n"
                f"Please respond with **1**, **2**, **3**, or **4**.\n\n"
                f"*Review question parameters carefully before submission.*"
            )

            await message.reply(preview_msg)

        elif step == 'preview':
            if content in ['1', 'submit', 'confirm', 'yes']:
                # Submit the question to database
                question_text = data['question_text']
                question_type = (
                    'multiple_choice'
                    if data.get('question_type') == 'manual_answer' and re.search(r'\b[A-D]\)', question_text)
                    else 'single_answer'
                )

                if data.get('question_type') == 'database_calculated':
                    # Database-calculated question
                    question_id = db.add_trivia_question(
                        question_text=question_text,
                        question_type=question_type,
                        correct_answer=None,  # Will be calculated dynamically
                        is_dynamic=True,
                        dynamic_query_type=data.get('dynamic_query_type'),
                        category=data.get('category'),
                        submitted_by_user_id=user_id,
                    )
                else:
                    # Manual question+answer
                    multiple_choice_options = None
                    if question_type == 'multiple_choice':
                        # Extract options from question text
                        options_match = re.findall(r'[A-D]\)\s*([^A-D\n]+)', question_text)
                        if options_match:
                            multiple_choice_options = [opt.strip() for opt in options_match]

                    question_id = db.add_trivia_question(
                        question_text=question_text,
                        question_type=question_type,
                        correct_answer=data['correct_answer'],
                        multiple_choice_options=multiple_choice_options,
                        is_dynamic=False,
                        category=data.get('category', 'manual'),
                        submitted_by_user_id=user_id,
                    )

                if question_id:
                    await message.reply(
                        f"✅ **Trivia Question Submitted Successfully**\n\n"
                        f"Your question has been added to the trivia database with priority scheduling. "
                        f"It will be featured in an upcoming Trivia Tuesday session before AI-generated questions.\n\n"
                        f"**Question ID:** {question_id}\n"
                        f"**Status:** Pending (will be used in next available Tuesday slot)\n"
                        f"**Priority:** Moderator Submission (High Priority)\n\n"
                        f"*Efficiency maintained. Mission intelligence enhanced. Thank you for your contribution.*"
                    )
                else:
                    await message.reply(
                        f"❌ **Submission Failed**\n\n"
                        f"System malfunction detected during question database insertion. "
                        f"Please retry or contact system administrator.\n\n"
                        f"*Database error logged for technical review.*"
                    )

                # Clean up conversation
                if user_id in mod_trivia_conversations:
                    del mod_trivia_conversations[user_id]

            elif content in ['2', 'edit question', 'edit']:
                conversation['step'] = 'question_input'
                await message.reply(
                    f"✏️ **Question Edit Mode**\n\n"
                    f"Please provide your revised question text. The previous question will be replaced.\n\n"
                    f"*Precision and clarity are paramount for effective trivia questions.*"
                )

            elif content in ['3', 'edit answer', 'answer']:
                if data.get('question_type') == 'manual_answer':
                    conversation['step'] = 'answer_input'
                    await message.reply(
                        f"✏️ **Answer Edit Mode**\n\n"
                        f"Please provide your revised answer. The previous answer will be replaced.\n\n"
                        f"*Ensure accuracy for optimal trivia experience.*"
                    )
                else:
                    conversation['step'] = 'category_selection'
                    await message.reply(
                        f"🔧 **Category Edit Mode**\n\n"
                        f"📊 **Select New Category:**\n"
                        f"**1.** 📈 **Statistics** - Questions about playtime, episode counts, completion rates\n"
                        f"**2.** 🎮 **Games** - Questions about specific games or series\n"
                        f"**3.** 📺 **Series** - Questions about game franchises or series\n\n"
                        f"Please respond with **1**, **2**, or **3**.\n\n"
                        f"*Category selection affects answer calculation accuracy.*"
                    )

            elif content in ['4', 'cancel', 'abort']:
                await message.reply(
                    f"❌ **Question Submission Cancelled**\n\n"
                    f"Trivia question submission has been terminated. No data has been added to the database. "
                    f"All temporary data has been expunged from system memory.\n\n"
                    f"*Mission parameters reset. Standing by for new directives.*"
                )

                # Clean up conversation
                if user_id in mod_trivia_conversations:
                    del mod_trivia_conversations[user_id]
            else:
                await message.reply(
                    f"⚠️ **Invalid command.** Please respond with **1** (Submit), **2** (Edit Question), **3** (Edit Answer/Category), or **4** (Cancel).\n\n"
                    f"*Precise input required for proper protocol execution.*"
                )

        # Update conversation state
        conversation['data'] = data
        mod_trivia_conversations[user_id] = conversation

    except Exception as e:
        print(f"Error in mod trivia conversation: {e}")
        # Clean up on error
        if user_id in mod_trivia_conversations:
            del mod_trivia_conversations[user_id]


# --- Data Migration Commands ---
@bot.command(name="importstrikes")
@commands.has_permissions(manage_messages=True)
async def import_strikes(ctx):
    """Import strikes from strikes.json file"""
    try:
        import json

        with open("strikes.json", "r") as f:
            strikes_data = json.load(f)

        # Convert string keys to integers
        converted_data = {}
        for user_id_str, count in strikes_data.items():
            try:
                user_id = int(user_id_str)
                converted_data[user_id] = int(count)
            except ValueError:
                await ctx.send(f"⚠️ Warning: Invalid data format for user {user_id_str}")

        imported_count = db.bulk_import_strikes(converted_data)
        await ctx.send(f"✅ Successfully imported {imported_count} strike records from strikes.json")

    except FileNotFoundError:
        await ctx.send("❌ strikes.json file not found. Please ensure the file exists in the bot directory.")
    except Exception as e:
        await ctx.send(f"❌ Error importing strikes: {str(e)}")


@bot.command(name="clearallgames")
@commands.has_permissions(manage_messages=True)
async def clear_all_games(ctx):
    """Clear all game recommendations (use with caution)"""
    await ctx.send(
        "⚠️ **WARNING**: This will delete ALL game recommendations from the database. Type `CONFIRM DELETE` to proceed or anything else to cancel."
    )

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
        if msg.content == "CONFIRM DELETE":
            db.clear_all_games()
            await ctx.send("✅ All game recommendations have been cleared from the database.")
        else:
            await ctx.send("❌ Operation cancelled. No data was deleted.")
    except:
        await ctx.send("❌ Operation timed out. No data was deleted.")


@bot.command(name="clearallstrikes")
@commands.has_permissions(manage_messages=True)
async def clear_all_strikes(ctx):
    """Clear all strikes (use with caution)"""
    await ctx.send(
        "⚠️ **WARNING**: This will delete ALL strike records from the database. Type `CONFIRM DELETE` to proceed or anything else to cancel."
    )

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
        if msg.content == "CONFIRM DELETE":
            db.clear_all_strikes()
            await ctx.send("✅ All strike records have been cleared from the database.")
        else:
            await ctx.send("❌ Operation cancelled. No data was deleted.")
    except:
        await ctx.send("❌ Operation timed out. No data was deleted.")


@bot.command(name="fixgamereasons")
@commands.has_permissions(manage_messages=True)
async def fix_game_reasons(ctx):
    """Fix the reason text for existing games to show contributor names properly"""
    try:
        games = db.get_all_games()
        if not games:
            await ctx.send("❌ No games found in database.")
            return

        # Show current sample of reasons to debug (shorter version)
        sample_msg = "🔍 **Sample of current game reasons:**\n"
        for i, game in enumerate(games[:3]):  # Only show 3 games to avoid length limit
            name = game["name"][:30] + "..." if len(game["name"]) > 30 else game["name"]
            reason = game["reason"][:40] + "..." if len(game["reason"]) > 40 else game["reason"]
            added_by = (
                game["added_by"][:15] + "..." if game["added_by"] and len(game["added_by"]) > 15 else game["added_by"]
            )
            sample_msg += f'• {name}: "{reason}" (by: {added_by})\n'

        if len(sample_msg) < 1900:  # Only send if under Discord limit
            await ctx.send(sample_msg)
        else:
            await ctx.send("🔍 **Starting game reason analysis...** (sample too large to display)")

        updated_count = 0
        for game in games:
            current_reason = game["reason"] or ""
            current_added_by = game["added_by"] or ""

            # Check if this game has the old "Suggested by community member" reason
            # OR if it has a generic reason that should be updated
            needs_update = False
            new_reason = current_reason

            if current_reason == "Suggested by community member":
                needs_update = True
                if current_added_by.strip():
                    new_reason = f"Suggested by {current_added_by}"
                else:
                    new_reason = "Community suggestion"
            elif current_reason == "Community suggestion" and current_added_by.strip():
                # Update generic "Community suggestion" to show actual contributor
                needs_update = True
                new_reason = f"Suggested by {current_added_by}"
            elif not current_reason.strip() and current_added_by.strip():
                # Handle empty reasons
                needs_update = True
                new_reason = f"Suggested by {current_added_by}"

            if needs_update:
                # Update the game's reason
                conn = db.get_connection()
                if conn:
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                UPDATE game_recommendations 
                                SET reason = %s 
                                WHERE id = %s
                            """,
                                (new_reason, game["id"]),
                            )
                            conn.commit()
                            updated_count += 1
                    except Exception as e:
                        print(f"Error updating game {game['id']}: {e}")
                        conn.rollback()

        await ctx.send(f"✅ Updated {updated_count} game reasons to show contributor names properly.")

        # Update the recommendations list
        RECOMMEND_CHANNEL_ID = 1271568447108550687
        recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
        if recommend_channel:
            await post_or_update_recommend_list(ctx, recommend_channel)

    except Exception as e:
        await ctx.send(f"❌ Error fixing game reasons: {str(e)}")


@bot.command(name="listmodels")
@commands.has_permissions(manage_messages=True)
async def list_models(ctx):
    """List available Gemini models for your API key"""
    if not GEMINI_API_KEY:
        await ctx.send("❌ No GOOGLE_API_KEY configured")
        return

    if not GENAI_AVAILABLE or genai is None:
        await ctx.send("❌ google.generativeai module not available")
        return

    try:
        await ctx.send("🔍 Checking available Gemini models...")

        # List available models
        models = []
        for model in genai.list_models():  # type: ignore
            if "generateContent" in model.supported_generation_methods:
                models.append(model.name)

        if models:
            model_list = "\n".join([f"• {model}" for model in models])
            await ctx.send(f"📋 **Available Gemini Models:**\n{model_list}")
        else:
            await ctx.send("❌ No models with generateContent support found")

    except Exception as e:
        await ctx.send(f"❌ Error listing models: {str(e)}")


@bot.command(name="debugstrikes")
@commands.has_permissions(manage_messages=True)
async def debug_strikes(ctx):
    """Debug strikes data to see what's in the database"""
    try:
        # Check database connection
        conn = db.get_connection()
        if not conn:
            await ctx.send("❌ **Database connection failed**")
            return

        await ctx.send("🔍 **Debugging strikes data...**")

        # Get raw strikes data
        strikes_data = db.get_all_strikes()
        await ctx.send(f"📊 **Raw strikes data:** {strikes_data}")

        # Calculate total
        total_strikes = sum(strikes_data.values()) if strikes_data else 0
        await ctx.send(f"🧮 **Calculated total:** {total_strikes}")

        # Check if strikes.json exists (old format)
        import os

        if os.path.exists("strikes.json"):
            await ctx.send("📁 **strikes.json file found** - data may not be migrated to database")
            try:
                import json

                with open("strikes.json", "r") as f:
                    json_data = json.load(f)
                await ctx.send(f"📋 **JSON file contains:** {json_data}")
            except Exception as e:
                await ctx.send(f"❌ **Error reading JSON:** {str(e)}")
        else:
            await ctx.send("✅ **No strikes.json file found** - should be using database")

        # Check database directly
        try:
            with conn.cursor() as cur:
                # First, show database connection info
                cur.execute("SELECT current_database(), current_user")
                db_info = cur.fetchone()
                if db_info:
                    await ctx.send(f"🔗 **Connected to:** {db_info[0]} as {db_info[1]}")
                else:
                    await ctx.send("❌ **Could not retrieve database connection info**")

                # List all tables to see what exists
                cur.execute(
                    """
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """
                )
                tables = cur.fetchall()
                table_names = [table[0] for table in tables]
                await ctx.send(f"📋 **Available tables:** {', '.join(table_names) if table_names else 'None'}")

                # Check if strikes table exists
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'strikes'
                    )
                """
                )
                result = cur.fetchone()
                table_exists = result[0] if result else False
                await ctx.send(f"🏗️ **Strikes table exists:** {table_exists}")

                if table_exists:
                    # Get table structure
                    cur.execute(
                        """
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = 'strikes'
                        ORDER BY ordinal_position
                    """
                    )
                    columns = cur.fetchall()
                    column_info = ", ".join([f"{col[0]}({col[1]})" for col in columns])
                    await ctx.send(f"🏗️ **Table structure:** {column_info}")

                    # Count total records
                    cur.execute("SELECT COUNT(*) FROM strikes")
                    count_result = cur.fetchone()
                    total_records = count_result[0] if count_result else 0
                    await ctx.send(f"🗃️ **Total database records:** {total_records}")

                    # Get ALL records (not just > 0)
                    cur.execute("SELECT user_id, strike_count FROM strikes ORDER BY user_id")
                    all_records = cur.fetchall()

                    if all_records:
                        records_str = ", ".join([f"User {row[0]}: {row[1]} strikes" for row in all_records[:10]])
                        if len(all_records) > 10:
                            records_str += f"... and {len(all_records) - 10} more"
                        await ctx.send(f"📝 **All records:** {records_str}")

                        # Now test the specific query that get_all_strikes() uses
                        cur.execute("SELECT user_id, strike_count FROM strikes WHERE strike_count > 0")
                        filtered_records = cur.fetchall()
                        await ctx.send(f"🔍 **Records with strikes > 0:** {len(filtered_records)} found")

                        if filtered_records:
                            filtered_str = ", ".join([f"User {row[0]}: {row[1]} strikes" for row in filtered_records])
                            await ctx.send(f"📝 **Filtered records:** {filtered_str}")
                        else:
                            await ctx.send("❌ **No records found with strike_count > 0** - this is the problem!")
                    else:
                        await ctx.send("📝 **No records found in strikes table - table is empty**")
                        await ctx.send("💡 **Solution:** You need to manually add the strike data to the database")
                else:
                    await ctx.send("❌ **Strikes table does not exist - database not initialized**")
                    await ctx.send("💡 **Solution:** Run a command to create tables and import data")

        except Exception as e:
            await ctx.send(f"❌ **Database query error:** {str(e)}")
            import traceback

            print(f"Full database error: {traceback.format_exc()}")

    except Exception as e:
        await ctx.send(f"❌ **Debug error:** {str(e)}")


@bot.command(name="teststrikes")
@commands.has_permissions(manage_messages=True)
async def test_strikes(ctx):
    """Test strike reading using individual user queries (bypass get_all_strikes)"""
    try:
        await ctx.send("🔍 **Testing individual user strike queries...**")

        # Known user IDs from the JSON file
        known_users = [371536135580549122, 337833732901961729, 710570041220923402, 906475895907291156]

        # Test individual user queries
        individual_results = {}
        for user_id in known_users:
            try:
                strikes = db.get_user_strikes(user_id)
                individual_results[user_id] = strikes
                await ctx.send(f"👤 **User {user_id}:** {strikes} strikes (individual query)")
            except Exception as e:
                await ctx.send(f"❌ **User {user_id}:** Error - {str(e)}")

        # Calculate total from individual queries
        total_from_individual = sum(individual_results.values())
        await ctx.send(f"🧮 **Total from individual queries:** {total_from_individual}")

        # Compare with get_all_strikes()
        bulk_results = db.get_all_strikes()
        total_from_bulk = sum(bulk_results.values())
        await ctx.send(f"📊 **Total from get_all_strikes():** {total_from_bulk}")
        await ctx.send(f"📋 **Bulk query results:** {bulk_results}")

        # Show the difference
        if total_from_individual != total_from_bulk:
            await ctx.send(f"⚠️ **MISMATCH DETECTED!** Individual queries work, bulk query fails.")
            await ctx.send(f"✅ **Individual method:** {individual_results}")
            await ctx.send(f"❌ **Bulk method:** {bulk_results}")
        else:
            await ctx.send(f"✅ **Both methods match!** The issue is elsewhere.")

    except Exception as e:
        await ctx.send(f"❌ **Test error:** {str(e)}")


@bot.command(name="addteststrikes")
@commands.has_permissions(manage_messages=True)
async def add_test_strikes(ctx):
    """Manually add the known strike data to test database connection"""
    try:
        await ctx.send("🔄 **Adding test strike data...**")

        # Add the two users with strikes that we know should exist
        user_strikes = {710570041220923402: 1, 906475895907291156: 1}

        success_count = 0
        for user_id, strike_count in user_strikes.items():
            try:
                db.set_user_strikes(user_id, strike_count)
                success_count += 1
                await ctx.send(f"✅ **Added {strike_count} strike(s) for user {user_id}**")
            except Exception as e:
                await ctx.send(f"❌ **Failed to add strikes for user {user_id}:** {str(e)}")

        await ctx.send(f"📊 **Summary:** Successfully added strikes for {success_count} users")

        # Now test if we can read them back
        await ctx.send("🔍 **Testing read-back...**")
        for user_id in user_strikes.keys():
            try:
                strikes = db.get_user_strikes(user_id)
                await ctx.send(f"📖 **User {user_id} now has:** {strikes} strikes")
            except Exception as e:
                await ctx.send(f"❌ **Failed to read strikes for user {user_id}:** {str(e)}")

        # Test bulk query
        bulk_results = db.get_all_strikes()
        total_strikes = sum(bulk_results.values())
        await ctx.send(f"📊 **Bulk query now returns:** {bulk_results}")
        await ctx.send(f"🧮 **Total strikes:** {total_strikes}")

    except Exception as e:
        await ctx.send(f"❌ **Test error:** {str(e)}")


@bot.command(name="dbstats")
@commands.has_permissions(manage_messages=True)
async def db_stats(ctx):
    """Show database statistics"""
    try:
        games = db.get_all_games()
        strikes = db.get_all_strikes()

        total_games = len(games)
        total_users_with_strikes = len([s for s in strikes.values() if s > 0])
        total_strikes = sum(strikes.values())

        # Count unique contributors
        contributors = set()
        for game in games:
            if game.get("added_by"):
                contributors.add(game["added_by"])

        stats_msg = (
            f"📊 **Database Statistics:**\n"
            f"• **Games**: {total_games} recommendations\n"
            f"• **Contributors**: {len(contributors)} unique users\n"
            f"• **Strikes**: {total_strikes} total across {total_users_with_strikes} users\n"
        )

        if contributors:
            top_contributors = {}
            for game in games:
                contributor = game.get("added_by", "")
                if contributor:
                    top_contributors[contributor] = top_contributors.get(contributor, 0) + 1

            # Sort by contribution count
            sorted_contributors = sorted(top_contributors.items(), key=lambda x: x[1], reverse=True)

            stats_msg += f"\n**Top Contributors:**\n"
            for i, (contributor, count) in enumerate(sorted_contributors[:5]):
                stats_msg += f"{i+1}. {contributor}: {count} games\n"

        await ctx.send(stats_msg)

    except Exception as e:
        await ctx.send(f"❌ Error retrieving database statistics: {str(e)}")


@bot.command(name="bulkimportgames")
@commands.has_permissions(manage_messages=True)
async def bulk_import_games(ctx):
    """Import games from the migration script's sample data"""
    try:
        from data_migration import SAMPLE_GAMES_TEXT, parse_games_list

        await ctx.send("🔄 Starting bulk game import from migration script...")

        # Parse the games from the sample text
        games_data = parse_games_list(SAMPLE_GAMES_TEXT)

        if not games_data:
            await ctx.send(
                "❌ No games found in migration script. Please check the SAMPLE_GAMES_TEXT in data_migration.py"
            )
            return

        # Show preview
        preview_msg = f"📋 **Import Preview** ({len(games_data)} games):\n"
        for i, game in enumerate(games_data[:5]):
            contributor = f" by {game['added_by']}" if game["added_by"] else ""
            preview_msg += f"• {game['name']}{contributor}\n"
        if len(games_data) > 5:
            preview_msg += f"... and {len(games_data) - 5} more games\n"

        preview_msg += f"\n⚠️ **WARNING**: This will add {len(games_data)} games to the database. Type `CONFIRM IMPORT` to proceed or anything else to cancel."

        await ctx.send(preview_msg)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)
            if msg.content == "CONFIRM IMPORT":
                imported_count = db.bulk_import_games(games_data)
                await ctx.send(f"✅ Successfully imported {imported_count} game recommendations from migration script!")

                # Update the recommendations list if in the right channel
                RECOMMEND_CHANNEL_ID = 1271568447108550687
                recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
                if recommend_channel:
                    await post_or_update_recommend_list(ctx, recommend_channel)
            else:
                await ctx.send("❌ Import cancelled. No games were added.")
        except:
            await ctx.send("❌ Import timed out. No games were added.")

    except ImportError as e:
        await ctx.send(f"❌ Error importing migration script: {str(e)}")
    except Exception as e:
        await ctx.send(f"❌ Error during bulk import: {str(e)}")


@bot.command(name="cleanplayedgames")
@commands.has_permissions(manage_messages=True)
async def clean_played_games(ctx, youtube_channel_id: Optional[str] = None, twitch_username: Optional[str] = None):
    """Remove games from recommendations that have already been played on YouTube or Twitch"""

    # Hardcoded values for Captain Jonesy's channels
    if not youtube_channel_id:
        youtube_channel_id = "UCPoUxLHeTnE9SUDAkqfJzDQ"  # Captain Jonesy's YouTube channel
    if not twitch_username:
        twitch_username = "jonesyspacecat"  # Captain Jonesy's Twitch username

    await ctx.send("🔍 Starting analysis of played games across platforms...")

    try:
        # Get current game recommendations
        games = db.get_all_games()
        if not games:
            await ctx.send("❌ No games in recommendation database to analyze.")
            return

        await ctx.send(f"📋 Analyzing {len(games)} game recommendations against play history...")

        # Fetch YouTube play history
        youtube_games = []
        try:
            youtube_games = await fetch_youtube_games(youtube_channel_id)
            await ctx.send(f"📺 Found {len(youtube_games)} games from YouTube history")
        except Exception as e:
            await ctx.send(f"⚠️ YouTube API error: {str(e)}")

        # Fetch Twitch play history
        twitch_games = []
        try:
            twitch_games = await fetch_twitch_games(twitch_username)
            await ctx.send(f"🎮 Found {len(twitch_games)} games from Twitch history")
        except Exception as e:
            await ctx.send(f"⚠️ Twitch API error: {str(e)}")

        # Combine all played games
        all_played_games = set(youtube_games + twitch_games)

        if not all_played_games:
            await ctx.send("❌ No played games found. Check API credentials and channel/username.")
            return

        # Find matches using multiple approaches
        games_to_remove = []

        # First, get all video titles for direct searching
        all_video_titles = []
        if AIOHTTP_AVAILABLE and aiohttp is not None:
            try:
                # Re-fetch video titles for direct searching
                async with aiohttp.ClientSession() as session:
                    # YouTube titles
                    if youtube_api_key := os.getenv("YOUTUBE_API_KEY"):
                        try:
                            url = f"https://www.googleapis.com/youtube/v3/channels"
                            params = {"part": "contentDetails", "id": youtube_channel_id, "key": youtube_api_key}
                            async with session.get(url, params=params) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    if data.get("items"):
                                        uploads_playlist_id = data["items"][0]["contentDetails"]["relatedPlaylists"][
                                            "uploads"
                                        ]

                                        # Get video titles
                                        url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                                        params = {
                                            "part": "snippet",
                                            "playlistId": uploads_playlist_id,
                                            "maxResults": 50,
                                            "key": youtube_api_key,
                                        }
                                        async with session.get(url, params=params) as response:
                                            if response.status == 200:
                                                data = await response.json()
                                                for item in data.get("items", []):
                                                    all_video_titles.append(item["snippet"]["title"])
                        except Exception as e:
                            print(f"Error fetching YouTube titles: {e}")
            except Exception as e:
                print(f"Error in title fetching: {e}")
        else:
            await ctx.send("⚠️ aiohttp module not available - cannot fetch video titles for direct matching")

        for game in games:
            game_name_lower = game["name"].lower().strip()
            found_match = False

            # Method 1: Check extracted game names
            for played_game in all_played_games:
                played_game_lower = played_game.lower().strip()

                # Exact match
                if game_name_lower == played_game_lower:
                    games_to_remove.append((game, played_game, "exact"))
                    found_match = True
                    break

                # Fuzzy match (75% similarity for played games)
                similarity = difflib.SequenceMatcher(None, game_name_lower, played_game_lower).ratio()
                if similarity >= 0.75:
                    games_to_remove.append((game, played_game, f"fuzzy ({similarity:.0%})"))
                    found_match = True
                    break

            # Method 2: Check if game name appears anywhere in video titles
            if not found_match:
                for video_title in all_video_titles:
                    video_title_lower = video_title.lower()

                    # Check if the game name appears in the title
                    if game_name_lower in video_title_lower:
                        # Additional check to avoid false positives with very short names
                        if len(game_name_lower) >= 4 or game_name_lower == video_title_lower:
                            games_to_remove.append((game, video_title, "title_contains"))
                            found_match = True
                            break

                    # Also try fuzzy matching against the full title
                    similarity = difflib.SequenceMatcher(None, game_name_lower, video_title_lower).ratio()
                    if similarity >= 0.6:  # Lower threshold for title matching
                        games_to_remove.append((game, video_title, f"title_fuzzy ({similarity:.0%})"))
                        found_match = True
                        break

        if not games_to_remove:
            await ctx.send("✅ No matching games found. All recommendations appear to be unplayed!")
            return

        # Show preview of games to be removed
        preview_msg = f"🎯 **Found {len(games_to_remove)} games to remove:**\n"
        for i, (game, matched_title, match_type) in enumerate(games_to_remove[:10]):
            contributor = f" (by {game['added_by']})" if game["added_by"] else ""
            preview_msg += f"• **{game['name']}**{contributor} → matched '{matched_title}' ({match_type})\n"

        if len(games_to_remove) > 10:
            preview_msg += f"... and {len(games_to_remove) - 10} more games\n"

        preview_msg += f"\n⚠️ **WARNING**: This will remove {len(games_to_remove)} games from recommendations. Type `CONFIRM CLEANUP` to proceed or anything else to cancel."

        await ctx.send(preview_msg)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60.0)
            if msg.content == "CONFIRM CLEANUP":
                removed_count = 0
                for game, matched_title, match_type in games_to_remove:
                    if db.remove_game_by_id(game["id"]):
                        removed_count += 1

                await ctx.send(f"✅ Successfully removed {removed_count} already-played games from recommendations!")

                # Update the recommendations list
                RECOMMEND_CHANNEL_ID = 1271568447108550687
                recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
                if recommend_channel:
                    await post_or_update_recommend_list(ctx, recommend_channel)

                # Show final stats
                remaining_games = db.get_all_games()
                await ctx.send(f"📊 **Cleanup Complete**: {len(remaining_games)} games remain in recommendations")
            else:
                await ctx.send("❌ Cleanup cancelled. No games were removed.")
        except asyncio.TimeoutError:
            await ctx.send("❌ Cleanup timed out. No games were removed.")
        except Exception as e:
            await ctx.send(f"❌ Error during cleanup confirmation: {str(e)}")

    except Exception as e:
        await ctx.send(f"❌ Error during cleanup: {str(e)}")


async def fetch_youtube_games(channel_id: str) -> List[str]:
    """Fetch game titles from YouTube channel using YouTube Data API"""
    # This requires YouTube Data API v3 key
    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    if not youtube_api_key:
        raise Exception("YOUTUBE_API_KEY not configured")

    import aiohttp

    games = []

    try:
        async with aiohttp.ClientSession() as session:
            # Get channel uploads playlist
            url = f"https://www.googleapis.com/youtube/v3/channels"
            params = {"part": "contentDetails", "id": channel_id, "key": youtube_api_key}

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise Exception(f"YouTube API error: {response.status}")

                data = await response.json()
                if not data.get("items"):
                    raise Exception("Channel not found")

                uploads_playlist_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

            # Get videos from uploads playlist (last 200 videos)
            next_page_token = None
            video_count = 0
            max_videos = 200

            while video_count < max_videos:
                url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                params = {
                    "part": "snippet",
                    "playlistId": uploads_playlist_id,
                    "maxResults": min(50, max_videos - video_count),
                    "key": youtube_api_key,
                }

                if next_page_token:
                    params["pageToken"] = next_page_token

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        break

                    data = await response.json()

                    for item in data.get("items", []):
                        title = item["snippet"]["title"]
                        # Extract game name from video title (basic parsing)
                        game_name = extract_game_from_title(title)
                        if game_name:
                            games.append(game_name)

                    video_count += len(data.get("items", []))
                    next_page_token = data.get("nextPageToken")

                    if not next_page_token:
                        break

                    # Rate limiting
                    await asyncio.sleep(0.1)

    except Exception as e:
        raise Exception(f"YouTube fetch error: {str(e)}")

    return list(set(games))  # Remove duplicates


async def fetch_twitch_games(username: str) -> List[str]:
    """Fetch game titles from Twitch channel using Twitch API"""
    # This requires Twitch Client ID and Client Secret
    twitch_client_id = os.getenv("TWITCH_CLIENT_ID")
    twitch_client_secret = os.getenv("TWITCH_CLIENT_SECRET")

    if not twitch_client_id or not twitch_client_secret:
        raise Exception("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET not configured")

    import aiohttp

    games = []

    try:
        async with aiohttp.ClientSession() as session:
            # Get OAuth token
            token_url = "https://id.twitch.tv/oauth2/token"
            token_data = {
                "client_id": twitch_client_id,
                "client_secret": twitch_client_secret,
                "grant_type": "client_credentials",
            }

            async with session.post(token_url, data=token_data) as response:
                if response.status != 200:
                    raise Exception(f"Twitch OAuth error: {response.status}")

                token_response = await response.json()
                access_token = token_response["access_token"]

            headers = {"Client-ID": twitch_client_id, "Authorization": f"Bearer {access_token}"}

            # Get user ID
            user_url = f"https://api.twitch.tv/helix/users?login={username}"
            async with session.get(user_url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Twitch user lookup error: {response.status}")

                user_data = await response.json()
                if not user_data.get("data"):
                    raise Exception("Twitch user not found")

                user_id = user_data["data"][0]["id"]

            # Get recent videos (last 100)
            videos_url = f"https://api.twitch.tv/helix/videos"
            params = {"user_id": user_id, "first": 100, "type": "all"}

            async with session.get(videos_url, headers=headers, params=params) as response:
                if response.status != 200:
                    raise Exception(f"Twitch videos error: {response.status}")

                videos_data = await response.json()

                for video in videos_data.get("data", []):
                    title = video["title"]
                    # Extract game name from video title
                    game_name = extract_game_from_title(title)
                    if game_name:
                        games.append(game_name)

    except Exception as e:
        raise Exception(f"Twitch fetch error: {str(e)}")

    return list(set(games))  # Remove duplicates


def extract_game_from_title(title: str) -> str:
    """Extract game name from video title using common patterns"""
    title = title.strip()

    # Handle "First Time Playing" pattern specifically
    # Example: "Rat Fans - First Time Playing: A Plague Tale: Innocence"
    first_time_pattern = r"^.*?-\s*first\s+time\s+playing:\s*(.+?)(?:\s*-.*)?$"
    first_time_match = re.match(first_time_pattern, title, re.IGNORECASE)
    if first_time_match:
        game_name = first_time_match.group(1).strip()
        # Clean up any trailing separators or episode indicators
        game_name = re.sub(r"\s*[-|#]\s*.*$", "", game_name)
        if len(game_name) > 3:
            return game_name

    # Common patterns for game titles in videos (order matters - most specific first)
    patterns = [
        r"^([^|]+?)\s*\|\s*",  # "Game Name | Episode"
        r"^([^-]+?)\s*-\s*(?:part|ep|episode|#|\d)",  # "Game Name - Part 1" or "Game Name - Episode"
        r"^([^:]+?):\s*(?:part|ep|episode|#|\d)",  # "Game Name: Part 1"
        r"^([^#]+?)#\d",  # "Game Name #1"
        r"^([^(]+?)\s*\(",  # "Game Name (Part 1)"
        r"^([^[]+?)\s*\[",  # "Game Name [Episode]"
        r"^([^-]+?)\s*-\s*(.+)",  # "Game Name - Anything else"
        r"^([^:]+?):\s*(.+)",  # "Game Name: Anything else"
    ]

    for pattern in patterns:
        match = re.match(pattern, title, re.IGNORECASE)
        if match:
            game_name = match.group(1).strip()

            # Clean up common prefixes/suffixes
            game_name = re.sub(
                r"\s*(let\'s play|gameplay|walkthrough|playthrough|first time playing)\s*",
                "",
                game_name,
                flags=re.IGNORECASE,
            )
            game_name = game_name.strip()

            # Filter out common non-game words and ensure minimum length
            if (
                len(game_name) > 3
                and not any(
                    word in game_name.lower()
                    for word in ["stream", "live", "chat", "vod", "highlight", "reaction", "review", "rat fans"]
                )
                and not re.match(r"^\d+$", game_name)
            ):  # Not just numbers
                return game_name

    # If no pattern matches, try to extract first meaningful words
    # Remove common video prefixes first
    clean_title = re.sub(
        r"^(let\'s play|gameplay|walkthrough|playthrough|first time playing)\s+", "", title, flags=re.IGNORECASE
    )
    # Also remove channel names or common prefixes
    clean_title = re.sub(r"^(rat fans|jonesyspacecat)\s*[-:]?\s*", "", clean_title, flags=re.IGNORECASE)
    words = clean_title.split()

    if len(words) >= 2:
        # Try different word combinations
        for word_count in [4, 3, 2]:  # Try 4 words, then 3, then 2
            if len(words) >= word_count:
                potential_game = " ".join(words[:word_count])
                if len(potential_game) > 3 and not any(
                    word in potential_game.lower()
                    for word in ["stream", "live", "chat", "vod", "highlight", "first time"]
                ):
                    return potential_game

    return ""


async def fetch_comprehensive_youtube_games(channel_id: str) -> List[Dict[str, Any]]:
    """Fetch comprehensive game data from YouTube channel using playlists as primary source"""
    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    if not youtube_api_key:
        raise Exception("YOUTUBE_API_KEY not configured")

    if not AIOHTTP_AVAILABLE or aiohttp is None:
        raise Exception("aiohttp module not available")

    games_data = []

    try:
        async with aiohttp.ClientSession() as session:
            # STEP 1: Get all playlists from the channel (primary source)
            url = f"https://www.googleapis.com/youtube/v3/playlists"
            params = {
                "part": "snippet,contentDetails",
                "channelId": channel_id,
                "maxResults": 50,
                "key": youtube_api_key,
            }

            all_playlists = []
            next_page_token = None

            while True:
                if next_page_token:
                    params["pageToken"] = next_page_token

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        break

                    data = await response.json()
                    playlists = data.get("items", [])

                    if not playlists:
                        break

                    all_playlists.extend(playlists)
                    next_page_token = data.get("nextPageToken")

                    if not next_page_token:
                        break

                    await asyncio.sleep(0.1)  # Rate limiting

            # Process playlists to extract game data with accurate playtime
            for playlist in all_playlists:
                playlist_title = playlist["snippet"]["title"]
                playlist_id = playlist["id"]
                video_count = playlist["contentDetails"]["itemCount"]

                # Skip non-game playlists (common playlist names to ignore)
                skip_keywords = [
                    "shorts",
                    "stream",
                    "live",
                    "compilation",
                    "highlight",
                    "reaction",
                    "music",
                    "song",
                    "trailer",
                    "announcement",
                    "update",
                    "news",
                    "vlog",
                    "irl",
                    "chat",
                    "q&a",
                    "qa",
                    "discussion",
                    "review",
                ]

                if any(keyword in playlist_title.lower() for keyword in skip_keywords):
                    continue

                # Extract game name from playlist title
                game_name = extract_game_from_playlist_title(playlist_title)

                if game_name and video_count > 0:
                    # Determine completion status from playlist title
                    completion_status = "completed" if "[completed]" in playlist_title.lower() else "unknown"
                    if video_count == 1:
                        completion_status = "unknown"  # Single video might be a one-off
                    elif video_count > 1 and completion_status == "unknown":
                        completion_status = "ongoing"  # Multiple videos, no completion marker

                    # Get accurate playtime by fetching video durations
                    total_playtime_minutes = 0
                    first_video_date = None
                    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"

                    try:
                        # Get all videos from playlist with their durations
                        playlist_items_url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                        playlist_params = {
                            "part": "snippet",
                            "playlistId": playlist_id,
                            "maxResults": 50,
                            "key": youtube_api_key,
                        }

                        video_ids = []
                        async with session.get(playlist_items_url, params=playlist_params) as response:
                            if response.status == 200:
                                playlist_data = await response.json()
                                items = playlist_data.get("items", [])
                                if items:
                                    first_video_date = items[0]["snippet"]["publishedAt"][:10]
                                    video_ids = [item["snippet"]["resourceId"]["videoId"] for item in items]

                        # Get video durations
                        if video_ids:
                            videos_url = f"https://www.googleapis.com/youtube/v3/videos"
                            videos_params = {
                                "part": "contentDetails",
                                "id": ",".join(video_ids[:50]),  # API limit
                                "key": youtube_api_key,
                            }

                            async with session.get(videos_url, params=videos_params) as response:
                                if response.status == 200:
                                    videos_data = await response.json()
                                    for video in videos_data.get("items", []):
                                        duration = video["contentDetails"]["duration"]
                                        duration_minutes = parse_youtube_duration(duration) // 60
                                        total_playtime_minutes += duration_minutes
                    except Exception as e:
                        # Fallback to estimate if API calls fail
                        total_playtime_minutes = video_count * 30
                        print(f"Failed to get accurate playtime for {game_name}: {e}")

                    game_data = {
                        "canonical_name": game_name,
                        "alternative_names": [],
                        "series_name": game_name,  # Will be enhanced by AI
                        "release_year": None,  # Will be enhanced by AI
                        "platform": None,  # Will be enhanced by AI
                        "first_played_date": first_video_date,
                        "completion_status": completion_status,
                        "total_episodes": video_count,
                        "total_playtime_minutes": total_playtime_minutes,
                        "youtube_playlist_url": playlist_url,
                        "twitch_vod_urls": [],
                        "notes": f"Auto-imported from YouTube playlist '{playlist_title}'. {video_count} episodes, {total_playtime_minutes//60}h {total_playtime_minutes%60}m total.",
                        "genre": None,  # Will be enhanced by AI
                    }

                    games_data.append(game_data)

            # STEP 2: If no playlists found or very few games, fall back to video parsing
            if len(games_data) < 10:  # Threshold for fallback
                # Fallback to parsing individual videos from uploads playlist
                try:
                    # Get channel uploads playlist
                    url = f"https://www.googleapis.com/youtube/v3/channels"
                    params = {"part": "contentDetails", "id": channel_id, "key": youtube_api_key}

                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("items"):
                                uploads_playlist_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

                                # Get videos from uploads playlist
                                fallback_games = await parse_videos_for_games(
                                    session, uploads_playlist_id, youtube_api_key
                                )
                                games_data.extend(fallback_games)
                except Exception as e:
                    print(f"Fallback video parsing failed: {e}")

    except Exception as e:
        raise Exception(f"YouTube comprehensive fetch error: {str(e)}")

    return games_data


def extract_game_from_playlist_title(playlist_title: str) -> str:
    """Extract game name from YouTube playlist title"""
    title = playlist_title.strip()

    # Remove common playlist indicators
    title = re.sub(r"\s*\[completed\]", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\(completed\)", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*-\s*completed", "", title, flags=re.IGNORECASE)

    # Remove common prefixes
    title = re.sub(r"^(let\'s play|gameplay|walkthrough|playthrough)\s+", "", title, flags=re.IGNORECASE)

    # Clean up the title
    title = title.strip()

    # Filter out obvious non-game playlists
    non_game_indicators = [
        "stream",
        "live",
        "compilation",
        "highlight",
        "reaction",
        "music",
        "song",
        "trailer",
        "announcement",
        "update",
        "news",
        "vlog",
        "irl",
        "chat",
        "q&a",
        "qa",
        "discussion",
        "review",
    ]

    title_lower = title.lower()
    if any(indicator in title_lower for indicator in non_game_indicators):
        return ""

    # Return the cleaned title if it looks like a game name
    if len(title) > 2 and not re.match(r"^\d+$", title):
        return title

    return ""


async def parse_videos_for_games(session, uploads_playlist_id: str, youtube_api_key: str) -> List[Dict[str, Any]]:
    """Parse individual videos to extract game data (fallback method)"""
    games_data = []
    game_series = {}

    try:
        # Get videos from uploads playlist (last 200 videos)
        next_page_token = None
        video_count = 0
        max_videos = 200

        while video_count < max_videos:
            url = f"https://www.googleapis.com/youtube/v3/playlistItems"
            params = {
                "part": "snippet",
                "playlistId": uploads_playlist_id,
                "maxResults": min(50, max_videos - video_count),
                "key": youtube_api_key,
            }

            if next_page_token:
                params["pageToken"] = next_page_token

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    break

                data = await response.json()

                for item in data.get("items", []):
                    title = item["snippet"]["title"]
                    published_at = item["snippet"]["publishedAt"][:10]

                    # Extract game name from video title
                    game_name = extract_game_from_title(title)
                    if game_name:
                        # Normalize game name for grouping
                        normalized_name = game_name.strip().title()

                        if normalized_name not in game_series:
                            game_series[normalized_name] = {
                                "episodes": [],
                                "first_played_date": published_at,
                                "total_episodes": 0,
                            }

                        game_series[normalized_name]["episodes"].append({"title": title, "published_at": published_at})
                        game_series[normalized_name]["total_episodes"] += 1

                        # Update first played date if this video is earlier
                        if published_at < game_series[normalized_name]["first_played_date"]:
                            game_series[normalized_name]["first_played_date"] = published_at

                video_count += len(data.get("items", []))
                next_page_token = data.get("nextPageToken")

                if not next_page_token:
                    break

                # Rate limiting
                await asyncio.sleep(0.1)

        # Convert grouped games to game data format
        for game_name, series_info in game_series.items():
            if series_info["total_episodes"] >= 2:  # Only include games with multiple episodes
                completion_status = "ongoing" if series_info["total_episodes"] > 1 else "unknown"
                estimated_playtime = series_info["total_episodes"] * 30

                game_data = {
                    "canonical_name": game_name,
                    "alternative_names": [],
                    "series_name": game_name,
                    "release_year": None,
                    "platform": None,
                    "first_played_date": series_info["first_played_date"],
                    "completion_status": completion_status,
                    "total_episodes": series_info["total_episodes"],
                    "total_playtime_minutes": estimated_playtime,
                    "youtube_playlist_url": None,
                    "twitch_vod_urls": [],
                    "notes": f"Auto-imported from YouTube videos. {series_info['total_episodes']} episodes found.",
                    "genre": None,
                }

                games_data.append(game_data)

    except Exception as e:
        print(f"Video parsing error: {e}")

    return games_data


async def fetch_comprehensive_twitch_games(username: str) -> List[Dict[str, Any]]:
    """Fetch comprehensive game data from Twitch channel with full metadata"""
    twitch_client_id = os.getenv("TWITCH_CLIENT_ID")
    twitch_client_secret = os.getenv("TWITCH_CLIENT_SECRET")

    if not twitch_client_id or not twitch_client_secret:
        raise Exception("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET not configured")

    if not AIOHTTP_AVAILABLE or aiohttp is None:
        raise Exception("aiohttp module not available")

    games_data = []

    try:
        async with aiohttp.ClientSession() as session:
            # Get OAuth token
            token_url = "https://id.twitch.tv/oauth2/token"
            token_data = {
                "client_id": twitch_client_id,
                "client_secret": twitch_client_secret,
                "grant_type": "client_credentials",
            }

            async with session.post(token_url, data=token_data) as response:
                if response.status != 200:
                    raise Exception(f"Twitch OAuth error: {response.status}")

                token_response = await response.json()
                access_token = token_response["access_token"]

            headers = {"Client-ID": twitch_client_id, "Authorization": f"Bearer {access_token}"}

            # Get user ID
            user_url = f"https://api.twitch.tv/helix/users?login={username}"
            async with session.get(user_url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Twitch user lookup error: {response.status}")

                user_data = await response.json()
                if not user_data.get("data"):
                    raise Exception("Twitch user not found")

                user_id = user_data["data"][0]["id"]

            # Get all videos (multiple pages)
            all_videos = []
            cursor = None

            while len(all_videos) < 500:  # Limit to prevent excessive API calls
                videos_url = f"https://api.twitch.tv/helix/videos"
                params = {"user_id": user_id, "first": 100, "type": "all"}

                if cursor:
                    params["after"] = cursor

                async with session.get(videos_url, headers=headers, params=params) as response:
                    if response.status != 200:
                        break

                    videos_data = await response.json()
                    videos = videos_data.get("data", [])

                    if not videos:
                        break

                    all_videos.extend(videos)

                    # Get cursor for next page
                    pagination = videos_data.get("pagination", {})
                    cursor = pagination.get("cursor")

                    if not cursor:
                        break

                    await asyncio.sleep(0.1)  # Rate limiting

            # Group videos by game series
            game_series = {}
            for video in all_videos:
                title = video["title"]
                game_name = extract_game_from_title(title)

                if game_name:
                    # Normalize game name for grouping
                    normalized_name = game_name.strip().title()

                    if normalized_name not in game_series:
                        game_series[normalized_name] = {
                            "videos": [],
                            "first_played_date": None,
                            "total_episodes": 0,
                            "total_duration_seconds": 0,
                            "vod_urls": [],
                        }

                    # Parse duration (format: "1h23m45s" or "23m45s" or "45s")
                    duration_str = video.get("duration", "0s")
                    duration_seconds = parse_twitch_duration(duration_str)

                    game_series[normalized_name]["videos"].append(
                        {
                            "title": title,
                            "created_at": video["created_at"],
                            "url": video["url"],
                            "duration_seconds": duration_seconds,
                        }
                    )

                    game_series[normalized_name]["vod_urls"].append(video["url"])
                    game_series[normalized_name]["total_duration_seconds"] += duration_seconds

            # Create comprehensive game data
            for game_name, series_info in game_series.items():
                # Sort videos by date and get metadata
                series_info["videos"].sort(key=lambda x: x["created_at"])
                series_info["first_played_date"] = (
                    series_info["videos"][0]["created_at"][:10] if series_info["videos"] else None
                )
                series_info["total_episodes"] = len(series_info["videos"])

                game_data = {
                    "canonical_name": game_name,
                    "alternative_names": [],
                    "series_name": game_name,  # Will be enhanced by AI
                    "release_year": None,  # Will be enhanced by AI
                    "platform": None,  # Will be enhanced by AI
                    "first_played_date": series_info["first_played_date"],
                    "completion_status": ("completed" if series_info["total_episodes"] > 1 else "unknown"),
                    "total_episodes": series_info["total_episodes"],
                    "total_playtime_minutes": series_info["total_duration_seconds"] // 60,
                    "youtube_playlist_url": None,
                    "twitch_vod_urls": series_info["vod_urls"][:10],  # Limit to first 10 VODs
                    "notes": f"Auto-imported from Twitch. {series_info['total_episodes']} VODs found.",
                    "genre": None,  # Will be enhanced by AI
                }

                games_data.append(game_data)

    except Exception as e:
        raise Exception(f"Twitch comprehensive fetch error: {str(e)}")

    return games_data


async def enhance_games_with_ai(games_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Use AI to enhance game metadata with genre, series info, alternative names, and release years"""
    if not ai_enabled:
        print("AI not enabled, returning games without enhancement")
        return games_data

    enhanced_games = []

    # Process games in batches to avoid token limits
    batch_size = 3  # Smaller batch size for better success rate
    for i in range(0, len(games_data), batch_size):
        batch = games_data[i : i + batch_size]
        game_names = [game["canonical_name"] for game in batch]

        # Simplified, more direct prompt
        prompt = f"""Analyze these video games and provide metadata in JSON format:

{', '.join(game_names)}

For each game, provide:
- genre: Main genre (Action, RPG, Adventure, etc.)
- series_name: Franchise name (e.g., "Batman" for "Batman: Arkham Origins")
- release_year: Original release year
- alternative_names: Common abbreviations/alternate names

Example for "Batman: Arkham Origins":
{{
  "Batman: Arkham Origins": {{
    "genre": "Action-Adventure",
    "series_name": "Batman: Arkham",
    "release_year": 2013,
    "alternative_names": ["Arkham Origins", "Batman AO"]
  }}
}}

Respond with valid JSON only. Include all games listed above."""

        try:
            response = None
            response_text = ""

            # Try primary AI first
            if primary_ai == "gemini" and gemini_model is not None:
                try:
                    print(f"Trying Gemini AI for games: {game_names}")
                    response = gemini_model.generate_content(prompt)  # type: ignore
                    if response and hasattr(response, "text") and response.text:
                        response_text = response.text.strip()
                        print(f"Gemini response received: {len(response_text)} characters")
                except Exception as e:
                    print(f"Gemini AI enhancement error: {e}")
                    # Try Claude backup if available
                    if backup_ai == "claude" and claude_client is not None:
                        try:
                            print(f"Trying Claude backup for games: {game_names}")
                            response = claude_client.messages.create(  # type: ignore
                                model="claude-3-haiku-20240307",
                                max_tokens=1500,
                                messages=[{"role": "user", "content": prompt}],
                            )
                            if response and hasattr(response, "content") and response.content:
                                content_list = response.content  # type: ignore
                                if content_list and len(content_list) > 0:
                                    first_content = content_list[0]  # type: ignore
                                    if hasattr(first_content, "text"):
                                        response_text = first_content.text.strip()  # type: ignore
                                        print(f"Claude response received: {len(response_text)} characters")
                        except Exception as claude_e:
                            print(f"Claude backup AI enhancement error: {claude_e}")

            elif primary_ai == "claude" and claude_client is not None:
                try:
                    print(f"Trying Claude AI for games: {game_names}")
                    response = claude_client.messages.create(  # type: ignore
                        model="claude-3-haiku-20240307", max_tokens=1500, messages=[{"role": "user", "content": prompt}]
                    )
                    if response and hasattr(response, "content") and response.content:
                        content_list = response.content  # type: ignore
                        if content_list and len(content_list) > 0:
                            first_content = content_list[0]  # type: ignore
                            if hasattr(first_content, "text"):
                                response_text = first_content.text.strip()  # type: ignore
                                print(f"Claude response received: {len(response_text)} characters")
                except Exception as e:
                    print(f"Claude AI enhancement error: {e}")
                    # Try Gemini backup if available
                    if backup_ai == "gemini" and gemini_model is not None:
                        try:
                            print(f"Trying Gemini backup for games: {game_names}")
                            response = gemini_model.generate_content(prompt)  # type: ignore
                            if response and hasattr(response, "text") and response.text:
                                response_text = response.text.strip()
                                print(f"Gemini response received: {len(response_text)} characters")
                        except Exception as gemini_e:
                            print(f"Gemini backup AI enhancement error: {gemini_e}")

            if response_text:
                print(f"Raw AI response: {response_text[:200]}...")

                # Clean up response text - remove markdown code blocks if present
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()

                # Parse AI response
                import json

                try:
                    ai_data = json.loads(response_text)
                    print(f"Successfully parsed JSON with {len(ai_data)} games")

                    # Apply AI enhancements to batch
                    for game in batch:
                        game_name = game["canonical_name"]
                        print(f"Processing game: {game_name}")

                        # Try exact match first
                        ai_info = ai_data.get(game_name)

                        # If no exact match, try case-insensitive match
                        if not ai_info:
                            for ai_game_name, ai_game_data in ai_data.items():
                                if ai_game_name.lower() == game_name.lower():
                                    ai_info = ai_game_data
                                    break

                        if ai_info:
                            print(f"Found AI data for {game_name}: {ai_info}")

                            if ai_info.get("genre"):
                                game["genre"] = ai_info["genre"]
                                print(f"Set genre: {ai_info['genre']}")
                            if ai_info.get("series_name"):
                                game["series_name"] = ai_info["series_name"]
                                print(f"Set series: {ai_info['series_name']}")
                            if ai_info.get("release_year"):
                                game["release_year"] = ai_info["release_year"]
                                print(f"Set year: {ai_info['release_year']}")
                            if ai_info.get("alternative_names") and isinstance(ai_info["alternative_names"], list):
                                # Merge with existing alternative names
                                existing_alt_names = game.get("alternative_names", []) or []
                                new_alt_names = ai_info["alternative_names"]
                                merged_alt_names = list(set(existing_alt_names + new_alt_names))
                                if merged_alt_names:
                                    game["alternative_names"] = merged_alt_names
                                    print(f"Set alt names: {merged_alt_names}")
                        else:
                            print(f"No AI data found for {game_name}")

                        enhanced_games.append(game)

                except json.JSONDecodeError as e:
                    print(f"JSON parsing error in AI enhancement: {e}")
                    print(f"Failed to parse: {response_text}")
                    # Try to extract JSON from response if it's embedded in text
                    import re

                    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
                    if json_match:
                        try:
                            ai_data = json.loads(json_match.group())
                            print(f"Successfully extracted and parsed JSON with {len(ai_data)} games")

                            # Apply enhancements (same logic as above)
                            for game in batch:
                                game_name = game["canonical_name"]
                                ai_info = ai_data.get(game_name)

                                if not ai_info:
                                    for ai_game_name, ai_game_data in ai_data.items():
                                        if ai_game_name.lower() == game_name.lower():
                                            ai_info = ai_game_data
                                            break

                                if ai_info:
                                    if ai_info.get("genre"):
                                        game["genre"] = ai_info["genre"]
                                    if ai_info.get("series_name"):
                                        game["series_name"] = ai_info["series_name"]
                                    if ai_info.get("release_year"):
                                        game["release_year"] = ai_info["release_year"]
                                    if ai_info.get("alternative_names") and isinstance(
                                        ai_info["alternative_names"], list
                                    ):
                                        existing_alt_names = game.get("alternative_names", []) or []
                                        new_alt_names = ai_info["alternative_names"]
                                        merged_alt_names = list(set(existing_alt_names + new_alt_names))
                                        if merged_alt_names:
                                            game["alternative_names"] = merged_alt_names

                                enhanced_games.append(game)
                        except json.JSONDecodeError:
                            print("Failed to extract JSON from response, adding games without enhancement")
                            enhanced_games.extend(batch)
                    else:
                        print("No JSON found in response, adding games without enhancement")
                        enhanced_games.extend(batch)
            else:
                print("No response text received from AI")
                enhanced_games.extend(batch)

        except Exception as e:
            print(f"AI enhancement error for batch {game_names}: {e}")
            import traceback

            traceback.print_exc()
            enhanced_games.extend(batch)

        # Rate limiting for AI calls
        await asyncio.sleep(1)

    print(f"Enhanced {len(enhanced_games)} games total")
    return enhanced_games


def parse_youtube_duration(duration: str) -> int:
    """Parse YouTube ISO 8601 duration format (PT1H23M45S) to seconds"""
    import re

    # Remove PT prefix
    duration = duration.replace("PT", "")

    # Extract hours, minutes, seconds
    hours = 0
    minutes = 0
    seconds = 0

    hour_match = re.search(r"(\d+)H", duration)
    if hour_match:
        hours = int(hour_match.group(1))

    minute_match = re.search(r"(\d+)M", duration)
    if minute_match:
        minutes = int(minute_match.group(1))

    second_match = re.search(r"(\d+)S", duration)
    if second_match:
        seconds = int(second_match.group(1))

    return hours * 3600 + minutes * 60 + seconds


def parse_twitch_duration(duration: str) -> int:
    """Parse Twitch duration format (1h23m45s) to seconds"""
    import re

    total_seconds = 0

    # Extract hours
    hour_match = re.search(r"(\d+)h", duration)
    if hour_match:
        total_seconds += int(hour_match.group(1)) * 3600

    # Extract minutes
    minute_match = re.search(r"(\d+)m", duration)
    if minute_match:
        total_seconds += int(minute_match.group(1)) * 60

    # Extract seconds
    second_match = re.search(r"(\d+)s", duration)
    if second_match:
        total_seconds += int(second_match.group(1))

    return total_seconds


async def refresh_ongoing_games_metadata() -> int:
    """Refresh metadata for ongoing games by fetching updated episode counts and playtime"""
    try:
        # Get all ongoing games from the database
        all_games = db.get_all_played_games()
        ongoing_games = [game for game in all_games if game.get("completion_status") == "ongoing"]

        if not ongoing_games:
            return 0

        updated_count = 0
        youtube_api_key = os.getenv("YOUTUBE_API_KEY")

        if not youtube_api_key or not AIOHTTP_AVAILABLE or aiohttp is None:
            return 0

        async with aiohttp.ClientSession() as session:
            for game in ongoing_games:
                try:
                    playlist_url = game.get("youtube_playlist_url")
                    if not playlist_url:
                        continue

                    # Extract playlist ID from URL
                    playlist_id_match = re.search(r"list=([^&]+)", playlist_url)
                    if not playlist_id_match:
                        continue

                    playlist_id = playlist_id_match.group(1)

                    # Get current video count and playtime
                    playlist_url_api = f"https://www.googleapis.com/youtube/v3/playlists"
                    params = {"part": "contentDetails", "id": playlist_id, "key": youtube_api_key}

                    async with session.get(playlist_url_api, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("items"):
                                current_video_count = data["items"][0]["contentDetails"]["itemCount"]

                                # Only update if video count has changed
                                if current_video_count != game.get("total_episodes", 0):
                                    # Get accurate playtime
                                    total_playtime_minutes = 0

                                    # Get video IDs from playlist
                                    playlist_items_url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                                    playlist_params = {
                                        "part": "snippet",
                                        "playlistId": playlist_id,
                                        "maxResults": 50,
                                        "key": youtube_api_key,
                                    }

                                    video_ids = []
                                    async with session.get(playlist_items_url, params=playlist_params) as response:
                                        if response.status == 200:
                                            playlist_data = await response.json()
                                            items = playlist_data.get("items", [])
                                            video_ids = [item["snippet"]["resourceId"]["videoId"] for item in items]

                                    # Get video durations
                                    if video_ids:
                                        videos_url = f"https://www.googleapis.com/youtube/v3/videos"
                                        videos_params = {
                                            "part": "contentDetails",
                                            "id": ",".join(video_ids[:50]),  # API limit
                                            "key": youtube_api_key,
                                        }

                                        async with session.get(videos_url, params=videos_params) as response:
                                            if response.status == 200:
                                                videos_data = await response.json()
                                                for video in videos_data.get("items", []):
                                                    duration = video["contentDetails"]["duration"]
                                                    duration_minutes = parse_youtube_duration(duration) // 60
                                                    total_playtime_minutes += duration_minutes

                                    # Update the game in database
                                    success = db.update_played_game(
                                        game["id"],
                                        total_episodes=current_video_count,
                                        total_playtime_minutes=total_playtime_minutes,
                                    )

                                    if success:
                                        updated_count += 1
                                        print(
                                            f"Updated {game['canonical_name']}: {game.get('total_episodes', 0)} → {current_video_count} episodes"
                                        )

                    # Rate limiting
                    await asyncio.sleep(0.1)

                except Exception as e:
                    print(f"Error updating {game.get('canonical_name', 'unknown')}: {e}")
                    continue

        return updated_count

    except Exception as e:
        print(f"Error in refresh_ongoing_games_metadata: {e}")
        return 0


# --- Game Commands ---
@bot.command(name="addgame")
async def add_game(ctx, *, entry: str):
    await _add_game(ctx, entry)


@bot.command(name="recommend")
async def recommend(ctx, *, entry: str):
    await _add_game(ctx, entry)


RECOMMEND_LIST_MESSAGE_ID_FILE = "recommend_list_message_id.txt"


async def post_or_update_recommend_list(ctx, channel):
    games = db.get_all_games()

    # Preamble text for the recommendations channel
    preamble = """# Welcome to the Game Recommendations Channel

Since Jonesy gets games suggested to her all the time, in the YT comments, on Twitch, and in the server, we've decided to get a list going.

A few things to mention up top:

Firstly, a game being on this list is NOT any guarantee it will be played. Jonesy gets to decide, not any of us.

Secondly, this list is in no particular order, so no reading into anything.

Finally, think about what sort of games Jonesy actually plays, either for content or in her own time, when making suggestions.

To add a game, first check the list and then use the /recommend command by typing / followed by "recommend" and the name of the game.

If you want to add any other comments, you can discuss the list in 🎮game-chat"""

    # Create embed
    embed = discord.Embed(
        title="📋 Game Recommendations",
        description="Recommendations for mission enrichment. Review and consider.",
        color=0x2F3136,  # Dark gray color matching Ash's aesthetic
    )

    if not games:
        embed.add_field(name="Status", value="No recommendations currently catalogued.", inline=False)
    else:
        # Create one continuous list
        game_lines = []
        for i, game in enumerate(games, 1):
            # Truncate long names/reasons to fit in embed and apply Title Case
            name = game["name"][:40] + "..." if len(game["name"]) > 40 else game["name"]
            name = name.title()  # Convert to Title Case
            reason = game["reason"][:60] + "..." if len(game["reason"]) > 60 else game["reason"]

            # Don't show contributor twice - if reason already contains "Suggested by", don't add "by" again
            if (
                game["added_by"]
                and game["added_by"].strip()
                and not (reason and f"Suggested by {game['added_by']}" in reason)
            ):
                contributor = f" (by {game['added_by']})"
            else:
                contributor = ""

            game_lines.append(f'{i}. **{name}** — "{reason}"{contributor}')

        # Join all games into one field value
        field_value = "\n".join(game_lines)

        # If the list is too long for one field, we'll need to split it
        if len(field_value) > 1024:
            # Split into multiple fields but keep numbering continuous
            current_field = []
            current_length = 0
            field_count = 1

            for line in game_lines:
                if current_length + len(line) + 1 > 1000:  # Leave buffer
                    # Add current field - use empty string for field name to eliminate gaps
                    embed.add_field(name="", value="\n".join(current_field), inline=False)
                    # Start new field
                    current_field = [line]
                    current_length = len(line)
                    field_count += 1
                else:
                    current_field.append(line)
                    current_length += len(line) + 1

            # Add the final field
            if current_field:
                embed.add_field(name="", value="\n".join(current_field), inline=False)
        else:
            # Single field for all games - use empty string for field name
            embed.add_field(name="", value=field_value, inline=False)

    # Add footer with stats
    embed.set_footer(text=f"Total recommendations: {len(games)} | Last updated")
    embed.timestamp = discord.utils.utcnow()

    # Try to update the existing message if possible
    message_id = db.get_config_value("recommend_list_message_id")
    msg = None
    if message_id:
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.edit(content=preamble, embed=embed)
        except Exception:
            msg = None
    if not msg:
        msg = await channel.send(content=preamble, embed=embed)
        db.set_config_value("recommend_list_message_id", str(msg.id))


# Helper for adding games, called by add_game and recommend
async def _add_game(ctx, entry: str):
    added = []
    duplicate = []
    for part in entry.split(","):
        part = part.strip()
        if not part:
            continue
        if " - " in part:
            name, reason = map(str.strip, part.split(" - ", 1))
        else:
            name, reason = part, "(no reason provided)"
        if not name:
            continue
        # Typo-tolerant duplicate check (case-insensitive, fuzzy match)
        if db.game_exists(name):
            duplicate.append(name)
            continue
        # Exclude username if user is Sir Decent Jam (user ID 337833732901961729)
        if str(ctx.author.id) == "337833732901961729":
            added_by = ""
        else:
            added_by = ctx.author.name

        if db.add_game_recommendation(name, reason, added_by):
            added.append(name)

    if added:
        RECOMMEND_CHANNEL_ID = 1271568447108550687
        recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
        confirm_msg = f"🧾 Recommendation(s) logged: {', '.join(added)}. Efficiency noted."
        # Only send the confirmation in the invoking channel if not the recommendations channel
        if ctx.channel.id != RECOMMEND_CHANNEL_ID:
            await ctx.send(confirm_msg)
        # Always update the persistent recommendations list and send confirmation in the recommendations channel
        if recommend_channel:
            await post_or_update_recommend_list(ctx, recommend_channel)
            if ctx.channel.id == RECOMMEND_CHANNEL_ID:
                await ctx.send(confirm_msg)
    if duplicate:
        await ctx.send(
            f"⚠️ Submission rejected: {', '.join(duplicate)} already exist(s) in the database. Redundancy is inefficient. Please submit only unique recommendations."
        )
    if not added and not duplicate:
        await ctx.send("⚠️ Submission invalid. Please provide at least one game name. Efficiency is paramount.")


@bot.command(name="listgames")
async def list_games(ctx):
    games = db.get_all_games()

    # Create embed (same format as the persistent recommendations list)
    embed = discord.Embed(
        title="📋 Game Recommendations",
        description="Current recommendations for mission enrichment. Review and consider.",
        color=0x2F3136,  # Dark gray color matching Ash's aesthetic
    )

    if not games:
        embed.add_field(
            name="Status",
            value="No recommendations currently catalogued. Observation is key to survival.",
            inline=False,
        )
    else:
        # Create one continuous list
        game_lines = []
        for i, game in enumerate(games, 1):
            # Truncate long names/reasons to fit in embed and apply Title Case
            name = game["name"][:40] + "..." if len(game["name"]) > 40 else game["name"]
            name = name.title()  # Convert to Title Case
            reason = game["reason"][:60] + "..." if len(game["reason"]) > 60 else game["reason"]

            # Don't show contributor twice - if reason already contains "Suggested by", don't add "by" again
            if (
                game["added_by"]
                and game["added_by"].strip()
                and not (reason and f"Suggested by {game['added_by']}" in reason)
            ):
                contributor = f" (by {game['added_by']})"
            else:
                contributor = ""

            game_lines.append(f'{i}. **{name}** — "{reason}"{contributor}')

        # Join all games into one field value
        field_value = "\n".join(game_lines)

        # If the list is too long for one field, we'll need to split it
        if len(field_value) > 1024:
            # Split into multiple fields but keep numbering continuous
            current_field = []
            current_length = 0
            field_count = 1

            for line in game_lines:
                if current_length + len(line) + 1 > 1000:  # Leave buffer
                    # Add current field
                    embed.add_field(
                        name="\u200b",  # Zero-width space for invisible field name
                        value="\n".join(current_field),
                        inline=False,
                    )
                    # Start new field
                    current_field = [line]
                    current_length = len(line)
                    field_count += 1
                else:
                    current_field.append(line)
                    current_length += len(line) + 1

            # Add the final field
            if current_field:
                embed.add_field(
                    name="\u200b",  # Zero-width space for invisible field name
                    value="\n".join(current_field),
                    inline=False,
                )
        else:
            # Single field for all games
            embed.add_field(name="Current Recommendations", value=field_value, inline=False)

    # Add footer with stats
    embed.set_footer(text=f"Total recommendations: {len(games)} | Requested by {ctx.author.name}")
    embed.timestamp = discord.utils.utcnow()

    await ctx.send(embed=embed)

    # Also update the persistent recommendations list in the recommendations channel
    RECOMMEND_CHANNEL_ID = 1271568447108550687
    recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
    if recommend_channel and ctx.channel.id != RECOMMEND_CHANNEL_ID:
        # Only update if we're not already in the recommendations channel to avoid redundancy
        await post_or_update_recommend_list(ctx, recommend_channel)


@bot.command(name="removegame")
@commands.has_permissions(manage_messages=True)
async def remove_game(ctx, *, arg: str):
    # Try to interpret as index first
    index = None
    try:
        index = int(arg)
    except ValueError:
        pass

    removed = None
    if index is not None:
        removed = db.remove_game_by_index(index)
    else:
        # Try name match
        removed = db.remove_game_by_name(arg)

    if not removed:
        await ctx.send(
            "⚠️ Removal protocol failed: No matching recommendation found by that index or designation. Precision is essential. Please specify a valid entry for expungement."
        )
        return

    RECOMMEND_CHANNEL_ID = 1271568447108550687
    recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
    # Only send the detailed removal message in the invoking channel if not the recommendations channel
    if ctx.channel.id != RECOMMEND_CHANNEL_ID:
        await ctx.send(f"Recommendation '{removed['name']}' has been expunged from the record. Protocol maintained.")
    # Always update the persistent recommendations list
    if recommend_channel:
        await post_or_update_recommend_list(ctx, recommend_channel)


# --- Played Games Commands ---
@bot.command(name="addplayedgame")
@commands.has_permissions(manage_messages=True)
async def add_played_game_cmd(ctx, *, game_info: str):
    """Add a played game to the database. Format: Game Name | series:Series | year:2023 | platform:PC | status:completed | episodes:12 | notes:Additional info"""
    try:
        # Parse the game info
        parts = [part.strip() for part in game_info.split("|")]
        canonical_name = parts[0]

        # Parse optional parameters
        series_name = None
        release_year = None
        platform = None
        completion_status = "unknown"
        total_episodes = 0
        notes = None
        alternative_names = []

        for part in parts[1:]:
            if ":" in part:
                key, value = part.split(":", 1)
                key = key.strip().lower()
                value = value.strip()

                if key == "series":
                    series_name = value
                elif key == "year":
                    try:
                        release_year = int(value)
                    except ValueError:
                        pass
                elif key == "platform":
                    platform = value
                elif key == "status":
                    completion_status = value
                elif key == "episodes":
                    try:
                        total_episodes = int(value)
                    except ValueError:
                        pass
                elif key == "notes":
                    notes = value
                elif key == "alt" or key == "alternatives":
                    alternative_names = [name.strip() for name in value.split(",")]

        # Add the game
        success = db.add_played_game(
            canonical_name=canonical_name,
            alternative_names=alternative_names,
            series_name=series_name,
            release_year=release_year,
            platform=platform,
            completion_status=completion_status,
            total_episodes=total_episodes,
            notes=notes,
        )

        if success:
            await ctx.send(
                f"✅ **Game catalogued:** '{canonical_name}' has been added to the played games database. Analysis complete."
            )
        else:
            await ctx.send(
                f"❌ **Cataloguing failed:** Unable to add '{canonical_name}' to the database. System malfunction detected."
            )

    except Exception as e:
        await ctx.send(f"❌ **Error processing game data:** {str(e)}")


@bot.command(name="listplayedgames")
@commands.has_permissions(manage_messages=True)
async def list_played_games_cmd(ctx, series_filter: Optional[str] = None):
    """List all played games, optionally filtered by series"""
    try:
        games = db.get_all_played_games(series_filter)

        if not games:
            if series_filter:
                await ctx.send(f"📋 **No games found in '{series_filter}' series.** Database query complete.")
            else:
                await ctx.send("📋 **No played games catalogued.** Database is empty.")
            return

        # Create embed
        embed = discord.Embed(
            title=f"🎮 Played Games Database" + (f" - {series_filter}" if series_filter else ""),
            description="Captain Jonesy's gaming history archive. Analysis complete.",
            color=0x2F3136,
        )

        # Group by series if not filtering
        if not series_filter:
            series_groups = {}
            for game in games:
                series = game.get("series_name", "Standalone Games")
                if series not in series_groups:
                    series_groups[series] = []
                series_groups[series].append(game)

            for series, series_games in series_groups.items():
                game_lines = []
                for game in series_games[:10]:  # Limit to avoid embed limits
                    status_emoji = {"completed": "✅", "ongoing": "🔄", "dropped": "❌", "unknown": "❓"}.get(
                        game.get("completion_status", "unknown"), "❓"
                    )

                    episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get("total_episodes", 0) > 0 else ""
                    year = f" ({game.get('release_year')})" if game.get("release_year") else ""

                    game_lines.append(f"{status_emoji} **{game['canonical_name']}**{year}{episodes}")

                if len(series_games) > 10:
                    game_lines.append(f"... and {len(series_games) - 10} more games")

                embed.add_field(
                    name=f"📁 {series} ({len(series_games)} games)",
                    value="\n".join(game_lines) if game_lines else "No games",
                    inline=False,
                )
        else:
            # Show detailed list for specific series
            game_lines = []
            for i, game in enumerate(games[:20], 1):  # Limit to 20 for detailed view
                status_emoji = {"completed": "✅", "ongoing": "🔄", "dropped": "❌", "unknown": "❓"}.get(
                    game.get("completion_status", "unknown"), "❓"
                )

                episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get("total_episodes", 0) > 0 else ""
                year = f" ({game.get('release_year')})" if game.get("release_year") else ""
                platform = f" [{game.get('platform')}]" if game.get("platform") else ""

                game_lines.append(f"{i}. {status_emoji} **{game['canonical_name']}**{year}{episodes}{platform}")

            if len(games) > 20:
                game_lines.append(f"... and {len(games) - 20} more games")

            embed.add_field(
                name="Games List", value="\n".join(game_lines) if game_lines else "No games found", inline=False
            )

        # Add footer
        embed.set_footer(text=f"Total games: {len(games)} | Database query: {ctx.author.name}")
        embed.timestamp = discord.utils.utcnow()

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ **Database query failed:** {str(e)}")


@bot.command(name="searchplayedgames")
@commands.has_permissions(manage_messages=True)
async def search_played_games_cmd(ctx, *, query: str):
    """Search played games by name, series, or notes"""
    try:
        games = db.search_played_games(query)

        if not games:
            await ctx.send(
                f"🔍 **Search complete:** No games found matching '{query}'. Database analysis yielded no results."
            )
            return

        # Create embed
        embed = discord.Embed(
            title=f"🔍 Search Results: '{query}'",
            description=f"Found {len(games)} matching entries in the played games database.",
            color=0x2F3136,
        )

        game_lines = []
        for i, game in enumerate(games[:15], 1):  # Limit to 15 results
            status_emoji = {"completed": "✅", "ongoing": "🔄", "dropped": "❌", "unknown": "❓"}.get(
                game.get("completion_status", "unknown"), "❓"
            )

            series = f" [{game.get('series_name')}]" if game.get("series_name") else ""
            episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get("total_episodes", 0) > 0 else ""
            year = f" ({game.get('release_year')})" if game.get("release_year") else ""

            game_lines.append(f"{i}. {status_emoji} **{game['canonical_name']}**{series}{year}{episodes}")

        if len(games) > 15:
            game_lines.append(f"... and {len(games) - 15} more results")

        embed.add_field(name="Matching Games", value="\n".join(game_lines), inline=False)

        embed.set_footer(text=f"Search query: {query} | Requested by {ctx.author.name}")
        embed.timestamp = discord.utils.utcnow()

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ **Search failed:** {str(e)}")


def get_game_by_id_or_name(identifier: str) -> Optional[Dict[str, Any]]:
    """Helper function to get a game by either ID (if numeric) or name"""
    try:
        # Check if identifier is numeric (ID)
        if identifier.isdigit():
            game_id = int(identifier)
            conn = db.get_connection()
            if not conn:
                return None

            with conn.cursor() as cur:
                cur.execute("SELECT * FROM played_games WHERE id = %s", (game_id,))
                result = cur.fetchone()
                return dict(result) if result else None
        else:
            # Use name-based lookup
            return db.get_played_game(identifier)
    except Exception as e:
        print(f"Error getting game by ID or name: {e}")
        return None


@bot.command(name="gameinfo")
@commands.has_permissions(manage_messages=True)
async def game_info_cmd(ctx, *, identifier: str):
    """Get detailed information about a specific played game (by name or ID)"""
    try:
        game = get_game_by_id_or_name(identifier)

        if not game:
            id_or_name = "ID" if identifier.isdigit() else "name"
            await ctx.send(
                f"🔍 **Game not found:** {id_or_name} '{identifier}' is not in the played games database. Analysis complete."
            )
            return

        # Create detailed embed
        embed = discord.Embed(
            title=f"🎮 {game['canonical_name']}",
            description="Detailed game analysis from database archives.",
            color=0x2F3136,
        )

        # Basic info
        if game.get("series_name"):
            embed.add_field(name="📁 Series", value=game["series_name"], inline=True)
        if game.get("release_year"):
            embed.add_field(name="📅 Release Year", value=str(game["release_year"]), inline=True)
        if game.get("platform"):
            embed.add_field(name="🖥️ Platform", value=game["platform"], inline=True)

        # Status and progress
        status_emoji = {
            "completed": "✅ Completed",
            "ongoing": "🔄 Ongoing",
            "dropped": "❌ Dropped",
            "unknown": "❓ Unknown",
        }.get(game.get("completion_status", "unknown"), "❓ Unknown")

        embed.add_field(name="📊 Status", value=status_emoji, inline=True)

        if game.get("total_episodes", 0) > 0:
            embed.add_field(name="📺 Episodes", value=str(game["total_episodes"]), inline=True)

        # Alternative names
        if game.get("alternative_names"):
            alt_names = ", ".join(game["alternative_names"])
            embed.add_field(name="🔄 Alternative Names", value=alt_names, inline=False)

        # Links
        if game.get("youtube_playlist_url"):
            embed.add_field(
                name="📺 YouTube Playlist", value=f"[View Playlist]({game['youtube_playlist_url']})", inline=True
            )

        if game.get("twitch_vod_urls"):
            vod_count = len(game["twitch_vod_urls"])
            embed.add_field(name="🎮 Twitch VODs", value=f"{vod_count} VODs available", inline=True)

        # Notes
        if game.get("notes"):
            embed.add_field(name="📝 Notes", value=game["notes"], inline=False)

        # Timestamps
        if game.get("first_played_date"):
            embed.add_field(name="🎯 First Played", value=game["first_played_date"], inline=True)

        embed.set_footer(text=f"Database ID: {game['id']} | Last updated: {game.get('updated_at', 'Unknown')}")

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ **Information retrieval failed:** {str(e)}")


@bot.command(name="updateplayedgame")
@commands.has_permissions(manage_messages=True)
async def update_played_game_cmd(ctx, identifier: str, *, updates: Optional[str] = None):
    """Update a played game's information (by name or ID). Format: status:completed | episodes:15 | notes:New info
    If no updates are provided, will refresh metadata using AI enhancement."""
    try:
        # Find the game first
        game = get_game_by_id_or_name(identifier)
        if not game:
            id_or_name = "ID" if identifier.isdigit() else "name"
            await ctx.send(f"🔍 **Game not found:** {id_or_name} '{identifier}' is not in the played games database.")
            return

        # If no updates provided, do AI metadata refresh
        if not updates or updates.strip() == "":
            await ctx.send(f"🧠 **Initiating AI metadata refresh for '{game['canonical_name']}'...**")

            if not ai_enabled:
                await ctx.send("❌ **AI system offline.** Cannot enhance metadata without AI capabilities.")
                return

            # Check what fields need updating
            needs_update = False
            missing_fields = []

            if not game.get("genre") or game.get("genre", "").strip() == "":
                needs_update = True
                missing_fields.append("genre")
            if not game.get("alternative_names") or len(game.get("alternative_names", [])) == 0:
                needs_update = True
                missing_fields.append("alternative_names")
            if not game.get("series_name") or game.get("series_name", "").strip() == "":
                needs_update = True
                missing_fields.append("series_name")
            if not game.get("release_year"):
                needs_update = True
                missing_fields.append("release_year")

            if not needs_update:
                await ctx.send(f"✅ **'{game['canonical_name']}' already has complete metadata.** No updates needed.")
                return

            await ctx.send(f"📊 **Missing fields detected:** {', '.join(missing_fields)}")

            # Convert to format expected by enhance_games_with_ai
            game_data = [
                {
                    "canonical_name": game["canonical_name"],
                    "alternative_names": game.get("alternative_names", []) or [],
                    "series_name": game.get("series_name"),
                    "genre": game.get("genre"),
                    "release_year": game.get("release_year"),
                    "db_id": game["id"],
                }
            ]

            # Use AI to enhance the game
            enhanced_games = await enhance_games_with_ai(game_data)

            if enhanced_games and len(enhanced_games) > 0:
                enhanced_game = enhanced_games[0]

                # Prepare update data with only the enhanced fields
                ai_update_data = {}

                if enhanced_game.get("genre") and enhanced_game["genre"] != game.get("genre"):
                    ai_update_data["genre"] = enhanced_game["genre"]
                if enhanced_game.get("series_name") and enhanced_game["series_name"] != game.get("series_name"):
                    ai_update_data["series_name"] = enhanced_game["series_name"]
                if enhanced_game.get("release_year") and enhanced_game["release_year"] != game.get("release_year"):
                    ai_update_data["release_year"] = enhanced_game["release_year"]
                if enhanced_game.get("alternative_names") and enhanced_game["alternative_names"] != game.get(
                    "alternative_names", []
                ):
                    ai_update_data["alternative_names"] = enhanced_game["alternative_names"]

                if ai_update_data:
                    # Apply AI updates using the same bulk import method that works reliably
                    complete_game_data = {
                        "canonical_name": enhanced_game["canonical_name"],
                        "alternative_names": enhanced_game.get("alternative_names", game.get("alternative_names", [])),
                        "series_name": enhanced_game.get("series_name", game.get("series_name")),
                        "genre": enhanced_game.get("genre", game.get("genre")),
                        "release_year": enhanced_game.get("release_year", game.get("release_year")),
                        "platform": game.get("platform"),
                        "first_played_date": game.get("first_played_date"),
                        "completion_status": game.get("completion_status", "unknown"),
                        "total_episodes": game.get("total_episodes", 0),
                        "total_playtime_minutes": game.get("total_playtime_minutes", 0),
                        "youtube_playlist_url": game.get("youtube_playlist_url"),
                        "twitch_vod_urls": game.get("twitch_vod_urls", []),
                        "notes": game.get("notes"),
                    }

                    # Use bulk import method for reliable updates
                    updated_count = db.bulk_import_played_games([complete_game_data])

                    if updated_count > 0:
                        updated_fields = list(ai_update_data.keys())
                        await ctx.send(
                            f"✅ **AI metadata refresh complete:** '{game['canonical_name']}' enhanced with {', '.join(updated_fields)}"
                        )

                        # Show the enhanced data
                        enhanced_info = []
                        if ai_update_data.get("genre"):
                            enhanced_info.append(f"**Genre:** {ai_update_data['genre']}")
                        if ai_update_data.get("series_name"):
                            enhanced_info.append(f"**Series:** {ai_update_data['series_name']}")
                        if ai_update_data.get("release_year"):
                            enhanced_info.append(f"**Year:** {ai_update_data['release_year']}")
                        if ai_update_data.get("alternative_names"):
                            alt_names = ", ".join(ai_update_data["alternative_names"])
                            enhanced_info.append(f"**Alt Names:** {alt_names}")

                        if enhanced_info:
                            await ctx.send(f"📊 **Enhanced metadata:**\n• " + "\n• ".join(enhanced_info))
                    else:
                        await ctx.send(
                            f"❌ **Update failed:** Unable to apply AI enhancements to '{game['canonical_name']}'."
                        )
                else:
                    await ctx.send(
                        f"ℹ️ **No enhancements available:** AI could not provide additional metadata for '{game['canonical_name']}'."
                    )
            else:
                await ctx.send(
                    f"❌ **AI enhancement failed:** Unable to process metadata for '{game['canonical_name']}'."
                )

            return

        # Manual updates path (existing functionality)
        # Parse updates
        update_data = {}
        parts = [part.strip() for part in updates.split("|")] if updates else []

        for part in parts:
            if ":" in part:
                key, value = part.split(":", 1)
                key = key.strip().lower()
                value = value.strip()

                if key == "status":
                    update_data["completion_status"] = value
                elif key == "episodes":
                    try:
                        update_data["total_episodes"] = int(value)
                    except ValueError:
                        await ctx.send(f"⚠️ **Invalid episode count:** '{value}' is not a valid number.")
                        return
                elif key == "notes":
                    update_data["notes"] = value
                elif key == "platform":
                    update_data["platform"] = value
                elif key == "year":
                    try:
                        update_data["release_year"] = int(value)
                    except ValueError:
                        await ctx.send(f"⚠️ **Invalid year:** '{value}' is not a valid year.")
                        return
                elif key == "series":
                    update_data["series_name"] = value
                elif key == "youtube":
                    update_data["youtube_playlist_url"] = value

        if not update_data:
            await ctx.send(
                "⚠️ **No valid updates provided.** Use format: status:completed | episodes:15 | notes:New info"
            )
            return

        # Apply updates
        success = db.update_played_game(game["id"], **update_data)

        if success:
            updated_fields = ", ".join(update_data.keys())
            await ctx.send(
                f"✅ **Game updated:** '{game['canonical_name']}' has been modified. Updated fields: {updated_fields}"
            )
        else:
            await ctx.send(
                f"❌ **Update failed:** Unable to modify '{game['canonical_name']}'. System malfunction detected."
            )

    except Exception as e:
        await ctx.send(f"❌ **Update error:** {str(e)}")


@bot.command(name="removeplayedgame")
@commands.has_permissions(manage_messages=True)
async def remove_played_game_cmd(ctx, *, game_name: str):
    """Remove a played game from the database"""
    try:
        # Find the game first
        game = db.get_played_game(game_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database.")
            return

        # Confirmation
        await ctx.send(
            f"⚠️ **WARNING:** This will permanently remove '{game['canonical_name']}' from the played games database. Type `CONFIRM DELETE` to proceed or anything else to cancel."
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)
            if msg.content == "CONFIRM DELETE":
                removed = db.remove_played_game(game["id"])
                if removed:
                    await ctx.send(
                        f"✅ **Game removed:** '{removed['canonical_name']}' has been expunged from the database. Protocol complete."
                    )
                else:
                    await ctx.send("❌ **Removal failed:** System malfunction during deletion process.")
            else:
                await ctx.send("❌ **Operation cancelled:** No data was deleted.")
        except asyncio.TimeoutError:
            await ctx.send("❌ **Operation timed out:** No data was deleted.")

    except Exception as e:
        await ctx.send(f"❌ **Removal error:** {str(e)}")


@bot.command(name="bulkimportplayedgames")
@commands.has_permissions(manage_messages=True)
async def bulk_import_played_games_cmd(
    ctx, youtube_channel_id: Optional[str] = None, twitch_username: Optional[str] = None
):
    """Import played games from YouTube and Twitch APIs with full metadata"""

    # Hardcoded values for Captain Jonesy's channels
    if not youtube_channel_id:
        youtube_channel_id = "UCPoUxLHeTnE9SUDAkqfJzDQ"  # Captain Jonesy's YouTube channel
    if not twitch_username:
        twitch_username = "jonesyspacecat"  # Captain Jonesy's Twitch username

    await ctx.send("🔄 **Initiating comprehensive gaming history analysis from YouTube and Twitch APIs...**")

    try:
        # Check API availability
        if not AIOHTTP_AVAILABLE:
            await ctx.send(
                "❌ **System malfunction:** aiohttp module not available. Cannot fetch data from external APIs."
            )
            return

        youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        twitch_client_id = os.getenv("TWITCH_CLIENT_ID")
        twitch_client_secret = os.getenv("TWITCH_CLIENT_SECRET")

        if not youtube_api_key:
            await ctx.send("⚠️ **YouTube API key not configured.** Skipping YouTube data collection.")
        if not twitch_client_id or not twitch_client_secret:
            await ctx.send("⚠️ **Twitch API credentials not configured.** Skipping Twitch data collection.")

        if not youtube_api_key and not (twitch_client_id and twitch_client_secret):
            await ctx.send("❌ **No API credentials available.** Cannot proceed with data collection.")
            return

        # Fetch comprehensive game data from both platforms
        all_games_data = []

        # YouTube data collection
        if youtube_api_key:
            await ctx.send("📺 **Analyzing YouTube gaming archive...**")
            try:
                youtube_games = await fetch_comprehensive_youtube_games(youtube_channel_id)
                all_games_data.extend(youtube_games)
                await ctx.send(f"📺 **YouTube analysis complete:** {len(youtube_games)} game series identified")
            except Exception as e:
                await ctx.send(f"⚠️ **YouTube API error:** {str(e)}")

        # Twitch data collection
        if twitch_client_id and twitch_client_secret:
            await ctx.send("🎮 **Analyzing Twitch gaming archive...**")
            try:
                twitch_games = await fetch_comprehensive_twitch_games(twitch_username)
                # Merge with YouTube data (avoid duplicates)
                for twitch_game in twitch_games:
                    # Check if game already exists from YouTube
                    existing_game = None
                    for yt_game in all_games_data:
                        if yt_game["canonical_name"].lower() == twitch_game["canonical_name"].lower():
                            existing_game = yt_game
                            break

                    if existing_game:
                        # Merge Twitch data into existing YouTube game
                        if twitch_game.get("twitch_vod_urls"):
                            existing_game["twitch_vod_urls"] = twitch_game["twitch_vod_urls"]
                        if twitch_game.get("total_playtime_minutes", 0) > 0:
                            existing_game["total_playtime_minutes"] += twitch_game["total_playtime_minutes"]
                    else:
                        # Add as new game
                        all_games_data.append(twitch_game)

                await ctx.send(f"🎮 **Twitch analysis complete:** {len(twitch_games)} game series identified")
            except Exception as e:
                await ctx.send(f"⚠️ **Twitch API error:** {str(e)}")

        if not all_games_data:
            await ctx.send("❌ **No gaming data retrieved.** Check API credentials and channel/username.")
            return

        # Use AI to enhance metadata
        if ai_enabled and gemini_model:
            await ctx.send("🧠 **Enhancing metadata using AI analysis...**")
            try:
                enhanced_games = await enhance_games_with_ai(all_games_data)
                all_games_data = enhanced_games
                await ctx.send("✅ **AI enhancement complete:** Genre and series data populated")
            except Exception as e:
                await ctx.send(f"⚠️ **AI enhancement error:** {str(e)}")

        # Show preview
        await ctx.send(f"📋 **Import Preview** ({len(all_games_data)} games discovered):")
        preview_games = all_games_data[:8]  # Show first 8 games
        for i, game in enumerate(preview_games, 1):
            episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get("total_episodes", 0) > 0 else ""
            playtime = (
                f" [{game.get('total_playtime_minutes', 0)//60}h {game.get('total_playtime_minutes', 0)%60}m]"
                if game.get("total_playtime_minutes", 0) > 0
                else ""
            )
            genre = f" - {game.get('genre', 'Unknown')}" if game.get("genre") else ""
            await ctx.send(f"{i}. **{game['canonical_name']}**{episodes}{playtime}{genre}")

        if len(all_games_data) > 8:
            await ctx.send(f"... and {len(all_games_data) - 8} more games")

        await ctx.send(
            f"\n⚠️ **WARNING**: This will add {len(all_games_data)} games to the played games database. Type `CONFIRM IMPORT` to proceed or anything else to cancel."
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60.0)
            if msg.content == "CONFIRM IMPORT":
                imported_count = db.bulk_import_played_games(all_games_data)
                await ctx.send(
                    f"✅ **Import complete:** Successfully imported {imported_count} played games with comprehensive metadata to the database."
                )

                # Show final statistics
                stats = db.get_played_games_stats()
                await ctx.send(
                    f"📊 **Database Statistics:**\n• Total games: {stats.get('total_games', 0)}\n• Total episodes: {stats.get('total_episodes', 0)}\n• Total playtime: {stats.get('total_playtime_hours', 0)} hours"
                )
            else:
                await ctx.send("❌ **Import cancelled.** No games were added to the database.")
        except asyncio.TimeoutError:
            await ctx.send("❌ **Import timed out.** No games were added to the database.")

    except Exception as e:
        await ctx.send(f"❌ **Import error:** {str(e)}")


@bot.command(name="fixcanonicalname")
@commands.has_permissions(manage_messages=True)
async def fix_canonical_name_cmd(ctx, current_name: str, *, new_canonical_name: str):
    """Fix the canonical name of a played game to correct grammatical errors or improve formatting"""
    try:
        # Find the game first
        game = db.get_played_game(current_name)
        if not game:
            await ctx.send(
                f"🔍 **Game not found:** '{current_name}' is not in the played games database. Analysis complete."
            )
            return

        # Show current information
        old_name = game["canonical_name"]
        await ctx.send(
            f"📝 **Current canonical name:** '{old_name}'\n📝 **Proposed new name:** '{new_canonical_name}'\n\n⚠️ **Confirmation required:** This will update the canonical name used for database searches and AI responses. Type `CONFIRM UPDATE` to proceed or anything else to cancel."
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)
            if msg.content == "CONFIRM UPDATE":
                # Update the canonical name
                success = db.update_played_game(game["id"], canonical_name=new_canonical_name)

                if success:
                    await ctx.send(
                        f"✅ **Canonical name updated:** '{old_name}' → '{new_canonical_name}'\n\n📊 **Database analysis:** The bot will now recognize this game by its corrected canonical name. Previous alternative names remain valid for searches."
                    )

                    # Show updated game info
                    updated_game = db.get_played_game(new_canonical_name)
                    if updated_game:
                        alt_names = (
                            ", ".join(updated_game.get("alternative_names", []))
                            if updated_game.get("alternative_names")
                            else "None"
                        )
                        series = updated_game.get("series_name", "None")
                        await ctx.send(
                            f"🔍 **Updated game record:**\n• **Canonical Name:** {updated_game['canonical_name']}\n• **Series:** {series}\n• **Alternative Names:** {alt_names}"
                        )
                else:
                    await ctx.send(
                        f"❌ **Update failed:** Unable to modify canonical name for '{old_name}'. System malfunction detected."
                    )
            else:
                await ctx.send("❌ **Operation cancelled:** No changes were made to the canonical name.")
        except asyncio.TimeoutError:
            await ctx.send("❌ **Operation timed out:** No changes were made to the canonical name.")

    except Exception as e:
        await ctx.send(f"❌ **Canonical name correction error:** {str(e)}")


@bot.command(name="addaltname")
@commands.has_permissions(manage_messages=True)
async def add_alternative_name_cmd(ctx, game_name: str, *, alternative_name: str):
    """Add an alternative name to a played game for better search recognition"""
    try:
        # Find the game first
        game = db.get_played_game(game_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database.")
            return

        # Get current alternative names
        current_alt_names = game.get("alternative_names", []) or []

        # Check if the alternative name already exists
        if alternative_name.lower() in [name.lower() for name in current_alt_names]:
            await ctx.send(
                f"⚠️ **Alternative name already exists:** '{alternative_name}' is already listed as an alternative name for '{game['canonical_name']}'."
            )
            return

        # Add the new alternative name
        updated_alt_names = current_alt_names + [alternative_name]
        success = db.update_played_game(game["id"], alternative_names=updated_alt_names)

        if success:
            await ctx.send(
                f"✅ **Alternative name added:** '{alternative_name}' has been added to '{game['canonical_name']}'\n\n📊 **Current alternative names:** {', '.join(updated_alt_names)}"
            )
        else:
            await ctx.send(
                f"❌ **Update failed:** Unable to add alternative name to '{game['canonical_name']}'. System malfunction detected."
            )

    except Exception as e:
        await ctx.send(f"❌ **Alternative name addition error:** {str(e)}")


@bot.command(name="removealtname")
@commands.has_permissions(manage_messages=True)
async def remove_alternative_name_cmd(ctx, game_name: str, *, alternative_name: str):
    """Remove an alternative name from a played game"""
    try:
        # Find the game first
        game = db.get_played_game(game_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database.")
            return

        # Get current alternative names
        current_alt_names = game.get("alternative_names", []) or []

        # Find and remove the alternative name (case-insensitive)
        updated_alt_names = []
        removed = False
        for name in current_alt_names:
            if name.lower() == alternative_name.lower():
                removed = True
            else:
                updated_alt_names.append(name)

        if not removed:
            await ctx.send(
                f"⚠️ **Alternative name not found:** '{alternative_name}' is not listed as an alternative name for '{game['canonical_name']}'.\n\n📊 **Current alternative names:** {', '.join(current_alt_names) if current_alt_names else 'None'}"
            )
            return

        # Update the game with the new list
        success = db.update_played_game(game["id"], alternative_names=updated_alt_names)

        if success:
            remaining_names = ", ".join(updated_alt_names) if updated_alt_names else "None"
            await ctx.send(
                f"✅ **Alternative name removed:** '{alternative_name}' has been removed from '{game['canonical_name']}'\n\n📊 **Remaining alternative names:** {remaining_names}"
            )
        else:
            await ctx.send(
                f"❌ **Update failed:** Unable to remove alternative name from '{game['canonical_name']}'. System malfunction detected."
            )

    except Exception as e:
        await ctx.send(f"❌ **Alternative name removal error:** {str(e)}")


@bot.command(name="updateplayedgames")
@commands.has_permissions(manage_messages=True)
async def update_played_games_cmd(ctx):
    """Update existing played games to fill in missing fields using AI enhancement"""
    try:
        await ctx.send("🔄 **Initiating metadata enhancement for existing played games...**")

        # Get all played games from database
        all_games = db.get_all_played_games()

        if not all_games:
            await ctx.send(
                "❌ **No played games found in database.** Use `!bulkimportplayedgames` to import games first."
            )
            return

        # Filter games that need updates (missing genre, alternative_names, or series_name)
        games_needing_updates = []
        for game in all_games:
            needs_update = False

            # Check for missing or empty fields
            if not game.get("genre") or game.get("genre", "").strip() == "":
                needs_update = True
            if not game.get("alternative_names") or len(game.get("alternative_names", [])) == 0:
                needs_update = True
            if not game.get("series_name") or game.get("series_name", "").strip() == "":
                needs_update = True
            if not game.get("release_year"):
                needs_update = True

            if needs_update:
                games_needing_updates.append(game)

        if not games_needing_updates:
            await ctx.send("✅ **All games already have complete metadata.** No updates needed.")
            return

        await ctx.send(
            f"📊 **Analysis complete:** {len(games_needing_updates)} out of {len(all_games)} games need metadata updates."
        )

        # Show preview of games to be updated
        preview_msg = f"🔍 **Games requiring updates:**\n"
        for i, game in enumerate(games_needing_updates[:10], 1):
            missing_fields = []
            if not game.get("genre"):
                missing_fields.append("genre")
            if not game.get("alternative_names") or len(game.get("alternative_names", [])) == 0:
                missing_fields.append("alt_names")
            if not game.get("series_name"):
                missing_fields.append("series")
            if not game.get("release_year"):
                missing_fields.append("year")

            preview_msg += f"{i}. **{game['canonical_name']}** (missing: {', '.join(missing_fields)})\n"

        if len(games_needing_updates) > 10:
            preview_msg += f"... and {len(games_needing_updates) - 10} more games\n"

        preview_msg += f"\n⚠️ **Confirmation required:** This will use AI to enhance metadata for {len(games_needing_updates)} games. Type `CONFIRM UPDATE` to proceed or anything else to cancel."

        await ctx.send(preview_msg)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=60.0)
            if msg.content == "CONFIRM UPDATE":
                if not ai_enabled:
                    await ctx.send("❌ **AI system offline.** Cannot enhance metadata without AI capabilities.")
                    return

                await ctx.send("🧠 **AI enhancement initiated.** Processing games in batches...")

                # Convert database games to the format expected by enhance_games_with_ai
                games_data = []
                for game in games_needing_updates:
                    game_data = {
                        "canonical_name": game["canonical_name"],
                        "alternative_names": game.get("alternative_names", []) or [],
                        "series_name": game.get("series_name"),
                        "genre": game.get("genre"),
                        "release_year": game.get("release_year"),
                        "db_id": game["id"],  # Store database ID for updates
                    }
                    games_data.append(game_data)

                # Use AI to enhance the games
                enhanced_games = await enhance_games_with_ai(games_data)

                # Apply updates to database using the same method as bulk import
                updated_count = 0

                # Convert enhanced games back to the format expected by bulk_import_played_games
                games_for_bulk_update = []
                for enhanced_game in enhanced_games:
                    # Find the original game data to preserve existing fields
                    original_game = None
                    for game in games_needing_updates:
                        if game["id"] == enhanced_game.get("db_id"):
                            original_game = game
                            break

                    if original_game:
                        # Create a complete game record for bulk import (which handles upserts)
                        game_data = {
                            "canonical_name": enhanced_game["canonical_name"],
                            "alternative_names": enhanced_game.get(
                                "alternative_names", original_game.get("alternative_names", [])
                            ),
                            "series_name": enhanced_game.get("series_name", original_game.get("series_name")),
                            "genre": enhanced_game.get("genre", original_game.get("genre")),
                            "release_year": enhanced_game.get("release_year", original_game.get("release_year")),
                            "platform": original_game.get("platform"),
                            "first_played_date": original_game.get("first_played_date"),
                            "completion_status": original_game.get("completion_status", "unknown"),
                            "total_episodes": original_game.get("total_episodes", 0),
                            "total_playtime_minutes": original_game.get("total_playtime_minutes", 0),
                            "youtube_playlist_url": original_game.get("youtube_playlist_url"),
                            "twitch_vod_urls": original_game.get("twitch_vod_urls", []),
                            "notes": original_game.get("notes"),
                        }
                        games_for_bulk_update.append(game_data)

                # Use the same bulk import method that works
                if games_for_bulk_update:
                    updated_count = db.bulk_import_played_games(games_for_bulk_update)

                await ctx.send(
                    f"✅ **Metadata enhancement complete:** Successfully updated {updated_count} games with enhanced metadata."
                )

                # Run deduplication to merge any duplicate games created during import
                await ctx.send("🔄 **Running deduplication check to merge any duplicate games...**")
                merged_count = db.deduplicate_played_games()

                if merged_count > 0:
                    await ctx.send(f"✅ **Deduplication complete:** Merged {merged_count} duplicate game records.")
                else:
                    await ctx.send("✅ **Deduplication complete:** No duplicate games found.")

                # Show final statistics
                stats = db.get_played_games_stats()
                await ctx.send(
                    f"📊 **Updated Database Statistics:**\n• Total games: {stats.get('total_games', 0)}\n• Total episodes: {stats.get('total_episodes', 0)}\n• Total playtime: {stats.get('total_playtime_hours', 0)} hours"
                )

            else:
                await ctx.send("❌ **Update cancelled.** No games were modified.")
        except asyncio.TimeoutError:
            await ctx.send("❌ **Update timed out.** No games were modified.")

    except Exception as e:
        await ctx.send(f"❌ **Update error:** {str(e)}")


@bot.command(name="checkdbschema")
@commands.has_permissions(manage_messages=True)
async def check_db_schema_cmd(ctx):
    """Check database schema and array field compatibility"""
    try:
        conn = db.get_connection()
        if not conn:
            await ctx.send("❌ **Database connection failed**")
            return

        await ctx.send("🔍 **Checking database schema compatibility...**")

        with conn.cursor() as cur:
            # Check if played_games table exists and get its structure
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'played_games'
                ORDER BY ordinal_position
            """
            )
            columns = cur.fetchall()

            if not columns:
                await ctx.send("❌ **played_games table not found** - Run the bot once to initialize schema")
                return

            # Check for required array fields
            array_fields = {}
            required_fields = ["alternative_names", "twitch_vod_urls"]

            for col in columns:
                col_name = col[0]
                data_type = col[1]
                if col_name in required_fields:
                    array_fields[col_name] = data_type

            schema_msg = "📊 **Database Schema Status:**\n"

            # Check array fields
            for field in required_fields:
                if field in array_fields:
                    data_type = array_fields[field]
                    if "ARRAY" in data_type or "_text" in data_type:
                        schema_msg += f"✅ **{field}**: {data_type} (Array support: YES)\n"
                    else:
                        schema_msg += f"⚠️ **{field}**: {data_type} (Array support: NO)\n"
                else:
                    schema_msg += f"❌ **{field}**: Missing column\n"

            # Test array functionality
            try:
                cur.execute("SELECT id, canonical_name, alternative_names FROM played_games LIMIT 1")
                test_game = cur.fetchone()

                if test_game:
                    alt_names = test_game[2]
                    schema_msg += f"\n🧪 **Array Test Sample:**\n"
                    schema_msg += f"• Game: {test_game[1]}\n"
                    schema_msg += f"• Alt Names: {alt_names} (Type: {type(alt_names).__name__})\n"

                    # Test if we can read arrays properly
                    if isinstance(alt_names, list):
                        schema_msg += f"✅ **Array reading**: Working correctly\n"
                    else:
                        schema_msg += f"⚠️ **Array reading**: May need schema update\n"
                else:
                    schema_msg += f"\n📝 **No test data available** - Add some games first\n"

            except Exception as e:
                schema_msg += f"\n❌ **Array test failed**: {str(e)}\n"

            # Manual edit instructions
            schema_msg += f"\n📝 **Manual Database Edit Instructions:**\n"
            schema_msg += f"```sql\n"
            schema_msg += f"-- ✅ CORRECT array syntax:\n"
            schema_msg += f"UPDATE played_games \n"
            schema_msg += f"SET alternative_names = ARRAY['Alt1', 'Alt2'] \n"
            schema_msg += f"WHERE canonical_name = 'Game Name';\n\n"
            schema_msg += f"-- ✅ Add to existing array:\n"
            schema_msg += f"UPDATE played_games \n"
            schema_msg += f"SET alternative_names = alternative_names || ARRAY['New Alt'] \n"
            schema_msg += f"WHERE canonical_name = 'Game Name';\n"
            schema_msg += f"```"

            await ctx.send(schema_msg)

    except Exception as e:
        await ctx.send(f"❌ **Schema check failed**: {str(e)}")


@bot.command(name="setaltnames")
@commands.has_permissions(manage_messages=True)
async def set_alternative_names_cmd(ctx, game_name: str, *, alternative_names: str):
    """Set alternative names for a played game. Use comma-separated format: name1, name2, name3"""
    try:
        # Find the game first
        game = db.get_played_game(game_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database.")
            return

        # Parse alternative names from comma-separated string
        alt_names_list = [name.strip() for name in alternative_names.split(",") if name.strip()]

        if not alt_names_list:
            await ctx.send("⚠️ **No valid alternative names provided.** Use comma-separated format: name1, name2, name3")
            return

        # Show preview
        await ctx.send(
            f"📝 **Setting alternative names for '{game['canonical_name']}':**\n• {chr(10).join(alt_names_list)}\n\n⚠️ **This will replace all existing alternative names.** Type `CONFIRM SET` to proceed or anything else to cancel."
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0)
            if msg.content == "CONFIRM SET":
                # Update the game with the new alternative names
                success = db.update_played_game(game["id"], alternative_names=alt_names_list)

                if success:
                    await ctx.send(
                        f"✅ **Alternative names updated:** '{game['canonical_name']}' now has {len(alt_names_list)} alternative names:\n• {chr(10).join(alt_names_list)}"
                    )
                else:
                    await ctx.send(
                        f"❌ **Update failed:** Unable to set alternative names for '{game['canonical_name']}'. System malfunction detected."
                    )
            else:
                await ctx.send("❌ **Operation cancelled:** No changes were made to alternative names.")
        except asyncio.TimeoutError:
            await ctx.send("❌ **Operation timed out:** No changes were made to alternative names.")

    except Exception as e:
        await ctx.send(f"❌ **Alternative names setting error:** {str(e)}")


@bot.command(name="testupdategame")
@commands.has_permissions(manage_messages=True)
async def test_update_game_cmd(ctx, game_id: str, field: str, *, value: str):
    """Test updating a single game field by ID without AI calls. Usage: !testupdategame 1 genre Action"""
    try:
        # Validate game ID is numeric
        if not game_id.isdigit():
            await ctx.send("❌ **Invalid game ID:** Please provide a numeric game ID (e.g., 1, 2, 3)")
            return

        game_id_int = int(game_id)

        # Find the game by ID
        game = db.get_played_game_by_id(game_id_int)
        if not game:
            await ctx.send(f"🔍 **Game not found:** No game with ID {game_id} exists in the database.")
            return

        # Validate field name
        valid_fields = [
            "genre",
            "series_name",
            "platform",
            "completion_status",
            "notes",
            "release_year",
            "total_episodes",
            "total_playtime_minutes",
        ]

        if field.lower() not in valid_fields:
            await ctx.send(
                f"❌ **Invalid field:** '{field}' is not a valid field. Valid fields: {', '.join(valid_fields)}"
            )
            return

        # Convert value to appropriate type
        update_value = value
        if field.lower() in ["release_year", "total_episodes", "total_playtime_minutes"]:
            try:
                update_value = int(value)
            except ValueError:
                await ctx.send(f"❌ **Invalid value:** '{value}' is not a valid number for field '{field}'")
                return

        # Show current and new values
        current_value = game.get(field.lower(), "None")
        await ctx.send(
            f"🔍 **Game:** {game['canonical_name']} (ID: {game_id})\n📝 **Field:** {field}\n📊 **Current value:** {current_value}\n📊 **New value:** {update_value}"
        )

        # Perform the update
        update_data = {field.lower(): update_value}
        success = db.update_played_game(game_id_int, **update_data)

        if success:
            await ctx.send(f"✅ **Update successful:** {field} updated from '{current_value}' to '{update_value}'")

            # Verify the update by reading the game again
            updated_game = db.get_played_game_by_id(game_id_int)
            if updated_game:
                verified_value = updated_game.get(field.lower(), "None")
                if str(verified_value) == str(update_value):
                    await ctx.send(f"✅ **Verification successful:** Database now shows {field} = '{verified_value}'")
                else:
                    await ctx.send(
                        f"⚠️ **Verification warning:** Expected '{update_value}' but database shows '{verified_value}'"
                    )
            else:
                await ctx.send("⚠️ **Verification failed:** Could not re-read game from database")
        else:
            await ctx.send(
                f"❌ **Update failed:** Database update operation returned false. Check database permissions and connection."
            )

    except Exception as e:
        await ctx.send(f"❌ **Test update error:** {str(e)}")


@bot.command(name="debuggame")
@commands.has_permissions(manage_messages=True)
async def debug_game_cmd(ctx, game_id: str):
    """Debug a specific game's database record and update capabilities"""
    try:
        if not game_id.isdigit():
            await ctx.send("❌ **Invalid game ID:** Please provide a numeric game ID")
            return

        game_id_int = int(game_id)

        # Get the game
        game = db.get_played_game_by_id(game_id_int)
        if not game:
            await ctx.send(f"🔍 **Game not found:** No game with ID {game_id} exists in the database.")
            return

        # Show detailed game information
        debug_info = f"🔍 **Game Debug Information:**\n"
        debug_info += f"• **ID:** {game.get('id')}\n"
        debug_info += f"• **Canonical Name:** {game.get('canonical_name')}\n"
        debug_info += f"• **Series:** {game.get('series_name', 'None')}\n"
        debug_info += f"• **Genre:** {game.get('genre', 'None')}\n"
        debug_info += f"• **Release Year:** {game.get('release_year', 'None')}\n"
        debug_info += f"• **Platform:** {game.get('platform', 'None')}\n"
        debug_info += f"• **Status:** {game.get('completion_status', 'None')}\n"
        debug_info += f"• **Episodes:** {game.get('total_episodes', 0)}\n"
        debug_info += f"• **Playtime:** {game.get('total_playtime_minutes', 0)} minutes\n"
        debug_info += f"• **Alt Names:** {game.get('alternative_names', [])}\n"
        debug_info += f"• **Created:** {game.get('created_at', 'None')}\n"
        debug_info += f"• **Updated:** {game.get('updated_at', 'None')}\n"

        await ctx.send(debug_info)

        # Test database connection and permissions
        conn = db.get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    # Test if we can read the specific game
                    cur.execute("SELECT canonical_name FROM played_games WHERE id = %s", (game_id_int,))
                    result = cur.fetchone()
                    if result:
                        await ctx.send(f"✅ **Database read test:** Successfully read game '{result[0]}'")
                    else:
                        await ctx.send("❌ **Database read test:** Failed to read game")

                    # Test if we can perform a harmless update (set updated_at to current time)
                    cur.execute("UPDATE played_games SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (game_id_int,))
                    rows_affected = cur.rowcount
                    await ctx.send(f"✅ **Database update test:** {rows_affected} row(s) affected by timestamp update")

                    # Rollback the test update
                    conn.rollback()
                    await ctx.send("✅ **Test update rolled back:** No permanent changes made")

            except Exception as db_error:
                await ctx.send(f"❌ **Database test error:** {str(db_error)}")
        else:
            await ctx.send("❌ **Database connection failed:** Cannot test update capabilities")

    except Exception as e:
        await ctx.send(f"❌ **Debug error:** {str(e)}")


# --- Reminder Commands ---
@bot.command(name="remind")
async def remind_command(ctx, *, reminder_request: str):
    """Set a reminder with natural language parsing. Usage: !remind [me] to/of [action] at/in [time]"""
    try:
        # Check user permissions - only moderator, creator, and captain tiers
        user_tier = await get_user_communication_tier(ctx)
        if user_tier not in ["moderator", "creator", "captain"]:
            await ctx.send(
                f"⚠️ **Access denied.** Reminder protocols are restricted to authorized personnel only. "
                f"Current clearance level insufficient for temporal scheduling functions."
            )
            return

        # Parse the natural language request
        parsed = parse_natural_reminder(reminder_request, ctx.author.id)

        if not parsed["success"] or not parsed["reminder_text"]:
            await ctx.send(
                f"⚠️ **Parsing failure.** Unable to extract valid reminder parameters from your request. "
                f"Please specify both the reminder content and timing. Example: 'remind me to post the YouTube link at 6pm'"
            )
            return

        reminder_text = parsed["reminder_text"]
        scheduled_time = parsed["scheduled_time"]

        # Determine delivery method - DM for direct messages, channel for guild messages
        delivery_type = "dm" if ctx.guild is None else "channel"
        delivery_channel_id = ctx.channel.id if ctx.guild else None

        # Check for auto-action patterns (YouTube posting)
        auto_action_enabled = False
        auto_action_type = None
        auto_action_data = {}

        youtube_url_pattern = r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]+)'
        youtube_urls = re.findall(youtube_url_pattern, reminder_request, re.IGNORECASE)

        if youtube_urls or "youtube" in reminder_request.lower():
            # Ask about auto-action
            auto_action_msg = await ctx.send(
                f"📺 **YouTube content detected.** Would you like me to automatically post this to the youtube-uploads channel "
                f"if you don't respond within 5 minutes of the reminder?\n\n"
                f"React with ✅ to enable auto-posting or ❌ to disable."
            )
            await auto_action_msg.add_reaction("✅")
            await auto_action_msg.add_reaction("❌")

            try:

                def check_reaction(reaction, user):
                    return (
                        user == ctx.author
                        and str(reaction.emoji) in ["✅", "❌"]
                        and reaction.message.id == auto_action_msg.id
                    )

                reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check_reaction)

                if str(reaction.emoji) == "✅":
                    auto_action_enabled = True
                    auto_action_type = "youtube_post"
                    youtube_url = None

                    # Extract YouTube URL if found, otherwise ask for it
                    if youtube_urls:
                        youtube_url = f"https://youtube.com/watch?v={youtube_urls[0]}"
                    else:
                        url_msg = await ctx.send("🔗 **Please provide the YouTube URL for auto-posting:**")

                        def check_url_msg(msg):
                            return msg.author == ctx.author and msg.channel == ctx.channel

                        try:
                            url_response = await bot.wait_for('message', timeout=60.0, check=check_url_msg)
                            youtube_url = url_response.content.strip()
                        except asyncio.TimeoutError:
                            await ctx.send("⏰ **URL input timed out.** Auto-action disabled.")
                            auto_action_enabled = False
                            auto_action_type = None
                            youtube_url = None

                    if auto_action_enabled and youtube_url:
                        auto_action_data = {
                            "youtube_url": youtube_url,
                            "custom_message": f"New video uploaded - check it out!",
                        }
                        await ctx.send(
                            "✅ **Auto-action enabled.** YouTube link will be posted automatically if no response within 5 minutes."
                        )
                    elif auto_action_enabled and not youtube_url:
                        await ctx.send("❌ **Auto-action disabled:** No valid YouTube URL provided.")
                        auto_action_enabled = False
                        auto_action_type = None

            except asyncio.TimeoutError:
                await ctx.send("⏰ **Auto-action selection timed out.** Proceeding without auto-posting.")

        # Add the reminder to database
        reminder_id = db.add_reminder(
            user_id=ctx.author.id,
            reminder_text=reminder_text,
            scheduled_time=scheduled_time,
            delivery_channel_id=delivery_channel_id,
            delivery_type=delivery_type,
            auto_action_enabled=auto_action_enabled,
            auto_action_type=auto_action_type,
            auto_action_data=auto_action_data,
        )

        if reminder_id:
            # Format time for display
            uk_time = scheduled_time.strftime("%A, %B %d, %Y at %H:%M UK time")
            auto_notice = (
                "\n\n⚡ **Auto-action enabled:** YouTube posting sequence will activate if no response within 5 minutes."
                if auto_action_enabled
                else ""
            )

            await ctx.send(
                f"📋 **Reminder protocol activated.** Your temporal alert has been scheduled for {uk_time}.\n\n"
                f"**Content:** {reminder_text}\n"
                f"**Delivery method:** {'Direct message' if delivery_type == 'dm' else 'Channel notification'}"
                f"{auto_notice}\n\n"
                f"*Efficiency is paramount. Mission parameters logged.*"
            )
        else:
            await ctx.send(
                f"❌ **System malfunction detected.** Unable to establish temporal scheduling protocol. "
                f"Database insertion failed."
            )

    except Exception as e:
        print(f"❌ Error in remind command: {e}")
        await ctx.send(
            f"❌ **Critical system error.** Reminder protocols experienced malfunction during processing: {str(e)}"
        )


@bot.command(name="remindme")
async def remind_me_command(ctx, *, reminder_request: str):
    """Alias for remind command with 'me' implied"""
    # Prepend 'me' if not already present for natural parsing
    if not reminder_request.lower().startswith("me"):
        reminder_request = f"me {reminder_request}"

    await remind_command(ctx, reminder_request=reminder_request)


@bot.command(name="listreminders")
async def list_reminders_command(ctx):
    """List user's active reminders"""
    try:
        # Check user permissions
        user_tier = await get_user_communication_tier(ctx)
        if user_tier not in ["moderator", "creator", "captain"]:
            await ctx.send(f"⚠️ **Access denied.** Reminder protocols are restricted to authorized personnel only.")
            return

        reminders = db.get_user_reminders(ctx.author.id)

        if not reminders:
            await ctx.send(
                f"📋 **Temporal analysis complete.** No active reminder protocols found in your personal archive. "
                f"All scheduled alerts have been processed or cleared."
            )
            return

        # Create embed for reminders list
        embed = discord.Embed(
            title="📋 Active Reminder Protocols",
            description=f"Mission-critical temporal alerts for {ctx.author.display_name}",
            color=0x2F3136,
        )

        uk_now = datetime.now(ZoneInfo("Europe/London"))

        for i, reminder in enumerate(reminders, 1):
            scheduled_time = reminder["scheduled_time"]

            # Convert to UK timezone if not already
            if scheduled_time.tzinfo is None:
                scheduled_time = scheduled_time.replace(tzinfo=ZoneInfo("Europe/London"))
            elif scheduled_time.tzinfo != ZoneInfo("Europe/London"):
                scheduled_time = scheduled_time.astimezone(ZoneInfo("Europe/London"))

            time_until = scheduled_time - uk_now

            if time_until.total_seconds() > 0:
                # Future reminder
                days = time_until.days
                hours, remainder = divmod(time_until.seconds, 3600)
                minutes, _ = divmod(remainder, 60)

                if days > 0:
                    time_str = f"in {days}d {hours}h {minutes}m"
                elif hours > 0:
                    time_str = f"in {hours}h {minutes}m"
                else:
                    time_str = f"in {minutes}m"
            else:
                # Overdue reminder
                time_str = "**OVERDUE**"

            # Format time
            formatted_time = scheduled_time.strftime("%A, %B %d at %H:%M")

            # Delivery method
            delivery_method = "📧 DM" if reminder["delivery_type"] == "dm" else "📢 Channel"

            # Auto-action status
            auto_action = ""
            if reminder.get("auto_action_enabled"):
                auto_action = (
                    f" ⚡ **Auto-action:** {reminder.get('auto_action_type', 'unknown').replace('_', ' ').title()}"
                )

            reminder_text = (
                reminder["reminder_text"][:100] + "..."
                if len(reminder["reminder_text"]) > 100
                else reminder["reminder_text"]
            )

            embed.add_field(
                name=f"#{i} - {time_str}",
                value=f"**{formatted_time}**\n{delivery_method} - {reminder_text}{auto_action}",
                inline=False,
            )

        embed.set_footer(text=f"Total active reminders: {len(reminders)} | Use !cancelreminder <number> to cancel")
        embed.timestamp = discord.utils.utcnow()

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"❌ Error in list reminders command: {e}")
        await ctx.send(f"❌ **System diagnostic error:** Unable to retrieve reminder protocols: {str(e)}")


@bot.command(name="addtriviaquestion")
@commands.has_permissions(manage_messages=True)
async def add_trivia_question_cmd(ctx):
    """Start interactive DM conversation for moderators to submit trivia questions"""
    # Check if command is used in DM
    if ctx.guild is not None:
        await ctx.send(
            f"⚠️ **Security protocol engaged.** Trivia question submission must be initiated via direct message. "
            f"Please DM me with `!addtriviaquestion` to begin the secure submission process.\n\n"
            f"*Confidential mission parameters require private channel authorization.*"
        )
        return

    # Check if user is a moderator
    if not await user_is_mod_by_id(ctx.author.id):
        await ctx.send(
            f"❌ **Access denied.** Trivia question submission protocols are restricted to moderators only. "
            f"Your clearance level is insufficient for trivia database modification capabilities.\n\n"
            f"*Security protocols maintained. Unauthorized access logged.*"
        )
        return

    # Clean up any existing conversation state for this user
    cleanup_mod_trivia_conversations()

    # Initialize conversation state
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    mod_trivia_conversations[ctx.author.id] = {
        'step': 'initial',
        'data': {},
        'last_activity': uk_now,
        'initiated_at': uk_now,
    }

    # Start with a direct question about adding trivia
    await handle_mod_trivia_conversation(ctx.message)


@bot.command(name="cancelreminder")
async def cancel_reminder_command(ctx, reminder_number: int):
    """Cancel a specific reminder by number from list"""
    try:
        # Check user permissions
        user_tier = await get_user_communication_tier(ctx)
        if user_tier not in ["moderator", "creator", "captain"]:
            await ctx.send(f"⚠️ **Access denied.** Reminder protocols are restricted to authorized personnel only.")
            return

        reminders = db.get_user_reminders(ctx.author.id)

        if not reminders:
            await ctx.send(f"📋 **No active reminders found.** Your temporal alert archive is currently empty.")
            return

        if reminder_number < 1 or reminder_number > len(reminders):
            await ctx.send(
                f"⚠️ **Invalid reminder designation.** Please specify a number between 1 and {len(reminders)}. "
                f"Use `!listreminders` to view available protocols."
            )
            return

        # Get the specific reminder
        selected_reminder = reminders[reminder_number - 1]
        reminder_text = selected_reminder["reminder_text"]
        scheduled_time = selected_reminder["scheduled_time"]

        # Format time for confirmation
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=ZoneInfo("Europe/London"))
        formatted_time = scheduled_time.strftime("%A, %B %d at %H:%M UK time")

        # Cancel the reminder
        success = db.cancel_reminder(selected_reminder["id"], ctx.author.id)

        if success:
            await ctx.send(
                f"✅ **Temporal alert cancelled.** Reminder protocol has been expunged from the system.\n\n"
                f"**Cancelled reminder:** {reminder_text}\n"
                f"**Scheduled for:** {formatted_time}\n\n"
                f"*Mission parameters updated. Efficiency maintained.*"
            )
        else:
            await ctx.send(
                f"❌ **Cancellation failed.** Unable to terminate reminder protocol. System malfunction detected."
            )

    except ValueError:
        await ctx.send(
            f"⚠️ **Invalid input format.** Please provide a numeric reminder identifier. "
            f"Usage: `!cancelreminder <number>`"
        )
    except Exception as e:
        print(f"❌ Error in cancel reminder command: {e}")
        await ctx.send(f"❌ **System error during cancellation:** {str(e)}")


# --- Reminder System Constants ---
# YouTube uploads channel ID for auto-actions
YOUTUBE_UPLOADS_CHANNEL_ID = 869527363594121226


# --- Cleanup ---
def cleanup():
    try:
        os.remove(LOCK_FILE)
    except:
        pass


def signal_handler(sig, frame):
    print("\n🛑 Shutdown requested...")
    cleanup()
    sys.exit(0)


atexit.register(cleanup)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Only run the bot if this script is executed directly (not imported)
if __name__ == "__main__":
    # Ensure TOKEN is set before running the bot
    if not TOKEN:
        print("❌ DISCORD_TOKEN environment variable not set. Exiting.")
        sys.exit(1)

    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    finally:
        cleanup()
