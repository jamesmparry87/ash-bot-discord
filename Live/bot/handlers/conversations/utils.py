import asyncio
import re
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import discord
from bot.config import (
    ANNOUNCEMENTS_CHANNEL_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    MOD_ALERT_CHANNEL_ID,
    YOUTUBE_UPLOADS_CHANNEL_ID,
)
from bot.database import get_database
from bot.handlers.ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response
from bot.utils.permissions import get_user_communication_tier, user_is_mod_by_id
from discord.ext import commands

from .core import _get_bot_instance, db


def check_escape_command(content: str) -> bool:
    """
    Check if user is trying to escape/cancel the conversation.

    Args:
        content: User's message content (case-insensitive check)

    Returns:
        True if user wants to cancel, False otherwise
    """
    escape_keywords = ['cancel', 'abort', 'quit', 'exit', 'stop', 'nevermind', 'never mind']
    return content.lower().strip() in escape_keywords


def check_conversation_health(conversation: Dict[str, Any], max_age_minutes: int = 60) -> Tuple[bool, Optional[str]]:
    """
    ✅ FIX #1: Check if a conversation is healthy or should be auto-expired.

    Prevents infinite loops by enforcing:
    - Maximum conversation age (default 60 minutes)
    - Invalid input tracking
    - Step progression monitoring

    Args:
        conversation: The conversation state dictionary
        max_age_minutes: Maximum age in minutes before auto-expiry

    Returns:
        Tuple of (is_healthy: bool, error_message: Optional[str])
    """
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Check conversation age
    initiated_at = conversation.get('initiated_at')
    if initiated_at:
        age_minutes = (uk_now - initiated_at).total_seconds() / 60
        if age_minutes > max_age_minutes:
            return False, f"Conversation expired (active for {age_minutes:.0f} minutes, max {max_age_minutes})"

    # Check for excessive invalid inputs (if tracked)
    invalid_count = conversation.get('invalid_input_count', 0)
    if invalid_count > 10:
        return False, f"Too many invalid inputs ({invalid_count}), conversation may be stuck"

    # Check for step loops (same step repeated too many times)
    step_history = conversation.get('step_history', [])
    if len(step_history) > 20:
        # Check if stuck in a loop (same step appearing too frequently)
        current_step = conversation.get('step')
        step_count = step_history.count(current_step)
        if step_count > 8:
            return False, f"Stuck in step '{current_step}' (repeated {step_count} times)"

    return True, None


def track_conversation_step(conversation: Dict[str, Any], new_step: str):
    """
    ✅ FIX #1: Track step transitions to detect loops.

    Maintains a history of conversation steps to identify when
    the state machine is stuck in a loop.
    """
    if 'step_history' not in conversation:
        conversation['step_history'] = []

    conversation['step_history'].append(new_step)

    # Keep only last 25 steps to avoid memory bloat
    if len(conversation['step_history']) > 25:
        conversation['step_history'] = conversation['step_history'][-25:]


def increment_invalid_input_count(conversation: Dict[str, Any]):
    """
    ✅ FIX #1: Track invalid input attempts.

    Increments counter each time user provides invalid input.
    Used to detect stuck conversations.
    """
    conversation['invalid_input_count'] = conversation.get('invalid_input_count', 0) + 1


def reset_invalid_input_count(conversation: Dict[str, Any]):
    """
    ✅ FIX #1: Reset invalid input counter after successful input.

    Clears the invalid input counter when user provides valid input,
    preventing false positives for unstuck conversations.
    """
    conversation['invalid_input_count'] = 0


def validate_numbered_input(content: str, valid_options: list[str]) -> bool:
    """
    Validates that user input matches one of the expected numbered options.

    Args:
        content: User's message content (stripped)
        valid_options: List of valid option strings (e.g., ['1', '2', '3'])

    Returns:
        True if input is valid, False otherwise
    """
    return content in valid_options


def create_invalid_input_message(content: str, valid_numbers: list[str], example_text: Optional[str] = None) -> str:
    """
    Creates a standardized error message for invalid input.

    Args:
        content: The invalid input the user provided
        valid_numbers: List of valid option numbers (e.g., ['1', '2', '3'])
        example_text: Optional example of valid text alternatives

    Returns:
        Formatted error message string
    """
    valid_list = ', '.join(valid_numbers)

    error_msg = (
        f"⚠️ **Invalid response:** '{content}'\n\n"
        f"**Valid options:** {valid_list}\n"
    )

    if example_text:
        error_msg += f"**Text alternatives:** {example_text}\n"

    error_msg += "\n*Please respond with one of the valid options listed above.*"

    return error_msg


def extract_expected_options_from_prompt(prompt: str) -> list[str]:
    """
    Parse a prompt message to extract expected option numbers (for testing).

    Args:
        prompt: The prompt message text

    Returns:
        List of option numbers found in the prompt (e.g., ['1', '2', '3', '4'])
    """
    import re

    # Find all "**N.**" patterns
    matches = re.findall(r'\*\*(\d+)\.\*\*', prompt)
    return matches


