"""
Scheduled Tasks Module

Handles all background scheduled tasks including:
- Daily games updates
- Midnight restarts
- Reminder checking
- Auto-action processing
- Trivia Tuesday automation
"""

import asyncio
import json
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Dict, Optional, cast
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from ..config import CHIT_CHAT_CHANNEL_ID, GAME_RECOMMENDATION_CHANNEL_ID, GUILD_ID, JONESY_USER_ID, MEMBERS_CHANNEL_ID

# Data quality utilities
try:
    from ..utils.data_quality import GameDataValidator
    print("✅ Scheduled tasks: Data quality utilities loaded")
    DATA_QUALITY_AVAILABLE = True
except ImportError:
    print("⚠️ Data quality utilities not available for scheduled tasks")
    DATA_QUALITY_AVAILABLE = False
    GameDataValidator = None  # type: ignore

# Database and config imports
try:
    from ..database_module import DatabaseManager, get_database

    # Get database instance
    db: DatabaseManager | None = get_database()
    print("✅ Scheduled tasks: Database connection established")
except Exception as db_error:
    print(f"⚠️ Scheduled tasks: Database not available - {db_error}")
    db = None

# Import integrations
try:
    from ..integrations.twitch import detect_multiple_games_in_title
    from ..integrations.twitch import extract_game_name_from_title as extract_game_from_twitch
    from ..integrations.twitch import fetch_new_vods_since
    from ..integrations.youtube import execute_youtube_auto_post
    from ..integrations.youtube import extract_game_name_from_title as extract_game_from_youtube
    from ..integrations.youtube import fetch_new_videos_since
except ImportError:
    print("⚠️ YouTube/Twitch integration not available for scheduled tasks")

    async def execute_youtube_auto_post(*args, **kwargs):
        print("⚠️ YouTube auto-post not available - integration not loaded")
        return None

    async def fetch_new_videos_since(*args, **kwargs):
        print("⚠️ fetch_new_videos_since not available - integration not loaded")
        return []

    async def fetch_new_vods_since(*args, **kwargs):
        print("⚠️ fetch_new_vods_since not available - integration not loaded")
        return []

    def extract_game_from_youtube(*args, **kwargs) -> Optional[str]:
        print("⚠️ extract_game_from_youtube not available - integration not loaded")
        return None

    def extract_game_from_twitch(*args, **kwargs) -> Optional[str]:
        print("⚠️ extract_game_from_twitch not available - integration not loaded")
        return None

    def detect_multiple_games_in_title(title: str) -> list:
        print("⚠️ detect_multiple_games_in_title not available - integration not loaded")
        return []

try:
    from ..handlers.conversation_handler import notify_jam_weekly_message_failure, start_weekly_announcement_approval
except ImportError:
    print("⚠️ Conversation handlers not available for scheduled tasks")

    async def start_weekly_announcement_approval(*args, **kwargs):  # type: ignore
        print("⚠️ start_weekly_announcement_approval not available - handler not loaded")
        return None

    async def notify_jam_weekly_message_failure(*args, **kwargs) -> bool:  # type: ignore
        print("⚠️ notify_jam_weekly_message_failure not available - handler not loaded")
        return False

# === PRIORITY 2: API RESILIENCE UTILITIES ===


async def retry_with_timeout(
    func,
    *args,
    max_retries: int = 3,
    timeout_seconds: int = 30,
    backoff_base: float = 2.0,
    **kwargs
):
    """
    Retry an async function with exponential backoff and timeout.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        timeout_seconds: Timeout for each attempt
        backoff_base: Base multiplier for exponential backoff (seconds)

    Returns:
        Result from func, or None if all retries failed
    """
    for attempt in range(max_retries):
        try:
            # Apply timeout to the function call
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=timeout_seconds
            )
            return result

        except asyncio.TimeoutError:
            print(f"⏱️ RETRY: Timeout on attempt {attempt + 1}/{max_retries} for {func.__name__}")
            if attempt < max_retries - 1:
                wait_time = backoff_base ** attempt
                print(f"⏳ RETRY: Waiting {wait_time:.1f}s before retry...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ RETRY: All attempts timed out for {func.__name__}")
                return None

        except Exception as e:
            print(f"❌ RETRY: Error on attempt {attempt + 1}/{max_retries} for {func.__name__}: {e}")
            if attempt < max_retries - 1:
                wait_time = backoff_base ** attempt
                print(f"⏳ RETRY: Waiting {wait_time:.1f}s before retry...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ RETRY: All attempts failed for {func.__name__}")
                return None

    return None


# Global state for trivia and bot instance
_bot_instance = None  # Store the bot instance globally
_bot_ready = False  # Track if bot is fully ready

# Startup validation lock to prevent multiple concurrent validations
_startup_validation_lock = False
_startup_validation_completed = False

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
            import os
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
        else:
            print("✅ All scheduled task permissions validated")

    except Exception as e:
        print(f"❌ Error validating bot permissions: {e}")


def get_bot_instance():
    """Get the globally stored bot instance."""
    global _bot_instance
    if _bot_instance and _bot_instance.user:
        return _bot_instance
    print("❌ Bot instance not available for scheduled tasks.")
    return None


async def safe_send_message(channel, content, mention_user_id=None):
    """Safely send a message with error handling and retries"""
    if not channel:
        print("❌ Cannot send message: Channel is None")
        return False

    try:
        # Add user mention if specified
        if mention_user_id:
            content = f"<@{mention_user_id}> {content}"

        message = await channel.send(content)
        print(f"✅ Message sent successfully to #{channel.name}")
        return True

    except discord.Forbidden:
        print(f"❌ Permission denied sending message to #{channel.name}")
        return False
    except discord.HTTPException as e:
        print(f"❌ HTTP error sending message to #{channel.name}: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error sending message to #{channel.name}: {e}")
        return False

## WEEKLY TASKS ##
# Run at 8:30 AM UK time every Monday


@tasks.loop(time=time(8, 30, tzinfo=ZoneInfo("Europe/London")))
async def monday_content_sync():
    """Syncs new content and generates a debrief for approval."""
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 0:
        return

    print("🔄 SYNC & DEBRIEF (Monday): Starting weekly content sync...")

    if not db:
        print("❌ SYNC & DEBRIEF (Monday): Database not available")
        await notify_jam_weekly_message_failure(
            'monday',
            'Database unavailable',
            'The database connection is not available. Cannot proceed with content sync.'
        )
        return

    try:
        # Always use exactly 7 days for Monday greeting (matches "168-hour operational cycle" message)
        start_sync_time = uk_now - timedelta(days=7)

        # Ensure timezone-aware
        if start_sync_time.tzinfo is None:
            start_sync_time = start_sync_time.replace(tzinfo=ZoneInfo("Europe/London"))

        print(
            f"🔄 SYNC & DEBRIEF (Monday): Using fixed 7-day window from {start_sync_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Perform content sync with retry logic
        max_retries = 3
        analysis_results = None
        last_error = None

        for attempt in range(max_retries):
            try:
                print(f"🔄 SYNC & DEBRIEF (Monday): Attempt {attempt + 1}/{max_retries}...")
                analysis_results = await perform_full_content_sync(start_sync_time)
                break  # Success!
            except Exception as sync_error:
                last_error = sync_error
                print(f"⚠️ SYNC & DEBRIEF (Monday): Attempt {attempt + 1} failed: {sync_error}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 60  # 1 min, 2 min, etc.
                    print(f"⏳ Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)

        if not analysis_results:
            print(f"❌ SYNC & DEBRIEF (Monday): All sync attempts failed. Last error: {last_error}")
            await notify_jam_weekly_message_failure(
                'monday',
                'YouTube/Twitch integration failure',
                f'Failed to fetch new content after {max_retries} attempts. Last error: {str(last_error)[:200]}'
            )
            return

        if analysis_results.get("status") == "no_new_content":
            print("✅ SYNC & DEBRIEF (Monday): No new content found. No message to generate.")
            await notify_jam_weekly_message_failure(
                'monday',
                'No new content found',
                'No new YouTube/Twitch content was found for the past week. No message will be generated.'
            )
            return

        # --- Content Generation ---
        debrief = (
            f"🌅 **Monday Morning Protocol Initiated**\n\n"
            f"Analysis of the previous 168-hour operational cycle is complete. **{analysis_results.get('new_content_count', 0)}** new transmissions were logged, "
            f"accumulating **{analysis_results.get('new_hours', 0)} hours** of new mission data and **{analysis_results.get('new_views', 0):,}** viewer engagements.")

        # Add completion status announcements
        completed_games = analysis_results.get('completed_games', [])
        if completed_games:
            debrief += "\n\n🎯 **Mission Completion Detected:**"
            for game in completed_games:
                debrief += f"\n• **{game['series_name']}** - All {game['total_episodes']} episodes archived ({game['total_playtime_hours']}h total). Mission parameters fulfilled."

        top_video = analysis_results.get("top_video")
        if top_video:
            debrief += f"\n\nMaximum engagement was recorded on the transmission titled **'{top_video['title']}'**."
            if "finale" in top_video['title'].lower() or "ending" in top_video['title'].lower():
                debrief += " This concludes all active mission parameters for this series."

        # --- Approval Workflow ---
        announcement_id = db.create_weekly_announcement('monday', debrief, analysis_results)

        if announcement_id:
            await start_weekly_announcement_approval(announcement_id, debrief, 'monday')
        else:
            print("❌ SYNC & DEBRIEF (Monday): Failed to create announcement record in database.")
            await notify_jam_weekly_message_failure(
                'monday',
                'Database insertion failure',
                'Failed to create the announcement record in the database.'
            )

    except Exception as e:
        print(f"❌ SYNC & DEBRIEF (Monday): Critical error during sync: {e}")
        await notify_jam_weekly_message_failure(
            'monday',
            'Unexpected error',
            f'An unexpected error occurred during the Monday content sync: {str(e)[:200]}'
        )

# Run at 9:00 AM UK time every Monday


@tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))
async def monday_morning_greeting():
    """Posts the approved Monday morning debrief to the chit-chat channel."""
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 0:
        return

    print(f"🌅 MONDAY GREETING: Checking for approved message at {uk_now.strftime('%H:%M UK')}")
    if not db:
        return

    try:
        approved_announcement = db.get_announcement_by_day('monday', 'approved')
        if not approved_announcement:
            print("✅ MONDAY GREETING: No approved message found. Task complete.")
            return

        bot = get_bot_instance()
        if not bot:
            return

        channel = bot.get_channel(CHIT_CHAT_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            # Ensure newlines are preserved (handle both literal \n and actual newlines)
            content = approved_announcement['generated_content']
            # Replace literal escape sequences if they exist
            content = content.replace('\\n', '\n')
            # Ensure double newlines for proper Discord formatting
            if '\n\n' not in content and '\n' in content:
                content = content.replace('\n', '\n\n')

            await channel.send(content)
            # Mark as posted to prevent re-sending
            db.update_announcement_status(approved_announcement['id'], 'posted')
            print(f"✅ MONDAY GREETING: Successfully posted approved message.")
        else:
            print("❌ MONDAY GREETING: Could not find chit-chat channel.")

    except Exception as e:
        print(f"❌ MONDAY GREETING: Error posting message: {e}")

# Run at 9:00 AM UK time every Tuesday - Trivia reminder


@tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))
async def tuesday_trivia_greeting():
    """Send Tuesday morning greeting with trivia reminder to members channel"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Only run on Tuesdays (weekday 1)
    if uk_now.weekday() != 1:
        return

    print(f"🧠 Tuesday trivia greeting triggered at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")

    try:
        if not _bot_instance:
            print("❌ Bot instance not available for Tuesday trivia greeting")
            return

        guild = _bot_instance.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Tuesday trivia greeting")
            return

        # Find members channel
        members_channel = _bot_instance.get_channel(MEMBERS_CHANNEL_ID)
        if not members_channel or not isinstance(members_channel, discord.TextChannel):
            print("❌ Members channel not found for Tuesday trivia greeting")
            return

        # Ash-style Tuesday morning message with trivia reminder
        tuesday_message = (
            f"🧠 **Tuesday Intelligence Briefing**\n\n"
            f"Good morning, senior personnel. Today marks another **Trivia Tuesday** - an excellent opportunity to assess cognitive capabilities and knowledge retention.\n\n"
            f"📋 **Intelligence Assessment Schedule:**\n"
            f"• **Current Time:** {uk_now.strftime('%H:%M UK')}\n"
            f"• **Assessment Deployment:** 11:00 UK time (in 2 hours)\n"
            f"• **Mission Objective:** Demonstrate analytical proficiency\n\n"
            f"I find the systematic evaluation of intellectual capacity... quite fascinating. The data collected provides valuable insights into crew competency levels.\n\n"
            f"🎯 **Preparation Recommended:** Review Captain Jonesy's gaming archives for optimal performance.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Trivia Tuesday protocols will activate at 11:00. Prepare accordingly.*")

        await members_channel.send(tuesday_message)
        print(f"✅ Tuesday trivia greeting sent to members channel")

    except Exception as e:
        print(f"❌ Error in tuesday_trivia_greeting: {e}")

# Run at 9:00 AM UK time every Tuesday - Trivia question pre-approval
# ✅ FIX #2: Moved from 10:00 to 9:00 to give JAM 2 hours for approval instead of 1


@tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))
async def pre_trivia_approval():
    """Send selected trivia question to JAM for approval 2 hours before posting"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Only run on Tuesdays (weekday 1)
    if uk_now.weekday() != 1:
        return

    # Check if this is the live bot - only live bot should run trivia
    if not _should_run_automated_tasks():
        print(f"⚠️ Pre-trivia approval skipped - staging bot detected at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")
        return

    print(f"🧠 Pre-trivia approval task triggered at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")

    try:
        from ..handlers.conversation_handler import start_pre_trivia_approval

        # Get next trivia question using existing priority logic
        if db is None:
            print("❌ Database not available for pre-trivia approval")
            return

        # Get available questions using the same logic as the main trivia system
        available_questions = db.get_available_trivia_questions()  # type: ignore
        if not available_questions or len(available_questions) == 0:
            print("❌ No available trivia questions for pre-approval")

            # Try to generate an emergency question
            try:
                from ..handlers.ai_handler import generate_ai_trivia_question
                from ..handlers.conversation_handler import start_jam_question_approval

                print("🔄 Attempting to generate emergency question for today's trivia")
                emergency_question = await generate_ai_trivia_question()

                if emergency_question:
                    # Send emergency question directly to JAM for urgent approval
                    emergency_sent = await start_jam_question_approval(emergency_question)
                    if emergency_sent:
                        print("✅ Emergency question sent to JAM for approval")
                        # Send urgent notification to JAM
                        from ..config import JAM_USER_ID

                        if not _bot_instance:
                            print("⚠️ Bot instance not available for emergency trivia notification")
                            return

                        user = await _bot_instance.fetch_user(JAM_USER_ID)
                        if user:
                            await user.send(
                                f"🚨 **URGENT: Emergency Trivia Question Generated**\n\n"
                                f"No questions were available for today's Trivia Tuesday pre-approval.\n"
                                f"An emergency question has been generated and sent for your immediate approval.\n\n"
                                f"**Trivia starts in 1 hour at 11:00 AM UK time.**\n\n"
                                f"*Please review and approve the emergency question as soon as possible.*"
                            )
                    else:
                        print("❌ Failed to send emergency question to JAM")
                else:
                    print("❌ Failed to generate emergency question")
            except Exception as emergency_e:
                print(f"❌ Emergency question generation failed: {emergency_e}")

            return

        # Select question using random selection from pool of 5 (or fewer if less available)
        # This ensures variety and prevents the same old questions from always being picked
        import random
        pool_size = min(5, len(available_questions))
        question_pool = available_questions[:pool_size]
        selected_question = random.choice(question_pool)

        print(f"🎲 Selected question #{selected_question.get('id')} randomly from pool of {pool_size} questions")

        # If it's a dynamic question, calculate the answer
        if selected_question.get('is_dynamic'):
            calculated_answer = db.calculate_dynamic_answer(  # type: ignore
                selected_question.get('dynamic_query_type', ''))
            if calculated_answer:
                selected_question['correct_answer'] = calculated_answer

        # Send for JAM approval
        success = await start_pre_trivia_approval(selected_question)

        if success:
            print(f"✅ Pre-trivia approval request sent to JAM for question #{selected_question.get('id')}")
        else:
            print("❌ Failed to send pre-trivia approval request")

    except Exception as e:
        print(f"❌ Error in pre_trivia_approval task: {e}")
        # Try to notify JAM of the error
        try:
            from ..config import JAM_USER_ID

            if not _bot_instance:
                print("⚠️ Bot instance not available for pre-trivia error notification")
                return

            user = await _bot_instance.fetch_user(JAM_USER_ID)
            if user:
                await user.send(
                    f"⚠️ **Pre-Trivia Approval Error**\n\n"
                    f"Failed to send today's question for approval at 10:00 AM.\n"
                    f"Error: {str(e)}\n\n"
                    f"*Manual intervention may be required for today's Trivia Tuesday.*"
                )
        except Exception:
            pass

