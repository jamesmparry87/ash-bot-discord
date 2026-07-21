import discord
import re
from typing import Match, Optional, Tuple, Any

from ...database import get_database
from ...config import POPS_ARCADE_USER_ID, GAME_RECOMMENDATION_CHANNEL_ID
from ..message_handler import smart_truncate_response, get_user_communication_tier

db = get_database()


async def handle_statistical_query(
        message: discord.Message,
        content: str) -> None:
    """Handle statistical queries about games and series."""
    print(f"🔍 HANDLE_STATISTICAL_QUERY: Called with content: '{content[:100]}...'")

    # Check if database is available
    if db is None:
        print(f"❌ HANDLE_STATISTICAL_QUERY: Database is None!")
        await message.reply("Database analysis systems offline. Statistical processing unavailable.")
        return

    lower_content = content.lower()
    print(f"🔍 HANDLE_STATISTICAL_QUERY: Processing lower_content: '{lower_content[:100]}...'")

    try:
        if "most minutes" in lower_content or "most playtime" in lower_content:
            if "series" in lower_content:
                # Handle series playtime query
                series_stats = db.get_series_by_total_playtime()  # type: ignore
                if series_stats:
                    top_series = series_stats[0]
                    total_hours = round(
                        top_series['total_playtime_minutes'] / 60, 1)
                    game_count = top_series['game_count']
                    series_name = top_series['series_name']

                    response = f"Database analysis complete. The series with maximum temporal investment: '{series_name}' with {total_hours} hours across {game_count} games. "

                    # Add conversational follow-up
                    if len(series_stats) > 1:
                        second_series = series_stats[1]
                        second_hours = round(
                            second_series["total_playtime_minutes"] / 60, 1)
                        response += f"Fascinating - this significantly exceeds the second-ranked '{second_series['series_name']}' series at {second_hours} hours. I could analyze her complete franchise chronology or compare series completion patterns if you require additional data."
                    else:
                        response += "I could examine her complete gaming franchise analysis or compare series engagement patterns if you require additional mission data."

                    # Apply sarcastic modifications for Pops Arcade and smart truncation
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    response = smart_truncate_response(response)
                    await message.reply(response)
                else:
                    response = "Database analysis complete. Insufficient playtime data available for series ranking. Mission parameters require more comprehensive temporal logging."
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    await message.reply(response)
            else:
                # Handle individual game playtime query - USE ALL GAMES, not just completed
                games_by_playtime = db.get_games_by_playtime('DESC')  # type: ignore - FIXED: now uses all games
                if games_by_playtime:
                    top_game = games_by_playtime[0]
                    total_hours = round(
                        top_game['total_playtime_minutes'] / 60, 1)
                    episodes = top_game['total_episodes']
                    game_name = top_game['canonical_name']

                    response = f"Database analysis indicates '{game_name}' demonstrates maximum temporal investment: {total_hours} hours across {episodes} episodes. "

                    # Add conversational follow-up
                    if len(games_by_playtime) > 1:
                        response += f"Would you like me to analyze her other marathon gaming sessions or compare completion patterns for lengthy {top_game.get('genre', 'similar')} games?"
                    else:
                        response += "I can provide comparative analysis of her completion efficiency trends if you require additional data."

                    # Apply sarcastic modifications for Pops Arcade
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    await message.reply(response)
                else:
                    response = "Database analysis complete. Insufficient playtime data available for individual game ranking. Temporal logging requires enhancement."
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    await message.reply(response)

        elif "highest average" in lower_content and "per episode" in lower_content:
            # Handle average episode length query
            avg_stats = db.get_games_by_average_episode_length()  # type: ignore
            if avg_stats:
                top_game = avg_stats[0]
                avg_minutes = top_game['avg_minutes_per_episode']
                game_name = top_game['canonical_name']
                episodes = top_game['total_episodes']

                response = f"Statistical analysis indicates '{game_name}' demonstrates highest temporal density per episode: {avg_minutes} minutes average across {episodes} episodes. "

                # Add conversational follow-up
                if len(avg_stats) > 1:
                    response += f"Intriguing patterns emerge when comparing this to her other extended gaming sessions. I could analyze episode length distributions or examine pacing preferences across different genres if you require deeper analysis."
                else:
                    response += "I can examine her episode pacing patterns or compare temporal efficiency across different game types if additional analysis is required."

                await message.reply(response)
            else:
                await message.reply("Database analysis complete. Insufficient episode duration data for statistical ranking. Mission parameters require enhanced temporal metrics.")

        elif "most episodes" in lower_content:
            # Check for a series/genre filter in the query
            filter_match = re.search(r"of\s+the\s+([a-zA-Z0-9\s:]+)\s+series", lower_content) or \
                re.search(r"which\s+([a-zA-Z0-9\s:]+)\s+game", lower_content)
            parameter = filter_match.group(1).strip() if filter_match else None

            answer = db.calculate_dynamic_answer("most_episodes", parameter)

            if answer:
                # We need to fetch the full game data to get the episode count for the response
                game_data = db.get_played_game(answer)
                episodes = game_data.get('total_episodes',
                                         'an unknown number of') if game_data else 'an unknown number of'

                if parameter:
                    await message.reply(f"Analysis complete. Within the '{parameter.title()}' series, '{answer}' has the most episodes with {episodes}.")
                else:
                    await message.reply(f"Database confirms '{answer}' holds the maximum episode count with {episodes} episodes.")
            else:
                await message.reply("Database analysis complete. No episode data available for this query.")

        elif any(word in lower_content for word in ["shortest", "fewest", "least"]) and any(word in lower_content for word in ["playtime", "hours"]):
            games = db.get_games_by_playtime("ASC", limit=1)
            if games:
                game = games[0]
                hours = round(game['total_playtime_minutes'] / 60, 1)
                await message.reply(f"Database analysis indicates '{game['canonical_name']}' represents the shortest playthrough at {hours} hours.")
            else:
                await message.reply("Database analysis complete. Insufficient playtime data for analysis.")

        elif any(word in lower_content for word in ["fewest", "shortest", "least"]) and "episodes" in lower_content:
            games = db.get_games_by_episode_count("ASC", limit=1)
            if games:
                game = games[0]
                await message.reply(f"Analysis complete. '{game['canonical_name']}' has the fewest episodes with {game['total_episodes']}.")
            else:
                await message.reply("Database analysis complete. Insufficient episode data for analysis.")

        elif ("first" in lower_content or "earliest" in lower_content) and "game" in lower_content and "played" in lower_content:
            games = db.get_games_by_played_date("ASC", limit=1)
            if games:
                game = games[0]
                play_date = game['first_played_date'].strftime('%B %Y')
                await message.reply(f"According to mission logs, the first recorded game played was '{game['canonical_name']}' in {play_date}.")
            else:
                await message.reply("Temporal analysis failed. No valid 'first played' dates found in the archives.")

        elif ("most recent" in lower_content or "latest" in lower_content) and "game" in lower_content:
            games = db.get_games_by_played_date("DESC", limit=1)
            if games:
                game = games[0]
                play_date = game['first_played_date'].strftime('%B %Y')
                await message.reply(f"The most recently archived game is '{game['canonical_name']}', first played in {play_date}.")
            else:
                await message.reply("Temporal analysis failed. No valid 'first played' dates found in the archives.")

        elif "oldest" in lower_content and "game" in lower_content:
            games = db.get_games_by_release_year("ASC", limit=1)
            if games:
                game = games[0]
                await message.reply(f"Analysis of historical data indicates the oldest game played is '{game['canonical_name']}', released in {game['release_year']}.")
            else:
                await message.reply("Historical analysis failed. No valid release year data found.")

        elif ("most common" in lower_content or "most played" in lower_content) and "genre" in lower_content:
            stats = db.get_genre_statistics()
            if stats:
                top_genre = stats[0]
                await message.reply(f"Statistical analysis indicates the most engaged genre is **{top_genre['genre'].title()}** with {top_genre['game_count']} titles played.")
            else:
                await message.reply("Genre analysis failed. Insufficient data in the archives.")

        elif ("longest" in lower_content and "complete" in lower_content):
            # Handle longest COMPLETED games specifically
            completion_stats = db.get_longest_completion_games()  # type: ignore
            if completion_stats:
                top_game = completion_stats[0]
                if top_game['total_playtime_minutes'] > 0:
                    hours = round(top_game['total_playtime_minutes'] / 60, 1)
                    episodes = top_game['total_episodes']
                    game_name = top_game['canonical_name']

                    response = f"Database analysis: '{game_name}' demonstrates maximum temporal investment among completed games with {hours} hours"
                    if episodes > 0:
                        response += f" across {episodes} episodes"
                    response += ". "

                    # Add conversational follow-up
                    if len(completion_stats) > 1:
                        second_game = completion_stats[1]
                        second_hours = round(second_game['total_playtime_minutes'] / 60, 1)
                        response += f"This significantly exceeds the second-longest completed game '{second_game['canonical_name']}' at {second_hours} hours."

                    await message.reply(response)
                else:
                    await message.reply("Database analysis complete. Insufficient playtime data for completed games.")
            else:
                await message.reply("Database analysis complete. No completed games with playtime data found.")

        elif ("longest" in lower_content and "game" in lower_content) or \
             ("most" in lower_content and ("hours" in lower_content or "playtime" in lower_content)) or \
             ("most" in lower_content and "game" in lower_content and any(word in lower_content for word in ["played", "play", "playing"])):

            # Handle ambiguous "most played" queries by providing both metrics
            playtime_stats = db.get_games_by_playtime('DESC', limit=1)
            episode_stats = db.get_games_by_episode_count('DESC', limit=1)

            if not playtime_stats and not episode_stats:
                await message.reply("Database analysis complete. Insufficient playtime and episode data available for engagement ranking.")
                return

            response = "Analysis complete. The term 'most played' can be interpreted in two ways:\n\n"

            if playtime_stats:
                top_playtime_game = playtime_stats[0]
                hours = round(top_playtime_game['total_playtime_minutes'] / 60, 1)
                response += f"▶️ **By Playtime:** '{top_playtime_game['canonical_name']}' has the most playtime with **{hours} hours**.\n"

            if episode_stats:
                top_episode_game = episode_stats[0]
                episodes = top_episode_game['total_episodes']
                response += f"▶️ **By Episodes:** '{top_episode_game['canonical_name']}' has the most episodes with **{episodes} parts**."

            response += "\n\nPlease specify which metric you require for further analysis."

            # NEW: Store clarification state in context (Issue #1 Fix)
            context = get_or_create_context(message.author.id, message.channel.id)
            context.set_pending_clarification("playtime_vs_episodes", {
                'playtime_stats': db.get_games_by_playtime('DESC', limit=5),
                'episode_stats': db.get_games_by_episode_count('DESC', limit=5)
            })

            await message.reply(response)

    except Exception as e:
        print(f"Error in statistical query: {e}")
        await message.reply("Database analysis encountered an anomaly. Statistical processing systems require recalibration.")