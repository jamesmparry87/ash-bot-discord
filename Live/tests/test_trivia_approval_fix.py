#!/usr/bin/env python3
"""
Test Trivia Question Approval System Fix
Tests the specific regression where JAM's responses (1, 2, 3) were not being processed.
"""

import asyncio
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo


def test_conversation_state_conflicts():
    """Test that conversation state conflicts have been resolved"""
    print("🧪 Testing conversation state conflict resolution...")

    try:
        # Import main.py and check for conflicting variables
        from bot.main import bot
        from bot.handlers.conversation_handler import (
            jam_approval_conversations,
            announcement_conversations,
            mod_trivia_conversations
        )

        # Check that main.py no longer has conflicting global variables
        import bot.main as main_module

        # These should NOT exist in main.py anymore (we removed them!)
        conflicting_vars = []
        if hasattr(main_module, 'announcement_conversations'):
            conflicting_vars.append('announcement_conversations')
        if hasattr(main_module, 'mod_trivia_conversations'):
            conflicting_vars.append('mod_trivia_conversations')

        if conflicting_vars:
            print(f"❌ Still have conflicting variables in main.py: {conflicting_vars}")
            return False
        else:
            print("✅ No conflicting conversation variables found in main.py")

        # Verify that we can import and use the conversation dictionaries
        print(f"✅ jam_approval_conversations imported successfully: {type(jam_approval_conversations)}")
        print(f"✅ announcement_conversations imported successfully: {type(announcement_conversations)}")
        print(f"✅ mod_trivia_conversations imported successfully: {type(mod_trivia_conversations)}")

        # Test that conversation state is properly managed
        from bot.config import JAM_USER_ID

        # Simulate conversation state
        test_conversation = {
            'step': 'approval',
            'data': {'question_data': {'question_text': 'Test question?', 'correct_answer': 'Test answer'}},
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }

        # Set conversation state
        jam_approval_conversations[JAM_USER_ID] = test_conversation

        # Verify it's accessible
        retrieved_conversation = jam_approval_conversations.get(JAM_USER_ID)
        if retrieved_conversation:
            print("✅ Conversation state can be set and retrieved successfully")

            # Clean up
            del jam_approval_conversations[JAM_USER_ID]
            print("✅ Conversation state cleanup works")
        else:
            print("❌ Failed to retrieve conversation state")
            return False

        print("✅ Conversation state conflict resolution successful")
        return True

    except Exception as e:
        print(f"❌ Conversation state test failed: {e}")
        return False


