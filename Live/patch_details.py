import sys
import re

with open(r'bot\handlers\queries\details.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace return signatures
content = content.replace(
    "async def handle_game_status_query(\n        message: discord.Message,\n        match: Match[str]) -> None:",
    "async def handle_game_status_query(\n        message: discord.Message,\n        match: Match[str]) -> bool:"
)

content = content.replace(
    "async def handle_game_details_query(\n        message: discord.Message,\n        match: Match[str]) -> None:",
    "async def handle_game_details_query(\n        message: discord.Message,\n        match: Match[str]) -> bool:"
)

# Return True/False changes for early returns
content = content.replace(
    "await message.reply(\"Database analysis systems offline. Game status queries unavailable.\")\n        return",
    "await message.reply(\"Database analysis systems offline. Game status queries unavailable.\")\n        return True"
)

content = content.replace(
    "await message.reply(\"Database analysis systems offline. Game detail queries unavailable.\")\n        return",
    "await message.reply(\"Database analysis systems offline. Game detail queries unavailable.\")\n        return True"
)

content = content.replace(
    "return\n\n    # Search for the game in PLAYED GAMES database",
    "return True\n\n    # Search for the game in PLAYED GAMES database"
)

# For status query
status_split = content.split("    if played_game:\n        # Game found in played games database - enhanced response with\n        # conversational follow-ups")
if len(status_split) == 2:
    status_part1 = status_split[0]
    status_part2 = status_split[1]
    
    # find where details query starts
    end_of_status_idx = status_part2.find("async def handle_game_details_query")
    
    status_replacement = """    if played_game:
        # Generate dynamic response using AI
        from ..ai_handler import call_ai_for_generation
        
        system_prompt = \"\"\"You are Ash, the ship's AI computer. The user has asked if Captain Jonesy played a specific game or for its completion status. 
Respond dynamically and concisely. Use the following data.
Game: {game_name}
Status: {status}
Episodes: {episodes}
Completed Date: {completed_date}
\"\"\"
        system_prompt = system_prompt.format(
            game_name=played_game['canonical_name'],
            status=played_game.get('completion_status', 'unknown'),
            episodes=played_game.get('total_episodes', 0),
            completed_date=played_game.get('completed_date', 'unknown')
        )
        
        response, _ = await call_ai_for_generation(system_prompt, message.content)
        if not response:
            response = f"Affirmative. Captain Jonesy has played '{played_game['canonical_name']}'."
        await message.reply(response)
        return True
    else:
        # Game not found in played games database
        return False

"""
    content = status_part1 + status_replacement + status_part2[end_of_status_idx:]

# For details query
details_split = content.split("    if played_game:\n        playtime_minutes = played_game.get('total_playtime_minutes', 0)")
if len(details_split) == 2:
    details_part1 = details_split[0]
    details_part2 = details_split[1]
    
    # find where recommendation query starts
    end_of_details_idx = details_part2.find("async def handle_recommendation_query")
    
    details_replacement = """    if played_game:
        from ..ai_handler import call_ai_for_generation
        
        system_prompt = \"\"\"You are Ash, the ship's AI computer. The user is asking for details/playtime about a specific game Jonesy played.
Respond dynamically and concisely. Use the following data:
Game: {game_name}
Status: {status}
Episodes: {episodes}
Playtime (minutes): {playtime}
Completed Date: {completed_date}
\"\"\"
        system_prompt = system_prompt.format(
            game_name=played_game['canonical_name'],
            status=played_game.get('completion_status', 'unknown'),
            episodes=played_game.get('total_episodes', 0),
            playtime=played_game.get('total_playtime_minutes', 0),
            completed_date=played_game.get('completed_date', 'unknown')
        )
        
        response, _ = await call_ai_for_generation(system_prompt, message.content)
        if not response:
            response = f"Captain Jonesy has invested {played_game.get('total_playtime_minutes', 0)} minutes in '{played_game['canonical_name']}'."
        await message.reply(response)
        return True
    else:
        # Game not found
        return False

"""
    content = details_part1 + details_replacement + details_part2[end_of_details_idx:]

with open(r'bot\handlers\queries\details.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied properly")
