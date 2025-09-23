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

from ..config import GAME_RECOMMENDATION_CHANNEL_ID, GUILD_ID, MEMBERS_CHANNEL_ID

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

# Global state for trivia and bot instance
active_trivia_sessions = {}
_bot_instance = None  # Store the bot instance globally

# Startup validation lock to prevent multiple concurrent validations
_startup_validation_lock = False
_startup_validation_completed = False


def initialize_bot_instance(bot):
    """Initialize the bot instance for scheduled tasks"""
    global _bot_instance
    _bot_instance = bot
    print(f"✅ Scheduled tasks: Bot instance initialized ({bot.user.name if bot.user else 'Unknown'})")


@tasks.loop(time=time(12, 0))  # Run at 12:00 PM (midday) every day
async def scheduled_games_update():
    """Automatically update ongoing games data every Sunday at midday"""
    # Only run on Sundays (weekday 6)
    if datetime.now().weekday() != 6:
        return

    print("🔄 Starting scheduled games update (Sunday midday)")

    try:
        if not _bot_instance:
            print("❌ Bot instance not available for scheduled games update")
            return

        guild = _bot_instance.get_guild(GUILD_ID)
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
        if not _bot_instance:
            print("❌ Bot instance not available for scheduled midnight restart")
            return

        guild = _bot_instance.get_guild(GUILD_ID)
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
        await _bot_instance.close()

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
                # Fallback: use global bot instance
                bot = _bot_instance
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

                if not _bot_instance:
                    print("⚠️ Bot instance not available for AI refresh notification")
                    return

                user = await _bot_instance.fetch_user(JAM_USER_ID)
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

            if not _bot_instance:
                print("⚠️ Bot instance not available for AI refresh error notification")
                return

            user = await _bot_instance.fetch_user(JAM_USER_ID)
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
    """Send Monday morning greeting to chit-chat channel with permission verification"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Only run on Mondays (weekday 0)
    if uk_now.weekday() != 0:
        return

    print(f"🌅 Monday morning greeting triggered at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")

    try:
        if not _bot_instance:
            print("❌ Bot instance not available for Monday morning greeting")
            await notify_scheduled_message_error("Monday morning greeting", "Bot instance not available", uk_now)
            return

        guild = _bot_instance.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Monday morning greeting")
            await notify_scheduled_message_error("Monday morning greeting", "Guild not found", uk_now)
            return

        # Find chit-chat channel
        chit_chat_channel = _bot_instance.get_channel(869528946725748766)
        if not chit_chat_channel or not isinstance(chit_chat_channel, discord.TextChannel):
            print("❌ Chit-chat channel not found for Monday morning greeting")
            await notify_scheduled_message_error("Monday morning greeting", "Chit-chat channel not found or inaccessible", uk_now)
            return

        # Check bot permissions
        bot_member = guild.get_member(_bot_instance.user.id) if _bot_instance.user else None
        if not bot_member:
            print("❌ Bot member not found in guild for permission check")
            await notify_scheduled_message_error("Monday morning greeting", "Bot member not found in guild", uk_now)
            return

        permissions = chit_chat_channel.permissions_for(bot_member)
        if not permissions.send_messages:
            print("❌ Bot lacks Send Messages permission in chit-chat channel")
            await notify_scheduled_message_error("Monday morning greeting", "Missing Send Messages permission in chit-chat channel", uk_now)
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
            f"*Analysis complete. Commence daily operations.*")

        await chit_chat_channel.send(monday_message)
        print(f"✅ Monday morning greeting sent to chit-chat channel")

    except discord.Forbidden:
        print("❌ Permission denied when sending Monday morning greeting")
        await notify_scheduled_message_error("Monday morning greeting", "Permission denied (Forbidden)", uk_now)
    except Exception as e:
        print(f"❌ Error in monday_morning_greeting: {e}")
        await notify_scheduled_message_error("Monday morning greeting", str(e), uk_now)


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
        if not _bot_instance:
            print("❌ Bot instance not available for Tuesday trivia greeting")
            return

        guild = _bot_instance.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Tuesday trivia greeting")
            return

        # Find members channel
        members_channel = _bot_instance.get_channel(MEMBERS_CHANNEL_ID)
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
            f"*Trivia Tuesday protocols will activate at 11:00. Prepare accordingly.*")

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
        if not _bot_instance:
            print("❌ Bot instance not available for Friday morning greeting")
            return

        guild = _bot_instance.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Friday morning greeting")
            return

        # Find chit-chat channel
        chit_chat_channel = _bot_instance.get_channel(869528946725748766)
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
            f"*Weekend operational pause in T-minus 8 hours. Prepare for recreational mode.*")

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

                        if not _bot_instance:
                            print("⚠️ Bot instance not available for emergency trivia notification")
                            return

                        user = await _bot_instance.fetch_user(JAM_USER_ID)
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

            if not _bot_instance:
                print("⚠️ Bot instance not available for pre-trivia error notification")
                return

            user = await _bot_instance.fetch_user(JAM_USER_ID)
            if user:
                await user.send(
                    f"⚠️ **Pre-Trivia Approval Error**\n\n"
                    f"Failed to send today's question for approval at 10:00 AM.\n"
                    f"Error: {str(e)}\n\n"
                    f"*Manual intervention may be required for today's Trivia Tuesday.*"
                )
        except Exception:
            pass


# Run every hour to cleanup old recommendation messages
@tasks.loop(hours=1)
async def cleanup_game_recommendations():
    """Clean up user recommendation messages older than 24 hours in #game-recommendation channel"""
    try:
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        cutoff_time = uk_now - timedelta(hours=24)

        print(f"🧹 Game recommendation cleanup starting at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")

        # Improved bot instance checking with multiple fallback methods
        bot_instance = None
        
        # Method 1: Use global _bot_instance if available
        if _bot_instance and hasattr(_bot_instance, 'user') and _bot_instance.user:
            bot_instance = _bot_instance
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

        guild = bot_instance.get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for game recommendation cleanup")
            return

        # Get the game recommendation channel
        game_rec_channel = bot_instance.get_channel(GAME_RECOMMENDATION_CHANNEL_ID)
        if not game_rec_channel or not isinstance(game_rec_channel, discord.TextChannel):
            print("❌ Game recommendation channel not found for cleanup")
            return

        # Check bot permissions in the channel
        bot_member = guild.get_member(bot_instance.user.id) if bot_instance.user else None
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

        if not _bot_instance:
            print("❌ Bot instance not available for Trivia Tuesday")
            return

        guild = _bot_instance.get_guild(GUILD_ID)
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
            if not _bot_instance:
                print("⚠️ Bot instance not available for Trivia Tuesday error notification")
                return

            guild = _bot_instance.get_guild(GUILD_ID)
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
        if not _bot_instance:
            print("❌ Bot instance not available for trivia answer reveal")
            return

        if session_id not in active_trivia_sessions:
            return

        session_data = active_trivia_sessions[session_id]
        question_data = session_data['question_data']
        channel_id = session_data['channel_id']

        channel = _bot_instance.get_channel(channel_id)
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


