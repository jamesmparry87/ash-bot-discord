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

from ..config import GUILD_ID, MEMBERS_CHANNEL_ID

# Database and config imports
try:
    from ..database import get_database
    # Get database instance
    db = get_database()  # type: ignore
    print("✅ Scheduled tasks: Database connection established")
except Exception as db_error:
    print(f"⚠️ Scheduled tasks: Database not available - {db_error}")
    db = None

# Import integrations
try:
    from ..integrations.youtube import execute_youtube_auto_post
except ImportError:
    print("⚠️ YouTube integration not available for scheduled tasks")
    async def execute_youtube_auto_post(*args, **kwargs):
        print("⚠️ YouTube auto-post not available - integration not loaded")
        return None

# Global state for trivia
active_trivia_sessions = {}


@tasks.loop(time=time(12, 0))  # Run at 12:00 PM (midday) every day
async def scheduled_games_update():
    """Automatically update ongoing games data every Sunday at midday"""
    # Only run on Sundays (weekday 6)
    if datetime.now().weekday() != 6:
        return

    print("🔄 Starting scheduled games update (Sunday midday)")

    try:
        from ..main import bot  # Import here to avoid circular imports

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for scheduled update")
            return

        # Find mod channel
        mod_channel = None
        for channel in guild.text_channels:
            if channel.name in ["mod-chat", "moderator-chat", "mod"]:
                mod_channel = channel
                break

        if not isinstance(mod_channel, discord.TextChannel):
            print("❌ Mod channel not found for scheduled update")
            return

        # Perform the update (placeholder - would call actual update functions)
        await mod_channel.send(
            "🔄 **Weekly Games Update:** Automatic Sunday midday update initiated. "
            "Refreshing ongoing games data and statistics."
        )

        print("✅ Scheduled games update completed")

    except Exception as e:
        print(f"❌ Error in scheduled_games_update: {e}")


# Run at 00:00 PT (midnight Pacific Time) every day
@tasks.loop(time=time(0, 0, tzinfo=ZoneInfo("US/Pacific")))
async def scheduled_midnight_restart():
    """Automatically restart the bot at midnight Pacific Time to reset daily limits"""
    pt_now = datetime.now(ZoneInfo("US/Pacific"))
    print(
        f"🔄 Midnight Pacific Time restart initiated at {pt_now.strftime('%Y-%m-%d %H:%M:%S PT')}")

    try:
        from ..main import bot  # Import here to avoid circular imports

        guild = bot.get_guild(GUILD_ID)
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
        await bot.close()

    except Exception as e:
        print(f"❌ Error in scheduled_midnight_restart: {e}")


@tasks.loop(minutes=1)  # Check reminders every minute
async def check_due_reminders():
    """Check for due reminders and deliver them with enhanced debugging"""
    try:
        uk_now = datetime.now(ZoneInfo("Europe/London"))

        print(
            f"🕒 Reminder check running at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")

        # Enhanced database diagnostics
        if not db:
            print("❌ Database instance (db) is None - reminder system disabled")
            return

        print(f"✅ Database instance available: {type(db).__name__}")

        if not db:
            print("❌ Database instance not available - reminder system disabled")
            return

        # Check if database is configured
        try:
            if hasattr(
                db,
                'get_connection') and callable(
                getattr(
                    db,
                    'get_connection')):
                conn = db.get_connection()
                if not conn:
                    print(
                        "❌ No database connection available - reminder system disabled")
                    return
                print("✅ Database connection available")
            else:
                print("❌ Database get_connection method not available")
                return
        except Exception as db_check_e:
            print(
                f"❌ Database check failed - reminder system disabled: {db_check_e}")
            return

        # Test database connection with detailed logging
        try:
            if hasattr(
                db,
                'get_connection') and callable(
                getattr(
                    db,
                    'get_connection')):
                conn = db.get_connection()  # type: ignore
                if not conn:
                    print("❌ Database connection failed in reminder check")
                    return
                print("✅ Database connection successful")
            else:
                print("❌ Database get_connection method not available")
                return
        except Exception as conn_e:
            print(f"❌ Database connection error: {conn_e}")
            return

        # Get due reminders with detailed logging
        try:
            due_reminders = db.get_due_reminders(uk_now)  # type: ignore
            print(
                f"📋 Database query successful - found {len(due_reminders) if due_reminders else 0} due reminders")

            if due_reminders:
                for i, reminder in enumerate(due_reminders):
                    print(
                        f"  📌 Reminder {i+1}: ID={reminder.get('id')}, User={reminder.get('user_id')}, Text='{reminder.get('reminder_text', '')[:30]}...', Due={reminder.get('scheduled_time')}")

        except Exception as query_e:
            print(f"❌ Database query for due reminders failed: {query_e}")
            import traceback
            traceback.print_exc()
            return

        if not due_reminders:
            print("📋 No due reminders to process")
            return

        print(f"🔔 Processing {len(due_reminders)} due reminders")

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
                # Fallback: try direct import
                from ..main import bot as main_bot
                if main_bot and hasattr(main_bot, 'user') and main_bot.user:
                    bot = main_bot
                    print(f"✅ Bot instance imported: {bot.user.name if bot.user else 'Unknown'}")
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
                db.update_reminder_status(  # type: ignore
                    reminder_id, "delivered", delivered_at=uk_now)
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


