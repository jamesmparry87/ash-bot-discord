from typing import Tuple
import re
import difflib
import random
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ..ai_handler import _get_db, pacific_tz

question_history = {
    "last_questions": [],
    "template_usage": {},
    "category_cooldowns": {}
}


def execute_answer_logic(logic: str, games_data: List[Dict[str, Any]], template: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the answer logic and return question data"""
    import random
    from collections import Counter

    if logic == "compare_episodes":
        # Pick two games with episode data
        games_with_episodes = [g for g in games_data if g.get("total_episodes", 0) > 0]
        if len(games_with_episodes) >= 2:
            game1, game2 = random.sample(games_with_episodes, 2)
            winner = game1 if game1.get("total_episodes", 0) > game2.get("total_episodes", 0) else game2
            return {
                "question_text": template["template"].format(
                    game1=game1["canonical_name"],
                    game2=game2["canonical_name"]),
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"}

    elif logic == "compare_playtime":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if len(games_with_playtime) >= 2:
            game1, game2 = random.sample(games_with_playtime, 2)
            winner = game1 if game1.get("total_playtime_minutes", 0) > game2.get("total_playtime_minutes", 0) else game2
            return {
                "question_text": template["template"].format(
                    game1=game1["canonical_name"],
                    game2=game2["canonical_name"]),
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"}

    elif logic == "max_episodes":
        games_with_episodes = [g for g in games_data if g.get("total_episodes", 0) > 0]
        if games_with_episodes:
            winner = max(games_with_episodes, key=lambda x: x.get("total_episodes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "max_playtime":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if games_with_playtime:
            winner = max(games_with_playtime, key=lambda x: x.get("total_playtime_minutes", 0))
            playtime_minutes = winner.get("total_playtime_minutes", 0)
            playtime_hours = round(playtime_minutes / 60, 1)
            episodes = winner.get("total_episodes", 0)

            return {
                "question_text": template["template"],
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer",
                "context_data": {  # Add context for better responses
                    "playtime_minutes": playtime_minutes,
                    "playtime_hours": playtime_hours,
                    "total_episodes": episodes
                }
            }

    elif logic == "completion_percentage":
        completed = len([g for g in games_data if g.get("completion_status") == "completed"])
        percentage = round((completed / len(games_data)) * 100) if games_data else 0
        return {
            "question_text": template["template"],
            "correct_answer": f"{percentage}%",
            "question_type": "single_answer"
        }

    elif logic == "most_common_genre":
        genres = [g.get("genre") for g in games_data if g.get("genre")]
        if genres:
            most_common = Counter(genres).most_common(1)[0][0]
            return {
                "question_text": template["template"],
                "correct_answer": most_common,
                "question_type": "single_answer"
            }

    elif logic == "unique_genres_count":
        genres = [g.get("genre") for g in games_data if g.get("genre")]
        unique_count = len(set(genres)) if genres else 0
        return {
            "question_text": template["template"],
            "correct_answer": str(unique_count),
            "question_type": "single_answer"
        }

    elif logic == "first_completed_game":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        if completed_games:
            # Use the first game in the list as a simple implementation
            first_completed = completed_games[0]
            return {
                "question_text": template["template"],
                "correct_answer": first_completed["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "shortest_completed_game":
        completed_games = [
            g for g in games_data if g.get("completion_status") == "completed" and g.get(
                "total_playtime_minutes", 0) > 0]
        if completed_games:
            shortest = min(completed_games, key=lambda x: x.get("total_playtime_minutes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": shortest["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "most_recent_completion":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        if completed_games:
            # Use last game in list as most recent (simple implementation)
            most_recent = completed_games[-1]
            return {
                "question_text": template["template"],
                "correct_answer": most_recent["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "largest_series":
        series_counts = Counter([g.get("series_name") for g in games_data if g.get("series_name")])
        if series_counts:
            largest_series = series_counts.most_common(1)[0][0]
            return {
                "question_text": template["template"],
                "correct_answer": largest_series,
                "question_type": "single_answer"
            }

    elif logic == "mc_longest_game":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if len(games_with_playtime) >= 3:
            # Pick the longest game and 3 others for choices
            longest = max(games_with_playtime, key=lambda x: x.get("total_playtime_minutes", 0))
            others = [g for g in games_with_playtime if g != longest]
            choices = [longest] + random.sample(others, min(3, len(others)))
            random.shuffle(choices)

            choice_names = [g["canonical_name"] for g in choices]
            correct_letter = chr(65 + choice_names.index(longest["canonical_name"]))  # A, B, C, D

            return {
                "question_text": template["template"],
                "correct_answer": correct_letter,
                "question_type": "multiple_choice",
                "multiple_choice_options": choice_names
            }

    elif logic == "mc_completed_game":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        incomplete_games = [g for g in games_data if g.get("completion_status") != "completed"]

        if len(completed_games) >= 1 and len(incomplete_games) >= 2:
            correct_game = random.choice(completed_games)
            wrong_games = random.sample(incomplete_games, min(3, len(incomplete_games)))
            choices = [correct_game] + wrong_games
            random.shuffle(choices)

            choice_names = [g["canonical_name"] for g in choices]
            correct_letter = chr(65 + choice_names.index(correct_game["canonical_name"]))

            return {
                "question_text": template["template"],
                "correct_answer": correct_letter,
                "question_type": "multiple_choice",
                "multiple_choice_options": choice_names
            }

    # === TEMPORAL GAMING TIMELINE LOGIC ===
    elif logic == "oldest_game_by_release":
        # Find oldest game by release year
        games_with_release = [g for g in games_data if g.get("release_year")]
        if games_with_release:
            oldest = min(games_with_release, key=lambda x: x.get("release_year", 9999))
            return {
                "question_text": template["template"],
                "correct_answer": oldest["canonical_name"],
                "question_type": "single_answer",
                "context_data": {
                    "release_year": oldest.get("release_year"),
                    "first_played_date": oldest.get("first_played_date")
                }
            }

    elif logic == "newest_game_by_release":
        # Find newest game by release year
        games_with_release = [g for g in games_data if g.get("release_year")]
        if games_with_release:
            newest = max(games_with_release, key=lambda x: x.get("release_year", 0))
            return {
                "question_text": template["template"],
                "correct_answer": newest["canonical_name"],
                "question_type": "single_answer",
                "context_data": {
                    "release_year": newest.get("release_year"),
                    "first_played_date": newest.get("first_played_date")
                }
            }

    elif logic == "first_played_game":
        # Find first game by first_played_date using get_gaming_timeline
        current_db = _get_db()
        if current_db and hasattr(current_db, 'get_gaming_timeline'):
            timeline = current_db.get_gaming_timeline(order='ASC')
            if timeline:
                first_game = timeline[0]
                return {
                    "question_text": template["template"],
                    "correct_answer": first_game["canonical_name"],
                    "question_type": "single_answer",
                    "context_data": {
                        "first_played_date": first_game.get("first_played_date"),
                        "release_year": first_game.get("release_year")
                    }
                }

    elif logic == "last_played_game":
        # Find most recently played game using get_gaming_timeline
        current_db = _get_db()
        if current_db and hasattr(current_db, 'get_gaming_timeline'):
            timeline = current_db.get_gaming_timeline(order='DESC')
            if timeline:
                last_game = timeline[0]
                return {
                    "question_text": template["template"],
                    "correct_answer": last_game["canonical_name"],
                    "question_type": "single_answer",
                    "context_data": {
                        "first_played_date": last_game.get("first_played_date"),
                        "release_year": last_game.get("release_year")
                    }
                }

    # ✅ NEW IMPLEMENTATIONS - Previously missing answer_logic functions

    elif logic == "latest_genre_game":
        # Find most recent game in a specific genre
        genre_filter = template.get("genre_filter", "").lower()
        if genre_filter:
            genre_games = [
                g for g in games_data if g.get(
                    "genre",
                    "").lower() == genre_filter and g.get("first_played_date")]
            if genre_games:
                # Sort by first_played_date descending to get latest
                latest = max(genre_games, key=lambda x: x.get("first_played_date", ""))
                return {
                    "question_text": template["template"],
                    "correct_answer": latest["canonical_name"],
                    "question_type": "single_answer"
                }

    elif logic == "longest_episodes_by_genre":
        # Find game with most episodes in a specific genre
        genre_filter = template.get("genre_filter", "").lower()
        if genre_filter:
            genre_games = [
                g for g in games_data if g.get(
                    "genre", "").lower() == genre_filter and g.get(
                    "total_episodes", 0) > 0]
            if genre_games:
                longest = max(genre_games, key=lambda x: x.get("total_episodes", 0))
                return {
                    "question_text": template["template"],
                    "correct_answer": longest["canonical_name"],
                    "question_type": "single_answer"
                }

    elif logic == "count_games_by_genre":
        # Count games in a specific genre
        genre_filter = template.get("genre_filter", "").lower()
        if genre_filter:
            genre_count = len([g for g in games_data if g.get("genre", "").lower() == genre_filter])
            return {
                "question_text": template["template"],
                "correct_answer": str(genre_count),
                "question_type": "single_answer"
            }

    elif logic == "most_youtube_views":
        # Find game with most YouTube views
        youtube_games = [g for g in games_data if g.get("youtube_views", 0) > 0]
        if youtube_games:
            top_game = max(youtube_games, key=lambda x: x.get("youtube_views", 0))
            return {
                "question_text": template["template"],
                "correct_answer": top_game["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "most_youtube_episodes":
        # Find longest YouTube playthrough by episode count
        youtube_games = [g for g in games_data if g.get("youtube_playlist_url") and g.get("total_episodes", 0) > 0]
        if youtube_games:
            longest = max(youtube_games, key=lambda x: x.get("total_episodes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": longest["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "count_both_platforms":
        # Count games on both YouTube and Twitch
        both_platforms = [g for g in games_data
                          if g.get("youtube_playlist_url") and
                          g.get("twitch_vod_urls") and
                          g.get("twitch_vod_urls") not in ['', '{}', None]]
        return {
            "question_text": template["template"],
            "correct_answer": str(len(both_platforms)),
            "question_type": "single_answer"
        }

    elif logic == "longest_dropped_game":
        # Find longest abandoned game by episode count
        dropped_games = [g for g in games_data
                         if g.get("completion_status") not in ["completed", "in_progress"] and
                         g.get("total_episodes", 0) > 0]
        if dropped_games:
            longest = max(dropped_games, key=lambda x: x.get("total_episodes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": longest["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "count_ongoing_games":
        # Count games with in_progress status
        ongoing_count = len([g for g in games_data if g.get("completion_status") == "in_progress"])
        return {
            "question_text": template["template"],
            "correct_answer": str(ongoing_count),
            "question_type": "single_answer"
        }

    elif logic == "series_most_time":
        # Find series with most total playtime
        series_playtime = {}
        for game in games_data:
            series = game.get("series_name")
            if series:
                series_playtime[series] = series_playtime.get(series, 0) + game.get("total_playtime_minutes", 0)

        if series_playtime:
            top_series = max(series_playtime.items(), key=lambda x: x[1])
            return {
                "question_text": template["template"],
                "correct_answer": top_series[0],
                "question_type": "single_answer"
            }

    elif logic == "unique_series_count":
        # Count unique game series
        series_set = {g.get("series_name") for g in games_data if g.get("series_name")}
        return {
            "question_text": template["template"],
            "correct_answer": str(len(series_set)),
            "question_type": "single_answer"
        }

    elif logic == "compare_completion_order":
        # Compare which of two games was completed first
        # Template should have {game1} and {game2} placeholders
        # This would need specific games - for now, pick two random completed games
        completed_games = [g for g in games_data if g.get(
            "completion_status") == "completed" and g.get("first_played_date")]
        if len(completed_games) >= 2:
            game1, game2 = random.sample(completed_games, 2)
            # Determine which was completed first (using first_played_date as proxy)
            first_completed = game1 if game1.get(
                "first_played_date", "") < game2.get(
                "first_played_date", "") else game2
            return {
                "question_text": template["template"].format(
                    game1=game1["canonical_name"],
                    game2=game2["canonical_name"]),
                "correct_answer": first_completed["canonical_name"],
                "question_type": "single_answer"
            }

    elif logic == "compare_play_order":
        # Compare which of two games was played first
        games_with_dates = [g for g in games_data if g.get("first_played_date")]
        if len(games_with_dates) >= 2:
            game1, game2 = random.sample(games_with_dates, 2)
            first_played = game1 if game1.get("first_played_date", "") < game2.get("first_played_date", "") else game2
            second_played = game2 if first_played == game1 else game1

            # Format answer: "before" or "after"
            answer = "before" if first_played == game1 else "after"

            return {
                "question_text": template["template"].format(
                    game1=game1["canonical_name"],
                    game2=game2["canonical_name"]),
                "correct_answer": answer,
                "question_type": "single_answer"
            }

    elif logic == "mc_genre_game":
        # Multiple choice: which game is in a specific genre
        genre_filter = template.get("genre_filter", "").lower()
        if genre_filter:
            genre_games = [g for g in games_data if g.get("genre", "").lower() == genre_filter]
            other_games = [g for g in games_data if g.get("genre", "").lower() != genre_filter]

            if len(genre_games) >= 1 and len(other_games) >= 2:
                correct_game = random.choice(genre_games)
                wrong_games = random.sample(other_games, min(3, len(other_games)))
                choices = [correct_game] + wrong_games
                random.shuffle(choices)

                choice_names = [g["canonical_name"] for g in choices]
                correct_letter = chr(65 + choice_names.index(correct_game["canonical_name"]))

                return {
                    "question_text": template["template"],
                    "correct_answer": correct_letter,
                    "question_type": "multiple_choice",
                    "multiple_choice_options": choice_names
                }

    # Fallback - return empty dict if logic couldn't execute
    return {}


def update_question_history(question_data: Dict[str, Any], category: str):
    """Update question history to track usage and implement cooldowns"""
    current_time = datetime.now(pacific_tz)

    # Add to recent questions list (keep last 10)
    question_history["last_questions"].append({
        "question": question_data.get("question_text", "")[:50],
        "category": category,
        "timestamp": current_time
    })
    if len(question_history["last_questions"]) > 10:
        question_history["last_questions"].pop(0)

    # Update template usage count
    template_id = question_data.get("question_text", "")[:20]
    question_history["template_usage"][template_id] = question_history["template_usage"].get(template_id, 0) + 1

    # Set category cooldown if used too recently
    recent_usage = sum(1 for q in question_history["last_questions"][-3:] if q["category"] == category)
    if recent_usage >= 2:  # Used 2 times in last 3 questions
        cooldown_duration = 30 * 60  # 30 minutes
        question_history["category_cooldowns"][category] = current_time + timedelta(seconds=cooldown_duration)
        print(f"⏰ Category '{category}' on cooldown for 30 minutes due to recent usage")


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


def evaluate_answer(user_answer: str, correct_answer: str, question_type: str) -> Tuple[float, str]:
    """
    Evaluate a trivia answer with enhanced fuzzy matching.
    Returns: (score, match_type) where score is 0.0-1.0
    """
    import difflib

    # Clean up inputs
    user_clean = user_answer.strip()
    correct_clean = correct_answer.strip()

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
