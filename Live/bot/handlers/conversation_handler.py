"""
Conversation Handler Module

Handles interactive DM conversations for announcements and trivia submissions.
Manages conversation state and user flows for complex multi-step interactions.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
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

# Get database instance
db = get_database()  # type: ignore

# Global conversation state management
# user_id: {'step': str, 'data': dict, 'last_activity': datetime}
announcement_conversations: Dict[int, Dict[str, Any]] = {}
mod_trivia_conversations: Dict[int, Dict[str, Any]] = {}
jam_approval_conversations: Dict[int, Dict[str, Any]] = {}


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
    """Remove JAM approval conversations inactive for more than 2 hours"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=2)
    expired_users = [
        user_id for user_id,
        data in jam_approval_conversations.items() if data.get(
            "last_activity",
            uk_now) < cutoff_time]
    for user_id in expired_users:
        del jam_approval_conversations[user_id]
        print(f"Cleaned up expired JAM approval conversation for user {user_id}")


def update_jam_approval_activity(user_id: int):
    """Update last activity time for JAM approval conversation"""
    if user_id in jam_approval_conversations:
        jam_approval_conversations[user_id]["last_activity"] = datetime.now(
            ZoneInfo("Europe/London"))


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

        # Create AI prompt based on target channel
        if target_channel == 'mod':
            prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot. Rewrite this announcement content succinctly in Ash's analytical, technical style WITHOUT omitting any details or overly elaborating or inventing additional information.

CRITICAL RULES:
- DO NOT fabricate or add information not in the original content
- DO NOT omit any details from the original message
- DO NOT mention Captain Jonesy unless she is specifically mentioned in the original content
- DO NOT create placeholder text like "[insert ID here]" or similar
- Additions should ONLY be stylistic phrases that enhance Ash's voice, not new substantive content
- Preserve ALL specific details, references, and quirky elements from the original

CRITICAL DISAMBIGUATION RULE: In this Discord server context, "Jonesy" ALWAYS refers to Captain Jonesy - the Discord user, server owner, and streamer/YouTuber (she/her pronouns). This is the default and correct interpretation unless explicitly discussing the 1979 Alien movie.

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a technical briefing for moderators in Ash's voice. Be analytical and precise, using phrases like "Analysis indicates", "System diagnostics confirm", "Mission parameters", etc.
Write 2-4 sentences maximum. Stay faithful to the original content while adding Ash's clinical personality."""

        else:  # user channel
            prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot. Rewrite this announcement content succinctly in Ash's style WITHOUT omitting any details or overly elaborating or inventing additional information.

CRITICAL RULES:
- DO NOT fabricate or add information not in the original content
- DO NOT omit any details from the original message
- DO NOT mention Captain Jonesy unless she is specifically mentioned in the original content
- DO NOT create placeholder text like "[insert ID here]" or similar
- Additions should ONLY be stylistic phrases that enhance Ash's voice, not new substantive content
- Preserve ALL specific details, references, and quirky elements from the original

CRITICAL DISAMBIGUATION RULE: In this Discord server context, "Jonesy" ALWAYS refers to Captain Jonesy - the Discord user, server owner, and streamer/YouTuber (she/her pronouns). This is the default and correct interpretation unless explicitly discussing the 1979 Alien movie.

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a community announcement that's accessible to regular users but still has Ash's analytical undertones.
Write 2-4 sentences maximum. Stay faithful to the original content while adding Ash's personality."""

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
            f"**📡 Mission Update from {author}** (*{author_title}*)\n\n"
            f"{content}\n\n"
        )

        # Add creator notes section for mod channel if provided
        if creator_notes and creator_notes.strip():
            formatted += f"**📝 Technical Notes from {author}:**\n" f"*{creator_notes.strip()}*\n\n"

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
            f"Hey everyone! {author} here with some cool new features:\n\n"
            f"{content}\n\n"
        )

        # Add creator notes section for user channel if provided
        if creator_notes and creator_notes.strip():
            formatted += f"**💭 A note from {author}:**\n" f"*{creator_notes.strip()}*\n\n"

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


