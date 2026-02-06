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

    # Delegation methods for backward compatibility
    # These delegate to the appropriate sub-modules while maintaining
    # the original DatabaseManager API

    def get_all_played_games(self, series_name: Optional[str] = None):
        """Delegate to games module - get all played games"""
        return self.games.get_all_played_games(series_name)

    def get_games_by_playtime(self, order: str = 'DESC', limit: int = 15):
        """Delegate to games module - get games ranked by playtime"""
        return self.games.get_games_by_playtime(order, limit)

    def get_active_trivia_session(self):
        """Delegate to trivia module - get active trivia session"""
        return self.trivia.get_active_trivia_session()

    # ========== REMINDER DELEGATIONS (to users module) ==========

    def get_due_reminders(self, current_time):
        """Delegate to users module - get due reminders"""
        return self.users.get_due_reminders(current_time)

    def get_reminders_awaiting_auto_action(self, current_time):
        """Delegate to users module - get reminders awaiting auto action"""
        return self.users.get_reminders_awaiting_auto_action(current_time)

    def add_reminder(self, user_id, reminder_text, scheduled_time, delivery_channel_id=None,
                     delivery_type='dm', auto_action_enabled=False, auto_action_type=None,
                     auto_action_data=None):
        """Delegate to users module - add reminder"""
        return self.users.add_reminder(user_id, reminder_text, scheduled_time,
                                       delivery_channel_id, delivery_type,
                                       auto_action_enabled, auto_action_type, auto_action_data)

    def get_user_reminders(self, user_id, status='pending'):
        """Delegate to users module - get user reminders"""
        return self.users.get_user_reminders(user_id, status)

    def update_reminder_status(self, reminder_id, status, delivered_at=None, auto_executed_at=None):
        """Delegate to users module - update reminder status"""
        return self.users.update_reminder_status(reminder_id, status, delivered_at, auto_executed_at)

    def get_all_pending_reminders(self):
        """Delegate to users module - get all pending reminders"""
        return self.users.get_all_pending_reminders()

    def get_pending_reminders_for_user(self, user_id):
        """Delegate to users module - get pending reminders for user"""
        return self.users.get_pending_reminders_for_user(user_id)

    def get_reminder_by_id(self, reminder_id):
        """Delegate to users module - get reminder by ID"""
        return self.users.get_reminder_by_id(reminder_id)

    def cancel_user_reminder(self, reminder_id, user_id):
        """Delegate to users module - cancel user reminder"""
        return self.users.cancel_user_reminder(reminder_id, user_id)

    # ========== STRIKES DELEGATIONS (to users module) ==========

    def get_user_strikes(self, user_id):
        """Delegate to users module - get user strikes"""
        return self.users.get_user_strikes(user_id)

    def set_user_strikes(self, user_id, count):
        """Delegate to users module - set user strikes"""
        return self.users.set_user_strikes(user_id, count)

    def add_user_strike(self, user_id):
        """Delegate to users module - add user strike"""
        return self.users.add_user_strike(user_id)

    def get_all_strikes(self):
        """Delegate to users module - get all strikes"""
        return self.users.get_all_strikes()

    def bulk_import_strikes(self, strikes_data):
        """Delegate to users module - bulk import strikes"""
        return self.users.bulk_import_strikes(strikes_data)

    def clear_all_strikes(self):
        """Delegate to users module - clear all strikes"""
        return self.users.clear_all_strikes()

    # ========== GAME RECOMMENDATIONS DELEGATIONS (to users module) ==========

    def add_game_recommendation(self, name, reason, added_by):
        """Delegate to users module - add game recommendation"""
        return self.users.add_game_recommendation(name, reason, added_by)

    def get_all_games(self):
        """Delegate to users module - get all game recommendations"""
        return self.users.get_all_games()

    def remove_game_by_index(self, index):
        """Delegate to users module - remove game by index"""
        return self.users.remove_game_by_index(index)

    def remove_game_by_name(self, name):
        """Delegate to users module - remove game by name"""
        return self.users.remove_game_by_name(name)

    def remove_game_by_id(self, game_id):
        """Delegate to users module - remove game by ID"""
        return self.users.remove_game_by_id(game_id)

    def game_exists(self, name):
        """Delegate to users module - check if game exists"""
        return self.users.game_exists(name)

    def bulk_import_games(self, games_data):
        """Delegate to users module - bulk import games"""
        return self.users.bulk_import_games(games_data)

    def clear_all_games(self):
        """Delegate to users module - clear all games"""
        return self.users.clear_all_games()

    # ========== CONFIG DELEGATIONS (to config module) ==========

    def get_config_value(self, key):
        """Delegate to config module - get config value"""
        return self.config.get_config_value(key)

    def set_config_value(self, key, value):
        """Delegate to config module - set config value"""
        return self.config.set_config_value(key, value)

    def delete_config_value(self, key):
        """Delegate to config module - delete config value"""
        return self.config.delete_config_value(key)

    # ========== GAMES DELEGATIONS (to games module) ==========

    def get_games_by_franchise(self, series_name):
        """Delegate to games module - get games by franchise"""
        return self.games.get_games_by_franchise(series_name)

    def update_played_game(self, game_id, **kwargs):
        """Delegate to games module - update played game"""
        return self.games.update_played_game(game_id, **kwargs)

    def add_played_game(self, **kwargs):
        """Delegate to games module - add played game"""
        return self.games.add_played_game(**kwargs)

    def get_played_game(self, game_name):
        """Delegate to games module - get played game"""
        return self.games.get_played_game(game_name)

    def deduplicate_played_games(self):
        """Delegate to games module - deduplicate played games"""
        return self.games.deduplicate_played_games()

    def get_series_by_total_playtime(self):
        """Delegate to games module - get series by total playtime"""
        return self.games.get_series_by_total_playtime()

    def get_games_by_average_episode_length(self):
        """Delegate to games module - get games by average episode length"""
        return self.games.get_games_by_average_episode_length()

    def get_games_by_episode_count(self, order='DESC', limit=15):
        """Delegate to games module - get games by episode count"""
        return self.games.get_games_by_episode_count(order, limit)

    def get_games_by_played_date(self, order='DESC', limit=15):
        """Delegate to games module - get games by played date"""
        return self.games.get_games_by_played_date(order, limit)

    def get_games_by_release_year(self, order='DESC', limit=15):
        """Delegate to games module - get games by release year"""
        return self.games.get_games_by_release_year(order, limit)

    def get_genre_statistics(self):
        """Delegate to games module - get genre statistics"""
        return self.games.get_genre_statistics()

    def get_longest_completion_games(self):
        """Delegate to games module - get longest completion games"""
        return self.games.get_longest_completion_games()

    def compare_games(self, game1_name, game2_name):
        """Delegate to games module - compare games"""
        return self.games.compare_games(game1_name, game2_name)

    def get_games_by_genre_flexible(self, genre_query):
        """Delegate to games module - get games by genre flexible"""
        return self.games.get_games_by_genre_flexible(genre_query)

    def get_series_games(self, series_name):
        """Delegate to games module - get series games"""
        return self.games.get_series_games(series_name)

    def get_ranking_context(self, game_name, context_type='all'):
        """Delegate to games module - get ranking context"""
        return self.games.get_ranking_context(game_name, context_type)

    def get_cached_youtube_rankings(self):
        """Delegate to games module - get cached youtube rankings"""
        return self.games.get_cached_youtube_rankings()

    def update_youtube_cache(self, rankings):
        """Delegate to games module - update youtube cache"""
        return self.games.update_youtube_cache(rankings)

    def get_games_by_twitch_views(self, limit=10):
        """Delegate to games module - get games by twitch views"""
        return self.games.get_games_by_twitch_views(limit)

    def get_games_by_total_views(self, limit=10):
        """Delegate to games module - get games by total views"""
        return self.games.get_games_by_total_views(limit)

    def get_platform_comparison_stats(self):
        """Delegate to games module - get platform comparison stats"""
        return self.games.get_platform_comparison_stats()

    def get_engagement_metrics(self, limit=10):
        """Delegate to games module - get engagement metrics"""
        return self.games.get_engagement_metrics(limit)

    def get_gaming_timeline(self, order='ASC'):
        """Delegate to games module - get gaming timeline"""
        return self.games.get_gaming_timeline(order)

    def get_played_games_stats(self):
        """Delegate to games module - get played games stats"""
        return self.games.get_played_games_stats()

    def get_all_unique_series_names(self):
        """Delegate to games module - get all unique series names"""
        return self.games.get_all_unique_series_names()

    def played_game_exists(self, game_name):
        """Delegate to games module - check if played game exists"""
        return self.games.played_game_exists(game_name)

    # ========== TRIVIA DELEGATIONS (to trivia module) ==========

    def get_available_trivia_questions(self):
        """Delegate to trivia module - get available trivia questions"""
        return self.trivia.get_available_trivia_questions()

    def calculate_dynamic_answer(self, query_type, parameter=None):
        """Delegate to trivia module - calculate dynamic answer"""
        return self.trivia.calculate_dynamic_answer(query_type, parameter)

    def get_trivia_question_by_id(self, question_id):
        """Delegate to trivia module - get trivia question by id"""
        return self.trivia.get_trivia_question_by_id(question_id)

    def get_next_trivia_question(self, exclude_user_id=None):
        """Delegate to trivia module - get next trivia question"""
        return self.trivia.get_next_trivia_question(exclude_user_id)

    def create_trivia_session(self, question_id, **kwargs):
        """Delegate to trivia module - create trivia session"""
        return self.trivia.create_trivia_session(question_id, **kwargs)

    def update_trivia_session_messages(self, session_id, question_message_id, confirmation_message_id, channel_id):
        """Delegate to trivia module - update trivia session messages"""
        return self.trivia.update_trivia_session_messages(
            session_id, question_message_id, confirmation_message_id, channel_id)

    def end_trivia_session(self, session_id, ended_by=None):
        """Delegate to trivia module - end trivia session"""
        return self.trivia.end_trivia_session(session_id, ended_by)

    def get_trivia_participant_stats_for_week(self):
        """Delegate to trivia module - get trivia participant stats for week"""
        return self.trivia.get_trivia_participant_stats_for_week()

    def cleanup_hanging_trivia_sessions(self):
        """Delegate to trivia module - cleanup hanging trivia sessions"""
        return self.trivia.cleanup_hanging_trivia_sessions()

    def add_trivia_question(self, **kwargs):
        """Delegate to trivia module - add trivia question"""
        return self.trivia.add_trivia_question(**kwargs)

    def update_trivia_question_status(self, question_id, status):
        """Delegate to trivia module - update trivia question status"""
        return self.trivia.update_trivia_question_status(question_id, status)

    def get_trivia_session_by_message_id(self, message_id):
        """Delegate to trivia module - get trivia session by message id"""
        return self.trivia.get_trivia_session_by_message_id(message_id)

    def get_trivia_session_answers(self, session_id):
        """Delegate to trivia module - get trivia session answers"""
        return self.trivia.get_trivia_session_answers(session_id)

    def submit_trivia_answer(self, session_id, user_id, answer_text, normalized_answer=None):
        """Delegate to trivia module - submit trivia answer"""
        return self.trivia.submit_trivia_answer(session_id, user_id, answer_text, normalized_answer)

    def get_trivia_question(self, question_id):
        """Delegate to trivia module - get trivia question"""
        return self.trivia.get_trivia_question(question_id)

    def start_trivia_session(self, question_id, **kwargs):
        """Delegate to trivia module - start trivia session"""
        return self.trivia.start_trivia_session(question_id, **kwargs)

    def ensure_minimum_question_pool(self, minimum=5):
        """Delegate to trivia module - ensure minimum question pool"""
        return self.trivia.ensure_minimum_question_pool(minimum)

    def get_trivia_leaderboard(self, timeframe='all'):
        """Delegate to trivia module - get trivia leaderboard"""
        return self.trivia.get_trivia_leaderboard(timeframe)

    def get_pending_trivia_questions(self):
        """Delegate to trivia module - get pending trivia questions"""
        return self.trivia.get_pending_trivia_questions()

    def reset_trivia_questions(self):
        """Delegate to trivia module - reset trivia questions"""
        return self.trivia.reset_trivia_questions()

    def complete_trivia_session(self, session_id):
        """Delegate to trivia module - complete trivia session"""
        return self.trivia.complete_trivia_session(session_id)

    def get_trivia_question_statistics(self):
        """Delegate to trivia module - get trivia question statistics"""
        return self.trivia.get_trivia_question_statistics()

    def check_question_duplicate(self, question_text, similarity_threshold=0.8):
        """Delegate to trivia module - check question duplicate"""
        return self.trivia.check_question_duplicate(question_text, similarity_threshold)

    def safe_add_trivia_question(self, **kwargs):
        """Delegate to trivia module - safe add trivia question"""
        return self.trivia.safe_add_trivia_question(**kwargs)

    # ========== SESSIONS DELEGATIONS (to sessions module) ==========

    def create_weekly_announcement(self, day, content, analysis_cache=None):
        """Delegate to sessions module - create weekly announcement"""
        return self.sessions.create_weekly_announcement(day, content, analysis_cache)

    def get_announcement_by_day(self, day, status='pending_approval'):
        """Delegate to sessions module - get announcement by day"""
        return self.sessions.get_announcement_by_day(day, status)

    def update_announcement_status(self, announcement_id, status, new_content=None):
        """Delegate to sessions module - update announcement status"""
        return self.sessions.update_announcement_status(announcement_id, status, new_content)

    def get_all_active_approval_sessions(self):
        """Delegate to sessions module - get all active approval sessions"""
        return self.sessions.get_all_active_approval_sessions()

    def update_approval_session(self, session_id, increment_restart_count=False, **kwargs):
        """Delegate to sessions module - update approval session"""
        return self.sessions.update_approval_session(session_id, increment_restart_count, **kwargs)

    def complete_approval_session(self, session_id, status='completed'):
        """Delegate to sessions module - complete approval session"""
        return self.sessions.complete_approval_session(session_id, status)

    def create_game_review_session(self, **kwargs):
        """Delegate to sessions module - create game review session"""
        return self.sessions.create_game_review_session(**kwargs)

    def update_game_review_session(self, session_id, **kwargs):
        """Delegate to sessions module - update game review session"""
        return self.sessions.update_game_review_session(session_id, **kwargs)

    def complete_game_review_session(self, session_id, status='completed'):
        """Delegate to sessions module - complete game review session"""
        return self.sessions.complete_game_review_session(session_id, status)

    def create_approval_session(self, **kwargs):
        """Delegate to sessions module - create approval session"""
        return self.sessions.create_approval_session(**kwargs)

    def cleanup_expired_approval_sessions(self):
        """Delegate to sessions module - cleanup expired approval sessions"""
        return self.sessions.cleanup_expired_approval_sessions()

    # ========== STATS DELEGATIONS (to stats module) ==========

    def update_last_sync_timestamp(self, timestamp):
        """Delegate to stats module - update last sync timestamp"""
        return self.stats.update_last_sync_timestamp(timestamp)

    # ========== ADDITIONAL DELEGATIONS ==========

    def cancel_reminder(self, reminder_id):
        """Delegate to users module - cancel reminder (admin version)"""
        return self.users.cancel_reminder(reminder_id)

    def get_latest_game_update_timestamp(self):
        """Delegate to games module - get latest game update timestamp"""
        return self.games.get_latest_game_update_timestamp()

    def log_announcement(self, user_id, message, announcement_type='general'):
        """Delegate to config module - log announcement"""
        return self.config.log_announcement(user_id, message, announcement_type)

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