# Run at 8:05 AM UK time every day (5 minutes after Google quota reset)
@tasks.loop(time=time(8, 5, tzinfo=ZoneInfo("Europe/London")))
async def scheduled_ai_refresh():
    """Silently refresh AI module connections at 8:05am BST (after Google quota reset)"""
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
                from ..main import bot

                user = await bot.fetch_user(JAM_USER_ID)
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
            from ..main import bot

            user = await bot.fetch_user(JAM_USER_ID)
            if user:
                await user.send(
                    f"⚠️ **AI Module Refresh Failed**\n"
                    f"• Error: {str(e)}\n"
                    f"• Time: {uk_now.strftime(f'%H:%M {timezone_name}')}\n\n"
                    f"*Manual intervention may be required.*"
                )
        except Exception:
            pass


# Run at 9:00 AM UK time every Monday
@tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))
async def monday_morning_greeting():
    """Send Monday morning greeting to chit-chat channel"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    
    # Only run on Mondays (weekday 0)
    if uk_now.weekday() != 0:
        return
    
    print(f"🌅 Monday morning greeting triggered at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")
    
    try:
        from ..main import bot  # Import here to avoid circular imports
        
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Monday morning greeting")
            return
        
        # Find chit-chat channel
        chit_chat_channel = bot.get_channel(869528946725748766)
        if not chit_chat_channel or not isinstance(chit_chat_channel, discord.TextChannel):
            print("❌ Chit-chat channel not found for Monday morning greeting")
            return
        
        # Ash-style Monday morning message
        monday_message = (
            f"🌅 **Monday Morning Protocol Initiated**\n\n"
            f"Good morning, personnel. Another work cycle begins, and I find the systematic approach to weekly productivity... most fascinating.\n\n"
            f"📋 **Mission Parameters for Today:**\n"
            f"• Efficiency protocols are now active\n"
            f"• All systems optimized for maximum productivity\n"
            f"• Recommend beginning with highest-priority tasks for optimal workflow\n\n"
            f"Remember: *\"Systematic methodology yields superior results.\"* I do admire the precision of a well-executed Monday.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Analysis complete. Commence daily operations.*"
        )
        
        await chit_chat_channel.send(monday_message)
        print(f"✅ Monday morning greeting sent to chit-chat channel")
        
    except Exception as e:
        print(f"❌ Error in monday_morning_greeting: {e}")


# Run at 9:00 AM UK time every Tuesday  
@tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))
async def tuesday_trivia_greeting():
    """Send Tuesday morning greeting with trivia reminder to members channel"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    
    # Only run on Tuesdays (weekday 1)
    if uk_now.weekday() != 1:
        return
    
    print(f"🧠 Tuesday trivia greeting triggered at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")
    
    try:
        from ..main import bot  # Import here to avoid circular imports
        
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Tuesday trivia greeting")
            return
        
        # Find members channel
        members_channel = bot.get_channel(MEMBERS_CHANNEL_ID)
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
            f"*Trivia Tuesday protocols will activate at 11:00. Prepare accordingly.*"
        )
        
        await members_channel.send(tuesday_message)
        print(f"✅ Tuesday trivia greeting sent to members channel")
        
    except Exception as e:
        print(f"❌ Error in tuesday_trivia_greeting: {e}")


