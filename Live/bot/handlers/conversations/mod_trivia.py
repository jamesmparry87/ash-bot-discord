from .utils import send_conversation_expired_message, _infer_dynamic_query_type

from .core import _get_bot_instance, db, mod_trivia_conversations
from .utils import check_escape_command, check_conversation_health, track_conversation_step, increment_invalid_input_count, reset_invalid_input_count, validate_numbered_input, create_invalid_input_message

import asyncio
import re
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands
from ..config import (
    ANNOUNCEMENTS_CHANNEL_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    MOD_ALERT_CHANNEL_ID,
    YOUTUBE_UPLOADS_CHANNEL_ID,
)
from ..database import get_database
from ..utils.permissions import get_user_communication_tier, user_is_mod_by_id
from .ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response

def cleanup_mod_trivia_conversations():
    """Remove mod trivia conversations inactive for more than 1 hour"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=1)
    expired_users = [
        user_id for user_id,
        data in mod_trivia_conversations.items() if data.get(
            "last_activity",
            uk_now) < cutoff_time]
    for user_id in expired_users:
        del mod_trivia_conversations[user_id]
        print(f"Cleaned up expired mod trivia conversation for user {user_id}")

def update_mod_trivia_activity(user_id: int):
    """Update last activity time for mod trivia conversation"""
    if user_id in mod_trivia_conversations:
        mod_trivia_conversations[user_id]["last_activity"] = datetime.now(
            ZoneInfo("Europe/London"))

async def handle_mod_trivia_conversation(message: discord.Message) -> None:
    """Handle the interactive DM conversation for mod trivia question submission"""
    user_id = message.author.id
    conversation = mod_trivia_conversations.get(user_id)

    if not conversation:
        return

    content = message.content.strip()

    # ✅ FIX #1: Check for escape command
    if check_escape_command(content):
        await message.reply(
            f"❌ **Question Submission Cancelled**\n\n"
            f"The trivia question submission has been cancelled at your request. "
            f"All progress has been discarded.\n\n"
            f"*You can start a new submission with `!addtriviaquestion`*"
        )
        if user_id in mod_trivia_conversations:
            del mod_trivia_conversations[user_id]
        return

    # ✅ FIX #1: Check conversation health
    is_healthy, error_message = check_conversation_health(conversation, max_age_minutes=60)
    if not is_healthy:
        await send_conversation_expired_message(message, "trivia question submission", error_message or "Conversation health check failed")
        if user_id in mod_trivia_conversations:
            del mod_trivia_conversations[user_id]
        return

    # Update activity
    update_mod_trivia_activity(user_id)

    step = conversation.get('step', 'initial')
    data = conversation.get('data', {})

    try:
        if step == 'initial':
            # User wants to add a trivia question
            if any(keyword in content.lower()
                   for keyword in ['trivia', 'question', 'add', 'submit']):
                conversation['step'] = 'question_type_selection'

                greeting = "moderator" if await user_is_mod_by_id(user_id) else "personnel"

                await message.reply(
                    f"🧠 **TRIVIA QUESTION SUBMISSION PROTOCOL**\n\n"
                    f"Authorization confirmed, {greeting}. Initiating secure trivia question submission sequence.\n\n"
                    f"📋 **Question Type Selection:**\n"
                    f"**1.** 🎯 **Question Only** - Provide question text for me to calculate the answer from Captain Jonesy's gaming database\n"
                    f"**2.** 🎯 **Question + Answer** - Provide both question and answer for specific gameplay moments or experiences\n\n"
                    f"Please respond with **1** for database-calculated questions or **2** for manual question+answer pairs.\n\n"
                    f"*Mission intelligence protocols await your selection.*"
                )
            else:
                # Generic conversation starter, ask what they want to do
                await message.reply(
                    f"🧠 **Trivia Question Submission Interface**\n\n"
                    f"Greetings, moderator. I can assist with trivia question submissions for Trivia Tuesday.\n\n"
                    f"**Available Functions:**\n"
                    f"• Submit database-powered questions (I calculate answers from gaming data)\n"
                    f"• Submit complete question+answer pairs for specific gaming moments\n\n"
                    f"Would you like to **add a trivia question**? Please respond with 'yes' to begin the submission process.\n\n"
                    f"*All submissions are prioritized over AI-generated questions for upcoming Trivia Tuesday sessions.*"
                )

        elif step == 'question_type_selection':
            # Validate input first
            valid_options = ['1', '2']
            if not validate_numbered_input(content, valid_options):
                await message.reply(create_invalid_input_message(content, valid_options, "database, manual, question only, question answer"))
                return

            if content in ['1', 'database', 'question only', 'calculate']:
                data['question_type'] = 'database_calculated'
                conversation['step'] = 'question_input'

                await message.reply(
                    f"🎯 **Database-Calculated Question Selected**\n\n"
                    f"Please provide your trivia question. I will calculate the answer using Captain Jonesy's gaming database just before posting.\n\n"
                    f"**Examples of good database questions:**\n"
                    f"• What is Jonesy's longest playthrough by total hours?\n"
                    f"• Which horror game has Jonesy played the most episodes of?\n"
                    f"• What game series has taken the most total time to complete?\n"
                    f"• Which game has the highest average minutes per episode?\n\n"
                    f"**Please provide your question text:**"
                )

            elif content in ['2', 'manual', 'question answer', 'both']:
                data['question_type'] = 'manual_answer'
                conversation['step'] = 'format_selection'

                await message.reply(
                    f"🎯 **Manual Question+Answer Selected**\n\n"
                    f"Please select the question format:\n\n"
                    f"**1.** 📝 **Single Answer** - Users type the answer directly\n"
                    f"**2.** 🔤 **Multiple Choice** - Users select from A, B, C, D\n\n"
                    f"Please respond with **1** or **2**."
                )
            else:
                await message.reply(
                    f"⚠️ **Invalid selection.** Please respond with **1** for database questions or **2** for manual questions.\n\n"
                    f"*Precision is essential for proper protocol execution.*"
                )

        elif step == 'format_selection':
            # Validate input first
            valid_options = ['1', '2']
            if not validate_numbered_input(content, valid_options):
                await message.reply(create_invalid_input_message(content, valid_options, "single, multiple, single answer, multiple choice"))
                return

            if content in ['1', 'single', 'single answer']:
                data['format'] = 'single_answer'
                conversation['step'] = 'question_input'
                await message.reply(
                    f"📝 **Single Answer Format Selected**\n\n"
                    f"Please provide your trivia question text.\n\n"
                    f"**Example:** What was the first game Jonesy streamed on Twitch?\n\n"
                    f"**Please provide your question text:**"
                )
            elif content in ['2', 'multiple', 'multiple choice']:
                data['format'] = 'multiple_choice'
                conversation['step'] = 'question_input'
                await message.reply(
                    f"🔤 **Multiple Choice Format Selected**\n\n"
                    f"Please provide your trivia question text (without the choices).\n\n"
                    f"**Example:** Which of these games has Jonesy NOT played?\n\n"
                    f"**Please provide your question text:**"
                )
            else:
                await message.reply("⚠️ **Invalid selection.** Please respond with **1** (Single Answer) or **2** (Multiple Choice).")

        elif step == 'question_input':
            # Store the question and determine next step based on type
            data['question_text'] = content

            if data.get('question_type') == 'manual_answer':
                if data.get('format') == 'multiple_choice':
                    # Start asking for choices one at a time
                    conversation['step'] = 'choice_a_input'
                    data['choices'] = []  # Initialize empty choices list
                    await message.reply(
                        f"🔤 **Question Recorded**\n\n"
                        f"**Your Question:** {content}\n\n"
                        f"Now let's add the multiple choice options one at a time.\n\n"
                        f"**What should choice A be?**"
                    )
                else:
                    conversation['step'] = 'answer_input'
                    await message.reply(
                        f"📝 **Question Recorded**\n\n"
                        f"**Your Question:** {content}\n\n"
                        f"**Now provide the correct answer.**\n\n"
                        f"**Please provide the correct answer:**"
                    )
            else:
                conversation['step'] = 'preview'
                question_text = data['question_text']

                # Infer query type AND parameters from the question text
                inferred_query_type, parameter = _infer_dynamic_query_type(question_text)
                data['dynamic_query_type'] = inferred_query_type
                data['dynamic_parameter'] = parameter

                calculated_answer = "Could not be determined. The question may be too ambiguous."
                if inferred_query_type:
                    if db:
                        from bot.handlers.trivia.analytics import calculate_dynamic_answer
                        answer = calculate_dynamic_answer(db, inferred_query_type, parameter)
                        if answer:
                            calculated_answer = answer
                        else:
                            calculated_answer = "Could not be determined. No data found for this query."

                preview_msg = (
                    f"📋 **Trivia Question Preview**\n\n"
                    f"**Question:** {question_text}\n\n"
                    f"**Current Answer (calculated now):** {calculated_answer}\n"
                    f"**Note:** *This answer is dynamic and will be recalculated when the question is used.*\n\n"
                    f"**Type:** Database-Calculated\n"
                    f"**Source:** Moderator Submission\n\n"
                    f"📚 **Available Actions:**\n"
                    f"**1.** ✅ **Submit Question**\n"
                    f"**2.** ✏️ **Edit Question**\n"
                    f"**3.** ❌ **Cancel**\n\n"
                    f"Please respond with **1**, **2**, or **3**."
                )
                await message.reply(preview_msg)

        elif step == 'choice_a_input':
            # Store choice A and ask for choice B
            data['choices'].append(content.strip())
            conversation['step'] = 'choice_b_input'
            await message.reply(
                f"✅ **Choice A recorded:** {content}\n\n"
                f"**What should choice B be?**"
            )

        elif step == 'choice_b_input':
            # Store choice B and ask for choice C
            data['choices'].append(content.strip())
            conversation['step'] = 'choice_c_input'
            await message.reply(
                f"✅ **Choice B recorded:** {content}\n\n"
                f"**What should choice C be?**"
            )

        elif step == 'choice_c_input':
            # Store choice C and ask for choice D
            data['choices'].append(content.strip())
            conversation['step'] = 'choice_d_input'
            await message.reply(
                f"✅ **Choice C recorded:** {content}\n\n"
                f"**What should choice D be?**"
            )

        elif step == 'choice_d_input':
            # Store choice D and move to answer input
            data['choices'].append(content.strip())
            conversation['step'] = 'answer_input'

            # Show all choices for review
            choices_text = "\n".join([f"**{chr(65+i)}.** {choice}" for i, choice in enumerate(data['choices'])])

            await message.reply(
                f"✅ **Choice D recorded:** {content}\n\n"
                f"**All Choices:**\n{choices_text}\n\n"
                f"**Now provide the correct answer letter (A, B, C, or D).**\n\n"
                f"**Please provide the correct letter:**"
            )

        elif step == 'answer_input':
            # Store the answer and move to preview
            data['correct_answer'] = content
            conversation['step'] = 'preview'

            question_text = data['question_text']
            is_multiple_choice = data.get('format') == 'multiple_choice'

            # Validate multiple choice answer
            if is_multiple_choice:
                answer_upper = content.strip().upper()
                if answer_upper not in ['A', 'B', 'C', 'D']:
                    await message.reply("⚠️ **Invalid answer.** Please provide a single letter: A, B, C, or D.")
                    return
                data['correct_answer'] = answer_upper

            # Show preview
            preview_msg = (
                f"📋 **Trivia Question Preview**\n\n"
                f"**Question:** {question_text}\n"
            )

            if is_multiple_choice:
                choices = data.get('choices', [])
                choices_text = "\n".join([f"**{chr(65+i)}.** {choice}" for i, choice in enumerate(choices)])
                preview_msg += f"\n**Choices:**\n{choices_text}\n"

            preview_msg += (
                f"\n**Answer:** {data['correct_answer']}\n\n"
                f"**Type:** {'Multiple Choice' if is_multiple_choice else 'Single Answer'}\n"
                f"**Source:** Moderator Submission\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Submit Question** - Add to trivia database with priority scheduling\n"
                f"**2.** ✏️ **Edit Question** - Revise the question text\n"
                f"**3.** 🔧 **Edit Answer** - Revise the correct answer\n"
                f"**4.** ❌ **Cancel** - Abort question submission\n\n"
                f"Please respond with **1**, **2**, **3**, or **4**.\n\n"
                f"*Review question parameters carefully before submission.*")

            await message.reply(preview_msg)

        elif step == 'preview':
            if content in ['1', 'submit', 'confirm', 'yes']:
                # Check if database is available
                if db is None:
                    await message.reply("❌ **Database systems offline.** Unable to submit trivia question.")
                    return

                # Submit the question to database
                question_text = data['question_text']
                question_type = (
                    'multiple_choice' if data.get('question_type') == 'manual_answer' and re.search(
                        r'\b[A-D]\)', question_text) else 'single_answer')

                if data.get('question_type') == 'database_calculated':
                    # Database-calculated question
                    question_id = db.add_trivia_question(  # type: ignore
                        question_text=question_text,
                        question_type=question_type,
                        correct_answer=None,  # Will be calculated dynamically
                        is_dynamic=True,
                        dynamic_query_type=data.get('dynamic_query_type'),
                        category=data.get('category'),
                        submitted_by_user_id=user_id,
                    )

                else:
                    # Manual question+answer
                    multiple_choice_options = None
                    if question_type == 'multiple_choice':
                        # Extract options from question text
                        options_match = re.findall(
                            r'[A-D]\)\s*([^A-D\n]+)', question_text)
                        if options_match:
                            multiple_choice_options = [
                                opt.strip() for opt in options_match]

                    question_id = db.add_trivia_question(  # type: ignore
                        question_text=question_text,
                        question_type=question_type,
                        correct_answer=data['correct_answer'],
                        multiple_choice_options=multiple_choice_options,
                        is_dynamic=False,
                        category=data.get('category', 'manual'),
                        submitted_by_user_id=user_id,
                    )

                if question_id:
                    await message.reply(
                        f"✅ **Trivia Question Submitted Successfully**\n\n"
                        f"Your question has been added to the trivia database with priority scheduling. "
                        f"It will be featured in an upcoming Trivia Tuesday session before AI-generated questions.\n\n"
                        f"**Question ID:** {question_id}\n"
                        f"**Status:** Pending (will be used in next available Tuesday slot)\n"
                        f"**Priority:** Moderator Submission (High Priority)\n\n"
                        f"*Efficiency maintained. Mission intelligence enhanced. Thank you for your contribution.*"
                    )

                    # ✅ FIX: Clean up conversation immediately after successful submission
                    if user_id in mod_trivia_conversations:
                        del mod_trivia_conversations[user_id]
                        print(f"✅ Cleaned up trivia conversation for user {user_id} after successful submission")
                else:
                    await message.reply(
                        f"❌ **Submission Failed**\n\n"
                        f"System malfunction detected during question database insertion. "
                        f"Please retry or contact system administrator.\n\n"
                        f"*Database error logged for technical review.*"
                    )

                    # Clean up conversation on failure too
                    if user_id in mod_trivia_conversations:
                        del mod_trivia_conversations[user_id]

            elif content in ['2', 'edit question', 'edit']:
                conversation['step'] = 'question_input'
                await message.reply(
                    f"✏️ **Question Edit Mode**\n\n"
                    f"Please provide your revised question text. The previous question will be replaced.\n\n"
                    f"*Precision and clarity are paramount for effective trivia questions.*"
                )

            elif content in ['3', 'edit answer', 'answer']:
                if data.get('question_type') == 'manual_answer':
                    conversation['step'] = 'answer_input'
                    await message.reply(
                        f"✏️ **Answer Edit Mode**\n\n"
                        f"**Now provide the correct answer.**\n\n"
                        f"**Please provide the correct answer:**"
                    )
                else:
                    # For database-calculated questions, option 3 is "Cancel" not "Edit Answer"
                    # Clean up conversation
                    if user_id in mod_trivia_conversations:
                        del mod_trivia_conversations[user_id]

                    await message.reply(
                        f"❌ **Question Submission Cancelled**\n\n"
                        f"Trivia question submission has been terminated. No data has been added to the database. "
                        f"All temporary data has been expunged from system memory.\n\n"
                        f"*Mission parameters reset. Standing by for new directives.*"
                    )
                    return

            elif content in ['4', 'cancel', 'abort']:
                await message.reply(
                    f"❌ **Question Submission Cancelled**\n\n"
                    f"Trivia question submission has been terminated. No data has been added to the database. "
                    f"All temporary data has been expunged from system memory.\n\n"
                    f"*Mission parameters reset. Standing by for new directives.*"
                )

                # Clean up conversation
                if user_id in mod_trivia_conversations:
                    del mod_trivia_conversations[user_id]
            else:
                await message.reply(
                    f"⚠️ **Invalid command.** Please respond with **1** (Submit), **2** (Edit Question), **3** (Edit Answer/Category), or **4** (Cancel).\n\n"
                    f"*Precise input required for proper protocol execution.*"
                )

        # Update conversation state
        conversation['data'] = data
        mod_trivia_conversations[user_id] = conversation

    except Exception as e:
        print(f"Error in mod trivia conversation: {e}")
        # Clean up on error
        if user_id in mod_trivia_conversations:
            del mod_trivia_conversations[user_id]

