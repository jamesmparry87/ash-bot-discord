"""
Data Cleanup Commands

Provides commands for manually cleaning up and normalizing database data.
"""

import discord
from discord.ext import commands

from ..database_module import get_database
from ..utils.data_quality import audit_data_quality, cleanup_all_genres, cleanup_series_names

db = get_database()


class DataCleanupCommands(commands.Cog):
    """Commands for data quality maintenance"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='cleanupdata')
    @commands.has_permissions(manage_messages=True)
    async def cleanup_data(self, ctx):
        """
        Run comprehensive data cleanup on the games database.

        This will:
        - Normalize all genre names
        - Normalize all series names
        - Deduplicate games
        - Generate audit report

        Usage: !cleanupdata
        """

        if not db:
            await ctx.send("❌ Database not available.")
            return

        # Send initial message
        status_msg = await ctx.send("🔄 **Data Cleanup Started**\n\nPhase 1: Genre normalization...")

        try:
            # Phase 1: Genre cleanup
            genre_stats = cleanup_all_genres(db)

            phase1_msg = (
                f"✅ **Phase 1 Complete: Genre Normalization**\n"
                f"• Total games: {genre_stats.get('total_games', 0)}\n"
                f"• Updated: {genre_stats.get('updated', 0)}\n"
                f"• Already normalized: {genre_stats.get('already_normalized', 0)}\n"
                f"• Missing genre: {genre_stats.get('missing_genre', 0)}"
            )

            await status_msg.edit(content=f"{phase1_msg}\n\n🔄 Phase 2: Series name normalization...")

            # Phase 2: Series name cleanup
            series_stats = cleanup_series_names(db)

            phase2_msg = (
                f"\n\n✅ **Phase 2 Complete: Series Name Normalization**\n"
                f"• Total games: {series_stats.get('total_games', 0)}\n"
                f"• Updated: {series_stats.get('updated', 0)}\n"
                f"• Already normalized: {series_stats.get('already_normalized', 0)}\n"
                f"• Missing series: {series_stats.get('missing_series', 0)}"
            )

            await status_msg.edit(content=f"{phase1_msg}{phase2_msg}\n\n🔄 Phase 3: Deduplication...")

            # Phase 3: Deduplication
            duplicates_merged = db.deduplicate_played_games()

            phase3_msg = (
                f"\n\n✅ **Phase 3 Complete: Deduplication**\n"
                f"• Duplicates merged: {duplicates_merged}"
            )

            # Final summary
            final_msg = (
                f"✅ **Data Cleanup Complete**\n\n"
                f"**Phase 1 - Genre Normalization:**\n"
                f"• Updated: {genre_stats.get('updated', 0)}\n"
                f"• Already normalized: {genre_stats.get('already_normalized', 0)}\n"
                f"• Missing genre: {genre_stats.get('missing_genre', 0)}\n\n"
                f"**Phase 2 - Series Normalization:**\n"
                f"• Updated: {series_stats.get('updated', 0)}\n"
                f"• Already normalized: {series_stats.get('already_normalized', 0)}\n"
                f"• Missing series: {series_stats.get('missing_series', 0)}\n\n"
                f"**Phase 3 - Deduplication:**\n"
                f"• Duplicates merged: {duplicates_merged}\n\n"
                f"Use `!auditdata` to see detailed quality report."
            )

            await status_msg.edit(content=final_msg)

        except Exception as e:
            await status_msg.edit(content=f"❌ **Cleanup Failed**\n\nError: {str(e)}")
            print(f"❌ Data cleanup error: {e}")

    @commands.command(name='auditdata')
    @commands.has_permissions(manage_messages=True)
    async def audit_data(self, ctx):
        """
        Generate a data quality audit report.

        Shows:
        - Missing fields
        - Non-standard values
        - Duplicate series spellings
        - Data consistency issues

        Usage: !auditdata
        """

        if not db:
            await ctx.send("❌ Database not available.")
            return

        await ctx.send("🔍 **Running Data Quality Audit...**")

        try:
            report = audit_data_quality(db)

            if 'error' in report:
                await ctx.send(f"❌ Audit failed: {report['error']}")
                return

            # Build report message
            report_msg = (
                f"📊 **Data Quality Audit Report**\n\n"
                f"**Overview:**\n"
                f"• Total games: {report['total_games']}\n"
                f"• Missing genre: {report['missing_genre']}\n"
                f"• Missing series: {report['missing_series']}\n"
                f"• Missing completion status: {report['missing_completion_status']}\n\n"
            )

            # Non-standard genres
            if report['non_standard_genres']:
                report_msg += f"**Non-Standard Genres ({len(report['non_standard_genres'])}):**\n"
                for item in report['non_standard_genres'][:5]:  # Show first 5
                    report_msg += f"• {item['game']}: `{item['current']}` → `{item['should_be']}`\n"
                if len(report['non_standard_genres']) > 5:
                    report_msg += f"• ... and {len(report['non_standard_genres']) - 5} more\n"
                report_msg += "\n"

            # Non-standard series
            if report['non_standard_series']:
                report_msg += f"**Non-Standard Series Names ({len(report['non_standard_series'])}):**\n"
                for item in report['non_standard_series'][:5]:
                    report_msg += f"• {item['game']}: `{item['current']}` → `{item['should_be']}`\n"
                if len(report['non_standard_series']) > 5:
                    report_msg += f"• ... and {len(report['non_standard_series']) - 5} more\n"
                report_msg += "\n"

            # Duplicate series spellings
            if report['duplicate_series_spellings']:
                report_msg += f"**Duplicate Series Spellings ({len(report['duplicate_series_spellings'])}):**\n"
                for series_lower, variations in list(report['duplicate_series_spellings'].items())[:3]:
                    report_msg += f"• {series_lower}: {', '.join(f'`{v}`' for v in variations)}\n"
                if len(report['duplicate_series_spellings']) > 3:
                    report_msg += f"• ... and {len(report['duplicate_series_spellings']) - 3} more\n"
                report_msg += "\n"

            # Data consistency issues
            if report['games_with_episodes_no_playtime'] > 0 or report['games_with_playtime_no_episodes'] > 0:
                report_msg += "**Data Consistency Issues:**\n"
                if report['games_with_episodes_no_playtime'] > 0:
                    report_msg += f"• {report['games_with_episodes_no_playtime']} games with episodes but no playtime\n"
                if report['games_with_playtime_no_episodes'] > 0:
                    report_msg += f"• {report['games_with_playtime_no_episodes']} games with playtime but no episodes\n"
                report_msg += "\n"

            report_msg += "**Recommendation:** Run `!cleanupdata` to fix these issues."

            # Split into multiple messages if too long
            if len(report_msg) > 2000:
                parts = []
                current_part = ""
                for line in report_msg.split('\n'):
                    if len(current_part) + len(line) + 1 > 1900:
                        parts.append(current_part)
                        current_part = line + '\n'
                    else:
                        current_part += line + '\n'
                if current_part:
                    parts.append(current_part)

                for part in parts:
                    await ctx.send(part)
            else:
                await ctx.send(report_msg)

        except Exception as e:
            await ctx.send(f"❌ **Audit Failed**\n\nError: {str(e)}")
            print(f"❌ Data audit error: {e}")


async def setup(bot):
    await bot.add_cog(DataCleanupCommands(bot))