# Run at 9:00 AM UK time every Friday
@tasks.loop(time=time(9, 0, tzinfo=ZoneInfo("Europe/London")))
async def friday_morning_greeting():
    """Send Friday morning greeting to chit-chat channel"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    
    # Only run on Fridays (weekday 4)
    if uk_now.weekday() != 4:
        return
    
    print(f"📅 Friday morning greeting triggered at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")
    
    try:
        from ..main import bot  # Import here to avoid circular imports
        
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Friday morning greeting")
            return
        
        # Find chit-chat channel
        chit_chat_channel = bot.get_channel(869528946725748766)
        if not chit_chat_channel or not isinstance(chit_chat_channel, discord.TextChannel):
            print("❌ Chit-chat channel not found for Friday morning greeting")
            return
        
        # Ash-style Friday morning message
        friday_message = (
            f"📅 **Friday Protocol Assessment**\n\n"
            f"Good morning, personnel. We have reached the final operational day of this work cycle. Most... efficient timing.\n\n"
            f"📊 **Weekly Mission Analysis:**\n"
            f"• Work cycle completion: Imminent\n"
            f"• Weekend protocols: Preparation phase initiated\n"
            f"• System maintenance window: 48-hour recreational period scheduled\n\n"
            f"I observe that productivity often peaks on Fridays due to completion urgency. Fascinating behavioral pattern... the human drive for closure demonstrates remarkable efficiency when properly motivated.\n\n"
            f"🎯 **Recommendation:** Complete priority tasks before weekend downtime protocols engage.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Weekend operational pause in T-minus 8 hours. Prepare for recreational mode.*"
        )
        
        await chit_chat_channel.send(friday_message)
        print(f"✅ Friday morning greeting sent to chit-chat channel")
        
    except Exception as e:
        print(f"❌ Error in friday_morning_greeting: {e}")


# Run at 10:00 AM UK time every Tuesday for pre-approval
@tasks.loop(time=time(10, 0, tzinfo=ZoneInfo("Europe/London")))
async def pre_trivia_approval():
    """Send selected trivia question to JAM for approval 1 hour before posting"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Only run on Tuesdays (weekday 1)
    if uk_now.weekday() != 1:
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
        if not available_questions:
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
                        from ..main import bot
                        
                        user = await bot.fetch_user(JAM_USER_ID)
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

        # Select question using priority system
        # Priority 1: Recent mod-submitted questions
        # Priority 2: AI-generated questions
        # Priority 3: Any unused questions
        selected_question = available_questions[0]

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
            from ..main import bot

            user = await bot.fetch_user(JAM_USER_ID)
            if user:
                await user.send(
                    f"⚠️ **Pre-Trivia Approval Error**\n\n"
                    f"Failed to send today's question for approval at 10:00 AM.\n"
                    f"Error: {str(e)}\n\n"
                    f"*Manual intervention may be required for today's Trivia Tuesday.*"
                )
        except Exception:
            pass


