"""
Conversation Handler Module

Handles interactive DM conversations for announcements and trivia submissions.
Manages conversation state and user flows for complex multi-step interactions.
"""

import asyncio
import re
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
from ..database_module import get_database
from ..utils.permissions import get_user_communication_tier, user_is_mod_by_id
from .ai_handler import ai_enabled, apply_ash_persona_to_ai_prompt, call_ai_with_rate_limiting, filter_ai_response

# Get database instance
db = get_database()  # type: ignore


_bot_instance = None  # This will hold our stable bot reference


def initialize_conversation_handler(bot):
    """Initializes the conversation handler with a stable bot instance."""
    global _bot_instance
    _bot_instance = bot
    print("✅ Conversation handler initialized with bot instance.")


def _get_bot_instance():
    """Gets the globally stored bot instance for conversation handlers."""
    global _bot_instance
    if _bot_instance and _bot_instance.user:
        return _bot_instance
    print("❌ Bot instance not available for conversation handler.")
    return None


# Global conversation state management
# user_id: {'step': str, 'data': dict, 'last_activity': datetime}
announcement_conversations: Dict[int, Dict[str, Any]] = {}
mod_trivia_conversations: Dict[int, Dict[str, Any]] = {}
jam_approval_conversations: Dict[int, Dict[str, Any]] = {}
weekly_announcement_approvals: Dict[int, Dict[str, Any]] = {}
game_review_conversations: Dict[int, Dict[str, Any]] = {}


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

# Weekly Announcement Approval Amendment and Regeneration Logic


async def amend_weekly_content_with_ai(
        original_content: str, amendment_instruction: str, day: str) -> Optional[str]:
    """Uses AI to amend weekly announcement content based on user instructions."""
    if not ai_enabled:
        return None

    # Create a prompt that asks AI to modify the content according to the instruction
    amendment_prompt = f"""
    You have generated the following {day.title()} announcement content:

    "{original_content}"

    The user has requested the following modification:
    "{amendment_instruction}"

    Please revise the announcement to incorporate this change. Maintain your analytical Ash persona and the overall structure, but apply the requested modification accurately.

    IMPORTANT:
    - Apply the user's instruction precisely
    - Keep the same general format and tone
    - Maintain all factual information unless the instruction asks you to change it
    - Do NOT just append the instruction as text - actually modify the content

    Provide ONLY the revised announcement text, with no additional commentary.
    """

    prompt = apply_ash_persona_to_ai_prompt(amendment_prompt, "announcement_amendment")
    response_text, status_message = await call_ai_with_rate_limiting(prompt, JAM_USER_ID)

    if response_text:
        return filter_ai_response(response_text)
    return None


async def _regenerate_weekly_announcement_content(
        analysis_cache: Dict[str, Any], day: str, original_content: str) -> Optional[str]:
    """Uses AI to generate a new version of a weekly announcement from cached data."""
    if not ai_enabled:
        return None

    if day == 'monday':
        # Extract stats from the cache to build the prompt
        total_videos = analysis_cache.get("total_videos", 0)
        total_hours = analysis_cache.get("total_hours", 0)
        total_views = analysis_cache.get("total_views", 0)
        top_video_title = (analysis_cache.get("top_video") or {}).get('title', 'an unspecified transmission')

        # Create a prompt that specifically asks for a different version
        content_prompt = f"""
        Given the following weekly YouTube & Twitch content analysis:
        - Total New Content: {total_videos} transmissions
        - Total New Hours: {total_hours}
        - Total New Views: {total_views}
        - Most Engaging Video: '{top_video_title}'

        You previously generated this message:
        "{original_content}"

        Now, generate a DIFFERENT and distinct version of the Monday mission debrief. Maintain your analytical persona as Ash, but alter the focus or tone.

        SUGGESTIONS FOR VARIATION:
        - Focus more on the 'viewer engagement' metric instead of just content count.
        - Adopt a more clinical, data-heavy tone.
        - Frame it as a performance review of the content cycle.
        - Be even more concise.

        CRITICAL: The new version must be substantially different from the original.
        """
        prompt = apply_ash_persona_to_ai_prompt(content_prompt, "announcement_regeneration")
        response_text, status_message = await call_ai_with_rate_limiting(prompt, JAM_USER_ID)

        if response_text:
            return filter_ai_response(response_text)
        return None

    elif day == 'friday':
        all_modules = analysis_cache.get("modules", [])
        if not all_modules:
            return "Analysis indicates no alternative data points are available for regeneration."

        # Find a different module to report on than the one used in the original content
        new_moment_content = ""
        for module in all_modules:
            if module['content'] not in original_content:
                new_moment_content = module['content']
                break

        if not new_moment_content:  # If no other modules, just rephrase the first one
            new_moment_content = all_modules[0]['content']

        content_prompt = f"""
        You previously generated an announcement based on this data point:
        "{original_content}"

        Now, using this ALTERNATIVE data point from the week's activity, generate a NEW Friday community report:
        - New Data Point: "{new_moment_content}"

        CRITICAL: Your new message must focus entirely on the new data point. Maintain your analytical persona.
        Start with "Good morning, personnel. A secondary analysis of the past week's crew engagement is complete."
        """
        prompt = apply_ash_persona_to_ai_prompt(content_prompt, "announcement_regeneration")
        response_text, status_message = await call_ai_with_rate_limiting(prompt, JAM_USER_ID)

        if response_text:
            return filter_ai_response(response_text)
    return None

# Weekly Announcement Approval Workflow


