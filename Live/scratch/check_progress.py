from bot.database import get_database
import asyncio
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# pyrefly: ignore [missing-import]


def main():
    db = get_database()
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM clip_lore")
            total_processed = cur.fetchone()['count']

            # Get the most recently processed ones
            cur.execute("SELECT game_title FROM clip_lore LIMIT 5")
            recent_clips = cur.fetchall()

            print(f"Total Clips Processed and Saved: {total_processed}\n")
            print("Some Processed Clips:")
            for clip in recent_clips:
                print(f" - {clip['game_title']}")

    except Exception as e:
        print(f"Error querying database: {e}")
    finally:
        conn.close()

    state_file = "data/clip_scan_state.json"
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            state = json.load(f)
            last_msg = state.get("last_scanned_message_id")
            print(f"\nPagination State: Currently scanning backwards from Discord Message ID: {last_msg}")


if __name__ == "__main__":
    main()
