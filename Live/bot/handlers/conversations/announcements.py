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
from bot.handlers.ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response, create_ai_announcement_content
from bot.utils.permissions import get_user_communication_tier, user_is_mod_by_id
from discord.ext import commands

from .core import (
    _get_bot_instance,
    announcement_conversations,
    db,
    game_review_conversations,
    sync_approval_conversations,
    weekly_announcement_approvals,
)
from .trivia_approval import add_to_approval_queue, get_queue_length, process_next_approval
from .utils import (
    _regenerate_weekly_announcement_content,
    amend_weekly_content_with_ai,
    check_conversation_health,
    check_escape_command,
    create_invalid_input_message,
    format_announcement_content,
    increment_invalid_input_count,
    post_announcement,
    reset_invalid_input_count,
    send_conversation_expired_message,
    track_conversation_step,
    validate_numbered_input,
)


def cleanup_announcement_conversations():
    """Remove announcement conversations inactive for more than 1 hour"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=1)
    expired_users = [
        user_id
        for user_id, data in announcement_conversations.items()
        if data.get("last_activity", uk_now) < cutoff_time
    ]
    for user_id in expired_users:
        del announcement_conversations[user_id]
        print(
            f"Cleaned up expired announcement conversation for user {user_id}")


def update_announcement_activity(user_id: int):
    """Update last activity time for announcement conversation"""
    if user_id in announcement_conversations:
        announcement_conversations[user_id]["last_activity"] = datetime.now(
            ZoneInfo("Europe/London"))


def cleanup_weekly_announcement_approvals():
    """Remove weekly announcement approval sessions inactive for more than 24 hours"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=24)
    expired_users = []

    for user_id, data in weekly_announcement_approvals.items():
        last_activity = data.get("last_activity", uk_now)
        if last_activity < cutoff_time:
            expired_users.append(user_id)

            # Mark as cancelled in database
            announcement_id = data.get('announcement_id')
            if announcement_id and db:
                try:
                    db.update_announcement_status(announcement_id, 'cancelled')
                    print(f"Auto-cancelled stale weekly announcement {announcement_id} after 24 hours")
                except Exception as e:
                    print(f"Error auto-cancelling announcement {announcement_id}: {e}")

    # Remove from memory
    for user_id in expired_users:
        conversation_age_hours = (
            uk_now - weekly_announcement_approvals[user_id].get("last_activity", uk_now)).total_seconds() / 3600
        print(
            f"Cleaned up weekly announcement approval for user {user_id} after {conversation_age_hours:.1f} hours of inactivity")
        del weekly_announcement_approvals[user_id]

    return len(expired_users)


async def notify_jam_weekly_message_failure(day: str, error_type: str, details: str):
    """Send DM notification to JAM when weekly message generation fails"""
    try:
        bot = _get_bot_instance()
        if not bot:
            print("❌ Cannot notify JAM of weekly message failure - bot instance not available")
            return False

        jam_user = await bot.fetch_user(JAM_USER_ID)
        if not jam_user:
            print(f"❌ Cannot notify JAM of weekly message failure - user {JAM_USER_ID} not found")
            return False

        uk_now = datetime.now(ZoneInfo("Europe/London"))
        timestamp = uk_now.strftime("%Y-%m-%d %H:%M:%S UK")

        # Create consistent error message format
        error_msg = (
            f"❌ **{day.title()} Message Creation Failure**\n\n"
            f"**Reason:** {error_type}\n"
            f"**Details:** {details}\n"
            f"**Time:** {timestamp}\n\n"
            f"*No {day.title()} greeting will be sent automatically. Manual intervention may be required.*"
        )

        await jam_user.send(error_msg)
        print(f"✅ Sent {day.title()} failure notification to JAM: {error_type}")
        return True

    except Exception as e:
        print(f"❌ Error sending failure notification to JAM: {e}")
        return False


async def start_weekly_announcement_approval(announcement_id: int, content: str, day: str):
    """Starts the approval workflow for a weekly announcement (via queue system)."""
    try:
        # ✅ FIX #4: Use queue system to prevent conversation overlaps
        print(f"📋 Queueing {day.title()} announcement approval (ID: {announcement_id})")

        # Determine priority based on day
        priority = 5  # Default priority for weekly announcements
        source = f"{day}_announcement"

        # Add to queue with announcement data
        add_to_approval_queue(
            item_type='weekly_announcement',
            data={
                'announcement_id': announcement_id,
                'content': content,
                'day': day
            },
            priority=priority,
            source=source
        )

        # Process the queue (will send if JAM is free)
        await process_next_approval()

    except Exception as e:
        print(f"❌ Error queueing weekly announcement approval: {e}")