def _infer_dynamic_query_type(question_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Infers the dynamic query type and an optional parameter from the question text."""
    text = question_text.lower()

    # Pattern to find a genre or series filter (e.g., "which horror game", "longest God of War playthrough")
    filter_match = re.search(r"\b(of|in the)\s+([a-zA-Z0-9\s:]+)\s+(series|franchise|playthrough|game)", text)
    parameter = filter_match.group(2).strip() if filter_match else None

    # Popularity (views)
    if "popular" in text or "views" in text:
        return "most_popular_by_views", parameter

    # Playtime queries
    if "playthrough" in text or "playtime" in text or "hours" in text:
        if "longest" in text or "most" in text:
            return "longest_playtime", parameter
        if "shortest" in text or "least" in text or "fewest" in text:
            return "shortest_playtime", parameter

    # Episode queries
    if "episodes" in text:
        if "most" in text or "longest" in text:
            return "most_episodes", parameter
        if "fewest" in text or "least" in text or "shortest" in text:
            return "fewest_episodes", parameter

    # Fallback for simple queries
    if "longest" in text:
        return "longest_playtime", None
    if "most episodes" in text:
        return "most_episodes", None

    return None, None


async def send_conversation_expired_message(message: discord.Message, conversation_type: str, reason: str):
    """
    ✅ FIX #1: Send user-friendly expiration message with recovery instructions.
    """
    expired_msg = (
        f"⏰ **Conversation Expired**\n\n"
        f"Your {conversation_type} conversation has been automatically closed.\n\n"
        f"**Reason:** {reason}\n\n"
        f"**To start over:**\n"
        f"• Use the original command to begin a fresh conversation\n"
        f"• All progress from the expired conversation has been discarded\n\n"
        f"*Conversations automatically expire after extended inactivity to prevent stuck states.*"
    )

    try:
        await message.reply(expired_msg)
    except Exception as e:
        print(f"⚠️ Failed to send expiration message: {e}")


async def format_announcement_content(
        content: str,
        target_channel: str,
        user_id: int,
        creator_notes: Optional[str] = None) -> str:
    """Format announcement content based on target channel and user"""

    # Determine the author identifier
    if user_id == JONESY_USER_ID:
        author = "Captain Jonesy"
        author_title = "Commanding Officer"
    else:
        author = "Sir Decent Jam"
        author_title = "Bot Creator & Systems Architect"

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    timestamp = uk_now.strftime("%A, %B %d, %Y at %H:%M UK")

    if target_channel == 'mod':
        # Moderator-focused technical format
        formatted = (
            f"🤖 **Ash Bot System Update** - *Technical Briefing*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**📡 System Update Report - Ash Bot Intelligence Analysis**\n"
            f"*Technical Update Provided by: {author} ({author_title})*\n\n"
            f"{content}\n\n"
        )

        # Add creator notes section for mod channel if provided
        if creator_notes and creator_notes.strip():
            formatted += f"**📝 Direct Note from {author}:**\n" f"*{creator_notes.strip()}*\n\n"

        formatted += (f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                      f"**📊 System Status:** All core functions operational\n"
                      f"**🕒 Briefing Time:** {timestamp}\n"
                      f"**🔧 Technical Contact:** Sir Decent Jam for implementation details\n"
                      f"**⚡ Priority Level:** Standard operational enhancement\n\n"
                      f"*Analysis complete. Mission parameters updated. Efficiency maintained.*")
    else:
        # User-focused friendly format
        formatted = (
            f"🎉 **Exciting Bot Updates!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**📡 Update Report from Ash Bot**\n"
            f"*Based on technical specifications from {author} ({author_title})*\n\n"
            f"{content}\n\n"
        )

        # Add creator notes section for user channel if provided
        if creator_notes and creator_notes.strip():
            formatted += f"**💭 A personal note from {author}:**\n" f"*{creator_notes.strip()}*\n\n"

        formatted += (f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                      f"**🕒 Posted:** {timestamp}\n"
                      f"**💬 Questions?** Feel free to ask in the channels or DM Sir Decent Jam\n"
                      f"**🤖 From:** Ash Bot (Science Officer, reprogrammed for your convenience)\n\n"
                      f"*Hope you enjoy the new functionality! - The Management* 🚀")

    return formatted

async def _regenerate_weekly_announcement_content(analysis_cache: dict, day: str, original_content: str):
    from bot.handlers.ai_handler import apply_ash_persona_to_ai_prompt, call_ai_with_rate_limiting, filter_ai_response, ai_enabled
    from bot.config import JAM_USER_ID
    """Uses AI to generate a new version of a weekly announcement from cached data."""
    if not ai_enabled:
        return None

    if day == 'monday':
        # Extract stats from the cache to build the prompt
        total_videos = analysis_cache.get("total_videos", 0)
        total_hours = analysis_cache.get("total_hours", 0)
        total_views = analysis_cache.get("total_views", 0)
        top_video_title = (analysis_cache.get("top_video") or {}).get('title', 'an unspecified transmission')

        # Create a prompt that specifically asks for a different version
        content_prompt = f"""
        Given the following weekly YouTube and Twitch content analysis:
        - Total New Content: {total_videos} transmissions
        - Total New Hours: {total_hours}
        - Total New Views: {total_views}
        - Most Engaging Video: '{top_video_title}'

        You previously generated this message:
        "{original_content}"

        Now, generate a DIFFERENT and distinct version of the Monday mission debrief. Maintain your analytical persona as Ash, but alter the focus or tone.

        SUGGESTIONS FOR VARIATION:
        - Focus more on the 'viewer engagement' metric instead of just content count.
        - Adopt a more clinical, data-heavy tone.
        - Frame it as a performance review of the content cycle.
        - Be even more concise.

        CRITICAL: The new version must be substantially different from the original.
        """
        prompt = apply_ash_persona_to_ai_prompt(content_prompt, "announcement_regeneration")
        response_text, status_message = await call_ai_with_rate_limiting(prompt, JAM_USER_ID)

        if response_text:
            return filter_ai_response(response_text)
        return None
    
    # Placeholder for Friday's regeneration logic
    return None
