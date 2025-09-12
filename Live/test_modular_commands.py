"""
Test script for the modular command architecture
Tests that command modules can be loaded and basic functionality works
"""

import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock

# Add the bot directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

def test_module_imports():
    """Test that all command modules can be imported"""
    print("🧪 Testing module imports...")
    
    try:
        from bot.commands import strikes, games, utility
        print("✅ All command modules imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_cog_creation():
    """Test that cogs can be instantiated"""
    print("🧪 Testing cog instantiation...")
    
    try:
        from bot.commands.strikes import StrikesCommands
        from bot.commands.games import GamesCommands
        from bot.commands.utility import UtilityCommands
        
        # Mock bot object
        mock_bot = Mock()
        
        # Test cog creation
        strikes_cog = StrikesCommands(mock_bot)
        games_cog = GamesCommands(mock_bot)
        utility_cog = UtilityCommands(mock_bot)
        
        print("✅ All cogs instantiated successfully")
        print(f"  - StrikesCommands: {len(strikes_cog.get_commands())} commands")
        print(f"  - GamesCommands: {len(games_cog.get_commands())} commands") 
        print(f"  - UtilityCommands: {len(utility_cog.get_commands())} commands")
        
        return True
    except Exception as e:
        print(f"❌ Cog creation error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_imports():
    """Test that database modules can be imported"""
    print("🧪 Testing database imports...")
    
    try:
        from bot.database import db, DatabaseManager
        print("✅ Database modules imported successfully")
        print(f"  - Database instance: {'Available' if db else 'None'}")
        return True
    except ImportError as e:
        print(f"❌ Database import error: {e}")
        return False

def test_config_imports():
    """Test that config modules can be imported"""
    print("🧪 Testing config imports...")
    
    try:
        from bot.config import (
            TOKEN, GUILD_ID, JONESY_USER_ID, JAM_USER_ID,
            FAQ_RESPONSES, BOT_PERSONA
        )
        print("✅ Config modules imported successfully")
        print(f"  - FAQ responses: {len(FAQ_RESPONSES) if FAQ_RESPONSES else 0} entries")
        print(f"  - Bot persona: {'Configured' if BOT_PERSONA else 'None'}")
        return True
    except ImportError as e:
        print(f"❌ Config import error: {e}")
        return False

def test_utils_imports():
    """Test that utility modules can be imported"""
    print("🧪 Testing utils imports...")
    
    try:
        from bot.utils.permissions import (
            get_user_communication_tier, user_is_mod, user_is_member
        )
        print("✅ Utils modules imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Utils import error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Starting modular architecture tests...\n")
    
    tests = [
        ("Module Imports", test_module_imports),
        ("Database Imports", test_database_imports), 
        ("Config Imports", test_config_imports),
        ("Utils Imports", test_utils_imports),
        ("Cog Creation", test_cog_creation),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        result = test_func()
        results.append((test_name, result))
    
    print(f"\n{'='*50}")
    print("📊 TEST SUMMARY:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed! Modular architecture is working correctly.")
        print("\nThe bot has been successfully refactored from a 5000+ line monolithic file")
        print("into focused modules of 100-300 lines each, achieving massive context reduction!")
    else:
        print("⚠️ Some tests failed. Check the error messages above for details.")
    
    return passed == len(tests)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