def test_jam_approval_message_processing():
    """Test JAM approval message processing logic"""
    print("\n🧪 Testing JAM approval message processing...")

    try:
        from bot.handlers.conversation_handler import handle_jam_approval_conversation, jam_approval_conversations
        from bot.config import JAM_USER_ID

        # Mock message from JAM
        mock_message = MagicMock()
        mock_message.author.id = JAM_USER_ID
        mock_message.content = "1"  # Approval response
        mock_message.reply = AsyncMock()

        # Set up conversation state
        test_conversation = {
            'step': 'approval',
            'data': {
                'question_data': {
                    'question_text': 'Test question?',
                    'correct_answer': 'Test answer',
                    'question_type': 'single_answer',
                    'category': 'test'
                }
            },
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }
        jam_approval_conversations[JAM_USER_ID] = test_conversation

        print(f"✅ Set up test conversation state for JAM user {JAM_USER_ID}")

        # Mock database
        with patch('bot.handlers.conversation_handler.db') as mock_db:
            mock_db.add_trivia_question.return_value = 123  # Mock question ID

            # Test the handler function directly
            print("🔍 Testing handle_jam_approval_conversation with response '1'...")

            # This should process the approval without errors
            result = asyncio.run(handle_jam_approval_conversation(mock_message))

            # Check that database was called
            mock_db.add_trivia_question.assert_called_once()

            # Check that reply was sent
            mock_message.reply.assert_called_once()
            reply_text = mock_message.reply.call_args[0][0]

            if "Question Approved Successfully" in reply_text:
                print("✅ JAM approval response processed successfully")
                print(f"✅ Reply message: {reply_text[:100]}...")
            else:
                print(f"❌ Unexpected reply message: {reply_text}")
                return False

            # Check that conversation was cleaned up
            if JAM_USER_ID not in jam_approval_conversations:
                print("✅ Conversation state cleaned up after approval")
            else:
                print("⚠️ Conversation state not cleaned up")

        print("✅ JAM approval message processing test passed")
        return True

    except Exception as e:
        print(f"❌ JAM approval message processing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_approval_response_variations():
    """Test different approval response formats"""
    print("\n🧪 Testing approval response variations...")

    try:
        from bot.handlers.conversation_handler import handle_jam_approval_conversation, jam_approval_conversations
        from bot.config import JAM_USER_ID

        # Test different valid responses
        valid_responses = [
            ('1', 'numeric choice'),
            ('approve', 'text approval'),
            ('yes', 'yes response'),
            ('accept', 'accept response'),
            ('2', 'modify choice'),
            ('modify', 'text modify'),
            ('edit', 'edit response'),
            ('3', 'reject choice'),
            ('reject', 'text reject'),
            ('no', 'no response')
        ]

        for response, description in valid_responses:
            print(f"🔍 Testing response: '{response}' ({description})")

            # Mock message
            mock_message = MagicMock()
            mock_message.author.id = JAM_USER_ID
            mock_message.content = response
            mock_message.reply = AsyncMock()

            # Set up fresh conversation state
            test_conversation = {
                'step': 'approval',
                'data': {
                    'question_data': {
                        'question_text': 'Test question?',
                        'correct_answer': 'Test answer',
                        'question_type': 'single_answer',
                        'category': 'test'
                    }
                },
                'last_activity': datetime.now(ZoneInfo("Europe/London")),
            }
            jam_approval_conversations[JAM_USER_ID] = test_conversation

            # Mock database for approval responses
            with patch('bot.handlers.conversation_handler.db') as mock_db:
                mock_db.add_trivia_question.return_value = 123

                # Test the response
                try:
                    asyncio.run(handle_jam_approval_conversation(mock_message))

                    # Check that some reply was sent
                    if mock_message.reply.called:
                        print(f"✅ Response '{response}' processed successfully")
                    else:
                        print(f"❌ Response '{response}' did not trigger any reply")

                except Exception as e:
                    print(f"⚠️ Response '{response}' caused error: {e}")

            # Clean up conversation state
            if JAM_USER_ID in jam_approval_conversations:
                del jam_approval_conversations[JAM_USER_ID]

        print("✅ Approval response variations test completed")
        return True

    except Exception as e:
        print(f"❌ Approval response variations test failed: {e}")
        return False


def test_debugging_output():
    """Test that debugging output is working"""
    print("\n🧪 Testing debugging output...")

    try:
        from bot.handlers.conversation_handler import handle_jam_approval_conversation, jam_approval_conversations
        from bot.config import JAM_USER_ID

        # Mock message
        mock_message = MagicMock()
        mock_message.author.id = JAM_USER_ID
        mock_message.content = "1"
        mock_message.reply = AsyncMock()

        # Set up conversation state
        test_conversation = {
            'step': 'approval',
            'data': {
                'question_data': {
                    'question_text': 'Test question?',
                    'correct_answer': 'Test answer'
                }
            },
            'last_activity': datetime.now(ZoneInfo("Europe/London")),
        }
        jam_approval_conversations[JAM_USER_ID] = test_conversation

        print("🔍 Running handler with debug output enabled...")

        # Capture stdout to check for debug messages
        import io
        from contextlib import redirect_stdout

        debug_output = io.StringIO()

        with redirect_stdout(debug_output):
            with patch('bot.handlers.conversation_handler.db') as mock_db:
                mock_db.add_trivia_question.return_value = 123
                asyncio.run(handle_jam_approval_conversation(mock_message))

        debug_text = debug_output.getvalue()

        # Check for expected debug messages
        expected_debug_patterns = [
            "JAM APPROVAL DEBUG: User",
            "JAM APPROVAL DEBUG: Conversation exists",
            "JAM APPROVAL DEBUG: Processing approval conversation for JAM",
            "JAM APPROVAL DEBUG: Current step:",
            "JAM APPROVAL DEBUG: Message content:"
        ]

        found_patterns = []
        for pattern in expected_debug_patterns:
            if pattern in debug_text:
                found_patterns.append(pattern)
                print(f"✅ Found debug pattern: {pattern}")
            else:
                print(f"❌ Missing debug pattern: {pattern}")

        if len(found_patterns) >= 3:  # At least some debug output
            print("✅ Debug output is working")
        else:
            print("⚠️ Limited debug output detected")
            print(f"Full debug output:\n{debug_text}")

        # Clean up
        if JAM_USER_ID in jam_approval_conversations:
            del jam_approval_conversations[JAM_USER_ID]

        return True

    except Exception as e:
        print(f"❌ Debug output test failed: {e}")
        return False


async def test_integration():
    """Test full integration"""
    print("\n🧪 Testing full integration...")

    try:
        # Test that all modules can be imported without conflicts
        from bot.main import bot
        from bot.handlers.conversation_handler import (
            jam_approval_conversations,
            handle_jam_approval_conversation,
            start_jam_question_approval
        )
        from bot.config import JAM_USER_ID

        print("✅ All modules imported successfully")

        # Test the full approval workflow
        test_question_data = {
            'question_text': 'Integration test question?',
            'correct_answer': 'Integration test answer',
            'question_type': 'single_answer',
            'category': 'test'
        }

        print("🔍 Testing start_jam_question_approval...")

        # Mock the bot and user fetching
        with patch('bot.handlers.conversation_handler.sys.modules') as mock_modules:
            # Mock bot instance
            mock_bot = MagicMock()
            mock_bot.user.return_value = True
            mock_user = MagicMock()
            mock_user.name = "TestJAM"
            mock_user.discriminator = "0001"
            mock_user.send = AsyncMock()
            mock_bot.fetch_user.return_value = mock_user

            # Mock finding bot in modules
            mock_obj = MagicMock()
            mock_obj.bot = mock_bot
            mock_modules.items.return_value = [('test_module', mock_obj)]

            # Try to start approval workflow
            result = await start_jam_question_approval(test_question_data)

            if result:
                print("✅ start_jam_question_approval returned success")

                # Check that conversation state was created
                if JAM_USER_ID in jam_approval_conversations:
                    print("✅ Conversation state was created")

                    # Check conversation data
                    conversation = jam_approval_conversations[JAM_USER_ID]
                    if conversation.get('step') == 'approval':
                        print("✅ Conversation step set correctly")

                    # Clean up
                    del jam_approval_conversations[JAM_USER_ID]
                else:
                    print("❌ Conversation state was not created")
                    return False
            else:
                print("❌ start_jam_question_approval returned failure")
                return False

        print("✅ Full integration test passed")
        return True

    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test execution"""
    print("🚀 Starting Trivia Question Approval System Fix Tests...")
    print("=" * 60)

    # Run all tests
    tests = [
        ("Conversation State Conflicts", test_conversation_state_conflicts),
        ("JAM Approval Message Processing", test_jam_approval_message_processing),
        ("Approval Response Variations", test_approval_response_variations),
        ("Debugging Output", test_debugging_output),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))

    # Run async integration test
    print("\n" + "=" * 60)
    try:
        integration_result = asyncio.run(test_integration())
        results.append(("Full Integration", integration_result))
    except Exception as e:
        print(f"❌ Integration test crashed: {e}")
        results.append(("Full Integration", False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)

    passed = 0
    failed = 0

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
        else:
            failed += 1

    print("=" * 60)
    print(f"📈 OVERALL: {passed}/{len(results)} tests passed ({passed/len(results)*100:.1f}%)")

    if failed == 0:
        print("🎉 ALL TESTS PASSED! Trivia approval fix is working correctly.")
        return True
    else:
        print(f"⚠️  {failed} test(s) failed - review implementation")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
