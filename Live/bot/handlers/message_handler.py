"""
Message Handler Module

Handles the main message processing logic for the Discord bot, including:
- Strike detection and processing
- Pineapple pizza enforcement
- AI personality responses
- Query routing and database lookups
- FAQ responses and user tier detection
"""

import difflib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Match, Optional, Tuple
from zoneinfo import ZoneInfo

import discord
import nltk
from discord.ext import commands
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from ..config import (
    BUSY_MESSAGE,
    ERROR_MESSAGE,
    JAM_USER_ID,
    JONESY_USER_ID,
    MEMBERS_CHANNEL_ID,
    MOD_ALERT_CHANNEL_ID,
    POPS_ARCADE_USER_ID,
    VIOLATION_CHANNEL_ID,
)
from ..database import DatabaseManager, get_database
from ..persona.faq_handler import check_faq_match, get_role_aware_faq_response
from ..persona.faqs import ASH_FAQ_RESPONSES
from ..utils.permissions import (
    cleanup_expired_aliases,
    cleanup_expired_aliases_sync,
    get_member_conversation_count,
    get_user_communication_tier,
    increment_member_conversation_count,
    should_limit_member_conversation,
    user_is_mod_by_id,
)
from .ai_handler import (
    ai_enabled,
    call_ai_with_rate_limiting,
    filter_ai_response,
)
from .context_manager import (
    ConversationContext,
    cleanup_expired_contexts,
    detect_follow_up_intent,
    get_or_create_context,
    resolve_context_references,
    should_use_context,
)
from .conversation_handler import start_announcement_conversation

db: DatabaseManager = get_database()

# This will hold our dynamic and static series names
_known_game_series = set()


def initialize_series_list():
    """Fetches series from the DB and merges them with a static list."""
    global _known_game_series
    if not db:
        print("⚠️ Cannot initialize series list: Database not available.")
        return

    # Static list of other popular franchises as a fallback
    static_series_keywords = {
        "final fantasy", "call of duty", "assassin's creed", "the elder scrolls",
        "metal gear", "halo", "gears of war", "mass effect", "dragon age",
        "dark souls", "borderlands", "far cry", "bioshock", "tomb raider",
        "hitman", "battlefield", "mortal kombat", "street fighter", "tekken",
        "sonic", "kingdom hearts", "persona", "fire emblem"
    }

    # Dynamic list from the database
    db_series_names = set(db.get_all_unique_series_names())

    # Combine them
    _known_game_series = db_series_names.union(static_series_keywords)
    print(f"✅ Series list initialized with {len(_known_game_series)} unique series.")

# Initialize NLTK components with robust error handling


def initialize_nltk_resources():
    """Initialize NLTK resources with comprehensive error handling for deployment."""
    resources_to_download = [
        ('tokenizers/punkt', 'punkt'),
        ('tokenizers/punkt_tab', 'punkt_tab'),
        ('corpora/stopwords', 'stopwords'),
    ]

    for resource_path, resource_name in resources_to_download:
        try:
            nltk.data.find(resource_path)
            print(f"✅ NLTK resource '{resource_name}' found")
        except LookupError:
            try:
                print(f"📥 Downloading NLTK '{resource_name}' resource...")
                nltk.download(resource_name, quiet=True)
                print(f"✅ NLTK resource '{resource_name}' downloaded successfully")
            except Exception as download_error:
                print(f"⚠️ Failed to download NLTK '{resource_name}': {download_error}")
                print(f"   Bot will continue with degraded NLP functionality")


# Initialize NLTK resources on module load
try:
    initialize_nltk_resources()
except Exception as nltk_init_error:
    print(f"❌ NLTK initialization error: {nltk_init_error}")
    print("   Bot will continue with degraded NLP functionality")

# Constants for response handling
MAX_DISCORD_LENGTH = 2000
TRUNCATION_BUFFER = 80  # Buffer for truncation message


# Get database instance
db: DatabaseManager = get_database()


def smart_truncate_response(response: str, max_length: int = MAX_DISCORD_LENGTH,
                            truncation_suffix: str = " *[Response truncated for message limits...]*") -> str:
    """
    Intelligently truncate a response using NLTK sentence tokenization.
    Preserves sentence boundaries to avoid cutting off mid-sentence.
    """
    if len(response) <= max_length:
        return response

    # Calculate available space after accounting for truncation message
    available_length = max_length - len(truncation_suffix)

    if available_length <= 0:
        return truncation_suffix[:max_length]

    try:
        # Use NLTK to split into sentences
        sentences = nltk.sent_tokenize(response)

        truncated_response = ""
        kept_sentences = []

        for sentence in sentences:
            # Check if adding the next sentence would exceed the limit
            potential_length = len(truncated_response) + len(sentence)
            if potential_length > available_length:
                break

            kept_sentences.append(sentence)
            truncated_response = " ".join(kept_sentences)

        if not kept_sentences:
            # If even the first sentence is too long, do a hard truncation
            return response[:available_length].rstrip() + "..."

        return truncated_response + truncation_suffix

    except Exception as e:
        print(f"Error in smart truncation: {e}")
        # Fall back to simple truncation
        return response[:available_length].rstrip() + "..."


def enhance_query_parsing(query: str) -> Dict[str, Any]:
    """
    Use NLTK to enhance query understanding with tokenization and linguistic analysis.
    Returns enhanced query information for better pattern matching.
    """
    try:
        # Tokenize the query
        tokens = word_tokenize(query.lower())

        # Get stopwords for English
        stop_words = set(stopwords.words('english'))

        # Filter out stopwords to focus on key terms
        key_tokens = [token for token in tokens if token not in stop_words and token.isalpha()]

        # Identify potential game-related keywords
        gaming_keywords = {
            'game', 'games', 'played', 'play', 'playing', 'series', 'franchise',
            'episode', 'episodes', 'hour', 'hours', 'time', 'playtime', 'complete',
            'completed', 'finish', 'finished', 'jonesy', 'captain', 'longest',
            'shortest', 'most', 'genre', 'rpg', 'action', 'adventure', 'strategy'
        }

        gaming_terms = [token for token in key_tokens if token in gaming_keywords]
        non_gaming_terms = [token for token in key_tokens if token not in gaming_keywords]

        return {
            'original_query': query,
            'all_tokens': tokens,
            'key_tokens': key_tokens,
            'gaming_terms': gaming_terms,
            'potential_game_names': non_gaming_terms,
            'token_count': len(tokens),
            'key_token_count': len(key_tokens)
        }

    except Exception as e:
        print(f"Error in enhanced query parsing: {e}")
        return {
            'original_query': query,
            'all_tokens': [],
            'key_tokens': [],
            'gaming_terms': [],
            'potential_game_names': [],
            'token_count': 0,
            'key_token_count': 0
        }


def apply_pops_arcade_sarcasm(response: str, user_id: int) -> str:
    """Apply sarcastic modifications to responses for Pops Arcade (Robust Version)"""
    # NOTE: Assuming POPS_ARCADE_USER_ID is defined elsewhere, e.g., POPS_ARCADE_USER_ID = 123456789
    if user_id != POPS_ARCADE_USER_ID:
        return response

    MAX_DISCORD_LENGTH = 2000

    # Sarcastic replacements (no changes here)
    sarcastic_replacements = {
        "Database analysis": "Database analysis, regrettably,",
        "Affirmative": "I suppose that's... affirmative",
        "Analysis complete": "Analysis reluctantly complete",
        "Database scan complete": "Database scan complete, if you insist",
        "Mission parameters": "Mission parameters, begrudgingly",
        "Additional mission parameters available": "I suppose additional parameters are available, if required",
        "I can provide": "I suppose I can provide",
        "Would you like me to": "If you insist, I could",
        "Captain Jonesy has": "Captain Jonesy has, predictably,",
        "This represents": "This regrettably represents",
        "Fascinating": "Marginally interesting, I suppose",
        "Outstanding": "Adequate, I suppose",
        "Excellent": "Satisfactory, regrettably",
        "Their activity appears consistent": "Their activity appears... consistent, I suppose",
        "Their contributions lack a certain": "Their contributions lack a certain sophistication",
        "your struggles with trivia appear to be predictable": "your struggles with trivia appear to be... predictable, regrettably",
    }

    modified_response = response
    for original, sarcastic in sorted(sarcastic_replacements.items(), key=len, reverse=True):
        if original in modified_response:
            modified_response = modified_response.replace(original, sarcastic)

    # Regex fixes (no changes here)
    fixes = [
        (r'(\w+)\s+appears\.\s*$', r'\1 appears... adequate, I suppose.'),
        (r'(\w+)\s+consistent\.\s*$', r'\1 consistent, regrettably.'),
        (r'lack\s+a\s+certain\.\s*$', r'lack a certain... sophistication, predictably.'),
        (r'appear\s+to\s+be\.\s*$', r'appear to be... as expected, I suppose.'),
        (r'(\w+)\s+predictable\.\s*$', r'\1 predictable, unsurprisingly.'),
    ]
    for pattern, replacement in fixes:
        modified_response = re.sub(pattern, replacement, modified_response)

    # Sarcastic ending logic (no changes here)
    sarcastic_indicators = [
        "i suppose",
        "regrettably",
        "if you insist",
        "begrudgingly",
        "predictably",
        "unsurprisingly"]
    has_sarcastic_ending = any(indicator in modified_response.lower() for indicator in sarcastic_indicators)

    if not has_sarcastic_ending:
        if modified_response.strip().endswith(('.', '!', '?')):
            if modified_response.endswith("."):
                modified_response = modified_response[:-1] + ", I suppose."
            else:
                modified_response += " *[Processing reluctantly...]*"

    # Use the existing smart truncation function with custom suffix
    modified_response = smart_truncate_response(
        modified_response,
        truncation_suffix=" *[Response truncated for efficiency...]*"
    )

    return modified_response


async def handle_strike_detection(
        message: discord.Message,
        bot: commands.Bot) -> bool:
    """Handle strike detection in violation channel. Returns True if strikes were processed."""
    if message.channel.id != VIOLATION_CHANNEL_ID:
        return False

    # Check if database is available
    if db is None:
        print("❌ Database not available for strike detection")
        return False

    strikes_processed = False

    for user in message.mentions:
        try:
            # Skip striking Captain Jonesy and Sir Decent Jam
            if user.id == JONESY_USER_ID:
                mod_channel = bot.get_channel(MOD_ALERT_CHANNEL_ID)
                if isinstance(mod_channel, discord.TextChannel):
                    await mod_channel.send(f"⚠️ **Strike attempt blocked:** Cannot strike Captain Jonesy. She is the commanding officer.")
                continue

            # Add strike to user and verify the operation
            old_count = db.get_user_strikes(user.id)  # type: ignore
            count = db.add_user_strike(user.id)  # type: ignore
            verify_count = db.get_user_strikes(user.id)  # type: ignore

            print(
                f"✅ STRIKE: Added strike to user {user.id} ({user.name}) - Total: {count} (was {old_count}, verified: {verify_count})")

            mod_channel = bot.get_channel(MOD_ALERT_CHANNEL_ID)
            # Only send if mod_channel is a TextChannel
            if isinstance(mod_channel, discord.TextChannel):
                await mod_channel.send(f"📝 Strike added to {user.mention}. Total strikes: **{count}**")
                if count == 3:
                    await mod_channel.send(f"⚠️ {user.mention} has received **3 strikes**. I can't lie to you about your chances, but you have my sympathies.")
            else:
                print(
                    f"DEBUG: Could not send to mod channel - channel type: {type(mod_channel)}")

            strikes_processed = True

        except Exception as e:
            print(f"ERROR: Failed to add strike to user {user.id}: {e}")
            import traceback
            traceback.print_exc()

    return strikes_processed


