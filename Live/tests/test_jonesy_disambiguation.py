#!/usr/bin/env python3
"""
Test script for Jonesy disambiguation system
Tests the context detection patterns and FAQ responses
"""

import os
import sys

from bot.persona.faqs import ASH_FAQ_RESPONSES
from bot.handlers.context_manager import detect_jonesy_context

sys.path.append(os.path.join(os.path.dirname(__file__)))


def test_jonesy_context_detection():
    """Test the context detection function"""
    print("🧪 Testing Jonesy context detection...")

    # Test cases for Captain Jonesy (user)
    user_test_cases = [
        "Has Jonesy played God of War?",
        "What games has Jonesy streamed?",
        "Did Captain Jonesy complete this?",
        "How long did Jonesy play that game?",
        "What's Jonesy's gaming history?",
        "Check Jonesy's YouTube channel",
        "Did the server owner play it?",
    ]

    # Test cases for Jonesy the cat (movie)
    cat_test_cases = [
        "Jonesy the cat survived the alien",
        "The ship's cat was named Jonesy",
        "In the 1979 Alien movie, Jonesy was a cat",
        "Jonesy survived with Ripley",
        "The orange cat from Alien was Jonesy",
        "That space cat was so smart",
        "The feline crew member was brave",
    ]

    print("\n📊 Testing USER context detection:")
    user_correct = 0
    for test_case in user_test_cases:
        result = detect_jonesy_context(test_case)
        status = "✅" if result == "user" else "❌"
        print(f"  {status} '{test_case}' -> {result}")
        if result == "user":
            user_correct += 1

    print(
        f"\n📊 USER accuracy: {user_correct}/{len(user_test_cases)} ({user_correct/len(user_test_cases)*100:.1f}%)")

    print("\n📊 Testing CAT context detection:")
    cat_correct = 0
    for test_case in cat_test_cases:
        result = detect_jonesy_context(test_case)
        status = "✅" if result == "cat" else "❌"
        print(f"  {status} '{test_case}' -> {result}")
        if result == "cat":
            cat_correct += 1

    print(
        f"\n📊 CAT accuracy: {cat_correct}/{len(cat_test_cases)} ({cat_correct/len(cat_test_cases)*100:.1f}%)")

    return user_correct == len(
        user_test_cases) and cat_correct == len(cat_test_cases)


def test_faq_responses():
    """Test the FAQ disambiguation responses"""
    print("\n🧪 Testing FAQ disambiguation responses...")

    disambiguation_faqs = [
        "who is jonesy",
        "jonesy the cat",
        "alien cat",
        "jones",
        "which jonesy"
    ]

    all_present = True
    for faq in disambiguation_faqs:
        if faq in ASH_FAQ_RESPONSES:
            print(f"✅ FAQ '{faq}' present")
            # Show a snippet of the response
            response = ASH_FAQ_RESPONSES[faq]
            snippet = response[:80] + "..." if len(response) > 80 else response
            print(f"   Response: {snippet}")
        else:
            print(f"❌ FAQ '{faq}' missing")
            all_present = False

    return all_present


def main():
    """Run all disambiguation tests"""
    print("🚀 Testing Jonesy Disambiguation System")
    print("=" * 50)

    context_test_passed = test_jonesy_context_detection()
    faq_test_passed = test_faq_responses()

    print("\n" + "=" * 50)
    print("📋 TEST SUMMARY:")
    print(
        f"  Context Detection: {'✅ PASSED' if context_test_passed else '❌ FAILED'}")
    print(
        f"  FAQ Responses:     {'✅ PASSED' if faq_test_passed else '❌ FAILED'}")

    if context_test_passed and faq_test_passed:
        print("\n🎉 All tests passed! Jonesy disambiguation system is working correctly.")
        return True
    else:
        print("\n⚠️ Some tests failed. System may need adjustments.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