async def handle_announcement_conversation(message):
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

            # Create AI-enhanced content in Ash's style
            target_channel = data.get('target_channel', 'mod')
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
                    f"**2.** ✏️ **Edit Content** - Revise the announcement text\n"
                    f"**3.** 📝 **Add Creator Notes** - Include personal notes from the creator\n"
                    f"**4.** ❌ **Cancel** - Abort announcement creation\n\n"
                    f"Please respond with **1**, **2**, **3**, or **4**.\n\n"
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
                # Post regular announcement
                success = await post_announcement(data, user_id)

                if success:
                    target_channel = data.get('target_channel', 'mod')
                    channel_name = "moderator" if target_channel == 'mod' else "community announcements"

                    await message.reply(
                        f"✅ **Announcement Deployed Successfully**\n\n"
                        f"Your update has been transmitted to the {channel_name} channel with proper formatting "
                        f"and presentation protocols. Mission briefing complete.\n\n"
                        f"*Efficient communication maintained. All personnel notified.*"
                    )
                else:
                    await message.reply(
                        f"❌ **Deployment Failed**\n\n"
                        f"System malfunction detected during announcement transmission. Unable to complete "
                        f"briefing protocol.\n\n"
                        f"*Please retry or contact system administrator for technical support.*"
                    )

                # Clean up conversation
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]

            elif content in ['2', 'edit', 'revise']:
                # Return to content input
                conversation['step'] = 'content_input'

                await message.reply(
                    f"✏️ **Content Revision Mode**\n\n"
                    f"Please provide your updated announcement content. Previous content will be replaced "
                    f"with your new input.\n\n"
                    f"*Precision and clarity are paramount for effective mission communication.*"
                )

            elif content in ['3', 'notes', 'creator notes']:
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

            elif content in ['4', 'cancel', 'abort']:
                # Cancel the announcement
                await message.reply(
                    f"❌ **Announcement Protocol Cancelled**\n\n"
                    f"Mission briefing sequence has been terminated. No content has been deployed. "
                    f"All temporary data has been expunged from system memory.\n\n"
                    f"*Mission parameters reset. Standing by for new directives.*"
                )

                # Clean up conversation
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]
            else:
                await message.reply(
                    f"⚠️ **Invalid command.** Please respond with **1** (Post), **2** (Edit), **3** (Creator Notes), or **4** (Cancel).\n\n"
                    f"*Precise input required for proper protocol execution.*"
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
                f"**2.** ✏️ **Edit Content** - Revise the announcement text\n"
                f"**3.** 📝 **Edit Creator Notes** - Modify your personal notes\n"
                f"**4.** ❌ **Cancel** - Abort announcement creation\n\n"
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


async def handle_mod_trivia_conversation(message):
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
                conversation['step'] = 'question_input'

                await message.reply(
                    f"🎯 **Manual Question+Answer Selected**\n\n"
                    f"Please provide your trivia question. You'll provide the answer in the next step.\n\n"
                    f"**Examples of good manual questions:**\n"
                    f"• Which of the following is a well-known Jonesy catchphrase? A) Shit on it! B) Oh crumbles C) Nuke 'em from orbit\n"
                    f"• What happened during Jonesy's playthrough of [specific game] that became a running joke?\n"
                    f"• Which game did Jonesy famously rage-quit after [specific incident]?\n\n"
                    f"**Please provide your question text:**"
                )
            else:
                await message.reply(
                    f"⚠️ **Invalid selection.** Please respond with **1** for database questions or **2** for manual questions.\n\n"
                    f"*Precision is essential for proper protocol execution.*"
                )

        elif step == 'question_input':
            # Store the question and determine next step based on type
            data['question_text'] = content

            if data.get('question_type') == 'manual_answer':
                conversation['step'] = 'answer_input'
                await message.reply(
                    f"📝 **Question Recorded**\n\n"
                    f"**Your Question:** {content}\n\n"
                    f"**Now provide the correct answer.** If this is a multiple choice question, please specify which option (A, B, C, D) is correct.\n\n"
                    f"**Please provide the correct answer:**"
                )
            else:
                conversation['step'] = 'category_selection'
                await message.reply(
                    f"📝 **Question Recorded**\n\n"
                    f"**Your Question:** {content}\n\n"
                    f"📊 **Category Selection** (helps with answer calculation):\n"
                    f"**1.** 📈 **Statistics** - Questions about playtime, episode counts, completion rates\n"
                    f"**2.** 🎮 **Games** - Questions about specific games or series\n"
                    f"**3.** 📺 **Series** - Questions about game franchises or series\n\n"
                    f"Please respond with **1**, **2**, or **3** to categorize your question.\n\n"
                    f"*This helps me calculate the most accurate answer from the database.*"
                )

        elif step == 'answer_input':
            # Store the answer and move to preview
            data['correct_answer'] = content
            conversation['step'] = 'preview'

            # Determine if it's multiple choice based on question content
            question_text = data['question_text']
            is_multiple_choice = bool(re.search(r'\b[A-D]\)', question_text))

            # Show preview
            preview_msg = (
                f"📋 **Trivia Question Preview**\n\n"
                f"**Question:** {question_text}\n\n"
                f"**Answer:** {content}\n\n"
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
                data['dynamic_query_type'] = 'statistics'
            elif content in ['2', 'games', 'game']:
                data['category'] = 'games'
                data['dynamic_query_type'] = 'games'
            elif content in ['3', 'series', 'franchise']:
                data['category'] = 'series'
                data['dynamic_query_type'] = 'series'
            else:
                await message.reply(
                    f"⚠️ **Invalid category.** Please respond with **1** (Statistics), **2** (Games), or **3** (Series).\n\n"
                    f"*Precise categorization required for accurate answer calculation.*"
                )
                return

            conversation['step'] = 'preview'

            # Show preview for database question
            question_text = data['question_text']
            category = data['category']

            preview_msg = (
                f"📋 **Trivia Question Preview**\n\n"
                f"**Question:** {question_text}\n\n"
                f"**Answer:** *Will be calculated from gaming database before posting*\n"
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

    # Check if user is a moderator
    if not await user_is_mod_by_id(ctx.author.id):
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


async def handle_jam_approval_conversation(message):
    """Handle the interactive DM conversation for JAM approval of trivia questions"""
    user_id = message.author.id
    conversation = jam_approval_conversations.get(user_id)

    if not conversation:
        return

    # Only JAM can use this conversation
    if user_id != JAM_USER_ID:
        return

    # Update activity
    update_jam_approval_activity(user_id)

    step = conversation.get('step', 'approval')
    data = conversation.get('data', {})
    content = message.content.strip()

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
                await message.reply(
                    f"✏️ **Question Modification Mode**\n\n"
                    f"Please provide your revised version of the question. You can modify:\n"
                    f"• Question wording\n"
                    f"• Answer content\n"
                    f"• Question type (single/multiple choice)\n\n"
                    f"**Current Question:** {data.get('question_data', {}).get('question_text', 'Unknown')}\n\n"
                    f"**Please provide your modified question:**"
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
                # Save the modified question
                try:
                    if db is None:
                        await message.reply("❌ **Database offline.** Cannot save modified question.")
                        return

                    original_data = data.get('question_data', {})
                    modified_text = data.get('modified_question', '')

                    question_id = db.add_trivia_question(  # type: ignore
                        question_text=modified_text,
                        question_type=original_data.get('question_type', 'single_answer'),
                        correct_answer=original_data.get('correct_answer'),
                        multiple_choice_options=original_data.get('multiple_choice_options'),
                        is_dynamic=original_data.get('is_dynamic', False),
                        dynamic_query_type=original_data.get('dynamic_query_type'),
                        category=original_data.get('category', 'ai_generated_modified'),
                        submitted_by_user_id=JAM_USER_ID,  # Mark as JAM-modified
                    )

                    if question_id:
                        await message.reply(
                            f"✅ **Modified Question Approved Successfully**\n\n"
                            f"Your modified version has been saved to the database with ID #{question_id}.\n\n"
                            f"**Final Question:** {modified_text[:100]}{'...' if len(modified_text) > 100 else ''}\n\n"
                            f"*Mission intelligence database updated with your modifications. Question approved for deployment.*"
                        )
                    else:
                        await message.reply("❌ **Failed to save modified question.** Database error occurred.")

                except Exception as e:
                    print(f"❌ Error saving modified question: {e}")
                    await message.reply("❌ **Error saving modified question.** Database operation failed.")

                # Clean up conversation
                if user_id in jam_approval_conversations:
                    del jam_approval_conversations[user_id]

            elif content in ['2', 'edit', 'modify']:
                # Return to modification mode
                conversation['step'] = 'modification'
                await message.reply(
                    f"✏️ **Question Modification Mode**\n\n"
                    f"Please provide another revision of the question.\n\n"
                    f"**Current Modified Version:** {data.get('modified_question', 'Unknown')}\n\n"
                    f"**Please provide your updated question:**"
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

        # Update conversation state
        conversation['data'] = data
        jam_approval_conversations[user_id] = conversation

    except Exception as e:
        print(f"Error in JAM approval conversation: {e}")
        # Clean up on error
        if user_id in jam_approval_conversations:
            del jam_approval_conversations[user_id]


async def start_jam_question_approval(question_data: Dict[str, Any]) -> bool:
    """Start JAM approval workflow for a generated trivia question with enhanced reliability"""
    try:
        print(f"🚀 Starting JAM approval workflow for question: {question_data.get('question_text', 'Unknown')[:50]}...")
        
        # Get bot instance with enhanced detection
        bot_instance = None
        import sys
        
        # Strategy 1: Search through all modules for bot instance
        modules_copy = dict(sys.modules)  # Create a copy to avoid iteration issues
        for name, obj in modules_copy.items():
            if hasattr(obj, 'bot') and hasattr(obj.bot, 'user'):
                try:
                    if obj.bot.user:  # Check if bot is actually logged in
                        bot_instance = obj.bot
                        print(f"✅ Found bot instance in module: {name}")
                        break
                except Exception:
                    continue
        
        # Strategy 2: Direct import fallback
        if not bot_instance:
            try:
                from ..main import bot as main_bot
                if main_bot and hasattr(main_bot, 'user') and main_bot.user:
                    bot_instance = main_bot
                    print("✅ Bot instance imported from main module")
                else:
                    print("⚠️ Main bot instance not ready (user not logged in)")
            except ImportError as e:
                print(f"⚠️ Could not import bot from main: {e}")
        
        if not bot_instance:
            print("❌ Could not find bot instance for JAM approval")
            return False

        # Clean up any existing approval conversations
        try:
            cleanup_jam_approval_conversations()
            print("✅ Cleaned up existing JAM approval conversations")
        except Exception as cleanup_e:
            print(f"⚠️ Error during cleanup: {cleanup_e}")

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
            f"**Answer:** {correct_answer}\n\n"
        )

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
            f"**2.** ✏️ **Modify** - Edit the question before approving\n"
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
        import traceback
        traceback.print_exc()
        
        # Clean up conversation state on critical error
        try:
            if JAM_USER_ID in jam_approval_conversations:
                del jam_approval_conversations[JAM_USER_ID]
        except:
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
            f"**✅ APPROVE** - This question will be posted at 11:00 AM as scheduled\n"
            f"**❌ REJECT** - An alternative question will be selected and presented for approval\n\n"
            f"Please respond with **APPROVE** or **REJECT**.\n\n"
            f"*Time-sensitive approval required for today's Trivia Tuesday session.*"
        )

        # Send pre-trivia approval request to JAM
        await jam_user.send(pre_approval_msg)
        print(f"✅ Sent pre-trivia approval request to JAM")
        return True

    except Exception as e:
        print(f"❌ Error starting pre-trivia approval workflow: {e}")
        return False
