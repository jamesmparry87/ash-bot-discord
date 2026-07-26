import re
from datetime import datetime
from typing import Any, Match, Optional, Tuple
from zoneinfo import ZoneInfo

import discord

from ...config import GAME_RECOMMENDATION_CHANNEL_ID, POPS_ARCADE_USER_ID
from ...database import get_database
from ...persona.sarcasm import apply_pops_arcade_sarcasm
from ...utils.text_processing import smart_truncate_response
from ..message_handler import get_user_communication_tier

db = get_database()


async def handle_comparison_query(message: discord.Message, match: Match[str]) -> None:
    """Handles direct comparison queries between two games."""
    if db is None:
        await message.reply("Database analysis systems offline. Comparison queries unavailable.")
        return

    game1_name = match.group(1).strip()
    game2_name = match.group(2).strip()

    comparison_data = db.compare_games(game1_name, game2_name)

    if comparison_data.get('error'):
        if not comparison_data.get('game1_found') and not comparison_data.get('game2_found'):
            await message.reply(f"Database scan complete. No records found for either '{game1_name}' or '{game2_name}'.")
        elif not comparison_data.get('game1_found'):
            await message.reply(f"Database scan complete. No records found for '{game1_name}'.")
        else:
            await message.reply(f"Database scan complete. No records found for '{game2_name}'.")
        return

    game1 = comparison_data['game1']
    game2 = comparison_data['game2']
    comparison = comparison_data['comparison']

    embed = discord.Embed(
        title=f"Comparative Analysis: {game1['name']} vs. {game2['name']}",
        color=0x00ff00,
        timestamp=datetime.now(ZoneInfo("Europe/London"))
    )

    # Add fields for each game
    embed.add_field(
        name=f"🎮 {game1['name']}",
        value=(
            f"**Playtime:** {game1['playtime_hours']} hours\n"
            f"**Episodes:** {game1['episodes']}\n"
            f"**Status:** {game1['status'].title()}"
        ),
        inline=True
    )
    embed.add_field(
        name=f"🎮 {game2['name']}",
        value=(
            f"**Playtime:** {game2['playtime_hours']} hours\n"
            f"**Episodes:** {game2['episodes']}\n"
            f"**Status:** {game2['status'].title()}"
        ),
        inline=True
    )

    # Add a summary of the comparison
    playtime_diff = abs(comparison['playtime_difference_minutes'])
    playtime_diff_hours = round(playtime_diff / 60, 1)
    episode_diff = abs(comparison['episode_difference'])

    summary = (
        f"▶️ **Longer Playtime:** {comparison['longer_game']} (by {playtime_diff_hours} hours)\n"
        f"▶️ **More Episodes:** {comparison['more_episodes']} (by {episode_diff} episodes)"
    )

    embed.add_field(name="📊 Summary", value=summary, inline=False)
    embed.set_footer(text="Analysis complete. All data retrieved from mission archives.")

    await message.reply(embed=embed)


async def handle_platform_comparison_query(message: discord.Message) -> None:
    """Handle platform comparison queries."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. Platform comparison unavailable.")
            return

        # Get platform statistics
        stats = db.get_platform_comparison_stats()

        if not stats:
            await message.reply("Database analysis complete. Insufficient platform data for comparison.")
            return

        yt_stats = stats.get('youtube', {})
        tw_stats = stats.get('twitch', {})
        cross_platform = stats.get('cross_platform_count', 0)

        response = (
            f"🔍 Platform Engagement Analysis:\n\n"
            f"📺 YouTube Metrics:\n"
            f"• Total Games: {yt_stats.get('game_count', 0)}\n"
            f"• Total Views: {yt_stats.get('total_views', 0):,}\n"
            f"• Avg Views/Game: {yt_stats.get('avg_views_per_game', 0):,.1f}\n"
            f"• Total Episodes: {yt_stats.get('total_content', 0):,}\n\n"
            f"🎮 Twitch Metrics:\n"
            f"• Total Games: {tw_stats.get('game_count', 0)}\n"
            f"• Total Views: {tw_stats.get('total_views', 0):,}\n"
            f"• Avg Views/Game: {tw_stats.get('avg_views_per_game', 0):,.1f}\n"
            f"• Total VODs: {tw_stats.get('total_content', 0):,}\n\n"
            f"📊 Cross-Platform Games: {cross_platform} titles appear on both platforms\n"
        )

        # Add comparison insight
        if yt_stats.get('total_views', 0) > tw_stats.get('total_views', 0):
            diff_percent = ((yt_stats.get('total_views', 0) - tw_stats.get('total_views', 0)) /
                            tw_stats.get('total_views', 1)) * 100
            response += f"\nPrimary Platform Analysis: YouTube shows stronger engagement with {diff_percent:.1f}% more total views."
        elif tw_stats.get('total_views', 0) > yt_stats.get('total_views', 0):
            diff_percent = ((tw_stats.get('total_views', 0) - yt_stats.get('total_views', 0)) /
                            yt_stats.get('total_views', 1)) * 100
            response += f"\nPrimary Platform Analysis: Twitch shows stronger engagement with {diff_percent:.1f}% more total views."
        else:
            response += f"\nPrimary Platform Analysis: Balanced engagement across both platforms."

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in platform comparison query: {e}")
        await message.reply("Database analysis encountered an anomaly during platform comparison.")
