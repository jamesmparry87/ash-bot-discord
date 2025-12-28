"""
AI Response Cache Module

Implements intelligent caching for AI responses to maximize API quota efficiency.
Reduces redundant API calls by caching similar queries and responses.
"""

import hashlib
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


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
        """Normalize query for better matching"""
        # Convert to lowercase
        normalized = query.lower()
        
        # Remove extra whitespace
        normalized = " ".join(normalized.split())
        
        # Remove common punctuation at end
        normalized = normalized.rstrip('?.!,')
        
        # Remove common filler words for better matching
        filler_words = ['please', 'can you', 'could you', 'would you', 'um', 'uh']
        for filler in filler_words:
            normalized = normalized.replace(filler, '')
        
        # Clean up again after removals
        normalized = " ".join(normalized.split())
        
        return normalized

    def _generate_cache_key(self, query: str) -> str:
        """Generate cache key from normalized query"""
        normalized = self._normalize_query(query)
        # Use MD5 hash for consistent key generation
        return hashlib.md5(normalized.encode()).hexdigest()

    def _detect_query_type(self, query: str) -> str:
        """Detect the type of query for appropriate TTL"""
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
        similarity_threshold: float = 0.85
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Find similar cached query using fuzzy matching"""
        normalized_query = self._normalize_query(query)
        
        best_match = None
        best_similarity = 0.0
        
        for cache_key, entry in self.cache.items():
            if self._is_expired(entry):
                continue
            
            cached_normalized = self._normalize_query(entry["original_query"])
            similarity = SequenceMatcher(
                None, 
                normalized_query, 
                cached_normalized
            ).ratio()
            
            if similarity > best_similarity and similarity >= similarity_threshold:
                best_similarity = similarity
                best_match = (cache_key, entry)
        
        return best_match

    def get(
        self, 
        query: str, 
        user_id: int,
        similarity_threshold: float = 0.85
    ) -> Optional[str]:
        """
        Get cached response for query.
        
        Args:
            query: The query string
            user_id: User ID making the query
            similarity_threshold: Minimum similarity for fuzzy matching
            
        Returns:
            Cached response text or None if not found/expired
        """
        self.stats["total_queries"] += 1
        
        # Try exact match first
        cache_key = self._generate_cache_key(query)
        
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
            
            print(f"✅ CACHE HIT: {query[:50]}... (exact match, {entry['hits']} total hits)")
            return entry["response"]
        
        # Try similarity matching
        similar_match = self._find_similar_cached_query(query, similarity_threshold)
        
        if similar_match:
            cache_key, entry = similar_match
            
            # Update hit stats
            entry["hits"] += 1
            entry["last_accessed"] = datetime.now(ZoneInfo("Europe/London"))
            
            self.stats["hits"] += 1
            self.stats["saves"] += 1
            
            print(f"✅ CACHE HIT: {query[:50]}... (fuzzy match, {entry['hits']} total hits)")
            return entry["response"]
        
        # Cache miss
        self.stats["misses"] += 1
        print(f"❌ CACHE MISS: {query[:50]}...")
        return None

    def set(
        self, 
        query: str, 
        response: str, 
        user_id: int,
        query_type: Optional[str] = None
    ):
        """
        Cache a response.
        
        Args:
            query: The query string
            response: The AI response to cache
            user_id: User ID who made the query
            query_type: Optional type override, auto-detected if None
        """
        cache_key = self._generate_cache_key(query)
        
        # Detect query type if not provided
        if query_type is None:
            query_type = self._detect_query_type(query)
        
        # Calculate expiry time
        ttl_seconds = self.ttl_config.get(query_type, self.ttl_config["general"])
        now = datetime.now(ZoneInfo("Europe/London"))
        expires_at = now + timedelta(seconds=ttl_seconds)
        
        # Store in cache
        self.cache[cache_key] = {
            "original_query": query,
            "response": response,
            "user_id": user_id,
            "query_type": query_type,
            "created_at": now,
            "expires_at": expires_at,
            "last_accessed": now,
            "hits": 0
        }
        
        ttl_hours = ttl_seconds / 3600
        print(f"💾 CACHE SET: {query[:50]}... (type: {query_type}, TTL: {ttl_hours:.1f}h)")

    def cleanup_expired(self) -> int:
        """Remove expired cache entries. Returns number of entries removed."""
        expired_keys = [
            key for key, entry in self.cache.items() 
            if self._is_expired(entry)
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            print(f"🧹 Cache cleanup: Removed {len(expired_keys)} expired entries")
        
        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
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
        size = len(self.cache)
        self.cache.clear()
        print(f"🗑️ Cache cleared: Removed {size} entries")

    def get_cache_info(self) -> List[Dict[str, Any]]:
        """Get information about cached entries for debugging"""
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
