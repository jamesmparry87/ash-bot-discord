#!/usr/bin/env python3
"""
Test the enhanced trivia answer matching system to ensure correct answers are properly recognized.
This test validates the fixes implemented for the trivia matching issues.
"""

import os
import sys
from typing import Dict, List, Tuple

# Add the Live directory to Python path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from bot.database_module import DatabaseManager

def test_answer_matching():
    """Test the enhanced answer matching logic directly"""
    print("🧠 Testing Enhanced Trivia Answer Matching System")
    print("=" * 60)
    
    # Create a database manager instance to access the matching methods
    db = DatabaseManager()
    
    # Test cases: (user_answer, normalized_answer, correct_answer, expected_result, expected_type)
    test_cases = [
        # Basic case sensitivity tests
        ("blue", "blue", "blue", (True, False), "exact"),
        ("Blue", "blue", "blue", (True, False), "case_insensitive"),
        ("BLUE", "blue", "blue", (True, False), "case_insensitive"),
        
        # Fuzzy matching tests
        ("blu", "blu", "blue", (False, True), "fuzzy_close"),  # Close match
        ("bleu", "bleu", "blue", (False, True), "fuzzy_close"),  # Typo
        ("green", "green", "blue", (False, False), "no_match"),  # Wrong answer
        
        # Abbreviation tests  
        ("b", "b", "blue", (True, False), "abbreviation"),
        ("r", "r", "red", (True, False), "abbreviation"),
        ("g", "g", "green", (True, False), "abbreviation"),
        
        # Multi-word answers
        ("god of war", "god of war", "God of War", (True, False), "case_insensitive"),
        ("God War", "god war", "God of War", (True, False), "word_overlap"),  # Missing "of"
        ("War God", "war god", "God of War", (False, True), "word_overlap"),  # Different order
        
        # Game abbreviations
        ("gta", "gta", "Grand Theft Auto", (True, False), "abbreviation_expansion"),
        ("cod", "cod", "Call of Duty", (True, False), "abbreviation_expansion"),
        
        # Numerical answers
        ("18", "18", "18", (True, False), "exact"),
        ("18 hours", "18 hours", "18", (True, False), "numerical"),
        ("19", "19", "18", (False, True), "numerical_close"),  # Close number
        
        # Edge cases
        ("", "", "blue", (False, False), "no_match"),  # Empty answer
        ("   blue   ", "blue", "blue", (True, False), "exact"),  # Whitespace
    ]
    
    print(f"Running {len(test_cases)} test cases...\n")
    
    passed = 0
    failed = 0
    
    for i, (user_answer, normalized_answer, correct_answer, expected_result, test_type) in enumerate(test_cases, 1):
        try:
            # Test the enhanced matching logic
            is_correct, is_close, match_type = db._evaluate_trivia_answer(
                user_answer, normalized_answer, correct_answer
            )
            
            actual_result = (is_correct, is_close)
            
            # Check if result matches expected
            if actual_result == expected_result:
                status = "✅ PASS"
                passed += 1
            else:
                status = "❌ FAIL"
                failed += 1
                
            print(f"Test {i:2d}: {status} | '{user_answer}' vs '{correct_answer}'")
            print(f"         Expected: correct={expected_result[0]}, close={expected_result[1]}")
            print(f"         Got:      correct={is_correct}, close={is_close}, type={match_type}")
            print(f"         Test:     {test_type}")
            print()
            
        except Exception as e:
            print(f"Test {i:2d}: ❌ ERROR | Exception: {e}")
            failed += 1
            print()
    
    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! The trivia answer matching system is working correctly.")
    else:
        print(f"⚠️ {failed} tests failed. The matching system needs further refinement.")
    
    return failed == 0


def test_specific_log_case():
    """Test the specific case from the logs where 'blue' and 'Blue' failed to match"""
    print("\n🎯 Testing Specific Log Case")
    print("=" * 40)
    
    db = DatabaseManager()
    
    # The exact case from the logs
    test_cases = [
        ("blue", "blue", "blue"),  # Exact match that should work
        ("Blue", "blue", "blue"),  # Case difference that should work
    ]
    
    for user_answer, normalized_answer, correct_answer in test_cases:
        is_correct, is_close, match_type = db._evaluate_trivia_answer(
            user_answer, normalized_answer, correct_answer
        )
        
        print(f"Answer: '{user_answer}' → Correct: {is_correct}, Close: {is_close}, Type: {match_type}")
        
        if is_correct:
            print(f"✅ SUCCESS: '{user_answer}' would now be marked as CORRECT")
        else:
            print(f"❌ FAILURE: '{user_answer}' is still not being recognized correctly")
    
    print()


def test_enhanced_features():
    """Test the enhanced features like fuzzy matching and partial credit"""
    print("🔶 Testing Enhanced Features")
    print("=" * 40)
    
    db = DatabaseManager()
    
    # Test cases for enhanced features
    enhanced_tests = [
        # Fuzzy matching
        ("God of Warr", "god of warr", "God of War"),  # Small typo
        ("Grand Thef Auto", "grand thef auto", "Grand Theft Auto"),  # Typo in middle
        
        # Partial word matching
        ("God War", "god war", "God of War"),  # Missing word
        ("Call Duty", "call duty", "Call of Duty"),  # Missing word
        
        # Close numerical answers
        ("17", "17", "18"),  # Close number
        ("20", "20", "18"),  # Somewhat close number
    ]
    
    for user_answer, normalized_answer, correct_answer in enhanced_tests:
        is_correct, is_close, match_type = db._evaluate_trivia_answer(
            user_answer, normalized_answer, correct_answer
        )
        
        if is_correct:
            points = "FULL POINTS"
        elif is_close:
            points = "HALF POINTS"  
        else:
            points = "NO POINTS"
            
        print(f"'{user_answer}' vs '{correct_answer}' → {points} ({match_type})")
    
    print()


if __name__ == "__main__":
    print("🔧 Trivia Answer Matching Fix Validation")
    print("Testing the enhanced fuzzy matching system...")
    print()
    
    # Run comprehensive tests
    success = test_answer_matching()
    
    # Test the specific problematic case from the logs
    test_specific_log_case()
    
    # Test enhanced features
    test_enhanced_features()
    
    if success:
        print("🎉 VALIDATION COMPLETE: The trivia answer matching fixes are working correctly!")
        print("   - Case insensitive matching: ✅ Fixed")
        print("   - Fuzzy matching for typos: ✅ Added")
        print("   - Partial credit system: ✅ Implemented")
        print("   - Enhanced debugging: ✅ Added")
        sys.exit(0)
    else:
        print("❌ VALIDATION FAILED: Some issues still need to be addressed.")
        sys.exit(1)