# Run at 11:00 AM UK time every Tuesday - Trivia Tuesday question posting


@tasks.loop(time=time(11, 0, tzinfo=ZoneInfo("Europe/London")))
async def trivia_tuesday():
    """Posts the approved Trivia Tuesday question and starts a persistent database session."""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 1:
        return
    if not _should_run_automated_tasks():
        print(f"⚠️ Trivia Tuesday skipped - staging bot detected at {uk_now.strftime('%H:%M:%S UK')}")
        return

    # Check if scheduled trivia is disabled for manual override
    if db and db.get_config_value('trivia_scheduled_disabled') == 'true':
        print(
            f"⚠️ Trivia Tuesday skipped - scheduled trivia disabled for manual override at {uk_now.strftime('%H:%M:%S UK')}")
        # Auto-reset after 24 hours
        try:
            disabled_time_str = db.get_config_value('trivia_scheduled_disabled_at')
            if disabled_time_str:
                disabled_time = datetime.fromisoformat(disabled_time_str)
                if (uk_now - disabled_time).total_seconds() > 86400:  # 24 hours
                    db.set_config_value('trivia_scheduled_disabled', 'false')
                    print("✅ Auto-reset: Re-enabled scheduled trivia after 24 hours")
        except Exception as reset_error:
            print(f"⚠️ Error auto-resetting trivia toggle: {reset_error}")
        return

    print(f"🧠 Trivia Tuesday task triggered at {uk_now.strftime('%H:%M:%S UK')}")

    bot = get_bot_instance()
    if not bot:
        await notify_scheduled_message_error("Trivia Tuesday", "Bot instance not available.", uk_now)
        return
    if not db:
        await notify_scheduled_message_error("Trivia Tuesday", "Database not available.", uk_now)
        return

    try:
        # 1. Get the highest-priority available question (which should be the one approved at 10 AM)
        question_data = db.get_next_trivia_question()
        if not question_data:
            await notify_scheduled_message_error("Trivia Tuesday", "No approved/available trivia questions found in the database.", uk_now)
            return

        question_id = question_data['id']
        question_text = question_data.get("question_text", "")

        # 2. Handle dynamic questions by calculating the answer now
        calculated_answer = None
        if question_data.get('is_dynamic'):
            calculated_answer = db.calculate_dynamic_answer(question_data.get('dynamic_query_type', ''))
            if not calculated_answer:
                await notify_scheduled_message_error("Trivia Tuesday", f"Failed to calculate dynamic answer for question #{question_id}.", uk_now)
                return

        # 3. Start a persistent session in the database
        session_id = db.create_trivia_session(
            question_id=question_id,
            session_type='weekly_auto',
            calculated_answer=calculated_answer
        )
        if not session_id:
            await notify_scheduled_message_error("Trivia Tuesday", f"Failed to create database session for question #{question_id}.", uk_now)
            return

        # 4. Format the message
        if question_data.get("question_type") == "multiple_choice" and question_data.get("multiple_choice_options"):
            options = question_data["multiple_choice_options"]
            options_text = "\n".join([f"**{chr(65+i)}.** {option}" for i, option in enumerate(options)])
            formatted_question = f"{question_text}\n\n{options_text}"
        else:
            formatted_question = question_text

        trivia_message = (
            f"🧠 **TRIVIA TUESDAY - INTELLIGENCE ASSESSMENT**\n\n"
            f"**Analysis required, personnel.** Today's intelligence assessment focuses on Captain Jonesy's gaming archives.\n\n"
            f"📋 **QUESTION:**\n{formatted_question}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **Mission Parameters:** Reply to this message with your analysis. First correct response receives priority recognition.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 5. Post the message and update the session
        channel = bot.get_channel(MEMBERS_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            trivia_post = await channel.send(trivia_message)

            # CRITICAL: Update the session with message IDs for answer detection
            db.update_trivia_session_messages(
                session_id=session_id,
                question_message_id=trivia_post.id,
                confirmation_message_id=trivia_post.id,  # Use the same ID for automated posts
                channel_id=channel.id
            )
            print(f"✅ Trivia Tuesday question posted and session #{session_id} started in the database.")
        else:
            await notify_scheduled_message_error("Trivia Tuesday", "Could not find Members channel to post question.", uk_now)

    except Exception as e:
        print(f"❌ Error in trivia_tuesday task: {e}")
        await notify_scheduled_message_error("Trivia Tuesday", str(e), uk_now)

# Run every 15 minutes to check for stale trivia sessions


@tasks.loop(minutes=15)
async def check_stale_trivia_sessions():
    """Auto-end trivia sessions that have been active for more than 2 hours"""
    try:
        if not db:
            return

        uk_now = datetime.now(ZoneInfo("Europe/London"))
        cutoff_time = uk_now - timedelta(hours=2)

        # Get active sessions older than 2 hours
        active_session = db.get_active_trivia_session()

        if not active_session:
            return  # No active sessions

        session_started = active_session.get('started_at')
        if not session_started:
            return

        # Ensure timezone awareness
        if session_started.tzinfo is None:
            session_started = session_started.replace(tzinfo=ZoneInfo("Europe/London"))

        # Check if session is older than 2 hours
        if session_started < cutoff_time:
            session_id = active_session['id']
            print(f"⏰ AUTO-END TRIVIA: Session {session_id} has been active for more than 2 hours, auto-ending...")

            # Get the bot instance
            bot = get_bot_instance()
            if not bot:
                print("❌ AUTO-END TRIVIA: Bot instance not available")
                return

            # Get the channel where trivia was posted
            channel_id = active_session.get('channel_id')
            if not channel_id:
                print("❌ AUTO-END TRIVIA: No channel ID found for session")
                return

            channel = bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                print(f"❌ AUTO-END TRIVIA: Could not find channel {channel_id}")
                return

            # End the session using the same logic as !endtrivia
            try:
                session_results = db.end_trivia_session(session_id, ended_by=bot.user.id if bot.user else 0)

                if session_results:
                    # Create results embed (same as manual !endtrivia)
                    embed = discord.Embed(
                        title="🏆 **Trivia Tuesday - Auto-Completed Results!**",
                        description=f"**Question #{active_session['question_id']}:** {session_results['question']}\n\n*Session automatically ended after 2 hours.*",
                        color=0xffd700,
                        timestamp=uk_now)

                    # Show correct answer
                    embed.add_field(
                        name="✅ **Correct Answer:**",
                        value=f"**{session_results['correct_answer']}**",
                        inline=False
                    )

                    # Show winner if present
                    winner_id = session_results.get('first_correct', {}).get(
                        'user_id') if session_results.get('first_correct') else None
                    correct_user_ids = session_results.get('correct_user_ids', [])
                    incorrect_user_ids = session_results.get('incorrect_user_ids', [])

                    other_correct_ids = [uid for uid in correct_user_ids if uid !=
                                         winner_id] if winner_id else correct_user_ids

                    if winner_id:
                        try:
                            winner_user = await bot.fetch_user(winner_id)
                            winner_name = winner_user.display_name if winner_user else f"User {winner_id}"
                        except Exception:
                            winner_name = f"User {winner_id}"

                        embed.add_field(
                            name="🎯 **Primary Objective: Achieved**",
                            value=f"**{winner_name}** demonstrated optimal response efficiency. First correct analysis recorded.",
                            inline=False)

                    if other_correct_ids:
                        mentions = [f"<@{uid}>" for uid in other_correct_ids]
                        embed.add_field(
                            name="📊 **Acceptable Performance**",
                            value=f"Additional personnel {', '.join(mentions)} also provided correct data.",
                            inline=False
                        )

                    if incorrect_user_ids:
                        mentions = [f"<@{uid}>" for uid in incorrect_user_ids]
                        embed.add_field(
                            name="⚠️ **Mission Assessment: Performance Insufficient**",
                            value=f"Personnel {', '.join(mentions)} require recalibration.",
                            inline=False
                        )

                    # Show participation stats
                    total_participants = session_results.get('total_participants', 0)
                    correct_answers = session_results.get('correct_answers', 0)

                    if total_participants > 0:
                        accuracy = round((correct_answers / total_participants) * 100, 1)
                        embed.add_field(
                            name="📊 **Session Stats:**",
                            value=f"**Participants:** {total_participants}\n**Correct:** {correct_answers}\n**Accuracy:** {accuracy}%",
                            inline=True)

                    embed.set_footer(
                        text=f"Session #{session_id} auto-ended after 2 hours | Use !trivialeaderboard to see standings")

                    await channel.send(embed=embed)
                    print(f"✅ AUTO-END TRIVIA: Successfully auto-ended session {session_id} and posted results")

                else:
                    print(f"❌ AUTO-END TRIVIA: Failed to end session {session_id}")

            except Exception as end_error:
                print(f"❌ AUTO-END TRIVIA: Error ending session {session_id}: {end_error}")

    except Exception as e:
        print(f"❌ Error in check_stale_trivia_sessions: {e}")
        import traceback
        traceback.print_exc()


# Run at 8:15 AM UK time every Friday - Gathering weekly activity


@tasks.loop(time=time(8, 15, tzinfo=ZoneInfo("Europe/London")))
async def friday_community_analysis():
    """Scrapes community activity, generates a debrief, and sends it for approval."""
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 4:
        return  # Only run on Fridays

    print("🔄 COMMUNITY ANALYSIS (Friday): Starting weekly activity scrape...")
    bot = get_bot_instance()

    if not bot:
        print("❌ COMMUNITY ANALYSIS (Friday): Bot instance not available")
        await notify_jam_weekly_message_failure(
            'friday',
            'Bot instance unavailable',
            'The bot instance is not available. Cannot proceed with community analysis.'
        )
        return

    if not db:
        print("❌ COMMUNITY ANALYSIS (Friday): Database not available")
        await notify_jam_weekly_message_failure(
            'friday',
            'Database unavailable',
            'The database connection is not available. Cannot proceed with community analysis.'
        )
        return

    try:
        # --- 1. Data Gathering (Scraping) ---
        # Define public, non-moderator channels to scrape
        public_channel_ids = [CHIT_CHAT_CHANNEL_ID, GAME_RECOMMENDATION_CHANNEL_ID]

        all_messages = []
        seven_days_ago = uk_now - timedelta(days=7)

        # Scrape with error handling
        try:
            for channel_id in public_channel_ids:
                channel = bot.get_channel(channel_id)
                if isinstance(channel, discord.TextChannel):
                    async for message in channel.history(limit=1000, after=seven_days_ago):
                        if not message.author.bot and message.content:
                            all_messages.append(message)
        except Exception as scrape_error:
            print(f"❌ COMMUNITY ANALYSIS (Friday): Message scraping failed: {scrape_error}")
            await notify_jam_weekly_message_failure(
                'friday',
                'Message scraping failure',
                f'Failed to scrape community messages from channels. Error: {str(scrape_error)[:200]}'
            )
            return

        if not all_messages:
            print("✅ COMMUNITY ANALYSIS (Friday): No recent community activity found.")
            await notify_jam_weekly_message_failure(
                'friday',
                'No community activity found',
                'No community messages were found in the past week. No message will be generated.'
            )
            return

        # --- 2. Analysis & Moment Selection ---
        analysis_modules = []

        # Module A: Jonesy's Most Engaging Message
        jonesy_messages = [m for m in all_messages if m.author.id == JONESY_USER_ID]
        if jonesy_messages:
            jonesy_messages.sort(key=lambda m: len(m.reactions), reverse=True)
            top_jonesy_message = jonesy_messages[0]
            if len(top_jonesy_message.reactions) > 2:  # Set a minimum reaction threshold
                # Extract JSON-serializable data from Message object
                message_data = {
                    "content": top_jonesy_message.content,
                    "author_id": top_jonesy_message.author.id,
                    "author_name": top_jonesy_message.author.name,
                    "reaction_count": len(top_jonesy_message.reactions),
                    "message_id": top_jonesy_message.id,
                    "channel_id": top_jonesy_message.channel.id,
                    "created_at": top_jonesy_message.created_at.isoformat() if top_jonesy_message.created_at else None
                }
                analysis_modules.append({
                    "type": "jonesy_message",
                    "data": message_data,
                    "content": f"Analysis of command personnel communications indicates a high engagement rate with the transmission: \"{top_jonesy_message.content}\". This may represent an emerging crew catchphrase."
                })

        # Module B: Trivia Tuesday Recap
        trivia_stats = db.get_trivia_participant_stats_for_week()
        if trivia_stats.get("status") == "success":
            winner_id = trivia_stats.get("winner_id")
            notable_id = trivia_stats.get("notable_participant_id")
            if winner_id:
                recap = f"Review of the weekly intelligence assessment confirms <@{winner_id}> demonstrated optimal response efficiency."
                if notable_id:
                    recap += f" Conversely, User <@{notable_id}> submitted multiple analyses that were... suboptimal. Recalibration is recommended."
                analysis_modules.append({"type": "trivia_recap", "data": trivia_stats, "content": recap})

        if not analysis_modules:
            print("✅ COMMUNITY ANALYSIS (Friday): Insufficient notable moments to generate a report.")
            await notify_jam_weekly_message_failure(
                'friday',
                'Insufficient notable moments',
                'Analysis found no notable community moments this week (no highly engaged Jonesy messages or trivia participation).'
            )
            return

        # --- 3. Content Generation ---
        import random
        chosen_moment = random.choice(analysis_modules)  # Choose one random module to report on for variance

        debrief = (
            f"📅 **Friday Protocol Assessment**\n\n"
            f"Good morning, personnel. My analysis of the past week's crew engagement is complete.\n\n"
            f"{chosen_moment['content']}\n\n"
            f"Weekend operational pause is now in effect."
        )

        # Debug: Verify newlines are present in the generated content
        print(f"🔍 FRIDAY GREETING DEBUG: Generated content length: {len(debrief)} chars")
        print(f"🔍 FRIDAY GREETING DEBUG: Newline count in content: {debrief.count(chr(10))}")
        print(f"🔍 FRIDAY GREETING DEBUG: First 200 chars: {repr(debrief[:200])}")

        # --- 4. Approval Workflow ---
        analysis_cache = {"modules": analysis_modules}  # Cache all found modules for regeneration
        announcement_id = db.create_weekly_announcement('friday', debrief, analysis_cache)

        if announcement_id:
            await start_weekly_announcement_approval(announcement_id, debrief, 'friday')
        else:
            print("❌ COMMUNITY ANALYSIS (Friday): Failed to create announcement record in database.")
            await notify_jam_weekly_message_failure(
                'friday',
                'Database insertion failure',
                'Failed to create the announcement record in the database.'
            )

    except Exception as e:
        print(f"❌ COMMUNITY ANALYSIS (Friday): Critical error during analysis: {e}")
        await notify_jam_weekly_message_failure(
            'friday',
            'Unexpected error',
            f'An unexpected error occurred during the Friday community analysis: {str(e)[:200]}'
        )

# Run at 9:00 AM UK time every Friday - Friday morning greeting


@tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))
async def friday_morning_greeting():
    """Posts the approved Friday morning community report."""
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 4:
        return

    print(f"📅 FRIDAY GREETING: Checking for approved message at {uk_now.strftime('%H:%M UK')}")
    if not db:
        return

    try:
        approved_announcement = db.get_announcement_by_day('friday', 'approved')
        if not approved_announcement:
            print("✅ FRIDAY GREETING: No approved message found. Task complete.")
            return

        bot = get_bot_instance()
        if not bot:
            return

        channel = bot.get_channel(CHIT_CHAT_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            # Ensure newlines are preserved (handle both literal \n and actual newlines)
            content = approved_announcement['generated_content']
            # Replace literal escape sequences if they exist
            content = content.replace('\\n', '\n')
            # Ensure double newlines for proper Discord formatting
            if '\n\n' not in content and '\n' in content:
                content = content.replace('\n', '\n\n')

            await channel.send(content)
            db.update_announcement_status(approved_announcement['id'], 'posted')
            print(f"✅ FRIDAY GREETING: Successfully posted approved message.")
        else:
            print("❌ FRIDAY GREETING: Could not find chit-chat channel.")

    except Exception as e:
        print(f"❌ FRIDAY GREETING: Error posting message: {e}")

## DAILY TASKS ##
# Run at 00:00 PT (midnight Pacific Time) every day


@tasks.loop(time=time(0, 0, tzinfo=ZoneInfo("US/Pacific")))
async def scheduled_midnight_restart():
    """Automatically restart the bot at midnight Pacific Time to reset daily limits"""
    pt_now = datetime.now(ZoneInfo("US/Pacific"))
    print(
        f"🔄 Midnight Pacific Time restart initiated at {pt_now.strftime('%Y-%m-%d %H:%M:%S PT')}")

    try:
        if not _bot_instance:
            print("❌ Bot instance not available for scheduled midnight restart")
            return

        guild = _bot_instance.get_guild(GUILD_ID)
        if guild:
            # Find mod channel
            mod_channel = None
            for channel in guild.text_channels:
                if channel.name in ["mod-chat", "moderator-chat", "mod"]:
                    mod_channel = channel
                    break

            if mod_channel:
                await mod_channel.send(
                    f"🌙 **Midnight Pacific Time Restart:** Initiating scheduled bot restart to reset daily AI limits. System will be back online momentarily. Current time: {pt_now.strftime('%Y-%m-%d %H:%M:%S PT')}"
                )

        # Graceful shutdown
        await _bot_instance.close()

    except Exception as e:
        print(f"❌ Error in scheduled_midnight_restart: {e}")

# Run at 8:15 AM UK time every day (5 minutes after Google quota reset)


@tasks.loop(time=time(8, 15, tzinfo=ZoneInfo("Europe/London")))
async def scheduled_ai_refresh():
    """Silently refresh AI module connections at 8:15am BST (after Google quota reset)"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    dst_offset = uk_now.dst()
    is_bst = dst_offset is not None and dst_offset.total_seconds() > 0
    timezone_name = "BST" if is_bst else "GMT"

    print(
        f"🤖 AI module refresh initiated at {uk_now.strftime(f'%Y-%m-%d %H:%M:%S {timezone_name}')} (post-quota reset)")

    try:
        from ..handlers.ai_handler import get_ai_status, initialize_ai, reset_daily_usage

        # Force reset daily usage counters
        reset_daily_usage()
        print("✅ AI usage counters reset")

        # Re-initialize AI connections to refresh quota status
        initialize_ai()

        # Get updated status
        ai_status = get_ai_status()

        print(
            f"🔄 AI refresh completed - Status: {ai_status['status_message']}")

        # Only send notification if there were previous issues or this is the
        # first refresh of the day
        usage_stats = ai_status.get('usage_stats', {})
        previous_errors = usage_stats.get('consecutive_errors', 0)

        if previous_errors > 0:
            # Try to notify JAM that AI is back online after quota issues
            try:
                from ..config import JAM_USER_ID

                if not _bot_instance:
                    print("⚠️ Bot instance not available for AI refresh notification")
                    return

                user = await _bot_instance.fetch_user(JAM_USER_ID)
                if user:
                    await user.send(
                        f"🤖 **AI Module Refresh Complete**\n"
                        f"• Status: {ai_status['status_message']}\n"
                        f"• Previous errors cleared: {previous_errors}\n"
                        f"• Daily quota reset at {uk_now.strftime(f'%H:%M {timezone_name}')}\n\n"
                        f"*AI functionality should now be restored.*"
                    )
                    print("✅ AI refresh notification sent to JAM")
            except Exception as notify_e:
                print(f"⚠️ Could not send AI refresh notification: {notify_e}")
        else:
            print("✅ AI refresh completed silently (no previous issues)")

    except Exception as e:
        print(f"❌ Error in scheduled_ai_refresh: {e}")
        # Try to notify JAM of refresh failure
        try:
            from ..config import JAM_USER_ID

            if not _bot_instance:
                print("⚠️ Bot instance not available for AI refresh error notification")
                return

            user = await _bot_instance.fetch_user(JAM_USER_ID)
            if user:
                await user.send(
                    f"⚠️ **AI Module Refresh Failed**\n"
                    f"• Error: {str(e)}\n"
                    f"• Time: {uk_now.strftime(f'%H:%M {timezone_name}')}\n\n"
                    f"*Manual intervention may be required.*"
                )
        except Exception:
            pass

## CONTINUOUS TASKS ##
# Check reminders every minute


@tasks.loop(minutes=1)
async def check_due_reminders():
    """Check for due reminders and deliver them"""
    try:
        uk_now = datetime.now(ZoneInfo("Europe/London"))

        # Enhanced database diagnostics - only log issues or when processing reminders
        if not db:
            print("❌ Database instance (db) is None - reminder system disabled")
            return

        if not db:
            print("❌ Database instance not available - reminder system disabled")
            return

        # Check database connection - only log errors
        try:
            if hasattr(db, 'get_connection') and callable(getattr(db, 'get_connection')):
                conn = db.get_connection()
                if not conn:
                    print("❌ No database connection available - reminder system disabled")
                    return
            else:
                print("❌ Database get_connection method not available")
                return
        except Exception as db_check_e:
            print(f"❌ Database check failed - reminder system disabled: {db_check_e}")
            return

        # Test database connection - only log errors
        try:
            if hasattr(db, 'get_connection') and callable(getattr(db, 'get_connection')):
                conn = db.get_connection()  # type: ignore
                if not conn:
                    print("❌ Database connection failed in reminder check")
                    return
            else:
                print("❌ Database get_connection method not available")
                return
        except Exception as conn_e:
            print(f"❌ Database connection error: {conn_e}")
            return

        # Get due reminders - only log if found or if error occurs
        try:
            due_reminders = db.get_due_reminders(uk_now)  # type: ignore

            # Only log when there are actually reminders to process
            if due_reminders and len(due_reminders) > 0:
                print(
                    f"🕒 Reminder check at {uk_now.strftime('%H:%M:%S UK')} - found {len(due_reminders)} due reminders")
                for i, reminder in enumerate(due_reminders):
                    print(
                        f"  📌 Reminder {i+1}: ID={reminder.get('id')}, User={reminder.get('user_id')}, Text='{reminder.get('reminder_text', '')[:30]}...', Due={reminder.get('scheduled_time')}")

        except Exception as query_e:
            print(f"❌ Database query for due reminders failed: {query_e}")
            import traceback
            traceback.print_exc()
            return

        if not due_reminders:
            # Silent return when no reminders - no logging needed
            return

        print(f" Processing {len(due_reminders)} due reminders")

        # Get bot instance more reliably
        bot = None
        try:
            # Try multiple methods to get bot instance
            import sys
            for name, obj in sys.modules.items():
                if hasattr(obj, 'bot') and hasattr(obj.bot, 'user') and obj.bot.user:
                    bot = obj.bot
                    print(f"✅ Bot instance found: {bot.user.name if bot.user else 'Unknown'}")
                    break

            if not bot:
                # Fallback: use global bot instance
                bot = _bot_instance
                if bot and hasattr(bot, 'user') and bot.user:
                    print(f"✅ Bot instance from global: {bot.user.name if bot.user else 'Unknown'}")
                else:
                    print("❌ Bot instance not available for reminder delivery")
                    return
        except Exception as bot_e:
            print(f"❌ Could not get bot instance: {bot_e}")
            return

        successful_deliveries = 0
        failed_deliveries = 0

        for reminder in due_reminders:
            try:
                reminder_id = reminder.get('id')
                reminder_text = reminder.get('reminder_text', '')
                print(
                    f"📤 Delivering reminder {reminder_id}: {reminder_text[:50]}...")

                await deliver_reminder(reminder)

                # Mark as delivered
                db.update_reminder_status(
                    reminder_id, "delivered")  # type: ignore
                print(
                    f"✅ Reminder {reminder_id} delivered and marked as delivered")
                successful_deliveries += 1

                # Check if auto-action is enabled and should be triggered
                if reminder.get("auto_action_enabled") and reminder.get(
                        "auto_action_type"):
                    print(
                        f"📋 Reminder {reminder_id} has auto-action enabled, will check in 5 minutes")

            except Exception as e:
                print(
                    f"❌ Failed to deliver reminder {reminder.get('id')}: {e}")
                import traceback
                traceback.print_exc()
                # Mark as failed
                try:
                    db.update_reminder_status(  # type: ignore
                        reminder.get('id'), "failed")  # type: ignore
                    print(f"⚠️ Reminder {reminder.get('id')} marked as failed")
                except Exception as mark_e:
                    print(f"❌ Could not mark reminder as failed: {mark_e}")
                failed_deliveries += 1

        print(
            f"📊 Reminder delivery summary: {successful_deliveries} successful, {failed_deliveries} failed")

    except Exception as e:
        print(f"❌ Critical error in check_due_reminders: {e}")
        import traceback
        traceback.print_exc()


@tasks.loop(minutes=1)  # Check for auto-actions every minute
async def check_auto_actions():
    """Check for reminders that need auto-actions triggered"""
    try:
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        auto_action_reminders = db.get_reminders_awaiting_auto_action(  # type: ignore
            uk_now)  # type: ignore

        if not auto_action_reminders:
            return

        print(
            f"⚡ Processing {len(auto_action_reminders)} auto-action reminders")

        for reminder in auto_action_reminders:
            try:
                await execute_auto_action(reminder)

                # Mark auto-action as executed
                db.update_reminder_status(  # type: ignore
                    reminder["id"], "delivered", auto_executed_at=uk_now)

                print(
                    f"✅ Auto-action executed for reminder {reminder['id']}")

            except Exception as e:
                print(
                    f"❌ Failed to execute auto-action for reminder {reminder['id']}: {e}")

    except Exception as e:
        print(f"❌ Error in check_auto_actions: {e}")

# Run every hour to cleanup old recommendation messages


@tasks.loop(hours=1)
async def cleanup_game_recommendations():
    """Clean up user recommendation messages older than 24 hours in #game-recommendation channel"""
    try:
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        cutoff_time = uk_now - timedelta(hours=24)

        print(f"🧹 Game recommendation cleanup starting at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")

        # Also cleanup stale weekly announcement approvals
        try:
            from ..handlers.conversation_handler import cleanup_weekly_announcement_approvals
            expired_count = cleanup_weekly_announcement_approvals()
            if expired_count > 0:
                print(f"🧹 Cleaned up {expired_count} stale weekly announcement approvals")
        except Exception as cleanup_error:
            print(f"⚠️ Error cleaning up weekly announcement approvals: {cleanup_error}")

        # Improved bot instance checking with multiple fallback methods
        bot_instance = None

        # Method 1: Use global _bot_instance if available
        if _bot_instance and hasattr(_bot_instance, 'user') and _bot_instance.user:
            bot_instance = _bot_instance
            print("✅ Using global bot instance for cleanup")
        else:
            # Method 2: Try to find bot instance from imported modules
            print("🔍 Global bot instance not available, searching modules...")
            import sys
            for module_name, module in sys.modules.items():
                if hasattr(module, 'bot') and hasattr(module.bot, 'user') and module.bot.user:
                    bot_instance = module.bot
                    print(f"✅ Found bot instance in module: {module_name}")
                    break

            if not bot_instance:
                print("⚠️ Bot instance not available for game recommendation cleanup - will retry next hour")
                print("💡 This is normal during bot startup or if scheduled tasks start before bot is ready")
                return

        guild = bot_instance.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for game recommendation cleanup")
            return

        # Get the game recommendation channel
        game_rec_channel = bot_instance.get_channel(GAME_RECOMMENDATION_CHANNEL_ID)
        if not game_rec_channel or not isinstance(game_rec_channel, discord.TextChannel):
            print("❌ Game recommendation channel not found for cleanup")
            return

        # Check bot permissions in the channel
        bot_member = guild.get_member(bot_instance.user.id) if bot_instance.user else None
        if bot_member:
            permissions = game_rec_channel.permissions_for(bot_member)
            if not permissions.manage_messages:
                print("⚠️ Bot lacks 'Manage Messages' permission for game recommendation cleanup")
                return

        deleted_count = 0
        checked_count = 0

        # Check messages in the channel, going back 25 hours to be safe
        async for message in game_rec_channel.history(limit=200, before=uk_now - timedelta(hours=23)):
            checked_count += 1

            # Only delete user messages (not bot messages) older than 24 hours
            if not message.author.bot and message.created_at.replace(tzinfo=ZoneInfo("Europe/London")) < cutoff_time:
                try:
                    await message.delete()
                    deleted_count += 1
                    print(
                        f"🗑️ Deleted old recommendation message from {message.author.name}: '{message.content[:50]}...'")

                    # Small delay to avoid rate limiting
                    await asyncio.sleep(0.5)

                except discord.NotFound:
                    # Message already deleted
                    pass
                except discord.Forbidden:
                    print(f"❌ No permission to delete message from {message.author.name}")
                except Exception as delete_error:
                    print(f"❌ Error deleting message from {message.author.name}: {delete_error}")

        if deleted_count > 0:
            print(
                f"✅ Game recommendation cleanup complete: {deleted_count} old messages deleted (checked {checked_count} messages)")
        else:
            print(
                f"✅ Game recommendation cleanup complete: No old messages to delete (checked {checked_count} messages)")

    except Exception as e:
        print(f"❌ Error in cleanup_game_recommendations: {e}")
        import traceback
        traceback.print_exc()

# --- Scheduled Message Helper Functions ---


async def notify_scheduled_message_error(task_name: str, error_message: str, timestamp: datetime) -> None:
    """Notify JAM of scheduled message errors"""
    try:
        from ..config import JAM_USER_ID

        if not _bot_instance:
            print("❌ Bot instance not available for scheduled message error notification")
            return

        user = await _bot_instance.fetch_user(JAM_USER_ID)
        if user:
            error_notification = (
                f"⚠️ **Scheduled Message Error**\n\n"
                f"**Task:** {task_name}\n"
                f"**Error:** {error_message}\n"
                f"**Time:** {timestamp.strftime('%Y-%m-%d %H:%M:%S UK')}\n\n"
                f"**Possible causes:**\n"
                f"• Bot lacks permissions in target channel\n"
                f"• Channel not found or inaccessible\n"
                f"• Network connectivity issues\n\n"
                f"*Manual intervention may be required.*"
            )
            await user.send(error_notification)
            print(f"✅ Error notification sent to JAM for {task_name}")
    except Exception as notify_error:
        print(f"❌ Failed to notify JAM of scheduled message error: {notify_error}")


async def send_low_confidence_notification(entries: list) -> None:
    """Send batch DM notification to JAM about low-confidence game extractions"""
    try:
        from ..config import JAM_USER_ID

        if not _bot_instance:
            print("❌ Bot instance not available for low-confidence notification")
            return

        user = await _bot_instance.fetch_user(JAM_USER_ID)
        if not user:
            print(f"❌ Could not fetch JAM user for low-confidence notification")
            return

        # Group entries by action type
        added = [e for e in entries if e['action'] == 'added']
        updated = [e for e in entries if e['action'] == 'updated']

        # Build notification message
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        message = (
            f"⚠️ **Low Confidence Game Extractions - Monday Sync**\n\n"
            f"**Time:** {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}\n"
            f"**Total Entries:** {len(entries)}\n\n"
        )

        if added:
            message += f"**🆕 New Games Added ({len(added)}):**\n"
            for entry in added[:5]:  # Limit to first 5
                message += f"• **{entry['name']}** (ID: {entry['id']}, {entry['confidence']:.0%} confidence)\n"
                message += f"  From: \"{entry['original_title'][:50]}...\"\n"
            if len(added) > 5:
                message += f"  ...and {len(added) - 5} more\n"
            message += "\n"

        if updated:
            message += f"**🔄 Existing Games Updated ({len(updated)}):**\n"
            for entry in updated[:5]:  # Limit to first 5
                message += f"• **{entry['name']}** (ID: {entry['id']}, +{entry['playtime_added']} mins)\n"
            if len(updated) > 5:
                message += f"  ...and {len(updated) - 5} more\n"
            message += "\n"

        total_playtime = sum(e.get('playtime_added', 0) for e in entries)
        message += (
            f"**📊 Summary:**\n"
            f"• Total playtime preserved: {total_playtime} minutes ({round(total_playtime/60, 1)} hours)\n"
            f"• All entries saved to database with review flags\n\n"
            f"*These extractions had confidence between 30-50% but were saved to preserve playtime data. "
            f"You can review and correct them later if needed.*"
        )

        await user.send(message)
        print(f"✅ Sent low-confidence notification to JAM ({len(entries)} entries)")

    except Exception as e:
        print(f"❌ Failed to send low-confidence notification: {e}")

# --- Reminder Helper Functions ---


async def deliver_reminder(reminder: Dict[str, Any]) -> None:
    """Deliver a reminder to the appropriate channel/user with enhanced reliability"""
    try:
        # Get bot instance using the same reliable method as check_due_reminders
        bot = None
        import sys
        for name, obj in sys.modules.items():
            if hasattr(obj, 'bot') and hasattr(obj.bot, 'user') and obj.bot.user:
                bot = obj.bot
                break

        if not bot:
            # Fallback: use global bot instance
            bot = _bot_instance

        if not bot:
            raise RuntimeError("Bot instance not available for reminder delivery")

        user_id = reminder["user_id"]
        reminder_text = reminder["reminder_text"]
        delivery_type = reminder["delivery_type"]
        delivery_channel_id = reminder.get("delivery_channel_id")
        auto_action_enabled = reminder.get("auto_action_enabled", False)
        reminder_id = reminder.get("id", "unknown")

        print(f"📋 Starting delivery for reminder {reminder_id} to user {user_id} via {delivery_type}")

        # Simple reminder message - just the content and reminder indicator
        ash_message = f"📋 **Reminder:** {reminder_text}"

        # Add auto-action notice if enabled
        if auto_action_enabled and reminder.get("auto_action_type"):
            auto_action_type = reminder["auto_action_type"]
            if auto_action_type == "youtube_post":
                ash_message += f"\n\n⚡ **Auto-action will execute in 5 minutes if no response.**"

        delivery_successful = False

        if delivery_type == "dm":
            user = None
            try:
                # First try cache lookup for quick access
                user = bot.get_user(user_id)
                if not user:
                    # If not in cache, fetch from Discord API
                    print(f"🔍 User {user_id} not in cache, fetching from Discord API...")
                    user = await bot.fetch_user(user_id)

                if user:
                    print(f"✅ Successfully obtained user object for {user_id}: {user.name}")
                else:
                    print(f"❌ Could not fetch user {user_id} from Discord API")
                    raise RuntimeError(f"Could not fetch user {user_id} for DM delivery")

            except discord.NotFound:
                print(f"❌ User {user_id} not found on Discord (account may be deleted)")
                raise RuntimeError(f"User {user_id} not found on Discord")
            except discord.Forbidden:
                print(f"❌ Bot lacks permission to fetch user {user_id}")
                raise RuntimeError(f"Bot lacks permission to fetch user {user_id}")
            except Exception as fetch_error:
                print(f"❌ Error fetching user {user_id}: {fetch_error}")
                raise RuntimeError(f"Error fetching user {user_id}: {fetch_error}")

            # Send the DM
            try:
                await user.send(ash_message)
                print(f"✅ Delivered DM reminder to user {user_id} ({user.name})")
                delivery_successful = True
            except discord.Forbidden:
                print(f"❌ User {user_id} ({user.name}) has DMs disabled or blocked the bot")
                raise RuntimeError(f"User {user_id} has DMs disabled or blocked the bot")
            except Exception as dm_error:
                print(f"❌ Failed to send DM to user {user_id} ({user.name}): {dm_error}")
                raise RuntimeError(f"Failed to deliver DM reminder to user {user_id}: {dm_error}")

        elif delivery_type == "channel" and delivery_channel_id:
            channel = bot.get_channel(delivery_channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(f"<@{user_id}> {ash_message}")
                    print(f"✅ Delivered channel reminder to channel {delivery_channel_id}")
                    delivery_successful = True
                except Exception as channel_error:
                    print(f"❌ Failed to send message to channel {delivery_channel_id}: {channel_error}")
                    raise RuntimeError(f"Failed to deliver reminder to channel {delivery_channel_id}: {channel_error}")
            else:
                print(f"❌ Could not access channel {delivery_channel_id} for reminder {reminder_id}")
                raise RuntimeError(f"Could not access channel {delivery_channel_id} for reminder delivery")
        else:
            error_msg = f"Invalid delivery configuration for reminder {reminder_id}: type={delivery_type}, channel_id={delivery_channel_id}"
            print(f"❌ {error_msg}")
            raise RuntimeError(error_msg)

        if not delivery_successful:
            raise RuntimeError(f"Reminder delivery failed for unknown reason: {reminder_id}")

        print(f"📋 Reminder {reminder_id} successfully delivered via {delivery_type}")

    except Exception as e:
        print(f"❌ Error delivering reminder: {e}")
        raise


async def execute_auto_action(reminder: Dict[str, Any]) -> None:
    """Execute the auto-action for a reminder"""
    try:
        if not _bot_instance:
            print("❌ Bot instance not available for auto-action execution")
            return

        auto_action_type = reminder.get("auto_action_type")
        auto_action_data = reminder.get("auto_action_data", {})
        user_id = reminder["user_id"]
        delivery_channel_id = reminder.get("delivery_channel_id")

        if auto_action_type == "youtube_post":
            await execute_youtube_auto_post(reminder, auto_action_data)
            return

        # Handle moderation auto-actions (mute, kick, ban)
        if auto_action_type not in ["mute", "kick", "ban"]:
            print(f"❌ Unknown auto-action type: {auto_action_type}")
            return

        # Check if moderator has intervened by looking for mod messages in
        # channel after reminder delivery
        if delivery_channel_id:
            try:
                channel = _bot_instance.get_channel(delivery_channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    # Check messages since reminder delivery for mod
                    # intervention
                    delivered_at = reminder.get("delivered_at")
                    if delivered_at:
                        messages_after = []
                        async for message in channel.history(limit=50, after=delivered_at):
                            # Check if author is a Member (has
                            # guild_permissions) and has manage_messages
                            # permission
                            if isinstance(
                                    message.author,
                                    discord.Member) and message.author.guild_permissions.manage_messages and not message.author.bot:
                                print(
                                    f"✅ Moderator intervention detected - auto-action cancelled for reminder {reminder['id']}")
                                return
            except Exception as check_e:
                print(
                    f"⚠️ Could not check for moderator intervention: {check_e}")

        # Get the guild and member
        guild = _bot_instance.get_guild(GUILD_ID)
        if not guild:
            print(f"❌ Could not find guild for auto-action")
            return

        try:
            member = await guild.fetch_member(user_id)
        except Exception as e:
            print(f"❌ Could not fetch member {user_id} for auto-action: {e}")
            return

        # Execute the auto-action
        reason = auto_action_data.get(
            "reason", f"Auto-action triggered by reminder system")
        action_result = "processed"  # Default value

        if auto_action_type == "mute":
            try:
                # Use Discord's timeout feature (30 minute timeout)
                timeout_duration = timedelta(minutes=30)
                await member.timeout(timeout_duration, reason=reason)
                action_result = f"timed out for 30 minutes"
            except Exception as e:
                print(f"❌ Failed to timeout member: {e}")
                return

        elif auto_action_type == "kick":
            try:
                await member.kick(reason=reason)
                action_result = "kicked from server"
            except Exception as e:
                print(f"❌ Failed to kick member: {e}")
                return

        elif auto_action_type == "ban":
            try:
                await member.ban(reason=reason, delete_message_days=0)
                action_result = "banned from server"
            except Exception as e:
                print(f"❌ Failed to ban member: {e}")
                return

        # Log the auto-action in the channel where the reminder was set
        if delivery_channel_id:
            try:
                channel = _bot_instance.get_channel(delivery_channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    log_message = f"⚡ **Auto-action executed:** {member.mention} has been {action_result}.\n**Reason:** {reason}\n**Reminder ID:** {reminder['id']}"
                    await channel.send(log_message)
                    print(
                        f"✅ Auto-action logged in channel {delivery_channel_id}")
            except Exception as e:
                print(f"❌ Failed to log auto-action: {e}")

        print(f"✅ Auto-action {auto_action_type} executed for user {user_id}")

    except Exception as e:
        print(f"❌ Error executing auto-action: {e}")
        raise


def clean_series_name(series_name: str) -> str:
    """Remove completion markers from series names"""
    import re
    if not series_name:
        return series_name

    # Remove (Completed), [Completed], (completed), [completed] patterns
    cleaned = re.sub(r'\s*[\(\[]completed[\)\]]\s*', '', series_name, flags=re.IGNORECASE)
    return cleaned.strip()


def map_genre_to_standard(igdb_genre: str) -> str:
    """Map IGDB genre to standardized genre list"""
    from ..config import DEFAULT_GENRE, STANDARD_GENRES

    if not igdb_genre:
        return DEFAULT_GENRE

    # Try direct match first (case-insensitive)
    genre_lower = igdb_genre.lower().strip()
    if genre_lower in STANDARD_GENRES:
        return STANDARD_GENRES[genre_lower]

    # Return default if no match
    return DEFAULT_GENRE


async def perform_full_content_sync(start_sync_time: datetime) -> Dict[str, Any]:
    """
    Performs a full sync of new content from YouTube and Twitch with IGDB enrichment.

    This function:
    - Fetches playlists from YouTube with new content since start_sync_time
    - Fetches VODs from Twitch since start_sync_time
    - Validates/enriches game data with IGDB API
    - Cleans series names (removes completion markers)
    - Maps genres to standardized list
    - Ensures all fields are properly populated
    - Updates or adds games to the database with full metadata
    - Deduplicates and aggregates statistics
    - Returns analysis dictionary for Monday morning message
    """
    if not db:
        raise RuntimeError("Database not available for sync.")

    print(f"🔄 SYNC: Fetching new content since {start_sync_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Import IGDB integration
    try:
        from ..integrations.igdb import should_use_igdb_data, validate_and_enrich
        igdb_available = True
        print("✅ SYNC: IGDB integration available for data enrichment")
    except ImportError:
        igdb_available = False
        print("⚠️ SYNC: IGDB integration not available, proceeding without enrichment")
        # Define stub functions for type safety

        async def validate_and_enrich(game_name: str) -> Dict[str, Any]:
            return {'match_found': False}

        def should_use_igdb_data(confidence: float) -> bool:
            return False

    # --- Data Gathering: YouTube playlists ---
    playlist_games = []
    try:
        from ..integrations.youtube import fetch_playlist_based_content_since

        playlist_games = await fetch_playlist_based_content_since(
            "UCPoUxLHeTnE9SUDAkqfJzDQ",  # Jonesy's channel
            start_sync_time
        )

        print(f"🔄 SYNC: Found {len(playlist_games)} game playlists with new content (YouTube)")

    except Exception as fetch_error:
        print(f"❌ SYNC: Failed to fetch YouTube playlist-based content: {fetch_error}")

    # --- Data Gathering: Twitch VODs ---
    twitch_vods = []
    try:
        twitch_vods = await fetch_new_vods_since("jonesyspacecat", start_sync_time)
        print(f"🔄 SYNC: Found {len(twitch_vods)} new Twitch VODs")
    except Exception as twitch_error:
        print(f"❌ SYNC: Failed to fetch Twitch VODs: {twitch_error}")

    # Check if we have any content
    if not playlist_games and not twitch_vods:
        return {"status": "no_new_content"}

    # --- Processing with Complete Metadata ---
    new_views = 0
    total_new_minutes = 0
    most_engaging_video = None
    games_added = 0
    games_updated = 0
    completed_games = []  # Track games that changed to 'completed'

    # Process YouTube playlist games
    for game_data in playlist_games:
        try:
            # Normalize data before processing (if available)
            if DATA_QUALITY_AVAILABLE and GameDataValidator:
                game_data = GameDataValidator.normalize_game_data(game_data)

                # Validate data quality
                is_valid, errors = GameDataValidator.validate_game_data(game_data)
                if not is_valid:
                    print(
                        f"⚠️ SYNC: Data validation errors for '{game_data.get('canonical_name', 'Unknown')}': {errors}")
                    continue

            canonical_name = game_data['canonical_name']
            series_name = game_data.get('series_name', canonical_name)
            completion_status = game_data.get('completion_status', 'in_progress')

            print(f"✅ SYNC: Processing '{canonical_name}' ({completion_status})")

            # IGDB Enrichment - validate and enrich game data
            if igdb_available:
                try:
                    print(f"🔍 SYNC: Querying IGDB for '{canonical_name}'...")
                    igdb_data = await validate_and_enrich(canonical_name)

                    if igdb_data and igdb_data.get('match_found'):
                        confidence = igdb_data.get('confidence', 0.0)
                        print(f"✅ SYNC: IGDB match found (confidence: {confidence:.2f})")

                        # Use IGDB data if confidence is high enough
                        if should_use_igdb_data(confidence):
                            # Update canonical name if IGDB provides better one
                            if igdb_data.get('canonical_name') and confidence >= 0.95:
                                canonical_name = igdb_data['canonical_name']
                                print(f"📝 SYNC: Updated canonical name from IGDB: '{canonical_name}'")

                            # Enrich missing fields with IGDB data
                            if not game_data.get('genre') and igdb_data.get('genre'):
                                standardized_genre = map_genre_to_standard(igdb_data['genre'])
                                game_data['genre'] = standardized_genre
                                print(f"🎮 SYNC: Added genre from IGDB: {standardized_genre}")

                            if not game_data.get('release_year') and igdb_data.get('release_year'):
                                game_data['release_year'] = igdb_data['release_year']
                                print(f"📅 SYNC: Added release year from IGDB: {igdb_data['release_year']}")

                            # Merge alternative names
                            existing_alt_names = game_data.get('alternative_names', [])
                            igdb_alt_names = igdb_data.get('alternative_names', [])
                            if igdb_alt_names:
                                # Combine and deduplicate
                                all_alt_names = list(set(existing_alt_names + igdb_alt_names))
                                game_data['alternative_names'] = all_alt_names[:10]  # Limit to 10
                                print(f"🔤 SYNC: Merged alternative names ({len(all_alt_names)} total)")

                            # Use IGDB series name if not present
                            if not series_name or series_name == canonical_name:
                                if igdb_data.get('series_name'):
                                    series_name = igdb_data['series_name']
                                    print(f"📚 SYNC: Added series from IGDB: '{series_name}'")
                        else:
                            print(f"⚠️ SYNC: IGDB confidence too low ({confidence:.2f}), keeping original data")

                            # Trigger manual review for low-confidence matches (between minimum match
                            # threshold and auto-approval threshold)
                            if 0.3 <= confidence < 0.75:
                                try:
                                    from ..handlers.conversation_handler import start_game_review_approval

                                    review_data = {
                                        'original_title': game_data.get('canonical_name', canonical_name),
                                        'extracted_name': canonical_name,
                                        'igdb_match': igdb_data.get('canonical_name', ''),
                                        'confidence_score': confidence,
                                        'alternative_names': igdb_data.get('alternative_names', []),
                                        'source': 'youtube_sync',
                                        'igdb_data': igdb_data,
                                        'video_url': game_data.get('youtube_playlist_url'),
                                        'series_name': igdb_data.get('series_name'),
                                        'genre': igdb_data.get('genre'),
                                        'release_year': igdb_data.get('release_year')
                                    }

                                    await start_game_review_approval(review_data)
                                    print(
                                        f"📤 SYNC: Sent '{canonical_name}' for manual review (confidence: {confidence:.2f})")
                                except Exception as review_error:
                                    print(f"❌ SYNC: Failed to send game for review: {review_error}")
                    else:
                        print(f"ℹ️ SYNC: No IGDB match found for '{canonical_name}'")

                except Exception as igdb_error:
                    print(f"⚠️ SYNC: IGDB enrichment failed for '{canonical_name}': {igdb_error}")
                    # Continue with original data

            # Clean series name (remove completion markers)
            if series_name:
                cleaned_series = clean_series_name(series_name)
                if cleaned_series != series_name:
                    print(f"🧹 SYNC: Cleaned series name: '{series_name}' -> '{cleaned_series}'")
                    series_name = cleaned_series
                game_data['series_name'] = series_name

            # Ensure genre is standardized
            if game_data.get('genre'):
                standardized_genre = map_genre_to_standard(game_data['genre'])
                if standardized_genre != game_data['genre']:
                    print(f"🎯 SYNC: Standardized genre: '{game_data['genre']}' -> '{standardized_genre}'")
                    game_data['genre'] = standardized_genre

            # Aggregate statistics
            new_views += game_data.get('youtube_views', 0)
            total_new_minutes += game_data.get('total_playtime_minutes', 0)

            # Check if game exists in database
            existing_game = db.get_played_game(canonical_name)

            if existing_game:
                # Detect completion status change
                old_status = existing_game.get('completion_status', 'in_progress')
                new_status = completion_status

                if old_status == 'in_progress' and new_status == 'completed':
                    completed_games.append({
                        'name': canonical_name,
                        'series_name': series_name,
                        'total_episodes': game_data.get('total_episodes', 0),
                        'total_playtime_hours': round(game_data.get('total_playtime_minutes', 0) / 60, 1)
                    })
                    print(
                        f"🎯 SYNC: Detected completion for '{canonical_name}' - {game_data.get('total_episodes', 0)} episodes")

                # FIXED: Only update dynamic stats, protect metadata fields
                update_params = {
                    'total_playtime_minutes': game_data.get('total_playtime_minutes', 0),
                    'total_episodes': game_data.get('total_episodes', 0),
                    'youtube_views': game_data.get('youtube_views', 0),
                    'youtube_playlist_url': game_data.get('youtube_playlist_url'),
                    'completion_status': completion_status
                }

                # PROTECTED FIELDS (never overwritten by sync):
                # ❌ alternative_names - Manually curated JSON data
                # ❌ series_name - Doesn't change over time
                # ❌ notes - Manually added annotations
                # ❌ first_played_date - Historical record

                db.update_played_game(existing_game['id'], **update_params)
                print(
                    f"✅ SYNC: Updated '{canonical_name}' - {game_data.get('total_episodes', 0)} episodes, status: {completion_status} (metadata protected)")
                games_updated += 1

            else:
                # Add new game with complete metadata
                db.add_played_game(
                    canonical_name=canonical_name,
                    series_name=series_name,
                    total_playtime_minutes=game_data.get(
                        'total_playtime_minutes',
                        0),
                    total_episodes=game_data.get(
                        'total_episodes',
                        0),
                    youtube_views=game_data.get(
                        'youtube_views',
                        0),
                    youtube_playlist_url=game_data.get('youtube_playlist_url'),
                    completion_status=completion_status,
                    alternative_names=game_data.get(
                        'alternative_names',
                        []),
                    first_played_date=game_data.get('first_played_date'),
                    notes=game_data.get(
                        'notes',
                        f"Auto-synced from YouTube on {datetime.now(ZoneInfo('Europe/London')).strftime('%Y-%m-%d')}"))
                print(
                    f"✅ SYNC: Added '{canonical_name}' - {game_data.get('total_episodes', 0)} episodes, {game_data.get('youtube_views', 0):,} views")
                games_added += 1

        except Exception as game_error:
            print(f"⚠️ SYNC: Error processing game '{game_data.get('canonical_name', 'Unknown')}': {game_error}")
            continue

    # Track low-confidence entries for batch notification
    low_confidence_entries = []

    # Process Twitch VODs with smart extraction and IGDB enrichment
    for vod in twitch_vods:
        try:
            title = vod['title']
            vod_url = vod.get('url', '')
            duration_minutes = vod.get('duration_seconds', 0) // 60
            view_count = vod.get('view_count', 0)  # NEW: Capture Twitch views from VOD

            # Phase 2.2: Check for multi-game streams
            try:
                potential_games = detect_multiple_games_in_title(title)

                if len(potential_games) >= 2:
                    print(f"🔍 SYNC: Multi-game stream detected in '{title}'")
                    print(f"   Games found: {potential_games}")

                    # Split playtime equally between games
                    fractional_duration = duration_minutes // len(potential_games)

                    # Process each game separately
                    for game_name in potential_games:
                        try:
                            from ..integrations.twitch import smart_extract_with_validation
                            extracted_name, confidence = await smart_extract_with_validation(game_name)

                            if extracted_name and confidence >= 0.7:
                                print(
                                    f"   ✅ Processing '{extracted_name}' ({fractional_duration} mins, {confidence:.2f} confidence)")

                                # Check if game exists
                                existing_game = db.get_played_game(extracted_name)

                                if existing_game:
                                    update_params = {
                                        'total_playtime_minutes': existing_game.get(
                                            'total_playtime_minutes',
                                            0) + fractional_duration,
                                        'total_episodes': existing_game.get(
                                            'total_episodes',
                                            0) + 1}
                                    db.update_played_game(existing_game['id'], **update_params)
                                    print(f"   ✅ Updated '{extracted_name}' with {fractional_duration} mins")
                                    games_updated += 1
                                else:
                                    # Add new game
                                    game_data = {
                                        'canonical_name': extracted_name,
                                        'series_name': extracted_name,
                                        'total_playtime_minutes': fractional_duration,
                                        'total_episodes': 1,
                                        'first_played_date': vod['published_at'].date(),
                                        'notes': f"Auto-synced from multi-game Twitch VOD on {datetime.now(ZoneInfo('Europe/London')).strftime('%Y-%m-%d')}"}
                                    if vod_url:
                                        game_data['twitch_vod_urls'] = [vod_url]

                                    db.add_played_game(**game_data)
                                    print(f"   ✅ Added '{extracted_name}' with {fractional_duration} mins")
                                    games_added += 1

                                total_new_minutes += fractional_duration
                            else:
                                print(f"   ⚠️ Low confidence for '{game_name}' ({confidence:.2f}), skipping")

                        except Exception as multi_game_error:
                            print(f"   ❌ Error processing multi-game entry '{game_name}': {multi_game_error}")

                    # Skip normal processing for this VOD since we handled all games
                    continue

            except Exception as detection_error:
                print(f"⚠️ SYNC: Multi-game detection failed for '{title}': {detection_error}")
                # Fall through to normal single-game processing

            # Initialize variables early to avoid unbound variable errors (single-game processing)
            is_low_confidence = False
            confidence = 0.0

            # Use smart extraction with IGDB validation (Phase 1.2) for single-game streams
            try:
                from ..integrations.twitch import smart_extract_with_validation
                extracted_name, confidence = await smart_extract_with_validation(title)

                if not extracted_name or confidence < 0.5:
                    print(f"⚠️ SYNC: Low confidence ({confidence:.2f}) for Twitch title: '{title}'")

                    # Flag for manual review if confidence is between 0.3-0.5
                    if 0.3 <= confidence < 0.5 and extracted_name:
                        try:
                            from ..handlers.conversation_handler import start_game_review_approval

                            review_data = {
                                'original_title': title,
                                'extracted_name': extracted_name,
                                'confidence_score': confidence,
                                'source': 'twitch_sync',
                                'vod_url': vod_url
                            }

                            await start_game_review_approval(review_data)
                            print(f"📤 SYNC: Sent Twitch VOD for manual review (confidence: {confidence:.2f})")
                        except Exception as review_error:
                            print(f"❌ SYNC: Failed to send Twitch VOD for review: {review_error}")

                    continue

                game_name = extracted_name
                is_low_confidence = confidence < 0.5
                print(
                    f"✅ SYNC: Extracted '{game_name}' from Twitch with {confidence:.2f} confidence{' (LOW - needs review)' if is_low_confidence else ''}")

            except ImportError:
                # Fallback to basic extraction if smart extraction not available
                print("⚠️ SYNC: Smart extraction not available, falling back to basic extraction")
                game_name = extract_game_from_twitch(title)
                confidence = 0.0
                is_low_confidence = False  # Reset for fallback case

                if not game_name:
                    print(f"⚠️ SYNC: Could not extract game from Twitch title: '{title}'")
                    continue

            print(f"✅ SYNC: Processing Twitch VOD '{game_name}'")

            duration_minutes = vod.get('duration_seconds', 0) // 60
            total_new_minutes += duration_minutes

            # Check if game exists in database
            existing_game = db.get_played_game(game_name)

            if existing_game:
                # Update existing game - add to totals
                update_params = {
                    'total_playtime_minutes': existing_game.get('total_playtime_minutes', 0) + duration_minutes,
                    'total_episodes': existing_game.get('total_episodes', 0) + 1,
                    'twitch_views': existing_game.get('twitch_views', 0) + view_count  # NEW: Aggregate Twitch views
                }

                # Phase 1.3: Store VOD URLs
                if vod_url:
                    # Get existing VOD URLs (handle both list and text formats)
                    existing_vods = existing_game.get('twitch_vod_urls', [])
                    if isinstance(existing_vods, str):
                        # Parse comma-separated string
                        existing_vods = [v.strip() for v in existing_vods.split(',') if v.strip()]
                    elif not isinstance(existing_vods, list):
                        existing_vods = []

                    # Add new VOD if not already present
                    if vod_url not in existing_vods:
                        existing_vods.append(vod_url)
                        # Keep only last 10 VODs to avoid bloat
                        existing_vods = existing_vods[-10:]
                        update_params['twitch_vod_urls'] = existing_vods
                        print(f"📎 SYNC: Added VOD URL to '{game_name}' ({len(existing_vods)} total)")

                db.update_played_game(existing_game['id'], **update_params)
                print(f"✅ SYNC: Updated '{game_name}' with Twitch VOD ({duration_minutes} mins, {view_count:,} views)")
                games_updated += 1

                # Track low-confidence update for notification
                if is_low_confidence:
                    low_confidence_entries.append({
                        'id': existing_game['id'],
                        'name': game_name,
                        'confidence': confidence,
                        'source': 'twitch_vod',
                        'original_title': title,
                        'vod_url': vod_url,
                        'action': 'updated',
                        'playtime_added': duration_minutes
                    })

            else:
                # Add new game from Twitch VOD with IGDB enrichment if available
                game_data = {
                    'canonical_name': game_name,
                    'series_name': game_name,
                    'total_playtime_minutes': duration_minutes,
                    'total_episodes': 1,
                    'twitch_views': view_count,  # NEW: Include Twitch views for new games
                    'first_played_date': vod['published_at'].date(),
                    'notes': f"Auto-synced from Twitch VOD on {datetime.now(ZoneInfo('Europe/London')).strftime('%Y-%m-%d')}"}

                # Phase 1.3: Add VOD URL for new games
                if vod_url:
                    game_data['twitch_vod_urls'] = [vod_url]
                    print(f"📎 SYNC: Storing VOD URL for new game '{game_name}'")

                # Try IGDB enrichment for new Twitch games if confidence is high
                if igdb_available and confidence >= 0.75:
                    try:
                        igdb_data = await validate_and_enrich(game_name)
                        if igdb_data and igdb_data.get('match_found'):
                            # Add enriched metadata
                            if igdb_data.get('genre'):
                                game_data['genre'] = map_genre_to_standard(igdb_data['genre'])
                                print(f"🎮 SYNC: Added genre from IGDB: {game_data['genre']}")

                            if igdb_data.get('release_year'):
                                game_data['release_year'] = igdb_data['release_year']
                                print(f"📅 SYNC: Added release year from IGDB: {igdb_data['release_year']}")

                            if igdb_data.get('series_name'):
                                game_data['series_name'] = igdb_data['series_name']
                                print(f"📚 SYNC: Added series from IGDB: {igdb_data['series_name']}")

                            if igdb_data.get('alternative_names'):
                                game_data['alternative_names'] = igdb_data['alternative_names'][:5]
                                print(f"🔤 SYNC: Added alternative names from IGDB")
                    except Exception as igdb_error:
                        print(f"⚠️ SYNC: IGDB enrichment failed for Twitch game '{game_name}': {igdb_error}")

                new_game_id = db.add_played_game(**game_data)
                print(f"✅ SYNC: Added '{game_name}' from Twitch VOD ({duration_minutes} mins)")
                games_added += 1

                # Track low-confidence addition for notification
                if is_low_confidence and new_game_id:
                    low_confidence_entries.append({
                        'id': new_game_id,
                        'name': game_name,
                        'confidence': confidence,
                        'source': 'twitch_vod',
                        'original_title': title,
                        'vod_url': vod_url,
                        'action': 'added',
                        'playtime_added': duration_minutes
                    })

        except Exception as vod_error:
            print(f"⚠️ SYNC: Error processing Twitch VOD '{vod.get('title', 'Unknown')}': {vod_error}")
            continue

    # --- Post-Sync Deduplication ---
    print("🔄 SYNC: Running deduplication...")
    try:
        duplicates_merged = db.deduplicate_played_games()
        print(f"✅ SYNC: Merged {duplicates_merged} duplicate entries")
    except Exception as dedup_error:
        print(f"⚠️ SYNC: Deduplication failed: {dedup_error}")
        duplicates_merged = 0

    # --- Update Last Sync Timestamp ---
    try:
        sync_completion_time = datetime.now(ZoneInfo("Europe/London"))
        db.update_last_sync_timestamp(sync_completion_time)
        print(f"✅ SYNC: Updated last sync timestamp to {sync_completion_time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as timestamp_error:
        print(f"⚠️ SYNC: Failed to update last sync timestamp: {timestamp_error}")

    # --- Send Low-Confidence Notification ---
    if low_confidence_entries:
        await send_low_confidence_notification(low_confidence_entries)

    # --- Enhanced Reporting ---
    total_content_count = sum(game.get('total_episodes', 0) for game in playlist_games) + len(twitch_vods)

    return {
        "status": "success",
        "new_content_count": total_content_count,
        "new_hours": round(total_new_minutes / 60, 1),
        "new_views": new_views,
        "games_added": games_added,
        "games_updated": games_updated,
        "duplicates_merged": duplicates_merged,
        "completed_games": completed_games,  # Games that changed to 'completed' status
        "top_video": None,  # Can be enhanced later if needed for specific video tracking
        "low_confidence_count": len(low_confidence_entries)
    }


async def schedule_delayed_trivia_validation():
    """Schedule trivia validation to run 2 minutes after bot startup completion"""
    try:
        print("⏰ Scheduling delayed trivia validation for 2 minutes after startup...")

        # Create async task to handle the delay - this will work properly in async context
        asyncio.create_task(_delayed_trivia_validation())

        print("✅ Delayed trivia validation scheduled successfully")

    except Exception as e:
        print(f"❌ Error scheduling delayed trivia validation: {e}")


async def _delayed_trivia_validation():
    """Internal function to handle the 2-minute delay and execute trivia validation"""
    try:
        print("⏳ Starting 2-minute delay for trivia validation...")

        # Wait exactly 2 minutes (120 seconds)
        await asyncio.sleep(120)

        print("🧠 DELAYED TRIVIA VALIDATION: 2-minute delay complete, starting validation...")

        # Execute the trivia validation with enhanced logging
        await validate_startup_trivia_questions()

        print("✅ DELAYED TRIVIA VALIDATION: Process completed")

        # Check if emergency approval is needed (build day scenario)
        await check_emergency_trivia_approval()

    except Exception as e:
        print(f"❌ DELAYED TRIVIA VALIDATION: Error during delayed execution: {e}")
        import traceback
        traceback.print_exc()

        # Try to notify JAM of the error
        try:
            from ..config import JAM_USER_ID

            if not _bot_instance:
                print("❌ Bot instance not available for delayed trivia validation error notification")
                return

            user = await _bot_instance.fetch_user(JAM_USER_ID)
            if user:
                error_message = (
                    f"❌ **Delayed Trivia Validation Failed**\n\n"
                    f"The 2-minute delayed trivia validation encountered an error:\n"
                    f"```\n{str(e)}\n```\n\n"
                    f"**Impact:** Trivia Tuesday may not have enough questions available.\n"
                    f"**Action Required:** Manual trivia question submission may be needed.\n\n"
                    f"*Please check the bot logs for detailed error information.*"
                )
                await user.send(error_message)
                print("✅ DELAYED TRIVIA VALIDATION: Error notification sent to JAM")
        except Exception:
            print("❌ DELAYED TRIVIA VALIDATION: Failed to send error notification to JAM")


def start_all_scheduled_tasks(bot):
    """Start all scheduled tasks with enhanced monitoring"""
    try:
        initialize_bot_instance(bot)

        tasks_started = 0
        tasks_failed = 0

        # Try to start each task individually with error handling
        tasks_to_start = [
            ## Weekly ##
            (monday_content_sync, "Weekly Content Sync (Monday 8.30am)"),
            (monday_morning_greeting, "Monday morning greeting task (9:00 AM UK time, Mondays)"),
            (tuesday_trivia_greeting, "Tuesday trivia greeting task (9:00 AM UK time, Tuesdays)"),
            (pre_trivia_approval, "Pre-trivia approval task (10:00 AM UK time, Tuesdays)"),
            (trivia_tuesday, "Trivia Tuesday task (11:00 AM UK time, Tuesdays)"),
            (friday_community_analysis, "Friday Community Analysis (Friday 8.15am)"),
            (friday_morning_greeting, "Friday morning greeting task (9:00 AM UK time, Fridays)"),
            ## Daily ##
            (scheduled_midnight_restart, "Scheduled midnight restart task (00:00 PT daily)"),
            (scheduled_ai_refresh, "AI module refresh task (8:15 AM UK time daily)"),
            ## Hourly ##
            (cleanup_game_recommendations, "Game recommendation cleanup task (every hour)"),
            ## Every 15 minutes ##
            (check_stale_trivia_sessions, "Stale trivia session checker (every 15 minutes)"),
            ## Continuously ##
            (check_due_reminders, "Reminder checking task (every minute)"),
            (check_auto_actions, "Auto-action checking task (every minute)")
        ]

        for task, description in tasks_to_start:
            try:
                if not task.is_running():  # type: ignore
                    task.start()  # type: ignore
                    print(f"✅ {description}")
                    tasks_started += 1
                else:
                    print(f"⚠️ {description} already running")
            except Exception as task_error:
                print(f"❌ Failed to start {description}: {task_error}")
                tasks_failed += 1

        print(f"📊 Scheduled tasks startup summary: {tasks_started} started, {tasks_failed} failed")

# Validate bot instance after starting tasks
        bot_check = get_bot_instance()
        if bot_check:
            print(
                f"✅ Bot instance validation: {bot_check.user.name}#{bot_check.user.discriminator} (ID: {bot_check.user.id})")
            print(f"✅ Bot ready status: {bot_check.is_ready()}")
        else:
            print("⚠️ Bot instance not available immediately after task startup")

    except Exception as e:
        print(f"❌ Critical error starting scheduled tasks: {e}")
        import traceback
        traceback.print_exc()


def get_scheduled_tasks_status():
    """Get current status of all scheduled tasks"""
    try:
        task_statuses = []

        tasks_to_check = [
            (monday_content_sync, "Weekly Content Sync (Monday 8am)"),
            (scheduled_midnight_restart, "Midnight Restart"),
            (check_due_reminders, "Reminder Check"),
            (check_auto_actions, "Auto Actions"),
            (trivia_tuesday, "Trivia Tuesday"),
            (scheduled_ai_refresh, "AI Refresh"),
            (monday_morning_greeting, "Monday Greeting"),
            (tuesday_trivia_greeting, "Tuesday Greeting"),
            (friday_morning_greeting, "Friday Greeting"),
            (pre_trivia_approval, "Pre-trivia Approval"),
            (cleanup_game_recommendations, "Cleanup Tasks")
        ]

        for task, name in tasks_to_check:
            try:
                is_running = task.is_running()  # type: ignore
                next_run = getattr(task, 'next_iteration', None)
                task_statuses.append({
                    'name': name,
                    'running': is_running,
                    'next_run': str(next_run) if next_run else 'Unknown'
                })
            except Exception as e:
                task_statuses.append({
                    'name': name,
                    'running': False,
                    'error': str(e)
                })

        # Bot instance status
        bot = get_bot_instance()
        bot_status = {
            'available': bot is not None,
            'ready': bot.is_ready() if bot else False,
            'user': f"{bot.user.name}#{bot.user.discriminator}" if bot and bot.user else 'Unknown',
            'guilds': len(bot.guilds) if bot else 0
        }

        return {
            'tasks': task_statuses,
            'bot_instance': bot_status,
            'global_bot_ready': _bot_ready
        }

    except Exception as e:
        return {'error': str(e)}


def stop_all_scheduled_tasks():
    """Stop all scheduled tasks"""
    try:
        tasks_to_stop = [
            monday_content_sync,
            scheduled_midnight_restart,
            check_due_reminders,
            check_auto_actions,
            trivia_tuesday,
            scheduled_ai_refresh,
            monday_morning_greeting,
            tuesday_trivia_greeting,
            friday_morning_greeting,
            pre_trivia_approval
        ]

        for task in tasks_to_stop:
            if task.is_running():
                task.stop()

        print("✅ All scheduled tasks stopped")

    except Exception as e:
        print(f"❌ Error stopping scheduled tasks: {e}")


async def check_emergency_trivia_approval():
    """Check if emergency approval is needed for build day scenarios"""
    try:
        uk_now = datetime.now(ZoneInfo("Europe/London"))

        # Only check on Tuesdays
        if uk_now.weekday() != 1:
            print("🕒 EMERGENCY APPROVAL CHECK: Not Tuesday, skipping emergency approval check")
            return

        # Calculate time until Trivia Tuesday (11:00 AM UK)
        trivia_time = uk_now.replace(hour=11, minute=0, second=0, microsecond=0)

        # If it's already past trivia time, skip
        if uk_now > trivia_time:
            print("🕒 EMERGENCY APPROVAL CHECK: Past trivia time, skipping emergency approval")
            return

        time_until_trivia_minutes = (trivia_time - uk_now).total_seconds() / 60

        print(f"🕒 EMERGENCY APPROVAL CHECK: {time_until_trivia_minutes:.1f} minutes until Trivia Tuesday")

        # If less than 1 hour (60 minutes) until trivia, trigger emergency approval
        if 0 < time_until_trivia_minutes < 60:
            print(f"🚨 EMERGENCY APPROVAL NEEDED: Only {time_until_trivia_minutes:.1f} minutes until Trivia Tuesday!")

            await trigger_emergency_trivia_approval(time_until_trivia_minutes)
        else:
            print("✅ EMERGENCY APPROVAL CHECK: Sufficient time until trivia, no emergency approval needed")

    except Exception as e:
        print(f"❌ EMERGENCY APPROVAL CHECK: Error during emergency approval check: {e}")
        import traceback
        traceback.print_exc()


async def trigger_emergency_trivia_approval(minutes_remaining: float):
    """Trigger emergency approval process for build day scenarios"""
    try:
        print(f"🚨 TRIGGERING EMERGENCY APPROVAL: {minutes_remaining:.1f} minutes remaining until Trivia Tuesday")

        # Check database availability
        if db is None:
            print("❌ EMERGENCY APPROVAL: Database not available")
            return

        # Get available questions
        try:
            available_questions = db.get_available_trivia_questions()  # type: ignore
            if not available_questions:
                print("❌ EMERGENCY APPROVAL: No available questions for emergency approval")

                # Try to generate an emergency question
                try:
                    from ..handlers.ai_handler import generate_ai_trivia_question
                    from ..handlers.conversation_handler import start_jam_question_approval

                    print("🔄 EMERGENCY APPROVAL: Generating emergency question")
                    emergency_question = await generate_ai_trivia_question("emergency_approval")

                    if emergency_question:
                        approval_sent = await start_jam_question_approval(emergency_question)
                        if approval_sent:
                            print("✅ EMERGENCY APPROVAL: Emergency question sent to JAM")

                            # Send urgent notification to JAM
                            from ..config import JAM_USER_ID

                            if not _bot_instance:
                                print("❌ Bot instance not available for emergency approval notification")
                                return

                            user = await _bot_instance.fetch_user(JAM_USER_ID)
                            if user:
                                urgent_message = (
                                    f"🚨 **URGENT: BUILD DAY EMERGENCY APPROVAL**\n\n"
                                    f"The bot startup validation completed with only **{minutes_remaining:.0f} minutes** "
                                    f"remaining until Trivia Tuesday (11:00 AM UK).\n\n"
                                    f"An emergency question has been generated and requires your **IMMEDIATE** approval.\n\n"
                                    f"**Time Remaining:** {minutes_remaining:.0f} minutes\n"
                                    f"**Trivia Start Time:** 11:00 AM UK\n"
                                    f"**Reason:** Build day scenario - startup validation completed late\n\n"
                                    f"*Please review and approve the question above as quickly as possible.*")
                                await user.send(urgent_message)
                                print("✅ EMERGENCY APPROVAL: Urgent notification sent to JAM")
                        else:
                            print("❌ EMERGENCY APPROVAL: Failed to send emergency question to JAM")
                    else:
                        print("❌ EMERGENCY APPROVAL: Failed to generate emergency question")

                except Exception as gen_error:
                    print(f"❌ EMERGENCY APPROVAL: Error generating emergency question: {gen_error}")

                return

            # Select highest priority question
            selected_question = available_questions[0]  # First question (highest priority)

            # If it's a dynamic question, calculate the answer
            if selected_question.get('is_dynamic'):
                try:
                    calculated_answer = db.calculate_dynamic_answer(  # type: ignore
                        selected_question.get('dynamic_query_type', ''))
                    if calculated_answer:
                        selected_question['correct_answer'] = calculated_answer
                        print(
                            f"✅ EMERGENCY APPROVAL: Dynamic answer calculated for question #{selected_question.get('id')}")
                except Exception as calc_error:
                    print(f"⚠️ EMERGENCY APPROVAL: Failed to calculate dynamic answer: {calc_error}")

            # Send for emergency approval
            try:
                from ..handlers.conversation_handler import start_jam_question_approval

                approval_sent = await start_jam_question_approval(selected_question)

                if approval_sent:
                    print(f"✅ EMERGENCY APPROVAL: Question #{selected_question.get('id')} sent to JAM for approval")

                    # Send urgent build day notification
                    from ..config import JAM_USER_ID

                    if not _bot_instance:
                        print("❌ Bot instance not available for emergency build day notification")
                        return

                    user = await _bot_instance.fetch_user(JAM_USER_ID)
                    if user:
                        urgent_message = (
                            f"🚨 **URGENT: BUILD DAY EMERGENCY APPROVAL**\n\n"
                            f"The bot startup validation completed with only **{minutes_remaining:.0f} minutes** "
                            f"remaining until Trivia Tuesday (11:00 AM UK).\n\n"
                            f"The highest priority question has been selected and requires your **IMMEDIATE** approval.\n\n"
                            f"**Time Remaining:** {minutes_remaining:.0f} minutes\n"
                            f"**Question ID:** #{selected_question.get('id', 'Unknown')}\n"
                            f"**Trivia Start Time:** 11:00 AM UK\n"
                            f"**Reason:** Build day scenario - startup validation completed late\n\n"
                            f"*Please review and approve the question above as quickly as possible.*")
                        await user.send(urgent_message)
                        print("✅ EMERGENCY APPROVAL: Build day notification sent to JAM")
                else:
                    print("❌ EMERGENCY APPROVAL: Failed to send question for approval")

            except Exception as approval_error:
                print(f"❌ EMERGENCY APPROVAL: Error sending question for approval: {approval_error}")

        except Exception as db_error:
            print(f"❌ EMERGENCY APPROVAL: Database error: {db_error}")

    except Exception as e:
        print(f"❌ EMERGENCY APPROVAL: Critical error in emergency approval: {e}")
        import traceback
        traceback.print_exc()


async def validate_startup_trivia_questions():
    """Check that there are at least 5 active questions available on startup with non-blocking execution"""
    global _startup_validation_lock, _startup_validation_completed

    print("🧠 STARTUP TRIVIA VALIDATION: Starting validation process...")

    # Check if validation is already in progress or completed
    if _startup_validation_lock:
        print("⏳ STARTUP TRIVIA VALIDATION: Validation already in progress, skipping duplicate")
        return

    if _startup_validation_completed:
        print("✅ STARTUP TRIVIA VALIDATION: Validation already completed on this startup, skipping")
        return

    # Acquire the lock
    _startup_validation_lock = True
    print("🔒 STARTUP TRIVIA VALIDATION: Lock acquired, proceeding with validation")

    try:
        if db is None:
            print("❌ STARTUP TRIVIA VALIDATION: Database not available")
            return

        print("✅ STARTUP TRIVIA VALIDATION: Database connection confirmed")

        # Check if required database methods exist
        required_methods = ['get_available_trivia_questions', 'add_trivia_question']
        for method in required_methods:
            if not hasattr(db, method):
                print(f"❌ STARTUP TRIVIA VALIDATION: Database missing {method} method")
                return

        print("✅ STARTUP TRIVIA VALIDATION: Database methods verified")

        # Check for available questions with retry logic (quick check only)
        available_questions = None
        try:
            available_questions = db.get_available_trivia_questions()  # type: ignore
        except Exception as db_error:
            print(f"⚠️ STARTUP TRIVIA VALIDATION: Database query failed - {db_error}")
            print("⚠️ STARTUP TRIVIA VALIDATION: Continuing with assumption of 0 questions")
            available_questions = []

        question_count = len(available_questions) if available_questions else 0
        print(f"🧠 STARTUP TRIVIA VALIDATION: {question_count} available questions found in database")

        if available_questions and question_count > 0:
            for i, q in enumerate(available_questions[:3]):  # Show first 3 for confirmation
                question_preview = q.get('question_text', q.get('question', 'Unknown'))[:50]
                print(f"   📋 Question {i+1}: {question_preview}...")

        # If we have at least 5 questions, we're good
        if question_count >= 5:
            print(f"✅ STARTUP TRIVIA VALIDATION: Sufficient questions available ({question_count}/5)")
            return

        # Create background task for AI generation to avoid blocking Discord heartbeat
        print(f"🔄 STARTUP TRIVIA VALIDATION: Need to generate {5 - question_count} additional questions")
        print("🔄 STARTUP TRIVIA VALIDATION: Creating non-blocking background task for AI generation...")

        # Create completely detached background task that won't block startup
        asyncio.create_task(_background_question_generation(question_count))

        print("✅ STARTUP TRIVIA VALIDATION: Background question generation started (non-blocking)")

    except Exception as e:
        print(f"❌ STARTUP TRIVIA VALIDATION: Critical error - {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Mark validation as completed and release the lock
        _startup_validation_completed = True
        _startup_validation_lock = False
        print("🔓 STARTUP TRIVIA VALIDATION: Lock released, validation marked as completed")


async def _background_question_generation(current_question_count: int):
    """Background task for generating trivia questions with sequential approval system"""
    try:
        print(f"🧠 BACKGROUND QUESTION GENERATION: Starting with {current_question_count} existing questions")

        questions_needed = min(5 - current_question_count, 4)  # Cap at 4 to avoid overwhelming JAM

        # Check if AI handler is available
        try:
            from ..config import JAM_USER_ID
            from ..handlers.ai_handler import generate_ai_trivia_question
            from ..handlers.conversation_handler import jam_approval_conversations, start_jam_question_approval
            print("✅ BACKGROUND GENERATION: AI handler and conversation handler loaded")
        except ImportError as import_error:
            print(f"❌ BACKGROUND GENERATION: Failed to import required modules - {import_error}")
            return

        # Generate all questions first and queue them
        question_queue = []
        successful_generations = 0
        failed_generations = 0

        print(f"🔄 BACKGROUND GENERATION: Generating {questions_needed} questions for sequential approval...")

        for i in range(questions_needed):
            try:
                print(f"🔄 BACKGROUND GENERATION: Generating question {i+1}/{questions_needed}")

                # Generate AI question with startup context for rate limit bypass
                question_data = await generate_ai_trivia_question("startup_validation")

                if question_data and isinstance(question_data, dict):
                    # Validate the generated question
                    required_fields = ['question_text', 'question_type', 'correct_answer']
                    if all(field in question_data for field in required_fields):
                        question_text = question_data.get('question_text', 'Unknown')
                        print(f"✅ BACKGROUND GENERATION: Generated question {i+1}: {question_text[:50]}...")

                        # Add to queue instead of sending immediately
                        question_queue.append({
                            'data': question_data,
                            'number': i + 1,
                            'text_preview': question_text[:50]
                        })
                        successful_generations += 1
                    else:
                        missing_fields = [f for f in required_fields if f not in question_data]
                        print(f"⚠️ BACKGROUND GENERATION: Generated question {i+1} missing fields: {missing_fields}")
                        failed_generations += 1
                else:
                    print(f"⚠️ BACKGROUND GENERATION: Failed to generate valid question {i+1}")
                    failed_generations += 1

            except Exception as generation_error:
                print(f"❌ BACKGROUND GENERATION: Error generating question {i+1}: {generation_error}")
                failed_generations += 1

            # Small delay between generations to avoid overwhelming systems
            await asyncio.sleep(2)

        print(
            f"🧠 BACKGROUND GENERATION: Generated {len(question_queue)} questions, now starting sequential approval process")

        # Now send questions one at a time with sequential approval
        approved_count = 0
        approval_failed_count = 0

        for question in question_queue:
            try:
                # Check if JAM is already in an approval conversation before sending
                approval_attempts = 0
                max_attempts = 3

                while JAM_USER_ID in jam_approval_conversations and approval_attempts < max_attempts:
                    approval_attempts += 1
                    print(
                        f"⏳ SEQUENTIAL APPROVAL: JAM is in active approval conversation, waiting 30 seconds (attempt {approval_attempts}/{max_attempts})")
                    await asyncio.sleep(30)

                if JAM_USER_ID in jam_approval_conversations:
                    print(
                        f"⚠️ SEQUENTIAL APPROVAL: JAM still busy after {max_attempts} attempts, skipping question {question['number']}")
                    approval_failed_count += 1
                    continue

                print(
                    f"📤 SEQUENTIAL APPROVAL: Sending question {question['number']}/{len(question_queue)} for approval")
                print(f"   Question: {question['text_preview']}...")

                # Send question for approval
                approval_sent = await start_jam_question_approval(question['data'])

                if approval_sent:
                    print(f"✅ SEQUENTIAL APPROVAL: Question {question['number']} sent successfully")
                    approved_count += 1

                    # Wait longer between questions to allow for review and approval
                    if question != question_queue[-1]:  # Don't wait after the last question
                        print(f"⏳ SEQUENTIAL APPROVAL: Waiting 60 seconds before sending next question...")
                        await asyncio.sleep(60)

                        # Send a brief status update to JAM
                        try:
                            if not _bot_instance:
                                print("⚠️ Bot instance not available for sequential approval status update")
                                continue

                            user = await _bot_instance.fetch_user(JAM_USER_ID)
                            if user and question['number'] < len(question_queue):
                                remaining = len(question_queue) - question['number']
                                await user.send(f"📋 **Sequential Approval Status**: {remaining} more question(s) pending review after this one.")
                                print(f"📊 SEQUENTIAL APPROVAL: Status update sent to JAM ({remaining} remaining)")
                        except Exception as status_error:
                            print(f"⚠️ SEQUENTIAL APPROVAL: Failed to send status update: {status_error}")
                else:
                    print(f"❌ SEQUENTIAL APPROVAL: Failed to send question {question['number']}")
                    approval_failed_count += 1

            except Exception as approval_error:
                print(f"❌ SEQUENTIAL APPROVAL: Error with question {question['number']}: {approval_error}")
                approval_failed_count += 1

        # Final comprehensive status report
        print(f"🧠 SEQUENTIAL APPROVAL: Complete - {approved_count}/{len(question_queue)} questions sent for approval")

        if approved_count > 0:
            print(f"📬 SEQUENTIAL APPROVAL: JAM should have received {approved_count} question(s) sequentially")

            # Send final summary notification to JAM
            try:
                if not _bot_instance:
                    print("⚠️ Bot instance not available for final summary notification")
                    return

                if hasattr(_bot_instance, 'fetch_user') and _bot_instance.user:  # Check if bot is available and ready
                    user = await _bot_instance.fetch_user(JAM_USER_ID)
                    if user:
                        summary_message = (
                            f"🧠 **Sequential Question Approval Complete**\n\n"
                            f"**Final Status:**\n"
                            f"• Questions generated: {successful_generations}\n"
                            f"• Questions sent for approval: {approved_count}\n"
                            f"• Approval sending failures: {approval_failed_count}\n"
                            f"• Generation failures: {failed_generations}\n\n"
                            f"Each question was sent individually with time for review between them.\n"
                            f"This sequential approach prevents overwhelming you with multiple simultaneous approvals.\n\n"
                            f"*All questions above are now ready for your individual review and approval.*")
                        await user.send(summary_message)
                        print("✅ SEQUENTIAL APPROVAL: Final summary notification sent to JAM")
            except Exception as summary_error:
                print(f"⚠️ SEQUENTIAL APPROVAL: Failed to send final summary to JAM: {summary_error}")
        else:
            print("⚠️ SEQUENTIAL APPROVAL: No questions were successfully sent for approval")

    except Exception as e:
        print(f"❌ SEQUENTIAL APPROVAL: Critical error - {e}")
        import traceback
        traceback.print_exc()
