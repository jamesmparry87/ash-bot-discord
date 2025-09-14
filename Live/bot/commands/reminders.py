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

# Get database instance
db = get_database()


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

                # Add reminder to database with auto-action support
                reminder_id = database.add_reminder(
                    user_id=target_user_id,
                    reminder_text=reminder_text,
                    scheduled_time=scheduled_time,
                    delivery_channel_id=ctx.channel.id,
                    delivery_type="channel",
                    auto_action_enabled=auto_action_enabled,
                    auto_action_type=auto_action_type,
                    auto_action_data=auto_action_data
                )

                if reminder_id:
                    target_user = await self.bot.fetch_user(target_user_id)
                    time_desc = time_str
                    response = f"✅ Reminder set for {target_user.display_name if target_user else 'user'} in {time_desc}: *{reminder_text}*"

                    if auto_action_enabled:
                        response += f"\n⚡ **Auto-action enabled:** {auto_action_type} (executed if no mod responds within 5 minutes)"

                    await ctx.send(response)
                else:
                    await ctx.send("❌ Failed to save reminder. Please try again.")
                return

            # Try natural language parsing for other formats
            try:
                from bot.tasks.reminders import format_reminder_time, parse_natural_reminder, validate_reminder_text

                parsed = parse_natural_reminder(content, ctx.author.id)

                if not parsed["success"]:
                    # Better error message with examples
                    await ctx.send(
                        "❌ **Unable to parse reminder.** Try:\n"
                        "• `!remind @user 2m Stand up` (traditional)\n"
                        "• `remind me in 30 minutes to check stream`\n"
                        "• `set reminder for 7pm` (asks for message)\n\n"
                        "**Time formats:** 2m, 1h, 30s, 1d, 'in 5 minutes', 'at 7pm'"
                    )
                    return

                if not validate_reminder_text(parsed["reminder_text"]):
                    # Ask for reminder message if missing
                    if not parsed["reminder_text"].strip():
                        formatted_time = format_reminder_time(
                            parsed["scheduled_time"])
                        await ctx.send(f"⏰ Reminder scheduled for {formatted_time}. What should I remind you about?")
                        return
                    else:
                        await ctx.send("❌ Reminder message is too short or invalid. Please provide a meaningful reminder.")
                        return

                # Add reminder to database (natural language format - always for
                # self)
                reminder_id = database.add_reminder(
                    user_id=ctx.author.id,
                    reminder_text=parsed["reminder_text"],
                    scheduled_time=parsed["scheduled_time"],
                    delivery_channel_id=ctx.channel.id,
                    delivery_type="channel"
                )

                if reminder_id:
                    formatted_time = format_reminder_time(parsed["scheduled_time"])
                    await ctx.send(f"✅ Reminder set for {formatted_time}: *{parsed['reminder_text']}*")
                else:
                    await ctx.send("❌ Failed to save reminder. Please try again.")

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
                    reminders = database.get_pending_reminders_for_user(user.id)
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


def setup(bot):
    """Add the RemindersCommands cog to the bot"""
    bot.add_cog(RemindersCommands(bot))
