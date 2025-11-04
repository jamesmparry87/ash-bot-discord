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
    - "Horror + Monsters = Cronos: A New Dawn" → "Cronos: A New Dawn"

    Args:
        title: Video or stream title string

    Returns:
        Extracted game name or None if no valid name found
    """
    if not title or not isinstance(title, str):
        return None

    cleaned_title = title.strip()

    # PRIORITY 0: Handle "=" separator for creative titles (e.g., "Episode Title = Game Name")
    # This is common for creative stream titles
    if '=' in cleaned_title:
        parts = cleaned_title.split('=')
        if len(parts) == 2:
            # Take everything after the "=" as the game name
            after_equals = parts[1].strip()
            # Remove day/episode markers
            after_equals = re.sub(r'\s*\((?:day|part|episode|ep)\s+\d+[^)]*\)', '', after_equals, flags=re.IGNORECASE)
            after_equals = re.sub(r'\s*\[(?:day|part|episode|ep)\s+\d+[^\]]*\]', '', after_equals, flags=re.IGNORECASE)
            # Remove common suffixes
            after_equals = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', after_equals, flags=re.IGNORECASE)
            after_equals = cleanup_game_name(after_equals)
            
            if len(after_equals) >= 3 and not is_generic_term(after_equals):
                return after_equals

    # PRIORITY 1: Extract game name that appears IMMEDIATELY before day/part/episode indicators
    # Match the LAST segment before the marker to avoid episode titles
    # Allow for optional text before "day" like "First Playthrough day 5"
    day_marker_match = re.search(r'\([^)]*(?:day|part|episode|ep)\s+\d+[^)]*\)', cleaned_title, re.IGNORECASE)
    bracket_marker_match = re.search(r'\[[^\]]*(?:day|part|episode|ep)\s+\d+[^\]]*\]', cleaned_title, re.IGNORECASE)
    
    if day_marker_match or bracket_marker_match:
        # Find the position of the marker (prioritize parentheses over brackets)
        if day_marker_match:
            marker_pos = day_marker_match.start()
        else:
            marker_pos = bracket_marker_match.start() if bracket_marker_match else 0
        
        # Extract everything before the marker
        before_marker = cleaned_title[:marker_pos].strip()
        
        # If there's a dash or pipe, take the LAST segment (closest to marker)
        if ' - ' in before_marker or ' | ' in before_marker:
            # Split by separators and take the last part
            parts = re.split(r'\s*[-|]\s*', before_marker)
            if parts:
                game_name = parts[-1].strip()  # Last part before the marker
            else:
                game_name = before_marker
        else:
            game_name = before_marker
        
        # Clean up trailing metadata
        game_name = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', game_name, flags=re.IGNORECASE)
        game_name = re.sub(r'\s+(?:ft\.|feat\.|featuring).*$', '', game_name, flags=re.IGNORECASE)
        game_name = cleanup_game_name(game_name)
        
        # Validate
        if len(game_name) >= 3 and not is_generic_term(game_name):
            # Reject short exclamatory phrases (episode titles)
            if len(game_name) < 25 and game_name.endswith('!') and game_name.count(' ') <= 5:
                pass  # Continue to fallback patterns
            else:
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
    # Remove episode information in parentheses and brackets
    cleaned_title = re.sub(r'\s*\([^)]*(?:day|part|episode|ep|pt)\s*\d+[^)]*\)', '', cleaned_title, flags=re.IGNORECASE)
    cleaned_title = re.sub(r'\s*\[(?:day|part|episode|ep|pt)\s*\d+[^\]]*\]', '', cleaned_title, flags=re.IGNORECASE)

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
    
    # Reject short exclamatory episode titles
    if len(cleaned_title) < 25 and cleaned_title.endswith('!') and cleaned_title.count(' ') <= 5:
        return None
    
    # Reject vague questions
    if cleaned_title.endswith('?') and len(cleaned_title) < 15:
        return None
    
    # Reject conversational episode titles (contains personal pronouns or emotions)
    conversational_words = ['you', 'i', 'me', 'we', 'scared', 'happy', 'sad', 'angry']
    words_lower = cleaned_title.lower().split()
    if len(words_lower) <= 6 and any(word in conversational_words for word in words_lower):
        # Only reject if it's relatively short and conversational
        return None

    return cleaned_title
