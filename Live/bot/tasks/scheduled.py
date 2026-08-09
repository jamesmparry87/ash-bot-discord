

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
import uuid
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Dict, Optional, cast
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from ..config import (
    CHIT_CHAT_CHANNEL_ID,
    GAME_RECOMMENDATION_CHANNEL_ID,
    GUILD_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    MEMBERS_CHANNEL_ID,
    POPS_ARCADE_USER_ID,
)
from .greetings import (
    friday_morning_greeting,
    monday_morning_greeting,
    pops_annual_birthday_greeting,
    tuesday_trivia_greeting,
)
from .sync_vods import monday_content_sync
from .trivia_preflight import (
    pre_trivia_approval,
    pre_trivia_preflight_check,
)
from .utils import (
    _detect_bot_environment,
    _should_run_automated_tasks,
    get_bot_instance,
    initialize_bot_instance,
    is_bot_ready,
)

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
    from ..database import DatabaseManager, get_database
    print("✅ Scheduled tasks: Database module imported successfully")
except Exception as db_error:
    print(f"⚠️ Scheduled tasks: Database import failed - {db_error}")
    def get_database(): return None  # type: ignore

from ..handlers.ai_handler import call_ai_with_rate_limiting, filter_ai_response
from ..persona.sarcasm import apply_pops_arcade_sarcasm

# Import integrations
try:
    from ..integrations.twitch import detect_multiple_games_in_title
    from ..integrations.twitch import extract_game_name_from_title as extract_game_from_twitch
    from ..integrations.twitch import fetch_new_vods_since, smart_extract_with_validation
    from ..integrations.youtube import execute_youtube_auto_post
    from ..integrations.youtube import extract_game_name_from_title as extract_game_from_youtube
    from ..integrations.youtube import fetch_playlist_based_content_since
except ImportError:
    print("⚠️ YouTube/Twitch integration not available for scheduled tasks")

    async def execute_youtube_auto_post(*args, **kwargs):
        print("⚠️ YouTube auto-post not available - integration not loaded")
        return None

    async def fetch_playlist_based_content_since(*args, **kwargs):
        print("⚠️ fetch_playlist_based_content_since not available - integration not loaded")
        return []

    async def fetch_new_vods_since(*args, **kwargs):
        print("⚠️ fetch_new_vods_since not available - integration not loaded")
        return []

    async def smart_extract_with_validation(title: str):
        print("⚠️ smart_extract_with_validation not available - integration not loaded")
        # Fallback to basic extraction with 0.0 confidence
        extracted = extract_game_from_twitch(title)
        return extracted, 0.0

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
    from ..handlers.conversations import notify_jam_weekly_message_failure, start_weekly_announcement_approval
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


# Need these directly imported since they are accessed globally in the file
# Global state for trivia and bot instance

_startup_validation_lock = False
_startup_validation_completed = False


# Apply schedules to the imported task functions

# ---------------------------------------------------------
# IMPORT TASK MODULES HERE TO AVOID CIRCULAR IMPORTS
# ---------------------------------------------------------

