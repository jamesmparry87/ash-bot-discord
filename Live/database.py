import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from typing import List, Dict, Optional, Any, Union

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            logger.warning("DATABASE_URL not found. Database features will be disabled.")
            self.connection = None
        else:
            self.connection = None
            self.init_database()
    
    def get_connection(self):
        """Get database connection with retry logic"""
        if not self.database_url:
            return None
        
        try:
            if self.connection is None or self.connection.closed:
                self.connection = psycopg2.connect(
                    self.database_url,
                    cursor_factory=RealDictCursor
                )
            return self.connection
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return None
    
    def init_database(self):
        """Initialize database tables"""
        if not self.database_url:
            logger.warning("Skipping database initialization - no DATABASE_URL")
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
                cur.execute("SELECT strike_count FROM strikes WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                if result:
                    return int(result[0])  # Use index instead of key
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
                cur.execute("SELECT user_id, strike_count FROM strikes WHERE strike_count > 0")
                results = cur.fetchall()
                return {int(row[0]): int(row[1]) for row in results}  # Use indices instead of keys
        except Exception as e:
            logger.error(f"Error getting all strikes: {e}")
            return {}
    
    def add_game_recommendation(self, name: str, reason: str, added_by: str) -> bool:
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
        matches = difflib.get_close_matches(name_lower, game_names, n=1, cutoff=0.8)
        
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
                cur.execute("SELECT * FROM game_recommendations WHERE id = %s", (game_id,))
                game = cur.fetchone()
                
                if game:
                    cur.execute("DELETE FROM game_recommendations WHERE id = %s", (game_id,))
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
        matches = difflib.get_close_matches(name_lower, existing_names, n=1, cutoff=0.85)
        return len(matches) > 0
    
    def get_config_value(self, key: str) -> Optional[str]:
        """Get a configuration value"""
        conn = self.get_connection()
        if not conn:
            return None
        
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM bot_config WHERE key = %s", (key,))
                result = cur.fetchone()
                if result:
                    return str(result[0])  # Use index instead of key
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
                data_tuples = [(user_id, count, count) for user_id, count in strikes_data.items() if count > 0]
                
                if data_tuples:
                    cur.executemany("""
                        INSERT INTO strikes (user_id, strike_count, updated_at)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id)
                        DO UPDATE SET strike_count = %s, updated_at = CURRENT_TIMESTAMP
                    """, data_tuples)
                    conn.commit()
                    logger.info(f"Bulk imported {len(data_tuples)} strike records")
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
                data_tuples = [(game['name'], game['reason'], game['added_by']) for game in games_data]
                
                if data_tuples:
                    cur.executemany("""
                        INSERT INTO game_recommendations (name, reason, added_by, created_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    """, data_tuples)
                    conn.commit()
                    logger.info(f"Bulk imported {len(data_tuples)} game recommendations")
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

    def close(self):
        """Close database connection"""
        if self.connection and not self.connection.closed:
            self.connection.close()

# Global database manager instance
db = DatabaseManager()