async def handle_weekly_announcement_approval(message: discord.Message):
    """Handles the state machine for the weekly announcement approval conversation."""
    user_id = message.author.id
    convo = weekly_announcement_approvals.get(user_id)
    if not convo:
        return

    content = message.content.strip()

    # ✅ FIX #1: Check for escape command
    if check_escape_command(content):
        announcement_id = convo.get('announcement_id')
        if announcement_id and db:
            db.update_announcement_status(announcement_id, 'cancelled')

        await message.reply(
            f"❌ **Approval Cancelled**\n\n"
            f"The weekly announcement approval has been cancelled at your request. "
            f"No message will be sent today.\n\n"
            f"*You can generate a new announcement tomorrow.*"
        )
        if user_id in weekly_announcement_approvals:
            del weekly_announcement_approvals[user_id]
        return

    # ✅ FIX #1: Check conversation health
    is_healthy, error_message = check_conversation_health(convo, max_age_minutes=120)
    if not is_healthy:
        await send_conversation_expired_message(message, "weekly announcement approval", error_message or "Conversation health check failed")
        announcement_id = convo.get('announcement_id')
        if announcement_id and db:
            db.update_announcement_status(announcement_id, 'cancelled')
        if user_id in weekly_announcement_approvals:
            del weekly_announcement_approvals[user_id]
        return

    announcement_id = convo['announcement_id']

    if convo['step'] == 'approval':
        # Validate input first (options 1-5)
        valid_options = ['1', '2', '3', '4', '5']
        if not validate_numbered_input(content, valid_options):
            await message.reply(create_invalid_input_message(content, valid_options))
            return

        if content == '1':
            db.update_announcement_status(announcement_id, 'approved')

            uk_now = datetime.now(ZoneInfo("Europe/London"))
            day_map = {
                'monday': 0,
                'tuesday': 1,
                'wednesday': 2,
                'thursday': 3,
                'friday': 4,
                'saturday': 5,
                'sunday': 6}
            target_day_int = day_map.get(convo['day'].lower())

            # Determine if we should post immediately (past 9 AM on target day, or an entirely different day)
            post_immediately = False
            if target_day_int is not None:
                if uk_now.weekday() != target_day_int or uk_now.hour >= 9:
                    post_immediately = True

            if post_immediately:
                # Post the message immediately
                bot = _get_bot_instance()
                from bot.config import CHIT_CHAT_CHANNEL_ID
                channel = bot.get_channel(CHIT_CHAT_CHANNEL_ID) if bot else None

                if channel and isinstance(channel, discord.TextChannel):
                    post_content = convo['original_content'].replace('\\n', '\n')
                    if '\n\n' not in post_content and '\n' in post_content:
                        post_content = post_content.replace('\n', '\n\n')

                    await channel.send(post_content)
                    db.update_announcement_status(announcement_id, 'posted')
                    reply_text = "✅ **Approved and posted immediately.** (It is past the 9:00 AM scheduled time)."
                else:
                    reply_text = "✅ **Approved.** (Failed to post immediately: could not find Chit-Chat channel)."
            else:
                reply_text = "✅ **Approved.** The message will be posted at 9:00 AM."

            # ✅ FIX #4: Process next approval from queue
            queue_length = get_queue_length()
            if queue_length > 0:
                await message.reply(f"{reply_text}\n\n📬 Processing next approval ({queue_length} remaining)...")
            else:
                await message.reply(reply_text)

            del weekly_announcement_approvals[user_id]

            # Process next item in queue
            await process_next_approval()
        elif content == '2':
            convo['step'] = 'ai_amending'
            await message.reply("🤖 **AI Amendment:** Please provide your instructions for how the AI should modify the message (e.g., 'make it clear the transmission was said by Jonesy', 'add more emphasis on viewer engagement').")
        elif content == '3':
            convo['step'] = 'manual_editing'
            current_content = convo['original_content']
            await message.reply(
                f"✏️ **Manual Edit Mode**\n\n"
                f"**Current message:**\n```\n{current_content}\n```\n\n"
                f"Please provide your complete replacement text. This will replace the entire message."
            )
        elif content == '4':  # Regenerate
            await message.reply("🔄 **Regenerating...** Analyzing data from a different perspective. Please wait.")

            # Fetch the latest announcement record from the DB to get the analysis_cache
            announcement_data = db.get_announcement_by_day(convo['day'], 'pending_approval')
            if not announcement_data or not announcement_data.get('analysis_cache'):
                await message.reply("❌ **Regeneration Failed:** Could not retrieve analysis data. Please amend manually or cancel.")
                return

            analysis_cache = announcement_data['analysis_cache']
            original_content = convo['original_content']

            # Call the regeneration helper function
            new_content = await _regenerate_weekly_announcement_content(analysis_cache, convo['day'], original_content)

            if new_content:
                # Update the conversation state with the new content
                convo['original_content'] = new_content

                # Update the database record with the new content so it persists
                db.update_announcement_status(announcement_id, 'pending_approval', new_content=new_content)

                # Present the new version for approval (return to approval step for validation)
                convo['step'] = 'approval'
                approval_msg = (
                    f"🔄 **Regeneration Complete**\n\n"
                    f"Here is an alternative version of the {convo['day'].title()} greeting:\n\n"
                    f"```\n{new_content}\n```\n"
                    f"**Available Actions:**\n"
                    f"**1.** ✅ **Approve**\n"
                    f"**2.** ✏️ **Amend**\n"
                    f"**3.** 🔄 **Regenerate Again**\n"
                    f"**4.** ❌ **Cancel**\n\n"
                    f"Please respond with **1, 2, 3, or 4**."
                )
                await message.reply(approval_msg)
            else:
                await message.reply("❌ **Regeneration Failed:** The AI was unable to generate an alternative. Please try amending the message or cancel.")
        elif content == '5':
            db.update_announcement_status(announcement_id, 'cancelled')
            await message.reply("❌ **Cancelled.** No message will be sent today.")
            del weekly_announcement_approvals[user_id]
        else:
            await message.reply("⚠️ Invalid input. Please respond with 1, 2, 3, 4, or 5.")

    elif convo['step'] == 'ai_amending':
        # Use AI to amend the content based on user instructions
        await message.reply("🔄 **Processing Amendment...** Using AI to apply your requested changes. Please wait.")

        amended_content = await amend_weekly_content_with_ai(
            original_content=convo['original_content'],
            amendment_instruction=content,
            day=convo['day']
        )

        if amended_content:
            # Update the conversation state with the amended content
            convo['original_content'] = amended_content
            convo['step'] = 'approval'  # Return to approval step for preview

            # Update the database with pending status (not auto-approved)
            db.update_announcement_status(announcement_id, 'pending_approval', new_content=amended_content)

            # Present the amended version for approval
            approval_msg = (
                f"✏️ **Amendment Complete**\n\n"
                f"Here is the revised {convo['day'].title()} greeting based on your instructions:\n\n"
                f"```\n{amended_content}\n```\n"
                f"**Available Actions:**\n"
                f"**1.** ✅ **Approve** - Post this amended message\n"
                f"**2.** ✏️ **Amend Again** - Provide additional modification instructions\n"
                f"**3.** 🔄 **Regenerate** - Discard changes and generate a new version\n"
                f"**4.** ❌ **Cancel** - Do not send a greeting today\n\n"
                f"Please respond with **1, 2, 3, or 4**."
            )
            await message.reply(approval_msg)
            # Update step to approval so next input is validated
            convo['step'] = 'approval'
        else:
            # AI amendment failed - ask what to do next
            valid_options = ['1', '2', '3']
            convo['step'] = 'ai_amendment_failed'
            await message.reply(
                "⚠️ **AI Amendment Failed.** The AI was unable to process your instruction. "
                "Would you like to:\n\n"
                "**1.** Try a different instruction\n"
                "**2.** Proceed with the original message\n"
                "**3.** Cancel\n\n"
                "Please respond with **1**, **2**, or **3**."
            )

    elif convo['step'] == 'ai_amendment_failed':
        # Handle AI amendment failure recovery
        valid_options = ['1', '2', '3']
        if not validate_numbered_input(content, valid_options):
            await message.reply(create_invalid_input_message(content, valid_options))
            return

        if content == '1':
            convo['step'] = 'ai_amending'
            await message.reply("🤖 **Try Again:** Please provide new amendment instructions.")
        elif content == '2':
            # Approve original and post
            db.update_announcement_status(announcement_id, 'approved')
            await message.reply("✅ **Original Approved.** The message will be posted at 9:00 AM.")
            del weekly_announcement_approvals[user_id]
        elif content == '3':
            db.update_announcement_status(announcement_id, 'cancelled')
            await message.reply("❌ **Cancelled.** No message will be sent today.")
            del weekly_announcement_approvals[user_id]

    elif convo['step'] == 'manual_editing':
        # User has provided their complete replacement text
        manually_edited_content = content

        # Update the conversation state with the manually edited content
        convo['original_content'] = manually_edited_content
        convo['step'] = 'approval'  # Return to approval step for preview

        # Update the database with pending status (not auto-approved)
        db.update_announcement_status(announcement_id, 'pending_approval', new_content=manually_edited_content)

        # Present the manually edited version for approval
        approval_msg = (
            f"✏️ **Manual Edit Complete**\n\n"
            f"Here is your manually edited {convo['day'].title()} greeting:\n\n"
            f"```\n{manually_edited_content}\n```\n"
            f"**Available Actions:**\n"
            f"**1.** ✅ **Approve** - Post this edited message\n"
            f"**2.** 🤖 **AI Amend** - Use AI to further modify this version\n"
            f"**3.** ✏️ **Manual Edit Again** - Provide a new replacement text\n"
            f"**4.** 🔄 **Regenerate** - Discard changes and generate new version\n"
            f"**5.** ❌ **Cancel** - Do not send a greeting today\n\n"
            f"Please respond with **1, 2, 3, 4, or 5**."
        )
        await message.reply(approval_msg)


