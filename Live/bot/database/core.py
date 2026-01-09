"""
Database Core Module - Connection Management & Base Class

This module provides the foundational DatabaseManager class with:
- Database connection management
- SQL injection prevention helpers
- Database initialization
- Connection retry logic
"""

import logging
import os
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Base database manager with connection handling and security utilities.

    This class provides the core functionality for database connections,
    SQL injection prevention, and schema initialization. Domain-specific
    database classes inherit from or compose with this class.
    """

    # SQL Injection Prevention: Whitelisted columns for ORDER BY clauses
    PLAYED_GAMES_COLUMNS = [
        'id', 'canonical_name', 'series_name', 'genre', 'release_year',
        'platform', 'first_played_date', 'completion_status', 'total_episodes',
        'total_playtime_minutes', 'youtube_views', 'twitch_views', 'youtube_playlist_url',
        'created_at', 'updated_at'
    ]

    def __init__(self):
        """
        Initialize database manager with all domain modules.

        Reads DATABASE_URL from environment and establishes connection.
        If DATABASE_URL is not set, database features will be disabled.
        """
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            logger.warning(
                "DATABASE_URL not found. Database features will be disabled.")
            self.connection = None
        else:
            self.connection = None
            self.init_database()

        # Initialize domain modules (lazy loaded when first accessed)
        self._config = None
        self._sessions = None
        self._users = None
        self._stats = None
        self._trivia = None
        self._games = None

    @property
    def config(self):
        """Lazy-load config database module."""
        if self._config is None:
            from .config import ConfigDatabase
            self._config = ConfigDatabase(self)
        return self._config

    @property
    def sessions(self):
        """Lazy-load sessions database module."""
        if self._sessions is None:
            from .sessions import SessionDatabase
            self._sessions = SessionDatabase(self)
        return self._sessions

    @property
    def users(self):
        """Lazy-load users database module."""
        if self._users is None:
            from .users import UserDatabase
            self._users = UserDatabase(self)
        return self._users

    @property
    def stats(self):
        """Lazy-load stats database module."""
        if self._stats is None:
            from .stats import StatsDatabase
            self._stats = StatsDatabase(self)
        return self._stats

    @property
    def trivia(self):
        """Lazy-load trivia database module."""
        if self._trivia is None:
            from .trivia import TriviaDatabase
            self._trivia = TriviaDatabase(self)
        return self._trivia

    @property
    def games(self):
        """Lazy-load games database module."""
        if self._games is None:
            from .games import GamesDatabase
            self._games = GamesDatabase(self)
        return self._games

    def _validate_column_name(self, column: str, allowed_columns: List[str]) -> str:
        """
        Validate column name against whitelist to prevent SQL injection.

        Args:
            column: Column name to validate
            allowed_columns: List of allowed column names

        Returns:
            Validated column name

        Raises:
            ValueError: If column name is not in whitelist
        """
        if column not in allowed_columns:
            logger.error(f"SQL Injection attempt detected - Invalid column name: {column}")
            raise ValueError(f"Invalid column name: {column}")
        return column

    def _validate_order_direction(self, order: str) -> str:
        """
        Validate ORDER BY direction (ASC/DESC) to prevent SQL injection.

        Args:
            order: Order direction string

        Returns:
            Validated order direction (ASC or DESC)
        """
        order_upper = order.upper().strip()
        if order_upper not in ['ASC', 'DESC']:
            logger.warning(f"Invalid order direction '{order}', defaulting to DESC")
            return 'DESC'  # Safe default
        return order_upper

    def _parse_comma_separated_list(self, text: str) -> List[str]:
        """
        Parse comma-separated string into list of strings.

        Used for converting stored alternative_names from TEXT to List[str].

        Args:
            text: Comma-separated string

        Returns:
            List of strings (empty list if text is empty)
        """
        if not text or not text.strip():
            return []
        return [item.strip() for item in text.split(',') if item.strip()]

    def repair_database_sequences(self) -> dict:
        """
        Repair database sequences that are out of sync with table data.

        This can happen when IDs are manually inserted or during migrations.
        The method finds the maximum ID in each table and updates the sequence
        to continue from that point.

        Returns:
            Dict with repair results: {'repaired': List[str], 'total_repaired': int}
        """
        conn = self.get_connection()
        if not conn:
            logger.error("Cannot repair sequences: No database connection")
            return {'repaired': [], 'total_repaired': 0}

        repaired = []
        try:
            with conn.cursor() as cur:
                # List of tables with SERIAL primary keys
                tables_to_check = [
                    ('trivia_questions', 'id'),
                    ('trivia_sessions', 'id'),
                    ('trivia_answers', 'id'),
                    ('trivia_approval_sessions', 'id'),
                    ('game_review_sessions', 'id'),
                    ('played_games', 'id'),
                    ('game_recommendations', 'id'),
                    ('reminders', 'id'),
                    ('weekly_announcements', 'id'),
                    ('ai_alert_log', 'id')
                ]

                for table_name, id_column in tables_to_check:
                    try:
                        # Get the maximum ID currently in the table
                        cur.execute(f"SELECT MAX({id_column}) FROM {table_name}")
                        result = cur.fetchone()
                        max_id = result[0] if result and result[0] is not None else 0

                        # Set the sequence to max_id + 1
                        sequence_name = f"{table_name}_{id_column}_seq"
                        cur.execute(f"SELECT setval('{sequence_name}', %s, true)", (max(max_id, 1),))

                        repaired.append(f"{table_name} (set to {max_id + 1})")
                        logger.info(f"✅ Repaired sequence for {table_name}: set to {max_id + 1}")

                    except Exception as table_error:
                        logger.warning(f"Could not repair {table_name}: {table_error}")
                        # Continue with other tables

                conn.commit()
                logger.info(f"🔧 Sequence repair complete: {len(repaired)} sequences repaired")
                return {'repaired': repaired, 'total_repaired': len(repaired)}

        except Exception as e:
            logger.error(f"Error during sequence repair: {e}")
            conn.rollback()
            return {'repaired': [], 'total_repaired': 0}
        finally:
            if conn:
                conn.close()

    def get_connection(self):
        """
        Get database connection with retry logic.

        Always creates a fresh connection for each operation to avoid stale connections.
        This is more reliable than trying to reuse connections.

        Returns:
            psycopg2 connection object or None if connection fails
        """
        if not self.database_url:
            return None

        try:
            # Always create a fresh connection for each operation to avoid stale connections
            self.connection = psycopg2.connect(
                self.database_url, cursor_factory=RealDictCursor)
            return self.connection
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return None

    def init_database(self):
        """
        Initialize database tables and schema.

        Creates all necessary tables if they don't exist. This method is called
        automatically during __init__ if DATABASE_URL is set.
        """
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
                """)

                # Create played_games table (comprehensive schema)
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
                        youtube_views INTEGER,
                        twitch_vod_urls TEXT,
                        twitch_views INTEGER,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create indexes for played_games
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_played_games_canonical_name
                    ON played_games(canonical_name)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_played_games_series_name
                    ON played_games(series_name)
                """)

                # Create reminders table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        reminder_text TEXT NOT NULL,
                        scheduled_time TIMESTAMP NOT NULL,
                        delivery_channel_id BIGINT,
                        delivery_type VARCHAR(20) NOT NULL,
                        auto_action_enabled BOOLEAN DEFAULT FALSE,
                        auto_action_type VARCHAR(50),
                        auto_action_data JSONB,
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        delivered_at TIMESTAMP,
                        auto_executed_at TIMESTAMP
                    )
                """)

                # Create trivia tables
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trivia_questions (
                        id SERIAL PRIMARY KEY,
                        question_text TEXT NOT NULL,
                        question_type VARCHAR(20) NOT NULL,
                        correct_answer TEXT,
                        multiple_choice_options TEXT[],
                        is_dynamic BOOLEAN DEFAULT FALSE,
                        dynamic_query_type VARCHAR(50),
                        submitted_by_user_id BIGINT,
                        category VARCHAR(50),
                        difficulty_level INTEGER DEFAULT 1,
                        is_active BOOLEAN DEFAULT TRUE,
                        status VARCHAR(20) DEFAULT 'available',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_used_at TIMESTAMP,
                        usage_count INTEGER DEFAULT 0
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trivia_sessions (
                        id SERIAL PRIMARY KEY,
                        question_id INTEGER REFERENCES trivia_questions(id),
                        session_date DATE NOT NULL,
                        session_type VARCHAR(20) DEFAULT 'weekly',
                        question_submitter_id BIGINT,
                        calculated_answer TEXT,
                        status VARCHAR(20) DEFAULT 'active',
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ended_at TIMESTAMP,
                        first_correct_user_id BIGINT,
                        total_participants INTEGER DEFAULT 0,
                        correct_answers_count INTEGER DEFAULT 0,
                        question_message_id BIGINT,
                        confirmation_message_id BIGINT,
                        channel_id BIGINT
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trivia_answers (
                        id SERIAL PRIMARY KEY,
                        session_id INTEGER REFERENCES trivia_sessions(id),
                        user_id BIGINT NOT NULL,
                        answer_text TEXT NOT NULL,
                        normalized_answer TEXT,
                        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_correct BOOLEAN,
                        is_first_correct BOOLEAN DEFAULT FALSE,
                        conflict_detected BOOLEAN DEFAULT FALSE,
                        is_close BOOLEAN DEFAULT FALSE
                    )
                """)

                # Create session management tables
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trivia_approval_sessions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        session_type VARCHAR(50) NOT NULL DEFAULT 'question_approval',
                        conversation_step VARCHAR(50) NOT NULL,
                        question_data JSONB NOT NULL,
                        conversation_data JSONB DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        status VARCHAR(20) DEFAULT 'active',
                        bot_restart_count INTEGER DEFAULT 0
                    )
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trivia_approval_user_status
                    ON trivia_approval_sessions(user_id, status)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trivia_approval_expires
                    ON trivia_approval_sessions(expires_at)
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS game_review_sessions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        session_type VARCHAR(50) NOT NULL DEFAULT 'game_review',
                        original_title TEXT NOT NULL,
                        extracted_name TEXT NOT NULL,
                        confidence_score FLOAT NOT NULL,
                        alternative_names TEXT,
                        source VARCHAR(20) NOT NULL,
                        igdb_data JSONB,
                        video_url TEXT,
                        conversation_step VARCHAR(50) NOT NULL,
                        conversation_data JSONB DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        status VARCHAR(20) DEFAULT 'pending',
                        approved_name TEXT,
                        approved_data JSONB,
                        bot_restart_count INTEGER DEFAULT 0
                    )
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_game_review_user_status
                    ON game_review_sessions(user_id, status)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_game_review_expires
                    ON game_review_sessions(expires_at)
                """)

                # Create weekly_announcements table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS weekly_announcements (
                        id SERIAL PRIMARY KEY,
                        day VARCHAR(10) NOT NULL,
                        generated_content TEXT NOT NULL,
                        analysis_cache JSONB,
                        status VARCHAR(20) DEFAULT 'pending_approval',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        approved_at TIMESTAMP WITH TIME ZONE
                    )
                """)

                # Create AI usage tracking tables
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ai_usage_tracking (
                        tracking_date DATE PRIMARY KEY,
                        daily_requests INTEGER DEFAULT 0,
                        hourly_requests INTEGER DEFAULT 0,
                        daily_errors INTEGER DEFAULT 0,
                        last_reset_time TIMESTAMP WITH TIME ZONE,
                        last_hour_reset INTEGER DEFAULT 0,
                        quota_exhausted BOOLEAN DEFAULT FALSE,
                        current_model TEXT,
                        last_model_switch TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ai_alert_log (
                        id SERIAL PRIMARY KEY,
                        alert_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        message TEXT NOT NULL,
                        error_details JSONB,
                        dm_sent BOOLEAN DEFAULT FALSE,
                        dm_sent_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_alert_log_created
                    ON ai_alert_log(created_at)
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_alert_log_type_severity
                    ON ai_alert_log(alert_type, severity)
                """)

                conn.commit()
                logger.info("✅ Database tables initialized successfully")

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def close(self):
        """
        Close database connection.

        Should be called when shutting down the bot or during cleanup.
        """
        if self.connection:
            try:
                self.connection.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
