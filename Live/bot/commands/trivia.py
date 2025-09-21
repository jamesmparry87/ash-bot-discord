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
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..config import JAM_USER_ID, JONESY_USER_ID
from ..database_module import DatabaseManager, get_database

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
        import re

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

    def _parse_natural_multiple_choice(self, content: str) -> Optional[dict]:
        """Parse natural multiple choice format into structured data"""
        import re

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

        # Validate we have everything we need
        if not question_text or len(choices) < 2 or not correct_answer:
            return None

        # Validate correct answer is a valid choice letter
        choice_index = ord(correct_answer) - ord('A')
        if choice_index < 0 or choice_index >= len(choices):
            return None

        return {
            'question': question_text.strip(),
            'choices': choices,
            'answer': correct_answer,
        }

    async def _generate_ai_question_fallback(self):
        """Enhanced AI question generation with fan-accessible questions"""
        try:
            import random

            from ..handlers.ai_handler import call_ai_with_rate_limiting

            # Multiple question types for variety
            question_types = [
                {
                    'type': 'fan_observable',
                    'prompt': (
                        "Generate a trivia question about Captain Jonesy's gaming that dedicated fans and stream viewers could realistically answer. "
                        "Focus on observable patterns like: most played genres, memorable series, recent completions, gaming preferences. "
                        "Avoid exact statistics - use questions about trends fans would notice. "
                        "Examples: 'What genre does Jonesy play most often?', 'Which game series has she completed multiple entries from?' "
                        "Format: Question: [question] | Answer: [answer]"
                    )
                },
                {
                    'type': 'gaming_knowledge',
                    'prompt': (
                        "Generate a general gaming trivia question that relates to games Captain Jonesy has played. "
                        "Focus on gaming history, popular games, or industry knowledge that gaming enthusiasts would know. "
                        "Examples: 'What genre is God of War?', 'Which company developed The Last of Us?', 'What does RPG stand for?' "
                        "Format: Question: [question] | Answer: [answer]"
                    )
                },
                {
                    'type': 'broad_database',
                    'prompt': (
                        "Generate a trivia question about Captain Jonesy's gaming habits using broad categories instead of exact numbers. "
                        "Focus on questions fans could estimate: 'more action or RPG games?', 'games from which decade?', 'completed vs abandoned?' "
                        "Avoid precise statistics - use comparative or categorical questions. "
                        "Format: Question: [question] | Answer: [answer]"
                    )
                },
                {
                    'type': 'memorable_moments',
                    'prompt': (
                        "Generate a trivia question about memorable gaming moments or notable games from Captain Jonesy's streams. "
                        "Focus on things regular viewers would remember: longest series, recent favorites, gaming reactions. "
                        "Examples: 'What was the most recent horror game Jonesy completed?', 'Which platformer series has she played most entries from?' "
                        "Format: Question: [question] | Answer: [answer]"
                    )
                }
            ]

            # Randomly select a question type for variety
            selected_type = random.choice(question_types)

            response_text, status = await call_ai_with_rate_limiting(selected_type['prompt'], JAM_USER_ID)

            if response_text:
                # Parse AI response with improved parsing
                lines = response_text.strip().split('\n')
                question_text = ""
                answer = ""

                # Try to extract from formatted response first
                for line in lines:
                    line = line.strip()
                    if line.startswith("Question:"):
                        question_text = line.replace("Question:", "").strip()
                    elif line.startswith("Answer:"):
                        answer = line.replace("Answer:", "").strip()

                # Fallback: try to parse from pipe-separated format
                if not question_text or not answer:
                    for line in lines:
                        if '|' in line:
                            parts = line.split('|')
                            if len(parts) >= 2:
                                q_part = parts[0].strip()
                                a_part = parts[1].strip()
                                if 'Question:' in q_part:
                                    question_text = q_part.replace('Question:', '').strip()
                                if 'Answer:' in a_part:
                                    answer = a_part.replace('Answer:', '').strip()

                # Basic validation
                if question_text and answer and len(question_text) > 10 and len(answer) > 0:
                    # Clean up the question and answer
                    question_text = question_text.strip('?"')
                    if not question_text.endswith('?'):
                        question_text += '?'

                    return {
                        'question_text': question_text,
                        'correct_answer': answer.strip(),
                        'question_type': 'single',
                        'category': f"ai_{selected_type['type']}",
                        'difficulty_level': 2,  # Medium difficulty
                        'is_dynamic': False
                    }
                else:
                    logger.warning(f"AI generated invalid question format: Q='{question_text}', A='{answer}'")

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

                if question_type == 'multiple' and not choices:
                    await ctx.send("❌ **Choices required for multiple choice.** Format: `| choices:A,B,C,D`")
                    return

            if len(question_text) < 10:
                await ctx.send("❌ **Question too short.** Please provide a meaningful trivia question.")
                return

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
                    if question_data['question_type'] == 'multiple' and question_data.get(
                            'choices'):
                        choices_text = '\n'.join(
                            [f"**{chr(65+i)}.** {choice}" for i, choice in enumerate(question_data['choices'])])
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
                        value=session_results['correct_answer'],
                        inline=False)

                    # Show participation stats
                    total_participants = session_results.get(
                        'total_participants', 0)
                    correct_answers = session_results.get('correct_answers', 0)

                    if total_participants > 0:
                        accuracy = round(
                            (correct_answers / total_participants) * 100, 1)
                        embed.add_field(
                            name="📊 **Session Stats:**",
                            value=f"**Participants:** {total_participants}\n**Correct:** {correct_answers}\n**Accuracy:** {accuracy}%",
                            inline=True)

                        # Show winners (first correct answer)
                        if session_results.get('first_correct'):
                            winner_user = await self.bot.fetch_user(session_results['first_correct']['user_id'])
                            winner_name = winner_user.display_name if winner_user else f"User {session_results['first_correct']['user_id']}"
                            embed.add_field(
                                name="🥇 **First Correct:**",
                                value=f"{winner_name}",
                                inline=True)
                    else:
                        embed.add_field(
                            name="📊 **Session Stats:**",
                            value="No participants this round",
                            inline=True)

                    embed.set_footer(
                        text=f"Session #{active_session['id']} ended by {ctx.author.display_name}")

                    await ctx.send(embed=embed)

                    # Thank you message
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
    @commands.has_permissions(manage_messages=True)
    async def trivia_leaderboard(self, ctx, timeframe: str = "all"):
        """Show trivia participation and success statistics (moderators only)"""
        try:
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

    @commands.command(name="listpendingquestions")
    @commands.has_permissions(manage_messages=True)
    async def list_pending_questions(self, ctx):
        """View submitted trivia questions awaiting use (moderators only)"""
        try:
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
                    question_text = question['question'][:80] + "..." if len(
                        question['question']) > 80 else question['question']
                    question_type = question.get(
                        'question_type', 'single').title()

                    # Get creator name
                    try:
                        creator = await self.bot.fetch_user(question['created_by'])
                        creator_name = creator.display_name if creator else f"User {question['created_by']}"
                    except BaseException:
                        creator_name = f"User {question['created_by']}"

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
    @commands.has_permissions(manage_messages=True)
    async def reset_trivia(self, ctx):
        """Reset answered questions to available status (moderators only)"""
        try:
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
            from bot.handlers.conversation_handler import start_trivia_conversation
            await start_trivia_conversation(ctx)
        except ImportError:
            await ctx.send("❌ Trivia submission system not available - conversation handler not loaded.")

    @commands.command(name="approvequestion")
    @commands.has_permissions(manage_messages=True)
    async def approve_question(self, ctx, target: Optional[str] = None):
        """Send trivia question to JAM for manual approval (moderators only)"""
        try:
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
                    "**Manual Question Approval Usage:**\n"
                    "`!approvequestion <question_id>` - Send specific question to JAM for review\n"
                    "`!approvequestion auto` - Send next auto-selected question for approval\n"
                    "`!approvequestion generate` - Generate new question and send for approval\n\n"
                    "**Examples:**\n"
                    "• `!approvequestion 25` - Review question #25\n"
                    "• `!approvequestion auto` - Review what would be auto-selected\n"
                    "• `!approvequestion generate` - Create and review new AI question\n\n"
                    "**Use Cases:**\n"
                    "• Quality check before bonus trivia sessions\n"
                    "• Review newly added questions\n"
                    "• Preview auto-selection before events"
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
    @commands.has_permissions(manage_messages=True)
    async def approval_status(self, ctx):
        """Check status of pending JAM approvals (moderators only)"""
        try:
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


async def setup(bot):
    """Load the trivia cog"""
    await bot.add_cog(TriviaCommands(bot))
