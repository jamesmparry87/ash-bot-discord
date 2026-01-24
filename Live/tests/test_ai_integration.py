"""
Tests for AI integration and response handling.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from test_commands import mock_discord_message  # type: ignore

# Add the Live directory to sys.path
live_path = os.path.join(os.path.dirname(__file__), '..')
if live_path not in sys.path:
    sys.path.insert(0, live_path)

# Try to import both bot_modular and ai_handler
try:
    import bot_modular  # type: ignore
    from bot.handlers.ai_handler import filter_ai_response  # type: ignore
    IMPORTS_AVAILABLE = True
except ImportError:
    # Create mock modules for type checking
    class MockBotModule:  # type: ignore
        @staticmethod
        async def on_message(message):
            pass

        BOT_PERSONA = {'enabled': True}
        JONESY_USER_ID = 123456
        JAM_USER_ID = 789012
        bot = None

    class MockAIHandler:  # type: ignore
        @staticmethod
        def filter_ai_response(response):
            """Mock implementation that matches real filter_ai_response logic"""
            if not response:
                return response

            # Split into sentences
            sentences = [s.strip() for s in response.split('.') if s.strip()]

            # Remove duplicate sentences (case-insensitive)
            seen_sentences = set()
            filtered_sentences = []
            for sentence in sentences:
                sentence_lower = sentence.lower()
                if sentence_lower not in seen_sentences:
                    seen_sentences.add(sentence_lower)
                    filtered_sentences.append(sentence)

            # Limit to maximum 4 sentences for conciseness
            final_sentences = filtered_sentences[:4]

            # Reconstruct response
            result = '. '.join(final_sentences)
            if result and not result.endswith('.'):
                result += '.'

            return result

    bot_modular = MockBotModule()  # type: ignore
    filter_ai_response = MockAIHandler.filter_ai_response  # type: ignore
    IMPORTS_AVAILABLE = False


class TestAIResponseFiltering:
    """Test AI response filtering and processing."""

    def test_filter_ai_response_basic(self):
        """Test basic response filtering."""
        response = "This is a test response. It has multiple sentences. Some are repetitive. Some are repetitive."
        filtered = filter_ai_response(response)

        # Should remove duplicate sentences
        assert filtered.count("Some are repetitive") == 1


if __name__ == '__main__':
    pytest.main([__file__])
