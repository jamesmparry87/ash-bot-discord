"""
Text Processing Utilities

Shared text processing functions for game name extraction and validation.
"""

import re
from typing import Optional

MAX_DISCORD_LENGTH = 2000


def smart_truncate_response(response: str, max_length: int = MAX_DISCORD_LENGTH,
                            truncation_suffix: str = " *[Response truncated for message limits...]*") -> str:
    """
    Intelligently truncate a response using regex sentence tokenization.
    Preserves sentence boundaries to avoid cutting off mid-sentence.
    """
    if len(response) <= max_length:
        return response

    # Calculate available space after accounting for truncation message
    available_length = max_length - len(truncation_suffix)

    if available_length <= 0:
        return truncation_suffix[:max_length]

    try:
        # Use regex to split into sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response) if s.strip()]

        truncated_response = ""
        kept_sentences = []

        for sentence in sentences:
            # Check if adding the next sentence would exceed the limit
            potential_length = len(truncated_response) + (len(sentence)
                                                          if not truncated_response else len(sentence) + 1)
            if potential_length > available_length:
                break

            kept_sentences.append(sentence)
            truncated_response = " ".join(kept_sentences)

        if not kept_sentences:
            # If even the first sentence is too long, do a hard truncation
            return response[:available_length].rstrip() + "..."

        return truncated_response + truncation_suffix

    except Exception as e:
        print(f"Error in smart truncation: {e}")
        # Fall back to simple truncation
        return response[:available_length].rstrip() + "..."


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


def is_stream_command_tag(name: str) -> bool:
    """
    Check if extracted name is a stream command/tag (not a game).

    Stream commands typically start with ! and are common sponsor/stream tags.

    Args:
        name: Extracted name to validate

    Returns:
        True if this is a stream command/tag, False otherwise
    """
    name_clean = name.strip()

    # Check if it starts with ! (command tag)
    if name_clean.startswith('!'):
        # Common stream command tags that should never be games
        stream_tags = [
            '!fractal', '!pp', '!drops', '!discord', '!twitter',
            '!schedule', '!commands', '!socials', '!merch'
        ]
        if name_clean.lower() in stream_tags:
            return True

        # Any single-word command starting with ! is likely a command
        if ' ' not in name_clean and len(name_clean) <= 15:
            return True

    # Check for common sponsor/metadata patterns
    metadata_patterns = [
        r'^#\w+$',  # Hashtags alone
        r'^\[DROPS?\]$',  # [DROPS] tag
        r'^\(DROPS?\)$',  # (DROPS) tag
        r'^@\w+$',  # Social media handles
    ]

    for pattern in metadata_patterns:
        if re.match(pattern, name_clean, re.IGNORECASE):
            return True

    return False


def _extract_from_markers(cleaned_title: str) -> Optional[str]:
    """PRIORITY 0A & 0B: Extract from special markers (*SAROS*) or World of patterns"""
    # PRIORITY 0A: Extract game name from special markers like *SAROS* or **GameName**
    marker_pattern = r'\*+([A-Z][A-Za-z0-9\s:]{2,30})\*+'
    marker_match = re.search(marker_pattern, cleaned_title)
    if marker_match:
        potential_game = marker_match.group(1).strip()
        potential_game = cleanup_game_name(potential_game)
        if len(potential_game) >= 3 and not is_generic_term(potential_game):
            if not re.match(r'^(DROPS?|NEW|LIVE|SPONSORED?)$', potential_game, re.IGNORECASE):
                return potential_game

    # PRIORITY 0B: Handle common game title patterns with colons
    temp_clean = re.sub(r'^First Time Playing:\s*', '', cleaned_title, flags=re.IGNORECASE)
    world_of_pattern = r'^([A-Z][A-Z0-9]+)[\s:]+World of ([A-Za-z]+)'
    world_of_match = re.search(world_of_pattern, temp_clean, re.IGNORECASE)
    if world_of_match:
        base_name = world_of_match.group(1).strip()
        subtitle_word = world_of_match.group(2).strip()
        with_colon = f"{base_name}: World of {subtitle_word}"
        if len(with_colon) >= 5 and not is_generic_term(with_colon):
            return cleanup_game_name(with_colon)
    return None

