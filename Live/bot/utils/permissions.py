"""
User permissions and tier checking utilities
Handles user role detection, permission checking, and tier assignment
"""
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..config import JAM_USER_ID, JONESY_USER_ID, MEMBER_ROLE_IDS, MEMBERS_CHANNEL_ID, MODERATOR_CHANNEL_IDS

# Global state for tracking
member_conversation_counts: Dict[int, Dict[str, Any]] = {}
user_alias_state: Dict[int, Dict[str, Any]] = {}

# --- Member Conversation Tracking ---


def get_today_date_str() -> str:
    """Get today's date as a string for tracking daily limits"""
    return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")


def get_member_conversation_count(user_id: int) -> int:
    """Get today's conversation count for a member"""
    today = get_today_date_str()
    user_data = member_conversation_counts.get(user_id, {})

    # Reset count if it's a new day
    if user_data.get('date') != today:
        return 0

    return user_data.get('count', 0)


def increment_member_conversation_count(user_id: int) -> int:
    """Increment and return the conversation count for a member"""
    today = get_today_date_str()
    current_count = get_member_conversation_count(user_id)
    new_count = current_count + 1

    member_conversation_counts[user_id] = {'count': new_count, 'date': today}
    return new_count


def should_limit_member_conversation(
        user_id: int,
        channel_id: Optional[int]) -> bool:
    """Check if member conversation should be limited outside members channel"""
    # Check for active alias first - aliases are exempt from conversation
    # limits
    cleanup_expired_aliases()
    if user_id in user_alias_state:
        update_alias_activity(user_id)
        return False  # Aliases are exempt from conversation limits

    # No limits in the members channel
    if channel_id == MEMBERS_CHANNEL_ID:
        return False

    # No limits in DMs - treat DMs like the members channel for members
    if channel_id is None:  # DM channels have no ID
        return False

    # Check if they've reached their daily limit
    current_count = get_member_conversation_count(user_id)
    return current_count >= 5

# --- Alias System Helper Functions ---


def cleanup_expired_aliases():
    """Remove aliases inactive for more than 1 hour"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    cutoff_time = uk_now - timedelta(hours=1)
    expired_users = [
        user_id for user_id, data in user_alias_state.items()
        if data["last_activity"] < cutoff_time
    ]
    for user_id in expired_users:
        del user_alias_state[user_id]


def update_alias_activity(user_id: int):
    """Update last activity time for alias"""
    if user_id in user_alias_state:
        user_alias_state[user_id]["last_activity"] = datetime.now(
            ZoneInfo("Europe/London"))

# --- Permission Checking Functions ---


async def is_moderator_channel(channel_id: int) -> bool:
    """Check if a channel allows moderator function discussions"""
    return channel_id in MODERATOR_CHANNEL_IDS


async def user_is_mod(message: discord.Message) -> bool:
    """Check if user has moderator permissions"""
    if not message.guild:
        return False  # No mod permissions in DMs

    # Ensure we have a Member object (not just User)
    if not isinstance(message.author, discord.Member):
        return False

    member = message.author
    perms = member.guild_permissions
    return perms.manage_messages


async def user_is_mod_by_id(user_id: int,
                            bot: Optional[commands.Bot] = None) -> bool:
    """Check if user ID belongs to a moderator (for DM checks)"""
    if not bot:
        return False

    from ..config import GUILD_ID
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False

    try:
        member = await guild.fetch_member(user_id)
        return member.guild_permissions.manage_messages
    except (discord.NotFound, discord.Forbidden):
        return False


async def can_discuss_mod_functions(
    user: discord.User,
    channel: Optional[discord.TextChannel],
    bot: Optional[commands.Bot] = None
) -> bool:
    """Check if mod functions can be discussed based on user and channel"""
    # Always allow in DMs for authorized users
    if not channel:
        return user.id in [JONESY_USER_ID, JAM_USER_ID] or await user_is_mod_by_id(user.id, bot)

    # Check if channel allows mod discussions
    return await is_moderator_channel(channel.id)


async def user_is_member(message: discord.Message) -> bool:
    """Check if user has member role permissions"""
    if not message.guild:
        return False  # No member permissions in DMs

    # Ensure we have a Member object (not just User)
    if not isinstance(message.author, discord.Member):
        return False

    member = message.author
    member_roles = [role.id for role in member.roles]
    return any(role_id in MEMBER_ROLE_IDS for role_id in member_roles)


async def user_is_member_by_id(user_id: int,
                               bot: Optional[commands.Bot] = None) -> bool:
    """Check if user ID belongs to a member (for DM checks)"""
    if not bot:
        return False

    from ..config import GUILD_ID
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False

    try:
        member = await guild.fetch_member(user_id)
        member_roles = [role.id for role in member.roles]
        return any(role_id in MEMBER_ROLE_IDS for role_id in member_roles)
    except (discord.NotFound, discord.Forbidden):
        return False


async def get_user_communication_tier(
        message_or_ctx, bot: Optional[commands.Bot] = None) -> str:
    """Determine communication tier for user responses
    Accepts either discord.Message or commands.Context"""

    # Handle both Message and Context objects
    if hasattr(message_or_ctx, 'author'):
        user_id = message_or_ctx.author.id
        user = message_or_ctx.author
        guild = message_or_ctx.guild
    else:
        # Fallback - treat as user ID
        user_id = message_or_ctx
        user = None
        guild = None

    # First check for active alias (debugging only)
    cleanup_expired_aliases()
    if user_id in user_alias_state:
        update_alias_activity(user_id)
        alias_tier = user_alias_state[user_id]["alias_type"]
        return alias_tier

    # Normal tier detection
    if user_id == JONESY_USER_ID:
        return "captain"
    elif user_id == JAM_USER_ID:
        return "creator"
    elif guild and user and isinstance(user, discord.Member):
        # Check if user has mod permissions
        if user.guild_permissions.manage_messages:
            return "moderator"
        # Check if user has member roles
        member_roles = [role.id for role in user.roles]
        if any(role_id in MEMBER_ROLE_IDS for role_id in member_roles):
            return "member"
    elif guild:
        # For Context objects where we need to check permissions
        try:
            if hasattr(
                    message_or_ctx,
                    'author') and hasattr(
                    message_or_ctx.author,
                    'guild_permissions'):
                if message_or_ctx.author.guild_permissions.manage_messages:
                    return "moderator"

            # Check member roles for Context objects
            if hasattr(
                    message_or_ctx,
                    'author') and hasattr(
                    message_or_ctx.author,
                    'roles'):
                member_roles = [
                    role.id for role in message_or_ctx.author.roles]
                if any(role_id in MEMBER_ROLE_IDS for role_id in member_roles):
                    return "member"
        except AttributeError:
            pass

    return "standard"
