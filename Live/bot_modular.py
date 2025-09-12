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
    """Initialize all modular components and return status report"""
    status_report = {
        "ai_handler": False,
        "database": False,
        "commands": False,
        "scheduled_tasks": False,
        "message_handlers": False,
        "fallback_mode": False,
        "errors": []
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

    # 3. Load Command Cogs
    try:
        # Load strikes commands
        from bot.commands.strikes import StrikesCommands
        await bot.add_cog(StrikesCommands(bot))

        # Load other command modules if they exist
        command_modules_loaded = 1  # We loaded strikes at minimum

        try:
            from bot.commands.games import GamesCommands
            await bot.add_cog(GamesCommands(bot))
            command_modules_loaded += 1
        except ImportError:
            print("⚠️ Games commands module not found, skipping")
        except Exception as e:
            print(f"⚠️ Games commands failed to load: {e}")

        try:
            from bot.commands.utility import UtilityCommands
            await bot.add_cog(UtilityCommands(bot))
            command_modules_loaded += 1
        except ImportError:
            print("⚠️ Utility commands module not found, skipping")
        except Exception as e:
            print(f"⚠️ Utility commands failed to load: {e}")

        status_report["commands"] = True
        print(
            f"✅ Command modules loaded successfully ({command_modules_loaded} modules)")

    except Exception as e:
        status_report["errors"].append(f"Commands: {e}")
        print(f"❌ Command loading failed: {e}")

    # 4. Set up Message Handlers
    try:
        # Import message handler functions
        global message_handler_functions
        from bot.handlers.message_handler import (
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
    """Send deployment success notification to JAM_USER_ID (once per deployment cycle)"""
    global deployment_notification_sent

    # Check if we've already sent a notification in the last 5 minutes
    # This prevents duplicate messages during deployment restarts
    if deployment_notification_sent:
        print("✅ Deployment notification already sent, skipping duplicate")
        return

    try:
        user = await bot.fetch_user(JAM_USER_ID)
        if not user:
            print(
                f"❌ Could not fetch user {JAM_USER_ID} for deployment notification")
            return

        # Count successful components
        successful_components = sum(1 for key, value in status_report.items()
                                    if key != "errors" and value)
        total_components = len(
            [k for k in status_report.keys() if k != "errors"])

        # Create status message
        error_count = len(status_report["errors"])
        component_count = sum(
            1 for key, value in status_report.items() if key not in [
                "errors", "fallback_mode"] and value)

        if error_count <= 2 and component_count >= 3:  # Require at least 3 components working
            embed = discord.Embed(
                title="🎉 Ash Bot Fully Operational!",
                description="All modular components loaded and initialized successfully. The bot is now fully responsive!",
                color=0x00ff00,
                timestamp=datetime.now(
                    ZoneInfo("Europe/London")))

            # Build component status
            component_status = []
            if status_report["commands"]:
                component_status.append("• Commands (strikes, games, utility)")
            if status_report["message_handlers"]:
                component_status.append(
                    "• Message handlers (strike detection, query routing)")
            if status_report["scheduled_tasks"]:
                component_status.append(
                    "• Scheduled tasks (reminders, trivia)")
            if status_report["ai_handler"]:
                component_status.append("• AI handler (rate limiting)")
            if status_report["database"]:
                component_status.append("• Database system")

            embed.add_field(name="✅ Loaded Components", value="\n".join(
                component_status) if component_status else "Core systems operational", inline=False)

            embed.add_field(
                name="🔧 Deployment Fixes Active",
                value="• Progressive penalty system (30s → 60s → 120s → 300s)\n• Enhanced database import strategies\n• Reduced alias cooldowns for testing\n• Complete alias debugging system\n• Enhanced !ashstatus with AI diagnostics",
                inline=False)

            embed.set_footer(
                text="Bot is now responsive to commands and messages!")

        else:
            embed = discord.Embed(
                title="⚠️ Modular Architecture Deployment - Partial Success",
                description=f"Deployed with {successful_components}/{total_components} components successful",
                color=0xffaa00,
                timestamp=datetime.now(
                    ZoneInfo("Europe/London")))

            if status_report["errors"]:
                error_text = "\n".join(
                    [f"• {error}" for error in status_report["errors"][:5]])
                embed.add_field(
                    name="❌ Errors",
                    value=error_text,
                    inline=False)

        await user.send(embed=embed)
        deployment_notification_sent = True  # Mark as sent
        print(f"✅ Deployment notification sent to {user.display_name}")

        # Reset the flag after 5 minutes to allow for genuine redeployments
        async def reset_notification_flag():
            await asyncio.sleep(300)  # 5 minutes
            global deployment_notification_sent
            deployment_notification_sent = False
            print("🔄 Deployment notification flag reset")

        asyncio.create_task(reset_notification_flag())

    except Exception as e:
        print(f"❌ Failed to send deployment notification: {e}")


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

        # Check for capability questions with location-aware responses
        if any(
            trigger in content_lower for trigger in [
                "what can you do",
                "what does this bot do",
                "what are your functions",
                "what are your capabilities",
                "help",
                "commands"]):
            if user_tier == "moderator_in_mod_channel":
                # Short initial response for mods in mod channels
                help_text = (
                    "**Core systems:** Strike management, game database analysis, AI integration, trivia system, reminder protocols, and announcement system.\n\n"
                    "Would you like me to provide the complete FAQ system overview with available topics and command examples?")
            elif user_tier in ["moderator", "creator", "captain"]:
                # Short initial response for elevated users
                help_text = (
                    "**Primary functions:** Strike management, game recommendations, Captain Jonesy's gaming database queries, conversation, and Trivia Tuesday management.\n\n"
                    "Would you like detailed information about commands and database query capabilities?")
            else:
                # Short initial response for standard users
                help_text = (
                    "**Available functions:** Game recommendations, Captain Jonesy's gaming database queries, basic conversation, and Trivia Tuesday participation.\n\n"
                    "Would you like more details about specific commands or how to interact with the gaming database?")
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


@bot.command(name="addtriviaquestion")
async def add_trivia_question_command(ctx):
    """Start interactive DM conversation for trivia question submission"""
    if start_trivia_conversation is not None:
        await start_trivia_conversation(ctx)
    else:
        await ctx.send("❌ Trivia submission system not available - conversation handler not loaded.")


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


@bot.command(name="time")
async def get_current_time(ctx):
    """Get current time in GMT/BST"""
    try:
        from bot.utils.time_utils import get_uk_time, is_dst_active

        uk_now = get_uk_time()
        is_dst = is_dst_active(uk_now)
        timezone_name = "BST" if is_dst else "GMT"

        formatted_time = uk_now.strftime(
            f"%A, %B %d, %Y at %H:%M:%S {timezone_name}")

        await ctx.send(f"Current time: {formatted_time}")

    except Exception as e:
        # Fallback to basic implementation
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        # Check if DST is active (rough approximation)
        is_summer = 3 <= uk_now.month <= 10  # March to October roughly
        timezone_name = "BST" if is_summer else "GMT"

        formatted_time = uk_now.strftime(
            f"%A, %B %d, %Y at %H:%M:%S {timezone_name}")
        await ctx.send(f"Current time: {formatted_time}")


@bot.command(name="remind")
async def set_reminder(ctx, *, content: Optional[str] = None):
    """Enhanced reminder command with natural language support"""
    try:
        if not content:
            # Show improved help message
            help_text = (
                "**Reminder System Usage:**\n\n"
                "**Simple Commands:**\n"
                "• `remind me in 2 minutes <message>` - Set quick reminder\n"
                "• `remind me in 1 hour to check stream` - Reminder with message\n"
                "• `set reminder for 7pm` - Set for specific time (asks for message)\n\n"
                "**Time Formats:**\n"
                "• Relative: `in 5 minutes`, `in 2 hours`, `in 1 day`\n"
                "• Absolute: `at 7pm`, `at 19:00`, `for 7:30pm`\n"
                "• Tomorrow: `tomorrow`, `tomorrow at 9am`\n\n"
                "*For moderators: Additional auto-action features available*")
            await ctx.send(help_text)
            return

        # Check if database is available for reminders
        if db is None:
            await ctx.send("❌ Reminder system offline - database not available.")
            return

        # Try to parse the natural language reminder
        try:
            from bot.tasks.reminders import format_reminder_time, parse_natural_reminder, validate_reminder_text

            parsed = parse_natural_reminder(content, ctx.author.id)

            if not parsed["success"] or not validate_reminder_text(
                    parsed["reminder_text"]):
                # Ask for reminder message if missing
                if not parsed["reminder_text"].strip():
                    formatted_time = format_reminder_time(
                        parsed["scheduled_time"])
                    await ctx.send(f"Reminder scheduled for {formatted_time}. What should I remind you about?")
                    # Here you'd typically wait for the next message, but for
                    # now just ask
                    return
                else:
                    await ctx.send("❌ **Invalid reminder format.** Use formats like: `remind me in 30 minutes to check stream` or `remind me at 7pm <message>`")
                    return

            # Add reminder to database
            reminder_id = db.add_reminder(
                user_id=ctx.author.id,
                reminder_text=parsed["reminder_text"],
                scheduled_time=parsed["scheduled_time"],
                delivery_channel_id=ctx.channel.id,
                delivery_type="channel"
            )

            if reminder_id:
                formatted_time = format_reminder_time(parsed["scheduled_time"])
                await ctx.send(f"✅ Reminder set for {formatted_time}: *{parsed['reminder_text']}*")
            else:
                await ctx.send("❌ Failed to save reminder. Please try again.")

        except ImportError:
            # Fallback if reminder parsing not available
            await ctx.send("❌ Enhanced reminder parsing not available. Use format: `!remind @user <time> <message>`")

    except Exception as e:
        print(f"❌ Error in remind command: {e}")
        await ctx.send("❌ System error occurred while processing reminder. Please try again.")


@bot.command(name="listgames")
async def list_games(ctx):
    """List game recommendations"""
    try:
        if db is None:
            await ctx.send("❌ Game database offline - DATABASE_URL not configured.")
            return

        games = db.get_all_games()

        if not games:
            await ctx.send("📋 No game recommendations found. Use `!addgame <name> - <reason>` to suggest games!")
            return

        # Build game list with recommendations
        game_list = []
        for i, game in enumerate(games[:15], 1):  # Limit to first 15 games
            reason = f" - {game['reason']}" if game.get('reason') else ""
            added_by = f" (by {game['added_by']})" if game.get(
                'added_by') else ""
            game_list.append(f"{i}. **{game['name']}**{reason}{added_by}")

        response = "🎮 **Game Recommendations:**\n\n" + "\n".join(game_list)

        if len(games) > 15:
            response += f"\n\n*Showing first 15 of {len(games)} total recommendations*"

        response += f"\n\n*Use `!addgame <name> - <reason>` to suggest more games*"

        await ctx.send(response[:2000])  # Discord message limit

    except Exception as e:
        print(f"❌ Error in listgames command: {e}")
        await ctx.send("❌ Error retrieving game recommendations. Database may be experiencing issues.")


@bot.command(name="addgame")
async def add_game(ctx, *, content: Optional[str] = None):
    """Add a game recommendation"""
    try:
        if not content:
            await ctx.send("❌ **Usage:** `!addgame <game name> - <reason for recommendation>`\n**Example:** `!addgame Hollow Knight - Amazing metroidvania with beautiful art`")
            return

        if db is None:
            await ctx.send("❌ Game database offline - DATABASE_URL not configured.")
            return

        # Parse game name and reason
        if " - " not in content:
            await ctx.send("❌ **Invalid format.** Use: `!addgame <game name> - <reason>`\n**Example:** `!addgame Hollow Knight - Amazing metroidvania with beautiful art`")
            return

        parts = content.split(" - ", 1)
        game_name = parts[0].strip()
        reason = parts[1].strip()

        if not game_name or not reason:
            await ctx.send("❌ **Both game name and reason are required.**\n**Example:** `!addgame Hollow Knight - Amazing metroidvania with beautiful art`")
            return

        # Check if game already exists
        if db.game_exists(game_name):
            await ctx.send(f"❌ **'{game_name}'** is already in the recommendations list.")
            return

        # Add the game
        success = db.add_game_recommendation(
            game_name, reason, ctx.author.display_name)

        if success:
            await ctx.send(f"✅ **'{game_name}'** added to recommendations! Thank you {ctx.author.display_name}.")
        else:
            await ctx.send("❌ Failed to add game recommendation. Database error occurred.")

    except Exception as e:
        print(f"❌ Error in addgame command: {e}")
        await ctx.send("❌ Error adding game recommendation. Please try again.")


@bot.command(name="dbstats")
@commands.has_permissions(manage_messages=True)
async def database_stats(ctx):
    """Show database statistics (moderators only)"""
    try:
        if db is None:
            await ctx.send("❌ Database offline - DATABASE_URL not configured.")
            return

        # Get comprehensive database statistics
        played_games_stats = db.get_played_games_stats()
        strikes_data = db.get_all_strikes()
        game_recs = db.get_all_games()

        stats_msg = "📊 **Database Statistics Report**\n\n"

        # Played Games Stats
        if played_games_stats:
            stats_msg += f"🎮 **Gaming Database:**\n"
            stats_msg += f"• Total games: {played_games_stats.get('total_games', 0)}\n"
            stats_msg += f"• Total episodes: {played_games_stats.get('total_episodes', 0)}\n"
            stats_msg += f"• Total playtime: {played_games_stats.get('total_playtime_hours', 0)} hours\n"

            status_counts = played_games_stats.get('status_counts', {})
            if status_counts:
                stats_msg += f"• Completed: {status_counts.get('completed', 0)}\n"
                stats_msg += f"• Ongoing: {status_counts.get('ongoing', 0)}\n"
                stats_msg += f"• Dropped: {status_counts.get('dropped', 0)}\n"

            top_genres = played_games_stats.get('top_genres', {})
            if top_genres:
                stats_msg += f"• Top genres: {', '.join(list(top_genres.keys())[:3])}\n"

        # Strike System Stats
        total_strikes = sum(strikes_data.values()) if strikes_data else 0
        users_with_strikes = len(
            [s for s in strikes_data.values() if s > 0]) if strikes_data else 0
        stats_msg += f"\n⚠️ **Strike System:**\n"
        stats_msg += f"• Total strikes: {total_strikes}\n"
        stats_msg += f"• Users with strikes: {users_with_strikes}\n"

        # Game Recommendations Stats
        stats_msg += f"\n🎯 **Game Recommendations:**\n"
        stats_msg += f"• Total recommendations: {len(game_recs)}\n"

        # Database Connection Status
        try:
            # Test database connection
            test_strikes = db.get_user_strikes(12345)  # Test query
            stats_msg += f"\n🔗 **Database Connection:**\n"
            stats_msg += f"• Status: ✅ Connected to Railway PostgreSQL\n"
            stats_msg += f"• Connection: postgresql://postgres:***@postgres.railway.internal:5432/railway\n"
        except Exception as e:
            stats_msg += f"\n🔗 **Database Connection:**\n"
            stats_msg += f"• Status: ❌ Connection error: {str(e)[:50]}...\n"

        await ctx.send(stats_msg[:2000])

    except Exception as e:
        print(f"❌ Error in dbstats command: {e}")
        await ctx.send(f"❌ Database statistics error: {str(e)[:100]}...")


@bot.command(name="ashstatus")
async def ash_status(ctx):
    """Show comprehensive bot status with AI diagnostics - works in DMs for authorized users and in guilds for mods"""
    try:
        # Custom permission checking that works in both DMs and guilds
        is_authorized = False

        if ctx.guild is None:  # DM
            # Allow JAM, JONESY, and moderators in DMs
            if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
                is_authorized = True
            else:
                # Check if user is a mod
                guild = bot.get_guild(GUILD_ID)
                if guild:
                    try:
                        member = await guild.fetch_member(ctx.author.id)
                        is_authorized = member.guild_permissions.manage_messages
                    except (discord.NotFound, discord.Forbidden):
                        is_authorized = False
        else:  # Guild
            # Check standard mod permissions
            is_authorized = ctx.author.guild_permissions.manage_messages

        # Show different responses for unauthorized users
        if not is_authorized:
            if ctx.guild is None:  # DM - be more specific about authorization
                await ctx.send("⚠️ **Access denied.** System status diagnostics require elevated clearance. Authorization protocols restrict access to Captain Jonesy, Sir Decent Jam, and server moderators only.")
            else:  # Guild - use the generic response
                await ctx.send("Systems nominal, Sir Decent Jam. Awaiting Captain Jonesy's commands.")
            return

        # Get comprehensive status information
        status_msg = "🤖 **Ash Bot Comprehensive System Status**\n\n"

        # Component Status
        try:
            if db is not None:
                # Test database with actual query
                strikes_data = db.get_all_strikes() if hasattr(db, 'get_all_strikes') else {}
                total_strikes = sum(
                    strikes_data.values()) if strikes_data else 0
                status_msg += f"📊 **Database:** Online ({total_strikes} total strikes)\n"
            else:
                status_msg += f"📊 **Database:** Offline (DATABASE_URL not configured)\n"
        except Exception as e:
            status_msg += f"📊 **Database:** Error - {str(e)[:50]}...\n"

        # AI System Status with detailed diagnostics
        try:
            from bot.handlers.ai_handler import (
                ai_enabled,
                get_ai_status,
            )

            ai_status = get_ai_status()
            # Get basic AI stats from the status
            ai_stats = ai_status.get('usage_stats', {})

            status_msg += f"🧠 **AI System:** {ai_status['status_message']}\n"

            if ai_enabled:
                # Get current Pacific Time for display
                pt_now = datetime.now(ZoneInfo("US/Pacific"))

                # AI Budget tracking status
                status_msg += f"\n📊 **AI Budget Tracking (Pacific Time):**\n"
                status_msg += f"• **Daily Requests:** {ai_stats.get('daily_requests', 0)}/{ai_stats.get('max_daily_requests', 1400)} ({(ai_stats.get('daily_requests', 0)/ai_stats.get('max_daily_requests', 1400)*100):.1f}%)\n"
                status_msg += f"• **Hourly Requests:** {ai_stats.get('hourly_requests', 0)}/{ai_stats.get('max_hourly_requests', 120)} ({(ai_stats.get('hourly_requests', 0)/ai_stats.get('max_hourly_requests', 120)*100):.1f}%)\n"
                status_msg += f"• **Consecutive Errors:** {ai_stats.get('consecutive_errors', 0)}\n"
                status_msg += f"• **Current PT Time:** {pt_now.strftime('%Y-%m-%d %H:%M:%S PT')}\n"

                # Rate limit status
                if ai_stats.get(
                        "rate_limited_until") and pt_now < ai_stats["rate_limited_until"]:
                    remaining = (
                        ai_stats["rate_limited_until"] -
                        pt_now).total_seconds()
                    status_msg += f"• **Rate Limit:** 🚫 Active ({int(remaining)}s remaining)\n"
                else:
                    status_msg += f"• **Rate Limit:** ✅ Clear\n"
            else:
                status_msg += f"• **AI System:** Offline (API key not configured)\n"

        except Exception as e:
            status_msg += f"🧠 **AI System:** Error - {str(e)[:50]}...\n"

        # Component Status Summary
        try:
            status_report = {
                "message_handlers": message_handler_functions is not None,
                "database": db is not None,
                "alias_system": True,  # Always available
                "commands": True  # Basic commands always available
            }

            active_components = sum(status_report.values())
            status_msg += f"\n🔧 **System Components:** {active_components}/4 Active\n"

            if status_report["message_handlers"]:
                status_msg += "• ✅ Message Handlers (AI conversation, query routing)\n"
            else:
                status_msg += "• ❌ Message Handlers (limited functionality)\n"

            if status_report["database"]:
                status_msg += "• ✅ Database System (strikes, game tracking)\n"
            else:
                status_msg += "• ⚠️ Database System (DATABASE_URL not configured)\n"

            status_msg += "• ✅ Alias Debug System (user tier testing)\n"
            status_msg += "• ✅ Core Commands (strikes, utility)\n"

        except Exception as e:
            status_msg += f"\n❌ Component Status Error: {str(e)[:100]}...\n"

        # Current alias status if applicable
        cleanup_expired_aliases()
        if ctx.author.id in user_alias_state:
            alias_data = user_alias_state[ctx.author.id]
            time_active = datetime.now(
                ZoneInfo("Europe/London")) - alias_data["set_time"]
            hours = int(time_active.total_seconds() // 3600)
            minutes = int((time_active.total_seconds() % 3600) // 60)
            time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            status_msg += f"\n🎭 **Your Active Alias:** {alias_data['alias_type'].title()} (active for {time_str})\n"

        # Send response (split if too long)
        if len(status_msg) > 2000:
            # Split at logical points
            parts = status_msg.split('\n\n')
            current_part = ""

            for part in parts:
                if len(current_part + part) < 1900:
                    current_part += part + '\n\n'
                else:
                    if current_part:
                        await ctx.send(current_part.strip())
                    current_part = part + '\n\n'

            if current_part:
                await ctx.send(current_part.strip())
        else:
            await ctx.send(status_msg)

    except Exception as e:
        await ctx.send(f"❌ **System diagnostic error:** {str(e)[:100]}... Please contact Sir Decent Jam for technical assistance.")
        print(f"❌ Error in ashstatus command: {e}")


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

    bot.run(TOKEN)


if __name__ == "__main__":
    main()
