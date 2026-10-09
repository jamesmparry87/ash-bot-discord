import aiohttp
import asyncio
import os
import argparse
import sys

# Determine the absolute path to the Live directory
LIVE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LIVE_DIR = os.path.join(LIVE_DIR, "Live")

# Load environment variables
env_path = os.path.join(LIVE_DIR, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CLIPS_CHANNEL_ID = "1210874007591718982"

async def check_backlog(limit: int, dry_run: bool):
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_TOKEN not found in environment or Live/.env")
        sys.exit(1)
        
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    print(f"📡 Querying Discord API for the last {limit} messages in the clips channel...")
    
    all_messages = []
    before = None
    
    async with aiohttp.ClientSession() as session:
        while len(all_messages) < limit:
            batch_limit = min(100, limit - len(all_messages))
            url = f"https://discord.com/api/v10/channels/{CLIPS_CHANNEL_ID}/messages?limit={batch_limit}"
            if before:
                url += f"&before={before}"
                
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ Error fetching channel history: HTTP {response.status}\n{error_text}")
                    sys.exit(1)
                    
                batch = await response.json()
                if not batch:
                    break
                    
                all_messages.extend(batch)
                before = batch[-1]["id"]
        
        messages = all_messages
        
        unprocessed_count = 0
        unprocessed_urls = []
        
        for msg in messages:
            content = msg.get("content", "")
            if "clip" in content or "youtu" in content or "twitch.tv" in content:
                reactions = msg.get("reactions", [])
                has_check = any(r.get("emoji", {}).get("name") == "✅" for r in reactions)
                if not has_check:
                    unprocessed_count += 1
                    unprocessed_urls.append(content)
                        
        print("\n📊 Backlog Report:")
        print(f"Total messages scanned: {len(messages)}")
        print(f"Unprocessed clips (missing ✅): {unprocessed_count}")
        
        if dry_run:
            print("\n🔍 [DRY RUN] Would report these clips but not take further action.")
        else:
            if unprocessed_count > 0:
                print("\nList of unprocessed clip URLs:")
                for u in unprocessed_urls[:5]:
                    print(f" - {u.strip()}")
                if unprocessed_count > 5:
                    print(f" ... and {unprocessed_count - 5} more.")
                print("\nThese clips will be automatically processed during the next nightly batch job.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check Discord clips channel for unprocessed clips.")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")
    parser.add_argument("--limit", type=int, default=100, help="Number of messages to scan")
    args = parser.parse_args()
    
    # Ensure Windows prints emojis properly
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
        
    asyncio.run(check_backlog(args.limit, args.dry_run))
