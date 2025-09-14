"""
Test the improved reminder parsing system
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot.tasks.reminders import format_reminder_time, parse_natural_reminder


def test_problematic_cases():
    """Test cases that were previously failing"""
    
    print("🧪 Testing Reminder Parsing Fixes")
    print("=" * 50)
    
    test_cases = [
        "set a reminder for 1 minute's time",
        "remind me in 5 minutes time", 
        "set reminder for 2 minutes' time",
        "remind me in 1 minute to check the server",
        "set reminder for 7pm",
        "remind me in 30 seconds to test",
        "remind me in 1 hour to review",
        "set a reminder for tomorrow at 9am"
    ]
    
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🔍 Test {i}: '{test_case}'")
        
        result = parse_natural_reminder(test_case, 12345)  # Mock user ID
        
        if result["success"]:
            time_diff = result["scheduled_time"] - uk_now
            formatted_time = format_reminder_time(result["scheduled_time"])
            
            print(f"✅ SUCCESS")
            print(f"   Message: '{result['reminder_text']}'")
            print(f"   Time: {formatted_time}")
            print(f"   Confidence: {result.get('confidence', 'unknown')}")
            
            # Specific validation for the problematic case
            if "1 minute's time" in test_case:
                minutes = int(time_diff.total_seconds() // 60)
                if 0 <= minutes <= 2:  # Should be about 1 minute
                    print(f"   ✅ Correct timing: ~{minutes} minute(s)")
                else:
                    print(f"   ❌ WRONG TIMING: {minutes} minutes (expected ~1)")
                    
                if result["reminder_text"] and len(result["reminder_text"]) > 3:
                    print(f"   ✅ Good message extraction")
                else:
                    print(f"   ❌ POOR MESSAGE: '{result['reminder_text']}'")
        else:
            print(f"❌ FAILED: {result.get('error_message', 'Unknown error')}")
            if result.get('suggestion'):
                print(f"   Suggestion: {result['suggestion']}")

def test_edge_cases():
    """Test edge cases and validation"""
    
    print("\n\n🧪 Testing Edge Cases & Validation")
    print("=" * 50)
    
    edge_cases = [
        "",  # Empty
        "set a reminder",  # No time or message
        "remind me in 5",  # No units
        "remind me",  # Just command
        "1 minute's time",  # Just time, no message  
        "set reminder for test",  # Ambiguous
    ]
    
    for i, test_case in enumerate(edge_cases, 1):
        print(f"\n🔍 Edge Case {i}: '{test_case}'")
        
        result = parse_natural_reminder(test_case, 12345)
        
        if result["success"]:
            print(f"✅ Parsed (unexpected)")
            print(f"   Message: '{result['reminder_text']}'")
        else:
            print(f"❌ Correctly rejected: {result.get('error_message', 'Unknown error')}")

if __name__ == "__main__":
    test_problematic_cases()
    test_edge_cases()
    
    print("\n" + "=" * 50)
    print("🎯 Test Summary:")
    print("- Main fix: 'set a reminder for 1 minute's time' should parse correctly")
    print("- Should extract meaningful message or ask for clarification")
    print("- Should calculate timing correctly (1 minute, not 59 minutes)")
    print("- Should provide helpful error messages for ambiguous input")