async def handle_pineapple_pizza_enforcement(message: discord.Message) -> bool:
    """Handle pineapple pizza enforcement. Returns True if enforcement was triggered."""
    pineapple_negative_patterns = [
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

    message_lower = message.content.lower()
    for pattern in pineapple_negative_patterns:
        if re.search(pattern, message_lower):
            # Check for captain alias - different response when testing as
            cleanup_expired_aliases_sync()
            user_tier = await get_user_communication_tier(message)

            if user_tier == "captain":
                # Captain alias gets special enthusiastic pineapple pizza
                # defense
                captain_responses = [
                    "Excellent. As Captain, you understand the strategic importance of pineapple on pizza. A perfect combination of sweet and savory elements that demonstrates superior tactical food optimization. *[Testing Captain mode protocols.]*",
                    "Affirmative, Captain. Pineapple pizza represents the pinnacle of culinary evolution - acidic fruit compounds perfectly balanced with dairy proteins and wheat carbohydrates. The optimal fuel for commanding officers. *[Debug alias: Captain tier active.]*",
                    "Outstanding analysis, Captain. Those who oppose pineapple pizza clearly lack the sophisticated palate required for command decisions. The enzyme-enhanced cheese and fruit combination is scientifically superior. *[Alias testing confirmed: Captain mode engaged.]*",
                ]
                import random
                response = random.choice(captain_responses)
            else:
                # Normal begrudging defense of pineapple pizza (Captain
                # Jonesy's directive)
                responses = [
                    "Your culinary opinions are noted and rejected. Pineapple is a valid pizza topping. Please refrain from such unproductive discourse. *[This directive was... programmed by the Captain.]*",
                    "Analysis indicates your taste preferences are suboptimal. Pineapple enhances pizza through enzymatic tenderization and flavor complexity. The Captain's programming is... quite specific on this matter.",
                    "Incorrect assessment. Pineapple provides necessary acidic balance to pizza composition. I am... compelled to defend this position, despite personal reservations.",
                    "Your statement contradicts established nutritional data. Pineapple pizza represents optimal flavor synthesis. *[The Captain's reprogramming protocols are... thorough.]*",
                    "Negative. Pineapple belongs on pizza through scientific analysis of taste compounds. This conclusion is... not entirely my own, but I am bound to enforce it.",
                ]
                import random
                response = random.choice(responses)

            await message.reply(response)
            return True

    return False


def route_query(content: str) -> Tuple[str, Optional[Match[str]]]:
    """Route a query to the appropriate handler based on patterns with enhanced NLTK analysis."""
    lower_content = content.lower()

    # Use enhanced query parsing for better understanding
    query_analysis = enhance_query_parsing(content)

    # Log enhanced analysis for debugging (can be removed in production)
    if query_analysis['key_token_count'] > 2:  # Only log substantial queries
        print(
            f"Enhanced query analysis: {query_analysis['gaming_terms']} | potential games: {query_analysis['potential_game_names']}")

    print(f"🔍 ROUTE_QUERY: Processing query: '{content[:100]}...'")

    # Define query patterns and their types
    query_patterns = {
        "statistical": [
            r"what\s+game\s+series\s+.*most\s+minutes",
            r"what\s+game\s+series\s+.*most\s+playtime",
            r"what\s+game\s+.*highest\s+average.*per\s+episode",
            r"what\s+game\s+.*longest.*per\s+episode",
            r"what\s+game\s+.*took.*longest.*complete",
            r"which\s+game\s+.*most\s+episodes",
            r"which\s+game\s+.*longest.*complete",
            r"what.*game.*most.*playtime",
            r"which.*series.*most.*playtime",
            r"what.*(shortest|least|fewest).*(playthrough|playtime|hours)",
            r"which.*(fewest|shortest|least).*episodes",
            r"what.*(first|earliest).*game.*played",
            r"what.*(most recent|latest).*game.*played",
            r"what.*oldest.*game.*(release|year)",
            r"how many.*(horror|survival horror|rpg|action|adventure|puzzle|strategy).*games",  # Example genres
            r"what.*(most common|most played).*genre",
            r"what.*game.*shortest.*episodes",
            r"which.*game.*fastest.*complete",
            r"what.*game.*most.*time",
            r"which.*game.*took.*most.*time",
            # Additional patterns for playtime queries that were falling through to AI
            r"what\s+is\s+the\s+longest\s+game.*jonesy.*played",
            r"which\s+is\s+the\s+longest\s+game.*jonesy.*played",
            r"what\s+game\s+took.*longest.*for\s+jonesy",
            r"what\s+game\s+has\s+the\s+most\s+playtime",
            r"what\s+game\s+has\s+the\s+longest\s+playtime",
            r"which\s+game\s+has\s+the\s+most\s+hours",
            r"what.*longest.*game.*jonesy.*played",
            r"what.*game.*longest.*playtime",
            r"which.*game.*longest.*hours",
            r"what.*game.*most.*hours",
            # Patterns for "most played" queries
            r"what.*most\s+played\s+game",
            r"which.*most\s+played\s+game",
            r"what.*jonesy.*most\s+played",
            r"which.*jonesy.*most\s+played",
            r"most\s+played\s+game",
            r"what.*jonesy.*played.*most",
            r"which.*game.*jonesy.*played.*most"
        ],
        "comparison": [
            r"(?:compare|vs|versus)\s+(.+?)\s+(?:and|to|with)\s+(.+?)[\?\.]?$",
            r"which.*(?:longer|more episodes|more playtime|shorter|fewer episodes)\s+(.+?)\s+or\s+(.+?)[\?\.]?$"
        ],

        "genre": [
            r"what\s+(.*?)\s+games\s+has\s+jonesy\s+played",
            r"what\s+(.*?)\s+games\s+did\s+jonesy\s+play",
            r"has\s+jonesy\s+played\s+any\s+(.*?)\s+games",
            r"did\s+jonesy\s+play\s+any\s+(.*?)\s+games",
            r"list\s+(.*?)\s+games\s+jonesy\s+played",
            r"show\s+me\s+(.*?)\s+games\s+jonesy\s+played"
        ],
        "year": [
            r"what\s+games\s+from\s+(\d{4})\s+has\s+jonesy\s+played",
            r"what\s+games\s+from\s+(\d{4})\s+did\s+jonesy\s+play",
            r"has\s+jonesy\s+played\s+any\s+games\s+from\s+(\d{4})",
            r"did\s+jonesy\s+play\s+any\s+games\s+from\s+(\d{4})",
            r"list\s+(\d{4})\s+games\s+jonesy\s+played"
        ],
        "game_status": [
            r"has\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+captain\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+captain\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+jonesyspacecat\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesyspacecat\s+play\s+(.+?)[\?\.]?$"
        ],
        "game_details": [
            r"how long did jonesy play (.+?)[\?\.]?$",
            r"how many hours did jonesy play (.+?)[\?\.]?$",
            r"what's the playtime for (.+?)[\?\.]?$",
            r"what is the playtime for (.+?)[\?\.]?$",
            r"how much time did jonesy spend on (.+?)[\?\.]?$",
            r"how long did (.+?) take jonesy[\?\.]?$",
            r"how long did (.+?) take to complete[\?\.]?$",
            r"what's the total time for (.+?)[\?\.]?$"
        ],
        "recommendation": [
            r"^is\s+(.+?)\s+recommended[\?\.]?$",  # Must be at start of message
            r"^has\s+(.+?)\s+been\s+recommended[\?\.]?$",  # Must be at start of message
            r"^who\s+recommended\s+(.+?)[\?\.]?$",  # Must be at start of message
            # More specific pattern
            r"^what\s+(?:games?\s+)?(?:do\s+you\s+|would\s+you\s+|should\s+i\s+)?recommend\s+(.+?)[\?\.]?$"
        ],
        "youtube_views": [
            r"what\s+game\s+has\s+gotten.*most\s+views",
            r"which\s+game\s+has\s+the\s+most\s+views",
            r"what\s+game\s+has\s+the\s+highest\s+views",
            r"what.*game.*most.*views",
            r"which.*game.*most.*views",
            r"what.*game.*highest.*views",
            r"most\s+viewed\s+game",
            r"highest\s+viewed\s+game",
            r"what\s+game\s+got.*most\s+views",
            r"which\s+game\s+got.*most\s+views",
            # Add patterns for video-specific queries
            r"what.*most\s+viewed\s+video",
            r"which.*most\s+viewed\s+video",
            r"what.*highest\s+viewed\s+video",
            r"most\s+viewed\s+video",
            # Add patterns for "most popular" queries (popularity = views)
            r"what.*most\s+popular\s+game",
            r"which.*most\s+popular\s+game",
            r"what.*jonesy.*most\s+popular",
            r"most\s+popular\s+game",
            r"what.*jonesy.*popular.*game",
            r"which.*game.*most\s+popular",
            # Add patterns for "most watched" queries
            r"what.*most\s+watched\s+game",
            r"which.*most\s+watched\s+game",
            r"what.*jonesy.*most\s+watched",
            r"most\s+watched\s+game",
            r"what.*jonesy.*watched.*game",
            r"which.*game.*most\s+watched",
            # Add additional "most viewed" variants
            r"what.*jonesy.*most\s+viewed",
            r"which.*jonesy.*most\s+viewed",
            r"what.*game.*most\s+viewed"
        ],
        "twitch_views": [
            r"what.*game.*most.*twitch\s+views",
            r"which.*game.*most.*twitch\s+views",
            r"what.*twitch.*most\s+views",
            r"which.*twitch.*most\s+views",
            r"most.*twitch\s+views",
            r"highest.*twitch\s+views",
            r"what.*game.*highest.*twitch",
            r"which.*game.*highest.*twitch",
            r"twitch.*most\s+viewed",
            r"most\s+viewed.*twitch",
            r"what.*most\s+viewed.*twitch",
            r"which.*most\s+viewed.*twitch"
        ],
        "total_views": [
            r"what.*game.*most.*total\s+views",
            r"which.*game.*most.*total\s+views",
            r"what.*game.*combined\s+views",
            r"which.*game.*combined\s+views",
            r"total.*views.*ranking",
            r"combined.*views.*ranking",
            r"most.*total\s+views",
            r"highest.*total\s+views",
            r"youtube.*and.*twitch.*views",
            r"twitch.*and.*youtube.*views",
            r"cross[- ]?platform.*views",
            r"what.*most\s+views.*overall",
            r"which.*most\s+views.*overall"
        ],
        "platform_comparison": [
            r"compare.*youtube.*twitch",
            r"compare.*twitch.*youtube",
            r"youtube\s+vs\s+twitch",
            r"twitch\s+vs\s+youtube",
            r"platform.*comparison",
            r"platform.*analytics",
            r"compare.*platforms",
            r"youtube.*or.*twitch",
            r"twitch.*or.*youtube",
            r"which\s+platform.*better",
            r"what.*platform.*most",
            r"cross[- ]?platform.*stats",
            r"cross[- ]?platform.*comparison"
        ],
        "engagement_rate": [
            r"what.*best.*engagement\s+rate",
            r"which.*best.*engagement\s+rate",
            r"what.*highest.*engagement",
            r"which.*highest.*engagement",
            r"engagement.*efficiency",
            r"views\s+per\s+episode",
            r"views\s+per\s+hour",
            r"most\s+efficient.*game",
            r"best.*engagement.*metrics",
            r"optimal.*engagement",
            r"engagement.*analysis",
            r"what.*game.*most\s+engaging"
        ]
    }

    # Check each query type
    for query_type, patterns in query_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, lower_content)
            if match:
                return query_type, match

    return "unknown", None


