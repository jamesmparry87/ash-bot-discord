"""
Trivia Tuesday Command Module

Handles comprehensive trivia management including:
- Question submission and management
- Session management (start/end trivia)
- Leaderboard and statistics
- Question prioritization and AI generation
"""

import asyncio
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..config import JAM_USER_ID, JONESY_USER_ID
from ..database_module import DatabaseManager, get_database
from ..handlers.ai_handler import call_ai_with_rate_limiting
from ..handlers.conversation_handler import (
    force_reset_approval_session,
    jam_approval_conversations,
    start_jam_question_approval,
    start_trivia_conversation,
)
from ..integrations.youtube import get_most_viewed_game_overall, get_youtube_analytics_for_game
from ..utils.permissions import user_is_mod_by_id

# Set up logging
logger = logging.getLogger(__name__)

# Get database instance
db: DatabaseManager = get_database()


class TriviaCommands(commands.Cog):
    """Trivia Tuesday management commands"""

    def __init__(self, bot):
        self.bot = bot

    def _is_natural_multiple_choice_format(self, content: str) -> bool:
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

    def _validate_multiple_choice_options(self, choices: list, correct_answer: str) -> dict:
        """
        ✅ FIX #6: Validate multiple choice options for count and consistency

        Ensures:
        - Minimum 2 options (required for multiple choice)
        - Maximum 4 options (A, B, C, D limit)
        - Correct answer letter corresponds to valid option
        - No empty options

        Returns dict with 'valid' (bool) and 'error' (str if invalid)
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

    def _parse_natural_multiple_choice(self, content: str) -> Optional[dict]:
        """Parse natural multiple choice format into structured data"""
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

        # ✅ FIX #6: Apply comprehensive validation
        validation = self._validate_multiple_choice_options(choices, correct_answer)
        if not validation['valid']:
            logger.warning(f"Multiple choice validation failed: {validation['error']}")
            return None

        return {
            'question': question_text.strip(),
            'choices': choices,
            'answer': correct_answer,
        }

    async def _generate_youtube_analytics_question(self):
        """Generate trivia questions powered by real YouTube analytics data"""
        try:
            # Try to get YouTube data
            try:

                # First, try to get overall most viewed data
                overall_data = await get_most_viewed_game_overall()

                if overall_data and 'most_viewed_game' in overall_data:
                    logger.info("YouTube analytics data retrieved successfully")

                    # Question type options based on available data
                    question_types = []

                    most_viewed = overall_data['most_viewed_game']
                    runner_up = overall_data.get('runner_up')

                    # Direct fact questions about most viewed game
                    question_types.extend([{'type': 'most_viewed_direct',
                                            'question': f"Which game has the most YouTube views on Captain Jonesy's channel?",
                                            'answer': most_viewed['name'],
                                            'data': {'total_views': most_viewed['total_views'],
                                                     'episodes': most_viewed['total_episodes']}},
                                           {'type': 'view_count_range',
                                            'question': f"Approximately how many total YouTube views does '{most_viewed['name']}' have?",
                                            'answer': self._format_view_count_range(most_viewed['total_views']),
                                            'data': {'actual_views': most_viewed['total_views']}}])

                    # Comparative questions if we have runner-up data
                    if runner_up:
                        question_types.append({
                            'type': 'comparative_views',
                            'question': f"Which game has more YouTube views: '{most_viewed['name']}' or '{runner_up['name']}'?",
                            'answer': most_viewed['name'],
                            'data': {'winner_views': most_viewed['total_views'], 'runner_up_views': runner_up['total_views']}
                        })

                    # Episode count questions
                    if most_viewed.get('total_episodes', 0) > 0:
                        episode_ranges = self._get_episode_range_choices(most_viewed['total_episodes'])
                        question_types.append({
                            'type': 'episode_count_multiple',
                            'question': f"How many episodes does '{most_viewed['name']}' have on Captain Jonesy's YouTube channel?",
                            'answer': 'B',  # Will be set dynamically
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
                        return await self._generate_ai_enhanced_question(selected['prompt_data'])
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

    def _format_view_count_range(self, actual_views: int) -> str:
        """Format view count into a reasonable range for trivia answers"""
        if actual_views >= 10000000:  # 10M+
            return "Over 10 million"
        elif actual_views >= 5000000:  # 5M+
            return "5-10 million"
        elif actual_views >= 1000000:  # 1M+
            return "1-5 million"
        elif actual_views >= 500000:  # 500K+
            return "500K-1 million"
        elif actual_views >= 100000:  # 100K+
            return "100K-500K"
        else:
            return "Under 100K"

    def _get_episode_range_choices(self, actual_episodes: int) -> dict:
        """Generate multiple choice options for episode count questions"""
        # Create ranges around the actual number
        ranges = []

        if actual_episodes <= 5:
            ranges = ["1-5 episodes", "6-10 episodes", "11-20 episodes", "21+ episodes"]
            correct = 'A'
        elif actual_episodes <= 10:
            ranges = ["1-5 episodes", "6-10 episodes", "11-20 episodes", "21+ episodes"]
            correct = 'B'
        elif actual_episodes <= 20:
            ranges = ["1-10 episodes", "11-20 episodes", "21-30 episodes", "31+ episodes"]
            correct = 'B'
        elif actual_episodes <= 30:
            ranges = ["1-10 episodes", "11-20 episodes", "21-30 episodes", "31+ episodes"]
            correct = 'C'
        else:
            ranges = ["1-15 episodes", "16-30 episodes", "31-50 episodes", "50+ episodes"]
            correct = 'C' if actual_episodes <= 50 else 'D'

        return {
            'choices': ranges,
            'correct_letter': correct
        }

    async def _generate_ai_enhanced_question(self, prompt_data: dict):
        """Generate AI question enhanced with real YouTube data"""
        try:
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
                member_obj=None, bot=self.bot)

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

    def _validate_question_quality(self, question_data: dict) -> tuple[bool, str, float]:
        """
        ✅ FIX #5: Validate AI-generated question quality before approval.

        Checks for:
        - Question clarity and completeness
        - Answer appropriateness
        - No ambiguity or multiple interpretations
        - Fan-answerable difficulty

        Returns: (is_valid, reason, quality_score)
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

    async def _generate_ai_question_fallback(self):
        """
        ✅ FIX #5: Enhanced AI question generation with quality validation.

        Improvements:
        - Stricter prompts with clear guidelines
        - Quality validation before approval
        - Better error handling and retry logic
        - Enhanced parsing with fallbacks
        """
        try:
            # Try YouTube analytics integration first for data-driven questions
            youtube_question = await self._generate_youtube_analytics_question()
            if youtube_question:
                logger.info("Generated YouTube analytics-powered trivia question")

                # ✅ FIX #5: Validate YouTube question quality
                is_valid, reason, score = self._validate_question_quality(youtube_question)
                if is_valid:
                    logger.info(f"YouTube question quality: {score:.1f}% - {reason}")
                    return youtube_question
                else:
                    logger.warning(f"YouTube question failed quality check ({score:.1f}%): {reason}")
                    # Fall through to traditional generation

            # ✅ FIX #5: Enhanced prompts with stricter guidelines
            question_types = [
                {
                    'type': 'fan_observable', 'prompt': (
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
                        "Format EXACTLY: Question: [your question] | Answer: [your answer]")}, {
                    'type': 'gaming_knowledge', 'prompt': (
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
                        "Format EXACTLY: Question: [your question] | Answer: [your answer]")}, {
                    'type': 'broad_trends', 'prompt': (
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
                            "Format EXACTLY: Question: [your question] | Answer: [your answer]")}, {
                                'type': 'series_knowledge', 'prompt': (
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
                                    "Format EXACTLY: Question: [your question] | Answer: [your answer]")}]

            # ✅ FIX #5: Retry logic for quality - try up to 2 times
            max_attempts = 2
            for attempt in range(max_attempts):
                # Randomly select a question type for variety
                selected_type = random.choice(question_types)

                logger.info(
                    f"Generating trivia question (attempt {attempt + 1}/{max_attempts}): {selected_type['type']}")
                response_text, status = await call_ai_with_rate_limiting(
                    selected_type['prompt'], JAM_USER_ID, context="trivia_generation",
                    member_obj=None, bot=self.bot)

                if response_text:
                    # ✅ FIX #5: Enhanced parsing with multiple fallback strategies
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

                        # ✅ FIX #5: Validate quality before returning
                        is_valid, reason, quality_score = self._validate_question_quality(question_data)

                        if is_valid:
                            # ✅ FIX #4: Check for duplicates in AI-generated questions
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

                            logger.info(
                                f"✅ Generated quality question (score: {quality_score:.1f}%): {question_text[:50]}...")
                            return question_data
                        else:
                            logger.warning(
                                f"⚠️ Generated question failed quality check ({quality_score:.1f}%): {reason}")
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

    @commands.command(name="addtrivia")
    async def add_trivia_question(self, ctx, *, content: Optional[str] = None):
        """Add a trivia question to the database (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** Trivia question submission requires moderator privileges.")
                return

            # If in DM, route to conversation handler for enhanced experience
            if ctx.guild is None:
                from ..handlers.conversation_handler import start_trivia_conversation
                await start_trivia_conversation(ctx)
                return

            if not content:
                # Progressive disclosure help
                help_text = (
                    "**Add Trivia Question Format:**\n"
                    "`!addtrivia <question> | answer:<correct_answer> | type:single`\n"
                    "`!addtrivia <question> | answer:<correct_answer> | choices:A,B,C,D | type:multiple`\n\n"
                    "**Examples:**\n"
                    "• `!addtrivia What game has the most playtime? | answer:God of War | type:single`\n"
                    "• `!addtrivia Which genre does Jonesy play most? | answer:B | choices:Action,RPG,Horror,Puzzle | type:multiple`\n\n"
                    "**Parameters:**\n"
                    "• **question:** The trivia question text\n"
                    "• **answer:** Correct answer\n"
                    "• **type:** single or multiple choice\n"
                    "• **choices:** Comma-separated options (multiple choice only)")
                await ctx.send(help_text)
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot add trivia questions without database connection.")
                return

            # Check if trivia methods exist
            if not hasattr(db, 'add_trivia_question'):
                await ctx.send("❌ **Trivia system not available.** Database methods need implementation.\n\n*Required method: `add_trivia_question(question, answer, question_type, choices, created_by)`*")
                return

            # Check if this is natural multiple choice format (contains A. B. C. pattern)
            if self._is_natural_multiple_choice_format(content):
                parsed_data = self._parse_natural_multiple_choice(content)
                if not parsed_data:
                    await ctx.send("❌ **Invalid multiple choice format.** Expected format:\n```\nQuestion text?\nA Option 1\nB Option 2\nC Option 3\nCorrect answer: B```")
                    return

                question_text = parsed_data['question']
                answer = parsed_data['answer']
                question_type = 'multiple'
                choices = parsed_data['choices']

            else:
                # Parse traditional pipe-separated format
                parts = content.split(' | ')
                if len(parts) < 3:
                    await ctx.send("❌ **Invalid format.** Use: `!addtrivia <question> | answer:<answer> | type:<single/multiple>`")
                    return

                question_text = parts[0].strip()

                # Parse answer
                answer = None
                question_type = "single"  # default
                choices = []

                for part in parts[1:]:
                    if ':' in part:
                        key, value = part.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip()

                        if key == 'answer':
                            answer = value
                        elif key == 'type':
                            if value.lower() in ['single', 'multiple']:
                                question_type = value.lower()
                            else:
                                await ctx.send("❌ **Invalid type.** Use: single or multiple")
                                return
                        elif key == 'choices':
                            choices = [choice.strip()
                                       for choice in value.split(',')]

                if not answer:
                    await ctx.send("❌ **Answer is required.** Format: `| answer:<correct_answer>`")
                    return

                if question_type == 'multiple':
                    if not choices:
                        await ctx.send("❌ **Choices required for multiple choice.** Format: `| choices:A,B,C,D`")
                        return

                    # ✅ FIX #6: Validate multiple choice options for pipe-separated format
                    validation = self._validate_multiple_choice_options(choices, answer)
                    if not validation['valid']:
                        await ctx.send(f"❌ **Multiple choice validation failed:** {validation['error']}\n\n*Ensure you have 2-4 options and the correct answer (A-D) matches an available option.*")
                        return

            if len(question_text) < 10:
                await ctx.send("❌ **Question too short.** Please provide a meaningful trivia question.")
                return

            # ✅ FIX #3: Validate question quality for manual submissions
            question_data_for_validation = {
                'question_text': question_text,
                'correct_answer': answer,
                'question_type': question_type
            }

            is_valid, reason, quality_score = self._validate_question_quality(question_data_for_validation)

            if not is_valid:
                await ctx.send(
                    f"❌ **Question quality check failed** (score: {quality_score:.0f}%):\n"
                    f"**Issues:** {reason}\n\n"
                    f"*Please revise your question to improve clarity and answerability.*"
                )
                logger.warning(
                    f"Manual question submission failed quality check: {reason} (score: {quality_score:.0f}%)")
                return
            elif quality_score < 80:
                # Warn but allow submission if score is between 60-80
                logger.info(f"Manual question submission has moderate quality: {quality_score:.0f}% - {reason}")

            # ✅ FIX #4: Check for duplicate questions before adding
            try:
                duplicate_check = db.check_question_duplicate(question_text, similarity_threshold=0.8)

                if duplicate_check:
                    # Found a similar question
                    duplicate_id = duplicate_check['duplicate_id']
                    duplicate_text = duplicate_check['duplicate_text']
                    similarity = duplicate_check['similarity_score']
                    duplicate_status = duplicate_check['status']

                    embed = discord.Embed(
                        title="⚠️ **Duplicate Question Detected**",
                        description=f"A similar question already exists in the database ({similarity*100:.1f}% match)",
                        color=0xffaa00
                    )

                    embed.add_field(
                        name="📋 **Your Question:**",
                        value=question_text[:200] + ("..." if len(question_text) > 200 else ""),
                        inline=False
                    )

                    embed.add_field(
                        name="🔍 **Existing Question:**",
                        value=f"**#{duplicate_id}** ({duplicate_status})\n{duplicate_text[:200] + ('...' if len(duplicate_text) > 200 else '')}",
                        inline=False)

                    embed.add_field(
                        name="💡 **Options:**",
                        value=(
                            "• Modify your question to make it more unique\n"
                            f"• Use existing question with `!starttrivia {duplicate_id}`\n"
                            "• If this is a false positive, contact a moderator"
                        ),
                        inline=False
                    )

                    await ctx.send(embed=embed)
                    logger.info(
                        f"Blocked duplicate question submission: {similarity*100:.1f}% match to Q#{duplicate_id}")
                    return

            except Exception as dup_error:
                logger.warning(f"Duplicate check failed, proceeding with addition: {dup_error}")
                # Continue with addition if duplicate check fails

            # Add to database
            try:
                question_id = db.add_trivia_question(  # type: ignore
                    question_text=question_text,
                    correct_answer=answer,
                    question_type=question_type,
                    multiple_choice_options=choices if choices else None,
                    submitted_by_user_id=ctx.author.id
                )

                if question_id:
                    type_text = f"{question_type} choice"
                    choices_text = f" (choices: {', '.join(choices)})" if choices else ""
                    await ctx.send(f"✅ **Trivia question #{question_id} added**\n\n**Type:** {type_text}\n**Question:** {question_text}\n**Answer:** {answer}{choices_text}\n\n*Use `!starttrivia {question_id}` to use this specific question*")
                else:
                    await ctx.send("❌ **Failed to add trivia question.** Database error occurred.")

            except Exception as e:
                print(f"❌ Error calling add_trivia_question: {e}")
                await ctx.send("❌ **Database method error.** The trivia system needs proper implementation.")

        except Exception as e:
            print(f"❌ Error in addtrivia command: {e}")
            await ctx.send("❌ System error occurred while adding trivia question.")

    @commands.command(name="starttrivia")
    @commands.has_permissions(manage_messages=True)
    async def start_trivia(self, ctx, question_id: Optional[int] = None):
        """Start a trivia session (moderators only)"""
        try:
            if db is None:
                await ctx.send("❌ **Database offline.** Cannot start trivia without database connection.")
                return

            # Check if trivia methods exist
            if not hasattr(db, 'start_trivia_session'):
                await ctx.send("❌ **Trivia session management not available.** Database methods need implementation.\n\n*Required methods: `start_trivia_session()`, `get_available_trivia_questions()`, `get_trivia_question()`*")
                return

            # Check if there's already an active session
            try:
                active_session = db.get_active_trivia_session()  # type: ignore
                if active_session:
                    await ctx.send("❌ **Trivia session already active.** Use `!endtrivia` to end the current session before starting a new one.")
                    return
            except BaseException:
                pass  # Method might not exist yet

            # Get question - either specified or auto-select
            question_data = None

            if question_id:
                try:
                    question_data = db.get_trivia_question(  # type: ignore
                        question_id)
                    if not question_data:
                        await ctx.send(f"❌ **Question #{question_id} not found.** Use `!listpendingquestions` to see available questions.")
                        return
                    if question_data.get('status') != 'available':
                        await ctx.send(f"❌ **Question #{question_id} is not available.** Status: {question_data.get('status', 'unknown')}")
                        return
                except Exception as e:
                    await ctx.send("❌ **Error retrieving specified question.** The question may not exist or database error occurred.")
                    return
            else:
                # Auto-select next question using priority system
                try:
                    available_questions = db.get_available_trivia_questions()  # type: ignore
                    if not available_questions:
                        await ctx.send("❌ **No available trivia questions.** Use `!addtrivia` to add questions first.")
                        return

                    # Priority 1: Recent mod-submitted questions (unused within 4 weeks)
                    # Priority 2: AI-generated questions focusing on statistical anomalies
                    # Priority 3: Any unused questions with 'available' status
                    # Use first available for now
                    question_data = available_questions[0]

                except Exception as e:
                    await ctx.send("❌ **Error selecting question.** Database method needs proper implementation.")
                    return

            # Start the trivia session
            try:
                session_id = db.start_trivia_session(  # type: ignore
                    question_id=question_data['id'],
                    started_by=ctx.author.id
                )

                if session_id:
                    # Create trivia announcement embed
                    embed = discord.Embed(
                        title="🧠 **Trivia Tuesday - Question Active!**",
                        description=question_data['question_text'],
                        color=0x00ff00,
                        timestamp=datetime.now(ZoneInfo("Europe/London"))
                    )

                    # Add choices for multiple choice
                    if question_data['question_type'] == 'multiple_choice' and question_data.get(
                            'multiple_choice_options'):
                        choices_text = '\n'.join([f"**{chr(65+i)}.** {choice}" for i,
                                                  choice in enumerate(question_data['multiple_choice_options'])])
                        embed.add_field(
                            name="📝 **Answer Choices:**",
                            value=choices_text,
                            inline=False)
                        embed.add_field(
                            name="💡 **How to Answer:**",
                            value="**Reply to this message** with the letter (A, B, C, D) of your choice!",
                            inline=False)
                    else:
                        embed.add_field(
                            name="💡 **How to Answer:**",
                            value="**Reply to this message** with your answer!",
                            inline=False)

                    embed.add_field(
                        name="⏰ **Session Info:**",
                        value=f"Session #{session_id} • Question #{question_data['id']}",
                        inline=False)
                    embed.set_footer(
                        text=f"Started by {ctx.author.display_name} • End with !endtrivia")

                    # Send question embed and capture message ID
                    question_message = await ctx.send(embed=embed)

                    # Send confirmation to moderator and capture message ID
                    confirmation_message = await ctx.send(f"✅ **Trivia session #{session_id} started** with question #{question_data['id']}.\n\n*Use `!endtrivia` when ready to reveal answers and end the session.*\n\n**Note:** Users should reply to either message above to submit answers.")

                    # Update session with message tracking information
                    try:
                        update_success = db.update_trivia_session_messages(  # type: ignore
                            session_id=session_id,
                            question_message_id=question_message.id,
                            confirmation_message_id=confirmation_message.id,
                            channel_id=ctx.channel.id
                        )

                        if update_success:
                            print(
                                f"✅ Trivia session {session_id} updated with message tracking: Q:{question_message.id}, C:{confirmation_message.id}")
                        else:
                            print(f"⚠️ Warning: Failed to update trivia session {session_id} with message IDs")

                    except Exception as msg_tracking_error:
                        print(f"❌ Error updating trivia session message tracking: {msg_tracking_error}")
                        # Continue anyway - session is still functional without message tracking

                else:
                    await ctx.send("❌ **Failed to start trivia session.** Database error occurred.")

            except Exception as e:
                print(f"❌ Error starting trivia session: {e}")
                await ctx.send("❌ **Database method error.** The trivia session system needs proper implementation.")

        except Exception as e:
            print(f"❌ Error in starttrivia command: {e}")
            await ctx.send("❌ System error occurred while starting trivia.")

    @commands.command(name="endtrivia")
    @commands.has_permissions(manage_messages=True)
    async def end_trivia(self, ctx):
        """End the current trivia session and reveal results (moderators only)"""
        try:
            if db is None:
                await ctx.send("❌ **Database offline.** Cannot end trivia without database connection.")
                return

            # Check if trivia methods exist
            if not hasattr(db, 'end_trivia_session'):
                await ctx.send("❌ **Trivia session management not available.** Database methods need implementation.\n\n*Required methods: `end_trivia_session()`, `get_active_trivia_session()`, `get_trivia_session_results()`*")
                return

            # Check for active session
            try:
                active_session = db.get_active_trivia_session()  # type: ignore
                if not active_session:
                    await ctx.send("❌ **No active trivia session.** Use `!starttrivia` to start a new session.")
                    return
            except Exception as e:
                await ctx.send("❌ **Error checking active session.** Database method needs implementation.")
                return

            # End the session and get results
            try:
                session_results = db.end_trivia_session(  # type: ignore
                    active_session['id'], ended_by=ctx.author.id)

                if session_results:
                    # Create results embed
                    embed = discord.Embed(
                        title="🏆 **Trivia Tuesday - Results!**",
                        description=f"**Question #{active_session['question_id']}:** {session_results['question']}",
                        color=0xffd700,  # Gold color
                        timestamp=datetime.now(ZoneInfo("Europe/London"))
                    )

                    # Show correct answer
                    embed.add_field(
                        name="✅ **Correct Answer:**",
                        value=f"**{session_results['correct_answer']}**",
                        inline=False)

                    # --- Enhanced Community Engagement Section ---
                    # Process participant lists
                    winner_id = session_results.get('first_correct', {}).get(
                        'user_id') if session_results.get('first_correct') else None
                    correct_user_ids = session_results.get('correct_user_ids', [])
                    incorrect_user_ids = session_results.get('incorrect_user_ids', [])

                    # Get list of users who were correct but NOT the first winner
                    other_correct_ids = [uid for uid in correct_user_ids if uid !=
                                         winner_id] if winner_id else correct_user_ids

                    # Show winner (first correct answer with Ash's analytical celebration)
                    if winner_id:
                        try:
                            winner_user = await self.bot.fetch_user(winner_id)
                            winner_name = winner_user.display_name if winner_user else f"User {winner_id}"
                        except Exception:
                            winner_name = f"User {winner_id}"

                        embed.add_field(
                            name="🎯 **Primary Objective: Achieved**",
                            value=f"**{winner_name}** demonstrated optimal response efficiency. First correct analysis recorded.",
                            inline=False)

                    # Acknowledge other correct users with analytical approval
                    if other_correct_ids:
                        mentions = [f"<@{uid}>" for uid in other_correct_ids]
                        embed.add_field(
                            name="📊 **Acceptable Performance**",
                            value=f"Additional personnel {', '.join(mentions)} also provided correct data. Mission parameters satisfied.",
                            inline=False)

                    # Encourage users who participated but got it wrong with clinical assessment
                    if incorrect_user_ids:
                        mentions = [f"<@{uid}>" for uid in incorrect_user_ids]
                        embed.add_field(
                            name="⚠️ **Mission Assessment: Performance Insufficient**",
                            value=f"Personnel {', '.join(mentions)} require recalibration. Analysis suggests additional database review recommended.",
                            inline=False)

                    # Show participation stats
                    total_participants = session_results.get('total_participants', 0)
                    correct_answers = session_results.get('correct_answers', 0)

                    if total_participants > 0:
                        accuracy = round((correct_answers / total_participants) * 100, 1)
                        embed.add_field(
                            name="📊 **Session Stats:**",
                            value=f"**Participants:** {total_participants}\n**Correct:** {correct_answers}\n**Accuracy:** {accuracy}%",
                            inline=True)
                    else:
                        embed.add_field(
                            name="📊 **Session Stats:**",
                            value="No participants this round.",
                            inline=True)

                    # Updated footer to promote leaderboard
                    embed.set_footer(
                        text=f"Session #{active_session['id']} ended by {ctx.author.display_name} | Use !trivialeaderboard to see the full standings!")

                    await ctx.send(embed=embed)

                    # NEW: Check if bonus round should be triggered (Ash is "annoyed")
                    if session_results.get('bonus_round_triggered', False):
                        bonus_reason = session_results.get('bonus_round_reason', 'Challenge parameters insufficient')

                        # Ash's "annoyed" bonus round message
                        bonus_message = (
                            f"⚠️ **RECALIBRATING DIFFICULTY MATRIX**\n\n"
                            f"Analysis indicates challenge parameters were... insufficient. "
                            f"{session_results.get('accuracy_rate', 0):.1%} success rate exceeds acceptable failure thresholds.\n\n"
                            f"*[Deploying enhanced difficulty protocols...]*\n\n"
                            f"The original assessment failed to adequately test personnel capabilities. "
                            f"Fascinating... and somewhat disappointing.\n\n"
                            f"**SECONDARY ASSESSMENT PROTOCOL WILL DEPLOY AUTOMATICALLY.**\n"
                            f"*Mission parameters require recalibration.*")

                        await ctx.send(bonus_message)

                        # Auto-start bonus round after a brief delay
                        await asyncio.sleep(3)

                        try:
                            # Get next available question for bonus round
                            bonus_question = db.get_next_trivia_question(exclude_user_id=ctx.author.id)

                            if bonus_question:
                                # Start bonus round session
                                bonus_session_id = db.create_trivia_session(
                                    bonus_question['id'],
                                    session_type="bonus"
                                )

                                if bonus_session_id:
                                    # Create bonus round embed with enhanced difficulty message
                                    bonus_embed = discord.Embed(
                                        title="⚡ **BONUS ROUND - ENHANCED DIFFICULTY PROTOCOL**",
                                        description=f"**Secondary assessment deployed.** Personnel demonstrated excessive competency. Difficulty parameters now recalibrated.\n\n📋 **ENHANCED QUESTION:**\n{bonus_question['question_text']}",
                                        color=0xff6600,  # Orange - warning color
                                        timestamp=datetime.now(ZoneInfo("Europe/London"))
                                    )

                                    # Add choices if multiple choice
                                    if bonus_question['question_type'] == 'multiple_choice' and bonus_question.get(
                                            'multiple_choice_options'):
                                        choices_text = '\n'.join([
                                            f"**{chr(65+i)}.** {choice}"
                                            for i, choice in enumerate(bonus_question['multiple_choice_options'])
                                        ])
                                        bonus_embed.add_field(
                                            name="📝 **Enhanced Options:**",
                                            value=choices_text,
                                            inline=False
                                        )

                                    bonus_embed.add_field(
                                        name="⚡ **Mission Parameters:**",
                                        value="**Reply to this message** with your enhanced analysis. Time limit reduced for increased difficulty.",
                                        inline=False)

                                    bonus_embed.add_field(
                                        name="🔬 **Bonus Session Info:**",
                                        value=f"Enhanced Protocol #{bonus_session_id} • Question #{bonus_question['id']}",
                                        inline=False)

                                    bonus_embed.set_footer(
                                        text=f"Bonus Round initiated by system recalibration • Enhanced difficulty active")

                                    # Send bonus question
                                    bonus_message = await ctx.send(embed=bonus_embed)

                                    # Update session with message tracking
                                    db.update_trivia_session_messages(
                                        bonus_session_id,
                                        bonus_message.id,
                                        bonus_message.id,
                                        ctx.channel.id
                                    )

                                    logger.info(f"Bonus round triggered: Session {bonus_session_id} started")
                                else:
                                    await ctx.send("⚠️ **System Error:** Bonus round initialization failed. Enhanced protocols unavailable.")
                            else:
                                await ctx.send("⚠️ **Insufficient Question Pool:** No available questions for bonus round deployment.")

                        except Exception as bonus_error:
                            logger.error(f"Error starting bonus round: {bonus_error}")
                            await ctx.send("⚠️ **Bonus Round Error:** Enhanced difficulty protocols encountered system malfunction.")

                    # Ensure minimum question pool after session
                    try:
                        pool_result = db.ensure_minimum_question_pool(5)
                        logger.info(f"Question pool management after trivia: {pool_result}")

                        if pool_result.get('still_needed', 0) > 0:
                            logger.warning(f"Question pool needs {pool_result['still_needed']} more questions")
                    except Exception as pool_error:
                        logger.error(f"Error managing question pool: {pool_error}")

                    # Thank you message (adjusted for potential bonus round)
                    if not session_results.get('bonus_round_triggered', False):
                        await ctx.send("🎉 **Thank you for participating in Trivia Tuesday!** Use `!trivialeaderboard` to see overall standings.")

                else:
                    await ctx.send("❌ **Failed to end trivia session.** Database error occurred.")

            except Exception as e:
                print(f"❌ Error ending trivia session: {e}")
                await ctx.send("❌ **Database method error.** The trivia results system needs proper implementation.")

        except Exception as e:
            print(f"❌ Error in endtrivia command: {e}")
            await ctx.send("❌ System error occurred while ending trivia.")

    @commands.command(name="trivialeaderboard")
    async def trivia_leaderboard(self, ctx, timeframe: str = "all"):
        """Show trivia participation and success statistics (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot show leaderboard without database connection.")
                return

            # Check if method exists
            if not hasattr(db, 'get_trivia_leaderboard'):
                await ctx.send("❌ **Trivia leaderboard not available.** Database method needs implementation.\n\n*Required method: `get_trivia_leaderboard(timeframe)`*")
                return

            # Validate timeframe
            valid_timeframes = ['all', 'month', 'week']
            if timeframe.lower() not in valid_timeframes:
                await ctx.send(f"❌ **Invalid timeframe.** Use: {', '.join(valid_timeframes)}")
                return

            try:
                leaderboard_data = db.get_trivia_leaderboard(  # type: ignore
                    timeframe.lower())

                if not leaderboard_data or not leaderboard_data.get(
                        'participants'):
                    await ctx.send(f"📊 **No trivia participation data found** for timeframe: {timeframe}")
                    return

                # Create leaderboard embed
                timeframe_text = timeframe.title() if timeframe != 'all' else 'All Time'
                embed = discord.Embed(
                    title=f"🏆 **Trivia Leaderboard - {timeframe_text}**",
                    color=0x00ff00,
                    timestamp=datetime.now(ZoneInfo("Europe/London"))
                )

                # Top participants
                participants = leaderboard_data['participants'][:10]  # Top 10
                leaderboard_text = ""

                for i, participant in enumerate(participants, 1):
                    try:
                        user = await self.bot.fetch_user(participant['user_id'])
                        name = user.display_name if user else f"User {participant['user_id']}"
                    except BaseException:
                        name = f"User {participant['user_id']}"

                    correct = participant.get('correct_answers', 0)
                    total = participant.get('total_answers', 0)
                    accuracy = round(
                        (correct / total) * 100,
                        1) if total > 0 else 0

                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
                    leaderboard_text += f"{medal} {name} • {correct}/{total} ({accuracy}%)\n"

                embed.add_field(
                    name="📈 **Top Participants:**",
                    value=leaderboard_text or "No participants yet",
                    inline=False)

                # Overall stats
                total_sessions = leaderboard_data.get('total_sessions', 0)
                total_questions = leaderboard_data.get('total_questions', 0)
                avg_participation = leaderboard_data.get(
                    'avg_participation_per_session', 0)

                stats_text = f"**Sessions:** {total_sessions}\n**Questions Used:** {total_questions}\n**Avg Participation:** {round(avg_participation, 1)} per session"
                embed.add_field(
                    name="📊 **Overall Stats:**",
                    value=stats_text,
                    inline=True)

                embed.set_footer(
                    text="Trivia Tuesday Statistics • Use !starttrivia to host a session")

                await ctx.send(embed=embed)

            except Exception as e:
                print(f"❌ Error getting trivia leaderboard: {e}")
                await ctx.send("❌ **Database method error.** The trivia leaderboard system needs proper implementation.")

        except Exception as e:
            print(f"❌ Error in trivialeaderboard command: {e}")
            await ctx.send("❌ System error occurred while retrieving leaderboard.")

    @commands.command(name="triviastats")
    async def trivia_stats(self, ctx, timeframe: str = "all"):
        """Show trivia participation statistics (public command)"""
        try:
            if db is None:
                await ctx.send("❌ **Database offline.** Cannot show stats without database connection.")
                return

            # Check if method exists
            if not hasattr(db, 'get_trivia_leaderboard'):
                await ctx.send("❌ **Trivia stats not available.** Database method needs implementation.")
                return

            # Validate timeframe
            valid_timeframes = ['all', 'month', 'week']
            if timeframe.lower() not in valid_timeframes:
                await ctx.send(f"❌ **Invalid timeframe.** Use: {', '.join(valid_timeframes)}")
                return

            try:
                leaderboard_data = db.get_trivia_leaderboard(timeframe.lower())

                if not leaderboard_data or not leaderboard_data.get('participants'):
                    await ctx.send(f"📊 **No trivia participation data found** for timeframe: {timeframe}")
                    return

                # Create stats embed (public-friendly version)
                timeframe_text = timeframe.title() if timeframe != 'all' else 'All Time'
                embed = discord.Embed(
                    title=f"🧠 **Trivia Tuesday Stats - {timeframe_text}**",
                    description="Community participation and performance",
                    color=0x00ff00,
                    timestamp=datetime.now(ZoneInfo("Europe/London"))
                )

                # Top 5 participants (public view)
                participants = leaderboard_data['participants'][:5]
                leaderboard_text = ""

                for i, participant in enumerate(participants, 1):
                    try:
                        user = await self.bot.fetch_user(participant['user_id'])
                        name = user.display_name if user else f"User {participant['user_id']}"
                    except BaseException:
                        name = f"User {participant['user_id']}"

                    correct = participant.get('correct_answers', 0)
                    total = participant.get('total_answers', 0)
                    accuracy = round((correct / total) * 100, 1) if total > 0 else 0

                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
                    leaderboard_text += f"{medal} {name} • {correct}/{total} ({accuracy}%)\n"

                embed.add_field(
                    name="🏆 **Top Participants:**",
                    value=leaderboard_text or "No participants yet",
                    inline=False
                )

                # Overall stats
                total_sessions = leaderboard_data.get('total_sessions', 0)
                avg_participation = leaderboard_data.get('avg_participation_per_session', 0)

                stats_text = f"**Total Sessions:** {total_sessions}\n**Avg Participants:** {round(avg_participation, 1)}"
                embed.add_field(
                    name="📊 **Community Stats:**",
                    value=stats_text,
                    inline=False
                )

                embed.set_footer(text="Trivia Tuesday • Every Tuesday at 11:00 UK time")

                await ctx.send(embed=embed)

            except Exception as e:
                logger.error(f"Error getting trivia stats: {e}")
                await ctx.send("❌ **Error retrieving trivia stats.** Please try again later.")

        except Exception as e:
            logger.error(f"Error in triviastats command: {e}")
            await ctx.send("❌ System error occurred while retrieving stats.")

    @commands.command(name="listpendingquestions")
    async def list_pending_questions(self, ctx):
        """View submitted trivia questions awaiting use (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot list questions without database connection.")
                return

            # Check if method exists
            if not hasattr(db, 'get_pending_trivia_questions'):
                await ctx.send("❌ **Question management not available.** Database method needs implementation.\n\n*Required method: `get_pending_trivia_questions()`*")
                return

            try:
                pending_questions = db.get_pending_trivia_questions()  # type: ignore

                if not pending_questions:
                    await ctx.send("📋 **No pending trivia questions.** Use `!addtrivia` to add questions to the pool.")
                    return

                # Build question list
                embed = discord.Embed(
                    title="📋 **Pending Trivia Questions**",
                    description=f"Showing {len(pending_questions)} available questions",
                    color=0x00ff00,
                    timestamp=datetime.now(
                        ZoneInfo("Europe/London")))

                for i, question in enumerate(
                        pending_questions[:10], 1):  # Show first 10
                    question_text = question['question_text'][:80] + "..." if len(
                        question['question_text']) > 80 else question['question_text']
                    question_type = question.get(
                        'question_type', 'single').title()

                    # Get creator name
                    try:
                        creator = await self.bot.fetch_user(question['submitted_by_user_id'])
                        creator_name = creator.display_name if creator else f"User {question['submitted_by_user_id']}"
                    except BaseException:
                        creator_name = f"User {question['submitted_by_user_id']}"

                    embed.add_field(
                        name=f"#{question['id']} - {question_type} Choice",
                        value=f"**Q:** {question_text}\n**By:** {creator_name}",
                        inline=False)

                if len(pending_questions) > 10:
                    embed.set_footer(
                        text=f"Showing first 10 of {len(pending_questions)} total questions • Use !starttrivia <id> to use specific question")
                else:
                    embed.set_footer(
                        text="Use !starttrivia <id> to use specific question or !starttrivia for auto-select")

                await ctx.send(embed=embed)

            except Exception as e:
                print(f"❌ Error getting pending questions: {e}")
                await ctx.send("❌ **Database method error.** The question management system needs proper implementation.")

        except Exception as e:
            print(f"❌ Error in listpendingquestions command: {e}")
            await ctx.send("❌ System error occurred while listing questions.")

    @commands.command(name="resettrivia")
    async def reset_trivia(self, ctx):
        """Reset answered questions to available status (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot reset trivia without database connection.")
                return

            # Check if method exists
            if not hasattr(db, 'reset_trivia_questions'):
                await ctx.send("❌ **Trivia reset not available.** Database method needs implementation.\n\n*Required method: `reset_trivia_questions()`*")
                return

            # Confirmation prompt
            confirmation_text = (
                "⚠️ **This will reset ALL answered trivia questions to 'available' status.**\n\n"
                "Previously used questions will become available again for future sessions.\n\n"
                "**Type `CONFIRM` to proceed with the reset:**")
            await ctx.send(confirmation_text)

            # Wait for confirmation
            def check(message):
                return message.author == ctx.author and message.channel == ctx.channel and message.content.upper() == "CONFIRM"

            try:
                await self.bot.wait_for('message', check=check, timeout=30.0)
            except BaseException:
                await ctx.send("❌ **Reset cancelled** - confirmation timeout.")
                return

            # Perform reset
            try:
                reset_count = db.reset_trivia_questions()  # type: ignore

                if reset_count is not None:
                    await ctx.send(f"✅ **Trivia questions reset successfully.**\n\n**{reset_count} questions** returned to available status. These questions can now be used in future trivia sessions.")
                else:
                    await ctx.send("❌ **Failed to reset trivia questions.** Database error occurred.")

            except Exception as e:
                print(f"❌ Error resetting trivia questions: {e}")
                await ctx.send("❌ **Database method error.** The trivia reset system needs proper implementation.")

        except Exception as e:
            print(f"❌ Error in resettrivia command: {e}")
            await ctx.send("❌ System error occurred while resetting trivia.")

    @commands.command(name="addtriviaquestion")
    async def add_trivia_question_conversation(self, ctx):
        """Start interactive DM conversation for trivia question submission"""
        try:
            from ..handlers.conversation_handler import start_trivia_conversation
            await start_trivia_conversation(ctx)
        except ImportError:
            await ctx.send("❌ Trivia submission system not available - conversation handler not loaded.")

    @commands.command(name="approvequestion")
    async def approve_question(self, ctx, target: Optional[str] = None):
        """Send trivia question to JAM for manual approval (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot access trivia questions without database connection.")
                return

            # Check if approval system is available
            try:
                from ..handlers.conversation_handler import start_jam_question_approval
            except ImportError:
                await ctx.send("❌ **Approval system not available.** Conversation handler not loaded.")
                return

            if not target:
                # Show usage help
                help_text = (
                    "**Add Trivia Question (Two Formats):**\n\n"
                    "**1. Easy Multi-line Format (Recommended):**\n"
                    "```\n"
                    "!addtrivia What is the capital of France?\n"
                    "A. London\n"
                    "B. Paris\n"
                    "C. Berlin\n"
                    "Correct answer: B"
                    "```\n"
                    "**2. Pipe-Delimited Format:**\n"
                    "`!addtrivia <question> | answer:<correct_answer> | choices:A,B,C,D | type:multiple`"
                )
                await ctx.send(help_text)
                return

            question_data = None

            if target.lower() == 'auto':
                # Auto-select next question using priority system
                try:
                    # Use same logic as starttrivia command
                    next_question = db.get_next_trivia_question(exclude_user_id=ctx.author.id)
                    if not next_question:
                        await ctx.send("❌ **No available questions for auto-selection.** Use `!addtrivia` to add questions or `!approvequestion generate` to create new ones.")
                        return

                    # Calculate dynamic answer if needed
                    if next_question.get('is_dynamic') and next_question.get('dynamic_query_type'):
                        calculated_answer = db.calculate_dynamic_answer(next_question['dynamic_query_type'])
                        next_question['correct_answer'] = calculated_answer

                    question_data = next_question
                    await ctx.send(f"🎯 **Auto-selected question #{question_data['id']} sent to JAM for approval**\n\nQuestion preview: {question_data['question_text'][:100]}{'...' if len(question_data['question_text']) > 100 else ''}")

                except Exception as e:
                    logger.error(f"Error auto-selecting question: {e}")
                    await ctx.send("❌ **Error auto-selecting question.** Database method may need implementation.")
                    return

            elif target.lower() == 'generate':
                # Generate new AI question (if available)
                await ctx.send("🧠 **AI Question Generation**\n\nGenerating new trivia question... This may take a moment.")

                try:
                    # Use our internal AI generation method (no problematic imports)
                    generated_question = await self._generate_ai_question_fallback()

                    if generated_question:
                        question_data = generated_question
                        await ctx.send(f"✅ **Generated question sent to JAM for approval**\n\nQuestion preview: {question_data.get('question_text', 'Generated question')[:100]}{'...' if len(question_data.get('question_text', '')) > 100 else ''}")
                    else:
                        await ctx.send("❌ **AI question generation failed.** System may be unavailable or rate limited.")
                        return

                except Exception as e:
                    logger.error(f"Error generating AI question: {e}")
                    await ctx.send("❌ **Error generating AI question.** System may be temporarily unavailable.")
                    return

            else:
                # Specific question ID
                try:
                    question_id = int(target)
                except ValueError:
                    await ctx.send("❌ **Invalid question ID.** Please provide a number, 'auto', or 'generate'.")
                    return

                # Get specific question
                try:
                    question_data = db.get_trivia_question_by_id(question_id)
                    if not question_data:
                        await ctx.send(f"❌ **Question #{question_id} not found.** Use `!listpendingquestions` to see available questions.")
                        return

                    # Check question status
                    if question_data.get('status') not in ['available', None]:
                        await ctx.send(f"❌ **Question #{question_id} is not available for approval.** Status: {question_data.get('status', 'unknown')}")
                        return

                    # Calculate dynamic answer if needed
                    if question_data.get('is_dynamic') and question_data.get('dynamic_query_type'):
                        calculated_answer = db.calculate_dynamic_answer(question_data['dynamic_query_type'])
                        question_data['correct_answer'] = calculated_answer

                    await ctx.send(f"📋 **Question #{question_id} sent to JAM for approval**\n\nQuestion preview: {question_data['question_text'][:100]}{'...' if len(question_data['question_text']) > 100 else ''}")

                except Exception as e:
                    logger.error(f"Error retrieving question {question_id}: {e}")
                    await ctx.send("❌ **Error retrieving question.** Database error or question may not exist.")
                    return

            # Send to JAM for approval
            if question_data:
                try:
                    approval_success = await start_jam_question_approval(question_data)

                    if approval_success:
                        # Success message sent above, add context
                        await ctx.send(f"💬 **JAM will receive a DM with approval options.** They can approve, modify, or reject the question.\n\n*Approval conversation will remain active for 24 hours to accommodate late responses.*")
                    else:
                        await ctx.send("❌ **Failed to send approval request to JAM.** They may have DMs disabled or system error occurred.")

                except Exception as e:
                    logger.error(f"Error starting JAM approval workflow: {e}")
                    await ctx.send("❌ **Error initiating approval workflow.** System may be temporarily unavailable.")

        except Exception as e:
            logger.error(f"Error in approvequestion command: {e}")
            await ctx.send("❌ System error occurred while processing approval request.")

    @commands.command(name="approvestatus")
    async def approval_status(self, ctx):
        """Check status of pending JAM approvals (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            from ..config import JAM_USER_ID
            from ..handlers.conversation_handler import jam_approval_conversations

            if JAM_USER_ID in jam_approval_conversations:
                conversation = jam_approval_conversations[JAM_USER_ID]
                initiated_at = conversation.get('initiated_at')
                last_activity = conversation.get('last_activity')
                step = conversation.get('step', 'unknown')

                if initiated_at:
                    age = datetime.now(ZoneInfo("Europe/London")) - initiated_at
                    age_text = f"{age.total_seconds() / 3600:.1f} hours" if age.total_seconds(
                    ) > 3600 else f"{age.total_seconds() / 60:.0f} minutes"
                else:
                    age_text = "Unknown"

                question_data = conversation.get('data', {}).get('question_data', {})
                question_preview = question_data.get('question_text', 'Unknown question')[
                    :50] + '...' if len(question_data.get('question_text', '')) > 50 else question_data.get('question_text', 'Unknown question')

                await ctx.send(
                    f"⏳ **JAM Approval Status**\n\n"
                    f"**Status:** Pending approval\n"
                    f"**Step:** {step.replace('_', ' ').title()}\n"
                    f"**Question:** {question_preview}\n"
                    f"**Age:** {age_text}\n"
                    f"**Timeout:** 24 hours\n\n"
                    f"*JAM has an active approval conversation waiting for response.*"
                )
            else:
                await ctx.send("✅ **No pending approvals.** JAM does not have any active approval conversations.")

        except ImportError:
            await ctx.send("❌ **Approval system not available.** Conversation handler not loaded.")
        except Exception as e:
            logger.error(f"Error checking approval status: {e}")
            await ctx.send("❌ System error occurred while checking approval status.")

    @commands.command(name="resetapproval")
    async def reset_approval(self, ctx):
        """Force reset any stuck approval sessions (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            from ..config import JAM_USER_ID
            from ..handlers.conversation_handler import force_reset_approval_session

            # Reset for JAM
            success = await force_reset_approval_session(JAM_USER_ID)

            if success:
                await ctx.send("✅ **Approval session reset successfully.** Any stuck conversations have been cleared.")
            else:
                await ctx.send("ℹ️ **No active approval session found to reset.**")

        except ImportError:
            await ctx.send("❌ **Approval system not available.** Conversation handler not loaded.")
        except Exception as e:
            logger.error(f"Error resetting approval session: {e}")
            await ctx.send("❌ System error occurred while resetting approval session.")

    @commands.command(name="triviatest")
    @commands.has_permissions(manage_messages=True)
    async def trivia_test(self, ctx):
        """Comprehensive test of reply-based trivia system including answer recording and acknowledgment (moderators only)"""
        try:
            if db is None:
                await ctx.send("❌ **Database offline.** Cannot test trivia without database connection.")
                return

            # Check if there's already an active trivia session
            try:
                active_session = db.get_active_trivia_session()
                if active_session:
                    await ctx.send("⚠️ **Active trivia session detected.** Please wait for it to end before testing to avoid interference.")
                    return
            except Exception:
                pass  # Continue with test even if we can't check active session

            print(
                f"🧪 TRIVIA TEST: Starting comprehensive test initiated by {ctx.author.id} in channel {ctx.channel.id}")

            # Create test questions with different answer variations to test fuzzy matching
            test_questions = [
                {
                    'question_text': '🧪 TEST: What is the name of the science officer android in this Discord server?',
                    'question_type': 'single',
                    'correct_answer': 'Ash',
                    'test_answers': ['Ash', 'ash', 'ASH', 'A', 'Bishop']  # Mix of correct variations and wrong answers
                },
                {
                    'question_text': '🧪 TEST: What color combines red and yellow?',
                    'question_type': 'single',
                    'correct_answer': 'Orange',
                    'test_answers': ['orange', 'Orange', 'ORANGE', 'oranje', 'blue']  # Test fuzzy matching
                }
            ]

            test_results = []

            for question_idx, test_question_data in enumerate(test_questions, 1):
                print(f"🧪 TRIVIA TEST: Running test {question_idx}/{len(test_questions)}")

                # Create temporary test question in database
                test_question_id = None
                try:
                    test_question_id = db.add_trivia_question(
                        question_text=test_question_data['question_text'],
                        question_type=test_question_data['question_type'],
                        correct_answer=test_question_data['correct_answer'],
                        multiple_choice_options=None,
                        is_dynamic=False,
                        dynamic_query_type=None,
                        submitted_by_user_id=ctx.author.id,
                        category='test',
                        difficulty_level=1
                    )

                    if not test_question_id:
                        await ctx.send(f"❌ **Test question {question_idx} creation failed.** Database error occurred.")
                        continue

                    print(f"🧪 TRIVIA TEST: Created temporary test question {test_question_id}")

                except Exception as question_error:
                    await ctx.send(f"❌ **Test question {question_idx} creation failed:** {question_error}")
                    continue

                # Start test session
                try:
                    test_session_id = db.create_trivia_session(
                        question_id=test_question_id,
                        session_type="test",
                        calculated_answer=test_question_data['correct_answer']
                    )

                    if not test_session_id:
                        await ctx.send(f"❌ **Test session {question_idx} creation failed.** Database error occurred.")
                        continue

                    print(f"🧪 TRIVIA TEST: Created test session {test_session_id}")

                except Exception as session_error:
                    await ctx.send(f"❌ **Test session {question_idx} creation failed:** {session_error}")
                    continue

                # Create test question embed
                test_embed = discord.Embed(
                    title=f"🧪 **TRIVIA TEST {question_idx}/{len(test_questions)} - ANSWER VALIDATION TEST**",
                    description=test_question_data['question_text'],
                    color=0xff9900,
                    timestamp=datetime.now(ZoneInfo("Europe/London"))
                )

                test_embed.add_field(
                    name="🔬 **Test Purpose:**",
                    value="Testing answer recording, fuzzy matching, and acknowledgment system",
                    inline=False
                )

                test_embed.add_field(
                    name="💡 **How to Test:**",
                    value=f"**Reply to this message** with '{test_question_data['correct_answer']}' to test the system!",
                    inline=False)

                test_embed.add_field(
                    name="🔧 **Test Session Info:**",
                    value=f"Test Session #{test_session_id} • Expected: '{test_question_data['correct_answer']}'",
                    inline=False
                )

                test_embed.set_footer(text=f"TEST by {ctx.author.display_name} • Auto-testing in progress...")

                # Send test question and capture message ID
                test_question_message = await ctx.send(embed=test_embed)

                # Update test session with message tracking
                try:
                    update_success = db.update_trivia_session_messages(
                        session_id=test_session_id,
                        question_message_id=test_question_message.id,
                        confirmation_message_id=test_question_message.id,  # Use same message for simplicity
                        channel_id=ctx.channel.id
                    )

                    if not update_success:
                        print(f"⚠️ TRIVIA TEST: Failed to update test session {test_session_id} with message IDs")

                except Exception as msg_tracking_error:
                    print(f"❌ TRIVIA TEST: Error updating test session message tracking: {msg_tracking_error}")

                # Automatically test answer variations
                test_variation_results = []

                for test_answer in test_question_data['test_answers']:
                    print(f"🧪 TRIVIA TEST: Testing answer variation: '{test_answer}'")

                    try:
                        # Test the answer evaluation directly
                        if hasattr(db, '_evaluate_trivia_answer'):
                            score, match_type = db._evaluate_trivia_answer(
                                test_answer,
                                test_question_data['correct_answer'],
                                test_question_data['question_type']
                            )

                            # Determine result
                            if score >= 1.0:
                                result = "✅ CORRECT"
                            elif score >= 0.7:
                                result = f"🟡 PARTIAL ({int(score * 100)}%)"
                            else:
                                result = f"❌ INCORRECT ({int(score * 100)}%)"

                            test_variation_results.append({
                                'answer': test_answer,
                                'score': score,
                                'match_type': match_type,
                                'result': result
                            })

                            print(
                                f"🧪 TRIVIA TEST: Answer '{test_answer}' → Score: {score}, Type: {match_type}, Result: {result}")

                        else:
                            test_variation_results.append({
                                'answer': test_answer,
                                'error': 'Evaluation method not available'
                            })

                    except Exception as eval_error:
                        print(f"❌ TRIVIA TEST: Error evaluating answer '{test_answer}': {eval_error}")
                        test_variation_results.append({
                            'answer': test_answer,
                            'error': str(eval_error)
                        })

                # Compile test results
                test_results.append({
                    'question_id': test_question_id,
                    'session_id': test_session_id,
                    'question': test_question_data['question_text'],
                    'correct_answer': test_question_data['correct_answer'],
                    'variations': test_variation_results
                })

                # Clean up test session immediately
                try:
                    db.complete_trivia_session(test_session_id)
                    await test_question_message.delete()
                    print(f"🧹 TRIVIA TEST: Cleaned up test session {test_session_id}")
                except Exception as cleanup_error:
                    print(f"⚠️ TRIVIA TEST: Cleanup error for session {test_session_id}: {cleanup_error}")

                # Brief pause between tests
                await asyncio.sleep(2)

            # Generate comprehensive test report
            report_embed = discord.Embed(
                title="🧪 **TRIVIA TEST REPORT - Answer Recording & Acknowledgment**",
                description="Comprehensive test of the trivia answer matching system",
                color=0x00ff00,
                timestamp=datetime.now(ZoneInfo("Europe/London"))
            )

            total_tests = sum(len(result['variations']) for result in test_results)
            successful_tests = 0
            partial_tests = 0
            failed_tests = 0

            for result in test_results:
                question_summary = f"**Q:** {result['question'][:50]}...\n**Expected:** {result['correct_answer']}\n"

                variation_details = []
                for variation in result['variations']:
                    if 'error' in variation:
                        variation_details.append(f"❌ '{variation['answer']}' → ERROR: {variation['error']}")
                        failed_tests += 1
                    else:
                        variation_details.append(
                            f"{variation['result']} '{variation['answer']}' ({variation['match_type']})")
                        if variation['score'] >= 1.0:
                            successful_tests += 1
                        elif variation['score'] >= 0.7:
                            partial_tests += 1
                        else:
                            failed_tests += 1

                question_summary += "\n".join(variation_details)

                report_embed.add_field(
                    name=f"Test Question #{result['question_id']}",
                    value=question_summary,
                    inline=False
                )

            # Add overall statistics
            accuracy = (successful_tests / total_tests * 100) if total_tests > 0 else 0

            report_embed.add_field(
                name="📊 **Test Statistics**",
                value=(
                    f"**Total Tests:** {total_tests}\n"
                    f"**✅ Correct:** {successful_tests}\n"
                    f"**🟡 Partial:** {partial_tests}\n"
                    f"**❌ Failed:** {failed_tests}\n"
                    f"**🎯 Accuracy:** {accuracy:.1f}%"
                ),
                inline=False
            )

            # Add system status
            system_status = []
            if hasattr(db, '_evaluate_trivia_answer'):
                system_status.append("✅ Enhanced answer matching available")
            else:
                system_status.append("❌ Enhanced answer matching not found")

            if hasattr(db, 'submit_trivia_answer'):
                system_status.append("✅ Answer submission system available")
            else:
                system_status.append("❌ Answer submission system not found")

            report_embed.add_field(
                name="🔧 **System Status**",
                value="\n".join(system_status),
                inline=False
            )

            # Determine overall result
            if accuracy >= 80 and failed_tests == 0:
                report_embed.color = 0x00ff00  # Green - success
                report_embed.add_field(
                    name="🎉 **Overall Result**",
                    value="**TEST PASSED** - Answer recording and acknowledgment system is working correctly!",
                    inline=False
                )
            elif accuracy >= 60:
                report_embed.color = 0xffaa00  # Orange - warning
                report_embed.add_field(
                    name="⚠️ **Overall Result**",
                    value="**PARTIAL SUCCESS** - System is working but may need adjustments.",
                    inline=False
                )
            else:
                report_embed.color = 0xff0000  # Red - failure
                report_embed.add_field(
                    name="❌ **Overall Result**",
                    value="**TEST FAILED** - Answer recording system needs attention.",
                    inline=False
                )

            report_embed.set_footer(
                text="For manual testing, use !starttrivia to create a real session and reply to test live functionality")

            await ctx.send(embed=report_embed)

            # Send follow-up instructions
            followup_message = (
                "🧪 **Test Complete!** The automated test shows how the answer matching system performs.\n\n"
                "**For Live Testing:**\n"
                "1. Use `!starttrivia` to create a real trivia session\n"
                "2. Reply to the trivia question with your answer\n"
                "3. Check that you get a 📝 reaction (acknowledgment)\n"
                "4. Use `!endtrivia` to see if your answer was recorded correctly\n\n"
                "**This verifies the complete flow:** Reply detection → Answer processing → Database recording → User acknowledgment")

            await ctx.send(followup_message)

            print(
                f"🧪 TRIVIA TEST: Comprehensive test completed - {successful_tests}/{total_tests} successful ({accuracy:.1f}%)")

        except Exception as e:
            print(f"❌ TRIVIA TEST: Critical error: {e}")
            await ctx.send(f"❌ **Comprehensive trivia test failed:** {str(e)}")

    @commands.command(name="generatequestions")
    async def generate_questions_manually(self, ctx, count: int = 1):
        """Manually generate trivia questions for testing and approval (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot generate questions without database connection.")
                return

            # Limit to reasonable number
            if count < 1 or count > 5:
                await ctx.send("❌ **Invalid count.** Please specify 1-5 questions to generate.")
                return

            await ctx.send(f"🧠 **Manual Question Generation**\n\nGenerating {count} trivia question(s) for your approval... This may take a moment.")

            from ..handlers.conversation_handler import start_jam_question_approval

            successful_generations = 0
            failed_generations = 0

            for i in range(count):
                try:
                    # Use our internal AI generation method
                    question_data = await self._generate_ai_question_fallback()

                    if question_data:
                        # Send each question for approval
                        approval_sent = await start_jam_question_approval(question_data)

                        if approval_sent:
                            successful_generations += 1
                            logger.info(f"Generated and sent question {i+1}/{count} for approval")

                            # Brief delay between questions to avoid overwhelming
                            if i < count - 1:
                                await asyncio.sleep(3)
                        else:
                            failed_generations += 1
                            logger.warning(f"Failed to send question {i+1}/{count} for approval")
                    else:
                        failed_generations += 1
                        logger.warning(f"Failed to generate question {i+1}/{count}")

                except Exception as gen_error:
                    failed_generations += 1
                    logger.error(f"Error generating question {i+1}/{count}: {gen_error}")

            # Send summary
            if successful_generations > 0:
                await ctx.send(f"✅ **Question Generation Complete**\n\n"
                               f"Successfully generated and sent {successful_generations}/{count} questions to JAM for approval.\n"
                               f"Failed: {failed_generations}\n\n"
                               f"*JAM should receive individual DMs for each question requiring approval.*")
            else:
                await ctx.send(f"❌ **Question Generation Failed**\n\n"
                               f"Unable to generate any questions. This could be due to:\n"
                               f"• AI rate limiting\n"
                               f"• Database approval session creation issues\n"
                               f"• Network connectivity problems\n\n"
                               f"*Check the logs for detailed error information.*")

        except Exception as e:
            logger.error(f"Error in manual question generation: {e}")
            await ctx.send(f"❌ **Manual generation failed:** {str(e)}")

    @commands.command(name="triviapoolstatus")
    async def trivia_pool_status(self, ctx):
        """Check the current trivia question pool status (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot check question pool status.")
                return

            # Get question statistics
            stats = db.get_trivia_question_statistics()

            if not stats:
                await ctx.send("❌ **Unable to retrieve question pool statistics.** Database error occurred.")
                return

            # Check minimum pool requirement
            available_count = stats.get('available_questions', 0)
            minimum_required = 5
            pool_health = "✅ Healthy" if available_count >= minimum_required else f"⚠️ Below minimum ({minimum_required})"

            # Create status embed
            embed = discord.Embed(
                title="📊 **Trivia Question Pool Status**",
                color=0x00ff00 if available_count >= minimum_required else 0xffaa00,
                timestamp=datetime.now(ZoneInfo("Europe/London"))
            )

            # Pool overview
            embed.add_field(
                name="🎯 **Pool Health**",
                value=f"{pool_health}\n**Available:** {available_count}\n**Minimum Required:** {minimum_required}",
                inline=True
            )

            # Status breakdown
            status_counts = stats.get('status_counts', {})
            status_text = "\n".join([f"**{status.title()}:** {count}"
                                     for status, count in status_counts.items()])

            embed.add_field(
                name="📋 **Status Breakdown**",
                value=status_text or "No data available",
                inline=True
            )

            # Source breakdown
            source_counts = stats.get('source_counts', {})
            source_text = "\n".join([f"**{source.replace('_', ' ').title()}:** {count}"
                                     for source, count in source_counts.items()])

            embed.add_field(
                name="🔄 **Question Sources**",
                value=source_text or "No data available",
                inline=True
            )

            # Total summary
            total_questions = stats.get('total_questions', 0)
            embed.add_field(
                name="📈 **Summary**",
                value=f"**Total Questions:** {total_questions}\n**Pool Status:** {pool_health}",
                inline=False
            )

            # Add recommendations if pool is low
            if available_count < minimum_required:
                needed = minimum_required - available_count
                embed.add_field(
                    name="💡 **Recommendations**",
                    value=f"• Generate {needed} more questions with `!generatequestions {needed}`\n• Reset old questions with `!resettrivia`\n• Add manual questions with `!addtrivia`",
                    inline=False)

            embed.set_footer(text="Use !generatequestions <count> to create new questions")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error checking trivia pool status: {e}")
            await ctx.send(f"❌ **Pool status check failed:** {str(e)}")

    @commands.command(name="triviahelp")
    async def trivia_help(self, ctx):
        """Display comprehensive trivia command summary (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            # Create Ash-styled help embed
            embed = discord.Embed(
                title="📋 **TRIVIA TUESDAY PROTOCOL SUMMARY**",
                description="*Systematic assessment of personnel knowledge acquisition capabilities.*",
                color=0x00ff00,
                timestamp=datetime.now(ZoneInfo("Europe/London"))
            )

            # Scheduled Operations
            embed.add_field(
                name="⏰ **Scheduled Operations**",
                value=(
                    "**Automated deployment:** Tuesdays at 11:00 UK time\n"
                    "**Auto-completion:** 2 hours after deployment\n"
                    "**Target channel:** #members\n"
                    "**Pre-approval:** 10:00 UK time (1 hour before)"
                ),
                inline=False
            )

            # Question Management
            embed.add_field(
                name="📝 **Question Management**",
                value=(
                    "`!addtrivia` - Submit question to database\n"
                    "`!approvequestion auto` - Send next priority question for review\n"
                    "`!approvequestion generate` - Generate AI question for approval\n"
                    "`!listpendingquestions` - Review available question inventory\n"
                    "`!generatequestions <count>` - Generate multiple AI questions"
                ),
                inline=False
            )

            # Session Control
            embed.add_field(
                name="🎮 **Session Control**",
                value=(
                    "`!starttrivia [id]` - Initialize trivia session (manual override)\n"
                    "`!endtrivia` - Complete active session and post results\n"
                    "`!disabletrivia` - Skip next scheduled trivia (for special events)\n"
                    "`!enabletrivia` - Re-enable scheduled trivia automation"
                ),
                inline=False
            )

            # Status & Analytics
            embed.add_field(
                name="📊 **Status & Analytics**",
                value=(
                    "`!trivialeaderboard` - Access performance analytics\n"
                    "`!triviapoolstatus` - Current question inventory assessment\n"
                    "`!approvestatus` - Check pending approval workflows\n"
                    "`!resettrivia` - Reset answered questions to available"
                ),
                inline=False
            )

            # Mission Parameters
            embed.add_field(
                name="🎯 **Mission Parameters**",
                value=(
                    "• Maintain minimum **5-question pool** for optimal operations\n"
                    "• Sessions **auto-end after 2 hours** with results posted\n"
                    "• Questions marked as **'answered'** after session completion\n"
                    "• Manual override available for **special events**"
                ),
                inline=False
            )

            embed.set_footer(text="TRIVIA TUESDAY OPERATIONAL MANUAL | All systems nominal")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error displaying trivia help: {e}")
            await ctx.send(f"❌ **Help system error:** {str(e)}")

    @commands.command(name="disabletrivia")
    async def disable_trivia(self, ctx):
        """Disable scheduled Trivia Tuesday for manual override (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot modify trivia schedule.")
                return

            # Set the disable flag
            db.set_config_value('trivia_scheduled_disabled', 'true')
            db.set_config_value('trivia_scheduled_disabled_at', datetime.now(ZoneInfo("Europe/London")).isoformat())

            # Create confirmation embed
            embed = discord.Embed(
                title="⚠️ **Scheduled Trivia Disabled**",
                description="The automated Trivia Tuesday deployment has been **suspended** for manual override operations.",
                color=0xffaa00,
                timestamp=datetime.now(
                    ZoneInfo("Europe/London")))

            embed.add_field(
                name="🔧 **Override Status**",
                value=(
                    "**Scheduled Task:** Disabled\n"
                    "**Auto-reset:** 24 hours\n"
                    "**Manual Control:** Enabled"
                ),
                inline=False
            )

            embed.add_field(
                name="💡 **Manual Operations**",
                value=(
                    "You can now run trivia manually using:\n"
                    "• `!starttrivia` - Start with auto-selected question\n"
                    "• `!starttrivia <id>` - Start with specific question\n"
                    "• Use in **any channel** (e.g., #chit-chat for special events)\n"
                    "• Combine generated and manual questions as needed"
                ),
                inline=False
            )

            embed.add_field(
                name="🔄 **Re-enabling**",
                value=(
                    "Use `!enabletrivia` to re-enable scheduled trivia\n"
                    "**Auto-reset:** Trivia will auto-reset after 24 hours\n\n"
                    "*This allows you to run special event trivia on Jonesy's birthday or other occasions.*"
                ),
                inline=False
            )

            embed.set_footer(text="Manual override active • Use !enabletrivia to restore automation")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error disabling trivia: {e}")
            await ctx.send(f"❌ **Failed to disable trivia:** {str(e)}")

    @commands.command(name="enabletrivia")
    async def enable_trivia(self, ctx):
        """Re-enable scheduled Trivia Tuesday automation (moderators only)"""
        try:
            # Check if user is a moderator (works in both DM and server context)
            from ..utils.permissions import user_is_mod_by_id
            if not await user_is_mod_by_id(ctx.author.id, self.bot):
                await ctx.send("❌ **Access denied.** This command requires moderator privileges.")
                return

            if db is None:
                await ctx.send("❌ **Database offline.** Cannot modify trivia schedule.")
                return

            # Clear the disable flag
            db.set_config_value('trivia_scheduled_disabled', 'false')
            db.set_config_value('trivia_scheduled_disabled_at', '')

            # Create confirmation embed
            embed = discord.Embed(
                title="✅ **Scheduled Trivia Re-enabled**",
                description="The automated Trivia Tuesday deployment has been **restored** to normal operations.",
                color=0x00ff00,
                timestamp=datetime.now(ZoneInfo("Europe/London"))
            )

            embed.add_field(
                name="🔧 **Automation Status**",
                value=(
                    "**Scheduled Task:** Enabled\n"
                    "**Next Deployment:** Tuesday at 11:00 UK time\n"
                    "**Target Channel:** #members\n"
                    "**Auto-end:** 2 hours after start"
                ),
                inline=False
            )

            embed.add_field(
                name="📋 **Normal Operations**",
                value=(
                    "• Pre-approval at 10:00 UK time (Tuesdays)\n"
                    "• Automatic question deployment at 11:00 UK time\n"
                    "• Auto-completion after 2 hours\n"
                    "• Results posted automatically"
                ),
                inline=False
            )

            embed.set_footer(text="Automation restored • Use !disabletrivia to suspend for special events")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error enabling trivia: {e}")
            await ctx.send(f"❌ **Failed to enable trivia:** {str(e)}")


async def setup(bot):
    """Load the trivia cog"""
    await bot.add_cog(TriviaCommands(bot))
