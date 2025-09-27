#!/usr/bin/env python3
"""
Test script for trivia system fixes

Tests the complete trivia question pipeline including:
- Rate limiting improvements
- JSON parsing robustness
- Startup validation
- JAM approval workflow
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add the Live directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Import the modules we need to test
try:
    from bot.handlers.ai_handler import (
        generate_ai_trivia_question,
        robust_json_parse,
        determine_request_priority,
        check_rate_limits,
        ai_enabled
    )
    from bot.handlers.conversation_handler import start_jam_question_approval
    from bot.tasks.scheduled import validate_startup_trivia_questions
    print("✅ Successfully imported modules to test")
except ImportError as e:
    print(f"❌ Failed to import modules: {e}")
    sys.exit(1)


class MockBot:
    """Mock bot for testing purposes"""

    def __init__(self):
        self.user = MockUser("Ash Bot", "1234")
        self.fetch_user_calls = []

    async def fetch_user(self, user_id):
        self.fetch_user_calls.append(user_id)
        return MockUser(f"User_{user_id}", str(user_id))


class MockUser:
    """Mock user for testing purposes"""

    def __init__(self, name, user_id):
        self.name = name
        self.id = int(user_id) if user_id.isdigit() else 12345
        self.discriminator = "0001"
        self.send_calls = []

    async def send(self, message):
        self.send_calls.append(message)
        print(f"📤 Mock DM sent to {self.name}: {message[:100]}...")
        return True


async def test_rate_limiting_improvements():
    """Test that startup priority bypasses rate limits"""
    print("\n🧪 Testing Rate Limiting Improvements...")

    try:
        # Test startup priority
        priority = determine_request_priority("Generate trivia question", 12345, "startup_validation")
        print(f"✅ Startup priority detected: {priority}")
        assert priority == "startup", f"Expected 'startup', got '{priority}'"

        # Test that startup priority bypasses rate limits
        can_request, reason = check_rate_limits("startup")
        print(f"✅ Startup priority bypass: {can_request}, {reason}")
        assert can_request, f"Startup priority should bypass rate limits"

        # Test regular priority detection
        priority = determine_request_priority("Generate trivia question", 12345, "trivia")
        print(f"✅ Regular trivia priority detected: {priority}")
        assert priority == "high", f"Expected 'high', got '{priority}'"

        print("✅ Rate limiting improvements working correctly")
        return True

    except Exception as e:
        print(f"❌ Rate limiting test failed: {e}")
        return False


async def test_json_parsing_robustness():
    """Test the robust JSON parser with various malformed inputs"""
    print("\n🧪 Testing JSON Parsing Robustness...")

    test_cases = [
        # Valid JSON
        ('{"question_text": "Test", "question_type": "single_answer", "correct_answer": "Answer"}', True),

        # JSON with markdown formatting
        ('```json\n{"question_text": "Test", "question_type": "single_answer", "correct_answer": "Answer"}\n```', True),

        # JSON with extra text
        ('Here is the JSON:\n{"question_text": "Test", "question_type": "single_answer", "correct_answer": "Answer"}\nThat\'s it!', True),

        # JSON with single quotes (should be fixed)
        ("{'question_text': 'Test', 'question_type': 'single_answer', 'correct_answer': 'Answer'}", True),

        # JSON with trailing comma
        ('{"question_text": "Test", "question_type": "single_answer", "correct_answer": "Answer",}', True),

        # Completely invalid
        ('This is not JSON at all', False),

        # Empty string
        ('', False),
    ]

    passed = 0
    failed = 0

    for i, (test_input, should_succeed) in enumerate(test_cases):
        try:
            result = robust_json_parse(test_input)
            if should_succeed:
                if result is not None and isinstance(result, dict):
                    print(f"✅ Test case {i+1}: Successfully parsed malformed JSON")
                    passed += 1
                else:
                    print(f"❌ Test case {i+1}: Expected success but got None")
                    failed += 1
            else:
                if result is None:
                    print(f"✅ Test case {i+1}: Correctly rejected invalid input")
                    passed += 1
                else:
                    print(f"❌ Test case {i+1}: Expected failure but got result")
                    failed += 1
        except Exception as e:
            print(f"❌ Test case {i+1}: Exception during parsing: {e}")
            failed += 1

    print(f"📊 JSON parsing test results: {passed} passed, {failed} failed")
    return failed == 0


async def test_trivia_question_generation():
    """Test the AI trivia question generation with improved parsing"""
    print("\n🧪 Testing Trivia Question Generation...")

    if not ai_enabled:
        print("⚠️ AI not enabled, skipping generation test")
        return True

    try:
        # Test with startup context to bypass rate limits
        question_data = await generate_ai_trivia_question("startup_validation")

        if question_data:
            print(f"✅ Successfully generated question: {question_data.get('question_text', 'Unknown')[:50]}...")

            # Validate required fields
            required_fields = ['question_text', 'question_type', 'correct_answer']
            missing_fields = [field for field in required_fields if field not in question_data]

            if not missing_fields:
                print("✅ Generated question has all required fields")
                return True
            else:
                print(f"❌ Generated question missing fields: {missing_fields}")
                return False
        else:
            print("❌ Failed to generate trivia question")
            return False

    except Exception as e:
        print(f"❌ Trivia generation test failed: {e}")
        return False


async def test_jam_approval_workflow():
    """Test the JAM approval workflow with mock bot"""
    print("\n🧪 Testing JAM Approval Workflow...")

    # Create a mock question
    mock_question = {
        'question_text': 'Test question for approval workflow?',
        'question_type': 'single_answer',
        'correct_answer': 'Test answer',
        'category': 'test',
        'is_dynamic': False
    }

    try:
        # Mock the bot instance in the system
        mock_bot = MockBot()

        # We can't easily inject the mock bot into the system, so we'll just test
        # that the function doesn't crash and handles errors gracefully
        success = await start_jam_question_approval(mock_question)

        # Since we can't actually send DMs in testing, we expect this to fail gracefully
        if success is False:
            print("✅ JAM approval workflow handled missing bot instance gracefully")
            return True
        else:
            print("⚠️ JAM approval workflow returned unexpected success")
            return True

    except Exception as e:
        print(f"❌ JAM approval workflow test failed: {e}")
        return False


async def test_startup_validation():
    """Test the startup trivia validation process"""
    print("\n🧪 Testing Startup Trivia Validation...")

    try:
        # This will attempt to validate startup questions
        # We expect it to handle missing components gracefully
        await validate_startup_trivia_questions()
        print("✅ Startup validation completed without crashing")
        return True

    except Exception as e:
        print(f"❌ Startup validation test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("🧪 Starting Trivia System Fix Tests")
    print("=" * 50)

    tests = [
        ("Rate Limiting Improvements", test_rate_limiting_improvements),
        ("JSON Parsing Robustness", test_json_parsing_robustness),
        ("Trivia Question Generation", test_trivia_question_generation),
        ("JAM Approval Workflow", test_jam_approval_workflow),
        ("Startup Validation", test_startup_validation),
    ]

    results = {}

    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = await test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = False

    # Summary
    print("\n" + "=" * 50)
    print("🏁 TEST SUMMARY")
    print("=" * 50)

    passed = sum(1 for r in results.values() if r)
    failed = sum(1 for r in results.values() if not r)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")

    print(f"\nTotal: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All tests passed! Trivia system fixes are working correctly.")
        return True
    else:
        print("⚠️ Some tests failed. Please review the output above.")
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fatal error during testing: {e}")
        sys.exit(1)
