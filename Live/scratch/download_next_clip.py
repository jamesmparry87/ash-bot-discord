from bot.database import get_database
from bot.commands.clips import ClipParsingService, canonicalize_clip_url
import sys
import asyncio
import json
import os
import re

import requests

# Load environment
token = os.getenv("DISCORD_TOKEN")


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def main():
    db = get_database()
    parser = ClipParsingService()

    headers = {
        "Authorization": f"Bot {token}"
    }

    channel_id = "1210874007591718982"
    url_base = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=100"
    url_pattern = re.compile(
        r'https?://(?:www\.)?(?:clips\.twitch\.tv/\S+|twitch\.tv/\w+/clip/\S+|youtube\.com/clip/\S+|youtube\.com/shorts/\S+|youtu\.be/clip/\S+)')

    # Check if there is a saved state for pagination
    state_file = "data/clip_scan_state.json"
    last_msg_id = None
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                state = json.load(f)
                last_msg_id = state.get("last_scanned_message_id")
        except Exception:
            pass

    while True:
        url = url_base
        if last_msg_id:
            url += f"&before={last_msg_id}"

        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print(json.dumps({"error": f"Failed to fetch messages: {resp.status_code} {resp.text}"}))
            return

        messages = resp.json()
        if not messages:
            print(json.dumps({"error": "Reached the end of the channel."}))
            break

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
                    file_id = f"clip_{msg_id}"
                    local_filename = f"temp/{file_id}.mp4"
                    os.makedirs("temp", exist_ok=True)

                    download_result = await asyncio.to_thread(parser._download_video_sync, clip_url, local_filename)
                    if not download_result or not os.path.exists(local_filename):
                        print(json.dumps({"error": f"Failed to download video from {clip_url}"}))
                        return

                    # Save state for next run
                    os.makedirs("data", exist_ok=True)
                    with open(state_file, 'w') as f:
                        json.dump({"last_scanned_message_id": msg_id}, f)

                    result = {
                        "message_id": msg_id,
                        "author_id": author_id,
                        "clip_url": clip_url,
                        "canonical_url": canonical_url,
                        "local_path": os.path.abspath(local_filename)
                    }
                    print(json.dumps(result))
                    return

    print(json.dumps({"error": "No unprocessed clips found."}))

if __name__ == "__main__":
    asyncio.run(main())
