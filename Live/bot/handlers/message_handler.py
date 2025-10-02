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

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

# Initialize NLTK components
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    print("Downloading NLTK 'punkt' model... (This will only happen once)")
    nltk.download('punkt', quiet=True)

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    print("Downloading NLTK 'stopwords' corpus... (This will only happen once)")
    nltk.download('stopwords', quiet=True)

# Constants for response handling
MAX_DISCORD_LENGTH = 2000
TRUNCATION_BUFFER = 80  # Buffer for truncation message

import discord
from discord.ext import commands

from ..config import (
    BOT_PERSONA,
    BUSY_MESSAGE,
    ERROR_MESSAGE,
    FAQ_RESPONSES,
    JAM_USER_ID,
    JONESY_USER_ID,
    MEMBER_ROLE_IDS,
    MEMBERS_CHANNEL_ID,
    MOD_ALERT_CHANNEL_ID,
    POPS_ARCADE_USER_ID,
    VIOLATION_CHANNEL_ID,
)
from ..database_module import DatabaseManager, get_database
from ..utils.permissions import (
    cleanup_expired_aliases,
    get_member_conversation_count,
    get_today_date_str,
    get_user_communication_tier,
    increment_member_conversation_count,
    member_conversation_counts,
    should_limit_member_conversation,
    update_alias_activity,
    user_alias_state,
    user_is_mod,
    user_is_mod_by_id,
)
from .ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response
from .context_manager import (
    cleanup_expired_contexts,
    detect_follow_up_intent,
    detect_jonesy_context,
    get_or_create_context,
    resolve_context_references,
    should_use_context,
)

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

    # --- ROBUST TRUNCATION LOGIC (UPDATED) ---
    if len(modified_response) > MAX_DISCORD_LENGTH:
        # Use NLTK to intelligently split the text into sentences
        sentences = nltk.sent_tokenize(modified_response)

        truncated_response = ""
        kept_sentences = []
        # Leave a buffer for the truncation message
        buffer = 50

        for sentence in sentences:
            # Check if adding the next sentence (plus a space) exceeds the limit
            if len(truncated_response) + len(sentence) + 1 > MAX_DISCORD_LENGTH - buffer:
                break

            kept_sentences.append(sentence)
            truncated_response = " ".join(kept_sentences)

        if not kept_sentences:
            # This happens if the very first sentence is already too long.
            # In this case, we have to perform a hard truncate on that sentence.
            modified_response = sentences[0][:MAX_DISCORD_LENGTH - buffer] + "..."
        else:
            modified_response = truncated_response

        # Add a consistent truncation indicator
        modified_response += " *[Response truncated for efficiency...]*"

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
            # captain
            cleanup_expired_aliases()
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
        print(f"Enhanced query analysis: {query_analysis['gaming_terms']} | potential games: {query_analysis['potential_game_names']}")

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
            r"what.*game.*most.*hours"
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
            r"which\s+game\s+got.*most\s+views"
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
    # Check if database is available
    if db is None:
        await message.reply("Database analysis systems offline. Statistical processing unavailable.")
        return

    lower_content = content.lower()

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
                # Handle individual game playtime query
                games_by_playtime = db.get_longest_completion_games()  # type: ignore
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
            # Handle episode count query
            episode_stats = db.get_games_by_episode_count(  # type: ignore
                'DESC')
            if episode_stats:
                top_game = episode_stats[0]
                episodes = top_game['total_episodes']
                game_name = top_game['canonical_name']
                status = top_game['completion_status']

                response = f"Database confirms '{game_name}' holds maximum episode count: {episodes} episodes, status: {status}. "

                # Add conversational follow-up
                if status == 'completed':
                    response += f"Remarkable commitment detected - this represents her most extensive completed gaming engagement. I could track her progress against typical completion metrics for similar marathon titles or analyze her sustained engagement patterns."
                else:
                    response += f"Mission status: {status}. I can provide comparative analysis of her other extended gaming commitments or examine engagement sustainability patterns if you require additional data."

                await message.reply(response)
            else:
                await message.reply("Database analysis complete. No episode data available for ranking. Mission logging requires enhancement.")

        elif ("longest" in lower_content and "complete" in lower_content) or \
             ("longest" in lower_content and "game" in lower_content) or \
             ("most" in lower_content and ("hours" in lower_content or "playtime" in lower_content)):
            # Handle longest playtime/completion games - unified handler for all playtime queries
            completion_stats = db.get_longest_completion_games()  # type: ignore
            if completion_stats:
                top_game = completion_stats[0]
                if top_game['total_playtime_minutes'] > 0:
                    hours = round(top_game['total_playtime_minutes'] / 60, 1)
                    episodes = top_game['total_episodes']
                    game_name = top_game['canonical_name']

                    response = f"Database analysis: '{game_name}' demonstrates maximum temporal investment with {hours} hours"
                    if episodes > 0:
                        response += f" across {episodes} episodes"
                    response += f", completion status: {top_game.get('completion_status', 'unknown')}. "

                    # Add conversational follow-up
                    if len(completion_stats) > 1:
                        second_game = completion_stats[1]
                        second_hours = round(second_game['total_playtime_minutes'] / 60, 1)
                        response += f"This significantly exceeds the second-longest '{second_game['canonical_name']}' at {second_hours} hours. Would you like me to analyze her other marathon gaming sessions or compare completion patterns?"
                    else:
                        response += f"I could investigate her completion timeline patterns or compare this against other {top_game.get('genre', 'similar')} gaming commitments if you require additional analysis."
                else:
                    # Fall back to episode count if no playtime data
                    episodes = top_game['total_episodes']
                    game_name = top_game['canonical_name']
                    response = f"Database analysis: '{game_name}' demonstrates maximum episode commitment with {episodes} episodes, however temporal data is insufficient. Mission parameters require enhanced playtime logging for comprehensive analysis."

                await message.reply(response)
            else:
                await message.reply("Database analysis complete. Insufficient playtime data available for temporal ranking. Mission parameters require more comprehensive logging.")

    except Exception as e:
        print(f"Error in statistical query: {e}")
        await message.reply("Database analysis encountered an anomaly. Statistical processing systems require recalibration.")


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

    # Common game series that need disambiguation
    game_series_keywords = [
        "god of war",
        "final fantasy",
        "call of duty",
        "assassin's creed",
        "grand theft auto",
        "gta",
        "the elder scrolls",
        "fallout",
        "resident evil",
        "silent hill",
        "metal gear",
        "halo",
        "gears of war",
        "dead space",
        "mass effect",
        "dragon age",
        "the witcher",
        "dark souls",
        "borderlands",
        "far cry",
        "just cause",
        "saints row",
        "watch dogs",
        "dishonored",
        "bioshock",
        "tomb raider",
        "hitman",
        "splinter cell",
        "rainbow six",
        "ghost recon",
        "battlefield",
        "need for speed",
        "fifa",
        "madden",
        "nba 2k",
        "mortal kombat",
        "street fighter",
        "tekken",
        "super mario",
        "zelda",
        "pokemon",
        "sonic",
        "crash bandicoot",
        "spyro",
        "kingdom hearts",
        "persona",
        "shin megami tensei",
        "tales of",
        "fire emblem",
        "advance wars"]

    # Check if this might be a game series query that needs disambiguation
    is_series_query = False
    for series in game_series_keywords:
        if series in game_name_lower and not any(
                char.isdigit() for char in game_name):
            # It's a series name without specific numbers/years
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
        played_games = db.get_all_played_games()  # type: ignore

        # Find all games in this series from played games database
        series_games = []
        available_game_names = []
        for game in played_games:
            game_lower = game['canonical_name'].lower()
            series_lower = game.get('series_name', '').lower()
            # Check if this game belongs to the detected series
            for series in game_series_keywords:
                if series in game_name_lower and (
                        series in game_lower or series in series_lower):
                    episodes = f" ({game.get('total_episodes', 0)} episodes)" if game.get(
                        "total_episodes", 0) > 0 else ""
                    status = game.get("completion_status", "unknown")
                    series_games.append(
                        f"'{game['canonical_name']}'{episodes} - {status}")
                    available_game_names.append(game['canonical_name'])
                    break

        # Create disambiguation response with specific games if found
        if series_games:
            games_list = ", ".join(series_games)

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

    # Common game series that need disambiguation (same list as game_status_query)
    game_series_keywords = [
        "god of war", "final fantasy", "call of duty", "assassin's creed", "grand theft auto", "gta",
        "the elder scrolls", "fallout", "resident evil", "silent hill", "metal gear", "halo",
        "gears of war", "dead space", "mass effect", "dragon age", "the witcher", "dark souls",
        "borderlands", "far cry", "just cause", "saints row", "watch dogs", "dishonored",
        "bioshock", "tomb raider", "hitman", "splinter cell", "rainbow six", "ghost recon",
        "battlefield", "need for speed", "fifa", "madden", "nba 2k", "mortal kombat",
        "street fighter", "tekken", "super mario", "zelda", "pokemon", "sonic",
        "crash bandicoot", "spyro", "kingdom hearts", "persona", "shin megami tensei",
        "tales of", "fire emblem", "advance wars"
    ]

    # Check if this might be a game series query that needs disambiguation
    is_series_query = False
    for series in game_series_keywords:
        if series in game_name_lower and not any(char.isdigit() for char in game_name):
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
        played_games = db.get_all_played_games()  # type: ignore
        series_games = []
        available_game_names = []

        for game in played_games:
            game_lower = game['canonical_name'].lower()
            series_lower = game.get('series_name', '').lower()
            # Check if this game belongs to the detected series
            for series in game_series_keywords:
                if series in game_name_lower and (series in game_lower or series in series_lower):
                    episodes = f" ({game.get('total_episodes', 0)} episodes)" if game.get(
                        "total_episodes", 0) > 0 else ""
                    status = game.get("completion_status", "unknown")
                    series_games.append(f"'{game['canonical_name']}'{episodes} - {status}")
                    available_game_names.append(game['canonical_name'])
                    break

        # Create disambiguation response with specific games if found
        if series_games:
            games_list = ", ".join(series_games)

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
    """Handle YouTube view count queries - prevents AI fabrication by providing proper response."""
    await message.reply("Database analysis: YouTube view count metrics require external API integration to prevent data fabrication. This functionality is not currently available - I cannot access YouTube Analytics data to determine which games have received the most views. Mission parameters require YouTube API implementation for accurate viewership analysis.")


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

        # FIRST: Check if this is a disambiguation response
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
                jam_approval_conversations,
                mod_trivia_conversations,
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

            context.add_message("query_processed", "bot")
            return True

        return False

    except Exception as e:
        print(f"Error in gaming query processing: {e}")
        import traceback
        traceback.print_exc()
        return False
