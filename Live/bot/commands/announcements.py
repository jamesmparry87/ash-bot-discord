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

            # Send to announcement channel
            announcement_channel = self.bot.get_channel(
                ANNOUNCEMENTS_CHANNEL_ID)
            if announcement_channel:
                await announcement_channel.send(embed=embed)
                await ctx.send(f"✅ **Announcement posted** to {announcement_channel.mention}.")

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


def setup(bot):
    """Add the AnnouncementsCommands cog to the bot"""
    bot.add_cog(AnnouncementsCommands(bot))
