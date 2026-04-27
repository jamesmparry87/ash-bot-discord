"""
Trivia Question Parsing and Validation Utilities

Handles parsing of various trivia question formats and validation
of question quality and correctness.
"""

import re
from typing import Optional


def is_natural_multiple_choice_format(content: str) -> bool:
    """
    Check if content is in natural multiple choice format for user-friendly question submission

    This allows moderators to submit questions in a readable format like:
    What is the capital of France?
    A. London
    B. Paris
    C. Berlin
    D. Madrid
    Correct answer: B

    Args:
        content (str): The raw input content from the user

    Returns:
        bool: True if content matches natural multiple choice format
    """
    # Split content into individual lines for analysis
    lines = content.strip().split('\n')

    # Basic validation: Need at least question + 2 choices + answer line
    if len(lines) < 4:
        return False

    # Pattern to match choice lines: "A. option" or "A) option"
    choice_pattern = re.compile(r'^[A-D][.)]\s+.+', re.IGNORECASE)
    choice_count = 0

    # Count how many lines match the choice pattern
    for line in lines:
        if choice_pattern.match(line.strip()):
            choice_count += 1

    # Look for answer indication line
    has_answer_line = any(
        'correct answer' in line.lower() or 'answer:' in line.lower()
        for line in lines
    )

    # Valid if we have at least 2 choices and an answer line
    return choice_count >= 2 and has_answer_line


def parse_natural_multiple_choice(content: str) -> Optional[dict]:
    """
    Parse natural multiple choice format into structured data
    
    Args:
        content: Raw multi-line content with question, choices, and answer
        
    Returns:
        dict with 'question', 'choices', 'answer' or None if parsing fails
    """
    lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
    if not lines:
        return None

    question_text = ""
    choices = []
    correct_answer = ""

    # Find question (usually first line without A. B. C. pattern and not answer line)
    choice_pattern = re.compile(r'^[A-D][.)]\s+(.+)', re.IGNORECASE)
    answer_pattern = re.compile(r'(?:correct\s+answer:?\s*|answer:?\s*)([A-D])', re.IGNORECASE)

    for line in lines:
        # Check if this is a choice line
        choice_match = choice_pattern.match(line)
        if choice_match:
            choices.append(choice_match.group(1).strip())
            continue

        # Check if this is the answer line
        answer_match = answer_pattern.search(line)
        if answer_match:
            correct_answer = answer_match.group(1).upper()
            continue

        # If not a choice or answer, assume it's part of the question
        if not question_text:
            question_text = line
        else:
            question_text += " " + line

    # Basic validation
    if not question_text or len(choices) < 2 or not correct_answer:
        return None

    # Apply comprehensive validation
    validation = validate_multiple_choice_options(choices, correct_answer)
    if not validation['valid']:
        print(f"Multiple choice validation failed: {validation['error']}")
        return None

    return {
        'question': question_text.strip(),
        'choices': choices,
        'answer': correct_answer,
    }


def validate_multiple_choice_options(choices: list, correct_answer: str) -> dict:
    """
    Validate multiple choice options for count and consistency

    Ensures:
    - Minimum 2 options (required for multiple choice)
    - Maximum 4 options (A, B, C, D limit)
    - Correct answer letter corresponds to valid option
    - No empty options

    Args:
        choices: List of choice strings
        correct_answer: Correct answer letter (A-D)

    Returns:
        dict with 'valid' (bool) and 'error' (str if invalid)
    """
    # Check minimum options
    if len(choices) < 2:
        return {
            'valid': False,
            'error': f"Multiple choice requires at least 2 options (found {len(choices)})"
        }

    # Check maximum options
    if len(choices) > 4:
        return {
            'valid': False,
            'error': f"Multiple choice limited to 4 options (A-D), found {len(choices)}"
        }

    # Check for empty options
    for i, choice in enumerate(choices):
        if not choice or not choice.strip():
            return {
                'valid': False,
                'error': f"Option {chr(65+i)} is empty"
            }

    # Validate correct answer letter
    if not correct_answer or len(correct_answer) != 1:
        return {
            'valid': False,
            'error': "Correct answer must be a single letter (A-D)"
        }

    correct_answer_upper = correct_answer.upper()
    if correct_answer_upper not in ['A', 'B', 'C', 'D']:
        return {
            'valid': False,
            'error': f"Correct answer must be A, B, C, or D (got '{correct_answer}')"
        }

    # Check if correct answer corresponds to available option
    choice_index = ord(correct_answer_upper) - ord('A')
    if choice_index >= len(choices):
        return {
            'valid': False,
            'error': f"Correct answer '{correct_answer_upper}' exceeds available options (only {len(choices)} options: {chr(65)}-{chr(64+len(choices))})"
        }

    # All validations passed
    return {'valid': True, 'error': None}


def validate_question_quality(question_data: dict) -> tuple[bool, str, float]:
    """
    Validate AI-generated question quality before approval.

    Checks for:
    - Question clarity and completeness
    - Answer appropriateness
    - No ambiguity or multiple interpretations
    - Fan-answerable difficulty

    Args:
        question_data: Dict with 'question_text', 'correct_answer', etc.

    Returns:
        tuple: (is_valid, reason, quality_score)
    """
    question_text = question_data.get('question_text', '')
    answer = question_data.get('correct_answer', '')

    # Quality score starts at 100
    quality_score = 100.0
    issues = []

    # Check question length (not too short, not too long)
    if len(question_text) < 15:
        quality_score -= 40
        issues.append("Question too short")
    elif len(question_text) > 200:
        quality_score -= 20
        issues.append("Question too verbose")

    # Check for question mark
    if not question_text.endswith('?'):
        quality_score -= 10
        issues.append("Missing question mark")

    # Check answer length (reasonable)
    if len(answer) < 2:
        quality_score -= 30
        issues.append("Answer too short")
    elif len(answer) > 100:
        quality_score -= 15
        issues.append("Answer too long")

    # Check for problematic patterns
    bad_patterns = [
        ('exact number', r'\d{4,}'),  # Exact large numbers (too specific)
        ('placeholder text', r'\[.*?\]'),  # [placeholder] format
        ('multiple questions', r'\?.*\?'),  # Multiple question marks
        ('incomplete', r'\.\.\.$'),  # Trailing ellipsis
    ]

    for pattern_name, pattern in bad_patterns:
        if re.search(pattern, question_text):
            quality_score -= 25
            issues.append(f"Contains {pattern_name}")

    # Check for ambiguous words
    ambiguous_words = ['maybe', 'approximately', 'around', 'roughly', 'about']
    if any(word in question_text.lower() for word in ambiguous_words):
        quality_score -= 10
        issues.append("Contains ambiguous language")

    # Reject if quality score too low
    is_valid = quality_score >= 60  # Minimum 60% quality
    reason = "; ".join(issues) if issues else "Quality check passed"

    return is_valid, reason, quality_score
