"""
Utility commands for Ash Bot
Handles system status, debugging, and administrative utilities
"""

import os
import platform
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..config import JAM_USER_ID, JONESY_USER_ID, MAX_DAILY_REQUESTS, MAX_HOURLY_REQUESTS, MOD_ALERT_CHANNEL_ID
from ..database import get_database

# Get database instance
db = get_database() # type: ignore


class UtilityCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_db(self):
        """Get database instance with error handling"""
        if db is None:
            raise RuntimeError("Database not available")
        return db

    async def _user_is_mod(self, message: discord.Message) -> bool:
        """Check if user has moderator permissions"""
        if not message.guild:
            return False  # No mod permissions in DMs

        # Ensure we have a Member object (not just User)
        if not isinstance(message.author, discord.Member):
            return False

        member = message.author
        perms = member.guild_permissions
        return perms.manage_messages

    async def _user_is_mod_by_id(self, user_id: int) -> bool:
        """Check if user ID belongs to a moderator (for DM checks)"""
        guild = self.bot.get_guild(869525857562161182)  # GUILD_ID
        if not guild:
            return False

        try:
            member = await guild.fetch_member(user_id)
            return member.guild_permissions.manage_messages
        except (discord.NotFound, discord.Forbidden):
            return False

    @commands.command(name="test")
    async def test_command(self, ctx):
        """Basic test command to verify bot functionality"""
        await ctx.send("🧾 Systems operational. Science Officer Ash reporting for duty.")

    @commands.command(name="ashstatus")
    async def ash_status(self, ctx):
        """Show bot status - works in DMs for authorized users and in guilds for mods"""
        try:
            # Custom permission checking that works in both DMs and guilds
            is_authorized = False

            if ctx.guild is None:  # DM
                # Allow JAM, JONESY, and moderators in DMs
                if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
                    is_authorized = True
                else:
                    # Check if user is a mod
                    is_authorized = await self._user_is_mod_by_id(ctx.author.id)
            else:  # Guild
                # Check standard mod permissions
                is_authorized = await self._user_is_mod(ctx)

            # The generic response should only be shown to unauthorized users in guilds
            # In DMs, unauthorized users should get a clearer message
            if not is_authorized:
                if ctx.guild is None:  # DM - be more specific about authorization
                    await ctx.send("⚠️ **Access denied.** System status diagnostics require elevated clearance. Authorization protocols restrict access to Captain Jonesy, Sir Decent Jam, and server moderators only.")
                else:  # Guild - use the generic response
                    await ctx.send("Systems nominal, Sir Decent Jam. Awaiting Captain Jonesy's commands.")
                return

            try:
                database = self._get_db()
                # Use individual queries as fallback if bulk query fails
                strikes_data = database.get_all_strikes()
                total_strikes = sum(strikes_data.values())

                # If bulk query returns 0 but we know there should be strikes,
                # use individual queries
                if total_strikes == 0:
                    # Known user IDs from the JSON file (fallback method)
                    known_users = [
                        371536135580549122,
                        337833732901961729,
                        710570041220923402,
                        906475895907291156]
                    individual_total = 0
                    for user_id in known_users:
                        try:
                            strikes = database.get_user_strikes(user_id)
                            individual_total += strikes
                        except Exception:
                            pass

                    if individual_total > 0:
                        total_strikes = individual_total

            except RuntimeError:
                total_strikes = "Database unavailable"

            # Get current Pacific Time for display
            pt_now = datetime.now(ZoneInfo("US/Pacific"))
            pt_time_str = pt_now.strftime("%Y-%m-%d %H:%M:%S PT")

            # Basic status information
            await ctx.send(
                f"🤖 Ash at your service.\n"
                f"Database: {'✅ Connected' if db else '❌ Unavailable'}\n"
                f"Total strikes: {total_strikes}\n"
                f"Current PT Time: {pt_time_str}\n"
                f"System: {platform.system()}"
            )

        except Exception as e:
            await ctx.send(f"❌ **System diagnostic error:** {str(e)}")

    @commands.command(name="errorcheck")
    async def error_check(self, ctx):
        """Test error message display"""
        error_message = (
            "*System malfunction detected. Unable to process query.*\nhttps://c.tenor.com/GaORbymfFqQAAAAd/tenor.gif"
        )
        await ctx.send(error_message)

    @commands.command(name="busycheck")
    async def busy_check(self, ctx):
        """Test busy message display"""
        busy_message = (
            "*My apologies, I am currently engaged in a critical diagnostic procedure. I will re-evaluate your request upon the completion of this vital task.*\nhttps://alien-covenant.com/aliencovenant_uploads/giphy22.gif"
        )
        await ctx.send(busy_message)

    @commands.command(name="timecheck")
    async def time_check(self, ctx):
        """Comprehensive time diagnostic command to debug time-related issues"""
        try:
            # Check if user has permissions (allow in DMs for authorized users,
            # or mods in guilds)
            is_authorized = False

            if ctx.guild is None:  # DM
                # Allow JAM, JONESY, and moderators in DMs
                if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
                    is_authorized = True
                else:
                    # Check if user is a mod
                    is_authorized = await self._user_is_mod_by_id(ctx.author.id)
            else:  # Guild
                # Check standard mod permissions
                is_authorized = await self._user_is_mod(ctx)

            if not is_authorized:
                await ctx.send("⚠️ **Access denied.** Time diagnostic protocols require elevated clearance.")
                return

            import time
            from datetime import timezone

            # Get various time representations with more precise timing
            uk_now = datetime.now(ZoneInfo("Europe/London"))
            utc_now = datetime.now(timezone.utc)
            pt_now = datetime.now(ZoneInfo("US/Pacific"))
            system_time = datetime.now()

            # Get server system time info
            system_timezone = str(system_time.astimezone().tzinfo)

            # Test database time with multiple queries for comparison
            db_time = None
            db_timezone = None
            db_utc_time = None
            try:
                database = self._get_db()
                conn = database.get_connection()
                if conn:
                    with conn.cursor() as cur:
                        # Get database time in multiple formats
                        cur.execute("""
                            SELECT
                                NOW() as db_time,
                                timezone('UTC', NOW()) as db_utc,
                                CURRENT_SETTING('timezone') as db_timezone,
                                EXTRACT(epoch FROM NOW()) as db_unix_timestamp
                        """)
                        result = cur.fetchone()
                        if result:
                            db_time = result[0]
                            db_utc_time = result[1]
                            db_timezone = result[2]
                            db_unix_timestamp = float(
                                result[3]) if result[3] else None
            except Exception as e:
                db_time = f"Error: {str(e)}"

            # Calculate time differences and identify potential issues
            time_diffs = {}

            # UK vs UTC should be 0 or 1 hour (depending on DST)
            uk_utc_diff = (uk_now - utc_now).total_seconds()
            time_diffs["uk_vs_utc"] = uk_utc_diff

            # System vs UK time difference
            system_uk_diff = (
                system_time.astimezone(
                    ZoneInfo("Europe/London")) -
                uk_now).total_seconds()
            time_diffs["system_vs_uk"] = system_uk_diff

            # Database vs UK time difference (if available)
            if db_time and isinstance(db_time, datetime):
                if db_time.tzinfo is None:
                    # Assume database time is UTC if no timezone
                    db_time_uk = db_time.replace(
                        tzinfo=timezone.utc).astimezone(
                        ZoneInfo("Europe/London"))
                else:
                    db_time_uk = db_time.astimezone(ZoneInfo("Europe/London"))

                db_uk_diff = (db_time_uk - uk_now).total_seconds()
                time_diffs["db_vs_uk"] = db_uk_diff

            time_report = (
                f"🕒 **COMPREHENSIVE TIME DIAGNOSTIC REPORT**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"**Bot Time References:**\n"
                f"• **UK Time (Bot Primary):** {uk_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"• **UTC Time:** {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"• **Pacific Time (AI Limits):** {pt_now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                f"• **System Local Time:** {system_time.strftime('%Y-%m-%d %H:%M:%S')} ({system_timezone})\n\n"
                f"**Database Time Analysis:**\n"
                f"• **Database NOW():** {db_time}\n"
                f"• **Database Timezone:** {db_timezone}\n"
                f"• **Database UTC:** {db_utc_time}\n\n"
                f"**Time Synchronization Status:**\n"
                f"• **UK vs UTC Offset:** {uk_utc_diff:.0f} seconds {'✅ Normal' if abs(uk_utc_diff) <= 7200 else '⚠️ Abnormal'}\n"
                f"• **System vs UK:** {system_uk_diff:.0f} seconds {'✅ Normal' if abs(system_uk_diff) <= 60 else '⚠️ Drift detected'}\n"
            )

            if "db_vs_uk" in time_diffs:
                time_report += f"• **Database vs UK:** {time_diffs['db_vs_uk']:.0f}s {'✅ Normal' if abs(time_diffs['db_vs_uk']) <= 60 else '⚠️ May have drift'}\n"

            await ctx.send(time_report)

        except Exception as e:
            await ctx.send(f"❌ **Time diagnostic error:** {str(e)}")

    @commands.command(name="dbstats")
    @commands.has_permissions(manage_messages=True)
    async def db_stats(self, ctx):
        """Show database statistics"""
        try:
            database = self._get_db()
            games = database.get_all_games()
            strikes = database.get_all_strikes()

            total_games = len(games)
            total_users_with_strikes = len(
                [s for s in strikes.values() if s > 0])
            total_strikes = sum(strikes.values())

            # Count unique contributors
            contributors = set()
            for game in games:
                if game.get('added_by'):
                    contributors.add(game['added_by'])

            stats_msg = (
                f"📊 **Database Statistics:**\n"
                f"• **Games**: {total_games} recommendations\n"
                f"• **Contributors**: {len(contributors)} unique users\n"
                f"• **Strikes**: {total_strikes} total across {total_users_with_strikes} users\n")

            if contributors:
                top_contributors = {}
                for game in games:
                    contributor = game.get('added_by', '')
                    if contributor:
                        top_contributors[contributor] = top_contributors.get(
                            contributor, 0) + 1

                # Sort by contribution count
                sorted_contributors = sorted(
                    top_contributors.items(), key=lambda x: x[1], reverse=True)

                stats_msg += f"\n**Top Contributors:**\n"
                for i, (contributor, count) in enumerate(
                        sorted_contributors[:5]):
                    stats_msg += f"{i+1}. {contributor}: {count} games\n"

            await ctx.send(stats_msg)

        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            await ctx.send(f"❌ Error retrieving database statistics: {str(e)}")


def setup(bot):
    """Add the UtilityCommands cog to the bot"""
    bot.add_cog(UtilityCommands(bot))
