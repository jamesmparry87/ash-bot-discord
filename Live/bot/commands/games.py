"""
Game recommendation commands for Ash Bot
Handles adding, listing, and managing game recommendations
"""

import discord
from discord.ext import commands
from typing import Optional

from ..database import db, DatabaseManager
from ..config import JAM_USER_ID


class GamesCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_db(self):
        """Get database instance with error handling"""
        if db is None:
            raise RuntimeError("Database not available")
        return db

    async def _add_game(self, ctx, entry: str):
        """Helper for adding games, called by add_game and recommend"""
        try:
            database = self._get_db()
            added = []
            duplicate = []
            
            for part in entry.split(","):
                part = part.strip()
                if not part:
                    continue
                    
                if " - " in part:
                    name, reason = map(str.strip, part.split(" - ", 1))
                else:
                    name, reason = part, "(no reason provided)"
                    
                if not name:
                    continue
                    
                # Typo-tolerant duplicate check (case-insensitive, fuzzy match)
                if database.game_exists(name):
                    duplicate.append(name)
                    continue
                    
                # Exclude username if user is Sir Decent Jam (user ID 337833732901961729)
                if str(ctx.author.id) == str(JAM_USER_ID):
                    added_by = ""
                else:
                    added_by = ctx.author.name

                if database.add_game_recommendation(name, reason, added_by):
                    added.append(name)

            if added:
                RECOMMEND_CHANNEL_ID = 1271568447108550687
                recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
                confirm_msg = f"🧾 Recommendation(s) logged: {', '.join(added)}. Efficiency noted."
                
                # Only send the confirmation in the invoking channel if not the recommendations channel
                if ctx.channel.id != RECOMMEND_CHANNEL_ID:
                    await ctx.send(confirm_msg)
                    
                # Always update the persistent recommendations list and send confirmation in the recommendations channel
                if recommend_channel:
                    await self.post_or_update_recommend_list(ctx, recommend_channel)
                    if ctx.channel.id == RECOMMEND_CHANNEL_ID:
                        await ctx.send(confirm_msg)
                        
            if duplicate:
                await ctx.send(f"⚠️ Submission rejected: {', '.join(duplicate)} already exist(s) in the database. Redundancy is inefficient. Please submit only unique recommendations.")
                
            if not added and not duplicate:
                await ctx.send("⚠️ Submission invalid. Please provide at least one game name. Efficiency is paramount.")
                
        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            await ctx.send(f"❌ Error adding game: {str(e)}")

    async def post_or_update_recommend_list(self, ctx, channel):
        """Post or update the persistent recommendations list"""
        try:
            database = self._get_db()
            games = database.get_all_games()

            # Preamble text for the recommendations channel
            preamble = """# Welcome to the Game Recommendations Channel

Since Jonesy gets games suggested to her all the time, in the YT comments, on Twitch, and in the server, we've decided to get a list going.

A few things to mention up top:

Firstly, a game being on this list is NOT any guarantee it will be played. Jonesy gets to decide, not any of us.

Secondly, this list is in no particular order, so no reading into anything.

Finally, think about what sort of games Jonesy actually plays, either for content or in her own time, when making suggestions.

To add a game, first check the list and then use the /recommend command by typing / followed by "recommend" and the name of the game.

If you want to add any other comments, you can discuss the list in 🎮game-chat"""

            # Create embed
            embed = discord.Embed(
                title="📋 Game Recommendations",
                description="Recommendations for mission enrichment. Review and consider.",
                color=0x2F3136  # Dark gray color matching Ash's aesthetic
            )

            if not games:
                embed.add_field(
                    name="Status",
                    value="No recommendations currently catalogued.",
                    inline=False)
            else:
                # Create one continuous list
                game_lines = []
                for i, game in enumerate(games, 1):
                    # Truncate long names/reasons to fit in embed and apply Title Case
                    name = game['name'][:40] + "..." if len(game['name']) > 40 else game['name']
                    name = name.title()  # Convert to Title Case
                    reason = game["reason"][:60] + "..." if len(game["reason"]) > 60 else game["reason"]

                    # Don't show contributor twice - if reason already contains "Suggested by", don't add "by" again
                    if game['added_by'] and game['added_by'].strip() and not (
                            reason and f"Suggested by {game['added_by']}" in reason):
                        contributor = f" (by {game['added_by']})"
                    else:
                        contributor = ""

                    game_lines.append(f"{i}. **{name}** — \"{reason}\"{contributor}")

                # Join all games into one field value
                field_value = "\n".join(game_lines)

                # If the list is too long for one field, we'll need to split it
                if len(field_value) > 1024:
                    # Split into multiple fields but keep numbering continuous
                    current_field = []
                    current_length = 0

                    for line in game_lines:
                        if current_length + len(line) + 1 > 1000:  # Leave buffer
                            # Add current field - use empty string for field name to eliminate gaps
                            embed.add_field(
                                name="", value="\n".join(current_field), inline=False)
                            # Start new field
                            current_field = [line]
                            current_length = len(line)
                        else:
                            current_field.append(line)
                            current_length += len(line) + 1

                    # Add the final field
                    if current_field:
                        embed.add_field(
                            name="",
                            value="\n".join(current_field),
                            inline=False
                        )
                else:
                    # Single field for all games - use empty string for field name
                    embed.add_field(
                        name="",
                        value=field_value,
                        inline=False
                    )

            # Add footer with stats
            embed.set_footer(
                text=f"Total recommendations: {len(games)} | Last updated")
            embed.timestamp = discord.utils.utcnow()

            # Try to update the existing message if possible
            message_id = database.get_config_value("recommend_list_message_id")
            msg = None
            if message_id:
                try:
                    msg = await channel.fetch_message(int(message_id))
                    await msg.edit(content=preamble, embed=embed)
                except Exception:
                    msg = None
            if not msg:
                msg = await channel.send(content=preamble, embed=embed)
                database.set_config_value("recommend_list_message_id", str(msg.id))
                
        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            await ctx.send(f"❌ Error updating recommendations list: {str(e)}")

    @commands.command(name="addgame")
    async def add_game(self, ctx, *, entry: str):
        """Add a game recommendation"""
        await self._add_game(ctx, entry)

    @commands.command(name="recommend")
    async def recommend(self, ctx, *, entry: str):
        """Add a game recommendation (alias for addgame)"""
        await self._add_game(ctx, entry)

    @commands.command(name="listgames")
    async def list_games(self, ctx):
        """List all game recommendations"""
        try:
            database = self._get_db()
            games = database.get_all_games()

            # Create embed (same format as the persistent recommendations list)
            embed = discord.Embed(
                title="📋 Game Recommendations",
                description="Current recommendations for mission enrichment. Review and consider.",
                color=0x2F3136  # Dark gray color matching Ash's aesthetic
            )

            if not games:
                embed.add_field(
                    name="Status",
                    value="No recommendations currently catalogued. Observation is key to survival.",
                    inline=False)
            else:
                # Create one continuous list
                game_lines = []
                for i, game in enumerate(games, 1):
                    # Truncate long names/reasons to fit in embed and apply Title Case
                    name = game['name'][:40] + "..." if len(game['name']) > 40 else game['name']
                    name = name.title()  # Convert to Title Case
                    reason = game["reason"][:60] + "..." if len(game["reason"]) > 60 else game["reason"]

                    # Don't show contributor twice - if reason already contains "Suggested by", don't add "by" again
                    if game['added_by'] and game['added_by'].strip() and not (
                            reason and f"Suggested by {game['added_by']}" in reason):
                        contributor = f" (by {game['added_by']})"
                    else:
                        contributor = ""

                    game_lines.append(f"{i}. **{name}** — \"{reason}\"{contributor}")

                # Join all games into one field value
                field_value = "\n".join(game_lines)

                # If the list is too long for one field, we'll need to split it
                if len(field_value) > 1024:
                    # Split into multiple fields but keep numbering continuous
                    current_field = []
                    current_length = 0

                    for line in game_lines:
                        if current_length + len(line) + 1 > 1000:  # Leave buffer
                            # Add current field
                            embed.add_field(
                                name="\u200b",  # Zero-width space for invisible field name
                                value="\n".join(current_field),
                                inline=False
                            )
                            # Start new field
                            current_field = [line]
                            current_length = len(line)
                        else:
                            current_field.append(line)
                            current_length += len(line) + 1

                    # Add the final field
                    if current_field:
                        embed.add_field(
                            name="\u200b",  # Zero-width space for invisible field name
                            value="\n".join(current_field),
                            inline=False
                        )
                else:
                    # Single field for all games
                    embed.add_field(
                        name="Current Recommendations",
                        value=field_value,
                        inline=False)

            # Add footer with stats
            embed.set_footer(
                text=f"Total recommendations: {len(games)} | Requested by {ctx.author.name}")
            embed.timestamp = discord.utils.utcnow()

            await ctx.send(embed=embed)

            # Also update the persistent recommendations list in the recommendations channel
            RECOMMEND_CHANNEL_ID = 1271568447108550687
            recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
            if recommend_channel and ctx.channel.id != RECOMMEND_CHANNEL_ID:
                # Only update if we're not already in the recommendations channel to avoid redundancy
                await self.post_or_update_recommend_list(ctx, recommend_channel)
                
        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            await ctx.send(f"❌ Error listing games: {str(e)}")

    @commands.command(name="removegame")
    @commands.has_permissions(manage_messages=True)
    async def remove_game(self, ctx, *, arg: str):
        """Remove a game recommendation by name or index (moderators only)"""
        try:
            database = self._get_db()
            
            # Try to interpret as index first
            index = None
            try:
                index = int(arg)
            except ValueError:
                pass

            removed = None
            if index is not None:
                removed = database.remove_game_by_index(index)
            else:
                # Try name match
                removed = database.remove_game_by_name(arg)

            if not removed:
                await ctx.send("⚠️ Removal protocol failed: No matching recommendation found by that index or designation. Precision is essential. Please specify a valid entry for expungement.")
                return

            RECOMMEND_CHANNEL_ID = 1271568447108550687
            recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
            
            # Only send the detailed removal message in the invoking channel if not the recommendations channel
            if ctx.channel.id != RECOMMEND_CHANNEL_ID:
                await ctx.send(f"Recommendation '{removed['name']}' has been expunged from the record. Protocol maintained.")
                
            # Always update the persistent recommendations list
            if recommend_channel:
                await self.post_or_update_recommend_list(ctx, recommend_channel)
                
        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            await ctx.send(f"❌ Error removing game: {str(e)}")


def setup(bot):
    """Add the GamesCommands cog to the bot"""
    bot.add_cog(GamesCommands(bot))
