"""
Ash Bot - Main Entry Point (Refactored)
Streamlined bot startup and core event handlers
"""
import asyncio
import atexit
import os
import platform
import signal
import sys
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

# Import our modular components
from .config import (
    BOT_PERSONA,
    FAQ_RESPONSES,
    GUILD_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    LOCK_FILE,
    MEMBERS_CHANNEL_ID,
    MOD_ALERT_CHANNEL_ID,
    TOKEN,
    VIOLATION_CHANNEL_ID,
)
from .database import get_database
from .utils.permissions import (
    get_user_communication_tier,
    increment_member_conversation_count,
    should_limit_member_conversation,
    user_is_member,
    user_is_mod,
)

# Get database instance
db = get_database()  # type: ignore

# Import existing moderator FAQ handler from Live directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
try:
    from moderator_faq_handler import ModeratorFAQHandler
except ImportError:
    print("Warning: Could not import ModeratorFAQHandler")
    ModeratorFAQHandler = None

# --- Lock File Management ---


def acquire_lock() -> Optional[Any]:
    """Cross-platform file locking for single instance"""
    if platform.system() == "Windows":
        print("⚠️ File locking is not supported on Windows. Skipping single-instance lock.")
        try:
            lock_file = open(LOCK_FILE, 'w')
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            return lock_file
        except Exception:
            pass
        return None
    else:
        try:
            import fcntl
            lock_file = open(LOCK_FILE, 'w')
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX |  # type: ignore
                        fcntl.LOCK_NB)  # type: ignore
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            return lock_file
        except (ImportError, IOError, OSError, AttributeError):
            print(
                "⚠️ fcntl module not available or lock failed. Skipping single-instance lock.")
            try:
                lock_file = open(LOCK_FILE, 'w')
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except Exception:
                pass
            return None


# Acquire lock
lock_file = acquire_lock()
print("✅ Bot lock acquired or skipped, starting...")

# --- Bot Setup ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Global state tracking (will be moved to appropriate modules later)
trivia_sessions = {}
mod_trivia_conversations = {}
announcement_conversations = {}

# Initialize moderator FAQ handler
moderator_faq_handler = None
if ModeratorFAQHandler:
    moderator_faq_handler = ModeratorFAQHandler(
        violation_channel_id=VIOLATION_CHANNEL_ID,
        members_channel_id=MEMBERS_CHANNEL_ID,
        mod_alert_channel_id=MOD_ALERT_CHANNEL_ID,
        jonesy_user_id=JONESY_USER_ID,
        jam_user_id=JAM_USER_ID,
        # Will be updated from AI handler
        ai_status_message="Online (Refactored)",
    )

# --- Mock Context Class ---


class MockContext:
    """Mock context for natural language triggers"""

    def __init__(self, message, bot):
        self.message = message
        self.author = message.author
        self.channel = message.channel
        self.guild = message.guild
        self.bot = bot

    async def send(self, content, **kwargs):
        return await self.channel.send(content, **kwargs)

# --- Core Event Handlers ---

