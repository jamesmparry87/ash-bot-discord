"""
Pytest configuration and fixtures for Discord bot testing.
"""
import asyncio
import os
import sys
from typing import Any, AsyncGenerator, Dict, Generator, List, Union
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add the Live directory to sys.path so we can import our modules
live_path = os.path.join(os.path.dirname(__file__), '..', 'Live')
if live_path not in sys.path:
    sys.path.insert(0, live_path)

# Import our modules after path setup
try:
    import discord
    from database import DatabaseManager  # type: ignore
    from discord.ext import commands
except ImportError as e:
    print(f"Warning: Could not import modules: {e}")
    # Create mock types for when imports fail
    DatabaseManager = type('DatabaseManager', (), {})  # type: ignore
    discord = MagicMock()  # type: ignore
    commands = MagicMock()  # type: ignore
    discord.Intents = MagicMock
    discord.Message = MagicMock  
    discord.Member = MagicMock
    commands.Bot = MagicMock
    commands.Context = MagicMock

# Test environment variables
TEST_ENV_VARS = {
    'DISCORD_TOKEN': 'test_discord_token',
    'DATABASE_URL': 'postgresql://test:test@localhost/test_discord_bot',
    'GOOGLE_API_KEY': 'test_google_api_key',
    'ANTHROPIC_API_KEY': 'test_anthropic_api_key',
    'YOUTUBE_API_KEY': 'test_youtube_api_key',
    'TWITCH_CLIENT_ID': 'test_twitch_client_id',
    'TWITCH_CLIENT_SECRET': 'test_twitch_client_secret',
}

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables for all tests."""
    for key, value in TEST_ENV_VARS.items():
        monkeypatch.setenv(key, value)

@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database manager for testing."""
    db = MagicMock(spec=DatabaseManager)
    
    # Mock connection methods
    db.get_connection.return_value = MagicMock()
    db.init_database.return_value = None
    
    # Mock user strikes methods
    db.get_user_strikes.return_value = 0
    db.set_user_strikes.return_value = None
    db.add_user_strike.return_value = 1
    db.get_all_strikes.return_value = {}
    
    # Mock game recommendation methods
    db.add_game_recommendation.return_value = True
    db.get_all_games.return_value = []
    db.remove_game_by_id.return_value = {"id": 1, "name": "Test Game", "reason": "Test"}
    db.remove_game_by_name.return_value = {"id": 1, "name": "Test Game", "reason": "Test"}
    db.game_exists.return_value = False
    
    # Mock played games methods
    db.get_played_game.return_value = None
    db.get_all_played_games.return_value = []
    db.add_played_game.return_value = True
    db.update_played_game.return_value = True
    db.remove_played_game.return_value = {'id': 1, 'canonical_name': 'Test Game'}
    db.search_played_games.return_value = []
    
    # Mock config methods
    db.get_config_value.return_value = None
    db.set_config_value.return_value = None
    
    return db

@pytest.fixture
async def mock_discord_bot() -> AsyncGenerator[Union[MagicMock, Any], None]:
    """Create a mock Discord bot for testing."""
    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    intents.message_content = True
    
    bot = MagicMock(spec=commands.Bot)
    bot.intents = intents
    bot.user = MagicMock()
    bot.user.id = 12345
    bot.user.name = "TestBot"
    bot.get_guild.return_value = MagicMock()
    
    # Mock channels with async methods
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_channel.fetch_message = AsyncMock()
    mock_channel.edit = AsyncMock()
    bot.get_channel.return_value = mock_channel
    
    # Mock fetch_user as AsyncMock
    bot.fetch_user = AsyncMock()
    bot.process_commands = AsyncMock()
    
    yield bot

@pytest.fixture
def mock_discord_context() -> MagicMock:
    """Create a mock Discord command context."""
    ctx = MagicMock(spec=commands.Context)
    
    # Mock author
    ctx.author = MagicMock()
    ctx.author.id = 123456789
    ctx.author.name = "TestUser"
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.manage_messages = True
    
    # Mock guild and channel
    ctx.guild = MagicMock()
    ctx.guild.id = 869525857562161182  # Same as production for testing
    
    # Mock channel with async send method
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_channel.fetch_message = AsyncMock()
    ctx.guild.get_channel.return_value = mock_channel
    
    ctx.channel = MagicMock()
    ctx.channel.id = 123456789
    ctx.channel.send = AsyncMock()
    
    # Mock send method
    ctx.send = AsyncMock()
    
    return ctx