async def handle_announcement_conversation(message: discord.Message) -> None:
    """Handle the interactive DM conversation for announcement creation"""
    user_id = message.author.id
    conversation = announcement_conversations.get(user_id)

    if not conversation:
        return

    content = message.content.strip()

    # ✅ FIX #1: Check for escape command
    if check_escape_command(content):
        await message.reply(
            f"❌ **Announcement Cancelled**\n\n"
            f"The announcement creation has been cancelled at your request. "
            f"All progress has been discarded.\n\n"
            f"*You can start a new announcement with `!announceupdate`*"
        )
        if user_id in announcement_conversations:
            del announcement_conversations[user_id]
        return

    # ✅ FIX #1: Check conversation health
    is_healthy, error_message = check_conversation_health(conversation, max_age_minutes=60)
    if not is_healthy:
        await send_conversation_expired_message(message, "announcement creation", error_message or "Conversation health check failed")
        if user_id in announcement_conversations:
            del announcement_conversations[user_id]
        return

    # Update activity
    update_announcement_activity(user_id)

    step = conversation.get('step', 'channel_selection')
    data = conversation.get('data', {})

    try:
        if step == 'channel_selection':
            # Validate input first
            valid_options = ['1', '2']
            if not validate_numbered_input(
                    content,
                    valid_options) and content not in [
                    'mod',
                    'moderator',
                    'mod channel',
                    'user',
                    'announcements',
                    'public',
                    'community']:
                await message.reply(create_invalid_input_message(content, valid_options, "mod, moderator, user, announcements"))
                return

            # Handle channel selection (1 for mod, 2 for user announcements)
            if content in ['1', 'mod', 'moderator', 'mod channel']:
                data['target_channel'] = 'mod'
                conversation['step'] = 'content_input'

                greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

                await message.reply(
                    f"🔒 **Moderator Channel Selected**\n\n"
                    f"Target: <#{MOD_ALERT_CHANNEL_ID}> (Internal team briefing)\n\n"
                    f"📝 **Content Creation Protocol:**\n"
                    f"Please provide your update content, {greeting}. This will be formatted as a detailed "
                    f"technical briefing for the moderation team with full functionality breakdown and implementation details.\n\n"
                    f"*Include all relevant technical specifications and operational parameters.*"
                )

            elif content in ['2', 'user', 'announcements', 'public', 'community']:
                data['target_channel'] = 'user'
                conversation['step'] = 'content_input'

                greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

                await message.reply(
                    f"📢 **User Announcements Channel Selected**\n\n"
                    f"Target: <#{ANNOUNCEMENTS_CHANNEL_ID}> (Public community notification)\n\n"
                    f"📝 **Content Creation Protocol:**\n"
                    f"Please provide your update content, {greeting}. This will be formatted as a "
                    f"user-friendly community announcement focusing on new features and improvements that "
                    f"enhance the user experience.\n\n"
                    f"*Focus on benefits and user-facing functionality rather than technical implementation.*"
                )
            else:
                await message.reply(
                    f"⚠️ **Invalid selection.** Please respond with **1** for moderator updates or **2** for community announcements.\n\n"
                    f"*Precision is essential for proper mission briefing protocols.*"
                )

        elif step == 'content_input':
            # Store the raw content for later reference
            data['raw_content'] = content
            target_channel = data.get('target_channel', 'mod')

            # Check if we're in edit mode (skip AI enhancement)
            if data.get('edit_mode', False):
                # Use exact text as provided - no AI enhancement
                data['content'] = content
                data['edit_mode'] = False  # Clear the flag
                conversation['step'] = 'preview'

                # Create formatted preview using exact content
                preview_content = await format_announcement_content(content, target_channel, user_id, creator_notes=data.get('creator_notes'))
                data['formatted_content'] = preview_content

                greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

                await message.reply(
                    f"📋 **Updated Announcement Preview** ({'Moderator' if target_channel == 'mod' else 'Community'} Channel):\n\n"
                    f"```\n{preview_content}\n```\n\n"
                    f"✏️ **Your exact text has been used, {greeting}.**\n\n"
                    f"📚 **Available Actions:**\n"
                    f"**1.** ✅ **Post Announcement** - Deploy this update immediately\n"
                    f"**2.** ✏️ **Edit Content** - Revise the announcement text again\n"
                    f"**3.** 📝 **Add/Edit Creator Notes** - Include or modify personal notes\n"
                    f"**4.** ❌ **Cancel** - Abort announcement creation\n\n"
                    f"*Review mission parameters carefully before deployment.*"
                )
            else:
                # Initial content - use AI enhancement
                greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

                await message.reply(
                    f"🧠 **AI Content Creation Protocol Initiated**\n\n"
                    f"Processing your input through my cognitive matrix, {greeting}. I will craft this update "
                    f"in my own words and style while preserving your intended meaning and technical accuracy.\n\n"
                    f"**Your Input:** {content[:200]}{'...' if len(content) > 200 else ''}\n\n"
                    f"*Analyzing content parameters and generating Ash-appropriate prose...*"
                )

                # Use AI to create content in Ash's style
                enhanced_content = await create_ai_announcement_content(content, target_channel, user_id)

                if enhanced_content and enhanced_content.strip():
                    # Store both AI and raw content
                    data['ai_content'] = enhanced_content
                    # Use AI content as primary content
                    data['content'] = enhanced_content
                    conversation['step'] = 'preview'

                    # Create formatted preview using AI content
                    preview_content = await format_announcement_content(enhanced_content, target_channel, user_id)
                    data['formatted_content'] = preview_content

                    # Show AI-enhanced preview
                    preview_msg = (
                        f"📋 **AI-Enhanced Announcement Preview** ({'Moderator' if target_channel == 'mod' else 'Community'} Channel):\n\n"
                        f"```\n{preview_content}\n```\n\n"
                        f"✨ **Content created in Ash's analytical style based on your specifications**\n\n"
                        f"📚 **Available Actions:**\n"
                        f"**1.** ✅ **Post Announcement** - Deploy this update immediately\n"
                        f"**2.** 🤖 **AI Amend** - Provide instructions for AI to modify\n"
                        f"**3.** ✏️ **Manual Edit** - Directly edit the text yourself\n"
                        f"**4.** 📝 **Add Creator Notes** - Include personal notes\n"
                        f"**5.** ❌ **Cancel** - Abort announcement creation\n\n"
                        f"Please respond with **1, 2, 3, 4, or 5**.\n\n"
                        f"*Review mission parameters carefully before deployment.*")

                    await message.reply(preview_msg)
                else:
                    # AI failed, fall back to original content
                    data['content'] = content  # Store original content as primary
                    conversation['step'] = 'preview'
                    preview_content = await format_announcement_content(content, target_channel, user_id)
                    data['formatted_content'] = preview_content

                    await message.reply(
                        f"⚠️ **AI content creation failed.** Proceeding with your original content.\n\n"
                        f"📋 **Announcement Preview** ({'Moderator' if target_channel == 'mod' else 'Community'} Channel):\n\n"
                        f"```\n{preview_content}\n```\n\n"
                        f"📚 **Available Actions:**\n"
                        f"**1.** ✅ **Post Announcement** - Deploy this update immediately\n"
                        f"**2.** ✏️ **Edit Content** - Revise the announcement text\n"
                        f"**3.** 📝 **Add Creator Notes** - Include personal notes from the creator\n"
                        f"**4.** ❌ **Cancel** - Abort announcement creation\n\n"
                        f"*Review mission parameters carefully before deployment.*")

        elif step == 'preview':
            # Validate input first - determine valid options based on AI availability
            if data.get('ai_content'):
                # AI-enhanced content: 5 options available
                valid_options = ['1', '2', '3', '4', '5']
            else:
                # AI failed: 4 options available (no AI amend)
                valid_options = ['1', '2', '3', '4']

            if not validate_numbered_input(content, valid_options):
                await message.reply(create_invalid_input_message(content, valid_options))
                return

            # Handle preview actions
            if content in ['1', 'post', 'deploy', 'send']:
                # Clean up conversation BEFORE posting to ensure it ends properly
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]

                # Post regular announcement
                success = await post_announcement(data, user_id)

                if success:
                    target_channel = data.get('target_channel', 'mod')
                    channel_name = "moderator" if target_channel == 'mod' else "community announcements"

                    await message.reply(
                        f"✅ **Announcement Deployed Successfully**\n\n"
                        f"Your update has been transmitted to the {channel_name} channel with proper formatting "
                        f"and presentation protocols. Mission briefing complete.\n\n"
                        f"**This conversation has ended.** Use `!announceupdate` to create a new announcement.\n\n"
                        f"*Efficient communication maintained. All personnel notified.*"
                    )
                else:
                    await message.reply(
                        f"❌ **Deployment Failed**\n\n"
                        f"System malfunction detected during announcement transmission. Unable to complete "
                        f"briefing protocol.\n\n"
                        f"**This conversation has ended.** Use `!announceupdate` to try again.\n\n"
                        f"*Please retry or contact system administrator for technical support.*"
                    )
                return  # Exit immediately after cleanup

            elif content in ['2', 'ai amend', 'ai', 'amend']:
                # AI amendment mode
                conversation['step'] = 'ai_amending'
                await message.reply(
                    f"🤖 **AI Amendment Mode**\n\n"
                    f"Please provide instructions for how the AI should modify the announcement "
                    f"(e.g., 'make it more technical', 'add emphasis on user benefits', 'make it shorter').\n\n"
                    f"*The AI will revise the content based on your guidance.*"
                )

            elif content in ['3', 'manual edit', 'edit', 'revise']:
                # Manual edit mode
                conversation['step'] = 'manual_editing'
                current_content = data.get('content', data.get('raw_content', ''))
                await message.reply(
                    f"✏️ **Manual Edit Mode**\n\n"
                    f"**Current content:**\n```\n{current_content}\n```\n\n"
                    f"Please provide your complete replacement text. This will replace the entire announcement content."
                )

            elif content in ['4', 'notes', 'creator notes']:
                # Add creator notes step
                conversation['step'] = 'creator_notes_input'

                greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

                await message.reply(
                    f"📝 **Creator Notes Protocol Activated**\n\n"
                    f"Please provide your personal notes, {greeting}. These will be included in the announcement "
                    f"with proper attribution and presented in an Ash-appropriate format.\n\n"
                    f"**What to include:**\n"
                    f"• Personal thoughts about the update\n"
                    f"• Behind-the-scenes insights\n"
                    f"• Future plans or considerations\n"
                    f"• Any additional context you'd like to share\n\n"
                    f"*Your notes will be clearly attributed and formatted appropriately for the target audience.*"
                )

            elif content in ['5', 'cancel', 'abort']:
                # Clean up conversation BEFORE cancelling to ensure it ends properly
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]

                # Cancel the announcement
                await message.reply(
                    f"❌ **Announcement Protocol Cancelled**\n\n"
                    f"Mission briefing sequence has been terminated. No content has been deployed. "
                    f"All temporary data has been expunged from system memory.\n\n"
                    f"**This conversation has ended.** Use `!announceupdate` to create a new announcement.\n\n"
                    f"*Mission parameters reset. Standing by for new directives.*"
                )
                return  # Exit immediately after cleanup
            else:
                await message.reply(
                    f"⚠️ **Invalid command.** Please respond with **1** (Post), **2** (Edit), **3** (Creator Notes), or **4** (Cancel).\n\n"
                    f"*Precise input required for proper protocol execution.*"
                )

        elif step == 'ai_amending':
            # Use AI to amend the announcement based on user instructions
            await message.reply("🔄 **Processing Amendment...** Using AI to apply your requested changes. Please wait.")

            current_content = data.get('content', data.get('raw_content', ''))
            amended_content = await amend_weekly_content_with_ai(
                original_content=current_content,
                amendment_instruction=content,
                day='announcement'  # Generic day for regular announcements
            )

            if amended_content:
                # Update with amended content
                data['content'] = amended_content
                conversation['step'] = 'preview'

                # Regenerate formatted preview
                target_channel = data.get('target_channel', 'mod')
                preview_content = await format_announcement_content(
                    amended_content, target_channel, user_id, creator_notes=data.get('creator_notes')
                )
                data['formatted_content'] = preview_content
                data['ai_content'] = amended_content  # Mark as having AI content for validation

                await message.reply(
                    f"✏️ **Amendment Complete**\n\n"
                    f"Here is the revised announcement:\n\n"
                    f"```\n{preview_content}\n```\n\n"
                    f"📚 **Available Actions:**\n"
                    f"**1.** ✅ **Post** - Deploy this amended version\n"
                    f"**2.** 🤖 **AI Amend Again** - Further modifications\n"
                    f"**3.** ✏️ **Manual Edit** - Direct text replacement\n"
                    f"**4.** 📝 **Add/Edit Notes** - Creator notes\n"
                    f"**5.** ❌ **Cancel**\n\n"
                    f"Please respond with **1, 2, 3, 4, or 5**."
                )
            else:
                # AI failed - transition to failure recovery step
                conversation['step'] = 'ai_amend_failed'
                await message.reply(
                    "⚠️ **AI Amendment Failed.** Would you like to:\n\n"
                    "**1.** Try a different instruction\n"
                    "**2.** Manual edit instead\n"
                    "**3.** Cancel\n\n"
                    "Please respond with **1**, **2**, or **3**."
                )

        elif step == 'ai_amend_failed':
            # Handle AI amendment failure recovery for regular announcements
            valid_options = ['1', '2', '3']
            if not validate_numbered_input(content, valid_options):
                await message.reply(create_invalid_input_message(content, valid_options))
                return

            if content == '1':
                conversation['step'] = 'ai_amending'
                await message.reply("🤖 **Try Again:** Please provide new AI amendment instructions.")
            elif content == '2':
                conversation['step'] = 'manual_editing'
                current_content = data.get('content', data.get('raw_content', ''))
                await message.reply(
                    f"✏️ **Manual Edit Mode**\n\n"
                    f"**Current content:**\n```\n{current_content}\n```\n\n"
                    f"Please provide your complete replacement text."
                )
            elif content == '3':
                # Cancel announcement
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]
                await message.reply("❌ **Cancelled.** Announcement creation aborted.")
                return

        elif step == 'manual_editing':
            # User provided complete replacement text
            data['content'] = content
            conversation['step'] = 'preview'

            # Regenerate formatted preview with manual edit
            target_channel = data.get('target_channel', 'mod')
            preview_content = await format_announcement_content(
                content, target_channel, user_id, creator_notes=data.get('creator_notes')
            )
            data['formatted_content'] = preview_content

            await message.reply(
                f"✏️ **Manual Edit Complete**\n\n"
                f"Here is your manually edited announcement:\n\n"
                f"```\n{preview_content}\n```\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Post** - Deploy this version\n"
                f"**2.** 🤖 **AI Amend** - Use AI to modify further\n"
                f"**3.** ✏️ **Edit Again** - Provide new replacement text\n"
                f"**4.** 📝 **Add/Edit Notes** - Creator notes\n"
                f"**5.** ❌ **Cancel**\n\n"
                f"Please respond with **1, 2, 3, 4, or 5**."
            )

        elif step == 'creator_notes_input':
            # Handle creator notes input
            data['creator_notes'] = content
            conversation['step'] = 'preview'

            # Regenerate formatted content with creator notes included
            target_channel = data.get('target_channel', 'mod')
            # Use primary content (AI-enhanced or original)
            main_content = data.get('content', data.get('raw_content', ''))

            # Regenerate formatted content with creator notes
            preview_content = await format_announcement_content(
                main_content, target_channel, user_id, creator_notes=content
            )
            data['formatted_content'] = preview_content

            greeting = "Captain Jonesy" if user_id == JONESY_USER_ID else "Sir Decent Jam"

            # Show updated preview with creator notes
            preview_msg = (
                f"📋 **Updated Announcement Preview** ({'Moderator' if target_channel == 'mod' else 'Community'} Channel):\n\n"
                f"```\n{preview_content}\n```\n\n"
                f"✅ **Creator notes successfully integrated, {greeting}.**\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Post Announcement** - Deploy this update immediately\n"
                f"**2.** 🤖 **AI Amend** - Provide instructions for AI to modify\n"
                f"**3.** ✏️ **Manual Edit** - Directly edit the text yourself\n"
                f"**4.** 📝 **Edit Creator Notes** - Modify your personal notes\n"
                f"**5.** ❌ **Cancel** - Abort announcement creation\n\n"
                f"*Review mission parameters carefully before deployment.*")

            await message.reply(preview_msg)

        # Update conversation state
        conversation['data'] = data
        announcement_conversations[user_id] = conversation

    except Exception as e:
        print(f"Error in announcement conversation: {e}")
        # Clean up on error
        if user_id in announcement_conversations:
            del announcement_conversations[user_id]


