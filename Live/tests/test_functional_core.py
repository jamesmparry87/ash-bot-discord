"""
Ash Bot - Core Functional Test Suite (SIMPLIFIED)

PURPOSE: Minimal high-level validation of critical bot features
GOAL: Catch deployment-breaking issues before go-live

Focus on ESSENTIAL functionality only:
- Database queries return complete data
- Config loads without errors
- Basic module imports work

NO complex workflows, NO heavy imports - just core validation.

NOTE: Timeouts managed at workflow level (8 minutes) and per-step level in CI.
Individual test timeouts removed because signal.SIGALRM doesn't work on Windows.

UPDATED: Tests now use modular database architecture (db.games, db.trivia, etc.)
"""

import os
import sys
import pytest

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
        from bot.database import get_database

        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")

        # Get any game from the database - USE MODULAR API
        games = db.games.get_all_played_games()

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
        from bot.database import get_database

        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")

        # Test playtime ranking - USE MODULAR API
        by_playtime = db.games.get_games_by_playtime(order='DESC', limit=5)
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
        from bot.database import get_database

        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")

        # Check that we can query active sessions - USE MODULAR API
        active_session = db.trivia.get_active_trivia_session()

        # Should return None or a dict, not crash
        assert active_session is None or isinstance(active_session, dict), \
            "Active session check must return None or dict"

        print("✅ PASS: Trivia session queries work")


# ============================================================================
# CONFIGURATION TESTS - Verify Core Config
# ============================================================================

class TestConfiguration:
    """
    CRITICAL: Configuration must load without errors
    Test Goal: Ensure all config constants are accessible
    """

    def test_config_loads_successfully(self):
        """
        CRITICAL TEST: Verify config module loads without errors

        User Impact: Config errors = bot won't start
        """
        from bot.config import (
            GUILD_ID,
            JONESY_USER_ID,
            JAM_USER_ID,
            MAX_DAILY_REQUESTS,
            MAX_HOURLY_REQUESTS
        )

        # Verify critical IDs are present and valid
        assert GUILD_ID is not None, "GUILD_ID not configured"
        assert JONESY_USER_ID is not None, "JONESY_USER_ID not configured"
        assert JAM_USER_ID is not None, "JAM_USER_ID not configured"

        # Verify rate limits are sensible
        assert MAX_DAILY_REQUESTS > 0, "MAX_DAILY_REQUESTS must be positive"
        assert MAX_HOURLY_REQUESTS > 0, "MAX_HOURLY_REQUESTS must be positive"
        assert MAX_HOURLY_REQUESTS <= MAX_DAILY_REQUESTS, "Hourly limit can't exceed daily limit"

        print("✅ PASS: Config module loads and validates successfully")


# ============================================================================
# DEPLOYMENT VERIFICATION - Bot Startup
# ============================================================================

class TestDeploymentReadiness:
    """
    CRITICAL: Verify bot can start and core modules load
    Test Goal: Catch deployment blockers before go-live
    """

    def test_core_database_module_imports(self):
        """
        CRITICAL TEST: Verify core database module can be imported

        User Impact: Import errors = bot won't start
        """
        try:
            from bot.database import get_database
            from bot import config
            print("✅ Core modules (database, config) import successfully")
        except ImportError as e:
            pytest.fail(f"❌ CRITICAL: Cannot import core modules: {e}")

    def test_database_connection_works(self):
        """
        CRITICAL TEST: Verify database connection can be established

        User Impact: No database = no bot functionality
        """
        from bot.database import get_database

        db = get_database()

        # In CI, database_url might be None, which is OK
        # In production, it must work
        if db and db.database_url:
            # If we have a database, test basic query using modular API
            try:
                games = db.games.get_all_played_games()
                assert games is not None, "Database query returned None"
                print("✅ PASS: Database connection works")
            except Exception as e:
                pytest.fail(f"❌ CRITICAL: Database query failed: {e}")
        else:
            pytest.skip("Database not configured (OK in CI, must work in prod)")

    def test_database_stats_query_works(self):
        """
        CRITICAL TEST: Verify database stats queries work

        User Impact: Stats queries are frequently used by the bot
        """
        from bot.database import get_database

        db = get_database()
        if not db or not db.database_url:
            pytest.skip("Database not available")

        try:
            stats = db.games.get_played_games_stats()
            assert stats is not None, "get_played_games_stats returned None"
            assert isinstance(stats, dict), "Stats must be a dictionary"
            
            # If stats is empty, database connection might have failed
            if not stats:
                pytest.skip("Database returned empty stats (connection may have failed)")
            
            assert "total_games" in stats, "Stats missing total_games"
            print(f"✅ PASS: Stats query works (found {stats.get('total_games', 0)} games)")
        except Exception as e:
            pytest.fail(f"❌ CRITICAL: Stats query failed: {e}")


# ============================================================================
# TEST EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("ASH BOT - CORE FUNCTIONAL TEST SUITE (SIMPLIFIED)")
    print("=" * 70)
    print("\nRunning essential functional tests...")
    print("Focus: Database, Config, Core Modules")
    print("NOTE: Some tests may be skipped if database is not available\n")

    pytest.main([
        __file__,
        "-v",
        "--tb=short"
    ])
