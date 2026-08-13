import difflib
import random
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..ai_handler import _get_db, pacific_tz


def normalize_trivia_answer(answer_text: str) -> str:
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
        'pokemon': 'pokÃ©mon',
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


def evaluate_answer(user_answer: str, correct_answer: str, question_type: str, multiple_choice_options: Optional[List[str]] = None) -> Tuple[float, str]:
    """
    Evaluate a trivia answer with enhanced fuzzy matching.
    Returns: (score, match_type) where score is 0.0-1.0
    """
    import difflib

    # Clean up inputs
    user_clean = user_answer.strip()
    correct_clean = correct_answer.strip()
    
    # Handle multiple choice letter mappings (A, B, C, D)
    if question_type == 'multiple_choice' and multiple_choice_options:
        import re

        # Check if the user answer is exactly a letter A-D (case insensitive), with optional period/parenthesis
        match = re.match(r'^([a-dA-D])[\.\)]?$', user_clean)
        if match:
            letter = match.group(1).upper()
            index = ord(letter) - ord('A')
            if 0 <= index < len(multiple_choice_options):
                # Replace user's letter guess with the actual full text from the options
                user_clean = multiple_choice_options[index].strip()

    # Normalize answers for better matching
    user_normalized = normalize_trivia_answer(user_clean)
    correct_normalized = normalize_trivia_answer(correct_clean)

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
    if _contains_numbers(correct_clean) and _contains_numbers(user_clean):
        correct_nums = _extract_numbers(correct_clean)
        answer_nums = _extract_numbers(user_clean)

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
    if _check_abbreviation_match(user_clean, correct_clean):
        return 1.0, "abbreviation_match"

    # Level 8: Weak similarity for debugging
    if similarity_exact >= 0.3:
        return similarity_exact, "weak_similarity"

    return 0.0, "no_match"


def _normalize_answer_for_matching(answer: str) -> str:
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


def _contains_numbers(text: str) -> bool:
    """Check if text contains numbers"""
    import re
    return bool(re.search(r'\d', text))


def _extract_numbers(text: str) -> list[float]:
    """Extract numbers from text"""
    import re
    numbers = re.findall(r'\d+\.?\d*', text)
    return [float(num) for num in numbers]


def _check_abbreviation_match(answer: str, correct: str) -> bool:
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