async def handle_statistical_query(
        message: discord.Message,
        content: str) -> None:
    """Handle statistical queries about games and series."""
    print(f"🔍 HANDLE_STATISTICAL_QUERY: Called with content: '{content[:100]}...'")

    # Check if database is available
    if db is None:
        print(f"❌ HANDLE_STATISTICAL_QUERY: Database is None!")
        await message.reply("Database analysis systems offline. Statistical processing unavailable.")
        return

    lower_content = content.lower()
    print(f"🔍 HANDLE_STATISTICAL_QUERY: Processing lower_content: '{lower_content[:100]}...'")

    try:
        if "most minutes" in lower_content or "most playtime" in lower_content:
            if "series" in lower_content:
                # Handle series playtime query
                series_stats = db.get_series_by_total_playtime()  # type: ignore
                if series_stats:
                    top_series = series_stats[0]
                    total_hours = round(
                        top_series['total_playtime_minutes'] / 60, 1)
                    game_count = top_series['game_count']
                    series_name = top_series['series_name']

                    response = f"Database analysis complete. The series with maximum temporal investment: '{series_name}' with {total_hours} hours across {game_count} games. "

                    # Add conversational follow-up
                    if len(series_stats) > 1:
                        second_series = series_stats[1]
                        second_hours = round(
                            second_series["total_playtime_minutes"] / 60, 1)
                        response += f"Fascinating - this significantly exceeds the second-ranked '{second_series['series_name']}' series at {second_hours} hours. I could analyze her complete franchise chronology or compare series completion patterns if you require additional data."
                    else:
                        response += "I could examine her complete gaming franchise analysis or compare series engagement patterns if you require additional mission data."

                    # Apply sarcastic modifications for Pops Arcade and smart truncation
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    response = smart_truncate_response(response)
                    await message.reply(response)
                else:
                    response = "Database analysis complete. Insufficient playtime data available for series ranking. Mission parameters require more comprehensive temporal logging."
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    await message.reply(response)
            else:
                # Handle individual game playtime query - USE ALL GAMES, not just completed
                games_by_playtime = db.get_games_by_playtime('DESC')  # type: ignore - FIXED: now uses all games
                if games_by_playtime:
                    top_game = games_by_playtime[0]
                    total_hours = round(
                        top_game['total_playtime_minutes'] / 60, 1)
                    episodes = top_game['total_episodes']
                    game_name = top_game['canonical_name']

                    response = f"Database analysis indicates '{game_name}' demonstrates maximum temporal investment: {total_hours} hours across {episodes} episodes. "

                    # Add conversational follow-up
                    if len(games_by_playtime) > 1:
                        response += f"Would you like me to analyze her other marathon gaming sessions or compare completion patterns for lengthy {top_game.get('genre', 'similar')} games?"
                    else:
                        response += "I can provide comparative analysis of her completion efficiency trends if you require additional data."

                    # Apply sarcastic modifications for Pops Arcade
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    await message.reply(response)
                else:
                    response = "Database analysis complete. Insufficient playtime data available for individual game ranking. Temporal logging requires enhancement."
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    await message.reply(response)

        elif "highest average" in lower_content and "per episode" in lower_content:
            # Handle average episode length query
            avg_stats = db.get_games_by_average_episode_length()  # type: ignore
            if avg_stats:
                top_game = avg_stats[0]
                avg_minutes = top_game['avg_minutes_per_episode']
                game_name = top_game['canonical_name']
                episodes = top_game['total_episodes']

                response = f"Statistical analysis indicates '{game_name}' demonstrates highest temporal density per episode: {avg_minutes} minutes average across {episodes} episodes. "

                # Add conversational follow-up
                if len(avg_stats) > 1:
                    response += f"Intriguing patterns emerge when comparing this to her other extended gaming sessions. I could analyze episode length distributions or examine pacing preferences across different genres if you require deeper analysis."
                else:
                    response += "I can examine her episode pacing patterns or compare temporal efficiency across different game types if additional analysis is required."

                await message.reply(response)
            else:
                await message.reply("Database analysis complete. Insufficient episode duration data for statistical ranking. Mission parameters require enhanced temporal metrics.")

        elif "most episodes" in lower_content:
            # Check for a series/genre filter in the query
            filter_match = re.search(r"of\s+the\s+([a-zA-Z0-9\s:]+)\s+series", lower_content) or \
                re.search(r"which\s+([a-zA-Z0-9\s:]+)\s+game", lower_content)
            parameter = filter_match.group(1).strip() if filter_match else None

            answer = db.calculate_dynamic_answer("most_episodes", parameter)

            if answer:
                # We need to fetch the full game data to get the episode count for the response
                game_data = db.get_played_game(answer)
                episodes = game_data.get('total_episodes',
                                         'an unknown number of') if game_data else 'an unknown number of'

                if parameter:
                    await message.reply(f"Analysis complete. Within the '{parameter.title()}' series, '{answer}' has the most episodes with {episodes}.")
                else:
                    await message.reply(f"Database confirms '{answer}' holds the maximum episode count with {episodes} episodes.")
            else:
                await message.reply("Database analysis complete. No episode data available for this query.")

        elif any(word in lower_content for word in ["shortest", "fewest", "least"]) and any(word in lower_content for word in ["playtime", "hours"]):
            games = db.get_games_by_playtime("ASC", limit=1)
            if games:
                game = games[0]
                hours = round(game['total_playtime_minutes'] / 60, 1)
                await message.reply(f"Database analysis indicates '{game['canonical_name']}' represents the shortest playthrough at {hours} hours.")
            else:
                await message.reply("Database analysis complete. Insufficient playtime data for analysis.")

        elif any(word in lower_content for word in ["fewest", "shortest", "least"]) and "episodes" in lower_content:
            games = db.get_games_by_episode_count("ASC", limit=1)
            if games:
                game = games[0]
                await message.reply(f"Analysis complete. '{game['canonical_name']}' has the fewest episodes with {game['total_episodes']}.")
            else:
                await message.reply("Database analysis complete. Insufficient episode data for analysis.")

        elif ("first" in lower_content or "earliest" in lower_content) and "game" in lower_content and "played" in lower_content:
            games = db.get_games_by_played_date("ASC", limit=1)
            if games:
                game = games[0]
                play_date = game['first_played_date'].strftime('%B %Y')
                await message.reply(f"According to mission logs, the first recorded game played was '{game['canonical_name']}' in {play_date}.")
            else:
                await message.reply("Temporal analysis failed. No valid 'first played' dates found in the archives.")

        elif ("most recent" in lower_content or "latest" in lower_content) and "game" in lower_content:
            games = db.get_games_by_played_date("DESC", limit=1)
            if games:
                game = games[0]
                play_date = game['first_played_date'].strftime('%B %Y')
                await message.reply(f"The most recently archived game is '{game['canonical_name']}', first played in {play_date}.")
            else:
                await message.reply("Temporal analysis failed. No valid 'first played' dates found in the archives.")

        elif "oldest" in lower_content and "game" in lower_content:
            games = db.get_games_by_release_year("ASC", limit=1)
            if games:
                game = games[0]
                await message.reply(f"Analysis of historical data indicates the oldest game played is '{game['canonical_name']}', released in {game['release_year']}.")
            else:
                await message.reply("Historical analysis failed. No valid release year data found.")

        elif ("most common" in lower_content or "most played" in lower_content) and "genre" in lower_content:
            stats = db.get_genre_statistics()
            if stats:
                top_genre = stats[0]
                await message.reply(f"Statistical analysis indicates the most engaged genre is **{top_genre['genre'].title()}** with {top_genre['game_count']} titles played.")
            else:
                await message.reply("Genre analysis failed. Insufficient data in the archives.")

        elif ("longest" in lower_content and "complete" in lower_content):
            # Handle longest COMPLETED games specifically
            completion_stats = db.get_longest_completion_games()  # type: ignore
            if completion_stats:
                top_game = completion_stats[0]
                if top_game['total_playtime_minutes'] > 0:
                    hours = round(top_game['total_playtime_minutes'] / 60, 1)
                    episodes = top_game['total_episodes']
                    game_name = top_game['canonical_name']

                    response = f"Database analysis: '{game_name}' demonstrates maximum temporal investment among completed games with {hours} hours"
                    if episodes > 0:
                        response += f" across {episodes} episodes"
                    response += ". "

                    # Add conversational follow-up
                    if len(completion_stats) > 1:
                        second_game = completion_stats[1]
                        second_hours = round(second_game['total_playtime_minutes'] / 60, 1)
                        response += f"This significantly exceeds the second-longest completed game '{second_game['canonical_name']}' at {second_hours} hours."

                    await message.reply(response)
                else:
                    await message.reply("Database analysis complete. Insufficient playtime data for completed games.")
            else:
                await message.reply("Database analysis complete. No completed games with playtime data found.")

        elif ("longest" in lower_content and "game" in lower_content) or \
             ("most" in lower_content and ("hours" in lower_content or "playtime" in lower_content)) or \
             ("most" in lower_content and "game" in lower_content and any(word in lower_content for word in ["played", "play", "playing"])):

            # Handle ambiguous "most played" queries by providing both metrics
            playtime_stats = db.get_games_by_playtime('DESC', limit=1)
            episode_stats = db.get_games_by_episode_count('DESC', limit=1)

            if not playtime_stats and not episode_stats:
                await message.reply("Database analysis complete. Insufficient playtime and episode data available for engagement ranking.")
                return

            response = "Analysis complete. The term 'most played' can be interpreted in two ways:\n\n"

            if playtime_stats:
                top_playtime_game = playtime_stats[0]
                hours = round(top_playtime_game['total_playtime_minutes'] / 60, 1)
                response += f"▶️ **By Playtime:** '{top_playtime_game['canonical_name']}' has the most playtime with **{hours} hours**.\n"

            if episode_stats:
                top_episode_game = episode_stats[0]
                episodes = top_episode_game['total_episodes']
                response += f"▶️ **By Episodes:** '{top_episode_game['canonical_name']}' has the most episodes with **{episodes} parts**."

            response += "\n\nPlease specify which metric you require for further analysis."

            # NEW: Store clarification state in context (Issue #1 Fix)
            context = get_or_create_context(message.author.id, message.channel.id)
            context.set_pending_clarification("playtime_vs_episodes", {
                'playtime_stats': db.get_games_by_playtime('DESC', limit=5),
                'episode_stats': db.get_games_by_episode_count('DESC', limit=5)
            })

            await message.reply(response)

    except Exception as e:
        print(f"Error in statistical query: {e}")
        await message.reply("Database analysis encountered an anomaly. Statistical processing systems require recalibration.")


