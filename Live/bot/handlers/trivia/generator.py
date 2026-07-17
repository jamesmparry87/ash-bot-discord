import json
import random
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ...config import CATEGORY_TEMPERATURES, JONESY_USER_ID, TRIVIA_CATEGORIES
from ..ai_handler import (
    _get_db,
    ai_enabled,
    call_ai_for_generation,
    call_ai_with_rate_limiting,
    pacific_tz,
    robust_json_parse,
)


def get_question_templates() -> Dict[str, List[Dict[str, Any]]]:
    """Get diverse question templates organized by category - IMPROVED for variety!"""
    return {
        # REMOVED: "most played" pattern (redundant and ambiguous)
        # Users found this question uninteresting and potentially confusing

        # ENHANCED: More genre variety
        "genre_insights": [
            {
                "template": "What horror game did Jonesy play most recently?",
                "answer_logic": "latest_genre_game",
                "type": "single_answer",
                "weight": 1.4,
                "genre_filter": "horror"
            },
            {
                "template": "Which RPG took Jonesy the most episodes to complete?",
                "answer_logic": "longest_episodes_by_genre",
                "type": "single_answer",
                "weight": 1.3,
                "genre_filter": "rpg"
            },
            {
                "template": "How many different horror games has Jonesy played?",
                "answer_logic": "count_games_by_genre",
                "type": "single_answer",
                "weight": 1.3,
                "genre_filter": "horror"
            },
            {
                "template": "What genre has Jonesy played the most games in?",
                "answer_logic": "most_common_genre",
                "type": "single_answer",
                "weight": 1.4
            }
        ],

        # NEW: Platform distinction (YouTube vs Twitch)
        "platform_detective": [
            {
                "template": "Which game has the most YouTube views?",
                "answer_logic": "most_youtube_views",
                "type": "single_answer",
                "weight": 1.5  # High engagement - real metrics
            },
            {
                "template": "What's Jonesy's longest YouTube playthrough by episodes?",
                "answer_logic": "most_youtube_episodes",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "How many games has Jonesy played on both YouTube and Twitch?",
                "answer_logic": "count_both_platforms",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # NEW: Temporal questions using release_year and first_played_date
        "temporal_gaming": [
            {
                "template": "What's the oldest game (by release year) that Jonesy has played?",
                "answer_logic": "oldest_game_by_release",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "What's the newest game in Jonesy's collection?",
                "answer_logic": "newest_game_by_release",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "Which game did Jonesy play first chronologically?",
                "answer_logic": "first_played_game",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # NEW: Completion status focus
        "completion_tracker": [
            {
                "template": "What percentage of Jonesy's games are completed?",
                "answer_logic": "completion_percentage",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "What's Jonesy's longest abandoned game (by episodes)?",
                "answer_logic": "longest_dropped_game",
                "type": "single_answer",
                "weight": 1.2
            },
            {
                "template": "How many games are currently ongoing?",
                "answer_logic": "count_ongoing_games",
                "type": "single_answer",
                "weight": 1.1
            }
        ],

        # ENHANCED: Series questions with more depth
        "series_master": [
            {
                "template": "Which series has Jonesy spent the most total time on?",
                "answer_logic": "series_most_time",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "What series has the most games in Jonesy's collection?",
                "answer_logic": "largest_series",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "How many different game series has Jonesy explored?",
                "answer_logic": "unique_series_count",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # IMPROVED: Gaming milestones (no playtime redundancy)
        "gaming_milestones": [
            {
                "template": "Which was Jonesy's first completed game?",
                "answer_logic": "first_completed_game",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "What's the shortest completed game by playtime?",
                "answer_logic": "shortest_completed_game",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # REFINED: Gaming stories (episode-focused, NOT playtime)
        "gaming_stories": [
            {
                "template": "What game took Jonesy the most episodes to complete?",
                "answer_logic": "max_episodes",
                "type": "single_answer",
                "weight": 1.3  # Clear distinction: episodes, not time
            },
            {
                "template": "What's the most recent game Jonesy completed?",
                "answer_logic": "most_recent_completion",
                "type": "single_answer",
                "weight": 1.4
            }
        ],

        # KEPT: Timeline comparisons (still engaging)
        "timeline_fun": [
            {
                "template": "Which game did Jonesy complete first - {game1} or {game2}?",
                "answer_logic": "compare_completion_order",
                "type": "single_answer",
                "weight": 1.3
            },
            {
                "template": "Did Jonesy play {game1} before or after {game2}?",
                "answer_logic": "compare_play_order",
                "type": "single_answer",
                "weight": 1.2
            }
        ],

        # KEPT: Multiple choice variety
        "multiple_choice_fun": [
            {
                "template": "Which of these games did Jonesy complete?",
                "answer_logic": "mc_completed_game",
                "type": "multiple_choice",
                "weight": 1.5
            },
            {
                "template": "Which horror game has Jonesy played?",
                "answer_logic": "mc_genre_game",
                "type": "multiple_choice",
                "weight": 1.4,
                "genre_filter": "horror"
            }
        ]
    }

def calculate_template_weights(templates: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """Calculate dynamic weights based on usage history and cooldowns"""
    current_time = datetime.now(pacific_tz)

    # Apply cooldowns and usage penalties
    for category, template_list in templates.items():
        # Category cooldown check
        category_cooldown = question_history["category_cooldowns"].get(category, None)
        if category_cooldown and current_time < category_cooldown:
            # Reduce weights for category in cooldown
            for template in template_list:
                template["weight"] *= 0.3

        # Individual template usage penalties
        for template in template_list:
            template_id = template.get("template", "")[:20]  # Use first 20 chars as ID
            usage_count = question_history["template_usage"].get(template_id, 0)

            # Apply usage penalty (more usage = lower weight)
            if usage_count > 0:
                penalty = max(0.2, 1.0 - (usage_count * 0.2))
                template["weight"] *= penalty

    return templates

def select_best_template(games_data: List[Dict[str, Any]],
                         avoid_templates: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Select the best template based on data availability and weights, avoiding recently used templates

    Args:
        games_data: List of game data dictionaries
        avoid_templates: List of recently used template IDs to avoid in this batch
    """
    templates = get_question_templates()
    weighted_templates = calculate_template_weights(templates)

    viable_templates = []

    # Check each template for data viability
    for category, template_list in weighted_templates.items():
        for template in template_list:
            # Check if we have enough data for this template
            if is_template_viable(template, games_data):
                # ✅ FIX: Skip recently-used templates in this batch
                template_id = template.get("template", "")[:20]
                if avoid_templates and template_id in avoid_templates:
                    print(f"⏭️ Skipping recently-used template: {template_id}")
                    continue

                viable_templates.append((template, category))

    if not viable_templates:
        print("⚠️ No viable templates found for current data")
        return None

    # Weight-based selection
    total_weight = sum(template["weight"] for template, _ in viable_templates)
    import random

    if total_weight > 0:
        # Weighted random selection
        target = random.uniform(0, total_weight)
        current_weight = 0

        for template, category in viable_templates:
            current_weight += template["weight"]
            if current_weight >= target:
                return {**template, "category": category}

    # Fallback to random selection
    template, category = random.choice(viable_templates)
    return {**template, "category": category}

def is_template_viable(template: Dict[str, Any], games_data: List[Dict[str, Any]]) -> bool:
    """Check if template can be answered with available data"""
    answer_logic = template.get("answer_logic", "")

    # Comparison templates need at least 2 games
    if answer_logic.startswith("compare_") and len(games_data) < 2:
        return False

    # Multiple choice needs at least 3 games for good options
    if template.get("type") == "multiple_choice" and len(games_data) < 3:
        return False

    # Episode-based questions need games with episode data
    if "episode" in answer_logic:
        if not any(game.get("total_episodes", 0) > 0 for game in games_data):
            return False

    # Playtime questions need games with playtime data
    if "playtime" in answer_logic or "hours" in answer_logic:
        if not any(game.get("total_playtime_minutes", 0) > 0 for game in games_data):
            return False

    # Genre questions need games with genre data
    if "genre" in answer_logic:
        if not any(game.get("genre") for game in games_data):
            return False

    return True

async def generate_ai_trivia_question(context: str = "trivia",
                                      avoid_questions: Optional[List[str]] = None,
                                      avoid_game_ids: Optional[List[int]] = None,
                                      avoid_templates: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """
    Generate a trivia question using the Trivia Director system.

    This new system selects a random category, curates appropriate games from the database,
    and uses AI to generate questions that test actual game knowledge rather than stream statistics.

    Args:
        context: Context string for rate limiting and logging
        avoid_questions: List of recently generated question texts to avoid patterns
        avoid_game_ids: List of game IDs to avoid using in generation
        avoid_templates: DEPRECATED - kept for backward compatibility, no longer used

    Returns:
        Dict with question data or None if generation failed
    """
    # Note: avoid_templates parameter is deprecated but kept for backward compatibility
    # The new Trivia Director system doesn't use templates
    if not ai_enabled:
        print("❌ AI not enabled for trivia question generation")
        return None

    # Check if database is available (lazy init)
    current_db = _get_db()
    if current_db is None:
        print("❌ Database not available for AI trivia generation")
        return None

    try:
        print(f"🎬 TRIVIA DIRECTOR: Starting question generation with context: {context}")
        if avoid_questions:
            print(f"   Avoiding {len(avoid_questions)} recent pattern(s)")
        if avoid_game_ids:
            print(f"   Avoiding {len(avoid_game_ids)} recent game(s)")

        # === NEW "ANSWER FIRST" TRIVIA DIRECTOR ===
        # Bot computes the correct answer from the database FIRST,
        # then asks the AI to write only the question text around it.
        # This prevents hallucinated lore/release-date questions entirely.
        TRIVIA_CATEGORIES = {
            # --- Channel stats (factual, answer-first) ---
            'Episode_Champion': {'weight': 2.0},  # Most episodes in a genre
            'Quickest_Completion': {'weight': 1.5},  # Fewest episodes to finish in a genre
            'Channel_Timeline': {'weight': 2.0},  # Which game Jonesy played first
            'Genre_Census': {'weight': 1.5},  # How many games of a genre
            'Genre_Pioneer': {'weight': 1.5},  # First game in a genre by play date
            'Series_Comparison': {'weight': 1.5},  # Which series game had most episodes
            'Series_Total_Episodes': {'weight': 1.5},  # Total episodes across a whole franchise
            'Playtime_Battle': {'weight': 1.5},  # Which of 2 games has more playtime hours
            'Release_Year': {'weight': 1.5},  # What year was a specific game released?
            'YouTube_Views_Champ': {'weight': 1.0},  # Most YouTube views (YouTube-only)
            # --- AI-creative (low weight - occasional variety) ---
            'Franchise_Lore': {'weight': 0.5},  # Lore question, AI provides answer
        }

        import random
        from collections import defaultdict

        categories = list(TRIVIA_CATEGORIES.keys())
        cat_weights = [TRIVIA_CATEGORIES[c]['weight'] for c in categories]

        # Get all games - we compute answers ourselves from real data
        all_games = current_db.get_all_played_games()
        if not all_games:
            print("❌ TRIVIA DIRECTOR: No games in database")
            return None

        # Filter out avoided game IDs
        if avoid_game_ids:
            all_games = [g for g in all_games if g.get('id') not in avoid_game_ids]

        # === UNIFIED ATTEMPT LOOP ===
        # Each attempt: pick a new category, build its prompt, call AI once.
        # On duplicate: continue → picks a DIFFERENT category next iteration.
        # On API failure: break → stops immediately to preserve quota.
        # Max 3 API calls total (one per attempt), vs old max of 9 (3 cats × 3 AI retries).

        tried_categories: set = set()
        for overall_attempt in range(3):
            selected_category = None
            category_prompt = None
            correct_answer = None
            source_games: List[Dict] = []
            is_json_response = False

            remaining = [c for c in categories if c not in tried_categories]
            if not remaining:
                break
            remaining_weights = [TRIVIA_CATEGORIES[c]['weight'] for c in remaining]
            cat = random.choices(remaining, weights=remaining_weights, k=1)[0]
            tried_categories.add(cat)

            print(f"🎬 TRIVIA DIRECTOR: Attempt {overall_attempt+1}/3 - Trying category '{cat}'")

            if cat == 'Episode_Champion':
                # Find a genre with 2+ games that have episode data
                games_with_eps = [g for g in all_games
                                  if g.get('total_episodes', 0) > 0 and g.get('genre')]
                if len(games_with_eps) < 2:
                    print("⚠️ TRIVIA DIRECTOR: Not enough episode data for Episode_Champion")
                    continue

                genre_groups_ep: Dict[str, List[Dict]] = defaultdict(list)
                for g in games_with_eps:
                    genre_groups_ep[g['genre']].append(g)

                eligible_ep = [(genre, gs) for genre, gs in genre_groups_ep.items() if len(gs) >= 2]
                if not eligible_ep:
                    continue

                chosen_genre_ep, genre_games_ep = random.choice(eligible_ep)
                winner_ep = max(genre_games_ep, key=lambda x: x.get('total_episodes', 0))
                correct_answer = winner_ep['canonical_name']
                source_games = sorted(genre_games_ep,
                                      key=lambda x: x.get('total_episodes', 0),
                                      reverse=True)[:5]

                game_lines_ep = '\n'.join([
                    f"  - {g['canonical_name']}: {g.get('total_episodes', 0)} episodes"
                    for g in source_games
                ])
                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Episode_Champion'")
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA - Jonesy's {chosen_genre_ep} games (episode counts from our database):
{game_lines_ep}

THE CORRECT ANSWER IS: {correct_answer}

Write a short question (under 120 characters) asking which of Jonesy's {chosen_genre_ep} games she played the most episodes of.
Do NOT ask about release dates, game lore, or in-game characters.
Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat
                # No break - fall through to AI call section below

            elif cat == 'Channel_Timeline':
                # Pick 2 random games with known first_played_date
                dated_games = [g for g in all_games if g.get('first_played_date')]
                if len(dated_games) < 2:
                    print("⚠️ TRIVIA DIRECTOR: Not enough date data for Channel_Timeline")
                    continue

                game1_tl, game2_tl = random.sample(dated_games, 2)
                date1 = str(game1_tl.get('first_played_date', ''))
                date2 = str(game2_tl.get('first_played_date', ''))
                correct_answer = game1_tl['canonical_name'] if date1 <= date2 else game2_tl['canonical_name']
                source_games = [game1_tl, game2_tl]

                print(f"✅ TRIVIA DIRECTOR: Got 2 game(s) for 'Channel_Timeline'")
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA from our database:
  - {game1_tl['canonical_name']}: Jonesy first played this on {date1}
  - {game2_tl['canonical_name']}: Jonesy first played this on {date2}

THE CORRECT ANSWER IS: {correct_answer}

Write a short question (under 120 characters) asking which of these two games Jonesy played FIRST on her channel.
Do NOT ask about release dates - ask about when Jonesy played them on her channel.
Good phrasing: "Which game did Jonesy play first on her channel - X or Y?"
Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat
                # No break - fall through to AI call section below

            elif cat == 'Genre_Census':
                # Count games per genre
                genre_counts_gc: Dict[str, int] = {}
                genre_game_names_gc: Dict[str, List[str]] = {}
                for g in all_games:
                    genre = g.get('genre')
                    if genre:
                        genre_counts_gc[genre] = genre_counts_gc.get(genre, 0) + 1
                        if genre not in genre_game_names_gc:
                            genre_game_names_gc[genre] = []
                        genre_game_names_gc[genre].append(g['canonical_name'])

                eligible_gc = [(genre, count) for genre, count in genre_counts_gc.items() if count >= 2]
                if not eligible_gc:
                    eligible_gc = list(genre_counts_gc.items())
                if not eligible_gc:
                    continue

                chosen_genre_gc, count_gc = random.choice(eligible_gc)
                correct_answer = str(count_gc)
                source_games = [g for g in all_games if g.get('genre') == chosen_genre_gc]
                game_list_gc = ', '.join(genre_game_names_gc[chosen_genre_gc][:8])

                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Genre_Census'")
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA from our database:
Jonesy has played exactly {count_gc} {chosen_genre_gc} game(s) on her channel: {game_list_gc}

THE CORRECT ANSWER IS: {count_gc}

Write a short question (under 120 characters) asking how many {chosen_genre_gc} games Jonesy has played on her channel.
Good phrasing: "How many {chosen_genre_gc} games has Jonesy played on her channel?"
Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat
                # No break - fall through to AI call section below

            elif cat == 'Series_Comparison':
                # Find a series with 2+ games that have episode data
                series_groups_sc: Dict[str, List[Dict]] = defaultdict(list)
                for g in all_games:
                    series = g.get('series_name')
                    if series and g.get('total_episodes', 0) > 0:
                        series_groups_sc[series].append(g)

                eligible_sc = [(s, gs) for s, gs in series_groups_sc.items() if len(gs) >= 2]
                if not eligible_sc:
                    print("⚠️ TRIVIA DIRECTOR: Not enough series data for Series_Comparison")
                    continue

                chosen_series_sc, series_games_sc = random.choice(eligible_sc)
                winner_sc = max(series_games_sc, key=lambda x: x.get('total_episodes', 0))
                correct_answer = winner_sc['canonical_name']
                source_games = sorted(series_games_sc,
                                      key=lambda x: x.get('total_episodes', 0),
                                      reverse=True)

                game_lines_sc = '\n'.join([
                    f"  - {g['canonical_name']}: {g.get('total_episodes', 0)} episodes"
                    for g in source_games
                ])
                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Series_Comparison'")
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA - Jonesy's {chosen_series_sc} games (episode counts from our database):
{game_lines_sc}

THE CORRECT ANSWER IS: {correct_answer}

Write a short question (under 120 characters) asking which {chosen_series_sc} game Jonesy spent the most episodes on.
Good phrasing: "Which {chosen_series_sc} game did Jonesy play the most episodes of?"
Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat
                # No break - fall through to AI call section below

            elif cat == 'Franchise_Lore':
                # AI-driven franchise question kept for variety - but fix pronouns
                series_groups_fl: Dict[str, List[Dict]] = defaultdict(list)
                for g in all_games:
                    series = g.get('series_name')
                    if series:
                        series_groups_fl[series].append(g)

                eligible_fl = [(s, gs) for s, gs in series_groups_fl.items() if len(gs) >= 2]
                if eligible_fl:
                    chosen_series_fl, series_games_fl = random.choice(eligible_fl)
                    game_names_fl = [g['canonical_name'] for g in series_games_fl]
                    source_games = series_games_fl
                    correct_answer = None  # AI determines this
                    is_json_response = True

                    print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Franchise_Lore'")
                    category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns. Always refer to Jonesy as "she/her".

Jonesy has played these {chosen_series_fl} games: {', '.join(game_names_fl)}

Write ONE engaging trivia question about the {chosen_series_fl} franchise that tests knowledge of recurring characters, themes, or mechanics.
Does NOT ask about release dates.
Return as JSON: {{"question_text": "Short question under 100 chars?", "correct_answer": "answer here"}}"""
                elif all_games:
                    game_fl = random.choice(all_games)
                    source_games = [game_fl]
                    correct_answer = None
                    is_json_response = True

                    print(f"✅ TRIVIA DIRECTOR: Got 1 game for 'Franchise_Lore' (fallback)")
                    category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns. Always refer to Jonesy as "she/her".

Jonesy has played: {game_fl['canonical_name']} ({game_fl.get('genre', 'Unknown')})

Write ONE engaging trivia question about {game_fl['canonical_name']} that tests memorable game knowledge.
Does NOT ask about release dates.
Return as JSON: {{"question_text": "Short question under 100 chars?", "correct_answer": "answer here"}}"""
                else:
                    continue  # Not enough data for Franchise_Lore, try next category

                selected_category = cat

            elif cat == 'Quickest_Completion':
                # Fewest episodes to complete a game, within a genre
                completed_with_eps = [g for g in all_games
                                      if g.get('completion_status') == 'completed' and
                                      (g.get('total_episodes') or 0) > 0 and
                                      g.get('genre')]
                if len(completed_with_eps) < 2:
                    print("⚠️ TRIVIA DIRECTOR: Not enough completed game data for Quickest_Completion")
                    continue

                genre_groups_qc: Dict[str, List[Dict]] = defaultdict(list)
                for g in completed_with_eps:
                    genre_groups_qc[g['genre']].append(g)

                eligible_qc = [(genre, gs) for genre, gs in genre_groups_qc.items() if len(gs) >= 2]
                if not eligible_qc:
                    continue

                chosen_genre_qc, genre_games_qc = random.choice(eligible_qc)
                winner_qc = min(genre_games_qc, key=lambda x: x.get('total_episodes') or 0)
                correct_answer = winner_qc['canonical_name']
                source_games = sorted(genre_games_qc, key=lambda x: x.get('total_episodes') or 0)[:5]

                game_lines_qc = '\n'.join([
                    f"  - {g['canonical_name']}: {g.get('total_episodes', 0)} episodes to complete"
                    for g in source_games
                ])
                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Quickest_Completion'")

                phrasing_qc = random.choice([
                    f"Which of Jonesy's completed {chosen_genre_qc} games did she finish in the fewest episodes?",
                    f"Jonesy's {chosen_genre_qc} completions — which game wrapped up in the least episodes?",
                    f"Among Jonesy's {chosen_genre_qc} games, which did she complete most quickly by episode count?",
                ])
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA - Jonesy's completed {chosen_genre_qc} games (episode counts from our database):
{game_lines_qc}

THE CORRECT ANSWER IS: {correct_answer}

Rephrase this question in your own words (under 120 characters):
"{phrasing_qc}"

Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat

            elif cat == 'Genre_Pioneer':
                # First game Jonesy played in a genre, by first_played_date
                dated_with_genre = [g for g in all_games
                                    if g.get('first_played_date') and g.get('genre')]
                if not dated_with_genre:
                    print("⚠️ TRIVIA DIRECTOR: Not enough dated+genre data for Genre_Pioneer")
                    continue

                genre_groups_gp: Dict[str, List[Dict]] = defaultdict(list)
                for g in dated_with_genre:
                    genre_groups_gp[g['genre']].append(g)

                # Need genres with at least 2 games so the answer isn't trivially obvious
                eligible_gp = [(genre, gs) for genre, gs in genre_groups_gp.items() if len(gs) >= 2]
                if not eligible_gp:
                    continue

                chosen_genre_gp, genre_games_gp = random.choice(eligible_gp)
                first_game_gp = min(genre_games_gp, key=lambda x: str(x.get('first_played_date', '')))
                correct_answer = first_game_gp['canonical_name']
                source_games = sorted(genre_games_gp, key=lambda x: str(x.get('first_played_date', '')))[:5]

                game_lines_gp = '\n'.join([
                    f"  - {g['canonical_name']}: first played {g.get('first_played_date', 'unknown')}"
                    for g in source_games
                ])
                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Genre_Pioneer'")

                phrasing_gp = random.choice([
                    f"What was the first {chosen_genre_gp} game Jonesy played on her channel?",
                    f"Which {chosen_genre_gp} game kicked off Jonesy's journey in that genre?",
                    f"Of all Jonesy's {chosen_genre_gp} games, which did she play first on the channel?",
                ])
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA - Jonesy's {chosen_genre_gp} games in order of when she first played them:
{game_lines_gp}

THE CORRECT ANSWER IS: {correct_answer}

Rephrase this question in your own words (under 120 characters):
"{phrasing_gp}"

Do NOT ask about release dates — ask about when Jonesy first played on her channel.
Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat

            elif cat == 'Series_Total_Episodes':
                # Total episode count across all games in a franchise
                series_groups_ste: Dict[str, List[Dict]] = defaultdict(list)
                for g in all_games:
                    series = g.get('series_name')
                    if series and (g.get('total_episodes') or 0) > 0:
                        series_groups_ste[series].append(g)

                eligible_ste = [(s, gs) for s, gs in series_groups_ste.items() if len(gs) >= 2]
                if not eligible_ste:
                    print("⚠️ TRIVIA DIRECTOR: Not enough multi-game series data for Series_Total_Episodes")
                    continue

                chosen_series_ste, series_games_ste = random.choice(eligible_ste)
                total_eps_ste = sum(g.get('total_episodes') or 0 for g in series_games_ste)
                correct_answer = str(total_eps_ste)
                source_games = series_games_ste

                game_lines_ste = '\n'.join([
                    f"  - {g['canonical_name']}: {g.get('total_episodes', 0)} episodes"
                    for g in series_games_ste
                ])
                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Series_Total_Episodes'")

                phrasing_ste = random.choice([
                    f"How many total episodes has Jonesy played across all her {chosen_series_ste} games?",
                    f"Combined across every {chosen_series_ste} game, how many episodes has Jonesy recorded?",
                    f"What's the total episode count for Jonesy's entire {chosen_series_ste} playthrough series?",
                ])
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA - Jonesy's {chosen_series_ste} games (individual episode counts from our database):
{game_lines_ste}
Combined total: {total_eps_ste} episodes

THE CORRECT ANSWER IS: {total_eps_ste}

Rephrase this question in your own words (under 120 characters):
"{phrasing_ste}"

Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat

            elif cat == 'Playtime_Battle':
                # Compare 2 games by total playtime hours
                games_with_time = [g for g in all_games if (g.get('total_playtime_minutes') or 0) > 0]
                if len(games_with_time) < 2:
                    print("⚠️ TRIVIA DIRECTOR: Not enough playtime data for Playtime_Battle")
                    continue

                game1_pb, game2_pb = random.sample(games_with_time, 2)
                hours1 = round((game1_pb.get('total_playtime_minutes') or 0) / 60, 1)
                hours2 = round((game2_pb.get('total_playtime_minutes') or 0) / 60, 1)
                correct_answer = game1_pb['canonical_name'] if hours1 >= hours2 else game2_pb['canonical_name']
                source_games = [game1_pb, game2_pb]

                print(f"✅ TRIVIA DIRECTOR: Got 2 game(s) for 'Playtime_Battle'")

                phrasing_pb = random.choice([
                    f"Which game has Jonesy spent more total hours on — {game1_pb['canonical_name']} or {game2_pb['canonical_name']}?",
                    f"Total hours logged: did Jonesy put more time into {game1_pb['canonical_name']} or {game2_pb['canonical_name']}?",
                    f"{game1_pb['canonical_name']} vs {game2_pb['canonical_name']} — which has more of Jonesy's playtime hours?",
                ])
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA from our database (total playtime recorded):
  - {game1_pb['canonical_name']}: {hours1} hours
  - {game2_pb['canonical_name']}: {hours2} hours

THE CORRECT ANSWER IS: {correct_answer}

Rephrase this question in your own words (under 120 characters):
"{phrasing_pb}"

Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat

            elif cat == 'Release_Year':
                # What year was a specific game released?
                games_with_year = [g for g in all_games if g.get('release_year')]
                if not games_with_year:
                    print("⚠️ TRIVIA DIRECTOR: No release year data for Release_Year")
                    continue

                chosen_game_ry = random.choice(games_with_year)
                correct_answer = str(chosen_game_ry['release_year'])
                source_games = [chosen_game_ry]

                print(f"✅ TRIVIA DIRECTOR: Got 1 game for 'Release_Year'")

                phrasing_ry = random.choice([
                    f"In what year was {chosen_game_ry['canonical_name']} originally released?",
                    f"When did {chosen_game_ry['canonical_name']} launch — what year was it released?",
                    f"What's the release year of {chosen_game_ry['canonical_name']}, one of Jonesy's games?",
                ])
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA from our database:
  - {chosen_game_ry['canonical_name']} was originally released in {chosen_game_ry['release_year']}

THE CORRECT ANSWER IS: {chosen_game_ry['release_year']}

Rephrase this question in your own words (under 100 characters):
"{phrasing_ry}"

Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat

            elif cat == 'YouTube_Views_Champ':
                # Which of 3 games has the most YouTube views? (YouTube-only, like-for-like)
                yt_games = [g for g in all_games if (g.get('youtube_views') or 0) > 0]
                if len(yt_games) < 3:
                    print("⚠️ TRIVIA DIRECTOR: Not enough YouTube view data for YouTube_Views_Champ")
                    continue

                # Pick top candidate + 2 random others for a 3-way comparison
                top_yt = max(yt_games, key=lambda x: x.get('youtube_views') or 0)
                others_yt = [g for g in yt_games if g != top_yt]
                choices_yt = [top_yt] + random.sample(others_yt, min(2, len(others_yt)))
                correct_answer = top_yt['canonical_name']
                source_games = choices_yt

                game_lines_yt = '\n'.join([
                    f"  - {g['canonical_name']}: {(g.get('youtube_views') or 0):,} YouTube views"
                    for g in choices_yt
                ])
                names_yt = [g['canonical_name'] for g in choices_yt]
                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'YouTube_Views_Champ'")

                phrasing_yt = random.choice([
                    f"Which of these games has the most YouTube views on Jonesy's channel?",
                    f"On YouTube, which of these Jonesy playthroughs has the highest view count?",
                    f"Which game tops the YouTube view count on Jonesy's channel out of these options?",
                ])
                category_prompt = f"""Write one trivia question for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL DATA - YouTube view counts from our database (YouTube-only, not including Twitch):
{game_lines_yt}

THE CORRECT ANSWER IS: {correct_answer}

Rephrase this question in your own words (under 120 characters), naming the specific games:
"{phrasing_yt}"
Games to mention: {', '.join(names_yt)}

Return ONLY the question sentence, nothing else. No JSON, no explanation."""
                selected_category = cat

            # --- If we couldn't build a prompt for this category, skip it ---
            if not selected_category or not category_prompt:
                continue

            # === PROMPT IS READY: LOG SELECTION AND CALL AI ===
            print(f"🎮 TRIVIA DIRECTOR: Selected '{selected_category}' | Answer: {correct_answer or 'AI-determined'}")
            print(f"   Source games: {[g['canonical_name'] for g in source_games[:3]]}")

            # Append avoid-questions hint to prompt
            prompt = category_prompt
            if avoid_questions:
                avoid_text = "\n\n🚫 AVOID questions similar to:\n"
                avoid_text += "\n".join([f"  - {q[:60]}..." for q in avoid_questions[-5:]])
                prompt = prompt + avoid_text

            # === CALL AI WITH CATEGORY-SPECIFIC TEMPERATURE ===
            CATEGORY_TEMPERATURES = {
                'Episode_Champion': 0.8,  # Creative phrasing, factual answer
                'Quickest_Completion': 0.8,  # Creative phrasing, factual answer (inverse)
                'Channel_Timeline': 0.7,  # Simple factual question (which game first)
                'Genre_Census': 0.8,  # Varied phrasing for count questions
                'Genre_Pioneer': 0.8,  # First game in genre - clear factual
                'Series_Comparison': 0.8,  # Creative phrasing, factual answer
                'Series_Total_Episodes': 0.8,  # Sum question - clear factual
                'Playtime_Battle': 0.8,  # Head-to-head comparison
                'Release_Year': 0.7,  # Simple factual (a year)
                'YouTube_Views_Champ': 0.8,  # Names specific games - stays focused
                'Franchise_Lore': 0.9,  # Most creative - AI provides answer
            }

            temperature = CATEGORY_TEMPERATURES.get(selected_category, 0.9)
            print(f"🌡️ TRIVIA DIRECTOR: Using temperature {temperature} for '{selected_category}'")

            # === SINGLE AI CALL PER CATEGORY ===
            # If this produces a duplicate, we try a DIFFERENT category next iteration.
            # This is more API-quota-friendly (max 3 calls total) and actually diversifies output.
            response_text, status_message = await call_ai_for_generation(
                prompt,
                context=context,
                temperature=temperature
            )

            if not response_text:
                print(f"❌ TRIVIA DIRECTOR: AI call failed (attempt {overall_attempt+1}): {status_message}")
                break  # API failure - don't retry, preserve quota

            print(
                f"✅ TRIVIA DIRECTOR: AI response received: {len(response_text)} characters (attempt {overall_attempt+1}/3)")

            # Parse AI response
            # Data-driven categories: AI returns plain question text only (we have the answer)
            # Franchise_Lore: AI returns JSON with both question and answer
            if is_json_response:
                ai_question = robust_json_parse(response_text)
                if ai_question:
                    ai_question["question_type"] = ai_question.get("question_type", "single_answer")
            else:
                q_text = response_text.strip().strip('"').strip("'").strip()
                for prefix in ['Question:', 'Here is a question:', "Here's a question:",
                               'Trivia question:', 'Here you go:']:
                    if q_text.lower().startswith(prefix.lower()):
                        q_text = q_text[len(prefix):].strip()
                if q_text and not q_text.endswith('?'):
                    q_text += '?'
                ai_question = {
                    "question_text": q_text,
                    "question_type": "single_answer",
                    "correct_answer": correct_answer
                } if (10 <= len(q_text) <= 250) else None

            if not ai_question or not all(
                key in ai_question for key in ["question_text", "question_type", "correct_answer"]
            ):
                print(f"⚠️ TRIVIA DIRECTOR: AI response missing required fields (attempt {overall_attempt+1})")
                continue  # Try different category

            # Check for duplicates before accepting
            duplicate_info = current_db.check_question_duplicate(
                ai_question["question_text"],
                similarity_threshold=0.8
            )

            if duplicate_info:
                print(
                    f"🔍 TRIVIA DIRECTOR: Duplicate detected (attempt {overall_attempt+1}/3): "
                    f"{duplicate_info['similarity_score']:.2f} similarity to question #{duplicate_info['duplicate_id']} "
                    f"- switching to different category...")
                continue  # Try a genuinely different category on next iteration

            # === SUCCESS - ADD METADATA ===
            ai_question.update({
                "generation_method": "trivia_director",
                "director_category": selected_category,
                "source_games": [
                    {
                        'id': g.get('id'),
                        'name': g['canonical_name'],
                        'genre': g.get('genre'),
                        'year': g.get('release_year')
                    } for g in source_games
                ],
                "temperature": temperature,
                "generation_timestamp": datetime.now(ZoneInfo('Europe/London')).isoformat()
            })

            print(f"✅ TRIVIA DIRECTOR: Question generated successfully!")
            print(f"   Category: {selected_category}")
            print(f"   Games: {[g['canonical_name'] for g in source_games[:3]]}")
            print(f"   Question: {ai_question['question_text'][:60]}...")
            return ai_question

        print(f"❌ TRIVIA DIRECTOR: All 3 generation attempts failed")
        return None

    except Exception as e:
        print(f"❌ Error in diverse trivia generation: {e}")
        traceback.print_exc()
        return None

async def generate_trivia_batch(batch_size: int = 10, context: str = "batch_generation") -> Dict[str, Any]:
    """
    PHASE 2: Generate multiple trivia questions in a single API call.

    This is the key optimization - instead of 10 API calls for 10 questions,
    we make 1 API call that generates all 10 at once.

    Args:
        batch_size: Number of questions to generate (default 10)
        context: Context string for logging

    Returns:
        Dict with generation results and statistics
    """
    if not ai_enabled:
        print("❌ AI not enabled for trivia batch generation")
        return {"success": False, "generated": 0, "error": "AI not enabled"}

    current_db = _get_db()
    if current_db is None:
        print("❌ Database not available for trivia batch generation")
        return {"success": False, "generated": 0, "error": "Database not available"}

    try:
        print(f"🎲 PHASE 2: Generating batch of {batch_size} trivia questions in single API call...")

        # Get game statistics for context
        stats = current_db.get_played_games_stats()
        sample_games = current_db.get_all_played_games()[:10]

        # Build game context
        game_context = ""
        if sample_games:
            game_details = []
            for game in sample_games[:5]:
                name = game['canonical_name']
                episodes = game.get('total_episodes', 0)
                status = game.get('completion_status', 'unknown')
                game_details.append(f"{name} ({episodes} eps, {status})")
            game_context = f"Sample games: {'; '.join(game_details)}"

        # Create batch generation prompt
        batch_prompt = f"""Generate exactly {batch_size} diverse trivia questions about Captain Jonesy's gaming experiences.

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {batch_size} questions
2. Use DIVERSE question types and categories
3. Each question must be UNIQUE and different from others
4. Be CONCISE - minimal preamble

TERMINOLOGY RULES:
⚠️ "most played" = HIGHEST total_playtime_minutes (time)
⚠️ "most episodes" = MOST episode count (episodes)
⚠️ These are DIFFERENT metrics!

DIVERSITY GUIDELINES:
- Mix genres, series, platforms, temporal questions
- Vary between completion status, playtime, episodes
- Include both easy and challenging questions
- Focus on engaging, interesting facts

AVAILABLE DATA:
{game_context}
Total games: {stats.get('total_games', 0)}

RETURN ONLY JSON ARRAY:
[
  {{
    "question_text": "Concise question here?",
    "question_type": "single_answer",
    "correct_answer": "Answer here",
    "category": "category_name",
    "difficulty_level": 1
  }},
  ... ({batch_size} total questions)
]

Generate diverse, engaging questions about Jonesy's gaming journey."""

        # Call AI with rate limiting
        print(f"📞 Making single API call for {batch_size} questions...")
        response_text, status_message = await call_ai_with_rate_limiting(batch_prompt, JONESY_USER_ID, context)

        if not response_text:
            print(f"❌ Batch generation failed: {status_message}")
            return {"success": False, "generated": 0, "error": status_message}

        print(f"✅ Received batch response: {len(response_text)} characters")

        # Parse the JSON array
        parsed_response = robust_json_parse(response_text)

        # Type check: must be a list
        if not parsed_response or not isinstance(parsed_response, list):
            print(f"❌ Failed to parse batch response as JSON array")
            return {"success": False, "generated": 0, "error": "Invalid JSON response"}

        # Now we know it's a list, type hint for Pylance
        questions_array: List[Any] = parsed_response

        print(f"📊 Parsed {len(questions_array)} questions from batch")

        # Store each question in the database
        stored_count = 0
        duplicate_count = 0
        error_count = 0

        for idx, question_data in enumerate(questions_array):
            try:
                # Type check: must be a dict
                if not isinstance(question_data, dict):
                    print(f"⚠️ Question {idx+1} is not a dict, skipping")
                    error_count += 1
                    continue

                # Type cast for Pylance after type check
                question_dict: Dict[str, Any] = question_data

                # Validate question structure
                if not all(key in question_dict for key in ["question_text", "question_type", "correct_answer"]):
                    print(f"⚠️ Question {idx+1} missing required fields, skipping")
                    error_count += 1
                    continue

                # Extract fields using .get() for Pylance compatibility
                question_text = question_dict.get("question_text", "")
                correct_answer = question_dict.get("correct_answer", "")

                if not question_text or not correct_answer:
                    print(f"⚠️ Question {idx+1} has empty required fields, skipping")
                    error_count += 1
                    continue

                # Check for duplicates
                duplicate_info = current_db.check_question_duplicate(
                    question_text,
                    similarity_threshold=0.8
                )

                if duplicate_info:
                    print(
                        f"🔍 Question {idx+1} is duplicate (similarity: {duplicate_info['similarity_score']:.2f}), skipping")
                    duplicate_count += 1
                    continue

                # Store question in database with 'available' status
                question_id = current_db.safe_add_trivia_question(
                    question_text=question_text,
                    question_type=question_dict.get("question_type", "single_answer"),
                    correct_answer=correct_answer,
                    multiple_choice_options=question_dict.get("multiple_choice_options"),
                    is_dynamic=False,
                    category=question_dict.get("category", "batch_generated"),
                    difficulty_level=question_dict.get("difficulty_level", 1),
                    submitted_by_user_id=None  # AI-generated
                )

                if question_id:
                    stored_count += 1
                    print(f"✅ Stored question {idx+1}/{len(questions_array)}: ID {question_id}")
                else:
                    error_count += 1
                    print(f"❌ Failed to store question {idx+1}")

            except Exception as e:
                print(f"❌ Error storing question {idx+1}: {e}")
                error_count += 1

        # Calculate efficiency
        efficiency = f"{stored_count}x" if stored_count > 0 else "0x"
        api_calls_saved = stored_count - 1 if stored_count > 1 else 0

        result = {
            "success": stored_count > 0,
            "generated": stored_count,
            "duplicates": duplicate_count,
            "errors": error_count,
            "total_attempted": len(questions_array),
            "api_calls_used": 1,
            "api_calls_saved": api_calls_saved,
            "efficiency": efficiency
        }

        print(
            f"🎉 PHASE 2 COMPLETE: Generated {stored_count} questions in 1 API call (saved {api_calls_saved} calls, {efficiency} efficiency)")

        return result

    except Exception as e:
        print(f"❌ Error in batch trivia generation: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "generated": 0, "error": str(e)}