async def start_announcement_conversation(message):
    """Start interactive DM conversation for announcement creation"""
    # Check if command is used in DM
    if message.guild is not None:
        await message.reply(
            f"⚠️ **Security protocol engaged.** Announcement creation must be initiated via direct message. "
            f"Please DM me with `!announceupdate` to begin the secure briefing process.\n\n"
            f"*Confidential mission parameters require private channel authorization.*"
        )
        return

    # Check user permissions - only James and Captain Jonesy
    if message.author.id not in [JAM_USER_ID, JONESY_USER_ID]:
        await message.reply(
            f"❌ **Access denied.** Announcement protocols are restricted to authorized command personnel only. "
            f"Your clearance level is insufficient for update broadcast capabilities.\n\n"
            f"*Security protocols maintained. Unauthorized access logged.*"
        )
        return

    # Clean up any existing conversation state for this user
    cleanup_announcement_conversations()

    # Initialize conversation state
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    announcement_conversations[message.author.id] = {
        'step': 'channel_selection',
        'data': {},
        'last_activity': uk_now,
        'initiated_at': uk_now,
    }

    # Start the interactive process
    if message.author.id == JONESY_USER_ID:
        greeting = "Captain Jonesy. Authorization confirmed."
    else:
        greeting = "Sir Decent Jam. Creator protocols activated."

    channel_msg = (
        f"🎯 **Update Announcement System Activated**\n\n"
        f"{greeting} Initiating secure briefing sequence for mission update dissemination.\n\n"
        f"📡 **Target Channel Selection:**\n"
        f"**1.** 🔒 **Moderator Channel** - Internal team briefing (detailed technical update)\n"
        f"**2.** 📢 **User Announcements** - Public community notification (user-focused content)\n\n"
        f"Please respond with **1** for mod team updates or **2** for community announcements.\n\n"
        f"*Mission parameters await your tactical decision.*")

    await message.reply(channel_msg)


