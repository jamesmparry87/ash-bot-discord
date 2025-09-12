#!/usr/bin/env python3
"""
Test script to validate the rate limiting and reminder system fixes
"""

import asyncio
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Add the bot module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))


def test_priority_intervals():
    """Test that priority intervals are properly configured"""
    try:
        from bot.config import PRIORITY_INTERVALS, RATE_LIMIT_COOLDOWNS

        print("🧪 Testing Priority Intervals Configuration...")

        # Check priority intervals exist and have expected values
        assert "high" in PRIORITY_INTERVALS, "High priority interval missing"
        assert "medium" in PRIORITY_INTERVALS, "Medium priority interval missing"
        assert "low" in PRIORITY_INTERVALS, "Low priority interval missing"

        assert PRIORITY_INTERVALS[
            "high"] == 1.0, f"High priority should be 1.0s, got {PRIORITY_INTERVALS['high']}"
        assert PRIORITY_INTERVALS[
            "medium"] == 2.0, f"Medium priority should be 2.0s, got {PRIORITY_INTERVALS['medium']}"
        assert PRIORITY_INTERVALS[
            "low"] == 3.0, f"Low priority should be 3.0s, got {PRIORITY_INTERVALS['low']}"

        print("✅ Priority intervals configured correctly")

        # Check progressive cooldowns
        assert RATE_LIMIT_COOLDOWNS[
            "first"] == 30, f"First cooldown should be 30s, got {RATE_LIMIT_COOLDOWNS['first']}"
        assert RATE_LIMIT_COOLDOWNS[
            "second"] == 60, f"Second cooldown should be 60s, got {RATE_LIMIT_COOLDOWNS['second']}"
        assert RATE_LIMIT_COOLDOWNS[
            "third"] == 120, f"Third cooldown should be 120s, got {RATE_LIMIT_COOLDOWNS['third']}"
        assert RATE_LIMIT_COOLDOWNS[
            "persistent"] == 300, f"Persistent cooldown should be 300s, got {RATE_LIMIT_COOLDOWNS['persistent']}"

        print("✅ Progressive cooldowns configured correctly")
        return True

    except Exception as e:
        print(f"❌ Priority intervals test failed: {e}")
        return False


def test_priority_determination():
    """Test the priority determination logic"""
    try:
        from bot.handlers.ai_handler import determine_request_priority

        print("🧪 Testing Priority Determination Logic...")

        # Test high priority cases
        assert determine_request_priority(
            "What is the answer?", 123, "trivia") == "high", "Trivia context should be high priority"
        assert determine_request_priority(
            "What is Captain Jonesy's favorite game?", 123) == "high", "Direct questions should be high priority"

        # Test medium priority cases
        assert determine_request_priority(
            "Hello there", 123) == "medium", "Greetings should be medium priority"
        assert determine_request_priority(
            "Can you help me?", 123) == "medium", "Help requests should be medium priority"

        # Test low priority cases
        background_result = determine_request_priority(
            "Rewrite this announcement", 123, "background")
        print(f"Debug: background context result = '{background_result}'")
        assert background_result == "low", f"Background tasks should be low priority, got '{background_result}'"

        announcement_result = determine_request_priority(
            "This is an announcement to rewrite", 123)
        print(f"Debug: announcement result = '{announcement_result}'")
        assert announcement_result == "low", f"Announcements should be low priority, got '{announcement_result}'"

        print("✅ Priority determination logic working correctly")
        return True

    except Exception as e:
        print(f"❌ Priority determination test failed: {e}")
        return False


def test_database_import():
    """Test that database imports work with the new robust system"""
    try:
        from bot.database import DatabaseManager, db

        print("🧪 Testing Database Import System...")

        # Check if database was imported successfully
        if db is not None:
            print(f"✅ Database imported successfully: {type(db).__name__}")

            # Try to access database_url (should exist even if None)
            if hasattr(db, 'database_url'):
                url_status = "configured" if db.database_url else "not configured"
                print(f"✅ Database URL: {url_status}")
            else:
                print("⚠️ Database URL attribute missing")

            return True
        else:
            print("⚠️ Database is None - this is expected if no DATABASE_URL is set")
            return True  # This is acceptable for testing

    except Exception as e:
        print(f"❌ Database import test failed: {e}")
        return False


def test_rate_limit_functions():
    """Test the rate limiting functions"""
    try:
        from bot.handlers.ai_handler import check_rate_limits, get_progressive_penalty_duration

        print("🧪 Testing Rate Limiting Functions...")

        # Test progressive penalty calculation
        assert get_progressive_penalty_duration(
            0) == 0, "No penalty for 0 errors"
        assert get_progressive_penalty_duration(
            2) == 0, "No penalty for 2 errors"
        assert get_progressive_penalty_duration(
            3) == 30, "30s penalty for 3 errors"
        assert get_progressive_penalty_duration(
            4) == 60, "60s penalty for 4 errors"
        assert get_progressive_penalty_duration(
            5) == 120, "120s penalty for 5 errors"
        assert get_progressive_penalty_duration(
            10) == 300, "300s penalty for 10+ errors"

        print("✅ Progressive penalty calculation working correctly")

        # Test rate limit checking (basic functionality)
        can_request, reason = check_rate_limits("high")
        print(
            f"✅ Rate limit check function callable: can_request={can_request}, reason='{reason}'")

        return True

    except Exception as e:
        print(f"❌ Rate limiting functions test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("🚀 Starting Rate Limiting and Reminder System Fix Validation\n")

    tests = [
        test_priority_intervals,
        test_priority_determination,
        test_database_import,
        test_rate_limit_functions
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
            print()  # Add spacing between tests
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}\n")

    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Deployment fixes are ready.")
        return True
    else:
        print("❌ Some tests failed. Review issues before deployment.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
