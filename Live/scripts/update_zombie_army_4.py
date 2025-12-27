"""
Update Zombie Army 4: Dead War Entry with Twitch VOD Data
Date: 2025-12-26
Purpose: Populate the Zombie Army 4 placeholder entry with Twitch VOD metadata
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import aiohttp
    from bot.database_module import get_database
    from bot.integrations.twitch import parse_twitch_duration
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Please ensure you are running this script from the correct directory.")
    sys.exit(1)


async def fetch_vod_data(vod_urls):
    """Fetch metadata for Twitch VODs"""
    # Get Twitch credentials and STRIP whitespace to prevent 400 errors
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID', '').strip()
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET', '').strip()
    
    if not twitch_client_id or not twitch_client_secret:
        print("❌ TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET required")
        print("   Please run with: export TWITCH_CLIENT_ID=... (or set env vars)")
        return None
    
    vod_data = []
    
    async with aiohttp.ClientSession() as session:
        try:
            # 1. Get OAuth token
            print("🔑 Requesting Twitch OAuth token...")
            token_url = "https://id.twitch.tv/oauth2/token"
            token_params = {
                'client_id': twitch_client_id,
                'client_secret': twitch_client_secret,
                'grant_type': 'client_credentials'
            }
            
            async with session.post(token_url, params=token_params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ Failed to get Twitch OAuth token: {response.status}")
                    print(f"   Twitch Response: {error_text}")
                    return None
                
                token_info = await response.json()
                access_token = token_info['access_token']
            
            headers = {
                "Client-ID": twitch_client_id,
                "Authorization": f"Bearer {access_token}"
            }
            
            # 2. Extract VOD IDs from URLs
            vod_ids = []
            for url in vod_urls:
                # Extract ID from url.split('/')[-1] -> remove query params
                vod_id = url.split('/')[-1].split('?')[0].strip()
                if vod_id.isdigit():
                    vod_ids.append(vod_id)
            
            if not vod_ids:
                print("❌ No valid numeric VOD IDs found in URLs.")
                return None
                
            print(f"📊 Fetching data for {len(vod_ids)} VODs...")
            
            # 3. Fetch VOD data
            videos_url = "https://api.twitch.tv/helix/videos"
            # Twitch allows max 100 IDs per request; we have fewer, so simple join is fine
            params = {
                "id": vod_ids
            }
            
            async with session.get(videos_url, params=params, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ Failed to fetch VOD data: {response.status}")
                    print(f"   Twitch Response: {error_text}")
                    return None
                
                videos_data = await response.json()
                data_list = videos_data.get('data', [])
                
                if not data_list:
                    print("⚠️ No data returned for these VOD IDs. Are they deleted or private?")
                    return None

                for video in data_list:
                    duration_str = video.get('duration', '0s')
                    duration_seconds = parse_twitch_duration(duration_str)
                    
                    vod_info = {
                        'url': video['url'],
                        'title': video['title'],
                        'duration_seconds': duration_seconds,
                        'duration_minutes': duration_seconds // 60,
                        'published_at': video['created_at'],
                        'view_count': int(video.get('view_count', 0))
                    }
                    vod_data.append(vod_info)
                    
                    print(f"✅ Found: {video['title'][:50]}...")
                    print(f"   Duration: {duration_seconds // 60}m | Date: {video['created_at']}")
                
                return vod_data
        
        except Exception as e:
            print(f"❌ Error fetching VOD data: {e}")
            import traceback
            traceback.print_exc()
            return None


async def update_zombie_army_4():
    """Main function to update Zombie Army 4 entry"""
    print("=" * 80)
    print("🧟 ZOMBIE ARMY 4: DEAD WAR - DATA UPDATE")
    print("=" * 80)
    
    # VOD URLs provided by user
    vod_urls = [
        "https://www.twitch.tv/videos/2620903257?filter=archives&sort=time",
        "https://www.twitch.tv/videos/2622563002?filter=archives&sort=time",
        "https://www.twitch.tv/videos/2624244748?filter=archives&sort=time",
        "https://www.twitch.tv/videos/2626881202?filter=archives&sort=time",
        "https://www.twitch.tv/videos/2628528499?filter=archives&sort=time",
        "https://www.twitch.tv/videos/2630093245?filter=archives&sort=time"
    ]
    
    # Fetch VOD data from Twitch API
    vod_data = await fetch_vod_data(vod_urls)
    
    if not vod_data:
        print("❌ Process aborted due to API errors.")
        return
    
    # Calculate totals
    total_duration_minutes = sum(vod['duration_minutes'] for vod in vod_data)
    total_duration_hours = total_duration_minutes // 60
    remaining_minutes = total_duration_minutes % 60
    
    # Get earliest published date for first_played_date
    # Twitch format: 2025-12-08T15:00:00Z
    published_dates = []
    for vod in vod_data:
        dt_str = vod['published_at'].replace('Z', '+00:00')
        published_dates.append(datetime.fromisoformat(dt_str))
        
    first_played_date = min(published_dates).date()
    
    # Prepare VOD URLs for database (clean URLs without query params)
    vod_urls_clean = [vod['url'].split('?')[0] for vod in vod_data]
    
    print("\n" + "=" * 80)
    print("📊 CALCULATED DATA:")
    print("=" * 80)
    print(f"Total Episodes: {len(vod_data)}")
    print(f"Total Playtime: {total_duration_hours}h {remaining_minutes}m ({total_duration_minutes} minutes)")
    print(f"First Played Date: {first_played_date}")
    print(f"VOD URLs: {len(vod_urls_clean)} URLs")
    
    # Database update
    try:
        db = get_database()
        print("\n" + "=" * 80)
        print("🔧 DATABASE OPERATIONS:")
        print("=" * 80)
        
        # Check if entry exists at id 142
        target_id = 142
        existing_game = db.get_played_game_by_id(target_id)
        
        if existing_game:
            print(f"✅ Found existing entry: {existing_game.get('canonical_name')}")
            
            # Update the entry
            update_success = db.update_played_game(
                target_id,
                total_episodes=len(vod_data),
                total_playtime_minutes=total_duration_minutes,
                first_played_date=first_played_date,
                twitch_vod_urls=vod_urls_clean,
                completion_status="completed", # Assuming completed based on context
                notes=f"Zombie Army 4: Dead War - Co-op campaign playthrough. {len(vod_data)} Twitch VODs, {total_duration_hours}h {remaining_minutes}m total playtime."
            )
            
            if update_success:
                print("✅ Successfully updated Zombie Army 4: Dead War entry")
            else:
                print("❌ Failed to update entry via db.update_played_game")
        else:
            print(f"❌ Entry at id {target_id} not found. Please verify the ID.")
        
        # Clean up malformed entries
        print("\n" + "-" * 40)
        print("🧹 Cleaning up malformed entries...")
        
        # Search for malformed "who's zombie army" entry
        malformed = db.get_played_game("who's zombie army")
        
        if malformed:
            print(f"⚠️ Found malformed entry: '{malformed.get('canonical_name')}' (id: {malformed.get('id')})")
            deleted = db.remove_played_game(malformed['id'])
            if deleted:
                print("✅ Successfully removed malformed entry")
            else:
                print("❌ Failed to remove malformed entry")
        else:
            print("ℹ️ No malformed 'who's zombie army' entry found")
            
    except Exception as e:
        print(f"❌ Database Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ ZOMBIE ARMY 4 UPDATE COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(update_zombie_army_4())