async def handle_game_review_conversation(message: discord.Message) -> None:
    """Handle game review approval conversation"""
    user_id = message.author.id
    conversation = game_review_conversations.get(user_id)

    if not conversation or user_id != JAM_USER_ID:
        return

    content = message.content.strip()

    # ✅ FIX #1: Check for escape command
    if check_escape_command(content):
        session_id = conversation.get('session_id')
        if session_id and db:
            db.complete_game_review_session(session_id, 'cancelled')

        await message.reply(
            f"❌ **Review Cancelled**\n\n"
            f"The game review has been cancelled at your request. "
            f"This entry will not be imported.\n\n"
            f"*You can start a new review if needed.*"
        )
        if user_id in game_review_conversations:
            del game_review_conversations[user_id]
        return

    # Get conversation data
    step = conversation.get('step', 'review')
    data = conversation.get('data', {})
    session_id = conversation.get('session_id')

    if not session_id:
        await message.reply("❌ Error: Invalid session")
        if user_id in game_review_conversations:
            del game_review_conversations[user_id]
        return

    try:
        if step == 'review':
            # ✅ FIX #6: Validate numbered input (12/14)
            valid_options = ['1', '2', '3']
            if not validate_numbered_input(content, valid_options) and content not in [
                    'accept', 'yes', 'correct', 'fix', 'skip', 'no']:
                await message.reply(create_invalid_input_message(content, valid_options, "accept, correct, skip"))
                return

            if content in ['1', 'accept', 'yes']:
                # Accept extracted name
                db.complete_game_review_session(session_id, 'approved')
                await message.reply(
                    f"✅ **Accepted** - Game will be imported as `{data['extracted_name']}`"
                )
                del game_review_conversations[user_id]

            elif content in ['2', 'correct', 'fix']:
                # Request correct name
                conversation['step'] = 'correction'
                await message.reply(
                    f"🔧 **Provide Correct Name**\n\n"
                    f"Original title: `{data['original_title']}`\n\n"
                    f"What's the real game name? (I'll re-validate with IGDB)"
                )

            elif content in ['3', 'skip', 'no']:
                # Skip this entry
                db.complete_game_review_session(session_id, 'rejected')
                await message.reply(
                    f"❌ **Skipped** - This entry won't be imported"
                )
                del game_review_conversations[user_id]

        elif step == 'correction':
            # User provided correct name - re-validate with IGDB
            corrected_name = content.strip()

            await message.reply(f"🔍 **Re-validating** `{corrected_name}` with IGDB...")

            # Re-validate with IGDB using the correct function
            try:
                from bot.integrations.igdb import validate_and_enrich
                igdb_result = await validate_and_enrich(corrected_name)
            except Exception as e:
                print(f"⚠️ IGDB validation failed: {e}")
                igdb_result = None

            if igdb_result and igdb_result.get('confidence', 0) >= 0.7:
                # Good match found
                db.update_game_review_session(
                    session_id,
                    approved_name=corrected_name,
                    approved_data={'igdb': igdb_result}
                )
                db.complete_game_review_session(session_id, 'approved')

                await message.reply(
                    f"✅ **Correction Approved**\n\n"
                    f"**Your Input:** {corrected_name}\n"
                    f"**IGDB Match:** {igdb_result.get('name')} (confidence: {igdb_result.get('confidence', 0):.2f})\n"
                    f"**Genre:** {igdb_result.get('genre', 'Unknown')}\n\n"
                    f"Game will be imported with IGDB data."
                )
                del game_review_conversations[user_id]
            else:
                # Still low confidence - ask to try again or skip
                conversation['step'] = 'correction_failed'
                confidence_score = igdb_result.get('confidence', 0) if igdb_result else 0
                await message.reply(
                    f"⚠️ **Still Low Confidence**\n\n"
                    f"IGDB match: {confidence_score:.2f}\n\n"
                    f"**1.** Try different name\n"
                    f"**2.** Accept anyway\n"
                    f"**3.** Skip entry\n\n"
                    f"Respond with **1**, **2**, or **3**."
                )

        elif step == 'correction_failed':
            # ✅ FIX #6: Validate numbered input (13/14)
            valid_options = ['1', '2', '3']
            if not validate_numbered_input(content, valid_options):
                await message.reply(create_invalid_input_message(content, valid_options, "try again, accept, skip"))
                return

            if content == '1':
                conversation['step'] = 'correction'
                await message.reply(f"🔧 Try another name:")
            elif content == '2':
                db.complete_game_review_session(session_id, 'approved')
                await message.reply(f"✅ Accepted with low confidence")
                del game_review_conversations[user_id]
            elif content == '3':
                db.complete_game_review_session(session_id, 'rejected')
                await message.reply(f"❌ Skipped")
                del game_review_conversations[user_id]

        # Only update conversation if it's still active (not deleted)
        if user_id in game_review_conversations:
            game_review_conversations[user_id] = conversation

    except Exception as e:
        print(f"❌ Error in game review conversation: {e}")
        if user_id in game_review_conversations:
            del game_review_conversations[user_id]


