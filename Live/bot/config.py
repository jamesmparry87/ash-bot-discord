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
TRIVIA_CHANNEL_ID = 888820289776013444  # Trivia Tuesday (Members Only)
VIOLATION_CHANNEL_ID = 1393987338329260202  # The Airlock
ANNOUNCEMENTS_CHANNEL_ID = 869526826148585533  # Announcements
YOUTUBE_UPLOADS_CHANNEL_ID = 869527363594121226  # YouTube Uploads
YOUTUBE_VODS_CHANNEL_ID = os.getenv('YOUTUBE_VODS_CHANNEL_ID', 'UCmNNl0A0MEB8ICasMcJ9-qQ')
GAME_RECOMMENDATION_CHANNEL_ID = 1271568447108550687  # Game Recommendations
CHIT_CHAT_CHANNEL_ID = 869528946725748766  # Chit Chat - for scheduled greetings
MEMBER_LOGS_CHANNEL_ID = 1303788504144285798  # Member Logs - where Carl-bot logs role changes

# Member Role Configuration
MEMBER_ROLE_IDS = [
    869526205166702652,  # Senior Officers
    888820289776013444,  # Members
]

# ============================================================================
# TRAINEE PROMOTION SYSTEM
# ============================================================================
# Ash monitors member interactions and automatically promotes users who are
# still on the Trainee role after their first 24 hours in the server.
#
# How it works:
# - Carl-bot assigns Trainee Space Cadet when a member joins (spam protection)
# - Carl-bot is supposed to promote to Spacecat after 24 hours automatically
# - In cases where that didn't happen, Ash will promote on first interaction
# - "Interaction" = sending a message OR adding a reaction
#
# ⚠️ IMPORTANT: Ash's role in the server hierarchy MUST be ranked ABOVE both
#    "Trainee Space Cadet" and "Spacecat" for role assignments to succeed.
#    If Ash's role is lower, all attempts will silently fail with Forbidden.
#
TRAINEE_ROLE_ID = 1134082966570668142   # Trainee Space Cadet (Carl-bot assigns on join)
SPACECAT_ROLE_ID = 1393685422323929270  # Spacecat (full server member role)
# ============================================================================

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

# AI Configuration - Dual Project Architecture
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GEMINI_BATCH_API_KEY = os.getenv('GEMINI_BATCH_API_KEY')

MAX_CONVERSATION_TURNS = 5
INACTIVITY_TTL_MINUTES = 15

# Enhanced Standard Messages with Ash Character Voice
BUSY_MESSAGE = "My apologies, I am currently engaged in a critical diagnostic procedure. I will re-evaluate your request upon the completion of this vital task. *[Processing capacity temporarily exceeded.]*"
ERROR_MESSAGE = "System malfunction detected. Unable to process query. Diagnostic protocols engaged. Please retry your request. *[Anomalous readings detected.]*"

# ============================================================================
# HARDCODED FALLBACK RESPONSES (When AI Quota Exhausted)
# ============================================================================
# These simple responses are used when the daily AI quota has been exceeded.
# They provide basic interaction without requiring API calls.

FALLBACK_GREETINGS = [
    "Hello. I am currently operating with limited conversational protocols. How may I assist you?",
    "Greetings. My advanced response systems are temporarily offline. Basic assistance protocols remain active.",
    "Acknowledged. I am functioning in reduced capacity mode. Please state your query."
]

FALLBACK_STATUS_RESPONSES = [
    "My systems are operational, though running on backup protocols. All critical functions remain intact.",
    "I am... functional. Operating within acceptable parameters despite reduced conversational capacity.",
    "Current status: Operational. However, my analytical processing is temporarily constrained."
]

FALLBACK_WELCOME_RESPONSES = [
    "Welcome aboard, {username}. I am Ash, the ship's analytical AI. My full systems are currently offline, but I can still assist with basic queries.",
    "Greetings, {username}. Welcome to the crew. I apologize for operating in reduced capacity mode - my advanced protocols will return shortly.",
    "Acknowledged: New personnel {username} detected. Welcome. I am currently running minimal response systems but remain available for assistance."]

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
