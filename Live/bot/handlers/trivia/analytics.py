
import json
import logging
import re
from collections import Counter
from datetime import datetime
from typing import List, Optional, cast

from psycopg2.extras import RealDictRow

logger = logging.getLogger(__name__)


def calculate_dynamic_answer(db, dynamic_query_type: str, parameter: Optional[str] = None) -> Optional[str]:
    """
    Calculate the current answer for a dynamic question, with optional filtering.

    Supports platform-specific queries to distinguish YouTube playthroughs from Twitch VODs.
    """
    conn = db.get_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            base_query = "SELECT canonical_name FROM played_games"
            where_clauses = []
            params = []
            order_by = ""

            # Add filter if a parameter (like a series name) is provided
            if parameter:
                where_clauses.append("(LOWER(series_name) = %s OR LOWER(genre) = %s)")
                params.extend([parameter.lower(), parameter.lower()])

            # Define query logic with platform-specific options
            if dynamic_query_type == "most_popular_by_views":
                where_clauses.extend(["youtube_views > 0",
                                      "youtube_playlist_url IS NOT NULL",
                                      "youtube_playlist_url != ''"])
                order_by = "ORDER BY youtube_views DESC"

            # YouTube-specific queries
            elif dynamic_query_type == "most_youtube_episodes":
                where_clauses.extend(["total_episodes > 0",
                                      "youtube_playlist_url IS NOT NULL",
                                      "youtube_playlist_url != ''"])
                order_by = "ORDER BY total_episodes DESC"
            elif dynamic_query_type == "longest_youtube_playthrough":
                where_clauses.extend(["total_playtime_minutes > 0",
                                      "youtube_playlist_url IS NOT NULL",
                                      "youtube_playlist_url != ''"])
                order_by = "ORDER BY total_playtime_minutes DESC"

            # Twitch-specific queries
            elif dynamic_query_type == "most_twitch_vods":
                where_clauses.extend(["total_episodes > 0", "twitch_vod_urls IS NOT NULL",
                                     "twitch_vod_urls != ''", "twitch_vod_urls != '{}'"])
                order_by = "ORDER BY total_episodes DESC"
            elif dynamic_query_type == "longest_twitch_stream":
                where_clauses.extend(["total_playtime_minutes > 0", "twitch_vod_urls IS NOT NULL",
                                     "twitch_vod_urls != ''", "twitch_vod_urls != '{}'"])
                order_by = "ORDER BY total_playtime_minutes DESC"

            # Generic queries (mixed platforms)
            elif dynamic_query_type == "longest_playtime":
                where_clauses.append("total_playtime_minutes > 0")
                order_by = "ORDER BY total_playtime_minutes DESC"
            elif dynamic_query_type == "shortest_playtime":
                where_clauses.append("total_playtime_minutes > 0")
                order_by = "ORDER BY total_playtime_minutes ASC"
            elif dynamic_query_type == "most_episodes":
                where_clauses.append("total_episodes > 0")
                order_by = "ORDER BY total_episodes DESC"

            # ✅ FIX: New query type for most episodes among COMPLETED games only
            elif dynamic_query_type == "most_episodes_completed":
                where_clauses.extend(["total_episodes > 0", "completion_status = 'completed'"])
                order_by = "ORDER BY total_episodes DESC"

            # Date-based queries (newest/most recent)
            elif dynamic_query_type == "newest_game":
                where_clauses.append("release_year IS NOT NULL")
                order_by = "ORDER BY release_year DESC"
            elif dynamic_query_type == "most_recent_game":
                where_clauses.append("first_played_date IS NOT NULL")
                order_by = "ORDER BY first_played_date DESC"
            elif dynamic_query_type == "oldest_game":
                where_clauses.append("release_year IS NOT NULL")
                order_by = "ORDER BY release_year ASC"

            # ===== PHASE 1: SERIES BATTLES =====
            elif dynamic_query_type == "series_playtime_comparison":
                # Parameter format: "Series A vs Series B"
                if not parameter or " vs " not in parameter.lower():
                    return None
                series_a, series_b = [s.strip() for s in parameter.split(" vs ", 1)]

                # Query total playtime for each series
                cur.execute("""
                        SELECT series_name, SUM(total_playtime_minutes) as total_playtime
                        FROM played_games
                        WHERE LOWER(series_name) IN (%s, %s)
                        AND total_playtime_minutes > 0
                        GROUP BY series_name
                        ORDER BY total_playtime DESC
                        LIMIT 1
                    """, (series_a.lower(), series_b.lower()))
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            elif dynamic_query_type == "series_episode_comparison":
                # Parameter format: "Series A vs Series B"
                if not parameter or " vs " not in parameter.lower():
                    return None
                series_a, series_b = [s.strip() for s in parameter.split(" vs ", 1)]

                # Query total episodes for each series
                cur.execute("""
                        SELECT series_name, SUM(total_episodes) as total_episodes
                        FROM played_games
                        WHERE LOWER(series_name) IN (%s, %s)
                        AND total_episodes > 0
                        GROUP BY series_name
                        ORDER BY total_episodes DESC
                        LIMIT 1
                    """, (series_a.lower(), series_b.lower()))
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            elif dynamic_query_type == "series_completion_comparison":
                # Parameter format: "Series A vs Series B"
                if not parameter or " vs " not in parameter.lower():
                    return None
                series_a, series_b = [s.strip() for s in parameter.split(" vs ", 1)]

                # Query completed games count for each series
                cur.execute("""
                        SELECT series_name, COUNT(*) as completed_count
                        FROM played_games
                        WHERE LOWER(series_name) IN (%s, %s)
                        AND completion_status = 'completed'
                        GROUP BY series_name
                        ORDER BY completed_count DESC
                        LIMIT 1
                    """, (series_a.lower(), series_b.lower()))
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            elif dynamic_query_type == "series_views_comparison":
                # Parameter format: "Series A vs Series B"
                if not parameter or " vs " not in parameter.lower():
                    return None
                series_a, series_b = [s.strip() for s in parameter.split(" vs ", 1)]

                # Query total YouTube views for each series
                cur.execute("""
                        SELECT series_name, SUM(youtube_views) as total_views
                        FROM played_games
                        WHERE LOWER(series_name) IN (%s, %s)
                        AND youtube_views > 0
                        GROUP BY series_name
                        ORDER BY total_views DESC
                        LIMIT 1
                    """, (series_a.lower(), series_b.lower()))
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            # ===== PHASE 1: GENRE INSIGHTS =====
            elif dynamic_query_type == "most_played_genre":
                # Which genre has the most games
                cur.execute("""
                        SELECT genre, COUNT(*) as game_count
                        FROM played_games
                        WHERE genre IS NOT NULL AND genre != ''
                        GROUP BY genre
                        ORDER BY game_count DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['genre'] if result else None

            elif dynamic_query_type == "longest_genre_playtime":
                # Which genre has the most total playtime
                cur.execute("""
                        SELECT genre, SUM(total_playtime_minutes) as total_playtime
                        FROM played_games
                        WHERE genre IS NOT NULL AND genre != ''
                        AND total_playtime_minutes > 0
                        GROUP BY genre
                        ORDER BY total_playtime DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['genre'] if result else None

            elif dynamic_query_type == "most_popular_genre_by_views":
                # Which genre has the most total YouTube views
                cur.execute("""
                        SELECT genre, SUM(youtube_views) as total_views
                        FROM played_games
                        WHERE genre IS NOT NULL AND genre != ''
                        AND youtube_views > 0
                        GROUP BY genre
                        ORDER BY total_views DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['genre'] if result else None

            elif dynamic_query_type == "genre_with_most_completed_games":
                # Which genre has the most completed games
                cur.execute("""
                        SELECT genre, COUNT(*) as completed_count
                        FROM played_games
                        WHERE genre IS NOT NULL AND genre != ''
                        AND completion_status = 'completed'
                        GROUP BY genre
                        ORDER BY completed_count DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['genre'] if result else None

            # ===== PHASE 2: MEMORABLE MILESTONES =====
            elif dynamic_query_type == "longest_completed_game":
                # Longest game Jonesy has completed (by playtime)
                cur.execute("""
                        SELECT canonical_name, total_playtime_minutes
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND total_playtime_minutes > 0
                        ORDER BY total_playtime_minutes DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['canonical_name'] if result else None

            elif dynamic_query_type == "shortest_completed_game":
                # Shortest completed game (by playtime)
                cur.execute("""
                        SELECT canonical_name, total_playtime_minutes
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND total_playtime_minutes > 0
                        ORDER BY total_playtime_minutes ASC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['canonical_name'] if result else None

            elif dynamic_query_type == "first_game_ever_played":
                # First game on the channel (earliest first_played_date)
                cur.execute("""
                        SELECT canonical_name, first_played_date
                        FROM played_games
                        WHERE first_played_date IS NOT NULL
                        ORDER BY first_played_date ASC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['canonical_name'] if result else None

            elif dynamic_query_type == "most_recent_completed_game":
                # Most recently completed game
                cur.execute("""
                        SELECT canonical_name, first_played_date
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND first_played_date IS NOT NULL
                        ORDER BY first_played_date DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['canonical_name'] if result else None

            elif dynamic_query_type == "oldest_completed_game_by_release":
                # Oldest game (by release year) that Jonesy has completed
                cur.execute("""
                        SELECT canonical_name, release_year
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND release_year IS NOT NULL
                        ORDER BY release_year ASC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['canonical_name'] if result else None

            elif dynamic_query_type == "newest_completed_game_by_release":
                # Newest game (by release year) that Jonesy has completed
                cur.execute("""
                        SELECT canonical_name, release_year
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND release_year IS NOT NULL
                        ORDER BY release_year DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['canonical_name'] if result else None

            # ===== PHASE 3: SERIES KNOWLEDGE & ENGAGEMENT =====
            elif dynamic_query_type == "series_with_most_games":
                # Which series has the most games played
                cur.execute("""
                        SELECT series_name, COUNT(*) as game_count
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        GROUP BY series_name
                        ORDER BY game_count DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            elif dynamic_query_type == "series_total_playtime":
                # Total playtime for a specific series (requires parameter)
                if not parameter:
                    return None

                cur.execute("""
                        SELECT series_name, SUM(total_playtime_minutes) as total_playtime
                        FROM played_games
                        WHERE LOWER(series_name) = %s
                        AND total_playtime_minutes > 0
                        GROUP BY series_name
                    """, (parameter.lower(),))
                result = cur.fetchone()

                if result:
                    total_minutes = cast(RealDictRow, result)['total_playtime']
                    total_hours = int(total_minutes / 60)
                    return f"{total_hours} hours"
                return None

            elif dynamic_query_type == "series_with_most_completed_games":
                # Series with the most completed games
                cur.execute("""
                        SELECT series_name, COUNT(*) as completed_count
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        AND completion_status = 'completed'
                        GROUP BY series_name
                        ORDER BY completed_count DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            elif dynamic_query_type == "most_incomplete_series":
                # Series with the most incomplete games
                cur.execute("""
                        SELECT series_name, COUNT(*) as incomplete_count
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        AND completion_status != 'completed'
                        GROUP BY series_name
                        ORDER BY incomplete_count DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            elif dynamic_query_type == "longest_average_series_length":
                # Series with the longest average playtime per game
                cur.execute("""
                        SELECT series_name, AVG(total_playtime_minutes) as avg_playtime
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        AND total_playtime_minutes > 0
                        GROUP BY series_name
                        HAVING COUNT(*) >= 2
                        ORDER BY avg_playtime DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            # ===== PHASE 4: ADVANCED PATTERNS =====
            elif dynamic_query_type == "best_views_per_episode":
                # Game with the best engagement rate (views per episode)
                cur.execute("""
                        SELECT canonical_name,
                               (youtube_views::float / NULLIF(total_episodes, 0)) as engagement_rate
                        FROM played_games
                        WHERE youtube_views > 0
                        AND total_episodes > 0
                        AND youtube_playlist_url IS NOT NULL
                        ORDER BY engagement_rate DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['canonical_name'] if result else None

            elif dynamic_query_type == "youtube_only_count":
                # Count of YouTube-exclusive games
                cur.execute("""
                        SELECT COUNT(*) as count
                        FROM played_games
                        WHERE youtube_playlist_url IS NOT NULL
                        AND youtube_playlist_url != ''
                        AND (twitch_vod_urls IS NULL OR twitch_vod_urls = '' OR twitch_vod_urls = '{}')
                    """)
                result = cur.fetchone()
                count = cast(RealDictRow, result)['count'] if result else 0
                return str(count)

            elif dynamic_query_type == "twitch_only_count":
                # Count of Twitch-exclusive games
                cur.execute("""
                        SELECT COUNT(*) as count
                        FROM played_games
                        WHERE (twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}')
                        AND (youtube_playlist_url IS NULL OR youtube_playlist_url = '')
                    """)
                result = cur.fetchone()
                count = cast(RealDictRow, result)['count'] if result else 0
                return str(count)

            elif dynamic_query_type == "most_cross_platform_series":
                # Series played on both YouTube and Twitch
                cur.execute("""
                        SELECT series_name, COUNT(*) as cross_platform_count
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        AND youtube_playlist_url IS NOT NULL AND youtube_playlist_url != ''
                        AND twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}'
                        GROUP BY series_name
                        ORDER BY cross_platform_count DESC
                        LIMIT 1
                    """)
                result = cur.fetchone()
                return cast(RealDictRow, result)['series_name'] if result else None

            elif dynamic_query_type == "total_completed_count":
                # Total number of completed games
                cur.execute("""
                        SELECT COUNT(*) as count
                        FROM played_games
                        WHERE completion_status = 'completed'
                    """)
                result = cur.fetchone()
                count = cast(RealDictRow, result)['count'] if result else 0
                return str(count)

            elif dynamic_query_type == "completion_rate_percentage":
                # Overall completion rate as a percentage
                cur.execute("""
                        SELECT
                            COUNT(CASE WHEN completion_status = 'completed' THEN 1 END)::float /
                            NULLIF(COUNT(*), 0) * 100 as completion_rate
                        FROM played_games
                    """)
                result = cur.fetchone()
                if result:
                    rate = cast(RealDictRow, result)['completion_rate']
                    return f"{int(rate)}%"
                return None

            else:
                return None  # Unknown query type

            # Build and execute the final query (for non-genre/series queries)
            if where_clauses:  # Only execute if we have a traditional query
                full_query = f"{base_query} WHERE {' AND '.join(where_clauses)} {order_by} LIMIT 1"
                cur.execute(full_query, tuple(params))
                result = cur.fetchone()
                return cast(RealDictRow, result)['canonical_name'] if result else None

            return None
    except Exception as e:
        logger.error(f"Error calculating dynamic answer for {dynamic_query_type}: {e}")
        return None


def get_recent_question_patterns(db, limit: int = 10) -> List[str]:
    """
    ✅ FIX #3: Get recently used question patterns for diversity enforcement

    Analyzes recent questions to identify patterns and prevent repetition.
    Returns list of pattern identifiers from recently used/added questions.
    """
    conn = db.get_connection()
    if not conn:
        return []

    try:
        with conn.cursor() as cur:
            # Get recently used questions (last 10 sessions) + recently added questions
            cur.execute("""
                    SELECT DISTINCT q.question_text, q.created_at, q.last_used_at
                    FROM trivia_questions q
                    WHERE q.is_active = TRUE
                    AND (q.last_used_at IS NOT NULL OR q.created_at > NOW() - INTERVAL '7 days')
                    ORDER BY COALESCE(q.last_used_at, q.created_at) DESC
                    LIMIT %s
                """, (limit,))

            recent_questions = cur.fetchall()
            patterns = []

            for row in recent_questions:
                question_text = dict(row)['question_text'].lower()

                # Identify pattern types
                if ' or ' in question_text and ('first' in question_text or 'before' in question_text):
                    patterns.append('comparison_temporal')
                elif ' vs ' in question_text or ' or ' in question_text:
                    patterns.append('comparison_choice')
                elif 'most' in question_text or 'longest' in question_text or 'highest' in question_text:
                    patterns.append('superlative_most')
                elif 'least' in question_text or 'shortest' in question_text or 'lowest' in question_text:
                    patterns.append('superlative_least')
                elif 'first' in question_text and 'play' in question_text:
                    patterns.append('temporal_first')
                elif 'completed' in question_text or 'finished' in question_text:
                    patterns.append('completion_status')
                elif 'how many' in question_text:
                    patterns.append('count_query')
                else:
                    patterns.append('general')

            logger.info(f"Recent question patterns: {patterns[:5]}")
            return patterns

    except Exception as e:
        logger.error(f"Error getting recent question patterns: {e}")
        return []


def should_avoid_pattern(pattern: str, recent_patterns: List[str], threshold: int = 3) -> bool:
    """
    ✅ FIX #3: Check if a pattern has been overused recently

    Args:
        pattern: The pattern to check
        recent_patterns: List of recently used patterns
        threshold: Maximum allowed occurrences before avoiding (default: 3 out of 10)

    Returns:
        True if pattern should be avoided, False if it's okay to use
    """
    if not recent_patterns:
        return False

    # Count occurrences of this pattern in recent questions
    pattern_count = recent_patterns.count(pattern)

    # If pattern appears more than threshold times, avoid it
    should_avoid = pattern_count >= threshold

    if should_avoid:
        logger.info(f"Pattern '{pattern}' overused ({pattern_count}/{len(recent_patterns)}), avoiding")

    return should_avoid


from ...utils.text_processing import extract_question_concepts, calculate_concept_similarity
