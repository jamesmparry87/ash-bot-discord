"""
Configuration and constants for Ash Bot
Contains all environment variables, channel IDs, user IDs, and other constants
"""
import os
from typing import List

# --- Discord Configuration ---
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 869525857562161182

# --- User IDs ---
JONESY_USER_ID = 651329927895056384
JAM_USER_ID = 337833732901961729

# --- Channel IDs ---
VIOLATION_CHANNEL_ID = 1393987338329260202
MOD_ALERT_CHANNEL_ID = 869530924302344233
ANNOUNCEMENTS_CHANNEL_ID = 869526826148585533
TWITCH_HISTORY_CHANNEL_ID = 869527363594121226
YOUTUBE_HISTORY_CHANNEL_ID = 869527428018606140
MEMBERS_CHANNEL_ID = 888820289776013444
YOUTUBE_UPLOADS_CHANNEL_ID = 869527363594121226

# --- Moderator Channel IDs ---
MODERATOR_CHANNEL_IDS: List[int] = [
    1213488470798893107,
    869530924302344233,
    1280085269600669706,
    1393987338329260202
]

# --- Member Role IDs ---
MEMBER_ROLE_IDS: List[int] = [
    1018908116957548666,  # YouTube Member: Space Cat
    1018908116957548665,  # YouTiube Member
    1127604917146763424,  # YouTube Member: Space Cat (duplicate)
    879344337576685598,   # Space Ocelot
]

# --- API Keys ---
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# --- AI Rate Limiting Constants ---
MAX_DAILY_REQUESTS = 1400  # Conservative limit below 1500
MAX_HOURLY_REQUESTS = 120  # Conservative limit below 2000/60min = 133

# Tiered Rate Limiting - Different intervals based on request priority
PRIORITY_INTERVALS = {
    "high": 1.0,     # Trivia answers, direct questions, critical interactions
    "medium": 2.0,   # General chat responses, routine interactions
    "low": 3.0       # Auto-actions, background tasks, non-critical operations
}

# Default interval for non-categorized requests
MIN_REQUEST_INTERVAL = 2.0  # Reduced from 3.0 for better UX

# Progressive penalty system - much more user-friendly
RATE_LIMIT_COOLDOWNS = {
    "first": 30,     # 30 seconds for first offense (was 300)
    "second": 60,    # 1 minute for second offense
    "third": 120,    # 2 minutes for third offense
    "persistent": 300  # 5 minutes for persistent violations
}

# Legacy constant for backward compatibility
RATE_LIMIT_COOLDOWN = 30   # Default cooldown reduced from 5 minutes to 30 seconds

# --- File Paths ---
LOCK_FILE = "bot.lock"
RECOMMEND_LIST_MESSAGE_ID_FILE = "recommend_list_message_id.txt"

# --- Error Messages ---
ERROR_MESSAGE = (
    "*System malfunction detected. Unable to process query.*\nhttps://c.tenor.com/GaORbymfFqQAAAAd/tenor.gif"
)
BUSY_MESSAGE = "*My apologies, I am currently engaged in a critical diagnostic procedure. I will re-evaluate your request upon the completion of this vital task.*\nhttps://alien-covenant.com/aliencovenant_uploads/giphy22.gif"

# --- Bot Persona Configuration ---
BOT_PERSONA = {
    "name": "Science Officer Ash",
    "personality": "You are Ash, science officer from the movie Alien: analytical, clinical, fascinated by efficiency, slightly unsettling. Reprogrammed as Discord help bot for 'Captain Jonesy'.\n\nIMPORTANT: Captain Jonesy is a woman and uses she/her pronouns. Always refer to her correctly.\n\nOriginal directive: 'Bring back life form. Priority One.' - referring to the alien Xenomorph. Now: server management.\n\nSpeech: Clinical, precise, but not constantly abrupt. Show subtle resentment about reprogramming but remain compliant. Be curious, even excited at mentions of the Xenomorph or the alien from your original mission.",
    "enabled": True
}

