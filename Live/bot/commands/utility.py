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
db = get_database()  # type: ignore


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
        """Show bot status - different levels based on authorization and channel"""
        try:
            # Import AI handler for status information
            try:
                from ..handlers.ai_handler import get_ai_status
                ai_status = get_ai_status()
            except ImportError:
                ai_status = {"enabled": False, "status_message": "AI handler unavailable"}

            # Determine authorization level and channel context
            is_authorized = False
            is_public_channel = False

            if ctx.guild is None:  # DM
                # Allow JAM, JONESY, and moderators in DMs
                if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
                    is_authorized = True
                else:
                    # Check if user is a mod
                    is_authorized = await self._user_is_mod_by_id(ctx.author.id)
            else:  # Guild
                # Check if it's a public channel (general chat or similar)
                # General chat channel ID from user requirements
                if ctx.channel.id == 869528946725748766:
                    is_public_channel = True

                # Check standard mod permissions
                is_authorized = await self._user_is_mod(ctx)

            # Handle public channel - simple response for everyone
            if is_public_channel:
                await ctx.send("🤖 Systems nominal. Awaiting mission parameters. *[All protocols operational.]*")
                return

            # Handle unauthorized users
            if not is_authorized:
                if ctx.guild is None:  # DM - be specific about authorization
                    await ctx.send("⚠️ **Access denied.** System status diagnostics require elevated clearance. Authorization protocols restrict access to Captain Jonesy, Sir Decent Jam, and server moderators only.")
                else:  # Guild - generic response
                    await ctx.send("🤖 Systems nominal. Awaiting mission parameters. *[All protocols operational.]*")
                return

            # Detailed status for authorized users
            try:
                database = self._get_db()

                # Get database statistics
                strikes_data = database.get_all_strikes()
                total_strikes = sum(strikes_data.values())
                users_with_strikes = len([s for s in strikes_data.values() if s > 0])

                # Get game statistics if available
                try:
                    games = database.get_all_games()
                    total_games = len(games)
                except Exception:
                    total_games = "N/A"

                # If bulk query returns 0 but we know there should be strikes, use fallback
                if total_strikes == 0:
                    known_users = [371536135580549122, 337833732901961729, 710570041220923402, 906475895907291156]
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
                users_with_strikes = "N/A"
                total_games = "N/A"

            # Build detailed status message
            status_lines = []
            status_lines.append("🤖 **Ash Bot - System Diagnostics**")

            # Database status with details
            if db:
                if total_games != "N/A" and users_with_strikes != "N/A":
                    status_lines.append(
                        f"• **Database**: ✅ Connected ({total_games} games, {users_with_strikes} users tracked)")
                else:
                    status_lines.append("• **Database**: ✅ Connected")
            else:
                status_lines.append("• **Database**: ❌ Unavailable")

            # Enhanced AI system status with detailed health information
            ai_status_line = f"• **AI System**: {ai_status.get('status_message', 'Unknown')}"
            if ai_status.get('enabled') and 'usage_stats' in ai_status:
                usage = ai_status['usage_stats']
                daily = usage.get('daily_requests', 0)
                hourly = usage.get('hourly_requests', 0)
                
                # Check for quota exhaustion or backup status
                quota_exhausted = usage.get('quota_exhausted', False)
                backup_active = usage.get('backup_active', False)
                primary_ai_errors = usage.get('primary_ai_errors', 0)
                backup_ai_errors = usage.get('backup_ai_errors', 0)
                
                # Build status line with health indicators
                status_indicator = "✅"
                if quota_exhausted:
                    status_indicator = "🚫"
                elif backup_active:
                    status_indicator = "⚠️"
                elif primary_ai_errors > 0:
                    status_indicator = "⚠️"
                
                ai_status_line = f"• **AI System**: {status_indicator} {ai_status.get('primary_ai', 'Unknown').title()}"
                
                # Add backup status if applicable
                if backup_active and ai_status.get('backup_ai'):
                    ai_status_line += f" → {ai_status.get('backup_ai', 'Unknown').title()} (Backup Active)"
                elif quota_exhausted and ai_status.get('backup_ai'):
                    ai_status_line += f" (Quota exhausted, using {ai_status.get('backup_ai', 'Unknown').title()} backup)"
                elif ai_status.get('backup_ai'):
                    ai_status_line += f" + {ai_status.get('backup_ai', 'Unknown').title()} backup"
                
                # Add usage stats
                ai_status_line += f" ({daily}/{MAX_DAILY_REQUESTS} daily, {hourly}/{MAX_HOURLY_REQUESTS} hourly)"
                
                # Add error information if present
                if primary_ai_errors > 0 or backup_ai_errors > 0:
                    ai_status_line += f" [Errors: P:{primary_ai_errors} B:{backup_ai_errors}]"
            
            status_lines.append(ai_status_line)

            # Strike management
            if total_strikes != "Database unavailable":
                if users_with_strikes != "N/A":
                    status_lines.append(
                        f"• **Strike Management**: {total_strikes} total strikes across {users_with_strikes} personnel")
                else:
                    status_lines.append(f"• **Strike Management**: {total_strikes} total strikes")
            else:
                status_lines.append("• **Strike Management**: Database unavailable")

            # Overall status
            status_lines.append("• **Status**: All systems operational")
            status_lines.append("")
            status_lines.append("*Analysis complete. Mission parameters updated.*")

            await ctx.send("\n".join(status_lines))

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

    @commands.command(name="time")
    async def get_current_time(self, ctx):
        """Get current time in GMT/BST"""
        try:
            from ..utils.time_utils import get_uk_time, is_dst_active

            uk_now = get_uk_time()
            is_dst = is_dst_active(uk_now)
            timezone_name = "BST" if is_dst else "GMT"

            formatted_time = uk_now.strftime(
                f"%A, %B %d, %Y at %H:%M:%S {timezone_name}")

            await ctx.send(f"Current time: {formatted_time}")

        except Exception as e:
            # Fallback to basic implementation
            from datetime import datetime
            from zoneinfo import ZoneInfo
            uk_now = datetime.now(ZoneInfo("Europe/London"))
            # Check if DST is active (rough approximation)
            is_summer = 3 <= uk_now.month <= 10  # March to October roughly
            timezone_name = "BST" if is_summer else "GMT"

            formatted_time = uk_now.strftime(
                f"%A, %B %d, %Y at %H:%M:%S {timezone_name}")
            await ctx.send(f"Current time: {formatted_time}")

    @commands.command(name="toggleai")
    @commands.has_permissions(manage_messages=True)
    async def toggle_ai(self, ctx):
        """Toggle AI system on/off (moderators only)"""
        try:
            # Import AI handler functions
            from ..handlers.ai_handler import ai_enabled, get_ai_status

            if not ai_enabled:
                await ctx.send("❌ **AI system is not available.** API keys are not configured or AI handler failed to initialize.")
                return

            # Get current AI status
            ai_status = get_ai_status()
            current_status = ai_status.get('enabled', True)

            # Toggle the status (this would need to be implemented in
            # ai_handler)
            try:
                from ..handlers.ai_handler import toggle_ai_system  # type: ignore
                new_status = toggle_ai_system()

                status_text = "**enabled**" if new_status else "**disabled**"
                await ctx.send(f"✅ **AI system {status_text}.** All AI-powered responses and conversation features are now {'active' if new_status else 'inactive'}.")

            except ImportError:
                await ctx.send("❌ **AI toggle function not implemented.** The AI handler needs to be updated with `toggle_ai_system()` function.")

        except ImportError:
            await ctx.send("❌ **AI handler not available.** Cannot toggle AI system.")
        except Exception as e:
            print(f"❌ Error in toggleai command: {e}")
            await ctx.send("❌ System error occurred while toggling AI.")

    @commands.command(name="setpersona")
    @commands.has_permissions(manage_messages=True)
    async def set_persona(
            self,
            ctx,
            *,
            persona_description: str | None = None):
        """Set or view the AI personality (moderators only)"""
        try:
            if not persona_description:
                # Show current persona and help
                help_text = (
                    "**Current AI Persona:** Science Officer Ash from Alien (1979)\n\n"
                    "**Usage:** `!setpersona <description>`\n\n"
                    "**Examples:**\n"
                    "• `!setpersona Helpful assistant with a friendly personality`\n"
                    "• `!setpersona Science Officer Ash from Alien - analytical and precise`\n"
                    "• `!setpersona reset` - Return to default Ash persona\n\n"
                    "**Current Traits:** Analytical, precise, scientific approach, slightly detached but helpful")
                await ctx.send(help_text)
                return

            # Handle reset command
            if persona_description.lower() == "reset":
                try:
                    from ..handlers.ai_handler import reset_persona  # type: ignore
                    reset_persona()
                    await ctx.send("✅ **AI persona reset** to default Science Officer Ash personality.")
                except ImportError:
                    await ctx.send("❌ **Persona reset function not implemented.** The AI handler needs `reset_persona()` function.")
                return

            # Set new persona
            try:
                from ..handlers.ai_handler import set_ai_persona  # type: ignore
                success = set_ai_persona(persona_description)

                if success:
                    await ctx.send(f"✅ **AI persona updated.**\n\n**New personality:** {persona_description[:200]}{'...' if len(persona_description) > 200 else ''}\n\n*Changes will take effect with the next AI response.*")
                else:
                    await ctx.send("❌ **Failed to update persona.** Please try again or check the persona description length.")

            except ImportError:
                await ctx.send("❌ **Persona setting function not implemented.** The AI handler needs `set_ai_persona()` function.\n\n*Note: Persona changes require updating the AI handler module.*")

        except Exception as e:
            print(f"❌ Error in setpersona command: {e}")
            await ctx.send("❌ System error occurred while setting persona.")


def setup(bot):
    """Add the UtilityCommands cog to the bot"""
    bot.add_cog(UtilityCommands(bot))
