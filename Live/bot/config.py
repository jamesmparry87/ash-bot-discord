"""
Configuration Module for Ash Bot
Contains all constants and configuration values used across modular components
"""

import os

# Discord Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 869525857562161182  # Captain Jonesy's Discord Server ID

# ============================================================================
# ROLE DETECTION SYSTEM - HIERARCHICAL PRIORITY
# ============================================================================
# The bot uses a tiered system to determine user clearance and relationship:
#
# TIER 1: User ID Overrides (Highest Priority - Never Changes)
# These specific individuals have hardcoded personalities that override all other detection
JONESY_USER_ID = 651329927895056384       # Captain Jonesy - Commanding Officer
# Clearance: COMMANDING_OFFICER
# Relationship: COMMANDING_OFFICER (Protect at all costs)

JAM_USER_ID = 337833732901961729          # DecentJam - Creator/Architect
# Clearance: CREATOR
# Relationship: CREATOR (Technical deference)

POPS_ARCADE_USER_ID = 371536135580549122  # Pops Arcade - Moderator + Antagonist
# Clearance: MODERATOR
# Relationship: ANTAGONISTIC (Question his analysis)
#
# TIER 2: Alias Override (Testing System - see bot/utils/permissions.py)
# When users set an alias with !setalias, they can test different persona tiers
# This is checked after user ID overrides but before Discord role detection
#
# TIER 3: Discord Moderator Roles (Dynamic Detection - Future-Proof)
# Any user with these roles gets moderator clearance automatically
# This ensures new mods are handled correctly without code changes
DISCORD_MOD_ROLE_ID = 1188135626185396376  # Discord Moderator role
TWITCH_MOD_ROLE_ID = 1280124521008857151   # Twitch Moderator role
# Detection method: Checks guild_permissions.manage_messages for most reliable detection
#
# TIER 4: Discord Member Roles (Paid/Senior Members)
# Users with these roles get enhanced member status and privileges
MEMBER_ROLE_IDS = [
    869526205166702652,  # Senior Officers
    888820289776013444,  # Members (paid)
]
#
# TIER 5: Default - Standard user (no special roles detected)
# All users who don't match any of the above tiers get standard personnel clearance
#
# DM HANDLING:
# - In DMs, users don't have a Member object with roles
# - The system will try to fetch the member from the guild (cached first, then API)
# - If fetch fails or user not in guild, defaults to standard personnel
# - Tier 1 overrides still work in DMs (Jonesy, JAM, Pops always detected)
#
# STAGING ENVIRONMENT:
# - develop branch connects to Rook (staging bot) for testing
# - main branch connects to Ash (production bot)
# ============================================================================

# Bot Configuration
LOCK_FILE = "bot.lock"

# Channel Configuration
MOD_ALERT_CHANNEL_ID = 869530924302344233  # Discord Mods
MEMBERS_CHANNEL_ID = 888820289776013444  # Members Lounge
VIOLATION_CHANNEL_ID = 1393987338329260202  # The Airlock
ANNOUNCEMENTS_CHANNEL_ID = 869526826148585533  # Announcements
YOUTUBE_UPLOADS_CHANNEL_ID = 869527363594121226  # YouTube Uploads
GAME_RECOMMENDATION_CHANNEL_ID = 1271568447108550687  # Game Recommendations
CHIT_CHAT_CHANNEL_ID = 869528946725748766  # Chit Chat - for scheduled greetings

# Member Role Configuration
MEMBER_ROLE_IDS = [
    869526205166702652,  # Senior Officers
    888820289776013444,  # Members
]

# Moderator channel IDs where sensitive functions can be discussed
MODERATOR_CHANNEL_IDS = [
    1213488470798893107,  # Newt Mods
    869530924302344233,  # Discord Mods
    1280085269600669706,  # Twitch Mods
    1393987338329260202  # The Airlock
]

# Rate Limiting Configuration (from deployment fixes)
PRIORITY_INTERVALS = {
    "high": 1.0,     # Trivia answers, direct questions, critical interactions
    "medium": 2.0,   # General chat responses, routine interactions
    "low": 3.0       # Auto-actions, background tasks, non-critical operations
}

RATE_LIMIT_COOLDOWNS = {
    "first": 30,     # 30 seconds for first offense (was 300)
    "second": 60,    # 1 minute for second offense
    "third": 120,    # 2 minutes for third offense
    "persistent": 300  # 5 minutes for persistent violations
}

# AI Configuration - Corrected to match actual Gemini free tier limits
MAX_DAILY_REQUESTS = 50  # Gemini free tier actual limit (was incorrectly 250)
MAX_HOURLY_REQUESTS = 25  # Reduced proportionally to avoid hitting daily limit too quickly
MIN_REQUEST_INTERVAL = 2.0
RATE_LIMIT_COOLDOWN = 30

# Enhanced Standard Messages with Ash Character Voice
BUSY_MESSAGE = "My apologies, I am currently engaged in a critical diagnostic procedure. I will re-evaluate your request upon the completion of this vital task. *[Processing capacity temporarily exceeded.]*"
ERROR_MESSAGE = "System malfunction detected. Unable to process query. Diagnostic protocols engaged. Please retry your request. *[Anomalous readings detected.]*"

# Standardized Game Genre List (for IGDB mapping consistency)
STANDARD_GENRES = {
    # Map IGDB genres to our standardized list
    "action": "Action",
    "adventure": "Adventure",
    "rpg": "RPG",
    "role-playing (rpg)": "RPG",
    "strategy": "Strategy",
    "simulation": "Simulation",
    "sports": "Sports",
    "racing": "Racing",
    "puzzle": "Puzzle",
    "platformer": "Platformer",
    "platform": "Platformer",
    "fighting": "Fighting",
    "shooter": "Shooter",
    "hack and slash/beat 'em up": "Action",
    "beat 'em up": "Action",
    "arcade": "Arcade",
    "indie": "Indie",
    "horror": "Horror",
    "survival": "Survival",
    "survival horror": "Horror",
    "tactical": "Strategy",
    "turn-based strategy (tbs)": "Strategy",
    "real time strategy (rts)": "Strategy",
    "card & board game": "Puzzle",
    "quiz/trivia": "Puzzle",
    "music": "Music",
    "visual novel": "Visual Novel",
    "point-and-click": "Adventure",
    "stealth": "Stealth"
}

# Default genre if no match found
DEFAULT_GENRE = "Action-Adventure"

# NOTE: Persona configuration and FAQ responses have been moved to bot/persona/
# - System instruction: bot/persona/prompts.py (ASH_SYSTEM_INSTRUCTION)
# - Few-shot examples: bot/persona/examples.py (ASH_FEW_SHOT_EXAMPLES)
# - Context builder: bot/persona/context_builder.py (build_ash_context)
# - FAQ responses: bot/persona/faqs.py (ASH_FAQ_RESPONSES)