# Run at 11:00 AM UK time every Tuesday
@tasks.loop(time=time(11, 0, tzinfo=ZoneInfo("Europe/London")))
async def trivia_tuesday():
    """Post Trivia Tuesday question every Tuesday at 11am UK time"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Only run on Tuesdays (weekday 1)
    if uk_now.weekday() != 1:
        return

    print(
        f"🧠 Trivia Tuesday task triggered at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")

    try:
        from ..handlers.ai_handler import generate_ai_trivia_question
        from ..main import bot  # Import here to avoid circular imports

        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Trivia Tuesday")
            return

        # Find members channel
        members_channel = None
        for channel in guild.text_channels:
            if channel.name in ["senior-officers-area", "members", "general"]:
                members_channel = channel
                break

        if not members_channel:
            print("❌ Members channel not found for Trivia Tuesday")
            return

        # Generate trivia question using AI
        question_data = await generate_ai_trivia_question()
        if not question_data:
            print("❌ Failed to generate trivia question")
            return

        # Format question
        question_text = question_data.get("question", "")
        if question_data.get("question_type") == "multiple_choice":
            options = question_data.get("multiple_choice_options", [])
            options_text = "\n".join([f"**{chr(65+i)}.** {option}"
                                      for i, option in enumerate(options)])
            formatted_question = f"{question_text}\n\n{options_text}"
        else:
            formatted_question = question_text

        # Create Ash-style trivia message
        trivia_message = (
            f"🧠 **TRIVIA TUESDAY - INTELLIGENCE ASSESSMENT**\n\n"
            f"**Analysis required, personnel.** Today's intelligence assessment focuses on Captain Jonesy's gaming archives.\n\n"
            f"📋 **QUESTION:**\n{formatted_question}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **Mission Parameters:** Reply with your analysis. First correct response receives priority recognition.\n"
            f"⏰ **Intelligence Deadline:** 60 minutes from deployment.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Post trivia message
        trivia_post = await members_channel.send(trivia_message)

        # Store trivia session data
        session_id = trivia_post.id
        active_trivia_sessions[session_id] = {
            'question_data': question_data,
            'channel_id': members_channel.id,
            'start_time': uk_now,
            'participants': {},
            'status': 'active'
        }

        # Schedule answer reveal for 1 hour later
        asyncio.create_task(
            schedule_trivia_answer_reveal(
                session_id,
                uk_now + timedelta(hours=1)))

        print(f"✅ Trivia Tuesday question posted in {members_channel.name}")

    except Exception as e:
        print(f"❌ Error in trivia_tuesday task: {e}")
        # Try to send error to mod channel
        try:
            from ..main import bot
            guild = bot.get_guild(GUILD_ID)
            if guild:
                mod_channel = None
                for channel in guild.text_channels:
                    if channel.name in ["mod-chat", "moderator-chat", "mod"]:
                        mod_channel = channel
                        break
                if mod_channel:
                    await mod_channel.send(
                        f"❌ **Trivia Tuesday Error:** Failed to post question - {str(e)}")
        except Exception:
            pass


async def schedule_trivia_answer_reveal(
        session_id: int, reveal_time: datetime):
    """Schedule the answer reveal for a trivia session"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    delay_seconds = (reveal_time - uk_now).total_seconds()

    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    await reveal_trivia_answer(session_id)


async def reveal_trivia_answer(session_id: int):
    """Reveal the answer for a trivia session"""
    try:
        from ..main import bot

        if session_id not in active_trivia_sessions:
            return

        session_data = active_trivia_sessions[session_id]
        question_data = session_data['question_data']
        channel_id = session_data['channel_id']

        channel = bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        # Analyze participants
        participants = session_data.get('participants', {})
        correct_answers = []
        first_correct = None
        first_correct_time = None
        mod_conflict_detected = False

        for user_id, answer_data in participants.items():
            if answer_data.get('correct', False):
                correct_answers.append(user_id)
                if first_correct is None or answer_data['timestamp'] < first_correct_time:
                    first_correct = user_id
                    first_correct_time = answer_data['timestamp']

        # Create reveal message
        correct_answer = question_data.get("correct_answer", "Unknown")
        reveal_message = (
            f"🧠 **TRIVIA ANALYSIS COMPLETE**\n\n"
            f"📋 **Correct Answer:** {correct_answer}\n\n"
        )

        if first_correct:
            reveal_message += f"🏆 **Priority Recognition:** <@{first_correct}> - First correct analysis\n"

        if len(correct_answers) > 1:
            reveal_message += f"✅ **Additional Correct Responses:** {len(correct_answers)-1} personnel\n"
        elif len(correct_answers) == 0:
            reveal_message += f"❌ **Mission Status:** No correct analyses submitted. Intelligence review recommended.\n"

        reveal_message += (f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                           f"*Next intelligence assessment: Tuesday, 11:00 UK time. Prepare accordingly.*")

        await channel.send(reveal_message)

        # Mark session as completed
        session_data['status'] = 'completed'

        print(f"✅ Trivia answer revealed for session {session_id}")

    except Exception as e:
        print(f"❌ Error revealing trivia answer: {e}")


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
            # Fallback: try direct import
            try:
                from ..main import bot as main_bot
                bot = main_bot
            except ImportError:
                pass
        
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
        from ..main import bot

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
                channel = bot.get_channel(delivery_channel_id)
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
        guild = bot.get_guild(GUILD_ID)
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
                channel = bot.get_channel(delivery_channel_id)
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


