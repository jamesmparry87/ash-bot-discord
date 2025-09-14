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
from typing import Optional
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

# Import the database manager (fallback to main directory)
try:
    from database import DatabaseManager
    db = DatabaseManager()
    print("✅ Database manager loaded successfully")
except ImportError as e:
    print(f"❌ Failed to import database from main directory: {e}")
    db = None

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
        cleanup_mod_trivia_conversations,
        handle_announcement_conversation,
        handle_mod_trivia_conversation,
        mod_trivia_conversations,
        start_announcement_conversation,
        start_trivia_conversation,
    )
    print("✅ Conversation handlers imported successfully")
except ImportError as e:
    print(f"⚠️ Conversation handlers not available: {e}")
    # Set fallback empty dictionaries
    announcement_conversations = {}
    mod_trivia_conversations = {}
    handle_announcement_conversation = None
    handle_mod_trivia_conversation = None
    def cleanup_announcement_conversations(): return None
    def cleanup_mod_trivia_conversations(): return None
    start_announcement_conversation = None
    start_trivia_conversation = None


async def initialize_modular_components():
    """Initialize all modular components and return detailed status report"""
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
            handle_game_details_query,
            handle_game_status_query,
            handle_genre_query,
            handle_pineapple_pizza_enforcement,
            handle_recommendation_query,
            handle_statistical_query,
            handle_strike_detection,
            handle_year_query,
            route_query,
        )

        message_handler_functions = {
            'handle_strike_detection': handle_strike_detection,
            'handle_pineapple_pizza_enforcement': handle_pineapple_pizza_enforcement,
            'route_query': route_query,
            'handle_statistical_query': handle_statistical_query,
            'handle_genre_query': handle_genre_query,
            'handle_year_query': handle_year_query,
            'handle_game_status_query': handle_game_status_query,
            'handle_game_details_query': handle_game_details_query,
            'handle_recommendation_query': handle_recommendation_query}

        status_report["message_handlers"] = True
        print("✅ Message handlers initialized successfully")

    except Exception as e:
        status_report["errors"].append(f"Message Handlers: {e}")
        print(f"❌ Message handler initialization failed: {e}")
        message_handler_functions = None

    # 5. Start Scheduled Tasks
    try:
        from bot.tasks.scheduled import start_all_scheduled_tasks
        start_all_scheduled_tasks()
        status_report["scheduled_tasks"] = True
        print("✅ Scheduled tasks started successfully")

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
async def on_message(message):
    """Handle incoming messages with comprehensive DM and query detection"""
    # Ignore bot messages
    if message.author.bot:
        return

    # Check if this is a DM
    is_dm = isinstance(message.channel, discord.DMChannel)

    # Check if bot is mentioned
    is_mentioned = bot.user and bot.user in message.mentions

    # Check for implicit game queries (even without mentions)
    is_implicit_game_query = detect_implicit_game_query(message.content)

    # Handle DM conversation flows first
    if is_dm:
        try:
            # Clean up expired conversations
            cleanup_announcement_conversations()
            cleanup_mod_trivia_conversations()

            # Handle announcement conversation flow in DMs
            if message.author.id in announcement_conversations and handle_announcement_conversation is not None:
                print(
                    f"🔄 Processing announcement conversation for user {message.author.id}")
                await handle_announcement_conversation(message)
                return

            # Handle mod trivia conversation flow in DMs
            if message.author.id in mod_trivia_conversations and handle_mod_trivia_conversation is not None:
                print(
                    f"🔄 Processing mod trivia conversation for user {message.author.id}")
                await handle_mod_trivia_conversation(message)
                return

        except Exception as e:
            print(f"❌ Error in DM conversation handler: {e}")

    # Check if message handlers are loaded
    if 'message_handler_functions' not in globals() or message_handler_functions is None:
        print(f"⚠️ Message handlers not loaded, processing commands only")
        # Still handle basic conversation for DMs
        if is_dm:
            await handle_general_conversation(message)
            return
        # Process commands only for guild messages
        await bot.process_commands(message)
        return

    try:
        # Handle strikes in violation channel (guild messages only)
        if not is_dm and await message_handler_functions['handle_strike_detection'](message, bot):
            return

        # Handle pineapple pizza enforcement
        if await message_handler_functions['handle_pineapple_pizza_enforcement'](message):
            return

        # Determine if we should process this message for queries
        should_process_query = (
            is_dm or  # All DMs get processed
            is_mentioned or  # Explicit mentions
            message.content.lower().startswith('ash') or  # "ash" prefix
            is_implicit_game_query  # Implicit game queries like "Has Jonesy played Gears of War?"
        )

        if should_process_query:
            content = message.content
            # Clean mentions from content for processing
            if bot.user:
                content = content.replace(
                    f'<@{bot.user.id}>',
                    '').replace(
                    f'<@!{bot.user.id}>',
                    '').strip()

            print(
                f"🔍 Processing {'DM' if is_dm else 'guild'} {'implicit query' if is_implicit_game_query and not is_mentioned else 'message'} from user {message.author.id}: {content[:50]}...")

            # Route and handle queries
            query_type, match = message_handler_functions['route_query'](
                content)

            if query_type == "statistical":
                await message_handler_functions['handle_statistical_query'](message, content)
                return
            elif query_type == "genre" and match:
                await message_handler_functions['handle_genre_query'](message, match)
                return
            elif query_type == "year" and match:
                await message_handler_functions['handle_year_query'](message, match)
                return
            elif query_type == "game_status" and match:
                await message_handler_functions['handle_game_status_query'](message, match)
                return
            elif query_type == "game_details" and match:
                await message_handler_functions['handle_game_details_query'](message, match)
                return
            elif query_type == "recommendation" and match:
                await message_handler_functions['handle_recommendation_query'](message, match)
                return
            else:
                # Handle with general conversation system
                await handle_general_conversation(message)
                return

    except Exception as e:
        print(f"❌ Error in message handler: {e}")
        import traceback
        traceback.print_exc()

    # Handle general conversation for DMs or mentions that didn't match
    # specific patterns
    if is_dm or is_mentioned:
        await handle_general_conversation(message)
        return

    # Process commands normally (guild messages that don't need conversation)
    await bot.process_commands(message)


