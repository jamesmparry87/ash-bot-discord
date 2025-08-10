import json
import re
from database import db
from typing import List, Dict

def parse_games_list(games_text: str) -> List[Dict[str, str]]:
    """Parse the games list text into structured data"""
    games = []
    lines = games_text.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.lower().startswith('games list') or line.lower().startswith('suggested so far'):
            continue
        
        # Check if line has " - username" format
        if ' - ' in line:
            parts = line.rsplit(' - ', 1)  # Split from the right to handle game names with dashes
            game_name = parts[0].strip()
            username = parts[1].strip()
        else:
            game_name = line.strip()
            username = ""  # No username provided
        
        if game_name:
            games.append({
                'name': game_name,
                'reason': f"Suggested by community member",
                'added_by': username
            })
    
    return games

def load_strikes_from_json(json_file_path: str) -> Dict[int, int]:
    """Load strikes data from JSON file"""
    try:
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        
        # Convert string keys to integers
        strikes_data = {}
        for user_id_str, count in data.items():
            try:
                user_id = int(user_id_str)
                strikes_data[user_id] = int(count)
            except ValueError:
                print(f"Warning: Invalid user ID or count: {user_id_str} -> {count}")
        
        return strikes_data
    except Exception as e:
        print(f"Error loading strikes from JSON: {e}")
        return {}

def migrate_strikes_data(json_file_path: str = "strikes.json") -> int:
    """Migrate strikes data from JSON file to database"""
    print("Loading strikes data from JSON...")
    strikes_data = load_strikes_from_json(json_file_path)
    
    if not strikes_data:
        print("No strikes data found or failed to load.")
        return 0
    
    print(f"Found {len(strikes_data)} users with strike data")
    
    # Import to database
    imported_count = db.bulk_import_strikes(strikes_data)
    print(f"Successfully imported {imported_count} strike records to database")
    
    return imported_count

def migrate_games_data(games_text: str) -> int:
    """Migrate games data from text list to database"""
    print("Parsing games list...")
    games_data = parse_games_list(games_text)
    
    if not games_data:
        print("No games data found or failed to parse.")
        return 0
    
    print(f"Parsed {len(games_data)} game recommendations")
    
    # Show sample of parsed data
    print("\nSample of parsed games:")
    for i, game in enumerate(games_data[:5]):
        print(f"  {i+1}. '{game['name']}' by '{game['added_by']}'")
    if len(games_data) > 5:
        print(f"  ... and {len(games_data) - 5} more")
    
    # Import to database
    imported_count = db.bulk_import_games(games_data)
    print(f"Successfully imported {imported_count} game recommendations to database")
    
    return imported_count

def full_migration(games_text: str, strikes_json_path: str = "strikes.json"):
    """Perform full data migration"""
    print("=== Starting Full Data Migration ===\n")
    
    # Migrate strikes
    print("1. Migrating Strikes Data:")
    strikes_imported = migrate_strikes_data(strikes_json_path)
    
    print("\n" + "="*50 + "\n")
    
    # Migrate games
    print("2. Migrating Games Data:")
    games_imported = migrate_games_data(games_text)
    
    print("\n=== Migration Complete ===")
    print(f"Total strikes imported: {strikes_imported}")
    print(f"Total games imported: {games_imported}")

# Sample games text for testing
SAMPLE_GAMES_TEXT = """
telltale the walking dead
resident evil 2
resident evil village
sekiro: shadows die twice
dark souls
dark souls 3
demon's souls
darksiders
the quarry
until dawn
detroit become human
stellar blade
life is strange
mortuary assistant
prototype
metro trilogy
doom
bully
star wars jedi: fallen order
star wars jedi: survivor
call of duty: black ops 3
mass effect trilogy
days gone
rage 2
splinter cell
armoured core 6
sniper elite 5
deliver us the moon
sleeping dogs
mad max
signalis - popsarcade
lies of p - hovscorpion12
socom: u.s. navy seals - lubu1950
yakuza - lubu1950
ace combat 7 - lubu1950
prey - mysticaldragonborn
far cry series - mcpeteface
dishonored - mysticaldragonborn
crysis remastered - bubbamattx
chernbylite - mysticaldragonborn
lollipop chainsaw repop - barrymk400
assassins creed black flag - mcpeteface
scars above - mysticaldragonborn
wolfenstein - mysticaldragonborn
splinter cell series - lubu1950
ace combat 3-6 - lubu1950
tenchu series - lubu1950
assassin's creed origins - mysticaldragonborn
silent hill 2-original and remake - popsarcade
black myth: wukong - mcpeteface
still wakes the deep - darkmatter
tales from the borderlands - katzenscaboose
ryse: son of rome - katzenscaboose
garden life a cozy simulator - mysticaldragonborn
sniper ghost warrior contracts 2 - mysticaldragonborn
maneater - mysticaldragonborn
house flipper 2 - mysticaldragonborn
quantum break - katzenscaboose
stalker 2 - katzenscaboose
squirrel with a gun - popsarcade
gta iii / vice city / san andreas - definitive edition - el_matheus_dantas
my time at sandrock - mysticaldragonborn
the outer worlds - mcpeteface
black mirror ps4 - mysticaldragonborn
max payne (series) - el_matheus_dantas
jusant - katzenscaboose
shadow of the colossus - katzenscaboose
silent hill 2 remake - mysticaldragonborn
spirit of the north - mysticaldragonborn
gears of war judgement - saints96
crimson snow - popsarcade
phoenix wright ace attorney - saints96
stars in the trash (steam) - katzenscaboose
the thing remastered - katzenscaboose
alone in the dark - saints96
transformers: fall of cybertron - castintheshadows
dues ex (2000) - castintheshadows
terminator: resistance - castintheshadows
amanda the adventurer - king_group
titanfall 2 - castintheshadows
bully (bully: scholarship edition) - zlluksnikuyr
the invincible - katzenscaboose
spiritfarer - ozric42
"""

if __name__ == "__main__":
    # Run the migration with the sample data
    full_migration(SAMPLE_GAMES_TEXT.strip())