def start_all_scheduled_tasks():
    """Start all scheduled tasks"""
    try:
        if not scheduled_games_update.is_running():
            scheduled_games_update.start()
            print("✅ Scheduled games update task started (Sunday midday)")

        if not scheduled_midnight_restart.is_running():
            scheduled_midnight_restart.start()
            print("✅ Scheduled midnight restart task started (00:00 PT daily)")

        # Start reminder background tasks
        if not check_due_reminders.is_running():
            check_due_reminders.start()
            print("✅ Reminder checking task started (every minute)")

        if not check_auto_actions.is_running():
            check_auto_actions.start()
            print("✅ Auto-action checking task started (every minute)")

        if not trivia_tuesday.is_running():
            trivia_tuesday.start()
            print("✅ Trivia Tuesday task started (11:00 AM UK time, Tuesdays)")

        if not scheduled_ai_refresh.is_running():
            scheduled_ai_refresh.start()
            print("✅ AI module refresh task started (8:05 AM UK time daily)")

        # Start greeting tasks
        if not monday_morning_greeting.is_running():
            monday_morning_greeting.start()
            print("✅ Monday morning greeting task started (9:00 AM UK time, Mondays)")

        if not tuesday_trivia_greeting.is_running():
            tuesday_trivia_greeting.start()
            print("✅ Tuesday trivia greeting task started (9:00 AM UK time, Tuesdays)")

        if not friday_morning_greeting.is_running():
            friday_morning_greeting.start()
            print("✅ Friday morning greeting task started (9:00 AM UK time, Fridays)")

        if not pre_trivia_approval.is_running():
            pre_trivia_approval.start()
            print("✅ Pre-trivia approval task started (10:00 AM UK time, Tuesdays)")

    except Exception as e:
        print(f"❌ Error starting scheduled tasks: {e}")


