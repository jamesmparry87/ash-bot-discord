#!/usr/bin/env python3
"""
Test script for DM conversation functionality
Tests interactive conversation flows for announcements and trivia submissions.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

# Add the bot directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

# Set up test environment
os.environ.setdefault('DISCORD_TOKEN', 'test_token')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/test')


def test_conversation_handler_imports():
    """Test that conversation handler modules can be imported"""
    print("🧪 Testing conversation handler imports...")

    try:
        from bot.handlers.conversation_handler import (
            announcement_conversations,
            cleanup_announcement_conversations,
            cleanup_mod_trivia_conversations,
            handle_announcement_conversation,
            handle_mod_trivia_conversation,
            mod_trivia_conversations,
            start_announcement_conversation,
            start_trivia_conversation,
        )
        print("✅ All conversation handler modules imported successfully")
        print(
            f"   - Announcement conversations: {type(announcement_conversations).__name__}")
        print(
            f"   - Trivia conversations: {type(mod_trivia_conversations).__name__}")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


async def test_announcement_conversation_flow():
    """Test complete announcement conversation flow"""
    print("🧪 Testing announcement conversation flow...")

    user_id = None  # Initialize to None for safe cleanup
    try:
        from bot.handlers.conversation_handler import announcement_conversations, handle_announcement_conversation

        # Mock user and message objects
        mock_user = MagicMock()
        mock_user.id = 337833732901961729  # JAM_USER_ID
        mock_user.name = "TestJam"

        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()

        # Test conversation flow
        user_id = mock_user.id

        # 1. Initialize conversation state
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        announcement_conversations[user_id] = {
            'step': 'channel_selection',
            'data': {},
            'last_activity': uk_now,
        }

        # 2. Test channel selection
        mock_message = MagicMock()
        mock_message.author = mock_user
        mock_message.content = "1"  # Select mod channel
        mock_message.reply = AsyncMock()

        await handle_announcement_conversation(mock_message)

        # Verify step progression
        assert announcement_conversations[user_id]['step'] == 'content_input'
        assert announcement_conversations[user_id]['data']['target_channel'] == 'mod'

        # 3. Test content input
        mock_message.content = "Test announcement content for modular bot testing"
        await handle_announcement_conversation(mock_message)

        # Verify preview step
        assert announcement_conversations[user_id]['step'] in ['preview']
        assert 'raw_content' in announcement_conversations[user_id]['data']

        print("✅ Announcement conversation flow test passed")
        return True

    except Exception as e:
        print(f"❌ Announcement conversation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up test data safely
        try:
            if user_id is not None:
                from bot.handlers.conversation_handler import announcement_conversations
                if user_id in announcement_conversations:
                    del announcement_conversations[user_id]
        except Exception:
            pass  # Ignore cleanup errors


async def test_trivia_conversation_flow():
    """Test complete trivia question submission flow"""
    print("🧪 Testing trivia conversation flow...")

    user_id = None  # Initialize to None for safe cleanup
    try:
        from bot.handlers.conversation_handler import handle_mod_trivia_conversation, mod_trivia_conversations

        # Mock user and message objects
        mock_user = MagicMock()
        mock_user.id = 337833732901961729  # JAM_USER_ID (has mod permissions)
        mock_user.name = "TestMod"

        user_id = mock_user.id

        # 1. Initialize conversation state
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        mod_trivia_conversations[user_id] = {
            'step': 'initial',
            'data': {},
            'last_activity': uk_now,
        }

        # 2. Test initial question submission
        mock_message = MagicMock()
        mock_message.author = mock_user
        mock_message.content = "I want to add a trivia question"
        mock_message.reply = AsyncMock()

        await handle_mod_trivia_conversation(mock_message)

        # Verify step progression
        assert mod_trivia_conversations[user_id]['step'] == 'question_type_selection'

        # 3. Test question type selection
        mock_message.content = "2"  # Manual question+answer
        await handle_mod_trivia_conversation(mock_message)

        assert mod_trivia_conversations[user_id]['data']['question_type'] == 'manual_answer'
        assert mod_trivia_conversations[user_id]['step'] == 'question_input'

        # 4. Test question input
        mock_message.content = "What is Captain Jonesy's favorite catchphrase? A) Shit on it! B) Oh crumbles C) Nuke 'em from orbit"
        await handle_mod_trivia_conversation(mock_message)

        assert 'question_text' in mod_trivia_conversations[user_id]['data']
        assert mod_trivia_conversations[user_id]['step'] == 'answer_input'

        # 5. Test answer input
        mock_message.content = "A) Shit on it!"
        await handle_mod_trivia_conversation(mock_message)

        assert 'correct_answer' in mod_trivia_conversations[user_id]['data']
        assert mod_trivia_conversations[user_id]['step'] == 'preview'

        print("✅ Trivia conversation flow test passed")
        return True

    except Exception as e:
        print(f"❌ Trivia conversation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up test data safely
        try:
            if user_id is not None:
                from bot.handlers.conversation_handler import mod_trivia_conversations
                if user_id in mod_trivia_conversations:
                    del mod_trivia_conversations[user_id]
        except Exception:
            pass  # Ignore cleanup errors


async def test_dm_command_permissions():
    """Test DM command permission checking"""
    print("🧪 Testing DM command permissions...")

    try:
        from bot.handlers.conversation_handler import start_announcement_conversation

        # Test authorized user (JAM_USER_ID)
        mock_ctx = MagicMock()
        mock_ctx.guild = None  # DM context
        mock_ctx.author.id = 337833732901961729  # JAM_USER_ID
        mock_ctx.send = AsyncMock()

        await start_announcement_conversation(mock_ctx)

        # Should succeed (no error raised, conversation started)
        mock_ctx.send.assert_called_once()

        # Reset mock
        mock_ctx.send.reset_mock()

        # Test unauthorized user
        mock_ctx.author.id = 999999999  # Random unauthorized ID
        await start_announcement_conversation(mock_ctx)

        # Should send access denied message
        mock_ctx.send.assert_called_once()
        call_content = mock_ctx.send.call_args[0][0]
        assert "Access denied" in call_content

        print("✅ DM command permissions test passed")
        return True

    except Exception as e:
        print(f"❌ DM command permissions test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_conversation_cleanup():
    """Test conversation state cleanup functionality"""
    print("🧪 Testing conversation cleanup...")

    try:
        from bot.handlers.conversation_handler import (
            announcement_conversations,
            cleanup_announcement_conversations,
            cleanup_mod_trivia_conversations,
            mod_trivia_conversations,
        )

        # Add expired conversation
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        old_time = uk_now - timedelta(hours=2)  # 2 hours ago (expired)

        test_user_id = 999999999
        announcement_conversations[test_user_id] = {
            'step': 'content_input',
            'data': {},
            'last_activity': old_time,
        }

        mod_trivia_conversations[test_user_id] = {
            'step': 'initial',
            'data': {},
            'last_activity': old_time,
        }

        # Run cleanup
        cleanup_announcement_conversations()
        cleanup_mod_trivia_conversations()

        # Verify expired conversations were removed
        assert test_user_id not in announcement_conversations
        assert test_user_id not in mod_trivia_conversations

        print("✅ Conversation cleanup test passed")
        return True

    except Exception as e:
        print(f"❌ Conversation cleanup test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ai_content_enhancement():
    """Test AI content enhancement for announcements"""
    print("🧪 Testing AI content enhancement...")

    try:
        from bot.handlers.conversation_handler import create_ai_announcement_content

        # Mock AI being disabled (fallback test)
        with patch('bot.handlers.conversation_handler.ai_enabled', False):
            original_content = "Test announcement content"
            enhanced = await create_ai_announcement_content(
                original_content, 'mod', 337833732901961729
            )

            # Should return original content when AI is disabled
            assert enhanced == original_content

        print("✅ AI content enhancement test passed (fallback scenario)")
        return True

    except Exception as e:
        print(f"❌ AI content enhancement test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_announcement_formatting():
    """Test announcement content formatting"""
    print("🧪 Testing announcement formatting...")

    try:
        from bot.handlers.conversation_handler import format_announcement_content

        # Test mod channel formatting
        content = "Test update content"
        user_id = 337833732901961729  # JAM_USER_ID

        formatted_mod = await format_announcement_content(content, 'mod', user_id)

        # Verify mod formatting
        assert "Technical Briefing" in formatted_mod
        assert "Sir Decent Jam" in formatted_mod
        assert content in formatted_mod

        # Test user channel formatting
        formatted_user = await format_announcement_content(content, 'user', user_id)

        # Verify user formatting
        assert "Exciting Bot Updates" in formatted_user
        assert "Sir Decent Jam" in formatted_user
        assert content in formatted_user

        print("✅ Announcement formatting test passed")
        return True

    except Exception as e:
        print(f"❌ Announcement formatting test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_dm_conversation_tests():
    """Run all DM conversation tests"""
    print("🚀 Starting DM Conversation Testing Suite\n")

    tests = [
        ("Import Tests", test_conversation_handler_imports),
        ("Announcement Flow", test_announcement_conversation_flow),
        ("Trivia Flow", test_trivia_conversation_flow),
        ("DM Permissions", test_dm_command_permissions),
        ("Conversation Cleanup", test_conversation_cleanup),
        ("AI Enhancement", test_ai_content_enhancement),
        ("Announcement Formatting", test_announcement_formatting),
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
    print("📊 DM CONVERSATION TEST SUMMARY:")

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {test_name}")
        if result:
            passed += 1

    print(f"\nResults: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("🎉 All DM conversation tests passed!")
        print("\n✅ DM Functionality Validated:")
        print("   • !announceupdate command (interactive announcement creation)")
        print("   • !addtriviaquestion command (interactive trivia submission)")
        print("   • Permission checking and access control")
        print("   • Conversation state management and cleanup")
        print("   • AI content enhancement with fallback")
        print("   • Multi-format announcement generation")
        print("   • Complete conversation flow handling")
    else:
        print("⚠️ Some DM conversation tests failed. Review errors above.")

    return passed == len(tests)


if __name__ == "__main__":
    success = asyncio.run(run_dm_conversation_tests())
    sys.exit(0 if success else 1)
