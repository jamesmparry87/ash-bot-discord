import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from typing import List, Dict, Optional, Any, Union, cast

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
            # Always create a fresh connection for each operation to avoid stale connections
            # This is more reliable than trying to reuse connections
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
                
                # Create played_games table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS played_games (
                        id SERIAL PRIMARY KEY,
                        canonical_name VARCHAR(255) NOT NULL,
                        alternative_names TEXT[],
                        series_name VARCHAR(255),
                        genre VARCHAR(100),
                        release_year INTEGER,
                        platform VARCHAR(100),
                        first_played_date DATE,
                        completion_status VARCHAR(50) DEFAULT 'unknown',
                        total_episodes INTEGER DEFAULT 0,
                        total_playtime_minutes INTEGER DEFAULT 0,
                        youtube_playlist_url TEXT,
                        twitch_vod_urls TEXT[],
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Add new columns to existing table if they don't exist (remove franchise_name)
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
                cur.execute("SELECT strike_count FROM strikes WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                if result:
                    # Handle both RealDictCursor (dict-like) and regular cursor (tuple-like)
                    try:
                        return int(result['strike_count'])  # type: ignore
                    except (TypeError, KeyError):
                        return int(result[0])  # Fallback to index access
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
                # Handle both RealDictCursor (dict-like) and regular cursor (tuple-like)
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
                    # Handle both RealDictCursor (dict-like) and regular cursor (tuple-like)
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

    def add_played_game(self, canonical_name: str, alternative_names: Optional[List[str]] = None, 
                       series_name: Optional[str] = None, genre: Optional[str] = None, 
                       release_year: Optional[int] = None, platform: Optional[str] = None, 
                       first_played_date: Optional[str] = None, completion_status: str = "unknown", 
                       total_episodes: int = 0, total_playtime_minutes: int = 0, 
                       youtube_playlist_url: Optional[str] = None, twitch_vod_urls: Optional[List[str]] = None, 
                       notes: Optional[str] = None) -> bool:
        """Add a played game to the database"""
        conn = self.get_connection()
        if not conn:
            return False
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO played_games (
                        canonical_name, alternative_names, series_name, genre,
                        release_year, platform, first_played_date, completion_status, total_episodes,
                        total_playtime_minutes, youtube_playlist_url, twitch_vod_urls, notes, 
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    canonical_name, 
                    alternative_names if alternative_names is not None else [], 
                    series_name,
                    genre,
                    release_year,
                    platform, 
                    first_played_date, 
                    completion_status, 
                    total_episodes,
                    total_playtime_minutes,
                    youtube_playlist_url, 
                    twitch_vod_urls if twitch_vod_urls is not None else [], 
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
                
                # Search canonical name first
                cur.execute("""
                    SELECT * FROM played_games 
                    WHERE LOWER(canonical_name) = %s
                """, (name_lower,))
                result = cur.fetchone()
                
                if result:
                    return dict(result)
                
                # Search alternative names
                cur.execute("""
                    SELECT * FROM played_games 
                    WHERE %s = ANY(SELECT LOWER(unnest(alternative_names)))
                """, (name_lower,))
                result = cur.fetchone()
                
                if result:
                    return dict(result)
                
                # Fuzzy search on canonical names
                cur.execute("SELECT * FROM played_games")
                all_games = cur.fetchall()
                
                import difflib
                canonical_names = []
                for game in all_games:
                    game_dict = dict(game)
                    canonical_name = game_dict.get('canonical_name')
                    if canonical_name:
                        canonical_names.append(str(canonical_name).lower())
                
                matches = difflib.get_close_matches(name_lower, canonical_names, n=1, cutoff=0.8)
                
                if matches:
                    match_name = matches[0]
                    for game in all_games:
                        game_dict = dict(game)
                        canonical_name = game_dict.get('canonical_name')
                        if canonical_name and str(canonical_name).lower() == match_name:
                            return game_dict
                
                return None
        except Exception as e:
            logger.error(f"Error getting played game {name}: {e}")
            return None
    
    def get_all_played_games(self, series_name: Optional[str] = None) -> List[Dict[str, Any]]:
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
                    'canonical_name', 'alternative_names', 'series_name',
                    'genre', 'release_year', 'platform', 'first_played_date', 'completion_status', 
                    'total_episodes', 'total_playtime_minutes', 'youtube_playlist_url', 
                    'twitch_vod_urls', 'notes'
                ]
                
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
                cur.execute("SELECT * FROM played_games WHERE id = %s", (game_id,))
                game = cur.fetchone()
                
                if game:
                    cur.execute("DELETE FROM played_games WHERE id = %s", (game_id,))
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
                cur.execute("""
                    SELECT * FROM played_games 
                    WHERE LOWER(canonical_name) LIKE %s 
                       OR LOWER(series_name) LIKE %s 
                       OR LOWER(notes) LIKE %s
                       OR %s = ANY(SELECT LOWER(unnest(alternative_names)))
                    ORDER BY 
                        CASE WHEN LOWER(canonical_name) = %s THEN 1 ELSE 2 END,
                        canonical_name ASC
                """, (query_lower, query_lower, query_lower, query.lower(), query.lower()))
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
    
    def bulk_import_played_games(self, games_data: List[Dict[str, Any]]) -> int:
        """Bulk import played games data with upsert logic (insert or update)"""
        conn = self.get_connection()
        if not conn:
            return 0
        
        try:
            with conn.cursor() as cur:
                imported_count = 0
                for game_data in games_data:
                    try:
                        canonical_name = game_data.get('canonical_name')
                        if not canonical_name:
                            continue
                        
                        # Check if game already exists
                        existing_game = self.get_played_game(canonical_name)
                        
                        if existing_game:
                            # Update existing game, preserving existing data where new data is empty
                            update_fields = {}
                            
                            # Only update fields that have new data or are empty in existing record
                            for field in ['alternative_names', 'series_name', 'genre', 'release_year', 
                                        'platform', 'first_played_date', 'completion_status', 
                                        'total_episodes', 'total_playtime_minutes', 'youtube_playlist_url', 
                                        'twitch_vod_urls', 'notes']:
                                new_value = game_data.get(field)
                                existing_value = existing_game.get(field)
                                
                                # Update if new value exists and either existing is empty/null or new has more data
                                if new_value is not None:
                                    if field == 'alternative_names' or field == 'twitch_vod_urls':
                                        # For arrays, merge unique values
                                        if isinstance(new_value, list) and isinstance(existing_value, list):
                                            merged = list(set(existing_value + new_value))
                                            if merged != existing_value:
                                                update_fields[field] = merged
                                        elif isinstance(new_value, list) and new_value:
                                            update_fields[field] = new_value
                                    elif field == 'total_episodes' or field == 'total_playtime_minutes':
                                        # For numeric fields, use the higher value
                                        if isinstance(new_value, int) and isinstance(existing_value, int):
                                            if new_value > existing_value:
                                                update_fields[field] = new_value
                                        elif isinstance(new_value, int) and new_value > 0:
                                            update_fields[field] = new_value
                                    elif field == 'notes':
                                        # For notes, append if different
                                        if isinstance(new_value, str) and new_value.strip():
                                            if not existing_value or new_value not in existing_value:
                                                if existing_value:
                                                    update_fields[field] = f"{existing_value} | {new_value}"
                                                else:
                                                    update_fields[field] = new_value
                                    else:
                                        # For other fields, update if existing is empty or new value is different
                                        if not existing_value or (new_value != existing_value and str(new_value).strip()):
                                            update_fields[field] = new_value
                            
                            # Apply updates if any
                            if update_fields:
                                self.update_played_game(existing_game['id'], **update_fields)
                                logger.info(f"Updated existing game: {canonical_name}")
                            
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
                        logger.error(f"Error importing game {game_data.get('canonical_name', 'unknown')}: {e}")
                        continue
                
                conn.commit()
                logger.info(f"Bulk imported/updated {imported_count} played games")
                return imported_count
        except Exception as e:
            logger.error(f"Error bulk importing played games: {e}")
            conn.rollback()
            return 0
    
    def get_last_channel_check(self, channel_type: str) -> Optional[str]:
        """Get the last time we checked a channel for new games (YouTube/Twitch)"""
        return self.get_config_value(f"last_{channel_type}_check")
    
    def set_last_channel_check(self, channel_type: str, timestamp: str):
        """Set the last time we checked a channel for new games"""
        self.set_config_value(f"last_{channel_type}_check", timestamp)
    
    def add_discovered_game(self, canonical_name: str, discovered_from: str, 
                           video_title: Optional[str] = None, video_url: Optional[str] = None,
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
            notes=notes
        )
    
    def update_game_episodes(self, canonical_name: str, new_episode_count: int) -> bool:
        """Update the episode count for a game"""
        game = self.get_played_game(canonical_name)
        if not game:
            return False
        
        return self.update_played_game(
            game['id'], 
            total_episodes=new_episode_count,
            completion_status="ongoing" if new_episode_count > 1 else "completed"
        )

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
    
    def get_games_by_franchise(self, franchise_name: str) -> List[Dict[str, Any]]:
        """Get all games in a specific franchise"""
        conn = self.get_connection()
        if not conn:
            return []
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM played_games 
                    WHERE LOWER(franchise_name) = %s
                    ORDER BY release_year ASC, canonical_name ASC
                """, (franchise_name.lower(),))
                results = cur.fetchall()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting games by franchise {franchise_name}: {e}")
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
                total_games = int(result['count']) if result else 0  # type: ignore
                
                # Completed vs ongoing
                cur.execute("SELECT completion_status, COUNT(*) as count FROM played_games GROUP BY completion_status")
                status_results = cur.fetchall()
                status_counts = {str(row['completion_status']): int(row['count']) for row in status_results} if status_results else {}  # type: ignore
                
                # Total episodes and playtime
                cur.execute("SELECT COALESCE(SUM(total_episodes), 0) as episodes, COALESCE(SUM(total_playtime_minutes), 0) as playtime FROM played_games")
                totals = cur.fetchone()
                total_episodes = int(totals['episodes']) if totals else 0  # type: ignore
                total_playtime = int(totals['playtime']) if totals else 0  # type: ignore
                
                # Genre distribution
                cur.execute("SELECT genre, COUNT(*) as count FROM played_games WHERE genre IS NOT NULL GROUP BY genre ORDER BY COUNT(*) DESC LIMIT 5")
                genre_results = cur.fetchall()
                top_genres = {str(row['genre']): int(row['count']) for row in genre_results} if genre_results else {}  # type: ignore
                
                # Series distribution (replacing franchise)
                cur.execute("SELECT series_name, COUNT(*) as count FROM played_games WHERE series_name IS NOT NULL GROUP BY series_name ORDER BY COUNT(*) DESC LIMIT 5")
                series_results = cur.fetchall()
                top_series = {str(row['series_name']): int(row['count']) for row in series_results} if series_results else {}  # type: ignore
                
                return {
                    'total_games': total_games,
                    'status_counts': status_counts,
                    'total_episodes': total_episodes,
                    'total_playtime_minutes': total_playtime,
                    'total_playtime_hours': round(total_playtime / 60, 1) if total_playtime > 0 else 0,
                    'top_genres': top_genres,
                    'top_series': top_series
                }
        except Exception as e:
            logger.error(f"Error getting played games stats: {e}")
            return {}

    def close(self):
        """Close database connection"""
        if self.connection and not self.connection.closed:
            self.connection.close()

# Global database manager instance
db = DatabaseManager()
