"""
Shared utilities for automated tasks.
Contains state management for the bot instance and environment detection.
"""

import asyncio
import os

import discord

from ..config import CHIT_CHAT_CHANNEL_ID, GAME_RECOMMENDATION_CHANNEL_ID, GUILD_ID, MEMBERS_CHANNEL_ID

# Global state for trivia and bot instance
_bot_instance = None  # Store the bot instance globally
_bot_ready = False  # Track if bot is fully ready

# Environment detection for staging vs live bot
_is_live_bot = None  # Cache the environment detection

def _detect_bot_environment():
    """
    Detect if this is the live bot or staging bot.
    Returns True if live bot, False if staging bot, None if undetermined.
    """
    global _is_live_bot

    if _is_live_bot is not None:
        return _is_live_bot  # Use cached result

    try:
        bot = get_bot_instance()
        if not bot or not bot.user:
            print("⚠️ ENVIRONMENT DETECTION: Bot instance not available")
            return None

        bot_id = bot.user.id

        LIVE_BOT_ID = 1393984585502687293
        STAGING_BOT_ID = 1413574803545395290

        if bot_id == LIVE_BOT_ID:
            _is_live_bot = True
            print(f"✅ ENVIRONMENT DETECTION: Live bot detected (ID: {bot_id})")
            return True
        elif STAGING_BOT_ID and bot_id == STAGING_BOT_ID:
            _is_live_bot = False
            print(f"✅ ENVIRONMENT DETECTION: Staging bot detected (ID: {bot_id})")
            return False
        else:
            # Fallback: check environment variables
            env_type = os.getenv('BOT_ENVIRONMENT', '').lower()
            if env_type == 'production':
                _is_live_bot = True
                print(f"✅ ENVIRONMENT DETECTION: Live bot detected via environment variable (ID: {bot_id})")
                return True
            elif env_type == 'staging':
                _is_live_bot = False
                print(f"✅ ENVIRONMENT DETECTION: Staging bot detected via environment variable (ID: {bot_id})")
                return False
            else:
                # Default: assume live for safety (better to have trivia than not)
                _is_live_bot = True
                print(f"⚠️ ENVIRONMENT DETECTION: Unknown bot ID {bot_id}, defaulting to live bot")
                return True

    except Exception as e:
        print(f"❌ ENVIRONMENT DETECTION: Error detecting environment - {e}")
        # Default to live for safety
        _is_live_bot = True
        return True


def _should_run_automated_tasks():
    """
    Check if scheduled trivia tasks should run (only on live bot).
    """
    try:
        is_live = _detect_bot_environment()
        if is_live is None:
            print("⚠️ AUTOMATED TASKS: Environment detection failed, allowing tasks to run")
            return True
        elif is_live:
            print("✅ AUTOMATED TASKS: Live bot confirmed, tasks enabled")
            return True
        else:
            print("⚠️ AUTOMATED TASKS: Staging bot detected, tasks disabled")
            return False
    except Exception as e:
        print(f"❌ AUTOMATED TASKS: Error checking environment - {e}")
        # Default to allowing tasks for safety
        return True


def initialize_bot_instance(bot):
    """Initialize the bot instance for scheduled tasks with validation"""
    global _bot_instance, _bot_ready

    try:
        if not bot or not hasattr(bot, 'user') or not bot.user:
            print("⚠️ Bot instance initialization failed: Bot not logged in")
            return False

        _bot_instance = bot
        _bot_ready = True

        print(f"✅ Scheduled tasks: Bot instance initialized and ready ({bot.user.name}#{bot.user.discriminator})")
        print(f"✅ Bot ID: {bot.user.id}, Guilds: {len(bot.guilds) if bot.guilds else 0}")

        # Test bot permissions in key channels
        asyncio.create_task(_validate_bot_permissions())

        return True

    except Exception as e:
        print(f"❌ Bot instance initialization failed: {e}")
        _bot_ready = False
        return False


async def _validate_bot_permissions():
    """Validate bot permissions in key channels"""
    try:
        if not _bot_instance or not _bot_ready:
            print("⚠️ Cannot validate permissions - bot not ready")
            return

        guild = _bot_instance.get_guild(GUILD_ID)
        if not guild:
            print(f"⚠️ Cannot find guild {GUILD_ID} for permission validation")
            return

        bot_member = guild.get_member(_bot_instance.user.id)
        if not bot_member:
            print("⚠️ Bot member not found in guild for permission validation")
            return

        # Check key channels
        channels_to_check = {
            'chit-chat': CHIT_CHAT_CHANNEL_ID,
            'members': MEMBERS_CHANNEL_ID,
            'game-recommendations': GAME_RECOMMENDATION_CHANNEL_ID
        }

        permission_issues = []

        for channel_name, channel_id in channels_to_check.items():
            try:
                channel = _bot_instance.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    perms = channel.permissions_for(bot_member)

                    missing_perms = []
                    if not perms.send_messages:
                        missing_perms.append('Send Messages')
                    if not perms.read_messages:
                        missing_perms.append('Read Messages')
                    if channel_name == 'game-recommendations' and not perms.manage_messages:
                        missing_perms.append('Manage Messages')

                    if missing_perms:
                        permission_issues.append(f"{channel_name}: {', '.join(missing_perms)}")
                    else:
                        print(f"✅ Permissions OK for #{channel_name}")
                else:
                    permission_issues.append(f"{channel_name}: Channel not accessible")

            except Exception as channel_error:
                permission_issues.append(f"{channel_name}: Error checking permissions - {channel_error}")

        if permission_issues:
            print("⚠️ Permission issues detected:")
            for issue in permission_issues:
                print(f"   • {issue}")

    except Exception as e:
        print(f"❌ Error validating bot permissions: {e}")


def get_bot_instance():
    """Get the globally stored bot instance."""
    global _bot_instance
    if _bot_instance and _bot_instance.user:
        return _bot_instance

    print("❌ Bot instance not available for scheduled tasks.")
    return None


def is_bot_ready():
    global _bot_ready
    return _bot_ready
