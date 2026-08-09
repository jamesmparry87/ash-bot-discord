import asyncio
import re
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import discord
from bot.config import (
    ANNOUNCEMENTS_CHANNEL_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    MOD_ALERT_CHANNEL_ID,
    YOUTUBE_UPLOADS_CHANNEL_ID,
)
from bot.database import get_database
from bot.handlers.ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response
from bot.utils.permissions import get_user_communication_tier, user_is_mod_by_id
from discord.ext import commands

from .core import (
    _get_bot_instance,
    announcement_conversations,
    db,
    game_review_conversations,
    jam_approval_conversations,
    jam_approval_queue,
    mod_trivia_conversations,
    sync_approval_conversations,
    weekly_announcement_approvals,
)
from .utils import (
    _infer_dynamic_query_type,
    check_conversation_health,
    check_escape_command,
    create_invalid_input_message,
    extract_expected_options_from_prompt,
    increment_invalid_input_count,
    reset_invalid_input_count,
    send_conversation_expired_message,
    track_conversation_step,
    validate_numbered_input,
)


def add_to_approval_queue(item_type: str, data: Dict[str, Any], priority: int = 0, source: str = 'unknown') -> int:
    """
    Add an approval item to JAM's queue.

    Args:
        item_type: Type of approval ('trivia_question', 'weekly_announcement', 'game_review')
        data: The data payload for the approval
        priority: Priority level (0-10, higher = more urgent)
        source: Source of the request (for tracking)

    Returns:
        Queue position (0-indexed)
    """
    global jam_approval_queue

    uk_now = datetime.now(ZoneInfo("Europe/London"))

    queue_item = {
        'type': item_type,
        'data': data,
        'priority': priority,
        'added_at': uk_now,
        'source': source
    }

    # Insert based on priority (higher priority first)
    inserted = False
    i = 0
    for i, existing_item in enumerate(jam_approval_queue):
        if priority > existing_item.get('priority', 0):
            jam_approval_queue.insert(i, queue_item)
            inserted = True
            print(f"📋 Added {item_type} to approval queue at position {i} (priority {priority})")
            break

    if not inserted:
        jam_approval_queue.append(queue_item)
        position = len(jam_approval_queue) - 1
        print(f"📋 Added {item_type} to approval queue at position {position} (priority {priority})")

    return len(jam_approval_queue) - 1 if not inserted else i

def get_queue_length() -> int:
    """Get the current length of the approval queue."""
    global jam_approval_queue
    return len(jam_approval_queue)

def get_queue_status() -> Dict[str, Any]:
    """
    Get detailed status of the approval queue.

    Returns:
        Dictionary with queue statistics and item details
    """
    global jam_approval_queue

    return {
        'queue_length': len(jam_approval_queue),
        'active_approval': is_jam_approval_active(),
        'items': [
            {
                'type': item['type'],
                'priority': item['priority'],
                'source': item['source'],
                'age_minutes': int((datetime.now(ZoneInfo("Europe/London")) - item['added_at']).total_seconds() / 60)
            }
            for item in jam_approval_queue
        ]
    }

def clear_approval_queue() -> int:
    """
    Clear all items from the approval queue (admin function).

    Returns:
        Number of items that were cleared
    """
    global jam_approval_queue

    count = len(jam_approval_queue)
    jam_approval_queue = []
    print(f"🧹 Cleared approval queue ({count} items removed)")

    return count

async def process_next_approval() -> bool:
    """
    Process the next item in the approval queue if JAM is free.

    Returns:
        True if an item was sent, False otherwise
    """
    global jam_approval_queue, jam_approval_active

    # Check if JAM is busy
    if is_jam_approval_active():
        print(f"⏸️ JAM is busy with active approval. Queue has {len(jam_approval_queue)} pending items.")
        return False

    # Check if queue is empty
    if len(jam_approval_queue) == 0:
        print(f"✅ Approval queue is empty. JAM is free.")
        return False

    # Get the next item (highest priority first)
    next_item = jam_approval_queue.pop(0)

    item_type = next_item['type']
    data = next_item['data']
    priority = next_item['priority']
    source = next_item['source']

    remaining = len(jam_approval_queue)

    print(
        f"📤 Processing approval: {item_type} (priority {priority}, source: {source}). {remaining} items remaining in queue.")

    # Route to appropriate approval handler
    try:
        if item_type == 'trivia_question':
            # Check if it's a pre-trivia approval (context in data)
            if data.get('context') == 'pre_trivia':
                success = await start_pre_trivia_approval(data)
            else:
                success = await start_jam_question_approval(data)

            if success:
                jam_approval_active = True
                return True
            else:
                print(f"❌ Failed to start {item_type} approval")
                return False

        elif item_type == 'weekly_announcement':
            announcement_id = data.get('announcement_id')
            content = data.get('content')
            day = data.get('day')

            # Call internal sender (not the queue function)
            await _send_weekly_announcement_approval(announcement_id, content, day)
            jam_approval_active = True
            return True

        elif item_type == 'game_review':
            success = await start_game_review_approval(data)

            if success:
                jam_approval_active = True
                return True
            else:
                print(f"❌ Failed to start {item_type} approval")
                return False

        elif item_type == 'sync_approval':
            sync_session_id = data.get('sync_session_id')
            summary = data.get('summary')

            success = await start_sync_approval(sync_session_id, summary)

            if success:
                jam_approval_active = True
                return True
            else:
                print(f"❌ Failed to start {item_type} approval")
                return False

        else:
            print(f"⚠️ Unknown approval type: {item_type}")
            return False

    except Exception as e:
        print(f"❌ Error processing approval from queue: {e}")
        traceback.print_exc()
        return False

