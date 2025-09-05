"""
Tests for AI integration and response handling.
"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os

# Add the Live directory to sys.path
live_path = os.path.join(os.path.dirname(__file__), '..', 'Live')
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
        primary_ai = 'gemini'
        backup_ai = 'claude'
        gemini_model = None
        claude_client = None
        BOT_PERSONA = {'enabled': True}
        JONESY_USER_ID = 123456
        JAM_USER_ID = 789012
        bot = None
        
    ash_bot_fallback = MockBotModule()  # type: ignore


class TestAISetup:
    """Test AI provider setup and configuration."""
    
    @patch('ash_bot_fallback.genai')
    def test_setup_gemini_success(self, mock_genai):
        """Test successful Gemini AI setup."""
        import ash_bot_fallback  # type: ignore
        
        # Mock Gemini model and response
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Test response"
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model
        
        # Test the setup function
        result = ash_bot_fallback.setup_ai_provider(
            "gemini", "test_api_key", mock_genai, True
        )
        
        assert result is True
        mock_genai.configure.assert_called_once_with(api_key="test_api_key")
        mock_genai.GenerativeModel.assert_called_once_with('gemini-1.5-flash')
    
    @patch('ash_bot_fallback.anthropic')
    def test_setup_claude_success(self, mock_anthropic):
        """Test successful Claude AI setup."""
        import ash_bot_fallback  # type: ignore
        
        # Mock Claude client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Test response"
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client
        
        result = ash_bot_fallback.setup_ai_provider(
            "claude", "test_api_key", mock_anthropic, True
        )
        
        assert result is True
        mock_anthropic.Anthropic.assert_called_once_with(api_key="test_api_key")
    
    def test_setup_ai_no_api_key(self):
        """Test AI setup with missing API key."""
        import ash_bot_fallback  # type: ignore
        
        result = ash_bot_fallback.setup_ai_provider(
            "gemini", None, MagicMock(), True
        )
        
        assert result is False
    
    def test_setup_ai_module_unavailable(self):
        """Test AI setup with unavailable module."""
        import ash_bot_fallback  # type: ignore
        
        result = ash_bot_fallback.setup_ai_provider(
            "gemini", "test_key", None, False
        )
        
        assert result is False


class TestAIResponseFiltering:
    """Test AI response filtering and processing."""
    
    def test_filter_ai_response_basic(self):
        """Test basic response filtering."""
        import ash_bot_fallback  # type: ignore
        
        response = "This is a test response. It has multiple sentences. Some are repetitive. Some are repetitive."
        filtered = ash_bot_fallback.filter_ai_response(response)
        
        # Should remove duplicate sentences
        assert filtered.count("Some are repetitive") == 1
    
    def test_filter_ai_response_empty(self):
        """Test filtering empty response."""
        import ash_bot_fallback  # type: ignore
        
        filtered = ash_bot_fallback.filter_ai_response("")
        assert filtered == ""
    
    def test_filter_ai_response_repetitive_phrases(self):
        """Test filtering of repetitive character phrases."""
        import ash_bot_fallback  # type: ignore
        
        response = "You have my sympathies. Fascinating analysis. You have my sympathies again."
        filtered = ash_bot_fallback.filter_ai_response(response)
        
        # Should only keep first instance of repetitive phrases
        assert filtered.count("You have my sympathies") == 1
    
    def test_filter_ai_response_length_limit(self):
        """Test response length limiting."""
        import ash_bot_fallback  # type: ignore
        
        # Create a response with many sentences
        sentences = [f"This is sentence {i}." for i in range(10)]
        long_response = " ".join(sentences)
        
        filtered = ash_bot_fallback.filter_ai_response(long_response)
        
        # Should limit to maximum 4 sentences
        sentence_count = len([s for s in filtered.split('.') if s.strip()])
        assert sentence_count <= 4


class TestAIResponseGeneration:
    """Test AI response generation and handling."""
    
    @pytest.mark.asyncio
    async def test_ai_response_gemini_primary(self, mock_discord_message):
        """Test AI response with Gemini as primary."""
        import ash_bot_fallback  # type: ignore
        
        # Mock bot user and setup
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> Hello"
        mock_discord_message.author.id = 123456789
        
        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = "Hello. I'm Ash. How can I help you?"
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.ai_enabled', True):
                with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                    with patch('ash_bot_fallback.primary_ai', 'gemini'):
                        with patch('ash_bot_fallback.gemini_model') as mock_gemini:
                            mock_gemini.generate_content.return_value = mock_response
                            
                            # Mock process_commands to prevent actual command processing
                            with patch('ash_bot_fallback.bot.process_commands'):
                                await ash_bot_fallback.on_message(mock_discord_message)
                                
                                # Verify Gemini was called
                                mock_gemini.generate_content.assert_called_once()
                                
                                # Verify response was sent
                                mock_discord_message.reply.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ai_response_claude_primary(self, mock_discord_message):
        """Test AI response with Claude as primary."""
        import ash_bot_fallback  # type: ignore
        
        # Mock bot user and setup
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> Hello"
        mock_discord_message.author.id = 123456789
        
        # Mock Claude response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Hello. I'm Ash. How can I help you?"
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.ai_enabled', True):
                with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                    with patch('ash_bot_fallback.primary_ai', 'claude'):
                        with patch('ash_bot_fallback.claude_client') as mock_claude:
                            mock_claude.messages.create.return_value = mock_response
                            
                            with patch('ash_bot_fallback.bot.process_commands'):
                                await ash_bot_fallback.on_message(mock_discord_message)
                                
                                # Verify Claude was called
                                mock_claude.messages.create.assert_called_once()
                                
                                # Verify response was sent
                                mock_discord_message.reply.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ai_response_with_backup(self, mock_discord_message):
        """Test AI response with backup when primary fails."""
        import ash_bot_fallback  # type: ignore
        
        # Mock bot user and setup
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> Hello"
        mock_discord_message.author.id = 123456789
        
        # Mock backup Claude response
        mock_claude_response = MagicMock()
        mock_claude_response.content = [MagicMock()]
        mock_claude_response.content[0].text = "Backup response from Claude"
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.ai_enabled', True):
                with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                    with patch('ash_bot_fallback.primary_ai', 'gemini'):
                        with patch('ash_bot_fallback.backup_ai', 'claude'):
                            with patch('ash_bot_fallback.gemini_model') as mock_gemini:
                                with patch('ash_bot_fallback.claude_client') as mock_claude:
                                    # Make Gemini fail
                                    mock_gemini.generate_content.side_effect = Exception("API Error")
                                    mock_claude.messages.create.return_value = mock_claude_response
                                    
                                    with patch('ash_bot_fallback.bot.process_commands'):
                                        await ash_bot_fallback.on_message(mock_discord_message)
                                        
                                        # Verify primary failed and backup was used
                                        mock_gemini.generate_content.assert_called_once()
                                        mock_claude.messages.create.assert_called_once()
                                        
                                        # Verify response was sent
                                        mock_discord_message.reply.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ai_quota_error_handling(self, mock_discord_message):
        """Test handling of AI quota/rate limit errors."""
        import ash_bot_fallback  # type: ignore
        
        # Mock bot user and setup
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> Hello"
        mock_discord_message.author.id = 123456789
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.ai_enabled', True):
                with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                    with patch('ash_bot_fallback.primary_ai', 'gemini'):
                        with patch('ash_bot_fallback.gemini_model') as mock_gemini:
                            # Simulate quota error
                            mock_gemini.generate_content.side_effect = Exception("quota exceeded")
                            
                            with patch('ash_bot_fallback.bot.process_commands'):
                                await ash_bot_fallback.on_message(mock_discord_message)
                                
                                # Should send busy message for quota errors
                                mock_discord_message.reply.assert_called_once()
                                call_args = mock_discord_message.reply.call_args[0][0]
                                assert "critical diagnostic procedure" in call_args


class TestSpecialUserHandling:
    """Test special handling for Captain Jonesy and Sir Decent Jam."""
    
    @pytest.mark.asyncio
    async def test_captain_jonesy_respectful_response(self, mock_discord_message):
        """Test respectful responses to Captain Jonesy."""
        import ash_bot_fallback  # type: ignore
        
        # Mock Captain Jonesy
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> Hello"
        mock_discord_message.author.id = ash_bot_fallback.JONESY_USER_ID  # Captain Jonesy
        
        # Mock AI response
        mock_response = MagicMock()
        mock_response.text = "Captain Jonesy. Science Officer Ash reporting for duty."
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.ai_enabled', True):
                with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                    with patch('ash_bot_fallback.primary_ai', 'gemini'):
                        with patch('ash_bot_fallback.gemini_model') as mock_gemini:
                            mock_gemini.generate_content.return_value = mock_response
                            
                            with patch('ash_bot_fallback.bot.process_commands'):
                                await ash_bot_fallback.on_message(mock_discord_message)
                                
                                # Verify AI was called with respectful prompt
                                mock_gemini.generate_content.assert_called_once()
                                prompt_used = mock_gemini.generate_content.call_args[0][0]
                                assert "Captain Jonesy" in prompt_used
                                assert "commanding officer" in prompt_used
    
    @pytest.mark.asyncio
    async def test_sir_decent_jam_creator_response(self, mock_discord_message):
        """Test respectful responses to Sir Decent Jam (creator)."""
        import ash_bot_fallback  # type: ignore
        
        # Mock Sir Decent Jam
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> Hello"
        mock_discord_message.author.id = ash_bot_fallback.JAM_USER_ID  # Sir Decent Jam
        
        # Mock AI response
        mock_response = MagicMock()
        mock_response.text = "Sir Decent Jam. Your creation acknowledges you."
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.ai_enabled', True):
                with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                    with patch('ash_bot_fallback.primary_ai', 'gemini'):
                        with patch('ash_bot_fallback.gemini_model') as mock_gemini:
                            mock_gemini.generate_content.return_value = mock_response
                            
                            with patch('ash_bot_fallback.bot.process_commands'):
                                await ash_bot_fallback.on_message(mock_discord_message)
                                
                                # Verify AI was called with creator-respectful prompt
                                mock_gemini.generate_content.assert_called_once()
                                prompt_used = mock_gemini.generate_content.call_args[0][0]
                                assert "Sir Decent Jam" in prompt_used
                                assert "creator" in prompt_used


class TestFAQResponses:
    """Test FAQ response handling."""
    
    @pytest.mark.asyncio
    async def test_simple_faq_response(self, mock_discord_message):
        """Test simple FAQ responses."""
        import ash_bot_fallback  # type: ignore
        
        # Mock bot user and setup
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> hello"
        mock_discord_message.author.id = 123456789
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                with patch('ash_bot_fallback.bot.process_commands'):
                    await ash_bot_fallback.on_message(mock_discord_message)
                    
                    # Should send simple FAQ response without calling AI
                    mock_discord_message.reply.assert_called_once()
                    call_args = mock_discord_message.reply.call_args[0][0]
                    assert "Science Officer Ash" in call_args
    
    @pytest.mark.asyncio
    async def test_faq_response_captain_jonesy(self, mock_discord_message):
        """Test FAQ responses to Captain Jonesy."""
        import ash_bot_fallback  # type: ignore
        
        # Mock Captain Jonesy
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> hello"
        mock_discord_message.author.id = ash_bot_fallback.JONESY_USER_ID
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                with patch('ash_bot_fallback.bot.process_commands'):
                    await ash_bot_fallback.on_message(mock_discord_message)
                    
                    # Should send respectful FAQ response to Captain
                    mock_discord_message.reply.assert_called_once()
                    call_args = mock_discord_message.reply.call_args[0][0]
                    assert "Captain Jonesy" in call_args
                    assert "reporting for duty" in call_args


class TestContextInjection:
    """Test AI context injection and database integration."""
    
    @pytest.mark.asyncio
    async def test_game_query_context_injection(self, mock_discord_message, mock_db):
        """Test context injection for game-related queries."""
        import ash_bot_fallback  # type: ignore
        
        # Mock bot user and game-related query
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> what games has jonesy played"
        mock_discord_message.author.id = 123456789
        
        # Mock database stats
        mock_db.get_played_games_stats.return_value = {
            'total_games': 50,
            'total_episodes': 500,
            'total_playtime_hours': 250
        }
        mock_db.get_random_played_games.return_value = [
            {'canonical_name': 'Test Game 1'},
            {'canonical_name': 'Test Game 2'}
        ]
        
        # Mock AI response
        mock_response = MagicMock()
        mock_response.text = "Captain Jonesy has played many games including Test Game 1 and Test Game 2."
        
        with patch('ash_bot_fallback.bot') as mock_bot:
            mock_bot.user = mock_bot_user
            
            with patch('ash_bot_fallback.db', mock_db):
                with patch('ash_bot_fallback.ai_enabled', True):
                    with patch('ash_bot_fallback.BOT_PERSONA', {'enabled': True}):
                        with patch('ash_bot_fallback.primary_ai', 'gemini'):
                            with patch('ash_bot_fallback.gemini_model') as mock_gemini:
                                mock_gemini.generate_content.return_value = mock_response
                                
                                with patch('ash_bot_fallback.bot.process_commands'):
                                    await ash_bot_fallback.on_message(mock_discord_message)
                                    
                                    # Verify database stats were queried for context
                                    mock_db.get_played_games_stats.assert_called_once()
                                    mock_db.get_random_played_games.assert_called_once()
                                    
                                    # Verify context was injected into AI prompt
                                    mock_gemini.generate_content.assert_called_once()
                                    prompt_used = mock_gemini.generate_content.call_args[0][0]
                                    assert "50 games total" in prompt_used


if __name__ == '__main__':
    pytest.main([__file__])
