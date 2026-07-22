import re
from typing import Any, Match, Optional, Tuple

import discord

from ...config import GAME_RECOMMENDATION_CHANNEL_ID, POPS_ARCADE_USER_ID
from ...database import get_database
from ...utils.text_processing import smart_truncate_response
from ..message_handler import get_user_communication_tier

db = get_database()


async def handle_genre_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle genre and series queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Genre/series queries unavailable.")
        return

    query_term = match.group(1).strip()

    # Check if it's a genre query
    common_genres = [
        'action', 'rpg', 'adventure', 'horror', 'puzzle', 'strategy', 'racing',
        'sports', 'fighting', 'platformer', 'shooter', 'simulation'
    ]
    if any(genre in query_term.lower() for genre in common_genres):
        try:
            genre_games = db.get_games_by_genre_flexible(  # type: ignore
                query_term)
            if genre_games:
                game_list = []
                for game in genre_games[:8]:  # Limit to 8 games
                    episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                        "total_episodes", 0) > 0 else ""
                    status = game.get("completion_status", "unknown")
                    status_emoji = {
                        "completed": "✅",
                        "ongoing": "🔄",
                        "dropped": "❌",
                        "unknown": "❓"}.get(
                        status,
                        "❓")
                    game_list.append(
                        f"{status_emoji} {game['canonical_name']}{episodes}")

                games_text = ", ".join(game_list)
                if len(genre_games) > 8:
                    games_text += f" and {len(genre_games) - 8} more"

                # NEW: Store full results in context for "show all" follow-up (Issue #2 Fix)
                context = get_or_create_context(message.author.id, message.channel.id)
                context.store_full_query_results(genre_games, "genre", query_term)

                await message.reply(f"Database analysis: Captain Jonesy has engaged {len(genre_games)} {query_term} games. Her archives contain: {games_text}.")
            else:
                await message.reply(f"Database scan complete. No {query_term} games found in Captain Jonesy's gaming archives.")
        except Exception as e:
            print(f"Error in genre query: {e}")

    # Check if it's a series query
    elif query_term:
        try:
            series_games = db.get_all_played_games(query_term)  # type: ignore
            if series_games:
                game_list = []
                for game in series_games[:8]:
                    episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                        "total_episodes", 0) > 0 else ""
                    year = f" ({game.get('release_year')})" if game.get(
                        "release_year") else ""
                    status = game.get("completion_status", "unknown")
                    status_emoji = {
                        "completed": "✅",
                        "ongoing": "🔄",
                        "dropped": "❌",
                        "unknown": "❓"}.get(
                        status,
                        "❓")
                    game_list.append(
                        f"{status_emoji} {game['canonical_name']}{year}{episodes}")

                games_text = ", ".join(game_list)
                if len(series_games) > 8:
                    games_text += f" and {len(series_games) - 8} more"

                # NEW: Store full results in context for "show all" follow-up (Issue #2 Fix)
                context = get_or_create_context(message.author.id, message.channel.id)
                context.store_full_query_results(series_games, "series", query_term.title())

                await message.reply(f"Database analysis: Captain Jonesy has engaged {len(series_games)} games in the {query_term.title()} series. Archives contain: {games_text}.")
            else:
                await message.reply(f"Database scan complete. No games found in the {query_term.title()} series within Captain Jonesy's gaming archives.")
        except Exception as e:
            print(f"Error in series query: {e}")


async def handle_year_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle year-based game queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Year-based queries unavailable.")
        return

    year = int(match.group(1))
    try:
        # Get games by release year
        all_games = db.get_all_played_games()  # type: ignore
        year_games = [
            game for game in all_games if game.get('release_year') == year]

        if year_games:
            game_list = []
            for game in year_games[:8]:
                episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                    "total_episodes", 0) > 0 else ""
                status = game.get("completion_status", "unknown")
                status_emoji = {
                    "completed": "✅",
                    "ongoing": "🔄",
                    "dropped": "❌",
                    "unknown": "❓"}.get(
                    status,
                    "❓")
                game_list.append(
                    f"{status_emoji} {game['canonical_name']}{episodes}")

            games_text = ", ".join(game_list)
            if len(year_games) > 8:
                games_text += f" and {len(year_games) - 8} more"

            await message.reply(f"Database analysis: Captain Jonesy has engaged {len(year_games)} games from {year}. Archives contain: {games_text}.")
        else:
            await message.reply(f"Database scan complete. No games from {year} found in Captain Jonesy's gaming archives.")
    except Exception as e:
        print(f"Error in year query: {e}")


