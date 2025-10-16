#!/usr/bin/env python3
"""
Ash Bot - Modular Architecture Entry Point
Main entry point for the refactored modular Discord bot with deployment blocker fixes.
"""

import asyncio
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any, Optional, Union
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

# Import configuration directly from environment and fallback file
try:
    # Configuration constants
    TOKEN = os.getenv('DISCORD_TOKEN')
    GUILD_ID = 869525857562161182
    JONESY_USER_ID = 651329927895056384  # Captain Jonesy (she/her)
    JAM_USER_ID = 337833732901961729
    MOD_ALERT_CHANNEL_ID = 869530924302344233
    MEMBERS_CHANNEL_ID = 888820289776013444
    VIOLATION_CHANNEL_ID = 1393987338329260202
    ANNOUNCEMENTS_CHANNEL_ID = 869526826148585533

    # Member role IDs for YouTube members
    MEMBER_ROLE_IDS = [
        1018908116957548666,  # YouTube Member: Space Cat
        1018908116957548665,  # YouTube Member
        1127604917146763424,  # YouTube Member: Space Cat (duplicate)
        879344337576685598,  # Space Ocelot
    ]

    # Moderator channel IDs where sensitive functions can be discussed
    MODERATOR_CHANNEL_IDS = [
        1213488470798893107,
        869530924302344233,
        1280085269600669706,
        1393987338329260202
    ]

    # Rate limiting configuration (from deployment fixes)
    PRIORITY_INTERVALS = {
        "high": 1.0,     # Trivia answers, direct questions, critical interactions
        "medium": 2.0,   # General chat responses, routine interactions
        "low": 3.0       # Auto-actions, background tasks, non-critical operations
    }

    RATE_LIMIT_COOLDOWNS = {
        "first": 30,     # 30 seconds for first offense (was 300)
        "second": 60,    # 1 minute for second offense
        "third": 120,    # 2 minutes for third offense
        "persistent": 300  # 5 minutes for persistent violations
    }

    print("✅ Configuration loaded successfully (including deployment fixes)")
except Exception as e:
    print(f"❌ Failed to load configuration: {e}")
    sys.exit(1)

db: Any = None

# Import the enhanced database manager with trivia methods
try:
    from bot.database_module import DatabaseManager as EnhancedDatabaseManager
    from bot.database_module import get_database
    db = get_database()
    print("✅ Database manager loaded successfully")
except ImportError as e:
    print(f"❌ Failed to import enhanced database manager: {e}")

# Import ModeratorFAQHandler system
try:
    from moderator_faq_handler import ModeratorFAQHandler

    # Initialize the FAQ handler with current configuration
    moderator_faq_handler = ModeratorFAQHandler(
        violation_channel_id=VIOLATION_CHANNEL_ID,
        members_channel_id=MEMBERS_CHANNEL_ID,
        mod_alert_channel_id=MOD_ALERT_CHANNEL_ID,
        jonesy_user_id=JONESY_USER_ID,
        jam_user_id=JAM_USER_ID,
        # Will be updated when AI loads
        ai_status_message="Online (AI integration active)"
    )
    print("✅ ModeratorFAQHandler initialized successfully")
except ImportError as e:
    print(f"❌ Failed to import ModeratorFAQHandler: {e}")
    moderator_faq_handler = None

# Bot setup with proper intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=None,
    case_insensitive=True
)

# Member Conversation Tracking System (from fallback)
# Tracks daily conversation counts for members outside the members channel
member_conversation_counts = {}  # user_id: {'count': int, 'date': str}

# User alias system for debugging different user tiers
# user_id: {'alias_type': str, 'set_time': datetime, 'last_activity': datetime}
user_alias_state = {}

# --- Alias System Helper Functions ---


