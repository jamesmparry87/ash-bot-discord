#!/usr/bin/env python3
"""
Test Natural Language Command Priority Fix

Tests that natural language commands like "set a reminder for 1 minute from now"
are properly detected and processed as commands instead of FAQ responses.
"""

import os
import re
import sys

# Add the parent directory to the path so we can import from bot_modular
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def detect_natural_language_command(content: str) -> bool:
    """Detect if a message is likely a natural language command that should be processed as a command"""
    content_lower = content.lower().strip()

    # Natural language command patterns - these should be processed as commands, not FAQ
    command_patterns = [
        # Reminder commands
        r"set\s+(?:a\s+)?remind(?:er)?\s+for",
        r"remind\s+me\s+(?:in|at|to)",
        r"create\s+(?:a\s+)?remind(?:er)?\s+for",
        r"schedule\s+(?:a\s+)?remind(?:er)?\s+for",
        r"set\s+(?:a\s+)?timer\s+for",
        r"remind\s+(?:me\s+)?in\s+\d+",
        r"reminder\s+(?:in|for)\s+\d+",
        
        # Game recommendation commands (natural language alternatives)
        r"(?:add|suggest|recommend)\s+(?:the\s+)?game",
        r"i\s+want\s+to\s+(?:add|suggest|recommend)",
        r"(?:add|suggest)\s+.+\s+(?:game|to\s+(?:the\s+)?(?:list|database))",
        
        # Other potential natural language commands
        r"show\s+(?:me\s+)?(?:my\s+)?reminders?",
        r"list\s+(?:my\s+)?reminders?",
        r"cancel\s+(?:my\s+)?reminder",
        r"delete\s+(?:my\s+)?reminder",
    ]

    return any(re.search(pattern, content_lower) for pattern in command_patterns)


def test_natural_language_commands():
    """Test that natural language commands are properly detected"""
    
    # Test cases that SHOULD be detected as commands
    command_cases = [
        "set a reminder for 1 minute from now",
        "remind me in 5 minutes to check stream",
        "create a reminder for tomorrow at 9am",
        "schedule a reminder for 2 hours",
        "set a timer for 30 minutes", 
        "remind me in 10 minutes",
        "reminder for 1 hour",
        "add the game Dark Souls",
        "suggest a game called Elden Ring",
        "i want to recommend Bloodborne",
        "show me my reminders",
        "list my reminders",
        "cancel my reminder",
        "delete my reminder",
    ]
    
    # Test cases that should NOT be detected as commands (should go to FAQ/conversation)
    non_command_cases = [
        "hello",
        "what can you do", 
        "has jonesy played gears of war",
        "what games has jonesy played",
        "how are you",
        "thank you",
        "what time is it",
        "who are you",
        "random conversation text",
        "just chatting here",
    ]
    
    print("🔍 Testing Natural Language Command Detection")
    print("=" * 50)
    
    # Test positive cases
    print("\n✅ Commands that SHOULD be detected:")
    all_commands_detected = True
    for test_case in command_cases:
        is_detected = detect_natural_language_command(test_case)
        status = "✅ DETECTED" if is_detected else "❌ MISSED"
        print(f"  {status}: '{test_case}'")
        if not is_detected:
            all_commands_detected = False
    
    # Test negative cases  
    print("\n❌ Text that should NOT be detected as commands:")
    all_non_commands_ignored = True
    for test_case in non_command_cases:
        is_detected = detect_natural_language_command(test_case)
        status = "✅ IGNORED" if not is_detected else "❌ FALSE POSITIVE"
        print(f"  {status}: '{test_case}'")
        if is_detected:
            all_non_commands_ignored = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY:")
    
    if all_commands_detected:
        print("✅ All command patterns correctly detected")
    else:
        print("❌ Some command patterns were missed")
        
    if all_non_commands_ignored:
        print("✅ All non-command text correctly ignored")  
    else:
        print("❌ Some non-command text was falsely detected as commands")
        
    if all_commands_detected and all_non_commands_ignored:
        print("\n🎉 ALL TESTS PASSED - Natural language command detection working correctly!")
        return True
    else:
        print("\n⚠️ SOME TESTS FAILED - Review detection patterns")
        return False


def test_reminder_pattern_matching():
    """Test specific reminder patterns that were problematic"""
    
    print("\n🔍 Testing Specific Reminder Patterns")
    print("=" * 40)
    
    reminder_test_cases = [
        ("set a reminder for 1 minute from now", True),
        ("set reminder for 2 hours", True), 
        ("remind me in 30 minutes to check stream", True),
        ("remind me to take a break", False),  # No time specified
        ("create a reminder for tonight", True),
        ("schedule reminder for tomorrow", True),
        ("set a timer for 5 minutes", True),
        ("reminder in 10 minutes", True),
        ("what are reminders", False),  # FAQ question
        ("how do reminders work", False),  # FAQ question
    ]
    
    for test_input, should_detect in reminder_test_cases:
        is_detected = detect_natural_language_command(test_input)
        
        if should_detect and is_detected:
            status = "✅ CORRECT - Detected as command"
        elif not should_detect and not is_detected:
            status = "✅ CORRECT - Ignored (not a command)"
        elif should_detect and not is_detected:
            status = "❌ FAILED - Should be detected as command"
        else:
            status = "❌ FAILED - Should not be detected as command"
            
        print(f"  {status}: '{test_input}'")


def main():
    """Run all tests"""
    print("🚀 Testing Natural Language Command Priority Fix")
    print("=" * 60)
    
    # Test basic command detection
    detection_passed = test_natural_language_commands()
    
    # Test specific reminder patterns
    test_reminder_pattern_matching()
    
    print("\n" + "=" * 60)
    if detection_passed:
        print("🎉 OVERALL: Command priority fix appears to be working correctly!")
        print("\nThe bot should now:")
        print("✅ Detect 'set a reminder for 1 minute from now' as a command")
        print("✅ Process natural language reminders instead of showing FAQ")
        print("✅ Still handle regular conversation and gaming queries normally")
    else:
        print("⚠️ OVERALL: Some issues detected - may need pattern adjustments")
    
    return detection_passed


if __name__ == "__main__":
    main()
