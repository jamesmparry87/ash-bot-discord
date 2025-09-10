"""
Tests for AI integration and response handling.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add the Live directory to sys.path
live_path = os.path.join(os.path.dirname(__file__), "..", "Live")
if live_path not in sys.path:
    sys.path.insert(0, live_path)

# Try to import bot module - use type: ignore for testing environments
try:
    import ash_bot_fallback  # type: ignore
except ImportError:
    # Create a mock module for type checking
    class MockBotModule:  # type: ignore
        @staticmethod
        async def setup_ai_provider(provider, api_key, module, available):
            pass

        @staticmethod
        def filter_ai_response(response):
            return response

        @staticmethod
        async def on_message(message):
            pass

        # Add other mock attributes as needed
        ai_enabled = False
        primary_ai = "gemini"
        backup_ai = "claude"
        gemini_model = None
        claude_client = None
        BOT_PERSONA = {"enabled": True}
        JONESY_USER_ID = 123456
        JAM_USER_ID = 789012
        bot = None

    ash_bot_fallback = MockBotModule()  # type: ignore


class TestAIResponseFiltering:
    """Test AI response filtering and processing."""

    def test_filter_ai_response_basic(self):
        """Test basic response filtering."""
        import ash_bot_fallback  # type: ignore

        response = "This is a test response. It has multiple sentences. Some are repetitive. Some are repetitive."
        filtered = ash_bot_fallback.filter_ai_response(response)

        # Should remove duplicate sentences
        assert filtered.count("Some are repetitive") == 1

    def test_filter_ai_response_length_limit(self):
        """Test response length limiting."""
        import ash_bot_fallback  # type: ignore

        # Create a response with many sentences
        sentences = [f"This is sentence {i}." for i in range(10)]
        long_response = " ".join(sentences)

        filtered = ash_bot_fallback.filter_ai_response(long_response)

        # Should limit to maximum 4 sentences
        sentence_count = len([s for s in filtered.split(".") if s.strip()])
        assert sentence_count <= 4


class TestAIIntegration:
    """Test essential AI integration functionality."""

    @pytest.mark.asyncio
    async def test_ai_response_generation(self, mock_discord_message):
        """Test basic AI response generation."""
        import ash_bot_fallback  # type: ignore

        # Mock bot user and setup
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> What is your purpose?"
        mock_discord_message.author.id = 123456789

        # Mock AI response
        mock_response = MagicMock()
        mock_response.text = "I am Science Officer Ash. My purpose is to assist."

        with patch("ash_bot_fallback.bot") as mock_bot:
            mock_bot.user = mock_bot_user

            with patch("ash_bot_fallback.ai_enabled", True):
                with patch("ash_bot_fallback.BOT_PERSONA", {"enabled": True, "personality": "Test persona"}):
                    with patch("ash_bot_fallback.primary_ai", "gemini"):
                        with patch("ash_bot_fallback.backup_ai", "claude"):
                            with patch("ash_bot_fallback.gemini_model") as mock_gemini:
                                mock_gemini.generate_content.return_value = mock_response

                                with patch("ash_bot_fallback.bot.process_commands", new=AsyncMock()):
                                    await ash_bot_fallback.on_message(mock_discord_message)

                                    # Verify response was sent (AI may not be called for simple queries)
                                    mock_discord_message.reply.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