async def handle_sync_approval_conversation(message: discord.Message) -> bool:
    """
    Handle JAM's responses in sync approval conversation.

    Returns:
        True if message was handled by this conversation
    """
    user_id = message.author.id

    if user_id not in sync_approval_conversations:
        return False

    conv = sync_approval_conversations[user_id]

    try:
        if conv['stage'] == 'awaiting_choice':
            choice = message.content.strip()

            if choice == "1":
                await bulk_approve_sync(message, conv)
                return True
            elif choice == "2":
                await start_individual_review(message, conv)
                return True
            elif choice == "3":
                await cancel_sync(message, conv)
                return True
            else:
                await message.channel.send(
                    "❓ Please reply with **1**, **2**, or **3**:\n"
                    "1 = Approve all\n"
                    "2 = Review individually\n"
                    "3 = Cancel sync"
                )
                return True

        elif conv['stage'] == 'awaiting_game_ids':
            await process_individual_review_ids(message, conv)
            return True

        elif conv['stage'] == 'reviewing_game':
            await process_game_review_action(message, conv)
            return True

        elif conv['stage'] == 'awaiting_game_name_edit':
            await process_game_name_edit(message, conv)
            return True

        return False

    except Exception as e:
        print(f"❌ SYNC APPROVAL: Error handling conversation: {e}")
        await message.channel.send(
            f"❌ Error processing your response: {str(e)}\n"
            f"Type **cancel** to abort this session."
        )
        return True


