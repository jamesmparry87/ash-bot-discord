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

from ..config import GUILD_ID

# Database and config imports
from ..database import get_database

# Import integrations
from ..integrations.youtube import execute_youtube_auto_post

# Global state for trivia
active_trivia_sessions = {}

# Get database instance
db = get_database()


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
            if hasattr(db, 'get_connection') and callable(getattr(db, 'get_connection')):
                conn = db.get_connection()
                if not conn:
                    print("❌ No database connection available - reminder system disabled")
                    return
                print("✅ Database connection available")
            else:
                print("❌ Database get_connection method not available")
                return
        except Exception as db_check_e:
            print(f"❌ Database check failed - reminder system disabled: {db_check_e}")
            return

        # Test database connection with detailed logging
        try:
            if hasattr(db, 'get_connection') and callable(getattr(db, 'get_connection')):
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
                        f"  📌 Reminder {i+1}: ID={reminder.get('id')}, User={reminder.get('user_id')}, Text='{reminder.get('reminder_text', '')[:30]}...', Due={reminder.get('due_at')}")

        except Exception as query_e:
            print(f"❌ Database query for due reminders failed: {query_e}")
            import traceback
            traceback.print_exc()
            return

        if not due_reminders:
            print("📋 No due reminders to process")
            return

        print(f"🔔 Processing {len(due_reminders)} due reminders")

        # Import bot here to test bot availability
        try:
            from ..main import bot
            if not bot:
                print("❌ Bot instance not available for reminder delivery")
                return
            print(
                f"✅ Bot instance available: {bot.user.name if bot.user else 'Not logged in'}")
        except ImportError as bot_e:
            print(f"❌ Could not import bot instance: {bot_e}")
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
    """Deliver a reminder to the appropriate channel/user"""
    try:
        from ..main import bot

        user_id = reminder["user_id"]
        reminder_text = reminder["reminder_text"]
        delivery_type = reminder["delivery_type"]
        delivery_channel_id = reminder.get("delivery_channel_id")
        auto_action_enabled = reminder.get("auto_action_enabled", False)

        # Create Ash-style reminder message
        ash_message = f"📋 **Temporal alert activated.** {reminder_text}"

        # Add auto-action notice if enabled
        if auto_action_enabled and reminder.get("auto_action_type"):
            auto_action_type = reminder["auto_action_type"]
            if auto_action_type == "youtube_post":
                ash_message += f"\n\n⚡ **Auto-action protocol engaged.** If you do not respond within 5 minutes, I will automatically execute the YouTube posting sequence. *Efficiency is paramount.*"

        if delivery_type == "dm":
            user = bot.get_user(user_id)
            if user:
                await user.send(ash_message)
                print(f"✅ Delivered DM reminder to user {user_id}")
            else:
                print(f"❌ Could not fetch user {user_id} for DM reminder")

        elif delivery_type == "channel" and delivery_channel_id:
            channel = bot.get_channel(delivery_channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                await channel.send(f"<@{user_id}> {ash_message}")
                print(
                    f"✅ Delivered channel reminder to channel {delivery_channel_id}")
            else:
                print(
                    f"❌ Could not access channel {delivery_channel_id} for reminder")
        else:
            print(
                f"❌ Invalid delivery type or missing channel for reminder {reminder['id']}")

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

        # Check if moderator has intervened by looking for mod messages in channel after reminder delivery
        if delivery_channel_id:
            try:
                channel = bot.get_channel(delivery_channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    # Check messages since reminder delivery for mod intervention
                    delivered_at = reminder.get("delivered_at")
                    if delivered_at:
                        messages_after = []
                        async for message in channel.history(limit=50, after=delivered_at):
                            # Check if author is a Member (has guild_permissions) and has manage_messages permission
                            if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages and not message.author.bot:
                                print(f"✅ Moderator intervention detected - auto-action cancelled for reminder {reminder['id']}")
                                return
            except Exception as check_e:
                print(f"⚠️ Could not check for moderator intervention: {check_e}")

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
        reason = auto_action_data.get("reason", f"Auto-action triggered by reminder system")
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
                    print(f"✅ Auto-action logged in channel {delivery_channel_id}")
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
            trivia_tuesday
        ]

        for task in tasks_to_stop:
            if task.is_running():
                task.stop()

        print("✅ All scheduled tasks stopped")

    except Exception as e:
        print(f"❌ Error stopping scheduled tasks: {e}")
