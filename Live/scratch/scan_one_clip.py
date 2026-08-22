import asyncio
import os
import re

import requests

# Load environment
token = os.getenv("DISCORD_TOKEN")

import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.commands.clips import ClipParsingService, canonicalize_clip_url
from bot.database import get_database
from bot.handlers.ai_handler import initialize_ai_async


class MockUser:
    def __init__(self, id):
        self.id = id

class MockMessage:
    def __init__(self, id, author_id):
        self.id = id
        self.author = MockUser(author_id)

async def main():
    print("Starting background clip scan...")
    await initialize_ai_async()
    db = get_database()
    parser = ClipParsingService()
    
    headers = {
        "Authorization": f"Bot {token}"
    }
    
    channel_id = "1210874007591718982"
    url_base = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=100"
    url_pattern = re.compile(r'https?://(?:www\.)?(?:clips\.twitch\.tv/\S+|twitch\.tv/\w+/clip/\S+|youtube\.com/clip/\S+|youtube\.com/shorts/\S+|youtu\.be/clip/\S+)')
    
    last_msg_id = None
    messages_scanned = 0

    print("Fetching messages from Discord API to find an unprocessed clip...")
    while True:
        url = url_base
        if last_msg_id:
            url += f"&before={last_msg_id}"
            
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to fetch messages: {resp.status_code} {resp.text}")
            return
            
        messages = resp.json()
        if not messages:
            print("Reached the end of the channel.")
            break
            
        messages_scanned += len(messages)
        print(f"Scanned {messages_scanned} messages so far...")
        
        for msg in messages:
            content = msg.get("content", "")
            author_id = msg.get("author", {}).get("id")
            msg_id = msg.get("id")
            last_msg_id = msg_id
            
            match = url_pattern.search(content)
            if match:
                clip_url = match.group(0)
                canonical_url = canonicalize_clip_url(clip_url)
                
                if not db.trivia.clip_lore_exists(canonical_url):
                    print(f"Found unprocessed clip: {clip_url}")
                    mock_msg = MockMessage(int(msg_id), int(author_id))
                    
                    success = await parser.process_clip(clip_url, mock_msg)
                    if success:
                        print(f"Successfully processed clip {clip_url}")
                    else:
                        print(f"Failed to process clip {clip_url}")
                    
                    # Only process ONE clip
                    return
                else:
                    # Optional: uncomment to see skipped clips
                    # print(f"Skipping already processed clip: {clip_url}")
                    pass

    print(f"No unprocessed clips found after scanning {messages_scanned} messages.")

if __name__ == "__main__":
    asyncio.run(main())
