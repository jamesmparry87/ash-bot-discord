"""
Test sync parser fixes for edge cases found in logs.

Run this to verify the parser improvements handle all the problematic titles.
"""

import sys
sys.path.insert(0, 'Live')

from bot.utils.text_processing import extract_game_name_from_title


def test_parser_fixes():
    """Test all the edge cases from the sync logs"""
    
    test_cases = [
        # SAROS detection via *markers*
        ("Early Access *SAROS* - Many thank to @PlayStation for the Key !Fractal #ad", "SAROS"),
        ("SPF NEEDED - SAROS - COME BACK STRONGER - !Fractal #ad", "SAROS"),
        ("Death Simulator SAROS !Fractal #ad", "Death Simulator SAROS"),
        
        # Resident Evil 9 false positive prevention
        ("First Time Playing: Resident Evil Requiem (day 9) - !Fractal", None),  # Should NOT extract "Resident Evil 9"
        ("First Time Playing: Resident Evil Requiem (day 5) - !Fractal", None),
        
        # HITMAN variants - should extract with colon
        ("First Time Playing: HITMAN World of Assassination - !Fractal [DROPS]", "HITMAN: World of Assassination"),
        ("HITMAN World of Assassination [DROPS] - !PP !Fractal", "HITMAN: World of Assassination"),
        
        # Should still work for legitimate numbered games
        ("Halo 3 (day 1) - First Playthrough", "Halo 3"),
        ("Resident Evil 4 Remake (part 2)", "Resident Evil 4 Remake"),
        
        # Multi-game streams
        ("Ink, Jazz & RAT-tat-tat Action (DAY 1) - !Fractal", "Ink, Jazz"),
        
        # Metro with creative prefix
        ("Mind the Gap (It's Full of Monsters): METRO 2033 (DAY 1) - !Fractal", None),  # Too complex
        
        # Standard extractions should still work
        ("Yakuza 0 Director's Cut - Episode 5", "Yakuza 0 Director's Cut"),
        ("Saints Row: The Third - Part 12 Thanks @sponsor", "Saints Row: The Third"),
    ]
    
    print("Testing Sync Parser Fixes\n" + "=" * 60)
    
    passed = 0
    failed = 0
    
    for title, expected in test_cases:
        result = extract_game_name_from_title(title)
        
        # Special handling for SAROS - check if it contains SAROS
        if expected == "SAROS" and result and "SAROS" in result.upper():
            status = "[PASS]"
            passed += 1
        elif expected and result and expected.lower() == result.lower():
            status = "[PASS]"
            passed += 1
        elif expected is None and result is None:
            status = "[PASS]"
            passed += 1
        else:
            status = "[FAIL]"
            failed += 1
        
        print(f"\n{status}")
        print(f"  Title:    {title[:70]}...")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    
    if failed == 0:
        print("[SUCCESS] All parser fixes working correctly!")
    else:
        print(f"[WARNING] {failed} tests failed - review needed")
    
    return failed == 0


if __name__ == "__main__":
    success = test_parser_fixes()
    sys.exit(0 if success else 1)