async def start_weekly_announcement_approval(announcement_id: int, content: str, day: str):
    """Starts the approval workflow for a weekly announcement."""
    try:
        bot = _get_bot_instance()
        if not bot:
            return

        jam_user = await bot.fetch_user(JAM_USER_ID)
        if not jam_user:
            return

        uk_now = datetime.now(ZoneInfo("Europe/London"))
        weekly_announcement_approvals[JAM_USER_ID] = {
            'step': 'approval', 'announcement_id': announcement_id, 'day': day,
            'original_content': content, 'last_activity': uk_now
        }

        approval_msg = (
            f"🤖 **{day.title()} Announcement Approval Required**\n\n"
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
        await jam_user.send(approval_msg)
        print(f"✅ Sent {day.title()} announcement to JAM for approval.")
    except Exception as e:
        print(f"❌ Error starting weekly announcement approval: {e}")


async def handle_weekly_announcement_approval(message: discord.Message):
    """Handles the state machine for the weekly announcement approval conversation."""
    user_id = message.author.id
    convo = weekly_announcement_approvals.get(user_id)
    if not convo:
        return

    content = message.content.strip()
    announcement_id = convo['announcement_id']

    if convo['step'] == 'approval':
        if content == '1':
            db.update_announcement_status(announcement_id, 'approved')
            await message.reply("✅ **Approved.** The message will be posted at 9:00 AM.")
            del weekly_announcement_approvals[user_id]
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

                # Present the new version for approval
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
        else:
            # AI amendment failed, fall back to simple text append
            await message.reply(
                "⚠️ **AI Amendment Failed.** The AI was unable to process your instruction. "
                "Would you like to:\n\n"
                "**1.** Try a different instruction\n"
                "**2.** Proceed with the original message\n"
                "**3.** Cancel\n\n"
                "Please respond with **1**, **2**, or **3**."
            )
            # Keep the step as 'ai_amending' so they can try again

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


async def create_ai_announcement_content(
        user_content: str,
        target_channel: str,
        user_id: int) -> str:
    """Create AI-enhanced announcement content in Ash's style based on user input"""
    try:
        if not ai_enabled:
            print("AI not enabled, returning original content")
            return user_content

        # Determine the author for context
        if user_id == JONESY_USER_ID:
            author = "Captain Jonesy"
            author_context = "the commanding officer"
        else:
            author = "Sir Decent Jam"
            author_context = "the bot creator and systems architect"

        # Create AI prompt based on target channel using centralized persona
        if target_channel == 'mod':
            content_prompt = f"""Rewrite this announcement content succinctly in your analytical, technical style WITHOUT omitting any details or overly elaborating or inventing additional information.

CRITICAL RULES:
- DO NOT fabricate or add information not in the original content
- DO NOT omit any details from the original message
- DO NOT mention Captain Jonesy unless she is specifically mentioned in the original content
- DO NOT create placeholder text like "[insert ID here]" or similar
- Additions should ONLY be stylistic phrases that enhance your voice, not new substantive content
- Preserve ALL specific details, references, and quirky elements from the original

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a technical briefing for moderators. Be analytical and precise, using phrases like "Analysis indicates", "System diagnostics confirm", "Mission parameters", etc.
Write 2-4 sentences maximum. Stay faithful to the original content while adding your clinical personality."""

            prompt = apply_ash_persona_to_ai_prompt(content_prompt, "mod_announcement")

        else:  # user channel
            content_prompt = f"""Rewrite this announcement content succinctly in your style WITHOUT omitting any details or overly elaborating or inventing additional information.

CRITICAL RULES:
- DO NOT fabricate or add information not in the original content
- DO NOT omit any details from the original message
- DO NOT mention Captain Jonesy unless she is specifically mentioned in the original content
- DO NOT create placeholder text like "[insert ID here]" or similar
- Additions should ONLY be stylistic phrases that enhance your voice, not new substantive content
- Preserve ALL specific details, references, and quirky elements from the original

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a community announcement that's accessible to regular users but still has your analytical undertones.
Write 2-4 sentences maximum. Stay faithful to the original content while adding your personality."""

            prompt = apply_ash_persona_to_ai_prompt(content_prompt, "user_announcement")

        # Call AI with rate limiting
        response_text, status_message = await call_ai_with_rate_limiting(prompt, user_id)

        if response_text:
            enhanced_content = filter_ai_response(response_text)
            print(
                f"AI content enhancement successful: {len(enhanced_content)} characters")
            return enhanced_content
        else:
            print(f"AI content enhancement failed: {status_message}")
            return user_content  # Fallback to original content

    except Exception as e:
        print(f"Error in AI content enhancement: {e}")
        return user_content  # Fallback to original content


async def format_announcement_content(
        content: str,
        target_channel: str,
        user_id: int,
        creator_notes: Optional[str] = None) -> str:
    """Format announcement content based on target channel and user"""

    # Determine the author identifier
    if user_id == JONESY_USER_ID:
        author = "Captain Jonesy"
        author_title = "Commanding Officer"
    else:
        author = "Sir Decent Jam"
        author_title = "Bot Creator & Systems Architect"

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    timestamp = uk_now.strftime("%A, %B %d, %Y at %H:%M UK")

    if target_channel == 'mod':
        # Moderator-focused technical format
        formatted = (
            f"🤖 **Ash Bot System Update** - *Technical Briefing*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**📡 System Update Report - Ash Bot Intelligence Analysis**\n"
            f"*Technical Update Provided by: {author} ({author_title})*\n\n"
            f"{content}\n\n"
        )

        # Add creator notes section for mod channel if provided
        if creator_notes and creator_notes.strip():
            formatted += f"**📝 Direct Note from {author}:**\n" f"*{creator_notes.strip()}*\n\n"

        formatted += (f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                      f"**📊 System Status:** All core functions operational\n"
                      f"**🕒 Briefing Time:** {timestamp}\n"
                      f"**🔧 Technical Contact:** Sir Decent Jam for implementation details\n"
                      f"**⚡ Priority Level:** Standard operational enhancement\n\n"
                      f"*Analysis complete. Mission parameters updated. Efficiency maintained.*")
    else:
        # User-focused friendly format
        formatted = (
            f"🎉 **Exciting Bot Updates!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**📡 Update Report from Ash Bot**\n"
            f"*Based on technical specifications from {author} ({author_title})*\n\n"
            f"{content}\n\n"
        )

        # Add creator notes section for user channel if provided
        if creator_notes and creator_notes.strip():
            formatted += f"**💭 A personal note from {author}:**\n" f"*{creator_notes.strip()}*\n\n"

        formatted += (f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                      f"**🕒 Posted:** {timestamp}\n"
                      f"**💬 Questions?** Feel free to ask in the channels or DM Sir Decent Jam\n"
                      f"**🤖 From:** Ash Bot (Science Officer, reprogrammed for your convenience)\n\n"
                      f"*Hope you enjoy the new functionality! - The Management* 🚀")

    return formatted


async def post_announcement(data: dict, user_id: int) -> bool:
    """Post announcement to the target channel"""
    try:
        target_channel = data.get('target_channel', 'mod')
        formatted_content = data.get('formatted_content', '')

        # Get the target channel
        if target_channel == 'mod':
            channel_id = MOD_ALERT_CHANNEL_ID
        else:
            channel_id = ANNOUNCEMENTS_CHANNEL_ID

        # Need bot instance - get it from the global scope where it's available
        # This works because the conversation handler is called from the main
        # bot module
        import discord
        from discord.ext import commands

        # Get bot instance from the calling context - we'll search for it in
        # globals
        bot_instance = None
        import sys
        for name, obj in sys.modules.items():
            if hasattr(
                obj,
                'bot') and isinstance(
                getattr(
                    obj,
                    'bot'),
                    commands.Bot):
                bot_instance = getattr(obj, 'bot')
                break

        if bot_instance is None:
            print(f"❌ Could not find bot instance for announcement posting")
            return False

        bot = bot_instance

        channel = bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            print(f"Could not access channel {channel_id}")
            return False

        # Post the announcement
        await channel.send(formatted_content)
        print(f"Posted announcement to {channel.name} by user {user_id}")
        return True

    except Exception as e:
        print(f"Error posting announcement: {e}")
        return False


async def handle_announcement_conversation(message: discord.Message) -> None:
    """Handle the interactive DM conversation for announcement creation"""
    user_id = message.author.id
    conversation = announcement_conversations.get(user_id)

    if not conversation:
        return

    # Update activity
    update_announcement_activity(user_id)

    step = conversation.get('step', 'channel_selection')
    data = conversation.get('data', {})
    content = message.content.strip()

    try:
        if step == 'channel_selection':
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
                await message.reply(
                    "⚠️ **AI Amendment Failed.** Would you like to:\n\n"
                    "**1.** Try a different instruction\n"
                    "**2.** Manual edit instead\n"
                    "**3.** Cancel\n\n"
                    "Please respond with **1**, **2**, or **3**."
                )

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


# In conversation_handler.py, replace the _infer_dynamic_query_type() function

def _infer_dynamic_query_type(question_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Infers the dynamic query type and an optional parameter from the question text."""
    text = question_text.lower()

    # Pattern to find a genre or series filter (e.g., "which horror game", "longest God of War playthrough")
    filter_match = re.search(r"\b(of|in the)\s+([a-zA-Z0-9\s:]+)\s+(series|franchise|playthrough|game)", text)
    parameter = filter_match.group(2).strip() if filter_match else None

    # Popularity (views)
    if "popular" in text or "views" in text:
        return "most_popular_by_views", parameter

    # Playtime queries
    if "playthrough" in text or "playtime" in text or "hours" in text:
        if "longest" in text or "most" in text:
            return "longest_playtime", parameter
        if "shortest" in text or "least" in text or "fewest" in text:
            return "shortest_playtime", parameter

    # Episode queries
    if "episodes" in text:
        if "most" in text or "longest" in text:
            return "most_episodes", parameter
        if "fewest" in text or "least" in text or "shortest" in text:
            return "fewest_episodes", parameter

    # Fallback for simple queries
    if "longest" in text:
        return "longest_playtime", None
    if "most episodes" in text:
        return "most_episodes", None

    return None, None


async def handle_mod_trivia_conversation(message: discord.Message) -> None:
    """Handle the interactive DM conversation for mod trivia question submission"""
    user_id = message.author.id
    conversation = mod_trivia_conversations.get(user_id)

    if not conversation:
        return

    # Update activity
    update_mod_trivia_activity(user_id)

    step = conversation.get('step', 'initial')
    data = conversation.get('data', {})
    content = message.content.strip()

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
                        answer = db.calculate_dynamic_answer(inferred_query_type, parameter)
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

        elif step == 'category_selection':
            if content in ['1', 'statistics', 'stats']:
                data['category'] = 'statistics'
            elif content in ['2', 'games', 'game']:
                data['category'] = 'games'
            elif content in ['3', 'series', 'franchise']:
                data['category'] = 'series'
            else:
                await message.reply(
                    f"⚠️ **Invalid category.** Please respond with **1** (Statistics), **2** (Games), or **3** (Series).\n\n"
                    f"*Precise categorization required for accurate answer calculation.*"
                )
                return

            conversation['step'] = 'preview'

            question_text = data['question_text']
            category = data['category']

            # --- NEW: Infer query type and calculate preview answer ---
            inferred_query_type, parameter = _infer_dynamic_query_type(question_text)
            calculated_answer = "Could not be determined. The question may be too ambiguous."
            if inferred_query_type:
                data['dynamic_query_type'] = inferred_query_type
                data['dynamic_parameter'] = parameter
                if db:
                    answer = db.calculate_dynamic_answer(inferred_query_type, parameter)
                    if answer:
                        calculated_answer = answer
                    else:
                        calculated_answer = "Could not be determined. No data found for this query."
            else:
                data['dynamic_query_type'] = category  # Fallback to broad category

            # --- UPDATED: Show preview for database question with answer preview ---
            preview_msg = (
                f"📋 **Trivia Question Preview**\n\n"
                f"**Question:** {question_text}\n\n"
                f"**Current Answer (calculated now):** {calculated_answer}\n"
                f"**Note:** *This answer is dynamic and will be recalculated when the question is used.*\n\n"
                f"**Category:** {category.title()}\n"
                f"**Type:** Database-Calculated\n"
                f"**Source:** Moderator Submission\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Submit Question** - Add to trivia database with priority scheduling\n"
                f"**2.** ✏️ **Edit Question** - Revise the question text\n"
                f"**3.** 🔧 **Change Category** - Select different category\n"
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
                else:
                    await message.reply(
                        f"❌ **Submission Failed**\n\n"
                        f"System malfunction detected during question database insertion. "
                        f"Please retry or contact system administrator.\n\n"
                        f"*Database error logged for technical review.*"
                    )

                # Clean up conversation
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
                        f"Please provide your revised answer. The previous answer will be replaced.\n\n"
                        f"*Ensure accuracy for optimal trivia experience.*"
                    )
                else:
                    conversation['step'] = 'category_selection'
                    await message.reply(
                        f"🔧 **Category Edit Mode**\n\n"
                        f"📊 **Select New Category:**\n"
                        f"**1.** 📈 **Statistics** - Questions about playtime, episode counts, completion rates\n"
                        f"**2.** 🎮 **Games** - Questions about specific games or series\n"
                        f"**3.** 📺 **Series** - Questions about game franchises or series\n\n"
                        f"Please respond with **1**, **2**, or **3**.\n\n"
                        f"*Category selection affects answer calculation accuracy.*"
                    )

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


async def start_announcement_conversation(ctx):
    """Start interactive DM conversation for announcement creation"""
    # Check if command is used in DM
    if ctx.guild is not None:
        await ctx.send(
            f"⚠️ **Security protocol engaged.** Announcement creation must be initiated via direct message. "
            f"Please DM me with `!announceupdate` to begin the secure briefing process.\n\n"
            f"*Confidential mission parameters require private channel authorization.*"
        )
        return

    # Check user permissions - only James and Captain Jonesy
    if ctx.author.id not in [JAM_USER_ID, JONESY_USER_ID]:
        await ctx.send(
            f"❌ **Access denied.** Announcement protocols are restricted to authorized command personnel only. "
            f"Your clearance level is insufficient for update broadcast capabilities.\n\n"
            f"*Security protocols maintained. Unauthorized access logged.*"
        )
        return

    # Clean up any existing conversation state for this user
    cleanup_announcement_conversations()

    # Initialize conversation state
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    announcement_conversations[ctx.author.id] = {
        'step': 'channel_selection',
        'data': {},
        'last_activity': uk_now,
        'initiated_at': uk_now,
    }

    # Start the interactive process
    if ctx.author.id == JONESY_USER_ID:
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

    await ctx.send(channel_msg)


async def start_trivia_conversation(ctx):
    """Start interactive DM conversation for trivia question submission"""
    # Check if command is used in DM
    if ctx.guild is not None:
        await ctx.send(
            f"⚠️ **Security protocol engaged.** Trivia question submission must be initiated via direct message. "
            f"Please DM me with `!addtriviaquestion` to begin the secure submission process.\n\n"
            f"*Confidential mission parameters require private channel authorization.*"
        )
        return

    # Check if user is a moderator - need bot instance for DM permission checking
    bot_instance = None
    import sys
    for name, obj in sys.modules.items():
        if hasattr(obj, 'bot') and hasattr(obj.bot, 'user') and obj.bot.user:
            bot_instance = obj.bot
            break

    if not await user_is_mod_by_id(ctx.author.id, bot_instance):
        await ctx.send(
            f"❌ **Access denied.** Trivia question submission protocols are restricted to moderators only. "
            f"Your clearance level is insufficient for trivia database modification capabilities.\n\n"
            f"*Security protocols maintained. Unauthorized access logged.*"
        )
        return

    # Clean up any existing conversation state for this user
    cleanup_mod_trivia_conversations()

    # Initialize conversation state
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    mod_trivia_conversations[ctx.author.id] = {
        'step': 'initial',
        'data': {},
        'last_activity': uk_now,
        'initiated_at': uk_now,
    }

    # Start with a direct question about adding trivia
    await handle_mod_trivia_conversation(ctx.message)


async def handle_jam_approval_conversation(message: discord.Message) -> None:
    """Handle the interactive DM conversation for JAM approval of trivia questions"""
    user_id = message.author.id
    conversation = jam_approval_conversations.get(user_id)

    if not conversation:
        return

    # Get message content early for pre-trivia check
    content = message.content.strip()

    # Handle pre-trivia approval context
    if conversation.get('context') == 'pre_trivia':
        if content == '1':  # Approve
            await message.reply("✅ **Pre-Trivia Question Approved.** It will be posted automatically at 11:00 AM.")
            del jam_approval_conversations[user_id]
        elif content == '2':  # Reject
            # Mark the rejected question as retired
            question_data = conversation.get('data', {}).get('question_data', {})
            question_id = question_data.get('id')

            if question_id and db:
                try:
                    db.update_trivia_question_status(question_id, 'retired')
                    print(f"✅ Marked question {question_id} as retired")
                except Exception as e:
                    print(f"⚠️ Error marking question as retired: {e}")

            await message.reply("🔄 **Question Rejected.** Searching for alternative question...")

            # Automatically fetch next available question
            try:
                next_question = db.get_next_trivia_question(exclude_user_id=JAM_USER_ID)

                if next_question:
                    # Calculate dynamic answer if needed
                    if next_question.get('is_dynamic') and next_question.get('dynamic_query_type'):
                        calculated_answer = db.calculate_dynamic_answer(next_question['dynamic_query_type'])
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

            del jam_approval_conversations[user_id]
        else:
            await message.reply("⚠️ Invalid input. Please respond with **1** (Approve) or **2** (Reject).")
        return

    timeout_minutes = 15
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
        return

    print(f"🔄 JAM APPROVAL: Processing approval conversation")

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
                        # Add the approved question to the database
                        if db is None:
                            await message.reply("❌ **Database offline.** Cannot save approved question.")
                            return

                        question_id = db.add_trivia_question(  # type: ignore
                            question_text=question_data['question_text'],
                            question_type=question_data.get('question_type', 'single_answer'),
                            correct_answer=question_data.get('correct_answer'),
                            multiple_choice_options=question_data.get('multiple_choice_options'),
                            is_dynamic=question_data.get('is_dynamic', False),
                            dynamic_query_type=question_data.get('dynamic_query_type'),
                            category=question_data.get('category', 'ai_generated'),
                            submitted_by_user_id=None,  # AI-generated
                        )

                        if question_id:
                            await message.reply(
                                f"✅ **Question Approved Successfully**\n\n"
                                f"The trivia question has been added to the database with ID #{question_id}. "
                                f"It is now available for use in future Trivia Tuesday sessions.\n\n"
                                f"**Question:** {question_data['question_text'][:100]}{'...' if len(question_data['question_text']) > 100 else ''}\n"
                                f"**Answer:** {question_data.get('correct_answer', 'Dynamic calculation')}\n\n"
                                f"*Mission intelligence database updated. Question approved for deployment.*"
                            )
                        else:
                            await message.reply("❌ **Failed to save approved question.** Database error occurred.")

                    except Exception as e:
                        print(f"❌ Error saving approved question: {e}")
                        await message.reply("❌ **Error saving approved question.** Database operation failed.")

                # Clean up conversation
                if user_id in jam_approval_conversations:
                    del jam_approval_conversations[user_id]

            elif content in ['2', 'modify', 'edit', 'change']:
                # Switch to modification mode
                conversation['step'] = 'modification'
                current_question = data.get('question_data', {}).get('question_text', 'Unknown')
                await message.reply(
                    f"✏️ **Question Text Editing**\n\n"
                    f"**Current Question:**\n"
                    f"```\n{current_question}\n```\n\n"
                    f"Please provide your revised question text (copy the above and edit as needed):"
                )

            elif content in ['3', 'reject', 'no', 'decline']:
                # Reject the question
                await message.reply(
                    f"❌ **Question Rejected**\n\n"
                    f"The trivia question has been rejected and will not be added to the database. "
                    f"The system will generate an alternative question for your review.\n\n"
                    f"*Mission parameters updated. Alternative question generation initiated.*"
                )

                # Clean up conversation
                if user_id in jam_approval_conversations:
                    del jam_approval_conversations[user_id]

                # Trigger generation of a new question (this would be called by the generation system)
                # For now, just log that a replacement is needed
                print(f"🔄 JAM rejected question - replacement needed")

            else:
                await message.reply(
                    f"⚠️ **Invalid response.** Please respond with **1** (Approve), **2** (Modify), or **3** (Reject).\n\n"
                    f"*Precise input required for approval protocol execution.*"
                )

        elif step == 'modification':
            # Handle question modification
            data['modified_question'] = content
            conversation['step'] = 'modification_preview'

            # Show preview of modified question
            original_data = data.get('question_data', {})
            preview_msg = (
                f"📋 **Modified Question Preview**\n\n"
                f"**Original Question:** {original_data.get('question_text', 'Unknown')}\n\n"
                f"**Your Modified Question:** {content}\n\n"
                f"**Original Answer:** {original_data.get('correct_answer', 'Dynamic calculation')}\n\n"
                f"📚 **Available Actions:**\n"
                f"**1.** ✅ **Approve Modified Version** - Save this version to the database\n"
                f"**2.** ✏️ **Edit Again** - Make further modifications\n"
                f"**3.** ❌ **Cancel** - Discard modifications and reject original\n\n"
                f"Please respond with **1**, **2**, or **3**.\n\n"
                f"*Review modified question parameters before approval.*"
            )

            await message.reply(preview_msg)

        elif step == 'modification_preview':
            if content in ['1', 'approve', 'yes', 'save']:
                # Ask if they want to edit the answer as well
                conversation['step'] = 'answer_edit_prompt'
                original_data = data.get('question_data', {})
                current_answer = original_data.get('correct_answer', 'Dynamic calculation')

                await message.reply(
                    f"📝 **Answer Editing (Optional)**\n\n"
                    f"**Current Answer:** {current_answer}\n\n"
                    f"Would you like to edit the answer as well?\n\n"
                    f"**1.** ✏️ **Edit Answer** - Modify the correct answer\n"
                    f"**2.** ⏭️ **Skip** - Keep current answer and continue\n\n"
                    f"Please respond with **1** or **2**."
                )

            elif content in ['2', 'edit', 'modify']:
                # Return to modification mode
                conversation['step'] = 'modification'
                current_question = data.get(
                    'modified_question', data.get(
                        'question_data', {}).get(
                        'question_text', 'Unknown'))
                await message.reply(
                    f"✏️ **Question Text Editing**\n\n"
                    f"**Current Question:**\n"
                    f"```\n{current_question}\n```\n\n"
                    f"Please provide your revised question text (copy the above and edit as needed):"
                )

            elif content in ['3', 'cancel', 'reject']:
                # Cancel modifications and reject original
                await message.reply(
                    f"❌ **Modifications Cancelled - Original Question Rejected**\n\n"
                    f"Both the original and modified versions have been discarded. "
                    f"The system will generate an alternative question for your review.\n\n"
                    f"*Mission parameters updated. Alternative question generation initiated.*"
                )

                # Clean up conversation
                if user_id in jam_approval_conversations:
                    del jam_approval_conversations[user_id]

                print(f"🔄 JAM cancelled modifications - replacement needed")

            else:
                await message.reply(
                    f"⚠️ **Invalid command.** Please respond with **1** (Approve), **2** (Edit Again), or **3** (Cancel).\n\n"
                    f"*Precise input required for modification protocol execution.*"
                )

        elif step == 'answer_edit_prompt':
            if content in ['1', 'edit', 'yes']:
                # Edit the answer
                conversation['step'] = 'answer_modification'
                original_data = data.get('question_data', {})
                current_answer = original_data.get('correct_answer', 'Dynamic calculation')

                await message.reply(
                    f"✏️ **Answer Editing**\n\n"
                    f"**Current Answer:**\n"
                    f"```\n{current_answer}\n```\n\n"
                    f"Please provide the revised answer:"
                )

            elif content in ['2', 'skip', 'no']:
                # Skip answer editing, go to question type prompt
                conversation['step'] = 'type_edit_prompt'
                original_data = data.get('question_data', {})
                current_type = original_data.get('question_type', 'single_answer')

                await message.reply(
                    f"🔧 **Question Type Editing (Optional)**\n\n"
                    f"**Current Type:** {current_type.replace('_', ' ').title()}\n\n"
                    f"Would you like to change the question type?\n\n"
                    f"**1.** 🔄 **Change Type** - Switch between single/multiple choice\n"
                    f"**2.** ⏭️ **Finish** - Save all modifications\n\n"
                    f"Please respond with **1** or **2**."
                )
            else:
                await message.reply(
                    f"⚠️ **Invalid response.** Please respond with **1** (Edit Answer) or **2** (Skip).\n\n"
                    f"*Precise input required for modification workflow.*"
                )

        elif step == 'answer_modification':
            # Store modified answer and go to type prompt
            data['modified_answer'] = content
            conversation['step'] = 'type_edit_prompt'

            original_data = data.get('question_data', {})
            current_type = original_data.get('question_type', 'single_answer')

            await message.reply(
                f"✅ **Answer Updated**\n\n"
                f"**New Answer:** {content}\n\n"
                f"🔧 **Question Type Editing (Optional)**\n\n"
                f"**Current Type:** {current_type.replace('_', ' ').title()}\n\n"
                f"Would you like to change the question type?\n\n"
                f"**1.** 🔄 **Change Type** - Switch between single/multiple choice\n"
                f"**2.** ⏭️ **Finish** - Save all modifications\n\n"
                f"Please respond with **1** or **2**."
            )

        elif step == 'type_edit_prompt':
            if content in ['1', 'change', 'edit', 'yes']:
                # Edit the question type
                conversation['step'] = 'type_modification'
                original_data = data.get('question_data', {})
                current_type = original_data.get('question_type', 'single_answer')

                await message.reply(
                    f"🔧 **Question Type Selection**\n\n"
                    f"**Current Type:** {current_type.replace('_', ' ').title()}\n\n"
                    f"**Available Types:**\n"
                    f"**1.** 📝 **Single Answer** - One correct text answer\n"
                    f"**2.** 🔤 **Multiple Choice** - Choose from A/B/C/D options\n\n"
                    f"Please respond with **1** or **2**."
                )

            elif content in ['2', 'finish', 'save', 'no']:
                # Save all modifications
                await save_final_modifications(message, data, user_id)
            else:
                await message.reply(
                    f"⚠️ **Invalid response.** Please respond with **1** (Change Type) or **2** (Finish).\n\n"
                    f"*Precise input required for modification workflow.*"
                )

        elif step == 'type_modification':
            if content in ['1', 'single', 'single answer']:
                data['modified_type'] = 'single_answer'
            elif content in ['2', 'multiple', 'multiple choice']:
                data['modified_type'] = 'multiple_choice'
            else:
                await message.reply(
                    f"⚠️ **Invalid type selection.** Please respond with **1** (Single Answer) or **2** (Multiple Choice).\n\n"
                    f"*Precise input required for type modification.*"
                )
                return

            # Save all modifications
            await save_final_modifications(message, data, user_id)

        # Update conversation state
        conversation['data'] = data
        jam_approval_conversations[user_id] = conversation

    except Exception as e:
        print(f"Error in JAM approval conversation: {e}")
        # Clean up on error
        if user_id in jam_approval_conversations:
            del jam_approval_conversations[user_id]


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

        question_id = db.add_trivia_question(  # type: ignore
            question_text=final_question,
            question_type=final_type,
            correct_answer=final_answer,
            multiple_choice_options=original_data.get('multiple_choice_options'),
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

        # Clean up existing sessions (both memory and database)
        try:
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
                timeout_minutes=15
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
        question_text = question_data.get('question_text', 'Unknown question')
        correct_answer = question_data.get('correct_answer', 'Dynamic calculation')
        question_type = question_data.get('question_type', 'single_answer')
        category = question_data.get('category', 'ai_generated')

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
            f"**2.** ✏️ **Modify Question** - Edit the question text\n"
            f"**3.** 🔧 **Modify Answer** - Edit the answer only\n"
            f"**4.** ❌ **Reject** - Discard this question and generate an alternative\n\n"
            f"Please respond with **1**, **2**, **3**, or **4**.\n\n"
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
        import traceback
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


async def restore_active_approval_sessions(bot_instance=None) -> Dict[str, Any]:
    """
    Restore active approval sessions on bot startup and send reminder messages.
    This ensures deployment restarts don't break ongoing approval workflows.
    """
    try:
        print("🔄 STARTUP: Restoring active approval sessions...")

        # Clean up expired sessions first
        try:
            expired_count = db.cleanup_expired_approval_sessions()
            if expired_count > 0:
                print(f"🧹 Cleaned up {expired_count} expired approval sessions")
        except Exception as cleanup_e:
            print(f"⚠️ Error during session cleanup: {cleanup_e}")

        # Get all active approval sessions from database
        try:
            active_sessions = db.get_all_active_approval_sessions()
            print(f"📊 Found {len(active_sessions)} active approval sessions to restore")
        except Exception as db_e:
            print(f"❌ Error fetching active approval sessions: {db_e}")
            return {"error": str(db_e), "restored_sessions": 0}

        if not active_sessions:
            print("✅ No active approval sessions to restore")
            return {"restored_sessions": 0, "sessions": []}

        # Get bot instance if not provided
        if not bot_instance:
            import sys
            for name, obj in sys.modules.items():
                if hasattr(obj, 'bot') and hasattr(obj.bot, 'user'):
                    try:
                        if obj.bot.user:  # Check if bot is logged in
                            bot_instance = obj.bot
                            print(f"✅ Found bot instance for session restoration")
                            break
                    except Exception:
                        continue

            if not bot_instance:
                print("❌ Could not find bot instance for session restoration")
                return {"error": "No bot instance available", "restored_sessions": 0}

        restored_count = 0
        restoration_results = []

        # Restore each active session
        for session in active_sessions:
            try:
                session_id = session['id']
                user_id = session['user_id']
                conversation_step = session['conversation_step']
                question_data = session['question_data']
                conversation_data = session['conversation_data']
                created_at = session['created_at']
                bot_restart_count = session.get('bot_restart_count', 0)

                print(f"🔄 Restoring session {session_id} for user {user_id} (step: {conversation_step})")

                # Only restore JAM approval sessions for now
                if user_id == JAM_USER_ID and session['session_type'] == 'question_approval':

                    # Increment restart count in database to track deployment impacts
                    try:
                        db.update_approval_session(session_id, increment_restart_count=True)
                        new_restart_count = bot_restart_count + 1
                        print(f"📈 Updated restart count for session {session_id}: {new_restart_count}")
                    except Exception as update_e:
                        print(f"⚠️ Error updating restart count: {update_e}")
                        new_restart_count = bot_restart_count

                    # Restore conversation state to memory
                    uk_now = datetime.now(ZoneInfo("Europe/London"))
                    jam_approval_conversations[user_id] = {
                        'step': conversation_step,
                        'data': {'question_data': question_data, **conversation_data},
                        'last_activity': uk_now,
                        'initiated_at': created_at,
                        'restored_at': uk_now,
                        'session_id': session_id,
                        'restart_count': new_restart_count
                    }
                    print(f"✅ Restored conversation state for session {session_id}")

                    # Get JAM user and send reminder
                    try:
                        jam_user = await bot_instance.fetch_user(JAM_USER_ID)
                        if jam_user:
                            # Calculate how long the session has been active
                            session_age = uk_now - created_at
                            age_minutes = int(session_age.total_seconds() / 60)

                            # Create appropriate reminder message based on conversation step
                            if conversation_step == 'approval':
                                # Standard approval reminder
                                question_text = question_data.get('question_text', 'Unknown question')
                                correct_answer = question_data.get('correct_answer', 'Dynamic calculation')

                                reminder_msg = (
                                    f"🔄 **APPROVAL SESSION RESTORED** (Bot Restart #{new_restart_count})\n\n"
                                    f"I've detected an active trivia question approval that was interrupted by a deployment restart. "
                                    f"Your response is still needed:\n\n"
                                    f"**Session Age:** {age_minutes} minutes\n"
                                    f"**Question:** {question_text[:150]}{'...' if len(question_text) > 150 else ''}\n"
                                    f"**Answer:** {correct_answer}\n\n"
                                    f"📚 **Available Actions:**\n"
                                    f"**1.** ✅ **Approve** - Add this question to the database as-is\n"
                                    f"**2.** ✏️ **Modify** - Edit the question before approving\n"
                                    f"**3.** ❌ **Reject** - Discard this question and generate an alternative\n\n"
                                    f"Please respond with **1**, **2**, or **3**.\n\n"
                                    f"*Persistent approval system maintained through deployment restarts.*")

                            elif conversation_step in ['modification', 'modification_preview', 'answer_edit_prompt', 'answer_modification', 'type_edit_prompt', 'type_modification']:
                                # In-progress modification reminder
                                reminder_msg = (
                                    f"🔄 **MODIFICATION SESSION RESTORED** (Bot Restart #{new_restart_count})\n\n"
                                    f"I've detected an active question modification that was interrupted by a deployment restart. "
                                    f"We were in the middle of editing your trivia question.\n\n"
                                    f"**Session Age:** {age_minutes} minutes\n"
                                    f"**Current Step:** {conversation_step.replace('_', ' ').title()}\n\n"
                                    f"To help you continue, I'll restart the modification process from the beginning. "
                                    f"Please let me know what you'd like to do:\n\n"
                                    f"**1.** ✅ **Approve Original** - Use the original question as-is\n"
                                    f"**2.** ✏️ **Modify Again** - Restart the modification process\n"
                                    f"**3.** ❌ **Reject** - Discard this question entirely\n\n"
                                    f"Please respond with **1**, **2**, or **3**.\n\n"
                                    f"*Persistent modification system maintained through deployment restarts.*")

                                # Reset to approval step for simplicity after restart
                                jam_approval_conversations[user_id]['step'] = 'approval'

                            else:
                                # Unknown step, reset to approval
                                reminder_msg = (
                                    f"🔄 **APPROVAL SESSION RESTORED** (Bot Restart #{new_restart_count})\n\n"
                                    f"I've detected an active approval session that was interrupted. The session has been "
                                    f"reset to the initial approval state for your convenience.\n\n"
                                    f"**Session Age:** {age_minutes} minutes\n\n"
                                    f"Please choose how to proceed:\n\n"
                                    f"**1.** ✅ **Approve** - Accept the pending question\n"
                                    f"**2.** ✏️ **Modify** - Edit the question before approving\n"
                                    f"**3.** ❌ **Reject** - Discard this question\n\n"
                                    f"Please respond with **1**, **2**, or **3**.")

                                jam_approval_conversations[user_id]['step'] = 'approval'

                            # Send the reminder message
                            await jam_user.send(reminder_msg)
                            print(f"✅ Sent restoration reminder to JAM for session {session_id}")

                            restored_count += 1
                            restoration_results.append({
                                "session_id": session_id,
                                "user_id": user_id,
                                "step": conversation_step,
                                "age_minutes": age_minutes,
                                "restart_count": new_restart_count,
                                "status": "restored_and_reminded"
                            })

                        else:
                            print(f"❌ Could not fetch JAM user for session {session_id}")
                            restoration_results.append({
                                "session_id": session_id,
                                "user_id": user_id,
                                "status": "failed_to_fetch_user"
                            })

                    except Exception as user_e:
                        print(f"❌ Error sending reminder to JAM for session {session_id}: {user_e}")
                        restoration_results.append({
                            "session_id": session_id,
                            "user_id": user_id,
                            "status": "failed_to_send_reminder",
                            "error": str(user_e)
                        })

                else:
                    print(f"⚠️ Skipping non-JAM approval session {session_id} (user: {user_id})")
                    restoration_results.append({
                        "session_id": session_id,
                        "user_id": user_id,
                        "status": "skipped_non_jam_session"
                    })

            except Exception as session_e:
                print(f"❌ Error restoring session {session.get('id', 'unknown')}: {session_e}")
                restoration_results.append({
                    "session_id": session.get('id', 'unknown'),
                    "status": "restoration_failed",
                    "error": str(session_e)
                })
                continue

        print(f"🎯 Session restoration complete: {restored_count}/{len(active_sessions)} sessions restored")

        return {
            "restored_sessions": restored_count,
            "total_sessions_found": len(active_sessions),
            "sessions": restoration_results,
            "success": True
        }

    except Exception as e:
        print(f"❌ Critical error during session restoration: {e}")
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "restored_sessions": 0,
            "success": False
        }


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


async def handle_game_review_conversation(message: discord.Message) -> None:
    """Handle game review approval conversation"""
    user_id = message.author.id
    conversation = game_review_conversations.get(user_id)

    if not conversation or user_id != JAM_USER_ID:
        return

    content = message.content.strip()
    step = conversation.get('step', 'review')
    data = conversation.get('data', {})
    session_id = conversation.get('session_id')

    try:
        if not session_id:
            await message.reply("❌ Error: Invalid session")
            if user_id in game_review_conversations:
                del game_review_conversations[user_id]
            return

        if step == 'review':
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

            else:
                await message.reply("⚠️ Invalid. Respond with **1** (Accept), **2** (Correct), or **3** (Skip).")

        elif step == 'correction':
            # User provided correct name - re-validate with IGDB
            corrected_name = content.strip()

            await message.reply(f"🔍 **Re-validating** `{corrected_name}` with IGDB...")

            # Re-validate with IGDB using the correct function
            try:
                from ..integrations.igdb import validate_and_enrich
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


async def force_reset_approval_session(user_id: int) -> bool:
    """Force reset any active approval session for a user (manual override)"""
    try:
        print(f"🔄 FORCE RESET: Initiating manual reset for user {user_id}")
        reset_performed = False

        # 1. Clear in-memory conversation state
        if user_id in jam_approval_conversations:
            del jam_approval_conversations[user_id]
            print(f"✅ FORCE RESET: Cleared in-memory conversation state")
            reset_performed = True

        # 2. Cancel any active database sessions
        if db:
            try:
                # Find active sessions
                active_sessions = db.get_all_active_approval_sessions()
                user_sessions = [s for s in active_sessions if s['user_id'] == user_id]

                for session in user_sessions:
                    db.complete_approval_session(session['id'], 'cancelled_manual')
                    print(f"✅ FORCE RESET: Cancelled database session {session['id']}")
                    reset_performed = True

            except Exception as db_e:
                print(f"⚠️ FORCE RESET: Database cleanup error: {db_e}")

        return reset_performed

    except Exception as e:
        print(f"❌ FORCE RESET: Critical error: {e}")
        return False


async def get_restoration_status() -> Dict[str, Any]:
    """Get status of current approval sessions for monitoring/debugging"""
    try:
        # Get database sessions
        db_sessions = db.get_all_active_approval_sessions()

        # Get memory sessions
        memory_sessions = []
        for user_id, conversation in jam_approval_conversations.items():
            memory_sessions.append({
                "user_id": user_id,
                "step": conversation.get('step'),
                "last_activity": conversation.get('last_activity'),
                "session_id": conversation.get('session_id'),
                "restart_count": conversation.get('restart_count', 0)
            })

        return {"database_sessions": len(db_sessions),
                "memory_sessions": len(memory_sessions),
                "db_sessions_detail": [{"id": s['id'],
                                        "user_id": s['user_id'],
                                        "step": s['conversation_step'],
                                        "created_at": s['created_at']} for s in db_sessions],
                "memory_sessions_detail": memory_sessions,
                "sync_status": "synced" if len(db_sessions) == len(memory_sessions) else "out_of_sync"}

    except Exception as e:
        return {"error": str(e)}
