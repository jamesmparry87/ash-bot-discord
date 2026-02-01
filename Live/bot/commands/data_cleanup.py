"""
Data Cleanup Commands Module

Admin commands for cleaning and validating the played games database.
"""

from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from ..config import JAM_USER_ID
from ..database import get_database


class DataCleanupCommands(commands.Cog):
    """Commands for database cleanup and validation"""

    def __init__(self, bot):
        self.bot = bot
        self.db = get_database()

    @commands.command(name='cleandatabase')
    @commands.check(lambda ctx: ctx.author.id == JAM_USER_ID)
    async def clean_database(self, ctx):
        """
        Re-validate all game titles in the database against IGDB.
        This will identify misnamed games and suggest corrections.

        **Admin only command**
        """
        await ctx.send("🔄 **Database Cleanup Started**\n\nValidating all game titles against IGDB. This may take a few minutes...")

        try:
            # Import IGDB validation
            from ..integrations.igdb import filter_english_names, validate_and_enrich

            # Get all games from database
            all_games = self.db.get_all_played_games()

            if not all_games:
                await ctx.send("❌ No games found in database.")
                return

            # Track results
            total_games = len(all_games)
            validated = 0
            needs_correction = []
            needs_review = []
            errors = 0

            status_msg = await ctx.send(f"📊 Progress: 0/{total_games} games validated...")

            for i, game in enumerate(all_games):
                canonical_name = game.get('canonical_name', '')  # Initialize outside try block
                try:
                    game_id = game.get('id')

                    if not canonical_name:
                        continue

                    # Validate against IGDB
                    igdb_result = await validate_and_enrich(canonical_name)

                    if igdb_result and igdb_result.get('match_found'):
                        confidence = igdb_result.get('confidence', 0.0)
                        igdb_name = igdb_result.get('canonical_name', '')

                        # High confidence but different name - suggest correction
                        if confidence >= 0.85 and igdb_name.lower() != canonical_name.lower():
                            needs_correction.append({
                                'id': game_id,
                                'current_name': canonical_name,
                                'suggested_name': igdb_name,
                                'confidence': confidence,
                                'igdb_data': igdb_result
                            })

                        # Medium confidence - flag for review
                        elif 0.5 <= confidence < 0.85:
                            needs_review.append({
                                'id': game_id,
                                'current_name': canonical_name,
                                'suggested_name': igdb_name,
                                'confidence': confidence
                            })

                        validated += 1

                    # Update progress every 10 games
                    if (i + 1) % 10 == 0:
                        await status_msg.edit(content=f"📊 Progress: {i+1}/{total_games} games validated...")

                except Exception as game_error:
                    print(f"⚠️ Error validating game '{canonical_name}': {game_error}")
                    errors += 1

            # Final report
            await status_msg.delete()

            embed = discord.Embed(
                title="🧹 Database Cleanup Report",
                description=f"Validation complete for {total_games} games",
                color=0x00ff00
            )

            embed.add_field(
                name="✅ Validated Successfully",
                value=f"{validated} games",
                inline=True
            )

            embed.add_field(
                name="📝 Need Correction",
                value=f"{len(needs_correction)} games",
                inline=True
            )

            embed.add_field(
                name="⚠️ Need Review",
                value=f"{len(needs_review)} games",
                inline=True
            )

            if errors > 0:
                embed.add_field(
                    name="❌ Errors",
                    value=f"{errors} games",
                    inline=True
                )

            await ctx.send(embed=embed)

            # Show corrections needed
            if needs_correction:
                correction_msg = "**🔧 Suggested Corrections (High Confidence):**\n\n"
                for i, item in enumerate(needs_correction[:10], 1):  # Show first 10
                    correction_msg += f"{i}. **{item['current_name']}** → **{item['suggested_name']}** ({item['confidence']:.0%})\n"

                if len(needs_correction) > 10:
                    correction_msg += f"\n*...and {len(needs_correction) - 10} more*"

                correction_msg += f"\n\n*Use `!applycorrections` to apply these changes*"
                await ctx.send(correction_msg)

            # Show items needing review
            if needs_review:
                review_msg = "**⚠️ Items Needing Manual Review (Medium Confidence):**\n\n"
                for i, item in enumerate(needs_review[:5], 1):  # Show first 5
                    review_msg += f"{i}. **{item['current_name']}** → **{item['suggested_name']}** ({item['confidence']:.0%})\n"

                if len(needs_review) > 5:
                    review_msg += f"\n*...and {len(needs_review) - 5} more*"

                await ctx.send(review_msg)

            # Store results for later commands
            self.bot.cleanup_results = {
                'corrections': needs_correction,
                'reviews': needs_review
            }

        except Exception as e:
            await ctx.send(f"❌ **Error during database cleanup:** {str(e)}")
            print(f"Error in clean_database: {e}")
            import traceback
            traceback.print_exc()

    @commands.command(name='applycorrections')
    @commands.check(lambda ctx: ctx.author.id == JAM_USER_ID)
    async def apply_corrections(self, ctx):
        """
        Apply the corrections suggested by !cleandatabase

        **Admin only command**
        """
        if not hasattr(self.bot, 'cleanup_results') or not self.bot.cleanup_results.get('corrections'):
            await ctx.send("❌ No corrections available. Run `!cleandatabase` first.")
            return

        corrections = self.bot.cleanup_results['corrections']

        await ctx.send(f"🔄 **Applying {len(corrections)} corrections...**")

        success_count = 0
        error_count = 0

        for item in corrections:
            try:
                game_id = item['id']
                new_name = item['suggested_name']
                igdb_data = item['igdb_data']

                # Update game with corrected name and enriched data
                update_params = {
                    'canonical_name': new_name
                }

                # Add enriched data from IGDB
                if igdb_data.get('genre'):
                    from ..tasks.scheduled import map_genre_to_standard
                    update_params['genre'] = map_genre_to_standard(igdb_data['genre'])

                if igdb_data.get('release_year'):
                    update_params['release_year'] = igdb_data['release_year']

                if igdb_data.get('series_name'):
                    update_params['series_name'] = igdb_data['series_name']

                if igdb_data.get('alternative_names'):
                    from ..integrations.igdb import filter_english_names
                    update_params['alternative_names'] = filter_english_names(igdb_data['alternative_names'])[:5]

                # 🔧 FIX: Save IGDB metadata fields (previously missing!)
                if igdb_data.get('igdb_id'):
                    update_params['igdb_id'] = igdb_data['igdb_id']

                update_params['data_confidence'] = igdb_data.get('confidence', 0.0)
                update_params['igdb_last_validated'] = datetime.now()

                self.db.update_played_game(game_id, **update_params)
                success_count += 1
                print(f"✅ Updated: {item['current_name']} → {new_name}")

            except Exception as e:
                error_count += 1
                print(f"❌ Failed to update {item.get('current_name', 'unknown')}: {e}")

        embed = discord.Embed(
            title="✅ Corrections Applied",
            description=f"Database cleanup complete",
            color=0x00ff00
        )

        embed.add_field(name="Success", value=f"{success_count} games updated", inline=True)
        if error_count > 0:
            embed.add_field(name="Errors", value=f"{error_count} failed", inline=True)

        await ctx.send(embed=embed)

        # Clear stored results
        self.bot.cleanup_results = None

    @commands.command(name='databasemaintenance')
    @commands.check(lambda ctx: ctx.author.id == JAM_USER_ID)
    async def database_maintenance(self, ctx):
        """
        Complete database maintenance - runs all cleanup tasks in sequence:
        1. Deduplicate games
        2. Clean alternative names
        3. Validate against IGDB
        4. Apply corrections

        **Admin only command - Use this after deploying changes**
        """
        await ctx.send("🚀 **Starting Complete Database Maintenance**\n\nThis will run all cleanup tasks in sequence...")

        try:
            # Step 1: Deduplicate
            await ctx.send("**Step 1/4:** Deduplicating games...")
            merged_count = self.db.deduplicate_played_games()
            if merged_count > 0:
                await ctx.send(f"✅ Merged {merged_count} duplicate entries")
            else:
                await ctx.send("✅ No duplicates found")

            # Step 2: Clean alternative names
            await ctx.send("\n**Step 2/4:** Cleaning alternative names (English-only)...")
            from ..integrations.igdb import filter_english_names

            all_games = self.db.get_all_played_games()
            cleaned_count = 0
            total_removed = 0

            for game in all_games:
                alt_names = game.get('alternative_names', [])

                if alt_names:
                    if isinstance(alt_names, str):
                        import json
                        try:
                            alt_names = json.loads(alt_names)
                        except BaseException:
                            alt_names = [n.strip() for n in alt_names.split(',') if n.strip()]

                    if not isinstance(alt_names, list):
                        continue

                    original_count = len(alt_names)
                    english_only = filter_english_names(alt_names)
                    unique_names = list(set(english_only))

                    if len(unique_names) < original_count:
                        self.db.update_played_game(game['id'], alternative_names=unique_names)
                        cleaned_count += 1
                        total_removed += original_count - len(unique_names)

            await ctx.send(f"✅ Cleaned {cleaned_count} games, removed {total_removed} non-English names")

            # Step 3: Validate against IGDB
            await ctx.send("\n**Step 3/4:** Validating all games against IGDB...")
            from ..integrations.igdb import validate_and_enrich

            all_games = self.db.get_all_played_games()  # Refresh after deduplication
            total_games = len(all_games)
            validated = 0
            needs_correction = []
            needs_review = []

            status_msg = await ctx.send(f"📊 Progress: 0/{total_games} games...")

            for i, game in enumerate(all_games):
                canonical_name = game.get('canonical_name', '')
                try:
                    if not canonical_name:
                        continue

                    igdb_result = await validate_and_enrich(canonical_name)

                    if igdb_result and igdb_result.get('match_found'):
                        confidence = igdb_result.get('confidence', 0.0)
                        igdb_name = igdb_result.get('canonical_name', '')

                        if confidence >= 0.85 and igdb_name.lower() != canonical_name.lower():
                            needs_correction.append({
                                'id': game.get('id'),
                                'current_name': canonical_name,
                                'suggested_name': igdb_name,
                                'confidence': confidence,
                                'igdb_data': igdb_result
                            })
                        elif 0.5 <= confidence < 0.85:
                            needs_review.append({
                                'id': game.get('id'),
                                'current_name': canonical_name,
                                'suggested_name': igdb_name,
                                'confidence': confidence
                            })
                        validated += 1

                    if (i + 1) % 10 == 0:
                        await status_msg.edit(content=f"📊 Progress: {i+1}/{total_games} games...")

                except Exception as e:
                    print(f"⚠️ Error validating '{canonical_name}': {e}")

            await status_msg.delete()
            await ctx.send(f"✅ Validated {validated} games")

            # Step 4: Apply corrections
            if needs_correction:
                await ctx.send(f"\n**Step 4/4:** Applying {len(needs_correction)} high-confidence corrections...")

                success_count = 0
                for item in needs_correction:
                    try:
                        game_id = item['id']
                        new_name = item['suggested_name']
                        igdb_data = item['igdb_data']

                        update_params = {'canonical_name': new_name}

                        if igdb_data.get('genre'):
                            from ..tasks.scheduled import map_genre_to_standard
                            update_params['genre'] = map_genre_to_standard(igdb_data['genre'])

                        if igdb_data.get('release_year'):
                            update_params['release_year'] = igdb_data['release_year']

                        if igdb_data.get('series_name'):
                            update_params['series_name'] = igdb_data['series_name']

                        if igdb_data.get('alternative_names'):
                            update_params['alternative_names'] = filter_english_names(
                                igdb_data['alternative_names'])[:5]

                        # 🔧 FIX: Save IGDB metadata fields (previously missing!)
                        if igdb_data.get('igdb_id'):
                            update_params['igdb_id'] = igdb_data['igdb_id']

                        update_params['data_confidence'] = igdb_data.get('confidence', 0.0)
                        update_params['igdb_last_validated'] = datetime.now()

                        self.db.update_played_game(game_id, **update_params)
                        success_count += 1

                    except Exception as e:
                        print(f"❌ Failed to update {item.get('current_name', 'unknown')}: {e}")

                await ctx.send(f"✅ Applied {success_count} corrections")
            else:
                await ctx.send("\n**Step 4/4:** No corrections needed")

            # Final summary
            embed = discord.Embed(
                title="✅ Database Maintenance Complete",
                description="All housekeeping tasks finished successfully",
                color=0x00ff00
            )

            embed.add_field(name="Duplicates Merged", value=str(merged_count), inline=True)
            embed.add_field(name="Alt Names Cleaned", value=str(cleaned_count), inline=True)
            embed.add_field(name="Games Validated", value=str(validated), inline=True)
            embed.add_field(name="Corrections Applied", value=str(len(needs_correction)), inline=True)

            if needs_review:
                embed.add_field(
                    name="⚠️ Manual Review Needed",
                    value=f"{len(needs_review)} games need manual review",
                    inline=False
                )

                review_msg = "**Items needing manual review:**\n"
                for item in needs_review[:5]:
                    review_msg += f"• **{item['current_name']}** → **{item['suggested_name']}** ({item['confidence']:.0%})\n"
                if len(needs_review) > 5:
                    review_msg += f"*...and {len(needs_review) - 5} more*"

                await ctx.send(review_msg)

            await ctx.send(embed=embed)
            await ctx.send("🎉 **Database is now clean and optimized!**")

        except Exception as e:
            await ctx.send(f"❌ **Error during maintenance:** {str(e)}")
            print(f"Error in database_maintenance: {e}")
            import traceback
            traceback.print_exc()

    @commands.command(name='cleanaltnames')
    @commands.check(lambda ctx: ctx.author.id == JAM_USER_ID)
    async def clean_alt_names(self, ctx):
        """
        Clean all alternative names to English-only.
        Removes non-Latin script names from all games.

        **Admin only command**
        """
        await ctx.send("🔄 **Cleaning Alternative Names**\n\nFiltering to English-only names...")

        try:
            from ..integrations.igdb import filter_english_names

            all_games = self.db.get_all_played_games()

            cleaned_count = 0
            total_removed = 0

            for game in all_games:
                alt_names = game.get('alternative_names', [])

                if alt_names:
                    # Handle string format
                    if isinstance(alt_names, str):
                        # Parse various formats
                        import json
                        try:
                            alt_names = json.loads(alt_names)
                        except BaseException:
                            # Try comma-separated
                            alt_names = [n.strip() for n in alt_names.split(',') if n.strip()]

                    if not isinstance(alt_names, list):
                        continue

                    original_count = len(alt_names)

                    # Filter to English-only
                    english_only = filter_english_names(alt_names)

                    # Deduplicate
                    unique_names = list(set(english_only))

                    if len(unique_names) < original_count:
                        # Update database
                        self.db.update_played_game(game['id'], alternative_names=unique_names)
                        cleaned_count += 1
                        removed = original_count - len(unique_names)
                        total_removed += removed
                        print(
                            f"✅ Cleaned {game['canonical_name']}: {original_count} → {len(unique_names)} names ({removed} removed)")

            embed = discord.Embed(
                title="✅ Alternative Names Cleaned",
                description=f"Filtered all alternative names to English-only",
                color=0x00ff00
            )

            embed.add_field(name="Games Cleaned", value=f"{cleaned_count} games", inline=True)
            embed.add_field(name="Names Removed", value=f"{total_removed} non-English names", inline=True)

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ **Error cleaning alternative names:** {str(e)}")
            print(f"Error in clean_alt_names: {e}")
            import traceback
            traceback.print_exc()


async def setup(bot):
    await bot.add_cog(DataCleanupCommands(bot))
