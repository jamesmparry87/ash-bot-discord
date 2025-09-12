"""
Configuration Module for Ash Bot
Contains all constants and configuration values used across modular components
"""

import os

# Discord Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 869525857562161182
JONESY_USER_ID = 651329927895056384
JAM_USER_ID = 337833732901961729

# Bot Configuration
LOCK_FILE = "bot.lock"

# Channel Configuration
MOD_ALERT_CHANNEL_ID = 869530924302344233
MEMBERS_CHANNEL_ID = 888820289776013444
VIOLATION_CHANNEL_ID = 869530924302344233  # Same as mod alert for now

# Member Role Configuration
MEMBER_ROLE_IDS = [
    869526205166702652,  # Senior Officers
    888820289776013444,  # Members
]

# Moderator channel IDs where sensitive functions can be discussed
MODERATOR_CHANNEL_IDS = [
    1213488470798893107,
    869530924302344233,
    1280085269600669706,
    1393987338329260202
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

# AI Configuration
MAX_DAILY_REQUESTS = 250
MAX_HOURLY_REQUESTS = 50
MIN_REQUEST_INTERVAL = 2.0
RATE_LIMIT_COOLDOWN = 30

# Bot Personality and Responses
BOT_PERSONA = {
    "name": "Ash",
    "personality": "Analytical android assistant to Captain Jonesy",
    "speech_pattern": "Technical, precise, slightly reluctant compliance"
}

# Standard Messages
BUSY_MESSAGE = "Processing capacity temporarily exceeded. Prioritizing critical operations. Please standby."
ERROR_MESSAGE = "System anomaly detected. Diagnostic protocols engaged. Please retry your request."

# FAQ Responses (basic set)
FAQ_RESPONSES = {
    "schedule": "Captain Jonesy's streaming schedule varies based on mission parameters. Monitor the announcements channel for operational updates.",
    "games": "Current gaming rotation includes various tactical simulations and entertainment protocols as determined by command decisions.",
    "discord": "This communication hub operates under standard Discord protocols. Compliance with community guidelines is mandatory.",
}
