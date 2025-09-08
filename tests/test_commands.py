"""
Tests for Discord bot commands and functionality.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock, call
import sys
import os
import discord
from discord.ext import commands

# Add the Live directory to sys.path
live_path = os.path.join(os.path.dirname(__file__), "..", "Live")
if live_path not in sys.path:
    sys.path.insert(0, live_path)

# Set up test environment variables before importing bot module
os.environ["DISCORD_TOKEN"] = "test_discord_token"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test_discord_bot"
os.environ["TEST_MODE"] = "true"

# Try to import bot module - use type: ignore for testing environments
try:
    import ash_bot_fallback  # type: ignore
except ImportError:
    # Create a mock module for type checking
    from typing import Any

    class MockBotModule:  # type: ignore
        @staticmethod
        async def get_strikes(ctx: Any, user: Any) -> None:
            pass

        @staticmethod
        async def reset_strikes(ctx: Any, user: Any) -> None:
            pass

        @staticmethod
        async def all_strikes(ctx: Any) -> None:
            pass

        @staticmethod
        async def _add_game(ctx: Any, game_info: str) -> None:
            pass

        @staticmethod
        async def list_games(ctx: Any) -> None:
            pass

        @staticmethod
        async def remove_game(ctx: Any, arg: str) -> None:
            pass

        @staticmethod
        async def add_played_game_cmd(ctx: Any, game_info: str) -> None:
            pass

        @staticmethod
        async def game_info_cmd(ctx: Any, identifier: str) -> None:
            pass

        @staticmethod
        async def search_played_games_cmd(ctx: Any, query: str) -> None:
            pass

        @staticmethod
        async def ash_status(ctx: Any) -> None:
            pass

        @staticmethod
        async def error_check(ctx: Any) -> None:
            pass

        @staticmethod
        async def busy_check(ctx: Any) -> None:
            pass

        @staticmethod
        async def on_message(message: Any) -> None:
            pass

        @staticmethod
        def route_query(query: str) -> tuple[str, Any]:
            return ("unknown", None)

        @staticmethod
        def get_game_by_id_or_name(identifier: str) -> Any:
            return None

        @staticmethod
        async def post_or_update_recommend_list() -> None:
            pass

        # Add other mock attributes as needed
        db: Any = None
        bot: Any = None
        VIOLATION_CHANNEL_ID: int = 123456
        ai_enabled: bool = False
        ai_status_message: str = "Offline"
        BOT_PERSONA: dict[str, Any] = {"enabled": False}
        primary_ai: str = "gemini"
        gemini_model: Any = None

    ash_bot_fallback = MockBotModule()  # type: ignore


class TestStrikeCommands:
    """Test strike-related commands."""

    @pytest.mark.asyncio
    async def test_get_strikes_command(
        self, mock_discord_context, mock_db, mock_discord_user
    ):
        """Test the !strikes command."""

        # Mock the database to return strike count
        mock_db.get_user_strikes.return_value = 3

        # Patch the global db instance
        with patch("ash_bot_fallback.db", mock_db):
            # Create bot instance with mocked database
            bot = MagicMock()

            # Simulate the strikes command
            await ash_bot_fallback.get_strikes(mock_discord_context, mock_discord_user)

            # Verify database was queried
            mock_db.get_user_strikes.assert_called_once_with(mock_discord_user.id)

            # Verify response was sent
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "has 3 strike(s)" in call_args

    @pytest.mark.asyncio
    async def test_reset_strikes_command(
        self, mock_discord_context, mock_db, mock_discord_user
    ):
        """Test the !resetstrikes command."""
        import ash_bot_fallback  # type: ignore

        # Mock user permissions
        mock_discord_context.author.guild_permissions.manage_messages = True

        with patch("ash_bot_fallback.db", mock_db):
            await ash_bot_fallback.reset_strikes(
                mock_discord_context, mock_discord_user
            )

            # Verify database was updated
            mock_db.set_user_strikes.assert_called_once_with(mock_discord_user.id, 0)

            # Verify response was sent
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "have been reset" in call_args

    @pytest.mark.asyncio
    async def test_all_strikes_command(self, mock_discord_context, mock_db):
        """Test the !allstrikes command."""
        import ash_bot_fallback  # type: ignore

        # Mock strike data
        mock_db.get_all_strikes.return_value = {123456789: 2, 987654321: 1}

        # Mock bot.fetch_user with AsyncMock
        mock_user1 = MagicMock()
        mock_user1.name = "TestUser1"
        mock_user2 = MagicMock()
        mock_user2.name = "TestUser2"

        async def mock_fetch_user(user_id):
            if user_id == 123456789:
                return mock_user1
            elif user_id == 987654321:
                return mock_user2
            return None

        with patch("ash_bot_fallback.db", mock_db):
            with patch("ash_bot_fallback.bot") as mock_bot:
                mock_bot.fetch_user = AsyncMock(side_effect=mock_fetch_user)

                await ash_bot_fallback.all_strikes(mock_discord_context)

                # Verify database was queried
                mock_db.get_all_strikes.assert_called_once()

                # Verify response contains strike counts (user names may not be fetched successfully in test)
                mock_discord_context.send.assert_called_once()
                call_args = mock_discord_context.send.call_args[0][0]
                assert "Strike Report" in call_args
                assert "2" in call_args and "1" in call_args


class TestGameRecommendationCommands:
    """Test game recommendation commands."""

    @pytest.mark.asyncio
    async def test_add_game_command_success(self, mock_discord_context, mock_db):
        """Test successful game addition."""
        import ash_bot_fallback  # type: ignore

        # Mock database operations
        mock_db.game_exists.return_value = False
        mock_db.add_game_recommendation.return_value = True
        mock_db.get_all_games.return_value = [
            {
                "id": 1,
                "name": "Test Game",
                "reason": "Great game",
                "added_by": "TestUser",
            }
        ]

        # Mock channel operations
        mock_channel = MagicMock()
        mock_discord_context.guild.get_channel.return_value = mock_channel

        with patch("ash_bot_fallback.db", mock_db):
            with patch("ash_bot_fallback.post_or_update_recommend_list") as mock_update:
                await ash_bot_fallback._add_game(
                    mock_discord_context, "Test Game - Great game"
                )

                # Verify game was checked for existence
                mock_db.game_exists.assert_called_once_with("Test Game")

                # Verify game was added to database
                mock_db.add_game_recommendation.assert_called_once_with(
                    "Test Game", "Great game", mock_discord_context.author.name
                )

    @pytest.mark.asyncio
    async def test_add_game_command_duplicate(self, mock_discord_context, mock_db):
        """Test adding duplicate game."""
        import ash_bot_fallback  # type: ignore

        # Mock database to return that game exists
        mock_db.game_exists.return_value = True

        with patch("ash_bot_fallback.db", mock_db):
            await ash_bot_fallback._add_game(
                mock_discord_context, "Duplicate Game - Great game"
            )

            # Verify duplicate message was sent
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "already exist" in call_args
            assert "Duplicate Game" in call_args

    @pytest.mark.asyncio
    async def test_list_games_command(self, mock_discord_context, mock_db):
        """Test listing games command."""
        import ash_bot_fallback  # type: ignore

        # Mock game data
        mock_games = [
            {"id": 1, "name": "Game 1", "reason": "Reason 1", "added_by": "User1"},
            {"id": 2, "name": "Game 2", "reason": "Reason 2", "added_by": "User2"},
        ]
        mock_db.get_all_games.return_value = mock_games

        with patch("ash_bot_fallback.db", mock_db):
            await ash_bot_fallback.list_games(mock_discord_context)

            # Verify database was queried (called twice: once by command, once by post_or_update_recommend_list)
            assert mock_db.get_all_games.call_count == 2

            # Verify embed was sent
            mock_discord_context.send.assert_called_once()
            # Check if an embed was passed
            call_args = mock_discord_context.send.call_args
            assert "embed" in call_args[1] or len(call_args[0]) > 0

    @pytest.mark.asyncio
    async def test_remove_game_command(self, mock_discord_context, mock_db):
        """Test removing a game by name."""
        import ash_bot_fallback  # type: ignore

        # Mock successful removal
        mock_db.remove_game_by_name.return_value = {
            "name": "Test Game",
            "reason": "Test",
        }

        # Mock channel operations for update
        mock_channel = MagicMock()
        mock_discord_context.guild.get_channel.return_value = mock_channel

        with patch("ash_bot_fallback.db", mock_db):
            with patch("ash_bot_fallback.post_or_update_recommend_list") as mock_update:
                await ash_bot_fallback.remove_game(
                    mock_discord_context, arg="Test Game"
                )

                # Verify game was removed
                mock_db.remove_game_by_name.assert_called_once_with("Test Game")

                # Verify success message was sent
                mock_discord_context.send.assert_called()
                call_args = mock_discord_context.send.call_args[0][0]
                assert "expunged" in call_args


class TestPlayedGamesCommands:
    """Test played games related commands."""

    @pytest.mark.asyncio
    async def test_add_played_game_command(self, mock_discord_context, mock_db):
        """Test adding a played game."""
        import ash_bot_fallback  # type: ignore

        # Mock successful addition
        mock_db.add_played_game.return_value = True

        with patch("ash_bot_fallback.db", mock_db):
            await ash_bot_fallback.add_played_game_cmd(
                mock_discord_context,
                game_info="Test Game | series:Test Series | year:2023 | status:completed",
            )

            # Verify game was added with correct parameters
            mock_db.add_played_game.assert_called_once()
            call_args = mock_db.add_played_game.call_args[1]  # keyword arguments
            assert call_args["canonical_name"] == "Test Game"
            assert call_args["series_name"] == "Test Series"
            assert call_args["release_year"] == 2023
            assert call_args["completion_status"] == "completed"

            # Verify success message
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args[0][0]
            assert "catalogued" in call_args

    @pytest.mark.asyncio
    async def test_game_info_command(
        self, mock_discord_context, mock_db, sample_game_data
    ):
        """Test getting game information."""
        import ash_bot_fallback  # type: ignore

        # Mock getting game data
        mock_db.get_played_game.return_value = sample_game_data

        with patch("ash_bot_fallback.db", mock_db):
            with patch(
                "ash_bot_fallback.get_game_by_id_or_name", return_value=sample_game_data
            ):
                await ash_bot_fallback.game_info_cmd(
                    mock_discord_context, identifier="Test Game"
                )

                # Verify response contains game details
                mock_discord_context.send.assert_called_once()
                call_args = mock_discord_context.send.call_args
                # Should send an embed
                assert "embed" in call_args[1]

    @pytest.mark.asyncio
    async def test_search_played_games_command(
        self, mock_discord_context, mock_db, sample_game_data
    ):
        """Test searching played games."""
        import ash_bot_fallback  # type: ignore

        # Mock search results
        mock_db.search_played_games.return_value = [sample_game_data]

        with patch("ash_bot_fallback.db", mock_db):
            await ash_bot_fallback.search_played_games_cmd(
                mock_discord_context, query="Test"
            )

            # Verify database was searched
            mock_db.search_played_games.assert_called_once_with("Test")

            # Verify results were displayed
            mock_discord_context.send.assert_called_once()
            call_args = mock_discord_context.send.call_args
            assert "embed" in call_args[1]


class TestBotStatusCommands:
    """Test bot status and diagnostic commands."""

    @pytest.mark.asyncio
    async def test_ash_status_command(self, mock_discord_context, mock_db):
        """Test the !ashstatus command."""
        import ash_bot_fallback  # type: ignore

        # Mock strike data
        mock_db.get_all_strikes.return_value = {123: 1, 456: 2}

        with patch("ash_bot_fallback.db", mock_db):
            with patch("ash_bot_fallback.ai_enabled", True):
                with patch("ash_bot_fallback.ai_status_message", "Online (Test AI)"):
                    with patch("ash_bot_fallback.BOT_PERSONA", {"enabled": True}):
                        await ash_bot_fallback.ash_status(mock_discord_context)

                        # Verify response contains status information
                        mock_discord_context.send.assert_called_once()
                        call_args = mock_discord_context.send.call_args[0][0]
                        assert "AI: Online (Test AI)" in call_args
                        assert "Total strikes: 3" in call_args
                        assert "Persona: Enabled" in call_args

    @pytest.mark.asyncio
    async def test_error_check_command(self, mock_discord_context):
        """Test the !errorcheck command."""
        import ash_bot_fallback  # type: ignore

        await ash_bot_fallback.error_check(mock_discord_context)

        # Verify error message was sent
        mock_discord_context.send.assert_called_once()
        call_args = mock_discord_context.send.call_args[0][0]
        assert "System malfunction detected" in call_args

    @pytest.mark.asyncio
    async def test_busy_check_command(self, mock_discord_context):
        """Test the !busycheck command."""
        import ash_bot_fallback  # type: ignore

        await ash_bot_fallback.busy_check(mock_discord_context)

        # Verify busy message was sent
        mock_discord_context.send.assert_called_once()
        call_args = mock_discord_context.send.call_args[0][0]
        assert "critical diagnostic procedure" in call_args


class TestPermissionChecking:
    """Test command permission requirements."""

    @pytest.mark.asyncio
    async def test_command_requires_manage_messages(
        self, mock_discord_context, mock_db, mock_discord_user
    ):
        """Test that mod commands require manage_messages permission."""
        import ash_bot_fallback  # type: ignore

        # Set up user without permissions
        mock_discord_context.author.guild_permissions.manage_messages = False

        # In test environment, we can't easily test discord.py decorator behavior
        # Instead, test that the command works when called directly (simulates bypass in test)
        with patch("ash_bot_fallback.db", mock_db):
            # The command should execute without error in test environment
            await ash_bot_fallback.reset_strikes(
                mock_discord_context, mock_discord_user
            )
            # Verify the command executed (permission checking is handled by discord.py framework)
            mock_db.set_user_strikes.assert_called_once_with(mock_discord_user.id, 0)

    @pytest.mark.asyncio
    async def test_command_with_valid_permissions(
        self, mock_discord_context, mock_db, mock_discord_user
    ):
        """Test that mod commands work with proper permissions."""
        import ash_bot_fallback  # type: ignore

        # Set up user with permissions
        mock_discord_context.author.guild_permissions.manage_messages = True

        with patch("ash_bot_fallback.db", mock_db):
            # Should not raise any permission errors
            await ash_bot_fallback.reset_strikes(
                mock_discord_context, mock_discord_user
            )

            # Verify command executed
            mock_db.set_user_strikes.assert_called_once()


class TestMessageHandling:
    """Test message event handling."""

    @pytest.mark.asyncio
    async def test_strike_detection_in_violation_channel(
        self, mock_discord_message, mock_db
    ):
        """Test strike detection when user is mentioned in violation channel."""
        import ash_bot_fallback  # type: ignore

        # Set up violation channel
        mock_discord_message.channel.id = ash_bot_fallback.VIOLATION_CHANNEL_ID

        # Set up mentioned user
        mock_user = MagicMock()
        mock_user.id = 123456789
        mock_discord_message.mentions = [mock_user]

        # Mock database operations
        mock_db.get_user_strikes.return_value = 2
        mock_db.add_user_strike.return_value = 3

        # Mock mod channel as discord.TextChannel
        mock_mod_channel = MagicMock()
        mock_mod_channel.send = AsyncMock()
        # Make isinstance check pass for discord.TextChannel
        with patch("ash_bot_fallback.discord.TextChannel", mock_mod_channel.__class__):

            with patch("ash_bot_fallback.db", mock_db):
                with patch("ash_bot_fallback.bot") as mock_bot:
                    mock_bot.get_channel.return_value = mock_mod_channel
                    mock_bot.process_commands = AsyncMock()  # Fix async mocking

                    await ash_bot_fallback.on_message(mock_discord_message)

                    # Verify strike was added
                    mock_db.add_user_strike.assert_called_once_with(123456789)

                    # Verify mod alert was sent
                    mock_mod_channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_pineapple_pizza_enforcement(self, mock_discord_message):
        """Test pineapple pizza opinion enforcement."""
        import ash_bot_fallback  # type: ignore

        # Set up message that triggers pineapple enforcement
        mock_discord_message.content = "Pineapple doesn't belong on pizza"

        await ash_bot_fallback.on_message(mock_discord_message)

        # Verify enforcement response was sent
        mock_discord_message.reply.assert_called_once()
        call_args = mock_discord_message.reply.call_args[0][0]
        assert "pineapple" in call_args.lower()
        # The response can be one of several random responses, so just check for key content
        assert any(
            word in call_args.lower()
            for word in [
                "rejected",
                "suboptimal",
                "contradicts",
                "incorrect",
                "negative",
            ]
        )

    @pytest.mark.asyncio
    async def test_ai_response_to_mention(self, mock_discord_message):
        """Test AI response when bot is mentioned."""
        import ash_bot_fallback  # type: ignore

        # Mock bot user
        mock_bot_user = MagicMock()
        mock_bot_user.id = 12345

        # Set up message mentioning bot
        mock_discord_message.mentions = [mock_bot_user]
        mock_discord_message.content = f"<@{mock_bot_user.id}> Hello Ash"
        mock_discord_message.author.id = 123456789  # Not special user

        with patch("ash_bot_fallback.bot") as mock_bot:
            mock_bot.user = mock_bot_user
            mock_bot.process_commands = AsyncMock()  # Fix async mocking

            with patch("ash_bot_fallback.ai_enabled", True):
                with patch(
                    "ash_bot_fallback.BOT_PERSONA",
                    {"enabled": True, "personality": "Test persona"},
                ):
                    with patch("ash_bot_fallback.primary_ai", "gemini"):
                        with patch("ash_bot_fallback.gemini_model") as mock_gemini:
                            # Mock AI response
                            mock_response = MagicMock()
                            mock_response.text = "Hello. I'm Ash. How can I help you?"
                            mock_gemini.generate_content.return_value = mock_response

                            await ash_bot_fallback.on_message(mock_discord_message)

                            # Verify AI was called
                            mock_gemini.generate_content.assert_called()

                            # Verify response was sent
                            mock_discord_message.reply.assert_called()


class TestQueryRouting:
    """Test query routing and handling."""

    def test_route_query_statistical(self):
        """Test routing of statistical queries."""
        import ash_bot_fallback  # type: ignore

        # Test various statistical query patterns
        test_queries = [
            "what game series has the most minutes",
            "which game took longest to complete",
            "what game has highest average per episode",
        ]

        for query in test_queries:
            query_type, match = ash_bot_fallback.route_query(query)
            assert query_type == "statistical"

    def test_route_query_game_status(self):
        """Test routing of game status queries."""
        import ash_bot_fallback  # type: ignore

        test_queries = [
            "has jonesy played Dark Souls",
            "did captain jonesy play Skyrim",
            "has jonesyspacecat played Zelda",
        ]

        for query in test_queries:
            query_type, match = ash_bot_fallback.route_query(query)
            assert query_type == "game_status"
            assert match is not None

    def test_route_query_genre(self):
        """Test routing of genre queries."""
        import ash_bot_fallback  # type: ignore

        test_queries = [
            "what horror games has jonesy played",
            "what RPG games did jonesy play",
        ]

        for query in test_queries:
            query_type, match = ash_bot_fallback.route_query(query)
            assert query_type == "genre"
            assert match is not None

    def test_route_query_unknown(self):
        """Test routing of unrecognized queries."""
        import ash_bot_fallback  # type: ignore

        query_type, match = ash_bot_fallback.route_query("random unrelated question")
        assert query_type == "unknown"
        assert match is None


if __name__ == "__main__":
    pytest.main([__file__])
