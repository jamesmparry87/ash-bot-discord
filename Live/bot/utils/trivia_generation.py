"""
Trivia Question Generation Utilities

Handles AI-powered and data-driven trivia question generation including:
- YouTube analytics-based questions
- AI-enhanced questions with real data
- Fallback AI generation with quality validation
"""

import asyncio
import logging
import random
from typing import Optional

from .trivia_formatting import format_view_count_range, get_episode_range_choices
from .trivia_parsing import validate_question_quality

logger = logging.getLogger(__name__)


async def generate_youtube_analytics_question(db=None):
    """
    Generate trivia questions powered by real YouTube analytics data
    
    Args:
        db: Database instance for duplicate checking (optional)
    
    Returns:
        dict: Question data or None if generation fails
    """
    try:
        # Try to get YouTube data
        try:
            from ..integrations.youtube import get_most_viewed_game_overall

            # First, try to get overall most viewed data
            overall_data = await get_most_viewed_game_overall()

            if overall_data and 'most_viewed_game' in overall_data:
                logger.info("YouTube analytics data retrieved successfully")

                # Question type options based on available data
                question_types = []

                most_viewed = overall_data['most_viewed_game']
                runner_up = overall_data.get('runner_up')

                # Direct fact questions about most viewed game
                question_types.extend([
                    {
                        'type': 'most_viewed_direct',
                        'question': f"Which game has the most YouTube views on Captain Jonesy's channel?",
                        'answer': most_viewed['name'],
                        'data': {
                            'total_views': most_viewed['total_views'],
                            'episodes': most_viewed['total_episodes']
                        }
                    },
                    {
                        'type': 'view_count_range',
                        'question': f"Approximately how many total YouTube views does '{most_viewed['name']}' have?",
                        'answer': format_view_count_range(most_viewed['total_views']),
                        'data': {'actual_views': most_viewed['total_views']}
                    }
                ])

                # Comparative questions if we have runner-up data
                if runner_up:
                    question_types.append({
                        'type': 'comparative_views',
                        'question': f"Which game has more YouTube views: '{most_viewed['name']}' or '{runner_up['name']}'?",
                        'answer': most_viewed['name'],
                        'data': {
                            'winner_views': most_viewed['total_views'],
                            'runner_up_views': runner_up['total_views']
                        }
                    })

                # Episode count questions
                if most_viewed.get('total_episodes', 0) > 0:
                    episode_ranges = get_episode_range_choices(most_viewed['total_episodes'])
                    question_types.append({
                        'type': 'episode_count_multiple',
                        'question': f"How many episodes does '{most_viewed['name']}' have on Captain Jonesy's YouTube channel?",
                        'answer': episode_ranges['correct_letter'],
                        'choices': episode_ranges['choices'],
                        'correct_choice': episode_ranges['correct_letter'],
                        'data': {'actual_episodes': most_viewed['total_episodes']}
                    })

                # AI-enhanced questions with real data
                if most_viewed['total_views'] > 1000000:  # Only for popular games
                    question_types.append({
                        'type': 'ai_enhanced_popularity',
                        'prompt_data': {
                            'game_name': most_viewed['name'],
                            'total_views': most_viewed['total_views'],
                            'episodes': most_viewed['total_episodes'],
                            'avg_views': most_viewed.get('average_views_per_episode', 0)
                        }
                    })

                # Select a random question type
                selected = random.choice(question_types)

                if selected['type'] == 'ai_enhanced_popularity':
                    # Generate AI question with real data
                    return await generate_ai_enhanced_question(selected['prompt_data'])
                elif selected['type'] == 'episode_count_multiple':
                    # Return multiple choice question
                    return {
                        'question_text': selected['question'],
                        'correct_answer': selected['correct_choice'],
                        'question_type': 'multiple_choice',
                        'multiple_choice_options': selected['choices'],
                        'category': 'youtube_analytics',
                        'difficulty_level': 2,
                        'is_dynamic': False
                    }
                else:
                    # Return single answer question
                    return {
                        'question_text': selected['question'],
                        'correct_answer': selected['answer'],
                        'question_type': 'single',
                        'category': 'youtube_analytics',
                        'difficulty_level': 2,
                        'is_dynamic': False
                    }
            else:
                logger.info("No YouTube analytics data available, skipping YouTube question generation")
                return None

        except ImportError:
            logger.info("YouTube integration not available for question generation")
            return None
        except Exception as youtube_error:
            logger.warning(f"YouTube analytics failed for question generation: {youtube_error}")
            return None

    except Exception as e:
        logger.error(f"Error in YouTube analytics question generation: {e}")
        return None