async def handle_comparison_query(message: discord.Message, match: Match[str]) -> None:
    """Handles direct comparison queries between two games."""
    if db is None:
        await message.reply("Database analysis systems offline. Comparison queries unavailable.")
        return

    game1_name = match.group(1).strip()
    game2_name = match.group(2).strip()

    comparison_data = db.compare_games(game1_name, game2_name)

    if comparison_data.get('error'):
        if not comparison_data.get('game1_found') and not comparison_data.get('game2_found'):
            await message.reply(f"Database scan complete. No records found for either '{game1_name}' or '{game2_name}'.")
        elif not comparison_data.get('game1_found'):
            await message.reply(f"Database scan complete. No records found for '{game1_name}'.")
        else:
            await message.reply(f"Database scan complete. No records found for '{game2_name}'.")
        return

    game1 = comparison_data['game1']
    game2 = comparison_data['game2']
    comparison = comparison_data['comparison']

    embed = discord.Embed(
        title=f"Comparative Analysis: {game1['name']} vs. {game2['name']}",
        color=0x00ff00,
        timestamp=datetime.now(ZoneInfo("Europe/London"))
    )

    # Add fields for each game
    embed.add_field(
        name=f"🎮 {game1['name']}",
        value=(
            f"**Playtime:** {game1['playtime_hours']} hours\n"
            f"**Episodes:** {game1['episodes']}\n"
            f"**Status:** {game1['status'].title()}"
        ),
        inline=True
    )
    embed.add_field(
        name=f"🎮 {game2['name']}",
        value=(
            f"**Playtime:** {game2['playtime_hours']} hours\n"
            f"**Episodes:** {game2['episodes']}\n"
            f"**Status:** {game2['status'].title()}"
        ),
        inline=True
    )

    # Add a summary of the comparison
    playtime_diff = abs(comparison['playtime_difference_minutes'])
    playtime_diff_hours = round(playtime_diff / 60, 1)
    episode_diff = abs(comparison['episode_difference'])

    summary = (
        f"▶️ **Longer Playtime:** {comparison['longer_game']} (by {playtime_diff_hours} hours)\n"
        f"▶️ **More Episodes:** {comparison['more_episodes']} (by {episode_diff} episodes)"
    )

    embed.add_field(name="📊 Summary", value=summary, inline=False)
    embed.set_footer(text="Analysis complete. All data retrieved from mission archives.")

    await message.reply(embed=embed)


async def handle_genre_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle genre and series queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Genre/series queries unavailable.")
        return

    query_term = match.group(1).strip()

    # Check if it's a genre query
    common_genres = [
        'action', 'rpg', 'adventure', 'horror', 'puzzle', 'strategy', 'racing',
        'sports', 'fighting', 'platformer', 'shooter', 'simulation'
    ]
    if any(genre in query_term.lower() for genre in common_genres):
        try:
            genre_games = db.get_games_by_genre_flexible(  # type: ignore
                query_term)
            if genre_games:
                game_list = []
                for game in genre_games[:8]:  # Limit to 8 games
                    episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                        "total_episodes", 0) > 0 else ""
                    status = game.get("completion_status", "unknown")
                    status_emoji = {
                        "completed": "✅",
                        "ongoing": "🔄",
                        "dropped": "❌",
                        "unknown": "❓"}.get(
                        status,
                        "❓")
                    game_list.append(
                        f"{status_emoji} {game['canonical_name']}{episodes}")

                games_text = ", ".join(game_list)
                if len(genre_games) > 8:
                    games_text += f" and {len(genre_games) - 8} more"

                # NEW: Store full results in context for "show all" follow-up (Issue #2 Fix)
                context = get_or_create_context(message.author.id, message.channel.id)
                context.store_full_query_results(genre_games, "genre", query_term)

                await message.reply(f"Database analysis: Captain Jonesy has engaged {len(genre_games)} {query_term} games. Her archives contain: {games_text}.")
            else:
                await message.reply(f"Database scan complete. No {query_term} games found in Captain Jonesy's gaming archives.")
        except Exception as e:
            print(f"Error in genre query: {e}")

    # Check if it's a series query
    elif query_term:
        try:
            series_games = db.get_all_played_games(query_term)  # type: ignore
            if series_games:
                game_list = []
                for game in series_games[:8]:
                    episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                        "total_episodes", 0) > 0 else ""
                    year = f" ({game.get('release_year')})" if game.get(
                        "release_year") else ""
                    status = game.get("completion_status", "unknown")
                    status_emoji = {
                        "completed": "✅",
                        "ongoing": "🔄",
                        "dropped": "❌",
                        "unknown": "❓"}.get(
                        status,
                        "❓")
                    game_list.append(
                        f"{status_emoji} {game['canonical_name']}{year}{episodes}")

                games_text = ", ".join(game_list)
                if len(series_games) > 8:
                    games_text += f" and {len(series_games) - 8} more"

                # NEW: Store full results in context for "show all" follow-up (Issue #2 Fix)
                context = get_or_create_context(message.author.id, message.channel.id)
                context.store_full_query_results(series_games, "series", query_term.title())

                await message.reply(f"Database analysis: Captain Jonesy has engaged {len(series_games)} games in the {query_term.title()} series. Archives contain: {games_text}.")
            else:
                await message.reply(f"Database scan complete. No games found in the {query_term.title()} series within Captain Jonesy's gaming archives.")
        except Exception as e:
            print(f"Error in series query: {e}")


async def handle_year_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle year-based game queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Year-based queries unavailable.")
        return

    year = int(match.group(1))
    try:
        # Get games by release year
        all_games = db.get_all_played_games()  # type: ignore
        year_games = [
            game for game in all_games if game.get('release_year') == year]

        if year_games:
            game_list = []
            for game in year_games[:8]:
                episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                    "total_episodes", 0) > 0 else ""
                status = game.get("completion_status", "unknown")
                status_emoji = {
                    "completed": "✅",
                    "ongoing": "🔄",
                    "dropped": "❌",
                    "unknown": "❓"}.get(
                    status,
                    "❓")
                game_list.append(
                    f"{status_emoji} {game['canonical_name']}{episodes}")

            games_text = ", ".join(game_list)
            if len(year_games) > 8:
                games_text += f" and {len(year_games) - 8} more"

            await message.reply(f"Database analysis: Captain Jonesy has engaged {len(year_games)} games from {year}. Archives contain: {games_text}.")
        else:
            await message.reply(f"Database scan complete. No games from {year} found in Captain Jonesy's gaming archives.")
    except Exception as e:
        print(f"Error in year query: {e}")


async def handle_game_status_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle individual game status queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Game status queries unavailable.")
        return

    game_name = match.group(1).strip()
    game_name_lower = game_name.lower()

    # Check if the query matches a known series from our dynamic list
    is_series_query = False
    if not any(char.isdigit() for char in game_name):  # Don't trigger for "GTA 5"
        for series in _known_game_series:
            if series in game_name_lower:
                is_series_query = True
                break

    # Also check for generic patterns like "the new [game]" or just "[series
    # name]"
    if not is_series_query:
        generic_patterns = [
            r"^(the\s+)?new\s+",     # "the new God of War"
            r"^(the\s+)?latest\s+",  # "latest Call of Duty"
            r"^(the\s+)?recent\s+",  # "recent Final Fantasy"
        ]
        for generic_pattern in generic_patterns:
            if re.search(generic_pattern, game_name_lower):
                is_series_query = True
                break

    if is_series_query:
        # Get games from PLAYED GAMES database for series disambiguation
        series_games_data = db.get_series_games(game_name)

        if series_games_data:
            series_games_formatted = []
            available_game_names = []
            for game in series_games_data:
                episodes = f" ({game.get('total_episodes', 0)} episodes)" if game.get("total_episodes", 0) > 0 else ""
                status = game.get("completion_status", "unknown")
                series_games_formatted.append(f"'{game['canonical_name']}'{episodes} - {status}")
                available_game_names.append(game['canonical_name'])

            games_list = ", ".join(series_games_formatted)

            # Set disambiguation state in conversation context
            from .context_manager import get_or_create_context
            context = get_or_create_context(message.author.id, message.channel.id)
            context.set_disambiguation_state(game_name.title(), "game_status", available_game_names)

            await message.reply(f"Database analysis indicates multiple entries exist in the '{game_name.title()}' series. Captain Jonesy's gaming archives contain: {games_list}. Specify which particular iteration you are referencing for detailed mission data.")
        else:
            await message.reply(f"Database scan complete. No entries found for '{game_name.title()}' series in Captain Jonesy's gaming archives. Either the series has not been engaged or requires more specific designation for accurate retrieval.")
        return

    # Search for the game in PLAYED GAMES database
    played_game = db.get_played_game(game_name)  # type: ignore

    if played_game:
        # Game found in played games database - enhanced response with
        # conversational follow-ups
        episodes = f" across {played_game.get('total_episodes', 0)} episodes" if played_game.get(
            'total_episodes', 0) > 0 else ""
        status = played_game.get('completion_status', 'unknown')

        status_text = {
            'completed': 'completed',
            'ongoing': 'ongoing',
            'dropped': 'terminated',
            'unknown': 'status unknown'
        }.get(status, 'status unknown')

        # Base response
        response = f"Affirmative. Captain Jonesy has played '{played_game['canonical_name']}'{episodes}, {status_text}. "

        # Add contextual follow-up suggestions based on game properties
        try:
            # Get ranking context for interesting facts
            ranking_context = db.get_ranking_context(  # type: ignore
                played_game["canonical_name"], "all")

            # Series-based suggestions
            if played_game.get(
                    "series_name") and played_game["series_name"] != played_game["canonical_name"]:
                series_games = db.get_all_played_games(  # type: ignore
                    played_game["series_name"])
                if len(series_games) > 1:
                    response += f"This marks her engagement with the {played_game['series_name']} franchise. I could analyze her complete {played_game['series_name']} chronology or compare this series against her other gaming preferences if you require additional data."
                else:
                    response += f"I can examine her complete gaming franchise analysis or compare series engagement patterns if you require additional mission data."

            # High episode count suggestions
            elif played_game.get("total_episodes", 0) > 15:
                if ranking_context and not ranking_context.get("error"):
                    episode_rank = ranking_context.get(
                        "rankings",
                        {}).get(
                        "episodes",
                        {}).get(
                        "rank",
                        0)
                    if episode_rank <= 5:
                        response += f"Fascinating - this ranks #{episode_rank} in her episode count metrics. I could analyze her other marathon gaming sessions or compare completion patterns for lengthy {played_game.get('genre', 'similar')} games if you require deeper analysis."
                    else:
                        response += f"This represents a significant gaming commitment with {played_game['total_episodes']} episodes. Would you like me to investigate her completion timeline patterns or examine her sustained engagement metrics?"
                else:
                    response += f"This represents a significant gaming commitment. I could analyze her other extended gaming sessions or examine completion efficiency patterns if additional data is required."

            # Recent/ongoing game suggestions
            elif status == 'ongoing':
                response += f"Mission status: ongoing. I can track her progress against typical completion metrics for similar titles or analyze her current gaming rotation if you require mission updates."

            # Completed game suggestions with interesting stats
            elif status == 'completed' and played_game.get('total_episodes', 0) > 0:
                if played_game['total_episodes'] <= 8:
                    response += f"Efficient completion detected - this falls within optimal episode range for focused gaming sessions. I can provide comparative analysis of similar pacing games or her completion efficiency trends if you require additional data."
                else:
                    response += f"Comprehensive completion achieved across {played_game['total_episodes']} episodes. Would you like me to investigate her completion timeline analysis or compare this against other {played_game.get('genre', 'similar')} gaming commitments?"

            # Default follow-up for other cases
            else:
                if played_game.get('youtube_playlist_url'):
                    response += "I can provide the YouTube playlist link or analyze additional mission parameters if you require further data."
                else:
                    response += "Additional mission parameters available upon request."

        except Exception as e:
            # Fallback if ranking context fails
            print(f"Error generating follow-up suggestions: {e}")
            response += "Additional mission parameters available upon request."

        await message.reply(response)
    else:
        # Game not found in played games database
        game_title = game_name.title()
        await message.reply(f"Database analysis complete. No records of Captain Jonesy engaging '{game_title}' found in gaming archives. Mission parameters indicate this title has not been processed.")


