import sys
import re

with open(r'bot\handlers\ai_handler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update timeout_duration
content = content.replace(
    "timeout_duration = 20.0",
    "timeout_duration = 40.0  # Increased for trivia generation"
)

# 2. Add Recent Games & Clips to _build_full_system_instruction
# We want to add this right before returning the tuple at the end of _build_full_system_instruction
# Find the end of _build_full_system_instruction
build_pattern = re.compile(r"(        return base_instruction, dynamic_context\n\n    except Exception as e:\n        print\(f\"🚨 Error building system instruction: \{e\}\"\))", re.DOTALL)

recent_context_code = """
        # === ENHANCEMENT: Add recent games and clips for general conversational awareness ===
        try:
            current_db = _get_db()
            if current_db:
                recent_summary = "\\n\\n--- RECENT ACTIVITY (GAMES & CLIPS) ---\\n"
                has_recent = False
                
                # Fetch recent games
                if hasattr(current_db, 'get_gaming_timeline'):
                    recent_games = current_db.get_gaming_timeline(order='DESC')[:5]
                    if recent_games:
                        has_recent = True
                        recent_summary += "Recently Played Games (Newest First):\\n"
                        for g in recent_games:
                            recent_summary += f"  • {g['canonical_name']} (Genre: {g.get('genre', 'Unknown')})\\n"
                
                # Fetch recent clips
                if hasattr(current_db.trivia, 'get_recent_clip_lore'):
                    recent_clips = current_db.trivia.get_recent_clip_lore(limit=5)
                    if recent_clips:
                        has_recent = True
                        recent_summary += "\\nRecently Logged Twitch Clips:\\n"
                        for c in recent_clips:
                            recent_summary += f"  • {c['game_title']} - {c['trigger']}\\n"
                
                if has_recent:
                    recent_summary += "\\nNOTE: You have access to a comprehensive database of all played games and video clips. If a user asks about a specific game or provides a clip link that is not in this recent summary, the system will automatically query the database and provide you with that specific context in the user's message! You can use these two lists in combination to think creatively about Jonesy's recent activity.\\n"
                    recent_summary += "--- END RECENT ACTIVITY ---\\n"
                    dynamic_context += recent_summary
        except Exception as summary_err:
            print(f"⚠️ Error building recent activity summary: {summary_err}")
            
        return base_instruction, dynamic_context

    except Exception as e:
        print(f"🚨 Error building system instruction: {e}")"""

content = build_pattern.sub(recent_context_code, content)

# 3. Delete generate_contextual_trivia
gen_trivia_pattern = re.compile(r"async def generate_contextual_trivia.*?return robust_json_parse\(response_text\)\n\n", re.DOTALL)
content = gen_trivia_pattern.sub("", content)

with open(r'bot\handlers\ai_handler.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied for ai_handler.py")