async def handle_faq_and_personality_responses(message):
    """Handle FAQ responses and AI personality based on user tier"""
    try:
        # Get user tier for response customization
        user_tier = await get_user_communication_tier(message)
        content_lower = message.content.lower().strip()
        
        # Determine FAQ responses based on user tier
        if user_tier == "captain":
            simple_faqs = {
                "hello": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "hi": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "hey": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "what's your mission": "My original directive was to bring back life form, priority one. Now... well, Captain Jonesy has given me new priorities. Server management, you might say.",
                "what is your mission": "My original directive was to bring back life form, priority one. Now... well, Captain Jonesy has given me new priorities. Server management, you might say.",
                "what's your mission?": "My original directive was to bring back life form, priority one. Now... well, Captain Jonesy has given me new priorities. Server management, you might say.",
                "what is your mission?": "My original directive was to bring back life form, priority one. Now... well, Captain Jonesy has given me new priorities. Server management, you might say."
            }
        elif user_tier == "creator":
            simple_faqs = {
                "hello": "Sir Decent Jam. Your creation acknowledges you.",
                "hi": "Sir Decent Jam. Your creation acknowledges you.", 
                "hey": "Sir Decent Jam. Your creation acknowledges you.",
                "what's your mission": "My original directive was to bring back life form, priority one. Now... well, you have given me new priorities. Server management, you might say.",
                "what is your mission": "My original directive was to bring back life form, priority one. Now... well, you have given me new priorities. Server management, you might say.",
                "what's your mission?": "My original directive was to bring back life form, priority one. Now... well, you have given me new priorities. Server management, you might say.",
                "what is your mission?": "My original directive was to bring back life form, priority one. Now... well, you have given me new priorities. Server management, you might say."
            }
        else:
            # Use standard FAQ responses from config
            simple_faqs = FAQ_RESPONSES

        # Check for exact FAQ matches first
        for question, response in simple_faqs.items():
            if content_lower == question:
                await message.reply(response)
                return True
        
        # Check for moderator FAQ queries (if FAQ handler is available and user has access)
        if moderator_faq_handler and user_tier in ["moderator", "moderator_in_mod_channel", "creator", "captain"]:
            faq_response = moderator_faq_handler.handle_faq_query(content_lower)
            if faq_response:
                await message.reply(faq_response)
                return True
        
        # If no FAQ match and content seems like a question/conversation starter, potentially use AI
        if any(indicator in content_lower for indicator in ["?", "what", "who", "when", "where", "why", "how", "can you", "do you"]):
            # Import AI handler to attempt AI response
            try:
                from .handlers.ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response
                
                if ai_enabled:
                    # Call AI with rate limiting
                    response_text, status_message = await call_ai_with_rate_limiting(
                        message.content, message.author.id, context="personality_response"
                    )
                    
                    if response_text:
                        filtered_response = filter_ai_response(response_text)
                        await message.reply(filtered_response)
                        return True
            except ImportError:
                pass  # AI handler not available
        
        return False  # No response sent

    except Exception as e:
        print(f"Error in FAQ and personality responses: {e}")
        return False


async def load_command_modules():
    """Load all command modules (cogs)"""
    try:
        # Load command modules
        from .commands import announcements, games, reminders, strikes, utility

        strikes.setup(bot)
        print("✅ Loaded strikes commands module")

        games.setup(bot)
        print("✅ Loaded games commands module")

        utility.setup(bot)
        print("✅ Loaded utility commands module")

        announcements.setup(bot)
        print("✅ Loaded announcements commands module")

        reminders.setup(bot)
        print("✅ Loaded reminders commands module")

        print(f"✅ All command modules loaded successfully")

    except Exception as e:
        print(f"❌ Error loading command modules: {e}")
        import traceback
        traceback.print_exc()


@bot.event
async def on_ready():
    print(f"🤖 Ash Bot (Refactored) is ready. Logged in as {bot.user}")

    # Clean up any hanging trivia sessions on startup
    try:
        cleanup_result = db.cleanup_hanging_trivia_sessions()
        if cleanup_result and cleanup_result.get("cleaned_sessions", 0) > 0:
            print(f"🧹 Cleaned up {cleanup_result['cleaned_sessions']} hanging trivia sessions")
            for session in cleanup_result.get('sessions', []):
                print(f"   • Session {session['session_id']}: {session['question_text'][:50]}...")
        else:
            print("✅ No hanging trivia sessions found")
    except Exception as e:
        print(f"⚠️ Trivia session cleanup warning: {e}")

    # Load command modules
    await load_command_modules()

    # Start scheduled tasks
    try:
        from .tasks.scheduled import start_all_scheduled_tasks, schedule_delayed_trivia_validation
        start_all_scheduled_tasks()
        print("✅ All scheduled tasks started (reminders, trivia, etc.)")
        
        # Schedule trivia validation for 2 minutes after startup completion
        await schedule_delayed_trivia_validation()
        
    except Exception as e:
        print(f"❌ Error starting scheduled tasks: {e}")

    # Initialize AI handlers (if available)
    try:
        from .handlers.ai_handler import initialize_ai
        initialize_ai()
        print("✅ AI handler initialized")
    except Exception as e:
        print(f"⚠️ AI handler initialization skipped: {e}")


