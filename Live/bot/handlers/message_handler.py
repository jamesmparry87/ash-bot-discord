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
from discord.ext import commands

from ..config import (
from ..persona.sarcasm import apply_pops_arcade_sarcasm, handle_pineapple_pizza_enforcement
from .queries.statistical import handle_statistical_query
from .queries.comparisons import handle_comparison_query, handle_platform_comparison_query
from .queries.details import handle_genre_query, handle_year_query, handle_game_status_query, handle_game_details_query, handle_recommendation_query
from .queries.views import handle_youtube_views_query, handle_twitch_views_query, handle_total_views_query, handle_engagement_rate_query
from .queries.context import handle_context_aware_query, _handle_ranking_follow_up
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

        # PRIORITY 0: Handle manual game input for sync (blocking operation)
        try:
            from .manual_game_input import handle_manual_input_response
            if await handle_manual_input_response(message):
                return True
        except ImportError:
            pass  # Manual input handler not available

        # Import conversation handlers
        try:
            from .conversation_handler import (
                announcement_conversations,
                game_review_conversations,
                handle_announcement_conversation,
                handle_game_review_conversation,
                handle_jam_approval_conversation,
                handle_mod_trivia_conversation,
                handle_sync_approval_conversation,
                handle_weekly_announcement_approval,
                jam_approval_conversations,
                mod_trivia_conversations,
                sync_approval_conversations,
                weekly_announcement_approvals,
            )
        except ImportError:
            print("⚠️ Conversation handlers not available for DM routing")
            return False

        # PRIORITY 1: Handle game review conversations FIRST (must be before AI routing)
        if user_id in game_review_conversations:
            print(f"🔄 Processing game review conversation for user {user_id}")
            await handle_game_review_conversation(message)
            return True

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

        # Handle sync approval conversations
        if user_id in sync_approval_conversations:
            print(f"🔄 Processing sync approval conversation for user {user_id}")
            handled = await handle_sync_approval_conversation(message)
            return handled

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

        # 🚨 IMPROVED TRIVIA CHECK: Only skip if it's clearly a trivia answer
        # Gaming queries with keywords should ALWAYS be processed
        if db is not None:
            try:
                active_trivia = db.get_active_trivia_session()
                if active_trivia:
                    message_lower = message.content.lower()
                    message_words = len(message.content.strip().split())

                    # Define clear gaming keywords that override trivia blocking
                    gaming_keywords = [
                        'game', 'played', 'play', 'episode', 'hour', 'playtime',
                        'jonesy', 'captain', 'view', 'youtube', 'twitch', 'stream',
                        'series', 'genre', 'complete', 'finish', 'longest', 'shortest',
                        'most', 'recent', 'first', 'last'
                    ]

                    # Check if message contains clear gaming keywords
                    has_gaming_keywords = any(keyword in message_lower for keyword in gaming_keywords)

                    if has_gaming_keywords:
                        print(
                            f"🎮 GAMING QUERY OVERRIDE: Trivia active but gaming keywords detected - processing query: '{message.content[:50]}...'")
                        # Continue with gaming query processing
                    elif message_words <= 4:
                        # Short message without gaming keywords during trivia = likely trivia answer
                        print(
                            f"🧠 GAMING QUERY SKIP: Active trivia session detected, skipping short message without gaming keywords: '{message.content}'")
                        return False
                    else:
                        # Longer message without clear gaming keywords during trivia
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
