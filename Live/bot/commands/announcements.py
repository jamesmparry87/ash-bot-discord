"""
Announcement commands for Ash Bot
Handles server-wide announcements and emergency alerts
"""

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..config import ANNOUNCEMENTS_CHANNEL_ID, JAM_USER_ID, JONESY_USER_ID
from ..database_module import get_database

# Get database instance
db = get_database()


class AnnouncementsCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_db(self):
        """Get database instance with error handling"""
        if db is None:
            raise RuntimeError("Database not available")
        return db

    @commands.command(name="announce")
    async def make_announcement(self, ctx, *, announcement_text: str | None = None):
        """Create server-wide announcement (Captain Jonesy and Sir Decent Jam only)"""
        # Strict access control - only Captain Jonesy and Sir Decent Jam
        if ctx.author.id not in [JONESY_USER_ID, JAM_USER_ID]:
            return  # Silent ignore for unauthorized users

        try:
            if not announcement_text:
                help_text = (
                    "**Announcement System Access Confirmed**\n\n"
                    "**Usage:** `!announce <message>`\n\n"
                    "**Features:**\n"
                    "• Cross-posted to announcement channels\n"
                    "• Special embed formatting with authority indicators\n"
                    "• Database logging for audit trail\n\n"
                    "**Also Available:**\n"
                    "• `!scheduleannouncement <time> <message>` - Schedule for later\n"
                    "• `!emergency <message>` - Emergency @everyone alert")
                await ctx.send(help_text)
                return

            # Create announcement embed
            embed = discord.Embed(
                title="📢 Server Announcement",
                description=announcement_text,
                color=0x00ff00,  # Green for normal announcements
                timestamp=datetime.now(ZoneInfo("Europe/London"))
            )

            # Add authority indicator
            if ctx.author.id == JONESY_USER_ID:
                embed.set_footer(
                    text="Announced by Captain Jonesy • Server Owner",
                    icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)
            elif ctx.author.id == JAM_USER_ID:
                embed.set_footer(
                    text="Announced by Sir Decent Jam • Bot Creator",
                    icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

            # Send to announcement channel with @everyone ping
            announcement_channel = self.bot.get_channel(
                ANNOUNCEMENTS_CHANNEL_ID)
            if announcement_channel:
                await announcement_channel.send("@everyone", embed=embed)
                await ctx.send(f"✅ **Announcement posted** with @everyone ping to {announcement_channel.mention}.")

            else:
                await ctx.send("❌ **Announcement channel not found.** Please check channel configuration.")

            # Log to database if available
            try:
                database = self._get_db()
                if hasattr(database, 'log_announcement'):
                    database.log_announcement(
                        ctx.author.id,
                        announcement_text,
                        "announcement")
            except BaseException:
                pass  # Non-critical logging failure

        except Exception as e:
            print(f"❌ Error in announce command: {e}")
            await ctx.send("❌ **System error occurred** while posting announcement.")

    @commands.command(name="emergency")
    async def emergency_announcement(self, ctx, *, message: str | None = None):
        """Create emergency announcement with @everyone ping (Captain Jonesy and Sir Decent Jam only)"""
        # Strict access control
        if ctx.author.id not in [JONESY_USER_ID, JAM_USER_ID]:
            return  # Silent ignore

        try:
            if not message:
                await ctx.send("❌ **Emergency message required.** Usage: `!emergency <critical message>`\n\n⚠️ This will ping @everyone - use responsibly.")
                return

            # Create emergency embed with red color
            embed = discord.Embed(
                title="🚨 EMERGENCY ANNOUNCEMENT",
                description=message,
                color=0xff0000,  # Red for emergency
                timestamp=datetime.now(ZoneInfo("Europe/London"))
            )

            # Add authority indicator
            if ctx.author.id == JONESY_USER_ID:
                embed.set_footer(
                    text="Emergency Alert by Captain Jonesy • Server Owner",
                    icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)
            elif ctx.author.id == JAM_USER_ID:
                embed.set_footer(
                    text="Emergency Alert by Sir Decent Jam • Bot Creator",
                    icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

            # Send to announcement channel with @everyone ping
            announcement_channel = self.bot.get_channel(
                ANNOUNCEMENTS_CHANNEL_ID)
            if announcement_channel:
                await announcement_channel.send("@everyone", embed=embed)
                await ctx.send(f"🚨 **Emergency announcement posted** with @everyone ping to {announcement_channel.mention}.")
            else:
                await ctx.send("❌ **Announcement channel not found.** Please check channel configuration.")

            # Log to database
            try:
                database = self._get_db()
                if hasattr(database, 'log_announcement'):
                    database.log_announcement(
                        ctx.author.id, message, "emergency")
            except BaseException:
                pass  # Non-critical logging failure

        except Exception as e:
            print(f"❌ Error in emergency command: {e}")
            await ctx.send("❌ **System error occurred** while posting emergency announcement.")

    @commands.command(name="announceupdate")
    async def start_announcement_update(self, ctx):
        """Start interactive announcement creation process (Captain Jonesy and Sir Decent Jam only)"""
        # Import conversation handler
        from ..handlers.conversation_handler import start_announcement_conversation
        await start_announcement_conversation(ctx)

    @commands.command(name="createannouncement")
    async def create_announcement(self, ctx):
        """Alternative command to start announcement creation (Captain Jonesy and Sir Decent Jam only)"""
        # Import conversation handler
        from ..handlers.conversation_handler import start_announcement_conversation
        await start_announcement_conversation(ctx)

    @commands.command(name="generatemonday")
    @commands.has_permissions(administrator=True)
    async def generate_monday_manual(self, ctx):
        """Manually trigger Monday content sync and approval workflow (Admin only)"""
        try:
            from ..tasks.scheduled import perform_full_content_sync
            from ..handlers.conversation_handler import start_weekly_announcement_approval

            uk_now = datetime.now(ZoneInfo("Europe/London"))
            
            await ctx.send("🔄 **Monday Content Sync Initiated...**\n\nAnalyzing new YouTube/Twitch content from the past week. This may take a moment...")

            database = self._get_db()
            
            # Get the last sync timestamp
            start_sync_time = database.get_latest_game_update_timestamp()
            if not start_sync_time:
                await ctx.send("❌ **Error:** Could not retrieve last update timestamp from database.")
                return

            # Perform the content sync
            try:
                analysis_results = await perform_full_content_sync(start_sync_time)
            except Exception as sync_error:
                await ctx.send(f"❌ **Content Sync Failed**\n\n**Error:** {str(sync_error)[:200]}\n\n*YouTube/Twitch integration may be experiencing issues.*")
                return

            # Check if we found new content
            if analysis_results.get("status") == "no_new_content":
                await ctx.send("ℹ️ **No New Content Found**\n\nNo new YouTube/Twitch content was detected since the last sync. No Monday message will be generated.")
                return

            # Generate the Monday debrief content
            debrief = (
                f"🌅 **Monday Morning Protocol Initiated**\n\n"
                f"Analysis of the previous 168-hour operational cycle is complete. **{analysis_results.get('new_content_count', 0)}** new transmissions were logged, "
                f"accumulating **{analysis_results.get('new_hours', 0)} hours** of new mission data and **{analysis_results.get('new_views', 0):,}** viewer engagements.")
            
            top_video = analysis_results.get("top_video")
            if top_video:
                debrief += f"\n\nMaximum engagement was recorded on the transmission titled **'{top_video['title']}'**."
                if "finale" in top_video['title'].lower() or "ending" in top_video['title'].lower():
                    debrief += " This concludes all active mission parameters for this series."

            # Create announcement record in database
            announcement_id = database.create_weekly_announcement('monday', debrief, analysis_results)

            if not announcement_id:
                await ctx.send("❌ **Database Error**\n\nFailed to create announcement record. Please check database connectivity.")
                return

            # Send status update
            await ctx.send(
                f"✅ **Monday Analysis Complete**\n\n"
                f"• **New Content:** {analysis_results.get('new_content_count', 0)} videos/VODs\n"
                f"• **Total Duration:** {analysis_results.get('new_hours', 0)} hours\n"
                f"• **Total Views:** {analysis_results.get('new_views', 0):,}\n\n"
                f"📬 **Approval request sent to your DMs.**\n"
                f"*Review and approve the message before it can be posted.*"
            )

            # Start the approval workflow
            await start_weekly_announcement_approval(announcement_id, debrief, 'monday')

        except RuntimeError as db_error:
            await ctx.send(f"❌ **Database Error:** {str(db_error)}")
        except Exception as e:
            print(f"❌ Error in generatemonday command: {e}")
            await ctx.send(f"❌ **System Error**\n\nAn unexpected error occurred during Monday content sync: {str(e)[:200]}")

    @commands.command(name="generatefriday")
    @commands.has_permissions(administrator=True)
    async def generate_friday_manual(self, ctx):
        """Manually trigger Friday community analysis and approval workflow (Admin only)"""
        try:
            import discord
            from datetime import timedelta
            from ..handlers.conversation_handler import start_weekly_announcement_approval
            from ..config import CHIT_CHAT_CHANNEL_ID, GAME_RECOMMENDATION_CHANNEL_ID, JONESY_USER_ID

            uk_now = datetime.now(ZoneInfo("Europe/London"))
            
            await ctx.send("🔄 **Friday Community Analysis Initiated...**\n\nAnalyzing community activity from the past week. This may take a moment...")

            database = self._get_db()

            # Define channels to scrape
            public_channel_ids = [CHIT_CHAT_CHANNEL_ID, GAME_RECOMMENDATION_CHANNEL_ID]
            
            all_messages = []
            seven_days_ago = uk_now - timedelta(days=7)

            # Scrape messages
            try:
                for channel_id in public_channel_ids:
                    channel = self.bot.get_channel(channel_id)
                    if isinstance(channel, discord.TextChannel):
                        async for message in channel.history(limit=1000, after=seven_days_ago):
                            if not message.author.bot and message.content:
                                all_messages.append(message)
            except Exception as scrape_error:
                await ctx.send(f"❌ **Message Scraping Failed**\n\n**Error:** {str(scrape_error)[:200]}\n\n*Failed to access community channels.*")
                return

            if not all_messages:
                await ctx.send("ℹ️ **No Community Activity Found**\n\nNo community messages were found in the past week. No Friday message will be generated.")
                return

            # Analyze and create moment modules
            analysis_modules = []
            
            # Module A: Jonesy's Most Engaging Message
            jonesy_messages = [m for m in all_messages if m.author.id == JONESY_USER_ID]
            if jonesy_messages:
                jonesy_messages.sort(key=lambda m: len(m.reactions), reverse=True)
                top_jonesy_message = jonesy_messages[0]
                if len(top_jonesy_message.reactions) > 2:
                    # Extract JSON-serializable data from Message object
                    message_data = {
                        "content": top_jonesy_message.content,
                        "author_id": top_jonesy_message.author.id,
                        "author_name": top_jonesy_message.author.name,
                        "reaction_count": len(top_jonesy_message.reactions),
                        "message_id": top_jonesy_message.id,
                        "channel_id": top_jonesy_message.channel.id,
                        "created_at": top_jonesy_message.created_at.isoformat() if top_jonesy_message.created_at else None
                    }
                    analysis_modules.append({
                        "type": "jonesy_message",
                        "data": message_data,
                        "content": f"Analysis of command personnel communications indicates a high engagement rate with the transmission: \"{top_jonesy_message.content}\". This may represent an emerging crew catchphrase."
                    })

            # Module B: Trivia Tuesday Recap
            trivia_stats = database.get_trivia_participant_stats_for_week()
            if trivia_stats.get("status") == "success":
                winner_id = trivia_stats.get("winner_id")
                notable_id = trivia_stats.get("notable_participant_id")
                if winner_id:
                    recap = f"Review of the weekly intelligence assessment confirms <@{winner_id}> demonstrated optimal response efficiency."
                    if notable_id:
                        recap += f" Conversely, User <@{notable_id}> submitted multiple analyses that were... suboptimal. Recalibration is recommended."
                    analysis_modules.append({
                        "type": "trivia_recap",
                        "data": trivia_stats,
                        "content": recap
                    })

            if not analysis_modules:
                await ctx.send("ℹ️ **Insufficient Notable Moments**\n\nAnalysis found no notable community moments this week. No Friday message will be generated.")
                return

            # Select a random moment to feature
            import random
            chosen_moment = random.choice(analysis_modules)

            # Generate Friday debrief
            debrief = (
                f"📅 **Friday Protocol Assessment**\n\n"
                f"Good morning, personnel. My analysis of the past week's crew engagement is complete.\n\n"
                f"{chosen_moment['content']}\n\n"
                f"Weekend operational pause is now in effect."
            )

            # Create announcement record
            analysis_cache = {"modules": analysis_modules}
            announcement_id = database.create_weekly_announcement('friday', debrief, analysis_cache)

            if not announcement_id:
                await ctx.send("❌ **Database Error**\n\nFailed to create announcement record. Please check database connectivity.")
                return

            # Send status update
            await ctx.send(
                f"✅ **Friday Analysis Complete**\n\n"
                f"• **Messages Analyzed:** {len(all_messages)}\n"
                f"• **Notable Moments Found:** {len(analysis_modules)}\n"
                f"• **Selected Module:** {chosen_moment['type'].replace('_', ' ').title()}\n\n"
                f"📬 **Approval request sent to your DMs.**\n"
                f"*Review and approve the message before it can be posted.*"
            )

            # Start the approval workflow
            await start_weekly_announcement_approval(announcement_id, debrief, 'friday')

        except RuntimeError as db_error:
            await ctx.send(f"❌ **Database Error:** {str(db_error)}")
        except Exception as e:
            print(f"❌ Error in generatefriday command: {e}")
            await ctx.send(f"❌ **System Error**\n\nAn unexpected error occurred during Friday community analysis: {str(e)[:200]}")


def setup(bot):
    """Add the AnnouncementsCommands cog to the bot"""
    bot.add_cog(AnnouncementsCommands(bot))
