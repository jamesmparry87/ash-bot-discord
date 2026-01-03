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
        self.ttl_config = {
            "faq": 86400,           # 24 hours - FAQs rarely change
            "gaming_query": 21600,  # 6 hours - game data is relatively static
            "personality": 43200,   # 12 hours - greetings/personality responses
            "trivia": 604800,       # 7 days - pre-generated trivia questions
            "general": 10800        # 3 hours - general conversation
        }

    def _normalize_query(self, query: str) -> str:
        """Normalize query for better matching while preserving conversational context"""
        # Convert to lowercase
        normalized = query.lower()

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

        Returns:
            - 'question': Questions requiring informational responses
            - 'conversational': Casual responses, greetings, acknowledgments
            - 'statement': Declarative statements
        """
        query_lower = query.lower().strip()

        # Question detection (most specific first)
        question_indicators = ['what', 'where', 'when', 'how', 'why', 'who', 'which', 'did',
                               'has', 'have', 'is', 'are', 'does', 'do', 'can', 'could', 'would', 'should']
        if any(query_lower.startswith(indicator) for indicator in question_indicators):
            return 'question'
        if query_lower.endswith('?'):
            return 'question'

        # Conversational responses (greetings, acknowledgments, casual chat)
        conversational_indicators = [
            'hi', 'hello', 'hey', 'thanks', 'thank you', 'ok', 'okay', 'cool', 'nice', 'great',
            'lol', 'haha', 'sure', 'alright', 'yeah', 'yep', 'nope', 'no worries',
            'take it easy', 'calm down', 'grouchy', 'chill', 'relax'
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

        # FAQ patterns
        faq_patterns = [
            r'who (is|are|am)',
            r'what (is|are) (you|your|the)',
            r'how (do|does|did) (you|i)',
            r'where (is|are|do)',
            r'when (is|are|do|did)'
        ]
        if any(re.search(pattern, query_lower) is not None for pattern in faq_patterns):
            return "faq"

        # Gaming query patterns
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

        IMPROVED: Prevents false matches between different query types (questions vs casual responses).
        Optimized to search a random sample for large caches to avoid O(N) complexity.
        CRITICAL: Only searches within the same conversation location (DM/channel isolation).
        """
        normalized_query = self._normalize_query(query)

        # NEW: Detect query type to prevent mismatches
        query_type = self._detect_query_type(query)

        # NEW: Calculate query characteristics
        query_words = set(normalized_query.split())
        query_length = len(query_words)

        # NEW: Adjust similarity threshold based on query length and type
        # Short messages need stricter matching to avoid false positives
        adjusted_threshold = similarity_threshold
        if query_length < 5:
            adjusted_threshold = 0.95  # Very strict for short messages
        elif query_length < 10:
            adjusted_threshold = 0.90  # Stricter for medium messages

        # CRITICAL: Conversational responses should NEVER match against questions
        if query_type == 'conversational':
            # Only match other conversational responses, with very strict similarity
            adjusted_threshold = 0.98

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

            # NEW: Detect cached query type
            cached_type = self._detect_query_type(entry["original_query"])

            # NEW: Don't match different query types (prevents "take it easy" matching "what are your plans")
            if query_type != cached_type:
                logger.debug(f"Cache: Skipping - type mismatch ({query_type} vs {cached_type})")
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

            # Try similarity matching within same conversation context
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