@pytest.fixture
def mock_discord_message() -> MagicMock:
    """Create a mock Discord message."""
    message = MagicMock(spec=discord.Message)
    
    # Mock author
    message.author = MagicMock()
    message.author.id = 123456789
    message.author.name = "TestUser"
    message.author.bot = False
    
    # Mock guild and channel
    message.guild = MagicMock()
    message.guild.id = 869525857562161182
    
    message.channel = MagicMock()
    message.channel.id = 123456789
    
    # Create async iterator mock for history()
    class MockAsyncIterator:
        def __init__(self, items):
            self.items = items
            self.index = 0
            
        def __aiter__(self):
            return self
            
        async def __anext__(self):
            if self.index >= len(self.items):
                raise StopAsyncIteration
            item = self.items[self.index]
            self.index += 1
            return item
    
    # Mock history to return async iterator
    mock_history_messages = []  # Empty history for tests
    message.channel.history = MagicMock(return_value=MockAsyncIterator(mock_history_messages))

    # Create proper async context manager mock for typing()
    typing_context = AsyncMock()
    typing_context.__aenter__ = AsyncMock(return_value=typing_context)
    typing_context.__aexit__ = AsyncMock(return_value=None)
    message.channel.typing = MagicMock(return_value=typing_context)
    
    # Mock content and methods
    message.content = "Test message"
    message.mentions = []
    message.reply = AsyncMock()
    
    return message

@pytest.fixture
def mock_discord_user() -> MagicMock:
    """Create a mock Discord user/member."""
    user = MagicMock(spec=discord.Member)
    user.id = 123456789
    user.name = "TestUser"
    user.display_name = "TestUser"
    user.mention = "<@123456789>"
    user.guild_permissions = MagicMock()
    user.guild_permissions.manage_messages = True
    
    return user

@pytest.fixture
def sample_game_data() -> Dict[str, Any]:
    """Sample game data for testing."""
    return {
        'id': 1,
        'canonical_name': 'Test Game',
        'alternative_names': ['TG', 'Test'],
        'series_name': 'Test Series',
        'genre': 'Action',
        'release_year': 2023,
        'platform': 'PC',
        'first_played_date': '2023-01-01',
        'completion_status': 'completed',
        'total_episodes': 10,
        'total_playtime_minutes': 600,
        'youtube_playlist_url': 'https://youtube.com/playlist?list=test',
        'twitch_vod_urls': ['https://twitch.tv/videos/123'],
        'notes': 'Test game notes',
        'created_at': '2023-01-01T00:00:00',
        'updated_at': '2023-01-01T00:00:00'
    }

@pytest.fixture
def sample_recommendation_data() -> Dict[str, Any]:
    """Sample recommendation data for testing."""
    return {
        'id': 1,
        'name': 'Test Recommendation',
        'reason': 'Great game for testing',
        'added_by': 'TestUser',
        'created_at': '2023-01-01T00:00:00'
    }

@pytest.fixture
def sample_strike_data() -> Dict[int, int]:
    """Sample strike data for testing."""
    return {
        123456789: 1,
        987654321: 2,
        555555555: 3
    }

# Mock AI responses
@pytest.fixture
def mock_ai_responses() -> Dict[str, Dict[str, Any]]:
    """Mock AI response data for testing."""
    return {
        "gemini_response": {"text": "Test Gemini response from Science Officer Ash.", "safety_ratings": []},
        "claude_response": {
            "content": [{"text": "Test Claude response from Science Officer Ash."}],
            "stop_reason": "end_turn",
        },
        'claude_response': {
            'content': [{'text': 'Test Claude response from Science Officer Ash.'}],
            'stop_reason': 'end_turn'
        }
    }

# Mock API responses
@pytest.fixture
def mock_youtube_api_response() -> Dict[str, List[Dict[str, Any]]]:
    """Mock YouTube API response."""
    return {
        'items': [
            {
                "id": "test_playlist_id",
                "snippet": {"title": "Test Game Playlist", "description": "Test game playlist description"},
                "contentDetails": {"itemCount": 5},
            }
        ]
    }

@pytest.fixture
def mock_twitch_api_response() -> Dict[str, List[Dict[str, Any]]]:
    """Mock Twitch API response."""
    return {
        'data': [
            {
                'id': '123456',
                'title': 'Test Game Stream',
                'created_at': '2023-01-01T00:00:00Z',
                'url': 'https://twitch.tv/videos/123456',
                'duration': '1h30m45s'
            }
        ]
    }

@pytest.fixture
async def clean_database() -> AsyncGenerator[None, None]:
    """Fixture to ensure clean database state for tests that need it."""
    # This would be used for integration tests with a real test database
    # For now, it's a placeholder for future database integration tests
    yield
    # Cleanup would happen here
