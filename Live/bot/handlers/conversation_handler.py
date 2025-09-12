"""
Conversation Handler Module

Handles interactive DM conversations for announcements and trivia submissions.
Manages conversation state and user flows for complex multi-step interactions.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..config import (
    JONESY_USER_ID, JAM_USER_ID, MOD_ALERT_CHANNEL_ID, ANNOUNCEMENTS_CHANNEL_ID,
    YOUTUBE_UPLOADS_CHANNEL_ID
)
from ..database import db
from ..utils.permissions import (
    get_user_communication_tier, user_is_mod_by_id
)
from .ai_handler import (
    ai_enabled, call_ai_with_rate_limiting, filter_ai_response
)

# Global conversation state management
# user_id: {'step': str, 'data': dict, 'last_activity': datetime}
announcement_conversations: Dict[int, Dict[str, Any]] = {}
mod_trivia_conversations: Dict[int, Dict[str, Any]] = {}


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
        print(f"Cleaned up expired announcement conversation for user {user_id}")


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


async def create_ai_announcement_content(user_content: str, target_channel: str, user_id: int) -> str:
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
            prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot. You need to rewrite this announcement content in your analytical, technical style for a moderator briefing.

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a technical briefing for moderators in Ash's voice. Be analytical, precise, and focus on:
- Technical implementation details
- Operational efficiency improvements  
- System functionality enhancements
- Mission-critical parameters

Use phrases like "Analysis indicates", "System diagnostics confirm", "Operational parameters enhanced", etc.
Keep it professional but maintain Ash's clinical, analytical personality.
Write 2-4 sentences maximum. Be concise but comprehensive."""

        else:  # user channel
            prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot. You need to rewrite this announcement content in a user-friendly way while maintaining some of Ash's analytical personality.

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a community announcement that's accessible to regular users but still has Ash's analytical undertones. Focus on:
- User benefits and improvements
- How features enhance the user experience
- Clear, helpful explanations
- Practical usage information

Be helpful and informative, but keep subtle hints of Ash's analytical nature.
Write 2-4 sentences maximum. Make it engaging and user-focused."""

        # Call AI with rate limiting
        response_text, status_message = await call_ai_with_rate_limiting(prompt, user_id)
        
        if response_text:
            enhanced_content = filter_ai_response(response_text)
            print(f"AI content enhancement successful: {len(enhanced_content)} characters")
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
                      f"**🔧 Technical Contact:** <@{JAM_USER_ID}> for implementation details\n"
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
                      f"**💬 Questions?** Feel free to ask in the channels or DM <@{JAM_USER_ID}>\n"
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

        # Need bot instance - this will need to be passed in when called
        # For now, we'll import it (this should be refactored in main.py integration)
        from ..main import bot

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
                data['content'] = enhanced_content  # Use AI content as primary content
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
                import re
                question_type = (
                    'multiple_choice' if data.get('question_type') == 'manual_answer' and re.search(
                        r'\b[A-D]\)', question_text) else 'single_answer')

                if data.get('question_type') == 'database_calculated':
                    # Database-calculated question
                    question_id = db.add_trivia_question(
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

                    question_id = db.add_trivia_question(
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