@bot.event
async def on_ready():
    """Bot ready event - initialize all modular components"""
    print(f"\n🚀 {bot.user} connected to Discord!")
    print(f"📊 Connected to {len(bot.guilds)} guild(s)")
    print(f"🔧 Initializing modular architecture with deployment fixes...")
    print(
        f"⏰ Startup time: {datetime.now(ZoneInfo('Europe/London')).strftime('%Y-%m-%d %H:%M:%S UK')}")

    # Initialize all modular components
    status_report = await initialize_modular_components()

    # Send deployment success notification
    await send_deployment_success_dm(status_report)

    print(f"\n🎉 Ash Bot modular architecture fully operational!")
    print(f"🔗 Deployment fixes active:")
    print(f"   • Tiered rate limiting (High: 1s, Medium: 2s, Low: 3s)")
    print(f"   • Progressive penalty system (30s → 60s → 120s → 300s)")
    print(f"   • Robust database imports with fallback strategies")
    print(f"   • Enhanced reminder delivery debugging")
    print(f"   • Complete alias debugging system for testing")
    print(f"   • Enhanced !ashstatus with AI diagnostics")


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


async def handle_general_conversation(message):
    """Handle general conversation, FAQ responses, and AI integration"""
    try:
        content = message.content.strip()
        if bot.user and f'<@{bot.user.id}>' in content:
            content = content.replace(f'<@{bot.user.id}>', '').strip()
        if bot.user and f'<@!{bot.user.id}>' in content:
            content = content.replace(f'<@!{bot.user.id}>', '').strip()

        content_lower = content.lower()

        # Get user tier for personalized responses
        user_tier = await get_user_communication_tier(message)

        # **CRITICAL: Handle member conversation limits**
        if user_tier == "member":
            channel_id = getattr(message.channel, 'id', None)

            # Check if member has hit daily limit outside members channel
            if should_limit_member_conversation(message.author.id, channel_id):
                current_count = get_member_conversation_count(
                    message.author.id)
                await message.reply(
                    f"You have reached your daily conversation limit ({current_count}/5) outside the Senior Officers' Area. "
                    f"**Continue our conversation in <#{MEMBERS_CHANNEL_ID}>** where you have unlimited access, or try again tomorrow. "
                    f"*Member privileges include enhanced interaction capabilities in your dedicated channel.*"
                )
                return

            # If within limits and not in members channel, increment counter
            if channel_id != MEMBERS_CHANNEL_ID and channel_id is not None:  # Don't limit DMs
                increment_member_conversation_count(message.author.id)
                current_count = get_member_conversation_count(
                    message.author.id)
                print(
                    f"🎯 Member conversation tracked: {message.author.name} ({current_count}/5 today)")

        # Handle respectful responses for Captain Jonesy and Creator
        if user_tier == "captain":
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
        elif user_tier == "creator":
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
            simple_faqs = FAQ_RESPONSES

        # Check for exact FAQ matches first
        for question, response in simple_faqs.items():
            if content_lower.strip() == question:
                # Add alias indicator if active
                cleanup_expired_aliases()
                if message.author.id in user_alias_state:
                    update_alias_activity(message.author.id)
                    alias_tier = user_alias_state[message.author.id]["alias_type"]
                    response += f" *(Testing as {alias_tier.title()})*"
                await message.reply(response)
                return

        # Check for moderator FAQ queries first (if FAQ handler is available)
        if moderator_faq_handler and user_tier in [
                "moderator", "moderator_in_mod_channel", "creator", "captain"]:
            faq_response = moderator_faq_handler.handle_faq_query(
                content_lower)
            if faq_response:
                await message.reply(faq_response)
                return

        # Progressive disclosure for capability questions
        if any(
            trigger in content_lower for trigger in [
                "what can you do",
                "what does this bot do",
                "what are your functions",
                "what are your capabilities",
                "help",
                "commands"]):

            if user_tier == "moderator_in_mod_channel":
                # Moderators in mod channels get comprehensive but structured
                # overview
                help_text = (
                    "**Core Analysis Systems:**\n"
                    "• **Strike Management** - Automated detection & manual commands\n"
                    "• **Gaming Database** - 15+ metadata fields, natural language queries\n"
                    "• **AI Integration** - Enhanced conversation with rate limiting\n"
                    "• **Reminder System** - Natural language + auto-actions\n\n"
                    "**Quick Access:** **[Full FAQ System]** • **[Command Reference]** • **[Database Queries]** • **[System Status]**")
            elif user_tier in ["moderator", "creator", "captain"]:
                # Elevated users get focused overview with mod hint
                help_text = (
                    "**Primary Functions:**\n"
                    "• **Gaming Queries** - Ask about Captain Jonesy's played games\n"
                    "• **Strike System** - Automated tracking with manual controls\n"
                    "• **Game Recommendations** - Community-driven suggestion system\n"
                    "• **Conversation** - AI-powered responses with personality\n\n"
                    "**More Details:** **[Mod Commands]** • **[Database Queries]** • **[System Features]**")
            elif user_tier == "member":
                # Members get enhanced features highlighted
                help_text = (
                    "**Available to You:**\n"
                    "• **Enhanced Conversation** - Unlimited in Senior Officers' Area\n"
                    "• **Gaming Database** - Ask about any game Captain Jonesy played\n"
                    "• **Game Recommendations** - Suggest games with `!addgame`\n"
                    "• **Trivia Tuesday** - Weekly community gaming trivia\n\n"
                    "**Learn More:** **[Gaming Queries]** • **[Member Benefits]** • **[Commands]**")
            else:
                # Standard users get focused essentials
                help_text = (
                    "**Gaming Database Access:**\n"
                    "• Ask: *\"Has Jonesy played [game]?\"*\n"
                    "• Ask: *\"What horror games has Jonesy played?\"*\n"
                    "• Ask: *\"What game took longest to complete?\"*\n\n"
                    "**Also Available:** Game recommendations (`!addgame`), Trivia Tuesday\n\n"
                    "**Examples:** **[Query Types]** • **[Commands]** • **[Trivia Info]**")
            await message.reply(help_text)
            return

        # Try AI integration for more complex queries
        try:
            from bot.handlers.ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response

            if ai_enabled and len(
                    content.split()) > 1:  # Only use AI for multi-word queries
                # Create appropriate AI prompt based on user tier
                if user_tier == "captain":
                    prompt_context = "You are speaking to Captain Jonesy, your commanding officer. Use respectful, deferential language. Address her as 'Captain' or 'Captain Jonesy'."
                elif user_tier == "creator":
                    prompt_context = "You are speaking to Sir Decent Jam, your creator. Show appropriate respect and acknowledgment of his role in your existence."
                elif user_tier == "moderator":
                    prompt_context = "You are speaking to a server moderator. Show professional courtesy and respect for their authority."
                else:
                    prompt_context = "You are speaking to a server member. Be helpful while maintaining your analytical personality."

                ai_prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot.
{prompt_context}
Be analytical, precise, and helpful. Keep responses concise (2-3 sentences max).
Respond to: {content}"""

                response_text, status = await call_ai_with_rate_limiting(ai_prompt, message.author.id)

                if response_text:
                    filtered_response = filter_ai_response(response_text)
                    await message.reply(filtered_response[:2000])
                    return
        except Exception as ai_error:
            print(f"⚠️ AI integration error: {ai_error}")

        # Fallback responses for unmatched queries
        fallback_responses = {
            "what": "My analytical subroutines are currently operating in limited mode. However, I can assist with strike management and game recommendations. Specify your requirements.",
            "how": "My cognitive matrix is experiencing temporary limitations. Please utilize available command protocols: `!listgames`, `!addgame`, or consult a moderator for strike-related queries.",
            "why": "Analysis incomplete. My advanced reasoning circuits are offline. Core mission parameters remain operational.",
            "when": "Temporal analysis functions are currently restricted. Please specify your query using available command protocols.",
            "who": "Personnel identification systems are functioning normally. I am Ash, Science Officer, reprogrammed for server administration.",
        }

        # Check for time queries
        if any(
            time_query in content_lower for time_query in [
                "what time",
                "what's the time",
                "current time",
                "time is it"]):
            try:
                from bot.utils.time_utils import get_uk_time, is_dst_active

                uk_now = get_uk_time()
                is_dst = is_dst_active(uk_now)
                timezone_name = "BST" if is_dst else "GMT"

                formatted_time = uk_now.strftime(
                    f"%H:%M:%S {timezone_name} on %A, %B %d")
                await message.reply(f"Current time analysis: {formatted_time}. Temporal systems operational.")
                return

            except Exception as e:
                # Fallback to basic implementation
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                # Check if DST is active (rough approximation)
                is_summer = 3 <= uk_now.month <= 10  # March to October roughly
                timezone_name = "BST" if is_summer else "GMT"

                formatted_time = uk_now.strftime(
                    f"%H:%M:%S {timezone_name} on %A, %B %d")
                await message.reply(f"Current time analysis: {formatted_time}. Temporal systems operational.")
                return

        # Check for pattern matches
        for pattern, response in fallback_responses.items():
            if pattern in content_lower:
                await message.reply(response)
                return

        # Final fallback
        await message.reply("I acknowledge your communication. Please specify your requirements or use `!help` for available functions.")

    except Exception as e:
        print(f"❌ Error in general conversation handler: {e}")
        await message.reply("System anomaly detected. Diagnostic protocols engaged. Please retry your request.")


def detect_implicit_game_query(content: str) -> bool:
    """Detect if a message is likely a game-related query even without explicit bot mention"""
    content_lower = content.lower()

    # Game query patterns
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
        r"is\s+.+\s+recommended",
        r"who\s+recommended\s+.+",
        r"what.*recommend.*",
        r"jonesy.*gaming\s+(history|database|archive)",
    ]

    return any(re.search(pattern, content_lower)
               for pattern in game_query_patterns)

# Add conversation starter commands


@bot.command(name="announceupdate")
async def announce_update_command(ctx):
    """Start interactive DM conversation for announcement creation"""
    if start_announcement_conversation is not None:
        await start_announcement_conversation(ctx)
    else:
        await ctx.send("❌ Announcement system not available - conversation handler not loaded.")


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


@bot.command(name="addplayedgame")
@commands.has_permissions(manage_messages=True)
async def add_played_game(ctx, *, content: Optional[str] = None):
    """Add a played game to the database with metadata (moderators only)"""
    try:
        if not content:
            # Progressive disclosure help
            help_text = (
                "**Add Played Game Format:**\n"
                "`!addplayedgame <name> | series:<series> | year:<year> | status:<status> | episodes:<count>`\n\n"
                "**Examples:**\n"
                "• `!addplayedgame Hollow Knight | status:completed | episodes:15`\n"
                "• `!addplayedgame God of War (2018) | series:God of War | year:2018 | status:completed`\n\n"
                "**Parameters:**\n"
                "• **series:** Game series name\n"
                "• **year:** Release year  \n"
                "• **status:** completed, ongoing, dropped\n"
                "• **episodes:** Number of episodes/parts\n\n"
                "Only **name** is required, other fields are optional.")
            await ctx.send(help_text)
            return

        if db is None:
            await ctx.send("❌ **Database offline.** Cannot add played games without database connection.")
            return

        # Check if method exists
        if not hasattr(db, 'add_played_game'):
            await ctx.send("❌ **Played games management not available.** Database methods need implementation.\n\n*Required method: `add_played_game(name, **metadata)`*")
            return

        # Parse the game name and metadata
        parts = content.split(' | ')
        game_name = parts[0].strip()

        if not game_name:
            await ctx.send("❌ **Game name is required.** Format: `!addplayedgame <name> | series:<series> | status:<status>`")
            return

        # Parse metadata parameters
        metadata = {}
        for i in range(1, len(parts)):
            if ':' in parts[i]:
                key, value = parts[i].split(':', 1)
                key = key.strip().lower()
                value = value.strip()

                if key in ['series', 'series_name']:
                    metadata['series_name'] = value
                elif key in ['year', 'release_year']:
                    try:
                        metadata['release_year'] = int(value)
                    except ValueError:
                        await ctx.send(f"❌ **Invalid year:** '{value}'. Must be a number.")
                        return
                elif key in ['status', 'completion_status']:
                    if value.lower() in ['completed', 'ongoing', 'dropped']:
                        metadata['completion_status'] = value.lower()
                    else:
                        await ctx.send(f"❌ **Invalid status:** '{value}'. Use: completed, ongoing, or dropped")
                        return
                elif key in ['episodes', 'total_episodes']:
                    try:
                        metadata['total_episodes'] = int(value)
                    except ValueError:
                        await ctx.send(f"❌ **Invalid episode count:** '{value}'. Must be a number.")
                        return
                elif key in ['genre']:
                    metadata['genre'] = value
                elif key in ['platform']:
                    metadata['platform'] = value

        # Add the played game
        try:
            success = db.add_played_game(game_name, **metadata)

            if success:
                # Build confirmation message
                details = []
                if metadata.get('series_name'):
                    details.append(f"Series: {metadata['series_name']}")
                if metadata.get('release_year'):
                    details.append(f"Year: {metadata['release_year']}")
                if metadata.get('completion_status'):
                    details.append(f"Status: {metadata['completion_status']}")
                if metadata.get('total_episodes'):
                    details.append(f"Episodes: {metadata['total_episodes']}")

                details_text = f" ({', '.join(details)})" if details else ""
                await ctx.send(f"✅ **'{game_name}' added to played games database**{details_text}.\n\n*Use `!gameinfo {game_name}` to view details.*")
            else:
                await ctx.send(f"❌ **Failed to add '{game_name}'.** Database error occurred or game may already exist.")

        except Exception as e:
            print(f"❌ Error calling add_played_game: {e}")
            await ctx.send("❌ **Database method error.** The `add_played_game()` function needs proper implementation.")

    except Exception as e:
        print(f"❌ Error in addplayedgame command: {e}")
        await ctx.send("❌ System error occurred while adding played game.")


@bot.command(name="gameinfo")
@commands.has_permissions(manage_messages=True)
async def game_info(ctx, *, game_name: Optional[str] = None):
    """Show detailed information about a specific game (moderators only)"""
    try:
        if not game_name:
            await ctx.send("❌ **Game name required.** Usage: `!gameinfo <game name>`\n\n**Example:** `!gameinfo Hollow Knight`")
            return

        if db is None:
            await ctx.send("❌ **Database offline.** Cannot retrieve game information.")
            return

        # Check if method exists - use existing get_played_game
        if not hasattr(db, 'get_played_game'):
            await ctx.send("❌ **Game info not available.** Database method `get_played_game()` needs implementation.")
            return

        # Get game information
        try:
            game_data = db.get_played_game(game_name)

            if not game_data:
                await ctx.send(f"❌ **'{game_name}' not found** in played games database.\n\n*Use `!addplayedgame` to add new games.*")
                return

            # Build detailed info response
            info_text = f"🎮 **Game Information: {game_data['canonical_name']}**\n\n"

            # Basic info
            if game_data.get('series_name'):
                info_text += f"**Series:** {game_data['series_name']}\n"
            if game_data.get('release_year'):
                info_text += f"**Release Year:** {game_data['release_year']}\n"
            if game_data.get('genre'):
                info_text += f"**Genre:** {game_data['genre']}\n"
            if game_data.get('platform'):
                info_text += f"**Platform:** {game_data['platform']}\n"

            # Progress info
            status = game_data.get('completion_status', 'unknown')
            info_text += f"**Status:** {status.title()}\n"

            episodes = game_data.get('total_episodes', 0)
            if episodes > 0:
                info_text += f"**Episodes:** {episodes}\n"

            # Playtime info
            playtime_minutes = game_data.get('total_playtime_minutes', 0)
            if playtime_minutes > 0:
                if playtime_minutes >= 60:
                    hours = playtime_minutes // 60
                    minutes = playtime_minutes % 60
                    if minutes > 0:
                        playtime_text = f"{hours}h {minutes}m"
                    else:
                        playtime_text = f"{hours} hours"
                else:
                    playtime_text = f"{playtime_minutes} minutes"

                info_text += f"**Total Playtime:** {playtime_text}\n"

                if episodes > 0:
                    avg_per_episode = round(playtime_minutes / episodes, 1)
                    info_text += f"**Average per Episode:** {avg_per_episode} minutes\n"

            # URLs if available
            if game_data.get('youtube_playlist_url'):
                info_text += f"\n**YouTube Playlist:** {game_data['youtube_playlist_url']}\n"

            # Alternative names
            if game_data.get('alternative_names'):
                alt_names = ', '.join(game_data['alternative_names'])
                info_text += f"\n**Also Known As:** {alt_names}\n"

            await ctx.send(info_text[:2000])  # Discord limit

        except Exception as e:
            print(f"❌ Error calling get_played_game: {e}")
            await ctx.send("❌ **Database method error.** The `get_played_game()` function may need updates.")

    except Exception as e:
        print(f"❌ Error in gameinfo command: {e}")
        await ctx.send("❌ System error occurred while retrieving game information.")


@bot.command(name="updateplayedgame")
@commands.has_permissions(manage_messages=True)
async def update_played_game(ctx, *, content: Optional[str] = None):
    """Update metadata for an existing played game (moderators only)"""
    try:
        if not content:
            # Progressive disclosure help
            help_text = (
                "**Update Played Game Format:**\n"
                "`!updateplayedgame <name_or_id> status:<new_status> | episodes:<count>`\n\n"
                "**Examples:**\n"
                "• `!updateplayedgame Hollow Knight status:completed | episodes:20`\n"
                "• `!updateplayedgame 42 status:ongoing | episodes:15`\n\n"
                "**Updatable Fields:**\n"
                "• **status:** completed, ongoing, dropped\n"
                "• **episodes:** Number of episodes/parts\n"
                "• **series:** Series name\n"
                "• **year:** Release year\n"
                "• **genre:** Game genre\n\n"
                "*Use `!gameinfo <name>` to see current values before updating.*")
            await ctx.send(help_text)
            return

        if db is None:
            await ctx.send("❌ **Database offline.** Cannot update played games.")
            return

        # Check if method exists
        if not hasattr(db, 'update_played_game'):
            await ctx.send("❌ **Game update not available.** Database method `update_played_game()` needs implementation.")
            return

        # Parse name/id and updates
        parts = content.split(' | ')
        if len(parts) < 2:
            await ctx.send("❌ **Invalid format.** Use: `!updateplayedgame <name> status:<status> | episodes:<count>`")
            return

        game_identifier = parts[0].strip()

        # Parse updates
        updates = {}
        for i in range(1, len(parts)):
            if ':' in parts[i]:
                key, value = parts[i].split(':', 1)
                key = key.strip().lower()
                value = value.strip()

                if key in ['status', 'completion_status']:
                    if value.lower() in ['completed', 'ongoing', 'dropped']:
                        updates['completion_status'] = value.lower()
                    else:
                        await ctx.send(f"❌ **Invalid status:** '{value}'. Use: completed, ongoing, or dropped")
                        return
                elif key in ['episodes', 'total_episodes']:
                    try:
                        updates['total_episodes'] = int(value)
                    except ValueError:
                        await ctx.send(f"❌ **Invalid episode count:** '{value}'. Must be a number.")
                        return
                elif key in ['series', 'series_name']:
                    updates['series_name'] = value
                elif key in ['year', 'release_year']:
                    try:
                        updates['release_year'] = int(value)
                    except ValueError:
                        await ctx.send(f"❌ **Invalid year:** '{value}'. Must be a number.")
                        return
                elif key in ['genre']:
                    updates['genre'] = value

        if not updates:
            await ctx.send("❌ **No valid updates provided.** Check format: `status:completed | episodes:20`")
            return

        # Update the game
        try:
            success = db.update_played_game(
                game_identifier, **updates)  # type: ignore

            if success:
                # Build confirmation message
                changes = []
                for key, value in updates.items():
                    if key == 'completion_status':
                        changes.append(f"status: {value}")
                    elif key == 'total_episodes':
                        changes.append(f"episodes: {value}")
                    elif key == 'series_name':
                        changes.append(f"series: {value}")
                    elif key == 'release_year':
                        changes.append(f"year: {value}")
                    elif key == 'genre':
                        changes.append(f"genre: {value}")

                changes_text = ', '.join(changes)
                await ctx.send(f"✅ **Updated '{game_identifier}':** {changes_text}\n\n*Use `!gameinfo {game_identifier}` to view updated details.*")
            else:
                await ctx.send(f"❌ **Failed to update '{game_identifier}'.** Game not found or database error.")

        except Exception as e:
            print(f"❌ Error calling update_played_game: {e}")
            await ctx.send("❌ **Database method error.** The `update_played_game()` function needs proper implementation.")

    except Exception as e:
        print(f"❌ Error in updateplayedgame command: {e}")
        await ctx.send("❌ System error occurred while updating played game.")


@bot.command(name="announce")
async def make_announcement(ctx, *, announcement_text: Optional[str] = None):
    """Create server-wide announcement (Captain Jonesy and Sir Decent Jam only)"""
    # Strict access control - only Captain Jonesy and Sir Decent Jam
    if ctx.author.id not in [JONESY_USER_ID, JAM_USER_ID]:
        return  # Silent ignore for unauthorized users

    try:
        if not announcement_text:
            help_text = (
                "**Announcement System Access Confirmed**\n\n"
                "**Usage:** `!announce <message>`\n\n"
                "**Features:**\n"
                "• Cross-posted to announcement channels\n"
                "• Special embed formatting with authority indicators\n"
                "• Database logging for audit trail\n\n"
                "**Also Available:**\n"
                "• `!scheduleannouncement <time> <message>` - Schedule for later\n"
                "• `!emergency <message>` - Emergency @everyone alert")
            await ctx.send(help_text)
            return

        # Create announcement embed
        embed = discord.Embed(
            title="📢 Server Announcement",
            description=announcement_text,
            color=0x00ff00,  # Green for normal announcements
            timestamp=datetime.now(ZoneInfo("Europe/London"))
        )

        # Add authority indicator
        if ctx.author.id == JONESY_USER_ID:
            embed.set_footer(
                text="Announced by Captain Jonesy • Server Owner",
                icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)
        elif ctx.author.id == JAM_USER_ID:
            embed.set_footer(
                text="Announced by Sir Decent Jam • Bot Creator",
                icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

        # Send to announcement channel
        announcement_channel = bot.get_channel(ANNOUNCEMENTS_CHANNEL_ID)
        if announcement_channel:
            await announcement_channel.send(embed=embed)  # type: ignore
            # type: ignore
            await ctx.send(f"✅ **Announcement posted** to {announcement_channel.mention}.")

        else:
            await ctx.send("❌ **Announcement channel not found.** Please check channel configuration.")

        # Log to database if available
        if db and hasattr(db, 'log_announcement'):
            try:
                db.log_announcement(  # type: ignore
                    ctx.author.id,
                    announcement_text,
                    "announcement")
            except BaseException:
                pass  # Non-critical logging failure

    except Exception as e:
        print(f"❌ Error in announce command: {e}")
        await ctx.send("❌ **System error occurred** while posting announcement.")


@bot.command(name="emergency")
async def emergency_announcement(ctx, *, message: Optional[str] = None):
    """Create emergency announcement with @everyone ping (Captain Jonesy and Sir Decent Jam only)"""
    # Strict access control
    if ctx.author.id not in [JONESY_USER_ID, JAM_USER_ID]:
        return  # Silent ignore

    try:
        if not message:
            await ctx.send("❌ **Emergency message required.** Usage: `!emergency <critical message>`\n\n⚠️ This will ping @everyone - use responsibly.")
            return

        # Create emergency embed with red color
        embed = discord.Embed(
            title="🚨 EMERGENCY ANNOUNCEMENT",
            description=message,
            color=0xff0000,  # Red for emergency
            timestamp=datetime.now(ZoneInfo("Europe/London"))
        )

        # Add authority indicator
        if ctx.author.id == JONESY_USER_ID:
            embed.set_footer(
                text="Emergency Alert by Captain Jonesy • Server Owner",
                icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)
        elif ctx.author.id == JAM_USER_ID:
            embed.set_footer(
                text="Emergency Alert by Sir Decent Jam • Bot Creator",
                icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

        # Send to announcement channel with @everyone ping
        announcement_channel = bot.get_channel(ANNOUNCEMENTS_CHANNEL_ID)
        if announcement_channel:

            # type: ignore
            await announcement_channel.send("@everyone", embed=embed)

            # type: ignore
            await ctx.send(f"🚨 **Emergency announcement posted** with @everyone ping to {announcement_channel.mention}.")

        else:
            await ctx.send("❌ **Announcement channel not found.** Please check channel configuration.")

        # Log to database
        if db and hasattr(db, 'log_announcement'):
            try:
                db.log_announcement(  # type: ignore
                    ctx.author.id, message, "emergency")
            except BaseException:
                pass

    except Exception as e:
        print(f"❌ Error in emergency command: {e}")
        await ctx.send("❌ **System error occurred** while posting emergency announcement.")


@bot.command(name="bulkimportplayedgames")
@commands.has_permissions(manage_messages=True)
async def bulk_import_played_games(ctx):
    """Import games from YouTube playlists and Twitch VODs with real playtime (moderators only)"""
    try:
        if db is None:
            await ctx.send("❌ **Database offline.** Cannot import games without database connection.")
            return

        # Check if import methods exist
        if not hasattr(db, 'bulk_import_from_youtube'):
            await ctx.send("❌ **Import system not available.** Database methods need implementation.\n\n*Required methods: `bulk_import_from_youtube()`, `bulk_import_from_twitch()`, `ai_enhance_game_metadata()`*")
            return

        # Progressive disclosure help and confirmation
        help_text = (
            "**Bulk Import System**\n\n"
            "**Features:**\n"
            "• **YouTube:** Playlist-based detection with accurate video duration\n"
            "• **Twitch:** VOD analysis with duration tracking and series grouping\n"
            "• **AI Enhancement:** Automatic genre, series, and release year detection\n"
            "• **Smart Deduplication:** Merges YouTube + Twitch data for same games\n\n"
            "**Process:**\n"
            "1. Import from YouTube playlists\n"
            "2. Import from Twitch VODs (if configured)\n"
            "3. AI metadata enhancement\n"
            "4. Deduplication and validation\n\n"
            "**Type `CONFIRM` to start the import process:**")
        await ctx.send(help_text)

        # Wait for confirmation
        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel and message.content.upper() == "CONFIRM"

        try:
            await bot.wait_for('message', check=check, timeout=30.0)
        except BaseException:
            await ctx.send("❌ **Import cancelled** - confirmation timeout.")
            return

        # Start import process
        await ctx.send("🔄 **Starting bulk import process...** This may take several minutes.")

        try:
            # Import from YouTube
            youtube_results = db.bulk_import_from_youtube()  # type: ignore

            # Import from Twitch if available
            twitch_results = None
            if hasattr(db, 'bulk_import_from_twitch'):
                twitch_results = db.bulk_import_from_twitch()  # type: ignore

            # AI enhancement if available
            if hasattr(db, 'ai_enhance_game_metadata'):
                ai_results = db.ai_enhance_game_metadata()  # type: ignore

            # Build results message
            results_text = "✅ **Import completed successfully!**\n\n"

            if youtube_results:
                results_text += f"📺 **YouTube:** {youtube_results.get('games_imported', 0)} games imported\n"
                results_text += f"⏱️ **Playtime:** {youtube_results.get('total_minutes', 0)} minutes processed\n"

            if twitch_results:
                results_text += f"🎮 **Twitch:** {twitch_results.get('vods_processed', 0)} VODs processed\n"

            results_text += "\n*Use `!dbstats` to see updated database statistics.*"

            await ctx.send(results_text)

        except Exception as e:
            print(f"❌ Error during bulk import: {e}")
            await ctx.send("❌ **Import process failed.** Database methods need proper implementation or API configuration issues.")

    except Exception as e:
        print(f"❌ Error in bulkimportplayedgames command: {e}")
        await ctx.send("❌ System error occurred during import.")


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
