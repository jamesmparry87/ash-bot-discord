"""
Database Games Module - Played Games Management

This module handles:
- Played games CRUD operations
- Game data enrichment (IGDB, YouTube, Twitch)
- Alternative names and series management
- View statistics and analytics
- Timeline and chronological operations
- Search and filtering
- Data quality and validation
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast
from zoneinfo import ZoneInfo

from psycopg2.extras import RealDictRow

logger = logging.getLogger(__name__)


class GamesDatabase:
    """
    Handles all played games database operations.

    This class manages the complete played_games table including
    CRUD operations, enrichment, analytics, and data quality.
    """

    def __init__(self, db_manager):
        """
        Initialize games database handler.

        Args:
            db_manager: DatabaseManager instance for connection access
        """
        self.db = db_manager

    def get_connection(self):
        """Get database connection from the database manager"""
        return self.db.get_connection()

    def get_config_value(self, key: str) -> Optional[str]:
        """Get a configuration value (delegates to config database)"""
        return self.db.config.get_config_value(key)

    def set_config_value(self, key: str, value: str):
        """Set a configuration value (delegates to config database)"""
        self.db.config.set_config_value(key, value)

    def add_played_game(self,
                        canonical_name: str,
                        alternative_names: Optional[List[str]] = None,
                        series_name: Optional[str] = None,
                        genre: Optional[str] = None,
                        release_year: Optional[int] = None,
                        first_played_date: Optional[str] = None,
                        completion_status: str = "unknown",
                        total_episodes: int = 0,
                        total_playtime_minutes: int = 0,
                        youtube_playlist_url: Optional[str] = None,
                        twitch_vod_urls: Optional[List[str]] = None,
                        notes: Optional[str] = None,
                        youtube_views: int = 0,
                        twitch_views: int = 0) -> bool:
        """Add a played game to the database"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                # NEW: Convert lists to JSON strings for robust storage
                alt_names_str = json.dumps(alternative_names) if alternative_names else '[]'
                vod_urls_str = json.dumps(twitch_vod_urls) if twitch_vod_urls else '[]'

                cur.execute("""
                    INSERT INTO played_games (
                        canonical_name, alternative_names, series_name, genre,
                        release_year, first_played_date, completion_status, total_episodes,
                        total_playtime_minutes, youtube_playlist_url, twitch_vod_urls, notes, youtube_views, twitch_views,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    canonical_name,
                    alt_names_str,
                    series_name,
                    genre,
                    release_year,
                    first_played_date,
                    completion_status,
                    total_episodes,
                    total_playtime_minutes,
                    youtube_playlist_url,
                    vod_urls_str,
                    notes,
                    youtube_views,
                    twitch_views
                ))
                conn.commit()
                logger.info(f"Added played game: {canonical_name}")
                return True
        except Exception as e:
            logger.error(f"Error adding played game {canonical_name}: {e}")
            conn.rollback()
            return False

    def get_played_game(self, name: str) -> Optional[Dict[str, Any]]:
        """Find a played game by name (searches canonical and alternative names)"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                name_lower = name.lower().strip()

                # Search canonical name first (exact match)
                cur.execute("""
                    SELECT * FROM played_games
                    WHERE LOWER(TRIM(canonical_name)) = %s
                """, (name_lower,))
                result = cur.fetchone()

                if result:
                    result_dict = dict(result)
                    # Convert TEXT fields back to lists for compatibility
                    result_dict = self._convert_text_to_arrays(result_dict)
                    logger.debug(
                        f"Found game by exact canonical name match: {name}")
                    return result_dict

                # Search alternative names (handles JSON, PostgreSQL array, and comma-separated formats)
                # Pre-filter in the database using LIKE to avoid fetching all rows, then do precise matching in Python.
                like_pattern = f'%{name_lower}%'
                cur.execute("""
                    SELECT * FROM played_games
                    WHERE alternative_names IS NOT NULL
                    AND alternative_names != ''
                    AND LOWER(alternative_names) LIKE %s
                """, (like_pattern,))
                all_games_with_alt_names = cur.fetchall()

                # Search alternative names in Python for better format compatibility
                for game_row in all_games_with_alt_names:
                    game_dict = dict(game_row)
                    alt_names_text = game_dict.get('alternative_names', '')
                    if alt_names_text:
                        alt_names = self._parse_comma_separated_list(alt_names_text)
                        # Check each alternative name (case-insensitive)
                        for alt_name in alt_names:
                            if alt_name.lower().strip() == name_lower:
                                result_dict = game_dict
                                result_dict = self._convert_text_to_arrays(result_dict)
                                logger.debug(f"Found game by alternative name match: {name} -> {alt_name}")
                                return result_dict

                # Fuzzy search on canonical names with better matching
                cur.execute(
                    "SELECT id, canonical_name, alternative_names FROM played_games")
                all_games = cur.fetchall()

                import difflib
                game_names_map = {}

                for game in all_games:
                    game_dict = dict(game)
                    canonical_name = game_dict.get('canonical_name')
                    if canonical_name:
                        canonical_lower = str(canonical_name).lower().strip()
                        game_names_map[canonical_lower] = game_dict

                        # Also add alternative names to the map (handle TEXT
                        # format)
                        alt_names_text = game_dict.get('alternative_names', '')
                        if alt_names_text and isinstance(alt_names_text, str):
                            alt_names = self._parse_comma_separated_list(
                                alt_names_text)
                            for alt_name in alt_names:
                                alt_lower = alt_name.lower().strip()
                                game_names_map[alt_lower] = game_dict

                # Try fuzzy matching with lower threshold for better matching
                all_name_keys = list(game_names_map.keys())
                matches = difflib.get_close_matches(
                    name_lower, all_name_keys, n=1, cutoff=0.75)

                if matches:
                    match_name = matches[0]
                    matched_game = game_names_map[match_name]
                    logger.debug(
                        f"Found game by fuzzy match: {name} -> {matched_game.get('canonical_name')}")

                    # Get the full game record
                    cur.execute(
                        "SELECT * FROM played_games WHERE id = %s", (matched_game['id'],))
                    full_result = cur.fetchone()
                    if full_result:
                        result_dict = dict(full_result)
                        result_dict = self._convert_text_to_arrays(result_dict)
                        return result_dict

                logger.debug(f"No game found for: {name}")
                return None
        except Exception as e:
            logger.error(f"Error getting played game {name}: {e}")
            return None

    def get_cached_youtube_rankings(self) -> List[Dict[str, Any]]:
        """Gets all played games ranked by their cached YouTube views."""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, canonical_name, youtube_views, last_youtube_sync
                    FROM played_games
                    WHERE youtube_views > 0
                    ORDER BY youtube_views DESC
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting cached YouTube rankings: {e}")
            return []

    def update_youtube_cache(self, game_rankings: List[Dict[str, Any]]) -> int:
        """Bulk updates the YouTube views and sync time for games."""
        conn = self.get_connection()
        if not conn or not game_rankings:
            return 0

        try:
            with conn.cursor() as cur:
                # Prepare data for batch update
                update_data = []
                sync_time = datetime.now(ZoneInfo("Europe/London"))
                for game in game_rankings:
                    # Align keys with the data from youtube.py and the database schema
                    if 'canonical_name' in game and 'youtube_views' in game:
                        update_data.append((game['youtube_views'], sync_time, game['canonical_name']))
                    if not update_data:
                        return 0

                # Use a temporary table for an efficient bulk update
                cur.execute("CREATE TEMP TABLE temp_youtube_updates (views INT, sync_time TIMESTAMP, name VARCHAR(255))")
                cur.executemany("INSERT INTO temp_youtube_updates VALUES (%s, %s, %s)", update_data)

                cur.execute("""
                    UPDATE played_games
                    SET
                        youtube_views = temp.views,
                        last_youtube_sync = temp.sync_time
                    FROM temp_youtube_updates temp
                    WHERE played_games.canonical_name = temp.name
                """)

                updated_count = cur.rowcount
                conn.commit()
                cur.execute("DROP TABLE temp_youtube_updates")
                logger.info(f"Updated YouTube cache for {updated_count} games.")
                return updated_count

        except Exception as e:
            logger.error(f"Error bulk updating YouTube cache: {e}")
            conn.rollback()
            return 0

    def get_games_by_twitch_views(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get games ranked by Twitch view count."""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        canonical_name,
                        series_name,
                        twitch_views,
                        total_episodes,
                        total_playtime_minutes,
                        completion_status,
                        twitch_vod_urls
                    FROM played_games
                    WHERE twitch_views > 0
                    ORDER BY twitch_views DESC
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by Twitch views: {e}")
            return []

    def get_games_by_total_views(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get games ranked by combined YouTube + Twitch views."""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        canonical_name,
                        series_name,
                        youtube_views,
                        twitch_views,
                        (COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0)) as total_views,
                        total_episodes,
                        total_playtime_minutes,
                        completion_status,
                        youtube_playlist_url,
                        twitch_vod_urls
                    FROM played_games
                    WHERE (youtube_views > 0 OR twitch_views > 0)
                    ORDER BY (COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0)) DESC
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by total views: {e}")
            return []

    def get_platform_comparison_stats(self) -> Dict[str, Any]:
        """Get comprehensive platform comparison statistics."""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                # YouTube statistics
                cur.execute("""
                    SELECT
                        COUNT(*) as game_count,
                        SUM(youtube_views) as total_views,
                        AVG(youtube_views) as avg_views_per_game,
                        SUM(total_episodes) as total_episodes
                    FROM played_games
                    WHERE youtube_playlist_url IS NOT NULL
                    AND youtube_playlist_url != ''
                    AND youtube_views > 0
                """)
                youtube_stats = cur.fetchone()

                # Twitch statistics
                cur.execute("""
                    SELECT
                        COUNT(*) as game_count,
                        SUM(twitch_views) as total_views,
                        AVG(twitch_views) as avg_views_per_game,
                        SUM(total_episodes) as total_vods
                    FROM played_games
                    WHERE twitch_vod_urls IS NOT NULL
                    AND twitch_vod_urls != ''
                    AND twitch_vod_urls != '{}'
                    AND twitch_views > 0
                """)
                twitch_stats = cur.fetchone()

                # Cross-platform games
                cur.execute("""
                    SELECT COUNT(*) as cross_platform_count
                    FROM played_games
                    WHERE youtube_views > 0
                    AND twitch_views > 0
                """)
                cross_platform = cur.fetchone()

                # Safe dictionary access with proper null handling
                youtube_dict = dict(youtube_stats) if youtube_stats else {}
                twitch_dict = dict(twitch_stats) if twitch_stats else {}
                cross_platform_dict = dict(cross_platform) if cross_platform else {}

                return {
                    'youtube': {
                        'game_count': int(youtube_dict.get('game_count') or 0),
                        'total_views': int(youtube_dict.get('total_views') or 0),
                        'avg_views_per_game': round(float(youtube_dict.get('avg_views_per_game') or 0), 1),
                        'total_content': int(youtube_dict.get('total_episodes') or 0)
                    },
                    'twitch': {
                        'game_count': int(twitch_dict.get('game_count') or 0),
                        'total_views': int(twitch_dict.get('total_views') or 0),
                        'avg_views_per_game': round(float(twitch_dict.get('avg_views_per_game') or 0), 1),
                        'total_content': int(twitch_dict.get('total_vods') or 0)
                    },
                    'cross_platform_count': int(cross_platform_dict.get('cross_platform_count') or 0)
                }
        except Exception as e:
            logger.error(f"Error getting platform comparison stats: {e}")
            return {}

    def get_engagement_metrics(self, game_name: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Calculate engagement efficiency metrics (views per episode/hour).
        If game_name provided: return metrics for that specific game
        If None: return top games by engagement rate
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                if game_name:
                    # Get metrics for specific game
                    cur.execute("""
                        SELECT
                            canonical_name,
                            series_name,
                            youtube_views,
                            twitch_views,
                            (COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0)) as total_views,
                            total_episodes,
                            total_playtime_minutes,
                            completion_status,
                            CASE
                                WHEN total_episodes > 0 THEN
                                    ROUND((COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::float / total_episodes, 1)
                                ELSE 0
                            END as views_per_episode,
                            CASE
                                WHEN total_playtime_minutes > 0 THEN
                                    ROUND((COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::float / (total_playtime_minutes::float / 60), 1)
                                ELSE 0
                            END as views_per_hour
                        FROM played_games
                        WHERE LOWER(canonical_name) LIKE LOWER(%s)
                        AND (youtube_views > 0 OR twitch_views > 0)
                        AND total_episodes > 0
                    """, (f'%{game_name}%',))
                else:
                    # Get top games by engagement rate
                    cur.execute("""
                        SELECT
                            canonical_name,
                            series_name,
                            youtube_views,
                            twitch_views,
                            (COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0)) as total_views,
                            total_episodes,
                            total_playtime_minutes,
                            completion_status,
                            CASE
                                WHEN total_episodes > 0 THEN
                                    ROUND((COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::float / total_episodes, 1)
                                ELSE 0
                            END as views_per_episode,
                            CASE
                                WHEN total_playtime_minutes > 0 THEN
                                    ROUND((COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::float / (total_playtime_minutes::float / 60), 1)
                                ELSE 0
                            END as views_per_hour
                        FROM played_games
                        WHERE (youtube_views > 0 OR twitch_views > 0)
                        AND total_episodes > 0
                        AND total_playtime_minutes > 0
                        ORDER BY
                            CASE
                                WHEN total_playtime_minutes > 0 THEN
                                    (COALESCE(youtube_views, 0) + COALESCE(twitch_views, 0))::float / (total_playtime_minutes::float / 60)
                                ELSE 0
                            END DESC
                        LIMIT %s
                    """, (limit,))

                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting engagement metrics: {e}")
            return []

    def _parse_comma_separated_list(self, text: Optional[str]) -> List[str]:
        """Convert JSON string, PostgreSQL array, or comma-separated string to list"""
        if not text or not isinstance(text, str):
            return []

        text = text.strip()

        # 1. Handle JSON format (The new standard) e.g. ["Game 1", "Game 2"]
        if text.startswith('[') and text.endswith(']'):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass  # Fallback to other methods if JSON parse fails

        # 2. Handle PostgreSQL array syntax: {"item1","item2"}
        if text.startswith('{') and text.endswith('}'):
            # Remove outer braces
            text = text[1:-1]
            import re

            # Regex to handle quoted strings properly
            items = re.findall(r'"([^"]*)"', text)
            if not items and text:  # Handle unquoted simple items
                items = text.split(',')
            return [item.strip() for item in items if item.strip()]

        # 3. Handle legacy comma-separated format
        return [item.strip() for item in text.split(',') if item.strip()]

    def _convert_text_to_arrays(
            self, game_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Convert TEXT fields back to arrays for backward compatibility"""
        # Convert alternative_names from TEXT to list
        if "alternative_names" in game_dict:
            if isinstance(game_dict["alternative_names"], str):
                game_dict["alternative_names"] = self._parse_comma_separated_list(
                    game_dict["alternative_names"])
            elif game_dict["alternative_names"] is None:
                game_dict["alternative_names"] = []

        # Convert twitch_vod_urls from TEXT to list
        if "twitch_vod_urls" in game_dict:
            if isinstance(game_dict["twitch_vod_urls"], str):
                game_dict["twitch_vod_urls"] = self._parse_comma_separated_list(
                    game_dict["twitch_vod_urls"])
            elif game_dict["twitch_vod_urls"] is None:
                game_dict["twitch_vod_urls"] = []

        return game_dict

    def _fuzzy_search_with_trgm(
            self, cur, name_lower: str) -> Optional[Dict[str, Any]]:
        """Database-level fuzzy search using pg_trgm extension"""
        try:
            # Set similarity threshold for this session
            cur.execute("SET pg_trgm.similarity_threshold = 0.75")

            # Search canonical names with similarity scoring
            cur.execute(
                """
                SELECT *, similarity(canonical_name, %s) as sim_score
                FROM played_games
                WHERE canonical_name %% %s
                ORDER BY sim_score DESC, canonical_name
                LIMIT 1
            """,
                (name_lower, name_lower),
            )
            result = cur.fetchone()

            if result:
                result_dict = dict(result)
                # Remove similarity score from final result
                result_dict.pop('sim_score', None)
                result_dict = self._convert_text_to_arrays(result_dict)
                logger.debug(
                    f"pg_trgm found match with similarity: {result.get('sim_score', 0)}")
                return result_dict

            # If no canonical match, try alternative names
            cur.execute(
                """
                SELECT *, similarity(alternative_names, %s) as sim_score
                FROM played_games
                WHERE alternative_names %% %s
                AND alternative_names IS NOT NULL
                AND alternative_names != ''
                ORDER BY sim_score DESC, canonical_name
                LIMIT 1
            """,
                (name_lower, name_lower),
            )
            result = cur.fetchone()

            if result:
                result_dict = dict(result)
                result_dict.pop('sim_score', None)
                result_dict = self._convert_text_to_arrays(result_dict)
                logger.debug(
                    f"pg_trgm found alt name match with similarity: {result.get('sim_score', 0)}")
                return result_dict

        except Exception as e:
            logger.debug(f"pg_trgm search failed, falling back to Python: {e}")

        return None

    def _fuzzy_search_python_optimized(
            self, cur, name_lower: str) -> Optional[Dict[str, Any]]:
        """Optimized Python-based fuzzy search as fallback"""
        try:
            # Get all games with full data (not just id/name) to avoid second
            # query
            cur.execute("SELECT * FROM played_games")
            all_games = cur.fetchall()

            if not all_games:
                return None

            import difflib

            # Build name mapping for fuzzy matching
            game_names_map = {}
            games_by_id = {}

            for game in all_games:
                game_dict = dict(game)
                games_by_id[game_dict["id"]] = game_dict

                canonical_name = game_dict.get("canonical_name")
                if canonical_name:
                    canonical_lower = str(canonical_name).lower().strip()
                    game_names_map[canonical_lower] = game_dict["id"]

                    # Also add alternative names to the map (handle TEXT
                    # format)
                    alt_names_text = game_dict.get("alternative_names", "")
                    if alt_names_text and isinstance(alt_names_text, str):
                        alt_names = self._parse_comma_separated_list(
                            alt_names_text)
                        for alt_name in alt_names:
                            alt_lower = alt_name.lower().strip()
                            game_names_map[alt_lower] = game_dict["id"]

            # Try fuzzy matching
            all_name_keys = list(game_names_map.keys())
            matches = difflib.get_close_matches(
                name_lower, all_name_keys, n=1, cutoff=0.75)

            if matches:
                match_name = matches[0]
                matched_game_id = game_names_map[match_name]
                game_dict = games_by_id[matched_game_id]
                result_dict = self._convert_text_to_arrays(game_dict)
                return result_dict

        except Exception as e:
            logger.error(f"Python fuzzy search failed: {e}")

        return None

    def _fuzzy_search_recommendations_with_trgm(
            self, cur, name_lower: str) -> Optional[int]:
        """Database-level fuzzy search for game recommendations using pg_trgm extension"""
        try:
            # Set similarity threshold for this session
            cur.execute("SET pg_trgm.similarity_threshold = 0.8")

            # Search game recommendation names with similarity scoring
            cur.execute(
                """
                SELECT id, similarity(name, %s) as sim_score
                FROM game_recommendations
                WHERE name %% %s
                ORDER BY sim_score DESC, name
                LIMIT 1
            """,
                (name_lower, name_lower),
            )
            result = cur.fetchone()

            if result:
                logger.debug(
                    f"pg_trgm found game recommendation match with similarity: {result.get('sim_score', 0)}")
                return int(result["id"])  # type: ignore

        except Exception as e:
            logger.debug(
                f"pg_trgm search for recommendations failed, falling back to Python: {e}")

        return None

    def _fuzzy_search_recommendations_python_optimized(
            self, cur, name_lower: str) -> Optional[int]:
        """Optimized Python-based fuzzy search for game recommendations as fallback"""
        try:
            # Get only id and name to minimize data transfer
            cur.execute("SELECT id, name FROM game_recommendations")
            all_recommendations = cur.fetchall()

            if not all_recommendations:
                return None

            import difflib

            # Build name mapping for fuzzy matching
            recommendation_names_map = {}

            for recommendation in all_recommendations:
                rec_dict = dict(recommendation)
                rec_id = rec_dict["id"]
                rec_name = rec_dict.get("name")

                if rec_name:
                    name_lower_clean = str(rec_name).lower().strip()
                    recommendation_names_map[name_lower_clean] = rec_id

            # Try fuzzy matching
            all_name_keys = list(recommendation_names_map.keys())
            matches = difflib.get_close_matches(
                name_lower, all_name_keys, n=1, cutoff=0.8)

            if matches:
                match_name = matches[0]
                matched_rec_id = recommendation_names_map[match_name]
                return int(matched_rec_id)

        except Exception as e:
            logger.error(
                f"Python fuzzy search for recommendations failed: {e}")

        return None

    def get_all_played_games(
            self, series_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all played games, optionally filtered by series"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                if series_name:
                    cur.execute("""
                        SELECT * FROM played_games
                        WHERE LOWER(series_name) = %s
                        ORDER BY release_year ASC NULLS LAST, canonical_name ASC
                    """, (series_name.lower(),))
                else:
                    cur.execute("""
                        SELECT * FROM played_games
                        ORDER BY
                            COALESCE(series_name, canonical_name) ASC,
                            release_year ASC NULLS LAST,
                            canonical_name ASC
                    """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting played games: {e}")
            return []

    def get_gaming_timeline(self, order: str = 'ASC') -> List[Dict[str, Any]]:
        """Get the full history of played games ordered by date"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            # Validate order
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        canonical_name,
                        first_played_date,
                        release_year,
                        genre,
                        series_name,
                        completion_status
                    FROM played_games
                    WHERE first_played_date IS NOT NULL
                    ORDER BY first_played_date {order_clause}
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting gaming timeline: {e}")
            return []

    def update_played_game(self, game_id: int, **kwargs) -> bool:
        """Update a played game's details"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                # Build dynamic update query
                valid_fields = [
                    'canonical_name',
                    'alternative_names',
                    'series_name',
                    'genre',
                    'release_year',
                    'platform',
                    'first_played_date',
                    'completion_status',
                    'total_episodes',
                    'total_playtime_minutes',
                    'youtube_playlist_url',
                    'twitch_vod_urls',
                    'notes',
                    'youtube_views',
                    'twitch_views']

                updates = []
                values = []

                for field, value in kwargs.items():
                    if field in valid_fields:
                        # Special handling for array fields - NEW: Store as JSON
                        if field in ['alternative_names', 'twitch_vod_urls']:
                            if isinstance(value, list):
                                # Convert list to JSON string
                                updates.append(f"{field} = %s")
                                values.append(json.dumps(value))
                            elif isinstance(value, str):
                                # Handle single string by converting to list then JSON
                                updates.append(f"{field} = %s")
                                values.append(json.dumps([value]))
                            else:
                                # Skip invalid array values
                                continue
                        else:
                            updates.append(f"{field} = %s")
                            values.append(value)

                if not updates:
                    return False

                updates.append("updated_at = CURRENT_TIMESTAMP")
                values.append(game_id)

                query = f"UPDATE played_games SET {', '.join(updates)} WHERE id = %s"
                cur.execute(query, values)
                conn.commit()

                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating played game {game_id}: {e}")
            conn.rollback()
            return False

    def remove_played_game(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Remove a played game by ID"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Get the game before deleting
                cur.execute(
                    "SELECT * FROM played_games WHERE id = %s", (game_id,))
                game = cur.fetchone()

                if game:
                    cur.execute(
                        "DELETE FROM played_games WHERE id = %s", (game_id,))
                    conn.commit()
                    game_dict = dict(game)
                    canonical_name = game_dict.get('canonical_name', 'Unknown')
                    logger.info(f"Removed played game: {canonical_name}")
                    return game_dict
                return None
        except Exception as e:
            logger.error(f"Error removing played game {game_id}: {e}")
            conn.rollback()
            return None

    def search_played_games(self, query: str) -> List[Dict[str, Any]]:
        """Search played games by name, series, or notes"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                query_lower = f"%{query.lower()}%"
                cur.execute(
                    """
                    SELECT * FROM played_games
                    WHERE LOWER(canonical_name) LIKE %s
                       OR LOWER(series_name) LIKE %s
                       OR LOWER(notes) LIKE %s
                       OR %s = ANY(SELECT LOWER(unnest(alternative_names)))
                    ORDER BY
                        CASE WHEN LOWER(canonical_name) = %s THEN 1 ELSE 2 END,
                        canonical_name ASC
                """, (query_lower, query_lower, query_lower, query.lower(), query.lower()), )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error searching played games: {e}")
            return []

    def get_series_games(self, series_name: str) -> List[Dict[str, Any]]:
        """Get all games in a specific series"""
        return self.get_all_played_games(series_name)

    def get_games_by_series_organized(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all games organized by series with chronological sorting"""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM played_games
                    WHERE series_name IS NOT NULL AND series_name != ''
                    ORDER BY
                        series_name ASC,
                        release_year ASC NULLS LAST,
                        canonical_name ASC
                """)
                results = cur.fetchall()

                # Group by series
                series_dict: Dict[str, List[Dict[str, Any]]] = {}
                for row in results:
                    game = dict(row)
                    series = game['series_name']
                    if series not in series_dict:
                        series_dict[series] = []
                    series_dict[series].append(game)

                return series_dict
        except Exception as e:
            logger.error(f"Error getting organized series: {e}")
            return {}

    def played_game_exists(self, name: str) -> bool:
        """Check if a game has been played (fuzzy match)"""
        return self.get_played_game(name) is not None

    def bulk_import_played_games(
            self, games_data: List[Dict[str, Any]]) -> int:
        """Bulk import played games data with upsert logic (insert or update)"""
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                # Optimization: Batch fetch all existing games to avoid N+1
                # queries
                canonical_names_to_check = [
                    g.get('canonical_name') for g in games_data if g.get('canonical_name')]

                if not canonical_names_to_check:
                    return 0

                # Single query to fetch all existing games
                cur.execute(
                    "SELECT * FROM played_games WHERE canonical_name = ANY(%s)",
                    (canonical_names_to_check,
                     ))
                existing_games_list = cur.fetchall()
                existing_games_map = {}
                for game in existing_games_list:
                    game_dict = dict(game)
                    canonical_name = game_dict.get('canonical_name')
                    if canonical_name:
                        existing_games_map[canonical_name] = game_dict

                imported_count = 0
                for game_data in games_data:
                    try:
                        canonical_name = game_data.get('canonical_name')
                        if not canonical_name:
                            continue

                        # Fast lookup from pre-fetched map instead of
                        # individual database query
                        existing_game = existing_games_map.get(canonical_name)

                        # Convert TEXT fields to arrays for compatibility if
                        # game exists
                        if existing_game:
                            existing_game = self._convert_text_to_arrays(
                                existing_game)

                        if existing_game:
                            # Update existing game, preserving existing data
                            # where new data is empty
                            update_fields = {}

                            # Only update fields that have new data or are
                            # empty in existing record
                            for field in [
                                'alternative_names',
                                'series_name',
                                'genre',
                                'release_year',
                                'platform',
                                'first_played_date',
                                'completion_status',
                                'total_episodes',
                                'total_playtime_minutes',
                                'youtube_playlist_url',
                                'twitch_vod_urls',
                                    'notes']:
                                new_value = game_data.get(field)
                                existing_value = existing_game.get(field)

                                # Update if new value exists and either
                                # existing is empty/null or new has more data
                                if new_value is not None:
                                    if field == "alternative_names" or field == "twitch_vod_urls":
                                        # For arrays, merge unique values
                                        if isinstance(
                                                new_value, list) and isinstance(
                                                existing_value, list):
                                            merged = list(
                                                set(existing_value + new_value))
                                            if merged != existing_value:
                                                update_fields[field] = merged
                                        elif isinstance(new_value, list) and new_value:
                                            update_fields[field] = new_value
                                    elif field == "total_episodes" or field == "total_playtime_minutes":
                                        # For numeric fields, use the higher
                                        # value
                                        if isinstance(
                                                new_value, int) and isinstance(
                                                existing_value, int):
                                            if new_value > existing_value:
                                                update_fields[field] = new_value
                                        elif isinstance(new_value, int) and new_value > 0:
                                            update_fields[field] = new_value
                                    elif field == 'notes':
                                        # For notes, append if different
                                        if isinstance(
                                                new_value, str) and new_value.strip():
                                            if not existing_value or new_value not in existing_value:
                                                if existing_value:
                                                    update_fields[field] = f"{existing_value} | {new_value}"
                                                else:
                                                    update_fields[field] = new_value
                                    else:
                                        # For other fields, update if existing
                                        # is empty or new value is different
                                        if not existing_value or (
                                                new_value != existing_value and str(new_value).strip()):
                                            update_fields[field] = new_value

                            # Apply updates if any
                            if update_fields:
                                self.update_played_game(
                                    existing_game["id"], **update_fields)
                                logger.info(
                                    f"Updated existing game: {canonical_name}")

                            imported_count += 1
                        else:
                            # Insert new game
                            cur.execute("""
                                INSERT INTO played_games (
                                    canonical_name, alternative_names, series_name, genre, release_year,
                                    platform, first_played_date, completion_status, total_episodes,
                                    total_playtime_minutes, youtube_playlist_url, twitch_vod_urls, notes,
                                    created_at, updated_at
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """, (
                                canonical_name,
                                game_data.get('alternative_names', []),
                                game_data.get('series_name'),
                                game_data.get('genre'),
                                game_data.get('release_year'),
                                game_data.get('platform'),
                                game_data.get('first_played_date'),
                                game_data.get('completion_status', 'unknown'),
                                game_data.get('total_episodes', 0),
                                game_data.get('total_playtime_minutes', 0),
                                game_data.get('youtube_playlist_url'),
                                game_data.get('twitch_vod_urls', []),
                                game_data.get('notes')
                            ))
                            logger.info(f"Inserted new game: {canonical_name}")
                            imported_count += 1

                    except Exception as e:
                        logger.error(
                            f"Error importing game {game_data.get('canonical_name', 'unknown')}: {e}")
                        continue

                conn.commit()
                logger.info(
                    f"Bulk imported/updated {imported_count} played games")
                return imported_count
        except Exception as e:
            logger.error(f"Error bulk importing played games: {e}")
            conn.rollback()
            return 0

    def deduplicate_played_games(self) -> int:
        """Find and merge duplicate games with identical canonical names"""
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                # Find games with duplicate canonical names
                cur.execute("""
                    SELECT LOWER(TRIM(canonical_name)) as canonical_name, COUNT(*) as count
                    FROM played_games
                    GROUP BY LOWER(TRIM(canonical_name))
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC
                """)
                duplicates = cur.fetchall()

                if not duplicates:
                    logger.info("No duplicate games found")
                    return 0

                merged_count = 0

                for duplicate in duplicates:
                    # Use dict key access for RealDictCursor compatibility
                    duplicate_dict = dict(duplicate)
                    canonical_name = duplicate_dict['canonical_name']
                    duplicate_count = duplicate_dict['count']

                    logger.info(
                        f"Processing {duplicate_count} duplicates of '{canonical_name}'")

                    # Get all games with this canonical name (case-insensitive)
                    cur.execute("""
                        SELECT * FROM played_games
                        WHERE LOWER(TRIM(canonical_name)) = LOWER(TRIM(%s))
                        ORDER BY created_at ASC
                    """, (canonical_name,))

                    duplicate_games = cur.fetchall()

                    if len(duplicate_games) < 2:
                        continue

                    # Keep the first game (oldest) as the master record
                    master_game = dict(duplicate_games[0])
                    games_to_merge = [dict(game)
                                      for game in duplicate_games[1:]]

                    # Merge data from all duplicates into the master record
                    # Handle NULL values from TEXT fields properly with explicit checks
                    master_alt_names = master_game.get("alternative_names")
                    if master_alt_names and master_alt_names != "" and isinstance(
                            master_alt_names, str) and master_alt_names.lower() != "null":
                        master_alt_names_list = self._parse_comma_separated_list(master_alt_names)
                    else:
                        master_alt_names_list = []

                    master_vod_urls = master_game.get("twitch_vod_urls")
                    if master_vod_urls and master_vod_urls != "" and isinstance(
                            master_vod_urls, str) and master_vod_urls.lower() != "null":
                        master_vod_urls_list = self._parse_comma_separated_list(master_vod_urls)
                    else:
                        master_vod_urls_list = []

                    merged_data = {
                        "alternative_names": master_alt_names_list,
                        "series_name": master_game.get("series_name"),
                        "genre": master_game.get("genre"),
                        "release_year": master_game.get("release_year"),
                        "platform": master_game.get("platform"),
                        "first_played_date": master_game.get("first_played_date"),
                        "completion_status": master_game.get(
                            "completion_status",
                            "unknown"),
                        "total_episodes": master_game.get(
                            "total_episodes",
                            0) or 0,
                        "total_playtime_minutes": master_game.get(
                            "total_playtime_minutes",
                            0) or 0,
                        "youtube_playlist_url": master_game.get("youtube_playlist_url"),
                        "twitch_vod_urls": master_vod_urls_list,
                        "notes": master_game.get("notes") or "",
                    }

                    # Merge data from duplicates
                    for duplicate_game in games_to_merge:
                        # Merge alternative names with NULL-safe handling
                        dup_alt_names = duplicate_game.get('alternative_names')
                        if dup_alt_names and dup_alt_names != "" and str(dup_alt_names).lower() != "null":
                            if isinstance(dup_alt_names, str):
                                # Handle TEXT format
                                alt_names = self._parse_comma_separated_list(dup_alt_names)
                            else:
                                # Handle list format
                                alt_names = dup_alt_names if isinstance(dup_alt_names, list) else []

                            if alt_names:
                                # Filter out empty strings and deduplicate (case-insensitive)
                                existing_lower = {name.lower() for name in merged_data["alternative_names"] if name}
                                for name in alt_names:
                                    if name and name.strip() and name.lower() not in existing_lower:
                                        merged_data["alternative_names"].append(name.strip())
                                        existing_lower.add(name.lower())

                        # Merge Twitch VOD URLs with NULL-safe handling
                        dup_vod_urls = duplicate_game.get('twitch_vod_urls')
                        if dup_vod_urls and dup_vod_urls != "" and str(dup_vod_urls).lower() != "null":
                            if isinstance(dup_vod_urls, str):
                                # Handle TEXT format
                                vod_urls = self._parse_comma_separated_list(dup_vod_urls)
                            else:
                                # Handle list format
                                vod_urls = dup_vod_urls if isinstance(dup_vod_urls, list) else []

                            if vod_urls:
                                # Deduplicate URLs
                                existing_urls = set(merged_data["twitch_vod_urls"])
                                for url in vod_urls:
                                    if url and url.strip() and url not in existing_urls:
                                        merged_data["twitch_vod_urls"].append(url.strip())
                                        existing_urls.add(url)

                        # Use non-empty values from duplicates
                        for field in [
                            "series_name",
                            "genre",
                            "platform",
                                "youtube_playlist_url"]:
                            if not merged_data.get(
                                    field) and duplicate_game.get(field):
                                merged_data[field] = duplicate_game[field]

                        # Use earliest first_played_date
                        if duplicate_game.get("first_played_date"):
                            if (
                                not merged_data["first_played_date"] or
                                duplicate_game["first_played_date"] < merged_data["first_played_date"]
                            ):
                                merged_data["first_played_date"] = duplicate_game["first_played_date"]

                        # Use latest release_year if master doesn't have one
                        if not merged_data.get(
                                "release_year") and duplicate_game.get("release_year"):
                            merged_data["release_year"] = duplicate_game["release_year"]

                        # Sum episodes and playtime
                        merged_data["total_episodes"] += duplicate_game.get(
                            "total_episodes", 0)
                        merged_data["total_playtime_minutes"] += duplicate_game.get(
                            "total_playtime_minutes", 0)

                        # Merge notes
                        if duplicate_game.get(
                                "notes") and duplicate_game["notes"].strip():
                            if merged_data["notes"]:
                                if duplicate_game["notes"] not in merged_data["notes"]:
                                    merged_data["notes"] += f" | {duplicate_game['notes']}"
                            else:
                                merged_data['notes'] = duplicate_game['notes']

                        # Use most advanced completion status
                        status_priority = {
                            "unknown": 0, "ongoing": 1, "dropped": 2, "completed": 3}
                        current_priority = status_priority.get(
                            merged_data["completion_status"], 0)
                        duplicate_priority = status_priority.get(
                            duplicate_game.get("completion_status", "unknown"), 0)
                        if duplicate_priority > current_priority:
                            merged_data["completion_status"] = duplicate_game["completion_status"]

                    # NEW: Convert lists to JSON format for robust database storage
                    alt_names_str = json.dumps(merged_data["alternative_names"]
                                               ) if merged_data["alternative_names"] else '[]'
                    vod_urls_str = json.dumps(
                        merged_data["twitch_vod_urls"]) if merged_data["twitch_vod_urls"] else '[]'

                    # Update the master record with merged data
                    cur.execute("""
                        UPDATE played_games SET
                            alternative_names = %s,
                            series_name = %s,
                            genre = %s,
                            release_year = %s,
                            first_played_date = %s,
                            completion_status = %s,
                            total_episodes = %s,
                            total_playtime_minutes = %s,
                            youtube_playlist_url = %s,
                            twitch_vod_urls = %s,
                            notes = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (
                        alt_names_str,
                        merged_data['series_name'],
                        merged_data['genre'],
                        merged_data['release_year'],
                        merged_data['first_played_date'],
                        merged_data['completion_status'],
                        merged_data['total_episodes'],
                        merged_data['total_playtime_minutes'],
                        merged_data['youtube_playlist_url'],
                        vod_urls_str,
                        merged_data['notes'],
                        master_game['id']
                    ))

                    # Delete the duplicate records
                    duplicate_ids = [game['id'] for game in games_to_merge]
                    if duplicate_ids:
                        cur.execute("""
                            DELETE FROM played_games
                            WHERE id = ANY(%s)
                        """, (duplicate_ids,))

                    merged_count += len(games_to_merge)
                    logger.info(
                        f"Merged {len(games_to_merge)} duplicates of '{canonical_name}' into master record (ID: {master_game['id']})")

                conn.commit()
                logger.info(
                    f"Deduplication complete: merged {merged_count} duplicate records")
                return merged_count

        except Exception as e:
            logger.error(f"Error during deduplication: {e}")
            conn.rollback()
            return 0

    def get_last_channel_check(self, channel_type: str) -> Optional[str]:
        """Get the last time we checked a channel for new games (YouTube/Twitch)"""
        return self.get_config_value(f"last_{channel_type}_check")

    def set_last_channel_check(self, channel_type: str, timestamp: str):
        """Set the last time we checked a channel for new games"""
        self.set_config_value(f"last_{channel_type}_check", timestamp)

    def add_discovered_game(
            self,
            canonical_name: str,
            discovered_from: str,
            video_title: Optional[str] = None,
            video_url: Optional[str] = None,
            estimated_episodes: int = 1) -> bool:
        """Add a game discovered from channel monitoring"""
        # Check if game already exists
        if self.played_game_exists(canonical_name):
            logger.info(f"Game {canonical_name} already exists, skipping")
            return False

        # Create notes about discovery
        notes = f"Auto-discovered from {discovered_from}"
        if video_title:
            notes += f" (first video: '{video_title}')"
        if video_url:
            notes += f" - {video_url}"

        return self.add_played_game(
            canonical_name=canonical_name,
            completion_status="ongoing" if estimated_episodes > 1 else "unknown",
            total_episodes=estimated_episodes,
            notes=notes)

    def update_game_episodes(
            self,
            canonical_name: str,
            new_episode_count: int) -> bool:
        """Update the episode count for a game"""
        game = self.get_played_game(canonical_name)
        if not game:
            return False

        return self.update_played_game(
            game['id'],
            total_episodes=new_episode_count,
            completion_status="ongoing" if new_episode_count > 1 else "completed")

    def get_latest_game_update_timestamp(self) -> Optional[datetime]:
        """Gets the most recent 'updated_at' timestamp from the played_games table or last sync time."""
        # First check if we have a stored last sync timestamp
        last_sync_str = self.get_config_value('last_content_sync_timestamp')
        if last_sync_str:
            try:
                return datetime.fromisoformat(last_sync_str)
            except (ValueError, TypeError):
                logger.warning(f"Invalid last_content_sync_timestamp format: {last_sync_str}")

        # Fallback to checking played_games updated_at
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(updated_at) as latest_update FROM played_games")
                result = cur.fetchone()

                # If there's no result from the database, fall back to syncing the last 7 days.
                if not result:
                    return datetime.now(ZoneInfo("Europe/London")) - timedelta(days=7)

                typed_result = cast(RealDictRow, result)

                # Now, safely access the key from the typed variable.
                if typed_result['latest_update']:
                    return typed_result['latest_update']
                else:
                    # Fallback if the latest_update value is NULL (e.g., table is empty).
                    return datetime.now(ZoneInfo("Europe/London")) - timedelta(days=7)
        except Exception as e:
            logger.error(f"Error getting latest game update timestamp: {e}")
            return None

    def update_last_sync_timestamp(self, timestamp: datetime) -> bool:
        """Update the last content sync timestamp in config"""
        try:
            timestamp_str = timestamp.isoformat()
            self.set_config_value('last_content_sync_timestamp', timestamp_str)
            logger.info(f"Updated last sync timestamp to {timestamp_str}")
            return True
        except Exception as e:
            logger.error(f"Error updating last sync timestamp: {e}")
            return False

    def get_games_by_genre(self, genre: str) -> List[Dict[str, Any]]:
        """Get all games in a specific genre"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM played_games
                    WHERE LOWER(genre) = %s
                    ORDER BY release_year ASC, canonical_name ASC
                """, (genre.lower(),))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by genre {genre}: {e}")
            return []

    def get_games_by_genre_flexible(
            self, genre_query: str) -> List[Dict[str, Any]]:
        """Get all games matching genre with flexible matching (e.g., 'horror' matches 'survival-horror')"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                # Use LIKE with wildcards for flexible matching
                genre_pattern = f"%{genre_query.lower()}%"
                cur.execute("""
                    SELECT * FROM played_games
                    WHERE LOWER(genre) LIKE %s
                    ORDER BY release_year ASC, canonical_name ASC
                """, (genre_pattern,))
                results = cur.fetchall()

                # Convert to list of dicts and apply text-to-array conversion
                games = []
                for row in results:
                    game_dict = dict(row)
                    game_dict = self._convert_text_to_arrays(game_dict)
                    games.append(game_dict)

                return games
        except Exception as e:
            logger.error(
                f"Error getting games by flexible genre {genre_query}: {e}")
            return []

    def get_games_by_franchise(
            self, franchise_name: str) -> List[Dict[str, Any]]:
        """Get all games in a specific franchise (using series_name)"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM played_games
                    WHERE LOWER(series_name) = %s
                    ORDER BY release_year ASC, canonical_name ASC
                """, (franchise_name.lower(),))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(
                f"Error getting games by franchise {franchise_name}: {e}")
            return []

    def get_random_played_games(self, limit: int = 8) -> List[Dict[str, Any]]:
        """Get a random sample of played games for AI responses"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM played_games
                    ORDER BY RANDOM()
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting random played games: {e}")
            return []

    def get_played_games_stats(self) -> Dict[str, Any]:
        """Get statistics about played games for AI responses"""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                # Total games
                cur.execute("SELECT COUNT(*) as count FROM played_games")
                result = cur.fetchone()
                total_games = int(
                    result['count']) if result else 0  # type: ignore

                # Completed vs ongoing
                cur.execute(
                    "SELECT completion_status, COUNT(*) as count FROM played_games GROUP BY completion_status")
                status_results = cur.fetchall()
                status_counts = {str(cast(RealDictRow, row)['completion_status']): int(cast(
                    RealDictRow, row)['count']) for row in status_results} if status_results else {}

                # Total episodes and playtime
                cur.execute(
                    "SELECT COALESCE(SUM(total_episodes), 0) as episodes, COALESCE(SUM(total_playtime_minutes), 0) as playtime FROM played_games")
                totals = cur.fetchone()
                total_episodes = int(
                    totals['episodes']) if totals else 0  # type: ignore
                total_playtime = int(
                    totals['playtime']) if totals else 0  # type: ignore

                # Genre distribution
                cur.execute(
                    "SELECT genre, COUNT(*) as count FROM played_games WHERE genre IS NOT NULL GROUP BY genre ORDER BY COUNT(*) DESC LIMIT 5")
                genre_results = cur.fetchall()
                top_genres = {str(cast(RealDictRow, row)['genre']): int(cast(RealDictRow, row)[
                    'count']) for row in genre_results} if genre_results else {}

                # Series distribution (replacing franchise)
                cur.execute(
                    "SELECT series_name, COUNT(*) as count FROM played_games WHERE series_name IS NOT NULL GROUP BY series_name ORDER BY COUNT(*) DESC LIMIT 5")
                series_results = cur.fetchall()
                top_series = {str(cast(RealDictRow, row)['series_name']): int(cast(
                    RealDictRow, row)['count']) for row in series_results} if series_results else {}

                return {
                    "total_games": total_games,
                    "status_counts": status_counts,
                    "total_episodes": total_episodes,
                    "total_playtime_minutes": total_playtime,
                    "total_playtime_hours": (
                        round(
                            total_playtime / 60,
                            1) if total_playtime > 0 else 0),
                    "top_genres": top_genres,
                    "top_series": top_series,
                }
        except Exception as e:
            logger.error(f"Error getting played games stats: {e}")
            return {}

    def get_played_game_by_id(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Get a played game by its database ID"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM played_games WHERE id = %s", (game_id,))
                result = cur.fetchone()
                if result:
                    return dict(result)
                return None
        except Exception as e:
            logger.error(f"Error getting played game by ID {game_id}: {e}")
            return None

    def get_game_by_id_or_name(
            self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get a game by either ID (if numeric) or name"""
        # Try to parse as ID first
        try:
            game_id = int(identifier)
            return self.get_played_game_by_id(game_id)
        except ValueError:
            # Not a number, search by name
            return self.get_played_game(identifier)

    def debug_update_issues(self, canonical_name: str) -> Dict[str, Any]:
        """Debug function to help identify update issues"""
        conn = self.get_connection()
        if not conn:
            return {"error": "No database connection"}

        try:
            with conn.cursor() as cur:
                debug_info = {
                    "search_name": canonical_name,
                    "search_name_lower": canonical_name.lower().strip(),
                    "found_games": [],
                    "exact_matches": [],
                    "fuzzy_matches": []
                }

                # Get all games for comparison
                cur.execute(
                    "SELECT id, canonical_name, alternative_names FROM played_games")
                all_games = cur.fetchall()

                for game in all_games:
                    game_dict = dict(game)
                    game_canonical = game_dict.get('canonical_name', '')
                    game_alt_names = game_dict.get('alternative_names', [])

                    debug_info["found_games"].append({
                        "id": game_dict.get('id'),
                        "canonical_name": game_canonical,
                        "alternative_names": game_alt_names
                    })

                    # Check exact matches
                    if game_canonical.lower().strip() == canonical_name.lower().strip():
                        debug_info["exact_matches"].append(game_dict.get('id'))

                    # Check alternative name matches
                    if game_alt_names:
                        for alt_name in game_alt_names:
                            if alt_name and alt_name.lower().strip() == canonical_name.lower().strip():
                                debug_info["exact_matches"].append(
                                    game_dict.get("id"))

                # Test fuzzy matching
                import difflib

                canonical_names = [
                    str(dict(game)["canonical_name"]).lower().strip()
                    for game in all_games
                    if dict(game).get("canonical_name")
                ]
                matches = difflib.get_close_matches(
                    canonical_name.lower().strip(), canonical_names, n=3, cutoff=0.75)
                debug_info["fuzzy_matches"] = matches

                # Test the actual get_played_game function
                found_game = self.get_played_game(canonical_name)
                debug_info["get_played_game_result"] = found_game is not None
                if found_game:
                    debug_info["found_game_id"] = found_game.get('id')
                    debug_info["found_game_name"] = found_game.get(
                        'canonical_name')

                return debug_info
        except Exception as e:
            logger.error(f"Error in debug_update_issues: {e}")
            return {"error": str(e)}

    def get_series_by_total_playtime(self) -> List[Dict[str, Any]]:
        """Get game series ranked by total playtime"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        series_name,
                        COUNT(*) as game_count,
                        SUM(total_playtime_minutes) as total_playtime_minutes,
                        SUM(total_episodes) as total_episodes,
                        ROUND(AVG(total_playtime_minutes), 1) as avg_playtime_per_game
                    FROM played_games
                    WHERE series_name IS NOT NULL
                    AND series_name != ''
                    AND total_playtime_minutes > 0
                    GROUP BY series_name
                    ORDER BY SUM(total_playtime_minutes) DESC
                    LIMIT 10
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting series by playtime: {e}")
            return []

    def get_games_by_average_episode_length(self) -> List[Dict[str, Any]]:
        """Get games ranked by average minutes per episode"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        canonical_name,
                        series_name,
                        total_episodes,
                        total_playtime_minutes,
                        ROUND(total_playtime_minutes::float / NULLIF(total_episodes, 0), 1) as avg_minutes_per_episode,
                        completion_status
                    FROM played_games
                    WHERE total_episodes > 0
                    AND total_playtime_minutes > 0
                    ORDER BY (total_playtime_minutes::float / NULLIF(total_episodes, 0)) DESC
                    LIMIT 15
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by average episode length: {e}")
            return []

    def get_longest_completion_games(self) -> List[Dict[str, Any]]:
        """Get games that took longest to complete (by episodes or time)"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        canonical_name,
                        series_name,
                        total_episodes,
                        total_playtime_minutes,
                        completion_status,
                        genre
                    FROM played_games
                    WHERE completion_status = 'completed'
                    AND (total_episodes > 0 OR total_playtime_minutes > 0)
                    ORDER BY
                        total_playtime_minutes DESC,
                        total_episodes DESC
                    LIMIT 10
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting longest completion games: {e}")
            return []

    def get_games_by_playtime(self, order: str = 'DESC', limit: int = 15) -> List[Dict[str, Any]]:
        """Get ALL games ranked by playtime (regardless of completion status)"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            # Validate order direction to prevent SQL injection
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        canonical_name,
                        series_name,
                        total_episodes,
                        total_playtime_minutes,
                        completion_status,
                        genre
                    FROM played_games
                    WHERE total_playtime_minutes > 0
                    ORDER BY total_playtime_minutes {order_clause}
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by playtime: {e}")
            return []

    # --- Platform-Specific Helper Methods ---

    def detect_game_platform(self, game_dict: Dict[str, Any]) -> str:
        """
        Detect which platform a game was played on based on available data.

        Returns: 'youtube', 'twitch', 'both', or 'unknown'
        """
        has_youtube = bool(game_dict.get('youtube_playlist_url'))
        has_twitch = bool(game_dict.get('twitch_vod_urls')) and game_dict.get('twitch_vod_urls') not in ['', '{}']

        if has_youtube and has_twitch:
            return 'both'
        elif has_youtube:
            return 'youtube'
        elif has_twitch:
            return 'twitch'
        else:
            # Fallback: Check notes for platform mentions
            notes = game_dict.get('notes', '').lower()
            if 'youtube' in notes:
                return 'youtube'
            elif 'twitch' in notes:
                return 'twitch'
            return 'unknown'

    def get_games_by_platform(self, platform: str, order_by: str = 'canonical_name') -> List[Dict[str, Any]]:
        """
        Get games filtered by platform (youtube/twitch/both).

        Args:
            platform: 'youtube', 'twitch', or 'both'
            order_by: Column to sort by (validated against whitelist)

        Returns:
            List of game dictionaries
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            # Validate order_by column to prevent SQL injection
            try:
                validated_order_by = self._validate_column_name(order_by, self.PLAYED_GAMES_COLUMNS)
            except ValueError as e:
                logger.error(f"Invalid order_by parameter in get_games_by_platform: {e}")
                return []

            with conn.cursor() as cur:
                if platform == 'youtube':
                    condition = "youtube_playlist_url IS NOT NULL AND youtube_playlist_url != ''"
                elif platform == 'twitch':
                    condition = "twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}'"
                elif platform == 'both':
                    condition = """
                        youtube_playlist_url IS NOT NULL AND youtube_playlist_url != ''
                        AND twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}'
                    """
                else:
                    logger.error(f"Invalid platform specification: {platform}")
                    return []

                query = f"""
                    SELECT * FROM played_games
                    WHERE {condition}
                    ORDER BY {validated_order_by} ASC
                """

                cur.execute(query)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by platform {platform}: {e}")
            return []

    def get_youtube_games_by_episodes(self, order: str = 'DESC', limit: int = 15) -> List[Dict[str, Any]]:
        """
        Get YouTube playthroughs ranked by episode count.

        Only includes games with YouTube playlist URLs to ensure platform accuracy.
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            # Validate order direction to prevent SQL injection
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        canonical_name,
                        series_name,
                        total_episodes,
                        total_playtime_minutes,
                        completion_status,
                        genre,
                        youtube_playlist_url,
                        youtube_views
                    FROM played_games
                    WHERE youtube_playlist_url IS NOT NULL
                    AND youtube_playlist_url != ''
                    AND total_episodes > 0
                    ORDER BY total_episodes {order_clause}
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting YouTube games by episodes: {e}")
            return []

    def get_twitch_games_by_vods(self, order: str = 'DESC', limit: int = 15) -> List[Dict[str, Any]]:
        """
        Get Twitch streams ranked by VOD count.

        Only includes games with Twitch VOD URLs to ensure platform accuracy.
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            # Validate order direction to prevent SQL injection
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        canonical_name,
                        series_name,
                        total_episodes,
                        total_playtime_minutes,
                        completion_status,
                        genre,
                        twitch_vod_urls
                    FROM played_games
                    WHERE twitch_vod_urls IS NOT NULL
                    AND twitch_vod_urls != ''
                    AND twitch_vod_urls != '{{}}'
                    AND total_episodes > 0
                    ORDER BY total_episodes {order_clause}
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting Twitch games by VODs: {e}")
            return []

    def get_youtube_games_by_playtime(self, order: str = 'DESC', limit: int = 15) -> List[Dict[str, Any]]:
        """
        Get YouTube playthroughs ranked by total playtime.

        Only includes games with YouTube playlist URLs.
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            # Validate order direction to prevent SQL injection
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        canonical_name,
                        series_name,
                        total_episodes,
                        total_playtime_minutes,
                        completion_status,
                        genre,
                        youtube_playlist_url,
                        youtube_views
                    FROM played_games
                    WHERE youtube_playlist_url IS NOT NULL
                    AND youtube_playlist_url != ''
                    AND total_playtime_minutes > 0
                    ORDER BY total_playtime_minutes {order_clause}
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting YouTube games by playtime: {e}")
            return []

    def get_twitch_games_by_playtime(self, order: str = 'DESC', limit: int = 15) -> List[Dict[str, Any]]:
        """
        Get Twitch streams ranked by total playtime.

        Only includes games with Twitch VOD URLs.
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            # Validate order direction to prevent SQL injection
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        canonical_name,
                        series_name,
                        total_episodes,
                        total_playtime_minutes,
                        completion_status,
                        genre,
                        twitch_vod_urls
                    FROM played_games
                    WHERE twitch_vod_urls IS NOT NULL
                    AND twitch_vod_urls != ''
                    AND twitch_vod_urls != '{{}}'
                    AND total_playtime_minutes > 0
                    ORDER BY total_playtime_minutes {order_clause}
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting Twitch games by playtime: {e}")
            return []

    def get_platform_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about games by platform.

        Returns counts and totals for YouTube vs Twitch vs Both platforms.
        """
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                # Count games by platform
                cur.execute("""
                    SELECT
                        COUNT(CASE WHEN youtube_playlist_url IS NOT NULL AND youtube_playlist_url != '' THEN 1 END) as youtube_count,
                        COUNT(CASE WHEN twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}' THEN 1 END) as twitch_count,
                        COUNT(CASE WHEN
                            (youtube_playlist_url IS NOT NULL AND youtube_playlist_url != '')
                            AND (twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}')
                            THEN 1 END) as both_platforms_count,
                        SUM(CASE WHEN youtube_playlist_url IS NOT NULL AND youtube_playlist_url != '' THEN total_episodes ELSE 0 END) as youtube_total_episodes,
                        SUM(CASE WHEN twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}' THEN total_episodes ELSE 0 END) as twitch_total_vods,
                        SUM(CASE WHEN youtube_playlist_url IS NOT NULL AND youtube_playlist_url != '' THEN total_playtime_minutes ELSE 0 END) as youtube_total_playtime,
                        SUM(CASE WHEN twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}' THEN total_playtime_minutes ELSE 0 END) as twitch_total_playtime
                    FROM played_games
                """)

                result = cur.fetchone()
                if result:
                    result_dict = dict(result)
                    return {
                        'youtube_games': int(result_dict.get('youtube_count', 0)),
                        'twitch_games': int(result_dict.get('twitch_count', 0)),
                        'both_platforms': int(result_dict.get('both_platforms_count', 0)),
                        'youtube_total_episodes': int(result_dict.get('youtube_total_episodes', 0)),
                        'twitch_total_vods': int(result_dict.get('twitch_total_vods', 0)),
                        'youtube_total_playtime_minutes': int(result_dict.get('youtube_total_playtime', 0)),
                        'twitch_total_playtime_minutes': int(result_dict.get('twitch_total_playtime', 0)),
                        'youtube_total_playtime_hours': round(int(result_dict.get('youtube_total_playtime', 0)) / 60, 1),
                        'twitch_total_playtime_hours': round(int(result_dict.get('twitch_total_playtime', 0)) / 60, 1)
                    }
                return {}
        except Exception as e:
            logger.error(f"Error getting platform statistics: {e}")
            return {}

    def get_games_by_episode_count(
            self, order: str = 'DESC', limit: int = 15) -> List[Dict[str, Any]]:
        """Get games ranked by episode count"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            # Validate order direction to prevent SQL injection
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                        SELECT
                            canonical_name,
                            series_name,
                            total_episodes,
                            total_playtime_minutes,
                            completion_status,
                            genre
                        FROM played_games
                        WHERE total_episodes > 0
                        ORDER BY total_episodes {order_clause}
                        LIMIT %s
                    """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by episode count: {e}")
            return []

    def get_games_by_played_date(self, order: str = 'DESC', limit: int = 1) -> List[Dict[str, Any]]:
        """Get games ranked by the date they were first played."""
        conn = self.get_connection()
        if not conn:
            return []
        try:
            # Validate order direction to prevent SQL injection
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                        SELECT canonical_name, first_played_date FROM played_games
                        WHERE first_played_date IS NOT NULL
                        ORDER BY first_played_date {order_clause}
                        LIMIT %s
                    """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by played date: {e}")
            return []

    def get_games_by_release_year(self, order: str = 'DESC', limit: int = 1) -> List[Dict[str, Any]]:
        """Get games ranked by their release year."""
        conn = self.get_connection()
        if not conn:
            return []
        try:
            # Validate order direction to prevent SQL injection
            order_clause = self._validate_order_direction(order)

            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT canonical_name, release_year FROM played_games
                    WHERE release_year IS NOT NULL AND release_year > 0
                    ORDER BY release_year {order_clause}
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by release year: {e}")
            return []

    def get_genre_statistics(self) -> List[Dict[str, Any]]:
        """Get comprehensive genre statistics"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        genre,
                        COUNT(*) as game_count,
                        SUM(total_episodes) as total_episodes,
                        SUM(total_playtime_minutes) as total_playtime_minutes,
                        ROUND(AVG(total_playtime_minutes), 1) as avg_playtime_per_game,
                        COUNT(CASE WHEN completion_status = 'completed' THEN 1 END) as completed_count,
                        ROUND(
                            COUNT(CASE WHEN completion_status = 'completed' THEN 1 END)::float / COUNT(*) * 100,
                            1
                        ) as completion_rate
                    FROM played_games
                    WHERE genre IS NOT NULL
                    AND genre != ''
                    GROUP BY genre
                    ORDER BY SUM(total_playtime_minutes) DESC
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting genre statistics: {e}")
            return []

    def get_temporal_gaming_data(
            self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get gaming data by year or all years"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                if year:
                    cur.execute("""
                        SELECT
                            canonical_name,
                            series_name,
                            genre,
                            release_year,
                            first_played_date,
                            total_episodes,
                            completion_status
                        FROM played_games
                        WHERE release_year = %s
                        ORDER BY first_played_date ASC, canonical_name ASC
                    """, (year,))
                else:
                    cur.execute("""
                        SELECT
                            release_year,
                            COUNT(*) as games_played,
                            SUM(total_episodes) as total_episodes,
                            SUM(total_playtime_minutes) as total_playtime_minutes
                        FROM played_games
                        WHERE release_year IS NOT NULL
                        GROUP BY release_year
                        ORDER BY release_year DESC
                    """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting temporal gaming data: {e}")
            return []

    def compare_games(self, game1_name: str,
                      game2_name: str) -> Dict[str, Any]:
        """Compare two games directly"""
        game1 = self.get_played_game(game1_name)
        game2 = self.get_played_game(game2_name)

        if not game1 or not game2:
            return {
                'error': 'One or both games not found',
                'game1_found': game1 is not None,
                'game2_found': game2 is not None
            }

        return {
            'game1': {
                'name': game1['canonical_name'],
                'series': game1.get('series_name'),
                'episodes': game1.get(
                    'total_episodes',
                    0),
                'playtime_minutes': game1.get(
                    'total_playtime_minutes',
                    0),
                'playtime_hours': round(
                    game1.get(
                        'total_playtime_minutes',
                        0) /
                    60,
                    1),
                'status': game1.get('completion_status'),
                'genre': game1.get('genre')},
            "game2": {
                "name": game2["canonical_name"],
                "series": game2.get("series_name"),
                "episodes": game2.get(
                    "total_episodes",
                    0),
                "playtime_minutes": game2.get(
                    "total_playtime_minutes",
                    0),
                "playtime_hours": round(
                    game2.get(
                        "total_playtime_minutes",
                        0) /
                    60,
                    1),
                "status": game2.get("completion_status"),
                "genre": game2.get("genre"),
            },
            "comparison": {
                "episode_difference": game1.get(
                    "total_episodes",
                    0) -
                game2.get(
                    "total_episodes",
                    0),
                "playtime_difference_minutes": game1.get(
                    "total_playtime_minutes",
                    0) -
                game2.get(
                    "total_playtime_minutes",
                    0),
                "longer_game": (
                    game1["canonical_name"] if game1.get(
                        "total_playtime_minutes",
                        0) > game2.get(
                        "total_playtime_minutes",
                        0) else game2["canonical_name"]),
                "more_episodes": (
                    game1["canonical_name"] if game1.get(
                        "total_episodes",
                        0) > game2.get(
                        "total_episodes",
                        0) else game2["canonical_name"])}}

    def get_ranking_context(self, game_name: str,
                            metric: str = "playtime") -> Dict[str, Any]:
        """Get where a specific game ranks in various metrics"""
        game = self.get_played_game(game_name)
        if not game:
            return {'error': 'Game not found'}

        conn = self.get_connection()
        if not conn:
            return {'error': 'Database connection failed'}

        try:
            with conn.cursor() as cur:
                context = {
                    'game_name': game['canonical_name'],
                    'rankings': {}
                }

                # Playtime ranking
                if metric in ['playtime', 'all']:
                    cur.execute("""
                        SELECT COUNT(*) + 1 as rank
                        FROM played_games
                        WHERE total_playtime_minutes > %s
                    """, (game.get('total_playtime_minutes', 0),))
                    result = cur.fetchone()
                    playtime_rank = int(
                        result["rank"]) if result else 0  # type: ignore

                    cur.execute(
                        "SELECT COUNT(*) as total FROM played_games WHERE total_playtime_minutes > 0")
                    total_result = cur.fetchone()
                    total_with_playtime = int(
                        total_result["total"]) if total_result else 0  # type: ignore

                    context["rankings"]["playtime"] = {
                        "rank": playtime_rank,
                        "total": total_with_playtime,
                        "percentile": (
                            round((1 - (playtime_rank - 1) / max(total_with_playtime, 1)) * 100, 1)
                            if total_with_playtime > 0
                            else 0
                        ),
                    }

                # Episode count ranking
                if metric in ['episodes', 'all']:
                    cur.execute("""
                        SELECT COUNT(*) + 1 as rank
                        FROM played_games
                        WHERE total_episodes > %s
                    """, (game.get('total_episodes', 0),))
                    result = cur.fetchone()
                    episode_rank = int(
                        result["rank"]) if result else 0  # type: ignore

                    cur.execute(
                        "SELECT COUNT(*) as total FROM played_games WHERE total_episodes > 0")
                    total_result = cur.fetchone()
                    total_with_episodes = int(
                        total_result["total"]) if total_result else 0  # type: ignore

                    context["rankings"]["episodes"] = {
                        "rank": episode_rank,
                        "total": total_with_episodes,
                        "percentile": (
                            round((1 - (episode_rank - 1) / max(total_with_episodes, 1)) * 100, 1)
                            if total_with_episodes > 0
                            else 0
                        ),
                    }

                return context
        except Exception as e:
            logger.error(f"Error getting ranking context: {e}")
            return {'error': str(e)}

    def add_reminder(
        self,
        user_id: int,
        reminder_text: str,
        scheduled_time: Any,  # Can be datetime or str
        delivery_channel_id: Optional[int] = None,
        delivery_type: str = "dm",
        auto_action_enabled: bool = False,
        auto_action_type: Optional[str] = None,
        auto_action_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Add a reminder to the database"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reminders (
                        user_id, reminder_text, scheduled_time, delivery_channel_id,
                        delivery_type, auto_action_enabled, auto_action_type, auto_action_data,
                        status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', CURRENT_TIMESTAMP)
                    RETURNING id
                """,
                    (
                        user_id,
                        reminder_text,
                        scheduled_time,
                        delivery_channel_id,
                        delivery_type,
                        auto_action_enabled,
                        auto_action_type,
                        auto_action_data,
                    ),
                )
                result = cur.fetchone()
                conn.commit()

                if result:
                    reminder_id = int(result["id"])  # type: ignore
                    logger.info(
                        f"Added reminder ID {reminder_id} for user {user_id}")
                    return reminder_id
                return None
        except Exception as e:
            logger.error(f"Error adding reminder: {e}")
            conn.rollback()
            return None

    def get_user_reminders(self, user_id: int,
                           status: str = "pending") -> List[Dict[str, Any]]:
        """Get all reminders for a user"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM reminders
                    WHERE user_id = %s AND status = %s
                    ORDER BY scheduled_time ASC
                """,
                    (user_id, status),
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting user reminders: {e}")
            return []

    def get_due_reminders(self, current_time) -> List[Dict[str, Any]]:
        """Get all reminders that are due for delivery"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM reminders
                    WHERE status = 'pending'
                    AND scheduled_time <= %s
                    ORDER BY scheduled_time ASC
                """,
                    (current_time,),
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting due reminders: {e}")
            return []

    def update_reminder_status(
        self,
        reminder_id: int,
        status: str,
        delivered_at: Optional[Any] = None,  # Can be datetime or str
        auto_executed_at: Optional[Any] = None,  # Can be datetime or str
    ) -> bool:
        """Update reminder status"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                # Build query dynamically to avoid repetition
                set_clauses = ["status = %s"]
                params: List[Any] = [status]

                if status == "delivered" and delivered_at:
                    set_clauses.append("delivered_at = %s")
                    params.append(delivered_at)
                elif status == "auto_completed" and auto_executed_at:
                    set_clauses.append("auto_executed_at = %s")
                    params.append(auto_executed_at)

                params.append(reminder_id)

                query = f"UPDATE reminders SET {', '.join(set_clauses)} WHERE id = %s"
                cur.execute(query, tuple(params))

                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating reminder status: {e}")
            conn.rollback()
            return False

    def cancel_user_reminder(self, reminder_id: int,
                             user_id: int) -> Optional[Dict[str, Any]]:
        """Cancel a reminder (only if it belongs to the user)"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Atomically update the reminder and return it if found
                cur.execute(
                    """
                    UPDATE reminders
                    SET status = 'cancelled'
                    WHERE id = %s AND user_id = %s AND status = 'pending'
                    RETURNING *
                    """,
                    (reminder_id, user_id),
                )
                reminder = cur.fetchone()

                if reminder:
                    conn.commit()
                    logger.info(
                        f"Cancelled reminder ID {reminder_id} for user {user_id}")
                    return dict(reminder)

                return None
        except Exception as e:
            logger.error(f"Error cancelling reminder: {e}")
            conn.rollback()
            return None

    def get_reminders_awaiting_auto_action(
            self, current_time) -> List[Dict[str, Any]]:
        """Get reminders that are past delivery time and waiting for auto-action"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                # Calculate 5 minutes ago from current time
                import datetime

                five_minutes_ago = current_time - datetime.timedelta(minutes=5)
                cur.execute(
                    """
                    SELECT * FROM reminders
                    WHERE status = 'delivered'
                    AND auto_action_enabled = TRUE
                    AND auto_executed_at IS NULL
                    AND delivered_at <= %s
                    ORDER BY delivered_at ASC
                """,
                    (five_minutes_ago,),
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting reminders awaiting auto-action: {e}")
            return []

    def get_all_pending_reminders(self) -> List[Dict[str, Any]]:
        """Get all pending reminders for moderator management"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM reminders
                    WHERE status = 'pending'
                    ORDER BY scheduled_time ASC
                """
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting all pending reminders: {e}")
            return []

    def get_pending_reminders_for_user(
            self, user_id: int) -> List[Dict[str, Any]]:
        """Get pending reminders for a specific user"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM reminders
                    WHERE user_id = %s AND status = 'pending'
                    ORDER BY scheduled_time ASC
                """,
                    (user_id,),
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(
                f"Error getting pending reminders for user {user_id}: {e}")
            return []

    def get_reminder_by_id(self, reminder_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific reminder by ID"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM reminders
                    WHERE id = %s
                """,
                    (reminder_id,),
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting reminder by ID {reminder_id}: {e}")
            return None

    async def cancel_reminder(self, reminder_id: int) -> bool:
        """Cancel a reminder by ID (admin version - no user restriction)"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE reminders
                    SET status = 'cancelled'
                    WHERE id = %s AND status = 'pending'
                """,
                    (reminder_id,),
                )
                conn.commit()
                success = cur.rowcount > 0
                if success:
                    logger.info(f"Admin cancelled reminder ID {reminder_id}")
                return success
        except Exception as e:
            logger.error(f"Error admin cancelling reminder {reminder_id}: {e}")
            conn.rollback()
            return False

    def close(self):
        """Close database connection"""
        if self.connection and not self.connection.closed:
            self.connection.close()

    def get_all_unique_series_names(self) -> List[str]:
        """Gets a list of all unique, non-empty series names from the played_games table."""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT series_name FROM played_games
                    WHERE series_name IS NOT NULL AND series_name != ''
                """)
                results = cur.fetchall()
                # Return a simple list of lowercase names for easy matching
                return [cast(RealDictRow, row)['series_name'].lower() for row in results]
        except Exception as e:
            logger.error(f"Error getting unique series names: {e}")
            return []

    # --- Trivia System Methods ---


# Export
__all__ = ['GamesDatabase']
