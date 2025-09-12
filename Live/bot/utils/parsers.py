"""
Data Parsers Module

Handles parsing and extracting structured data from various sources
"""

import re
from typing import Dict, Any, List, Optional, Union
from datetime import datetime


def parse_user_mention(text: str) -> Optional[int]:
    """Parse Discord user mention and return user ID"""
    mention_pattern = r'<@!?(\d+)>'
    match = re.search(mention_pattern, text)
    return int(match.group(1)) if match else None


def parse_channel_mention(text: str) -> Optional[int]:
    """Parse Discord channel mention and return channel ID"""
    channel_pattern = r'<#(\d+)>'
    match = re.search(channel_pattern, text)
    return int(match.group(1)) if match else None


def parse_role_mention(text: str) -> Optional[int]:
    """Parse Discord role mention and return role ID"""
    role_pattern = r'<@&(\d+)>'
    match = re.search(role_pattern, text)
    return int(match.group(1)) if match else None


def parse_all_mentions(text: str) -> Dict[str, List[int]]:
    """Parse all mentions from text and return categorized results"""
    user_mentions = []
    channel_mentions = []
    role_mentions = []
    
    # Find user mentions
    user_pattern = r'<@!?(\d+)>'
    for match in re.finditer(user_pattern, text):
        user_mentions.append(int(match.group(1)))
    
    # Find channel mentions
    channel_pattern = r'<#(\d+)>'
    for match in re.finditer(channel_pattern, text):
        channel_mentions.append(int(match.group(1)))
    
    # Find role mentions
    role_pattern = r'<@&(\d+)>'
    for match in re.finditer(role_pattern, text):
        role_mentions.append(int(match.group(1)))
    
    return {
        'users': user_mentions,
        'channels': channel_mentions,
        'roles': role_mentions
    }


def parse_command_arguments(content: str, command_prefix: str = "!") -> Dict[str, Any]:
    """Parse command and arguments from message content"""
    if not content.startswith(command_prefix):
        return {'command': None, 'args': [], 'full_text': content}
    
    # Remove prefix
    content_without_prefix = content[len(command_prefix):].strip()
    
    if not content_without_prefix:
        return {'command': None, 'args': [], 'full_text': content}
    
    parts = content_without_prefix.split()
    command = parts[0].lower() if parts else None
    args = parts[1:] if len(parts) > 1 else []
    
    return {
        'command': command,
        'args': args,
        'full_text': content_without_prefix
    }


def parse_key_value_args(args: List[str]) -> Dict[str, str]:
    """Parse key=value arguments from command arguments"""
    parsed = {}
    
    for arg in args:
        if '=' in arg:
            key, value = arg.split('=', 1)
            parsed[key.lower()] = value
        else:
            # Treat as boolean flag
            parsed[arg.lower()] = 'true'
    
    return parsed


def parse_quoted_strings(text: str) -> List[str]:
    """Parse quoted strings from text, respecting escape characters"""
    quoted_strings = []
    
    # Match both single and double quoted strings
    quote_pattern = r'(["\'])(?:(?=(\\?))\2.)*?\1'
    
    for match in re.finditer(quote_pattern, text):
        quoted_text = match.group(0)
        # Remove quotes and handle escape sequences
        unquoted = quoted_text[1:-1].replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
        quoted_strings.append(unquoted)
    
    return quoted_strings


def parse_urls(text: str) -> List[str]:
    """Extract URLs from text"""
    url_pattern = r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?'
    return re.findall(url_pattern, text, re.IGNORECASE)


def parse_discord_ids(text: str) -> List[int]:
    """Parse all Discord IDs (snowflakes) from text"""
    # Discord snowflakes are 17-19 digit numbers
    id_pattern = r'\b(\d{17,19})\b'
    matches = re.findall(id_pattern, text)
    return [int(match) for match in matches]


def parse_emoji_mentions(text: str) -> List[Dict[str, Any]]:
    """Parse custom emoji mentions from Discord text"""
    emoji_pattern = r'<(a?):([^:]+):(\d+)>'
    emojis = []
    
    for match in re.finditer(emoji_pattern, text):
        animated = bool(match.group(1))
        name = match.group(2)
        emoji_id = int(match.group(3))
        
        emojis.append({
            'animated': animated,
            'name': name,
            'id': emoji_id,
            'mention': match.group(0)
        })
    
    return emojis