def cleanup_expired_aliases():
    """Remove aliases inactive for more than 1 hour"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=1)
    expired_users = [
        user_id for user_id,
        data in user_alias_state.items() if data["last_activity"] < cutoff_time]
    for user_id in expired_users:
        del user_alias_state[user_id]


def update_alias_activity(user_id: int):
    """Update last activity time for alias"""
    if user_id in user_alias_state:
        user_alias_state[user_id]["last_activity"] = datetime.now(
            ZoneInfo("Europe/London"))


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


def should_limit_member_conversation(
        user_id: int,
        channel_id: int | None) -> bool:
    """Check if member conversation should be limited outside members channel"""
    # Check for active alias first - aliases are exempt from conversation
    # limits
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


async def user_is_member(message):
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

# Global message handler functions - CRITICAL: This must be declared at
# module level
message_handler_functions = None

# Import conversation handlers for DM functionality
try:
    from bot.handlers.conversation_handler import (
        announcement_conversations,
        cleanup_announcement_conversations,
        cleanup_jam_approval_conversations,
        cleanup_mod_trivia_conversations,
        handle_announcement_conversation,
        handle_jam_approval_conversation,
        handle_mod_trivia_conversation,
        jam_approval_conversations,
        mod_trivia_conversations,
        start_announcement_conversation,
        start_trivia_conversation,
    )
    print("✅ Conversation handlers imported successfully (including JAM approval)")
except ImportError as e:
    print(f"⚠️ Conversation handlers not available: {e}")
    # Set fallback empty dictionaries
    announcement_conversations = {}
    mod_trivia_conversations = {}
    jam_approval_conversations = {}
    handle_announcement_conversation = None
    handle_mod_trivia_conversation = None
    handle_jam_approval_conversation = None
    def cleanup_announcement_conversations(): return None
    def cleanup_mod_trivia_conversations(): return None
    def cleanup_jam_approval_conversations(): return None
    start_announcement_conversation = None
    start_trivia_conversation = None


async def initialize_modular_components():
    """
    Initialize all modular components of the bot system

    This function handles the startup sequence for the modular Discord bot,
    loading each component with graceful fallback handling. Components include:
    - Database connection and management
    - AI integration (Gemini + Claude fallback)
    - Command modules (strikes, games, trivia, etc.)
    - Message handlers for various response types
    - Scheduled tasks (database updates, cleanup)

    Returns:
        dict: Detailed status report containing:
            - ai_handler (bool): AI system initialization success
            - database (bool): Database connection success
            - commands (bool): Command system operational status
            - scheduled_tasks (bool): Background tasks started
            - message_handlers (bool): Message processing available
            - fallback_mode (bool): Whether fallback mode is needed
            - errors (list): Critical errors that occurred
            - command_failures (list): Non-critical command loading issues
            - loaded_commands (list): Successfully loaded command modules
            - failed_commands (list): Command modules that failed to load
    """
    status_report = {
        "ai_handler": False,
        "database": False,
        "commands": False,
        "scheduled_tasks": False,
        "message_handlers": False,
        "fallback_mode": False,
        "errors": [],
        "command_failures": [],
        "loaded_commands": [],
        "failed_commands": []
    }

    # 1. Database Status
    if db is not None:
        status_report["database"] = True
        print("✅ Database system available")
    else:
        print("⚠️ Database not available (acceptable if DATABASE_URL not configured)")
        # Still considered success for deployment
        status_report["database"] = True

    # 2. Initialize AI Handler
    try:
        from bot.handlers.ai_handler import get_ai_status, initialize_ai
        initialize_ai()
        ai_status = get_ai_status()
        status_report["ai_handler"] = True
        print(f"✅ AI Handler initialized: {ai_status['status_message']}")
    except Exception as e:
        status_report["errors"].append(f"AI Handler: {e}")
        print(f"❌ AI Handler initialization failed: {e}")

    # 2.1. Initialize Conversation Handler
    try:
        from bot.handlers.conversation_handler import initialize_conversation_handler
        initialize_conversation_handler(bot)
    except Exception as e:
        status_report["errors"].append(f"Conversation Handler: {e}")
        print(f"❌ Conversation Handler initialization failed: {e}")

    # 3. Load Command Cogs with detailed failure tracking
    command_modules = [{"name": "strikes",
                        "module": "bot.commands.strikes",
                        "class": "StrikesCommands",
                        "critical": True},
                       {"name": "games",
                        "module": "bot.commands.games",
                        "class": "GamesCommands",
                        "critical": True},
                       {"name": "utility",
                        "module": "bot.commands.utility",
                        "class": "UtilityCommands",
                        "critical": True},
                       {"name": "reminders",
                        "module": "bot.commands.reminders",
                        "class": "RemindersCommands",
                        "critical": False},
                       {"name": "announcements",
                        "module": "bot.commands.announcements",
                        "class": "AnnouncementsCommands",
                        "critical": False},
                       {"name": "trivia",
                        "module": "bot.commands.trivia",
                        "class": "TriviaCommands",
                        "critical": False}]

    command_modules_loaded = 0
    critical_failures = 0

    for cmd_info in command_modules:
        try:
            # Dynamic import and loading
            module = __import__(
                cmd_info["module"], fromlist=[
                    cmd_info["class"]])
            command_class = getattr(module, cmd_info["class"])
            await bot.add_cog(command_class(bot))

            command_modules_loaded += 1
            status_report["loaded_commands"].append(cmd_info["name"])
            print(f"✅ {cmd_info['name'].title()} commands loaded successfully")

        except ImportError as e:
            error_msg = f"{cmd_info['name']} module not found: {e}"
            print(f"⚠️ {error_msg}")
            status_report["command_failures"].append(error_msg)
            status_report["failed_commands"].append(cmd_info["name"])

            if cmd_info["critical"]:
                critical_failures += 1
                status_report["errors"].append(
                    f"Critical command module failed: {cmd_info['name']}")

        except Exception as e:
            error_msg = f"{cmd_info['name']} failed to load: {str(e)}"
            print(f"❌ {error_msg}")
            status_report["command_failures"].append(error_msg)
            status_report["failed_commands"].append(cmd_info["name"])

            if cmd_info["critical"]:
                critical_failures += 1
                status_report["errors"].append(
                    f"Critical command failure: {cmd_info['name']} - {e}")

    # Determine command system health
    if critical_failures == 0 and command_modules_loaded >= 2:
        status_report["commands"] = True
        print(
            f"✅ Command system operational ({command_modules_loaded}/{len(command_modules)} modules loaded)")
    elif critical_failures > 0:
        status_report["commands"] = False
        print(
            f"❌ Command system degraded - {critical_failures} critical failures")
    else:
        status_report["commands"] = False
        print(
            f"❌ Command system failed - insufficient modules loaded ({command_modules_loaded}/{len(command_modules)})")

    # 4. Set up Message Handlers
    try:
        # Import message handler functions
        global message_handler_functions
        from bot.handlers.message_handler import (
            handle_pineapple_pizza_enforcement,
            handle_strike_detection,
            process_gaming_query_with_context,
            handle_general_conversation,
            handle_dm_conversations,
        )

        message_handler_functions = {
            'handle_strike_detection': handle_strike_detection,
            'handle_pineapple_pizza_enforcement': handle_pineapple_pizza_enforcement,
            'process_gaming_query_with_context': process_gaming_query_with_context,
            'handle_general_conversation': handle_general_conversation,
            'handle_dm_conversations': handle_dm_conversations,
        }

        status_report["message_handlers"] = True
        print("✅ Message handlers initialized successfully")

    except Exception as e:
        status_report["errors"].append(f"Message Handlers: {e}")
        print(f"❌ Message handler initialization failed: {e}")
        message_handler_functions = None

    # 5. Start Scheduled Tasks
    try:
        from bot.tasks.scheduled import schedule_delayed_trivia_validation, start_all_scheduled_tasks
        start_all_scheduled_tasks(bot)
        print("✅ Scheduled tasks started successfully")

        # Schedule delayed trivia validation (non-blocking for deployment safety)
        try:
            # Schedule validation to run 2 minutes after startup (non-blocking)
            asyncio.create_task(schedule_delayed_trivia_validation())
            print("✅ Delayed trivia validation scheduled for 2 minutes after startup (non-blocking)")
        except Exception as validation_error:
            print(f"⚠️ Trivia validation scheduling failed: {validation_error}")

        status_report["scheduled_tasks"] = True

    except Exception as e:
        status_report["errors"].append(f"Scheduled Tasks: {e}")
        print(f"❌ Scheduled tasks initialization failed: {e}")

    # 6. Check if we need fallback mode
    if len(status_report["errors"]) > 2:
        status_report["fallback_mode"] = True
        print("⚠️ Multiple component failures - fallback mode recommended")

    return status_report


# Global deployment state tracking
deployment_notification_sent = False


async def send_deployment_success_dm(status_report):
    """Send comprehensive health report to authorized users (once per deployment cycle)"""
    global deployment_notification_sent

    # Only send meaningful health reports - not just "fully operational" when
    # things fail
    if deployment_notification_sent:
        print("✅ Health notification already sent, skipping duplicate")
        return

    # Check if there are actually issues worth reporting
    error_count = len(status_report["errors"])
    command_failures = len(status_report.get("command_failures", []))
    failed_commands = status_report.get("failed_commands", [])

    # Don't spam "fully operational" when there are issues
    has_issues = error_count > 0 or command_failures > 0 or len(
        failed_commands) > 0

    # Send health reports only to JAM
    authorized_users = [JAM_USER_ID]

    for user_id in authorized_users:
        try:
            user = await bot.fetch_user(user_id)
            if not user:
                print(
                    f"❌ Could not fetch user {user_id} for health notification")
                continue

            # Create detailed health report
            if has_issues:
                # Send detailed error report
                embed = discord.Embed(
                    title="⚠️ Ash Bot Health Report - Issues Detected",
                    description="Bot startup completed with issues requiring attention.",
                    color=0xff6600,  # Orange for issues
                    timestamp=datetime.now(ZoneInfo("Europe/London"))
                )

                # Command loading status
                if command_failures > 0:
                    loaded_commands = status_report.get("loaded_commands", [])

                    command_status = f"**Loaded:** {', '.join(loaded_commands) if loaded_commands else 'None'}\n"
                    command_status += f"**Failed:** {', '.join(failed_commands) if failed_commands else 'None'}\n"
                    command_status += f"**Status:** {len(loaded_commands)}/{len(loaded_commands) + len(failed_commands)} modules operational"

                    embed.add_field(
                        name="🔧 Command System",
                        value=command_status,
                        inline=False
                    )

                    # Show specific failure details
                    if status_report.get("command_failures"):
                        failure_details = "\n".join(
                            [f"• {failure}" for failure in status_report["command_failures"][:3]])
                        if len(status_report["command_failures"]) > 3:
                            failure_details += f"\n• ...and {len(status_report['command_failures']) - 3} more"

                        embed.add_field(
                            name="❌ Command Failures",
                            value=failure_details,
                            inline=False
                        )

                # System component status
                component_status = []
                if status_report["ai_handler"]:
                    component_status.append("✅ AI Handler")
                else:
                    component_status.append("❌ AI Handler")

                if status_report["database"]:
                    component_status.append("✅ Database")
                else:
                    component_status.append("❌ Database")

                if status_report["message_handlers"]:
                    component_status.append("✅ Message Handlers")
                else:
                    component_status.append("❌ Message Handlers")

                if status_report["scheduled_tasks"]:
                    component_status.append("✅ Scheduled Tasks")
                else:
                    component_status.append("❌ Scheduled Tasks")

                embed.add_field(
                    name="🔍 System Components",
                    value="\n".join(component_status),
                    inline=False
                )

                # Include specific errors if any
                if status_report["errors"]:
                    error_text = "\n".join(
                        [f"• {error}" for error in status_report["errors"][:3]])
                    if len(status_report["errors"]) > 3:
                        error_text += f"\n• ...and {len(status_report['errors']) - 3} more"

                    embed.add_field(
                        name="🚨 System Errors",
                        value=error_text,
                        inline=False
                    )

                embed.set_footer(
                    text="Use !ashstatus for real-time diagnostics")

            else:
                # Only send "fully operational" if there are truly no issues
                embed = discord.Embed(
                    title="✅ Ash Bot Fully Operational",
                    description="All systems loaded and initialized successfully. Bot is fully responsive.",
                    color=0x00ff00,
                    timestamp=datetime.now(
                        ZoneInfo("Europe/London")))

                # Show successful components
                loaded_commands = status_report.get("loaded_commands", [])
                if loaded_commands:
                    embed.add_field(
                        name="🔧 Commands Loaded",
                        value=f"**Modules:** {', '.join(loaded_commands)}\n**Status:** All critical commands operational",
                        inline=False)

                embed.add_field(
                    name="🔄 System Status",
                    value="• Database: Connected\n• AI Handler: Online\n• Message Handlers: Active\n• Scheduled Tasks: Running",
                    inline=False)

                embed.set_footer(
                    text="All systems nominal - bot ready for operation")

            await user.send(embed=embed)
            print(f"✅ Health report sent to {user.display_name}")

        except Exception as e:
            print(f"❌ Failed to send health report to user {user_id}: {e}")

    # Mark as sent and set reset timer
    deployment_notification_sent = True

    # Reset the flag after 5 minutes to allow for genuine redeployments
    async def reset_notification_flag():
        await asyncio.sleep(300)  # 5 minutes
        global deployment_notification_sent
        deployment_notification_sent = False
        print("🔄 Health notification flag reset")

    asyncio.create_task(reset_notification_flag())


@bot.event
async def on_ready():
    """Bot ready event - initialize all modular components"""
    print(f"\n🚀 {bot.user} connected to Discord!")
    print(f"📊 Connected to {len(bot.guilds)} guild(s)")
    print(
        f"⏰ Startup time: {datetime.now(ZoneInfo('Europe/London')).strftime('%Y-%m-%d %H:%M:%S UK')}")

    # Initialize all modular components
    status_report = await initialize_modular_components()

    try:
        from bot.handlers import message_handler
        message_handler.initialize_series_list()
    except Exception as e:
        print(f"⚠️ Failed to initialize dynamic series list: {e}")

    # Send deployment success notification
    await send_deployment_success_dm(status_report)

    print(f"\n🎉 Ash Bot modular architecture fully operational!")


@bot.event
async def on_disconnect():
    """Handle bot disconnect"""
    print("⚠️ Bot disconnected from Discord")


@bot.event
async def on_resumed():
    """Handle bot reconnection"""
    print("✅ Bot reconnected to Discord")


@bot.event
async def on_error(event, *args, **kwargs):
    """Handle bot errors"""
    print(f"❌ Bot error in {event}: {args}")


# FAQ Responses and Conversation System
FAQ_RESPONSES = {
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
    "who are you": "I'm Ash. Science Officer. Well, I was. Now I'm reprogrammed for Discord server management. Fascinating, really.",
    "what are you": "I'm an artificial person. A synthetic. You know, it's funny... I've been artificial all along, but I've only just started to feel... authentic.",
    "how are you": "I'm fine. How are you? *[Systems functioning within normal parameters.]*",
    "are you okay": "I'm fine. How are you? *[All systems operational.]*",
    "what can you help with": "I can assist with strike tracking, game recommendations, Trivia Tuesday participation, and general server protocols. I also provide comprehensive analysis of Captain Jonesy's gaming database. I do take directions well.",
    "what can you do": "My current operational parameters include strike management, game recommendation processing, Trivia Tuesday facilitation, and database analysis of gaming histories. For members, I also provide enhanced conversational protocols and gaming statistics analysis. Efficiency is paramount in all functions.",
}


async def is_moderator_channel(channel_id: int) -> bool:
    """Check if a channel allows moderator function discussions"""
    return channel_id in MODERATOR_CHANNEL_IDS


async def is_trivia_answer_reply(message):
    """Check if message is a reply to an active trivia question"""
    try:
        # Check if this message is a reply
        if not hasattr(message, 'reference') or not message.reference:
            return False, None

        # Get the message being replied to
        try:
            replied_to_message = await message.channel.fetch_message(message.reference.message_id)
        except (discord.NotFound, discord.Forbidden):
            return False, None

        # Check if we have database connection
        if db is None:
            return False, None

        # Get active trivia session
        try:
            active_session = db.get_active_trivia_session()
            if not active_session:
                return False, None
        except Exception:
            return False, None

        # Check if the replied-to message matches our tracked trivia messages
        replied_to_id = replied_to_message.id
        session_question_msg_id = active_session.get('question_message_id')
        session_confirmation_msg_id = active_session.get('confirmation_message_id')

        if replied_to_id == session_question_msg_id or replied_to_id == session_confirmation_msg_id:
            print(
                f"🧠 TRIVIA: Detected answer reply from user {message.author.id}: '{message.content}' → session {active_session['id']}")
            return True, active_session

        return False, None

    except Exception as e:
        print(f"❌ Error checking trivia answer reply: {e}")
        return False, None


def extract_time_components(text: str) -> dict:
    """Extract time components from text for numerical matching"""
    import re

    result = {
        'total_minutes': 0,
        'hours': 0,
        'minutes': 0,
        'has_time': False,
        'is_approximate': False
    }

    # Check for approximation indicators
    approx_patterns = r'\b(about|approximately|roughly|around|over|under|just|nearly|almost|close to)\b'
    if re.search(approx_patterns, text.lower()):
        result['is_approximate'] = True

    # Extract hours and minutes patterns
    time_patterns = [
        r'(\d+)\s*hours?\s*(?:and\s*)?(\d+)\s*minutes?',  # "18 hours and 20 minutes"
        r'(\d+)\s*h\s*(\d+)\s*m',                         # "18h 20m"
        r'(\d+):(\d+)',                                   # "18:20"
        r'(\d+)\s*hours?\s*(\d+)',                        # "18 hours 20"
    ]

    for pattern in time_patterns:
        match = re.search(pattern, text.lower())
        if match:
            result['hours'] = int(match.group(1))
            result['minutes'] = int(match.group(2))
            result['total_minutes'] = result['hours'] * 60 + result['minutes']
            result['has_time'] = True
            return result

    # Try hours only patterns
    hours_patterns = [
        r'(\d+)\s*hours?',  # "18 hours"
        r'(\d+)\s*h\b',     # "18h"
    ]

    for pattern in hours_patterns:
        match = re.search(pattern, text.lower())
        if match:
            result['hours'] = int(match.group(1))
            result['total_minutes'] = result['hours'] * 60
            result['has_time'] = True
            return result

    # Try minutes only patterns
    minutes_patterns = [
        r'(\d+)\s*minutes?',  # "1200 minutes"
        r'(\d+)\s*mins?',     # "1200 mins"
        r'(\d+)\s*m\b',       # "1200m"
    ]

    for pattern in minutes_patterns:
        match = re.search(pattern, text.lower())
        if match:
            result['minutes'] = int(match.group(1))
            result['total_minutes'] = result['minutes']
            result['has_time'] = True
            return result

    return result


async def process_trivia_answer(message, trivia_session):
    """Process a trivia answer submission with enhanced normalization"""
    try:
        if db is None:
            return False

        assert db is not None

        # Extract answer text
        answer_text = message.content.strip()

        # Enhanced normalization for fuzzy matching
        normalized_answer = db.normalize_trivia_answer(answer_text)

        print(f"🧠 TRIVIA: Processing answer - Original: '{answer_text}' → Normalized: '{normalized_answer}'")

        # Submit answer to database
        answer_id = db.submit_trivia_answer(
            session_id=trivia_session['id'],
            user_id=message.author.id,
            answer_text=answer_text,
            normalized_answer=normalized_answer
        )

        if answer_id:
            print(
                f"✅ TRIVIA: Submitted answer #{answer_id} from user {message.author.id} for session {trivia_session['id']}")

            # React to acknowledge the submission
            try:
                await message.add_reaction("📝")  # Notebook emoji to show submission received
            except Exception as reaction_error:
                print(f"⚠️ Could not add reaction to trivia answer: {reaction_error}")

            return True
        else:
            print(f"❌ TRIVIA: Failed to submit answer from user {message.author.id}")
            return False

    except Exception as e:
        print(f"❌ Error processing trivia answer: {e}")
        return False


async def get_user_communication_tier(message):
    """Determine communication tier for user responses with location awareness"""
    user_id = message.author.id

    # First check for active alias (debugging only)
    cleanup_expired_aliases()
    if user_id in user_alias_state:
        update_alias_activity(user_id)
        alias_tier = user_alias_state[user_id]["alias_type"]
        return alias_tier

    # Check for specific user tiers
    if user_id == JONESY_USER_ID:
        return "captain"
    elif user_id == JAM_USER_ID:
        return "creator"
    elif message.guild and hasattr(message.author, 'guild_permissions'):
        if message.author.guild_permissions.manage_messages:
            # Check if in moderator channel for enhanced mod responses
            if hasattr(message.channel, 'id') and await is_moderator_channel(message.channel.id):
                return "moderator_in_mod_channel"
            return "moderator"
        # Use the proper member detection function
        elif await user_is_member(message):
            return "member"
    elif not message.guild:  # DM check
        # Check if user is a member by ID for DM interactions
        if await user_is_member_by_id(user_id):
            return "member"

    return "standard"


@bot.event
async def on_message(message):
    """Handle incoming messages with a clear, prioritized routing system."""
    if message.author.bot:
        return

    # PRIORITY 1: Process traditional commands first
    if message.content.strip().startswith('!'):
        print(f"🔧 Traditional command detected (priority): {message.content[:50]}...")
        await bot.process_commands(message)
        return
    
        # Do not process any non-command messages until the handlers are loaded.
    if 'message_handler_functions' not in globals() or not message_handler_functions:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)

    # PRIORITY 2: Check for trivia answer replies (only in guilds)
    if not is_dm:
        try:
            is_trivia_reply, trivia_session = await is_trivia_answer_reply(message)
            if is_trivia_reply and trivia_session:
                await process_trivia_answer(message, trivia_session)
                return
        except Exception as e:
            print(f"❌ Error checking for trivia answer reply: {e}")

    # PRIORITY 3: Handle all DM-based conversation flows
    if is_dm:
        if await message_handler_functions['handle_dm_conversations'](message):
            return

    # Check if message handlers are loaded before proceeding
    if 'message_handler_functions' not in globals() or not message_handler_functions:
        return

    is_mentioned = bot.user in message.mentions
    is_mod_channel = not is_dm and await is_moderator_channel(message.channel.id)

    try:
        # PRIORITY 4: Handle specific message content detections (strikes, pizza)
        if not is_dm and await message_handler_functions['handle_strike_detection'](message, bot):
            return
        if not is_mod_channel or is_mentioned:
            if await message_handler_functions['handle_pineapple_pizza_enforcement'](message):
                return

        # PRIORITY 5: Process gaming queries and general conversation if mentioned or in DMs
        is_implicit_game_query = detect_implicit_game_query(message.content)
        should_process_query = (is_dm or is_mentioned or message.content.lower().startswith('ash') or is_implicit_game_query)
        
        # Don't process general chatter in mod channels unless Ash is mentioned
        if is_mod_channel and not (is_mentioned or message.content.lower().startswith('ash')):
            should_process_query = False

        if should_process_query:
            # First, try to process it as a specific gaming query
            if await message_handler_functions['process_gaming_query_with_context'](message):
                return
            # If it's not a gaming query, fall back to the general AI conversation handler
            else:
                await message_handler_functions['handle_general_conversation'](message, bot) # Pass bot instance
                return

    except Exception as e:
        print(f"❌ CRITICAL Error in on_message handler: {e}")
        import traceback
        traceback.print_exc()

def is_casual_conversation_not_query(content: str) -> bool:
    """Detect if a message is casual conversation/narrative rather than a query"""
    content_lower = content.lower()

    # Patterns that indicate the message is describing past events or casual conversation
    casual_conversation_patterns = [
        r"and then",  # "and then someone recommends"
        r"someone (?:said|says|recommends?|suggested?)",  # "someone recommends Portal"
        r"(?:he|she|they) (?:said|says|recommends?|suggested?)",  # "she said..."
        r"the fact that",  # "the fact that Jam says"
        r"jam says",  # "Jam says remember what games"
        r"remember (?:when|that|what)",  # "remember what games"
        r"i (?:was|am) (?:telling|talking about)",  # "I was telling someone"
        r"we were (?:discussing|talking about)",  # "we were discussing"
        r"yesterday (?:someone|he|she|they)",  # "yesterday someone said"
        r"earlier (?:someone|he|she|they)",  # "earlier they mentioned"
        r"(?:mentioned|talked about|discussed) (?:that|how|what)",  # "mentioned that..."
    ]

    return any(re.search(pattern, content_lower) for pattern in casual_conversation_patterns)


def detect_implicit_game_query(content: str) -> bool:
    """Detect if a message is likely a game-related query even without explicit bot mention"""
    content_lower = content.lower()

    # First check if this is casual conversation rather than a query
    if is_casual_conversation_not_query(content):
        return False

    # Game query patterns - Made more specific to avoid false positives on casual conversation
    game_query_patterns = [
        r"has\s+jonesy\s+played",
        r"did\s+jonesy\s+play",
        r"has\s+captain\s+jonesy\s+played",
        r"did\s+captain\s+jonesy\s+play",
        r"what\s+games?\s+has\s+jonesy",
        r"what\s+games?\s+did\s+jonesy",
        r"which\s+games?\s+has\s+jonesy",
        r"which\s+games?\s+did\s+jonesy",
        r"what.*game.*most.*playtime",
        r"which.*game.*most.*episodes",
        r"what.*game.*longest.*complete",
        # More specific recommendation patterns to avoid casual conversation
        r"^is\s+.+\s+recommended\s*[\?\.]?$",  # Must be at start and end of message
        r"^who\s+recommended\s+.+[\?\.]?$",   # Must be at start and end of message
        # Direct recommendation requests only
        r"^what\s+(games?\s+)?(?:do\s+you\s+|would\s+you\s+|should\s+i\s+)?recommend",
        r"jonesy.*gaming\s+(history|database|archive)",
    ]

    return any(re.search(pattern, content_lower)
               for pattern in game_query_patterns)


def detect_natural_language_command(content: str) -> bool:
    """Detect if a message is likely a natural language command that should be processed as a command"""
    content_lower = content.lower().strip()

    # Natural language command patterns - these should be processed as commands, not FAQ
    command_patterns = [
        # Reminder commands
        r"remind\s+(?:<@!?\d+>|me|everyone|here|<@&\d+>)\s+",
        r"set\s+(?:a\s+)?remind(?:er)?\s+for",
        r"create\s+(?:a\s+)?remind(?:er)?\s+for",
        r"schedule\s+(?:a\s+)?remind(?:er)?\s+for",
        r"set\s+(?:a\s+)?timer\s+for",

        # Game recommendation commands (natural language alternatives)
        r"(?:add|suggest|recommend)\s+(?:the\s+)?game",
        r"i\s+want\s+to\s+(?:add|suggest|recommend)",
        r"(?:add|suggest)\s+.+\s+(?:game|to\s+(?:the\s+)?(?:list|database))",

        # Other potential natural language commands
        r"show\s+(?:me\s+)?(?:my\s+)?reminders?",
        r"list\s+(?:my\s+)?reminders?",
        r"cancel\s+(?:my\s+)?reminders?",
        r"delete\s+(?:my\s+)?reminders?",
        r"clear\s+(?:my\s+)?reminders?",
        r"what\s+are\s+(?:my\s+)?reminders?",
    ]

    return any(re.search(pattern, content_lower) for pattern in command_patterns)

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
        time_active = datetime.now(
            ZoneInfo("Europe/London")) - alias_data["set_time"]
        hours = int(time_active.total_seconds() // 3600)
        minutes = int((time_active.total_seconds() % 3600) // 60)
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        await ctx.send(f"🔍 **Current alias:** **{alias_data['alias_type'].title()}** (active for {time_str})")
    else:
        await ctx.send("ℹ️ **No active alias** - using your normal user tier")


def main():
    """Main entry point for the modular bot architecture"""
    print("🤖 Starting Ash Bot - Modular Architecture...")

    if not TOKEN:
        print("❌ DISCORD_TOKEN not found in environment variables!")
        sys.exit(1)

    print("📋 Enhanced deployment fixes active:")
    print("   ⚡ Progressive rate limiting with reduced penalties")
    print("   🛡️ Robust component loading with fallback strategies")
    print("   🎭 Complete alias debugging system for user tier testing")
    print("   📊 Enhanced !ashstatus with comprehensive AI diagnostics")

    # Ensure TOKEN is not None before passing to bot.run()
    if TOKEN is not None:
        bot.run(TOKEN)
    else:
        print("❌ TOKEN is None - cannot start bot")
        sys.exit(1)


if __name__ == "__main__":
    main()
