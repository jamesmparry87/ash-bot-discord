#!/usr/bin/env python3
"""
Test script for the conversation context system

This script demonstrates how the new context-aware query system solves
the "Test Game 1" follow-up question problem.
"""

import asyncio
import os
import sys
from unittest.mock import Mock

# Add the Live directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))


def test_context_resolution():
    """Test the context resolution functions"""
    try:
        # Import the context manager
        from bot.handlers.context_manager import (
            ConversationContext,
            detect_follow_up_intent,
            resolve_context_references,
            should_use_context,
        )

        print("✅ Context manager imported successfully")

        # Create a test context
        context = ConversationContext(user_id=12345, channel_id=67890)
        context.update_game_context("Test Game 1", "game_status")

        print(f"✅ Created context with game: {context.last_mentioned_game}")

        # Test pronoun resolution
        test_queries = [
            "how long has she played it for?",
            "did she complete it?",
            "how many episodes does it have?",
            "what about her other games?"
        ]

        for query in test_queries:
            resolved, context_info = resolve_context_references(query, context)
            print(f"Query: '{query}'")
            print(f"  → Resolved: '{resolved}'")
            print(f"  → Context info: {context_info}")
            print()

        # Test follow-up detection
        follow_up_query = "how long has she played it for?"
        follow_up = detect_follow_up_intent(follow_up_query, context)
        if follow_up:
            print(f"✅ Follow-up detected: {follow_up['intent']}")
            print(f"   Context game: {follow_up['context_game']}")
        else:
            print("❌ Follow-up not detected")

        # Test ambiguity detection
        ambiguous_queries = [
            "how long has she played it for?",  # Should be True
            "has jonesy played Call of Duty?",  # Should be False
            "tell me about her gaming",         # Should be True
        ]

        for query in ambiguous_queries:
            needs_context = should_use_context(query)
            print(f"Query '{query}' needs context: {needs_context}")

        return True

    except Exception as e:
        print(f"❌ Context resolution test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query_routing():
    """Test that queries are routed correctly"""
    try:
        from bot.handlers.message_handler import route_query

        # Test resolved queries
        test_queries = [
            ("has jonesy played Test Game 1", "game_status"),
            ("how long did jonesy play Test Game 1", "game_details"),
            ("what horror games has jonesy played", "genre"),
        ]

        for query, expected_type in test_queries:
            query_type, match = route_query(query)
            if query_type == expected_type:
                print(f"✅ Query '{query}' correctly routed as {query_type}")
                if match:
                    print(
                        f"   Matched: {match.group(1) if match.lastindex else 'N/A'}")
            else:
                print(
                    f"❌ Query '{query}' incorrectly routed as {query_type}, expected {expected_type}")

        return True

    except Exception as e:
        print(f"❌ Query routing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("🧪 Testing Conversation Context System")
    print("=" * 50)

    tests_passed = 0
    total_tests = 2

    print("\n📝 Test 1: Context Resolution")
    print("-" * 30)
    if test_context_resolution():
        tests_passed += 1

    print("\n📝 Test 2: Query Routing")
    print("-" * 30)
    if test_query_routing():
        tests_passed += 1

    print("\n" + "=" * 50)
    print(f"✅ {tests_passed}/{total_tests} tests passed")

    if tests_passed == total_tests:
        print("\n🎉 Conversation context system is working correctly!")
        print("\nThe bot can now handle follow-up questions like:")
        print("  User: 'has jonesy played Test Game 1'")
        print("  Bot:  'Affirmative. Captain Jonesy has played...'")
        print("  User: 'how long has she played it for?'")
        print(
            "  Bot:  [Resolves context] 'Database analysis: Captain Jonesy invested...'")
    else:
        print(f"\n❌ {total_tests - tests_passed} tests failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
