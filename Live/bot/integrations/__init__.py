"""
Integrations module for Ash Bot

This module contains integration handlers for external services like:
- YouTube integration for fetching video data and auto-posting
- Twitch integration for fetching VOD data and game analysis
- Other third-party service integrations

Phase 3 integrations extracted from main bot file.
"""

from . import youtube
from . import twitch

__all__ = ['youtube', 'twitch']
