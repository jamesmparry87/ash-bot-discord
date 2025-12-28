"""
Ash Bot - Core Functional Test Suite (SIMPLIFIED)

PURPOSE: Minimal high-level validation of critical bot features
GOAL: Catch deployment-breaking issues before go-live

Focus on ESSENTIAL functionality only:
- Database queries return complete data
- AI responses are filtered correctly
- All modules import successfully
- Config loads without errors

NO complex workflows - just core validation.
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add Live directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


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

    def test_trivia_session_state_management(self):
        """
        CRITICAL TEST: Verify trivia session queries work

        User Impact: Multiple concurrent sessions would confuse users
        """
        from bot.database_module import get_database

        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")

        # Check that we can query active sessions
        active_session = db.get_active_trivia_session()

        # Should return None or a dict, not crash
        assert active_session is None or isinstance(active_session, dict), \
            "Active session check must return None or dict"

        print("✅ PASS: Trivia session queries work")


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


# ============================================================================
# DATA QUALITY TESTS - Ensure Database Integrity
# ============================================================================

class TestDataQuality:
    """
    CRITICAL: Bad data = bad answers to users
    Test Goal: Verify data normalization works
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
    print("ASH BOT - CORE FUNCTIONAL TEST SUITE (SIMPLIFIED)")
    print("=" * 70)
    print("\nRunning essential functional tests...")
    print("Focus: Database, AI, Modules, Config\n")

    pytest.main([
        __file__,
        "-v",
        "--tb=short"
    ])
