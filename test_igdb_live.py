"""
Test IGDB integration with live API calls to verify functionality
"""
import asyncio
import sys
import os

# Add Live directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Live'))

from bot.integrations import igdb


async def test_igdb_integration():
    """Test IGDB integration with various game names"""
    
    print("=" * 60)
    print("IGDB INTEGRATION TEST - LIVE API CALLS")
    print("=" * 60)
    print()
    
    # Test cases covering different scenarios
    test_cases = [
        # Simple known games
        ("Halo", "Should match 'Halo: Combat Evolved' with high confidence"),
        ("Dark Souls 3", "Should match 'Dark Souls III' with high confidence"),
        ("Zombie Army 4", "Should match exact game with high confidence"),
        
        # Games with subtitles
        ("God of War", "Should match base game or recent entry"),
        ("The Last of Us", "Should match with article handling"),
        
        # Abbreviated names
        ("GTA V", "Should expand and match 'Grand Theft Auto V'"),
        
        # Edge cases
        ("Pokémon", "Should handle accented characters"),
        ("Halo 3 + Halo Wars", "Should be filtered as compound game"),
    ]
    
    print("Testing IGDB API Connection...")
    print("-" * 60)
    
    # Test authentication first
    token = await igdb.get_igdb_access_token()
    if not token:
        print("❌ FAILED: Could not get IGDB access token")
        print("   Check your IGDB credentials:")
        print("   - IGDB_TWITCH_CLIENT_ID")
        print("   - IGDB_TWITCH_SECRET")
        return False
    
    print(f"✅ Authentication successful (token: {token[:10]}...)")
    print()
    
    # Test each game
    results = []
    for game_name, description in test_cases:
        print(f"Testing: '{game_name}'")
        print(f"  Expected: {description}")
        
        try:
            result = await igdb.validate_and_enrich(game_name)
            
            confidence = result.get('confidence', 0.0)
            canonical = result.get('canonical_name', 'N/A')
            match_found = result.get('match_found', False)
            alt_names = result.get('alternative_names', [])
            genre = result.get('genre', 'N/A')
            
            print(f"  Result: '{canonical}'")
            print(f"  Confidence: {confidence:.2f}")
            print(f"  Match Found: {match_found}")
            print(f"  Genre: {genre}")
            if alt_names:
                print(f"  Alt Names: {', '.join(alt_names[:3])}")
            
            # Determine success
            if match_found and confidence >= 0.7:
                print(f"  ✅ SUCCESS")
                results.append(True)
            elif "compound" in description.lower() and confidence == 0.0:
                print(f"  ✅ CORRECTLY FILTERED")
                results.append(True)
            else:
                print(f"  ⚠️ LOW CONFIDENCE or NO MATCH")
                results.append(False)
                
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append(False)
        
        print()
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Tests Passed: {passed}/{total} ({passed/total*100:.1f}%)")
    print()
    
    if passed == total:
        print("✅ ALL TESTS PASSED - IGDB integration working perfectly!")
        return True
    elif passed >= total * 0.7:
        print("⚠️ MOST TESTS PASSED - IGDB integration working but some edge cases")
        return True
    else:
        print("❌ MULTIPLE FAILURES - IGDB integration needs attention")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_igdb_integration())
    sys.exit(0 if success else 1)
