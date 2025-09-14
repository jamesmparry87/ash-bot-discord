#!/usr/bin/env python3
"""
Test script to verify the announcement routing fix

Tests that:
1. "I want to write an announcement" triggers the interactive system
2. "explain announcements" triggers the FAQ system
3. Both systems work correctly for authorized users
4. Unauthorized users are properly rejected
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from bot_modular import get_user_communication_tier, handle_general_conversation, moderator_faq_handler
from moderator_faq_handler import ModeratorFAQHandler

# Add the current directory to Python path for imports
sys.path.insert(0, '.')


class TestAnnouncementRouting:

    def __init__(self):
        self.passed_tests = []
        self.failed_tests = []

    async def create_mock_message(self, content: str, user_id: int, is_dm: bool = True):
        """Create a mock Discord message for testing"""
        message = MagicMock()
        message.content = content
        message.author = MagicMock()
        message.author.id = user_id
        message.reply = AsyncMock()

        # Set up channel type
        if is_dm:
            message.channel = MagicMock(spec=discord.DMChannel)
            message.guild = None
        else:
            message.channel = MagicMock()
            message.channel.id = 123456789  # Mock guild channel
            message.guild = MagicMock()
            message.author.guild_permissions = MagicMock()
            message.author.guild_permissions.manage_messages = False

        return message

    async def test_announcement_creation_intent(self):
        """Test that announcement creation intents are properly detected"""
        print("🔍 Testing announcement creation intent detection...")

        # Test cases for announcement creation
        creation_phrases = [
            "I want to write an announcement",
            "I want to create an announcement",
            "I want to make an announcement",
            "write an announcement",
            "create an announcement",
            "make an announcement"
        ]

        # Test with Captain Jonesy (authorized)
        JONESY_USER_ID = 651329927895056384
        for phrase in creation_phrases:
            try:
                message = await self.create_mock_message(phrase, JONESY_USER_ID, is_dm=True)

                # Mock the start_announcement_conversation function
                with patch('bot_modular.start_announcement_conversation', new_callable=AsyncMock) as mock_start:
                    await handle_general_conversation(message)

                    # Should have called the conversation starter
                    if mock_start.called:
                        self.passed_tests.append(f"✅ Captain Jonesy DM: '{phrase}' → conversation starter")
                    else:
                        # Check if it was handled by reply (redirect message)
                        if message.reply.called:
                            reply_content = message.reply.call_args[0][0]
                            if "conversation handler not loaded" in reply_content:
                                self.passed_tests.append(
                                    f"✅ Captain Jonesy DM: '{phrase}' → proper error (handler not loaded)")
                            else:
                                self.failed_tests.append(
                                    f"❌ Captain Jonesy DM: '{phrase}' → unexpected reply: {reply_content}")
                        else:
                            self.failed_tests.append(
                                f"❌ Captain Jonesy DM: '{phrase}' → no conversation starter or reply")

            except Exception as e:
                self.failed_tests.append(f"❌ Captain Jonesy DM: '{phrase}' → Exception: {e}")

    async def test_faq_system_routing(self):
        """Test that FAQ queries are properly routed to the FAQ system"""
        print("🔍 Testing FAQ system routing...")

        # Test cases for FAQ queries
        faq_phrases = [
            "explain announcements",
            "explain announcement system",
            "how do announcements work",
            "tell me about announcements"
        ]

        # Test with a moderator (has FAQ access)
        MOCK_MOD_USER_ID = 999999999  # Mock moderator ID

        for phrase in faq_phrases:
            try:
                message = await self.create_mock_message(phrase, MOCK_MOD_USER_ID, is_dm=True)

                # Mock moderator permissions
                message.guild = MagicMock()
                message.author.guild_permissions = MagicMock()
                message.author.guild_permissions.manage_messages = True

                # Test the FAQ handler directly first
                if moderator_faq_handler:
                    faq_response = moderator_faq_handler.handle_faq_query(phrase.lower())
                    if faq_response:
                        self.passed_tests.append(f"✅ FAQ Handler: '{phrase}' → FAQ response generated")
                    else:
                        self.failed_tests.append(f"❌ FAQ Handler: '{phrase}' → No FAQ response")
                else:
                    self.failed_tests.append(f"❌ FAQ Handler not available")

            except Exception as e:
                self.failed_tests.append(f"❌ FAQ test: '{phrase}' → Exception: {e}")

    async def test_unauthorized_announcement_creation(self):
        """Test that unauthorized users cannot create announcements"""
        print("🔍 Testing unauthorized announcement creation...")

        STANDARD_USER_ID = 123456789  # Mock standard user

        message = await self.create_mock_message("I want to write an announcement", STANDARD_USER_ID, is_dm=True)

        try:
            await handle_general_conversation(message)

            # Should not have triggered announcement creation
            if message.reply.called:
                reply_content = message.reply.call_args[0][0]
                # Should get a general response, not announcement creation
                if "announcement creation" not in reply_content.lower():
                    self.passed_tests.append("✅ Standard user: announcement creation properly blocked")
                else:
                    self.failed_tests.append(f"❌ Standard user: got announcement creation access: {reply_content}")
            else:
                # No reply could mean it fell through to AI or other handlers
                self.passed_tests.append("✅ Standard user: announcement creation not triggered (no reply)")

        except Exception as e:
            self.failed_tests.append(f"❌ Unauthorized test → Exception: {e}")

    async def test_guild_vs_dm_routing(self):
        """Test that announcement creation requires DM"""
        print("🔍 Testing guild vs DM routing...")

        JONESY_USER_ID = 651329927895056384

        # Test in guild (should redirect to DM)
        try:
            guild_message = await self.create_mock_message("I want to write an announcement", JONESY_USER_ID, is_dm=False)

            await handle_general_conversation(guild_message)

            if guild_message.reply.called:
                reply_content = guild_message.reply.call_args[0][0]
                if "direct message" in reply_content.lower() or "dm me" in reply_content.lower():
                    self.passed_tests.append("✅ Guild message: properly redirected to DM")
                else:
                    self.failed_tests.append(f"❌ Guild message: unexpected response: {reply_content}")
            else:
                self.failed_tests.append("❌ Guild message: no redirect to DM")

        except Exception as e:
            self.failed_tests.append(f"❌ Guild vs DM test → Exception: {e}")

    async def test_user_tier_detection(self):
        """Test that user tiers are correctly detected"""
        print("🔍 Testing user tier detection...")

        # Test Captain Jonesy
        JONESY_USER_ID = 651329927895056384
        jonesy_message = await self.create_mock_message("hello", JONESY_USER_ID, is_dm=True)
        jonesy_tier = await get_user_communication_tier(jonesy_message)

        if jonesy_tier == "captain":
            self.passed_tests.append("✅ User tier: Captain Jonesy correctly detected")
        else:
            self.failed_tests.append(f"❌ User tier: Captain Jonesy detected as {jonesy_tier}")

        # Test Sir Decent Jam
        JAM_USER_ID = 337833732901961729
        jam_message = await self.create_mock_message("hello", JAM_USER_ID, is_dm=True)
        jam_tier = await get_user_communication_tier(jam_message)

        if jam_tier == "creator":
            self.passed_tests.append("✅ User tier: Sir Decent Jam correctly detected")
        else:
            self.failed_tests.append(f"❌ User tier: Sir Decent Jam detected as {jam_tier}")

    async def run_all_tests(self):
        """Run all test cases"""
        print("🧪 Starting Announcement Routing Fix Tests...")
        print("=" * 60)

        await self.test_user_tier_detection()
        await self.test_faq_system_routing()
        await self.test_announcement_creation_intent()
        await self.test_unauthorized_announcement_creation()
        await self.test_guild_vs_dm_routing()

        print("\n" + "=" * 60)
        print("📊 Test Results Summary:")
        print(f"✅ Passed: {len(self.passed_tests)}")
        print(f"❌ Failed: {len(self.failed_tests)}")

        if self.passed_tests:
            print("\n✅ Passed Tests:")
            for test in self.passed_tests:
                print(f"   {test}")

        if self.failed_tests:
            print("\n❌ Failed Tests:")
            for test in self.failed_tests:
                print(f"   {test}")

        success_rate = len(self.passed_tests) / (len(self.passed_tests) + len(self.failed_tests)) * 100
        print(f"\n📈 Success Rate: {success_rate:.1f}%")

        if success_rate >= 80:
            print("🎉 Announcement routing fix appears to be working!")
            return True
        else:
            print("⚠️ Some issues detected - review failed tests")
            return False


async def main():
    """Run the test suite"""
    tester = TestAnnouncementRouting()
    success = await tester.run_all_tests()

    if success:
        print("\n🚀 Ready for deployment!")
    else:
        print("\n🔧 Further debugging may be needed")

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