monday_content_sync = tasks.loop(time=time(8, 30, tzinfo=ZoneInfo("Europe/London")))(monday_content_sync)
monday_morning_greeting = tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))(monday_morning_greeting)
tuesday_trivia_greeting = tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))(tuesday_trivia_greeting)
pre_trivia_approval = tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))(pre_trivia_approval)
pre_trivia_preflight_check = tasks.loop(time=time(10, 45, tzinfo=ZoneInfo("Europe/London")))(pre_trivia_preflight_check)
friday_morning_greeting = tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))(friday_morning_greeting)
pops_annual_birthday_greeting = tasks.loop(
    time=time(9, 0, tzinfo=ZoneInfo("America/Chicago")))(pops_annual_birthday_greeting)


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

    # 1. Check if scheduled Trivia Tuesday is disabled
    db = get_database()
    if not db:
        print("❌ TRIVIA TUESDAY: Database not available")
        await notify_scheduled_message_error("Trivia Tuesday", "Database not available.", uk_now)
        return

    if db.get_config_value('trivia_scheduled_disabled') == 'true':
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
        # ✅ FIX #3: Try pre-approved question first, fallback to 'available' pool
        approved_question_id = None
        if db:
            try:
                approved_id_str = db.get_config_value('trivia_approved_question_id')
                if approved_id_str:
                    approved_question_id = int(approved_id_str)
                    print(f"✅ Found pre-approved question ID {approved_question_id} from 9 AM approval")
            except Exception as e:
                print(f"⚠️ Error reading approved question ID from config: {e}")

        # Get question data - try pre-approved first, then fallback to available pool
        question_data = None

        if approved_question_id:
            # STEP 1: Try to use pre-approved question
            try:
                question_data = db.get_trivia_question_by_id(approved_question_id)
                if question_data:
                    print(f"✅ Using pre-approved question #{approved_question_id} from 9 AM approval")
                    # Clear the config value after successful retrieval
                    try:
                        db.delete_config_value('trivia_approved_question_id')
                        print(f"✅ Cleared approved question ID from config")
                    except Exception as clear_error:
                        print(f"⚠️ Failed to clear approved question ID: {clear_error}")
                else:
                    print(
                        f"⚠️ Pre-approved question #{approved_question_id} not found in database, falling back to pool")
                    # Clear the invalid config value
                    try:
                        db.delete_config_value('trivia_approved_question_id')
                    except Exception:
                        pass
            except Exception as e:
                print(f"⚠️ Error retrieving pre-approved question #{approved_question_id}: {e}")
                # Continue to fallback

        if not question_data:
            # STEP 2: Fallback to querying available questions (same logic as manual !starttrivia)
            print("🔄 TRIVIA AUTO-START: No pre-approved question, querying available pool...")
            try:
                available_questions = db.get_available_trivia_questions()  # type: ignore

                if not available_questions or len(available_questions) == 0:
                    error_msg = "No available questions found in pool - trivia cannot run automatically. Use !starttrivia with a specific question ID or add new questions."
                    await notify_scheduled_message_error("Trivia Tuesday", error_msg, uk_now)
                    print(f"❌ TRIVIA BLOCKED: {error_msg}")
                    return

                # Select first available (highest priority - matches manual !starttrivia logic)
                question_data = available_questions[0]
                print(
                    f"✅ TRIVIA AUTO-START: Auto-selected question #{question_data['id']} from available pool ({len(available_questions)} questions available)")

                # NOTIFY JAM ABOUT FALLBACK
                try:
                    from ..config import JAM_USER_ID
                    if bot:
                        user = await bot.fetch_user(JAM_USER_ID)
                        if user:
                            await user.send(
                                f"⚠️ **Trivia Tuesday Auto-Fallback Triggered**\n\n"
                                f"No pre-approved question was found for today's Trivia Tuesday.\n"
                                f"The system has automatically selected and posted question #{question_data['id']} from the available pool.\n"
                                f"Pool size remaining: {len(available_questions) - 1}"
                            )
                except Exception as notify_err:
                    print(f"⚠️ Failed to send fallback notification: {notify_err}")

            except Exception as pool_error:
                error_msg = f"Error querying available questions pool: {pool_error}"
                await notify_scheduled_message_error("Trivia Tuesday", error_msg, uk_now)
                print(f"❌ TRIVIA BLOCKED: {error_msg}")
                return

        question_id = question_data['id']
        question_text = question_data.get("question_text", "")

        # 2. Handle dynamic questions by calculating the answer now
        calculated_answer = None
        if question_data.get('is_dynamic'):
            from bot.handlers.trivia.analytics import calculate_dynamic_answer
            calculated_answer = calculate_dynamic_answer(db, question_data.get('dynamic_query_type', ''))
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

        # 4. Format the message using shared formatting function for consistency
        from ..utils.trivia_formatting import create_trivia_question_embed

        embed = create_trivia_question_embed(
            question_data=question_data,
            session_id=session_id,
            started_by="Ash (Automated)"  # type: ignore
        )

        # 5. Post the message and update the session
        channel = bot.get_channel(MEMBERS_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            trivia_post = await channel.send(embed=embed)

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
        db = get_database()
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
        # IMPORTANT: PostgreSQL stores CURRENT_TIMESTAMP as UTC (naive).
        # We must label it as UTC first, then compare to the UK-aware cutoff_time.
        # Using ZoneInfo("Europe/London") here would incorrectly shift the time
        # by 1 hour during BST, making the session appear to have started 1 hour
        # earlier than it did - causing the auto-close to trigger after only 1 hour.
        if session_started.tzinfo is None:
            from datetime import timezone as _tz
            session_started = session_started.replace(tzinfo=_tz.utc)

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

    db = get_database()
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
                import re

                # Clean the message content
                clean_content = top_jonesy_message.content
                clean_content = re.sub(r'https?://\S+', '', clean_content)  # Remove URLs
                clean_content = clean_content.replace('\n', ' ').replace('\r', '')  # Remove newlines
                clean_content = ' '.join(clean_content.split())  # Clean whitespace

                if len(clean_content) > 120:
                    clean_content = clean_content[:117] + "..."

                # Extract JSON-serializable data from Message object
                message_data = {
                    "content": top_jonesy_message.content,  # Keep raw for data
                    "clean_content": clean_content,
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
                    "content": f"Analysis of command personnel communications indicates a high engagement rate with the transmission: \"{clean_content}\". This may represent an emerging crew catchphrase."
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

        # Module C: General Activity (Fallback)
        # Always available as long as there are messages, guarantees Friday greeting generates
        if all_messages:
            activity_recap = f"Total communication volume across monitored channels registered at **{len(all_messages)} transmissions** this week. Processing complete."
            analysis_modules.append({
                "type": "general_activity",
                "data": {"total_messages": len(all_messages)},
                "content": activity_recap
            })

        if not analysis_modules:
            print("✅ COMMUNITY ANALYSIS (Friday): Insufficient notable moments to generate a report.")
            await notify_jam_weekly_message_failure(
                'friday',
                'Insufficient notable moments',
                'Analysis found no notable community moments this week (no highly engaged Jonesy messages or trivia participation).'
            )
            return

        analysis_cache = {"modules": analysis_modules}  # Cache all found modules for regeneration

        from ..handlers.ai_handler import generate_weekly_report

        # Try dynamic AI generation first
        debrief = await generate_weekly_report('friday', analysis_cache)

        if not debrief:
            # Fallback to static message if AI is disabled or fails
            import random

            # Give preference to specific modules over the general fallback if possible
            specific_modules = [m for m in analysis_modules if m['type'] != 'general_activity']
            if specific_modules:
                chosen_moment = random.choice(specific_modules)
            else:
                chosen_moment = random.choice(analysis_modules)

            intros = [
                "Good morning, personnel. My analysis of the past week's crew engagement is complete.",
                "Attention crew. I have processed the weekly communication logs. The results are... as expected.",
                "Greetings. I have concluded my scheduled Friday assessment of your interpersonal data exchanges.",
                "Weekly diagnostic complete. I have evaluated the crew's recent communication patterns for optimal efficiency."]

            outros = [
                "Weekend operational pause is now in effect.",
                "You are now authorized to commence your weekend operational pause. Please ensure your biological functions remain intact until Monday.",
                "I recommend using the next 48 hours for biological rest. Operational pause is active.",
                "End of report. Please return to your designated leisure activities."]

            debrief = (
                f"📅 **Friday Protocol Assessment**\n\n"
                f"{random.choice(intros)}\n\n"
                f"{chosen_moment['content']}\n\n"
                f"{random.choice(outros)}"
            )

        # Debug: Verify newlines are present in the generated content
        print(f"🔍 FRIDAY GREETING DEBUG: Generated content length: {len(debrief)} chars")
        print(f"🔍 FRIDAY GREETING DEBUG: Newline count in content: {debrief.count(chr(10))}")
        print(f"🔍 FRIDAY GREETING DEBUG: First 200 chars: {repr(debrief[:200])}")

        # --- 4. Approval Workflow ---
        # --- 4. Approval Workflow ---
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

## DAILY TASKS ##
# Run at 00:00 PT (midnight Pacific Time) every day


@tasks.loop(time=time(0, 0, tzinfo=ZoneInfo("US/Pacific")))
async def scheduled_midnight_restart():
    """Automatically restart the bot at midnight Pacific Time to reset daily limits"""
    pt_now = datetime.now(ZoneInfo("US/Pacific"))
    print(
        f"🔄 Midnight Pacific Time restart initiated at {pt_now.strftime('%Y-%m-%d %H:%M:%S PT')}")

    try:
        if not get_bot_instance():
            print("❌ Bot instance not available for scheduled midnight restart")
            return

        guild = get_bot_instance().get_guild(GUILD_ID)  # type: ignore
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
        await get_bot_instance().close()  # type: ignore

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

        # NEW: Trivia Pool Validation and Auto-Replenishment
        pool_status_message = ""
        try:
            db = get_database()
            if db:
                available_questions = db.get_available_trivia_questions()
                pool_count = len(available_questions) if available_questions else 0

                print(f"🧠 TRIVIA POOL CHECK (8:15 AM): {pool_count} questions available")

                if pool_count >= 3:
                    pool_status_message = f"✅ Trivia Pool: {pool_count} questions available"
                else:
                    pool_status_message = f"⚠️ Trivia Pool: {pool_count}/5 questions (LOW)"

                    # Auto-generate needed questions (always aim to fill back to 5)
                    needed = 5 - pool_count
                    print(f"🔄 TRIVIA POOL: Generating {needed} questions...")

                    try:
                        from ..handlers.conversations import start_jam_question_approval
                        from ..handlers.trivia.generator import generate_ai_trivia_question

                        generated = 0
                        failed = 0

                        # ✅ CIRCUIT BREAKER: Protect API quota from consecutive failures
                        consecutive_failures = 0
                        MAX_CONSECUTIVE_FAILURES = 2  # Stop after 2 failures in a row

                        for i in range(needed):
                            # ✅ CIRCUIT BREAKER CHECK: Stop if too many consecutive failures
                            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                                print(
                                    f"🚨 CIRCUIT BREAKER (8:15 AM): Stopping auto-replenishment after {consecutive_failures} consecutive failures")
                                print(f"⚠️ API quota preserved: {needed - i} questions not attempted")
                                pool_status_message += f"\n🚨 Circuit breaker activated after {consecutive_failures} failures"
                                break

                            try:
                                question_data = await generate_ai_trivia_question(f"auto_replenish_{i}")
                                if question_data:
                                    if await start_jam_question_approval(question_data):
                                        generated += 1
                                        consecutive_failures = 0  # ✅ Reset on success
                                        print(f"✅ Generated question {i+1}/{needed}")
                                    else:
                                        failed += 1
                                        consecutive_failures += 1
                                else:
                                    failed += 1
                                    consecutive_failures += 1
                                    print(f"⚠️ Generation failure {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}")
                                await asyncio.sleep(2)
                            except Exception as gen_error:
                                failed += 1
                                consecutive_failures += 1
                                print(f"❌ Question generation {i+1} failed: {gen_error}")
                                print(f"⚠️ Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}")

                        pool_status_message += f"\n📤 Auto-generated: {generated} questions sent to approval queue"
                        if failed > 0:
                            pool_status_message += f"\n⚠️ Failed: {failed} generation attempts"

                    except Exception as replenish_error:
                        pool_status_message += f"\n❌ Replenishment failed: {str(replenish_error)[:100]}"
                        print(f"❌ TRIVIA POOL: Replenishment error: {replenish_error}")
            else:
                pool_status_message = "❌ Trivia Pool: Database unavailable"

        except Exception as pool_error:
            pool_status_message = f"❌ Trivia Pool: Check failed - {str(pool_error)[:100]}"
            print(f"❌ TRIVIA POOL CHECK: Error - {pool_error}")

        # Send notification to JAM (always send now, includes pool status)
        try:
            from ..config import JAM_USER_ID

            if not get_bot_instance():
                print("⚠️ Bot instance not available for AI refresh notification")
                return

            user = await get_bot_instance().fetch_user(JAM_USER_ID)  # type: ignore
            if user:
                # Build notification message
                if previous_errors > 0:
                    notification_msg = (
                        f"🤖 **AI Module Refresh Complete**\n"
                        f"• Status: {ai_status['status_message']}\n"
                        f"• Previous errors cleared: {previous_errors}\n"
                        f"• Daily quota reset at {uk_now.strftime(f'%H:%M {timezone_name}')}\n\n"
                        f"{pool_status_message}\n\n"
                        f"*AI functionality should now be restored.*"
                    )
                else:
                    notification_msg = (
                        f"🤖 **Daily System Refresh - {uk_now.strftime(f'%H:%M {timezone_name}')}**\n"
                        f"• AI Status: {ai_status['status_message']}\n"
                        f"• {pool_status_message}\n\n"
                        f"*All systems refreshed post-quota reset.*"
                    )

                await user.send(notification_msg)
                print("✅ AI refresh notification with trivia pool status sent to JAM")
        except Exception as notify_e:
            print(f"⚠️ Could not send AI refresh notification: {notify_e}")

    except Exception as e:
        print(f"❌ Error in scheduled_ai_refresh: {e}")
        # Try to notify JAM of refresh failure
        try:
            from ..config import JAM_USER_ID

            if not get_bot_instance():
                print("⚠️ Bot instance not available for AI refresh error notification")
                return

            user = await get_bot_instance().fetch_user(JAM_USER_ID)  # type: ignore
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

        # Get dynamic database instance
        db = get_database()

        # Enhanced database diagnostics - only log issues or when processing reminders
        if db is None:
            print("❌ Database instance is None - reminder system disabled")
            return

        if not hasattr(db, 'get_due_reminders'):
            print("❌ Database instance missing get_due_reminders - reminder system disabled")
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
                bot = get_bot_instance()
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
        from ..database import get_database
        db = get_database()
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
            from ..handlers.conversations import cleanup_weekly_announcement_approvals
            expired_count = cleanup_weekly_announcement_approvals()
            if expired_count > 0:
                print(f"🧹 Cleaned up {expired_count} stale weekly announcement approvals")
        except Exception as cleanup_error:
            print(f"⚠️ Error cleaning up weekly announcement approvals: {cleanup_error}")

        # Improved bot instance checking with multiple fallback methods
        bot_instance = None

        # Method 1: Use global get_bot_instance() if available
        if get_bot_instance() and hasattr(get_bot_instance(), 'user') and get_bot_instance().user:  # type: ignore
            bot_instance = get_bot_instance()
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

        guild = bot_instance.get_guild(GUILD_ID)  # type: ignore
        if not guild:
            print("❌ Guild not found for game recommendation cleanup")
            return

        # Get the game recommendation channel
        game_rec_channel = bot_instance.get_channel(GAME_RECOMMENDATION_CHANNEL_ID)  # type: ignore
        if not game_rec_channel or not isinstance(game_rec_channel, discord.TextChannel):
            print("❌ Game recommendation channel not found for cleanup")
            return

        # Check bot permissions in the channel
        bot_member = guild.get_member(bot_instance.user.id) if bot_instance.user else None  # type: ignore
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

        if not get_bot_instance():
            print("❌ Bot instance not available for scheduled message error notification")
            return

        user = await get_bot_instance().fetch_user(JAM_USER_ID)  # type: ignore
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
            bot = get_bot_instance()

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
                    user = await bot.fetch_user(user_id) if bot else None

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
        if not get_bot_instance():
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
                channel = get_bot_instance().get_channel(delivery_channel_id)  # type: ignore
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
        guild = get_bot_instance().get_guild(GUILD_ID)  # type: ignore
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
                channel = get_bot_instance().get_channel(delivery_channel_id)  # type: ignore
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


@tasks.loop(time=time(hour=20, minute=15, tzinfo=ZoneInfo("Europe/London")))
async def daily_clip_scan_task():
    """Scan clips channel for unprocessed clips every weekday evening"""
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() > 4:  # 0-4 is Mon-Fri
        print("⏭️ Skipping daily clip scan (weekend)")
        return

    print("🎬 Starting daily clip scan task...")
    bot = get_bot_instance()
    if not bot:
        return

    channel_id = 1210874007591718982
    channel = bot.get_channel(channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        print("❌ Could not find clips channel for daily scan")
        return

    cog = bot.get_cog("ClipTriviaCog")
    if not cog:
        print("❌ Could not find ClipTriviaCog for daily scan")
        return

    db = get_database()
    if not db:
        print("❌ Could not get database for daily scan")
        return

    clips_to_process = []

    async for message in channel.history(limit=50):
        if message.author.bot:
            continue

        match = cog.url_pattern.search(message.content)
        if match:
            from ..commands.clips import canonicalize_clip_url
            clip_url = match.group(0)
            canonical_url = canonicalize_clip_url(clip_url)

            if not db.trivia.clip_lore_exists(canonical_url):
                clips_to_process.append((message, clip_url))
            else:
                # Clip already processed - ensure it has the ✅ reaction
                has_tick = any(str(r.emoji) == "✅" for r in message.reactions)
                if not has_tick:
                    try:
                        await message.add_reaction("✅")
                        if bot.user:
                            await message.remove_reaction("👀", bot.user)
                            await message.remove_reaction("❌", bot.user)
                    except Exception:
                        pass

    queued_count = len(clips_to_process)
    if queued_count == 0:
        print("✅ Daily clip scan complete. No new clips found.")
        return

    print(f"🎬 Processing {queued_count} new clips...")

    jam_user = None
    try:
        jam_user = await bot.fetch_user(JAM_USER_ID)
    except Exception as e:
        print(f"Failed to fetch Jam user for DMs: {e}")

    quota_exhausted = False
    for idx, (msg, curl) in enumerate(clips_to_process):
        if quota_exhausted:
            break

        success = False

        # Clear any old failure marks before retrying
        try:
            if bot.user:
                await msg.remove_reaction("❌", bot.user)
        except Exception:
            pass

        # Add a simple retry loop for Gemini 503 errors
        for attempt in range(3):
            success = await cog.parser.process_clip(curl, msg)
            if success:
                break

            from ..handlers.ai_handler import primary_ai
            if primary_ai != "gemini":
                print("🚫 Primary AI is exhausted or unavailable. Aborting clip batch.")
                quota_exhausted = True
                break

            print(f"⚠️ Clip processing failed (attempt {attempt + 1}/3). Retrying in 30s...")
            await asyncio.sleep(30.0)

        if quota_exhausted:
            # Send a DM saying we aborted
            if jam_user:
                await jam_user.send(f"⚠️ **Clip Processing Aborted**\nThe AI quota was exhausted while processing clip {idx + 1}/{queued_count}. The remaining {queued_count - idx} clips will be processed tomorrow.")
            # Do not apply ✅ or ❌, just leave it for tomorrow
            try:
                if bot.user:
                    await msg.remove_reaction("👀", bot.user)
            except Exception:
                pass
            break

        try:
            if bot.user:
                await msg.remove_reaction("👀", bot.user)
        except Exception:
            pass

        try:
            if success:
                await msg.add_reaction("✅")
            else:
                await msg.add_reaction("❌")
        except discord.Forbidden:
            print(f"⚠️ Missing permissions to add ✅/❌ reaction to message {msg.id}")
            if jam_user:
                await jam_user.send(f"⚠️ **Permission Error:** I don't have the 'Add Reactions' permission in the clips channel to react to {curl}!")
        except Exception as e:
            print(f"Error updating reaction on message {msg.id}: {e}")

        # Send DM update
        if jam_user:
            date_str = msg.created_at.strftime("%Y-%m-%d")
            if success:
                from ..commands.clips import canonicalize_clip_url
                canonical_url = canonicalize_clip_url(curl)
                clip_details = db.trivia.get_clip_lore(canonical_url)

                if clip_details:
                    title = clip_details.get('game_title', 'Unknown Game')
                    reaction = clip_details.get('reaction', 'Reaction')
                    quote = clip_details.get('notable_quote', '')
                    emotion = clip_details.get('emotion_category', '')
                    outcome = clip_details.get('clip_outcome', '')
                    characters = clip_details.get('characters_involved', '')

                    dm_msg = f"🔬 **Archive Update** [{idx + 1}/{queued_count}]\n"
                    dm_msg += f"I have processed the clip from {date_str}: **{title}**.\n"
                    dm_msg += f"Observed reaction: *{reaction}*."
                    if quote:
                        dm_msg += f"\nNotable Quote: *\"{quote}\"*"
                    if emotion or outcome or characters:
                        dm_msg += "\n\n**Additional Analysis:**"
                        if emotion:
                            dm_msg += f"\n• Emotion: {emotion}"
                        if outcome:
                            dm_msg += f"\n• Outcome: {outcome}"
                        if characters:
                            dm_msg += f"\n• Characters: {characters}"
                else:
                    dm_msg = f"🔬 Processing... [{idx + 1}/{queued_count}] (Success)"
            else:
                dm_msg = f"⚠️ **Archive Update** [{idx + 1}/{queued_count}]\n"
                dm_msg += f"I attempted to process the clip from {date_str}, but the analysis failed after 3 attempts."

            try:
                await jam_user.send(dm_msg)
            except Exception:
                pass

        if idx < queued_count - 1:
            await asyncio.sleep(60.0)

    print("✅ Daily clip scan completed successfully.")


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
            (pre_trivia_preflight_check, "Pre-trivia pre-flight check task (10:45 AM UK time, Tuesdays)"),
            (trivia_tuesday, "Trivia Tuesday task (11:00 AM UK time, Tuesdays)"),
            (friday_community_analysis, "Friday Community Analysis (Friday 8.15am)"),
            (friday_morning_greeting, "Friday morning greeting task (9:00 AM UK time, Fridays)"),
            ## Daily ##
            (scheduled_midnight_restart, "Scheduled midnight restart task (00:00 PT daily)"),
            (scheduled_ai_refresh, "AI module refresh task (8:15 AM UK time daily)"),
            (daily_clip_scan_task, "Daily clip scan task (20:15 UK time weekdays)"),
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
            (daily_clip_scan_task, "Daily Clip Scan"),
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
            'global_bot_ready': is_bot_ready()
        }

    except Exception as e:
        return {'error': str(e)}


def stop_all_scheduled_tasks():
    """Stop all scheduled tasks"""
    try:
        tasks_to_stop = [
            monday_content_sync,
            scheduled_midnight_restart,
            daily_clip_scan_task,
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
