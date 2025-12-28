"""
AI Question Validation Module

PHASE 3: Enhanced validation system for batch-generated trivia questions.
Provides answer verification, confidence scoring, and quality assurance.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def validate_trivia_question(
    question_dict: Dict[str, Any],
    db,
    auto_approve_threshold: float = 0.90
) -> Tuple[bool, float, List[str]]:
    """
    PHASE 3: Validate a trivia question with answer verification and confidence scoring.

    Args:
        question_dict: Question data with question_text, correct_answer, etc.
        db: Database instance for verification queries
        auto_approve_threshold: Confidence threshold for auto-approval (default 0.90)

    Returns:
        Tuple of (should_approve, confidence_score, warnings)
        - should_approve: True if confidence >= threshold
        - confidence_score: 0.0-1.0 quality score
        - warnings: List of quality issues found
    """

    if not db:
        return False, 0.0, ["Database not available for validation"]

    warnings: List[str] = []
    confidence_score = 1.0  # Start at perfect, deduct for issues

    question_text = question_dict.get("question_text", "")
    correct_answer = question_dict.get("correct_answer", "")
    category = question_dict.get("category", "unknown")

    # Validation 1: Answer Verification
    answer_verified, answer_confidence, answer_warnings = _verify_answer_accuracy(
        question_text, correct_answer, category, db
    )

    if not answer_verified:
        confidence_score *= answer_confidence
        warnings.extend(answer_warnings)

    # Validation 2: Question Clarity Check
    clarity_score, clarity_warnings = _check_question_clarity(question_text)
    confidence_score *= clarity_score
    warnings.extend(clarity_warnings)

    # Validation 3: Grammar and Structure
    grammar_score, grammar_warnings = _check_grammar_structure(question_text, correct_answer)
    confidence_score *= grammar_score
    warnings.extend(grammar_warnings)

    # Decision: Auto-approve if confidence high enough
    should_approve = confidence_score >= auto_approve_threshold

    if should_approve:
        logger.info(f"✅ Question auto-approved (confidence: {confidence_score:.2%})")
    elif confidence_score >= 0.70:
        logger.info(f"⚠️ Question flagged for review (confidence: {confidence_score:.2%})")
    else:
        logger.warning(f"❌ Question rejected (confidence: {confidence_score:.2%})")

    return should_approve, confidence_score, warnings


def _verify_answer_accuracy(
    question_text: str,
    correct_answer: str,
    category: str,
    db
) -> Tuple[bool, float, List[str]]:
    """Verify the answer is factually correct against database"""

    warnings: List[str] = []
    confidence = 1.0

    question_lower = question_text.lower()

    try:
        # Check "most time" / playtime questions
        if any(phrase in question_lower for phrase in ["most time", "longest playtime", "spent the most time"]):
            games_by_playtime = db.get_games_by_playtime(order='DESC', limit=1)
            if games_by_playtime:
                actual_answer = games_by_playtime[0]['canonical_name']
                if actual_answer.lower() != correct_answer.lower():
                    warnings.append(f"Answer mismatch: DB says '{actual_answer}', question says '{correct_answer}'")
                    confidence = 0.3  # Low confidence - wrong answer
                    return False, confidence, warnings

        # Check "most episodes" questions
        elif any(phrase in question_lower for phrase in ["most episodes", "episode count"]):
            games_by_episodes = db.get_games_by_episode_count(order='DESC', limit=1)
            if games_by_episodes:
                actual_answer = games_by_episodes[0]['canonical_name']
                if actual_answer.lower() != correct_answer.lower():
                    warnings.append(f"Answer mismatch: DB says '{actual_answer}', question says '{correct_answer}'")
                    confidence = 0.3
                    return False, confidence, warnings

        # Check "first played" / "oldest" questions
        elif "first" in question_lower or "oldest" in question_lower:
            if "release year" in question_lower:
                games_by_release = db.get_games_by_release_year(order='ASC', limit=1)
                if games_by_release:
                    actual_answer = games_by_release[0]['canonical_name']
                    if actual_answer.lower() != correct_answer.lower():
                        warnings.append(f"Answer mismatch for oldest game: DB says '{actual_answer}'")
                        confidence = 0.3
                        return False, confidence, warnings
            elif "played" in question_lower:
                games_by_date = db.get_games_by_played_date(order='ASC', limit=1)
                if games_by_date:
                    actual_answer = games_by_date[0]['canonical_name']
                    if actual_answer.lower() != correct_answer.lower():
                        warnings.append(f"Answer mismatch for first played: DB says '{actual_answer}'")
                        confidence = 0.3
                        return False, confidence, warnings

        # Check "most views" questions
        elif "most views" in question_lower or "most popular" in question_lower:
            if "youtube" in question_lower:
                # Would need a get_games_by_youtube_views method
                pass  # Skip verification if method doesn't exist
            elif "twitch" in question_lower:
                games_by_twitch = db.get_games_by_twitch_views(limit=1)
                if games_by_twitch:
                    actual_answer = games_by_twitch[0]['canonical_name']
                    if actual_answer.lower() != correct_answer.lower():
                        warnings.append(f"Answer mismatch for Twitch views: DB says '{actual_answer}'")
                        confidence = 0.3
                        return False, confidence, warnings

        # Verify answer exists in database
        game_exists = db.played_game_exists(correct_answer)
        if not game_exists:
            warnings.append(f"Game '{correct_answer}' not found in database")
            confidence = 0.5  # Medium confidence - might be alternate name
            return False, confidence, warnings

        return True, 1.0, []

    except Exception as e:
        logger.error(f"Error verifying answer: {e}")
        warnings.append(f"Verification error: {str(e)}")
        return False, 0.7, warnings


def _check_question_clarity(question_text: str) -> Tuple[float, List[str]]:
    """Check for ambiguous or unclear phrasing"""

    warnings: List[str] = []
    clarity_score = 1.0

    question_lower = question_text.lower()

    # Check for removed "most played" ambiguity (should never appear after removal)
    if "most played" in question_lower and "time" not in question_lower and "episodes" not in question_lower:
        warnings.append("CRITICAL: 'most played' without clarifying 'time' or 'episodes' - AMBIGUOUS")
        clarity_score = 0.2  # Very low - this was explicitly removed

    # Check for unclear terminology
    ambiguous_phrases = [
        ("longest game", ["time", "episodes"]),  # Should specify which
        ("biggest game", ["size", "episodes", "time"]),
        ("shortest game", ["time", "episodes"]),
    ]

    for phrase, clarifiers in ambiguous_phrases:
        if phrase in question_lower:
            has_clarifier = any(clarifier in question_lower for clarifier in clarifiers)
            if not has_clarifier:
                warnings.append(f"Ambiguous: '{phrase}' needs clarification (time vs episodes)")
                clarity_score *= 0.7

    # Check question length (too long = verbose)
    if len(question_text) > 200:
        warnings.append("Question too verbose (>200 chars)")
        clarity_score *= 0.9

    # Check for proper question format
    if not question_text.strip().endswith('?'):
        warnings.append("Question doesn't end with '?'")
        clarity_score *= 0.95

    return clarity_score, warnings


def _check_grammar_structure(question_text: str, correct_answer: str) -> Tuple[float, List[str]]:
    """Basic grammar and structure checks"""

    warnings: List[str] = []
    grammar_score = 1.0

    # Check for empty fields
    if not question_text or not question_text.strip():
        warnings.append("Empty question text")
        return 0.0, warnings

    if not correct_answer or not correct_answer.strip():
        warnings.append("Empty answer")
        return 0.0, warnings

    # Check capitalization
    if not question_text[0].isupper():
        warnings.append("Question doesn't start with capital letter")
        grammar_score *= 0.98

    # Check for multiple question marks (unusual)
    if question_text.count('?') > 1:
        warnings.append("Multiple question marks")
        grammar_score *= 0.95

    # Check answer is reasonable length
    if len(correct_answer) > 100:
        warnings.append("Answer suspiciously long (>100 chars)")
        grammar_score *= 0.85

    return grammar_score, warnings


def get_validation_summary(confidence_score: float, warnings: List[str]) -> str:
    """Generate human-readable validation summary"""

    if confidence_score >= 0.90:
        status = "✅ HIGH CONFIDENCE - Auto-approved"
    elif confidence_score >= 0.70:
        status = "⚠️ MEDIUM CONFIDENCE - Requires review"
    else:
        status = "❌ LOW CONFIDENCE - Rejected"

    summary = f"{status} ({confidence_score:.1%})\n"

    if warnings:
        summary += "\nIssues found:\n"
        for warning in warnings:
            summary += f"  • {warning}\n"
    else:
        summary += "\nNo issues found - excellent quality!\n"

    return summary


__all__ = [
    'validate_trivia_question',
    'get_validation_summary'
]
