"""
Database Config Module - Bot Configuration & Announcements

This module handles:
- Key-value configuration storage
- Weekly announcement management (Monday/Friday)
- Announcement approval workflows
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, cast
from zoneinfo import ZoneInfo

from psycopg2.extras import RealDictRow

logger = logging.getLogger(__name__)


class ConfigDatabase:
    """
    Handles bot configuration and weekly announcements.

    This class manages persistent key-value configuration storage
    and the weekly announcement approval system.
    """

    def __init__(self, db_manager):
        """
        Initialize config database handler.

        Args:
            db_manager: DatabaseManager instance for connection access
        """
        self.db = db_manager

    def get_config_value(self, key: str) -> Optional[str]:
        """
        Get a configuration value by key.

        Args:
            key: Configuration key to retrieve

        Returns:
            Configuration value as string, or None if not found
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM bot_config WHERE key = %s", (key,))
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
        finally:
            if conn:
                conn.close()

    def set_config_value(self, key: str, value: str):
        """
        Set a configuration value.

        Uses INSERT ... ON CONFLICT to update existing keys or create new ones.

        Args:
            key: Configuration key
            value: Configuration value
        """
        conn = self.db.get_connection()
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
        finally:
            if conn:
                conn.close()

    def delete_config_value(self, key: str) -> bool:
        """
        Delete a configuration value by key.

        Args:
            key: Configuration key to delete

        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM bot_config WHERE key = %s", (key,))
                conn.commit()
                rows_deleted = cur.rowcount
                if rows_deleted > 0:
                    logger.info(f"Deleted config value: {key}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error deleting config value {key}: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def log_announcement(
            self,
            user_id: int,
            message: str,
            announcement_type: str = "general") -> bool:
        """
        Log announcement to database using config storage.

        Stores announcement metadata as a config value with timestamp.

        Args:
            user_id: Discord user ID who made the announcement
            message: Announcement message content
            announcement_type: Type of announcement (default: "general")

        Returns:
            True if successful, False otherwise
        """
        try:
            self.set_config_value(
                f"last_announcement_{announcement_type}",
                f"{user_id}|{message}|{datetime.now().isoformat()}")
            return True
        except Exception as e:
            logger.error(f"Error logging announcement: {e}")
            return False

    # --- Weekly Announcement System ---

    def create_weekly_announcement(self, day: str, content: str, cache: Dict[str, Any]) -> Optional[int]:
        """
        Create a new weekly announcement record for approval.

        This creates a pending announcement (Monday/Friday) that moderators
        can review and approve before posting.

        Args:
            day: Day of announcement ('monday' or 'friday')
            content: Generated announcement content
            cache: Analysis cache data (stats, metrics, etc.)

        Returns:
            Announcement ID if successful, None otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Clean up any old pending messages for that day first
                cur.execute(
                    "DELETE FROM weekly_announcements WHERE day = %s AND status = 'pending_approval'",
                    (day,)
                )

                # Ensure newlines are preserved in content
                preserved_content = content

                cur.execute("""
                    INSERT INTO weekly_announcements (day, generated_content, analysis_cache)
                    VALUES (%s, %s, %s) RETURNING id
                """, (day, preserved_content, json.dumps(cache)))

                result = cur.fetchone()
                conn.commit()

                if result:
                    announcement_id = cast(RealDictRow, result)['id']
                    logger.info(f"Created weekly announcement record {announcement_id} for {day.title()}.")
                    return announcement_id
                return None

        except Exception as e:
            logger.error(f"Error creating weekly announcement: {e}")
            conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def get_announcement_by_day(self, day: str, status: str) -> Optional[Dict[str, Any]]:
        """
        Get a weekly announcement for a specific day and status.

        Args:
            day: Day to retrieve ('monday' or 'friday')
            status: Announcement status ('pending_approval', 'approved', 'rejected', 'posted')

        Returns:
            Announcement data dict, or None if not found
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM weekly_announcements
                    WHERE day = %s AND status = %s
                    ORDER BY created_at DESC LIMIT 1
                """, (day, status))

                result = cur.fetchone()
                if result:
                    return dict(result)
                return None

        except Exception as e:
            logger.error(f"Error getting weekly announcement for {day}: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_announcement_status(
            self,
            announcement_id: int,
            status: str,
            new_content: Optional[str] = None) -> bool:
        """
        Update the status and optionally the content of a weekly announcement.

        Args:
            announcement_id: ID of announcement to update
            status: New status ('approved', 'rejected', 'posted')
            new_content: Optional new content (if moderator edited it)

        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))

                if new_content:
                    cur.execute("""
                        UPDATE weekly_announcements
                        SET status = %s, generated_content = %s, approved_at = %s
                        WHERE id = %s
                    """, (status, new_content, uk_now, announcement_id))
                else:
                    cur.execute("""
                        UPDATE weekly_announcements
                        SET status = %s, approved_at = %s
                        WHERE id = %s
                    """, (status, uk_now, announcement_id))

                conn.commit()
                rows_affected = cur.rowcount

                if rows_affected > 0:
                    logger.info(f"Updated announcement {announcement_id} to status '{status}'")
                    return True
                else:
                    logger.warning(f"No announcement found with ID {announcement_id}")
                    return False

        except Exception as e:
            logger.error(f"Error updating announcement status: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
