"""
Manual Twitch VOD to Game Mapping Script
Date: 2025-12-26
Purpose: Manually map 25 Twitch VODs to database games for bulk stats update
"""

import asyncio
import os
import sys
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.database_module import get_database
from bot.integrations.twitch import parse_twitch_duration
import aiohttp


async def fetch_all_vods(username: str, session: aiohttp.ClientSession, headers: dict) -> List[Dict[str, Any]]:
    """Fetch ALL VODs from Twitch channel"""
    # Get user ID
    user_url = f"https://api.twitch.tv/helix/users?login={username}"
    
    async with session.get(user_url, headers=headers) as response:
        if response.status != 200:
            print(f"❌ Failed to get user ID: {response.status}")
            return []
        
        user_data = await response.json()
        if not user_data.get('data'):
            print(f"❌ User '{username}' not found")
            return []
        
        user_id = user_data['data'][0]['id']
    
    # Fetch VODs
    all_vods = []
    cursor = None
    
    while True:
        videos_url = "https://api.twitch.tv/helix/videos"
        params = {
            "user_id": user_id,
            "first": 100,
            "type": "archive"
        }
        
        if cursor:
            params['after'] = cursor
        
        async with session.get(videos_url, params=params, headers=headers) as response:
            if response.status != 200:
                break
            
            videos_data = await response.json()
            vods = videos_data.get('data', [])
            
            if not vods:
                break
            
            all_vods.extend(vods)
            cursor = videos_data.get('pagination', {}).get('cursor')
            if not cursor:
                break
    
    return all_vods


async def manual_mapping():
    """Interactive manual mapping of VODs to games"""
    print("=" * 80)
    print("🎮 MANUAL TWITCH VOD MAPPING")
    print("=" * 80)
    
    # Check credentials
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID', '').strip()
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET', '').strip()
    
    if not twitch_client_id or not twitch_client_secret:
        print("❌ TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET required")
        return
    
    # Get database
    db = get_database()
    
    # Fetch database games
    print("\n📚 Loading database games...")
    all_games = db.get_all_played_games()
    print(f"✅ Found {len(all_games)} games in database")
    
    # Create lookup dictionary
    game_lookup = {}
    for i, game in enumerate(all_games, 1):
        name = game.get('canonical_name', 'Unknown')
        game_lookup[i] = {
            'id': game.get('id'),
            'name': name,
            'alt_names': game.get('alternative_names', [])
        }
    
    # Fetch VODs
    twitch_username = "jonesyspacecat"
    
    async with aiohttp.ClientSession() as session:
        # Get OAuth token
        print(f"\n🔑 Authenticating with Twitch...")
        token_url = "https://id.twitch.tv/oauth2/token"
        token_params = {
            'client_id': twitch_client_id,
            'client_secret': twitch_client_secret,
            'grant_type': 'client_credentials'
        }
        
        async with session.post(token_url, params=token_params) as response:
            if response.status != 200:
                print(f"❌ Failed to authenticate")
                return
            
            token_info = await response.json()
            access_token = token_info['access_token']
        
        headers = {
            "Client-ID": twitch_client_id,
            "Authorization": f"Bearer {access_token}"
        }
        
        print(f"\n📡 Fetching VODs from '{twitch_username}'...")
        all_vods = await fetch_all_vods(twitch_username, session, headers)
        
        if not all_vods:
            print("❌ No VODs found")
            return
        
        print(f"✅ Found {len(all_vods)} VODs")
        
        # Interactive mapping
        print("\n" + "=" * 80)
        print("INTERACTIVE MAPPING")
        print("=" * 80)
        print("\nFor each VOD, enter the NUMBER of the matching game from the list below.")
        print("Enter 'skip' to skip a VOD, or 'quit' to exit.\n")
        
        # Show game list
        print("📋 AVAILABLE GAMES IN DATABASE:")
        print("-" * 80)
        for i, game_info in game_lookup.items():
            alt_names = game_info['alt_names']
            alt_str = f" (aka: {', '.join(alt_names[:3])})" if alt_names else ""
            print(f"  {i:2d}. {game_info['name']}{alt_str}")
        print("-" * 80)
        
        # Manual mapping
        vod_mapping = {}  # vod_index -> game_number
        
        for i, vod in enumerate(all_vods, 1):
            title = vod.get('title', 'Unknown')
            duration = vod.get('duration', '0s')
            views = vod.get('view_count', 0)
            
            print(f"\n[VOD {i}/{len(all_vods)}]")
            print(f"  Title: {title}")
            print(f"  Duration: {duration} | Views: {views:,}")
            
            while True:
                user_input = input(f"  → Enter game number (1-{len(game_lookup)}), 'skip', or 'quit': ").strip().lower()
                
                if user_input == 'quit':
                    print("\n⚠️ Quitting mapping process...")
                    return
                
                if user_input == 'skip':
                    print("  ⏭️ Skipped")
                    break
                
                try:
                    game_num = int(user_input)
                    if 1 <= game_num <= len(game_lookup):
                        game_name = game_lookup[game_num]['name']
                        vod_mapping[i-1] = game_num  # Store 0-indexed VOD index
                        print(f"  ✅ Mapped to: {game_name}")
                        break
                    else:
                        print(f"  ❌ Invalid number. Must be 1-{len(game_lookup)}")
                except ValueError:
                    print("  ❌ Invalid input. Enter a number, 'skip', or 'quit'")
        
        if not vod_mapping:
            print("\n⚠️ No VODs were mapped. Exiting.")
            return
        
        # Group VODs by game
        print("\n" + "=" * 80)
        print("📊 MAPPING SUMMARY")
        print("=" * 80)
        
        game_vods = defaultdict(list)
        for vod_idx, game_num in vod_mapping.items():
            game_vods[game_num].append(all_vods[vod_idx])
        
        for game_num in sorted(game_vods.keys()):
            game_name = game_lookup[game_num]['name']
            vod_count = len(game_vods[game_num])
            print(f"  {game_name}: {vod_count} VODs")
        
        # Calculate stats and update
        print("\n" + "=" * 80)
        print("💾 UPDATING DATABASE")
        print("=" * 80)
        
        updated_count = 0
        
        for game_num, vods in game_vods.items():
            game_id = game_lookup[game_num]['id']
            game_name = game_lookup[game_num]['name']
            
            # Calculate stats
            total_watch_minutes = 0
            total_views = 0
            vod_urls = []
            
            for vod in vods:
                duration_seconds = parse_twitch_duration(vod.get('duration', '0s'))
                total_watch_minutes += duration_seconds // 60
                total_views += int(vod.get('view_count', 0))
                if len(vod_urls) < 10:
                    vod_urls.append(vod['url'].split('?')[0])
            
            # Update database
            success = db.update_played_game(
                game_id,
                total_episodes=len(vods),
                total_playtime_minutes=total_watch_minutes,
                twitch_vod_urls=vod_urls
            )
            
            if success:
                print(f"  ✅ {game_name}:")
                print(f"     {total_watch_minutes//60}h {total_watch_minutes%60}m | {len(vods)} VODs | {total_views:,} views")
                updated_count += 1
            else:
                print(f"  ❌ Failed to update {game_name}")
        
        # Final summary
        print("\n" + "=" * 80)
        print("✅ MAPPING COMPLETE")
        print("=" * 80)
        print(f"  Total VODs: {len(all_vods)}")
        print(f"  Mapped: {len(vod_mapping)}")
        print(f"  Updated: {updated_count} games")
        print(f"  Skipped: {len(all_vods) - len(vod_mapping)} VODs")


if __name__ == "__main__":
    asyncio.run(manual_mapping())
