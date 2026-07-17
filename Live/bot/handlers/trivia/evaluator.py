import random
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ..ai_handler import _get_db, pacific_tz


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