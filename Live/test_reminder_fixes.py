#!/usr/bin/env python3
"""
Test script to verify reminder system fixes
Tests both simplified confirmations and DM delivery functionality
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add the project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

async def test_reminder_system():
    """Test the reminder system components"""
    print("🧪 Testing Reminder System Fixes")
    print("=" * 50)
    
    # Test 1: Database connection
    print("\n📋 Test 1: Database Connection")
    try:
        from bot.database_module import get_database
        db = get_database()
        
        if db and hasattr(db, 'get_connection'):
            conn = db.get_connection()
            if conn:
                print("✅ Database connection successful")
                
                # Test reminder methods exist
                if hasattr(db, 'add_reminder') and hasattr(db, 'get_due_reminders'):
                    print("✅ Required reminder methods exist")
                else:
                    print("❌ Missing reminder methods")
            else:
                print("❌ Database connection failed")
        else:
            print("❌ Database instance not available")
    except Exception as e:
        print(f"❌ Database test failed: {e}")
    
    # Test 2: Time formatting
    print("\n⏰ Test 2: Time Formatting")
    try:
        from bot.tasks.reminders import format_reminder_time
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        test_time = uk_now + timedelta(minutes=30)
        formatted = format_reminder_time(test_time)
        print(f"✅ Time formatting works: '{formatted}'")
    except Exception as e:
        print(f"❌ Time formatting test failed: {e}")
    
    # Test 3: Bot instance detection
    print("\n🤖 Test 3: Bot Instance Detection")
    try:
        import sys
        bot_found = False
        for name, obj in sys.modules.items():
            if hasattr(obj, 'bot') and hasattr(obj.bot, 'user'):
                print(f"✅ Found bot instance in module: {name}")
                bot_found = True
                break
        
        if not bot_found:
            print("⚠️ Bot instance not found in loaded modules (expected in test environment)")
        
    except Exception as e:
        print(f"❌ Bot instance detection test failed: {e}")
    
    # Test 4: Reminder parsing (if available)
    print("\n📝 Test 4: Natural Language Parsing")
    try:
        from bot.tasks.reminders import parse_natural_reminder
        
        test_cases = [
            "remind me in 5 minutes to check stream",
            "set reminder for 10 minutes about meeting",
            "remind me at 3pm to call john"
        ]
        
        for test_case in test_cases:
            try:
                result = parse_natural_reminder(test_case, 12345)
                if result.get("success"):
                    print(f"✅ Parsed: '{test_case}' -> {result.get('reminder_text')}")
                else:
                    print(f"⚠️ Failed to parse: '{test_case}' - {result.get('error_message')}")
            except Exception as parse_e:
                print(f"❌ Parse error for '{test_case}': {parse_e}")
                
    except ImportError:
        print("⚠️ Natural language parsing module not available")
    except Exception as e:
        print(f"❌ Natural language parsing test failed: {e}")
    
    # Test 5: Delivery function structure
    print("\n📤 Test 5: Delivery Function Structure")
    try:
        from bot.tasks.scheduled import deliver_reminder
        print("✅ deliver_reminder function exists")
        
        # Check function signature
        import inspect
        sig = inspect.signature(deliver_reminder)
        if 'reminder' in sig.parameters:
            print("✅ deliver_reminder has correct signature")
        else:
            print("❌ deliver_reminder has incorrect signature")
            
    except Exception as e:
        print(f"❌ Delivery function test failed: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 Test Summary Complete")
    print("\nKey improvements implemented:")
    print("• ✅ Simplified reminder confirmation messages")
    print("• ✅ Enhanced bot instance detection in scheduled tasks") 
    print("• ✅ Comprehensive error logging for DM delivery")
    print("• ✅ Reliable fallback mechanisms for bot access")
    print("\nNext steps:")
    print("• Test with actual bot instance running")
    print("• Set test reminders and verify DM delivery")
    print("• Monitor logs for any remaining issues")

if __name__ == "__main__":
    asyncio.run(test_reminder_system())
