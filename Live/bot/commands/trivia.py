"""
Trivia Tuesday Command Module

Handles comprehensive trivia management including:
- Question submission and management
- Session management (start/end trivia)
- Leaderboard and statistics
- Question prioritization and AI generation
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from ..config import JAM_USER_ID, JONESY_USER_ID
from ..database import get_database

# Set up logging
logger = logging.getLogger(__name__)

# Get database instance
db = get_database()  # type: ignore


class TriviaCommands(commands.Cog):
    """Trivia Tuesday management commands"""

    def __init__(self, bot):
        self.bot = bot

    async def _generate_ai_question_fallback(self):
        """Fallback AI question generation when dedicated function is unavailable"""
        try:
            from ..handlers.ai_handler import call_ai_with_rate_limiting
            
            # Simple AI prompt for question generation
            prompt = (
                "Generate a trivia question about Captain Jonesy's gaming based on her played games database. "
                "Focus on statistical data like playtime, episode counts, or completion rates. "
                "Format: Question: [question] | Answer: [answer] | Type: single_answer"
            )
            
            response_text, status = await call_ai_with_rate_limiting(prompt, JAM_USER_ID)
            
            if response_text:
                # Parse AI response
                lines = response_text.strip().split('\n')
                question_text = ""
                answer = ""
                
                for line in lines:
                    if line.startswith("Question:"):
                        question_text = line.replace("Question:", "").strip()
                    elif line.startswith("Answer:"):
                        answer = line.replace("Answer:", "").strip()
                
                if question_text and answer:
                    return {
                        'question_text': question_text,
                        'correct_answer': answer,
                        'question_type': 'single_answer',
                        'category': 'ai_generated',
                        'is_dynamic': False
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in fallback AI generation: {e}")
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

            # Parse question components
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
                            value="Reply with the letter (A, B, C, D) of your choice!",
                            inline=False)
                    else:
                        embed.add_field(
                            name="💡 **How to Answer:**",
                            value="Reply with your answer in this channel!",
                            inline=False)

                    embed.add_field(
                        name="⏰ **Session Info:**",
                        value=f"Session #{session_id} • Question #{question_data['id']}",
                        inline=False)
                    embed.set_footer(
                        text=f"Started by {ctx.author.display_name} • End with !endtrivia")

                    await ctx.send(embed=embed)

                    # Send confirmation to moderator
                    await ctx.send(f"✅ **Trivia session #{session_id} started** with question #{question_data['id']}.\n\n*Use `!endtrivia` when ready to reveal answers and end the session.*")

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
            from ..handlers.conversation_handler import jam_approval_conversations
            from ..config import JAM_USER_ID
            
            if JAM_USER_ID in jam_approval_conversations:
                conversation = jam_approval_conversations[JAM_USER_ID]
                initiated_at = conversation.get('initiated_at')
                last_activity = conversation.get('last_activity')
                step = conversation.get('step', 'unknown')
                
                if initiated_at:
                    age = datetime.now(ZoneInfo("Europe/London")) - initiated_at
                    age_text = f"{age.total_seconds() / 3600:.1f} hours" if age.total_seconds() > 3600 else f"{age.total_seconds() / 60:.0f} minutes"
                else:
                    age_text = "Unknown"
                
                question_data = conversation.get('data', {}).get('question_data', {})
                question_preview = question_data.get('question_text', 'Unknown question')[:50] + '...' if len(question_data.get('question_text', '')) > 50 else question_data.get('question_text', 'Unknown question')
                
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


async def setup(bot):
    """Load the trivia cog"""
    await bot.add_cog(TriviaCommands(bot))
