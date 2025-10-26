"""
Text Processing Utilities

Shared text processing functions for game name extraction and validation.
"""

import re
from typing import Optional


def cleanup_game_name(name: str) -> str:
    """
    Clean up extracted game name by removing extra whitespace and metadata.

    Args:
        name: Raw game name string

    Returns:
        Cleaned game name string
    """
    # Clean up whitespace and punctuation
    name = re.sub(r'\s+', ' ', name).strip()
    name = name.strip(' -|:')

    # Remove trailing metadata
    name = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', name, flags=re.IGNORECASE)

    return name


def is_generic_term(name: str) -> bool:
    """
    Check if extracted name is too generic to be a valid game title.

    Args:
        name: Game name to validate

    Returns:
        True if the name is a generic term, False otherwise
    """
    generic_terms = [
        'live', 'stream', 'streaming', 'gaming', 'playing',
        'game', 'gameplay', 'playthrough'
    ]
    return name.lower() in generic_terms


def extract_game_name_from_title(title: str) -> Optional[str]:
    """
    Extract game name from video/stream title using priority-based pattern matching.

    Handles common YouTube/Twitch streaming title formats with focus on reliable indicators
    like "(day X)", "(part X)", "(episode X)" that typically mark the actual game name.

    Examples:
    - "Samurai School Dropout - Ghost of Yotei (day 9) Thanks @playstation #ad/gift"
      → "Ghost of Yotei"
    - "First Time Playing: GAME NAME Road to X" → "GAME NAME"
    - "*DROPS* - GAME NAME Thanks @sponsor" → "GAME NAME"
    - "GAME NAME [COMPLETED]" → "GAME NAME" (preserves [COMPLETED] for playlist processing)

    Args:
        title: Video or stream title string

    Returns:
        Extracted game name or None if no valid name found
    """
    if not title or not isinstance(title, str):
        return None

    cleaned_title = title.strip()

    # PRIORITY 1: Extract game name that appears before day/part/episode indicators
    # These are the most reliable patterns as they explicitly mark ongoing series
    priority_patterns = [
        # Matches: "- Game Name (day 9)" or "| Game Name (day 9)"
        r'[-|]\s*([^-|()\[\]]+?)\s*\((?:day|part|episode|ep)\s+\d+\)',
        # Matches: "- Game Name [day 9]" or "| Game Name [day 9]"
        r'[-|]\s*([^-|()\[\]]+?)\s*\[(?:day|part|episode|ep)\s+\d+\]',
        # Matches without separator: "Game Name (day 9)"
        r'^([^-|()\[\]]+?)\s*\((?:day|part|episode|ep)\s+\d+\)',
        # Matches: "Game Name - day 9" (less parentheses version)
        r'[-|]\s*([^-|]+?)\s*-\s*(?:day|part|episode|ep)\s+\d+',
    ]

    for pattern in priority_patterns:
        match = re.search(pattern, cleaned_title, re.IGNORECASE)
        if match:
            game_name = match.group(1).strip()

            # Clean up trailing metadata (Thanks, @mentions, #hashtags, etc.)
            game_name = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', game_name, flags=re.IGNORECASE)
            game_name = re.sub(r'\s+(?:ft\.|feat\.|featuring).*$', '', game_name, flags=re.IGNORECASE)
            game_name = re.sub(r'\s*[|:]\s*$', '', game_name)  # Remove trailing separators

            # Final cleanup
            game_name = cleanup_game_name(game_name)

            # Validate extracted name
            if len(game_name) >= 2 and not is_generic_term(game_name):
                return game_name

    # PRIORITY 2: Look for clear game title before episode/part numbers
    # Handles formats like "Game Name - Episode 5" or "Game Name | Part 3"
    episode_patterns = [
        r'^([^-|]+?)\s*[-|]\s*(?:Episode|Part|Ep|Stream|VOD)\s*[#\d]',
        r'^([^-|]+?)\s*[-|]\s*S\d+E\d+',  # Season/Episode format
    ]

    for pattern in episode_patterns:
        match = re.search(pattern, cleaned_title, re.IGNORECASE)
        if match:
            game_name = match.group(1).strip()
            game_name = cleanup_game_name(game_name)
            if len(game_name) >= 2 and not is_generic_term(game_name):
                return game_name

    # PRIORITY 3: Remove common prefixes
    prefix_patterns = [
        r'^\*?(DROPS?|NEW|SPONSORED?|LIVE)\*?\s*[-:]?\s*',
        r'^First Time Playing:?\s*',
        r'^Let\'?s Play:?\s*',
        r'^Playing:?\s*',
        r'^Stream(?:ing)?:?\s*',
        r'^Gameplay:?\s*',
        r'^Playthrough:?\s*',
    ]

    for pattern in prefix_patterns:
        cleaned_title = re.sub(pattern, '', cleaned_title, flags=re.IGNORECASE)

    # PRIORITY 4: General cleanup (preserve [COMPLETED] for YouTube playlist detection)
    # Remove episode information in parentheses
    cleaned_title = re.sub(r'\s*\([^)]*(?:day|part|episode|ep|pt)\s*\d+[^)]*\)', '', cleaned_title, flags=re.IGNORECASE)

    # Remove episode titles after dash if followed by capital letter
    match = re.match(r'^([^-]+?)\s*-\s*[A-Z]', cleaned_title)
    if match:
        potential_game = match.group(1).strip()
        if len(potential_game) > 3:
            cleaned_title = potential_game

    # Remove suffix annotations
    suffix_patterns = [
        r'\s+Road to [^-]+$',
        r'\s+Thanks?(?:\s+to)?\s+@\w+.*$',
        r'\s+(?:End|Final) Game\??$',
        r'\s+#\w+(?:\s+#\w+)*$',
        r'\s+\*.*\*$',
        r'\s+[-|]\s*(?:Episode|Part|Ep)\s*\d+.*$',
        r'\s+[-|]\s*#\d+.*$',
        r'\s+S\d+E\d+.*$',
    ]

    for pattern in suffix_patterns:
        cleaned_title = re.sub(pattern, '', cleaned_title, flags=re.IGNORECASE)

    # Remove parentheses content (but preserve [COMPLETED] in brackets for YouTube)
    cleaned_title = re.sub(r'\s*\([^)]*\)', '', cleaned_title)

    # Final cleanup
    cleaned_title = cleanup_game_name(cleaned_title)

    # Validation
    if len(cleaned_title) < 3 or is_generic_term(cleaned_title):
        return None

    # Reject if mostly special characters
    alpha_chars = sum(c.isalnum() for c in cleaned_title)
    if alpha_chars < len(cleaned_title) * 0.5:
        return None

    return cleaned_title
