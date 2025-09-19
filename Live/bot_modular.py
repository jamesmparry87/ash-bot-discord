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
            handle_pineapple_pizza_enforcement,
            handle_strike_detection,
            process_gaming_query_with_context,
        )

        message_handler_functions = {
            'handle_strike_detection': handle_strike_detection,
            'handle_pineapple_pizza_enforcement': handle_pineapple_pizza_enforcement,
            'process_gaming_query_with_context': process_gaming_query_with_context,
        }

        status_report["message_handlers"] = True
        print("✅ Message handlers initialized successfully")

    except Exception as e:
        status_report["errors"].append(f"Message Handlers: {e}")
        print(f"❌ Message handler initialization failed: {e}")
        message_handler_functions = None

    # 5. Start Scheduled Tasks
    try:
        from bot.tasks.scheduled import start_all_scheduled_tasks, validate_startup_trivia_questions, schedule_delayed_trivia_validation
        start_all_scheduled_tasks()
        print("✅ Scheduled tasks started successfully")
        
        # Schedule delayed trivia validation (non-blocking for deployment safety)
        # Skip if bot/main.py is also running to prevent duplication
        try:
            # Check if we're running as the primary entry point
            import sys
            main_module_running = any('bot.main' in str(frame) or 'bot/main.py' in str(frame) 
                                    for frame in sys.modules.keys())
            
            if not main_module_running:
                # Schedule validation to run 2 minutes after startup (non-blocking)
                asyncio.create_task(schedule_delayed_trivia_validation())
                print("✅ Delayed trivia validation scheduled for 2 minutes after startup (non-blocking)")
            else:
                print("⚠️ Skipping trivia validation - will be handled by bot/main.py to prevent duplication")
                
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
async def on_message(message):
    """Handle incoming messages with comprehensive DM and query detection"""
    # Ignore bot messages
    if message.author.bot:
        return

    # PRIORITY 1: Process ALL traditional commands first, regardless of context
    # This ensures commands like "!remind @DecentJam 2m Smile" always work
    if message.content.strip().startswith('!'):
        print(f"🔧 Traditional command detected (priority): {message.content.strip()[:30]}...")
        await bot.process_commands(message)
        return

    # Check if this is a DM
    is_dm = isinstance(message.channel, discord.DMChannel)

    # Check if bot is mentioned
    is_mentioned = bot.user and bot.user in message.mentions

    # Check for implicit game queries (even without mentions)
    is_implicit_game_query = detect_implicit_game_query(message.content)

    # PRIORITY 2: Check for trivia answer replies BEFORE mod channel restrictions
    # This ensures trivia answers work in ALL channels, including mod channels
    if not is_dm:  # Only check in guild channels
        try:
            is_trivia_reply, trivia_session = await is_trivia_answer_reply(message)
            if is_trivia_reply and trivia_session:
                print(f"🎯 TRIVIA: Processing answer reply in channel {message.channel.id}")
                success = await process_trivia_answer(message, trivia_session)
                if success:
                    print(f"✅ TRIVIA: Successfully processed answer from user {message.author.id}")
                else:
                    print(f"⚠️ TRIVIA: Failed to process answer from user {message.author.id}")
                return  # Exit early - trivia answer has been handled
        except Exception as e:
            print(f"❌ Error checking for trivia answer reply: {e}")
            # Continue with normal message processing if trivia check fails

    # Handle DM conversation flows
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
        # For guild messages, commands were already handled above, so nothing more to do
        return

    # Check if this is a moderator channel
    is_mod_channel = False
    if not is_dm and hasattr(message.channel, 'id'):
        is_mod_channel = await is_moderator_channel(message.channel.id)

    try:
        # Handle strikes in violation channel (guild messages only)
        if not is_dm and await message_handler_functions['handle_strike_detection'](message, bot):
            return

        # Handle pineapple pizza enforcement (skip in mod channels unless directly mentioned)
        if not is_mod_channel or is_mentioned or message.content.lower().startswith('ash'):
            if await message_handler_functions['handle_pineapple_pizza_enforcement'](message):
                return

        # Determine if we should process this message for queries/conversation
        if is_mod_channel:
            # In mod channels, only process direct mentions/interactions
            should_process_query = (
                is_mentioned or  # Direct @Ash mentions
                message.content.lower().startswith('ash')  # "ash" prefix
            )
            print(f"🔧 Mod channel detected - limiting to direct mentions only")
        else:
            # Normal processing for non-mod channels
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

            # PRIORITY 2: Check for natural language commands
            if detect_natural_language_command(content):
                print(f"🔧 Natural language command detected: {content[:50]}... - processing as command")

                # For natural language commands, we need to construct a proper command
                # The reminder command supports natural language parsing
                content_lower = content.lower().strip()

                # Handle reminder patterns
                if any(re.search(pattern, content_lower) for pattern in [
                    r"set\s+(?:a\s+)?remind(?:er)?\s+for",
                    r"remind\s+me\s+(?:in|at|to)",
                    r"create\s+(?:a\s+)?remind(?:er)?\s+for",
                    r"schedule\s+(?:a\s+)?remind(?:er)?\s+for",
                    r"set\s+(?:a\s+)?timer\s+for",
                    r"remind\s+(?:me\s+)?in\s+\d+",
                    r"reminder\s+(?:in|for)\s+\d+"
                ]):
                    # Create a fake message with !remind command for processing
                    fake_content = f"!remind {content}"
                    original_content = message.content
                    message.content = fake_content
                    await bot.process_commands(message)
                    message.content = original_content  # Restore original content
                    return

                # Handle other natural language commands here as needed
                # For now, fall through to normal processing for other patterns

            # PRIORITY 3: Use the unified context-aware gaming query processor
            if await message_handler_functions['process_gaming_query_with_context'](message):
                return
            else:
                # PRIORITY 4: Handle with general conversation/FAQ system
                await handle_general_conversation(message)
                return

    except Exception as e:
        print(f"❌ Error in message handler: {e}")
        import traceback
        traceback.print_exc()

    # Handle general conversation for DMs or mentions that didn't match specific patterns
    if is_dm or is_mentioned:
        await handle_general_conversation(message)
        return

    # For guild messages that don't match any patterns, do nothing
    # (Commands were already processed at the top)


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
            print(f"🧠 TRIVIA: Detected answer reply from user {message.author.id}: '{message.content}' → session {active_session['id']}")
            return True, active_session
            
        return False, None
        
    except Exception as e:
        print(f"❌ Error checking trivia answer reply: {e}")
        return False, None


