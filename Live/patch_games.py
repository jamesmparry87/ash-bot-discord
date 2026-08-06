import os
import re

content = ""
with open(r'bot\database\games.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add completed_date parameter to add_played_game
content = re.sub(
    r"first_played_date:\s*Optional\[str\]\s*=\s*None,",
    "first_played_date: Optional[str] = None,\n                        completed_date: Optional[str] = None,",
    content
)

# 2. Update INSERT query in add_played_game
content = content.replace(
    "release_year, first_played_date, completion_status, total_episodes,",
    "release_year, first_played_date, completed_date, completion_status, total_episodes,"
)

# Fix VALUES string (%s string)
content = content.replace(
    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
    ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
)

# Add parameter to execution tuple
content = content.replace(
    "                    first_played_date,\n                    completion_status,\n",
    "                    first_played_date,\n                    completed_date,\n                    completion_status,\n"
)

# 3. Update update_played_game signature or wherever it iterates updates
# update_played_game just takes **kwargs and iterates over them, so it natively supports completed_date!
# Lines around 994: valid_fields list
content = content.replace(
    "'first_played_date',\n",
    "'first_played_date',\n                    'completed_date',\n"
)

# 4. In add_or_update_game (line 1195 approx) where it extracts kwargs
content = content.replace(
    "'first_played_date', 'completion_status', 'total_episodes',",
    "'first_played_date', 'completed_date', 'completion_status', 'total_episodes',"
)

content = content.replace(
    "game_data.get('first_played_date'),\n",
    "game_data.get('first_played_date'),\n                                game_data.get('completed_date'),\n"
)

# 5. In sync duplicate games (merge logic)
content = content.replace(
    "\"first_played_date\": master_game.get(\"first_played_date\"),",
    "\"first_played_date\": master_game.get(\"first_played_date\"),\n                        \"completed_date\": master_game.get(\"completed_date\"),"
)

merge_replacement = """                        if duplicate_game.get("first_played_date"):
                            if (
                                not merged_data["first_played_date"] or
                                duplicate_game["first_played_date"] < merged_data["first_played_date"]
                            ):
                                merged_data["first_played_date"] = duplicate_game["first_played_date"]

                        # Use latest completed_date
                        if duplicate_game.get("completed_date"):
                            if (
                                not merged_data["completed_date"] or
                                duplicate_game["completed_date"] > merged_data["completed_date"]
                            ):
                                merged_data["completed_date"] = duplicate_game["completed_date"]"""

content = content.replace(
    """                        if duplicate_game.get("first_played_date"):
                            if (
                                not merged_data["first_played_date"] or
                                duplicate_game["first_played_date"] < merged_data["first_played_date"]
                            ):
                                merged_data["first_played_date"] = duplicate_game["first_played_date"]""",
    merge_replacement
)

content = content.replace(
    "first_played_date = %s,\n",
    "first_played_date = %s,\n                            completed_date = %s,\n"
)

content = content.replace(
    "merged_data['first_played_date'],\n",
    "merged_data['first_played_date'],\n                        merged_data.get('completed_date'),\n"
)

# Save
with open(r'bot\database\games.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("games.py patched")
