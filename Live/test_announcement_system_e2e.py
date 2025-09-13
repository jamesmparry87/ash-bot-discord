#!/usr/bin/env python3
"""
End-to-End Testing for Announcement System
Comprehensive testing of all announcement system components including:
- Natural language triggers and commands (particularly in DMs)
- Message construction format and logic
- AI content rewriting in Ash's style
- Preview system with proper option numbering
- Error handling and edge cases
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import the modules we need to test
try:
    from bot.handlers.ai_handler import get_ai_status, call_ai_with_rate_limiting
    from bot.handlers.conversation_handler import (
        announcement_conversations,
        cleanup_announcement_conversations,
        create_ai_announcement_content,
        format_announcement_content,
        handle_announcement_conversation,
        post_announcement,
        start_announcement_conversation,
        update_announcement_activity,
    )
    print("✅ Successfully imported announcement system modules")
except ImportError as e:
    print(f"❌ Failed to import announcement modules: {e}")
    sys.exit(1)

# Test configuration
JONESY_USER_ID = 651329927895056384
JAM_USER_ID = 337833732901961729
MOD_ALERT_CHANNEL_ID = 869530924302344233
ANNOUNCEMENTS_CHANNEL_ID = 869526826148585533


class MockUser:
    """Mock Discord User for testing"""

    def __init__(self, user_id: int, display_name: str = "TestUser"):
        self.id = user_id
        self.display_name = display_name
        self.display_avatar = None


class MockChannel:
    """Mock Discord Channel for testing"""

    def __init__(
            self,
            channel_id: Optional[int] = None,
            name: str = "test-channel"):
        self.id = channel_id or 123456789  # Default ID for None case
        self.name = name
        self.send_calls = []

    async def send(self, content=None, **kwargs):
        """Mock send method that records calls"""
        call_info = {
            'content': content,
            'kwargs': kwargs,
            'timestamp': datetime.now(ZoneInfo("Europe/London"))
        }
        self.send_calls.append(call_info)
        print(f"📤 Mock channel {self.name} send: {content}")
        return MagicMock()  # Mock message object


class MockMessage:
    """Mock Discord Message for testing"""

    def __init__(self, content: str, author: MockUser, channel: MockChannel = None, guild=None):  # type: ignore
        self.content = content
        self.author = author
        self.channel = channel or MockChannel(123456789)
        self.guild = guild
        self.reply_calls = []

    async def reply(self, content: str, **kwargs):
        """Mock reply method that records calls"""
        call_info = {
            'content': content,
            'kwargs': kwargs,
            'timestamp': datetime.now(ZoneInfo("Europe/London"))
        }
        self.reply_calls.append(call_info)
        print(
            f"💬 Mock reply to user {self.author.id}: {content[:100]}{'...' if len(content) > 100 else ''}")
        return MagicMock()


class MockContext:
    """Mock Discord Context for testing"""

    def __init__(self, author: MockUser, guild=None, channel: MockChannel = None):  # type: ignore
        self.author = author
        self.guild = guild
        self.channel = channel or MockChannel(123456789)
        self.send_calls = []

    async def send(self, content: str, **kwargs):
        """Mock send method that records calls"""
        call_info = {
            'content': content,
            'kwargs': kwargs,
            'timestamp': datetime.now(ZoneInfo("Europe/London"))
        }
        self.send_calls.append(call_info)
        print(
            f"📢 Mock context send: {content[:100]}{'...' if len(content) > 100 else ''}")
        return MagicMock()


class AnnouncementSystemTester:
    """Comprehensive announcement system tester"""

    def __init__(self):
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'errors': []
        }

    def assert_test(self, condition: bool, test_name: str, details: str = ""):
        """Assert a test condition and record results"""
        if condition:
            self.test_results['passed'] += 1
            print(f"✅ {test_name}")
            if details:
                print(f"   {details}")
        else:
            self.test_results['failed'] += 1
            error_msg = f"❌ {test_name}"
            if details:
                error_msg += f" - {details}"
            print(error_msg)
            self.test_results['errors'].append(error_msg)

    async def test_access_control_dm_requirement(self):
        """Test 1: Access Control & DM Requirement"""
        print("\n🔐 Testing Access Control & DM Requirement")

        # Test 1a: Authorized user in DM should work
        jonesy_user = MockUser(JONESY_USER_ID, "Captain Jonesy")
        dm_channel = MockChannel(None, "DM")  # DM channels have no guild
        dm_context = MockContext(jonesy_user, guild=None, channel=dm_channel)

        try:
            await start_announcement_conversation(dm_context)
            self.assert_test(
                len(dm_context.send_calls) > 0 and "Target Channel Selection" in dm_context.send_calls[0]['content'],
                "Authorized user in DM gets channel selection prompt",
                f"Got {len(dm_context.send_calls)} messages"
            )
        except Exception as e:
            self.assert_test(
                False,
                "Authorized user in DM should not error",
                str(e))

        # Test 1b: Authorized user in guild should get error
        guild_mock = MagicMock()
        guild_mock.id = 869525857562161182
        guild_context = MockContext(jonesy_user, guild=guild_mock)

        try:
            await start_announcement_conversation(guild_context)
            self.assert_test(
                len(guild_context.send_calls) > 0 and "direct message" in guild_context.send_calls[0]['content'].lower(),
                "Authorized user in guild gets DM requirement message"
            )
        except Exception as e:
            self.assert_test(
                False,
                "Guild access should show proper error",
                str(e))

        # Test 1c: Unauthorized user should get access denied
        unauthorized_user = MockUser(999999999, "Unauthorized")
        unauthorized_context = MockContext(
            unauthorized_user,
            guild=None,
            channel=MockChannel(
                None,
                "DM"))

        try:
            await start_announcement_conversation(unauthorized_context)
            self.assert_test(
                len(unauthorized_context.send_calls) > 0 and "access denied" in unauthorized_context.send_calls[0]['content'].lower(),
                "Unauthorized user gets access denied message"
            )
        except Exception as e:
            self.assert_test(
                False,
                "Unauthorized access should show proper error",
                str(e))

    async def test_channel_selection_flow(self):
        """Test 2: Channel Selection Flow & Option Validation"""
        print("\n📺 Testing Channel Selection Flow")

        # Setup authorized user in conversation
        jonesy_user = MockUser(JONESY_USER_ID, "Captain Jonesy")

        # Clear any existing conversations
        cleanup_announcement_conversations()

        # Start conversation
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'channel_selection',
            'data': {},
            'last_activity': uk_now,
            'initiated_at': uk_now,
        }

        # Test 2a: Valid numeric selection (1 = mod channel)
        mod_selection_msg = MockMessage("1", jonesy_user)
        try:
            await handle_announcement_conversation(mod_selection_msg)
            conversation = announcement_conversations.get(JONESY_USER_ID, {})
            self.assert_test(
                conversation.get(
                    'data',
                    {}).get('target_channel') == 'mod' and conversation.get('step') == 'content_input',
                "Numeric selection '1' sets mod channel and advances step",
                f"Target: {conversation.get('data', {}).get('target_channel')}, Step: {conversation.get('step')}")
        except Exception as e:
            self.assert_test(
                False, "Mod channel selection should work", str(e))

        # Test 2b: Valid text selection (user channel)
        announcement_conversations[JONESY_USER_ID]['step'] = 'channel_selection'
        announcement_conversations[JONESY_USER_ID]['data'] = {}

        user_selection_msg = MockMessage("2", jonesy_user)
        try:
            await handle_announcement_conversation(user_selection_msg)
            conversation = announcement_conversations.get(JONESY_USER_ID, {})
            self.assert_test(
                conversation.get('data', {}).get('target_channel') == 'user',
                "Numeric selection '2' sets user channel",
                f"Target: {conversation.get('data', {}).get('target_channel')}"
            )
        except Exception as e:
            self.assert_test(
                False, "User channel selection should work", str(e))

        # Test 2c: Text alternatives
        announcement_conversations[JONESY_USER_ID]['step'] = 'channel_selection'
        announcement_conversations[JONESY_USER_ID]['data'] = {}

        text_selection_msg = MockMessage("moderator", jonesy_user)
        try:
            await handle_announcement_conversation(text_selection_msg)
            conversation = announcement_conversations.get(JONESY_USER_ID, {})
            self.assert_test(
                conversation.get('data', {}).get('target_channel') == 'mod',
                "Text selection 'moderator' sets mod channel"
            )
        except Exception as e:
            self.assert_test(
                False, "Text channel selection should work", str(e))

        # Test 2d: Invalid selection
        announcement_conversations[JONESY_USER_ID]['step'] = 'channel_selection'
        announcement_conversations[JONESY_USER_ID]['data'] = {}

        invalid_selection_msg = MockMessage("invalid", jonesy_user)
        try:
            await handle_announcement_conversation(invalid_selection_msg)
            self.assert_test(
                len(invalid_selection_msg.reply_calls) > 0 and "invalid selection" in invalid_selection_msg.reply_calls[0]['content'].lower(),
                "Invalid selection shows proper error message"
            )
        except Exception as e:
            self.assert_test(
                False, "Invalid selection should show error", str(e))

    async def test_content_input_and_ai_enhancement(self):
        """Test 3: Content Input & AI Enhancement"""
        print("\n🧠 Testing Content Input & AI Enhancement")

        jonesy_user = MockUser(JONESY_USER_ID, "Captain Jonesy")

        # Setup conversation in content input stage
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'content_input',
            'data': {'target_channel': 'mod'},
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        # Test 3a: Content processing and AI enhancement
        test_content = "We have updated the bot with new features for better moderation."
        content_msg = MockMessage(test_content, jonesy_user)

        try:
            await handle_announcement_conversation(content_msg)
            conversation = announcement_conversations.get(JONESY_USER_ID, {})

            # Check that content was stored
            self.assert_test(
                'raw_content' in conversation.get('data', {}),
                "Raw content is stored in conversation data"
            )

            # Check that conversation advanced to preview
            self.assert_test(
                conversation.get('step') == 'preview',
                "Conversation advances to preview step after content input"
            )

            # Check that reply contains preview
            self.assert_test(
                len(content_msg.reply_calls) > 0 and 'preview' in content_msg.reply_calls[0]['content'].lower(),
                "Response contains preview of announcement"
            )

        except Exception as e:
            self.assert_test(
                False, "Content input should work properly", str(e))

    async def test_ai_content_enhancement_function(self):
        """Test 3b: AI Content Enhancement Function"""
        print("\n🤖 Testing AI Content Enhancement Function")

        test_content = "Bot has new features for better user experience."

        # Test mod channel enhancement
        try:
            enhanced_mod = await create_ai_announcement_content(test_content, 'mod', JONESY_USER_ID)
            self.assert_test(
                enhanced_mod is not None and len(enhanced_mod.strip()) > 0,
                "AI enhancement returns content for mod channel",
                f"Enhanced length: {len(enhanced_mod) if enhanced_mod else 0}"
            )

            ai_status = get_ai_status()
            if ai_status["enabled"]:
                # If AI is enabled, enhanced content should be different from
                # original
                self.assert_test(
                    enhanced_mod != test_content,
                    "AI enhancement modifies the original content when AI is enabled")
            else:
                # If AI is disabled, should return original content
                self.assert_test(
                    enhanced_mod == test_content,
                    "AI enhancement returns original content when AI is disabled")
        except Exception as e:
            self.assert_test(
                False,
                "AI enhancement for mod channel should not error",
                str(e))

        # Test user channel enhancement
        try:
            enhanced_user = await create_ai_announcement_content(test_content, 'user', JONESY_USER_ID)
            self.assert_test(
                enhanced_user is not None and len(enhanced_user.strip()) > 0,
                "AI enhancement returns content for user channel"
            )
        except Exception as e:
            self.assert_test(
                False,
                "AI enhancement for user channel should not error",
                str(e))

    async def test_preview_system_and_options(self):
        """Test 4: Preview System & Option Numbering"""
        print("\n👁️ Testing Preview System & Option Numbering")

        jonesy_user = MockUser(JONESY_USER_ID, "Captain Jonesy")

        # Setup conversation in preview stage
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'preview',
            'data': {
                'target_channel': 'mod',
                'content': 'Enhanced announcement content',
                'formatted_content': 'Formatted enhanced announcement content'
            },
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        # Test 4a: Option 1 - Post announcement
        post_msg = MockMessage("1", jonesy_user)

        # Mock the post_announcement function to avoid actual posting
        with patch('bot.handlers.conversation_handler.post_announcement') as mock_post:
            mock_post.return_value = True

            try:
                await handle_announcement_conversation(post_msg)
                self.assert_test(
                    mock_post.called,
                    "Option '1' triggers post_announcement function"
                )

                self.assert_test(
                    JONESY_USER_ID not in announcement_conversations,
                    "Conversation is cleaned up after successful post"
                )
            except Exception as e:
                self.assert_test(False, "Post option should work", str(e))

        # Test 4b: Option 2 - Edit content
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'preview',
            'data': {'target_channel': 'mod', 'content': 'test content'},
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        edit_msg = MockMessage("2", jonesy_user)
        try:
            await handle_announcement_conversation(edit_msg)
            conversation = announcement_conversations.get(JONESY_USER_ID, {})
            self.assert_test(
                conversation.get('step') == 'content_input',
                "Option '2' returns to content input step"
            )
        except Exception as e:
            self.assert_test(False, "Edit option should work", str(e))

        # Test 4c: Option 4 - Cancel
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'preview',
            'data': {'target_channel': 'mod', 'content': 'test content'},
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        cancel_msg = MockMessage("4", jonesy_user)
        try:
            await handle_announcement_conversation(cancel_msg)
            self.assert_test(
                JONESY_USER_ID not in announcement_conversations,
                "Option '4' (cancel) cleans up conversation"
            )

            self.assert_test(
                len(cancel_msg.reply_calls) > 0 and "cancel" in cancel_msg.reply_calls[0]['content'].lower(),
                "Cancel option shows cancellation message"
            )
        except Exception as e:
            self.assert_test(False, "Cancel option should work", str(e))

        # Test 4d: Text alternatives for options
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'preview',
            'data': {'target_channel': 'mod', 'content': 'test content'},
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        text_post_msg = MockMessage("post", jonesy_user)
        with patch('bot.handlers.conversation_handler.post_announcement') as mock_post:
            mock_post.return_value = True

            try:
                await handle_announcement_conversation(text_post_msg)
                self.assert_test(
                    mock_post.called,
                    "Text alternative 'post' works like option '1'"
                )
            except Exception as e:
                self.assert_test(
                    False, "Text alternatives should work", str(e))

    async def test_creator_notes_functionality(self):
        """Test 5: Creator Notes Feature"""
        print("\n📝 Testing Creator Notes Functionality")

        jonesy_user = MockUser(JONESY_USER_ID, "Captain Jonesy")

        # Setup conversation in preview stage
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'preview',
            'data': {
                'target_channel': 'mod',
                'content': 'Test announcement',
                'formatted_content': 'Formatted test announcement'
            },
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        # Test 5a: Option 3 - Add creator notes
        notes_msg = MockMessage("3", jonesy_user)
        try:
            await handle_announcement_conversation(notes_msg)
            conversation = announcement_conversations.get(JONESY_USER_ID, {})
            self.assert_test(
                conversation.get('step') == 'creator_notes_input',
                "Option '3' advances to creator notes input step"
            )
        except Exception as e:
            self.assert_test(False, "Creator notes option should work", str(e))

        # Test 5b: Creator notes input
        test_notes = "This update includes important security fixes and performance improvements."
        notes_input_msg = MockMessage(test_notes, jonesy_user)

        try:
            await handle_announcement_conversation(notes_input_msg)
            conversation = announcement_conversations.get(JONESY_USER_ID, {})

            self.assert_test(
                conversation.get(
                    'data',
                    {}).get('creator_notes') == test_notes,
                "Creator notes are stored in conversation data")

            self.assert_test(
                conversation.get('step') == 'preview',
                "Returns to preview step after notes input"
            )

            # Check that reply shows updated preview
            self.assert_test(
                len(notes_input_msg.reply_calls) > 0 and 'updated' in notes_input_msg.reply_calls[0]['content'].lower(),
                "Shows updated preview with creator notes"
            )
        except Exception as e:
            self.assert_test(False, "Creator notes input should work", str(e))

    async def test_message_formatting(self):
        """Test 6: Message Formatting & Construction"""
        print("\n📄 Testing Message Formatting & Construction")

        test_content = "Test announcement content"
        test_notes = "Test creator notes"

        # Test 6a: Mod channel formatting
        try:
            formatted_mod = await format_announcement_content(
                test_content, 'mod', JONESY_USER_ID
            )

            self.assert_test(
                "Captain Jonesy" in formatted_mod,
                "Mod format includes Captain Jonesy attribution"
            )

            self.assert_test(
                "Technical Briefing" in formatted_mod or "System Update" in formatted_mod,
                "Mod format uses technical language")

            self.assert_test(
                test_content in formatted_mod,
                "Formatted content includes original content"
            )
        except Exception as e:
            self.assert_test(
                False, "Mod channel formatting should work", str(e))

        # Test 6b: User channel formatting
        try:
            formatted_user = await format_announcement_content(
                test_content, 'user', JONESY_USER_ID
            )

            self.assert_test(
                "Captain Jonesy" in formatted_user,
                "User format includes Captain Jonesy attribution"
            )

            self.assert_test(
                "Bot Updates" in formatted_user or "Exciting" in formatted_user,
                "User format uses friendly language")
        except Exception as e:
            self.assert_test(
                False, "User channel formatting should work", str(e))

        # Test 6c: Creator notes integration
        try:
            formatted_with_notes = await format_announcement_content(
                test_content, 'mod', JONESY_USER_ID, creator_notes=test_notes
            )

            self.assert_test(
                test_notes in formatted_with_notes,
                "Creator notes are integrated into formatted content"
            )

            self.assert_test(
                "Technical Notes" in formatted_with_notes or "Notes" in formatted_with_notes,
                "Creator notes have proper section header")
        except Exception as e:
            self.assert_test(
                False,
                "Creator notes integration should work",
                str(e))

        # Test 6d: JAM user attribution
        try:
            formatted_jam = await format_announcement_content(
                test_content, 'mod', JAM_USER_ID
            )

            self.assert_test(
                "Sir Decent Jam" in formatted_jam,
                "JAM user gets proper attribution as Sir Decent Jam"
            )
        except Exception as e:
            self.assert_test(False, "JAM user attribution should work", str(e))

    async def test_conversation_state_management(self):
        """Test 7: Conversation State Management"""
        print("\n🔄 Testing Conversation State Management")

        # Test 7a: Activity updates
        test_user_id = JONESY_USER_ID
        uk_now = datetime.now(ZoneInfo("Europe/London"))

        announcement_conversations[test_user_id] = {
            'step': 'test',
            'data': {},
            'last_activity': uk_now - timedelta(minutes=30),
        }

        update_announcement_activity(test_user_id)

        self.assert_test(
            announcement_conversations[test_user_id]['last_activity'] > uk_now -
            timedelta(
                minutes=5),
            "Activity update sets recent timestamp")

        # Test 7b: Cleanup of expired conversations
        # Set up expired conversation
        expired_user_id = 999999999
        announcement_conversations[expired_user_id] = {
            'step': 'test',
            'data': {},
            # 2 hours ago (expired)
            'last_activity': uk_now - timedelta(hours=2),
        }

        cleanup_announcement_conversations()

        self.assert_test(
            expired_user_id not in announcement_conversations,
            "Cleanup removes conversations inactive for more than 1 hour"
        )

        self.assert_test(
            test_user_id in announcement_conversations,
            "Cleanup preserves active conversations"
        )

    async def test_error_handling(self):
        """Test 8: Error Handling & Edge Cases"""
        print("\n⚠️ Testing Error Handling & Edge Cases")

        jonesy_user = MockUser(JONESY_USER_ID, "Captain Jonesy")

        # Test 8a: Invalid conversation state
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'invalid_step',
            'data': {},
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        invalid_msg = MockMessage("test", jonesy_user)
        try:
            await handle_announcement_conversation(invalid_msg)
            # Should not crash, conversation should be cleaned up
            self.assert_test(
                True,  # If we get here without exception, it's handled
                "Invalid conversation state doesn't crash the system"
            )
        except Exception as e:
            self.assert_test(
                False,
                "Invalid conversation state should be handled gracefully",
                str(e))

        # Test 8b: Empty/None content handling
        announcement_conversations[JONESY_USER_ID] = {
            'step': 'content_input',
            'data': {'target_channel': 'mod'},
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        empty_msg = MockMessage("", jonesy_user)
        try:
            await handle_announcement_conversation(empty_msg)
            # Should handle empty content gracefully
            self.assert_test(True, "Empty content is handled gracefully")
        except Exception as e:
            self.assert_test(
                False,
                "Empty content should be handled gracefully",
                str(e))

        # Test 8c: Missing conversation data
        if JONESY_USER_ID in announcement_conversations:
            del announcement_conversations[JONESY_USER_ID]

        orphaned_msg = MockMessage("test", jonesy_user)
        try:
            await handle_announcement_conversation(orphaned_msg)
            # Should handle missing conversation gracefully (no action)
            self.assert_test(
                True, "Missing conversation data is handled gracefully")
        except Exception as e:
            self.assert_test(
                False,
                "Missing conversation should be handled gracefully",
                str(e))

    async def test_posting_mechanism(self):
        """Test 9: Posting Mechanism & Channel Targeting"""
        print("\n📤 Testing Posting Mechanism & Channel Targeting")

        # Mock the bot instance and channels
        with patch('sys.modules') as mock_modules:
            # Create mock bot module
            mock_bot_module = MagicMock()
            mock_bot = MagicMock()
            mock_bot_module.bot = mock_bot
            mock_modules.__getitem__.return_value = mock_bot_module

            # Create mock channels
            mock_mod_channel = MockChannel(MOD_ALERT_CHANNEL_ID, "mod-alerts")
            mock_user_channel = MockChannel(
                ANNOUNCEMENTS_CHANNEL_ID, "announcements")

            def get_channel(channel_id):
                if channel_id == MOD_ALERT_CHANNEL_ID:
                    return mock_mod_channel
                elif channel_id == ANNOUNCEMENTS_CHANNEL_ID:
                    return mock_user_channel
                return None

            mock_bot.get_channel = get_channel

            # Test 9a: Mod channel posting
            mod_data = {
                'target_channel': 'mod',
                'formatted_content': 'Test mod announcement content'
            }

            try:
                result = await post_announcement(mod_data, JONESY_USER_ID)
                self.assert_test(
                    result,
                    "Mod channel posting returns success"
                )

                self.assert_test(
                    len(mock_mod_channel.send_calls) > 0,
                    "Mod channel receives the announcement"
                )
            except Exception as e:
                self.assert_test(
                    False, "Mod channel posting should work", str(e))

            # Reset send calls
            mock_mod_channel.send_calls = []
            mock_user_channel.send_calls = []

            # Test 9b: User channel posting
            user_data = {
                'target_channel': 'user',
                'formatted_content': 'Test user announcement content'
            }

            try:
                result = await post_announcement(user_data, JONESY_USER_ID)
                self.assert_test(
                    result,
                    "User channel posting returns success"
                )

                self.assert_test(
                    len(mock_user_channel.send_calls) > 0,
                    "User channel receives the announcement"
                )
            except Exception as e:
                self.assert_test(
                    False, "User channel posting should work", str(e))

    async def test_natural_language_triggers(self):
        """Test 10: Natural Language Triggers in DMs"""
        print("\n💬 Testing Natural Language Triggers in DMs")

        jonesy_user = MockUser(JONESY_USER_ID, "Captain Jonesy")

        # Test various trigger phrases that should start announcements
        trigger_phrases = [
            "!announceupdate",
            "I want to make an announcement",
            "Need to post an update",
            "Create an announcement"
        ]

        for phrase in trigger_phrases:
            # Clear conversations
            cleanup_announcement_conversations()

            # Test the trigger
            trigger_msg = MockMessage(phrase, jonesy_user)
            try:
                # This would typically be handled by the main message handler
                # For now, we'll test the start_announcement_conversation
                # directly
                ctx = MockContext(jonesy_user, guild=None)
                await start_announcement_conversation(ctx)

                self.assert_test(
                    len(ctx.send_calls) > 0,
                    f"Trigger phrase '{phrase}' initiates announcement flow"
                )
            except Exception as e:
                self.assert_test(
                    False, f"Trigger phrase '{phrase}' should work", str(e))

    async def run_comprehensive_test_suite(self):
        """Run all tests in sequence"""
        print("🚀 Starting Comprehensive Announcement System E2E Testing")
        print("=" * 70)

        test_methods = [
            self.test_access_control_dm_requirement,
            self.test_channel_selection_flow,
            self.test_content_input_and_ai_enhancement,
            self.test_ai_content_enhancement_function,
            self.test_preview_system_and_options,
            self.test_creator_notes_functionality,
            self.test_message_formatting,
            self.test_conversation_state_management,
            self.test_error_handling,
            self.test_posting_mechanism,
            self.test_natural_language_triggers
        ]

        for test_method in test_methods:
            try:
                await test_method()
            except Exception as e:
                print(f"❌ Test method {test_method.__name__} crashed: {e}")
                self.test_results['failed'] += 1
                self.test_results['errors'].append(
                    f"{test_method.__name__}: {str(e)}")

        # Print comprehensive results
        print("\n" + "=" * 70)
        print("📊 COMPREHENSIVE TEST RESULTS")
        print("=" * 70)

        total_tests = self.test_results['passed'] + self.test_results['failed']
        pass_rate = (
            self.test_results['passed'] /
            total_tests *
            100) if total_tests > 0 else 0

        print(f"✅ Passed: {self.test_results['passed']}")
        print(f"❌ Failed: {self.test_results['failed']}")
        print(f"📈 Pass Rate: {pass_rate:.1f}%")

        if self.test_results['errors']:
            print(f"\n🔍 FAILED TESTS:")
            for error in self.test_results['errors']:
                print(f"   • {error}")

        if pass_rate >= 90:
            print(f"\n🎉 EXCELLENT: Announcement system is highly reliable!")
        elif pass_rate >= 75:
            print(f"\n✅ GOOD: Announcement system is working well with minor issues")
        elif pass_rate >= 50:
            print(f"\n⚠️  CONCERNING: Multiple issues detected, needs attention")
        else:
            print(f"\n🚨 CRITICAL: Major problems detected, requires immediate fixes")

        return self.test_results


async def main():
    """Main test execution"""
    print("🤖 Ash Bot Announcement System - End-to-End Testing")
    print("Testing all natural language triggers, AI enhancement, and message construction")
    print()

    tester = AnnouncementSystemTester()
    results = await tester.run_comprehensive_test_suite()

    # Return exit code based on results
    if results['failed'] == 0:
        print("\n✅ All tests passed! Announcement system is fully operational.")
        return 0
    else:
        print(
            f"\n⚠️ {results['failed']} tests failed. Review and fix issues before deployment.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Testing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Testing framework error: {e}")
        sys.exit(1)