def normalize_trivia_answer(answer_text: str) -> str:
    """Enhanced normalization for trivia answers with fuzzy matching support"""
    import re
    
    # Start with the original text
    normalized = answer_text.strip()
    
    # Remove common punctuation but preserve important chars like hyphens in compound words
    normalized = re.sub(r'[.,!?;:"\'()[\]{}]', '', normalized)
    
    # Handle common game/media abbreviations and variations
    abbreviation_map = {
        'gta': 'grand theft auto',
        'cod': 'call of duty', 
        'gtav': 'grand theft auto v',
        'gtaiv': 'grand theft auto iv',
        'rdr': 'red dead redemption',
        'rdr2': 'red dead redemption 2',
        'gow': 'god of war',
        'tlou': 'the last of us',
        'botw': 'breath of the wild',
        'totk': 'tears of the kingdom',
        'ff': 'final fantasy',
        'ffvii': 'final fantasy vii',
        'ffx': 'final fantasy x',
        'mgs': 'metal gear solid',
        'loz': 'legend of zelda',
        'zelda': 'legend of zelda',
        'pokemon': 'pokémon',
        'mario': 'super mario',
        'doom': 'doom',
        'halo': 'halo',
        'fallout': 'fallout'
    }
    
    # Apply abbreviation expansions (case insensitive)
    words = normalized.lower().split()
    expanded_words = []
    for word in words:
        if word in abbreviation_map:
            expanded_words.extend(abbreviation_map[word].split())
        else:
            expanded_words.append(word)
    normalized = ' '.join(expanded_words)
    
    # Remove filler words that don't change meaning
    filler_words = ['and', 'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by',
                    'about', 'approximately', 'roughly', 'around', 'over', 'under', 'just',
                    'exactly', 'precisely', 'nearly', 'almost', 'close to', 'more than', 'less than']
    
    # Split into words and filter out filler words
    words = normalized.split()
    filtered_words = [word for word in words if word not in filler_words]
    
    # Rejoin and clean up extra spaces
    normalized = ' '.join(filtered_words)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


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
            
        # Extract answer text
        answer_text = message.content.strip()
        
        # Enhanced normalization for fuzzy matching
        normalized_answer = normalize_trivia_answer(answer_text)
        
        print(f"🧠 TRIVIA: Processing answer - Original: '{answer_text}' → Normalized: '{normalized_answer}'")
        
        # Submit answer to database
        answer_id = db.submit_trivia_answer(
            session_id=trivia_session['id'],
            user_id=message.author.id,
            answer_text=answer_text,
            normalized_answer=normalized_answer
        )
        
        if answer_id:
            print(f"✅ TRIVIA: Submitted answer #{answer_id} from user {message.author.id} for session {trivia_session['id']}")
            
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

        # Check for announcement creation intents BEFORE FAQ processing
        announcement_creation_patterns = [
            "i want to write an announcement",
            "i want to create an announcement",
            "i want to make an announcement",
            "write an announcement",
            "create an announcement",
            "make an announcement",
            "start announcement creation",
            "begin announcement creation"
        ]

        # Only Captain Jonesy and Sir Decent Jam can create announcements
        if user_tier in ["captain", "creator"] and any(
                pattern in content_lower for pattern in announcement_creation_patterns):
            # Check if this is a DM - announcement creation must be in DM
            if isinstance(message.channel, discord.DMChannel):
                # Import and start announcement conversation if available
                if start_announcement_conversation is not None:
                    print(f"🎯 Announcement creation intent detected from {user_tier} user in DM")
                    # Create a fake context object for the conversation handler

                    class FakeCtx:
                        def __init__(self, message):
                            self.author = message.author
                            self.guild = message.guild
                            self.send = message.reply

                    fake_ctx = FakeCtx(message)
                    await start_announcement_conversation(fake_ctx)
                    return
                else:
                    await message.reply("❌ Announcement creation system not available - conversation handler not loaded.")
                    return
            else:
                # Not in DM - redirect to DM
                await message.reply(
                    f"⚠️ **Security protocol engaged.** Announcement creation must be initiated via direct message. "
                    f"Please DM me with your announcement request to begin the secure briefing process.\n\n"
                    f"*Confidential mission parameters require private channel authorization.*"
                )
                return

        # Check for moderator FAQ queries (if FAQ handler is available)
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

