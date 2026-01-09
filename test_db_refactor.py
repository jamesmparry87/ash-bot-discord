#!/usr/bin/env python3
"""
Local Test Script - Database Refactor Validation
Tests the new modular database structure without needing DATABASE_URL
"""

print("=" * 60)
print("DATABASE REFACTOR - LOCAL VALIDATION TESTS")
print("=" * 60)

# Test 1: Module Imports
print("\n[TEST 1] Module Import Test...")
try:
    from Live.bot.database import get_database, DatabaseManager
    from Live.bot.database.core import DatabaseManager as CoreDB
    from Live.bot.database.config import ConfigDatabase
    from Live.bot.database.sessions import SessionDatabase
    from Live.bot.database.users import UserDatabase
    from Live.bot.database.stats import StatsDatabase
    from Live.bot.database.trivia import TriviaDatabase
    from Live.bot.database.games import GamesDatabase
    print("✅ All module imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    exit(1)

# Test 2: Singleton Instance
print("\n[TEST 2] Singleton Instance Test...")
try:
    db = get_database()
    print(f"✅ DatabaseManager instance created: {type(db).__name__}")
except Exception as e:
    print(f"❌ Singleton failed: {e}")
    exit(1)

# Test 3: Domain Module Properties
print("\n[TEST 3] Domain Module Properties...")
try:
    assert hasattr(db, 'config'), "Missing config property"
    assert hasattr(db, 'sessions'), "Missing sessions property"
    assert hasattr(db, 'users'), "Missing users property"
    assert hasattr(db, 'stats'), "Missing stats property"
    assert hasattr(db, 'trivia'), "Missing trivia property"
    assert hasattr(db, 'games'), "Missing games property"
    print("✅ All 6 domain properties exist")
except AssertionError as e:
    print(f"❌ Property check failed: {e}")
    exit(1)

# Test 4: Lazy Loading
print("\n[TEST 4] Lazy Loading Test...")
try:
    # Access each property (triggers lazy load)
    config_module = db.config
    sessions_module = db.sessions
    users_module = db.users
    stats_module = db.stats
    trivia_module = db.trivia
    games_module = db.games
    
    print(f"✅ config: {type(config_module).__name__}")
    print(f"✅ sessions: {type(sessions_module).__name__}")
    print(f"✅ users: {type(users_module).__name__}")
    print(f"✅ stats: {type(stats_module).__name__}")
    print(f"✅ trivia: {type(trivia_module).__name__}")
    print(f"✅ games: {type(games_module).__name__}")
except Exception as e:
    print(f"❌ Lazy loading failed: {e}")
    exit(1)

# Test 5: Module Method Existence
print("\n[TEST 5] Key Method Existence...")
try:
    # Config methods
    assert hasattr(db.config, 'get_config_value')
    assert hasattr(db.config, 'set_config_value')
    
    # Users methods
    assert hasattr(db.users, 'get_user_strikes')
    assert hasattr(db.users, 'add_reminder')
    
    # Trivia methods
    assert hasattr(db.trivia, 'add_trivia_question')
    assert hasattr(db.trivia, 'create_trivia_session')
    
    # Games methods
    assert hasattr(db.games, 'add_played_game')
    assert hasattr(db.games, 'get_all_played_games')
    
    # Stats methods
    assert hasattr(db.stats, 'get_platform_comparison_stats')
    
    # Sessions methods
    assert hasattr(db.sessions, 'create_approval_session')
    
    print("✅ All key methods exist")
except AssertionError as e:
    print(f"❌ Method check failed: {e}")
    exit(1)

# Test 6: Core Methods Still Work
print("\n[TEST 6] Core DatabaseManager Methods...")
try:
    assert hasattr(db, 'get_connection')
    assert hasattr(db, 'init_database')
    assert hasattr(db, 'close')
    print("✅ Core connection methods exist")
except AssertionError as e:
    print(f"❌ Core method check failed: {e}")
    exit(1)

# Test 7: Backward Compatibility Check
print("\n[TEST 7] Backward Compatibility...")
try:
    # Old import style should still work
    from Live.bot.database import db as global_db
    assert global_db is not None
    assert isinstance(global_db, DatabaseManager)
    print("✅ Global 'db' alias works")
except Exception as e:
    print(f"❌ Backward compatibility failed: {e}")
    exit(1)

# Summary
print("\n" + "=" * 60)
print("LOCAL VALIDATION: ✅ ALL TESTS PASSED")
print("=" * 60)
print("\n📋 SUMMARY:")
print("  ✅ Module imports: SUCCESS")
print("  ✅ Singleton pattern: SUCCESS")
print("  ✅ Domain properties: SUCCESS (6/6)")
print("  ✅ Lazy loading: SUCCESS")
print("  ✅ Method existence: SUCCESS")
print("  ✅ Core methods: SUCCESS")
print("  ✅ Backward compatibility: SUCCESS")
print("\n🚀 Ready for Rook staging tests!")