async def generate_ai_enhanced_question(prompt_data: dict, bot=None):
    """
    Generate AI question enhanced with real YouTube data
    
    Args:
        prompt_data: Dict with game_name, total_views, episodes, avg_views
        bot: Bot instance for AI call (optional, will try to import if None)
    
    Returns:
        dict: Question data or None if generation fails
    """
    try:
        from ..config import JAM_USER_ID
        from ..handlers.ai_handler import call_ai_with_rate_limiting

        # Create data-rich prompt for AI
        prompt = (
            f"Generate a trivia question about Captain Jonesy's YouTube gaming content using this REAL data:\n\n"
            f"Game: '{prompt_data['game_name']}'\n"
            f"Total Views: {prompt_data['total_views']:,}\n"
            f"Episodes: {prompt_data['episodes']}\n"
            f"Average Views per Episode: {prompt_data.get('avg_views', 0):,}\n\n"
            f"Create a question that fans could reasonably answer about this game's popularity or viewership. "
            f"Use the real data but make it accessible (e.g., 'over 2 million views' instead of exact numbers). "
            f"Focus on what viewers would notice: high popularity, many episodes, successful series, etc.\n\n"
            f"Examples:\n"
            f"• 'Which game series has the most total YouTube views?'\n"
            f"• 'What is Captain Jonesy's most popular completed gaming series?'\n"
            f"• 'Which game has over 2 million YouTube views?'\n\n"
            f"Format: Question: [question] | Answer: [answer]"
        )

        response_text, status = await call_ai_with_rate_limiting(
            prompt, JAM_USER_ID, context="trivia_generation",
            member_obj=None, bot=bot)

        if response_text:
            # Parse response
            lines = response_text.strip().split('\n')
            question_text = ""
            answer = ""

            for line in lines:
                line = line.strip()
                if line.startswith("Question:"):
                    question_text = line.replace("Question:", "").strip()
                elif line.startswith("Answer:"):
                    answer = line.replace("Answer:", "").strip()

            # Fallback parsing
            if not question_text or not answer:
                for line in lines:
                    if '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            q_part = parts[0].strip()
                            a_part = parts[1].strip()
                            if 'Question:' in q_part or not question_text:
                                question_text = q_part.replace('Question:', '').strip()
                            if 'Answer:' in a_part or not answer:
                                answer = a_part.replace('Answer:', '').strip()

            if question_text and answer:
                # Clean up
                question_text = question_text.strip('?"')
                if not question_text.endswith('?'):
                    question_text += '?'

                return {
                    'question_text': question_text,
                    'correct_answer': answer.strip(),
                    'question_type': 'single',
                    'category': 'youtube_ai_enhanced',
                    'difficulty_level': 2,
                    'is_dynamic': False
                }

        logger.warning("AI-enhanced YouTube question generation failed to parse response")
        return None

    except Exception as e:
        logger.error(f"Error in AI-enhanced YouTube question generation: {e}")
        return None


