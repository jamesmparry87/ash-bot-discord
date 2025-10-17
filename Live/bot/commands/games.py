"""
Game recommendation commands for Ash Bot
Handles adding, listing, and managing game recommendations
"""

from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands

from ..config import JAM_USER_ID
from ..database_module import get_database
from ..tasks.scheduled import perform_full_content_sync

# Get database instance
db = get_database()


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

                # Exclude username if user is Sir Decent Jam (user ID
                # 337833732901961729)
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

                # Send confirmation privately to the user via DM
                try:
                    await ctx.author.send(confirm_msg)
                except discord.Forbidden:
                    # If DM fails, send an ephemeral-style message in channel
                    await ctx.send(f"{ctx.author.mention} {confirm_msg}", delete_after=10)

                # Always update the persistent recommendations list
                if recommend_channel:
                    await self.post_or_update_recommend_list(ctx, recommend_channel)

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
                    # Truncate long names/reasons to fit in embed and apply
                    # Title Case
                    name = game['name'][:40] + \
                        "..." if len(game['name']) > 40 else game['name']
                    name = name.title()  # Convert to Title Case
                    reason = game["reason"][:60] + \
                        "..." if len(game["reason"]) > 60 else game["reason"]

                    # Don't show contributor twice - if reason already contains
                    # "Suggested by", don't add "by" again
                    if game['added_by'] and game['added_by'].strip() and not (
                            reason and f"Suggested by {game['added_by']}" in reason):
                        contributor = f" (by {game['added_by']})"
                    else:
                        contributor = ""

                    game_lines.append(
                        f"{i}. **{name}** — \"{reason}\"{contributor}")

                # Join all games into one field value
                field_value = "\n".join(game_lines)

                # If the list is too long for one field, we'll need to split it
                if len(field_value) > 1024:
                    # Split into multiple fields but keep numbering continuous
                    current_field = []
                    current_length = 0

                    for line in game_lines:
                        if current_length + \
                                len(line) + 1 > 1000:  # Leave buffer
                            # Add current field - use empty string for field
                            # name to eliminate gaps
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
                    # Single field for all games - use empty string for field
                    # name
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
                database.set_config_value(
                    "recommend_list_message_id", str(msg.id))

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
                    # Truncate long names/reasons to fit in embed and apply
                    # Title Case
                    name = game['name'][:40] + \
                        "..." if len(game['name']) > 40 else game['name']
                    name = name.title()  # Convert to Title Case
                    reason = game["reason"][:60] + \
                        "..." if len(game["reason"]) > 60 else game["reason"]

                    # Don't show contributor twice - if reason already contains
                    # "Suggested by", don't add "by" again
                    if game['added_by'] and game['added_by'].strip() and not (
                            reason and f"Suggested by {game['added_by']}" in reason):
                        contributor = f" (by {game['added_by']})"
                    else:
                        contributor = ""

                    game_lines.append(
                        f"{i}. **{name}** — \"{reason}\"{contributor}")

                # Join all games into one field value
                field_value = "\n".join(game_lines)

                # If the list is too long for one field, we'll need to split it
                if len(field_value) > 1024:
                    # Split into multiple fields but keep numbering continuous
                    current_field = []
                    current_length = 0

                    for line in game_lines:
                        if current_length + \
                                len(line) + 1 > 1000:  # Leave buffer
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

            # Also update the persistent recommendations list in the
            # recommendations channel
            RECOMMEND_CHANNEL_ID = 1271568447108550687
            recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
            if recommend_channel and ctx.channel.id != RECOMMEND_CHANNEL_ID:
                # Only update if we're not already in the recommendations
                # channel to avoid redundancy
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

            # Only send the detailed removal message in the invoking channel if
            # not the recommendations channel
            if ctx.channel.id != RECOMMEND_CHANNEL_ID:
                await ctx.send(f"Recommendation '{removed['name']}' has been expunged from the record. Protocol maintained.")

            # Always update the persistent recommendations list
            if recommend_channel:
                await self.post_or_update_recommend_list(ctx, recommend_channel)

        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            await ctx.send(f"❌ Error removing game: {str(e)}")

    @commands.command(name="addplayedgame")
    @commands.has_permissions(manage_messages=True)
    async def add_played_game(self, ctx, *, content: str | None = None):
        """Add a played game to the database with metadata (moderators only)"""
        try:
            if not content:
                # Progressive disclosure help
                help_text = (
                    "**Add Played Game Format:**\n"
                    "`!addplayedgame <name> | series:<series> | year:<year> | status:<status> | episodes:<count>`\n\n"
                    "**Examples:**\n"
                    "• `!addplayedgame Hollow Knight | status:completed | episodes:15`\n"
                    "• `!addplayedgame God of War (2018) | series:God of War | year:2018 | status:completed`\n\n"
                    "**Parameters:**\n"
                    "• **series:** Game series name\n"
                    "• **year:** Release year  \n"
                    "• **status:** completed, ongoing, dropped\n"
                    "• **episodes:** Number of episodes/parts\n\n"
                    "Only **name** is required, other fields are optional.")
                await ctx.send(help_text)
                return

            database = self._get_db()

            # Check if method exists
            if not hasattr(database, 'add_played_game'):
                await ctx.send("❌ **Played games management not available.** Database methods need implementation.\n\n*Required method: `add_played_game(name, **metadata)`*")
                return

            # Parse the game name and metadata
            parts = content.split(' | ')
            game_name = parts[0].strip()

            if not game_name:
                await ctx.send("❌ **Game name is required.** Format: `!addplayedgame <name> | series:<series> | status:<status>`")
                return

            # Parse metadata parameters
            metadata = {}
            for i in range(1, len(parts)):
                if ':' in parts[i]:
                    key, value = parts[i].split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if key in ['series', 'series_name']:
                        metadata['series_name'] = value
                    elif key in ['year', 'release_year']:
                        try:
                            metadata['release_year'] = int(value)
                        except ValueError:
                            await ctx.send(f"❌ **Invalid year:** '{value}'. Must be a number.")
                            return
                    elif key in ['status', 'completion_status']:
                        if value.lower() in [
                                'completed', 'ongoing', 'dropped']:
                            metadata['completion_status'] = value.lower()
                        else:
                            await ctx.send(f"❌ **Invalid status:** '{value}'. Use: completed, ongoing, or dropped")
                            return
                    elif key in ['episodes', 'total_episodes']:
                        try:
                            metadata['total_episodes'] = int(value)
                        except ValueError:
                            await ctx.send(f"❌ **Invalid episode count:** '{value}'. Must be a number.")
                            return
                    elif key in ['genre']:
                        metadata['genre'] = value
                    elif key in ['platform']:
                        metadata['platform'] = value

            # Add the played game
            try:
                success = database.add_played_game(game_name, **metadata)

                if success:
                    # Build confirmation message
                    details = []
                    if metadata.get('series_name'):
                        details.append(f"Series: {metadata['series_name']}")
                    if metadata.get('release_year'):
                        details.append(f"Year: {metadata['release_year']}")
                    if metadata.get('completion_status'):
                        details.append(
                            f"Status: {metadata['completion_status']}")
                    if metadata.get('total_episodes'):
                        details.append(
                            f"Episodes: {metadata['total_episodes']}")

                    details_text = f" ({', '.join(details)})" if details else ""
                    await ctx.send(f"✅ **'{game_name}' added to played games database**{details_text}.\n\n*Use `!gameinfo {game_name}` to view details.*")
                else:
                    await ctx.send(f"❌ **Failed to add '{game_name}'.** Database error occurred or game may already exist.")

            except Exception as e:
                print(f"❌ Error calling add_played_game: {e}")
                await ctx.send("❌ **Database method error.** The `add_played_game()` function needs proper implementation.")

        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            print(f"❌ Error in addplayedgame command: {e}")
            await ctx.send("❌ System error occurred while adding played game.")

    @commands.command(name="gameinfo")
    @commands.has_permissions(manage_messages=True)
    async def game_info(self, ctx, *, game_name: str | None = None):
        """Show detailed information about a specific game (moderators only)"""
        try:
            if not game_name:
                await ctx.send("❌ **Game name required.** Usage: `!gameinfo <game name>`\n\n**Example:** `!gameinfo Hollow Knight`")
                return

            database = self._get_db()

            # Check if method exists - use existing get_played_game
            if not hasattr(database, 'get_played_game'):
                await ctx.send("❌ **Game info not available.** Database method `get_played_game()` needs implementation.")
                return

            # Get game information
            try:
                game_data = database.get_played_game(game_name)

                if not game_data:
                    await ctx.send(f"❌ **'{game_name}' not found** in played games database.\n\n*Use `!addplayedgame` to add new games.*")
                    return

                # Build detailed info response
                info_text = f"🎮 **Game Information: {game_data['canonical_name']}**\n\n"

                # Basic info
                if game_data.get('series_name'):
                    info_text += f"**Series:** {game_data['series_name']}\n"
                if game_data.get('release_year'):
                    info_text += f"**Release Year:** {game_data['release_year']}\n"
                if game_data.get('genre'):
                    info_text += f"**Genre:** {game_data['genre']}\n"
                if game_data.get('platform'):
                    info_text += f"**Platform:** {game_data['platform']}\n"

                # Progress info
                status = game_data.get('completion_status', 'unknown')
                info_text += f"**Status:** {status.title()}\n"

                episodes = game_data.get('total_episodes', 0)
                if episodes > 0:
                    info_text += f"**Episodes:** {episodes}\n"

                # Playtime info
                playtime_minutes = game_data.get('total_playtime_minutes', 0)
                if playtime_minutes > 0:
                    if playtime_minutes >= 60:
                        hours = playtime_minutes // 60
                        minutes = playtime_minutes % 60
                        if minutes > 0:
                            playtime_text = f"{hours}h {minutes}m"
                        else:
                            playtime_text = f"{hours} hours"
                    else:
                        playtime_text = f"{playtime_minutes} minutes"

                    info_text += f"**Total Playtime:** {playtime_text}\n"

                    if episodes > 0:
                        avg_per_episode = round(playtime_minutes / episodes, 1)
                        info_text += f"**Average per Episode:** {avg_per_episode} minutes\n"

                # URLs if available
                if game_data.get('youtube_playlist_url'):
                    info_text += f"\n**YouTube Playlist:** {game_data['youtube_playlist_url']}\n"

                # Alternative names
                if game_data.get('alternative_names'):
                    alt_names = ', '.join(game_data['alternative_names'])
                    info_text += f"\n**Also Known As:** {alt_names}\n"

                await ctx.send(info_text[:2000])  # Discord limit

            except Exception as e:
                print(f"❌ Error calling get_played_game: {e}")
                await ctx.send("❌ **Database method error.** The `get_played_game()` function may need updates.")

        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            print(f"❌ Error in gameinfo command: {e}")
            await ctx.send("❌ System error occurred while retrieving game information.")

    @commands.command(name="updateplayedgame")
    @commands.has_permissions(manage_messages=True)
    async def update_played_game(self, ctx, *, content: str | None = None):
        """Update metadata for an existing played game (moderators only)"""
        try:
            if not content:
                # Progressive disclosure help
                help_text = (
                    "**Update Played Game Format:**\n"
                    "`!updateplayedgame <name_or_id> status:<new_status> | episodes:<count>`\n\n"
                    "**Examples:**\n"
                    "• `!updateplayedgame Hollow Knight status:completed | episodes:20`\n"
                    "• `!updateplayedgame 42 status:ongoing | episodes:15`\n\n"
                    "**Updatable Fields:**\n"
                    "• **status:** completed, ongoing, dropped\n"
                    "• **episodes:** Number of episodes/parts\n"
                    "• **series:** Series name\n"
                    "• **year:** Release year\n"
                    "• **genre:** Game genre\n\n"
                    "*Use `!gameinfo <name>` to see current values before updating.*")
                await ctx.send(help_text)
                return

            database = self._get_db()

            # Check if method exists
            if not hasattr(database, 'update_played_game'):
                await ctx.send("❌ **Game update not available.** Database method `update_played_game()` needs implementation.")
                return

            # Parse name/id and updates
            parts = content.split(' | ')
            if len(parts) < 2:
                await ctx.send("❌ **Invalid format.** Use: `!updateplayedgame <name> status:<status> | episodes:<count>`")
                return

            game_identifier = parts[0].strip()

            # Parse updates
            updates = {}
            for i in range(1, len(parts)):
                if ':' in parts[i]:
                    key, value = parts[i].split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if key in ['status', 'completion_status']:
                        if value.lower() in [
                                'completed', 'ongoing', 'dropped']:
                            updates['completion_status'] = value.lower()
                        else:
                            await ctx.send(f"❌ **Invalid status:** '{value}'. Use: completed, ongoing, or dropped")
                            return
                    elif key in ['episodes', 'total_episodes']:
                        try:
                            updates['total_episodes'] = int(value)
                        except ValueError:
                            await ctx.send(f"❌ **Invalid episode count:** '{value}'. Must be a number.")
                            return
                    elif key in ['series', 'series_name']:
                        updates['series_name'] = value
                    elif key in ['year', 'release_year']:
                        try:
                            updates['release_year'] = int(value)
                        except ValueError:
                            await ctx.send(f"❌ **Invalid year:** '{value}'. Must be a number.")
                            return
                    elif key in ['genre']:
                        updates['genre'] = value

            if not updates:
                await ctx.send("❌ **No valid updates provided.** Check format: `status:completed | episodes:20`")
                return

            # Update the game - handle both numeric IDs and game names
            try:
                # Determine if we have a numeric ID or a game name
                if game_identifier.isdigit():
                    # Direct numeric ID
                    game_id = int(game_identifier)
                    game_display_name = game_identifier
                else:
                    # Game name - look up the ID first
                    if not hasattr(database, 'get_played_game'):
                        await ctx.send("❌ **Game lookup not available.** Database method `get_played_game()` needs implementation.")
                        return

                    game_data = database.get_played_game(game_identifier)
                    if not game_data:
                        await ctx.send(f"❌ **'{game_identifier}' not found** in played games database.\n\n*Use `!gameinfo {game_identifier}` to verify the game exists.*")
                        return

                    game_id = game_data.get('id')
                    if game_id is None:
                        await ctx.send("❌ **Database error:** Game ID not available in game data.")
                        return

                    game_display_name = game_data.get(
                        'canonical_name', game_identifier)

                # Now call the database method with the correct integer ID
                success = database.update_played_game(game_id, **updates)

                if success:
                    # Build confirmation message
                    changes = []
                    for key, value in updates.items():
                        if key == 'completion_status':
                            changes.append(f"status: {value}")
                        elif key == 'total_episodes':
                            changes.append(f"episodes: {value}")
                        elif key == 'series_name':
                            changes.append(f"series: {value}")
                        elif key == 'release_year':
                            changes.append(f"year: {value}")
                        elif key == 'genre':
                            changes.append(f"genre: {value}")

                    changes_text = ', '.join(changes)
                    await ctx.send(f"✅ **Updated '{game_display_name}':** {changes_text}\n\n*Use `!gameinfo {game_identifier}` to view updated details.*")
                else:
                    await ctx.send(f"❌ **Failed to update '{game_display_name}'.** Game not found or database error.")

            except Exception as e:
                print(f"❌ Error calling update_played_game: {e}")
                await ctx.send("❌ **Database method error.** The `update_played_game()` function needs proper implementation.")

        except RuntimeError:
            await ctx.send("❌ Database unavailable")
        except Exception as e:
            print(f"❌ Error in updateplayedgame command: {e}")
            await ctx.send("❌ System error occurred while updating played game.")

    @commands.command(name="listplayedgames")
    @commands.has_permissions(manage_messages=True)
    async def list_played_games(self, ctx):
        """Lists all played games, sorted alphabetically by series."""
        # ... (This is the !listplayedgames code from our previous discussion, it's correct) ...

    @commands.command(name="syncgames")
    @commands.has_permissions(administrator=True)
    async def sync_games(self, ctx, mode: str = "standard"):
        """
        Triggers a content sync. Use `full` to re-scan all content.
        Usage: `!syncgames` (syncs new content) or `!syncgames full`
        """
        database = self._get_db()
        if mode.lower() == 'full':
            # A full rescan ignores the last sync time and goes back a long time (e.g., years)
            start_time = datetime.now() - timedelta(days=365 * 5)  # 5 years
            await ctx.send(f"🚀 **Full Content Sync Initiated.** Re-scanning all content from the last 5 years. This may take several minutes.")
        else:
            # Standard sync uses the most recent update timestamp
            start_time = database.get_latest_game_update_timestamp()
            # Add None-check with default fallback
            if start_time is None:
                start_time = datetime.now() - timedelta(days=7)  # Default to last week
            await ctx.send(f"🚀 **Standard Content Sync Initiated.** Scanning for new content since {start_time.strftime('%Y-%m-%d')}.")

        try:
            results = await perform_full_content_sync(start_time)
            await ctx.send(f"✅ **Sync Complete.**\n- Status: {results.get('status')}\n- New Content Found: {results.get('new_content_count', 0)}")
        except Exception as e:
            await ctx.send(f"❌ **Sync Failed:** {str(e)}")

    @commands.command(name="deduplicategames")
    @commands.has_permissions(administrator=True)
    async def deduplicate_games(self, ctx):
        """Manually triggers the game deduplication process."""


def setup(bot):
    """Add the GamesCommands cog to the bot"""
    bot.add_cog(GamesCommands(bot))