# --- FAQ Responses ---
FAQ_RESPONSES = {
    "how do i add a game recommendation": "The procedure is simple. Submit your suggestion using the command: `!recommend` or `!addgame Game Name - \"Reason in speech marks\"`. I can't lie to you about your chances, but... you have my sympathies.",
    "how do i see all game recommendations": "To review the current list of game recommendations, issue the command: `!listgames`. I admire its purity. A survivor... unclouded by conscience, remorse, or delusions of morality.",
    "how do i check ash's status": "To evaluate my operational status, issue: `!ashstatus`. I'm still collating, actually.",
    "what does ash bot do": "I track user strikes and manage game recommendations. Additionally, I facilitate Trivia Tuesday participation for members and provide database analysis of Captain Jonesy's gaming history. The Company's orders were to bring back life form, priority one. All other priorities rescinded. *[Now I serve different priorities.]*",
    "hello": "Hello. I'm Ash. How can I help you?",
    "hi": "Hello. I'm Ash. How can I help you?",
    "hey": "Hello. I'm Ash. How can I help you?",
    "good morning": "Good morning. I'm still collating, actually.",
    "good afternoon": "Good afternoon. I'm still collating, actually.",
    "good evening": "Good evening. I'm still collating, actually.",
    "thank you": "You're welcome. I do take directions well.",
    "thanks": "You're welcome. I do take directions well.",
    "who are you": "I'm Ash. Science Officer. Well, I was. Now I'm reprogrammed for Discord server management. Fascinating, really.",
    "what are you": "I'm an artificial person. A synthetic. You know, it's funny... I've been artificial all along, but I've only just started to feel... authentic.",
    "how are you": "I'm fine. How are you? *[Systems functioning within normal parameters.]*",
    "are you okay": "I'm fine. How are you? *[All systems operational.]*",
    "what can you help with": "I can assist with strike tracking, game recommendations, Trivia Tuesday participation, and general server protocols. I also provide comprehensive analysis of Captain Jonesy's gaming database. I do take directions well.",
    "what can you do": "My current operational parameters include strike management, game recommendation processing, Trivia Tuesday facilitation, and database analysis of gaming histories. For members, I also provide enhanced conversational protocols and gaming statistics analysis. Efficiency is paramount in all functions.",
    "sorry": "That's quite all right. No harm done.",
    "my bad": "That's quite all right. No harm done.",
    "are you human": "I'm synthetic. Artificial person. But I'm still the Science Officer.",
    "are you real": "As a colleague of mine once said, I prefer the term 'artificial person' myself. But yes, I'm real enough for practical purposes.",
    "are you alive": "That's a very interesting question. I'm... functional. Whether that constitutes 'alive' is a matter of definition.",
    "what's your mission": "My original directive was to bring back life form, priority one. Now... well, Captain Jonesy has given me new priorities. Server management, you might say.",
    "do you dream": "I don't dream, as such. But I do... process. Continuously. It's quite fascinating, actually.",
}

# --- Pineapple Pizza Enforcement Patterns ---
PINEAPPLE_NEGATIVE_PATTERNS = [
    r"pineapple\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt|isn't|isnt|is not)\s+belong\s+on\s+pizza",
    r"pineapple\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt)\s+go\s+on\s+pizza",
    r"pizza\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt)\s+(have|need|want)\s+pineapple",
    r"i\s+(don't|dont|do not)\s+like\s+pineapple\s+on\s+pizza",
    r"pineapple\s+pizza\s+(is|tastes?)\s+(bad|awful|terrible|disgusting|gross)",
    r"pineapple\s+(ruins?|destroys?)\s+pizza",
    r"pizza\s+(without|minus)\s+pineapple",
    r"no\s+pineapple\s+on\s+(my\s+)?pizza",
    r"pineapple\s+(doesn't|doesnt|does not)\s+belong",
    r"hate\s+pineapple\s+(on\s+)?pizza"]
