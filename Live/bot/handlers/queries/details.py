import re
from typing import Any, Match, Optional, Tuple

import discord

from ...config import GAME_RECOMMENDATION_CHANNEL_ID, POPS_ARCADE_USER_ID
from ...database import get_database
from ...utils.game_series import get_known_game_series
from ...utils.text_processing import smart_truncate_response
from ..context_manager import get_or_create_context
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
        match: Match[str]) -> bool:
    """Handle individual game status queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Game status queries unavailable.")
        return True

    game_name = match.group(1).strip()
    game_name_lower = game_name.lower()

    # Check if the query matches a known series from our dynamic list
    is_series_query = False
    if not any(char.isdigit() for char in game_name):  # Don't trigger for "GTA 5"
        for series in get_known_game_series():
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
            if len(series_games_data) == 1:
                # Auto-resolve single option disambiguation
                game_name = series_games_data[0]['canonical_name']
                is_series_query = False
            else:
                series_games_formatted = []
                available_game_names = []
                for game in series_games_data:
                    episodes = f" ({game.get('total_episodes', 0)} episodes)" if game.get(
                        "total_episodes", 0) > 0 else ""
                    status = game.get("completion_status", "unknown")
                    series_games_formatted.append(f"'{game['canonical_name']}'{episodes} - {status}")
                    available_game_names.append(game['canonical_name'])

                games_list = ", ".join(series_games_formatted)

                # Set disambiguation state in conversation context
                from ..context_manager import get_or_create_context
                context = get_or_create_context(message.author.id, message.channel.id)
                context.set_disambiguation_state(game_name.title(), "game_status", available_game_names)

                await message.reply(f"Database analysis indicates multiple entries exist in the '{game_name.title()}' series. Captain Jonesy's gaming archives contain: {games_list}. Specify which particular iteration you are referencing for detailed mission data.")
                return True
        else:
            return False

    # Search for the game in PLAYED GAMES database
    played_game = db.get_played_game(game_name)  # type: ignore

    if played_game:
        # Generate dynamic response using AI
        from ..ai_handler import call_ai_for_generation

        system_prompt = """You are Ash, the ship's AI computer. The user has asked if Captain Jonesy played a specific game or for its completion status.
Respond dynamically and concisely. Use the following data.
Game: {game_name}
Status: {status}
Episodes: {episodes}
Completed Date: {completed_date}
"""
        system_prompt = system_prompt.format(
            game_name=played_game['canonical_name'],
            status=played_game.get('completion_status', 'unknown'),
            episodes=played_game.get('total_episodes', 0),
            completed_date=played_game.get('completed_date', 'unknown')
        )

        response, _ = await call_ai_for_generation(system_prompt, message.content)
        if not response:
            response = f"Affirmative. Captain Jonesy has played '{played_game['canonical_name']}'."
        await message.reply(response)
        return True
    else:
        # Game not found in played games database
        return False


async def handle_game_details_query(
        message: discord.Message,
        match: Match[str]) -> bool:
    """Handle specific game detail queries (playtime, duration, etc.)."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Game detail queries unavailable.")
        return True

    game_name = match.group(1).strip()
    game_name_lower = game_name.lower()

    # Check if the query matches a known series from our dynamic list
    is_series_query = False
    if not any(char.isdigit() for char in game_name):  # Don't trigger for "GTA 5"
        for series in get_known_game_series():
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
            return True

    # Search for the game in PLAYED GAMES database
    played_game = db.get_played_game(game_name)  # type: ignore

    if played_game:
        from ..ai_handler import call_ai_for_generation

        system_prompt = """You are Ash, the ship's AI computer. The user is asking for details/playtime about a specific game Jonesy played.
Respond dynamically and concisely. Use the following data:
Game: {game_name}
Status: {status}
Episodes: {episodes}
Playtime (minutes): {playtime}
Completed Date: {completed_date}
"""
        system_prompt = system_prompt.format(
            game_name=played_game['canonical_name'],
            status=played_game.get('completion_status', 'unknown'),
            episodes=played_game.get('total_episodes', 0),
            playtime=played_game.get('total_playtime_minutes', 0),
            completed_date=played_game.get('completed_date', 'unknown')
        )

        response, _ = await call_ai_for_generation(system_prompt, message.content)
        if not response:
            response = f"Captain Jonesy has invested {played_game.get('total_playtime_minutes', 0)} minutes in '{played_game['canonical_name']}'."
        await message.reply(response)
        return True
    else:
        # Game not found
        return False


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
