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
from ..database import get_database
from ..handlers.ai_handler import call_ai_with_rate_limiting, filter_ai_response
from ..handlers.trivia.generator import generate_ai_trivia_question, generate_trivia_batch
from ..persona.sarcasm import apply_pops_arcade_sarcasm
from .utils import _should_run_automated_tasks, get_bot_instance

_startup_validation_lock = False
_startup_validation_completed = False


db = get_database()


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
                from ..handlers.conversation_handler import start_jam_question_approval
                from ..handlers.trivia.generator import generate_ai_trivia_question

                print("🔄 Attempting to generate emergency question for today's trivia")
                emergency_question = await generate_ai_trivia_question()

                if emergency_question:
                    # Send emergency question directly to JAM for urgent approval
                    emergency_sent = await start_jam_question_approval(emergency_question)
                    if emergency_sent:
                        print("✅ Emergency question sent to JAM for approval")
                        # Send urgent notification to JAM
                        from ..config import JAM_USER_ID

                        if not get_bot_instance():
                            print("⚠️ Bot instance not available for emergency trivia notification")
                            return

                        user = await get_bot_instance().fetch_user(JAM_USER_ID)
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

            if not get_bot_instance():
                print("⚠️ Bot instance not available for pre-trivia error notification")
                return

            user = await get_bot_instance().fetch_user(JAM_USER_ID)
            if user:
                await user.send(
                    f"⚠️ **Pre-Trivia Approval Error**\n\n"
                    f"Failed to send today's question for approval at 10:00 AM.\n"
                    f"Error: {str(e)}\n\n"
                    f"*Manual intervention may be required for today's Trivia Tuesday.*"
                )
        except Exception:
            pass