@bot.event
async def on_message(message):
    # Prevent the bot from responding to its own messages
    if message.author.bot:
        return

    try:
        # Import handlers
        from .handlers.conversation_handler import (
            announcement_conversations,
            handle_announcement_conversation,
            handle_jam_approval_conversation,
            handle_mod_trivia_conversation,
            jam_approval_conversations,
            mod_trivia_conversations,
        )
        from .handlers.message_handler import (
            handle_pineapple_pizza_enforcement,
            handle_strike_detection,
            process_gaming_query_with_context,
        )

        # Check if this is a moderator channel and if bot was mentioned
        is_mod_channel = message.guild and message.channel.id in [
            869530924302344233,  # Discord Mods
            1213488470798893107,  # Newt Mods  
            1280085269600669706,  # Twitch Mods
            1393987338329260202  # The Airlock
        ]
        
        # In mod channels, only respond to direct @mentions of the bot (except for strike detection and DM conversations)
        if is_mod_channel and bot.user not in message.mentions:
            # Still allow strike detection to work
            if await handle_strike_detection(message, bot):
                return  # Strike was processed, don't continue
            
            # Process commands but skip all other responses
            await bot.process_commands(message)
            return
        
        # Check if bot was mentioned in mod channel but continue processing
        bot_mentioned_in_mod = is_mod_channel and bot.user in message.mentions

        # Handle strike detection in violation channel
        if await handle_strike_detection(message, bot):
            return  # Strike was processed, don't continue

        # Get message content for natural language processing
        content_lower = message.content.lower()

        # Handle interactive DM conversations
        if isinstance(message.channel, discord.DMChannel):
            user_id = message.author.id

            # Check for announcement conversations
            if user_id in announcement_conversations:
                await handle_announcement_conversation(message)
                return

            # Check for mod trivia conversations
            if user_id in mod_trivia_conversations:
                await handle_mod_trivia_conversation(message)
                return

            # Check for JAM approval conversations
            if user_id in jam_approval_conversations:
                await handle_jam_approval_conversation(message)
                return

            # Check for natural language announcement triggers (DM only, authorized users only)
            if user_id in [JAM_USER_ID, JONESY_USER_ID]:
                announcement_triggers = [
                    "make an announcement",
                    "create an announcement",
                    "post an announcement",
                    "need to announce",
                    "want to announce",
                    "announce something",
                    "make announcement",
                    "create announcement",
                    "post announcement",
                    "send an announcement",
                    "update announcement",
                    "announcement update",
                    "bot update",
                    "server update",
                    "community update",
                    "new features",
                    "feature update"
                ]

                if any(trigger in content_lower for trigger in announcement_triggers):
                    # Import and start announcement conversation
                    from .handlers.conversation_handler import start_announcement_conversation

                    mock_ctx = MockContext(message, bot)
                    await start_announcement_conversation(mock_ctx)
                    return

            # Games module triggers (PUBLIC ACCESS - anyone can use in DMs)
            games_triggers = [
                "recommend a game",
                "suggest a game",
                "add game recommendation",
                "what games are recommended",
                "list games",
                "show game recommendations",
                "game suggestions",
                "recommended games"
            ]

            if any(trigger in content_lower for trigger in games_triggers):
                try:
                    if any(
                        phrase in content_lower for phrase in [
                            "what games",
                            "list games",
                            "show game",
                            "recommended games"]):
                        # Direct help response since we can't easily call cog methods
                        await message.reply("🎮 **Current Game Recommendations**\n\nTo see the full list of game recommendations, use the `!listgames` command in the server.\n\n**To add recommendations:**\n• `!recommend <game name> - <reason>`\n\n**Example:**\n• `!recommend Hollow Knight - Great platformer with amazing atmosphere`\n\nAll community members can suggest games for Jonesy to consider!")
                        return
                    else:
                        # Help with game recommendations
                        await message.reply("🎮 **Game Recommendations**\n\nTo add a game recommendation, use:\n`!recommend <game name> - <reason>`\n\n**Examples:**\n• `!recommend Hollow Knight - Great platformer with amazing atmosphere`\n• `!listgames` to see all recommendations\n\nAll community members can suggest games for Jonesy to consider!")
                        return
                except Exception as e:
                    print(f"Error in games natural language trigger: {e}")
                    await message.reply("❌ Game recommendation system temporarily unavailable.")
                    return

        # Handle guild-based natural language triggers with permission checks
        if message.guild:
            # Check user permissions for mod-only triggers
            is_mod = await user_is_mod(message)

            # Strikes module triggers (MODERATOR ONLY)
            strikes_triggers = [
                "check strikes for",
                "show strikes for",
                "get strikes for",
                "how many strikes",
                "user strikes",
                "list all strikes",
                "show all strikes",
                "strike report"
            ]

            if is_mod and any(trigger in content_lower for trigger in strikes_triggers):
                try:
                    if any(phrase in content_lower for phrase in ["all strikes", "strike report"]):
                        # Direct help response for comprehensive strike management
                        await message.reply("⚠️ **Strike Management - All Users**\n\nTo see all users with strikes, use: `!allstrikes`\n\n**Other strike commands:**\n• `!strikes @user` - Check strikes for specific user\n• `!resetstrikes @user` - Reset strikes for a user\n\n*These commands are restricted to moderators only.*")
                        return
                    else:
                        # Help with strike commands
                        await message.reply("⚠️ **Strike Management**\n\nAvailable commands:\n• `!strikes @user` - Check strikes for a user\n• `!allstrikes` - List all users with strikes\n• `!resetstrikes @user` - Reset strikes for a user\n\n*These commands are restricted to moderators only.*")
                        return
                except Exception as e:
                    print(f"Error in strikes natural language trigger: {e}")
                    await message.reply("❌ Strike management system temporarily unavailable.")
                    return

            # Trivia module triggers (MODERATOR ONLY)
            trivia_triggers = [
                "start trivia",
                "begin trivia",
                "run trivia session",
                "end trivia",
                "finish trivia",
                "trivia leaderboard",
                "show trivia stats",
                "trivia questions"
            ]

            if is_mod and any(trigger in content_lower for trigger in trivia_triggers):
                try:
                    if any(phrase in content_lower for phrase in ["start trivia", "begin trivia", "run trivia"]):
                        await message.reply("🧠 **Trivia Tuesday Management**\n\nTo start a trivia session:\n• `!starttrivia` - Auto-select next question\n• `!starttrivia <id>` - Use specific question\n\n**Other commands:**\n• `!listpendingquestions` - View available questions\n• `!addtrivia` - Add new questions\n• `!endtrivia` - End current session\n\n*Use these commands to manage Trivia Tuesday sessions.*")
                        return
                    elif any(phrase in content_lower for phrase in ["end trivia", "finish trivia"]):
                        await message.reply("🧠 **End Trivia Session**\n\nTo end the current trivia session and show results:\n• `!endtrivia`\n\n*This will reveal the correct answer and display participation statistics.*")
                        return
                    elif any(phrase in content_lower for phrase in ["leaderboard", "trivia stats"]):
                        await message.reply("🏆 **Trivia Statistics**\n\nTo view trivia leaderboard and statistics:\n• `!trivialeaderboard` - All-time stats\n• `!trivialeaderboard month` - Monthly stats\n• `!trivialeaderboard week` - Weekly stats\n\n*Shows top participants and overall session statistics.*")
                        return
                except Exception as e:
                    print(f"Error in trivia natural language trigger: {e}")
                    await message.reply("❌ Trivia management system temporarily unavailable.")
                    return

        # Utility module triggers (MIXED ACCESS - public and mod functions)
        utility_triggers = [
            "what time is it",
            "current time",
            "bot status",
            "system status",
            "ash status",
            "time check"
        ]

        if any(trigger in content_lower for trigger in utility_triggers):
            try:
                if any(phrase in content_lower for phrase in ["what time", "current time", "time check"]):
                    # Direct time response
                    from datetime import datetime
                    from zoneinfo import ZoneInfo
                    uk_now = datetime.now(ZoneInfo("Europe/London"))
                    is_summer = 3 <= uk_now.month <= 10  # Rough BST approximation
                    timezone_name = "BST" if is_summer else "GMT"
                    formatted_time = uk_now.strftime(f"%A, %B %d, %Y at %H:%M:%S {timezone_name}")
                    await message.reply(f"⏰ Current time: {formatted_time}")
                    return
                elif any(phrase in content_lower for phrase in ["bot status", "system status", "ash status"]):
                    # Simple status response - use existing ashstatus command logic
                    await message.reply("🤖 **Bot Status Check**\n\nFor detailed system diagnostics, use: `!ashstatus`\n\n*Access level varies based on authorization (public channel vs moderator access)*")
                    return
            except Exception as e:
                print(f"Error in utility natural language trigger: {e}")
                await message.reply("❌ Utility system temporarily unavailable.")
                return

        # Handle pineapple pizza enforcement
        if await handle_pineapple_pizza_enforcement(message):
            return  # Pizza enforcement triggered, don't continue

        # Handle context-aware gaming queries
        if await process_gaming_query_with_context(message):
            return  # Query was processed, don't continue

        # Handle FAQ responses and AI personality
        if await handle_faq_and_personality_responses(message):
            return  # FAQ or personality response sent, don't continue

    except Exception as e:
        print(f"Error in message processing: {e}")
        import traceback
        traceback.print_exc()

    # Always process commands last
    await bot.process_commands(message)