async def generate_ai_question_fallback(db=None, bot=None, avoid_questions=None, avoid_templates=None):
    """
    Enhanced AI question generation with quality validation.

    Improvements:
    - Stricter prompts with clear guidelines
    - Quality validation before approval
    - Better error handling and retry logic
    - Enhanced parsing with fallbacks
    
    Args:
        db: Database instance for duplicate checking (optional)
        bot: Bot instance for AI calls (optional)
        avoid_questions: List of question texts to avoid (for diversity)
        avoid_templates: List of template IDs to avoid (for diversity)
    
    Returns:
        dict: Question data or None if generation fails
    """
    try:
        from ..config import JAM_USER_ID
        from ..handlers.ai_handler import call_ai_with_rate_limiting

        # Try YouTube analytics integration first for data-driven questions
        youtube_question = await generate_youtube_analytics_question(db)
        if youtube_question:
            logger.info("Generated YouTube analytics-powered trivia question")

            # Validate YouTube question quality
            is_valid, reason, score = validate_question_quality(youtube_question)
            if is_valid:
                logger.info(f"YouTube question quality: {score:.1f}% - {reason}")
                return youtube_question
            else:
                logger.warning(f"YouTube question failed quality check ({score:.1f}%): {reason}")
                # Fall through to traditional generation

        # Enhanced prompts with stricter guidelines
        question_types = [
            {
                'type': 'fan_observable',
                'prompt': (
                    "Generate a trivia question about Captain Jonesy's gaming that fans could answer from watching streams.\n\n"
                    "STRICT REQUIREMENTS:\n"
                    "- Question must be answerable by regular viewers\n"
                    "- Avoid exact statistics (episode counts, view numbers)\n"
                    "- Focus on patterns: genres, series, preferences\n"
                    "- ONE clear correct answer only\n"
                    "- Question must end with '?'\n"
                    "- Answer must be 2-30 words\n\n"
                    "GOOD: 'What genre does Captain Jonesy play most often?'\n"
                    "BAD: 'How many episodes of God of War has Jonesy uploaded?' (too specific)\n\n"
                    "Format EXACTLY: Question: [your question] | Answer: [your answer]"
                )
            },
            {
                'type': 'gaming_knowledge',
                'prompt': (
                    "Generate general gaming trivia related to games Captain Jonesy has played.\n\n"
                    "STRICT REQUIREMENTS:\n"
                    "- Focus on gaming industry knowledge\n"
                    "- Must relate to games Jonesy has streamed\n"
                    "- ONE clear factual answer\n"
                    "- Question must end with '?'\n"
                    "- Answer must be 2-30 words\n"
                    "- No ambiguous or subjective questions\n\n"
                    "GOOD: 'What genre is The Last of Us?'\n"
                    "BAD: 'What is the best game ever?' (subjective)\n\n"
                    "Format EXACTLY: Question: [your question] | Answer: [your answer]"
                )
            },
            {
                'type': 'broad_trends',
                'prompt': (
                    "Generate a trivia question about observable trends in Captain Jonesy's gaming.\n\n"
                    "STRICT REQUIREMENTS:\n"
                    "- Use broad categories (action vs RPG, horror vs platformer)\n"
                    "- Avoid exact numbers or dates\n"
                    "- Focus on comparative questions\n"
                    "- ONE clear correct answer\n"
                    "- Question must end with '?'\n"
                    "- Answer must be 2-30 words\n\n"
                    "GOOD: 'Does Jonesy play more horror or action games?'\n"
                    "BAD: 'Exactly how many horror games has Jonesy completed?' (too specific)\n\n"
                    "Format EXACTLY: Question: [your question] | Answer: [your answer]"
                )
            },
            {
                'type': 'series_knowledge',
                'prompt': (
                    "Generate trivia about game series Captain Jonesy has played.\n\n"
                    "STRICT REQUIREMENTS:\n"
                    "- Focus on multi-entry series (God of War, Resident Evil, etc.)\n"
                    "- Must be verifiable from stream history\n"
                    "- ONE clear correct answer\n"
                    "- Question must end with '?'\n"
                    "- Answer must be 2-30 words\n"
                    "- Avoid exact episode/date counts\n\n"
                    "GOOD: 'Which game series has Jonesy completed multiple entries from?'\n"
                    "BAD: 'On what date did Jonesy start God of War?' (too specific)\n\n"
                    "Format EXACTLY: Question: [your question] | Answer: [your answer]"
                )
            }
        ]

        # Retry logic for quality - try up to 2 times
        max_attempts = 2
        for attempt in range(max_attempts):
            # Randomly select a question type for variety
            selected_type = random.choice(question_types)

            logger.info(f"Generating trivia question (attempt {attempt + 1}/{max_attempts}): {selected_type['type']}")
            
            response_text, status = await call_ai_with_rate_limiting(
                selected_type['prompt'], JAM_USER_ID, context="trivia_generation",
                member_obj=None, bot=bot)

            if response_text:
                # Enhanced parsing with multiple fallback strategies
                question_text = ""
                answer = ""

                # Strategy 1: Line-by-line parsing
                lines = response_text.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith("Question:"):
                        question_text = line.replace("Question:", "").strip()
                    elif line.startswith("Answer:"):
                        answer = line.replace("Answer:", "").strip()

                # Strategy 2: Pipe-separated format
                if not question_text or not answer:
                    for line in lines:
                        if '|' in line:
                            parts = line.split('|')
                            if len(parts) >= 2:
                                q_part = parts[0].strip()
                                a_part = parts[1].strip()

                                # Extract question
                                if 'Question:' in q_part or not question_text:
                                    question_text = q_part.replace('Question:', '').strip()

                                # Extract answer
                                if 'Answer:' in a_part or not answer:
                                    answer = a_part.replace('Answer:', '').strip()

                # Strategy 3: First line as question, second as answer (last resort)
                if not question_text or not answer:
                    if len(lines) >= 2:
                        question_text = lines[0].strip()
                        answer = lines[1].strip()

                # Clean up
                if question_text and answer:
                    question_text = question_text.strip('?"\'')
                    if not question_text.endswith('?'):
                        question_text += '?'
                    answer = answer.strip('."\'')

                    # Create question data
                    question_data = {
                        'question_text': question_text,
                        'correct_answer': answer,
                        'question_type': 'single',
                        'category': f"ai_{selected_type['type']}",
                        'difficulty_level': 2,
                        'is_dynamic': False
                    }

                    # Validate quality before returning
                    is_valid, reason, quality_score = validate_question_quality(question_data)

                    if is_valid:
                        # Check for duplicates in AI-generated questions
                        if db and hasattr(db, 'check_question_duplicate'):
                            try:
                                duplicate_check = db.check_question_duplicate(question_text, similarity_threshold=0.85)

                                if duplicate_check:
                                    similarity = duplicate_check['similarity_score']
                                    duplicate_id = duplicate_check['duplicate_id']
                                    logger.warning(
                                        f"AI generated duplicate question ({similarity*100:.1f}% match to Q#{duplicate_id}), retrying...")
                                    # Continue to next attempt
                                    if attempt < max_attempts - 1:
                                        await asyncio.sleep(2)
                                        continue
                                    else:
                                        logger.error("All AI generation attempts produced duplicates")
                                        return None
                            except Exception as dup_error:
                                logger.warning(f"Duplicate check failed for AI question: {dup_error}")
                                # Continue with the question if duplicate check fails

                        logger.info(f"✅ Generated quality question (score: {quality_score:.1f}%): {question_text[:50]}...")
                        return question_data
                    else:
                        logger.warning(f"⚠️ Generated question failed quality check ({quality_score:.1f}%): {reason}")
                        # Try again if we have attempts left
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(2)  # Brief pause before retry
                            continue
                else:
                    logger.warning(f"AI parsing failed (attempt {attempt + 1}): Q='{question_text}', A='{answer}'")
            else:
                logger.warning(f"AI returned no response (attempt {attempt + 1})")

        # All attempts exhausted
        logger.error("All AI generation attempts failed quality validation")
        return None

    except Exception as e:
        logger.error(f"Error in enhanced AI generation: {e}")
        return None
