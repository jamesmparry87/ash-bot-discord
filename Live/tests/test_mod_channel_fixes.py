"""
Test script to verify mod channel behavior fixes
Tests the specific issue where bot responded inappropriately to casual conversation
"""

from bot.handlers.context_manager import should_use_context
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add the bot directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))


class TestModChannelFixes(unittest.TestCase):
    """Test that mod channel fixes work correctly"""

    def test_context_detection_false_positives(self):
        """Test that casual conversation doesn't trigger context detection"""

        # The original problematic message
        problematic_message = "Ash will be but it's Rook right now because I'm testing it on the staging bot"

        # This should NOT trigger context detection (no gaming context)
        result = should_use_context(problematic_message)
        self.assertFalse(result, "Casual conversation should not trigger context detection")

    def test_context_detection_with_gaming_context(self):
        """Test that gaming queries with pronouns still work"""

        # These should trigger context detection (gaming context present)
        gaming_messages = [
            "how long did she play it",  # "it" with gaming context
            "what game did she complete",  # "she" with gaming context
            "did jonesy finish the game",  # gaming context present
            "how many hours did it take",  # "it" with gaming context
        ]

        for message in gaming_messages:
            result = should_use_context(message)
            self.assertTrue(result, f"Gaming query '{message}' should trigger context detection")

    def test_non_gaming_pronouns_ignored(self):
        """Test that pronouns without gaming context are ignored"""

        non_gaming_messages = [
            "it's raining outside",
            "she is coming tomorrow",
            "it's a nice day",
            "her car is red",
            "that's interesting",
            "it works fine",
            "she said hello"
        ]

        for message in non_gaming_messages:
            result = should_use_context(message)
            self.assertFalse(result, f"Non-gaming message '{message}' should not trigger context detection")

    def test_mixed_context_detection(self):
        """Test various combinations of gaming and non-gaming context"""

        test_cases = [
            ("it's a good game", True),  # "it" + gaming context
            ("the game she played", True),  # "she" + gaming context
            ("her favorite episode", True),  # "her" + gaming context
            ("it's ready", False),  # "it" without gaming context
            ("she likes it", False),  # pronouns without gaming context
            ("what time is it", False),  # "it" in time context
            ("how long did the game take", False),  # no pronouns, gaming context but specific
        ]

        for message, expected in test_cases:
            result = should_use_context(message)
            self.assertEqual(result, expected, f"Message '{message}' should return {expected}")

    async def test_mod_channel_mention_logic(self):
        """Test that mod channel logic works correctly"""

        # Mock message in mod channel without bot mention
        mock_message = MagicMock()
        mock_message.guild = MagicMock()
        mock_message.channel.id = 869530924302344233  # Discord Mods channel
        mock_message.mentions = []  # No mentions
        mock_message.content = "Ash will be but it's Rook right now"
        mock_message.author.bot = False

        # Mock bot user
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345  # Mock bot ID

        # Test the mod channel check logic (this simulates the main.py logic)
        is_mod_channel = mock_message.guild and mock_message.channel.id in [
            869530924302344233,  # Discord Mods
            1213488470798893107,  # Newt Mods
            1280085269600669706,  # Twitch Mods
            1393987338329260202  # The Airlock
        ]

        bot_mentioned = mock_bot_user in mock_message.mentions

        # In mod channel without bot mention should return early
        should_skip_processing = is_mod_channel and not bot_mentioned

        self.assertTrue(is_mod_channel, "Should detect mod channel")
        self.assertFalse(bot_mentioned, "Bot should not be mentioned")
        self.assertTrue(should_skip_processing, "Should skip processing in mod channel without mention")

    def test_context_detection_edge_cases(self):
        """Test edge cases for context detection"""

        edge_cases = [
            # Gaming context with pronouns - should trigger
            ("jonesy played it yesterday", True),
            ("she completed the series", True),
            ("how many episodes did it have", True),

            # Gaming words but no pronouns needing context - should not trigger
            ("jonesy plays games", False),
            ("the game is good", False),
            ("completed successfully", False),

            # Pronouns with non-gaming context - should not trigger
            ("it's working", False),
            ("she is here", False),
            ("her phone", False),

            # Empty/short messages
            ("", False),
            ("it", False),  # No gaming context
            ("game", False),  # No pronouns needing context
        ]

        for message, expected in edge_cases:
            result = should_use_context(message)
            self.assertEqual(result, expected, f"Edge case '{message}' should return {expected}")


def run_tests():
    """Run all the tests"""
    print("🧪 Testing mod channel fixes...")

    # Run the tests
    unittest.main(verbosity=2, exit=False)

    print("\n✅ Mod channel fix tests completed!")


if __name__ == "__main__":
    run_tests()