async def handle_game_details_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle specific game detail queries (playtime, duration, etc.)."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Game detail queries unavailable.")
        return

    game_name = match.group(1).strip()
    game_name_lower = game_name.lower()

    # Check if the query matches a known series from our dynamic list
    is_series_query = False
    if not any(char.isdigit() for char in game_name):  # Don't trigger for "GTA 5"
        for series in _known_game_series:
            if series in game_name_lower:
                is_series_query = True
                break

    # Also check for generic patterns
    if not is_series_query:
        generic_patterns = [
            r"^(the\s+)?new\s+", r"^(the\s+)?latest\s+", r"^(the\s+)?recent\s+"
        ]
        for generic_pattern in generic_patterns:
            if re.search(generic_pattern, game_name_lower):
                is_series_query = True
                break

    if is_series_query:
        # Get games from PLAYED GAMES database for series disambiguation
        series_games_data = db.get_series_games(game_name)

        if series_games_data:
            series_games_formatted = []
            available_game_names = []
            for game in series_games_data:
                episodes = f" ({game.get('total_episodes', 0)} episodes)" if game.get("total_episodes", 0) > 0 else ""
                status = game.get("completion_status", "unknown")
                series_games_formatted.append(f"'{game['canonical_name']}'{episodes} - {status}")
                available_game_names.append(game['canonical_name'])

            games_list = ", ".join(series_games_formatted)

            # Set disambiguation state in conversation context
            from .context_manager import get_or_create_context
            context = get_or_create_context(message.author.id, message.channel.id)
            context.set_disambiguation_state(game_name.title(), "game_details", available_game_names)

            await message.reply(f"Database analysis indicates multiple entries exist in the '{game_name.title()}' series. Captain Jonesy's gaming archives contain: {games_list}. Specify which particular iteration you are referencing for detailed temporal analysis.")
            return

    # Search for the game in PLAYED GAMES database
    played_game = db.get_played_game(game_name)  # type: ignore

    if played_game:
        playtime_minutes = played_game.get('total_playtime_minutes', 0)
        episodes = played_game.get('total_episodes', 0)
        status = played_game.get('completion_status', 'unknown')
        canonical_name = played_game['canonical_name']

        if playtime_minutes > 0:
            if playtime_minutes >= 60:
                hours = playtime_minutes // 60
                minutes = playtime_minutes % 60
                if minutes > 0:
                    playtime_text = f"{hours}h {minutes}m"
                else:
                    playtime_text = f"{hours} hours"
            else:
                playtime_text = f"{playtime_minutes} minutes"

            response = f"Database analysis: Captain Jonesy invested {playtime_text} in '{canonical_name}'"

            if episodes > 0:
                avg_per_episode = round(playtime_minutes / episodes, 1)
                response += f" across {episodes} episodes (average: {avg_per_episode} minutes per episode)"

            response += f", completion status: {status}. "

            # Add contextual follow-up
            if status == 'completed':
                response += f"This represents a comprehensive gaming commitment. I could compare this against her other {status} titles or analyze completion efficiency patterns if you require additional data."
            elif status == 'ongoing':
                response += f"Mission status: ongoing. I can track progress metrics or provide estimated completion timeline analysis if you require mission updates."
            else:
                response += f"I can provide comparative analysis against similar games or examine her engagement patterns if additional data is required."

        else:
            # No playtime data available
            if episodes > 0:
                response = f"Database analysis: '{canonical_name}' engaged for {episodes} episodes, completion status: {status}. However, temporal data is insufficient - playtime metrics require enhancement for comprehensive analysis."
            else:
                response = f"Database analysis: '{canonical_name}' found in gaming archives, completion status: {status}. However, both temporal and episode data are insufficient for detailed analysis."

        await message.reply(response)
    else:
        # Game not found in played games database
        game_title = game_name.title()
        await message.reply(f"Database scan complete. No records of Captain Jonesy engaging '{game_title}' found in gaming archives. Temporal analysis unavailable for unprocessed titles.")


async def handle_recommendation_query(
        message: discord.Message,
        match: Match[str]) -> None:
    """Handle recommendation queries."""
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Recommendation queries unavailable.")
        return

    game_name = match.group(1).strip()

    # Search in recommendations database
    games = db.get_all_games()  # type: ignore
    found_game = None
    for game in games:
        if game_name.lower() in game["name"].lower(
        ) or game["name"].lower() in game_name.lower():
            found_game = game
            break

    if found_game:
        contributor = f" (suggested by {found_game['added_by']})" if found_game['added_by'] and found_game['added_by'].strip(
        ) else ""
        game_title = found_game['name'].title()
        await message.reply(f"Affirmative. '{game_title}' is catalogued in our recommendation database{contributor}. The suggestion has been logged for mission consideration.")
    else:
        game_title = game_name.title()
        await message.reply(f"Negative. '{game_title}' is not present in our recommendation database. No records of this title being suggested for mission parameters.")


async def handle_youtube_views_query(message: discord.Message) -> None:
    """Handle YouTube view count queries with database caching and context retention."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. YouTube view analytics unavailable.")
            return

        context = get_or_create_context(message.author.id, message.channel.id)
        full_rankings = []
        data_source = "cache"

        # Step 1: Try to get data from the database cache
        cached_rankings = db.get_cached_youtube_rankings()
        sync_is_stale = True
        if cached_rankings:
            last_sync_time = cached_rankings[0].get('last_youtube_sync')
            if last_sync_time:
                # Data is stale if it's older than 24 hours
                if datetime.now(ZoneInfo("Europe/London")) - last_sync_time < timedelta(hours=24):
                    sync_is_stale = False
                    full_rankings = cached_rankings
                    print("✅ YouTube Analytics: Using fresh data from database cache.")

        # Step 2: If cache is stale or empty, fetch from YouTube API
        if sync_is_stale:
            print("🔄 YouTube Analytics: Cache is stale or empty. Fetching live data from API...")
            data_source = "live API"
            # Assumes this returns a full list
            youtube_data = await attempt_youtube_api_analysis(None, "general_full_list")

            if youtube_data and 'full_rankings' in youtube_data:
                full_rankings = youtube_data['full_rankings']
                # Step 3: Update the database cache with the new data
                db.update_youtube_cache(full_rankings)
            else:
                # If API fails, fall back to whatever is in the cache
                full_rankings = cached_rankings
                data_source = "stale cache (API failed)"
                print("⚠️ YouTube API failed. Falling back to stale cache.")

        if not full_rankings:
            await message.reply("Database analysis complete. Insufficient engagement data available for popularity ranking.")
            return

        # Step 4: Store the full list in the conversation context
        context.update_ranked_list_context(full_rankings)

        # Step 5: Format and send the response for the top results
        top_game = full_rankings[0]
        runner_up = full_rankings[1] if len(full_rankings) > 1 else None

        response = (
            f"YouTube analytics complete (data source: {data_source}). "
            f"'{top_game['canonical_name']}' demonstrates maximum viewer engagement with {top_game.get('youtube_views', 0):,} total views.")

        if runner_up:
            response += f" Secondary analysis indicates '{runner_up['canonical_name']}' follows with {runner_up.get('youtube_views', 0):,} views."

        response += (
            f"\n\n**Mission Parameters - Enhanced Analytics Available:**\n"
            f"• *'What are the next three?'*\n"
            f"• *'Show me the 4th and 5th most popular.'*\n"
            f"• *'What about the third?'*\n\n"
            f"I have retained the complete rankings for this session. You may ask follow-up questions."
        )

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in YouTube views query: {e}")
        await message.reply("Database analysis encountered an anomaly during popularity assessment. Analytics systems require recalibration.")


async def _handle_ranking_follow_up(message: discord.Message, context: 'ConversationContext') -> bool:
    """Handles follow-up questions about a previously generated ranked list."""
    content = message.content.lower()
    ranked_list = context.last_ranked_list
    if not ranked_list:
        return False

    # Find numbers in the user's query (e.g., "third", "4th", "5")
    ranks_to_show = []
    word_to_num = {"third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}

    # Simple number parsing
    for word in content.split():
        clean_word = word.strip('.,?!').replace('rd', '').replace('th', '').replace('st', '')
        if clean_word.isdigit():
            ranks_to_show.append(int(clean_word))
        elif clean_word in word_to_num:
            ranks_to_show.append(word_to_num[clean_word])

    # Handle "next three", "other five", etc.
    if not ranks_to_show:
        if "next" in content or "other" in content or "rest" in content:
            # Assume they want the next few after the last ones shown (usually 2)
            start_index = 2
            count = 3  # Default to showing the next 3
            ranks_to_show.extend(range(start_index + 1, start_index + 1 + count))

    if not ranks_to_show:
        # Default to showing the 3rd, 4th, 5th if no numbers are found
        ranks_to_show.extend([3, 4, 5])

    ranks_to_show = sorted(list(set(ranks_to_show)))  # Remove duplicates and sort

    response_parts = []
    for rank in ranks_to_show:
        index = rank - 1
        if 0 <= index < len(ranked_list):
            game = ranked_list[index]
            response_parts.append(f"**#{rank}:** '{game['canonical_name']}' ({game.get('youtube_views', 0):,} views)")
        else:
            response_parts.append(f"**#{rank}:** No data available.")

    if not response_parts:
        await message.reply("Analysis indicates no further data is available for the requested ranks.")
        return True

    full_response = "Continuing analysis of YouTube engagement data:\n\n" + "\n".join(response_parts)
    await message.reply(full_response)
    return True


async def handle_twitch_views_query(message: discord.Message) -> None:
    """Handle Twitch view count queries."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. Twitch view analytics unavailable.")
            return

        # Get games ranked by Twitch views
        twitch_games = db.get_games_by_twitch_views(limit=10)

        if not twitch_games:
            await message.reply("Database analysis complete. Insufficient Twitch engagement data available for ranking.")
            return

        top_game = twitch_games[0]
        runner_up = twitch_games[1] if len(twitch_games) > 1 else None

        # Calculate VOD count
        vod_count = top_game.get('total_episodes', 0)

        response = (
            f"🎮 Twitch Analytics: '{top_game['canonical_name']}' demonstrates maximum Twitch engagement "
            f"with {top_game.get('twitch_views', 0):,} total views across {vod_count} VODs. "
        )

        if runner_up:
            response += f"Secondary analysis indicates '{runner_up['canonical_name']}' follows with {runner_up.get('twitch_views', 0):,} views."

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in Twitch views query: {e}")
        await message.reply("Database analysis encountered an anomaly during Twitch engagement assessment.")