# --- Scheduled Message Helper Functions ---

async def notify_scheduled_message_error(task_name: str, error_message: str, timestamp: datetime) -> None:
    """Notify JAM of scheduled message errors"""
    try:
        from ..config import JAM_USER_ID

        if not _bot_instance:
            print("❌ Bot instance not available for scheduled message error notification")
            return

        user = await _bot_instance.fetch_user(JAM_USER_ID)
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
            bot = _bot_instance

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
        if not _bot_instance:
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
                channel = _bot_instance.get_channel(delivery_channel_id)
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
        guild = _bot_instance.get_guild(GUILD_ID)
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
                channel = _bot_instance.get_channel(delivery_channel_id)
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

            if not _bot_instance:
                print("❌ Bot instance not available for delayed trivia validation error notification")
                return

            user = await _bot_instance.fetch_user(JAM_USER_ID)
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


def start_all_scheduled_tasks():
    """Start all scheduled tasks"""
    try:
        if not scheduled_games_update.is_running():  # type: ignore
            scheduled_games_update.start()  # type: ignore
            print("✅ Scheduled games update task started (Sunday midday)")

        if not scheduled_midnight_restart.is_running():  # type: ignore
            scheduled_midnight_restart.start()  # type: ignore
            print("✅ Scheduled midnight restart task started (00:00 PT daily)")

        # Start reminder background tasks
        if not check_due_reminders.is_running():  # type: ignore
            check_due_reminders.start()  # type: ignore
            print("✅ Reminder checking task started (every minute)")

        if not check_auto_actions.is_running():  # type: ignore
            check_auto_actions.start()  # type: ignore
            print("✅ Auto-action checking task started (every minute)")

        if not trivia_tuesday.is_running():  # type: ignore
            trivia_tuesday.start()  # type: ignore
            print("✅ Trivia Tuesday task started (11:00 AM UK time, Tuesdays)")

        if not scheduled_ai_refresh.is_running():  # type: ignore
            scheduled_ai_refresh.start()  # type: ignore
            print("✅ AI module refresh task started (8:05 AM UK time daily)")

        # Start greeting tasks
        if not monday_morning_greeting.is_running():  # type: ignore
            monday_morning_greeting.start()  # type: ignore
            print("✅ Monday morning greeting task started (9:00 AM UK time, Mondays)")

        if not tuesday_trivia_greeting.is_running():  # type: ignore
            tuesday_trivia_greeting.start()  # type: ignore
            print("✅ Tuesday trivia greeting task started (9:00 AM UK time, Tuesdays)")

        if not friday_morning_greeting.is_running():  # type: ignore
            friday_morning_greeting.start()  # type: ignore
            print("✅ Friday morning greeting task started (9:00 AM UK time, Fridays)")

        if not pre_trivia_approval.is_running():  # type: ignore
            pre_trivia_approval.start()  # type: ignore
            print("✅ Pre-trivia approval task started (10:00 AM UK time, Tuesdays)")

        if not cleanup_game_recommendations.is_running():  # type: ignore
            cleanup_game_recommendations.start()  # type: ignore
            print("✅ Game recommendation cleanup task started (every hour)")

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
                    from ..handlers.ai_handler import generate_ai_trivia_question
                    from ..handlers.conversation_handler import start_jam_question_approval

                    print("🔄 EMERGENCY APPROVAL: Generating emergency question")
                    emergency_question = await generate_ai_trivia_question("emergency_approval")

                    if emergency_question:
                        approval_sent = await start_jam_question_approval(emergency_question)
                        if approval_sent:
                            print("✅ EMERGENCY APPROVAL: Emergency question sent to JAM")

                            # Send urgent notification to JAM
                            from ..config import JAM_USER_ID

                            if not _bot_instance:
                                print("❌ Bot instance not available for emergency approval notification")
                                return

                            user = await _bot_instance.fetch_user(JAM_USER_ID)
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

                    if not _bot_instance:
                        print("❌ Bot instance not available for emergency build day notification")
                        return

                    user = await _bot_instance.fetch_user(JAM_USER_ID)
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

        # Check for available questions with retry logic (quick check only)
        available_questions = None
        try:
            available_questions = db.get_available_trivia_questions()  # type: ignore
        except Exception as db_error:
            print(f"⚠️ STARTUP TRIVIA VALIDATION: Database query failed - {db_error}")
            print("⚠️ STARTUP TRIVIA VALIDATION: Continuing with assumption of 0 questions")
            available_questions = []

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

        # Create background task for AI generation to avoid blocking Discord heartbeat
        print(f"🔄 STARTUP TRIVIA VALIDATION: Need to generate {5 - question_count} additional questions")
        print("🔄 STARTUP TRIVIA VALIDATION: Creating non-blocking background task for AI generation...")

        # Create completely detached background task that won't block startup
        asyncio.create_task(_background_question_generation(question_count))

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
    """Background task for generating trivia questions with sequential approval system"""
    try:
        print(f"🧠 BACKGROUND QUESTION GENERATION: Starting with {current_question_count} existing questions")

        questions_needed = min(5 - current_question_count, 4)  # Cap at 4 to avoid overwhelming JAM

        # Check if AI handler is available
        try:
            from ..config import JAM_USER_ID
            from ..handlers.ai_handler import generate_ai_trivia_question
            from ..handlers.conversation_handler import jam_approval_conversations, start_jam_question_approval
            print("✅ BACKGROUND GENERATION: AI handler and conversation handler loaded")
        except ImportError as import_error:
            print(f"❌ BACKGROUND GENERATION: Failed to import required modules - {import_error}")
            return

        # Generate all questions first and queue them
        question_queue = []
        successful_generations = 0
        failed_generations = 0

        print(f"🔄 BACKGROUND GENERATION: Generating {questions_needed} questions for sequential approval...")

        for i in range(questions_needed):
            try:
                print(f"🔄 BACKGROUND GENERATION: Generating question {i+1}/{questions_needed}")

                # Generate AI question with startup context for rate limit bypass
                question_data = await generate_ai_trivia_question("startup_validation")

                if question_data and isinstance(question_data, dict):
                    # Validate the generated question
                    required_fields = ['question_text', 'question_type', 'correct_answer']
                    if all(field in question_data for field in required_fields):
                        question_text = question_data.get('question_text', 'Unknown')
                        print(f"✅ BACKGROUND GENERATION: Generated question {i+1}: {question_text[:50]}...")

                        # Add to queue instead of sending immediately
                        question_queue.append({
                            'data': question_data,
                            'number': i + 1,
                            'text_preview': question_text[:50]
                        })
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

            # Small delay between generations to avoid overwhelming systems
            await asyncio.sleep(2)

        print(
            f"🧠 BACKGROUND GENERATION: Generated {len(question_queue)} questions, now starting sequential approval process")

        # Now send questions one at a time with sequential approval
        approved_count = 0
        approval_failed_count = 0

        for question in question_queue:
            try:
                # Check if JAM is already in an approval conversation before sending
                approval_attempts = 0
                max_attempts = 3

                while JAM_USER_ID in jam_approval_conversations and approval_attempts < max_attempts:
                    approval_attempts += 1
                    print(
                        f"⏳ SEQUENTIAL APPROVAL: JAM is in active approval conversation, waiting 30 seconds (attempt {approval_attempts}/{max_attempts})")
                    await asyncio.sleep(30)

                if JAM_USER_ID in jam_approval_conversations:
                    print(
                        f"⚠️ SEQUENTIAL APPROVAL: JAM still busy after {max_attempts} attempts, skipping question {question['number']}")
                    approval_failed_count += 1
                    continue

                print(
                    f"📤 SEQUENTIAL APPROVAL: Sending question {question['number']}/{len(question_queue)} for approval")
                print(f"   Question: {question['text_preview']}...")

                # Send question for approval
                approval_sent = await start_jam_question_approval(question['data'])

                if approval_sent:
                    print(f"✅ SEQUENTIAL APPROVAL: Question {question['number']} sent successfully")
                    approved_count += 1

                    # Wait longer between questions to allow for review and approval
                    if question != question_queue[-1]:  # Don't wait after the last question
                        print(f"⏳ SEQUENTIAL APPROVAL: Waiting 60 seconds before sending next question...")
                        await asyncio.sleep(60)

                        # Send a brief status update to JAM
                        try:
                            if not _bot_instance:
                                print("⚠️ Bot instance not available for sequential approval status update")
                                continue

                            user = await _bot_instance.fetch_user(JAM_USER_ID)
                            if user and question['number'] < len(question_queue):
                                remaining = len(question_queue) - question['number']
                                await user.send(f"📋 **Sequential Approval Status**: {remaining} more question(s) pending review after this one.")
                                print(f"📊 SEQUENTIAL APPROVAL: Status update sent to JAM ({remaining} remaining)")
                        except Exception as status_error:
                            print(f"⚠️ SEQUENTIAL APPROVAL: Failed to send status update: {status_error}")
                else:
                    print(f"❌ SEQUENTIAL APPROVAL: Failed to send question {question['number']}")
                    approval_failed_count += 1

            except Exception as approval_error:
                print(f"❌ SEQUENTIAL APPROVAL: Error with question {question['number']}: {approval_error}")
                approval_failed_count += 1

        # Final comprehensive status report
        print(f"🧠 SEQUENTIAL APPROVAL: Complete - {approved_count}/{len(question_queue)} questions sent for approval")

        if approved_count > 0:
            print(f"📬 SEQUENTIAL APPROVAL: JAM should have received {approved_count} question(s) sequentially")

            # Send final summary notification to JAM
            try:
                if not _bot_instance:
                    print("⚠️ Bot instance not available for final summary notification")
                    return

                if hasattr(_bot_instance, 'fetch_user') and _bot_instance.user:  # Check if bot is available and ready
                    user = await _bot_instance.fetch_user(JAM_USER_ID)
                    if user:
                        summary_message = (
                            f"🧠 **Sequential Question Approval Complete**\n\n"
                            f"**Final Status:**\n"
                            f"• Questions generated: {successful_generations}\n"
                            f"• Questions sent for approval: {approved_count}\n"
                            f"• Approval sending failures: {approval_failed_count}\n"
                            f"• Generation failures: {failed_generations}\n\n"
                            f"Each question was sent individually with time for review between them.\n"
                            f"This sequential approach prevents overwhelming you with multiple simultaneous approvals.\n\n"
                            f"*All questions above are now ready for your individual review and approval.*")
                        await user.send(summary_message)
                        print("✅ SEQUENTIAL APPROVAL: Final summary notification sent to JAM")
            except Exception as summary_error:
                print(f"⚠️ SEQUENTIAL APPROVAL: Failed to send final summary to JAM: {summary_error}")
        else:
            print("⚠️ SEQUENTIAL APPROVAL: No questions were successfully sent for approval")

    except Exception as e:
        print(f"❌ SEQUENTIAL APPROVAL: Critical error - {e}")
        import traceback
        traceback.print_exc()
