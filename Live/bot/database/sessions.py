"""
Database Sessions Module - Approval & Review Workflows

This module handles:
- Trivia approval sessions (persistent across bot restarts)
- Game review sessions (low-confidence match reviews)
- Session cleanup and expiration
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class SessionDatabase:
    """
    Handles approval sessions and game review workflows.
    
    This class manages persistent conversation sessions that survive
    bot restarts, allowing moderators to continue approval flows.
    """

    def __init__(self, db_manager):
        """
        Initialize session database handler.
        
        Args:
            db_manager: DatabaseManager instance for connection access
        """
        self.db = db_manager

    # --- Trivia Approval Sessions ---

    def _insert_approval_session(
            self,
            cur,
            user_id: int,
            session_type: str,
            conversation_step: str,
            question_data: Dict[str, Any],
            conversation_data: Optional[Dict[str, Any]],
            uk_now,
            expires_at
    ) -> Optional[int]:
        """Helper method to insert approval session (reduces duplication)"""
        cur.execute("""
            INSERT INTO trivia_approval_sessions (
                user_id, session_type, conversation_step, question_data,
                conversation_data, created_at, last_activity, expires_at, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
            RETURNING id
        """, (
            user_id, session_type, conversation_step,
            json.dumps(question_data),
            json.dumps(conversation_data or {}),
            uk_now, uk_now, expires_at
        ))

        result = cur.fetchone()
        if result:
            # Use column name access for RealDictCursor compatibility
            try:
                return int(result['id'])  # type: ignore
            except (TypeError, KeyError):
                return int(result[0])  # Fallback to index access
        return None

    def create_approval_session(
            self,
            user_id: int,
            session_type: str,
            conversation_step: str,
            question_data: Dict[str, Any],
            conversation_data: Optional[Dict[str, Any]] = None,
            timeout_minutes: int = 180  # 3 hours default
    ) -> Optional[int]:
        """
        Create a new persistent approval session.
        
        Approval sessions survive bot restarts and allow moderators to
        continue approval workflows across disconnections.
        
        Args:
            user_id: Discord user ID
            session_type: Type of session (e.g., 'question_approval')
            conversation_step: Current step in the workflow
            question_data: Data being approved (question details)
            conversation_data: Additional conversation state
            timeout_minutes: Session expiration timeout (default: 180 minutes)
            
        Returns:
            Session ID if successful, None otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            logger.error("Failed to create approval session: No database connection")
            return None

        uk_now = datetime.now(ZoneInfo("Europe/London"))
        expires_at = uk_now + timedelta(minutes=timeout_minutes)

        try:
            with conn.cursor() as cur:
                logger.info(f"Creating approval session for user {user_id}, type: {session_type}")

                session_id = self._insert_approval_session(
                    cur, user_id, session_type, conversation_step,
                    question_data, conversation_data, uk_now, expires_at
                )

                if session_id:
                    conn.commit()
                    logger.info(f"✅ Successfully created persistent approval session {session_id} for user {user_id}")
                    return session_id
                else:
                    logger.error(f"❌ Failed to create approval session: INSERT returned no result")
                    return None

        except Exception as e:
            logger.error(f"❌ Error creating approval session - Exception type: {type(e).__name__}")
            logger.error(f"❌ Error creating approval session - Message: {str(e)}")
            logger.error(f"❌ Error creating approval session - User ID: {user_id}, Session type: {session_type}")

            # Check if this is a sequence synchronization issue
            error_str = str(e).lower()
            if "duplicate key value violates unique constraint" in error_str and "pkey" in error_str:
                logger.error("🔧 DETECTED: Primary key constraint violation - likely sequence synchronization issue")
                logger.info("🔄 Attempting automatic sequence repair...")

                # Attempt sequence repair
                repair_result = self.db.repair_database_sequences()
                if repair_result.get("total_repaired", 0) > 0:
                    logger.info(f"✅ Repaired {repair_result['total_repaired']} sequences, retrying session creation...")

                    # Retry using the helper method
                    try:
                        with conn.cursor() as retry_cur:
                            session_id = self._insert_approval_session(
                                retry_cur, user_id, session_type, conversation_step,
                                question_data, conversation_data, uk_now, expires_at
                            )

                            if session_id:
                                conn.commit()
                                logger.info(
                                    f"✅ Successfully created approval session {session_id} after sequence repair")
                                return session_id
                            else:
                                logger.error("❌ Retry after sequence repair also failed")
                    except Exception as retry_error:
                        logger.error(f"❌ Retry after sequence repair failed: {retry_error}")
                else:
                    logger.error("❌ Sequence repair found no issues to fix")

            conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def get_approval_session(self, user_id: int, session_type: str = 'question_approval') -> Optional[Dict[str, Any]]:
        """
        Get active approval session for user.
        
        Args:
            user_id: Discord user ID
            session_type: Session type to retrieve
            
        Returns:
            Session data dict with parsed JSON fields, or None if not found
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM trivia_approval_sessions
                    WHERE user_id = %s
                    AND session_type = %s
                    AND status = 'active'
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id, session_type))

                result = cur.fetchone()
                if result:
                    session_dict = dict(result)
                    # Parse JSON fields
                    session_dict['question_data'] = json.loads(session_dict['question_data'])
                    session_dict['conversation_data'] = json.loads(session_dict['conversation_data'])
                    return session_dict

                return None

        except Exception as e:
            logger.error(f"Error getting approval session for user {user_id}: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_approval_session(
            self,
            session_id: int,
            conversation_step: Optional[str] = None,
            question_data: Optional[Dict[str, Any]] = None,
            conversation_data: Optional[Dict[str, Any]] = None,
            increment_restart_count: bool = False
    ) -> bool:
        """
        Update approval session data and activity.
        
        Args:
            session_id: Session ID to update
            conversation_step: New conversation step
            question_data: Updated question data
            conversation_data: Updated conversation data
            increment_restart_count: Whether to increment restart counter
            
        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))

                # Build update query dynamically
                set_clauses = ["last_activity = %s"]
                params = [uk_now]

                if conversation_step is not None:
                    set_clauses.append("conversation_step = %s")
                    params.append(conversation_step)  # type: ignore

                if question_data is not None:
                    set_clauses.append("question_data = %s")
                    params.append(json.dumps(question_data))  # type: ignore

                if conversation_data is not None:
                    set_clauses.append("conversation_data = %s")
                    params.append(json.dumps(conversation_data))  # type: ignore

                if increment_restart_count:
                    set_clauses.append("bot_restart_count = bot_restart_count + 1")

                params.append(session_id)  # type: ignore

                query = f"""
                    UPDATE trivia_approval_sessions
                    SET {', '.join(set_clauses)}
                    WHERE id = %s AND status = 'active'
                """

                cur.execute(query, params)
                conn.commit()

                success = cur.rowcount > 0
                if success:
                    logger.info(f"Updated approval session {session_id}")
                return success

        except Exception as e:
            logger.error(f"Error updating approval session {session_id}: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def complete_approval_session(self, session_id: int, status: str = 'completed') -> bool:
        """
        Mark approval session as completed or cancelled.
        
        Args:
            session_id: Session ID to complete
            status: Final status ('completed', 'cancelled', 'expired')
            
        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE trivia_approval_sessions
                    SET status = %s, last_activity = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (status, session_id))

                conn.commit()
                success = cur.rowcount > 0
                if success:
                    logger.info(f"Completed approval session {session_id} with status: {status}")
                return success

        except Exception as e:
            logger.error(f"Error completing approval session {session_id}: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def get_all_active_approval_sessions(self) -> List[Dict[str, Any]]:
        """
        Get all active approval sessions (for restoration on startup).
        
        Used when bot restarts to restore in-progress approval workflows.
        
        Returns:
            List of session dicts with parsed JSON fields
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM trivia_approval_sessions
                    WHERE status = 'active'
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at ASC
                """)

                results = cur.fetchall()
                sessions = []
                for row in results:
                    session_dict = dict(row)
                    # Parse JSON fields
                    session_dict['question_data'] = json.loads(session_dict['question_data'])
                    session_dict['conversation_data'] = json.loads(session_dict['conversation_data'])
                    sessions.append(session_dict)

                return sessions

        except Exception as e:
            logger.error(f"Error getting active approval sessions: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def cleanup_expired_approval_sessions(self) -> int:
        """
        Clean up expired approval sessions.
        
        Marks expired sessions as 'expired' status for tracking purposes.
        
        Returns:
            Number of sessions cleaned up
        """
        conn = self.db.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE trivia_approval_sessions
                    SET status = 'expired'
                    WHERE status = 'active'
                    AND expires_at <= CURRENT_TIMESTAMP
                """)

                conn.commit()
                expired_count = cur.rowcount
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired approval sessions")
                return expired_count

        except Exception as e:
            logger.error(f"Error cleaning up expired approval sessions: {e}")
            conn.rollback()
            return 0
        finally:
            if conn:
                conn.close()

    # --- Game Review Sessions ---

    def create_game_review_session(
        self,
        user_id: int,
        original_title: str,
        extracted_name: str,
        confidence_score: float,
        alternative_names: List[str],
        source: str,
        igdb_data: Dict[str, Any],
        video_url: Optional[str] = None,
        timeout_hours: int = 24
    ) -> Optional[int]:
        """
        Create a new game review session for low-confidence matches.
        
        When automatic game matching has low confidence, this creates
        a review session for moderators to approve/reject the match.
        
        Args:
            user_id: Discord user ID (moderator)
            original_title: Original video/VOD title
            extracted_name: Extracted game name
            confidence_score: Match confidence (0.0-1.0)
            alternative_names: List of alternative names found
            source: Source platform ('youtube' or 'twitch')
            igdb_data: IGDB API data for the match
            video_url: Optional URL to video/VOD
            timeout_hours: Session expiration (default: 24 hours)
            
        Returns:
            Session ID if successful, None otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))
                expires_at = uk_now + timedelta(hours=timeout_hours)

                # Convert alternative names list to comma-separated string
                alt_names_str = ','.join(alternative_names) if alternative_names else ''

                cur.execute("""
                    INSERT INTO game_review_sessions (
                        user_id, original_title, extracted_name, confidence_score,
                        alternative_names, source, igdb_data, video_url,
                        conversation_step, created_at, last_activity, expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    user_id, original_title, extracted_name, confidence_score,
                    alt_names_str, source, json.dumps(igdb_data), video_url,
                    'review', uk_now, uk_now, expires_at
                ))

                result = cur.fetchone()
                conn.commit()

                if result:
                    session_id = int(result['id'])  # type: ignore
                    logger.info(f"Created game review session {session_id} for user {user_id}")
                    return session_id
                return None
                
        except Exception as e:
            logger.error(f"Error creating game review session: {e}")
            conn.rollback()
            return None
        finally:
            if conn:
                conn.close()

    def get_game_review_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get active game review session for user.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Session data dict with parsed JSON and list fields, or None
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM game_review_sessions
                    WHERE user_id = %s
                    AND status = 'pending'
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at ASC
                    LIMIT 1
                """, (user_id,))

                result = cur.fetchone()
                if result:
                    session_dict = dict(result)
                    # Parse JSON and convert alternative_names back to list
                    session_dict['igdb_data'] = json.loads(session_dict.get('igdb_data', '{}'))
                    session_dict['conversation_data'] = json.loads(session_dict.get('conversation_data', '{}'))
                    alt_names = session_dict.get('alternative_names', '')
                    session_dict['alternative_names'] = self.db._parse_comma_separated_list(alt_names) if alt_names else []
                    return session_dict
                return None
                
        except Exception as e:
            logger.error(f"Error getting game review session for user {user_id}: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_game_review_session(
        self,
        session_id: int,
        conversation_step: Optional[str] = None,
        conversation_data: Optional[Dict[str, Any]] = None,
        approved_name: Optional[str] = None,
        approved_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update game review session.
        
        Args:
            session_id: Session ID to update
            conversation_step: New conversation step
            conversation_data: Updated conversation data
            approved_name: Approved game name (if review complete)
            approved_data: Approved game data (if review complete)
            
        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                uk_now = datetime.now(ZoneInfo("Europe/London"))

                set_clauses = ["last_activity = %s"]
                params: List[Any] = [uk_now]

                if conversation_step:
                    set_clauses.append("conversation_step = %s")
                    params.append(conversation_step)

                if conversation_data:
                    set_clauses.append("conversation_data = %s")
                    params.append(json.dumps(conversation_data))

                if approved_name:
                    set_clauses.append("approved_name = %s")
                    params.append(approved_name)

                if approved_data:
                    set_clauses.append("approved_data = %s")
                    params.append(json.dumps(approved_data))

                params.append(session_id)

                query = f"""
                    UPDATE game_review_sessions
                    SET {', '.join(set_clauses)}
                    WHERE id = %s AND status = 'pending'
                """

                cur.execute(query, params)
                conn.commit()

                return cur.rowcount > 0
                
        except Exception as e:
            logger.error(f"Error updating game review session {session_id}: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def complete_game_review_session(self, session_id: int, status: str = 'approved') -> bool:
        """
        Complete game review session with final status.
        
        Args:
            session_id: Session ID to complete
            status: Final status ('approved', 'rejected', 'cancelled')
            
        Returns:
            True if successful, False otherwise
        """
        conn = self.db.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE game_review_sessions
                    SET status = %s, last_activity = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (status, session_id))

                conn.commit()
                success = cur.rowcount > 0
                if success:
                    logger.info(f"Completed game review session {session_id} with status: {status}")
                return success
                
        except Exception as e:
            logger.error(f"Error completing game review session {session_id}: {e}")
            conn.rollback()
            return False
        finally:
            if conn:
                conn.close()

    def get_pending_game_reviews(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get all pending game review sessions for a user.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            List of pending review session dicts
        """
        conn = self.db.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM game_review_sessions
                    WHERE user_id = %s
                    AND status = 'pending'
                    AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at ASC
                """, (user_id,))

                results = cur.fetchall()
                sessions = []
                for row in results:
                    session_dict = dict(row)
                    session_dict['igdb_data'] = json.loads(session_dict.get('igdb_data', '{}'))
                    session_dict['conversation_data'] = json.loads(session_dict.get('conversation_data', '{}'))
                    alt_names = session_dict.get('alternative_names', '')
                    session_dict['alternative_names'] = self.db._parse_comma_separated_list(alt_names) if alt_names else []
                    sessions.append(session_dict)
                return sessions
                
        except Exception as e:
            logger.error(f"Error getting pending game reviews for user {user_id}: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def cleanup_expired_game_review_sessions(self) -> int:
        """
        Clean up expired game review sessions.
        
        Returns:
            Number of sessions cleaned up
        """
        conn = self.db.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE game_review_sessions
                    SET status = 'expired'
                    WHERE status = 'pending'
                    AND expires_at <= CURRENT_TIMESTAMP
                """)

                conn.commit()
                expired_count = cur.rowcount
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired game review sessions")
                return expired_count

        except Exception as e:
            logger.error(f"Error cleaning up expired game review sessions: {e}")
            conn.rollback()
            return 0
        finally:
            if conn:
                conn.close()
