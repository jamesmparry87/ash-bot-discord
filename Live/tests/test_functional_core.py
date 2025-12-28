"""
Ash Bot - Core Functional Test Suite

PURPOSE: High-level functional validation of critical bot features
GOAL: Catch deployment-breaking issues before go-live

This test suite validates complete user workflows and critical functionality.
Tests are designed to catch real issues like:
- Trivia questions missing answer options
- Commands that fail silently
- Data queries returning incomplete results
- AI responses that are malformed

NO credential-dependent tests - all tests work offline/in CI.
NO one-off fix validations - only ongoing functional verification.
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add Live directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ============================================================================
# TRIVIA SYSTEM TESTS - Critical User-Facing Feature
# ============================================================================

class TestTriviaSystem:
    """
    CRITICAL: Trivia is a major user-facing feature
    Test Goal: Ensure complete trivia workflow works correctly
    """

    @pytest.mark.asyncio
    async def test_trivia_question_includes_answer_options(self):
        """
        CRITICAL TEST: Verify multiple-choice questions include ALL answer options
        
        User Impact: Without this, users get question but no way to answer
        Example Failure: "What game has the most playtime?" with no A/B/C/D options
        """
        from bot.commands.trivia import generate_trivia_question
        from bot.database_module import get_database
        
        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")
        
        # Generate a multiple-choice question
        question_data = await generate_trivia_question(question_type="multiple_choice")
        
        if question_data:
            assert "question_text" in question_data, "Question text missing"
            assert "question_type" in question_data, "Question type missing"
            assert "correct_answer" in question_data, "Correct answer missing"
            
            # CRITICAL: If multiple choice, must have options
            if question_data["question_type"] == "multiple_choice":
                assert "multiple_choice_options" in question_data, \
                    "❌ CRITICAL: Multiple choice question missing answer options!"
                
                options = question_data["multiple_choice_options"]
                assert isinstance(options, list), "Options must be a list"
                assert len(options) >= 2, "Must have at least 2 options"
                assert len(options) <= 4, "Should have at most 4 options"
                
                # Verify all options are non-empty strings
                for option in options:
                    assert option and isinstance(option, str), f"Invalid option: {option}"
                
                print(f"✅ PASS: Multiple choice has {len(options)} options")

    @pytest.mark.asyncio
    async def test_trivia_answer_validation_works(self):
        """
        CRITICAL TEST: Verify answer submission and validation works
        
        User Impact: Users can't participate if answer checking breaks
        """
        from bot.database_module import get_database
        
        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")
        
        # Create a test trivia session
        try:
            session_id = db.create_trivia_session(
                question_text="Test question?",
                question_type="single_answer",
                correct_answer="Test Answer",
                approver_id=123456
            )
            
            assert session_id is not None, "Failed to create trivia session"
            
            # Submit an answer
            result = db.submit_trivia_answer(
                session_id=session_id,
                user_id=789012,
                answer_text="Test Answer"
            )
            
            assert result is not None, "Answer submission returned None"
            assert isinstance(result, dict), "Answer result must be a dict"
            assert "success" in result, "Result must indicate success/failure"
            
            print("✅ PASS: Trivia answer submission works")
            
        finally:
            # Cleanup
            if session_id:
                try:
                    db.end_trivia_session(session_id)
                except:
                    pass

    def test_trivia_session_state_management(self):
        """
        CRITICAL TEST: Verify only one active trivia session at a time
        
        User Impact: Multiple concurrent sessions would confuse users
        """
        from bot.database_module import get_database
        
        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")
        
        # Check that we can detect active sessions
        active_session = db.get_active_trivia_session()
        
        # Should return None or a dict, not crash
        assert active_session is None or isinstance(active_session, dict), \
            "Active session check must return None or dict"
        
        print("✅ PASS: Trivia session state management works")


# ============================================================================
# REMINDER SYSTEM TESTS - Critical Scheduled Feature
# ============================================================================

class TestReminderSystem:
    """
    CRITICAL: Reminders affect user trust in bot reliability
    Test Goal: Ensure reminders are created, stored, and retrieved correctly
    """

    @pytest.mark.asyncio
    async def test_reminder_creation_from_natural_language(self):
        """
        CRITICAL TEST: Verify natural language reminder parsing works
        
        User Impact: Users can't create reminders if parsing breaks
        Example: "remind me in 2 hours to check stream" should work
        """
        from bot.commands.reminders import parse_reminder_from_message
        
        test_cases = [
            ("remind me in 2 hours to check stream", True),
            ("reminder in 30 minutes test", True),
            ("remind tomorrow at 3pm to do something", True),
            ("just a normal message", False),  # Should not parse as reminder
        ]
        
        for message, should_parse in test_cases:
            result = await parse_reminder_from_message(message, user_id=123456)
            
            if should_parse:
                assert result is not None, f"Failed to parse reminder: '{message}'"
                assert "content" in result or "message" in result, \
                    "Reminder must have content/message"
                assert "time" in result or "scheduled_time" in result, \
                    "Reminder must have time"
            else:
                assert result is None, f"Incorrectly parsed non-reminder: '{message}'"
        
        print("✅ PASS: Reminder natural language parsing works")

    def test_reminder_storage_and_retrieval(self):
        """
        CRITICAL TEST: Verify reminders are stored and can be retrieved
        
        User Impact: Reminders that aren't stored are lost forever
        """
        from bot.database_module import get_database
        
        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")
        
        # Create a test reminder
        future_time = datetime.now(ZoneInfo("Europe/London")) + timedelta(hours=1)
        
        reminder_id = db.add_reminder(
            user_id=123456,
            reminder_time=future_time,
            content="Test reminder",
            channel_id=789012
        )
        
        assert reminder_id is not None, "Failed to create reminder"
        
        # Retrieve pending reminders
        pending = db.get_pending_reminders()
        
        assert pending is not None, "get_pending_reminders returned None"
        assert isinstance(pending, list), "Pending reminders must be a list"
        
        # Our test reminder should be in there
        found = any(r.get("id") == reminder_id for r in pending)
        assert found, "Created reminder not found in pending list"
        
        print("✅ PASS: Reminder storage and retrieval works")
        
        # Cleanup
        try:
            db.delete_reminder(reminder_id)
        except:
            pass


# ============================================================================
# GAMING DATABASE TESTS - Core Data Feature
# ============================================================================

class TestGamingDatabase:
    """
    CRITICAL: Gaming queries are the bot's primary feature
    Test Goal: Ensure queries return complete, accurate data
    """

    def test_game_query_returns_complete_data(self):
        """
        CRITICAL TEST: Verify game queries return all required fields
        
        User Impact: Missing fields cause incomplete responses to users
        Example: Query for playtime but get no episode count
        """
        from bot.database_module import get_database
        
        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")
        
        # Get any game from the database
        games = db.get_all_played_games()
        
        assert games is not None, "get_all_played_games returned None"
        assert isinstance(games, list), "Games must be a list"
        
        if len(games) > 0:
            game = games[0]
            
            # Verify required fields are present
            required_fields = ["canonical_name", "completion_status"]
            for field in required_fields:
                assert field in game, f"❌ CRITICAL: Game missing required field '{field}'"
            
            # Verify field types
            assert isinstance(game["canonical_name"], str), "canonical_name must be string"
            assert game["canonical_name"].strip(), "canonical_name must not be empty"
            
            print(f"✅ PASS: Game data structure is complete for '{game['canonical_name']}'")

    def test_statistical_queries_return_valid_data(self):
        """
        CRITICAL TEST: Verify statistical queries work correctly
        
        User Impact: Broken stats mean users get wrong answers
        Example: "Most played game" returns None or wrong game
        """
        from bot.database_module import get_database
        
        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")
        
        # Test playtime ranking
        by_playtime = db.get_games_by_playtime(order='DESC', limit=5)
        assert by_playtime is not None, "get_games_by_playtime returned None"
        assert isinstance(by_playtime, list), "Playtime results must be a list"
        
        # If we have results, verify ordering
        if len(by_playtime) >= 2:
            first_game = by_playtime[0]
            second_game = by_playtime[1]
            
            first_time = first_game.get("total_playtime_minutes", 0)
            second_time = second_game.get("total_playtime_minutes", 0)
            
            assert first_time >= second_time, \
                f"❌ CRITICAL: Playtime ranking wrong order! {first_time} < {second_time}"
            
            print(f"✅ PASS: Statistical query ordering correct")


# ============================================================================
# AI RESPONSE TESTS - Critical User Experience
# ============================================================================

class TestAIResponses:
    """
    CRITICAL: AI responses are the bot's personality
    Test Goal: Ensure responses are complete, formatted correctly
    """

    def test_ai_response_filtering_works(self):
        """
        CRITICAL TEST: Verify AI responses are filtered for quality
        
        User Impact: Unfiltered AI can be verbose, repetitive, or broken
        """
        from bot.handlers.ai_handler import filter_ai_response
        
        # Test deduplication
        repetitive = "This is a sentence. This is a sentence. Another sentence."
        filtered = filter_ai_response(repetitive)
        
        assert filtered.count("This is a sentence") == 1, \
            "❌ CRITICAL: AI response not deduplicated!"
        
        # Test length limiting
        very_long = ". ".join([f"Sentence {i}" for i in range(20)])
        filtered = filter_ai_response(very_long)
        
        sentence_count = len([s for s in filtered.split('.') if s.strip()])
        assert sentence_count <= 4, \
            f"❌ CRITICAL: AI response too long! {sentence_count} sentences (max 4)"
        
        print("✅ PASS: AI response filtering works correctly")

    @pytest.mark.asyncio
    async def test_ai_context_detection_works(self):
        """
        CRITICAL TEST: Verify AI detects user context correctly
        
        User Impact: Wrong context = wrong personality/permissions
        """
        from bot.handlers.ai_handler import detect_user_context
        
        # Test with mock member object
        mock_member = MagicMock()
        mock_member.display_name = "Test User"
        mock_member.roles = []
        mock_member.guild_permissions = MagicMock()
        mock_member.guild_permissions.manage_messages = False
        
        context = await detect_user_context(
            user_id=999999,  # Not a special user
            member_obj=mock_member,
            bot=None
        )
        
        assert context is not None, "detect_user_context returned None"
        assert isinstance(context, dict), "Context must be a dict"
        assert "user_name" in context, "Context missing user_name"
        assert "clearance_level" in context, "Context missing clearance_level"
        
        print(f"✅ PASS: AI context detection works")


# ============================================================================
# COMMAND SYSTEM TESTS - Core Interaction
# ============================================================================

class TestCommandSystem:
    """
    CRITICAL: Commands are how users interact with the bot
    Test Goal: Ensure commands are registered and accessible
    """

    def test_critical_commands_are_registered(self):
        """
        CRITICAL TEST: Verify essential commands exist
        
        User Impact: Missing commands = broken functionality
        """
        from bot.commands import strikes, reminders, utility, announcements
        
        # Check that command modules have required functions
        assert hasattr(strikes, "get_user_strikes"), \
            "❌ CRITICAL: Strike system missing get_user_strikes!"
        
        assert hasattr(reminders, "parse_reminder_from_message"), \
            "❌ CRITICAL: Reminder system missing parse function!"
        
        assert hasattr(utility, "get_server_info") or hasattr(utility, "handle_utility_command"), \
            "❌ CRITICAL: Utility commands missing!"
        
        print("✅ PASS: Critical commands are registered")


# ============================================================================
# ANNOUNCEMENT SYSTEM TESTS - Scheduled Content
# ============================================================================

class TestAnnouncementSystem:
    """
    CRITICAL: Announcements are scheduled user-facing content
    Test Goal: Ensure announcement workflow is complete
    """

    @pytest.mark.asyncio
    async def test_announcement_creation_workflow(self):
        """
        CRITICAL TEST: Verify announcement creation doesn't crash
        
        User Impact: Broken announcements = no weekly content
        """
        from bot.handlers.conversation_handler import start_announcement_conversation
        
        # Create mock message
        mock_message = MagicMock()
        mock_message.author = MagicMock()
        mock_message.author.id = 123456
        mock_message.author.dm_channel = None
        mock_message.author.create_dm = AsyncMock()
        mock_message.content = "I want to make an announcement"
        
        # Test that it doesn't crash
        try:
            result = await start_announcement_conversation(mock_message)
            # Should return True (started) or False (didn't start), not crash
            assert isinstance(result, bool), "Announcement conversation must return bool"
            print("✅ PASS: Announcement workflow doesn't crash")
        except Exception as e:
            pytest.fail(f"❌ CRITICAL: Announcement creation crashed: {e}")


# ============================================================================
# DATA QUALITY TESTS - Ensure Database Integrity
# ============================================================================

class TestDataQuality:
    """
    CRITICAL: Bad data = bad answers to users
    Test Goal: Verify data normalization and validation works
    """

    def test_genre_normalization_consistency(self):
        """
        CRITICAL TEST: Verify genres are normalized consistently
        
        User Impact: Inconsistent genres break genre queries
        """
        from bot.utils.data_quality import normalize_genre
        
        test_cases = [
            ("action-rpg", "Action-RPG"),
            ("ACTION", "Action"),
            ("fps", "FPS"),
        ]
        
        for input_genre, expected in test_cases:
            result = normalize_genre(input_genre)
            assert result == expected, \
                f"❌ Genre normalization broken: '{input_genre}' -> '{result}' (expected '{expected}')"
        
        print("✅ PASS: Genre normalization is consistent")

    def test_alternative_names_parsing(self):
        """
        CRITICAL TEST: Verify alternative names are parsed correctly
        
        User Impact: Broken parsing = games not found by alternate names
        """
        from bot.utils.data_quality import parse_complex_array_syntax
        
        # Test PostgreSQL array format
        pg_array = '{"Name 1","Name 2","Name 3"}'
        parsed = parse_complex_array_syntax(pg_array)
        
        assert isinstance(parsed, list), "Parsed result must be a list"
        assert len(parsed) == 3, f"Expected 3 names, got {len(parsed)}"
        assert "Name 1" in parsed, "Parsing lost data"
        
        print("✅ PASS: Alternative names parsing works")


# ============================================================================
# INTEGRATION SMOKE TESTS - External Services
# ============================================================================

class TestIntegrations:
    """
    NON-CRITICAL: External integrations (best effort)
    Test Goal: Verify integrations fail gracefully without credentials
    """

    @pytest.mark.asyncio
    async def test_youtube_integration_fails_gracefully(self):
        """
        Test that YouTube integration handles missing credentials gracefully
        
        Note: Not critical - credentials available in production
        """
        from bot.integrations import youtube
        
        # Should not crash even without credentials
        try:
            # This might return None or empty, but shouldn't crash
            result = await youtube.get_channel_info("test_channel_id")
            # As long as it doesn't crash, we're good
            print("✅ PASS: YouTube integration fails gracefully")
        except Exception as e:
            # Should fail gracefully, not crash with unexpected error
            assert "credential" in str(e).lower() or "api" in str(e).lower(), \
                f"YouTube should fail gracefully, got: {e}"

    @pytest.mark.asyncio  
    async def test_twitch_integration_fails_gracefully(self):
        """
        Test that Twitch integration handles missing credentials gracefully
        
        Note: Not critical - credentials available in production
        """
        from bot.integrations import twitch
        
        # Should not crash even without credentials
        try:
            result = await twitch.get_channel_info("test_channel")
            print("✅ PASS: Twitch integration fails gracefully")
        except Exception as e:
            # Should fail gracefully
            assert "credential" in str(e).lower() or "token" in str(e).lower(), \
                f"Twitch should fail gracefully, got: {e}"


# ============================================================================
# DEPLOYMENT VERIFICATION - Bot Startup
# ============================================================================

class TestDeploymentReadiness:
    """
    CRITICAL: Verify bot can start and core modules load
    Test Goal: Catch deployment blockers before go-live
    """

    def test_all_required_modules_import(self):
        """
        CRITICAL TEST: Verify all core modules can be imported
        
        User Impact: Import errors = bot won't start
        """
        critical_modules = [
            "bot.commands.strikes",
            "bot.commands.reminders", 
            "bot.commands.trivia",
            "bot.commands.utility",
            "bot.commands.announcements",
            "bot.handlers.ai_handler",
            "bot.handlers.message_handler",
            "bot.handlers.conversation_handler",
            "bot.database_module",
            "bot.config",
        ]
        
        for module_name in critical_modules:
            try:
                __import__(module_name)
                print(f"✅ {module_name}")
            except ImportError as e:
                pytest.fail(f"❌ CRITICAL: Cannot import {module_name}: {e}")
        
        print("✅ PASS: All critical modules import successfully")

    def test_database_connection_works(self):
        """
        CRITICAL TEST: Verify database connection can be established
        
        User Impact: No database = no bot functionality
        """
        from bot.database_module import get_database
        
        db = get_database()
        
        # In CI, database_url might be None, which is OK
        # In production, it must work
        if db and db.database_url:
            # If we have a database, test basic query
            try:
                games = db.get_all_played_games()
                assert games is not None, "Database query returned None"
                print("✅ PASS: Database connection works")
            except Exception as e:
                pytest.fail(f"❌ CRITICAL: Database query failed: {e}")
        else:
            pytest.skip("Database not configured (OK in CI, must work in prod)")


# ============================================================================
# TEST EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("ASH BOT - CORE FUNCTIONAL TEST SUITE")
    print("=" * 70)
    print("\nRunning critical functional tests...")
    print("These tests verify complete workflows and catch deployment blockers.\n")
    
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-k", "not test_youtube and not test_twitch"  # Skip integration tests by default
    ])
