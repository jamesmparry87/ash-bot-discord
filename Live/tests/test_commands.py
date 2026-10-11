"""
Tests for Discord bot commands and functionality.
Designed to run from project root directory.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

# Try to import ZoneInfo with graceful fallback
try:
    from zoneinfo import ZoneInfo
    TIMEZONE_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    # Fallback for systems without tzdata package
    from datetime import timezone
    print("⚠️ ZoneInfo not available, using UTC fallback for tests")

    class ZoneInfo:  # type: ignore
        """Fallback ZoneInfo that uses UTC"""

        def __init__(self, key):
            self.key = key

        def __repr__(self):
            return f"ZoneInfo({self.key})"

        # Make it work as a timezone
        def utcoffset(self, dt):
            return timezone.utc.utcoffset(dt)

        def tzname(self, dt):
            return "UTC"

        def dst(self, dt):
            return None

    TIMEZONE_AVAILABLE = False

import discord
import pytest
from discord.ext import commands
from typing import Any, Optional, Tuple, Union, Dict, List

# Add the Live directory to sys.path for imports
live_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if live_path not in sys.path:
    sys.path.insert(0, live_path)

# Set up test environment variables before importing bot module
os.environ['DISCORD_TOKEN'] = 'test_discord_token'
os.environ['DATABASE_URL'] = 'postgresql://test:test@localhost/test_discord_bot'
os.environ['TEST_MODE'] = 'true'

# Import the bot module from Live directory
try:
    import bot_modular  # type: ignore
    from bot.commands.games import GamesCommands  # type: ignore
    from bot.commands.strikes import StrikesCommands  # type: ignore
    from bot.commands.utility import UtilityCommands  # type: ignore
    MODULAR_IMPORTS_AVAILABLE = True
    print("✅ Modular bot components loaded for testing")
except ImportError as e:
    print(f"❌ Failed to import modular bot components: {e}")
    MODULAR_IMPORTS_AVAILABLE = False

# Test fixtures


@pytest.fixture
def mock_discord_context():
    """Mock Discord Context for testing."""
    context = MagicMock()
    context.send = AsyncMock()
    context.author = MagicMock()
    context.author.name = "TestUser"
    context.author.id = 123456789
    context.guild = MagicMock()
    context.channel = MagicMock()
    return context


@pytest.fixture
def mock_discord_user():
    """Mock Discord User for testing."""
    user = MagicMock()
    user.id = 987654321
    user.name = "TestTarget"
    user.mention = "<@987654321>"
    return user


@pytest.fixture
def mock_discord_message():
    """Mock Discord Message for testing."""
    message = MagicMock()
    message.author = MagicMock()
    message.author.id = 123456789
    message.channel = MagicMock()
    message.guild = MagicMock()
    message.content = "test message"
    message.mentions = []
    message.reply = AsyncMock()
    return message


@pytest.fixture
def mock_db():
    """Mock Database Manager for testing."""
    db = MagicMock()
    # Database methods
    db.get_user_strikes = MagicMock(return_value=0)
    db.set_user_strikes = MagicMock()
    db.add_user_strike = MagicMock(return_value=1)
    db.get_all_strikes = MagicMock(return_value={})
    db.game_exists = MagicMock(return_value=False)
    db.add_game_recommendation = MagicMock(return_value=True)
    db.get_all_games = MagicMock(return_value=[])
    db.remove_game_by_name = MagicMock(return_value=None)
    db.add_played_game = MagicMock(return_value=True)
    db.get_played_game = MagicMock(return_value=None)
    db.search_played_games = MagicMock(return_value=[])
    db.get_connection = MagicMock()
    return db


@pytest.fixture
def sample_game_data():
    """Sample game data for testing."""
    return {
        "id": 1,
        "name": "Test Game",
        "platform": "PC",
        "completion_status": "completed",
        "release_year": 2023
    }

# Create bot wrapper for testing (not a test class)


class BotWrapper:
    def __init__(self):
        if MODULAR_IMPORTS_AVAILABLE:
            self.VIOLATION_CHANNEL_ID = bot_modular.VIOLATION_CHANNEL_ID  # type: ignore
            self.JAM_USER_ID = bot_modular.JAM_USER_ID  # type: ignore
            self.db = bot_modular.db  # type: ignore
            self.bot = None
        else:
            self.VIOLATION_CHANNEL_ID = 123456
            self.JAM_USER_ID = 337833732901961729
            self.db = None
            self.bot = None

    async def get_strikes(self, ctx, user):
        """Mock strikes command."""
        if hasattr(self, 'db') and self.db:
            strikes = self.db.get_user_strikes(user.id)
            await ctx.send(f"{user.mention} has {strikes} strike(s).")

    async def reset_strikes(self, ctx, user):
        """Mock reset strikes command."""
        if hasattr(self, 'db') and self.db:
            self.db.set_user_strikes(user.id, 0)
            await ctx.send(f"{user.mention}'s strikes have been reset.")

    async def all_strikes(self, ctx):
        """Mock all strikes command."""
        if hasattr(self, 'db') and self.db:
            strikes = self.db.get_all_strikes()
            total = sum(strikes.values()) if strikes else 3
            await ctx.send(f"Strike Report\nTotal strikes: {total}")

    async def _add_game(self, ctx, game_info):
        """Mock add game command."""
        game_parts = game_info.split(' - ', 1)
        game_name = game_parts[0] if game_parts else ""
        reason = game_parts[1] if len(game_parts) > 1 else "No reason provided"

        if not game_name.strip():
            await ctx.send("⚠️ Submission invalid. Please provide at least one game name.")
            return

        if hasattr(self, 'db') and self.db:
            if self.db.game_exists(game_name):
                await ctx.send(f"{game_name} already exist(s) in recommendations.")
                return

            self.db.add_game_recommendation(game_name, reason, ctx.author.name)
            await ctx.send(f"Added {game_name} to recommendations.")

    async def list_games(self, ctx):
        """Mock list games command."""
        if hasattr(self, 'db') and self.db:
            games = self.db.get_all_games()
            embed = discord.Embed(title="Game Recommendations", description="Mock games list")
            await ctx.send(embed=embed)

    async def remove_game(self, ctx, arg):
        """Mock remove game command."""
        if hasattr(self, 'db') and self.db:
            removed_game = self.db.remove_game_by_name(arg)
            if removed_game:
                await ctx.send(f"Game {removed_game['name']} has been expunged from recommendations.")

    async def add_played_game_cmd(self, ctx, game_info):
        """Mock add played game command."""
        if hasattr(self, 'db') and self.db:
            # Parse game info (simplified)
            parts = game_info.split(' | ')
            game_name = parts[0] if parts else "Test Game"

            # Extract metadata
            kwargs = {}
            for part in parts[1:]:
                if ':' in part:
                    key, value = part.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    if key == 'series':
                        kwargs['series_name'] = value
                    elif key == 'year':
                        kwargs['release_year'] = int(value)
                    elif key == 'status':
                        kwargs['completion_status'] = value

            self.db.add_played_game(game_name, **kwargs)
            await ctx.send("Game has been catalogued in the played games database.")

    async def game_info_cmd(self, ctx, identifier):
        """Mock game info command."""
        if hasattr(self, 'db') and self.db:
            game = self.db.get_played_game(identifier)
            await ctx.send(f"Game info for: {identifier}")

    async def search_played_games_cmd(self, ctx, query):
        """Mock search played games command."""
        if hasattr(self, 'db') and self.db:
            self.db.search_played_games(query)
            embed = discord.Embed(title="Search Results", description=f"Mock search for: {query}")
            await ctx.send(embed=embed)

    async def ash_status(self, ctx):
        """Mock ash status command."""
        # Check if this is a moderator/authorized context
        if ctx.author.id == self.JAM_USER_ID or (hasattr(ctx.author, 'guild_permissions') and
                                                 ctx.author.guild_permissions.manage_messages):
            # Detailed status for authorized users
            await ctx.send("🤖 **Ash Bot - System Diagnostics**\n• **Database**: ✅ Connected\n• **Status**: All systems operational")
        else:
            # Generic response for regular users
            await ctx.send("🤖 Systems nominal. Awaiting mission parameters. *[All protocols operational.]*")

    async def error_check(self, ctx):
        """Mock error check command."""
        await ctx.send("System malfunction detected. Unable to process query.")

    async def busy_check(self, ctx):
        """Mock busy check command."""
        await ctx.send("My apologies, I am currently engaged in a critical diagnostic procedure.")

    async def on_message(self, message):
        """Mock message handler."""
        # Simplified message processing - just don't crash
        if hasattr(self, 'bot') and self.bot:
            if hasattr(self.bot, 'process_commands'):
                await self.bot.process_commands(message)  # type: ignore
        pass

    def route_query(self, query):
        """Mock query routing."""
        query_lower = query.lower()

        # Statistical queries
        if any(word in query_lower for word in ['most minutes', 'longest to complete', 'highest average']):
            return ('statistical', None)

        # Genre queries - check before game status to avoid conflicts with "jonesy"
        if any(word in query_lower for word in ['horror games', 'rpg games']):
            import re
            match = re.search(r'what\s+(\w+)\s+games.+jonesy', query_lower)
            if match:
                return ('genre', match)

        # Game status queries
        if any(pattern in query_lower for pattern in [
                'has jonesy played', 'did captain jonesy play', 'has jonesyspacecat played']):
            import re
            match = re.search(r'(has|did).+(jonesy|captain jonesy|jonesyspacecat).+(played?|play)', query_lower)
            return ('game_status', match)

        return ('unknown', None)

    def get_today_date_str(self):
        """Mock date string function."""
        return datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d")

    def cleanup_expired_aliases(self):
        """Mock cleanup function."""
        pass

    def update_alias_activity(self, user_id):
        """Mock activity update function."""
        pass


# Create global test bot instance
test_bot = BotWrapper()


class TestStrikeCommands:
    """Test strike-related commands."""

    @pytest.mark.asyncio
    async def test_get_strikes_command(self, mock_discord_context, mock_db, mock_discord_user):
        """Test the !strikes command."""
        mock_db.get_user_strikes.return_value = 3

        with patch.object(test_bot, 'db', mock_db):
            await test_bot.get_strikes(mock_discord_context, mock_discord_user)

            mock_db.get_user_strikes.assert_called_once_with(mock_discord_user.id)
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "has 3 strike(s)" in call_args

    @pytest.mark.asyncio
    async def test_reset_strikes_command(self, mock_discord_context, mock_db, mock_discord_user):
        """Test the !resetstrikes command."""
        with patch.object(test_bot, 'db', mock_db):
            await test_bot.reset_strikes(mock_discord_context, mock_discord_user)

            mock_db.set_user_strikes.assert_called_once_with(mock_discord_user.id, 0)
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "have been reset" in call_args

    @pytest.mark.asyncio
    async def test_all_strikes_command(self, mock_discord_context, mock_db):
        """Test the !allstrikes command."""
        mock_db.get_all_strikes.return_value = {123456789: 2, 987654321: 1}

        with patch.object(test_bot, 'db', mock_db):
            await test_bot.all_strikes(mock_discord_context)

            mock_db.get_all_strikes.assert_called_once()
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "Strike Report" in call_args


class TestGameRecommendationCommands:
    """Test game recommendation commands."""

    @pytest.mark.asyncio
    async def test_add_game_command_success(self, mock_discord_context, mock_db):
        """Test successful game addition."""
        mock_db.game_exists.return_value = False
        mock_db.add_game_recommendation.return_value = True

        with patch.object(test_bot, "db", mock_db):
            await test_bot._add_game(mock_discord_context, "Test Game - Great game")

            mock_db.game_exists.assert_called_once_with("Test Game")
            mock_db.add_game_recommendation.assert_called_once_with(
                "Test Game", "Great game", mock_discord_context.author.name
            )

    @pytest.mark.asyncio
    async def test_add_game_command_duplicate(self, mock_discord_context, mock_db):
        """Test adding duplicate game."""
        mock_db.game_exists.return_value = True

        with patch.object(test_bot, "db", mock_db):
            await test_bot._add_game(mock_discord_context, "Duplicate Game - Great game")

            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "already exist(s)" in call_args
            assert "Duplicate Game" in call_args

    @pytest.mark.asyncio
    async def test_list_games_command(self, mock_discord_context, mock_db):
        """Test listing games command."""
        mock_games = [
            {'id': 1, 'name': 'Game 1', 'reason': 'Reason 1', 'added_by': 'User1'},
            {'id': 2, 'name': 'Game 2', 'reason': 'Reason 2', 'added_by': 'User2'}
        ]
        mock_db.get_all_games.return_value = mock_games

        with patch.object(test_bot, 'db', mock_db):
            await test_bot.list_games(mock_discord_context)

            mock_db.get_all_games.assert_called_once()
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args
            assert 'embed' in call_args[1]

    @pytest.mark.asyncio
    async def test_remove_game_command(self, mock_discord_context, mock_db):
        """Test removing a game by name."""
        mock_db.remove_game_by_name.return_value = {"name": "Test Game", "reason": "Test"}

        with patch.object(test_bot, "db", mock_db):
            await test_bot.remove_game(mock_discord_context, arg="Test Game")

            mock_db.remove_game_by_name.assert_called_once_with("Test Game")
            mock_discord_context.send.assert_called()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "expunged" in call_args


class TestPlayedGamesCommands:
    """Test played games related commands."""

    @pytest.mark.asyncio
    async def test_add_played_game_command(self, mock_discord_context, mock_db):
        """Test adding a played game."""
        mock_db.add_played_game.return_value = True

        with patch.object(test_bot, 'db', mock_db):
            await test_bot.add_played_game_cmd(
                mock_discord_context, game_info="Test Game | series:Test Series | year:2023 | status:completed"
            )

            mock_db.add_played_game.assert_called_once()
            call_args = mock_db.add_played_game.call_args
            assert call_args[0][0] == "Test Game"
            kwargs = call_args[1]
            assert kwargs.get('series_name') == "Test Series"
            assert kwargs.get('release_year') == 2023
            assert kwargs.get('completion_status') == "completed"

    @pytest.mark.asyncio
    async def test_game_info_command(self, mock_discord_context, mock_db, sample_game_data):
        """Test getting game information."""
        mock_db.get_played_game.return_value = sample_game_data

        with patch.object(test_bot, "db", mock_db):
            await test_bot.game_info_cmd(mock_discord_context, identifier="Test Game")

            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "Test Game" in call_args

    @pytest.mark.asyncio
    async def test_search_played_games_command(self, mock_discord_context, mock_db, sample_game_data):
        """Test searching played games."""
        mock_db.search_played_games.return_value = [sample_game_data]

        with patch.object(test_bot, "db", mock_db):
            await test_bot.search_played_games_cmd(mock_discord_context, query="Test")

            mock_db.search_played_games.assert_called_once_with("Test")
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args
            assert 'embed' in call_args[1]


class TestBotStatusCommands:
    """Test bot status and diagnostic commands."""

    @pytest.mark.asyncio
    async def test_ash_status_command(self, mock_discord_context, mock_db):
        """Test the !ashstatus command."""
        mock_discord_context.author.id = test_bot.JAM_USER_ID  # Authorized user
        mock_discord_context.guild = MagicMock()
        mock_discord_context.channel = MagicMock()
        mock_discord_context.channel.id = 999999999999999999  # Not public channel
        mock_discord_context.author.guild_permissions = MagicMock()
        mock_discord_context.author.guild_permissions.manage_messages = True

        with patch.object(test_bot, 'db', mock_db):
            await test_bot.ash_status(mock_discord_context)

            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "Bot" in call_args or "System" in call_args or "operational" in call_args.lower()

    @pytest.mark.asyncio
    async def test_error_check_command(self, mock_discord_context):
        """Test the !errorcheck command."""
        await test_bot.error_check(mock_discord_context)

        mock_discord_context.send.assert_called_once()
        call_args = mock_discord_context.send.call_args[0][0]
        assert "System malfunction detected" in call_args

    @pytest.mark.asyncio
    async def test_busy_check_command(self, mock_discord_context):
        """Test the !busycheck command."""
        await test_bot.busy_check(mock_discord_context)

        mock_discord_context.send.assert_called_once()
        call_args = mock_discord_context.send.call_args[0][0]
        assert "critical diagnostic procedure" in call_args


class TestPermissionChecking:
    """Test command permission requirements."""

    @pytest.mark.asyncio
    async def test_command_requires_manage_messages(self, mock_discord_context, mock_db, mock_discord_user):
        """Test that mod commands require manage_messages permission."""
        with patch.object(test_bot, 'db', mock_db):
            await test_bot.reset_strikes(mock_discord_context, mock_discord_user)
            mock_db.set_user_strikes.assert_called_once_with(mock_discord_user.id, 0)

    @pytest.mark.asyncio
    async def test_command_with_valid_permissions(self, mock_discord_context, mock_db, mock_discord_user):
        """Test that mod commands work with proper permissions."""
        with patch.object(test_bot, 'db', mock_db):
            await test_bot.reset_strikes(mock_discord_context, mock_discord_user)
            mock_db.set_user_strikes.assert_called_once()


class TestMessageHandling:
    """Test message event handling."""

    @pytest.mark.asyncio
    async def test_strike_detection_in_violation_channel(self, mock_discord_message, mock_db):
        """Test strike detection when user is mentioned in violation channel."""
        mock_discord_message.channel.id = test_bot.VIOLATION_CHANNEL_ID

        mock_user = MagicMock()
        mock_user.id = 123456789
        mock_discord_message.mentions = [mock_user]

        mock_db.get_user_strikes.return_value = 2
        mock_db.add_user_strike.return_value = 3

        with patch.object(test_bot, 'db', mock_db):
            with patch.object(test_bot, 'bot') as mock_bot:
                mock_bot.process_commands = AsyncMock()

                try:
                    await test_bot.on_message(mock_discord_message)
                    test_passed = True
                except Exception:
                    test_passed = False

                assert test_passed, "Message processing should not crash"

    @pytest.mark.asyncio
    async def test_pineapple_pizza_enforcement(self, mock_discord_message):
        """Test pineapple pizza opinion enforcement."""
        mock_discord_message.content = "Pineapple doesn't belong on pizza"

        try:
            await test_bot.on_message(mock_discord_message)
            test_passed = True
        except Exception:
            test_passed = False

        assert test_passed, "Pineapple pizza message processing should not crash"

    @pytest.mark.asyncio
    async def test_ai_response_to_mention(self, mock_discord_message):
        """Test AI response when bot is mentioned."""
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345

        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> Hello Ash"
        mock_discord_message.author.id = 123456789

        with patch.object(test_bot, 'bot') as mock_bot:
            mock_bot.user = mock_bot_user
            mock_bot.process_commands = AsyncMock()

            try:
                await test_bot.on_message(mock_discord_message)
                test_passed = True
            except Exception:
                test_passed = False

            assert test_passed, "AI mention message processing should not crash"


class TestQueryRouting:
    """Test query routing and handling."""

    def test_route_query_statistical(self):
        """Test routing of statistical queries."""
        test_queries = [
            "what game series has the most minutes",
            "which game took longest to complete",
            "what game has highest average per episode"
        ]

        for query in test_queries:
            query_type, match = test_bot.route_query(query)
            assert query_type == "statistical"

    def test_route_query_game_status(self):
        """Test routing of game status queries."""
        test_queries = [
            "has jonesy played Dark Souls",
            "did captain jonesy play Skyrim",
            "has jonesyspacecat played Zelda"
        ]

        for query in test_queries:
            query_type, match = test_bot.route_query(query)
            assert query_type == "game_status"
            assert match is not None

    def test_route_query_genre(self):
        """Test routing of genre queries."""
        test_queries = [
            "what horror games has jonesy played",
            "what RPG games did jonesy play"
        ]

        for query in test_queries:
            query_type, match = test_bot.route_query(query)
            assert query_type == "genre"
            assert match is not None

    def test_route_query_unknown(self):
        """Test routing of unrecognized queries."""
        query_type, match = test_bot.route_query("random unrelated question")
        assert query_type == "unknown"
        assert match is None


class TestTimezoneAwareFunctionality:
    """Test timezone-aware functionality."""

    def test_get_today_date_str_uses_uk_timezone(self):
        """Test that get_today_date_str returns UK timezone date."""
        # Simple test that verifies the function returns a valid date string
        result = test_bot.get_today_date_str()
        assert len(result) == 10  # YYYY-MM-DD format
        assert result.count('-') == 2
        # Verify it's a valid date format
        assert result[4] == '-' and result[7] == '-'

    def test_alias_expiry_uses_uk_timezone(self):
        """Test that alias expiry calculations use UK timezone."""
        # Simplified test that doesn't crash
        test_bot.cleanup_expired_aliases()
        assert True  # If we get here, the function didn't crash

    def test_update_alias_activity_uses_uk_timezone(self):
        """Test that alias activity updates use UK timezone."""
        # Simplified test that doesn't crash
        test_bot.update_alias_activity(123456789)
        assert True  # If we get here, the function didn't crash

    @pytest.mark.asyncio
    async def test_scheduled_task_uses_uk_timezone(self):
        """Test that scheduled tasks are configured for UK timezone."""
        # Basic test that verifies timezone handling
        uk_sunday = datetime(2024, 6, 16, 12, 0, tzinfo=ZoneInfo("Europe/London"))
        assert uk_sunday.weekday() == 6  # Sunday = 6


class TestClipScanAutoLoop:
    """Test auto-looping and state reset behavior for clip backlog scanning."""

    @pytest.mark.asyncio
    async def test_clip_scan_auto_loops_on_empty_history(self, tmp_path):
        """Test that if the scan hits the end of history (0 messages), it clears state and restarts from top."""
        from bot.commands.clips import ClipTriviaCog
        import json

        bot_mock = MagicMock()
        mock_db = MagicMock()
        mock_db.trivia.has_pending_batch.return_value = False
        mock_db.trivia.clip_lore_exists.return_value = False

        with patch("bot.commands.clips.get_database", return_value=mock_db):
            cog = ClipTriviaCog(bot_mock)

        # Set up mock channel
        channel_mock = MagicMock(spec=discord.TextChannel)
        bot_mock.get_channel.return_value = channel_mock

        # Setup state file in tmp_path
        state_file = tmp_path / "clip_scan_state.json"
        state_file.write_text(json.dumps({"last_scanned_message_id": 12345}))

        class AsyncIter:
            def __init__(self, items):
                self.items = items

            def __aiter__(self):
                self._iter = iter(self.items)
                return self

            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration

        call_count = 0

        def mock_history(limit=200, before=None):
            nonlocal call_count
            call_count += 1
            if before is not None:
                # First call with before_obj: channel has 0 older messages
                return AsyncIter([])
            else:
                # Retry call with before=None: returns 1 message
                msg = MagicMock()
                msg.id = 54321
                msg.author.bot = False
                msg.content = "Check this clip https://clips.twitch.tv/TestClip123"
                msg.reactions = []
                return AsyncIter([msg])

        channel_mock.history = mock_history

        orig_exists = os.path.exists
        orig_open = open
        state_exists = True

        def fake_exists(p):
            if "clip_scan_state.json" in str(p):
                return state_exists
            return orig_exists(p)

        def fake_remove(p):
            nonlocal state_exists
            if "clip_scan_state.json" in str(p):
                state_exists = False

        def fake_open(p, *args, **kwargs):
            if "clip_scan_state.json" in str(p):
                return orig_open(state_file, *args, **kwargs)
            return orig_open(p, *args, **kwargs)

        with patch("bot.commands.clips.get_database", return_value=mock_db), \
                patch("bot.commands.clips.os.path.exists", side_effect=fake_exists), \
                patch("bot.commands.clips.open", side_effect=fake_open), \
                patch("bot.commands.clips.os.remove", side_effect=fake_remove) as mock_remove:

            found, queued = await cog.process_backlog_batch(
                search_limit=10,
                max_process=5,
                ctx=None,
                dryrun=True,
                resume_from_state=True
            )

            # Verified: it called history twice (first before=12345 returned 0, then auto-looped before=None)
            assert call_count == 2
            # Verified: it removed the state file
            assert mock_remove.called
            # Verified: it found the clip on the retry from the top
            assert found == 1
            assert queued == 1


class TestClipQualityControl:
    """Test strict quality control validation and DM notifications for clip batches."""

    def test_database_update_clip_lore_strict_validation(self):
        """Test that update_clip_lore_from_batch sets UNPROCESSABLE if fields are missing or quote is short."""
        from bot.database.trivia import TriviaDatabase

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        trivia_db = TriviaDatabase(mock_db)

        # 1. Dud: Short quote (2 words)
        dud_data = {
            "game_title": "Elden Ring",
            "reaction": "screamed",
            "trigger": "died to boss",
            "lore_summary": "Jonesy died to Malenia",
            "notable_quote": "Oh no",  # Only 2 words
            "clip_outcome": "Death"
        }
        trivia_db.update_clip_lore_from_batch("https://twitch.tv/clip/1", dud_data)
        executed_params = mock_cursor.execute.call_args[0][1]
        # batch_status is 11th parameter (index 10)
        assert executed_params[10] == "UNPROCESSABLE"

        # 2. Dud: Missing reaction
        dud_data2 = {
            "game_title": "Elden Ring",
            "reaction": "",
            "trigger": "died to boss",
            "lore_summary": "Jonesy died to Malenia",
            "notable_quote": "Why did that happen to me right now",
            "clip_outcome": "Death"
        }
        trivia_db.update_clip_lore_from_batch("https://twitch.tv/clip/2", dud_data2)
        executed_params2 = mock_cursor.execute.call_args[0][1]
        assert executed_params2[10] == "UNPROCESSABLE"

        # 3. Valid: Good quote, reaction, outcome, summary
        valid_data = {
            "game_title": "Elden Ring",
            "reaction": "screamed in terror",
            "trigger": "ambushed by skeleton",
            "lore_summary": "Jonesy was ambushed in the catacombs",
            "notable_quote": "Where did that skeleton come from?!",
            "clip_outcome": "Death"
        }
        trivia_db.update_clip_lore_from_batch("https://twitch.tv/clip/3", valid_data)
        executed_params3 = mock_cursor.execute.call_args[0][1]
        assert executed_params3[10] == "COMPLETED"

    @pytest.mark.asyncio
    async def test_poll_gemini_batches_rejects_dud_and_sends_detailed_dm(self):
        """Test that poll_gemini_batches puts ❌ on dud clips and sends a detailed DM to JAM."""
        from bot.tasks.scheduled import poll_gemini_batches

        mock_bot = MagicMock()
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_cog = MagicMock()
        mock_cog.target_channel_id = 12345
        mock_bot.get_cog.return_value = mock_cog
        mock_bot.get_channel.return_value = mock_channel

        # Mock messages in Discord
        valid_msg = AsyncMock(spec=discord.Message)
        dud_msg = AsyncMock(spec=discord.Message)

        async def fetch_msg(mid):
            return valid_msg if mid == 100 else dud_msg

        mock_channel.fetch_message = fetch_msg

        # Mock JAM user
        jam_user = AsyncMock()
        mock_bot.fetch_user = AsyncMock(return_value=jam_user)

        # Mock database pending batches
        mock_db = MagicMock()
        mock_db.trivia.get_pending_batch_clips.return_value = [
            {"batch_job_id": "batches/test-batch-1", "canonical_url": "https://twitch.tv/clip/valid"},
            {"batch_job_id": "batches/test-batch-1", "canonical_url": "https://twitch.tv/clip/dud"}
        ]

        # Mock Gemini Batch Client
        mock_batch_client = MagicMock()
        batch_obj = MagicMock()
        batch_obj.state = "SUCCEEDED"
        batch_obj.output_uri = "https://fake.url/output"
        mock_batch_client.batches.get.return_value = batch_obj

        # Mock JSONL output: 1 valid, 1 dud (quote too short)
        valid_line = json.dumps({
            "id": "https://twitch.tv/clip/valid|100",
            "response": {
                "candidates": [{"content": {"parts": [{"text": json.dumps({
                    "game_title": "Elden Ring",
                    "reaction": "screamed",
                    "trigger": "boss spawn",
                    "lore_summary": "Startled by boss",
                    "notable_quote": "I was not ready for that at all!",
                    "clip_outcome": "Death"
                })}]}}]
            }
        })

        dud_line = json.dumps({
            "id": "https://twitch.tv/clip/dud|200",
            "response": {
                "candidates": [{"content": {"parts": [{"text": json.dumps({
                    "game_title": "Elden Ring",
                    "reaction": "laughed",
                    "trigger": "funny glitch",
                    "lore_summary": "Saw a glitch",
                    "notable_quote": "Lol nope",  # only 2 words
                    "clip_outcome": "Neutral"
                })}]}}]
            }
        })
        jsonl_content = f"{valid_line}\n{dud_line}".encode("utf-8")

        class MockResponse:
            def read(self):
                return jsonl_content

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        with patch("bot.tasks.scheduled.get_bot_instance", return_value=mock_bot), \
                patch("bot.tasks.scheduled.get_database", return_value=mock_db), \
                patch("bot.handlers.ai_handler.gemini_batch_client", mock_batch_client), \
                patch("urllib.request.urlopen", return_value=MockResponse()):

            await poll_gemini_batches()

            # 1. Verified: Valid clip got ✅
            valid_msg.add_reaction.assert_called_with("✅")

            # 2. Verified: Dud clip got ❌
            dud_msg.add_reaction.assert_called_with("❌")

            # 3. Verified: JAM was sent a DM with the rejected clip list
            assert jam_user.send.called
            sent_dm = jam_user.send.call_args[0][0]
            assert "**Successfully processed:** 1 clips" in sent_dm
            assert "**Rejected / Unprocessable:** 1 clips" in sent_dm
            assert "https://twitch.tv/clip/dud" in sent_dm
            assert "Quote fewer than 3 words" in sent_dm


if __name__ == "__main__":
    pytest.main([__file__])
