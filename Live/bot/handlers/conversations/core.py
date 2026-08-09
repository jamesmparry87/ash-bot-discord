import asyncio
import re
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..config import (
    ANNOUNCEMENTS_CHANNEL_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    MOD_ALERT_CHANNEL_ID,
    YOUTUBE_UPLOADS_CHANNEL_ID,
)
from ..database import get_database
from ..utils.permissions import get_user_communication_tier, user_is_mod_by_id
from .ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response

db = get_database()

_bot_instance = None


def initialize_conversation_handler(bot):
    """Initializes the conversation handler with a stable bot instance."""
    global _bot_instance
    _bot_instance = bot
    print("✅ Conversation handler initialized with bot instance.")


def _get_bot_instance():
    """Gets the globally stored bot instance for conversation handlers."""
    global _bot_instance
    if _bot_instance and _bot_instance.user:
        return _bot_instance
    print("❌ Bot instance not available for conversation handler.")
    return None


sync_approval_conversations = {}
