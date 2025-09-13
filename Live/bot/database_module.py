import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast

import psycopg2
from psycopg2.extras import RealDictCursor, RealDictRow

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            logger.warning(
                "DATABASE_URL not found. Database features will be disabled.")
            self.connection = None
        else:
            self.connection = None
            self.init_database()

    def get_connection(self):
        """Get database connection with retry logic"""
        if not self.database_url:
            return None

        try:
            # Always create a fresh connection for each operation to avoid stale connections
            # This is more reliable than trying to reuse connections
            self.connection = psycopg2.connect(
                self.database_url, cursor_factory=RealDictCursor)
            return self.connection
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return None

    def init_database(self):
        """Initialize database tables"""
        if not self.database_url:
            logger.warning(
                "Skipping database initialization - no DATABASE_URL")
            return

        conn = self.get_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cur:
                # Create strikes table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS strikes (
                        user_id BIGINT PRIMARY KEY,
                        strike_count INTEGER DEFAULT 0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create game_recommendations table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS game_recommendations (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        reason TEXT,
                        added_by VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create bot_config table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bot_config (
                        key VARCHAR(50) PRIMARY KEY,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                            )

                # Create reminders table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reminders (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        reminder_text TEXT NOT NULL,
                        scheduled_time TIMESTAMP NOT NULL,
                        delivery_channel_id BIGINT NULL,
                        delivery_type VARCHAR(20) NOT NULL,
                        auto_action_enabled BOOLEAN DEFAULT FALSE,
                        auto_action_type VARCHAR(50) NULL,
                        auto_action_data JSONB NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        delivered_at TIMESTAMP NULL,
                        auto_executed_at TIMESTAMP NULL
                    )
                """
                )

                # Create trivia_questions table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trivia_questions (
                        id SERIAL PRIMARY KEY,
                        question_text TEXT NOT NULL,
                        question_type VARCHAR(20) NOT NULL, -- 'single', 'multiple_choice'
                        correct_answer TEXT,
                        multiple_choice_options TEXT[], -- For multiple choice questions
                        is_dynamic BOOLEAN DEFAULT FALSE, -- Requires real-time calculation
                        dynamic_query_type VARCHAR(50), -- 'longest_playtime', 'most_episodes', etc.
                        submitted_by_user_id BIGINT, -- NULL for AI-generated questions
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used_at TIMESTAMP,
                        usage_count INTEGER DEFAULT 0,
                        category VARCHAR(50), -- 'completion', 'playtime', 'genre', 'series', etc.
                        difficulty_level INTEGER DEFAULT 1, -- 1-5 scale
                        is_active BOOLEAN DEFAULT TRUE,
                        status VARCHAR(20) DEFAULT 'available' -- 'available', 'answered', 'retired'
                    )
                """
                )

                # Add status column to existing trivia_questions table if it
                # doesn't exist
                cur.execute(
                    """
                    ALTER TABLE trivia_questions
                    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'available'
                """
                )

                # Update any NULL status values to 'available'
                cur.execute(
                    """
                    UPDATE trivia_questions
                    SET status = 'available'
                    WHERE status IS NULL
                """
                )

                # Create trivia_sessions table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trivia_sessions (
                        id SERIAL PRIMARY KEY,
                        question_id INTEGER REFERENCES trivia_questions(id),
                        session_date DATE NOT NULL,
                        session_type VARCHAR(20) DEFAULT 'weekly', -- 'weekly', 'bonus'
                        question_submitter_id BIGINT, -- For conflict checking
                        calculated_answer TEXT, -- For dynamic questions
                        status VARCHAR(20) DEFAULT 'active', -- 'active', 'completed', 'expired'
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ended_at TIMESTAMP,
                        first_correct_user_id BIGINT,
                        total_participants INTEGER DEFAULT 0,
                        correct_answers_count INTEGER DEFAULT 0
                    )
                """
                )

                # Create trivia_answers table
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trivia_answers (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER REFERENCES trivia_sessions(id),
                        user_id BIGINT NOT NULL,
                        answer_text TEXT NOT NULL,
                        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_correct BOOLEAN,
                        is_first_correct BOOLEAN DEFAULT FALSE,
                        conflict_detected BOOLEAN DEFAULT FALSE, -- Mod answering own question
                        normalized_answer TEXT -- For matching with alternative names
                    )
                """
                )

                # Create played_games table with proper data types for manual
                # editing
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS played_games (
                        id SERIAL PRIMARY KEY,
                        canonical_name VARCHAR(255) NOT NULL,
                        alternative_names TEXT,
                        series_name VARCHAR(255),
                        genre VARCHAR(100),
                        release_year INTEGER,
                        platform VARCHAR(100),
                        first_played_date DATE,
                        completion_status VARCHAR(50) DEFAULT 'unknown',
                        total_episodes INTEGER DEFAULT 0,
                        total_playtime_minutes INTEGER DEFAULT 0,
                        youtube_playlist_url TEXT,
                        twitch_vod_urls TEXT,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Migrate existing array columns to TEXT format for manual
                # editing
                try:
                    cur.execute("""
                        DO $$
                        BEGIN
                            -- Check if alternative_names is still an array type
                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'played_games'
                                AND column_name = 'alternative_names'
                                AND data_type = 'ARRAY'
                            ) THEN
                                -- Convert array to comma-separated text
                                ALTER TABLE played_games
                                ALTER COLUMN alternative_names TYPE TEXT
                                USING array_to_string(alternative_names, ',');
                            END IF;

                            -- Check if twitch_vod_urls is still an array type
                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'played_games'
                                AND column_name = 'twitch_vod_urls'
                                AND data_type = 'ARRAY'
                            ) THEN
                                -- Convert array to comma-separated text
                                ALTER TABLE played_games
                                ALTER COLUMN twitch_vod_urls TYPE TEXT
                                USING array_to_string(twitch_vod_urls, ',');
                            END IF;
                        END $$;
                    """)
                except Exception as migration_error:
                    logger.warning(
                        f"Array migration warning: {migration_error}")
                    # Continue with table creation even if migration fails

                # Add new columns to existing table if they don't exist (remove
                # franchise_name)
                cur.execute("""
                    ALTER TABLE played_games
                    ADD COLUMN IF NOT EXISTS genre VARCHAR(100),
                    ADD COLUMN IF NOT EXISTS total_playtime_minutes INTEGER DEFAULT 0
                """)

                # Remove franchise_name column if it exists
                cur.execute("""
                    ALTER TABLE played_games
                    DROP COLUMN IF EXISTS franchise_name
                """)

                # Create index for faster searches
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_played_games_canonical_name
                    ON played_games(canonical_name)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_played_games_series_name
                    ON played_games(series_name)
                """)

                conn.commit()
                logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            conn.rollback()

    def get_user_strikes(self, user_id: int) -> int:
        """Get strike count for a user"""
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT strike_count FROM strikes WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                if result:
                    return int(cast(RealDictRow, result)['strike_count'])
                return 0
        except Exception as e:
            logger.error(f"Error getting strikes for user {user_id}: {e}")
            return 0

    def set_user_strikes(self, user_id: int, count: int):
        """Set strike count for a user"""
        conn = self.get_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO strikes (user_id, strike_count, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id)
                    DO UPDATE SET strike_count = %s, updated_at = CURRENT_TIMESTAMP
                """, (user_id, count, count))
                conn.commit()
        except Exception as e:
            logger.error(f"Error setting strikes for user {user_id}: {e}")
            conn.rollback()

    def add_user_strike(self, user_id: int) -> int:
        """Add a strike to a user and return new count"""
        current_strikes = self.get_user_strikes(user_id)
        new_count = current_strikes + 1
        self.set_user_strikes(user_id, new_count)
        return new_count

    def get_all_strikes(self) -> Dict[int, int]:
        """Get all users with strikes"""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, strike_count FROM strikes WHERE strike_count > 0")
                results = cur.fetchall()
                # Handle both RealDictCursor (dict-like) and regular cursor
                # (tuple-like)
                result_dict = {}
                for row in results:
                    try:
                        user_id = int(row['user_id'])  # type: ignore
                        strike_count = int(row['strike_count'])  # type: ignore
                    except (TypeError, KeyError):
                        user_id = int(row[0])
                        strike_count = int(row[1])
                    result_dict[user_id] = strike_count
                return result_dict
        except Exception as e:
            logger.error(f"Error getting all strikes: {e}")
            return {}

    def add_game_recommendation(
            self,
            name: str,
            reason: str,
            added_by: str) -> bool:
        """Add a game recommendation"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO game_recommendations (name, reason, added_by, created_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """, (name, reason, added_by))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding game recommendation: {e}")
            conn.rollback()
            return False

    def get_all_games(self) -> List[Dict[str, Any]]:
        """Get all game recommendations"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, name, reason, added_by, created_at
                    FROM game_recommendations
                    ORDER BY created_at ASC
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting game recommendations: {e}")
            return []

    def remove_game_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        """Remove game by index (1-based)"""
        games = self.get_all_games()
        if not games or index < 1 or index > len(games):
            return None

        game_to_remove = games[index - 1]
        return self.remove_game_by_id(game_to_remove['id'])

    def remove_game_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Remove game by name (fuzzy match)"""
        games = self.get_all_games()
        name_lower = name.lower().strip()

        # Try exact match first
        for game in games:
            if game['name'].lower().strip() == name_lower:
                return self.remove_game_by_id(game['id'])

        # Try fuzzy match
        import difflib
        game_names = [game['name'].lower() for game in games]
        matches = difflib.get_close_matches(
            name_lower, game_names, n=1, cutoff=0.8)

        if matches:
            match_name = matches[0]
            for game in games:
                if game['name'].lower() == match_name:
                    return self.remove_game_by_id(game['id'])

        return None

    def remove_game_by_id(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Remove game by database ID"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Get the game before deleting
                cur.execute(
                    "SELECT * FROM game_recommendations WHERE id = %s", (game_id,))
                game = cur.fetchone()

                if game:
                    cur.execute(
                        "DELETE FROM game_recommendations WHERE id = %s", (game_id,))
                    conn.commit()
                    return dict(game)
                return None
        except Exception as e:
            logger.error(f"Error removing game by ID {game_id}: {e}")
            conn.rollback()
            return None

    def game_exists(self, name: str) -> bool:
        """Check if a game recommendation already exists (fuzzy match)"""
        games = self.get_all_games()
        name_lower = name.lower().strip()

        # Check exact matches
        existing_names = [game['name'].lower().strip() for game in games]
        if name_lower in existing_names:
            return True

        # Check fuzzy matches
        import difflib

        matches = difflib.get_close_matches(
            name_lower, existing_names, n=1, cutoff=0.85)
        return len(matches) > 0

    def get_config_value(self, key: str) -> Optional[str]:
        """Get a configuration value"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM bot_config WHERE key = %s", (key,))
                result = cur.fetchone()
                if result:
                    # Handle both RealDictCursor (dict-like) and regular cursor
                    # (tuple-like)
                    try:
                        return str(result['value'])  # type: ignore
                    except (TypeError, KeyError):
                        return str(result[0])  # Fallback to index access
                return None
        except Exception as e:
            logger.error(f"Error getting config value {key}: {e}")
            return None

    def set_config_value(self, key: str, value: str):
        """Set a configuration value"""
        conn = self.get_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_config (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key)
                    DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
                """, (key, value, value))
                conn.commit()
        except Exception as e:
            logger.error(f"Error setting config value {key}: {e}")
            conn.rollback()

    def bulk_import_strikes(self, strikes_data: Dict[int, int]) -> int:
        """Bulk import strike data"""
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                # Prepare data for batch insert
                data_tuples = [(user_id, count, count)
                               for user_id, count in strikes_data.items() if count > 0]

                if data_tuples:
                    cur.executemany("""
                        INSERT INTO strikes (user_id, strike_count, updated_at)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id)
                        DO UPDATE SET strike_count = %s, updated_at = CURRENT_TIMESTAMP
                    """, data_tuples)
                    conn.commit()
                    logger.info(
                        f"Bulk imported {len(data_tuples)} strike records")
                    return len(data_tuples)
                return 0
        except Exception as e:
            logger.error(f"Error bulk importing strikes: {e}")
            conn.rollback()
            return 0

    def bulk_import_games(self, games_data: List[Dict[str, str]]) -> int:
        """Bulk import game recommendations"""
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                # Prepare data for batch insert
                data_tuples = [
                    (game["name"],
                     game["reason"],
                        game["added_by"]) for game in games_data]

                if data_tuples:
                    cur.executemany("""
                        INSERT INTO game_recommendations (name, reason, added_by, created_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    """, data_tuples)
                    conn.commit()
                    logger.info(
                        f"Bulk imported {len(data_tuples)} game recommendations")
                    return len(data_tuples)
                return 0
        except Exception as e:
            logger.error(f"Error bulk importing games: {e}")
            conn.rollback()
            return 0

    def clear_all_games(self):
        """Clear all game recommendations (use with caution)"""
        conn = self.get_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM game_recommendations")
                conn.commit()
                logger.info("All game recommendations cleared")
        except Exception as e:
            logger.error(f"Error clearing games: {e}")
            conn.rollback()

    def clear_all_strikes(self):
        """Clear all strikes (use with caution)"""
        conn = self.get_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM strikes")
                conn.commit()
                logger.info("All strikes cleared")
        except Exception as e:
            logger.error(f"Error clearing strikes: {e}")
            conn.rollback()

    def add_played_game(self,
                        canonical_name: str,
                        alternative_names: Optional[List[str]] = None,
                        series_name: Optional[str] = None,
                        genre: Optional[str] = None,
                        release_year: Optional[int] = None,
                        platform: Optional[str] = None,
                        first_played_date: Optional[str] = None,
                        completion_status: str = "unknown",
                        total_episodes: int = 0,
                        total_playtime_minutes: int = 0,
                        youtube_playlist_url: Optional[str] = None,
                        twitch_vod_urls: Optional[List[str]] = None,
                        notes: Optional[str] = None) -> bool:
        """Add a played game to the database"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                # Convert lists to comma-separated strings for TEXT fields
                alt_names_str = ','.join(
                    alternative_names) if alternative_names else ''
                vod_urls_str = ','.join(
                    twitch_vod_urls) if twitch_vod_urls else ''

                cur.execute("""
                    INSERT INTO played_games (
                        canonical_name, alternative_names, series_name, genre,
                        release_year, platform, first_played_date, completion_status, total_episodes,
                        total_playtime_minutes, youtube_playlist_url, twitch_vod_urls, notes,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    canonical_name,
                    alt_names_str,
                    series_name,
                    genre,
                    release_year,
                    platform,
                    first_played_date,
                    completion_status,
                    total_episodes,
                    total_playtime_minutes,
                    youtube_playlist_url,
                    vod_urls_str,
                    notes
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

                # Search alternative names (now stored as comma-separated TEXT)
                cur.execute("""
                    SELECT * FROM played_games
                    WHERE alternative_names IS NOT NULL
                    AND alternative_names != ''
                    AND %s = ANY(string_to_array(LOWER(alternative_names), ','))
                """, (name_lower,))
                result = cur.fetchone()

                if result:
                    result_dict = dict(result)
                    result_dict = self._convert_text_to_arrays(result_dict)
                    logger.debug(
                        f"Found game by alternative name match: {name}")
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

    def _parse_comma_separated_list(self, text: Optional[str]) -> List[str]:
        """Convert a comma-separated string to a list of stripped, non-empty items"""
        if not text or not isinstance(text, str):
            return []
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
                        ORDER BY release_year ASC, canonical_name ASC
                    """, (series_name.lower(),))
                else:
                    cur.execute("""
                        SELECT * FROM played_games
                        ORDER BY series_name ASC, release_year ASC, canonical_name ASC
                    """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting played games: {e}")
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
                    'notes']

                updates = []
                values = []

                for field, value in kwargs.items():
                    if field in valid_fields:
                        # Special handling for array fields
                        if field in ['alternative_names', 'twitch_vod_urls']:
                            if isinstance(value, list):
                                # Convert list to PostgreSQL array format
                                updates.append(f"{field} = %s")
                                values.append(value)
                            elif isinstance(value, str):
                                # Handle single string by converting to list
                                updates.append(f"{field} = %s")
                                values.append([value])
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
                    SELECT canonical_name, COUNT(*) as count
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
                    canonical_name = duplicate[0]
                    duplicate_count = duplicate[1]

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
                    merged_data = {
                        "alternative_names": master_game.get(
                            "alternative_names",
                            []) or [],
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
                            0),
                        "total_playtime_minutes": master_game.get(
                            "total_playtime_minutes",
                            0),
                        "youtube_playlist_url": master_game.get("youtube_playlist_url"),
                        "twitch_vod_urls": master_game.get(
                            "twitch_vod_urls",
                            []) or [],
                        "notes": master_game.get(
                            "notes",
                            ""),
                    }

                    # Merge data from duplicates
                    for duplicate_game in games_to_merge:
                        # Merge alternative names
                        if duplicate_game.get('alternative_names'):
                            if isinstance(
                                    duplicate_game['alternative_names'], str):
                                # Handle TEXT format
                                alt_names = self._parse_comma_separated_list(
                                    duplicate_game["alternative_names"])
                            else:
                                # Handle list format
                                alt_names = duplicate_game["alternative_names"]

                            merged_data["alternative_names"] = list(
                                set(merged_data["alternative_names"] + alt_names))

                        # Merge Twitch VOD URLs
                        if duplicate_game.get('twitch_vod_urls'):
                            if isinstance(
                                    duplicate_game['twitch_vod_urls'], str):
                                # Handle TEXT format
                                vod_urls = self._parse_comma_separated_list(
                                    duplicate_game["twitch_vod_urls"])
                            else:
                                # Handle list format
                                vod_urls = duplicate_game["twitch_vod_urls"]

                            merged_data["twitch_vod_urls"] = list(
                                set(merged_data["twitch_vod_urls"] + vod_urls))

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
                                not merged_data["first_played_date"]
                                or duplicate_game["first_played_date"] < merged_data["first_played_date"]
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

                    # Convert lists to TEXT format for database storage
                    alt_names_str = (
                        ",".join(
                            merged_data["alternative_names"]) if merged_data["alternative_names"] else "")
                    vod_urls_str = ",".join(
                        merged_data["twitch_vod_urls"]) if merged_data["twitch_vod_urls"] else ""

                    # Update the master record with merged data
                    cur.execute("""
                        UPDATE played_games SET
                            alternative_names = %s,
                            series_name = %s,
                            genre = %s,
                            release_year = %s,
                            platform = %s,
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
                        merged_data['platform'],
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
                status_counts = {str(cast(RealDictRow, row)['completion_status']): int(
                    cast(RealDictRow, row)['count']) for row in status_results} if status_results else {}

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
                top_genres = {str(cast(RealDictRow, row)['genre']): int(
                    cast(RealDictRow, row)['count']) for row in genre_results} if genre_results else {}

                # Series distribution (replacing franchise)
                cur.execute(
                    "SELECT series_name, COUNT(*) as count FROM played_games WHERE series_name IS NOT NULL GROUP BY series_name ORDER BY COUNT(*) DESC LIMIT 5")
                series_results = cur.fetchall()
                top_series = {str(cast(RealDictRow, row)['series_name']): int(
                    cast(RealDictRow, row)['count']) for row in series_results} if series_results else {}

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

    def get_games_by_episode_count(
            self, order: str = 'DESC') -> List[Dict[str, Any]]:
        """Get games ranked by episode count"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                order_clause = "DESC" if order.upper() == "DESC" else "ASC"
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
                    LIMIT 15
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by episode count: {e}")
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
                'episodes': game1.get('total_episodes', 0),
                'playtime_minutes': game1.get('total_playtime_minutes', 0),
                'playtime_hours': round(game1.get('total_playtime_minutes', 0) / 60, 1),
                'status': game1.get('completion_status'),
                'genre': game1.get('genre')
            },
            "game2": {
                "name": game2["canonical_name"],
                "series": game2.get("series_name"),
                "episodes": game2.get("total_episodes", 0),
                "playtime_minutes": game2.get("total_playtime_minutes", 0),
                "playtime_hours": round(game2.get("total_playtime_minutes", 0) / 60, 1),
                "status": game2.get("completion_status"),
                "genre": game2.get("genre"),
            },
            "comparison": {
                "episode_difference": game1.get("total_episodes", 0) - game2.get("total_episodes", 0),
                "playtime_difference_minutes": game1.get("total_playtime_minutes", 0)
                - game2.get("total_playtime_minutes", 0),
                "longer_game": (
                    game1["canonical_name"]
                    if game1.get("total_playtime_minutes", 0) > game2.get("total_playtime_minutes", 0)
                    else game2["canonical_name"]
                ),
                "more_episodes": (
                    game1["canonical_name"]
                    if game1.get("total_episodes", 0) > game2.get("total_episodes", 0)
                    else game2["canonical_name"]
                ),
            },
            'comparison': {
                'episode_difference': game1.get('total_episodes', 0) - game2.get('total_episodes', 0),
                'playtime_difference_minutes': game1.get('total_playtime_minutes', 0) - game2.get('total_playtime_minutes', 0),
                'longer_game': game1['canonical_name'] if game1.get('total_playtime_minutes', 0) > game2.get('total_playtime_minutes', 0) else game2['canonical_name'],
                'more_episodes': game1['canonical_name'] if game1.get('total_episodes', 0) > game2.get('total_episodes', 0) else game2['canonical_name']
            }
        }

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

    def get_pending_reminders_for_user(self, user_id: int) -> List[Dict[str, Any]]:
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
            logger.error(f"Error getting pending reminders for user {user_id}: {e}")
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

    def cancel_reminder(self, reminder_id: int) -> bool:
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

    # --- Trivia System Methods ---

    def add_trivia_question(
        self,
        question_text: str,
        question_type: str,
        correct_answer: Optional[str] = None,
        multiple_choice_options: Optional[List[str]] = None,
        is_dynamic: bool = False,
        dynamic_query_type: Optional[str] = None,
        submitted_by_user_id: Optional[int] = None,
        category: Optional[str] = None,
        difficulty_level: int = 1,
    ) -> Optional[int]:
        """Add a new trivia question to the database"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trivia_questions (
                        question_text, question_type, correct_answer, multiple_choice_options,
                        is_dynamic, dynamic_query_type, submitted_by_user_id, category, difficulty_level,
                        created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                """,
                    (
                        question_text,
                        question_type,
                        correct_answer,
                        multiple_choice_options,
                        is_dynamic,
                        dynamic_query_type,
                        submitted_by_user_id,
                        category,
                        difficulty_level,
                    ),
                )
                result = cur.fetchone()
                conn.commit()

                if result:
                    question_id = int(result["id"])  # type: ignore
                    logger.info(f"Added trivia question ID {question_id}")
                    return question_id
                return None
        except Exception as e:
            logger.error(f"Error adding trivia question: {e}")
            conn.rollback()
            return None

    def get_next_trivia_question(
            self, exclude_user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get the next trivia question based on priority system (excluding answered questions)"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Build exclusion condition if exclude_user_id is provided
                exclusion_condition = ""
                query_params = []

                if exclude_user_id is not None:
                    exclusion_condition = "AND (submitted_by_user_id != %s OR submitted_by_user_id IS NULL)"
                    query_params = [exclude_user_id]

                # Priority 1: Recent mod-submitted questions (available status,
                # unused within 4 weeks)
                query1 = f"""
                    SELECT * FROM trivia_questions
                    WHERE is_active = TRUE
                    AND status = 'available'
                    AND submitted_by_user_id IS NOT NULL
                    AND (last_used_at IS NULL OR last_used_at < CURRENT_TIMESTAMP - INTERVAL '4 weeks')
                    {exclusion_condition}
                    ORDER BY created_at DESC, usage_count ASC
                    LIMIT 1
                """
                cur.execute(query1, query_params)
                result = cur.fetchone()

                if result:
                    return dict(result)

                # Priority 2: AI-generated questions focusing on statistical
                # anomalies (available status)
                query2 = f"""
                    SELECT * FROM trivia_questions
                    WHERE is_active = TRUE
                    AND status = 'available'
                    AND submitted_by_user_id IS NULL
                    AND (category IN ('statistical_anomaly', 'completion_rate', 'playtime_insight')
                         OR is_dynamic = TRUE)
                    AND (last_used_at IS NULL OR last_used_at < CURRENT_TIMESTAMP - INTERVAL '2 weeks')
                    {exclusion_condition}
                    ORDER BY usage_count ASC, created_at ASC
                    LIMIT 1
                """
                cur.execute(query2, query_params)
                result = cur.fetchone()

                if result:
                    return dict(result)

                # Priority 3: Any unused questions with available status
                query3 = f"""
                    SELECT * FROM trivia_questions
                    WHERE is_active = TRUE
                    AND status = 'available'
                    AND (last_used_at IS NULL OR last_used_at < CURRENT_TIMESTAMP - INTERVAL '1 week')
                    {exclusion_condition}
                    ORDER BY usage_count ASC, created_at ASC
                    LIMIT 1
                """
                cur.execute(query3, query_params)
                result = cur.fetchone()

                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting next trivia question: {e}")
            return None

    def create_trivia_session(
            self,
            question_id: int,
            session_type: str = "weekly",
            calculated_answer: Optional[str] = None) -> Optional[int]:
        """Create a new trivia session"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Get question submitter for conflict checking
                cur.execute(
                    "SELECT submitted_by_user_id FROM trivia_questions WHERE id = %s",
                    (question_id,
                     ))
                question_result = cur.fetchone()
                question_submitter_id = cast(RealDictRow, question_result)["submitted_by_user_id"] if question_result else None

                from datetime import datetime, timezone

                session_date = datetime.now(timezone.utc).date()

                cur.execute(
                    """
                    INSERT INTO trivia_sessions (
                        question_id, session_date, session_type, question_submitter_id,
                        calculated_answer, started_at
                    ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                """,
                    (question_id,
                     session_date,
                     session_type,
                     question_submitter_id,
                     calculated_answer),
                )
                result = cur.fetchone()

                # Update question usage
                cur.execute(
                    """
                    UPDATE trivia_questions
                    SET last_used_at = CURRENT_TIMESTAMP, usage_count = usage_count + 1
                    WHERE id = %s
                """,
                    (question_id,),
                )

                conn.commit()

                if result:
                    session_id = int(result["id"])  # type: ignore
                    logger.info(
                        f"Created trivia session ID {session_id} for question {question_id}")
                    return session_id
                return None
        except Exception as e:
            logger.error(f"Error creating trivia session: {e}")
            conn.rollback()
            return None

    def get_active_trivia_session(self) -> Optional[Dict[str, Any]]:
        """Get the current active trivia session"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ts.*, tq.question_text, tq.question_type, tq.correct_answer,
                           tq.multiple_choice_options, tq.is_dynamic, tq.dynamic_query_type,
                           tq.submitted_by_user_id, tq.category
                    FROM trivia_sessions ts
                    JOIN trivia_questions tq ON ts.question_id = tq.id
                    WHERE ts.status = 'active'
                    ORDER BY ts.started_at DESC
                    LIMIT 1
                """
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting active trivia session: {e}")
            return None

    def submit_trivia_answer(
            self,
            session_id: int,
            user_id: int,
            answer_text: str,
            normalized_answer: Optional[str] = None) -> Optional[int]:
        """Submit an answer to a trivia session"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Check for conflict (mod answering their own question)
                cur.execute(
                    """
                    SELECT question_submitter_id FROM trivia_sessions WHERE id = %s
                """,
                    (session_id,),
                )
                session_result = cur.fetchone()

                conflict_detected = False
                if session_result and cast(RealDictRow, session_result)["question_submitter_id"] == user_id:
                    conflict_detected = True

                cur.execute(
                    """
                    INSERT INTO trivia_answers (
                        session_id, user_id, answer_text, normalized_answer,
                        conflict_detected, submitted_at
                    ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                """,
                    (session_id, user_id, answer_text, normalized_answer, conflict_detected),
                )
                result = cur.fetchone()
                conn.commit()

                if result:
                    answer_id = int(result["id"])  # type: ignore
                    logger.info(
                        f"Submitted trivia answer ID {answer_id} for session {session_id}")
                    return answer_id
                return None
        except Exception as e:
            logger.error(f"Error submitting trivia answer: {e}")
            conn.rollback()
            return None

    def complete_trivia_session(
        self,
        session_id: int,
        first_correct_user_id: Optional[int] = None,
        total_participants: Optional[int] = None,
        correct_count: Optional[int] = None,
    ) -> bool:
        """Complete a trivia session and mark correct answers"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                # Get session details
                cur.execute(
                    """
                    SELECT * FROM trivia_sessions ts
                    JOIN trivia_questions tq ON ts.question_id = tq.id
                    WHERE ts.id = %s
                """,
                    (session_id,),
                )
                session = cur.fetchone()
                if not session:
                    return False

                session_dict = dict(session)
                correct_answer = session_dict.get(
                    "calculated_answer") or session_dict.get("correct_answer")

                if correct_answer:
                    # Mark correct answers (excluding conflicts)
                    cur.execute(
                        """
                        UPDATE trivia_answers
                        SET is_correct = TRUE
                        WHERE session_id = %s
                        AND conflict_detected = FALSE
                        AND (
                            LOWER(TRIM(answer_text)) = LOWER(TRIM(%s))
                            OR LOWER(TRIM(normalized_answer)) = LOWER(TRIM(%s))
                        )
                    """,
                        (session_id, correct_answer, correct_answer),
                    )

                    # Only calculate counts if not provided as parameters
                    if total_participants is None or correct_count is None:
                        cur.execute(
                            """
                            SELECT COUNT(*) as total_participants,
                                   COUNT(CASE WHEN is_correct = TRUE THEN 1 END) as correct_count
                            FROM trivia_answers
                            WHERE session_id = %s AND conflict_detected = FALSE
                        """,
                            (session_id,),
                        )
                        counts = cur.fetchone()

                        if counts:
                            if total_participants is None:
                                total_participants = int(
                                    counts["total_participants"])  # type: ignore
                            if correct_count is None:
                                correct_count = int(
                                    counts["correct_count"])  # type: ignore

                    # Use defaults if still None after database query
                    if total_participants is None:
                        total_participants = 0
                    if correct_count is None:
                        correct_count = 0

                    # Mark first correct answer
                    if first_correct_user_id:
                        cur.execute(
                            """
                            UPDATE trivia_answers
                            SET is_first_correct = TRUE
                            WHERE session_id = %s
                            AND user_id = %s
                            AND is_correct = TRUE
                        """,
                            (session_id, first_correct_user_id),
                        )

                # Update session
                cur.execute(
                    """
                    UPDATE trivia_sessions
                    SET status = 'completed',
                        ended_at = CURRENT_TIMESTAMP,
                        first_correct_user_id = %s,
                        total_participants = %s,
                        correct_answers_count = %s
                    WHERE id = %s
                """,
                    (first_correct_user_id, total_participants, correct_count, session_id),
                )

                # Mark the question as 'answered' so it won't be chosen again
                question_id = session_dict.get("question_id")
                if question_id:
                    cur.execute(
                        """
                        UPDATE trivia_questions
                        SET status = 'answered'
                        WHERE id = %s
                    """,
                        (question_id,),
                    )
                    logger.info(
                        f"Marked trivia question {question_id} as 'answered'")

                conn.commit()
                logger.info(f"Completed trivia session {session_id}")
                return True
        except Exception as e:
            logger.error(f"Error completing trivia session: {e}")
            conn.rollback()
            return False

    def get_trivia_session_answers(
            self, session_id: int) -> List[Dict[str, Any]]:
        """Get all answers for a trivia session"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM trivia_answers
                    WHERE session_id = %s
                    ORDER BY submitted_at ASC
                """,
                    (session_id,),
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting trivia session answers: {e}")
            return []

    def calculate_dynamic_answer(
            self, dynamic_query_type: str) -> Optional[str]:
        """Calculate the current answer for a dynamic question"""
        try:
            if dynamic_query_type == "longest_playtime":
                games = self.get_longest_completion_games()
                if games:
                    return games[0]["canonical_name"]

            elif dynamic_query_type == "most_episodes":
                games = self.get_games_by_episode_count("DESC")
                if games:
                    return games[0]["canonical_name"]

            elif dynamic_query_type == "series_most_playtime":
                series = self.get_series_by_total_playtime()
                if series:
                    return series[0]["series_name"]

            elif dynamic_query_type == "highest_avg_episode":
                games = self.get_games_by_average_episode_length()
                if games:
                    return games[0]["canonical_name"]

            elif dynamic_query_type == "genre_most_games":
                stats = self.get_genre_statistics()
                if stats:
                    return stats[0]["genre"]

            # Add more dynamic query types as needed
            return None
        except Exception as e:
            logger.error(
                f"Error calculating dynamic answer for {dynamic_query_type}: {e}")
            return None

    def get_trivia_question_by_id(
            self, question_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific trivia question by ID"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM trivia_questions WHERE id = %s", (question_id,))
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(
                f"Error getting trivia question by ID {question_id}: {e}")
            return None

    def get_pending_trivia_questions(
            self, submitted_by_user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get pending trivia questions for mod review"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                if submitted_by_user_id:
                    cur.execute(
                        """
                        SELECT * FROM trivia_questions
                        WHERE submitted_by_user_id = %s
                        ORDER BY created_at DESC
                    """,
                        (submitted_by_user_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM trivia_questions
                        WHERE submitted_by_user_id IS NOT NULL
                        AND is_active = TRUE
                        ORDER BY created_at DESC
                    """
                    )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting pending trivia questions: {e}")
            return []

    def get_answered_trivia_questions(self) -> List[Dict[str, Any]]:
        """Get all trivia questions that have been answered"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM trivia_questions
                    WHERE status = 'answered'
                    AND is_active = TRUE
                    ORDER BY last_used_at DESC
                """
                )
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting answered trivia questions: {e}")
            return []

    def reset_trivia_question_status(
            self,
            question_id: int,
            new_status: str = 'available') -> bool:
        """Reset a trivia question's status (e.g., from 'answered' back to 'available')"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE trivia_questions
                    SET status = %s
                    WHERE id = %s
                """,
                    (new_status, question_id),
                )
                conn.commit()

                if cur.rowcount > 0:
                    logger.info(
                        f"Reset trivia question {question_id} status to '{new_status}'")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error resetting trivia question status: {e}")
            conn.rollback()
            return False

    def reset_all_trivia_questions_status(
            self,
            from_status: str = 'answered',
            to_status: str = 'available') -> int:
        """Reset all trivia questions from one status to another (bulk operation)"""
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE trivia_questions
                    SET status = %s
                    WHERE status = %s
                    AND is_active = TRUE
                """,
                    (to_status, from_status),
                )
                conn.commit()

                reset_count = cur.rowcount
                if reset_count > 0:
                    logger.info(
                        f"Reset {reset_count} trivia questions from '{from_status}' to '{to_status}'")
                return reset_count
        except Exception as e:
            logger.error(f"Error resetting trivia questions status: {e}")
            conn.rollback()
            return 0

    def get_trivia_question_statistics(self) -> Dict[str, Any]:
        """Get statistics about trivia questions by status"""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                # Combined query using UNION ALL for efficiency
                cur.execute(
                    """
                    SELECT 'status' as dimension, status as value, COUNT(*) as count
                    FROM trivia_questions
                    WHERE is_active = TRUE
                    GROUP BY status
                    UNION ALL
                    SELECT 'type' as dimension, question_type as value, COUNT(*) as count
                    FROM trivia_questions
                    WHERE is_active = TRUE
                    GROUP BY question_type
                    UNION ALL
                    SELECT 'source' as dimension, CASE WHEN submitted_by_user_id IS NOT NULL THEN 'mod_submitted' ELSE 'ai_generated' END as value, COUNT(*) as count
                    FROM trivia_questions
                    WHERE is_active = TRUE
                    GROUP BY (submitted_by_user_id IS NOT NULL)
                    """
                )
                results = cur.fetchall()
                status_counts: Dict[str, int] = {}
                type_counts: Dict[str, int] = {}
                source_counts: Dict[str, int] = {}

                if results:
                    for row in results:
                        row_dict = dict(row)
                        dimension = row_dict['dimension']
                        value = str(row_dict['value'])
                        count = int(row_dict['count'])
                        if dimension == 'status':
                            status_counts[value] = count
                        elif dimension == 'type':
                            type_counts[value] = count
                        elif dimension == 'source':
                            source_counts[value] = count

                return {
                    "status_counts": status_counts,
                    "type_counts": type_counts,
                    "source_counts": source_counts,
                    "total_questions": sum(
                        status_counts.values()) if status_counts else 0,
                    "available_questions": status_counts.get(
                        'available',
                        0),
                    "answered_questions": status_counts.get(
                        'answered',
                        0),
                    "retired_questions": status_counts.get(
                        'retired',
                        0),
                }
        except Exception as e:
            logger.error(f"Error getting trivia question statistics: {e}")
            return {}

    # --- Missing Trivia Methods for Command Compatibility ---

    def get_trivia_question(self, question_id: int) -> Optional[Dict[str, Any]]:
        """Get trivia question by ID (alias for get_trivia_question_by_id)"""
        return self.get_trivia_question_by_id(question_id)

    def get_available_trivia_questions(self) -> List[Dict[str, Any]]:
        """Get all available trivia questions"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM trivia_questions
                    WHERE is_active = TRUE AND status = 'available'
                    ORDER BY 
                        CASE WHEN submitted_by_user_id IS NOT NULL THEN 1 ELSE 2 END,
                        created_at DESC,
                        usage_count ASC
                """)
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting available trivia questions: {e}")
            return []

    def start_trivia_session(self, question_id: int, started_by: int) -> Optional[int]:
        """Start trivia session (alias for create_trivia_session)"""
        return self.create_trivia_session(question_id, "weekly")

    def end_trivia_session(self, session_id: int, ended_by: int) -> Optional[Dict[str, Any]]:
        """End trivia session and return results"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Get session and question details
                cur.execute("""
                    SELECT ts.*, tq.question_text, tq.correct_answer, tq.calculated_answer
                    FROM trivia_sessions ts
                    JOIN trivia_questions tq ON ts.question_id = tq.id
                    WHERE ts.id = %s
                """, (session_id,))
                session = cur.fetchone()
                
                if not session:
                    return None
                
                session_dict = dict(session)
                
                # Get all answers for this session
                answers = self.get_trivia_session_answers(session_id)
                
                # Calculate results
                total_participants = len([a for a in answers if not a.get('conflict_detected', False)])
                correct_answers = len([a for a in answers if a.get('is_correct', False) and not a.get('conflict_detected', False)])
                first_correct_user = next((a for a in answers if a.get('is_first_correct', False)), None)
                
                # Complete the session
                first_correct_user_id = first_correct_user['user_id'] if first_correct_user else None
                success = self.complete_trivia_session(session_id, first_correct_user_id, total_participants, correct_answers)
                
                if success:
                    correct_answer = session_dict.get('calculated_answer') or session_dict.get('correct_answer')
                    return {
                        'session_id': session_id,
                        'question_id': session_dict.get('question_id'),
                        'question': session_dict.get('question_text'),
                        'correct_answer': correct_answer,
                        'total_participants': total_participants,
                        'correct_answers': correct_answers,
                        'first_correct': first_correct_user
                    }
                
                return None
        except Exception as e:
            logger.error(f"Error ending trivia session {session_id}: {e}")
            return None

    def get_trivia_leaderboard(self, timeframe: str = "all") -> Dict[str, Any]:
        """Get trivia leaderboard data"""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                # Build date filter based on timeframe
                date_filter = ""
                if timeframe == "week":
                    date_filter = "AND ts.started_at >= CURRENT_DATE - INTERVAL '7 days'"
                elif timeframe == "month":
                    date_filter = "AND ts.started_at >= CURRENT_DATE - INTERVAL '30 days'"
                
                # Get participant statistics
                cur.execute(f"""
                    SELECT 
                        ta.user_id,
                        COUNT(*) as total_answers,
                        COUNT(CASE WHEN ta.is_correct = TRUE THEN 1 END) as correct_answers,
                        COUNT(CASE WHEN ta.is_first_correct = TRUE THEN 1 END) as first_correct
                    FROM trivia_answers ta
                    JOIN trivia_sessions ts ON ta.session_id = ts.id
                    WHERE ta.conflict_detected = FALSE {date_filter}
                    GROUP BY ta.user_id
                    ORDER BY correct_answers DESC, total_answers DESC
                    LIMIT 20
                """)
                participants = cur.fetchall()
                
                # Get overall statistics
                cur.execute(f"""
                    SELECT 
                        COUNT(DISTINCT ts.id) as total_sessions,
                        COUNT(DISTINCT ts.question_id) as total_questions,
                        AVG(ts.total_participants) as avg_participation
                    FROM trivia_sessions ts
                    WHERE ts.status = 'completed' {date_filter}
                """)
                stats = cur.fetchone()
                
                return {
                    'participants': [dict(row) for row in participants],
                    'total_sessions': int(cast(RealDictRow, stats)['total_sessions']) if stats else 0,
                    'total_questions': int(cast(RealDictRow, stats)['total_questions']) if stats else 0,
                    'avg_participation_per_session': float(cast(RealDictRow, stats)['avg_participation']) if stats else 0.0
                }
        except Exception as e:
            logger.error(f"Error getting trivia leaderboard: {e}")
            return {}

    def reset_trivia_questions(self) -> int:
        """Reset all answered questions to available (alias for reset_all_trivia_questions_status)"""
        return self.reset_all_trivia_questions_status('answered', 'available')

    # --- Missing Announcement System ---

    def log_announcement(self, user_id: int, message: str, announcement_type: str = "general") -> bool:
        """Log announcement to database"""
        try:
            self.set_config_value(f"last_announcement_{announcement_type}", f"{user_id}|{message}|{datetime.now().isoformat()}")
            return True
        except Exception as e:
            logger.error(f"Error logging announcement: {e}")
            return False

    # --- Missing Import/Enhancement Systems ---

    def bulk_import_from_youtube(self) -> Dict[str, Any]:
        """Placeholder for YouTube import functionality"""
        logger.warning("bulk_import_from_youtube not implemented yet")
        return {"status": "not_implemented", "message": "YouTube import functionality not available"}

    def bulk_import_from_twitch(self) -> Dict[str, Any]:
        """Placeholder for Twitch import functionality"""
        logger.warning("bulk_import_from_twitch not implemented yet")
        return {"status": "not_implemented", "message": "Twitch import functionality not available"}

    def ai_enhance_game_metadata(self) -> Dict[str, Any]:
        """Placeholder for AI metadata enhancement"""
        logger.warning("ai_enhance_game_metadata not implemented yet")
        return {"status": "not_implemented", "message": "AI enhancement functionality not available"}


# Singleton database manager instance
_db_instance: Optional[DatabaseManager] = None

def get_database() -> DatabaseManager:
    """Get the singleton database manager instance with proper typing"""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
    return _db_instance

# Backward compatibility alias - can be removed after full migration
db = get_database()

# Export list for proper module interface
__all__ = ['DatabaseManager', 'get_database', 'db']
