#!/usr/bin/env python3
"""
Test script to verify AI disambiguation is working correctly
"""

import asyncio
import os
import sys

import pytest

# Add the current directory to the path so we can import the bot modules
sys.path.append(os.path.dirname(__file__))


@pytest.mark.asyncio
async def test_ai_jonesy_response():
    """Test the AI response to 'Who is Jonesy?' question"""
    try:
        from bot.handlers.ai_handler import ai_enabled, call_ai_with_rate_limiting

        if not ai_enabled:
            print("❌ AI not enabled - cannot test AI disambiguation")
            return False

        # Test the exact prompt that would be used in handle_general_conversation
        test_prompt = """You are Ash, the science officer from Alien, reprogrammed as a Discord bot.

CRITICAL DISAMBIGUATION RULE: In this Discord server context, "Jonesy" ALWAYS refers to Captain Jonesy - the Discord user, server owner, and streamer/YouTuber (she/her pronouns). This is the default and correct interpretation unless explicitly discussing the 1979 Alien movie. The cat named Jonesy from Alien is a separate entity that is rarely relevant in server discussions.

DEFAULT ASSUMPTION: Any mention of "Jonesy" = Captain Jonesy (the user).

You are speaking to a server member. Be helpful while maintaining your analytical personality.
Be analytical, precise, and helpful. Keep responses concise (2-3 sentences max).
Respond to: Who is Jonesy?"""

        print("🧪 Testing AI response to 'Who is Jonesy?'...")
        print("📝 Prompt includes critical disambiguation rule")

        # Test the AI response
        response_text, status = await call_ai_with_rate_limiting(test_prompt, 12345, "test")

        if response_text:
            print(f"✅ AI Response received: {response_text}")

            # Check if the response correctly identifies Captain Jonesy as the user
            response_lower = response_text.lower()

            # Positive indicators - should mention Captain Jonesy as user/owner/streamer
            positive_indicators = [
                "captain jonesy",
                "server owner",
                "commanding officer",
                "discord",
                "streamer",
                "youtuber",
                "user"
            ]

            # Negative indicators - should NOT describe the cat by default
            negative_indicators = [
                "feline",
                "cat",
                "alien movie",
                "nostromo",
                "ripley",
                "ship",
                "survival",
                "orange tabby"
            ]

            positive_matches = [indicator for indicator in positive_indicators if indicator in response_lower]
            negative_matches = [indicator for indicator in negative_indicators if indicator in response_lower]

            print(f"📊 Analysis:")
            print(f"   ✅ Positive indicators found: {positive_matches}")
            print(f"   ❌ Negative indicators found: {negative_matches}")

            # Determine if disambiguation worked
            has_user_context = len(positive_matches) > 0
            lacks_cat_context = len(negative_matches) == 0

            if has_user_context and lacks_cat_context:
                print("🎉 SUCCESS: AI correctly identifies Jonesy as Captain Jonesy (the user)")
                return True
            elif has_user_context and len(negative_matches) > 0:
                print("⚠️ MIXED: AI mentions Captain Jonesy but also includes cat references")
                return False
            else:
                print("❌ FAILED: AI does not correctly default to Captain Jonesy (the user)")
                return False
        else:
            print(f"❌ No AI response received: {status}")
            return False

    except Exception as e:
        print(f"❌ Error testing AI disambiguation: {e}")
        return False


async def main():
    """Run AI disambiguation test"""
    print("🚀 Testing AI Jonesy Disambiguation")
    print("=" * 50)

    success = await test_ai_jonesy_response()

    print("=" * 50)
    if success:
        print("🎉 AI disambiguation test PASSED!")
    else:
        print("⚠️ AI disambiguation test FAILED - may need further adjustments")

    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
