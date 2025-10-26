#!/usr/bin/env python3
"""
IGDB Authentication Test Script

Tests IGDB API authentication and basic functionality using Twitch OAuth.
This script uses hardcoded credentials for testing purposes.
"""

import asyncio
import sys
from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp


# Hardcoded credentials for testing (from Railway environment)
TWITCH_CLIENT_ID = "a4ywgixzibm7pfxe68i5mdw8es2ewj"
TWITCH_CLIENT_SECRET = "ch4v94o302rv8dvyysmacywg8jk6oy"


def print_header(text: str):
    """Print a formatted header"""
    print("\n" + "━" * 60)
    print(f"  {text}")
    print("━" * 60)


def print_success(text: str):
    """Print success message"""
    print(f"✅ {text}")


def print_error(text: str):
    """Print error message"""
    print(f"❌ {text}")


def print_info(text: str):
    """Print info message"""
    print(f"ℹ️  {text}")


async def test_oauth_token() -> Optional[str]:
    """Test OAuth token retrieval from Twitch"""
    print_header("Step 1: OAuth Token Request")
    
    print_info(f"Client ID: {TWITCH_CLIENT_ID[:10]}...")
    print_info(f"Client Secret: {TWITCH_CLIENT_SECRET[:10]}...")
    
    try:
        async with aiohttp.ClientSession() as session:
            print_info("Requesting OAuth token from Twitch...")
            
            async with session.post(
                'https://id.twitch.tv/oauth2/token',
                params={
                    'client_id': TWITCH_CLIENT_ID,
                    'client_secret': TWITCH_CLIENT_SECRET,
                    'grant_type': 'client_credentials'
                }
            ) as response:
                print_info(f"Response status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    access_token = data.get('access_token')
                    expires_in = data.get('expires_in', 0)
                    
                    print_success(f"OAuth token obtained")
                    print_info(f"Token: {access_token[:20]}...")
                    print_info(f"Expires in: {expires_in} seconds ({expires_in / 3600:.1f} hours)")
                    
                    return access_token
                else:
                    response_text = await response.text()
                    print_error(f"Failed to get OAuth token: {response.status}")
                    print_error(f"Response: {response_text}")
                    return None
                    
    except Exception as e:
        print_error(f"Exception during OAuth request: {e}")
        return None


async def test_igdb_search(access_token: str, game_name: str) -> Optional[Dict[str, Any]]:
    """Test IGDB game search"""
    print_header(f"Step 2: IGDB Search - '{game_name}'")
    
    try:
        # Escape double quotes to prevent query injection
        game_name_escaped = game_name.replace('"', '\\"')
        
        async with aiohttp.ClientSession() as session:
            print_info("Sending search request to IGDB...")
            
            query = f'search "{game_name_escaped}"; fields name,alternative_names.name,franchises.name,genres.name,release_dates.y,cover.url; limit 3;'
            print_info(f"Query: {query}")
            
            async with session.post(
                'https://api.igdb.com/v4/games',
                headers={
                    'Client-ID': TWITCH_CLIENT_ID,
                    'Authorization': f'Bearer {access_token}'
                },
                data=query
            ) as response:
                print_info(f"Response status: {response.status}")
                
                if response.status == 200:
                    results = await response.json()
                    print_success(f"IGDB search successful")
                    print_info(f"Found {len(results)} result(s)")
                    
                    return results[0] if results else None
                else:
                    response_text = await response.text()
                    print_error(f"IGDB search failed: {response.status}")
                    print_error(f"Response: {response_text}")
                    return None
                    
    except Exception as e:
        print_error(f"Exception during IGDB search: {e}")
        return None


def display_game_data(game_data: Dict[str, Any]):
    """Display parsed game data"""
    print_header("Step 3: Parse Game Data")
    
    if not game_data:
        print_error("No game data to display")
        return
    
    print(f"\n📊 Game Information:")
    print(f"   Name: {game_data.get('name', 'N/A')}")
    print(f"   IGDB ID: {game_data.get('id', 'N/A')}")
    
    # Alternative names
    if 'alternative_names' in game_data and game_data['alternative_names']:
        alt_names = [alt.get('name') for alt in game_data['alternative_names']]
        print(f"   Alternative Names: {alt_names}")
    else:
        print(f"   Alternative Names: None")
    
    # Genres
    if 'genres' in game_data and game_data['genres']:
        genres = [genre.get('name') for genre in game_data['genres']]
        print(f"   Genres: {genres}")
    else:
        print(f"   Genres: None")
    
    # Franchises/Series
    if 'franchises' in game_data and game_data['franchises']:
        franchises = [franchise.get('name') for franchise in game_data['franchises']]
        print(f"   Series/Franchise: {franchises}")
    else:
        print(f"   Series/Franchise: None")
    
    # Release year
    if 'release_dates' in game_data and game_data['release_dates']:
        years = [rd.get('y') for rd in game_data['release_dates'] if rd.get('y')]
        if years:
            print(f"   Release Year(s): {sorted(set(years))}")
        else:
            print(f"   Release Year: None")
    else:
        print(f"   Release Year: None")
    
    # Cover
    if 'cover' in game_data and game_data['cover']:
        cover_url = game_data['cover'].get('url', 'N/A')
        print(f"   Cover URL: {cover_url}")


async def run_comprehensive_test():
    """Run comprehensive IGDB authentication test"""
    print_header("🧪 IGDB Authentication Test")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: OAuth Token
    access_token = await test_oauth_token()
    
    if not access_token:
        print_error("\n❌ OAuth authentication failed - cannot proceed")
        return False
    
    # Test 2: Search for well-known games
    test_games = [
        "Resident Evil 4",
        "The Last of Us Part II",
        "God of War"
    ]
    
    all_tests_passed = True
    
    for game_name in test_games:
        game_data = await test_igdb_search(access_token, game_name)
        
        if game_data:
            display_game_data(game_data)
        else:
            print_error(f"Failed to retrieve data for '{game_name}'")
            all_tests_passed = False
        
        # Small delay between requests
        await asyncio.sleep(0.3)
    
    # Final summary
    print_header("Test Summary")
    
    if all_tests_passed:
        print_success("All tests passed! IGDB authentication is working correctly.")
        print_info("The credentials are valid and the API is responding as expected.")
        return True
    else:
        print_error("Some tests failed. Check the output above for details.")
        return False


async def test_validation_function():
    """Test the actual validation function from igdb.py"""
    print_header("Step 4: Test validate_and_enrich() Function")
    
    # Import the actual module
    try:
        import sys
        import os
        
        # Add parent directory to path
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        
        from bot.integrations import igdb
        
        # Temporarily set environment variables
        os.environ['TWITCH_CLIENT_ID'] = TWITCH_CLIENT_ID
        os.environ['TWITCH_CLIENT_SECRET'] = TWITCH_CLIENT_SECRET
        
        print_info("Testing validate_and_enrich() function...")
        
        result = await igdb.validate_and_enrich("Resident Evil 4")
        
        print_success("Function executed successfully")
        print(f"\n📊 Validation Result:")
        print(f"   Canonical Name: {result.get('canonical_name')}")
        print(f"   Confidence: {result.get('confidence')}")
        print(f"   IGDB ID: {result.get('igdb_id')}")
        print(f"   Genre: {result.get('genre')}")
        print(f"   Series: {result.get('series_name')}")
        print(f"   Release Year: {result.get('release_year')}")
        print(f"   Alternative Names: {result.get('alternative_names', [])}")
        
        if result.get('confidence', 0) >= 0.8:
            print_success(f"High confidence match ({result.get('confidence')})")
        else:
            print_error(f"Low confidence match ({result.get('confidence')})")
        
        return True
        
    except Exception as e:
        print_error(f"Error testing validation function: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point"""
    try:
        # Run the comprehensive test
        loop = asyncio.get_event_loop()
        success = loop.run_until_complete(run_comprehensive_test())
        
        # Also test the actual module function
        print("\n")
        loop.run_until_complete(test_validation_function())
        
        print_header("✨ Testing Complete")
        
        if success:
            print_success("IGDB authentication is working correctly!")
            print_info("You can now run sync commands with confidence.")
            sys.exit(0)
        else:
            print_error("IGDB authentication has issues.")
            print_info("Review the output above for diagnostic information.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
