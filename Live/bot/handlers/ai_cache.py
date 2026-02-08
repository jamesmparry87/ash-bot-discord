"""
AI Response Cache Module

PHASE 1: Intelligent caching system for AI responses to maximize Gemini free-tier quota.
Implements hash-based caching with fuzzy matching and intelligent TTL management.
"""

import hashlib
import logging
import random
import re
import threading
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

# Configure logging
logger = logging.getLogger(__name__)


class AIResponseCache:
    """
    Intelligent caching system for AI responses.

    Features:
    - Hash-based cache with similarity matching
    - TTL (time-to-live) for different query types
    - Cache statistics tracking
    - Automatic cleanup of expired entries
    """

    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()  # Thread safety for async operations
        self.stats = {
            "hits": 0,
            "misses": 0,
            "saves": 0,  # API calls saved
            "total_queries": 0
        }

        # TTL configuration (in seconds)
        # 🚨 AGGRESSIVE TTL REDUCTION: Shorter cache times = fresher, more natural conversations
        self.ttl_config = {
            "faq": 86400,                    # 24 hours - FAQs rarely change
            "gaming_query": 21600,           # 6 hours - game data is relatively static (but bypassed anyway)
            "conversational_query": 1800,    # 30 minutes - conversational responses need to feel fresh
            "personality": 1800,             # 30 minutes - greetings should vary, not feel robotic
            "trivia": 604800,                # 7 days - pre-generated trivia questions
            "general": 3600                  # 1 hour - general conversation (reduced from 3h)
        }

    def _normalize_query(self, query: str) -> str:
        """Normalize query for better matching while preserving conversational context"""
        # Convert to lowercase
        normalized = query.lower()

        # NEW: Normalize Discord user mentions to improve cache hits
        # Replace <@123456789> with generic placeholder
        import re
        normalized = re.sub(r'<@!?\d+>', '<@user>', normalized)

        # NEW: Normalize Discord role mentions
        normalized = re.sub(r'<@&\d+>', '<@role>', normalized)

        # NEW: Normalize Discord channel mentions
        normalized = re.sub(r'<#\d+>', '<#channel>', normalized)

        # Remove extra whitespace
        normalized = " ".join(normalized.split())

        # Remove common punctuation at end
        normalized = normalized.rstrip('?.!,')

        # IMPROVED: Only remove truly filler words, preserve conversational markers
        # Keep: question words (what, where, when, how, why), negations (no, not, don't),
        # conversational markers (hi, hello, thanks, easy, grouchy, etc.)
        filler_words = ['um', 'uh', 'like']  # Reduced list - only remove obvious fillers
        for filler in filler_words:
            normalized = normalized.replace(filler, '')

        # Clean up again after removals
        normalized = " ".join(normalized.split())

        return normalized

    def _generate_cache_key(
            self,
            query: str,
            user_id: int,
            channel_id: Optional[int] = None,
            is_dm: bool = False) -> str:
        """
        Generate cache key from normalized query with conversation context.

        Args:
            query: The query text
            user_id: User ID making the query
            channel_id: Channel ID (None for DMs)
            is_dm: Whether this is a DM conversation

        Returns:
            MD5 hash incorporating query, user, and conversation location
        """
        normalized = self._normalize_query(query)

        # Build context string to ensure conversation isolation
        context_parts = [
            normalized,
            str(user_id),
            "dm" if is_dm else (f"channel_{channel_id}" if channel_id is not None else "unknown")
        ]
        context_string = "|".join(context_parts)

        # Use MD5 hash for consistent key generation
        return hashlib.md5(context_string.encode()).hexdigest()

    def _detect_query_type(self, query: str) -> str:
        """
        Detect query type to prevent matching incompatible message types.

        🚨 ENHANCED: Now detects specific question types to prevent cross-matching
        - 'question_identity': Who/what is questions (identity queries)
        - 'question_status': How are you, what's happening (status queries)
        - 'question_data': Informational data queries
        - 'conversational': Casual responses, greetings, acknowledgments
        - 'statement': Declarative statements
        """
        query_lower = query.lower().strip()

        # 🚨 NEW: Detect specific question sub-types
        if query_lower.startswith('who '):
            return 'question_identity'  # "Who is Jonesy?" vs "Who recommended X?"
        if query_lower.startswith('what is ') or query_lower.startswith('what are '):
            # Check if it's asking about identity/definition or data
            if any(word in query_lower for word in ['your purpose', 'you', 'ash', 'jonesy is', 'captain is']):
                return 'question_identity'  # "What is your purpose?" vs "What is the longest game?"
        if query_lower.startswith('how are') or query_lower.startswith('how is'):
            return 'question_status'  # "How are you?" - status query

        # General question detection (data queries)
        question_indicators = ['what', 'where', 'when', 'how', 'why', 'who', 'which', 'did',
                               'has', 'have', 'is', 'are', 'does', 'do', 'can', 'could', 'would', 'should']
        if any(query_lower.startswith(indicator) for indicator in question_indicators):
            return 'question_data'  # Generic data questions
        if query_lower.endswith('?'):
            return 'question_data'

        # Conversational responses (greetings, acknowledgments, casual chat)
        conversational_indicators = [
            'hi', 'hello', 'hey', 'thanks', 'thank you', 'ok', 'okay', 'cool', 'nice', 'great',
            'lol', 'haha', 'sure', 'alright', 'yeah', 'yep', 'nope', 'no worries',
            'take it easy', 'calm down', 'grouchy', 'chill', 'relax', 'good morning', 'good afternoon'
        ]
        if any(indicator in query_lower for indicator in conversational_indicators):
            return 'conversational'

        # Default to statement
        return 'statement'

    def _calculate_word_overlap(self, words1: set, words2: set) -> float:
        """
        Calculate word overlap ratio between two sets of words.

        Returns:
            Overlap ratio from 0.0 to 1.0
        """
        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        total = len(words1 | words2)

        return overlap / total if total > 0 else 0.0

    def _detect_query_category(self, query: str) -> str:
        """Detect the query category for appropriate TTL (different from query type)"""
        query_lower = query.lower()

        # User presence/activity queries (NEW - check before conversational to prevent false matches)
        presence_patterns = [
            r'where (has|have) <@user>',  # "where has @user been"
            r'<@user> (been|hiding|gone)',  # "@user been quiet", "@user hiding"
            r'(where|what) (is|has) <@user> (been|up to|doing)',  # "what has @user been up to"
            r'haven\'t seen <@user>',  # "haven't seen @user"
        ]
        if any(re.search(pattern, query_lower) is not None for pattern in presence_patterns):
            return "gaming_query"  # User activity = gaming/community queries

        # Conversational/emotional queries (REFINED - removed overly broad "been" pattern)
        conversational_patterns = [
            r'why (have|are) you (been )?(quiet|grouchy|upset|acting)',  # More specific: requires emotion
            r'\b(quiet|grouchy|upset|feeling|mood|behavior)\b',  # Emotion/mood words
            r'what\'s wrong',
            r'are you (okay|ok|alright)',
            r'(cheer up|calm down|relax|take it easy)'
        ]
        if any(re.search(pattern, query_lower) is not None for pattern in conversational_patterns):
            return "conversational_query"

        # FAQ patterns (EXPANDED - added "have/has" variants)
        faq_patterns = [
            r'who (is|are|am)',
            r'what (is|are|have|has) (you|your|the)',
            r'how (do|does|did|have|has) (you|i)',
            r'where (is|are|do|have|has)',
            r'when (is|are|do|did|have|has)'
        ]
        if any(re.search(pattern, query_lower) is not None for pattern in faq_patterns):
            return "faq"

        # Gaming query patterns - must have specific gaming context
        gaming_patterns = [
            r'(game|play|episode|hour|complete|finish)',
            r'(jonesy|captain)',
            r'(series|genre|rpg|horror)',
            r'(youtube|twitch|view|stream)'
        ]
        if any(re.search(pattern, query_lower) is not None for pattern in gaming_patterns):
            return "gaming_query"

        # Personality/greeting patterns
        personality_patterns = [
            r'^(hello|hi|hey|greetings)',
            r'(thank|thanks|appreciate)',
            r'(good (morning|afternoon|evening|night))',
            r'how are you'
        ]
        if any(re.search(pattern, query_lower) is not None for pattern in personality_patterns):
            return "personality"

        # Default to general
        return "general"

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry has expired"""
        now = datetime.now(ZoneInfo("Europe/London"))
        expiry_time = entry["expires_at"]
        return now >= expiry_time

    def _find_similar_cached_query(
        self,
        query: str,
        user_id: int,
        channel_id: Optional[int],
        is_dm: bool,
        similarity_threshold: float = 0.85
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Find similar cached query using fuzzy matching within the same conversation context.

        🚨 AGGRESSIVE RESTRICTIONS: Cache fuzzy matching heavily restricted to prevent false positives.
        - Gaming queries: DISABLED (always query database fresh)
        - Conversational: DISABLED (too context-dependent)
        - Questions: NEAR-EXACT only (0.98+ similarity required)
        - FAQ only: Moderate matching allowed
        """
        normalized_query = self._normalize_query(query)

        # Detect query type and category
        query_type = self._detect_query_type(query)
        query_category = self._detect_query_category(query)

        # Calculate query characteristics
        query_words = set(normalized_query.split())
        query_length = len(query_words)

        # 🚨 CRITICAL FIX: DISABLE fuzzy matching for gaming queries entirely
        # Gaming queries should ALWAYS hit the database for fresh data
        if query_category == 'gaming_query':
            logger.info(f"🚨 CACHE POLICY: Gaming query detected - DISABLING fuzzy match to ensure fresh database query")
            return None  # Force cache miss for gaming queries

        # 🚨 ULTRA-AGGRESSIVE RESTRICTION: Disable fuzzy matching for almost everything
        adjusted_threshold = 0.99  # Default: essentially exact match only

        # 🚨 CRITICAL: Disable fuzzy matching for conversational, personality, and question types
        if query_type in ['conversational', 'question_identity', 'question_status']:
            logger.debug(f"Cache: DISABLED fuzzy match for type '{query_type}' (too context-dependent)")
            return None  # Never fuzzy match these types

        # Whitelist: Only enable fuzzy matching for FAQ with VERY strict threshold
        if query_category == 'faq':
            # 🚨 RAISED from 0.92 → 0.95: FAQ responses need near-exact match
            # This prevents "Who is Jonesy?" from matching "What is your purpose?"
            adjusted_threshold = 0.95
            logger.debug(f"Cache: FAQ fuzzy match enabled with strict threshold: {adjusted_threshold}")
        else:
            # Everything else: no fuzzy matching
            logger.debug(f"Cache: Fuzzy match DISABLED for category '{query_category}' and type '{query_type}'")
            return None

        best_match = None
        best_similarity = 0.0

        # Optimize for large caches: search random sample instead of entire cache
        cache_items = list(self.cache.items())
        sample_size = min(len(cache_items), 1000)  # Search max 1000 entries

        if len(cache_items) > 1000:
            cache_items = random.sample(cache_items, sample_size)

        for cache_key, entry in cache_items:
            if self._is_expired(entry):
                continue

            # CRITICAL: Only match within same conversation context
            entry_user_id = entry.get("user_id")
            entry_is_dm = entry.get("is_dm", False)
            entry_channel_id = entry.get("channel_id")

            # Skip if conversation context doesn't match
            if entry_user_id != user_id:
                continue
            if entry_is_dm != is_dm:
                continue
            if not is_dm and entry_channel_id != channel_id:
                continue

            cached_normalized = self._normalize_query(entry["original_query"])

            # NEW: Detect cached query type and category
            cached_type = self._detect_query_type(entry["original_query"])
            cached_category = entry.get("query_type", self._detect_query_category(entry["original_query"]))

            # 🚨 CRITICAL: Don't match different query types (now with sub-types)
            # This prevents "Who is X?" from matching "What is Y?"
            if query_type != cached_type:
                logger.debug(f"Cache: Skipping - type mismatch ({query_type} vs {cached_type})")
                continue
            
            # 🚨 EXTRA SAFETY: For question types, ensure exact sub-type match
            if query_type.startswith('question_') and cached_type.startswith('question_'):
                if query_type != cached_type:
                    logger.debug(f"Cache: Skipping - question sub-type mismatch ({query_type} vs {cached_type})")
                    continue

            # CRITICAL: Don't match different query categories (prevents gaming_query matching conversational_query)
            if query_category != cached_category:
                logger.debug(f"Cache: Skipping - category mismatch ({query_category} vs {cached_category})")
                continue

            # NEW: Check word overlap for additional validation
            cached_words = set(cached_normalized.split())
            word_overlap = self._calculate_word_overlap(query_words, cached_words)

            # Require meaningful word overlap (at least 30% shared words)
            if word_overlap < 0.3:
                logger.debug(f"Cache: Skipping - insufficient word overlap ({word_overlap:.2f})")
                continue

            # NEW: Check length similarity (messages of very different lengths rarely mean the same thing)
            length_ratio = min(query_length,
                               len(cached_words)) / max(query_length,
                                                        len(cached_words)) if max(query_length,
                                                                                  len(cached_words)) > 0 else 0
            if length_ratio < 0.6:  # Lengths must be within 60% of each other
                logger.debug(f"Cache: Skipping - length mismatch ({length_ratio:.2f})")
                continue

            # Calculate sequence similarity
            similarity = SequenceMatcher(
                None,
                normalized_query,
                cached_normalized
            ).ratio()

            if similarity > best_similarity and similarity >= adjusted_threshold:
                best_similarity = similarity
                best_match = (cache_key, entry)
                logger.debug(
                    f"Cache: Potential match - similarity {similarity:.2f}, overlap {word_overlap:.2f}, type {query_type}")

        if best_match:
            logger.info(f"Cache: Found similar query (similarity: {best_similarity:.2f}, type: {query_type})")

        return best_match

    def get(
        self,
        query: str,
        user_id: int,
        channel_id: Optional[int] = None,
        is_dm: bool = False,
        similarity_threshold: float = 0.85
    ) -> Optional[str]:
        """
        Get cached response for query with conversation context isolation.

        🚨 AGGRESSIVE CACHE POLICY:
        - Gaming queries: NO CACHE (always fresh from database)
        - Exact matches: Allowed for all types
        - Fuzzy matches: Only FAQ, extremely restricted

        Args:
            query: The query string
            user_id: User ID making the query
            channel_id: Channel ID (None for DMs)
            is_dm: Whether this is a DM conversation
            similarity_threshold: Minimum similarity for fuzzy matching

        Returns:
            Cached response text or None if not found/expired
        """
        with self._lock:
            self.stats["total_queries"] += 1

            # 🚨 CRITICAL FIX: Detect gaming queries and skip cache entirely
            query_category = self._detect_query_category(query)
            if query_category == 'gaming_query':
                self.stats["misses"] += 1
                logger.info(f"🚨 CACHE BYPASS: Gaming query detected - forcing fresh database query")
                return None  # Always bypass cache for gaming queries

            # Try exact match first with conversation context
            cache_key = self._generate_cache_key(query, user_id, channel_id, is_dm)

            if cache_key in self.cache:
                entry = self.cache[cache_key]

                # Check if expired
                if self._is_expired(entry):
                    del self.cache[cache_key]
                    self.stats["misses"] += 1
                    return None

                # Update hit stats
                entry["hits"] += 1
                entry["last_accessed"] = datetime.now(ZoneInfo("Europe/London"))

                self.stats["hits"] += 1
                self.stats["saves"] += 1

                context_type = "DM" if is_dm else f"channel_{channel_id}"
                logger.info(f"CACHE HIT: {query[:50]}... (exact match in {context_type}, {entry['hits']} total hits)")
                return entry["response"]

            # Try similarity matching within same conversation context (restricted to FAQ only now)
            similar_match = self._find_similar_cached_query(query, user_id, channel_id, is_dm, similarity_threshold)

            if similar_match:
                cache_key, entry = similar_match

                # Update hit stats
                entry["hits"] += 1
                entry["last_accessed"] = datetime.now(ZoneInfo("Europe/London"))

                self.stats["hits"] += 1
                self.stats["saves"] += 1

                context_type = "DM" if is_dm else f"channel_{channel_id}"
                logger.info(f"CACHE HIT: {query[:50]}... (fuzzy match in {context_type}, {entry['hits']} total hits)")
                return entry["response"]

            # Cache miss
            self.stats["misses"] += 1
            context_type = "DM" if is_dm else f"channel_{channel_id}"
            logger.debug(f"CACHE MISS: {query[:50]}... (context: {context_type})")
            return None

    def set(
        self,
        query: str,
        response: str,
        user_id: int,
        channel_id: Optional[int] = None,
        is_dm: bool = False,
        query_type: Optional[str] = None
    ):
        """
        Cache a response with conversation context.

        Args:
            query: The query string
            response: The AI response to cache
            user_id: User ID who made the query
            channel_id: Channel ID (None for DMs)
            is_dm: Whether this is a DM conversation
            query_type: Optional type override, auto-detected if None
        """
        with self._lock:
            # Periodically clean up expired entries to prevent unbounded growth
            if len(self.cache) > 500 and len(self.cache) % 50 == 0:
                self.cleanup_expired()

            # Generate cache key with conversation context
            cache_key = self._generate_cache_key(query, user_id, channel_id, is_dm)

            # Detect query category if not provided (for TTL determination)
            if query_type is None:
                query_type = self._detect_query_category(query)

            # Calculate expiry time
            ttl_seconds = self.ttl_config.get(query_type, self.ttl_config["general"])
            now = datetime.now(ZoneInfo("Europe/London"))
            expires_at = now + timedelta(seconds=ttl_seconds)

            # Store in cache with conversation context
            self.cache[cache_key] = {
                "original_query": query,
                "response": response,
                "user_id": user_id,
                "channel_id": channel_id,
                "is_dm": is_dm,
                "query_type": query_type,
                "created_at": now,
                "expires_at": expires_at,
                "last_accessed": now,
                "hits": 0
            }

            ttl_hours = ttl_seconds / 3600
            context_type = "DM" if is_dm else f"channel_{channel_id}"
            logger.info(
                f"CACHE SET: {query[:50]}... (type: {query_type}, context: {context_type}, TTL: {ttl_hours:.1f}h)")

    def cleanup_expired(self) -> int:
        """Remove expired cache entries. Returns number of entries removed."""
        with self._lock:
            expired_keys = [
                key for key, entry in self.cache.items()
                if self._is_expired(entry)
            ]

            for key in expired_keys:
                del self.cache[key]

            if expired_keys:
                logger.info(f"Cache cleanup: Removed {len(expired_keys)} expired entries")

            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            hit_rate = (
                (self.stats["hits"] / self.stats["total_queries"] * 100)
                if self.stats["total_queries"] > 0
                else 0.0
            )

            return {
                **self.stats,
                "hit_rate": hit_rate,
                "cache_size": len(self.cache),
                "api_calls_saved": self.stats["saves"]
            }

    def clear(self):
        """Clear all cache entries"""
        with self._lock:
            size = len(self.cache)
            self.cache.clear()
            logger.info(f"Cache cleared: Removed {size} entries")

    def get_cache_info(self) -> List[Dict[str, Any]]:
        """Get information about cached entries for debugging"""
        with self._lock:
            info = []

            for key, entry in self.cache.items():
                now = datetime.now(ZoneInfo("Europe/London"))
                time_remaining = (entry["expires_at"] - now).total_seconds()

                info.append({
                    "query": entry["original_query"][:50] + "...",
                    "type": entry["query_type"],
                    "hits": entry["hits"],
                    "created": entry["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                    "expires_in_hours": round(time_remaining / 3600, 1),
                    "is_expired": self._is_expired(entry)
                })

            # Sort by hits descending
            info.sort(key=lambda x: x["hits"], reverse=True)

            return info


# Global cache instance
_global_cache: Optional[AIResponseCache] = None


def get_cache() -> AIResponseCache:
    """Get or create global cache instance"""
    global _global_cache
    if _global_cache is None:
        _global_cache = AIResponseCache()
    return _global_cache


def clear_global_cache():
    """Clear the global cache instance"""
    global _global_cache
    if _global_cache:
        _global_cache.clear()
        _global_cache = None
