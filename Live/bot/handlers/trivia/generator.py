import json
import random
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ...config import JONESY_USER_ID
from ..ai_handler import (
    _get_db,
    ai_enabled,
    call_ai_for_generation,
    call_ai_with_rate_limiting,
    pacific_tz,
    robust_json_parse,
)


async def generate_ai_trivia_question(context: str = "trivia",
                                      avoid_questions: Optional[List[str]] = None,
                                      avoid_game_ids: Optional[List[int]] = None,
                                      avoid_templates: Optional[List[str]] = None,
                                      force_category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Generate a trivia question using the Trivia Director system.

    This new system selects a random category, curates appropriate games from the database,
    and uses AI to generate questions that test actual game knowledge rather than stream statistics.

    Args:
        context: Context string for rate limiting and logging
        avoid_questions: List of recently generated question texts to avoid patterns
        avoid_game_ids: List of game IDs to avoid using in generation
        avoid_templates: DEPRECATED - kept for backward compatibility, no longer used
        force_category: Optional specific category to generate

    Returns:
        Dict with question data or None if generation failed
    """
    # Note: avoid_templates parameter is deprecated but kept for backward compatibility
    # The new Trivia Director system doesn't use templates
    if not ai_enabled:
        print("❌ AI not enabled for trivia question generation")
        return []

    # Check if database is available (lazy init)
    current_db = _get_db()
    if current_db is None:
        print("❌ Database not available for AI trivia generation")
        return []

    try:
        print(f"🎬 TRIVIA DIRECTOR: Starting question generation with context: {context}")

        if avoid_questions is None:
            avoid_questions = []

        # Fetch recently generated questions from the database to avoid repetition across manual triggers
        avoid_clips = []
        try:
            with current_db.get_connection().cursor() as cur:
                cur.execute("SELECT question_text, dynamic_query_type FROM trivia_questions ORDER BY id DESC LIMIT 20")
                rows = cur.fetchall()
                for row in rows:
                    if row and 'question_text' in row:
                        avoid_questions.append(row['question_text'])
                    if row and row.get('dynamic_query_type'):
                        try:
                            import json
                            dq = json.loads(row['dynamic_query_type'])
                            if isinstance(dq, dict) and 'clip_url' in dq:
                                avoid_clips.append(dq['clip_url'])
                        except BaseException:
                            pass
        except Exception as e:
            print(f"Error fetching recent questions for avoidance: {e}")

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
            # 'Episode_Champion': {'weight': 2.0},  # Most episodes in a genre
            # 'Quickest_Completion': {'weight': 1.5},  # Fewest episodes to finish in a genre
            # 'Channel_Timeline': {'weight': 2.0},  # Which game Jonesy played first
            # 'Genre_Census': {'weight': 1.5},  # How many games of a genre
            # 'Genre_Pioneer': {'weight': 1.5},  # First game in a genre by play date
            'Series_Comparison': {'weight': 1.5},  # Which series game had most episodes
            'Series_Total_Episodes': {'weight': 1.5},  # Total episodes across a whole franchise
            'Playtime_Battle': {'weight': 1.5},  # Which of 2 games has more playtime hours
            # 'Release_Year': {'weight': 1.5},  # What year was a specific game released?
            # Most YouTube views (YouTube-only, reduced weight to prevent repetition)
            'YouTube_Views_Champ': {'weight': 0.2},
            # --- AI-creative & Clips (moderate weight for variety) ---
            'Clip_Famous_Last_Words': {'weight': 1.2},
            'Clip_Vibe_Check': {'weight': 1.2},
            'Clip_Cause_And_Effect': {'weight': 1.2},
            'Clip_Quote_Guess': {'weight': 1.2},
            'Clip_What_Happened_Next': {'weight': 1.2},
        }

        categories = list(TRIVIA_CATEGORIES.keys())
        if force_category:
            if force_category.lower() == 'clip':
                categories = [c for c in categories if c.startswith('Clip_')]
            elif force_category in TRIVIA_CATEGORIES:
                categories = [force_category]

        # Get all games - we compute answers ourselves from real data
        all_games = current_db.get_all_played_games()
        if not all_games:
            print("❌ TRIVIA DIRECTOR: No games in database")
            return []

        # Filter out avoided game IDs
        if avoid_game_ids:
            all_games = [g for g in all_games if g.get('id') not in avoid_game_ids]

        # === UNIFIED ATTEMPT LOOP ===
        # Each attempt: pick a new category, build its prompt, call AI once.
        # On duplicate: continue → picks a DIFFERENT category next iteration.
        # On API failure: break → stops immediately to preserve quota.
        # Max 3 API calls total (one per attempt), vs old max of 9 (3 cats × 3 AI retries).

        tried_categories: set = set()
        while True:
            selected_category = None
            final_question_text = None
            category_prompt = None
            correct_answer = None
            source_games: List[Dict] = []
            is_json_response = False
            raw_questions: List[Dict[str, Any]] = []

            remaining = [c for c in categories if c not in tried_categories]
            if not remaining:
                break
            remaining_weights = [TRIVIA_CATEGORIES[c]['weight'] for c in remaining]
            cat = random.choices(remaining, weights=remaining_weights, k=1)[0]
            tried_categories.add(cat)

            print(f"🎬 TRIVIA DIRECTOR: Attempt {len(tried_categories)} - Trying category '{cat}'")

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

                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Episode_Champion'")
                names_ep = [g['canonical_name'] for g in source_games]
                phrasing_ep = random.choice([
                    f"Which of these {chosen_genre_ep} games did Jonesy play the most episodes of?",
                    f"Out of these {chosen_genre_ep} games, which one has the highest episode count?",
                    f"Jonesy loves a good {chosen_genre_ep}, but which of these options kept her busy for the most episodes?",
                    f"If you count up all the episodes, which of these {chosen_genre_ep} games takes the top spot?",
                    f"Which of the following {chosen_genre_ep} titles is Jonesy's longest playthrough by episode count?",
                    f"Looking at these {chosen_genre_ep} games, which one resulted in the most episodes for the channel?",
                    f"She played all of these {chosen_genre_ep} games, but which one holds the record for most episodes?",
                    f"Which of these {chosen_genre_ep} titles had Jonesy hitting the 'record' button the most times?"
                ])
                final_question_text = f"{phrasing_ep} Options: {', '.join(names_ep)}"
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
                final_question_text = f"Which game did Jonesy play first on her channel: {game1_tl['canonical_name']} or {game2_tl['canonical_name']}?"
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

                phrasing_gc = random.choice([
                    f"How many {chosen_genre_gc} games has Jonesy played on her channel?",
                    f"What is the total number of {chosen_genre_gc} games Jonesy has played?",
                    f"Jonesy has played a few {chosen_genre_gc} games on the channel. How many exactly?",
                    f"If you check the archives, how many {chosen_genre_gc} titles has Jonesy streamed?",
                    f"Can you guess the exact number of {chosen_genre_gc} games Jonesy has covered?",
                    f"Between YouTube and Twitch, how many {chosen_genre_gc} games has Jonesy played?",
                    f"What's the official count of {chosen_genre_gc} games played by Captain Jonesy?",
                    f"How many times has Jonesy dived into a {chosen_genre_gc} game on stream?"
                ])
                final_question_text = phrasing_gc
                category_prompt = None

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

                phrasing_sc = random.choice([
                    f"Which {chosen_series_sc} game did Jonesy play the most episodes of?",
                    f"Out of her {chosen_series_sc} playthroughs, which one took the most episodes?",
                    f"Which game in the {chosen_series_sc} series has the highest episode count on Jonesy's channel?",
                    f"Jonesy is a big {chosen_series_sc} fan, but which game took the most episodes to get through?",
                    f"Of all the {chosen_series_sc} games Jonesy has played, which holds the record for most episodes?",
                    f"Which entry in the {chosen_series_sc} franchise kept Jonesy occupied for the most episodes?",
                    f"If you look at Jonesy's {chosen_series_sc} videos, which specific game has the most episodes?",
                    f"Which {chosen_series_sc} title resulted in the longest episodic series for Jonesy?"
                ])
                final_question_text = phrasing_sc
                category_prompt = None

                selected_category = cat
                # No break - fall through to AI call section below

            elif cat == 'Clip_Famous_Last_Words':
                clips = current_db.trivia.get_random_clip_lore(
                    limit=10,
                    required_fields=[
                        'notable_quote',
                        'clip_outcome',
                        'canonical_url',
                        'lore_summary',
                        'characters_involved',
                        'game_title',
                        'trigger'])
                clips = [c for c in clips if c['clip_outcome'].lower() in (
                    'death', 'failure') and c.get('canonical_url') not in avoid_clips]
                if not clips:
                    print("⚠️ TRIVIA DIRECTOR: Not enough death/failure clips for Clip_Famous_Last_Words")
                    continue
                selected_clips = random.sample(clips, min(2, len(clips)))
                correct_answer = None
                is_json_response = True
                print(f"✅ TRIVIA DIRECTOR: Got {len(selected_clips)} clip(s) for Clip_Famous_Last_Words")

                clip_data_str = ""
                for idx, c in enumerate(selected_clips):
                    clip_data_str += f"\\nCLIP {idx+1}:\\nURL: {c.get('canonical_url', 'Unknown')}\\nGame: {c.get('game_title', 'Unknown')}\\nCharacters Involved: {c.get('characters_involved', 'None')}\\nContext (Lore): {c.get('lore_summary', 'None')}\\nTrigger: {c.get('trigger', 'Unknown')}\\nOutcome: {c.get('clip_outcome', 'Unknown')}\\nQuote spoken right before outcome: \\\"{c.get('notable_quote', '')}\\\"\\nSubmitted By: {c.get('submitted_by_discord_id', 'Unknown')}\\n"

                category_prompt = f"""Write 5 diverse trivia questions for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL CLIP DATA:{clip_data_str}

Create 5 "Famous Last Words" style questions based on these clips.
Example: "While fighting the final boss in Elden Ring, Jonesy confidently told chat 'I have this in the bag'. What happened next?"
The question text MUST include the specific Game Title and Context (Lore) so the audience can reasonably guess.
Use the provided Characters Involved and Context to create rich, specific questions. The correct answer should relate to the Quote or the Outcome.
Autonomously determine difficulty: For obscure details, provide 3 decoys and set question_type to 'multiple_choice'. For easier facts, set question_type to 'single_answer'.
Additionally, for each question, include the "clip_url" from the clip it was based on, and write a custom Ash "commentary" string to be displayed alongside the answer.
IMPORTANT: Ash uses he/him pronouns. You MUST credit the discord user who submitted the clip in your commentary using their Discord ID. (e.g. "I can confirm Jonesy was in a state of alarm. I have prepared this visual evidence for review, courtesy of Archival Agent <@123456789>.")
Return strictly as a raw JSON array containing exactly 5 generated questions.
DO NOT output a schema or placeholder text. You must generate REAL trivia questions based on the clip data.
Each object in the JSON array MUST follow this exact format:
[
  {{
    "question_text": "Write the actual question here based on the clip",
    "question_type": "multiple_choice",
    "correct_answer": "The real answer",
    "decoy_1": "A real fake option",
    "decoy_2": "Another real fake option",
    "decoy_3": "A third real fake option",
    "clip_url": "The provided URL",
    "commentary": "Ash's commentary"
  }}
]
"""
                selected_category = cat

            elif cat == 'Clip_Vibe_Check':
                clips = current_db.trivia.get_random_clip_lore(
                    limit=10,
                    required_fields=[
                        'emotion_category',
                        'game_title',
                        'canonical_url',
                        'lore_summary',
                        'characters_involved',
                        'trigger',
                        'reaction'])
                clips = [c for c in clips if c.get('canonical_url') not in avoid_clips]
                if not clips:
                    print("⚠️ TRIVIA DIRECTOR: Not enough clips for Clip_Vibe_Check")
                    continue
                selected_clips = random.sample(clips, min(2, len(clips)))
                correct_answer = None
                is_json_response = True
                print(f"✅ TRIVIA DIRECTOR: Got {len(selected_clips)} clip(s) for Clip_Vibe_Check")

                clip_data_str = ""
                for idx, c in enumerate(selected_clips):
                    clip_data_str += f"\\nCLIP {idx+1}:\\nURL: {c.get('canonical_url', 'Unknown')}\\nGame: {c.get('game_title', 'Unknown')}\\nCharacters Involved: {c.get('characters_involved', 'None')}\\nEmotion Displayed: {c.get('emotion_category', 'Unknown')}\\nTrigger: {c.get('trigger', 'Unknown')}\\nReaction: {c.get('reaction', 'Unknown')}\\nContext: {c.get('lore_summary', 'None')}\\nSubmitted By: {c.get('submitted_by_discord_id', 'Unknown')}\\n"

                category_prompt = f"""Write 5 diverse trivia questions for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL CLIP DATA:{clip_data_str}

Create 5 "Vibe Check" questions about Jonesy's specific physical or verbal reactions to scary or surprising moments.
Example: "When the Xenomorph suddenly dropped from the ceiling in Alien Isolation, what was Jonesy's immediate reaction?"
The question text MUST describe the Game Title and the exact situation (Trigger) so the audience can reasonably guess. The correct answer should be a description of her reaction (e.g., "She screamed and threw her headset" or "She paused the game and walked away"), rather than just a single emotion word.
Use the provided Emotion Displayed, Characters Involved, and Context to create rich, specific questions.
Autonomously determine difficulty: For obscure details, provide 3 decoys and set question_type to 'multiple_choice'. For easier facts, set question_type to 'single_answer'.
Additionally, for each question, include the "clip_url" from the clip it was based on, and write a custom Ash "commentary" string to be displayed alongside the answer.
IMPORTANT: Ash uses he/him pronouns. You MUST credit the discord user who submitted the clip in your commentary using their Discord ID. (e.g. "I can confirm Jonesy was in a state of alarm. I have prepared this visual evidence for review, courtesy of Archival Agent <@123456789>.")
Return strictly as a raw JSON array containing exactly 5 generated questions.
DO NOT output a schema or placeholder text. You must generate REAL trivia questions based on the clip data.
Each object in the JSON array MUST follow this exact format:
[
  {{
    "question_text": "Write the actual question here based on the clip",
    "question_type": "multiple_choice",
    "correct_answer": "The real answer",
    "decoy_1": "A real fake option",
    "decoy_2": "Another real fake option",
    "decoy_3": "A third real fake option",
    "clip_url": "The provided URL",
    "commentary": "Ash's commentary"
  }}
]
"""
                selected_category = cat

            elif cat == 'Clip_Cause_And_Effect':
                clips = current_db.trivia.get_random_clip_lore(
                    limit=10,
                    required_fields=[
                        'trigger',
                        'reaction',
                        'characters_involved',
                        'game_title',
                        'canonical_url',
                        'lore_summary'])
                clips = [c for c in clips if c.get('canonical_url') not in avoid_clips]
                if not clips:
                    print("⚠️ TRIVIA DIRECTOR: Not enough clips for Clip_Cause_And_Effect")
                    continue
                selected_clips = random.sample(clips, min(2, len(clips)))
                correct_answer = None
                is_json_response = True
                print(f"✅ TRIVIA DIRECTOR: Got {len(selected_clips)} clip(s) for Clip_Cause_And_Effect")

                clip_data_str = ""
                for idx, c in enumerate(selected_clips):
                    clip_data_str += f"\\nCLIP {idx+1}:\\nURL: {c.get('canonical_url', 'Unknown')}\\nGame: {c.get('game_title', 'Unknown')}\\nCharacters Involved: {c.get('characters_involved', 'None')}\\nContext (Lore): {c.get('lore_summary', 'None')}\\nEvent (Cause): {c.get('trigger', 'Unknown')}\\nJonesy's Reaction (Effect): {c.get('reaction', 'Unknown')}\\nSubmitted By: {c.get('submitted_by_discord_id', 'Unknown')}\\n"

                category_prompt = f"""Write 5 diverse trivia questions for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL CLIP DATA:{clip_data_str}

Create 5 "Cause and Effect" questions. Example: "What caused Jonesy to drop her controller during her Phasmophobia stream?"
Use the provided Characters Involved and Context to create rich, specific questions.
Autonomously determine difficulty: For obscure details, provide 3 decoys and set question_type to 'multiple_choice'. For easier facts, set question_type to 'single_answer'.
Additionally, for each question, include the "clip_url" from the clip it was based on, and write a custom Ash "commentary" string to be displayed alongside the answer.
IMPORTANT: Ash uses he/him pronouns. You MUST credit the discord user who submitted the clip in your commentary using their Discord ID. (e.g. "I can confirm Jonesy was in a state of alarm. I have prepared this visual evidence for review, courtesy of Archival Agent <@123456789>.")
Return strictly as a raw JSON array containing exactly 5 generated questions.
DO NOT output a schema or placeholder text. You must generate REAL trivia questions based on the clip data.
Each object in the JSON array MUST follow this exact format:
[
  {{
    "question_text": "Write the actual question here based on the clip",
    "question_type": "multiple_choice",
    "correct_answer": "The real answer",
    "decoy_1": "A real fake option",
    "decoy_2": "Another real fake option",
    "decoy_3": "A third real fake option",
    "clip_url": "The provided URL",
    "commentary": "Ash's commentary"
  }}
]
"""
                selected_category = cat

            elif cat == 'Clip_Quote_Guess':
                clips = current_db.trivia.get_random_clip_lore(
                    limit=10,
                    required_fields=[
                        'notable_quote',
                        'characters_involved',
                        'game_title',
                        'canonical_url',
                        'lore_summary'])
                clips = [c for c in clips if c.get('canonical_url') not in avoid_clips]
                if not clips:
                    print("⚠️ TRIVIA DIRECTOR: Not enough clips for Clip_Quote_Guess")
                    continue
                selected_clips = random.sample(clips, min(2, len(clips)))
                correct_answer = None
                is_json_response = True
                print(f"✅ TRIVIA DIRECTOR: Got {len(selected_clips)} clip(s) for Clip_Quote_Guess")

                clip_data_str = ""
                for idx, c in enumerate(selected_clips):
                    clip_data_str += f"\\nCLIP {idx+1}:\\nURL: {c.get('canonical_url', 'Unknown')}\\nGame Title (THIS MUST BE THE CORRECT ANSWER): {c.get('game_title', 'Unknown')}\\nCharacters Involved: {c.get('characters_involved', 'None')}\\nContext (Lore): {c.get('lore_summary', 'None')}\\nNotable Quote: \\\"{c.get('notable_quote', '')}\\\"\\nSubmitted By: {c.get('submitted_by_discord_id', 'Unknown')}\\n"

                category_prompt = f"""Write 5 diverse trivia questions for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL CLIP DATA:{clip_data_str}

Create 5 "Quote Guess" questions. Example: "Which game caused Jonesy to say X when facing an arachnid enemy?"
The correct answer MUST ALWAYS be the 'Game Title' associated with the clip.
Use the provided Characters Involved, Context, and Notable Quote to create rich, specific questions.
Autonomously determine difficulty: For obscure details, provide 3 decoys (which should be names of other games) and set question_type to 'multiple_choice'. For easier facts, set question_type to 'single_answer'.
Additionally, for each question, include the "clip_url" from the clip it was based on, and write a custom Ash "commentary" string to be displayed alongside the answer.
IMPORTANT: Ash uses he/him pronouns. You MUST credit the discord user who submitted the clip in your commentary using their Discord ID. (e.g. "I can confirm Jonesy was in a state of alarm. I have prepared this visual evidence for review, courtesy of Archival Agent <@123456789>.")
Return strictly as a raw JSON array containing exactly 5 generated questions.
DO NOT output a schema or placeholder text. You must generate REAL trivia questions based on the clip data.
Each object in the JSON array MUST follow this exact format:
[
  {{
    "question_text": "Write the actual question here based on the clip",
    "question_type": "multiple_choice",
    "correct_answer": "The real answer",
    "decoy_1": "A real fake option",
    "decoy_2": "Another real fake option",
    "decoy_3": "A third real fake option",
    "clip_url": "The provided URL",
    "commentary": "Ash's commentary"
  }}
]
"""
                selected_category = cat

            elif cat == 'Clip_What_Happened_Next':
                clips = current_db.trivia.get_random_clip_lore(
                    limit=10,
                    required_fields=[
                        'trigger',
                        'clip_outcome',
                        'reaction',
                        'lore_summary',
                        'canonical_url',
                        'game_title'])
                clips = [c for c in clips if c.get('canonical_url') not in avoid_clips]
                if not clips:
                    print("⚠️ TRIVIA DIRECTOR: Not enough clips for Clip_What_Happened_Next")
                    continue
                selected_clips = random.sample(clips, min(2, len(clips)))
                correct_answer = None
                is_json_response = True
                print(f"✅ TRIVIA DIRECTOR: Got {len(selected_clips)} clip(s) for Clip_What_Happened_Next")

                clip_data_str = ""
                for idx, c in enumerate(selected_clips):
                    clip_data_str += f"\\nCLIP {idx+1}:\\nURL: {c.get('canonical_url', 'Unknown')}\\nGame: {c.get('game_title', 'Unknown')}\\nContext (Lore): {c.get('lore_summary', 'None')}\\nEvent (Trigger): {c.get('trigger', 'Unknown')}\\nOutcome/Reaction (THIS IS THE CORRECT ANSWER): {c.get('clip_outcome', 'Unknown')} - {c.get('reaction', 'Unknown')}\\nSubmitted By: {c.get('submitted_by_discord_id', 'Unknown')}\\n"

                category_prompt = f"""Write 5 diverse trivia questions for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

REAL CLIP DATA:{clip_data_str}

Create 5 "What happened next?" questions.
Example: "In Lethal Company, Jonesy confidently told the team 'I'll check the basement' and walked into the darkness. What happened next?"
The question text MUST act as a narrator, setting the scene using the Game Title, Context, and Trigger. It must end with "What happened next?" (or a similar phrasing).
The correct answer must be a description of the actual Outcome/Reaction.
You must invent 3 highly plausible decoy outcomes for the multiple choice options.
Autonomously determine difficulty: For obscure details, provide 3 decoys and set question_type to 'multiple_choice'. For easier facts, set question_type to 'single_answer'.
Additionally, for each question, include the "clip_url" from the clip it was based on, and write a custom Ash "commentary" string to be displayed alongside the answer.
IMPORTANT: Ash uses he/him pronouns. You MUST credit the discord user who submitted the clip in your commentary using their Discord ID. (e.g. "I can confirm Jonesy was in a state of alarm. I have prepared this visual evidence for review, courtesy of Archival Agent <@123456789>.")
Return strictly as a raw JSON array containing exactly 5 generated questions.
DO NOT output a schema or placeholder text. You must generate REAL trivia questions based on the clip data.
Each object in the JSON array MUST follow this exact format:
[
  {{
    "question_text": "Write the actual question here based on the clip",
    "question_type": "multiple_choice",
    "correct_answer": "The real answer",
    "decoy_1": "A real fake option",
    "decoy_2": "Another real fake option",
    "decoy_3": "A third real fake option",
    "clip_url": "The provided URL",
    "commentary": "Ash's commentary"
  }}
]
"""
                selected_category = cat

            elif cat == 'Franchise_Lore':
                # AI-driven franchise question kept for variety
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
                    category_prompt = f"""Write 5 diverse trivia questions for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

Jonesy has played these {chosen_series_fl} games: {', '.join(game_names_fl)}

Write 5 engaging trivia questions about the {chosen_series_fl} franchise testing knowledge of recurring characters, themes, or mechanics. DO NOT ask about release dates.
Autonomously determine difficulty: For obscure details, provide 3 decoys and set question_type to 'multiple_choice'. For easier facts, set question_type to 'single_answer'.
Return strictly as a raw JSON array containing exactly 5 generated questions.
DO NOT output a schema or placeholder text. You must generate REAL trivia questions based on the games data.
Each object in the JSON array MUST follow this exact format:
[
  {
    "question_text": "Write the actual question here",
    "question_type": "multiple_choice",
    "correct_answer": "The real answer",
    "decoy_1": "A real fake option",
    "decoy_2": "Another real fake option",
    "decoy_3": "A third real fake option"
  }
]
"""
                elif all_games:
                    game_fl = random.choice(all_games)
                    source_games = [game_fl]
                    correct_answer = None
                    is_json_response = True

                    print(f"✅ TRIVIA DIRECTOR: Got 1 game for 'Franchise_Lore' (fallback)")
                    category_prompt = f"""Write 5 diverse trivia questions for fans of Captain Jonesy's gaming channel.
Jonesy uses she/her pronouns.

Jonesy has played: {game_fl['canonical_name']} ({game_fl.get('genre', 'Unknown')})

Write 5 engaging trivia questions about {game_fl['canonical_name']} testing memorable game knowledge. DO NOT ask about release dates.
Autonomously determine difficulty: For obscure details, provide 3 decoys and set question_type to 'multiple_choice'. For easier facts, set question_type to 'single_answer'.
Return strictly as a raw JSON array containing exactly 5 generated questions.
DO NOT output a schema or placeholder text. You must generate REAL trivia questions based on the games data.
Each object in the JSON array MUST follow this exact format:
[
  {
    "question_text": "Write the actual question here",
    "question_type": "multiple_choice",
    "correct_answer": "The real answer",
    "decoy_1": "A real fake option",
    "decoy_2": "Another real fake option",
    "decoy_3": "A third real fake option"
  }
]
"""
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

                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Quickest_Completion'")

                phrasing_qc = random.choice([
                    f"Which of Jonesy's completed {chosen_genre_qc} games did she finish in the fewest episodes?",
                    f"Jonesy's {chosen_genre_qc} completions — which game wrapped up in the least episodes?",
                    f"Among Jonesy's {chosen_genre_qc} games, which did she complete most quickly by episode count?",
                    f"What was Jonesy's fastest {chosen_genre_qc} game completion in terms of total episodes?",
                    f"Which {chosen_genre_qc} game did Jonesy manage to beat in the fewest number of episodes?",
                    f"Of all the {chosen_genre_qc} games she's finished, which one had the shortest episode list?",
                    f"Which {chosen_genre_qc} title did Jonesy speed through with the lowest episode count?",
                    f"Looking at completed {chosen_genre_qc} games, which one took the fewest episodes to beat?"
                ])
                final_question_text = phrasing_qc
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

                print(f"✅ TRIVIA DIRECTOR: Got {len(source_games)} game(s) for 'Genre_Pioneer'")

                phrasing_gp = random.choice([
                    f"What was the first {chosen_genre_gp} game Jonesy played on her channel?",
                    f"Which {chosen_genre_gp} game kicked off Jonesy's journey in that genre?",
                    f"Of all Jonesy's {chosen_genre_gp} games, which did she play first on the channel?",
                    f"If we look back, what was Jonesy's very first foray into the {chosen_genre_gp} genre?",
                    f"Which game holds the title of Jonesy's first ever {chosen_genre_gp} playthrough?",
                    f"Going back to the beginning, what was the first {chosen_genre_gp} game featured on the channel?",
                    f"What {chosen_genre_gp} game did Jonesy play before any others in that genre?",
                    f"Which title introduced the {chosen_genre_gp} genre to Jonesy's channel?"
                ])
                final_question_text = phrasing_gp
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

                print(f"✅ TRIVIA DIRECTOR: Found {len(series_games_ste)} game(s) for 'Series_Total_Episodes'")

                phrasing_ste = random.choice([
                    f"How many total episodes has Jonesy played across all her {chosen_series_ste} games?",
                    f"Combined across every {chosen_series_ste} game, how many episodes has Jonesy recorded?",
                    f"What's the total episode count for Jonesy's entire {chosen_series_ste} playthrough series?",
                    f"If you add up every episode of {chosen_series_ste} Jonesy has ever made, what's the total?",
                    f"How many times has Jonesy hit record while playing a {chosen_series_ste} game?",
                    f"What is the grand total of {chosen_series_ste} episodes available on Jonesy's channel?",
                    f"Across the entire {chosen_series_ste} franchise, how many episodes has Jonesy uploaded?",
                    f"Add up all the {chosen_series_ste} games — how many episodes in total did Jonesy play?"
                ])
                final_question_text = phrasing_ste
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
                    f"Between {game1_pb['canonical_name']} and {game2_pb['canonical_name']}, which game consumed more of Jonesy's time?",
                    f"Which of these two games boasts a higher playtime on the channel: {game1_pb['canonical_name']} or {game2_pb['canonical_name']}?",
                    f"Did Jonesy rack up more total hours playing {game1_pb['canonical_name']} or {game2_pb['canonical_name']}?",
                    f"In a battle of playtime, who wins out: {game1_pb['canonical_name']} or {game2_pb['canonical_name']}?",
                    f"Which game stole more hours of Jonesy's life: {game1_pb['canonical_name']} or {game2_pb['canonical_name']}?"
                ])
                final_question_text = phrasing_pb
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
                    f"Do you know what year {chosen_game_ry['canonical_name']} first hit the shelves?",
                    f"Which year did the game {chosen_game_ry['canonical_name']} officially come out?",
                    f"Jonesy played {chosen_game_ry['canonical_name']}, but what year was it originally published?",
                    f"What year did {chosen_game_ry['canonical_name']} make its debut in the gaming world?",
                    f"Can you name the exact release year of {chosen_game_ry['canonical_name']}?"
                ])
                final_question_text = phrasing_ry
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
                    f"Out of these titles, which one racked up the most views on Jonesy's YouTube channel?",
                    f"Which of these games was the biggest hit on YouTube by view count?",
                    f"If you check the YouTube stats, which of these Jonesy playthroughs is the most viewed?",
                    f"Which of the following games drew the largest YouTube audience for Jonesy?",
                    f"Out of this list, which game's playlist has the most total views on YouTube?"
                ])
                final_question_text = f"{phrasing_yt} Options: {', '.join(names_yt)}"
                selected_category = cat

            # --- If we couldn't build a prompt for this category, skip it ---
            if not selected_category or (not category_prompt and not final_question_text):
                continue

            # === PROMPT IS READY: LOG SELECTION AND CALL AI (IF LORE) ===
            print(f"🎮 TRIVIA DIRECTOR: Selected '{selected_category}' | Answer: {correct_answer or 'AI-determined'}")

            ai_question = None
            temperature = 0.0  # Default if AI is skipped

            if final_question_text and selected_category != 'Franchise_Lore':
                # HYBRID APPROACH: Skip AI for statistical questions
                print(f"✅ TRIVIA DIRECTOR: Using pre-generated phrasing for {selected_category}, skipping AI call.")
                q_text = final_question_text
                if q_text and not q_text.endswith('?'):
                    q_text += '?'
                ai_question = {
                    "question_text": q_text,
                    "question_type": "single_answer",
                    "correct_answer": correct_answer
                }
                raw_questions = [ai_question]
            else:
                # FRANCHISE_LORE OR OTHER AI CATEGORY
                prompt = category_prompt
                if avoid_questions:
                    avoid_text = "\\n\\n🚫 AVOID questions similar to:\\n"
                    # Use up to 15 questions, taking the newest ones from the front
                    avoid_text += "\\n".join([f"  - {q[:60]}..." for q in avoid_questions[:15]])
                    prompt = str(prompt) + avoid_text  # type: ignore

                CATEGORY_TEMPERATURES = {
                    'Franchise_Lore': 0.9,
                    'Clip_Famous_Last_Words': 0.8,
                    'Clip_Vibe_Check': 0.8,
                    'Clip_Cause_And_Effect': 0.8,
                }
                temperature = CATEGORY_TEMPERATURES.get(selected_category, 0.9)
                print(f"🌡️ TRIVIA DIRECTOR: Using temperature {temperature} for '{selected_category}'")

                response_text, status_message = await call_ai_for_generation(
                    prompt,
                    context=context,
                    temperature=temperature
                )

                if not response_text:
                    print(f"❌ TRIVIA DIRECTOR: AI call failed: {status_message}")
                    break  # API failure - don't retry, preserve quota

                if is_json_response:
                    parsed_response = robust_json_parse(response_text)
                    if isinstance(parsed_response, list):
                        raw_questions = parsed_response
                    elif isinstance(parsed_response, dict):
                        raw_questions = [parsed_response]
                    else:
                        raw_questions = []
                else:
                    q_text = response_text.strip().strip('"').strip("'").strip()
                    for prefix in ['Question:', 'Here is a question:', "Here's a question:",
                                   'Trivia question:', 'Here you go:']:
                        if q_text.lower().startswith(prefix.lower()):
                            q_text = q_text[len(prefix):].strip()
                    if q_text and not q_text.endswith('?'):
                        q_text += '?'

                    if 10 <= len(q_text) <= 250:
                        raw_questions = [{
                            "question_text": q_text,
                            "question_type": "single_answer",
                            "correct_answer": correct_answer
                        }]
                    else:
                        raw_questions = []

            # Validate and filter generated questions
            valid_questions = []
            for q_data in raw_questions:
                if not q_data or not all(
                    key in q_data for key in ["question_text", "question_type", "correct_answer"]
                ):
                    continue

                # Check for multiple_choice required fields
                if q_data.get("question_type") == "multiple_choice":  # type: ignore
                    if not all(key in q_data for key in ["decoy_1", "decoy_2", "decoy_3"]):
                        print(f"⚠️ TRIVIA DIRECTOR: Discarding multiple_choice question missing decoys")
                        continue

                    # Compile options
                    opts = [
                        q_data["correct_answer"],
                        q_data["decoy_1"],
                        q_data["decoy_2"],
                        q_data["decoy_3"]
                    ]
                    random.shuffle(opts)
                    q_data["multiple_choice_options"] = opts

                # Check for duplicates before accepting
                duplicate_info = current_db.check_question_duplicate(
                    q_data["question_text"],  # type: ignore
                    similarity_threshold=0.8
                )

                if duplicate_info:
                    print(
                        f"🔍 TRIVIA DIRECTOR: Duplicate detected: "
                        f"{duplicate_info['similarity_score']:.2f} similarity to question #{duplicate_info['duplicate_id']}")
                    continue  # Skip this specific duplicate

                # Add metadata
                q_data.update({  # type: ignore
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

                if selected_category and selected_category.startswith("Clip_"):
                    clip_url = q_data.pop("clip_url", None)  # type: ignore
                    commentary = q_data.pop("commentary", None)  # type: ignore
                    if clip_url and commentary:
                        import json
                        q_data["dynamic_query_type"] = json.dumps({  # type: ignore
                            "clip_url": clip_url,
                            "commentary": commentary
                        })

                valid_questions.append(q_data)

            if not valid_questions:
                print(f"⚠️ TRIVIA DIRECTOR: All parsed questions were invalid or duplicates")
                continue  # Try different category

            print(f"✅ TRIVIA DIRECTOR: Generated {len(valid_questions)} valid question(s) successfully!")
            return valid_questions

        print(f"❌ TRIVIA DIRECTOR: All 3 generation attempts failed")
        return []

    except Exception as e:
        print(f"❌ Error in diverse trivia generation: {e}")
        traceback.print_exc()
        return []


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
