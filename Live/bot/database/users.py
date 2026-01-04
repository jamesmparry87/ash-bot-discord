"""
Database Users Module - User Management

This module handles:
- Strike system (user moderation tracking)
- Reminders (user-scheduled reminders with auto-actions)
- Game recommendations (community submissions)
"""

import difflib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class UserDatabase:
    """
    Handles user management: strikes, reminders, and game recommendations.

    This class manages user-related data including moderation strikes,
    scheduled reminders with optional auto-actions, and community game
    recommendation submissions.
    """

    def __init__(self, db_manager):
        """
        Initialize user database handler.

        Args:
            db_manager: DatabaseManager instance for connection access
        """
        self.db = db_manager

    # --- Strike System ---

    def get_user_strikes(self, user_id: int) -> int:
        """
        Get strike count for a user.

        Args:
            user_id: Discord user ID

        Returns:
            Strike count (0 if user has no strikes)
        """
        conn = self.db.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT strike_count FROM strikes WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                if result:
                    # Handle both RealDictCursor (dict-like) and regular cursor (tuple-like)
                    try:
                        return int(result['strike_count'])  # type: ignore
                    except (TypeError, KeyError):
                        return int(result[0])  # type: ignore  # Fallback to index access
                return 0
        except Exception as e:
            logger.error(f"Error getting strikes for user {user_id}: {e}")
            return 0
        finally:
            if conn:
                conn.close()

    def set_user_strikes(self, user_id: int, count: int):
        """
        Set strike count for a user.

        Uses INSERT ... ON CONFLICT to update existing records or create new ones.

        Args:
            user_id: Discord user ID
            count: New strike count
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def add_user_strike(self, user_id: int) -> int:
        """
        Add a strike to a user and return new count.

        Args:
            user_id: Discord user ID

        Returns:
            New strike count after addition
        """
        current_strikes = self.get_user_strikes(user_id)
        new_count = current_strikes + 1
        self.set_user_strikes(user_id, new_count)
        return new_count

    def get_all_strikes(self) -> Dict[int, int]:
        """
        Get all users with strikes.

        Returns:
            Dict mapping user_id to strike_count for all users with strikes > 0
        """
        conn = self.db.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, strike_count FROM strikes WHERE strike_count > 0")
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
        finally:
            if conn:
                conn.close()

    def bulk_import_strikes(self, strikes_data: Dict[int, int]) -> int:
        """
        Bulk import strike data.

        Args:
            strikes_data: Dict mapping user_id to strike_count

        Returns:
            Number of records imported
        """
        conn = self.db.get_connection()
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
                    logger.info(f"Bulk imported {len(data_tuples)} strike records")
                    return len(data_tuples)
                return 0
        except Exception as e:
            logger.error(f"Error bulk importing strikes: {e}")
            conn.rollback()
            return 0
        finally:
            if conn:
                conn.close()

    def clear_all_strikes(self):
        """Clear all strikes (use with caution)."""
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    # --- Reminder System ---

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
        """
        Add a reminder to the database.

        Args:
            user_id: Discord user ID
            reminder_text: Reminder message
            scheduled_time: When to deliver (datetime or ISO string)
            delivery_channel_id: Optional channel ID for delivery
            delivery_type: 'dm' or 'channel'
            auto_action_enabled: Whether to execute auto-action after delivery
            auto_action_type: Type of auto-action (e.g., 'start_trivia')
            auto_action_data: Additional data for auto-action

        Returns:
            Reminder ID if successful, None otherwise
        """
        conn = self.db.get_connection()
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
                    logger.info(f"Added reminder ID {reminder_id} for user {user_id}")
                    return reminder_id
                return None
        except Exception as e:
            logger.error(f"Error adding reminder: {e}")
            conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def get_user_reminders(self, user_id: int, status: str = "pending") -> List[Dict[str, Any]]:
        """
        Get all reminders for a user.

        Args:
            user_id: Discord user ID
            status: Reminder status filter ('pending', 'delivered', etc.)

        Returns:
            List of reminder dicts
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def get_due_reminders(self, current_time) -> List[Dict[str, Any]]:
        """
        Get all reminders that are due for delivery.

        Args:
            current_time: Current datetime to compare against

        Returns:
            List of due reminder dicts
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def update_reminder_status(
        self,
        reminder_id: int,
        status: str,
        delivered_at: Optional[Any] = None,  # Can be datetime or str
        auto_executed_at: Optional[Any] = None,  # Can be datetime or str
    ) -> bool:
        """
        Update reminder status.

        Args:
            reminder_id: Reminder ID to update
            status: New status ('delivered', 'cancelled', 'auto_completed', etc.)
            delivered_at: Optional delivery timestamp
            auto_executed_at: Optional auto-action execution timestamp

        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def cancel_user_reminder(self, reminder_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Cancel a reminder (only if it belongs to the user).

        Args:
            reminder_id: Reminder ID to cancel
            user_id: Discord user ID (must match reminder owner)

        Returns:
            Cancelled reminder dict if successful, None otherwise
        """
        conn = self.db.get_connection()
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
                    logger.info(f"Cancelled reminder ID {reminder_id} for user {user_id}")
                    return dict(reminder)

                return None
        except Exception as e:
            logger.error(f"Error cancelling reminder: {e}")
            conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def get_reminders_awaiting_auto_action(self, current_time) -> List[Dict[str, Any]]:
        """
        Get reminders that are past delivery time and waiting for auto-action.

        Auto-actions execute 5 minutes after reminder delivery.

        Args:
            current_time: Current datetime

        Returns:
            List of reminders ready for auto-action
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                # Calculate 5 minutes ago from current time
                five_minutes_ago = current_time - timedelta(minutes=5)
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
        finally:
            if conn:
                conn.close()

    def get_all_pending_reminders(self) -> List[Dict[str, Any]]:
        """
        Get all pending reminders for moderator management.

        Returns:
            List of all pending reminder dicts
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def get_pending_reminders_for_user(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get pending reminders for a specific user.

        Args:
            user_id: Discord user ID

        Returns:
            List of pending reminder dicts for the user
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def get_reminder_by_id(self, reminder_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific reminder by ID.

        Args:
            reminder_id: Reminder ID

        Returns:
            Reminder dict if found, None otherwise
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    async def cancel_reminder(self, reminder_id: int) -> bool:
        """
        Cancel a reminder by ID (admin version - no user restriction).

        Args:
            reminder_id: Reminder ID to cancel

        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    # --- Game Recommendations ---

    def add_game_recommendation(self, name: str, reason: str, added_by: str) -> bool:
        """
        Add a game recommendation.

        Args:
            name: Game name
            reason: Why user recommends it
            added_by: Discord username who recommended

        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def get_all_games(self) -> List[Dict[str, Any]]:
        """
        Get all game recommendations.

        Returns:
            List of game recommendation dicts
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def remove_game_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        """
        Remove game by index (1-based).

        Args:
            index: 1-based index in the list

        Returns:
            Removed game dict if successful, None otherwise
        """
        games = self.get_all_games()
        if not games or index < 1 or index > len(games):
            return None

        game_to_remove = games[index - 1]
        return self.remove_game_by_id(game_to_remove['id'])

    def remove_game_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Remove game by name (fuzzy match).

        Args:
            name: Game name (will try fuzzy matching)

        Returns:
            Removed game dict if successful, None otherwise
        """
        games = self.get_all_games()
        name_lower = name.lower().strip()

        # Try exact match first
        for game in games:
            if game['name'].lower().strip() == name_lower:
                return self.remove_game_by_id(game['id'])

        # Try fuzzy match
        game_names = [game['name'].lower() for game in games]
        matches = difflib.get_close_matches(name_lower, game_names, n=1, cutoff=0.8)

        if matches:
            match_name = matches[0]
            for game in games:
                if game['name'].lower() == match_name:
                    return self.remove_game_by_id(game['id'])

        return None

    def remove_game_by_id(self, game_id: int) -> Optional[Dict[str, Any]]:
        """
        Remove game by database ID.

        Args:
            game_id: Game recommendation ID

        Returns:
            Removed game dict if successful, None otherwise
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def game_exists(self, name: str) -> bool:
        """
        Check if a game recommendation already exists (fuzzy match).

        Args:
            name: Game name to check

        Returns:
            True if exists, False otherwise
        """
        games = self.get_all_games()
        name_lower = name.lower().strip()

        # Check exact matches
        existing_names = [game['name'].lower().strip() for game in games]
        if name_lower in existing_names:
            return True

        # Check fuzzy matches
        matches = difflib.get_close_matches(name_lower, existing_names, n=1, cutoff=0.85)
        return len(matches) > 0

    def bulk_import_games(self, games_data: List[Dict[str, str]]) -> int:
        """
        Bulk import game recommendations.

        Args:
            games_data: List of dicts with 'name', 'reason', 'added_by'

        Returns:
            Number of games imported
        """
        conn = self.db.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                # Prepare data for batch insert
                data_tuples = [
                    (game["name"], game["reason"], game["added_by"])
                    for game in games_data
                ]

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
        finally:
            if conn:
                conn.close()

    def clear_all_games(self):
        """Clear all game recommendations (use with caution)."""
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()
