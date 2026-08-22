import asyncio
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.database import get_database


def main():
    if len(sys.argv) < 2:
        print("Usage: python insert_trivia.py <path_to_json>")
        sys.exit(1)
        
    json_path = sys.argv[1]
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # The JSON should have two keys: 'clip_info' (from download_next_clip) and 'ai_analysis' (from Agent)
    clip_info = data.get("clip_info", {})
    ai_analysis = data.get("ai_analysis", {})
    
    canonical_url = clip_info.get("canonical_url")
    original_url = clip_info.get("clip_url")
    message_id = clip_info.get("message_id")
    author_id = clip_info.get("author_id")
    
    if not all([canonical_url, original_url, message_id]):
        print("Error: Missing clip metadata (canonical_url, original_url, or message_id)")
        sys.exit(1)
        
    db = get_database()
    
    success = db.trivia.add_clip_lore(
        canonical_url=canonical_url,
        original_url=original_url,
        game_title=ai_analysis.get("game_title", "Unknown"),
        reaction=ai_analysis.get("reaction", ""),
        trigger=ai_analysis.get("trigger", ""),
        lore_summary=ai_analysis.get("lore_summary", ""),
        notable_quote=ai_analysis.get("notable_quote", ""),
        emotion_category=ai_analysis.get("emotion_category", "Neutral"),
        characters_involved=ai_analysis.get("characters_involved", ""),
        clip_outcome=ai_analysis.get("clip_outcome", "Neutral"),
        submitted_by=str(author_id) if author_id else "0",
        message_id=int(message_id)
    )
    
    if success:
        print(f"Successfully inserted clip lore for {canonical_url}")
    else:
        print(f"Failed to insert clip lore for {canonical_url} (maybe it already exists?)")

if __name__ == "__main__":
    main()