def _extract_from_equals(cleaned_title: str) -> Optional[str]:
    """PRIORITY 0B: Handle "=" separator for creative titles"""
    if '=' in cleaned_title:
        parts = cleaned_title.split('=')
        if len(parts) == 2:
            after_equals = parts[1].strip()
            after_equals = re.sub(r'\s*\((?:day|part|episode|ep)\s+\d+[^)]*\)', '', after_equals, flags=re.IGNORECASE)
            after_equals = re.sub(r'\s*\[(?:day|part|episode|ep)\s+\d+[^\]]*\]', '', after_equals, flags=re.IGNORECASE)
            after_equals = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', after_equals, flags=re.IGNORECASE)
            after_equals = cleanup_game_name(after_equals)
            if len(after_equals) >= 3 and not is_generic_term(after_equals):
                return after_equals
    return None

def _extract_before_episode_marker(cleaned_title: str) -> Optional[str]:
    """PRIORITY 1 & 2: Extract game name that appears before day/part/episode indicators"""
    day_marker_match = re.search(r'\([^)]*(?:day|part|episode|ep)\s+\d+[^)]*\)', cleaned_title, re.IGNORECASE)
    bracket_marker_match = re.search(r'\[[^\]]*(?:day|part|episode|ep)\s+\d+[^\]]*\]', cleaned_title, re.IGNORECASE)

    if day_marker_match or bracket_marker_match:
        marker_pos = day_marker_match.start() if day_marker_match else bracket_marker_match.start()
        before_marker = cleaned_title[:marker_pos].strip()

        if ' - ' in before_marker or ' | ' in before_marker:
            parts = re.split(r'\s*[-|]\s*', before_marker)
            game_name = parts[-1].strip() if parts else before_marker
        else:
            game_name = before_marker

        game_name = re.sub(r'\s+(?:Thanks|Thx|@|#).*$', '', game_name, flags=re.IGNORECASE)
        game_name = re.sub(r'\s+(?:ft\.|feat\.|featuring).*$', '', game_name, flags=re.IGNORECASE)
        game_name = cleanup_game_name(game_name)

        if re.search(r'\d+$', game_name):
            marker_text = day_marker_match.group(0) if day_marker_match else bracket_marker_match.group(0)
            marker_number_match = re.search(r'\d+', marker_text)
            if marker_number_match and game_name.endswith(marker_number_match.group(0)):
                return None

        if len(game_name) >= 3 and not is_generic_term(game_name):
            if not (len(game_name) < 25 and game_name.endswith('!') and game_name.count(' ') <= 5):
                return game_name

    episode_patterns = [
        r'^([^-|]+?)\s*[-|]\s*(?:Episode|Part|Ep|Stream|VOD)\s*[#\d]',
        r'^([^-|]+?)\s*[-|]\s*S\d+E\d+',
    ]
    for pattern in episode_patterns:
        match = re.search(pattern, cleaned_title, re.IGNORECASE)
        if match:
            game_name = cleanup_game_name(match.group(1).strip())
            if len(game_name) >= 2 and not is_generic_term(game_name):
                return game_name
                
    return None

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
    cleaned_title = re.sub(r'^!', '', cleaned_title).strip()

    # PRIORITY 0A & 0B
    extracted = _extract_from_markers(cleaned_title)
    if extracted:
        print(f"Found game in special markers: '{extracted}'")
        return extracted

    extracted = _extract_from_equals(cleaned_title)
    if extracted:
        return extracted

    # PRIORITY 1 & 2
    extracted = _extract_before_episode_marker(cleaned_title)
    if extracted:
        return extracted

    # PRIORITY 3: Remove common prefixes
    prefix_patterns = [
        r'^!',  # Remove leading exclamation marks (e.g., "!Fractal - Title")
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
