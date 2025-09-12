"""
Text Formatters Module

Handles text formatting, display utilities, and content presentation
"""

from datetime import datetime
from typing import Any, Dict, List, Optional


def format_game_list(games: List[Dict[str,
                                      Any]],
                     max_display: int = 10,
                     show_episodes: bool = True,
                     show_playtime: bool = True) -> str:
    """Format a list of games for display"""
    if not games:
        return "No games found."

    formatted_games = []
    for i, game in enumerate(games[:max_display]):
        game_line = f"**{i+1}.** {game.get('canonical_name', 'Unknown Game')}"

        # Add episode info
        if show_episodes and game.get('total_episodes'):
            episodes = game['total_episodes']
            if episodes > 1:
                game_line += f" ({episodes} episodes)"

        # Add completion status
        if game.get('completion_status'):
            status = game['completion_status']
            if status != 'unknown':
                game_line += f" - *{status.title()}*"

        # Add playtime info
        if show_playtime and game.get('total_playtime_minutes'):
            playtime = game['total_playtime_minutes']
            hours = playtime // 60
            minutes = playtime % 60
            if hours > 0:
                game_line += f" - {hours}h {minutes}m"
            elif minutes > 0:
                game_line += f" - {minutes}m"

        formatted_games.append(game_line)

    result = "\n".join(formatted_games)

    # Add "and more" if there are additional games
    if len(games) > max_display:
        remaining = len(games) - max_display
        result += f"\n... and {remaining} more games"

    return result


def format_strike_list(
        strikes: List[Dict[str, Any]], show_details: bool = True) -> str:
    """Format a list of strikes for display"""
    if not strikes:
        return "No strikes found."

    formatted_strikes = []
    for i, strike in enumerate(strikes):
        strike_line = f"**{i+1}.** "

        # Add user info
        user_id = strike.get('user_id', 'Unknown')
        strike_line += f"<@{user_id}>"

        # Add reason if available
        if show_details and strike.get('reason'):
            reason = strike['reason'][:50]  # Truncate long reasons
            if len(strike['reason']) > 50:
                reason += "..."
            strike_line += f" - {reason}"

        # Add timestamp
        if strike.get('created_at'):
            timestamp = strike['created_at']
            if isinstance(timestamp, datetime):
                strike_line += f" ({timestamp.strftime('%Y-%m-%d')})"

        formatted_strikes.append(strike_line)

    return "\n".join(formatted_strikes)


def format_file_size(bytes_count: int) -> str:
    """Format file size in human-readable format"""
    size = float(bytes_count)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_duration(seconds: int) -> str:
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        else:
            return f"{minutes}m"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{hours}h"


def format_large_number(number: int) -> str:
    """Format large numbers with appropriate suffixes"""
    if number < 1000:
        return str(number)
    elif number < 1000000:
        return f"{number/1000:.1f}K"
    elif number < 1000000000:
        return f"{number/1000000:.1f}M"
    else:
        return f"{number/1000000000:.1f}B"


def format_percentage(value: float, total: float) -> str:
    """Format a value as a percentage of total"""
    if total == 0:
        return "0%"
    percentage = (value / total) * 100
    return f"{percentage:.1f}%"


def format_ai_response(response: str, max_length: int = 2000) -> str:
    """Format AI response with length limits and cleanup"""
    if not response:
        return "*No response generated.*"

    # Remove excessive whitespace
    cleaned = ' '.join(response.split())

    # Truncate if too long
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length - 3] + "..."

    return cleaned


def format_embed_description(text: str, max_length: int = 4096) -> str:
    """Format text for Discord embed description with proper length limits"""
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    # Try to cut at a sentence boundary
    truncated = text[:max_length - 3]
    last_sentence = truncated.rfind('.')
    last_space = truncated.rfind(' ')

    if last_sentence > max_length * 0.8:  # If we can cut at a sentence
        return truncated[:last_sentence + 1]
    elif last_space > max_length * 0.8:  # If we can cut at a word boundary
        return truncated[:last_space] + "..."
    else:
        return truncated + "..."


def format_list_with_bullets(items: List[str], bullet_style: str = "•") -> str:
    """Format a list of items with bullets"""
    if not items:
        return ""

    return "\n".join([f"{bullet_style} {item}" for item in items])


def format_table_row(columns: List[str], widths: List[int]) -> str:
    """Format a table row with proper column alignment"""
    formatted_cols = []
    for col, width in zip(columns, widths):
        if len(col) > width:
            col = col[:width - 3] + "..."
        formatted_cols.append(col.ljust(width))

    return "│".join(formatted_cols)


def format_progress_bar(
        current: int,
        total: int,
        width: int = 20,
        fill_char: str = "█",
        empty_char: str = "░") -> str:
    """Format a progress bar"""
    if total == 0:
        return empty_char * width

    filled_width = int((current / total) * width)
    empty_width = width - filled_width

    return fill_char * filled_width + empty_char * empty_width


def format_mention_list(user_ids: List[int], max_mentions: int = 10) -> str:
    """Format a list of user mentions"""
    if not user_ids:
        return "No users"

    mentions = [f"<@{user_id}>" for user_id in user_ids[:max_mentions]]
    result = ", ".join(mentions)

    if len(user_ids) > max_mentions:
        remaining = len(user_ids) - max_mentions
        result += f" and {remaining} more"

    return result


def format_code_block(code: str, language: str = "") -> str:
    """Format code in a Discord code block"""
    return f"```{language}\n{code}\n```"


def format_inline_code(code: str) -> str:
    """Format code inline"""
    return f"`{code}`"


def format_timestamp_relative(timestamp: datetime) -> str:
    """Format timestamp for Discord relative display"""
    unix_timestamp = int(timestamp.timestamp())
    return f"<t:{unix_timestamp}:R>"


def format_timestamp_datetime(timestamp: datetime) -> str:
    """Format timestamp for Discord datetime display"""
    unix_timestamp = int(timestamp.timestamp())
    return f"<t:{unix_timestamp}:F>"


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text with suffix if it exceeds max length"""
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def format_multiline_code(content: str, max_lines: int = 20) -> str:
    """Format multiline content as code with line limits"""
    lines = content.split('\n')

    if len(lines) > max_lines:
        displayed_lines = lines[:max_lines]
        displayed_lines.append(f"... ({len(lines) - max_lines} more lines)")
        content = '\n'.join(displayed_lines)

    return f"```\n{content}\n```"


def format_key_value_pairs(data: Dict[str, Any], separator: str = ": ") -> str:
    """Format key-value pairs for display"""
    formatted_pairs = []
    for key, value in data.items():
        formatted_key = key.replace('_', ' ').title()
        formatted_pairs.append(f"**{formatted_key}**{separator}{value}")

    return "\n".join(formatted_pairs)


def clean_markdown(text: str) -> str:
    """Clean markdown formatting from text"""
    import re

    # Remove markdown formatting
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*(.*?)\*', r'\1', text)      # Italic
    text = re.sub(r'`(.*?)`', r'\1', text)        # Code
    text = re.sub(r'~~(.*?)~~', r'\1', text)      # Strikethrough
    text = re.sub(r'__(.*?)__', r'\1', text)      # Underline

    return text


def format_error_message(error: str, context: Optional[str] = None) -> str:
    """Format error messages consistently"""
    base_message = f"❌ **Error:** {error}"

    if context:
        base_message += f"\n📍 **Context:** {context}"

    return base_message


def format_success_message(message: str, details: Optional[str] = None) -> str:
    """Format success messages consistently"""
    base_message = f"✅ **Success:** {message}"

    if details:
        base_message += f"\n📋 **Details:** {details}"

    return base_message
