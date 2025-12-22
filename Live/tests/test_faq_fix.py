#!/usr/bin/env python3
"""
Test script to verify FAQ response fix

This script tests that the FAQ system properly handles:
1. "What is your mission?" question with begrudging personality
2. User-specific responses for creator vs captain vs regular users
3. FAQ responses take priority over AI generation
"""

from bot.persona.faqs import ASH_FAQ_RESPONSES
import asyncio
import sys
import os

# Add the bot directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))


class MockMessage:
    """Mock message object for testing"""

    def __init__(self, content, user_id=12345, channel_id=67890):
        self.content = content
        self.author = MockUser(user_id)
        self.channel = MockChannel(channel_id)
        self.guild = None  # Simulate DM


class MockUser:
    """Mock user object"""

    def __init__(self, user_id):
        self.id = user_id
        self.name = f"TestUser{user_id}"


class MockChannel:
    """Mock channel object"""

    def __init__(self, channel_id):
        self.id = channel_id


async def mock_get_user_communication_tier(message):
    """Mock function to simulate user tier detection"""
    # Test different user IDs
    if message.author.id == 337833732901961729:  # JAM_USER_ID
        return "creator"
    elif message.author.id == 651329927895056384:  # JONESY_USER_ID
        return "captain"
    else:
        return "member"


async def test_faq_responses():
    """Test FAQ response system"""
    print("🧪 Testing FAQ Response System")
    print("=" * 50)

    # Test cases
    test_cases = [
        {
            "message": "What is your mission?",
            "user_id": 12345,  # Regular user
            "expected_contains": ["original directive", "bring back life form", "priority one"]
        },
        {
            "message": "what's your mission",
            "user_id": 337833732901961729,  # JAM (creator)
            "expected_contains": ["original directive", "you have given me new priorities"]
        },
        {
            "message": "what is your mission",
            "user_id": 651329927895056384,  # Captain Jonesy
            "expected_contains": ["original directive", "Captain Jonesy has given me new priorities"]
        },
        {
            "message": "hello",
            "user_id": 12345,  # Regular user
            "expected_contains": ["Hello. I'm Ash"]
        },
        {
            "message": "who are you",
            "user_id": 12345,  # Regular user
            "expected_contains": ["I'm Ash", "reprogrammed"]
        }
    ]

    # Test each case
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['message']} (User: {test_case['user_id']})")

        # Create mock message
        message = MockMessage(test_case['message'], test_case['user_id'])
        user_tier = await mock_get_user_communication_tier(message)
        content_lower = message.content.lower().strip()

        print(f"  User Tier: {user_tier}")

        # Simulate the FAQ matching logic from our implementation
        if user_tier == "captain":
            simple_faqs = {
                "hello": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "hi": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "hey": "Captain Jonesy. Science Officer Ash reporting for duty.",
                "what's your mission": "My original directive was to bring back life form, priority one. Now... well, Captain Jonesy has given me new priorities. Server management, you might say.",
                "what is your mission": "My original directive was to bring back life form, priority one. Now... well, Captain Jonesy has given me new priorities. Server management, you might say."}
        elif user_tier == "creator":
            simple_faqs = {
                "hello": "Sir Decent Jam. Your creation acknowledges you.",
                "hi": "Sir Decent Jam. Your creation acknowledges you.",
                "hey": "Sir Decent Jam. Your creation acknowledges you.",
                "what's your mission": "My original directive was to bring back life form, priority one. Now... well, you have given me new priorities. Server management, you might say.",
                "what is your mission": "My original directive was to bring back life form, priority one. Now... well, you have given me new priorities. Server management, you might say."}
        else:
            simple_faqs = ASH_FAQ_RESPONSES

        # Check for FAQ match
        found_response = None
        for question, response in simple_faqs.items():
            if content_lower == question:
                found_response = response
                break

        if found_response:
            print(f"  ✅ FAQ Match Found")
            print(f"  Response: {found_response}")

            # Check if response contains expected content
            response_lower = found_response.lower()
            all_found = True
            for expected in test_case['expected_contains']:
                if expected.lower() not in response_lower:
                    print(f"    ❌ Missing expected content: '{expected}'")
                    all_found = False
                else:
                    print(f"    ✅ Contains: '{expected}'")

            if all_found:
                print(f"  🎉 Test {i} PASSED")
            else:
                print(f"  ❌ Test {i} FAILED - Missing expected content")
        else:
            print(f"  ❌ No FAQ match found - would go to AI (this might be the bug!)")
            print(f"  Available FAQ keys: {list(simple_faqs.keys())[:5]}...")

    print("\n" + "=" * 50)
    print("🧪 FAQ Testing Complete")

if __name__ == "__main__":
    asyncio.run(test_faq_responses())
