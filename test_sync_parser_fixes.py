#!/usr/bin/env python3
"""
Test script for Fix #3: Punctuation Normalization

This script tests the new _normalize_for_matching() function to verify
it correctly handles HITMAN and other punctuation variations.
"""

import sys
import os

# Add the Live directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Live'))

from bot.database.games import GamesDatabase


def test_normalization():
    """Test the _normalize_for_matching() function"""
    # Create a mock database instance just for the normalization function
    class MockDB:
        def get_connection(self):
            return None
        def get_config_value(self, key):
            return None
    
    db = GamesDatabase(MockDB())
    
    test_cases = [
        # (input1, input2, should_match)
        ("HITMAN: World of Assassination", "HITMAN World of Assassination", True),
        ("Resident Evil 2 - Remake", "Resident Evil 2 Remake", True),
        ("The Legend of Zelda: Breath of the Wild", "Legend of Zelda Breath of the Wild", True),
        ("Metal Gear Solid: The Twin Snakes", "Metal Gear Solid The Twin Snakes", True),
        ("Don't Starve", "Dont Starve", True),
        ("Assassin's Creed", "Assassins Creed", True),
        ("The Witcher 3", "Witcher 3", True),
        ("Half-Life 2", "Half Life 2", True),
        ("BioShock", "Bioshock", True),
        ("HITMAN: World of Assassination", "Resident Evil 9", False),
    ]
    
    print("Testing Fix #3: Punctuation Normalization\n")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for title1, title2, should_match in test_cases:
        normalized1 = db._normalize_for_matching(title1)
        normalized2 = db._normalize_for_matching(title2)
        matches = (normalized1 == normalized2)
        
        status = "[PASS]" if matches == should_match else "[FAIL]"
        
        if matches == should_match:
            passed += 1
        else:
            failed += 1
        
        print(f"{status}")
        print(f"  Input 1: '{title1}'")
        print(f"  Input 2: '{title2}'")
        print(f"  Normalized 1: '{normalized1}'")
        print(f"  Normalized 2: '{normalized2}'")
        print(f"  Match: {matches} (Expected: {should_match})")
        print()
    
    print("=" * 70)
    print(f"\nResults: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    
    if failed == 0:
        print("[SUCCESS] All tests passed! Fix #3 is working correctly.")
        return True
    else:
        print("[ERROR] Some tests failed. Please review the implementation.")
        return False


if __name__ == "__main__":
    success = test_normalization()
    sys.exit(0 if success else 1)