async def handle_game_status_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle individual game status queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Game status queries unavailable.")
        return

    game_name = match.group(1).strip()
    game_name_lower = game_name.lower()

    # Check if the query matches a known series from our dynamic list
    is_series_query = False
    if not any(char.isdigit() for char in game_name):  # Don't trigger for "GTA 5"
        for series in _known_game_series:
            if series in game_name_lower:
                is_series_query = True
                break

    # Also check for generic patterns like "the new [game]" or just "[series
    # name]"
    if not is_series_query:
        generic_patterns = [
            r"^(the\s+)?new\s+",     # "the new God of War"
            r"^(the\s+)?latest\s+",  # "latest Call of Duty"
            r"^(the\s+)?recent\s+",  # "recent Final Fantasy"
        ]
        for generic_pattern in generic_patterns:
            if re.search(generic_pattern, game_name_lower):
                is_series_query = True
                break

    if is_series_query:
        # Get games from PLAYED GAMES database for series disambiguation
        series_games_data = db.get_series_games(game_name)

        if series_games_data:
            series_games_formatted = []
            available_game_names = []
            for game in series_games_data:
                episodes = f" ({game.get('total_episodes', 0)} episodes)" if game.get("total_episodes", 0) > 0 else ""
                status = game.get("completion_status", "unknown")
                series_games_formatted.append(f"'{game['canonical_name']}'{episodes} - {status}")
                available_game_names.append(game['canonical_name'])

            games_list = ", ".join(series_games_formatted)

            # Set disambiguation state in conversation context
            from ..context_manager import get_or_create_context
            context = get_or_create_context(message.author.id, message.channel.id)
            context.set_disambiguation_state(game_name.title(), "game_status", available_game_names)

            await message.reply(f"Database analysis indicates multiple entries exist in the '{game_name.title()}' series. Captain Jonesy's gaming archives contain: {games_list}. Specify which particular iteration you are referencing for detailed mission data.")
        else:
            await message.reply(f"Database scan complete. No entries found for '{game_name.title()}' series in Captain Jonesy's gaming archives. Either the series has not been engaged or requires more specific designation for accurate retrieval.")
        return

    # Search for the game in PLAYED GAMES database
    played_game = db.get_played_game(game_name)  # type: ignore

    if played_game:
        # Game found in played games database - enhanced response with
        # conversational follow-ups
        episodes = f" across {played_game.get('total_episodes', 0)} episodes" if played_game.get(
            'total_episodes', 0) > 0 else ""
        status = played_game.get('completion_status', 'unknown')

        status_text = {
            'completed': 'completed',
            'ongoing': 'ongoing',
            'dropped': 'terminated',
            'unknown': 'status unknown'
        }.get(status, 'status unknown')

        # Base response
        response = f"Affirmative. Captain Jonesy has played '{played_game['canonical_name']}'{episodes}, {status_text}. "

        # Add contextual follow-up suggestions based on game properties
        try:
            # Get ranking context for interesting facts
            ranking_context = db.get_ranking_context(  # type: ignore
                played_game["canonical_name"], "all")

            # Series-based suggestions
            if played_game.get(
                    "series_name") and played_game["series_name"] != played_game["canonical_name"]:
                series_games = db.get_all_played_games(  # type: ignore
                    played_game["series_name"])
                if len(series_games) > 1:
                    response += f"This marks her engagement with the {played_game['series_name']} franchise. I could analyze her complete {played_game['series_name']} chronology or compare this series against her other gaming preferences if you require additional data."
                else:
                    response += f"I can examine her complete gaming franchise analysis or compare series engagement patterns if you require additional mission data."

            # High episode count suggestions
            elif played_game.get("total_episodes", 0) > 15:
                if ranking_context and not ranking_context.get("error"):
                    episode_rank = ranking_context.get(
                        "rankings",
                        {}).get(
                        "episodes",
                        {}).get(
                        "rank",
                        0)
                    if episode_rank <= 5:
                        response += f"Fascinating - this ranks #{episode_rank} in her episode count metrics. I could analyze her other marathon gaming sessions or compare completion patterns for lengthy {played_game.get('genre', 'similar')} games if you require deeper analysis."
                    else:
                        response += f"This represents a significant gaming commitment with {played_game['total_episodes']} episodes. Would you like me to investigate her completion timeline patterns or examine her sustained engagement metrics?"
                else:
                    response += f"This represents a significant gaming commitment. I could analyze her other extended gaming sessions or examine completion efficiency patterns if additional data is required."

            # Recent/ongoing game suggestions
            elif status == 'ongoing':
                response += f"Mission status: ongoing. I can track her progress against typical completion metrics for similar titles or analyze her current gaming rotation if you require mission updates."

            # Completed game suggestions with interesting stats
            elif status == 'completed' and played_game.get('total_episodes', 0) > 0:
                if played_game['total_episodes'] <= 8:
                    response += f"Efficient completion detected - this falls within optimal episode range for focused gaming sessions. I can provide comparative analysis of similar pacing games or her completion efficiency trends if you require additional data."
                else:
                    response += f"Comprehensive completion achieved across {played_game['total_episodes']} episodes. Would you like me to investigate her completion timeline analysis or compare this against other {played_game.get('genre', 'similar')} gaming commitments?"

            # Default follow-up for other cases
            else:
                if played_game.get('youtube_playlist_url'):
                    response += "I can provide the YouTube playlist link or analyze additional mission parameters if you require further data."
                else:
                    response += "Additional mission parameters available upon request."

        except Exception as e:
            # Fallback if ranking context fails
            print(f"Error generating follow-up suggestions: {e}")
            response += "Additional mission parameters available upon request."

        await message.reply(response)
    else:
        # Game not found in played games database
        game_title = game_name.title()
        await message.reply(f"Database analysis complete. No records of Captain Jonesy engaging '{game_title}' found in gaming archives. Mission parameters indicate this title has not been processed.")


