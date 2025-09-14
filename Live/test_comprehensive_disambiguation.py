#!/usr/bin/env python3
"""
Comprehensive test to verify all Jonesy disambiguation fixes are in place
"""

import os
import re
import sys

# Add the current directory to the path
sys.path.append(os.path.dirname(__file__))

def test_context_detection():
    """Test the context detection system"""
    try:
        from bot.handlers.context_manager import detect_jonesy_context
        
        # Test user context detection
        user_cases = [
            "Has Jonesy played God of War?",
            "What games has Jonesy streamed?",
            "Did Captain Jonesy complete this?",
            "Who is Jonesy?"
        ]
        
        # Test cat context detection
        cat_cases = [
            "Jonesy the cat survived the alien",
            "The ship's cat was named Jonesy",
            "In the 1979 Alien movie, Jonesy was a cat"
        ]
        
        print("🧪 Testing context detection system...")
        
        user_correct = 0
        for case in user_cases:
            result = detect_jonesy_context(case)
            if result == "user":
                user_correct += 1
                print(f"  ✅ '{case}' -> {result}")
            else:
                print(f"  ❌ '{case}' -> {result} (expected 'user')")
        
        cat_correct = 0
        for case in cat_cases:
            result = detect_jonesy_context(case)
            if result == "cat":
                cat_correct += 1
                print(f"  ✅ '{case}' -> {result}")
            else:
                print(f"  ❌ '{case}' -> {result} (expected 'cat')")
        
        context_passed = (user_correct == len(user_cases) and cat_correct == len(cat_cases))
        print(f"📊 Context Detection: {'PASSED' if context_passed else 'FAILED'}")
        return context_passed
        
    except Exception as e:
        print(f"❌ Context detection test failed: {e}")
        return False

def test_faq_responses():
    """Test FAQ disambiguation responses"""
    try:
        from bot.config import FAQ_RESPONSES
        
        print("🧪 Testing FAQ disambiguation responses...")
        
        required_faqs = [
            "who is jonesy",
            "jonesy the cat", 
            "alien cat",
            "jonesy",
            "which jonesy"
        ]
        
        all_present = True
        for faq in required_faqs:
            if faq in FAQ_RESPONSES:
                response = FAQ_RESPONSES[faq]
                # Check that the "who is jonesy" response defaults to Captain Jonesy
                if faq == "who is jonesy":
                    if "Captain Jonesy" in response and any(phrase in response for phrase in ["server", "commanding officer", "Discord"]):
                        print(f"  ✅ '{faq}' correctly defaults to Captain Jonesy")
                    else:
                        print(f"  ❌ '{faq}' doesn't properly default to Captain Jonesy")
                        all_present = False
                else:
                    print(f"  ✅ '{faq}' present")
            else:
                print(f"  ❌ '{faq}' missing")
                all_present = False
        
        print(f"📊 FAQ Responses: {'PASSED' if all_present else 'FAILED'}")
        return all_present
        
    except Exception as e:
        print(f"❌ FAQ test failed: {e}")
        return False

def test_ai_prompt_fixes():
    """Test that AI prompts include disambiguation rules"""
    try:
        print("🧪 Testing AI prompt disambiguation fixes...")
        
        # Test 1: Check bot_modular.py for disambiguation rule in handle_general_conversation
        with open('bot_modular.py', 'r', encoding='utf-8') as f:
            bot_modular_content = f.read()
        
        # Look for the critical disambiguation rule in the AI prompt
        disambiguation_rule_pattern = r'CRITICAL DISAMBIGUATION RULE.*Jonesy.*ALWAYS refers to Captain Jonesy'
        
        if re.search(disambiguation_rule_pattern, bot_modular_content, re.DOTALL | re.IGNORECASE):
            print("  ✅ Main conversation AI prompt includes disambiguation rule")
            main_prompt_fixed = True
        else:
            print("  ❌ Main conversation AI prompt missing disambiguation rule")
            main_prompt_fixed = False
        
        # Test 2: Check ai_handler.py for disambiguation rule in announcement prompts
        with open('bot/handlers/ai_handler.py', 'r', encoding='utf-8') as f:
            ai_handler_content = f.read()
        
        # Test 3: Check conversation_handler.py for disambiguation rule (also has AI prompts)
        with open('bot/handlers/conversation_handler.py', 'r', encoding='utf-8') as f:
            conversation_handler_content = f.read()
        
        # Count occurrences of the disambiguation rule in both files
        ai_handler_count = len(re.findall(disambiguation_rule_pattern, ai_handler_content, re.DOTALL | re.IGNORECASE))
        conversation_handler_count = len(re.findall(disambiguation_rule_pattern, conversation_handler_content, re.DOTALL | re.IGNORECASE))
        
        total_count = ai_handler_count + conversation_handler_count
        
        if ai_handler_count >= 2:
            print(f"  ✅ AI handler includes disambiguation rule in {ai_handler_count} places")
            ai_handler_fixed = True
        else:
            print(f"  ⚠️ AI handler has disambiguation rule in {ai_handler_count} places (expected 2+)")
            ai_handler_fixed = False
        
        if conversation_handler_count >= 2:
            print(f"  ✅ Conversation handler includes disambiguation rule in {conversation_handler_count} places")
            conversation_handler_fixed = True
        else:
            print(f"  ⚠️ Conversation handler has disambiguation rule in {conversation_handler_count} places (expected 2+)")
            conversation_handler_fixed = False
        
        if total_count >= 2:  # Should have disambiguation rule in AI handlers
            print(f"  ✅ Total AI prompts with disambiguation: {total_count}")
            handler_prompts_fixed = True
        else:
            print(f"  ❌ Insufficient AI prompts with disambiguation rule (found {total_count}, expected 2+)")
            handler_prompts_fixed = False
        
        prompts_passed = main_prompt_fixed and handler_prompts_fixed
        print(f"📊 AI Prompt Fixes: {'PASSED' if prompts_passed else 'FAILED'}")
        return prompts_passed
        
    except Exception as e:
        print(f"❌ AI prompt test failed: {e}")
        return False

def main():
    """Run comprehensive disambiguation tests"""
    print("🚀 Comprehensive Jonesy Disambiguation Test")
    print("=" * 60)
    
    # Run all tests
    context_passed = test_context_detection()
    print()
    
    faq_passed = test_faq_responses()
    print()
    
    prompts_passed = test_ai_prompt_fixes()
    print()
    
    # Summary
    print("=" * 60)
    print("📋 COMPREHENSIVE TEST RESULTS:")
    print(f"  Context Detection:  {'✅ PASSED' if context_passed else '❌ FAILED'}")
    print(f"  FAQ Responses:      {'✅ PASSED' if faq_passed else '❌ FAILED'}")
    print(f"  AI Prompt Fixes:    {'✅ PASSED' if prompts_passed else '❌ FAILED'}")
    
    all_passed = context_passed and faq_passed and prompts_passed
    
    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("   The Jonesy disambiguation system is fully implemented and working correctly.")
        print("   Users asking 'Who is Jonesy?' should now get responses about Captain Jonesy (the user) by default.")
    else:
        print("⚠️ Some tests failed - disambiguation system may need additional fixes.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
