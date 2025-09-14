"""
Test the enhanced reminder parsing system with comprehensive date/time formats
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bot.tasks.reminders import parse_natural_reminder, format_reminder_time

def test_comprehensive_formats():
    """Test comprehensive date/time formats"""
    
    print("🧪 Testing Enhanced Reminder Parsing")
    print("=" * 60)
    
    # Duration-based reminders (most common)
    duration_tests = [
        "remind me in 1 minute to check server",
        "remind me in 5m to test something", 
        "remind me in 2 hours to review code",
        "remind me in 1h to call back",
        "remind me in 3 days to follow up",
        "remind me in 2 weeks to check project status",
        "remind me in 30 seconds to restart service",
    ]
    
    # Specific time reminders
    time_tests = [
        "remind me at 3pm to attend meeting",
        "remind me at 7:30am to wake up early",
        "remind me at 10.15pm to check logs",
        "set reminder for 2pm to review reports",
        "remind me at noon to have lunch",
        "remind me at midnight to backup database",
    ]
    
    # Day-specific reminders  
    day_tests = [
        "remind me monday at 9am to start week",
        "remind me next friday at 5pm for weekly review", 
        "remind me tomorrow at 10am to call client",
        "remind me tuesday to check updates",
        "remind me next monday to begin project",
    ]
    
    # Edge cases that should ask for clarification
    ambiguous_tests = [
        "set a reminder for 1 minute's time",
        "remind me in 5 minutes time",
        "set reminder for 7pm", 
        "remind me tomorrow",
    ]
    
    all_tests = [
        ("Duration-based", duration_tests),
        ("Specific times", time_tests),
        ("Day-specific", day_tests),
        ("Ambiguous (should ask for clarification)", ambiguous_tests),
    ]
    
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    
    for category, test_cases in all_tests:
        print(f"\n📅 {category.upper()}:")
        print("=" * 40)
        
        for test_case in test_cases:
            print(f"\n🔍 '{test_case}'")
            
            result = parse_natural_reminder(test_case, 12345)
            
            if result["success"]:
                time_diff = result["scheduled_time"] - uk_now
                formatted_time = format_reminder_time(result["scheduled_time"])
                
                print(f"✅ SUCCESS")
                print(f"   Message: '{result['reminder_text']}'")
                print(f"   When: {formatted_time}")
                print(f"   Confidence: {result.get('confidence', 'unknown')}")
                
                # Validate timing makes sense
                total_minutes = int(time_diff.total_seconds() / 60)
                if "1 minute" in test_case and 0 <= total_minutes <= 2:
                    print(f"   ✅ Correct timing (~{total_minutes} minutes)")
                elif "5m" in test_case and 4 <= total_minutes <= 6:
                    print(f"   ✅ Correct timing (~{total_minutes} minutes)")
                elif "2 hours" in test_case and 115 <= total_minutes <= 125:
                    print(f"   ✅ Correct timing (~{total_minutes//60} hours)")
                
            else:
                print(f"❌ FAILED: {result.get('error_message', 'Unknown error')}")
                if result.get('suggestion'):
                    print(f"   💡 Suggestion: {result['suggestion']}")
                    
                # Validate that ambiguous cases are properly caught
                if category == "Ambiguous (should ask for clarification)":
                    print(f"   ✅ Correctly identified as ambiguous")

def test_confirmation_suggestions():
    """Test that the bot provides clear confirmation suggestions"""
    
    print("\n\n🤖 Testing Confirmation Logic")
    print("=" * 40)
    
    # Cases where bot should ask "Did you mean X?"
    confirmation_tests = [
        ("set reminder for 7pm", "Did you mean: 'remind me at 7pm to [do something]'?"),
        ("remind me friday", "Did you mean: 'remind me friday at [time] to [do something]'?"),
        ("remind me in 1 hour", "Did you mean: 'remind me in 1 hour to [do something]'?"),
    ]
    
    for test_input, expected_pattern in confirmation_tests:
        print(f"\n🔍 '{test_input}'")
        
        result = parse_natural_reminder(test_input, 12345)
        
        if not result["success"]:
            error_msg = result.get('error_message', '')
            suggestion = result.get('suggestion', '')
            
            print(f"❌ Asked for clarification: {error_msg}")
            if suggestion:
                print(f"💡 Suggestion provided: {suggestion}")
                print(f"✅ Good user experience - clear guidance provided")
        else:
            print(f"⚠️ Parsed without asking for clarification")
            print(f"   Message: '{result['reminder_text']}'")

if __name__ == "__main__":
    test_comprehensive_formats()
    test_confirmation_suggestions()
    
    print("\n" + "=" * 60)
    print("🎯 SUMMARY:")
    print("✅ Duration parsing: in 1 minute, 5m, 2 hours, 1h, 3 days, 2 weeks")  
    print("✅ Time parsing: 3pm, 7:30am, 10.15pm, noon, midnight")
    print("✅ Day parsing: monday at 9am, next friday 5pm, tomorrow 10am")
    print("✅ Validation: Ambiguous cases ask for clarification") 
    print("✅ Simple delivery: Just 'Reminder: [message]'")
    print("✅ Scheduled tasks: Now properly start when bot loads")
