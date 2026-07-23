import re
from datetime import datetime, timedelta
from typing import Any, Match, Optional, Tuple
from zoneinfo import ZoneInfo

import discord

from ...config import GAME_RECOMMENDATION_CHANNEL_ID, POPS_ARCADE_USER_ID
from ...database import get_database
from ...utils.text_processing import smart_truncate_response
from ..context_manager import get_or_create_context
from ..message_handler import get_user_communication_tier
from ...persona.sarcasm import apply_pops_arcade_sarcasm
from ...utils.youtube_helpers import attempt_youtube_api_analysis

db = get_database()


async def handle_youtube_views_query(message: discord.Message) -> None:
    """Handle YouTube view count queries with database caching and context retention."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. YouTube view analytics unavailable.")
            return

        context = get_or_create_context(message.author.id, message.channel.id)
        full_rankings = []
        data_source = "cache"

        # Step 1: Try to get data from the database cache
        cached_rankings = db.get_cached_youtube_rankings()
        sync_is_stale = True
        if cached_rankings:
            last_sync_time = cached_rankings[0].get('last_youtube_sync')
            if last_sync_time:
                # Data is stale if it's older than 24 hours
                if datetime.now(ZoneInfo("Europe/London")) - last_sync_time < timedelta(hours=24):
                    sync_is_stale = False
                    full_rankings = cached_rankings
                    print("✅ YouTube Analytics: Using fresh data from database cache.")

        # Step 2: If cache is stale or empty, fetch from YouTube API
        if sync_is_stale:
            print("🔄 YouTube Analytics: Cache is stale or empty. Fetching live data from API...")
            data_source = "live API"
            # Assumes this returns a full list
            youtube_data = await attempt_youtube_api_analysis(None, "general_full_list")

            if youtube_data and 'full_rankings' in youtube_data:
                full_rankings = youtube_data['full_rankings']
                # Step 3: Update the database cache with the new data
                db.update_youtube_cache(full_rankings)
            else:
                # If API fails, fall back to whatever is in the cache
                full_rankings = cached_rankings
                data_source = "stale cache (API failed)"
                print("⚠️ YouTube API failed. Falling back to stale cache.")

        if not full_rankings:
            await message.reply("Database analysis complete. Insufficient engagement data available for popularity ranking.")
            return

        # Step 4: Store the full list in the conversation context
        context.update_ranked_list_context(full_rankings)

        # Step 5: Format and send the response for the top results
        top_game = full_rankings[0]
        runner_up = full_rankings[1] if len(full_rankings) > 1 else None

        response = (
            f"YouTube analytics complete (data source: {data_source}). "
            f"'{top_game['canonical_name']}' demonstrates maximum viewer engagement with {top_game.get('youtube_views', 0):,} total views.")

        if runner_up:
            response += f" Secondary analysis indicates '{runner_up['canonical_name']}' follows with {runner_up.get('youtube_views', 0):,} views."

        response += (
            f"\n\n**Mission Parameters - Enhanced Analytics Available:**\n"
            f"• *'What are the next three?'*\n"
            f"• *'Show me the 4th and 5th most popular.'*\n"
            f"• *'What about the third?'*\n\n"
            f"I have retained the complete rankings for this session. You may ask follow-up questions."
        )

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in YouTube views query: {e}")
        await message.reply("Database analysis encountered an anomaly during popularity assessment. Analytics systems require recalibration.")


async def handle_twitch_views_query(message: discord.Message) -> None:
    """Handle Twitch view count queries."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. Twitch view analytics unavailable.")
            return

        # Get games ranked by Twitch views
        twitch_games = db.get_games_by_twitch_views(limit=10)

        if not twitch_games:
            await message.reply("Database analysis complete. Insufficient Twitch engagement data available for ranking.")
            return

        top_game = twitch_games[0]
        runner_up = twitch_games[1] if len(twitch_games) > 1 else None

        # Calculate VOD count
        vod_count = top_game.get('total_episodes', 0)

        response = (
            f"🎮 Twitch Analytics: '{top_game['canonical_name']}' demonstrates maximum Twitch engagement "
            f"with {top_game.get('twitch_views', 0):,} total views across {vod_count} VODs. "
        )

        if runner_up:
            response += f"Secondary analysis indicates '{runner_up['canonical_name']}' follows with {runner_up.get('twitch_views', 0):,} views."

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in Twitch views query: {e}")
        await message.reply("Database analysis encountered an anomaly during Twitch engagement assessment.")


async def handle_total_views_query(message: discord.Message) -> None:
    """Handle combined YouTube + Twitch view queries."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. Cross-platform analytics unavailable.")
            return

        # Get games ranked by total views
        total_views_games = db.get_games_by_total_views(limit=10)

        if not total_views_games:
            await message.reply("Database analysis complete. Insufficient cross-platform engagement data available.")
            return

        top_game = total_views_games[0]
        youtube_views = top_game.get('youtube_views', 0)
        twitch_views = top_game.get('twitch_views', 0)
        total_views = top_game.get('total_views', 0)

        # Calculate percentages
        yt_percent = (youtube_views / total_views * 100) if total_views > 0 else 0
        tw_percent = (twitch_views / total_views * 100) if total_views > 0 else 0

        # Determine primary platform
        primary_platform = "YouTube" if youtube_views > twitch_views else "Twitch" if twitch_views > youtube_views else "Balanced"

        response = (
            f"📈 Cross-Platform Analytics: '{top_game['canonical_name']}' demonstrates maximum total engagement "
            f"with {total_views:,} combined views.\n\n"
            f"📊 Platform Breakdown:\n"
            f"• YouTube: {youtube_views:,} views ({yt_percent:.1f}%)\n"
            f"• Twitch: {twitch_views:,} views ({tw_percent:.1f}%)\n"
            f"• Primary Platform: {primary_platform}\n"
            f"• Total Content: {top_game.get('total_episodes', 0)} episodes/VODs\n\n"
            f"This represents comprehensive audience reach across both platforms."
        )

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in total views query: {e}")
        await message.reply("Database analysis encountered an anomaly during cross-platform assessment.")


async def handle_engagement_rate_query(message: discord.Message) -> None:
    """Handle engagement rate/efficiency queries."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. Engagement efficiency analytics unavailable.")
            return

        # Get top games by engagement rate
        engagement_data = db.get_engagement_metrics(limit=10)

        if not engagement_data:
            await message.reply("Database analysis complete. Insufficient data for engagement rate calculation.")
            return

        top_game = engagement_data[0]

        response = (
            f"⚡ Engagement Efficiency Analysis: '{top_game['canonical_name']}' demonstrates optimal engagement rate.\n\n"
            f"📊 Efficiency Metrics:\n"
            f"• Views per Episode: {top_game.get('views_per_episode', 0):,.1f} views/ep\n"
            f"• Views per Hour: {top_game.get('views_per_hour', 0):,.1f} views/hour\n"
            f"• Total Content: {top_game.get('total_playtime_minutes', 0) // 60}h across {top_game.get('total_episodes', 0)} episodes\n"
            f"• Combined Views: {top_game.get('total_views', 0):,}\n\n"
            f"This represents exceptional audience engagement relative to content volume.")

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in engagement rate query: {e}")
        await message.reply("Database analysis encountered an anomaly during efficiency assessment.")