async def pre_trivia_preflight_check():
    """Verify approved question exists 15 minutes before trivia"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Only run on Tuesdays (weekday 1)
    if uk_now.weekday() != 1:
        return

    if not _should_run_automated_tasks():
        return

    print(f"🔍 PRE-FLIGHT CHECK: Verifying approved question at {uk_now.strftime('%H:%M:%S UK')}")

    if not db:
        print("❌ PRE-FLIGHT CHECK: Database not available")
        return

    try:
        # Check if approved question exists
        approved_id_str = db.get_config_value('trivia_approved_question_id')

        if not approved_id_str:
            # No approved question - send urgent alert
            print("❌ PRE-FLIGHT CHECK: No approved question found!")

            from ..config import JAM_USER_ID

            if not get_bot_instance():
                print("❌ PRE-FLIGHT CHECK: Bot instance not available for alert")
                return

            try:
                user = await get_bot_instance().fetch_user(JAM_USER_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                print(f"❌ PRE-FLIGHT CHECK: Could not fetch user for alert: {e}")
                return

            if user:
                alert_message = (
                    f"🚨 **URGENT: Trivia Pre-Flight Check Failed**\n\n"
                    f"**Problem:** No approved question found for today's Trivia Tuesday!\n"
                    f"**Time Until Trivia:** 15 minutes (11:00 AM UK)\n"
                    f"**Current Time:** {uk_now.strftime('%H:%M UK')}\n\n"
                    f"**Next Steps:**\n"
                    f"1. Use `!approvequestion <question_id>` to manually approve a question\n"
                    f"2. Use `!generatequestions 1` to add more to the pool\n"
                    f"3. Use `!disabletrivia` if you want to skip trivia today\n\n"
                    f"**Without action, trivia will NOT run automatically.**"
                )
                await user.send(alert_message)
                print("✅ PRE-FLIGHT CHECK: Alert sent to JAM")
        else:
            # Verify question exists in database
            approved_question_id = int(approved_id_str)
            question_data = db.get_trivia_question_by_id(approved_question_id)

            if not question_data:
                print(f"❌ PRE-FLIGHT CHECK: Approved question #{approved_question_id} not found in database!")

                from ..config import JAM_USER_ID
                if not get_bot_instance():
                    return

                user = await get_bot_instance().fetch_user(JAM_USER_ID)
                if user:
                    alert_message = (
                        f"⚠️ **Trivia Pre-Flight Check Warning**\n\n"
                        f"**Problem:** Approved question #{approved_question_id} was deleted or not found!\n"
                        f"**Time Until Trivia:** 15 minutes (11:00 AM UK)\n\n"
                        f"Please approve a different question with `!approvequestion <question_id>`"
                    )
                    await user.send(alert_message)
                    print("✅ PRE-FLIGHT CHECK: Warning sent to JAM")
            else:
                print(f"✅ PRE-FLIGHT CHECK: Approved question #{approved_question_id} verified - trivia ready")

    except Exception as e:
        print(f"❌ PRE-FLIGHT CHECK: Error during check: {e}")


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

            if not get_bot_instance():
                print("❌ Bot instance not available for delayed trivia validation error notification")
                return

            user = await get_bot_instance().fetch_user(JAM_USER_ID)
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
                    from ..handlers.conversation_handler import start_jam_question_approval
                    from ..handlers.trivia.generator import generate_ai_trivia_question

                    print("🔄 EMERGENCY APPROVAL: Generating emergency question")
                    emergency_question = await generate_ai_trivia_question("emergency_approval")

                    if emergency_question:
                        approval_sent = await start_jam_question_approval(emergency_question)
                        if approval_sent:
                            print("✅ EMERGENCY APPROVAL: Emergency question sent to JAM")

                            # Send urgent notification to JAM
                            from ..config import JAM_USER_ID

                            if not get_bot_instance():
                                print("❌ Bot instance not available for emergency approval notification")
                                return

                            user = await get_bot_instance().fetch_user(JAM_USER_ID)
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

                    if not get_bot_instance():
                        print("❌ Bot instance not available for emergency build day notification")
                        return

                    user = await get_bot_instance().fetch_user(JAM_USER_ID)
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

        # ✅ NEW: Check for pending approval questions FIRST (restore orphaned questions)
        pending_questions = []
        try:
            if hasattr(db, 'get_pending_approval_questions'):
                pending_questions = db.get_pending_approval_questions()  # type: ignore
                pending_count = len(pending_questions) if pending_questions else 0

                if pending_count > 0:
                    print(
                        f"🔄 STARTUP TRIVIA VALIDATION: Found {pending_count} orphaned questions awaiting approval from previous session")

                    # Restore these questions to the approval queue
                    try:
                        from ..handlers.conversation_handler import add_to_approval_queue, process_next_approval

                        restored_count = 0
                        for pending_q in pending_questions:
                            # Add to queue with high priority (they were already generated)
                            queue_position = add_to_approval_queue(
                                item_type='trivia_question',
                                data=pending_q,
                                priority=8,  # Higher priority than new generations
                                source='startup_restoration'
                            )
                            print(
                                f"♻️ RESTORED: Question #{pending_q.get('id')} added to approval queue at position {queue_position}")
                            restored_count += 1

                        # Trigger queue processing to send first question to JAM
                        if restored_count > 0:
                            print(
                                f"🔄 STARTUP TRIVIA VALIDATION: Triggering approval queue for {restored_count} restored questions")
                            await process_next_approval()

                            # Notify JAM about restoration
                            try:
                                if get_bot_instance():
                                    from ..config import JAM_USER_ID
                                    user = await get_bot_instance().fetch_user(JAM_USER_ID)
                                    if user:
                                        await user.send(
                                            f"♻️ **Pending Questions Restored**\n\n"
                                            f"Bot restart detected. **{restored_count}** questions that were awaiting your approval "
                                            f"have been restored to the approval queue.\n\n"
                                            f"These questions were generated previously but not yet reviewed. "
                                            f"You'll receive them one at a time for approval.\n\n"
                                            f"*No new API calls were needed - these questions were preserved in the database.*"
                                        )
                                        print("✅ STARTUP TRIVIA VALIDATION: Restoration notification sent to JAM")
                            except Exception as notify_error:
                                print(
                                    f"⚠️ STARTUP TRIVIA VALIDATION: Failed to send restoration notification: {notify_error}")

                    except Exception as restore_error:
                        print(
                            f"❌ STARTUP TRIVIA VALIDATION: Failed to restore pending questions to queue: {restore_error}")
                else:
                    print("✅ STARTUP TRIVIA VALIDATION: No orphaned pending questions to restore")
            else:
                print("ℹ️ STARTUP TRIVIA VALIDATION: get_pending_approval_questions method not available")
        except Exception as pending_error:
            print(f"⚠️ STARTUP TRIVIA VALIDATION: Error checking for pending questions: {pending_error}")

        # Check for available questions with retry logic (quick check only)
        available_questions = None
        try:
            available_questions = db.get_available_trivia_questions()  # type: ignore
        except Exception as db_error:
            print(f"⚠️ STARTUP TRIVIA VALIDATION: Database query failed - {db_error}")
            print("⚠️ STARTUP TRIVIA VALIDATION: Continuing with assumption of 0 questions")
            available_questions = []

        available_count = len(available_questions) if available_questions else 0
        pending_count = len(pending_questions) if pending_questions else 0
        total_count = available_count + pending_count

        print(
            f"🧠 STARTUP TRIVIA VALIDATION: {available_count} available + {pending_count} pending = {total_count} total questions")

        if available_questions and available_count > 0:
            for i, q in enumerate(available_questions[:3]):  # Show first 3 for confirmation
                question_preview = q.get('question_text', q.get('question', 'Unknown'))[:50]
                print(f"   📋 Available Question {i+1}: {question_preview}...")

        # If we have at least 5 questions (available + pending), we're good
        if total_count >= 5:
            print(
                f"✅ STARTUP TRIVIA VALIDATION: Sufficient questions ({total_count}/5 including {pending_count} pending approval)")
            return

        # Create background task for AI generation to avoid blocking Discord heartbeat
        print(f"🔄 STARTUP TRIVIA VALIDATION: Need to generate {5 - total_count} additional questions")
        print("🔄 STARTUP TRIVIA VALIDATION: Creating non-blocking background task for AI generation...")

        # Create completely detached background task that won't block startup
        # Pass total_count to account for both available and pending questions
        asyncio.create_task(_background_question_generation(total_count))

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
    """Background task for generating trivia questions using the approval queue system"""
    try:
        print(f"🧠 BACKGROUND QUESTION GENERATION: Starting with {current_question_count} existing questions")

        questions_needed = min(5 - current_question_count, 4)  # Cap at 4 to avoid overwhelming JAM

        # Check if AI handler is available
        try:
            from ..config import JAM_USER_ID
            from ..handlers.conversation_handler import add_to_approval_queue, process_next_approval
            from ..handlers.trivia.generator import generate_ai_trivia_question
            print("✅ BACKGROUND GENERATION: AI handler and conversation handler loaded")
        except ImportError as import_error:
            print(f"❌ BACKGROUND GENERATION: Failed to import required modules - {import_error}")
            return

        # Generate all questions first
        successful_generations = 0
        failed_generations = 0
        duplicate_count = 0

        # ✅ CIRCUIT BREAKER: Protect API quota from consecutive failures
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 2  # Stop after 2 failures in a row

        # ✅ FIX: Track recently generated questions AND templates to prevent repetition
        generated_question_texts = []
        used_template_ids = []  # ✅ NEW: Track templates used in this batch

        print(f"🔄 BACKGROUND GENERATION: Generating {questions_needed} questions with pattern diversity...")

        for i in range(questions_needed):
            # ✅ CIRCUIT BREAKER CHECK: Stop if too many consecutive failures
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"🚨 CIRCUIT BREAKER: Stopping generation after {consecutive_failures} consecutive failures")
                print(f"⚠️ API quota preserved: {questions_needed - i} questions not attempted")

                # Notify JAM of the circuit breaker activation
                try:
                    if not get_bot_instance():
                        print("⚠️ Bot instance not available for circuit breaker notification")
                    else:
                        user = await get_bot_instance().fetch_user(JAM_USER_ID)
                        if user:
                            await user.send(
                                f"🚨 **Trivia Generation Circuit Breaker Activated**\n\n"
                                f"Question generation stopped after {consecutive_failures} consecutive failures.\n"
                                f"**API calls saved:** {questions_needed - i}\n"
                                f"**Successful:** {successful_generations} questions\n"
                                f"**Error:** Check logs for details\n\n"
                                f"*Manual intervention may be required to fix underlying issue.*"
                            )
                            print("✅ Circuit breaker notification sent to JAM")
                except Exception as notify_error:
                    print(f"⚠️ Failed to send circuit breaker notification: {notify_error}")
                break

            try:
                print(f"🔄 BACKGROUND GENERATION: Generating question {i+1}/{questions_needed}")

                # ✅ FIX #1: Use unique context for each generation to avoid cache hits
                unique_context = f"startup_validation_{i+1}"

                # ✅ FIX #2: Pass recently generated questions AND templates to avoid repetition
                import random
                from ..handlers.ai_handler import generate_contextual_trivia

                # 50% chance to use the new contextual clip/game lore generator
                if random.random() < 0.5:
                    print("🔄 BACKGROUND GENERATION: Using new contextual/clip trivia generator")
                    question_data = await generate_contextual_trivia()
                else:
                    print("🔄 BACKGROUND GENERATION: Using classic Trivia Director")
                    question_data = await generate_ai_trivia_question(
                        unique_context,
                        avoid_questions=generated_question_texts,
                        avoid_templates=used_template_ids  # ✅ NEW: Prevent template reuse in batch
                    )

                if question_data and isinstance(question_data, dict):
                    # ✅ SUCCESS: Reset consecutive failure counter
                    consecutive_failures = 0
                    # Validate the generated question
                    required_fields = ['question_text', 'question_type', 'correct_answer']
                    if all(field in question_data for field in required_fields):
                        question_text = question_data.get('question_text', 'Unknown')

                        # Check for duplicates before adding to queue
                        if db:
                            try:
                                duplicate_check = db.check_question_duplicate(question_text, similarity_threshold=0.85)
                                if duplicate_check:
                                    similarity = duplicate_check['similarity_score']
                                    duplicate_id = duplicate_check['duplicate_id']
                                    print(
                                        f"⚠️ BACKGROUND GENERATION: Question {i+1} is duplicate ({similarity*100:.0f}% match to Q#{duplicate_id}), skipping")
                                    duplicate_count += 1
                                    continue
                            except Exception as dup_error:
                                print(f"⚠️ BACKGROUND GENERATION: Duplicate check failed: {dup_error}")

                        print(f"✅ BACKGROUND GENERATION: Generated question {i+1}: {question_text[:50]}...")

                        # ✅ FIX #3: Add to recently-generated list for next iteration
                        generated_question_texts.append(question_text)

                        # ✅ FIX #4: Track template ID if this was a template-generated question
                        if question_data.get('generation_method') == 'template':
                            template_id = question_text[:20]  # Same ID format as in ai_handler
                            used_template_ids.append(template_id)
                            print(f"📝 BACKGROUND GENERATION: Tracked template ID for avoidance: {template_id}")

                        # ✅ NEW: Persist question to database IMMEDIATELY with pending_approval status
                        # This ensures questions survive bot restarts
                        question_id = None
                        if db:
                            try:
                                question_id = db.add_trivia_question(
                                    question_text=question_data['question_text'],
                                    question_type=question_data['question_type'],
                                    correct_answer=question_data.get('correct_answer'),
                                    multiple_choice_options=question_data.get('multiple_choice_options'),
                                    is_dynamic=question_data.get('is_dynamic', False),
                                    dynamic_query_type=question_data.get('dynamic_query_type'),
                                    submitted_by_user_id=None,  # AI-generated
                                    category=question_data.get('category'),
                                    difficulty_level=question_data.get('difficulty_level', 2),
                                    status='pending_approval'  # ✅ KEY: Pending status allows recovery on restart
                                )

                                if question_id:
                                    print(
                                        f"💾 BACKGROUND GENERATION: Question persisted to DB as ID #{question_id} (status: pending_approval)")
                                    # Add question_id to the data for the approval queue
                                    question_data['id'] = question_id
                                else:
                                    print(f"⚠️ BACKGROUND GENERATION: Failed to persist question to database")
                                    failed_generations += 1
                                    continue
                            except Exception as db_persist_error:
                                print(f"❌ BACKGROUND GENERATION: Database persist error: {db_persist_error}")
                                failed_generations += 1
                                continue

                        # ✅ FIX #2: Add to approval queue instead of manual sequential logic
                        queue_position = add_to_approval_queue(
                            item_type='trivia_question',
                            data=question_data,
                            priority=5,  # Normal priority for startup questions
                            source=f'startup_generation_{i+1}'
                        )

                        print(
                            f"📋 BACKGROUND GENERATION: Question {i+1} (ID #{question_id}) added to approval queue at position {queue_position}")
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

            # Delay between generations to respect Gemini free tier rate limit (5 RPM).
            # 15 seconds ensures we stay safely under 4 calls/minute for a 4-question batch.
            await asyncio.sleep(15)

        print(f"🧠 BACKGROUND GENERATION: Complete - {successful_generations} questions added to approval queue")
        print(
            f"📊 BACKGROUND GENERATION: Stats - Generated: {successful_generations}, Failed: {failed_generations}, Duplicates: {duplicate_count}")

        # ✅ FIX #2: Trigger the approval queue processor to start sending questions
        if successful_generations > 0:
            print(f"🔄 BACKGROUND GENERATION: Triggering approval queue processor...")
            await process_next_approval()
            print(f"✅ BACKGROUND GENERATION: Approval queue processor started - JAM will receive questions sequentially")

            # Send summary notification to JAM
            try:
                if not get_bot_instance():
                    print("⚠️ Bot instance not available for summary notification")
                    return

                if hasattr(get_bot_instance(), 'fetch_user') and get_bot_instance().user:
                    user = await get_bot_instance().fetch_user(JAM_USER_ID)
                    if user:
                        from ..handlers.conversation_handler import get_queue_length
                        remaining = get_queue_length()

                        summary_message = (
                            f"🧠 **Background Question Generation Complete**\n\n"
                            f"**Generation Summary:**\n"
                            f"• Questions generated: {successful_generations}\n"
                            f"• Duplicates detected: {duplicate_count}\n"
                            f"• Generation failures: {failed_generations}\n"
                            f"• Total in approval queue: {remaining}\n\n"
                            f"Questions will be sent to you **one at a time** for approval. "
                            f"The next question will arrive automatically after you complete each approval.\n\n"
                            f"*This queue system ensures you're never overwhelmed with multiple simultaneous approvals.*")
                        await user.send(summary_message)
                        print("✅ BACKGROUND GENERATION: Summary notification sent to JAM")
            except Exception as summary_error:
                print(f"⚠️ BACKGROUND GENERATION: Failed to send summary to JAM: {summary_error}")
        else:
            print("⚠️ BACKGROUND GENERATION: No questions were successfully generated")

    except Exception as e:
        print(f"❌ BACKGROUND GENERATION: Critical error - {e}")
        import traceback
        traceback.print_exc()
