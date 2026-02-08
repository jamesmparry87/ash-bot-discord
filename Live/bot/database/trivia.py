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

    def normalize_trivia_answer(self, answer_text: str) -> str:
        """Enhanced normalization for trivia answers with fuzzy matching support"""
        import re

        # Start with the original text
        normalized = answer_text.strip()

        # Remove common punctuation but preserve important chars like hyphens in compound words
        normalized = re.sub(r'[.,!?;:"\'()[\]{}]', '', normalized)

        # Handle common game/media abbreviations and variations
        abbreviation_map = {
            'gta': 'grand theft auto',
            'cod': 'call of duty',
            'gtav': 'grand theft auto v',
            'gtaiv': 'grand theft auto iv',
            'rdr': 'red dead redemption',
            'rdr2': 'red dead redemption 2',
            'gow': 'god of war',
            'tlou': 'the last of us',
            'botw': 'breath of the wild',
            'totk': 'tears of the kingdom',
            'ff': 'final fantasy',
            'ffvii': 'final fantasy vii',
            'ffx': 'final fantasy x',
            'mgs': 'metal gear solid',
            'loz': 'legend of zelda',
            'zelda': 'legend of zelda',
            'pokemon': 'pokémon',
            'mario': 'super mario',
            'doom': 'doom',
            'halo': 'halo',
            'fallout': 'fallout'
        }

        # Apply abbreviation expansions (case insensitive)
        words = normalized.lower().split()
        expanded_words = []
        for word in words:
            if word in abbreviation_map:
                expanded_words.extend(abbreviation_map[word].split())
            else:
                expanded_words.append(word)
        normalized = ' '.join(expanded_words)

        # Remove filler words that don't change meaning
        filler_words = ['and', 'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by',
                        'about', 'approximately', 'roughly', 'around', 'over', 'under', 'just',
                        'exactly', 'precisely', 'nearly', 'almost', 'close to', 'more than', 'less than']

        # Split into words and filter out filler words
        words = normalized.split()
        filtered_words = [word for word in words if word not in filler_words]

        # Rejoin and clean up extra spaces
        normalized = ' '.join(filtered_words)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

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
        """
        Get the next trivia question based on priority system (excluding answered/retired questions)

        ✅ FIX #2: Ensure retired questions are never selected
        """
        conn = self.db.get_connection()
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
                            score, match_type = self._evaluate_trivia_answer(
                                original_answer, correct_answer, 'single'
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

                        # ✅ FIX #5: Mark question as 'answered' within same transaction
                        question_id = session_dict.get("question_id")
                        if question_id:
                            cur.execute("""
                                UPDATE trivia_questions
                                SET status = 'answered'
                                WHERE id = %s
                            """, (question_id,))

                            if cur.rowcount == 0:
                                logger.warning(f"⚠️ FIX #5: Question {question_id} status update affected 0 rows")
                            else:
                                logger.info(f"✅ FIX #5: Marked question {question_id} as 'answered'")

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

    def _evaluate_trivia_answer(self, user_answer: str, correct_answer: str, question_type: str) -> Tuple[float, str]:
        """
        Evaluate a trivia answer with enhanced fuzzy matching.
        Returns: (score, match_type) where score is 0.0-1.0
        """
        import difflib

        # Clean up inputs
        user_clean = user_answer.strip()
        correct_clean = correct_answer.strip()

        # Normalize answers for better matching
        user_normalized = self.normalize_trivia_answer(user_clean)
        correct_normalized = self.normalize_trivia_answer(correct_clean)

        # Level 1: Exact match (case-insensitive)
        if user_clean.lower() == correct_clean.lower():
            return 1.0, "exact_case_insensitive"

        # Level 2: Normalized exact match
        if user_normalized.lower() == correct_normalized.lower():
            return 1.0, "normalized_exact"

        # Level 3: Fuzzy string matching with high threshold (correct answers)
        similarity_exact = difflib.SequenceMatcher(None, user_clean.lower(), correct_clean.lower()).ratio()
        if similarity_exact >= 0.9:  # 90% similarity = correct
            return 1.0, "fuzzy_high"

        # Level 4: Close matches (partial credit)
        if similarity_exact >= 0.7:  # 70-89% similarity = close
            return 0.8, "fuzzy_close"

        # Level 5: Word-based matching for multi-word answers
        if len(correct_clean.split()) > 1:
            correct_words = set(word.lower() for word in correct_clean.split())
            answer_words = set(word.lower() for word in user_clean.split())

            # Calculate word overlap
            if len(correct_words) > 0:
                overlap_ratio = len(correct_words.intersection(answer_words)) / len(correct_words)

                if overlap_ratio >= 0.8:  # 80% word overlap = correct
                    return 1.0, "word_overlap_high"
                elif overlap_ratio >= 0.6:  # 60% word overlap = close
                    return 0.75, "word_overlap_medium"

        # Level 6: Handle numerical/time answers
        if self._contains_numbers(correct_clean) and self._contains_numbers(user_clean):
            correct_nums = self._extract_numbers(correct_clean)
            answer_nums = self._extract_numbers(user_clean)

            # Check for numerical matches with tolerance
            for c_num in correct_nums:
                for a_num in answer_nums:
                    # Within 5% tolerance for large numbers, exact for small numbers
                    tolerance = max(1, c_num * 0.05) if c_num > 20 else 0
                    if abs(c_num - a_num) <= tolerance:
                        if abs(c_num - a_num) == 0:
                            return 1.0, "numerical_exact"
                        else:
                            return 0.8, "numerical_close"

        # Level 7: Common abbreviations and variations
        if self._check_abbreviation_match(user_clean, correct_clean):
            return 1.0, "abbreviation_match"

        # Level 8: Weak similarity for debugging
        if similarity_exact >= 0.3:
            return similarity_exact, "weak_similarity"

        return 0.0, "no_match"

    def _normalize_answer_for_matching(self, answer: str) -> str:
        """Normalize an answer for enhanced matching"""
        import re

        # Remove common punctuation
        normalized = re.sub(r'[.,!?;:"\'()[\]{}]', '', answer)

        # Handle common game abbreviations
        abbreviations = {
            'gta': 'grand theft auto',
            'cod': 'call of duty',
            'gow': 'god of war',
            'rdr': 'red dead redemption',
            'tlou': 'the last of us',
            'ff': 'final fantasy'
        }

        words = normalized.lower().split()
        expanded_words = []
        for word in words:
            if word in abbreviations:
                expanded_words.extend(abbreviations[word].split())
            else:
                expanded_words.append(word)

        # Remove filler words
        filler_words = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'with'}
        filtered_words = [word for word in expanded_words if word not in filler_words]

        return ' '.join(filtered_words).strip()

    def _contains_numbers(self, text: str) -> bool:
        """Check if text contains numbers"""
        import re
        return bool(re.search(r'\d', text))

    def _extract_numbers(self, text: str) -> list[float]:
        """Extract numbers from text"""
        import re
        numbers = re.findall(r'\d+\.?\d*', text)
        return [float(num) for num in numbers]

    def _check_abbreviation_match(self, answer: str, correct: str) -> bool:
        """Check for common abbreviation matches"""
        answer_lower = answer.lower().strip()
        correct_lower = correct.lower().strip()

        # Color abbreviations
        color_abbrev = {
            'b': 'blue', 'r': 'red', 'g': 'green', 'y': 'yellow',
            'w': 'white', 'bl': 'black', 'o': 'orange', 'p': 'purple'
        }

        if answer_lower in color_abbrev and color_abbrev[answer_lower] == correct_lower:
            return True
        if correct_lower in color_abbrev and color_abbrev[correct_lower] == answer_lower:
            return True

        return False

    def calculate_dynamic_answer(self, dynamic_query_type: str, parameter: Optional[str] = None) -> Optional[str]:
        """
        Calculate the current answer for a dynamic question, with optional filtering.

        Supports platform-specific queries to distinguish YouTube playthroughs from Twitch VODs.
        """
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cur:
                base_query = "SELECT canonical_name FROM played_games"
                where_clauses = []
                params = []
                order_by = ""

                # Add filter if a parameter (like a series name) is provided
                if parameter:
                    where_clauses.append("(LOWER(series_name) = %s OR LOWER(genre) = %s)")
                    params.extend([parameter.lower(), parameter.lower()])

                # Define query logic with platform-specific options
                if dynamic_query_type == "most_popular_by_views":
                    where_clauses.extend(["youtube_views > 0",
                                          "youtube_playlist_url IS NOT NULL",
                                          "youtube_playlist_url != ''"])
                    order_by = "ORDER BY youtube_views DESC"

                # YouTube-specific queries
                elif dynamic_query_type == "most_youtube_episodes":
                    where_clauses.extend(["total_episodes > 0",
                                          "youtube_playlist_url IS NOT NULL",
                                          "youtube_playlist_url != ''"])
                    order_by = "ORDER BY total_episodes DESC"
                elif dynamic_query_type == "longest_youtube_playthrough":
                    where_clauses.extend(["total_playtime_minutes > 0",
                                          "youtube_playlist_url IS NOT NULL",
                                          "youtube_playlist_url != ''"])
                    order_by = "ORDER BY total_playtime_minutes DESC"

                # Twitch-specific queries
                elif dynamic_query_type == "most_twitch_vods":
                    where_clauses.extend(["total_episodes > 0", "twitch_vod_urls IS NOT NULL",
                                         "twitch_vod_urls != ''", "twitch_vod_urls != '{}'"])
                    order_by = "ORDER BY total_episodes DESC"
                elif dynamic_query_type == "longest_twitch_stream":
                    where_clauses.extend(["total_playtime_minutes > 0", "twitch_vod_urls IS NOT NULL",
                                         "twitch_vod_urls != ''", "twitch_vod_urls != '{}'"])
                    order_by = "ORDER BY total_playtime_minutes DESC"

                # Generic queries (mixed platforms)
                elif dynamic_query_type == "longest_playtime":
                    where_clauses.append("total_playtime_minutes > 0")
                    order_by = "ORDER BY total_playtime_minutes DESC"
                elif dynamic_query_type == "shortest_playtime":
                    where_clauses.append("total_playtime_minutes > 0")
                    order_by = "ORDER BY total_playtime_minutes ASC"
                elif dynamic_query_type == "most_episodes":
                    where_clauses.append("total_episodes > 0")
                    order_by = "ORDER BY total_episodes DESC"

                # ✅ FIX: New query type for most episodes among COMPLETED games only
                elif dynamic_query_type == "most_episodes_completed":
                    where_clauses.extend(["total_episodes > 0", "completion_status = 'completed'"])
                    order_by = "ORDER BY total_episodes DESC"

                # Date-based queries (newest/most recent)
                elif dynamic_query_type == "newest_game":
                    where_clauses.append("release_year IS NOT NULL")
                    order_by = "ORDER BY release_year DESC"
                elif dynamic_query_type == "most_recent_game":
                    where_clauses.append("first_played_date IS NOT NULL")
                    order_by = "ORDER BY first_played_date DESC"
                elif dynamic_query_type == "oldest_game":
                    where_clauses.append("release_year IS NOT NULL")
                    order_by = "ORDER BY release_year ASC"

                # ===== PHASE 1: SERIES BATTLES =====
                elif dynamic_query_type == "series_playtime_comparison":
                    # Parameter format: "Series A vs Series B"
                    if not parameter or " vs " not in parameter.lower():
                        return None
                    series_a, series_b = [s.strip() for s in parameter.split(" vs ", 1)]

                    # Query total playtime for each series
                    cur.execute("""
                        SELECT series_name, SUM(total_playtime_minutes) as total_playtime
                        FROM played_games
                        WHERE LOWER(series_name) IN (%s, %s)
                        AND total_playtime_minutes > 0
                        GROUP BY series_name
                        ORDER BY total_playtime DESC
                        LIMIT 1
                    """, (series_a.lower(), series_b.lower()))
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                elif dynamic_query_type == "series_episode_comparison":
                    # Parameter format: "Series A vs Series B"
                    if not parameter or " vs " not in parameter.lower():
                        return None
                    series_a, series_b = [s.strip() for s in parameter.split(" vs ", 1)]

                    # Query total episodes for each series
                    cur.execute("""
                        SELECT series_name, SUM(total_episodes) as total_episodes
                        FROM played_games
                        WHERE LOWER(series_name) IN (%s, %s)
                        AND total_episodes > 0
                        GROUP BY series_name
                        ORDER BY total_episodes DESC
                        LIMIT 1
                    """, (series_a.lower(), series_b.lower()))
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                elif dynamic_query_type == "series_completion_comparison":
                    # Parameter format: "Series A vs Series B"
                    if not parameter or " vs " not in parameter.lower():
                        return None
                    series_a, series_b = [s.strip() for s in parameter.split(" vs ", 1)]

                    # Query completed games count for each series
                    cur.execute("""
                        SELECT series_name, COUNT(*) as completed_count
                        FROM played_games
                        WHERE LOWER(series_name) IN (%s, %s)
                        AND completion_status = 'completed'
                        GROUP BY series_name
                        ORDER BY completed_count DESC
                        LIMIT 1
                    """, (series_a.lower(), series_b.lower()))
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                elif dynamic_query_type == "series_views_comparison":
                    # Parameter format: "Series A vs Series B"
                    if not parameter or " vs " not in parameter.lower():
                        return None
                    series_a, series_b = [s.strip() for s in parameter.split(" vs ", 1)]

                    # Query total YouTube views for each series
                    cur.execute("""
                        SELECT series_name, SUM(youtube_views) as total_views
                        FROM played_games
                        WHERE LOWER(series_name) IN (%s, %s)
                        AND youtube_views > 0
                        GROUP BY series_name
                        ORDER BY total_views DESC
                        LIMIT 1
                    """, (series_a.lower(), series_b.lower()))
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                # ===== PHASE 1: GENRE INSIGHTS =====
                elif dynamic_query_type == "most_played_genre":
                    # Which genre has the most games
                    cur.execute("""
                        SELECT genre, COUNT(*) as game_count
                        FROM played_games
                        WHERE genre IS NOT NULL AND genre != ''
                        GROUP BY genre
                        ORDER BY game_count DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['genre'] if result else None

                elif dynamic_query_type == "longest_genre_playtime":
                    # Which genre has the most total playtime
                    cur.execute("""
                        SELECT genre, SUM(total_playtime_minutes) as total_playtime
                        FROM played_games
                        WHERE genre IS NOT NULL AND genre != ''
                        AND total_playtime_minutes > 0
                        GROUP BY genre
                        ORDER BY total_playtime DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['genre'] if result else None

                elif dynamic_query_type == "most_popular_genre_by_views":
                    # Which genre has the most total YouTube views
                    cur.execute("""
                        SELECT genre, SUM(youtube_views) as total_views
                        FROM played_games
                        WHERE genre IS NOT NULL AND genre != ''
                        AND youtube_views > 0
                        GROUP BY genre
                        ORDER BY total_views DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['genre'] if result else None

                elif dynamic_query_type == "genre_with_most_completed_games":
                    # Which genre has the most completed games
                    cur.execute("""
                        SELECT genre, COUNT(*) as completed_count
                        FROM played_games
                        WHERE genre IS NOT NULL AND genre != ''
                        AND completion_status = 'completed'
                        GROUP BY genre
                        ORDER BY completed_count DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['genre'] if result else None

                # ===== PHASE 2: MEMORABLE MILESTONES =====
                elif dynamic_query_type == "longest_completed_game":
                    # Longest game Jonesy has completed (by playtime)
                    cur.execute("""
                        SELECT canonical_name, total_playtime_minutes
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND total_playtime_minutes > 0
                        ORDER BY total_playtime_minutes DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['canonical_name'] if result else None

                elif dynamic_query_type == "shortest_completed_game":
                    # Shortest completed game (by playtime)
                    cur.execute("""
                        SELECT canonical_name, total_playtime_minutes
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND total_playtime_minutes > 0
                        ORDER BY total_playtime_minutes ASC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['canonical_name'] if result else None

                elif dynamic_query_type == "first_game_ever_played":
                    # First game on the channel (earliest first_played_date)
                    cur.execute("""
                        SELECT canonical_name, first_played_date
                        FROM played_games
                        WHERE first_played_date IS NOT NULL
                        ORDER BY first_played_date ASC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['canonical_name'] if result else None

                elif dynamic_query_type == "most_recent_completed_game":
                    # Most recently completed game
                    cur.execute("""
                        SELECT canonical_name, first_played_date
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND first_played_date IS NOT NULL
                        ORDER BY first_played_date DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['canonical_name'] if result else None

                elif dynamic_query_type == "oldest_completed_game_by_release":
                    # Oldest game (by release year) that Jonesy has completed
                    cur.execute("""
                        SELECT canonical_name, release_year
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND release_year IS NOT NULL
                        ORDER BY release_year ASC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['canonical_name'] if result else None

                elif dynamic_query_type == "newest_completed_game_by_release":
                    # Newest game (by release year) that Jonesy has completed
                    cur.execute("""
                        SELECT canonical_name, release_year
                        FROM played_games
                        WHERE completion_status = 'completed'
                        AND release_year IS NOT NULL
                        ORDER BY release_year DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['canonical_name'] if result else None

                # ===== PHASE 3: SERIES KNOWLEDGE & ENGAGEMENT =====
                elif dynamic_query_type == "series_with_most_games":
                    # Which series has the most games played
                    cur.execute("""
                        SELECT series_name, COUNT(*) as game_count
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        GROUP BY series_name
                        ORDER BY game_count DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                elif dynamic_query_type == "series_total_playtime":
                    # Total playtime for a specific series (requires parameter)
                    if not parameter:
                        return None

                    cur.execute("""
                        SELECT series_name, SUM(total_playtime_minutes) as total_playtime
                        FROM played_games
                        WHERE LOWER(series_name) = %s
                        AND total_playtime_minutes > 0
                        GROUP BY series_name
                    """, (parameter.lower(),))
                    result = cur.fetchone()

                    if result:
                        total_minutes = cast(RealDictRow, result)['total_playtime']
                        total_hours = int(total_minutes / 60)
                        return f"{total_hours} hours"
                    return None

                elif dynamic_query_type == "series_with_most_completed_games":
                    # Series with the most completed games
                    cur.execute("""
                        SELECT series_name, COUNT(*) as completed_count
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        AND completion_status = 'completed'
                        GROUP BY series_name
                        ORDER BY completed_count DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                elif dynamic_query_type == "most_incomplete_series":
                    # Series with the most incomplete games
                    cur.execute("""
                        SELECT series_name, COUNT(*) as incomplete_count
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        AND completion_status != 'completed'
                        GROUP BY series_name
                        ORDER BY incomplete_count DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                elif dynamic_query_type == "longest_average_series_length":
                    # Series with the longest average playtime per game
                    cur.execute("""
                        SELECT series_name, AVG(total_playtime_minutes) as avg_playtime
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        AND total_playtime_minutes > 0
                        GROUP BY series_name
                        HAVING COUNT(*) >= 2
                        ORDER BY avg_playtime DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                # ===== PHASE 4: ADVANCED PATTERNS =====
                elif dynamic_query_type == "best_views_per_episode":
                    # Game with the best engagement rate (views per episode)
                    cur.execute("""
                        SELECT canonical_name,
                               (youtube_views::float / NULLIF(total_episodes, 0)) as engagement_rate
                        FROM played_games
                        WHERE youtube_views > 0
                        AND total_episodes > 0
                        AND youtube_playlist_url IS NOT NULL
                        ORDER BY engagement_rate DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['canonical_name'] if result else None

                elif dynamic_query_type == "youtube_only_count":
                    # Count of YouTube-exclusive games
                    cur.execute("""
                        SELECT COUNT(*) as count
                        FROM played_games
                        WHERE youtube_playlist_url IS NOT NULL
                        AND youtube_playlist_url != ''
                        AND (twitch_vod_urls IS NULL OR twitch_vod_urls = '' OR twitch_vod_urls = '{}')
                    """)
                    result = cur.fetchone()
                    count = cast(RealDictRow, result)['count'] if result else 0
                    return str(count)

                elif dynamic_query_type == "twitch_only_count":
                    # Count of Twitch-exclusive games
                    cur.execute("""
                        SELECT COUNT(*) as count
                        FROM played_games
                        WHERE (twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}')
                        AND (youtube_playlist_url IS NULL OR youtube_playlist_url = '')
                    """)
                    result = cur.fetchone()
                    count = cast(RealDictRow, result)['count'] if result else 0
                    return str(count)

                elif dynamic_query_type == "most_cross_platform_series":
                    # Series played on both YouTube and Twitch
                    cur.execute("""
                        SELECT series_name, COUNT(*) as cross_platform_count
                        FROM played_games
                        WHERE series_name IS NOT NULL AND series_name != ''
                        AND youtube_playlist_url IS NOT NULL AND youtube_playlist_url != ''
                        AND twitch_vod_urls IS NOT NULL AND twitch_vod_urls != '' AND twitch_vod_urls != '{}'
                        GROUP BY series_name
                        ORDER BY cross_platform_count DESC
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['series_name'] if result else None

                elif dynamic_query_type == "total_completed_count":
                    # Total number of completed games
                    cur.execute("""
                        SELECT COUNT(*) as count
                        FROM played_games
                        WHERE completion_status = 'completed'
                    """)
                    result = cur.fetchone()
                    count = cast(RealDictRow, result)['count'] if result else 0
                    return str(count)

                elif dynamic_query_type == "completion_rate_percentage":
                    # Overall completion rate as a percentage
                    cur.execute("""
                        SELECT
                            COUNT(CASE WHEN completion_status = 'completed' THEN 1 END)::float /
                            NULLIF(COUNT(*), 0) * 100 as completion_rate
                        FROM played_games
                    """)
                    result = cur.fetchone()
                    if result:
                        rate = cast(RealDictRow, result)['completion_rate']
                        return f"{int(rate)}%"
                    return None

                else:
                    return None  # Unknown query type

                # Build and execute the final query (for non-genre/series queries)
                if where_clauses:  # Only execute if we have a traditional query
                    full_query = f"{base_query} WHERE {' AND '.join(where_clauses)} {order_by} LIMIT 1"
                    cur.execute(full_query, tuple(params))
                    result = cur.fetchone()
                    return cast(RealDictRow, result)['canonical_name'] if result else None

                return None
        except Exception as e:
            logger.error(f"Error calculating dynamic answer for {dynamic_query_type}: {e}")
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

    def get_recent_question_patterns(self, limit: int = 10) -> List[str]:
        """
        ✅ FIX #3: Get recently used question patterns for diversity enforcement

        Analyzes recent questions to identify patterns and prevent repetition.
        Returns list of pattern identifiers from recently used/added questions.
        """
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cur:
                # Get recently used questions (last 10 sessions) + recently added questions
                cur.execute("""
                    SELECT DISTINCT q.question_text, q.created_at, q.last_used_at
                    FROM trivia_questions q
                    WHERE q.is_active = TRUE
                    AND (q.last_used_at IS NOT NULL OR q.created_at > NOW() - INTERVAL '7 days')
                    ORDER BY COALESCE(q.last_used_at, q.created_at) DESC
                    LIMIT %s
                """, (limit,))

                recent_questions = cur.fetchall()
                patterns = []

                for row in recent_questions:
                    question_text = dict(row)['question_text'].lower()

                    # Identify pattern types
                    if ' or ' in question_text and ('first' in question_text or 'before' in question_text):
                        patterns.append('comparison_temporal')
                    elif ' vs ' in question_text or ' or ' in question_text:
                        patterns.append('comparison_choice')
                    elif 'most' in question_text or 'longest' in question_text or 'highest' in question_text:
                        patterns.append('superlative_most')
                    elif 'least' in question_text or 'shortest' in question_text or 'lowest' in question_text:
                        patterns.append('superlative_least')
                    elif 'first' in question_text and 'play' in question_text:
                        patterns.append('temporal_first')
                    elif 'completed' in question_text or 'finished' in question_text:
                        patterns.append('completion_status')
                    elif 'how many' in question_text:
                        patterns.append('count_query')
                    else:
                        patterns.append('general')

                logger.info(f"Recent question patterns: {patterns[:5]}")
                return patterns

        except Exception as e:
            logger.error(f"Error getting recent question patterns: {e}")
            return []

    def should_avoid_pattern(self, pattern: str, recent_patterns: List[str], threshold: int = 3) -> bool:
        """
        ✅ FIX #3: Check if a pattern has been overused recently

        Args:
            pattern: The pattern to check
            recent_patterns: List of recently used patterns
            threshold: Maximum allowed occurrences before avoiding (default: 3 out of 10)

        Returns:
            True if pattern should be avoided, False if it's okay to use
        """
        if not recent_patterns:
            return False

        # Count occurrences of this pattern in recent questions
        pattern_count = recent_patterns.count(pattern)

        # If pattern appears more than threshold times, avoid it
        should_avoid = pattern_count >= threshold

        if should_avoid:
            logger.info(f"Pattern '{pattern}' overused ({pattern_count}/{len(recent_patterns)}), avoiding")

        return should_avoid

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
                    normalized_new_answer = self.normalize_trivia_answer(question_answer).lower()
                    
                    for existing in existing_questions:
                        existing_dict = dict(existing)
                        existing_answer = existing_dict.get('correct_answer')
                        existing_status = existing_dict.get('status', '')
                        
                        if not existing_answer:
                            continue
                        
                        normalized_existing_answer = self.normalize_trivia_answer(existing_answer).lower()
                        
                        # Check if answers match
                        if normalized_new_answer == normalized_existing_answer:
                            # Same answer as RETIRED question - very strict (auto-reject territory)
                            if existing_status == 'retired':
                                logger.warning(
                                    f"⚠️ ANSWER DUPLICATE (RETIRED): New question has same answer '{question_answer}' as retired question #{existing_dict['id']}")
                                return {
                                    'duplicate_id': existing_dict['id'],
                                    'duplicate_text': existing_dict.get('question_text', ''),
                                    'similarity_score': 1.0,  # Perfect match on answer
                                    'status': existing_status,
                                    'created_at': existing_dict.get('created_at'),
                                    'match_type': 'answer_retired',
                                    'is_retired': True,
                                    'duplicate_reason': f"Same answer as retired question: '{question_answer}'"
                                }
                            
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
                new_question_concepts = self._extract_question_concepts(question_text)

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
                    existing_concepts = self._extract_question_concepts(existing_text)
                    concept_similarity = self._calculate_concept_similarity(
                        new_question_concepts, existing_concepts
                    )

                    # ✅ FIX #2: Use combined similarity score
                    combined_similarity = max(text_similarity, concept_similarity)

                    # ✅ FIX #2: Lower threshold for retired questions (be stricter)
                    # Changed from 0.85 to 0.65 to catch more semantic variations (e.g., "most views" questions)
                    effective_threshold = similarity_threshold * 0.65 if existing_status == 'retired' else similarity_threshold

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

    def _extract_question_concepts(self, question_text: str) -> set:
        """
        ✅ FIX #2: Extract key concepts from a question for semantic similarity

        Identifies: game titles, series, metrics (episodes, playtime), comparisons, completion status
        """
        import re

        concepts = set()
        text_lower = question_text.lower()

        # Key metrics and data points
        metrics = [
            'episodes',
            'playtime',
            'views',
            'time',
            'hours',
            'completed',
            'finished',
            'first',
            'longest',
            'shortest',
            'most',
            'least']
        for metric in metrics:
            if metric in text_lower:
                concepts.add(f"metric:{metric}")

        # Completion-related concepts
        if any(word in text_lower for word in ['completed', 'finished', 'beat', 'completion']):
            concepts.add('concept:completion')

        # Comparison-related concepts
        if any(word in text_lower for word in [' or ', ' vs ', 'between', 'compare']):
            concepts.add('concept:comparison')

        # Time-related concepts
        if any(word in text_lower for word in ['first', 'last', 'recent', 'oldest', 'newest', 'before', 'after']):
            concepts.add('concept:temporal')

        # Superlative concepts (most/least)
        if any(
            word in text_lower for word in [
                'most',
                'least',
                'highest',
                'lowest',
                'best',
                'worst',
                'longest',
                'shortest']):
            concepts.add('concept:superlative')

        # Extract potential game/series names (capitalized words or quoted text)
        capitalized_words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question_text)
        for word in capitalized_words:
            if word.lower() not in ['jonesy', 'captain', 'youtube', 'twitch']:
                concepts.add(f"entity:{word.lower()}")

        return concepts

    def _calculate_concept_similarity(self, concepts1: set, concepts2: set) -> float:
        """
        ✅ FIX #2: Calculate similarity based on concept overlap

        Uses Jaccard similarity: intersection / union
        """
        if not concepts1 or not concepts2:
            return 0.0

        intersection = len(concepts1.intersection(concepts2))
        union = len(concepts1.union(concepts2))

        if union == 0:
            return 0.0

        return intersection / union

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
                        SELECT ts.*, tq.question_text, ts.calculated_answer, tq.correct_answer
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

    # --- M


# Export
__all__ = ['TriviaDatabase']
