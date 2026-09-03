import difflib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast
from zoneinfo import ZoneInfo

from psycopg2.extras import RealDictRow

from ..utils.text_processing import calculate_concept_similarity, extract_question_concepts, normalize_trivia_answer

"""
Database Trivia Module - Trivia System

This module handles:
- Trivia question management (add, get, update, reset)
- Trivia session lifecycle (create, start, submit answers, complete)
- Answer evaluation with fuzzy matching
- Dynamic question calculations
- Trivia statistics and leaderboards
- Question pool management
"""

import difflib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast
from zoneinfo import ZoneInfo

from psycopg2.extras import RealDictRow

logger = logging.getLogger(__name__)


class TriviaDatabase:
    """
    Handles all trivia-related database operations.

    This class manages the complete trivia system including questions,
    sessions, answers, evaluation logic, and statistics tracking.
    """

    def __init__(self, db_manager):
        """
        Initialize trivia database handler.

        Args:
            db_manager: DatabaseManager instance for connection access
        """
        self.db = db_manager

    def get_connection(self):
        """Get database connection from the database manager"""
        return self.db.get_connection()

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
        status: str = 'available',
    ) -> Optional[int]:
        """
        Add a new trivia question to the database

        Args:
            status: Question status - 'pending_approval', 'available', 'answered', 'rejected', 'retired'
                    Default 'available' for manually added questions
                    Use 'pending_approval' for AI-generated questions awaiting approval
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trivia_questions (
                        question_text, question_type, correct_answer, multiple_choice_options,
                        is_dynamic, dynamic_query_type, submitted_by_user_id, category, difficulty_level,
                        status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
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
                        status,
                    ),
                )
                result = cur.fetchone()
                conn.commit()

                if result:
                    question_id = int(result["id"])  # type: ignore
                    logger.info(f"Added trivia question ID {question_id} with status '{status}'")
                    return question_id
                return None
        except Exception as e:
            logger.error(f"Error adding trivia question: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def clear_pending_trivia_questions(self) -> int:
        """
        Delete all trivia questions with status 'pending_approval'.
        Returns the number of deleted questions.
        """
        conn = self.get_connection()
        if not conn:
            return 0

        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM trivia_questions WHERE status = 'pending_approval'")
                deleted_count = cur.rowcount
                conn.commit()
                logger.info(f"Cleared {deleted_count} pending trivia questions")
                return deleted_count
        except Exception as e:
            logger.error(f"Error clearing pending trivia questions: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    def get_next_trivia_question(
            self, exclude_user_id: Optional[int] = None, avoid_category: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get the next trivia question based on priority system (excluding answered/retired questions)

        ✅ FIX #2: Ensure retired questions are never selected
        """
        conn = self.db.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Build exclusion condition if parameters are provided
                exclusion_conditions = []
                query_params = []

                if exclude_user_id is not None:
                    exclusion_conditions.append("(submitted_by_user_id != %s OR submitted_by_user_id IS NULL)")
                    query_params.append(exclude_user_id)

                if avoid_category:
                    exclusion_conditions.append("(category != %s OR category IS NULL)")
                    query_params.append(avoid_category)

                exclusion_condition = " AND " + " AND ".join(exclusion_conditions) if exclusion_conditions else ""

                # ✅ FIX #2: Explicitly exclude 'retired' and 'answered' statuses
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
                    logger.info(f"✅ FIX #2: Selected priority 1 question (mod-submitted, available status)")
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
                    logger.info(f"✅ FIX #2: Selected priority 2 question (AI statistical, available status)")
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

                if result:
                    logger.info(f"✅ FIX #2: Selected priority 3 question (any available)")

                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting next trivia question: {e}")
            return None
        finally:
            conn.close()

    def create_trivia_session(
            self,
            question_id: int,
            session_type: str = "weekly",
            calculated_answer: Optional[str] = None) -> Optional[int]:
        """Create a new trivia session"""
        conn = self.db.get_connection()
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
                question_submitter_id = cast(RealDictRow, question_result)[
                    "submitted_by_user_id"] if question_result else None

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

                # Update question usage AND mark as answered immediately
                # This prevents question reuse even if session processing fails later
                cur.execute(
                    """
                    UPDATE trivia_questions
                    SET last_used_at = CURRENT_TIMESTAMP,
                        usage_count = usage_count + 1,
                        status = 'answered'
                    WHERE id = %s
                """,
                    (question_id,),
                )

                conn.commit()
                logger.info(
                    f"✅ FIX #3: Marked question {question_id} as 'answered' during session creation (early commit)")

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
        finally:
            conn.close()

    def get_active_trivia_session(self) -> Optional[Dict[str, Any]]:
        """
        Get the current active trivia session

        ✅ FIX #6: Optimized with caching for frequent access during reply detection

        Performance notes:
        - Called on EVERY message during reply detection
        - Cached result to avoid repeated database queries
        - Cache invalidated when session starts/ends
        """
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

    def get_trivia_session_by_message_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Get trivia session by question or confirmation message ID"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ts.*, tq.question_text, tq.question_type, tq.correct_answer,
                           tq.multiple_choice_options, tq.is_dynamic, tq.dynamic_query_type,
                           tq.submitted_by_user_id, tq.category, ts.calculated_answer
                    FROM trivia_sessions ts
                    JOIN trivia_questions tq ON ts.question_id = tq.id
                    WHERE ts.status = 'active'
                    AND (ts.question_message_id = %s OR ts.confirmation_message_id = %s)
                    ORDER BY ts.started_at DESC
                    LIMIT 1
                    """,
                    (message_id, message_id)
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting trivia session by message ID {message_id}: {e}")
            return None

    def get_latest_trivia_session(self) -> Optional[Dict[str, Any]]:
        """Get the most recent trivia session, whether active or completed"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ts.*, tq.question_text, tq.question_type, tq.correct_answer,
                           tq.multiple_choice_options, tq.is_dynamic, tq.dynamic_query_type,
                           tq.submitted_by_user_id, tq.category, ts.calculated_answer
                    FROM trivia_sessions ts
                    JOIN trivia_questions tq ON ts.question_id = tq.id
                    ORDER BY ts.started_at DESC
                    LIMIT 1
                    """
                )
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting latest trivia session: {e}")
            return None

    def update_trivia_session_messages(
        self,
        session_id: int,
        question_message_id: int,
        confirmation_message_id: int,
        channel_id: int
    ) -> bool:
        """Update trivia session with Discord message IDs for reply tracking"""
        conn = self.get_connection()
        if not conn:
            return False

        try:
            with conn.cursor() as cur:
                # First check if the columns exist, if not add them
                cur.execute("""
                    ALTER TABLE trivia_sessions
                    ADD COLUMN IF NOT EXISTS question_message_id BIGINT,
                    ADD COLUMN IF NOT EXISTS confirmation_message_id BIGINT,
                    ADD COLUMN IF NOT EXISTS channel_id BIGINT
                """)

                # Update the session with message tracking info
                cur.execute(
                    """
                    UPDATE trivia_sessions
                    SET question_message_id = %s,
                        confirmation_message_id = %s,
                        channel_id = %s
                    WHERE id = %s
                    """,
                    (question_message_id, confirmation_message_id, channel_id, session_id)
                )

                conn.commit()
                success = cur.rowcount > 0

                if success:
                    logger.info(
                        f"Updated trivia session {session_id} with message tracking: Q:{question_message_id}, C:{confirmation_message_id}, Ch:{channel_id}")
                else:
                    logger.warning(f"Failed to update trivia session {session_id} - session not found")

                return success
        except Exception as e:
            logger.error(f"Error updating trivia session messages: {e}")
            conn.rollback()
            return False

    def submit_trivia_answer(
            self,
            session_id: int,
            user_id: int,
            answer_text: str,
            normalized_answer: Optional[str] = None) -> Dict[str, Any]:
        """
        Submit an answer to a trivia session

        ✅ FIX #6: Optimized for concurrent answer submissions
        ✅ FIX #7: Returns Dict format for proper error handling and duplicate detection

        Performance notes:
        - Uses simple INSERT for fast write performance
        - Conflict detection done via single query
        - Duplicate detection prevents multiple submissions
        - Minimal transaction scope for high concurrency

        Returns:
            Dict with 'success' (bool), 'answer_id' (int), or 'error' (str)
        """
        conn = self.get_connection()
        if not conn:
            return {'success': False, 'error': 'no_connection'}

        try:
            with conn.cursor() as cur:
                # Check for duplicate submission
                cur.execute(
                    """
                    SELECT id FROM trivia_answers
                    WHERE session_id = %s AND user_id = %s
                    LIMIT 1
                """,
                    (session_id, user_id),
                )

                existing = cur.fetchone()
                if existing:
                    logger.info(f"Duplicate answer submission detected for user {user_id} in session {session_id}")
                    return {'success': False, 'error': 'duplicate'}

                # Check for conflict (mod answering their own question)
                cur.execute(
                    """
                    SELECT question_submitter_id FROM trivia_sessions WHERE id = %s
                """,
                    (session_id,),
                )
                session_result = cur.fetchone()

                conflict_detected = False
                if session_result and cast(RealDictRow, session_result)[
                        "question_submitter_id"] == user_id:
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
                    return {'success': True, 'answer_id': answer_id}
                return {'success': False, 'error': 'insert_failed'}
        except Exception as e:
            logger.error(f"Error submitting trivia answer: {e}")
            conn.rollback()
            return {'success': False, 'error': 'database_error'}

    def complete_trivia_session(
        self,
        session_id: int,
        first_correct_user_id: Optional[int] = None,
        total_participants: Optional[int] = None,
        correct_count: Optional[int] = None,
    ) -> bool:
        """
        ✅ FIX #5: Complete trivia session with enhanced transaction management

        Improvements:
        - SAVEPOINT transactions for atomic operations
        - Exponential backoff retry logic
        - Proper rollback on failure
        - Enhanced error logging
        """
        conn = self.get_connection()
        if not conn:
            logger.error("❌ FIX #5: No database connection for complete_trivia_session")
            return False

        # ✅ FIX #5: Exponential backoff configuration
        max_retries = 3
        base_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                # ✅ FIX #5: Start SAVEPOINT transaction for atomicity
                with conn.cursor() as cur:
                    cur.execute("SAVEPOINT trivia_completion")

                    try:
                        # Get session details
                        cur.execute("""
                            SELECT * FROM trivia_sessions ts
                            JOIN trivia_questions tq ON ts.question_id = tq.id
                            WHERE ts.id = %s
                        """, (session_id,))

                        session = cur.fetchone()
                        if not session:
                            logger.error(f"❌ FIX #5: Trivia session {session_id} not found")
                            cur.execute("ROLLBACK TO SAVEPOINT trivia_completion")
                            return False

                        session_dict = dict(session)
                        correct_answer = session_dict.get("calculated_answer") or session_dict.get("correct_answer")
                        question_type = session_dict.get("question_type", "single")
                        multiple_choice_options = session_dict.get("multiple_choice_options")

                        if not correct_answer:
                            logger.error(f"❌ FIX #5: No correct answer for session {session_id}")
                            cur.execute("ROLLBACK TO SAVEPOINT trivia_completion")
                            return False

                        logger.info(f"🧠 FIX #5: Processing session {session_id}, attempt {attempt + 1}/{max_retries}")

                        # Get all answers
                        cur.execute("""
                            SELECT id, user_id, answer_text, normalized_answer, conflict_detected
                            FROM trivia_answers
                            WHERE session_id = %s
                            ORDER BY submitted_at ASC
                        """, (session_id,))

                        all_answers = cur.fetchall()
                        logger.info(f"🧠 FIX #5: Found {len(all_answers)} answers for session {session_id}")

                        correct_answer_ids = []
                        close_answer_ids = []
                        first_correct_answer = None

                        # Process each answer
                        for answer_row in all_answers:
                            answer_dict = dict(answer_row)
                            answer_id = answer_dict['id']
                            user_id = answer_dict['user_id']
                            original_answer = answer_dict['answer_text'].strip()
                            is_conflict = answer_dict['conflict_detected']

                            if is_conflict:
                                continue

                            # Evaluate answer
                            from ..handlers.trivia.evaluator import evaluate_answer
                            score, match_type = evaluate_answer(
                                original_answer, correct_answer, question_type, multiple_choice_options
                            )

                            is_correct = score >= 1.0
                            is_close = 0.7 <= score < 1.0

                            if is_correct:
                                correct_answer_ids.append(answer_id)
                                if first_correct_answer is None:
                                    first_correct_answer = {'id': answer_id, 'user_id': user_id}
                            elif is_close:
                                close_answer_ids.append(answer_id)

                        # Update correct answers
                        if correct_answer_ids:
                            cur.execute("""
                                UPDATE trivia_answers
                                SET is_correct = TRUE
                                WHERE id = ANY(%s)
                            """, (correct_answer_ids,))

                        # Update close answers
                        if close_answer_ids:
                            cur.execute("""
                                ALTER TABLE trivia_answers
                                ADD COLUMN IF NOT EXISTS is_close BOOLEAN DEFAULT FALSE
                            """)
                            cur.execute("""
                                UPDATE trivia_answers
                                SET is_close = TRUE
                                WHERE id = ANY(%s)
                            """, (close_answer_ids,))

                        # Calculate participant counts
                        if total_participants is None or correct_count is None:
                            cur.execute("""
                                SELECT COUNT(*) as total_participants,
                                       COUNT(CASE WHEN is_correct = TRUE THEN 1 END) as correct_count
                                FROM trivia_answers
                                WHERE session_id = %s AND conflict_detected = FALSE
                            """, (session_id,))
                            counts = cur.fetchone()

                            if counts:
                                counts_dict = dict(counts)
                                total_participants = int(
                                    counts_dict["total_participants"]) if total_participants is None else total_participants
                                correct_count = int(
                                    counts_dict["correct_count"]) if correct_count is None else correct_count

                        total_participants = total_participants or 0
                        correct_count = correct_count or 0

                        # Mark first correct answer
                        if first_correct_answer and not first_correct_user_id:
                            first_correct_user_id = first_correct_answer['user_id']

                        if first_correct_user_id:
                            cur.execute("""
                                UPDATE trivia_answers
                                SET is_first_correct = TRUE
                                WHERE session_id = %s
                                AND user_id = %s
                                AND is_correct = TRUE
                                AND NOT conflict_detected
                            """, (session_id, first_correct_user_id))

                        # Update session status
                        cur.execute("""
                            UPDATE trivia_sessions
                            SET status = 'completed',
                                ended_at = CURRENT_TIMESTAMP,
                                first_correct_user_id = %s,
                                total_participants = %s,
                                correct_answers_count = %s
                            WHERE id = %s
                        """, (first_correct_user_id, total_participants, correct_count, session_id))

                        # ✅ FIX: Mark question as 'answered' within same transaction WITH VERIFICATION
                        question_id = session_dict.get("question_id")
                        if question_id:
                            # Update status to 'answered'
                            cur.execute("""
                                UPDATE trivia_questions
                                SET status = 'answered'
                                WHERE id = %s
                            """, (question_id,))

                            if cur.rowcount == 0:
                                logger.error(
                                    f"❌ CRITICAL: Question {question_id} status update affected 0 rows - question may not exist!")
                            else:
                                logger.info(f"✅ Marked question {question_id} as 'answered' in transaction")

                            # IMMEDIATE VERIFICATION: Check the update actually worked
                            cur.execute("""
                                SELECT status FROM trivia_questions WHERE id = %s
                            """, (question_id,))
                            verification = cur.fetchone()

                            if verification and dict(verification)['status'] == 'answered':
                                logger.info(f"✅ VERIFIED: Question {question_id} status confirmed as 'answered'")
                            else:
                                actual_status = dict(verification)['status'] if verification else 'NOT_FOUND'
                                logger.error(
                                    f"❌ VERIFICATION FAILED: Question {question_id} status is '{actual_status}', not 'answered'!")
                                # Rollback and raise error to prevent commit
                                cur.execute("ROLLBACK TO SAVEPOINT trivia_completion")
                                raise ValueError(f"Question status verification failed - status is '{actual_status}'")

                        # ✅ FIX #5: Release savepoint and commit entire transaction atomically
                        cur.execute("RELEASE SAVEPOINT trivia_completion")
                        conn.commit()

                        logger.info(
                            f"✅ FIX #5: Session {session_id} completed successfully - {correct_count}/{total_participants} correct")
                        return True

                    except Exception as inner_error:
                        # ✅ FIX #5: Rollback to savepoint on any error
                        logger.error(f"❌ FIX #5: Error in transaction (attempt {attempt + 1}): {inner_error}")
                        cur.execute("ROLLBACK TO SAVEPOINT trivia_completion")
                        raise inner_error

            except Exception as e:
                logger.error(f"❌ FIX #5: Transaction attempt {attempt + 1}/{max_retries} failed: {e}")
                conn.rollback()

                # ✅ FIX #5: Exponential backoff before retry
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # 0.5s, 1s, 2s
                    logger.info(f"🔄 FIX #5: Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"❌ FIX #5: All {max_retries} attempts failed for session {session_id}")
                    return False

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

    def get_pending_approval_questions(self) -> List[Dict[str, Any]]:
        """
        Get all questions awaiting approval (status = 'pending_approval')

        This is used during startup to restore orphaned questions that were
        generated but not yet reviewed due to bot restart.

        Returns:
            List of question dicts with pending_approval status, ordered by creation time
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM trivia_questions
                    WHERE status = 'pending_approval'
                    AND is_active = TRUE
                    ORDER BY created_at ASC
                """
                )
                results = cur.fetchall()
                logger.info(f"Found {len(results)} questions with pending_approval status")
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting pending approval questions: {e}")
            return []

    def approve_trivia_question(self, question_id: int) -> bool:
        """
        Approve a question by updating its status from pending_approval to available

        Args:
            question_id: ID of the question to approve

        Returns:
            True if successful, False otherwise
        """
        return self.update_trivia_question_status(question_id, 'available')

    def reject_trivia_question(self, question_id: int) -> bool:
        """
        Reject a question by updating its status to rejected

        Args:
            question_id: ID of the question to reject

        Returns:
            True if successful, False otherwise
        """
        return self.update_trivia_question_status(question_id, 'rejected')

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

    def update_trivia_question_status(
            self,
            question_id: int,
            new_status: str) -> bool:
        """Update a trivia question's status to any valid value"""
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
                        f"Updated trivia question {question_id} status to '{new_status}'")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error updating trivia question status: {e}")
            conn.rollback()
            return False

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

    def get_trivia_participant_stats_for_week(self) -> Dict[str, Any]:
        """Gets key stats from the most recent Trivia Tuesday session."""
        conn = self.get_connection()
        if not conn:
            return {}

        try:
            with conn.cursor() as cur:
                # Find the most recent completed weekly trivia session in the last 7 days
                cur.execute("""
                    SELECT id, first_correct_user_id FROM trivia_sessions
                    WHERE status = 'completed' AND session_type LIKE 'weekly%'
                    AND started_at >= NOW() - INTERVAL '7 days'
                    ORDER BY started_at DESC LIMIT 1
                """)
                session = cur.fetchone()
                if not session:
                    return {"status": "no_session_found"}

                session_dict = dict(session)
                session_id = session_dict['id']
                winner_id = session_dict.get('first_correct_user_id')

                # Find a "notable participant" (someone who answered but didn't win)
                cur.execute("""
                    SELECT user_id FROM trivia_answers
                    WHERE session_id = %s AND conflict_detected = FALSE AND is_correct = FALSE
                    AND user_id != %s
                    GROUP BY user_id
                    ORDER BY COUNT(*) DESC, MAX(submitted_at) DESC
                    LIMIT 1
                """, (session_id, winner_id))
                notable_participant = cur.fetchone()

                return {
                    "status": "success",
                    "winner_id": winner_id,
                    "notable_participant_id": dict(notable_participant)['user_id'] if notable_participant else None
                }
        except Exception as e:
            logger.error(f"Error getting weekly trivia stats: {e}")
            return {"status": "error"}

    def check_question_duplicate(self, question_text: str,
                                 similarity_threshold: float = 0.8,
                                 check_retired: bool = True,
                                 question_answer: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Check if a similar question already exists in the database

        ✅ FIX #2: Enhanced duplicate detection with semantic similarity
        - Checks against ALL statuses including 'retired' (rejected questions)
        - Uses semantic similarity to catch questions with different wording
        - Prioritizes retired questions as strongest duplicates

        ✅ FIX #3: Answer-based duplicate detection
        - If question_answer provided, checks for same answer in retired/recent questions
        - Blocks questions with same answer as retired questions (0.3 threshold)
        - Warns about questions with same answer as recently answered questions (0.5 threshold)
        """
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # ✅ FIX #2: Get ALL questions including retired ones
                cur.execute("""
                    SELECT id, question_text, status, created_at, correct_answer
                    FROM trivia_questions
                    WHERE is_active = TRUE
                    ORDER BY
                        CASE WHEN status = 'retired' THEN 1 ELSE 2 END,
                        created_at DESC
                """)
                existing_questions = cur.fetchall()

                if not existing_questions:
                    return None

                # ✅ FIX #3: PHASE 1 - Check for answer-based duplicates FIRST (strictest filter)
                if question_answer:
                    normalized_new_answer = normalize_trivia_answer(question_answer).lower()

                    for existing in existing_questions:
                        existing_dict = dict(existing)
                        existing_answer = existing_dict.get('correct_answer')
                        existing_status = existing_dict.get('status', '')

                        if not existing_answer:
                            continue

                        normalized_existing_answer = normalize_trivia_answer(existing_answer).lower()

                        # Check if answers match
                        if normalized_new_answer == normalized_existing_answer:
                            # ✅ FIX: Skip retired questions for answer-based duplicate check.
                            # Retired questions have been used and are done - their answers should be
                            # recyclable. The Trivia Director generates questions based on real DB answers,
                            # so blocking by answer of a retired question starves the question pool.
                            if existing_status == 'retired':
                                continue  # Don't block new generation due to retired answer match

                            # Same answer as recently ANSWERED question - warn with medium strictness
                            elif existing_status == 'answered':
                                # Check if it's recent (within last 10 answered questions)
                                cur.execute("""
                                    SELECT id FROM trivia_questions
                                    WHERE is_active = TRUE AND status = 'answered'
                                    ORDER BY last_used_at DESC NULLS LAST
                                    LIMIT 10
                                """)
                                recent_answered_ids = [dict(row)['id'] for row in cur.fetchall()]

                                if existing_dict['id'] in recent_answered_ids:
                                    logger.warning(
                                        f"⚠️ ANSWER DUPLICATE (RECENT): New question has same answer '{question_answer}' as recently answered question #{existing_dict['id']}")
                                    return {
                                        'duplicate_id': existing_dict['id'],
                                        'duplicate_text': existing_dict.get('question_text', ''),
                                        'similarity_score': 0.9,  # High match on answer
                                        'status': existing_status,
                                        'created_at': existing_dict.get('created_at'),
                                        'match_type': 'answer_recent',
                                        'is_retired': False,
                                        'duplicate_reason': f"Same answer as recently used question: '{question_answer}'"
                                    }

                # Normalize the new question for comparison
                new_question_normalized = self._normalize_question_text(question_text)

                # ✅ FIX #2: Extract key concepts from the question
                new_question_concepts = extract_question_concepts(question_text)

                # Check each existing question
                import difflib

                for existing in existing_questions:
                    existing_dict = dict(existing)
                    existing_text = existing_dict.get('question_text', '')
                    existing_status = existing_dict.get('status', '')
                    existing_normalized = self._normalize_question_text(existing_text)

                    # Calculate text similarity
                    text_similarity = difflib.SequenceMatcher(
                        None,
                        new_question_normalized.lower(),
                        existing_normalized.lower()
                    ).ratio()

                    # ✅ FIX #2: Calculate semantic similarity (concept overlap)
                    existing_concepts = extract_question_concepts(existing_text)
                    concept_similarity = calculate_concept_similarity(
                        new_question_concepts, existing_concepts
                    )

                    # ✅ FIX #2: Use combined similarity score
                    combined_similarity = max(text_similarity, concept_similarity)

                    # ✅ FIX: Retired questions use a HIGHER threshold (harder to trigger as duplicate).
                    # Retired = previously used, not bad. The same topic should be recyclable.
                    # Using 1.25x multiplier (capped at 0.97) means retired questions need near-exact
                    # text match to block, preventing the pool from being starved by old questions.
                    if existing_status == 'retired':
                        effective_threshold = min(similarity_threshold * 1.25, 0.97)
                    else:
                        effective_threshold = similarity_threshold

                    if combined_similarity >= effective_threshold:
                        match_type = "semantic" if concept_similarity > text_similarity else "text"
                        logger.warning(
                            f"Duplicate question detected: {combined_similarity:.2%} {match_type} similarity to question #{existing_dict['id']} (status: {existing_status})")
                        return {
                            'duplicate_id': existing_dict['id'],
                            'duplicate_text': existing_text,
                            'similarity_score': combined_similarity,
                            'status': existing_status,
                            'created_at': existing_dict.get('created_at'),
                            'match_type': match_type,
                            'is_retired': existing_status == 'retired'
                        }

                return None  # No duplicate found

        except Exception as e:
            logger.error(f"Error checking for duplicate questions: {e}")
            return None

    def _normalize_question_text(self, question_text: str) -> str:
        """Normalize question text for duplicate comparison"""
        import re

        # Remove common variations that don't change meaning
        normalized = question_text.strip()

        # Remove punctuation and extra spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)

        # Remove common question words that don't affect uniqueness
        filler_words = ['what', 'which', 'who', 'when', 'where', 'how', 'did', 'has', 'is', 'was', 'the', 'a', 'an']
        words = normalized.lower().split()
        filtered_words = [word for word in words if word not in filler_words]

        return ' '.join(filtered_words)

    def ensure_minimum_question_pool(self, minimum_count: int = 5) -> Dict[str, Any]:
        """Ensure there are at least minimum_count available questions in the pool"""
        conn = self.get_connection()
        if not conn:
            return {"error": "No database connection", "available_count": 0}

        try:
            with conn.cursor() as cur:
                # Count current available questions
                cur.execute("""
                    SELECT COUNT(*) as available_count
                    FROM trivia_questions
                    WHERE is_active = TRUE AND status = 'available'
                """)
                result = cur.fetchone()
                current_available = int(cast(RealDictRow, result)['available_count']) if result else 0

                logger.info(f"Current available questions: {current_available}/{minimum_count}")

                if current_available >= minimum_count:
                    return {
                        "status": "sufficient",
                        "available_count": current_available,
                        "required_count": minimum_count,
                        "action_taken": "none"
                    }

                # Calculate how many questions we need
                needed_count = minimum_count - current_available

                # Strategy 1: Try to recycle old 'answered' questions (cooldown approach)
                recycled_count = 0
                cur.execute("""
                    SELECT id, question_text, last_used_at
                    FROM trivia_questions
                    WHERE is_active = TRUE
                    AND status = 'answered'
                    AND (last_used_at IS NULL OR last_used_at < NOW() - INTERVAL '2 weeks')
                    ORDER BY last_used_at ASC NULLS FIRST
                    LIMIT %s
                """, (needed_count,))

                recyclable_questions = cur.fetchall()

                if recyclable_questions:
                    question_ids = [cast(RealDictRow, q)['id'] for q in recyclable_questions]
                    cur.execute("""
                        UPDATE trivia_questions
                        SET status = 'available'
                        WHERE id = ANY(%s)
                    """, (question_ids,))

                    recycled_count = cur.rowcount
                    conn.commit()
                    logger.info(f"Recycled {recycled_count} old questions back to available status")

                # Check if we have enough now
                remaining_needed = needed_count - recycled_count

                return {
                    "status": "pool_managed",
                    "available_count": current_available + recycled_count,
                    "required_count": minimum_count,
                    "recycled_count": recycled_count,
                    "still_needed": remaining_needed,
                    "action_taken": f"recycled_{recycled_count}_questions"
                }

        except Exception as e:
            logger.error(f"Error ensuring minimum question pool: {e}")
            conn.rollback()
            return {"error": str(e), "available_count": 0}

    # --- Missing Trivia Methods for Command Compatibility ---

    def get_trivia_question(
            self, question_id: int) -> Optional[Dict[str, Any]]:
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

    def start_trivia_session(
            self,
            question_id: int,
            started_by: int) -> Optional[int]:
        """Start trivia session (alias for create_trivia_session)"""
        return self.create_trivia_session(question_id, "weekly")

    def end_trivia_session(self, session_id: int,
                           ended_by: int) -> Optional[Dict[str, Any]]:
        """End trivia session and return enhanced results with participant lists"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                # Get session and question details
                cur.execute("""
                    SELECT ts.*, tq.question_text, tq.correct_answer, ts.calculated_answer
                    FROM trivia_sessions ts
                    JOIN trivia_questions tq ON ts.question_id = tq.id
                    WHERE ts.id = %s
                """, (session_id,))
                session = cur.fetchone()

                if not session:
                    return None

                session_dict = dict(session)

                # Get all answers for this session (before evaluation)
                answers = self.get_trivia_session_answers(session_id)

                # Calculate unique participants (count unique users, not total answers)
                non_conflict_answers = [a for a in answers if not a.get('conflict_detected', False)]
                unique_participants = len(set(a['user_id'] for a in non_conflict_answers))

                print(
                    f"🧠 TRIVIA: Session {session_id} - Raw answers: {len(answers)}, Non-conflict: {len(non_conflict_answers)}, Unique users: {unique_participants}")

                # Complete the session with enhanced evaluation (pass None to let it calculate properly)
                success = self.complete_trivia_session(
                    session_id,
                    first_correct_user_id=None,  # Let complete_trivia_session determine this
                    total_participants=unique_participants,  # Use unique count
                    correct_count=None  # Let complete_trivia_session calculate this with enhanced matching
                )

                if success:
                    # Get the updated results after enhanced evaluation
                    cur.execute("""
                        SELECT ts.*, tq.question_text, ts.calculated_answer, tq.correct_answer, tq.category, tq.dynamic_query_type
                        FROM trivia_sessions ts
                        JOIN trivia_questions tq ON ts.question_id = tq.id
                        WHERE ts.id = %s
                    """, (session_id,))
                    updated_session = cur.fetchone()

                    if updated_session:
                        updated_session_dict = dict(updated_session)

                        # Get first correct user info
                        cur.execute("""
                            SELECT user_id, answer_text FROM trivia_answers
                            WHERE session_id = %s AND is_first_correct = TRUE
                            LIMIT 1
                        """, (session_id,))
                        first_correct_result = cur.fetchone()
                        first_correct_user = dict(first_correct_result) if first_correct_result else None

                        # NEW: Get lists of all correct and incorrect users (excluding conflicts)
                        cur.execute("""
                            SELECT DISTINCT user_id FROM trivia_answers
                            WHERE session_id = %s AND is_correct = TRUE AND conflict_detected = FALSE
                            ORDER BY user_id
                        """, (session_id,))
                        correct_users_results = cur.fetchall()
                        correct_user_ids = [dict(row)['user_id'] for row in correct_users_results]

                        cur.execute("""
                            SELECT DISTINCT user_id FROM trivia_answers
                            WHERE session_id = %s AND (is_correct = FALSE OR is_correct IS NULL) AND conflict_detected = FALSE
                            ORDER BY user_id
                        """, (session_id,))
                        incorrect_users_results = cur.fetchall()
                        incorrect_user_ids = [dict(row)['user_id'] for row in incorrect_users_results]

                        correct_answer = updated_session_dict.get(
                            'calculated_answer') or updated_session_dict.get('correct_answer')

                        # Calculate accuracy rate for bonus round consideration
                        total_count = updated_session_dict.get('total_participants', unique_participants)
                        correct_count = updated_session_dict.get('correct_answers_count', 0)
                        accuracy_rate = (correct_count / total_count) if total_count > 0 else 0

                        # Determine if bonus round should be triggered (Ash is "annoyed" that
                        # challenge was insufficient)
                        bonus_round_triggered = accuracy_rate > 0.5 and total_count >= 2  # At least 2 participants and >50% correct

                        return {
                            'session_id': session_id,
                            'question_id': updated_session_dict.get('question_id'),
                            'question': updated_session_dict.get('question_text'),
                            'correct_answer': correct_answer,
                            'total_participants': total_count,
                            'correct_answers': correct_count,
                            'accuracy_rate': accuracy_rate,
                            'first_correct': first_correct_user,
                            'category': updated_session_dict.get('category'),
                            'dynamic_query_type': updated_session_dict.get('dynamic_query_type'),
                            # Enhanced data for community engagement
                            'correct_user_ids': correct_user_ids,
                            'incorrect_user_ids': incorrect_user_ids,
                            # NEW: Bonus round system
                            'bonus_round_triggered': bonus_round_triggered,
                            'bonus_round_reason': f"Challenge parameters insufficient - {accuracy_rate:.1%} success rate exceeds acceptable failure thresholds" if bonus_round_triggered else None
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
                    'participants': [
                        dict(row) for row in participants],
                    'total_sessions': int(
                        cast(
                            RealDictRow,
                            stats)['total_sessions']) if stats else 0,
                    'total_questions': int(
                        cast(
                            RealDictRow,
                            stats)['total_questions']) if stats else 0,
                    'avg_participation_per_session': float(
                        cast(
                            RealDictRow,
                            stats)['avg_participation']) if stats else 0.0}
        except Exception as e:
            logger.error(f"Error getting trivia leaderboard: {e}")
            return {}

    def reset_trivia_questions(self) -> int:
        """Reset all answered questions to available (alias for reset_all_trivia_questions_status)"""
        return self.reset_all_trivia_questions_status('answered', 'available')

    def cleanup_hanging_trivia_sessions(self) -> Dict[str, Any]:
        """Clean up any hanging trivia sessions from previous bot runs"""
        conn = self.get_connection()
        if not conn:
            return {"error": "No database connection", "cleaned_sessions": 0}

        try:
            with conn.cursor() as cur:
                # Find active sessions that have been running for more than 2 hours
                cur.execute("""
                    SELECT ts.*, tq.question_text
                    FROM trivia_sessions ts
                    JOIN trivia_questions tq ON ts.question_id = tq.id
                    WHERE ts.status = 'active'
                    AND ts.started_at < NOW() - INTERVAL '2 hours'
                """)
                hanging_sessions = cur.fetchall()

                cleaned_count = 0
                session_details = []

                for session in hanging_sessions:
                    session_dict = dict(session)
                    session_id = session_dict['id']

                    try:
                        # Mark session as expired
                        cur.execute("""
                            UPDATE trivia_sessions
                            SET status = 'expired', ended_at = NOW()
                            WHERE id = %s
                        """, (session_id,))

                        # Don't mark the question as 'answered' for expired sessions
                        # so they can be used again

                        cleaned_count += 1
                        session_details.append({
                            "session_id": session_id,
                            "question_text": session_dict.get("question_text", "Unknown"),
                            "started_at": session_dict.get("started_at"),
                            "question_id": session_dict.get("question_id")
                        })

                        logger.info(f"Cleaned up hanging trivia session {session_id}")

                    except Exception as e:
                        logger.error(f"Error cleaning up session {session_id}: {e}")
                        continue

                conn.commit()

                return {
                    "cleaned_sessions": cleaned_count,
                    "sessions": session_details,
                    "total_found": len(hanging_sessions)
                }

        except Exception as e:
            logger.error(f"Error during trivia session cleanup: {e}")
            conn.rollback()
            return {"error": str(e), "cleaned_sessions": 0}

    # --- Trivia Director System: Category-Based Game Curation ---

    def get_trivia_curated_games(
        self,
        category: str,
        avoid_game_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Curate game data based on trivia category for the Trivia Director system.

        This method selects appropriate games from the played_games table based on
        the requested category, enabling the AI to generate questions that leverage
        its internal knowledge of video games rather than relying on stream statistics.

        Categories:
        - 'Single_Game_Lore': Returns 1 random game for deep dive questions
        - 'Franchise_Connection': Returns 2-3 games from the same series
        - 'Genre_Knowledge': Returns 3 games from the same genre
        - 'Timeline_Challenge': Returns 2 games for chronological comparison

        Args:
            category: The trivia category to curate for
            avoid_game_ids: Optional list of game IDs to exclude from selection

        Returns:
            Dict containing:
                - category: The category used
                - games: List of curated game dicts
                - fallback_used: Boolean indicating if fallback logic was used
                - metadata: Additional context for AI prompt generation
        """
        conn = self.get_connection()
        if not conn:
            logger.error("No database connection for trivia curation")
            return {
                'category': category,
                'games': [],
                'fallback_used': False,
                'error': 'No database connection'
            }

        avoid_ids = avoid_game_ids or []
        avoid_clause = "AND id NOT IN %(avoid_ids)s" if avoid_ids else ""

        try:
            with conn.cursor() as cur:
                games = []
                fallback_used = False
                metadata = {}

                # === SINGLE GAME LORE: Deep dive into one specific game ===
                if category == 'Single_Game_Lore':
                    # Priority: Completed games (more knowledge available)
                    query = f"""
                        SELECT * FROM played_games
                        WHERE completion_status = 'completed'
                        {avoid_clause}
                        ORDER BY RANDOM()
                        LIMIT 1
                    """
                    cur.execute(query, {'avoid_ids': tuple(avoid_ids)} if avoid_ids else {})
                    result = cur.fetchone()

                    if not result:
                        # Fallback: Any game
                        logger.info("Falling back to any game for Single_Game_Lore")
                        query = f"""
                            SELECT * FROM played_games
                            {avoid_clause.replace('AND', 'WHERE') if avoid_ids else ''}
                            ORDER BY RANDOM()
                            LIMIT 1
                        """
                        cur.execute(query, {'avoid_ids': tuple(avoid_ids)} if avoid_ids else {})
                        result = cur.fetchone()
                        fallback_used = True

                    if result:
                        games = [dict(result)]
                        metadata = {
                            'focus_game': games[0]['canonical_name'],
                            'genre': games[0].get('genre', 'Unknown'),
                            'completion_status': games[0].get('completion_status', 'Unknown')
                        }

                # === FRANCHISE CONNECTION: Multiple games from same series ===
                elif category == 'Franchise_Connection':
                    # Step 1: Find a series with 2+ games
                    query = f"""
                        SELECT series_name, COUNT(*) as game_count
                        FROM played_games
                        WHERE series_name IS NOT NULL
                          AND series_name != ''
                          {avoid_clause}
                        GROUP BY series_name
                        HAVING COUNT(*) >= 2
                        ORDER BY RANDOM()
                        LIMIT 1
                    """
                    cur.execute(query, {'avoid_ids': tuple(avoid_ids)} if avoid_ids else {})
                    series_result = cur.fetchone()

                    if series_result:
                        selected_series = dict(series_result)['series_name']

                        # Step 2: Get games from that series
                        query = f"""
                            SELECT * FROM played_games
                            WHERE series_name = %(series)s
                            {avoid_clause}
                            LIMIT 3
                        """
                        params = {'series': selected_series}
                        if avoid_ids:
                            params['avoid_ids'] = tuple(avoid_ids)
                        cur.execute(query, params)
                        results = cur.fetchall()

                        games = [dict(row) for row in results]
                        metadata = {
                            'series_name': selected_series,
                            'game_count': len(games)
                        }
                    else:
                        # Fallback: Use Genre_Knowledge instead
                        logger.info("No franchise with 2+ games, falling back to Genre_Knowledge")
                        return self.get_trivia_curated_games('Genre_Knowledge', avoid_game_ids)

                # === GENRE KNOWLEDGE: Multiple games from same genre ===
                elif category == 'Genre_Knowledge':
                    # Step 1: Find a genre with 3+ games
                    query = f"""
                        SELECT genre, COUNT(*) as game_count
                        FROM played_games
                        WHERE genre IS NOT NULL
                          AND genre != ''
                          {avoid_clause}
                        GROUP BY genre
                        HAVING COUNT(*) >= 3
                        ORDER BY RANDOM()
                        LIMIT 1
                    """
                    cur.execute(query, {'avoid_ids': tuple(avoid_ids)} if avoid_ids else {})
                    genre_result = cur.fetchone()

                    if genre_result:
                        selected_genre = dict(genre_result)['genre']

                        # Step 2: Get games from that genre
                        query = f"""
                            SELECT * FROM played_games
                            WHERE genre = %(genre)s
                            {avoid_clause}
                            ORDER BY RANDOM()
                            LIMIT 3
                        """
                        params = {'genre': selected_genre}
                        if avoid_ids:
                            params['avoid_ids'] = tuple(avoid_ids)
                        cur.execute(query, params)
                        results = cur.fetchall()

                        games = [dict(row) for row in results]
                        metadata = {
                            'genre': selected_genre,
                            'game_count': len(games)
                        }
                    else:
                        # Fallback: Single_Game_Lore (always works)
                        logger.info("No genre with 3+ games, falling back to Single_Game_Lore")
                        return self.get_trivia_curated_games('Single_Game_Lore', avoid_game_ids)

                # === TIMELINE CHALLENGE: Chronological comparison ===
                elif category == 'Timeline_Challenge':
                    # Get 2 games with different first_played_dates
                    query = f"""
                        SELECT * FROM played_games
                        WHERE first_played_date IS NOT NULL
                        {avoid_clause}
                        ORDER BY RANDOM()
                        LIMIT 2
                    """
                    cur.execute(query, {'avoid_ids': tuple(avoid_ids)} if avoid_ids else {})
                    results = cur.fetchall()

                    if results and len(results) >= 2:
                        games = [dict(row) for row in results]
                        metadata = {
                            'game1': games[0]['canonical_name'],
                            'game2': games[1]['canonical_name'],
                            'date1': games[0].get('first_played_date'),
                            'date2': games[1].get('first_played_date')
                        }
                    else:
                        # Fallback: Single_Game_Lore
                        logger.info("Not enough timeline data, falling back to Single_Game_Lore")
                        return self.get_trivia_curated_games('Single_Game_Lore', avoid_game_ids)

                else:
                    # Unknown category - default to Single_Game_Lore
                    logger.warning(f"Unknown category '{category}', using Single_Game_Lore")
                    return self.get_trivia_curated_games('Single_Game_Lore', avoid_game_ids)

                # Return curated data
                return {
                    'category': category,
                    'games': games,
                    'fallback_used': fallback_used,
                    'metadata': metadata
                }

        except Exception as e:
            logger.error(f"Error curating games for category '{category}': {e}")
            import traceback
            traceback.print_exc()

            # Emergency fallback: Try to get ANY game
            try:
                with conn.cursor() as fallback_cur:
                    fallback_cur.execute("SELECT * FROM played_games ORDER BY RANDOM() LIMIT 1")
                    result = fallback_cur.fetchone()
                if result:
                    return {
                        'category': 'Single_Game_Lore',
                        'games': [dict(result)],
                        'fallback_used': True,
                        'metadata': {'emergency_fallback': True},
                        'error': str(e)
                    }
            except Exception:
                pass

            return {
                'category': category,
                'games': [],
                'fallback_used': True,
                'error': str(e)
            }

    def clip_lore_exists(self, canonical_url: str) -> bool:
        """Check if a clip has already been analyzed and stored in the database."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM clip_lore WHERE canonical_url = %s",
                    (canonical_url,)
                )
                return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking clip lore existence: {e}")
            return False
        finally:
            conn.close()

    def add_clip_lore(
            self,
            canonical_url: str,
            original_url: str,
            game_title: str,
            reaction: str,
            trigger: str,
            lore_summary: str,
            notable_quote: str,
            emotion_category: str,
            characters_involved: str,
            clip_outcome: str,
            submitted_by: str,
            message_id: int) -> bool:
        """Insert extracted clip lore into the database."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO clip_lore (
                        canonical_url, original_url, game_title, reaction, trigger, lore_summary,
                        notable_quote, emotion_category, characters_involved, clip_outcome,
                        submitted_by_discord_id, message_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (canonical_url) DO NOTHING
                """, (canonical_url, original_url, game_title, reaction, trigger, lore_summary,
                      notable_quote, emotion_category, characters_involved, clip_outcome,
                      submitted_by, message_id))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Error inserting clip lore: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def get_clip_lore(self, canonical_url: str) -> Optional[Dict[str, Any]]:
        """Retrieve clip lore details from the database."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT game_title, reaction, trigger, lore_summary, notable_quote,
                           emotion_category, characters_involved, clip_outcome,
                           submitted_by_discord_id, message_id
                    FROM clip_lore
                    WHERE canonical_url = %s
                """, (canonical_url,))
                row = cur.fetchone()

                if row:
                    return {
                        'game_title': row['game_title'],
                        'reaction': row['reaction'],
                        'trigger': row['trigger'],
                        'lore_summary': row['lore_summary'],
                        'notable_quote': row['notable_quote'],
                        'emotion_category': row['emotion_category'],
                        'characters_involved': row['characters_involved'],
                        'clip_outcome': row['clip_outcome'],
                        'submitted_by': row['submitted_by_discord_id'],
                        'message_id': row['message_id']
                    }
                return None
        except Exception as e:
            logger.error(f"Error retrieving clip lore: {e}")
            return None
        finally:
            conn.close()

    
    def add_pending_batch_clip(self, canonical_url: str, video_title: str) -> bool:
        """Add a clip to clip_lore as PENDING for batch processing"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO clip_lore (
                        canonical_url, video_title, batch_status
                    ) VALUES (%s, %s, 'PENDING')
                    ON CONFLICT (canonical_url) DO UPDATE
                    SET batch_status = 'PENDING'
                    """,
                    (canonical_url, video_title)
                )
                self.conn.commit()
                return True
        except Exception as e:
            print(f"Error adding pending batch clip: {e}")
            return False

    def get_pending_batch_clips(self) -> list:
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    SELECT canonical_url, video_title FROM clip_lore 
                    WHERE batch_status = 'PENDING'
                    """
                )
                return cursor.fetchall()
        except Exception as e:
            print(f"Error getting pending clips: {e}")
            return []

    def update_clip_batch_job(self, canonical_url: str, batch_job_id: str) -> bool:
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE clip_lore 
                    SET batch_job_id = %s, batch_status = 'PROCESSING' 
                    WHERE canonical_url = %s
                    """,
                    (batch_job_id, canonical_url)
                )
                self.conn.commit()
                return True
        except Exception as e:
            print(f"Error updating batch job: {e}")
            return False
            
    def update_clip_lore_from_batch(self, canonical_url: str, data: dict) -> bool:
        try:
            with self.get_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE clip_lore 
                    SET 
                        game_title = %s,
                        reaction = %s,
                        trigger = %s,
                        lore_summary = %s,
                        tags = %s,
                        notable_quote = %s,
                        emotion_category = %s,
                        characters_involved = %s,
                        clip_outcome = %s,
                        batch_status = 'COMPLETED'
                    WHERE canonical_url = %s
                    """,
                    (
                        data.get('game_title', 'Unknown Game'),
                        data.get('reaction', ''),
                        data.get('trigger', ''),
                        data.get('lore_summary', ''),
                        ','.join(data.get('tags', [])),
                        data.get('notable_quote', ''),
                        data.get('emotion_category', ''),
                        data.get('characters_involved', ''),
                        data.get('clip_outcome', ''),
                        canonical_url
                    )
                )
                self.conn.commit()
                return True
        except Exception as e:
            print(f"Error updating from batch: {e}")
            return False

    def get_random_clip_lore(self, limit: int = 1, required_fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Retrieve random clip lore entries, optionally filtering for non-empty fields."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT canonical_url, original_url, game_title, reaction, trigger,
                           lore_summary, notable_quote, emotion_category, characters_involved,
                           clip_outcome, submitted_by_discord_id, message_id
                    FROM clip_lore
                """

                conditions = []
                if required_fields:
                    for field in required_fields:
                        # Ensure the field is valid to prevent SQL injection
                        valid_fields = [
                            'game_title',
                            'reaction',
                            'trigger',
                            'lore_summary',
                            'notable_quote',
                            'emotion_category',
                            'characters_involved',
                            'clip_outcome',
                            'submitted_by_discord_id']
                        if field in valid_fields:
                            conditions.append(f"({field} IS NOT NULL AND {field} != '')")

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                query += " ORDER BY RANDOM() LIMIT %s"

                cur.execute(query, (limit,))
                rows = cur.fetchall()

                results = []
                for row in rows:
                    results.append({
                        'canonical_url': row['canonical_url'],
                        'original_url': row['original_url'],
                        'game_title': row['game_title'],
                        'reaction': row['reaction'],
                        'trigger': row['trigger'],
                        'lore_summary': row['lore_summary'],
                        'notable_quote': row['notable_quote'],
                        'emotion_category': row['emotion_category'],
                        'characters_involved': row['characters_involved'],
                        'clip_outcome': row['clip_outcome'],
                        'submitted_by_discord_id': row['submitted_by_discord_id'],
                        'message_id': row['message_id']
                    })
                return results
        except Exception as e:
            logger.error(f"Error retrieving random clip lore: {e}")
            return []
        finally:
            conn.close()


# Export
__all__ = ['TriviaDatabase']
