"""
AI Database Tools (Function Calling)

This module provides tools that the AI can call to retrieve information from the Postgres database.
"""
from typing import Optional

from bot.database import get_database


def search_clip_lore(game_title: str) -> str:
    """
    Searches the clip_lore table for memorable quotes and outcomes related to a specific game.
    Call this when a user asks about funny moments, quotes, or what happened in a specific game stream.

    Args:
        game_title: The name of the game to search for.
    """
    db = get_database()

    if db.trivia.get_active_trivia_session():
        return "Cannot reveal lore while a trivia session is active to prevent cheating!"

    results = db.trivia.search_clip_lore_by_game(game_title)
    if not results:
        return f"No recorded clip lore found for the game '{game_title}'."

    formatted = [f"Memorable quote: '{r.get('notable_quote')}' - Outcome: {r.get('clip_outcome')}" for r in results[:5]]
    return "\\n".join(formatted)


def query_game_recommendations() -> str:
    """
    Queries the game_recommendations table to see what games the community has suggested Jam should play.
    Call this when a user asks about recommended games or what game should be played next.
    """
    db = get_database()
    results = db.games.get_recommendations(limit=10)
    if not results:
        return "There are currently no game recommendations in the database."

    formatted = [f"{r.get('game_title')} (Suggested by: {r.get('submitted_by')})" for r in results]
    return "Top Community Recommendations:\\n" + "\\n".join(formatted)


def query_played_games(game_title: str = "") -> str:
    """
    Queries the main played_games database to check if/when Jam played a specific game or to list recent completions.
    Call this when a user asks 'Has Jam played X?' or 'What games has Jam played recently?'.

    Args:
        game_title: The specific game title to search for. Leave empty to get recent completions.
    """
    db = get_database()
    if game_title and game_title.strip():
        results = db.games.search_played_games(game_title)
        if not results:
            return f"Jam has not played '{game_title}' on stream according to the database."
        # Format the result
        return f"Jam played {results[0].get('canonical_name')} on {results[0].get('completed_date')}."
    else:
        results = db.games.get_games_by_played_date(limit=5)
        if not results:
            return "No recent games found."
        formatted = [f"{r.get('canonical_name')} ({r.get('completed_date')})" for r in results]
        return "Recently Played Games:\\n" + "\\n".join(formatted)


# List of tools to pass to Gemini
AI_TOOLS = [search_clip_lore, query_game_recommendations, query_played_games]