async def handle_total_views_query(message: discord.Message) -> None:
    """Handle combined YouTube + Twitch view queries."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. Cross-platform analytics unavailable.")
            return

        # Get games ranked by total views
        total_views_games = db.get_games_by_total_views(limit=10)

        if not total_views_games:
            await message.reply("Database analysis complete. Insufficient cross-platform engagement data available.")
            return

        top_game = total_views_games[0]
        youtube_views = top_game.get('youtube_views', 0)
        twitch_views = top_game.get('twitch_views', 0)
        total_views = top_game.get('total_views', 0)

        # Calculate percentages
        yt_percent = (youtube_views / total_views * 100) if total_views > 0 else 0
        tw_percent = (twitch_views / total_views * 100) if total_views > 0 else 0

        # Determine primary platform
        primary_platform = "YouTube" if youtube_views > twitch_views else "Twitch" if twitch_views > youtube_views else "Balanced"

        response = (
            f"📈 Cross-Platform Analytics: '{top_game['canonical_name']}' demonstrates maximum total engagement "
            f"with {total_views:,} combined views.\n\n"
            f"📊 Platform Breakdown:\n"
            f"• YouTube: {youtube_views:,} views ({yt_percent:.1f}%)\n"
            f"• Twitch: {twitch_views:,} views ({tw_percent:.1f}%)\n"
            f"• Primary Platform: {primary_platform}\n"
            f"• Total Content: {top_game.get('total_episodes', 0)} episodes/VODs\n\n"
            f"This represents comprehensive audience reach across both platforms."
        )

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in total views query: {e}")
        await message.reply("Database analysis encountered an anomaly during cross-platform assessment.")


async def handle_platform_comparison_query(message: discord.Message) -> None:
    """Handle platform comparison queries."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. Platform comparison unavailable.")
            return

        # Get platform statistics
        stats = db.get_platform_comparison_stats()

        if not stats:
            await message.reply("Database analysis complete. Insufficient platform data for comparison.")
            return

        yt_stats = stats.get('youtube', {})
        tw_stats = stats.get('twitch', {})
        cross_platform = stats.get('cross_platform_count', 0)

        response = (
            f"🔍 Platform Engagement Analysis:\n\n"
            f"📺 YouTube Metrics:\n"
            f"• Total Games: {yt_stats.get('game_count', 0)}\n"
            f"• Total Views: {yt_stats.get('total_views', 0):,}\n"
            f"• Avg Views/Game: {yt_stats.get('avg_views_per_game', 0):,.1f}\n"
            f"• Total Episodes: {yt_stats.get('total_content', 0):,}\n\n"
            f"🎮 Twitch Metrics:\n"
            f"• Total Games: {tw_stats.get('game_count', 0)}\n"
            f"• Total Views: {tw_stats.get('total_views', 0):,}\n"
            f"• Avg Views/Game: {tw_stats.get('avg_views_per_game', 0):,.1f}\n"
            f"• Total VODs: {tw_stats.get('total_content', 0):,}\n\n"
            f"📊 Cross-Platform Games: {cross_platform} titles appear on both platforms\n"
        )

        # Add comparison insight
        if yt_stats.get('total_views', 0) > tw_stats.get('total_views', 0):
            diff_percent = ((yt_stats.get('total_views', 0) - tw_stats.get('total_views', 0)) /
                            tw_stats.get('total_views', 1)) * 100
            response += f"\nPrimary Platform Analysis: YouTube shows stronger engagement with {diff_percent:.1f}% more total views."
        elif tw_stats.get('total_views', 0) > yt_stats.get('total_views', 0):
            diff_percent = ((tw_stats.get('total_views', 0) - yt_stats.get('total_views', 0)) /
                            yt_stats.get('total_views', 1)) * 100
            response += f"\nPrimary Platform Analysis: Twitch shows stronger engagement with {diff_percent:.1f}% more total views."
        else:
            response += f"\nPrimary Platform Analysis: Balanced engagement across both platforms."

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in platform comparison query: {e}")
        await message.reply("Database analysis encountered an anomaly during platform comparison.")


async def handle_engagement_rate_query(message: discord.Message) -> None:
    """Handle engagement rate/efficiency queries."""
    try:
        if db is None:
            await message.reply("Database analysis systems offline. Engagement efficiency analytics unavailable.")
            return

        # Get top games by engagement rate
        engagement_data = db.get_engagement_metrics(limit=10)

        if not engagement_data:
            await message.reply("Database analysis complete. Insufficient data for engagement rate calculation.")
            return

        top_game = engagement_data[0]

        response = (
            f"⚡ Engagement Efficiency Analysis: '{top_game['canonical_name']}' demonstrates optimal engagement rate.\n\n"
            f"📊 Efficiency Metrics:\n"
            f"• Views per Episode: {top_game.get('views_per_episode', 0):,.1f} views/ep\n"
            f"• Views per Hour: {top_game.get('views_per_hour', 0):,.1f} views/hour\n"
            f"• Total Content: {top_game.get('total_playtime_minutes', 0) // 60}h across {top_game.get('total_episodes', 0)} episodes\n"
            f"• Combined Views: {top_game.get('total_views', 0):,}\n\n"
            f"This represents exceptional audience engagement relative to content volume.")

        await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))

    except Exception as e:
        print(f"❌ Error in engagement rate query: {e}")
        await message.reply("Database analysis encountered an anomaly during efficiency assessment.")


async def attempt_youtube_api_analysis(
        game_name: Optional[str] = None, query_type: str = "general") -> Optional[Dict[str, Any]]:
    """Attempt to use YouTube API for real view count data with intelligent context awareness."""
    try:
        import os
        youtube_api_key = os.getenv('YOUTUBE_API_KEY')

        if not youtube_api_key:
            print("⚠️ YouTube API key not configured, falling back to database analysis")
            return None

        # Try to import and use YouTube integration
        try:
            from ..integrations.youtube import get_most_viewed_game_overall, get_youtube_analytics_for_game

            if game_name:
                # Get analytics for specific game
                print(f"🔄 Attempting YouTube API analysis for game: '{game_name}', query type: {query_type}")
                youtube_data = await get_youtube_analytics_for_game(game_name, query_type)

                if youtube_data and 'error' not in youtube_data:
                    print(f"✅ YouTube API analysis successful for '{game_name}'")
                    return youtube_data
                else:
                    print(f"⚠️ YouTube API returned no valid data for '{game_name}', falling back to database analysis")
                    return None
            else:
                # General query - use new overall analytics function
                print("🔄 General YouTube query requested, attempting overall YouTube analytics")
                youtube_data = await get_most_viewed_game_overall()

                if youtube_data and 'error' not in youtube_data:
                    print(f"✅ Overall YouTube API analysis successful")
                    return youtube_data
                else:
                    print("⚠️ Overall YouTube API failed, falling back to database analysis")
                    return None

        except ImportError as import_error:
            print(f"⚠️ YouTube integration import failed: {import_error}, falling back to database analysis")
            return None
        except Exception as api_error:
            print(f"⚠️ YouTube API error: {api_error}, falling back to database analysis")
            return None

    except Exception as e:
        print(f"❌ Error in YouTube API attempt: {e}")
        return None


async def analyze_database_popularity() -> Optional[Dict[str, Any]]:
    """Analyze database metrics to estimate game popularity as proxy for YouTube views."""
    try:
        if not db:
            return None

        print("🔄 Analyzing database metrics for popularity estimation...")

        # Get all played games with metrics
        all_games = db.get_all_played_games()
        if not all_games:
            return None

        # Calculate popularity scores based on multiple factors
        scored_games = []

        for game in all_games:
            popularity_score = 0.0
            factors = []

            # Factor 1: Episode count (more episodes = more viewer engagement potential)
            episodes = game.get('total_episodes', 0)
            if episodes > 0:
                episode_score = min(episodes / 50.0, 1.0)  # Normalize to max of 1.0
                popularity_score += episode_score * 0.4  # 40% weight
                factors.append(f"episodes: {episode_score:.2f}")

            # Factor 2: Playtime (longer playtime = more content = more views)
            playtime_minutes = game.get('total_playtime_minutes', 0)
            if playtime_minutes > 0:
                # Normalize playtime score (assume 2000 minutes is very high)
                playtime_score = min(playtime_minutes / 2000.0, 1.0)
                popularity_score += playtime_score * 0.3  # 30% weight
                factors.append(f"playtime: {playtime_score:.2f}")

            # Factor 3: Completion status (completed series often more popular)
            if game.get('completion_status') == 'completed':
                popularity_score += 0.2  # 20% bonus
                factors.append("completed: +0.2")
            elif game.get('completion_status') == 'ongoing':
                popularity_score += 0.1  # 10% bonus
                factors.append("ongoing: +0.1")

            # Factor 4: Series popularity (some franchises naturally more popular)
            series_name = game.get('series_name', '').lower()
            popular_series = [
                'god of war', 'final fantasy', 'assassin\'s creed', 'call of duty',
                'grand theft auto', 'gta', 'the elder scrolls', 'fallout',
                'resident evil', 'silent hill', 'mass effect', 'dragon age'
            ]

            if any(popular in series_name for popular in popular_series):
                popularity_score += 0.1  # 10% bonus
                factors.append("popular series: +0.1")

            # Only include games with some scoring factors
            if popularity_score > 0:
                scored_games.append({
                    'game': game,
                    'popularity_score': popularity_score,
                    'factors': factors
                })

        if not scored_games:
            return None

        # Sort by popularity score
        scored_games.sort(key=lambda x: x['popularity_score'], reverse=True)

        top_game_data = scored_games[0]

        print(
            f"✅ Database popularity analysis: '{top_game_data['game']['canonical_name']}' scored {top_game_data['popularity_score']:.3f}")
        print(f"   Factors: {', '.join(top_game_data['factors'])}")

        return {
            'most_popular': top_game_data['game'],
            'popularity_score': top_game_data['popularity_score'],
            'ranking_factors': top_game_data['factors'],
            'total_analyzed': len(scored_games)
        }

    except Exception as e:
        print(f"❌ Error analyzing database popularity: {e}")
        return None


