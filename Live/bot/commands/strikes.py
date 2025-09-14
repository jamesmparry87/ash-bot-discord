"""
Strike management commands for Ash Bot
Handles user strike tracking, viewing, and administration
"""

from typing import Optional

import discord
from discord.ext import commands

from ..config import JONESY_USER_ID
from ..database import get_database

# Get database instance
db = get_database() # type: ignore


class StrikesCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_db(self):
        """Get database instance with error handling"""
        if db is None:
            raise RuntimeError("Database not available")
        return db

    @commands.command(name="strikes")
    @commands.has_permissions(manage_messages=True)
    async def get_strikes(self, ctx, member: discord.Member):
        """Get strike count for a specific user (moderators only)"""
        try:
            database = self._get_db()
            count = database.get_user_strikes(member.id)
        except RuntimeError:
            await ctx.send("❌ Database unavailable")
            return
        await ctx.send(f"🔍 {member.display_name} has {count} strike(s).")

    @commands.command(name="resetstrikes")
    @commands.has_permissions(manage_messages=True)
    async def reset_strikes(self, ctx, member: discord.Member):
        """Reset strikes for a specific user (moderators only)"""
        try:
            database = self._get_db()
            database.set_user_strikes(member.id, 0)

            # Never @mention Captain Jonesy, just use her name
            if str(member.id) == str(JONESY_USER_ID):
                await ctx.send(f"✅ Strikes for Captain Jonesy have been reset.")
            else:
                await ctx.send(f"✅ Strikes for {member.display_name} have been reset.")
        except RuntimeError:
            await ctx.send("❌ Database unavailable")

    @commands.command(name="allstrikes")
    @commands.has_permissions(manage_messages=True)
    async def all_strikes(self, ctx):
        """List all users with strikes (moderators only)"""
        try:
            database = self._get_db()
            strikes_data = database.get_all_strikes()

            if not strikes_data:
                await ctx.send("📋 No strikes recorded.")
                return

            report = "📋 **Strike Report:**\n"
            for user_id, count in strikes_data.items():
                if count > 0:
                    try:
                        user = await self.bot.fetch_user(user_id)
                        report += f"• **{user.name}**: {count} strike{'s' if count != 1 else ''}\n"
                    except Exception:
                        report += f"• Unknown User ({user_id}): {count}\n"

            if report.strip() == "📋 **Strike Report:**":
                report += "No users currently have strikes."

            await ctx.send(report[:2000])
        except RuntimeError:
            await ctx.send("❌ Database unavailable")

    @commands.command(name="addteststrikes")
    @commands.has_permissions(manage_messages=True)
    async def add_test_strikes(self, ctx):
        """Manually add known strike data for testing (moderators only)"""
        try:
            database = self._get_db()
            await ctx.send("🔄 **Adding test strike data...**")
            # Add test users with strikes
            user_strikes = {
                710570041220923402: 1,
                906475895907291156: 1
            }

            success_count = 0
            for user_id, strike_count in user_strikes.items():
                try:
                    database.set_user_strikes(user_id, strike_count)
                    success_count += 1
                    await ctx.send(f"✅ **Added {strike_count} strike(s) for user {user_id}**")
                except Exception as e:
                    await ctx.send(f"❌ **Failed to add strikes for user {user_id}:** {str(e)}")

            await ctx.send(f"📊 **Summary:** Successfully added strikes for {success_count} users")

            # Test read-back
            await ctx.send("🔍 **Testing read-back...**")
            for user_id in user_strikes.keys():
                try:
                    strikes = database.get_user_strikes(user_id)
                    await ctx.send(f"📖 **User {user_id} now has:** {strikes} strikes")
                except Exception as e:
                    await ctx.send(f"❌ **Failed to read strikes for user {user_id}:** {str(e)}")

            # Test bulk query
            bulk_results = database.get_all_strikes()
            total_strikes = sum(bulk_results.values())
            await ctx.send(f"📊 **Bulk query now returns:** {bulk_results}")
            await ctx.send(f"🧮 **Total strikes:** {total_strikes}")

        except Exception as e:
            await ctx.send(f"❌ **Test error:** {str(e)}")


def setup(bot):
    """Add the StrikesCommands cog to the bot"""
    bot.add_cog(StrikesCommands(bot))
