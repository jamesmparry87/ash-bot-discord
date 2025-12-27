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
live_path = os.path.join(os.path.dirname(__file__), '..', 'Live')
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
            return response

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

    def test_filter_ai_response_length_limit(self):
        """Test response length limiting."""
        # Create a response with many sentences
        sentences = [f"This is sentence {i}." for i in range(10)]
        long_response = " ".join(sentences)

        filtered = filter_ai_response(long_response)

        # Should limit to maximum 4 sentences
        sentence_count = len([s for s in filtered.split('.') if s.strip()])
        assert sentence_count <= 4

        @pytest.mark.asyncio
        async def test_ai_response_generation(self, mock_discord_message):
            """Test basic AI response generation."""
            # Mock bot user and setup
            mock_bot_user = MagicMock()
            mock_bot_user.id = 12345
            mock_discord_message.mentions = [mock_bot_user]
            mock_discord_message.content = f"<@{mock_bot_user.id}> What is your purpose?"
            mock_discord_message.author.id = 123456789

            # Mock AI response
            mock_response = MagicMock()
            mock_response.text = "I am Science Officer Ash. My purpose is to assist."

            with patch('bot_modular.bot') as mock_bot:
                mock_bot.user = mock_bot_user

                # Mock the ai_handler module functions
                with patch("bot.handlers.ai_handler.ai_enabled", True):
                    with patch("bot_modular.BOT_PERSONA", {"enabled": True, "personality": "Test persona"}):
                        with patch("bot.handlers.ai_handler.primary_ai", "gemini"):
                            with patch("bot.handlers.ai_handler.backup_ai", "huggingface"):
                                with patch("bot.handlers.ai_handler.gemini_model") as mock_gemini:
                                    mock_gemini.generate_content.return_value = mock_response

                                    with patch("bot_modular.bot.process_commands", new=AsyncMock()):
                                        await bot_modular.on_message(mock_discord_message)

                                        # Verify response was sent
                                        mock_discord_message.reply.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__])