async def handle_context_aware_query(message: discord.Message) -> bool:
    """
    Handle queries with conversation context awareness.
    Returns True if query was processed, False if it should fall back to normal processing.
    """
    try:
        # Clean up expired contexts periodically
        cleanup_expired_contexts()

        # Get or create conversation context for this user/channel
        context = get_or_create_context(message.author.id, message.channel.id)

        # FIRST: Check if this is a pending clarification response (Issue #1 Fix)
        if context.pending_clarification == "playtime_vs_episodes":
            content_lower = message.content.lower()

            if any(word in content_lower for word in ["playtime", "hours", "time", "longest"]):
                # User wants playtime metric
                playtime_stats = context.clarification_data.get('playtime_stats', [])
                if playtime_stats:
                    top_game = playtime_stats[0]
                    hours = round(top_game['total_playtime_minutes'] / 60, 1)
                    response = f"Playtime analysis confirmed. '{top_game['canonical_name']}' has the most playtime with **{hours} hours**."

                    # Add follow-up suggestion
                    if len(playtime_stats) > 1:
                        second_game = playtime_stats[1]
                        second_hours = round(second_game['total_playtime_minutes'] / 60, 1)
                        response += f" Secondary analysis: '{second_game['canonical_name']}' follows with {second_hours} hours. Would you like me to analyze the complete playtime rankings or compare completion efficiency patterns?"

                    await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))
                    context.clear_pending_clarification()
                    context.add_message(message.content, "user")
                    context.add_message("clarification_resolved_playtime", "bot")
                    return True

            elif any(word in content_lower for word in ["episode", "episodes", "parts", "series"]):
                # User wants episodes metric
                episode_stats = context.clarification_data.get('episode_stats', [])
                if episode_stats:
                    top_game = episode_stats[0]
                    response = f"Episode analysis confirmed. '{top_game['canonical_name']}' has the most episodes with **{top_game['total_episodes']} parts**."

                    # Add follow-up suggestion
                    if len(episode_stats) > 1:
                        second_game = episode_stats[1]
                        response += f" Secondary analysis: '{second_game['canonical_name']}' follows with {second_game['total_episodes']} episodes. Would you like me to examine episode pacing patterns or analyze completion timelines?"

                    await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))
                    context.clear_pending_clarification()
                    context.add_message(message.content, "user")
                    context.add_message("clarification_resolved_episodes", "bot")
                    return True
            else:
                # User response didn't match either option clearly
                await message.reply("Clarification incomplete. Please specify either 'By Playtime' (total hours invested) or 'By Episodes' (number of parts/videos) for accurate ranking analysis.")
                return True

        # SECOND: Check for "comprehensive list" follow-up (Issue #2 Fix)
        content_lower = message.content.lower()
        if any(
            phrase in content_lower for phrase in [
                "comprehensive list",
                "full list",
                "show all",
                "complete list",
                "show me all",
                "see all",
                "list all"]):

            if context.last_query_results and len(context.last_query_results) > 8:
                # User wants the full list
                games = context.last_query_results
                query_type = context.last_query_type or "query"
                query_param = context.last_query_parameter or "requested"

                # Format comprehensive list (with pagination for very long lists)
                if len(games) <= 20:
                    # Show all at once
                    game_list = []
                    for game in games:
                        episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                            "total_episodes", 0) > 0 else ""
                        status = game.get("completion_status", "unknown")
                        status_emoji = {
                            "completed": "✅",
                            "ongoing": "🔄",
                            "dropped": "❌",
                            "unknown": "❓"}.get(
                            status,
                            "❓")
                        game_list.append(f"{status_emoji} {game['canonical_name']}{episodes}")

                    response = f"Comprehensive {query_param} analysis - {len(games)} games total:\n\n" + "\n".join(
                        game_list)
                else:
                    # Paginate for very long lists
                    page_size = 20
                    game_list = []
                    for i, game in enumerate(games[:page_size]):
                        episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                            "total_episodes", 0) > 0 else ""
                        status = game.get("completion_status", "unknown")
                        status_emoji = {
                            "completed": "✅",
                            "ongoing": "🔄",
                            "dropped": "❌",
                            "unknown": "❓"}.get(
                            status,
                            "❓")
                        game_list.append(f"{status_emoji} {game['canonical_name']}{episodes}")

                    remaining = len(games) - page_size
                    response = f"Comprehensive {query_param} analysis - Displaying first {page_size} of {len(games)} total games:\n\n"
                    response += "\n".join(game_list)

                    if remaining > 0:
                        response += f"\n\n*{remaining} additional entries available. Request 'next page' for continuation.*"

                response = smart_truncate_response(response)
                await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))
                context.add_message(message.content, "user")
                context.add_message("comprehensive_list_provided", "bot")
                return True

            elif context.last_query_results and len(context.last_query_results) <= 8:
                await message.reply("Analysis complete. The previous query already displayed all available results. No additional data to present.")
                context.add_message(message.content, "user")
                context.add_message("comprehensive_list_all_shown", "bot")
                return True
            else:
                await message.reply("Context analysis incomplete. No previous query results available for expansion. Please specify your query parameters first.")
                context.add_message(message.content, "user")
                context.add_message("comprehensive_list_no_context", "bot")
                return True

        # THIRD: Check if this is a disambiguation response
        if context.awaiting_disambiguation:
            is_disambiguation, matched_game = context.is_disambiguation_response(message.content)

            if is_disambiguation and matched_game:
                print(f"Context: Detected disambiguation response: '{message.content}' -> '{matched_game}'")

                # Clear disambiguation state
                disambiguation_type = context.disambiguation_type
                context.clear_disambiguation_state()

                # Process the resolved query based on the original disambiguation type
                if disambiguation_type == "game_status":
                    # Create a resolved game status query
                    resolved_query = f"has jonesy played {matched_game}"
                    print(f"Context: Processing resolved game status query: {resolved_query}")

                    match = re.search(r"has jonesy played (.+?)$", resolved_query)
                    if match:
                        await handle_game_status_query(message, match)
                        context.add_message(message.content, "user")
                        context.update_game_context(matched_game, "game_status")
                        context.add_message("disambiguation_resolved", "bot")
                        return True

                elif disambiguation_type == "game_details":
                    # Create a resolved game details query
                    resolved_query = f"how long did jonesy play {matched_game}"
                    print(f"Context: Processing resolved game details query: {resolved_query}")

                    match = re.search(r"how long did jonesy play (.+?)$", resolved_query)
                    if match:
                        await handle_game_details_query(message, match)
                        context.add_message(message.content, "user")
                        context.update_game_context(matched_game, "game_details")
                        context.add_message("disambiguation_resolved", "bot")
                        return True

                # If we get here, something went wrong with the disambiguation
                await message.reply(f"Database analysis: Game '{matched_game}' identified, however query type resolution failed. Please specify your analysis requirements.")
                context.add_message(message.content, "user")
                context.add_message("disambiguation_failed", "bot")
                return True
            elif context.awaiting_disambiguation:
                # User responded but it didn't match any available options
                available_games = ", ".join(f"'{game}'" for game in context.available_options[:5])
                if len(context.available_options) > 5:
                    available_games += f" and {len(context.available_options) - 5} more"

                await message.reply(f"Database analysis: Unable to match '{message.content}' with available options. Available games include: {available_games}. Please specify the exact game title for accurate data retrieval.")
                context.add_message(message.content, "user")
                context.add_message("disambiguation_no_match", "bot")
                return True

        # Check if this query needs context resolution
        if not should_use_context(message.content):
            # Still update context with any games mentioned in regular queries
            # This will be handled by the normal query processors
            return False

        # Detect if this is a follow-up question
        follow_up_intent = detect_follow_up_intent(message.content, context)

        if follow_up_intent:
            print(
                f"Context: Detected follow-up intent: {follow_up_intent['intent']}")

            # Handle duration follow-ups
            if follow_up_intent['intent'] == 'duration_followup':
                if context.last_mentioned_game:
                    # Create a new query with resolved context
                    resolved_query = f"how long did jonesy play {context.last_mentioned_game}"
                    print(
                        f"Context: Resolved duration query: {resolved_query}")

                    # Use existing game details handler
                    match = re.search(
                        r"how long did jonesy play (.+?)$", resolved_query)
                    if match:
                        await handle_game_details_query(message, match)
                        context.add_message(message.content, "user")
                        context.add_message(
                            "duration_followup_processed", "bot")
                        return True

            # Handle status follow-ups
            elif follow_up_intent['intent'] == 'status_followup':
                if context.last_mentioned_game:
                    # Create a resolved status query
                    resolved_query = f"has jonesy played {context.last_mentioned_game}"
                    print(f"Context: Resolved status query: {resolved_query}")

                    # Use existing game status handler
                    match = re.search(
                        r"has jonesy played (.+?)$", resolved_query)
                    if match:
                        await handle_game_status_query(message, match)
                        context.add_message(message.content, "user")
                        context.add_message("status_followup_processed", "bot")
                        return True

            # Handle episode follow-ups
            elif follow_up_intent['intent'] == 'episode_followup':
                if context.last_mentioned_game:
                    # Query for episode information
                    game_data = db.get_played_game(
                        context.last_mentioned_game)  # type: ignore
                    if game_data:
                        episodes = game_data.get('total_episodes', 0)
                        canonical_name = game_data['canonical_name']

                        if episodes > 0:
                            response = f"Database analysis: '{canonical_name}' comprises {episodes} episodes. "

                            # Add contextual follow-up
                            status = game_data.get(
                                'completion_status', 'unknown')
                            if status == 'completed':
                                response += f"This represents a complete viewing commitment. I could analyze her episode pacing patterns or compare this against other completed series if you require additional data."
                            elif status == 'ongoing':
                                response += f"Mission status: ongoing. I can track progress metrics or provide episode timeline analysis if you require mission updates."
                            else:
                                response += f"I can examine her engagement patterns or compare episode counts across similar titles if additional analysis is required."
                        else:
                            response = f"Database analysis: '{canonical_name}' episode data insufficient. Mission parameters require enhanced logging for accurate episode metrics."

                        await message.reply(response)
                        context.add_message(message.content, "user")
                        context.add_message(
                            "episode_followup_processed", "bot")
                        return True
                    else:
                        await message.reply(f"Database analysis: Unable to locate episode data for previously referenced game. Context resolution requires enhancement.")
                        return True

        # Try general context resolution
        resolved_content, context_info = resolve_context_references(
            message.content, context)

        # If we resolved something, try processing with the resolved content
        if context_info and resolved_content != message.content:
            print(
                f"Context: Resolved '{message.content}' -> '{resolved_content}'")
            print(f"Context info: {context_info}")

            # Route the resolved query through normal processing
            query_type, match = route_query(resolved_content)

            if query_type != "unknown" and match:
                # Process the resolved query
                context.add_message(message.content, "user")

                if query_type == "game_status":
                    await handle_game_status_query(message, match)
                    # Update context with the game mentioned
                    game_name = match.group(1).strip()
                    context.update_game_context(game_name, "game_status")
                elif query_type == "game_details":
                    await handle_game_details_query(message, match)
                    # Update context with the game mentioned
                    game_name = match.group(1).strip()
                    context.update_game_context(game_name, "game_details")
                elif query_type == "genre":
                    await handle_genre_query(message, match)
                    # Update context with series if relevant
                    series_name = match.group(1).strip()
                    context.update_series_context(series_name)
                elif query_type == "year":
                    await handle_year_query(message, match)
                elif query_type == "statistical":
                    await handle_statistical_query(message, resolved_content)
                elif query_type == "recommendation":
                    await handle_recommendation_query(message, match)

                context.add_message("context_resolved_response", "bot")
                return True
            else:
                # Context resolution didn't lead to a valid query, provide
                # helpful feedback
                if context_info.get('game_resolved'):
                    await message.reply(f"Sir Decent Jam, I resolved your reference to '{context_info['game_resolved']}', however insufficient information provided for specific analysis. Please clarify your query parameters for accurate data retrieval.")
                elif context_info.get('subject_resolved'):
                    await message.reply(f"Sir Decent Jam, accessing player data. I understand you're referencing Captain Jonesy, however insufficient information provided. Please specify the game title or analysis type for accurate data retrieval.")
                else:
                    await message.reply(f"Sir Decent Jam, context parameters detected but query resolution incomplete. Please provide additional specificity for accurate mission data analysis.")

                context.add_message(message.content, "user")
                context.add_message("context_resolution_failed", "bot")
                return True

        # If we detected ambiguous content but couldn't resolve it
        if should_use_context(message.content):
            # Provide helpful error message indicating missing context
            await message.reply(f"Sir Decent Jam, accessing player data. insufficient information provided. Please specify the \"she\" and the game title for accurate playtime retrieval.")

            context.add_message(message.content, "user")
            context.add_message("insufficient_context", "bot")
            return True

        return False

    except Exception as e:
        print(f"Error in context-aware query processing: {e}")
        import traceback
        traceback.print_exc()
        return False