def parse_game_title(title: str) -> Dict[str, Any]:
    """Parse game title to extract name, episode info, and other metadata"""
    result = {
        'original_title': title,
        'clean_name': title,
        'episode_number': None,
        'part_number': None,
        'season_info': None,
        'is_finale': False,
        'is_demo': False,
        'platform': None
    }
    
    # Remove common prefixes/suffixes and extract info
    working_title = title.strip()
    
    # Check for episode patterns
    episode_patterns = [
        r'\s*-\s*Episode\s*(\d+)',
        r'\s*-\s*Ep\.?\s*(\d+)',
        r'\s*-\s*Part\s*(\d+)',
        r'\s*-\s*#(\d+)',
        r'\s*\|\s*Episode\s*(\d+)',
        r'\s*\|\s*Ep\.?\s*(\d+)',
    ]
    
    for pattern in episode_patterns:
        match = re.search(pattern, working_title, re.IGNORECASE)
        if match:
            result['episode_number'] = int(match.group(1))
            working_title = re.sub(pattern, '', working_title, flags=re.IGNORECASE).strip()
            break
    
    # Check for season info
    season_pattern = r'\s*-\s*Season\s*(\d+)'
    season_match = re.search(season_pattern, working_title, re.IGNORECASE)
    if season_match:
        result['season_info'] = int(season_match.group(1))
        working_title = re.sub(season_pattern, '', working_title, flags=re.IGNORECASE).strip()
    
    # Check for special markers
    if re.search(r'\b(finale|final)\b', working_title, re.IGNORECASE):
        result['is_finale'] = True
    
    if re.search(r'\b(demo|trial)\b', working_title, re.IGNORECASE):
        result['is_demo'] = True
    
    # Check for platform indicators
    platform_patterns = {
        'PC': r'\b(PC|Steam|Epic)\b',
        'PlayStation': r'\b(PS\d|PlayStation|PSN)\b',
        'Xbox': r'\b(Xbox|XB\d)\b',
        'Nintendo': r'\b(Nintendo|Switch|3DS)\b',
        'Mobile': r'\b(iOS|Android|Mobile)\b'
    }
    
    for platform, pattern in platform_patterns.items():
        if re.search(pattern, working_title, re.IGNORECASE):
            result['platform'] = platform
            break
    
    # Clean the title
    result['clean_name'] = working_title.strip(' -|:')
    
    return result


def parse_time_duration(duration_str: str) -> Optional[int]:
    """Parse various time duration formats and return seconds"""
    if not duration_str:
        return None
    
    duration_str = duration_str.lower().strip()
    total_seconds = 0
    
    # Handle different formats
    patterns = [
        (r'(\d+)h(?:ours?)?', 3600),
        (r'(\d+)m(?:in(?:utes?)?)?', 60),
        (r'(\d+)s(?:ec(?:onds?)?)?', 1),
        (r'(\d+):(\d+):(\d+)', None),  # HH:MM:SS
        (r'(\d+):(\d+)', None),        # MM:SS
    ]
    
    for pattern, multiplier in patterns:
        matches = re.findall(pattern, duration_str)
        if matches:
            if multiplier:
                # Simple format (e.g., "2h", "30m")
                for match in matches:
                    total_seconds += int(match) * multiplier
            else:
                # Time format (HH:MM:SS or MM:SS)
                match = matches[0]
                if len(match) == 3:  # HH:MM:SS
                    hours, minutes, seconds = map(int, match)
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                elif len(match) == 2:  # MM:SS
                    minutes, seconds = map(int, match)
                    total_seconds = minutes * 60 + seconds
    
    return total_seconds if total_seconds > 0 else None


def parse_boolean(value: Union[str, bool, int]) -> bool:
    """Parse various representations of boolean values"""
    if isinstance(value, bool):
        return value
    
    if isinstance(value, int):
        return value != 0
    
    if isinstance(value, str):
        value = value.lower().strip()
        return value in ('true', '1', 'yes', 'on', 'enabled', 'y', 't')
    
    return False


def parse_number_with_suffixes(text: str) -> Optional[int]:
    """Parse numbers with K, M, B suffixes (e.g., '1.5K' -> 1500)"""
    pattern = r'(\d+(?:\.\d+)?)\s*([kmb])?'
    match = re.search(pattern, text.lower())
    
    if not match:
        return None
    
    number = float(match.group(1))
    suffix = match.group(2)
    
    multipliers = {'k': 1000, 'm': 1000000, 'b': 1000000000}
    
    if suffix:
        number *= multipliers.get(suffix, 1)
    
    return int(number)


def parse_list_from_text(text: str, delimiter: str = ',') -> List[str]:
    """Parse a delimited list from text, cleaning whitespace"""
    if not text:
        return []
    
    items = text.split(delimiter)
    return [item.strip() for item in items if item.strip()]


def parse_markdown_links(text: str) -> List[Dict[str, str]]:
    """Parse markdown-style links [text](url) from text"""
    link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    links = []
    
    for match in re.finditer(link_pattern, text):
        links.append({
            'text': match.group(1),
            'url': match.group(2),
            'full_match': match.group(0)
        })
    
    return links


def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """Extract code blocks from Discord markdown"""
    code_blocks = []
    
    # Multi-line code blocks
    multiline_pattern = r'```(?:(\w+)\n)?(.*?)```'
    for match in re.finditer(multiline_pattern, text, re.DOTALL):
        language = match.group(1) or ''
        code = match.group(2)
        code_blocks.append({
            'type': 'multiline',
            'language': language,
            'code': code,
            'full_match': match.group(0)
        })
    
    # Inline code blocks
    inline_pattern = r'`([^`]+)`'
    for match in re.finditer(inline_pattern, text):
        # Skip if it's part of a multiline code block
        if not any(match.start() >= block['full_match'].find(block['code']) and 
                  match.end() <= block['full_match'].find(block['code']) + len(block['code'])
                  for block in code_blocks if block['type'] == 'multiline'):
            code_blocks.append({
                'type': 'inline',
                'language': '',
                'code': match.group(1),
                'full_match': match.group(0)
            })
    
    return code_blocks


def clean_text_for_search(text: str) -> str:
    """Clean text for search by removing special characters and normalizing"""
    # Remove Discord mentions and formatting
    text = re.sub(r'<[@#&!]?\w*>', '', text)  # Mentions
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*(.*?)\*', r'\1', text)  # Italic
    text = re.sub(r'`(.*?)`', r'\1', text)  # Code
    text = re.sub(r'~~(.*?)~~', r'\1', text)  # Strikethrough
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text.lower()