CRITICAL DISAMBIGUATION RULE: In this Discord server context, "Jonesy" ALWAYS refers to Captain Jonesy - the Discord user, server owner, and streamer/YouTuber (she/her pronouns). This is the default and correct interpretation unless explicitly discussing the 1979 Alien movie. The cat named Jonesy from Alien is a separate entity that is rarely relevant in server discussions.

DEFAULT ASSUMPTION: Any mention of "Jonesy" = Captain Jonesy (the user).

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
            "what": "My analytical subroutines are currently operating in limited mode. However, I can assist with game recommendations. Specify your requirements.",
            "how": "My cognitive matrix is experiencing temporary limitations. Please utilize available command protocols: `!listgames`, `!addgame`, or consult a moderator.",
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
        r"^what\s+(games?\s+)?(?:do\s+you\s+|would\s+you\s+|should\s+i\s+)?recommend", # Direct recommendation requests only
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
        r"set\s+(?:a\s+)?remind(?:er)?\s+for",
        r"remind\s+me\s+(?:in|at|to)",
        r"create\s+(?:a\s+)?remind(?:er)?\s+for",
        r"schedule\s+(?:a\s+)?remind(?:er)?\s+for",
        r"set\s+(?:a\s+)?timer\s+for",
        r"remind\s+(?:me\s+)?in\s+\d+",
        r"reminder\s+(?:in|for)\s+\d+",

        # Game recommendation commands (natural language alternatives)
        r"(?:add|suggest|recommend)\s+(?:the\s+)?game",
        r"i\s+want\s+to\s+(?:add|suggest|recommend)",
        r"(?:add|suggest)\s+.+\s+(?:game|to\s+(?:the\s+)?(?:list|database))",

        # Other potential natural language commands
        r"show\s+(?:me\s+)?(?:my\s+)?reminders?",
        r"list\s+(?:my\s+)?reminders?",
        r"cancel\s+(?:my\s+)?reminder",
        r"delete\s+(?:my\s+)?reminder",
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
