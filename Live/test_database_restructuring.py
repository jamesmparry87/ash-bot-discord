#!/usr/bin/env python3
"""
Test script to verify database restructuring works correctly.
This test verifies that the new singleton factory pattern is working
and that all database methods are properly accessible.
"""

import sys
import os

# Add the Live directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

def test_database_restructuring():
    """Test the restructured database import and access patterns."""
    
    print("🧪 Testing Database Restructuring...")
    
    # Test 1: Import the new get_database function
    try:
        from database import get_database
        print("✅ Successfully imported get_database function")
    except ImportError as e:
        print(f"❌ Failed to import get_database: {e}")
        return False
    
    # Test 2: Get database instance
    try:
        db = get_database()
        print(f"✅ Successfully got database instance: {type(db).__name__}")
    except Exception as e:
        print(f"❌ Failed to get database instance: {e}")
        return False
    
    # Test 3: Check if get_connection method is available
    try:
        if hasattr(db, 'get_connection') and callable(getattr(db, 'get_connection')):
            print("✅ get_connection method is available and callable")
        else:
            print("❌ get_connection method not available")
            return False
    except Exception as e:
        print(f"❌ Error checking get_connection method: {e}")
        return False
    
    # Test 4: Test multiple calls return same instance (singleton behavior)
    try:
        db1 = get_database()
        db2 = get_database()
        if db1 is db2:
            print("✅ Singleton pattern working - same instance returned")
        else:
            print("❌ Singleton pattern failed - different instances returned")
            return False
    except Exception as e:
        print(f"❌ Error testing singleton pattern: {e}")
        return False
    
    # Test 5: Check if key database methods are available
    key_methods = [
        'get_user_strikes', 'add_user_strike', 'get_all_games',
        'add_game_recommendation', 'get_played_game', 'get_all_played_games'
    ]
    
    missing_methods = []
    for method_name in key_methods:
        if not hasattr(db, method_name) or not callable(getattr(db, method_name)):
            missing_methods.append(method_name)
    
    if missing_methods:
        print(f"❌ Missing database methods: {missing_methods}")
        return False
    else:
        print(f"✅ All key database methods available: {len(key_methods)} methods checked")
    
    # Test 6: Test bot imports (simulate the problematic imports)
    try:
        # Test the pattern used in scheduled.py
        from bot.tasks.scheduled import db as scheduled_db
        if hasattr(scheduled_db, 'get_connection'):
            print("✅ Scheduled tasks database import working")
        else:
            print("❌ Scheduled tasks database import failed")
            return False
    except Exception as e:
        print(f"❌ Error testing scheduled tasks import: {e}")
        return False
    
    try:
        # Test the pattern used in message_handler.py
        from bot.handlers.message_handler import db as handler_db
        if hasattr(handler_db, 'get_user_strikes'):
            print("✅ Message handler database import working")
        else:
            print("❌ Message handler database import failed")
            return False
    except Exception as e:
        print(f"❌ Error testing message handler import: {e}")
        return False
    
    print("\n🎉 All database restructuring tests passed!")
    print("✅ Pylance errors should be resolved")
    print("✅ Singleton factory pattern working correctly")
    print("✅ All database methods accessible")
    print("✅ Import patterns consistent across modules")
    
    return True

if __name__ == "__main__":
    success = test_database_restructuring()
    if success:
        print("\n🔥 Database restructuring completed successfully!")
        print("The original Pylance error 'get_connection is not a known attribute of module ..database' has been resolved.")
        sys.exit(0)
    else:
        print("\n💥 Database restructuring tests failed!")
        sys.exit(1)