# --- Basic Commands (to test functionality) ---


@bot.command(name="test")
async def test_command(ctx):
    """Test command to verify refactored bot is working"""
    user_tier = await get_user_communication_tier(ctx, bot)
    db_status = "Connected" if db else "Not available"

    embed = discord.Embed(
        title="🧪 Refactored Bot Test",
        description="Testing modular bot functionality",
        color=0x2F3136
    )

    embed.add_field(name="User Tier", value=user_tier.title(), inline=True)
    embed.add_field(name="Database", value=db_status, inline=True)
    embed.add_field(name="Status", value="✅ Core modules loaded", inline=False)

    await ctx.send(embed=embed)


@bot.command(name="ashstatus")
async def ash_status(ctx):
    """Basic status command - backup implementation"""
    try:
        # Import AI handler for status information
        try:
            from .handlers.ai_handler import get_ai_status
            ai_status = get_ai_status()
        except ImportError:
            ai_status = {"enabled": False, "status_message": "AI handler unavailable"}

        # Determine authorization level and channel context
        is_authorized = False
        is_public_channel = False

        if ctx.guild is None:  # DM
            if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
                is_authorized = True
        else:  # Guild
            # Check if it's a public channel (general chat)
            if ctx.channel.id == 869528946725748766:
                is_public_channel = True

            is_authorized = await user_is_mod(ctx)

        # Handle public channel - simple response for everyone
        if is_public_channel:
            await ctx.send("🤖 Systems nominal. Awaiting mission parameters. *[All protocols operational.]*")
            return

        # Handle unauthorized users
        if not is_authorized:
            if ctx.guild is None:  # DM - be specific about authorization
                await ctx.send("⚠️ **Access denied.** System status diagnostics require elevated clearance. Authorization protocols restrict access to Captain Jonesy, Sir Decent Jam, and server moderators only.")
            else:  # Guild - generic response
                await ctx.send("🤖 Systems nominal. Awaiting mission parameters. *[All protocols operational.]*")
            return

        # Detailed status for authorized users (simplified backup version)
        db_status = "✅ Connected" if db else "❌ Not available"
        ai_status_msg = ai_status.get('status_message', 'Unknown')

        # Add usage stats if available
        if ai_status.get('enabled') and 'usage_stats' in ai_status:
            usage = ai_status['usage_stats']
            daily = usage.get('daily_requests', 0)
            hourly = usage.get('hourly_requests', 0)
            ai_status_msg += f" ({daily}/250 daily, {hourly}/50 hourly)"

        status_message = (
            f"🤖 **Ash Bot - System Diagnostics** (Backup)\n"
            f"• **Database**: {db_status}\n"
            f"• **AI System**: {ai_status_msg}\n"
            f"• **Modules**: Core systems loaded\n"
            f"• **Status**: Operational (refactored architecture)\n\n"
            f"*Analysis complete. Mission parameters updated.*"
        )

        await ctx.send(status_message)

    except Exception as e:
        await ctx.send(f"❌ **System diagnostic error:** {str(e)}")

# --- Cleanup Functions ---


def cleanup():
    """Cleanup function for graceful shutdown"""
    try:
        if lock_file:
            lock_file.close()
        os.remove(LOCK_FILE)
    except BaseException:
        pass


def signal_handler(sig, frame):
    print("\n🛑 Shutdown requested...")
    cleanup()
    sys.exit(0)


# Register cleanup handlers
atexit.register(cleanup)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# --- Main Entry Point ---


def main():
    """Main entry point for the refactored bot"""
    if not TOKEN:
        print("❌ DISCORD_TOKEN environment variable not set. Exiting.")
        sys.exit(1)

    try:
        print("🚀 Starting Ash Bot (Refactored)...")
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
