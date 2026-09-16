import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import argparse
import sys
import json

def run_inspector(title, platform="twitch", dry_run=False):
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "Live", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v

    if platform.lower() == "twitch" and not os.getenv("TWITCH_CLIENT_ID"):
        print("❌ ERROR: TWITCH_CLIENT_ID not found in environment.")
        sys.exit(1)
    elif platform.lower() == "youtube" and not os.getenv("YOUTUBE_API_KEY"):
        print("❌ ERROR: YOUTUBE_API_KEY not found in environment.")
        sys.exit(1)

    print("✅ API Credentials validated.")
    
    if dry_run:
        print(f"🔍 [DRY RUN] Would query {platform.upper()} API for stream/VOD with title: '{title}'")
        print("Run without --dry-run to execute the API call and run the extraction logic.")
        return
        
    print(f"📡 Querying {platform.upper()} API for '{title}'...")
    
    # Mocking the actual API call for this generic script, but it would normally hit the API here.
    # We will simulate passing it through the cleanup logic.
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    sys.path.insert(0, os.path.join(repo_dir, "Live"))
    
    try:
        from bot.integrations.twitch import cleanup_game_name
        canonical_name = cleanup_game_name(title)
        
        print("\n| Metric | Value |")
        print("| :--- | :--- |")
        print(f"| Platform | {platform.capitalize()} |")
        print(f"| Raw API Title | `{title}` |")
        print(f"| Parsed Canonical Name | `{canonical_name}` |")
        
        print("\nIf the Parsed Canonical Name does not match the database, you will need to add an alias.")
    except ImportError:
        print("⚠️ Warning: Could not import cleanup_game_name from Live/bot/integrations/twitch.py")
        print("Fallback analysis:")
        print(f"Raw Title: {title}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("title", help="The raw stream title to inspect")
    parser.add_argument("--platform", default="twitch", choices=["twitch", "youtube"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    run_inspector(args.title, args.platform, args.dry_run)