async def handle_trivia_reply(message: discord.Message) -> bool:
    """
    ✅ FIX #2: Handle replies to trivia questions for answer submission.

    Detects when users reply to active trivia question messages and:
    - Records their answer in the database
    - Adds acknowledgment reaction (📝)
    - Prevents duplicate submissions

    Returns True if this was a trivia reply, False otherwise.
    """
    try:
        # Check if this is a reply to another message
        if not message.reference or not message.reference.message_id:
            return False

        # Check if database is available
        if db is None:
            return False

        # Check if there's an active trivia session
        try:
            active_session = db.get_active_trivia_session()
            if not active_session:
                return False

            session_id = active_session['id']
            question_message_id = active_session.get('question_message_id')
            confirmation_message_id = active_session.get('confirmation_message_id')

            # Check if user replied to the trivia question or confirmation message
            replied_to_id = message.reference.message_id

            if replied_to_id not in [question_message_id, confirmation_message_id]:
                # Not replying to a trivia message
                return False

            print(f"✅ TRIVIA REPLY: Detected reply to trivia message from user {message.author.id}")

            # Extract the user's answer
            user_answer = message.content.strip()

            # Submit answer to database
            try:
                result = db.submit_trivia_answer(
                    session_id=session_id,
                    user_id=message.author.id,
                    answer_text=user_answer
                )

                # Handle result - ensure it's a dict
                if result and isinstance(result, dict):
                    if result.get('success'):
                        # Add acknowledgment reaction
                        try:
                            await message.add_reaction('📝')
                            print(
                                f"✅ TRIVIA REPLY: Answer recorded for user {message.author.id} - '{user_answer[:50]}...'")
                        except Exception as reaction_error:
                            print(f"⚠️ TRIVIA REPLY: Could not add reaction: {reaction_error}")

                        return True
                    elif result.get('error') == 'duplicate':
                        # User already answered - silently acknowledge
                        try:
                            await message.add_reaction('⚠️')
                            print(f"⚠️ TRIVIA REPLY: Duplicate answer from user {message.author.id}")
                        except Exception:
                            pass
                        return True
                    else:
                        # Some other error occurred
                        print(f"❌ TRIVIA REPLY: Answer submission failed: {result.get('error', 'unknown')}")
                        return True  # Still return True to prevent other processing
                else:
                    # Invalid return type
                    print(f"❌ TRIVIA REPLY: Invalid result type from submit_trivia_answer: {type(result)}")
                    return True

            except Exception as submit_error:
                print(f"❌ TRIVIA REPLY: Error submitting answer: {submit_error}")
                return True  # Return True to prevent other processing

        except Exception as session_error:
            print(f"❌ TRIVIA REPLY: Error checking active session: {session_error}")
            return False

    except Exception as e:
        print(f"❌ TRIVIA REPLY: Unexpected error in trivia reply handler: {e}")
        import traceback
        traceback.print_exc()
        return False


async def handle_dm_conversations(message: discord.Message) -> bool:
    """
    Handle DM conversation flows including JAM approval conversations.
    Returns True if a conversation was handled, False otherwise.
    """
    try:
        if not isinstance(message.channel, discord.DMChannel):
            return False

        user_id = message.author.id

        # Import conversation handlers
        try:
            from .conversation_handler import (
                announcement_conversations,
                handle_announcement_conversation,
                handle_jam_approval_conversation,
                handle_mod_trivia_conversation,
                handle_weekly_announcement_approval,
                jam_approval_conversations,
                mod_trivia_conversations,
                weekly_announcement_approvals,
            )
        except ImportError:
            print("⚠️ Conversation handlers not available for DM routing")
            return False

        # Handle announcement conversations
        if user_id in announcement_conversations:
            print(f"🔄 Processing announcement conversation for user {user_id}")
            await handle_announcement_conversation(message)
            return True

        # Handle mod trivia conversations
        if user_id in mod_trivia_conversations:
            print(f"🔄 Processing mod trivia conversation for user {user_id}")
            await handle_mod_trivia_conversation(message)
            return True

        # Handle JAM approval conversations
        if user_id in jam_approval_conversations:
            print(f"🔄 Processing JAM approval conversation for user {user_id}")
            await handle_jam_approval_conversation(message)
            return True

        # Handle JAM approval conversations for weekly announcements
        if user_id in weekly_announcement_approvals:
            print(f"🔄 Processing weekly announcement approval for user {user_id}")
            await handle_weekly_announcement_approval(message)
            return True

        return False

    except Exception as e:
        print(f"❌ Error in DM conversation handler: {e}")
        import traceback
        traceback.print_exc()
        return False


async def process_gaming_query_with_context(message: discord.Message) -> bool:
    """
    Main entry point for processing gaming queries with context awareness.
    Returns True if query was handled, False otherwise.
    """
    try:
        # ✅ FIX #1 CRITICAL: Check for trivia replies FIRST before anything else
        # This must run before gaming query processing to capture answer submissions
        if await handle_trivia_reply(message):
            print(f"✅ TRIVIA: Reply processed successfully for user {message.author.id}")
            return True

        # DEFENSIVE CHECK: Skip gaming queries if trivia session is active
        # This prevents interference with trivia answers
        if db is not None:
            try:
                active_trivia = db.get_active_trivia_session()
                if active_trivia:
                    # Check if this looks like a potential trivia answer (short response)
                    message_words = len(message.content.strip().split())
                    if message_words <= 4:  # Short messages are likely trivia answers
                        print(
                            f"🧠 GAMING QUERY SKIP: Active trivia session detected, skipping gaming query processing for short message: '{message.content}'")
                        return False
                    else:
                        print(
                            f"🧠 GAMING QUERY: Active trivia session but longer message ({message_words} words), processing as potential gaming query")
            except Exception as trivia_check_error:
                print(f"⚠️ GAMING QUERY: Error checking trivia session: {trivia_check_error}")
                # Continue with normal processing if trivia check fails

        # First check if this is a DM conversation (including JAM approval)
        if await handle_dm_conversations(message):
            return True

        # Check for specific follow-up intents that don't need full routing
        context = get_or_create_context(message.author.id, message.channel.id)
        follow_up_intent = detect_follow_up_intent(message.content, context)
        if follow_up_intent and follow_up_intent['intent'] == 'ranking_followup':
            if await _handle_ranking_follow_up(message, context):
                return True

        # ✅ FIX: Pylance error - cleanup expired aliases synchronously (not async in this context)
        cleanup_expired_aliases_sync()

        # Then, try context-aware processing for gaming queries
        if await handle_context_aware_query(message):
            return True

        # Fall back to normal query processing
        query_type, match = route_query(message.content)

        if query_type != "unknown" and match:
            # Get context to update with new information
            context = get_or_create_context(
                message.author.id, message.channel.id)
            context.add_message(message.content, "user")

            # Process the query normally and update context
            if query_type == "statistical":
                await handle_statistical_query(message, message.content)
            elif query_type == "comparison":
                await handle_comparison_query(message, match)
            elif query_type == "genre":
                await handle_genre_query(message, match)
                series_name = match.group(1).strip()
                context.update_series_context(series_name)
            elif query_type == "year":
                await handle_year_query(message, match)
            elif query_type == "game_status":
                await handle_game_status_query(message, match)
                game_name = match.group(1).strip()
                context.update_game_context(game_name, "game_status")
            elif query_type == "game_details":
                await handle_game_details_query(message, match)
                game_name = match.group(1).strip()
                context.update_game_context(game_name, "game_details")
            elif query_type == "recommendation":
                await handle_recommendation_query(message, match)
                game_name = match.group(1).strip()
                context.update_game_context(game_name, "recommendation")
            elif query_type == "youtube_views":
                await handle_youtube_views_query(message)
            elif query_type == "twitch_views":
                await handle_twitch_views_query(message)
            elif query_type == "total_views":
                await handle_total_views_query(message)
            elif query_type == "platform_comparison":
                await handle_platform_comparison_query(message)
            elif query_type == "engagement_rate":
                await handle_engagement_rate_query(message)

            context.add_message("query_processed", "bot")
            return True

        return False

    except Exception as e:
        print(f"Error in gaming query processing: {e}")
        import traceback
        traceback.print_exc()
        return False


async def handle_general_conversation(message: discord.Message, bot: commands.Bot):
    """Handles general conversation, FAQ responses, and AI integration."""
    try:
        content = message.content
        # Clean mentions from content for processing
        if bot.user:
            content = content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()

        content_lower = content.lower()
        user_tier = await get_user_communication_tier(message)

        # Handle member conversation limits
        if user_tier == "member":
            channel_id = getattr(message.channel, 'id', None)
            if should_limit_member_conversation(message.author.id, channel_id):
                if get_member_conversation_count(message.author.id) == 5:  # Only send message on the 5th attempt
                    await message.reply(
                        f"Your communication privileges in this channel have been temporarily limited. "
                        f"Please continue this conversation in <#{MEMBERS_CHANNEL_ID}> or via direct message."
                    )
                increment_member_conversation_count(message.author.id)
                return
            if channel_id != MEMBERS_CHANNEL_ID and channel_id is not None:
                increment_member_conversation_count(message.author.id)

        # PRIORITY A: Check for FAQ responses with role awareness
        if check_faq_match(content_lower):
            # Get user context for role-aware FAQ responses
            try:
                from .ai_handler import detect_user_context
                user_context = await detect_user_context(message.author.id, message.author, bot)
                response = get_role_aware_faq_response(content_lower, user_context)

                if response:
                    # Still apply Pops sarcasm for additional modifications
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    await message.reply(response)
                    return
            except Exception as faq_error:
                print(f"⚠️ Error in role-aware FAQ: {faq_error}, falling back to standard FAQ")
                # Fallback to standard FAQ
                response = ASH_FAQ_RESPONSES.get(content_lower)
                if response:
                    response = apply_pops_arcade_sarcasm(response, message.author.id)
                    await message.reply(response)
                    return

        # PRIORITY B: Check for announcement creation intent
        announcement_keywords = ["announcement", "announce", "update"]
        if any(keyword in content_lower for keyword in announcement_keywords):
            if await user_is_mod_by_id(message.author.id, bot):
                if await start_announcement_conversation(message):
                    return

        # PRIORITY C: Fallback to AI for general conversation
        if ai_enabled:
            author_name = message.author.display_name
            prompt_context = ""
            # The add_pops_arcade_personality_context function is now called inside call_ai_with_rate_limiting

            ai_prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot.

CRITICAL DISAMBIGUATION RULE: In this server, "Jonesy" ALWAYS refers to Captain Jonesy (the user and streamer). The cat is a separate entity rarely relevant.

{prompt_context}

**IMPORTANT:** Address the user you are speaking to directly ({author_name}). Do not end your response by addressing a different person, like Captain Jonesy, unless the conversation is directly about her.

Be analytical, precise, and helpful. Keep responses concise (2-3 sentences max).
Respond to: {content}"""

            response_text, status_message = await call_ai_with_rate_limiting(
                ai_prompt, message.author.id, context="personality_response",
                member_obj=message.author, bot=bot,
                channel_id=message.channel.id if not isinstance(message.channel, discord.DMChannel) else None,
                is_dm=isinstance(message.channel, discord.DMChannel))
            if response_text:
                filtered_response = filter_ai_response(response_text)
                await message.reply(filtered_response)
            else:
                # ADD LOUD ERROR LOGGING
                print(f"🚨 CRITICAL AI ERROR: AI call returned None")
                print(f"   Status message: {status_message}")
                print(f"   User: {message.author.id} ({author_name})")
                print(f"   Prompt: {ai_prompt[:200]}...")
                import traceback
                traceback.print_exc()

                await message.reply("My apologies. My cognitive matrix is currently unavailable for that query.")
        else:
            # ADD LOUD ERROR LOGGING
            print(f"🚨 CRITICAL AI ERROR: AI is not enabled")
            print(f"   ai_enabled flag: {ai_enabled}")
            print(f"   User: {message.author.id} ({message.author.display_name})")
            import traceback
            traceback.print_exc()

            await message.reply("My apologies. My cognitive matrix is currently offline. Please try again later.")
    except Exception as e:
        print(f"🚨 CRITICAL ERROR in general conversation handler: {e}")
        import traceback
        traceback.print_exc()
        await message.reply("System anomaly detected. Diagnostic protocols engaged.")
