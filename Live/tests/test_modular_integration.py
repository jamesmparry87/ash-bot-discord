#!/usr/bin/env python3
"""
Test script for modular bot integration
Tests end-to-end functionality through bot_modular.py with all components.
"""

import asyncio
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(__file__))

# Set up test environment
os.environ.setdefault('DISCORD_TOKEN', 'test_token')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/test')


def test_modular_bot_imports():
    """Test that modular bot can be imported with all components"""
    print("🧪 Testing modular bot imports...")

    try:
        import bot_modular
        print("✅ Main bot_modular.py imported successfully")

        # Check for key attributes
        assert hasattr(bot_modular, 'bot'), "Bot instance not found"
        assert hasattr(
            bot_modular, 'initialize_modular_components'), "Initialization function not found"
        assert hasattr(
            bot_modular, 'message_handler_functions'), "Message handler functions not declared"

        print(f"   - Bot instance: {type(bot_modular.bot).__name__}")
        print(
            f"   - Message handlers declared: {'Yes' if hasattr(bot_modular, 'message_handler_functions') else 'No'}")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Modular bot test failed: {e}")
        return False


async def test_modular_component_initialization():
    """Test that all modular components can be initialized"""
    print("🧪 Testing modular component initialization...")

    try:
        import bot_modular

        # Test the initialization function
        status_report = await bot_modular.initialize_modular_components()

        # Check status report structure
        expected_keys = [
            "ai_handler",
            "database",
            "commands",
            "scheduled_tasks",
            "message_handlers",
            "fallback_mode",
            "errors"]
        for key in expected_keys:
            assert key in status_report, f"Missing key in status report: {key}"

        # Count successful components
        successful_components = sum(
            1 for key, value in status_report.items() if key not in [
                "errors", "fallback_mode"] and value)

        print(f"✅ Component initialization completed")
        print(f"   - Successful components: {successful_components}")
        print(f"   - Errors encountered: {len(status_report['errors'])}")
        print(
            f"   - Fallback mode required: {status_report.get('fallback_mode', False)}")

        # Should have at least some components working
        assert successful_components >= 2, f"Too few components successful: {successful_components}"

        return True

    except Exception as e:
        print(f"❌ Component initialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_command_cog_loading():
    """Test that command cogs can be loaded into the bot"""
    print("🧪 Testing command cog loading...")

    try:
        import bot_modular
        from discord.ext import commands

        # Create a test bot instance
        test_bot = commands.Bot(
            command_prefix='!',
            intents=bot_modular.intents)

        # Test loading strikes commands
        from bot.commands.strikes import StrikesCommands
        strikes_cog = StrikesCommands(test_bot)
        await test_bot.add_cog(strikes_cog)

        # Verify cog was loaded
        loaded_cogs = list(test_bot.cogs.keys())
        assert 'StrikesCommands' in loaded_cogs, "StrikesCommands cog not loaded"

        # Test command availability
        strikes_commands = strikes_cog.get_commands()
        command_names = [cmd.name for cmd in strikes_commands]

        print(f"✅ Command cogs loaded successfully")
        print(f"   - Loaded cogs: {loaded_cogs}")
        print(f"   - Strikes commands: {command_names}")

        # Try to load other cogs if available
        try:
            from bot.commands.games import GamesCommands
            games_cog = GamesCommands(test_bot)
            await test_bot.add_cog(games_cog)
            print(
                f"   - Games cog loaded: {len(games_cog.get_commands())} commands")
        except ImportError:
            print("   - Games cog not available")
        except Exception as e:
            print(f"   - Games cog failed to load: {e}")

        try:
            from bot.commands.utility import UtilityCommands
            utility_cog = UtilityCommands(test_bot)
            await test_bot.add_cog(utility_cog)
            print(
                f"   - Utility cog loaded: {len(utility_cog.get_commands())} commands")
        except ImportError:
            print("   - Utility cog not available")
        except Exception as e:
            print(f"   - Utility cog failed to load: {e}")

        return True

    except Exception as e:
        print(f"❌ Command cog loading test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_message_handler_integration():
    """Test that message handlers are properly integrated"""
    print("🧪 Testing message handler integration...")

    try:
        import bot_modular

        # Initialize components to load message handlers
        await bot_modular.initialize_modular_components()

        # Check if message handler functions were loaded
        assert bot_modular.message_handler_functions is not None, "Message handler functions not loaded"

        # Verify expected handler functions exist
        expected_handlers = [
            'handle_strike_detection',
            'handle_pineapple_pizza_enforcement',
            'route_query',
            'handle_statistical_query',
            'handle_genre_query',
            'handle_year_query',
            'handle_game_status_query',
            'handle_recommendation_query'
        ]

        for handler in expected_handlers:
            assert handler in bot_modular.message_handler_functions, f"Handler missing: {handler}"

        print("✅ Message handler integration test passed")
        print(
            f"   - Loaded handlers: {len(bot_modular.message_handler_functions)}")
        print(
            f"   - Handler functions: {list(bot_modular.message_handler_functions.keys())}")

        return True

    except Exception as e:
        print(f"❌ Message handler integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_dm_vs_guild_message_routing():
    """Test DM vs guild message routing in on_message handler"""
    print("🧪 Testing DM vs guild message routing...")

    try:
        import bot_modular
        import discord

        # Initialize components
        await bot_modular.initialize_modular_components()

        # Test DM message routing
        mock_dm_message = MagicMock()
        mock_dm_message.author.bot = False
        mock_dm_message.author.id = 337833732901961729  # JAM_USER_ID
        mock_dm_message.channel = MagicMock(spec=discord.DMChannel)
        mock_dm_message.content = "test dm message"

        # Mock conversation states (empty)
        with patch('bot_modular.announcement_conversations', {}):
            with patch('bot_modular.mod_trivia_conversations', {}):
                with patch('bot_modular.bot.process_commands', new_callable=AsyncMock) as mock_process:
                    await bot_modular.on_message(mock_dm_message)
                    # Should reach process_commands for DM
                    mock_process.assert_called_once()

        # Test guild message routing
        mock_guild_message = MagicMock()
        mock_guild_message.author.bot = False
        mock_guild_message.author.id = 123456789
        mock_guild_message.channel = MagicMock(spec=discord.TextChannel)
        mock_guild_message.channel.id = 999999999  # Not violation channel
        mock_guild_message.content = "test guild message"
        mock_guild_message.mentions = []

        # Mock bot user for mention detection
        mock_bot_user = MagicMock()
        mock_bot_user.id = 888888888

        with patch('bot_modular.bot.user', mock_bot_user):
            with patch('bot_modular.bot.process_commands', new_callable=AsyncMock) as mock_process:
                await bot_modular.on_message(mock_guild_message)
                # Should reach process_commands for guild message too
                mock_process.assert_called_once()

        print("✅ DM vs guild message routing test passed")
        print("   - DM messages routed correctly")
        print("   - Guild messages routed correctly")
        print("   - Message handler functions called appropriately")

        return True

    except Exception as e:
        print(f"❌ DM vs guild message routing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_conversation_command_integration():
    """Test that conversation commands are properly integrated"""
    print("🧪 Testing conversation command integration...")

    try:
        import bot_modular

        # Test that conversation commands exist
        bot = bot_modular.bot

        # Check if announcement command exists
        announce_cmd = bot.get_command('announceupdate')
        assert announce_cmd is not None, "announceupdate command not found"

        # Check if trivia command exists
        trivia_cmd = bot.get_command('addtriviaquestion')
        assert trivia_cmd is not None, "addtriviaquestion command not found"

        print("✅ Conversation command integration test passed")
        print(
            f"   - !announceupdate command: {'Available' if announce_cmd else 'Missing'}")
        print(
            f"   - !addtriviaquestion command: {'Available' if trivia_cmd else 'Missing'}")

        return True

    except Exception as e:
        print(f"❌ Conversation command integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fallback_behavior():
    """Test bot behavior when components fail to load"""
    print("🧪 Testing fallback behavior...")

    original_handlers = None
    try:
        import bot_modular

        # Simulate message handler functions being None (failed to load)
        original_handlers = bot_modular.message_handler_functions
        bot_modular.message_handler_functions = None

        # Test message processing with failed handlers
        mock_message = MagicMock()
        mock_message.author.bot = False
        mock_message.author.id = 123456789
        mock_message.channel = MagicMock()
        mock_message.content = "test message"

        with patch('bot_modular.bot.process_commands', new_callable=AsyncMock) as mock_process:
            # Should not crash, should fall back to commands only
            await bot_modular.on_message(mock_message)
            mock_process.assert_called_once()

        # Restore original handlers
        bot_modular.message_handler_functions = original_handlers

        print("✅ Fallback behavior test passed")
        print("   - Bot continues to function when message handlers fail")
        print("   - Commands still processed normally")

        return True

    except Exception as e:
        print(f"❌ Fallback behavior test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Ensure handlers are restored even if test fails
        try:
            if original_handlers is not None:
                import bot_modular
                bot_modular.message_handler_functions = original_handlers
        except BaseException:
            pass


async def test_global_variable_initialization():
    """Test that critical global variables are properly initialized"""
    print("🧪 Testing global variable initialization...")

    try:
        import bot_modular

        # Check message_handler_functions is declared at module level
        assert hasattr(
            bot_modular, 'message_handler_functions'), "message_handler_functions not declared"

        # Check configuration constants
        assert hasattr(bot_modular, 'TOKEN'), "TOKEN not configured"
        assert hasattr(bot_modular, 'GUILD_ID'), "GUILD_ID not configured"
        assert hasattr(
            bot_modular, 'JAM_USER_ID'), "JAM_USER_ID not configured"
        assert hasattr(
            bot_modular, 'JONESY_USER_ID'), "JONESY_USER_ID not configured"

        # Check rate limiting configuration
        assert hasattr(
            bot_modular, 'PRIORITY_INTERVALS'), "PRIORITY_INTERVALS not configured"
        assert hasattr(
            bot_modular, 'RATE_LIMIT_COOLDOWNS'), "RATE_LIMIT_COOLDOWNS not configured"

        # Verify rate limiting values
        assert bot_modular.PRIORITY_INTERVALS['high'] == 1.0, "High priority interval incorrect"
        assert bot_modular.PRIORITY_INTERVALS['medium'] == 2.0, "Medium priority interval incorrect"
        assert bot_modular.PRIORITY_INTERVALS['low'] == 3.0, "Low priority interval incorrect"

        print("✅ Global variable initialization test passed")
        print("   - All critical variables declared")
        print("   - Configuration constants loaded")
        print("   - Rate limiting properly configured")
        print(f"   - Priority intervals: {bot_modular.PRIORITY_INTERVALS}")

        return True

    except Exception as e:
        print(f"❌ Global variable initialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_modular_integration_tests():
    """Run all modular integration tests"""
    print("🚀 Starting Modular Integration Testing Suite\n")

    tests = [
        ("Modular Bot Imports", test_modular_bot_imports),
        ("Component Initialization", test_modular_component_initialization),
        ("Command Cog Loading", test_command_cog_loading),
        ("Message Handler Integration", test_message_handler_integration),
        ("DM vs Guild Routing", test_dm_vs_guild_message_routing),
        ("Conversation Commands", test_conversation_command_integration),
        ("Fallback Behavior", test_fallback_behavior),
        ("Global Variable Init", test_global_variable_initialization),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test {test_name} crashed: {e}")
            results.append((test_name, False))

    # Results summary
    print(f"\n{'='*50}")
    print("📊 MODULAR INTEGRATION TEST SUMMARY:")

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")
        if result:
            passed += 1

    print(f"\nResults: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("🎉 All modular integration tests passed!")
        print("\n✅ Modular Architecture Validated:")
        print("   • End-to-end bot functionality through bot_modular.py")
        print("   • Command cogs loading and integration")
        print("   • Message handler routing (DM vs guild)")
        print("   • Conversation command integration")
        print("   • Robust fallback behavior when components fail")
        print("   • Global variable and configuration management")
        print("   • Component initialization and status reporting")
    else:
        print("⚠️ Some modular integration tests failed. Review errors above.")

    return passed == len(tests)


if __name__ == "__main__":
    success = asyncio.run(run_modular_integration_tests())
    sys.exit(0 if success else 1)