async def handle_game_details_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle specific game detail queries (playtime, duration, etc.)."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Game detail queries unavailable.")
        return

    game_name = match.group(1).strip()
    game_name_lower = game_name.lower()

    # Check if the query matches a known series from our dynamic list
    is_series_query = False
    if not any(char.isdigit() for char in game_name):  # Don't trigger for "GTA 5"
        for series in _known_game_series:
            if series in game_name_lower:
                is_series_query = True
                break

    # Also check for generic patterns
    if not is_series_query:
        generic_patterns = [
            r"^(the\s+)?new\s+", r"^(the\s+)?latest\s+", r"^(the\s+)?recent\s+"
        ]
        for generic_pattern in generic_patterns:
            if re.search(generic_pattern, game_name_lower):
                is_series_query = True
                break

    if is_series_query:
        # Get games from PLAYED GAMES database for series disambiguation
        series_games_data = db.get_series_games(game_name)

        if series_games_data:
            series_games_formatted = []
            available_game_names = []
            for game in series_games_data:
                episodes = f" ({game.get('total_episodes', 0)} episodes)" if game.get("total_episodes", 0) > 0 else ""
                status = game.get("completion_status", "unknown")
                series_games_formatted.append(f"'{game['canonical_name']}'{episodes} - {status}")
                available_game_names.append(game['canonical_name'])

            games_list = ", ".join(series_games_formatted)

            # Set disambiguation state in conversation context
            from ..context_manager import get_or_create_context
            context = get_or_create_context(message.author.id, message.channel.id)
            context.set_disambiguation_state(game_name.title(), "game_details", available_game_names)

            await message.reply(f"Database analysis indicates multiple entries exist in the '{game_name.title()}' series. Captain Jonesy's gaming archives contain: {games_list}. Specify which particular iteration you are referencing for detailed temporal analysis.")
            return

    # Search for the game in PLAYED GAMES database
    played_game = db.get_played_game(game_name)  # type: ignore

    if played_game:
        playtime_minutes = played_game.get('total_playtime_minutes', 0)
        episodes = played_game.get('total_episodes', 0)
        status = played_game.get('completion_status', 'unknown')
        canonical_name = played_game['canonical_name']

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

            response = f"Database analysis: Captain Jonesy invested {playtime_text} in '{canonical_name}'"

            if episodes > 0:
                avg_per_episode = round(playtime_minutes / episodes, 1)
                response += f" across {episodes} episodes (average: {avg_per_episode} minutes per episode)"

            response += f", completion status: {status}. "

            # Add contextual follow-up
            if status == 'completed':
                response += f"This represents a comprehensive gaming commitment. I could compare this against her other {status} titles or analyze completion efficiency patterns if you require additional data."
            elif status == 'ongoing':
                response += f"Mission status: ongoing. I can track progress metrics or provide estimated completion timeline analysis if you require mission updates."
            else:
                response += f"I can provide comparative analysis against similar games or examine her engagement patterns if additional data is required."

        else:
            # No playtime data available
            if episodes > 0:
                response = f"Database analysis: '{canonical_name}' engaged for {episodes} episodes, completion status: {status}. However, temporal data is insufficient - playtime metrics require enhancement for comprehensive analysis."
            else:
                response = f"Database analysis: '{canonical_name}' found in gaming archives, completion status: {status}. However, both temporal and episode data are insufficient for detailed analysis."

        await message.reply(response)
    else:
        # Game not found in played games database
        game_title = game_name.title()
        await message.reply(f"Database scan complete. No records of Captain Jonesy engaging '{game_title}' found in gaming archives. Temporal analysis unavailable for unprocessed titles.")


async def handle_recommendation_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle recommendation queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Recommendation queries unavailable.")
        return

    game_name = match.group(1).strip()

    # Search in recommendations database
    games = db.get_all_games()  # type: ignore
    found_game = None
    for game in games:
        if game_name.lower() in game["name"].lower(
        ) or game["name"].lower() in game_name.lower():
            found_game = game
            break

    if found_game:
        contributor = f" (suggested by {found_game['added_by']})" if found_game['added_by'] and found_game['added_by'].strip(
        ) else ""
        game_title = found_game['name'].title()
        await message.reply(f"Affirmative. '{game_title}' is catalogued in our recommendation database{contributor}. The suggestion has been logged for mission consideration.")
    else:
        game_title = game_name.title()
        await message.reply(f"Negative. '{game_title}' is not present in our recommendation database. No records of this title being suggested for mission parameters.")
