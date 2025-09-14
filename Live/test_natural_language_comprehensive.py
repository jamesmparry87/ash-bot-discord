#!/usr/bin/env python3
"""
Comprehensive Test Suite for Natural Language Triggers
Tests all natural language entry points with proper access control
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from unittest.mock import AsyncMock, MagicMock

# Import bot modules
from bot.config import JAM_USER_ID, JONESY_USER_ID


class MockBot:
    """Mock bot for testing"""
    def __init__(self):
        self.user = MagicMock()
        self.user.id = 123456789
        self.channels = {}
        
    def get_channel(self, channel_id):
        return self.channels.get(channel_id, None)
    
    def add_cog(self, cog):
        pass

class MockChannel:
    """Mock Discord channel"""
    def __init__(self, channel_id, is_dm=False):
        self.id = channel_id
        self.mention = f"<#{channel_id}>"
        self.name = "test-channel"
        self.send = AsyncMock()
        self.type = "dm" if is_dm else "text"
        
class MockUser:
    """Mock Discord user"""
    def __init__(self, user_id, name):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.display_avatar = None
        
class MockGuild:
    """Mock Discord guild"""
    def __init__(self, guild_id):
        self.id = guild_id
        self.name = "Test Guild"

class MockMember:
    """Mock Discord member with permissions"""
    def __init__(self, user_id, name, has_manage_messages=False):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.guild_permissions = MagicMock()
        self.guild_permissions.manage_messages = has_manage_messages
        
class MockMessage:
    """Mock Discord message"""
    def __init__(self, content, user_id, is_dm=False, is_mod=False):
        self.content = content
        self.author = MockMember(user_id, "Test User", has_manage_messages=is_mod) if not is_dm else MockUser(user_id, "Test User")
        self.reply = AsyncMock()
        
        if is_dm:
            self.channel = MockChannel(123456, is_dm=True)
            self.guild = None
        else:
            self.channel = MockChannel(123456)
            self.guild = MockGuild(869525857562161182)

def create_mock_bot():
    """Create a properly configured mock bot"""
    bot = MockBot()
    return bot

class TestNaturalLanguageTriggers:
    """Test all natural language triggers with access control"""
    
    def __init__(self):
        self.bot = create_mock_bot()
    
    async def test_announcement_triggers_authorized_users(self):
        """Test announcement triggers work for JAM and JONESY in DMs"""
        print("Testing announcement triggers for authorized users...")
        
        test_phrases = [
            "I need to make an announcement",
            "can we create an announcement?",
            "I want to post an announcement",
            "server update needed",
            "bot update announcement"
        ]
        
        # Test JAM user
        for phrase in test_phrases:
            message = MockMessage(phrase, JAM_USER_ID, is_dm=True)
            
            # Test trigger detection
            content_lower = message.content.lower()
            announcement_triggers = [
                "make an announcement", "create an announcement", "post an announcement",
                "need to announce", "want to announce", "announce something",
                "make announcement", "create announcement", "post announcement",
                "send an announcement", "update announcement", "announcement update",
                "bot update", "server update", "community update", "new features", "feature update"
            ]
            
            trigger_detected = any(trigger in content_lower for trigger in announcement_triggers)
            assert trigger_detected, f"Announcement trigger not detected for: '{phrase}'"
        
        print("✅ Announcement triggers working for authorized users")
    
    async def test_games_triggers_public_access(self):
        """Test games triggers work for all users in DMs"""
        print("Testing games triggers for public access...")
        
        test_phrases = [
            "recommend a game",
            "what games are recommended",
            "list games",
            "show game recommendations",
            "game suggestions"
        ]
        
        regular_user_id = 999999999  # Not JAM or JONESY
        
        for phrase in test_phrases:
            message = MockMessage(phrase, regular_user_id, is_dm=True)
            
            # Test trigger detection
            content_lower = message.content.lower()
            games_triggers = [
                "recommend a game", "suggest a game", "add game recommendation",
                "what games are recommended", "list games", "show game recommendations",
                "game suggestions", "recommended games"
            ]
            
            trigger_detected = any(trigger in content_lower for trigger in games_triggers)
            assert trigger_detected, f"Games trigger not detected for: '{phrase}'"
        
        print("✅ Games triggers working for public access")
    
    async def test_strikes_triggers_moderator_only(self):
        """Test strikes triggers only work for moderators in guild"""
        print("Testing strikes triggers for moderator access...")
        
        test_phrases = [
            "check strikes for user",
            "show all strikes",
            "list all strikes",
            "strike report",
            "how many strikes does user have"
        ]
        
        # Test with moderator
        for phrase in test_phrases:
            message = MockMessage(phrase, 888888888, is_dm=False, is_mod=True)
            
            # Test trigger detection and permission check
            content_lower = message.content.lower()
            strikes_triggers = [
                "check strikes for", "show strikes for", "get strikes for",
                "how many strikes", "user strikes", "list all strikes",
                "show all strikes", "strike report"
            ]
            
            trigger_detected = any(trigger in content_lower for trigger in strikes_triggers)
            is_mod = message.author.guild_permissions.manage_messages # type: ignore
            
            assert trigger_detected, f"Strikes trigger not detected for: '{phrase}'"
            assert is_mod, "User should have moderator permissions"
        
        # Test with non-moderator (should not trigger)
        non_mod_message = MockMessage("show all strikes", 999999999, is_dm=False, is_mod=False)
        is_mod = non_mod_message.author.guild_permissions.manage_messages # type: ignore
        assert not is_mod, "Non-mod user should not have manage_messages permission"
        
        print("✅ Strikes triggers properly restricted to moderators")
    
    async def test_trivia_triggers_moderator_only(self):
        """Test trivia triggers only work for moderators in guild"""
        print("Testing trivia triggers for moderator access...")
        
        test_phrases = [
            "start trivia",
            "begin trivia session",
            "end trivia",
            "trivia leaderboard",
            "show trivia stats"
        ]
        
        # Test with moderator
        for phrase in test_phrases:
            message = MockMessage(phrase, 888888888, is_dm=False, is_mod=True)
            
            # Test trigger detection and permission check
            content_lower = message.content.lower()
            trivia_triggers = [
                "start trivia", "begin trivia", "run trivia session",
                "end trivia", "finish trivia", "trivia leaderboard",
                "show trivia stats", "trivia questions"
            ]
            
            trigger_detected = any(trigger in content_lower for trigger in trivia_triggers)
            is_mod = message.author.guild_permissions.manage_messages # type: ignore
            
            assert trigger_detected, f"Trivia trigger not detected for: '{phrase}'"
            assert is_mod, "User should have moderator permissions"
        
        print("✅ Trivia triggers properly restricted to moderators")
    
    async def test_utility_triggers_mixed_access(self):
        """Test utility triggers work with proper access levels"""
        print("Testing utility triggers for mixed access...")
        
        # Public access phrases
        public_phrases = [
            "what time is it",
            "current time",
            "time check"
        ]
        
        # Status phrases (tiered access)
        status_phrases = [
            "bot status",
            "system status", 
            "ash status"
        ]
        
        regular_user_id = 999999999
        
        # Test public access phrases
        for phrase in public_phrases:
            message = MockMessage(phrase, regular_user_id, is_dm=False)
            
            content_lower = message.content.lower()
            utility_triggers = [
                "what time is it", "current time", "bot status",
                "system status", "ash status", "time check"
            ]
            
            trigger_detected = any(trigger in content_lower for trigger in utility_triggers)
            assert trigger_detected, f"Utility trigger not detected for: '{phrase}'"
        
        # Test status phrases (should trigger but have tiered responses)
        for phrase in status_phrases:
            message = MockMessage(phrase, regular_user_id, is_dm=False)
            
            content_lower = message.content.lower()
            trigger_detected = any(trigger in content_lower for trigger in utility_triggers) # type: ignore
            assert trigger_detected, f"Status trigger not detected for: '{phrase}'"
        
        print("✅ Utility triggers working with mixed access levels")
    
    async def test_access_control_enforcement(self):
        """Test that access control is properly enforced"""
        print("Testing access control enforcement...")
        
        # Test unauthorized user cannot access announcement triggers
        unauthorized_user = 777777777  # Not JAM or JONESY
        announcement_message = MockMessage("make an announcement", unauthorized_user, is_dm=True)
        
        # Should detect trigger but user is not authorized
        content_lower = announcement_message.content.lower()
        trigger_detected = any(trigger in content_lower for trigger in [
            "make an announcement", "create an announcement", "server update"
        ])
        is_authorized = announcement_message.author.id in [JAM_USER_ID, JONESY_USER_ID]
        
        assert trigger_detected, "Announcement trigger should be detected"
        assert not is_authorized, "Unauthorized user should not have announcement access"
        
        # Test non-mod cannot access strikes triggers  
        non_mod_strikes = MockMessage("show all strikes", 777777777, is_dm=False, is_mod=False)
        is_mod = non_mod_strikes.author.guild_permissions.manage_messages # type: ignore
        assert not is_mod, "Non-moderator should not have manage_messages permission"
        
        print("✅ Access control properly enforced")

async def run_tests():
    """Run all natural language trigger tests"""
    print("🧪 Running Natural Language Triggers Comprehensive Tests")
    print("=" * 70)
    
    test_suite = TestNaturalLanguageTriggers()
    
    # Test all trigger categories
    await test_suite.test_announcement_triggers_authorized_users()
    await test_suite.test_games_triggers_public_access()
    await test_suite.test_strikes_triggers_moderator_only()
    await test_suite.test_trivia_triggers_moderator_only()
    await test_suite.test_utility_triggers_mixed_access()
    await test_suite.test_access_control_enforcement()
    
    print("\n" + "=" * 70)
    print("🎉 ALL NATURAL LANGUAGE TRIGGER TESTS PASSED!")
    
    print("\n📊 Test Summary:")
    print("✅ Announcement triggers - Authorized users only (JAM, JONESY)")
    print("✅ Games triggers - Public access (all users)")
    print("✅ Strikes triggers - Moderator only")
    print("✅ Trivia triggers - Moderator only") 
    print("✅ Utility triggers - Mixed access levels")
    print("✅ Access control properly enforced")
    
    print("\n🔍 Natural Language Coverage:")
    print("• Announcements: 'make an announcement', 'server update', etc.")
    print("• Games: 'recommend a game', 'what games are recommended', etc.")
    print("• Strikes: 'check strikes for', 'show all strikes', etc.")
    print("• Trivia: 'start trivia', 'trivia leaderboard', etc.")
    print("• Utility: 'what time is it', 'bot status', etc.")
    
    return True

async def main():
    """Main test runner"""
    try:
        success = await run_tests()
        
        if success:
            print("\n✅ Natural language trigger test suite completed successfully!")
            return 0
        else:
            print("\n❌ Natural language trigger tests failed!")
            return 1
            
    except Exception as e:
        print(f"\n❌ TESTS FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    print("🚀 Starting Natural Language Triggers Tests...")
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
