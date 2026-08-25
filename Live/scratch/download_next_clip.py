import asyncio
import json
import os
import re
import sys

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.commands.clips import ClipParsingService, canonicalize_clip_url
from bot.database import get_database

# Load environment
token = os.getenv("DISCORD_TOKEN")


async def main():
    db = get_database()
    parser = ClipParsingService()

    batch_size = 10
    if len(sys.argv) > 1:
        try:
            batch_size = int(sys.argv[1])
        except ValueError:
            pass

    headers = {
        "Authorization": f"Bot {token}"
    }

    channel_id = "1210874007591718982"
    url_base = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=100"
    url_pattern = re.compile(
        r'https?://(?:www\.)?(?:clips\.twitch\.tv/\S+|twitch\.tv/\w+/clip/\S+|youtube\.com/clip/\S+|youtube\.com/shorts/\S+|youtu\.be/clip/\S+)')

    state_file = "data/clip_scan_state.json"
    last_msg_id = None
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
                last_msg_id = state.get("last_scanned_message_id")
        except Exception:
            pass

    results = []

    while len(results) < batch_size:
        url = url_base
        if last_msg_id:
            url += f"&before={last_msg_id}"

        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            if not results:
                print(json.dumps({"error": f"Failed to fetch messages: {resp.status_code} {resp.text}"}))
                return
            break

        messages = resp.json()
        if not messages:
            if not results:
                print(json.dumps({"error": "Reached the end of the channel."}))
                return
            break

        for msg in messages:
            if len(results) >= batch_size:
                break

            content = msg.get("content", "")
            author_id = msg.get("author", {}).get("id")
            msg_id = msg.get("id")
            last_msg_id = msg_id

            # Save state immediately so we don't re-scan if next clip fails
            os.makedirs("data", exist_ok=True)
            with open(state_file, 'w') as f:
                json.dump({"last_scanned_message_id": msg_id}, f)

            match = url_pattern.search(content)
            if match:
                clip_url = match.group(0)
                canonical_url = canonicalize_clip_url(clip_url)

                if not db.trivia.clip_lore_exists(canonical_url):
                    file_id = f"clip_{msg_id}"
                    local_filename = f"temp/{file_id}.mp4"
                    os.makedirs("temp", exist_ok=True)

                    download_result = await asyncio.to_thread(parser._download_video_sync, clip_url, local_filename)
                    if not download_result or not os.path.exists(local_filename):
                        continue # Skip failed downloads and keep looking

                    results.append({
                        "message_id": msg_id,
                        "author_id": author_id,
                        "clip_url": clip_url,
                        "canonical_url": canonical_url,
                        "local_path": os.path.abspath(local_filename)
                    })

    if results:
        print(json.dumps(results))
    else:
        print(json.dumps({"error": "No unprocessed clips found."}))

if __name__ == "__main__":
    asyncio.run(main())
