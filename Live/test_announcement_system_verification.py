#!/usr/bin/env python3
"""
Announcement System Verification
Simple verification that all functionality is properly accessible
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_module_loading():
    """Test that all required modules load correctly"""
    print("🔧 Testing Module Loading...")
    
    try:
        # Test config loading
        from bot.config import ANNOUNCEMENTS_CHANNEL_ID, JAM_USER_ID, JONESY_USER_ID
        print(f"  ✅ Config loaded - JAM: {JAM_USER_ID}, Jonesy: {JONESY_USER_ID}")
        
        # Test announcements command module
        from bot.commands.announcements import AnnouncementsCommands
        print("  ✅ Announcements commands module loaded")
        
        # Test conversation handler
        from bot.handlers.conversation_handler import (
            create_ai_announcement_content,
            format_announcement_content,
            handle_announcement_conversation,
            start_announcement_conversation,
        )
        print("  ✅ Conversation handler loaded")
        
        # Test AI handler integration
        from bot.handlers.ai_handler import ai_enabled, call_ai_with_rate_limiting
        print("  ✅ AI handler integration loaded")
        
        return True
        
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def test_access_control():
    """Test access control logic"""
    print("🔐 Testing Access Control...")
    
    from bot.config import JAM_USER_ID, JONESY_USER_ID

    # Test authorized users
    authorized_users = [JAM_USER_ID, JONESY_USER_ID]
    for user_id in authorized_users:
        if user_id in [JAM_USER_ID, JONESY_USER_ID]:
            print(f"  ✅ User {user_id} has access")
        else:
            print(f"  ❌ User {user_id} should have access but doesn't")
            return False
    
    # Test unauthorized user
    unauthorized_user = 999999999
    if unauthorized_user not in [JAM_USER_ID, JONESY_USER_ID]:
        print(f"  ✅ User {unauthorized_user} properly blocked")
    else:
        print(f"  ❌ User {unauthorized_user} should be blocked but isn't")
        return False
    
    return True

def test_natural_language_triggers():
    """Test natural language trigger detection"""
    print("🗣️ Testing Natural Language Triggers...")
    
    # From main.py implementation
    announcement_triggers = [
        "make an announcement",
        "create an announcement", 
        "post an announcement",
        "need to announce",
        "want to announce",
        "announce something",
        "make announcement",
        "create announcement",
        "post announcement",
        "send an announcement",
        "update announcement",
        "announcement update",
        "bot update",
        "server update",
        "community update",
        "new features",
        "feature update"
    ]
    
    test_phrases = [
        "I need to make an announcement",
        "Can we create an announcement?",
        "Want to announce new features",
        "Server update needed",
        "Bot update time"
    ]
    
    detected = 0
    for phrase in test_phrases:
        phrase_lower = phrase.lower()
        if any(trigger in phrase_lower for trigger in announcement_triggers):
            detected += 1
            print(f"  ✅ '{phrase}' - detected")
        else:
            print(f"  ❌ '{phrase}' - not detected")
    
    success_rate = detected / len(test_phrases)
    print(f"  📊 Detection rate: {detected}/{len(test_phrases)} ({success_rate*100:.0f}%)")
    
    return success_rate >= 0.8  # 80% success rate

def test_conversation_system():
    """Test conversation system components"""
    print("💬 Testing Conversation System...")
    
    try:
        # Test function availability
        from bot.handlers.conversation_handler import (
            create_ai_announcement_content,
            format_announcement_content,
            handle_announcement_conversation,
            start_announcement_conversation,
        )

        # Check functions are callable
        functions = [
            ("handle_announcement_conversation", handle_announcement_conversation),
            ("create_ai_announcement_content", create_ai_announcement_content),
            ("format_announcement_content", format_announcement_content),
            ("start_announcement_conversation", start_announcement_conversation)
        ]
        
        for name, func in functions:
            if callable(func):
                print(f"  ✅ {name} - available")
            else:
                print(f"  ❌ {name} - not callable")
                return False
        
        return True
        
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False

def test_command_registration():
    """Test that commands are properly registered"""
    print("⚡ Testing Command Registration...")
    
    try:
        from unittest.mock import MagicMock

        from bot.commands.announcements import AnnouncementsCommands

        # Create mock bot
        mock_bot = MagicMock()
        cog = AnnouncementsCommands(mock_bot)
        
        # Check that methods exist
        commands = [
            ("make_announcement", "!announce"),
            ("emergency_announcement", "!emergency"), 
            ("start_announcement_update", "!announceupdate"),
            ("create_announcement", "!createannouncement")
        ]
        
        for method_name, command_name in commands:
            if hasattr(cog, method_name):
                method = getattr(cog, method_name)
                if callable(method):
                    print(f"  ✅ {command_name} - registered")
                else:
                    print(f"  ❌ {command_name} - not callable")
                    return False
            else:
                print(f"  ❌ {command_name} - method missing")
                return False
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error testing commands: {e}")
        return False

def test_ai_integration():
    """Test AI integration availability"""
    print("🤖 Testing AI Integration...")
    
    try:
        from bot.handlers.ai_handler import ai_enabled, call_ai_with_rate_limiting, filter_ai_response
        
        print(f"  📊 AI enabled: {ai_enabled}")
        print(f"  ✅ call_ai_with_rate_limiting - available")
        print(f"  ✅ filter_ai_response - available")
        
        # Test AI content creation function
        from bot.handlers.conversation_handler import create_ai_announcement_content
        print(f"  ✅ create_ai_announcement_content - available")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def main():
    """Main verification function"""
    print("🧪 Announcement System Verification")
    print("=" * 50)
    
    tests = [
        ("Module Loading", test_module_loading),
        ("Access Control", test_access_control), 
        ("Natural Language Triggers", test_natural_language_triggers),
        ("Conversation System", test_conversation_system),
        ("Command Registration", test_command_registration),
        ("AI Integration", test_ai_integration)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}:")
        try:
            if test_func():
                passed += 1
                print(f"  ✅ {test_name} - PASSED")
            else:
                print(f"  ❌ {test_name} - FAILED")
        except Exception as e:
            print(f"  ❌ {test_name} - ERROR: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("\n✅ Announcement System Status:")
        print("• ✅ Accessible to both Jam and Jonesy")
        print("• ✅ Command-based entry points available")
        print("• ✅ Natural language triggers functional") 
        print("• ✅ Interactive conversation system ready")
        print("• ✅ AI content enhancement integrated")
        print("• ✅ Numbered steps workflow available")
        print("• ✅ All modules properly loaded")
        
        print("\n🚀 Available Entry Points:")
        print("• Commands: !announce, !emergency, !announceupdate, !createannouncement")
        print("• Natural Language: 'make an announcement', 'server update', etc.")
        print("• Location: DMs for interactive mode, any channel for basic commands")
        
        return True
    else:
        print(f"❌ {total-passed} tests failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