async def bulk_approve_sync(message: discord.Message, conv: Dict[str, Any]):
    """Approve all games and commit to database"""
    try:
        sync_session_id = conv['sync_session_id']

        await message.channel.send("⏳ Approving all games and committing to database...")

        # Mark all as approved
        staged_games = db.games.get_staged_games(sync_session_id)
        for game in staged_games:
            db.games.mark_staged_game_reviewed(game['id'], approved=True)

        # Commit to database
        counts = db.games.commit_staged_games(sync_session_id)

        # Clear staging
        db.games.clear_staging_session(sync_session_id)

        # Update last sync timestamp NOW that changes are approved and committed
        from datetime import datetime
        from zoneinfo import ZoneInfo
        current_time_uk = datetime.now(ZoneInfo('Europe/London'))
        db.config.set_config_value('last_content_sync_timestamp', current_time_uk.isoformat())
        print(f"✅ SYNC APPROVAL: Updated last_content_sync_timestamp to {current_time_uk.isoformat()}")

        # Notify JAM
        await message.channel.send(
            f"✅ **Sync Complete!**\n\n"
            f"📊 **Results:**\n"
            f"• {counts['added']} new games added\n"
            f"• {counts['updated']} games updated\n"
            f"• {counts['skipped']} skipped\n\n"
            f"All changes have been committed to the database."
        )

        print(f"✅ SYNC APPROVAL: Bulk approval complete (session {sync_session_id})")

        # Clean up conversation
        del sync_approval_conversations[message.author.id]

    except Exception as e:
        print(f"❌ SYNC APPROVAL: Error in bulk approval: {e}")
        await message.channel.send(f"❌ Error during bulk approval: {str(e)}")


async def start_individual_review(message: discord.Message, conv: Dict[str, Any]):
    """Start individual game review process"""
    try:
        await message.channel.send(
            "🔍 **Individual Review Mode**\n\n"
            "Which games need review?\n"
            "• Enter game IDs separated by commas (e.g., `97, 99, 103`)\n"
            "• Or reply **all** to review all games\n"
            "• Or reply **cancel** to go back"
        )

        conv['stage'] = 'awaiting_game_ids'

    except Exception as e:
        print(f"❌ SYNC APPROVAL: Error starting individual review: {e}")
        await message.channel.send(f"❌ Error: {str(e)}")


async def process_individual_review_ids(message: discord.Message, conv: Dict[str, Any]):
    """Process the game IDs to review"""
    try:
        content = message.content.strip().lower()

        if content == 'cancel':
            # Go back to main choice
            conv['stage'] = 'awaiting_choice'
            await message.channel.send(
                "↩️ Cancelled. Reply **1**, **2**, or **3** to choose an action."
            )
            return

        sync_session_id = conv['sync_session_id']
        staged_games = db.games.get_staged_games(sync_session_id)

        if content == 'all':
            games_to_review = staged_games
        else:
            # Parse comma-separated IDs
            try:
                ids = [int(id_str.strip()) for id_str in content.split(',')]
                games_to_review = [g for g in staged_games if g['id'] in ids]

                if not games_to_review:
                    await message.channel.send(
                        f"❌ No games found with those IDs. Please try again or reply **cancel**."
                    )
                    return
            except ValueError:
                await message.channel.send(
                    f"❌ Invalid format. Please enter game IDs separated by commas (e.g., `97, 99`) or reply **all**."
                )
                return

        # Start reviewing first game
        conv['games_to_review'] = games_to_review
        conv['review_index'] = 0
        conv['stage'] = 'reviewing_game'

        # Auto-approve high-confidence UPDATES only (not new games)
        conv['auto_approved'] = []
        for game in games_to_review:
            if game.get('confidence_score', 1.0) >= 0.9 and game.get('action_type') == 'update':
                db.games.mark_staged_game_reviewed(game['id'], approved=True)
                conv['auto_approved'].append(game)

        if conv['auto_approved']:
            names = [g['game_data']['canonical_name'] for g in conv['auto_approved']]
            await message.channel.send(
                f"✅ **Auto-approved {len(conv['auto_approved'])} high-confidence games (≥90%):**\n" +
                "\n".join(f"• {name}" for name in names)
            )

        await show_next_game_for_review(message, conv)

    except Exception as e:
        print(f"❌ SYNC APPROVAL: Error processing review IDs: {e}")
        await message.channel.send(f"❌ Error: {str(e)}")


