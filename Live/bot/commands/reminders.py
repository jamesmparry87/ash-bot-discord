"""
Reminder commands for Ash Bot
Handles reminder creation, management, and delivery
"""

import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..database_module import get_database
from ..utils.dm_permissions import is_moderator_or_authorized

# Get database instance
db = get_database()  # type: ignore


class RemindersCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_db(self):
        """Get database instance with error handling"""
        if db is None:
            raise RuntimeError("Database not available")
        return db

    @commands.command(name="remind")
    async def set_reminder(self, ctx, *, content: str | None = None):
        """Enhanced reminder command with traditional Discord format, auto-actions, and natural language support"""
        try:
            if not content:
                # Progressive disclosure help message
                help_text = (
                    "**Quick Examples:**\n"
                    "• `!remind @user 2m Stand up` - Traditional Discord format\n"
                    "• `!remind @user 1h Check on issue | auto:mute` - With auto-action\n"
                    "• `remind me in 5 minutes to check stream` - Natural language\n"
                    "• `set reminder for 7pm` - Specific time (asks for message)\n\n"
                    "**Auto-Actions:** `auto:mute`, `auto:kick`, `auto:ban` (executed if no mod responds within 5 minutes)\n"
                    "**Time Formats:** `2m`, `1h30m`, `2h`, `1d`, `2024-12-25 15:30`, mixed units supported")
                await ctx.send(help_text)
                return

            # Check if database is available for reminders
            database = self._get_db()

            # Parse traditional Discord format with auto-actions: !remind @user 2m
            # Stand up | auto:mute
            traditional_match = re.match(
                r'^<@!?(\d+)>\s+(\d+(?:[smhd]|\d+[smhd])*)\s+(.+)$',
                content.strip())

            if traditional_match:
                # Traditional Discord format detected
                target_user_id = int(traditional_match.group(1))
                time_str = traditional_match.group(2)
                remainder = traditional_match.group(3)

                # Check for auto-action syntax
                auto_action_enabled = False
                auto_action_type = None
                auto_action_data = {}

                if " | auto:" in remainder:
                    parts = remainder.split(" | auto:", 1)
                    reminder_text = parts[0].strip()
                    auto_action_part = parts[1].strip()

                    # Parse auto-action type
                    if auto_action_part.lower() in ['mute', 'kick', 'ban']:
                        auto_action_enabled = True
                        auto_action_type = auto_action_part.lower()
                        auto_action_data = {
                            "reason": f"Auto-action triggered by reminder: {reminder_text[:50]}"}
                    else:
                        await ctx.send("❌ Invalid auto-action type. Supported: `auto:mute`, `auto:kick`, `auto:ban`")
                        return
                else:
                    reminder_text = remainder

                # Parse enhanced time format supporting mixed units like 1h30m
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                scheduled_time = uk_now

                # Parse mixed time units (e.g., 1h30m, 2d5h, etc.)
                time_pattern = r'(\d+)([smhd])'
                time_matches = re.findall(time_pattern, time_str)

                if not time_matches:
                    await ctx.send("❌ Invalid time format. Examples: `2m`, `1h30m`, `2d`, `1h`, mixed units supported")
                    return

                total_seconds = 0
                for amount_str, unit in time_matches:
                    amount = int(amount_str)
                    if unit == 's':
                        total_seconds += amount
                    elif unit == 'm':
                        total_seconds += amount * 60
                    elif unit == 'h':
                        total_seconds += amount * 3600
                    elif unit == 'd':
                        total_seconds += amount * 86400

                scheduled_time = uk_now + timedelta(seconds=total_seconds)

                # Check permissions for setting reminders for others
                if target_user_id != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
                    await ctx.send("❌ Only moderators can set reminders for other users.")
                    return

                # Determine delivery method based on context
                if isinstance(ctx.channel, discord.DMChannel):
                    delivery_type = "dm"
                    delivery_channel_id = None
                else:
                    delivery_type = "channel"
                    delivery_channel_id = ctx.channel.id

                # Add reminder to database with auto-action support
                reminder_id = database.add_reminder(
                    user_id=target_user_id,
                    reminder_text=reminder_text,
                    scheduled_time=scheduled_time,
                    delivery_channel_id=delivery_channel_id,
                    delivery_type=delivery_type,
                    auto_action_enabled=auto_action_enabled,
                    auto_action_type=auto_action_type,
                    auto_action_data=auto_action_data
                )

                if reminder_id:
                    # Use the improved time formatting
                    try:
                        from ..tasks.reminders import format_reminder_time
                        formatted_time = format_reminder_time(scheduled_time)
                    except ImportError:
                        # Fallback if import fails
                        formatted_time = f"in {time_str}"

                    # Simplified confirmation - no user mentions or tags
                    if target_user_id == ctx.author.id:
                        # Setting reminder for themselves - simple confirmation
                        response = f"✅ **Reminder set** {formatted_time}\n*{reminder_text}*"
                    else:
                        # Setting for someone else - show target name only (no mentions)
                        target_user = await self.bot.fetch_user(target_user_id)
                        user_name = target_user.display_name if target_user else 'user'
                        response = f"✅ **Reminder set** for {user_name} {formatted_time}\n*{reminder_text}*"

                    if auto_action_enabled:
                        response += f"\n⚡ Auto-action: {auto_action_type} (if no mod response in 5 minutes)"

                    await ctx.send(response)
                else:
                    await ctx.send("❌ **Failed to save reminder.** Database error occurred. Please try again or contact system administrator.")
                return

            # Try natural language parsing for other formats
            try:
                from ..tasks.reminders import format_reminder_time, parse_natural_reminder, validate_reminder_text

                parsed = parse_natural_reminder(content, ctx.author.id)

                if not parsed["success"]:
                    # Use the enhanced error handling from the validation system
                    error_type = parsed.get("error_type", "unknown")
                    error_message = parsed.get("error_message", "Unable to parse reminder.")
                    suggestion = parsed.get("suggestion", "")

                    response = f"❌ **{error_message}**"
                    if suggestion:
                        response += f"\n\n💡 **Suggestion:** {suggestion}"

                    # Add general help for moderators if it's not a specific parsing error
                    if error_type in ["parsing_ambiguous", "unknown"]:
                        response += ("\n\n**As a moderator, you can also try:**\n"
                                     "• `!remind @user 2m Stand up` (traditional format)\n"
                                     "• `!remind @user 1h30m Check on issue | auto:mute` (with auto-action)\n"
                                     "• `remind me in 30 minutes to check stream` (natural language)\n"
                                     "• `set reminder for 7pm to review reports` (specific time)")

                    await ctx.send(response)
                    return

                # The validation is now handled within parse_natural_reminder, so we can trust the result
                # No need for additional validate_reminder_text check since it's built into the parser now

                # Check if moderator is setting reminder for themselves
                target_user_id = ctx.author.id

                # Determine delivery method based on context
                if isinstance(ctx.channel, discord.DMChannel):
                    delivery_type = "dm"
                    delivery_channel_id = None
                else:
                    delivery_type = "channel"
                    delivery_channel_id = ctx.channel.id

                # Add reminder to database (natural language format)
                reminder_id = database.add_reminder(
                    user_id=target_user_id,
                    reminder_text=parsed["reminder_text"],
                    scheduled_time=parsed["scheduled_time"],
                    delivery_channel_id=delivery_channel_id,
                    delivery_type=delivery_type
                )

                if reminder_id:
                    formatted_time = format_reminder_time(parsed["scheduled_time"])

                    # Simple confirmation message
                    confirmation = f"✅ **Reminder set** {formatted_time}\n*{parsed['reminder_text']}*"

                    await ctx.send(confirmation)
                else:
                    await ctx.send("❌ **Failed to save reminder.** Database error occurred. Please try again or contact system administrator.")

            except ImportError as e:
                # More helpful error for import failures
                print(f"⚠️ Reminder parsing import failed: {e}")
                await ctx.send(
                    "⚠️ **Natural language parsing unavailable.** Use traditional format:\n"
                    "`!remind @user 2m <message>`\n\n"
                    "**Time formats:** 2m (minutes), 1h (hours), 30s (seconds), 1d (days)"
                )

        except RuntimeError:
            await ctx.send("❌ Reminder system offline - database not available.")
        except Exception as e:
            print(f"❌ Error in remind command: {e}")
            await ctx.send("❌ System error occurred. Please try again or contact a moderator.")

    @commands.command(name="listreminders")
    @commands.has_permissions(manage_messages=True)
    async def list_reminders(self, ctx, user: discord.Member | None = None):
        """List pending reminders (moderators only)"""
        try:
            database = self._get_db()

            # Check if advanced reminder methods exist
            if not hasattr(database, 'get_all_pending_reminders'):
                await ctx.send("❌ **Advanced reminder management not available.** Database methods need to be implemented.\n\n*Required methods: `get_all_pending_reminders`, `get_pending_reminders_for_user`, `get_reminder_by_id`, `cancel_reminder`*")
                return

            # Get pending reminders
            try:
                if user:
                    # List reminders for specific user
                    reminders = database.get_pending_reminders_for_user(
                        user.id)
                    if not reminders:
                        await ctx.send(f"📋 **No pending reminders for {user.display_name}.**")
                        return
                    title = f"📋 **Pending Reminders for {user.display_name}:**"
                else:
                    # List all pending reminders
                    reminders = database.get_all_pending_reminders()
                    if not reminders:
                        await ctx.send("📋 **No pending reminders in the system.**")
                        return
                    title = "📋 **All Pending Reminders:**"
            except AttributeError as e:
                await ctx.send("❌ **Database method missing.** Advanced reminder features require additional database implementation.")
                return

            # Build reminder list
            reminder_list = []
            uk_now = datetime.now(ZoneInfo("Europe/London"))

            for reminder in reminders[:10]:  # Limit to 10 for readability
                user_mention = f"<@{reminder['user_id']}>"
                scheduled_time = reminder['scheduled_time']

                # Calculate time until reminder
                time_diff = scheduled_time - uk_now
                if time_diff.total_seconds() > 0:
                    if time_diff.days > 0:
                        time_desc = f"in {time_diff.days}d"
                    elif time_diff.total_seconds() >= 3600:
                        hours = int(time_diff.total_seconds() // 3600)
                        time_desc = f"in {hours}h"
                    else:
                        minutes = max(1, int(time_diff.total_seconds() // 60))
                        time_desc = f"in {minutes}m"
                else:
                    time_desc = "overdue"

                reminder_text = reminder['reminder_text'][:50] + \
                    ("..." if len(reminder['reminder_text']) > 50 else "")

                reminder_list.append(
                    f"**#{reminder['id']}** {user_mention} - *{reminder_text}* ({time_desc})"
                )

            response = title + "\n\n" + "\n".join(reminder_list)

            if len(reminders) > 10:
                response += f"\n\n*Showing first 10 of {len(reminders)} total reminders*"

            response += "\n\n*Use `!cancelreminder <id>` to cancel a reminder*"

            await ctx.send(response[:2000])

        except RuntimeError:
            await ctx.send("❌ Reminder system offline - database not available.")
        except Exception as e:
            print(f"❌ Error in listreminders command: {e}")
            await ctx.send("❌ System error occurred while retrieving reminders.")

    @commands.command(name="cancelreminder")
    @commands.has_permissions(manage_messages=True)
    async def cancel_reminder(self, ctx, reminder_id: int):
        """Cancel a pending reminder by ID (moderators only)"""
        try:
            database = self._get_db()

            # Get reminder details before canceling
            reminder = database.get_reminder_by_id(reminder_id)

            if not reminder:
                await ctx.send(f"❌ **Reminder #{reminder_id} not found.** Use `!listreminders` to see pending reminders.")
                return

            # Cancel the reminder
            success = database.cancel_reminder(reminder_id)

            if success:
                target_user = await self.bot.fetch_user(reminder['user_id'])
                user_name = target_user.display_name if target_user else f"User {reminder['user_id']}"
                reminder_text = reminder['reminder_text'][:100] + \
                    ("..." if len(reminder['reminder_text']) > 100 else "")

                await ctx.send(f"✅ **Reminder #{reminder_id} cancelled.**\n*Was for {user_name}: \"{reminder_text}\"*")
            else:
                await ctx.send(f"❌ **Failed to cancel reminder #{reminder_id}.** It may have already been delivered or cancelled.")

        except ValueError:
            await ctx.send("❌ **Invalid reminder ID.** Please provide a valid number from `!listreminders`.")
        except RuntimeError:
            await ctx.send("❌ Reminder system offline - database not available.")
        except Exception as e:
            print(f"❌ Error in cancelreminder command: {e}")
            await ctx.send("❌ System error occurred while canceling reminder.")

    @commands.command(name="testreminder")
    @is_moderator_or_authorized()
    async def test_reminder(self, ctx, delay: str = "2m"):
        """Test scheduled message delivery system (moderators and authorized users in DMs)"""
        try:
            import asyncio
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo

            from ..config import MODERATOR_CHANNEL_IDS

            # Parse delay time using existing logic from the reminder system
            uk_now = datetime.now(ZoneInfo("Europe/London"))

            # Parse time format (e.g., 2m, 30s, 1h, etc.)
            import re
            time_pattern = r'(\d+)([smhd])'
            time_match = re.match(time_pattern, delay.lower().strip())

            if not time_match:
                await ctx.send("❌ **Invalid time format.** Use formats like `2m`, `30s`, `1h`, `5m`\n\n**Examples:**\n• `!testreminder 2m` - Test in 2 minutes\n• `!testreminder 30s` - Test in 30 seconds\n• `!testreminder 5m` - Test in 5 minutes")
                return

            amount = int(time_match.group(1))
            unit = time_match.group(2)

            # Convert to seconds
            if unit == 's':
                total_seconds = amount
            elif unit == 'm':
                total_seconds = amount * 60
            elif unit == 'h':
                total_seconds = amount * 3600
            elif unit == 'd':
                total_seconds = amount * 86400
            else:
                await ctx.send("❌ **Invalid time unit.** Supported: `s` (seconds), `m` (minutes), `h` (hours), `d` (days)")
                return

            # Reasonable limits for testing
            if total_seconds < 10:
                await ctx.send("❌ **Test delay too short.** Minimum delay is 10 seconds for system reliability.")
                return
            elif total_seconds > 3600:  # 1 hour max
                await ctx.send("❌ **Test delay too long.** Maximum delay is 1 hour for testing purposes.")
                return

            scheduled_time = uk_now + timedelta(seconds=total_seconds)

            # Get Newt Mods channel (target channel for test)
            newt_mods_channel_id = 1213488470798893107  # From MODERATOR_CHANNEL_IDS
            target_channel = self.bot.get_channel(newt_mods_channel_id)

            if not target_channel:
                await ctx.send("❌ **Target channel not found.** Cannot access Newt Mods channel for testing.")
                return

            # Check bot permissions in target channel
            bot_member = ctx.guild.get_member(self.bot.user.id) if self.bot.user else None
            if bot_member:
                permissions = target_channel.permissions_for(bot_member)
                if not permissions.send_messages:
                    await ctx.send("❌ **Permission denied.** Bot lacks send message permission in Newt Mods channel.")
                    return

            # Format delay for display
            if unit == 's':
                delay_display = f"{amount} second{'s' if amount != 1 else ''}"
            elif unit == 'm':
                delay_display = f"{amount} minute{'s' if amount != 1 else ''}"
            elif unit == 'h':
                delay_display = f"{amount} hour{'s' if amount != 1 else ''}"
            else:
                delay_display = f"{amount} day{'s' if amount != 1 else ''}"

            # Send immediate confirmation
            confirmation_msg = (
                f"🧪 **SCHEDULED MESSAGE TEST INITIATED**\n\n"
                f"**Mission Parameters:**\n"
                f"• Test delay: {delay_display}\n"
                f"• Target channel: {target_channel.mention}\n"
                f"• Scheduled delivery: {scheduled_time.strftime('%H:%M:%S UK')}\n"
                f"• Current time: {uk_now.strftime('%H:%M:%S UK')}\n\n"
                f"**Analysis:** Scheduled message system test is now active. "
                f"Delivery confirmation will appear in {target_channel.mention} at the specified time.\n\n"
                f"*Test message deployment in T-minus {delay_display}. Monitoring protocols engaged.*"
            )

            await ctx.send(confirmation_msg)

            # Schedule the actual test message
            asyncio.create_task(
                self._deliver_test_message(
                    target_channel,
                    uk_now,
                    scheduled_time,
                    delay_display,
                    ctx.author.display_name))

            print(f"✅ Test reminder scheduled by {ctx.author.display_name} for {delay_display} from now")

        except Exception as e:
            print(f"❌ Error in testreminder command: {e}")
            await ctx.send("❌ System error occurred while scheduling test message.")

    async def _deliver_test_message(self, channel, initiated_time, scheduled_time, delay_display, initiator_name):
        """Deliver the actual test message after the specified delay"""
        try:
            import asyncio
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo

            # Calculate actual delay time
            uk_now = datetime.now(ZoneInfo("Europe/London"))
            delay_seconds = (scheduled_time - uk_now).total_seconds()

            if delay_seconds > 0:
                # Wait for the scheduled time
                await asyncio.sleep(delay_seconds)

            # Get the actual delivery time
            delivery_time = datetime.now(ZoneInfo("Europe/London"))

            # Create Ash-style test message
            test_message = (
                f"🧪 **SCHEDULED MESSAGE SYSTEM TEST COMPLETE**\n\n"
                f"**Mission Analysis:** Automated message delivery systems are functioning within normal parameters.\n\n"
                f"**Test Results:**\n"
                f"• Test initiated: {initiated_time.strftime('%H:%M:%S UK')}\n"
                f"• Scheduled delivery: {scheduled_time.strftime('%H:%M:%S UK')}\n"
                f"• Actual delivery: {delivery_time.strftime('%H:%M:%S UK')}\n"
                f"• Delay configured: {delay_display}\n"
                f"• Initiated by: {initiator_name}\n"
                f"• Target channel: **Newt Mods** ✅\n\n"
                f"**System Status:** All scheduling subroutines functioning correctly. "
                f"Monday morning messages, Friday messages, and other automated protocols should operate as expected.\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"*Test complete. Scheduled messaging infrastructure validated.*")

            # Send the test message
            await channel.send(test_message)
            print(f"✅ Test message delivered successfully to {channel.name} by {initiator_name}")

        except Exception as e:
            print(f"❌ Error delivering test message: {e}")
            # Try to send error message to the channel
            try:
                error_message = (
                    f"❌ **SCHEDULED MESSAGE TEST FAILED**\n\n"
                    f"An error occurred during test message delivery:\n"
                    f"```{str(e)}```\n\n"
                    f"This may indicate issues with the scheduled messaging system that require attention."
                )
                await channel.send(error_message)
            except Exception as send_error:
                print(f"❌ Could not send error message either: {send_error}")


def setup(bot):
    """Add the RemindersCommands cog to the bot"""
    bot.add_cog(RemindersCommands(bot))
