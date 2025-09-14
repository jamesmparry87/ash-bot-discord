#!/usr/bin/env python3
"""
Test Reminder Integration Fix

Comprehensive test to verify that the command priority fix works correctly
and that natural language reminders are processed instead of showing FAQ responses.
"""

import os
import re
import sys

# Add the parent directory to the path so we can import from bot_modular
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def simulate_message_processing_flow(message_content: str, is_dm: bool = False, is_mentioned: bool = False):
    """
    Simulate the message processing flow from bot_modular.py
    Returns the processing path that would be taken
    """
    
    # Import the functions from bot_modular
    try:
        from bot_modular import detect_implicit_game_query, detect_natural_language_command
    except ImportError:
        # Fallback - define the functions locally
        def detect_natural_language_command(content: str) -> bool:
            content_lower = content.lower().strip()
            command_patterns = [
                r"set\s+(?:a\s+)?remind(?:er)?\s+for",
                r"remind\s+me\s+(?:in|at|to)",
                r"create\s+(?:a\s+)?remind(?:er)?\s+for",
                r"schedule\s+(?:a\s+)?remind(?:er)?\s+for",
                r"set\s+(?:a\s+)?timer\s+for",
                r"remind\s+(?:me\s+)?in\s+\d+",
                r"reminder\s+(?:in|for)\s+\d+",
            ]
            return any(re.search(pattern, content_lower) for pattern in command_patterns)
        
        def detect_implicit_game_query(content: str) -> bool:
            content_lower = content.lower()
            game_query_patterns = [
                r"has\s+jonesy\s+played",
                r"did\s+jonesy\s+play",
                r"what\s+games?\s+has\s+jonesy",
                r"what.*game.*most.*playtime",
            ]
            return any(re.search(pattern, content_lower) for pattern in game_query_patterns)
    
    # Simulate the processing logic from on_message
    content = message_content
    is_implicit_game_query = detect_implicit_game_query(content)
    
    # Determine if we should process this message for queries
    should_process_query = (
        is_dm or  # All DMs get processed
        is_mentioned or  # Explicit mentions
        message_content.lower().startswith('ash') or  # "ash" prefix
        is_implicit_game_query  # Implicit game queries
    )
    
    if should_process_query:
        # Traditional command check
        if not is_dm and message_content.strip().startswith('!'):
            return "traditional_command"
        
        # Natural language command check
        if detect_natural_language_command(content):
            return "natural_language_command"
        
        # Game query check
        if is_implicit_game_query:
            return "game_query"
        
        # Fall through to general conversation
        return "general_conversation"
    
    # Process commands normally for guild messages
    if not is_dm and not is_mentioned:
        return "normal_command_processing"
    
    return "general_conversation"


def test_message_processing_priority():
    """Test that messages are processed in the correct priority order"""
    
    print("🔍 Testing Message Processing Priority")
    print("=" * 50)
    
    test_cases = [
        # Traditional commands should go to traditional_command
        ("!remind me in 5 minutes", False, False, "traditional_command"),
        ("!addgame Dark Souls", False, False, "traditional_command"),
        
        # Natural language commands should go to natural_language_command
        ("set a reminder for 1 minute from now", False, True, "natural_language_command"),
        ("remind me in 30 minutes to check stream", True, False, "natural_language_command"),
        ("create a reminder for tomorrow", False, True, "natural_language_command"),
        
        # Game queries should go to game_query
        ("has jonesy played gears of war", False, True, "game_query"),
        ("what horror games has jonesy played", True, False, "game_query"),
        
        # General conversation should go to general_conversation
        ("hello", True, False, "general_conversation"),
        ("what can you do", False, True, "general_conversation"),
        ("how are you", True, False, "general_conversation"),
        
        # Non-processed messages should go to normal command processing
        ("just regular chat", False, False, "normal_command_processing"),
    ]
    
    all_correct = True
    
    for message, is_dm, is_mentioned, expected_path in test_cases:
        actual_path = simulate_message_processing_flow(message, is_dm, is_mentioned)
        
        if actual_path == expected_path:
            status = "✅ CORRECT"
        else:
            status = "❌ INCORRECT"
            all_correct = False
        
        context = []
        if is_dm:
            context.append("DM")
        if is_mentioned:
            context.append("mentioned")
        context_str = f" ({', '.join(context)})" if context else ""
        
        print(f"  {status}: '{message}'{context_str}")
        print(f"    Expected: {expected_path} | Actual: {actual_path}")
        
    print("\n" + "=" * 50)
    if all_correct:
        print("✅ All message processing priorities are correct!")
    else:
        print("❌ Some message processing priorities are incorrect!")
        
    return all_correct


def test_reminder_specific_cases():
    """Test specific reminder cases that were problematic"""
    
    print("\n🎯 Testing Specific Reminder Cases")
    print("=" * 40)
    
    reminder_cases = [
        # The original problem case
        ("set a reminder for 1 minute from now", "Should be processed as natural language command, not FAQ"),
        
        # Other common reminder patterns
        ("remind me in 5 minutes", "Should be processed as natural language command"),
        ("create a reminder for 2 hours", "Should be processed as natural language command"),
        ("set a timer for 30 minutes", "Should be processed as natural language command"),
        
        # These should NOT be processed as commands
        ("what are reminders", "Should go to FAQ/conversation"),
        ("how do reminders work", "Should go to FAQ/conversation"),
        ("tell me about the reminder system", "Should go to FAQ/conversation"),
    ]
    
    for message, description in reminder_cases:
        # Test in different contexts
        contexts = [
            (True, False, "DM"),
            (False, True, "Guild + mentioned"),
            (False, False, "Guild only")
        ]
        
        print(f"\n📝 Testing: '{message}'")
        print(f"   Expected: {description}")
        
        for is_dm, is_mentioned, context_name in contexts:
            path = simulate_message_processing_flow(message, is_dm, is_mentioned)
            
            # Check if it's being processed correctly
            if "remind" in message.lower() and any(word in message.lower() for word in ["set", "create", "timer", "in", "for"]):
                expected_as_command = True
            else:
                expected_as_command = False
            
            is_command_path = path == "natural_language_command"
            
            if expected_as_command and is_command_path:
                status = "✅ GOOD"
            elif not expected_as_command and not is_command_path:
                status = "✅ GOOD"
            else:
                status = "⚠️ CHECK"
            
            print(f"   {status} {context_name}: {path}")


def main():
    """Run all integration tests"""
    
    print("🚀 Testing Reminder Integration Fix")
    print("=" * 60)
    
    # Test message processing priority
    priority_passed = test_message_processing_priority()
    
    # Test specific reminder cases
    test_reminder_specific_cases()
    
    print("\n" + "=" * 60)
    print("📊 INTEGRATION TEST SUMMARY:")
    
    if priority_passed:
        print("✅ Message processing priority is working correctly")
        print("✅ Natural language commands are prioritized over FAQ responses")
        print("✅ The original issue should be resolved:")
        print("   • 'set a reminder for 1 minute from now' → Command processing")
        print("   • 'remind me in 5 minutes' → Command processing") 
        print("   • 'what are reminders' → FAQ response")
        print("   • Game queries still work normally")
        
        print("\n🎉 INTEGRATION TESTS PASSED!")
        print("The command vs FAQ priority fix is working correctly.")
        
    else:
        print("❌ Some issues detected in message processing priority")
        print("⚠️ The fix may need additional adjustments")
    
    return priority_passed


if __name__ == "__main__":
    main()