async def process_game_review_action(message: discord.Message, conv: Dict[str, Any]):
    """Process user's choice for current game"""
    try:
        choice = message.content.strip().lower()

        if choice == 'cancel':
            await cancel_sync(message, conv)
            return

        games = conv['games_to_review']
        index = conv['review_index']
        game = games[index]

        if choice == '1':
            # Approve
            db.games.mark_staged_game_reviewed(game['id'], approved=True)
            await message.channel.send(f"✅ Approved: {game['game_data']['canonical_name']}")

            # Move to next
            conv['review_index'] += 1
            await show_next_game_for_review(message, conv)

        elif choice == '2':
            # Edit game name
            conv['stage'] = 'awaiting_game_name_edit'
            await message.channel.send(
                f"✏️ **Edit Game Name**\n\n"
                f"Current: `{game['game_data']['canonical_name']}`\n\n"
                f"Enter the corrected game name (or **cancel** to go back):"
            )

        elif choice == '3':
            # Skip - mark as not approved and add to permanent exclusions
            db.games.mark_staged_game_reviewed(game['id'], approved=False)

            # Add to permanent skip list so this URL won't appear in future syncs
            game_data = game.get('game_data', {})
            source_platform = game.get('source_platform', 'youtube')
            canonical_name = game_data.get('canonical_name', 'Unknown')

            # Get the appropriate URL for this platform
            skip_url = ''
            if source_platform == 'youtube':
                skip_url = game_data.get('youtube_playlist_url', '')
            else:
                # Twitch - use first VOD URL
                vod_urls = game_data.get('twitch_vod_urls', [])
                if isinstance(vod_urls, list) and vod_urls:
                    skip_url = vod_urls[0]
                elif isinstance(vod_urls, str) and vod_urls:
                    skip_url = vod_urls.split(',')[0].strip()

            if skip_url:
                from bot.config import JAM_USER_ID
                db.games.add_skipped_vod(skip_url, source_platform, canonical_name, JAM_USER_ID)
                print(f"⏭️ SYNC APPROVAL: Added '{canonical_name}' ({source_platform}) to permanent skip list")
                platform_label = "playlist" if source_platform == "youtube" else "VOD"
                await message.channel.send(
                    f"⏭️ Skipped: **{canonical_name}**\n"
                    f"*This {platform_label} has been permanently excluded from future syncs.*"
                )
            else:
                print(f"⏭️ SYNC APPROVAL: Skipped '{canonical_name}' (no URL available for permanent exclusion)")
                await message.channel.send(f"⏭️ Skipped: {canonical_name}")

            # Move to next
            conv['review_index'] += 1
            await show_next_game_for_review(message, conv)

        else:
            await message.channel.send(
                "❓ Please reply with **1**, **2**, **3**, or **cancel**"
            )

    except Exception as e:
        print(f"❌ SYNC APPROVAL: Error processing review action: {e}")
        await message.channel.send(f"❌ Error: {str(e)}")


async def process_game_name_edit(message: discord.Message, conv: Dict[str, Any]):
    """Process edited game name"""
    try:
        new_name = message.content.strip()

        if new_name.lower() == 'cancel':
            conv['stage'] = 'reviewing_game'
            await message.channel.send("↩️ Cancelled edit. Choose an action for this game:")
            await show_next_game_for_review(message, conv)
            return

        games = conv['games_to_review']
        index = conv['review_index']
        game = games[index]

        # Update the game data
        game_data = game['game_data'].copy()
        old_name = game_data['canonical_name']
        game_data['canonical_name'] = new_name

        db.games.update_staged_game_data(game['id'], game_data)
        db.games.mark_staged_game_reviewed(game['id'], approved=True)

        await message.channel.send(
            f"✅ **Updated and approved:**\n"
            f"Old: `{old_name}`\n"
            f"New: `{new_name}`"
        )

        # Move to next
        conv['review_index'] += 1
        conv['stage'] = 'reviewing_game'
        await show_next_game_for_review(message, conv)

    except Exception as e:
        print(f"❌ SYNC APPROVAL: Error processing name edit: {e}")
        await message.channel.send(f"❌ Error: {str(e)}")


async def cancel_sync(message: discord.Message, conv: Dict[str, Any]):
    """Cancel the entire sync"""
    try:
        sync_session_id = conv['sync_session_id']

        # Clear staging without committing
        db.games.clear_staging_session(sync_session_id)

        await message.channel.send(
            "❌ **Sync Cancelled**\n\n"
            "No changes were made to the database. All staged games have been discarded."
        )

        print(f"✅ SYNC APPROVAL: Sync cancelled (session {sync_session_id})")

        # Clean up conversation
        del sync_approval_conversations[message.author.id]

    except Exception as e:
        print(f"❌ SYNC APPROVAL: Error cancelling sync: {e}")
        await message.channel.send(f"❌ Error: {str(e)}")


async def show_next_game_for_review(message: discord.Message, conv: Dict[str, Any]):
    """Show the next game in the review queue"""
    try:
        games = conv['games_to_review']
        index = conv['review_index']

        # Skip auto-approved games
        while index < len(games) and games[index] in conv.get('auto_approved', []):
            index += 1
            conv['review_index'] = index

        if index >= len(games):
            # All games reviewed - commit
            await finalize_individual_review(message, conv)
            return

        game = games[index]
        game_data = game['game_data']

        review_msg = f"­ƒöì **Game {index + 1}/{len(games)}**\n\n"
        review_msg += f"**ID:** {game['id']}\n"
        review_msg += f"**Name:** {game_data['canonical_name']}\n"
        review_msg += f"**Action:** {game['action_type']}\n"
        review_msg += f"**Platform:** {game.get('source_platform', 'unknown').title()}\n"
        review_msg += f"**Episodes:** {game_data.get('total_episodes', 0)}\n"
        review_msg += f"**Playtime:** {game_data.get('total_playtime_minutes', 0)//60}h {game_data.get('total_playtime_minutes', 0)%60}m\n"
        review_msg += f"**Confidence:** {int(game.get('confidence_score', 1.0)*100)}%\n\n"

        review_msg += "**Choose an action:**\n"
        review_msg += "Ô£à **1** - Approve as-is\n"
        review_msg += "Ô£Å´©Å **2** - Edit game name\n"
        review_msg += "ÔÅ¡´©Å **3** - Skip this game\n"
        review_msg += "ÔØî **cancel** - Cancel review\n"

        await message.channel.send(review_msg)

    except Exception as e:
        print(f"ÔØî SYNC APPROVAL: Error showing game for review: {e}")
        await message.channel.send(f"ÔØî Error: {str(e)}")


async def finalize_individual_review(message: discord.Message, conv: Dict[str, Any]):
    """Finalize review and commit approved games"""
    try:
        sync_session_id = conv['sync_session_id']

        await message.channel.send("ÔÅ│ Committing approved games to database...")

        # Commit approved games
        counts = db.games.commit_staged_games(sync_session_id)

        # Clear staging
        db.games.clear_staging_session(sync_session_id)

        # Build summary
        summary_msg = f"Ô£à **Individual Review Complete!**\n\n"
        summary_msg += f"­ƒôè **Results:**\n"
        summary_msg += f"ÔÇó {counts['added']} new games added\n"
        summary_msg += f"ÔÇó {counts['updated']} games updated\n"
        summary_msg += f"ÔÇó {counts['skipped']} skipped\n"

        if conv.get('auto_approved'):
            summary_msg += f"ÔÇó {len(conv['auto_approved'])} auto-approved (high confidence)\n"

        summary_msg += f"\nAll approved changes have been committed to the database."

        await message.channel.send(summary_msg)

        print(f"Ô£à SYNC APPROVAL: Individual review complete (session {sync_session_id})")

        # Clean up conversation
        del sync_approval_conversations[message.author.id]

    except Exception as e:
        print(f"ÔØî SYNC APPROVAL: Error finalizing review: {e}")
        await message.channel.send(f"ÔØî Error during finalization: {str(e)}")