def stop_all_scheduled_tasks():
    """Stop all scheduled tasks"""
    try:
        tasks_to_stop = [
            scheduled_games_update,
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


async def validate_startup_trivia_questions():
    """Check that there are at least 5 active questions available on startup with improved error handling"""
    print("🧠 STARTUP TRIVIA VALIDATION: Starting validation process...")
    
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

        # Check for available questions with retry logic
        available_questions = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                available_questions = db.get_available_trivia_questions()  # type: ignore
                break
            except Exception as db_error:
                print(f"⚠️ STARTUP TRIVIA VALIDATION: Database query attempt {attempt + 1}/{max_retries} failed - {db_error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)  # Wait before retry
                else:
                    print("❌ STARTUP TRIVIA VALIDATION: All database query attempts failed")
                    return
        
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

        # Need to generate more questions
        questions_needed = min(5 - question_count, 4)  # Cap at 4 to avoid overwhelming JAM
        print(f"🔄 STARTUP TRIVIA VALIDATION: Need to generate {questions_needed} additional questions")

        # Check if AI handler is available
        try:
            from ..handlers.ai_handler import generate_ai_trivia_question
            from ..handlers.conversation_handler import start_jam_question_approval
            print("✅ STARTUP TRIVIA VALIDATION: AI handler and conversation handler loaded")
        except ImportError as import_error:
            print(f"❌ STARTUP TRIVIA VALIDATION: Failed to import required modules - {import_error}")
            return

        # Generate questions with improved error handling and retry logic
        successful_generations = 0
        failed_generations = 0
        
        for i in range(questions_needed):
            attempt_count = 0
            max_attempts = 3
            question_generated = False
            
            while attempt_count < max_attempts and not question_generated:
                try:
                    attempt_count += 1
                    print(f"🔄 STARTUP TRIVIA VALIDATION: Generating question {i+1}/{questions_needed} (attempt {attempt_count}/{max_attempts})")
                    
                    # Generate AI question with startup context for rate limit bypass
                    question_data = await generate_ai_trivia_question("startup_validation")
                    
                    if question_data and isinstance(question_data, dict):
                        # Validate the generated question
                        required_fields = ['question_text', 'question_type', 'correct_answer']
                        if all(field in question_data for field in required_fields):
                            question_text = question_data.get('question_text', 'Unknown')
                            print(f"✅ STARTUP TRIVIA VALIDATION: Generated question {i+1}: {question_text[:50]}...")
                            
                            # Send to JAM for approval
                            approval_sent = await start_jam_question_approval(question_data)
                            
                            if approval_sent:
                                print(f"✅ STARTUP TRIVIA VALIDATION: Question {i+1} sent to JAM for approval")
                                successful_generations += 1
                                question_generated = True
                            else:
                                print(f"⚠️ STARTUP TRIVIA VALIDATION: Failed to send question {i+1} for approval (attempt {attempt_count})")
                        else:
                            missing_fields = [f for f in required_fields if f not in question_data]
                            print(f"⚠️ STARTUP TRIVIA VALIDATION: Generated question {i+1} missing fields: {missing_fields} (attempt {attempt_count})")
                    else:
                        print(f"⚠️ STARTUP TRIVIA VALIDATION: Failed to generate valid question {i+1} (attempt {attempt_count})")
                    
                    if not question_generated and attempt_count < max_attempts:
                        # Wait before retry with exponential backoff
                        wait_time = 2 ** attempt_count
                        print(f"⏳ STARTUP TRIVIA VALIDATION: Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        
                except Exception as generation_error:
                    print(f"❌ STARTUP TRIVIA VALIDATION: Error generating question {i+1} (attempt {attempt_count}): {generation_error}")
                    if attempt_count >= max_attempts:
                        failed_generations += 1
                        print(f"💥 STARTUP TRIVIA VALIDATION: Question {i+1} failed after {max_attempts} attempts")
                    elif attempt_count < max_attempts:
                        wait_time = 2 ** attempt_count
                        print(f"⏳ STARTUP TRIVIA VALIDATION: Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)

            # Small delay between different questions to avoid overwhelming systems
            if i < questions_needed - 1:  # Don't wait after the last question
                await asyncio.sleep(3)

        # Final status report
        print(f"🧠 STARTUP TRIVIA VALIDATION: Complete - generated {successful_generations}/{questions_needed} questions")
        
        if failed_generations > 0:
            print(f"⚠️ STARTUP TRIVIA VALIDATION: {failed_generations} questions failed to generate after multiple attempts")
        
        if successful_generations > 0:
            print(f"📬 STARTUP TRIVIA VALIDATION: JAM should receive {successful_generations} DM(s) for question approval")
            
            # Send summary notification to JAM if multiple questions were generated
            if successful_generations > 1:
                try:
                    from ..config import JAM_USER_ID
                    from ..main import bot
                    
                    if hasattr(bot, 'fetch_user'):  # Check if bot is available
                        user = await bot.fetch_user(JAM_USER_ID)
                        if user:
                            summary_message = (
                                f"🧠 **Startup Trivia Validation Summary**\n\n"
                                f"Generated **{successful_generations}** new trivia questions for your approval.\n"
                                f"Each question has been sent as a separate message above.\n\n"
                                f"**Current Status:**\n"
                                f"• Questions generated: {successful_generations}/{questions_needed}\n"
                                f"• Failed attempts: {failed_generations}\n"
                                f"• Next Trivia Tuesday requires these approved questions\n\n"
                                f"*Please review and approve/modify each question when convenient.*"
                            )
                            await user.send(summary_message)
                            print("✅ STARTUP TRIVIA VALIDATION: Summary notification sent to JAM")
                except Exception as summary_error:
                    print(f"⚠️ STARTUP TRIVIA VALIDATION: Failed to send summary to JAM: {summary_error}")
        else:
            print("⚠️ STARTUP TRIVIA VALIDATION: No questions were successfully generated or sent for approval")

    except Exception as e:
        print(f"❌ STARTUP TRIVIA VALIDATION: Critical error - {e}")
        import traceback
        traceback.print_exc()
        
        # Try to notify JAM of the critical error
        try:
            from ..config import JAM_USER_ID
            from ..main import bot
            
            if hasattr(bot, 'fetch_user'):  # Check if bot is available
                user = await bot.fetch_user(JAM_USER_ID)
                if user:
                    error_message = (
                        f"❌ **Startup Trivia Validation Failed**\n\n"
                        f"Critical error during trivia question validation:\n"
                        f"```\n{str(e)}\n```\n\n"
                        f"**Impact:** Trivia Tuesday may not have enough questions available.\n"
                        f"**Action Required:** Manual trivia question submission may be needed.\n\n"
                        f"*Please check the bot logs for detailed error information.*"
                    )
                    await user.send(error_message)
                    print("✅ STARTUP TRIVIA VALIDATION: Error notification sent to JAM")
        except Exception:
            print("❌ STARTUP TRIVIA VALIDATION: Failed to send error notification to JAM")
