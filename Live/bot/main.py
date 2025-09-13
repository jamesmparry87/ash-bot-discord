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
db = get_database() # type: ignore

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

# --- Core Event Handlers ---


async def load_command_modules():
    """Load all command modules (cogs)"""
    try:
        # Load command modules
        from .commands import games, strikes, utility

        strikes.setup(bot)
        print("✅ Loaded strikes commands module")

        games.setup(bot)
        print("✅ Loaded games commands module")

        utility.setup(bot)
        print("✅ Loaded utility commands module")

        print(f"✅ All command modules loaded successfully")

    except Exception as e:
        print(f"❌ Error loading command modules: {e}")
        import traceback
        traceback.print_exc()


@bot.event
async def on_ready():
    print(f"🤖 Ash Bot (Refactored) is ready. Logged in as {bot.user}")

    # Load command modules
    await load_command_modules()

    # TODO: Start scheduled tasks
    # TODO: Initialize AI handlers


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
            handle_mod_trivia_conversation,
            mod_trivia_conversations,
        )
        from .handlers.message_handler import (
            handle_pineapple_pizza_enforcement,
            handle_strike_detection,
            process_gaming_query_with_context,
        )

        # Handle strike detection in violation channel
        if await handle_strike_detection(message, bot):
            return  # Strike was processed, don't continue

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

        # Handle pineapple pizza enforcement
        if await handle_pineapple_pizza_enforcement(message):
            return  # Pizza enforcement triggered, don't continue

        # Handle context-aware gaming queries
        if await process_gaming_query_with_context(message):
            return  # Query was processed, don't continue

        # TODO: Handle other AI personality responses and FAQ
        
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
    """Basic status command"""
    try:
        # Check user permissions
        is_authorized = False

        if ctx.guild is None:  # DM
            if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
                is_authorized = True
        else:  # Guild
            is_authorized = await user_is_mod(ctx)

        if not is_authorized:
            await ctx.send("Systems nominal, Sir Decent Jam. Awaiting Captain Jonesy's commands.")
            return

        # Basic status info for authorized users
        await ctx.send(
            f"🤖 Ash Bot (Refactored) Status:\n"
            f"Database: {'Connected' if db else 'Not available'}\n"
            f"Modules: Core systems loaded\n"
            f"Status: Operational (refactored architecture)\n\n"
            f"*Analysis complete. Mission parameters updated.*"
        )

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