def cleanup_jam_approval_conversations():
    """Remove JAM approval conversations inactive for more than 24 hours (extended for late responses)"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=24)  # Extended from 2 hours to 24 hours
    expired_users = [
        user_id for user_id,
        data in jam_approval_conversations.items() if data.get(
            "last_activity",
            uk_now) < cutoff_time]
    for user_id in expired_users:
        # Log extended cleanup for monitoring
        user_data = jam_approval_conversations.get(user_id, {})
        conversation_age_hours = (uk_now - user_data.get("last_activity", uk_now)).total_seconds() / 3600
        print(
            f"Cleaned up JAM approval conversation for user {user_id} after {conversation_age_hours:.1f} hours of inactivity")
        del jam_approval_conversations[user_id]

def update_jam_approval_activity(user_id: int):
    """Update last activity time for JAM approval conversation"""
    if user_id in jam_approval_conversations:
        jam_approval_conversations[user_id]["last_activity"] = datetime.now(
            ZoneInfo("Europe/London"))

async def handle_jam_approval_conversation(message: discord.Message) -> None:
    """Handle the interactive DM conversation for JAM approval of trivia questions"""
    user_id = message.author.id

    # ✅ CRITICAL: Check conversation exists AND is still valid
    conversation = jam_approval_conversations.get(user_id)
    if not conversation:
        print(f"🚫 CONVERSATION CHECK: No active approval conversation for user {user_id}")
        return

    print(
        f"🔄 CONVERSATION ACTIVE: Processing message '{message.content[:50]}...' for user {user_id} in step '{conversation.get('step')}'")

    # Get message content early for pre-trivia check
    content = message.content.strip()

    # ✅ FIX #1: Check for escape command
    if check_escape_command(content):
        await message.reply(
            f"❌ **Approval Cancelled**\n\n"
            f"The question approval process has been cancelled at your request. "
            f"The pending question has been discarded.\n\n"
            f"*You can start a new approval with `!approvequestion auto`*"
        )
        if user_id in jam_approval_conversations:
            del jam_approval_conversations[user_id]
        return

    # ✅ FIX #1: Check conversation health
    is_healthy, error_message = check_conversation_health(conversation, max_age_minutes=60)
    if not is_healthy:
        await send_conversation_expired_message(message, "question approval", error_message or "Conversation health check failed")
        if user_id in jam_approval_conversations:
            del jam_approval_conversations[user_id]
        return

    # Handle pre-trivia approval context
    if conversation.get('context') == 'pre_trivia':
        # ✅ FIX #6: Validate numbered input (14/14) - FINAL VALIDATION
        valid_options = ['1', '2']
        if not validate_numbered_input(content, valid_options):
            await message.reply(create_invalid_input_message(content, valid_options, "approve, reject"))
            return

        if content == '1':  # Approve
            # ✅ FIX #2: Store approved question ID in config for 11 AM posting
            question_data = conversation.get('data', {}).get('question_data', {})
            question_id = question_data.get('id')

            if question_id and db:
                try:
                    db.set_config_value('trivia_approved_question_id', str(question_id))
                    print(f"✅ FIX #2: Stored approved question ID {question_id} for 11:00 AM posting")
                    await message.reply("✅ **Pre-Trivia Question Approved.** Question #{} will be posted automatically at 11:00 AM.".format(question_id))
                except Exception as e:
                    print(f"⚠️ FIX #2: Failed to store approved question ID: {e}")
                    await message.reply("✅ **Pre-Trivia Question Approved.** It will be posted automatically at 11:00 AM.")
            else:
                await message.reply("✅ **Pre-Trivia Question Approved.** It will be posted automatically at 11:00 AM.")

            del jam_approval_conversations[user_id]
        elif content == '2':  # Reject
            # Mark the rejected question as rejected
            question_data = conversation.get('data', {}).get('question_data', {})
            question_id = question_data.get('id')

            if question_id and db:
                try:
                    success = db.trivia.reject_trivia_question(question_id)  # type: ignore
                    if success:
                        print(f"✅ PRE-TRIVIA REJECTION: Updated question #{question_id} status to rejected")
                    else:
                        print(f"⚠️ PRE-TRIVIA REJECTION: Failed to update status for question #{question_id}")
                except Exception as e:
                    print(f"⚠️ PRE-TRIVIA REJECTION: Status update error: {e}")

            await message.reply("🔄 **Question Rejected.** Searching for alternative question...")

            # ✅ FIX: Delete old conversation BEFORE starting new approval
            if user_id in jam_approval_conversations:
                del jam_approval_conversations[user_id]
                print(f"✅ Cleared old conversation state before replacement")

            # Automatically fetch next available question
            try:
                avoid_category = question_data.get('category')
                next_question = db.get_next_trivia_question(
                    exclude_user_id=JAM_USER_ID,
                    avoid_category=avoid_category
                )

                if next_question:
                    # Calculate dynamic answer if needed
                    if next_question.get('is_dynamic') and next_question.get('dynamic_query_type'):
                        from bot.handlers.trivia.analytics import calculate_dynamic_answer
                        calculated_answer = calculate_dynamic_answer(db, next_question['dynamic_query_type'])
                        next_question['correct_answer'] = calculated_answer

                    # Start new approval workflow for replacement question
                    await message.reply(
                        f"🎯 **Alternative Question Found**\n\n"
                        f"Presenting replacement question for your approval:"
                    )

                    # Send the new question for approval (reuse the approval workflow)
                    success = await start_pre_trivia_approval(next_question)

                    if not success:
                        await message.reply(
                            "⚠️ **Could not start approval for replacement.** "
                            "Please use `!starttrivia` manually at 11:00 AM."
                        )
                else:
                    await message.reply(
                        "⚠️ **No Alternative Questions Available**\n\n"
                        "The question pool is empty. You'll need to either:\n"
                        "• Generate a new question with `!generatequestions 1`\n"
                        "• Start trivia manually with `!starttrivia` at 11:00 AM"
                    )
            except Exception as e:
                print(f"❌ Error fetching replacement question: {e}")
                await message.reply(
                    "❌ **Error finding replacement.** Please start trivia manually at 11:00 AM."
                )
        else:
            await message.reply("⚠️ Invalid input. Please respond with **1** (Approve) or **2** (Reject).")
        return

    timeout_minutes = 180  # 3 hours - extended for flexible approval timing
    last_activity = conversation.get('last_activity', datetime.now(ZoneInfo("Europe/London")))
    if datetime.now(ZoneInfo("Europe/London")) > last_activity + timedelta(minutes=timeout_minutes):
        print(f"⌛️ JAM APPROVAL: Detected expired conversation for user {user_id}. Cleaning up.")

        # Mark as expired in the database if a session ID exists
        session_id = conversation.get('session_id')
        if session_id:
            db.complete_approval_session(session_id, 'expired')

        # Remove from memory
        del jam_approval_conversations[user_id]

        # Inform the user and stop processing.
        question_id_for_command = (conversation.get('data', {}).get('question_data', {}).get('id', 'Unknown'))
        await message.reply(
            f"⌛️ **Approval session timed out.**\n\n"
            f"Your previous conversation has ended due to inactivity.\n\n"
            f"**To Resume:**\n"
            f"• Use `!approvequestion auto` to pick up the next pending question\n"
            f"• Use `!approvequestion {question_id_for_command}` to restart approval for this specific question\n"
            f"• Use `!resetapproval` if you encounter any issues starting a new session"
        )
        return

    # Only JAM can use this conversation
    if user_id != JAM_USER_ID:
        print(f"🚫 ACCESS DENIED: User {user_id} attempted to access JAM approval conversation")
        return

    # ✅ CRITICAL: Double-check conversation still exists after all async operations
    if user_id not in jam_approval_conversations:
        print(f"🚫 CONVERSATION CLOSED: Approval conversation for JAM was closed during processing, ignoring message")
        return

    print(f"🔄 JAM APPROVAL: Processing approval conversation (step: {conversation.get('step')})")

    # Update activity
    update_jam_approval_activity(user_id)

    step = conversation.get('step', 'approval')
    data = conversation.get('data', {})
    # content already defined above for pre-trivia check

    try:
        if step == 'approval':
            # Handle approval decision
            if content in ['1', 'approve', 'yes', 'accept']:
                # Approve the question
                question_data = data.get('question_data')
                if question_data:
                    try:
                        # Check database availability
                        if db is None:
                            await message.reply("❌ **Database offline.** Cannot save approved question.")
                            return

                        question_id = None

                        # ✅ NEW: Check if question already exists in database (was persisted during generation)
                        existing_question_id = question_data.get('id')

                        if existing_question_id:
                            # Question was already persisted with pending_approval status - just update status
                            try:
                                success = db.approve_trivia_question(existing_question_id)  # type: ignore
                                if success:
                                    question_id = existing_question_id
                                    print(
                                        f"✅ APPROVAL: Updated question #{question_id} status from pending_approval to available")
                                else:
                                    print(
                                        f"⚠️ APPROVAL: Failed to update status for question #{existing_question_id}, will create new")
                                    existing_question_id = None  # Fall through to creation
                            except Exception as status_error:
                                print(f"⚠️ APPROVAL: Status update failed: {status_error}, will create new")
                                existing_question_id = None  # Fall through to creation

                        if not existing_question_id:
                            # Question not persisted yet (manual submission) - create it
                            question_id = db.add_trivia_question(  # type: ignore
                                question_text=question_data['question_text'],
                                question_type=question_data.get('question_type', 'single_answer'),
                                correct_answer=question_data.get('correct_answer'),
                                multiple_choice_options=question_data.get('multiple_choice_options'),
                                is_dynamic=question_data.get('is_dynamic', False),
                                dynamic_query_type=question_data.get('dynamic_query_type'),
                                category=question_data.get('category', 'ai_generated'),
                                submitted_by_user_id=None,  # AI-generated
                                status='available'  # Set to available immediately for manual submissions
                            )
                            print(f"✅ APPROVAL: Created new question #{question_id} with available status")

                        if question_id:
                            # Get queue status before replying
                            queue_length = get_queue_length()

                            approval_response = (
                                f"✅ **Question Approved Successfully**\n\n"
                                f"The trivia question has been added to the database with ID #{question_id}. "
                                f"It is now available for use in future Trivia Tuesday sessions.\n\n"
                                f"**Question:** {question_data['question_text'][:100]}{'...' if len(question_data['question_text']) > 100 else ''}\n"
                                f"**Answer:** {question_data.get('correct_answer', 'Dynamic calculation')}\n\n")

                            if queue_length > 0:
                                approval_response += f"📬 **Processing next question...** ({queue_length} remaining in queue)\n\n"

                            approval_response += "*Mission intelligence database updated. Question approved for deployment.*"

                            await message.reply(approval_response)
                        else:
                            await message.reply("❌ **Failed to save approved question.** Database error occurred.")

                    except Exception as e:
                        print(f"❌ Error saving approved question: {e}")
                        await message.reply("❌ **Error saving approved question.** Database operation failed.")

                # Clean up conversation FIRST
                if user_id in jam_approval_conversations:
                    del jam_approval_conversations[user_id]
                    print(f"✅ FIX: Cleared approval conversation after approval")

                # ✅ FIX: Auto-process next question in queue
                queue_length = get_queue_length()
                if queue_length > 0:
                    print(f"🔄 FIX: Auto-processing next question in queue ({queue_length} remaining)")
                    await process_next_approval()
                else:
                    print(f"✅ FIX: Queue empty after approval")

            elif content in ['2', 'modify', 'edit', 'change']:
                # Switch to template modification mode
                conversation['step'] = 'template_modification'
                original_data = data.get('question_data', {})
                q_text = original_data.get('question_text', '')
                q_ans = original_data.get('correct_answer', '')
                q_type = original_data.get('question_type', 'single_answer')

                decoys_str = ""
                if q_type == 'multiple_choice':
                    options = original_data.get('multiple_choice_options', [])
                    decoys = [opt for opt in options if opt != q_ans]
                    decoys_str = " | ".join(decoys)

                await message.reply(
                    f"✏️ **Manual Question Editing**\n\n"
                    f"Copy the text block below, make your changes, and send it back to apply the edits.\n"
                    f"*(Make sure to keep the Question:, Answer:, Type:, and Decoys: prefixes)*\n\n"
                    f"```text\n"
                    f"Question: {q_text}\n"
                    f"Answer: {q_ans}\n"
                    f"Type: {q_type}\n"
                    f"Decoys: {decoys_str}\n"
                    f"```"
                )

            elif content in ['3', 'reject', 'no', 'decline']:
                # ✅ NEW: Use reject_trivia_question method for clean status transition
                question_data = data.get('question_data', {})
                question_id = question_data.get('id')

                if question_id and db:
                    # Question already in database - update status to rejected
                    try:
                        success = db.trivia.reject_trivia_question(question_id)  # type: ignore
                        if success:
                            print(f"✅ REJECTION: Updated question #{question_id} status to rejected")
                        else:
                            print(f"⚠️ REJECTION: Failed to update status for question #{question_id}")
                    except Exception as e:
                        print(f"⚠️ REJECTION: Status update error: {e}")
                else:
                    # Question not in database yet (shouldn't happen with new flow, but handle gracefully)
                    print(f"⚠️ REJECTION: Question has no ID, cannot mark as rejected in database")

                # ✅ NEW: Purge any remaining questions in the queue that have the same rejected category
                global jam_approval_queue
                rejected_category = question_data.get('category')

                # Determine how many items we are about to remove
                items_to_remove = [
                    item for item in jam_approval_queue
                    if item.get('type') == 'trivia_question' and
                    item.get('data', {}).get('question_data', {}).get('category') == rejected_category
                ]

                if rejected_category and items_to_remove:
                    # Actually filter the queue
                    jam_approval_queue = [item for item in jam_approval_queue if item not in items_to_remove]

                    # Also mark them as rejected in the DB so they don't linger in pending_approval
                    for item in items_to_remove:
                        q_id = item.get('data', {}).get('question_data', {}).get('id')
                        if q_id and db:
                            try:
                                db.trivia.reject_trivia_question(q_id)
                            except Exception:
                                pass

                    print(
                        f"🗑️ Removed {len(items_to_remove)} pending questions of rejected category '{rejected_category}' from the queue.")

                # ✅ CRITICAL FIX: Get queue length BEFORE clearing conversation
                queue_length = get_queue_length()

                # ✅ CRITICAL FIX: Clear conversation state IMMEDIATELY before any async operations
                if user_id in jam_approval_conversations:
                    del jam_approval_conversations[user_id]
                    print(f"✅ CONVERSATION CLEANUP: Cleared approval conversation immediately (queue: {queue_length})")

                # Notify user of rejection
                rejection_msg = (
                    f"❌ **Question Rejected**\n\n"
                    f"The trivia question has been rejected and marked as 'retired'. "
                    f"It won't be shown again.\n\n"
                )

                if items_to_remove:
                    rejection_msg += f"🧹 Also purged {len(items_to_remove)} other pending questions in the '{rejected_category}' category.\n\n"

                if queue_length > 0:
                    rejection_msg += f"📬 **Processing next question...** ({queue_length} remaining in queue)"
                else:
                    rejection_msg += f"*No more questions pending approval.*"

                await message.reply(rejection_msg)

                # ✅ CRITICAL FIX: Only process queue if there are items AND conversation is cleared
                if queue_length > 0:
                    print(f"🔄 QUEUE PROCESSING: Auto-processing next item ({queue_length} remaining)")
                    await process_next_approval()
                else:
                    print(f"✅ QUEUE EMPTY: No more questions pending, conversation fully cleared")

                # ✅ CRITICAL FIX: Return immediately after rejection to prevent conversation recreation
                return

            else:
                await message.reply(
                    f"⚠️ **Invalid response.** Please respond with **1** (Approve), **2** (Modify), or **3** (Reject).\n\n"
                    f"*Precise input required for approval protocol execution.*"
                )

        elif step == 'template_modification':
            # Parse the incoming template
            import re

            q_match = re.search(r'Question:\s*(.+)', content, re.IGNORECASE)
            a_match = re.search(r'Answer:\s*(.+)', content, re.IGNORECASE)
            t_match = re.search(r'Type:\s*(.+)', content, re.IGNORECASE)
            d_match = re.search(r'Decoys:\s*(.+)', content, re.IGNORECASE)

            if not (q_match and a_match and t_match):
                await message.reply(
                    "⚠️ **Invalid Format**\n\n"
                    "Could not parse your edits. Please ensure your message includes `Question:`, `Answer:`, and `Type:`."
                )
                return

            new_q = q_match.group(1).strip()
            new_a = a_match.group(1).strip()
            new_t = t_match.group(1).strip().lower().replace(' ', '_')

            if new_t not in ['single_answer', 'multiple_choice']:
                await message.reply("⚠️ **Invalid Type**\n\nPlease use either `single_answer` or `multiple_choice` for the Type.")
                return

            new_decoys_list = []
            if new_t == 'multiple_choice':
                d_str = ""
                if d_match:
                    d_str = d_match.group(1).strip()

                if not d_str or d_str.lower() == 'none' or d_str == '-':
                    await message.reply("⚠️ **Missing Decoys**\n\nFor a `multiple_choice` question, you must provide exactly 3 decoys separated by `|` or `,`.")
                    return

                # Split by | or ,
                if '|' in d_str:
                    new_decoys_list = [d.strip() for d in d_str.split('|') if d.strip()]
                else:
                    new_decoys_list = [d.strip() for d in d_str.split(',') if d.strip()]

                if len(new_decoys_list) != 3:
                    await message.reply(f"⚠️ **Invalid Decoys Count**\n\nYou provided {len(new_decoys_list)} decoys. Please provide exactly 3 decoys.")
                    return

            # Set values and call save
            data['modified_question'] = new_q
            data['modified_answer'] = new_a
            data['modified_type'] = new_t
            if new_t == 'multiple_choice':
                import random
                options = [new_a] + new_decoys_list
                random.shuffle(options)
                data['modified_options'] = options
            else:
                data['modified_options'] = None

            await save_final_modifications(message, data, user_id)

        # Update conversation state
        conversation['data'] = data
        jam_approval_conversations[user_id] = conversation

    except Exception as e:
        print(f"Error in JAM approval conversation: {e}")
        # Clean up on error
        if user_id in jam_approval_conversations:
            del jam_approval_conversations[user_id]

async def start_jam_question_approval(question_data: Dict[str, Any]) -> bool:
    """Start JAM approval workflow for a generated trivia question with persistent storage"""
    try:
        print(
            f"🚀 Starting persistent JAM approval workflow for question: {question_data.get('question_text', 'Unknown')[:50]}...")

        # Get bot instance using centralized access function
        bot_instance = _get_bot_instance()

        if not bot_instance:
            print("❌ Could not find bot instance for JAM approval")
            return False

        # ✅ FIX: Defensive cleanup - clear ANY conflicting conversation states before starting
        try:
            # Clear ALL conversation types for JAM to prevent conflicts
            if JAM_USER_ID in jam_approval_conversations:
                del jam_approval_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared existing approval conversation for JAM")

            if JAM_USER_ID in mod_trivia_conversations:
                del mod_trivia_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting trivia conversation for JAM")

            if JAM_USER_ID in announcement_conversations:
                del announcement_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting announcement conversation for JAM")

            # Clean up expired sessions
            cleanup_jam_approval_conversations()
            db.cleanup_expired_approval_sessions()
            print("✅ Cleaned up existing approval conversations and sessions")
        except Exception as cleanup_e:
            print(f"⚠️ Error during cleanup: {cleanup_e}")

        # Create persistent approval session in database
        try:
            session_id = db.create_approval_session(
                user_id=JAM_USER_ID,
                session_type='question_approval',
                conversation_step='approval',
                question_data=question_data,
                timeout_minutes=180  # 3 hours - extended for flexible approval timing
            )

            if not session_id:
                print("❌ Failed to create persistent approval session")
                return False

            print(f"✅ Created persistent approval session {session_id}")
        except Exception as db_e:
            print(f"⚠️ Database session creation failed, using memory fallback: {db_e}")
            session_id = None

        # Get JAM user with retry logic
        jam_user = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                print(f"🔍 Attempting to fetch JAM user {JAM_USER_ID} (attempt {attempt + 1}/{max_attempts})")
                jam_user = await bot_instance.fetch_user(JAM_USER_ID)
                if jam_user:
                    print(f"✅ Successfully fetched JAM user: {jam_user.name}#{jam_user.discriminator}")
                    break
                else:
                    print(f"⚠️ Fetch returned None for JAM user {JAM_USER_ID}")
            except Exception as e:
                print(f"⚠️ Error fetching JAM user (attempt {attempt + 1}): {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(2)  # Wait before retry
                else:
                    print(f"❌ Failed to fetch JAM user after {max_attempts} attempts")
                    return False

        if not jam_user:
            print(f"❌ Could not fetch JAM user {JAM_USER_ID} after all attempts")
            return False

        # Initialize approval conversation
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        jam_approval_conversations[JAM_USER_ID] = {
            'step': 'approval',
            'data': {'question_data': question_data},
            'last_activity': uk_now,
            'initiated_at': uk_now,
        }
        print("✅ Initialized JAM approval conversation state")

        # Create approval message with enhanced formatting
        question_text = question_data.get('question_text') or 'Unknown question'
        correct_answer = question_data.get('correct_answer') or 'Dynamic calculation'
        question_type = question_data.get('question_type') or 'single_answer'
        category = question_data.get('category') or 'ai_generated'

        approval_msg = (
            f"🧠 **TRIVIA QUESTION APPROVAL REQUIRED**\n\n"
            f"A new trivia question has been generated and requires your approval before being added to the database.\n\n"
            f"**Question Type:** {question_type.replace('_', ' ').title()}\n"
            f"**Category:** {category.replace('_', ' ').title()}\n"
            f"**Question:** {question_text}\n\n"
            f"**Answer:** {correct_answer}\n\n")

        # Add multiple choice options if applicable
        if question_data.get('multiple_choice_options') and question_data.get('question_type') == 'multiple_choice':
            options_text = '\n'.join([f"**{chr(65+i)}.** {option}"
                                      for i, option in enumerate(question_data['multiple_choice_options'])])
            approval_msg += f"**Answer Choices:**\n{options_text}\n\n"

        # Add dynamic question info if applicable
        if question_data.get('is_dynamic'):
            approval_msg += f"**Note:** This is a dynamic question - the answer will be calculated from the gaming database when used.\n\n"

        approval_msg += (
            f"📚 **Available Actions:**\n"
            f"**1.** ✅ **Approve** - Add this question to the database as-is\n"
            f"**2.** ✏️ **Modify** - Edit question and/or answer\n"
            f"**3.** ❌ **Reject** - Discard this question and generate an alternative\n\n"
            f"Please respond with **1**, **2**, or **3**.\n\n"
            f"*Question approval required for Trivia Tuesday deployment.*"
        )

        # Send approval request to JAM with retry logic
        message_sent = False
        max_send_attempts = 3
        for attempt in range(max_send_attempts):
            try:
                print(f"📤 Attempting to send approval message to JAM (attempt {attempt + 1}/{max_send_attempts})")
                await jam_user.send(approval_msg)
                message_sent = True
                print(f"✅ Successfully sent question approval request to JAM")
                break
            except discord.Forbidden:
                print(f"❌ JAM has DMs disabled or blocked the bot")
                return False
            except discord.HTTPException as e:
                print(f"⚠️ HTTP error sending message (attempt {attempt + 1}): {e}")
                if attempt < max_send_attempts - 1:
                    await asyncio.sleep(2)  # Wait before retry
                else:
                    print(f"❌ Failed to send message after {max_send_attempts} attempts")
                    return False
            except Exception as e:
                print(f"⚠️ Unexpected error sending message (attempt {attempt + 1}): {e}")
                if attempt < max_send_attempts - 1:
                    await asyncio.sleep(2)  # Wait before retry
                else:
                    print(f"❌ Failed to send message due to unexpected error: {e}")
                    return False

        if message_sent:
            print("✅ JAM approval workflow started successfully")
            return True
        else:
            print("❌ Failed to send approval message to JAM")
            # Clean up conversation state if message failed
            if JAM_USER_ID in jam_approval_conversations:
                del jam_approval_conversations[JAM_USER_ID]
            return False

    except Exception as e:
        print(f"❌ Critical error in JAM approval workflow: {e}")
        traceback.print_exc()

        # Clean up conversation state on critical error
        try:
            if JAM_USER_ID in jam_approval_conversations:
                del jam_approval_conversations[JAM_USER_ID]
        except BaseException:
            pass

        return False

async def start_pre_trivia_approval(question_data: Dict[str, Any]) -> bool:
    """Start pre-trivia approval workflow (1 hour before Trivia Tuesday)"""
    try:
        # Get bot instance
        import sys
        bot_instance = None
        for name, obj in sys.modules.items():
            if hasattr(obj, 'bot') and hasattr(obj.bot, 'user') and obj.bot.user:
                bot_instance = obj.bot
                break

        if not bot_instance:
            print("❌ Could not find bot instance for pre-trivia approval")
            return False

        # ✅ FIX: Defensive cleanup - clear ANY conflicting conversation states before starting
        try:
            if JAM_USER_ID in jam_approval_conversations:
                del jam_approval_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting approval conversation for JAM before pre-trivia")

            if JAM_USER_ID in mod_trivia_conversations:
                del mod_trivia_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting trivia conversation for JAM before pre-trivia")

            if JAM_USER_ID in announcement_conversations:
                del announcement_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting announcement conversation for JAM before pre-trivia")
        except Exception as cleanup_e:
            print(f"⚠️ Error during pre-trivia defensive cleanup: {cleanup_e}")

        # Get current UK time
        uk_now = datetime.now(ZoneInfo("Europe/London"))

        jam_approval_conversations[JAM_USER_ID] = {
            'step': 'approval',
            'data': {'question_data': question_data},
            'context': 'pre_trivia',
            'last_activity': uk_now,
            'initiated_at': uk_now,
        }

        # Get JAM user
        try:
            jam_user = await bot_instance.fetch_user(JAM_USER_ID)
            if not jam_user:
                print(f"❌ Could not fetch JAM user {JAM_USER_ID}")
                return False
        except Exception as e:
            print(f"❌ Error fetching JAM user: {e}")
            return False

        # Create pre-trivia approval message
        question_text = question_data.get('question_text', 'Unknown question')
        correct_answer = question_data.get('correct_answer', 'Dynamic calculation')
        question_type = question_data.get('question_type', 'single_answer')

        uk_now = datetime.now(ZoneInfo("Europe/London"))
        trivia_time = uk_now.replace(hour=11, minute=0, second=0, microsecond=0)

        pre_approval_msg = (
            f"⏰ **TRIVIA TUESDAY - PRE-APPROVAL REQUIRED**\n\n"
            f"Trivia Tuesday begins in 1 hour ({trivia_time.strftime('%H:%M UK time')}). "
            f"The following question has been selected for today's session:\n\n"
            f"**Question ID:** {question_data.get('id', 'Generated')}\n"
            f"**Type:** {question_type.replace('_', ' ').title()}\n"
            f"**Question:** {question_text}\n\n"
            f"**Answer:** {correct_answer}\n\n"
        )

        # Add multiple choice options if applicable
        if question_data.get('multiple_choice_options'):
            options_text = '\n'.join([f"**{chr(65+i)}.** {option}"
                                      for i, option in enumerate(question_data['multiple_choice_options'])])
            pre_approval_msg += f"**Answer Choices:**\n{options_text}\n\n"

        pre_approval_msg += (
            f"📚 **Decision Required:**\n"
            f"**1.** ✅ **Approve** - This question will be posted at 11:00 AM as scheduled\n"
            f"**2.** ❌ **Reject** - An alternative question will be selected and presented for approval\n\n"
            f"Please respond with **1** or **2**.\n\n"
            f"*Time-sensitive approval required for today's Trivia Tuesday session.*"
        )

        # Send pre-trivia approval request to JAM
        await jam_user.send(pre_approval_msg)
        print(f"✅ Sent pre-trivia approval request to JAM")
        return True

    except Exception as e:
        print(f"❌ Error starting pre-trivia approval workflow: {e}")
        return False



def is_jam_approval_active() -> bool:
    """Check if JAM currently has an active approval conversation."""
    global jam_approval_active

    # Check both the flag and actual conversation states
    has_active_conversation = (
        JAM_USER_ID in jam_approval_conversations or
        JAM_USER_ID in weekly_announcement_approvals or
        JAM_USER_ID in game_review_conversations or
        JAM_USER_ID in sync_approval_conversations  # FIX: Include sync approvals
    )

    # Sync the flag with actual state
    jam_approval_active = has_active_conversation

    return has_active_conversation

async def _send_weekly_announcement_approval(announcement_id: int, content: str, day: str):
    """Internal function to actually send weekly announcement approval to JAM."""
    try:
        bot = _get_bot_instance()
        if not bot:
            return

        jam_user = await bot.fetch_user(JAM_USER_ID)
        if not jam_user:
            return

        # ✅ FIX: Defensive cleanup - clear ANY conflicting conversation states before starting
        try:
            if JAM_USER_ID in jam_approval_conversations:
                del jam_approval_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting approval conversation for JAM before weekly announcement")

            if JAM_USER_ID in mod_trivia_conversations:
                del mod_trivia_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting trivia conversation for JAM before weekly announcement")

            if JAM_USER_ID in announcement_conversations:
                del announcement_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting announcement conversation for JAM before weekly announcement")
        except Exception as cleanup_e:
            print(f"⚠️ Error during weekly announcement defensive cleanup: {cleanup_e}")

        uk_now = datetime.now(ZoneInfo("Europe/London"))

        # Show queue status
        queue_length = get_queue_length()
        queue_status = f" ({queue_length + 1} of {queue_length + 1})" if queue_length > 0 else ""

        weekly_announcement_approvals[JAM_USER_ID] = {
            'step': 'approval', 'announcement_id': announcement_id, 'day': day,
            'original_content': content, 'last_activity': uk_now
        }

        approval_msg = (
            f"🤖 **{day.title()} Announcement Approval Required**{queue_status}\n\n"
            f"The following message has been generated for this morning's greeting. Please review and approve.\n\n"
            f"```\n{content}\n```\n"
            f"**Available Actions:**\n"
            f"**1.** ✅ **Approve** - Post this message as-is\n"
            f"**2.** 🤖 **AI Amend** - Provide instructions for AI to modify\n"
            f"**3.** ✏️ **Manual Edit** - Directly edit the text yourself\n"
            f"**4.** 🔄 **Regenerate** - Generate new version from data\n"
            f"**5.** ❌ **Cancel** - Do not send a greeting today\n\n"
            f"Please respond with **1, 2, 3, 4, or 5**."
        )

        if queue_length > 0:
            approval_msg += f"\n\n⏳ **Queue Status:** {queue_length} more approvals pending after this one"

        await jam_user.send(approval_msg)
        print(f"✅ Sent {day.title()} announcement to JAM for approval.")
    except Exception as e:
        print(f"❌ Error sending weekly announcement approval: {e}")

async def save_final_modifications(message, data: Dict[str, Any], user_id: int):
    """Save all final modifications to the database"""
    try:
        if db is None:
            await message.reply("❌ **Database offline.** Cannot save modified question.")
            return

        original_data = data.get('question_data', {})

        # Use modified values if available, otherwise use originals
        final_question = data.get('modified_question', original_data.get('question_text', ''))
        final_answer = data.get('modified_answer', original_data.get('correct_answer'))
        final_type = data.get('modified_type', original_data.get('question_type', 'single_answer'))

        final_options = data.get('modified_options')
        if final_options is None and final_type == 'multiple_choice':
            final_options = original_data.get('multiple_choice_options')

        question_id = db.add_trivia_question(  # type: ignore
            question_text=final_question,
            question_type=final_type,
            correct_answer=final_answer,
            multiple_choice_options=final_options,
            is_dynamic=original_data.get('is_dynamic', False),
            dynamic_query_type=original_data.get('dynamic_query_type'),
            category=original_data.get('category', 'ai_generated_modified'),
            submitted_by_user_id=JAM_USER_ID,  # Mark as JAM-modified
        )

        if question_id:
            # Show summary of all changes
            changes_summary = []
            if data.get('modified_question'):
                changes_summary.append(f"• **Question text** updated")
            if data.get('modified_answer'):
                changes_summary.append(f"• **Answer** updated to: {final_answer}")
            if data.get('modified_type'):
                changes_summary.append(f"• **Question type** changed to: {final_type.replace('_', ' ').title()}")

            changes_text = '\n'.join(changes_summary) if changes_summary else "• No modifications made"

            await message.reply(
                f"✅ **All Modifications Saved Successfully**\n\n"
                f"Your modified question has been saved to the database with ID #{question_id}.\n\n"
                f"**Changes Applied:**\n{changes_text}\n\n"
                f"**Final Question:** {final_question[:100]}{'...' if len(final_question) > 100 else ''}\n\n"
                f"*Mission intelligence database updated with all your modifications. Question approved for deployment.*"
            )
        else:
            await message.reply("❌ **Failed to save modified question.** Database error occurred.")

    except Exception as e:
        print(f"❌ Error saving final modifications: {e}")
        await message.reply("❌ **Error saving modified question.** Database operation failed.")

    # Clean up conversation
    if user_id in jam_approval_conversations:
        del jam_approval_conversations[user_id]

    # ✅ FIX: Process next item in approval queue
    queue_length = get_queue_length()
    if queue_length > 0:
        print(f"🔄 AUTO-QUEUE: Processing next approval after modifications ({queue_length} remaining)")
        await process_next_approval()
    else:
        print(f"✅ QUEUE: Empty after modifications")

async def start_game_review_approval(game_data: Dict[str, Any]) -> bool:
    """Start game review approval workflow for low-confidence matches"""
    try:
        bot = _get_bot_instance()
        if not bot:
            print("❌ Cannot start game review - bot instance not available")
            return False

        jam_user = await bot.fetch_user(JAM_USER_ID)
        if not jam_user:
            print(f"❌ Cannot reach JAM for game review")
            return False

        # ✅ FIX: Defensive cleanup - clear ANY conflicting conversation states before starting
        try:
            if JAM_USER_ID in jam_approval_conversations:
                del jam_approval_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting approval conversation for JAM before game review")

            if JAM_USER_ID in mod_trivia_conversations:
                del mod_trivia_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting trivia conversation for JAM before game review")

            if JAM_USER_ID in announcement_conversations:
                del announcement_conversations[JAM_USER_ID]
                print(f"✅ FIX: Cleared conflicting announcement conversation for JAM before game review")
        except Exception as cleanup_e:
            print(f"⚠️ Error during game review defensive cleanup: {cleanup_e}")

        # Create session in database
        session_id = db.create_game_review_session(
            user_id=JAM_USER_ID,
            original_title=game_data['original_title'],
            extracted_name=game_data['extracted_name'],
            confidence_score=game_data['confidence_score'],
            alternative_names=game_data.get('alternative_names', []),
            source=game_data['source'],
            igdb_data=game_data.get('igdb_data', {}),
            video_url=game_data.get('video_url')
        )

        if not session_id:
            print("❌ Failed to create game review session")
            return False

        # Initialize conversation
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        game_review_conversations[JAM_USER_ID] = {
            'step': 'review',
            'session_id': session_id,
            'data': game_data,
            'last_activity': uk_now
        }

        # Build approval message
        alt_names = game_data.get('alternative_names', [])
        igdb_matched = len(alt_names) > 0

        # Build IGDB match string safely
        if not igdb_matched:
            igdb_match_text = "❌ No match found"
        else:
            igdb_match_text = f"✓ {', '.join(alt_names[:3])}"

        approval_msg = (
            f"🎮 **GAME MATCH REVIEW REQUIRED**\n\n"
            f"Low-confidence game extraction detected during {game_data['source'].title()} sync:\n\n"
            f"**Original Title:** {game_data['original_title']}\n"
            f"**Extracted Name:** `{game_data['extracted_name']}`\n"
            f"**Confidence:** {game_data['confidence_score']:.2f} (LOW)\n"
            f"**IGDB Match:** {igdb_match_text}\n"
        )

        if game_data.get('video_url'):
            approval_msg += f"**Video:** {game_data['video_url']}\n"

        approval_msg += (
            "\n**Actions:**\n"
            "**1.** ✅ Accept - Use extracted name as-is\n"
            "**2.** 🔧 Correct - Provide the real game name\n"
            "**3.** ❌ Skip - Don't import this entry\n\n"
            "Respond with **1**, **2**, or **3**."
        )

        await jam_user.send(approval_msg)
        print(f"✅ Started game review session {session_id}")
        return True

    except Exception as e:
        print(f"❌ Error starting game review: {e}")
        return False

async def start_sync_approval(sync_session_id: str, summary: Dict[str, Any]) -> bool:
    """
    Send sync approval request to JAM via DM.

    Args:
        sync_session_id: UUID for this sync session
        summary: Summary dict from get_staging_session_summary()

    Returns:
        True if message sent successfully
    """
    try:
        bot = _get_bot_instance()
        if not bot:
            print("❌ SYNC APPROVAL: Bot instance not available")
            return False

        user = await bot.fetch_user(JAM_USER_ID)
        if not user:
            print(f"❌ SYNC APPROVAL: Could not fetch JAM user {JAM_USER_ID}")
            return False

        # Build approval message
        new_games = summary.get('new_games', [])
        updates = summary.get('updates', [])
        total_count = summary.get('total_count', 0)

        message = "🔄 **Database Sync Complete**\n\n"
        message += f"📊 **{total_count} games detected**\n\n"

        # Show new games with IDs
        if new_games:
            message += f"🆕 **New Games ({len(new_games)}):**\n"
            for game in new_games[:10]:  # Limit to first 10
                game_data = game['game_data']
                confidence = game.get('confidence_score', 1.0)
                platform = game.get('source_platform', 'unknown')
                playtime = game_data.get('total_playtime_minutes', 0)
                episodes = game_data.get('total_episodes', 0)

                warning = " ⚠️" if confidence < 0.75 else ""
                message += (
                    f"{game['id']}. **{game_data['canonical_name']}** "
                    f"({platform.title()}, {episodes} ep, "
                    f"{playtime//60}h {playtime%60}m, {int(confidence*100)}%){warning}\n"
                )

            if len(new_games) > 10:
                message += f"... and {len(new_games) - 10} more\n"
            message += "\n"

        # Show updates
        if updates:
            message += f"🔄 **Updated Games ({len(updates)}):**\n"
            for game in updates[:5]:  # Show first 5
                game_data = game['game_data']
                existing_episodes = game_data.get('existing_episodes', 0)
                new_episodes = game_data.get('total_episodes', 0)
                added_episodes = new_episodes - existing_episodes

                message += (
                    f"{game['id']}. **{game_data['canonical_name']}** "
                    f"(+{added_episodes} ep)\n"
                )

            if len(updates) > 5:
                message += f"... and {len(updates) - 5} more\n"
            message += "\n"

        message += "**Choose an action:**\n"
        message += "✅ **1** - Approve all and commit to database\n"
        message += "🔍 **2** - Review individually\n"
        message += "❌ **3** - Cancel entire sync\n"

        await user.send(message)
        print(f"✅ SYNC APPROVAL: Sent approval request to JAM (session {sync_session_id})")

        # Store conversation state
        sync_approval_conversations[JAM_USER_ID] = {
            'type': 'sync_approval',
            'sync_session_id': sync_session_id,
            'stage': 'awaiting_choice',
            'summary': summary,
            'started_at': datetime.now(ZoneInfo("Europe/London"))
        }

        return True

    except Exception as e:
        print(f"❌ SYNC APPROVAL: Error sending approval request: {e}")
        import traceback
        traceback.print_exc()
        return False

