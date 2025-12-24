import json
import re
from datetime import datetime

# --- CONFIGURATION: FIX BAD DATES HERE ---
# Format: "Canonical Name": "YYYY-MM-DD"
# I have added a few that looked wrong (2025 dates for old games), 
# but please verify/add more here!
MANUAL_DATE_FIXES = {
    "Star Wars Jedi: Fallen Order": "2019-11-15", 
    "Grand Theft Auto: San Andreas": "2004-10-26", 
    "Wolfenstein: The New Order": "2014-05-20",
    "Mafia: The Old Country": "2025-12-31", # Keep as future if unreleased
    "Platinum Push": "2025-11-14", # Keep if accurate
    # Add any other games here that are sorting wrongly
}

# --- RAW DATA (Your latest backup) ---
RAW_DATA = [
  {
    "id": 53,
    "canonical_name": "Fallout: New Vegas",
    "alternative_names": "[\"FNV\", \"New Vegas\", \"NV\"]",
    "series_name": "Fallout",
    "release_year": 2010,
    "first_played_date": "2021-03-19"
  },
  {
    "id": 16,
    "canonical_name": "Gears of War",
    "alternative_names": "[]",
    "series_name": "Gears of War",
    "release_year": 2007,
    "first_played_date": "2024-07-30"
  },
  {
    "id": 1,
    "canonical_name": "God of War",
    "alternative_names": "[\"GOW\", \"God of War: New Omega\", \"God of War 4\", \"Deus da Guerra\", \"God of War IV\"]",
    "series_name": "God of War",
    "release_year": 2022,
    "first_played_date": "2021-06-28"
  },
  {
    "id": 35,
    "canonical_name": "God of War Ragnarök",
    "alternative_names": "[\"God of War Part II\", \"God of War: Ragnarok\", \"God of War Ragnarok\", \"God of War: Ragnar\\u00f6k\"]",
    "series_name": "God of War",
    "release_year": 2024,
    "first_played_date": "2022-11-09"
  },
  {
    "id": 17,
    "canonical_name": "Halo 3",
    "alternative_names": "[\"H3\"]",
    "series_name": "Halo",
    "release_year": 2007,
    "first_played_date": "2024-07-09"
  },
  {
    "id": 28,
    "canonical_name": "Grand Theft Auto IV: The Ballad of Gay Tony",
    "alternative_names": "[\"GTA IV: TBoGT\", \"Grand Theft Auto: The Ballad of Gay Tony\", \"GTA: The Ballad of Gay Tony\", \"The Ballad of Gay Tony\"]",
    "series_name": "Grand Theft Auto",
    "release_year": 2010,
    "first_played_date": "2023-07-09"
  },
  {
    "id": 29,
    "canonical_name": "Grand Theft Auto IV: The Lost and Damned",
    "alternative_names": "[\"GTA IV: TLAD\", \"Grand Theft Auto: The Lost and Damned\", \"GTA: The Lost and Damned\", \"The Lost and Damned\"]",
    "series_name": "Grand Theft Auto",
    "release_year": 2010,
    "first_played_date": "2023-06-01"
  },
  {
    "id": 19,
    "canonical_name": "Halo: Combat Evolved",
    "alternative_names": "[\"Halo CE HD\", \"Halo HD\", \"Halo: Combat Evolved Anniversary\", \"Halo CEA\", \"Halo: CE\"]",
    "series_name": "Halo",
    "release_year": 2002,
    "first_played_date": "2024-05-01"
  },
  {
    "id": 18,
    "canonical_name": "Halo 2",
    "alternative_names": "[\"H2\", \"H2\", \"Halo 2 for Windows Vista\"]",
    "series_name": "Halo",
    "release_year": 2004,
    "first_played_date": "2024-05-30"
  },
  {
    "id": 26,
    "canonical_name": "Outlast",
    "alternative_names": "[\"Outlast 1\"]",
    "series_name": "Outlast",
    "release_year": 2014,
    "first_played_date": "2023-10-01"
  },
  {
    "id": 15,
    "canonical_name": "Silent Hill 2",
    "alternative_names": "[\"Silent Hill 2 HD\"]",
    "series_name": "Silent Hill",
    "release_year": 2012,
    "first_played_date": "2024-10-28"
  },
  {
    "id": 48,
    "canonical_name": "Bloodborne",
    "alternative_names": "[\"Project Beast\"]",
    "series_name": "Souls",
    "release_year": 2015,
    "first_played_date": "2021-09-29"
  },
  {
    "id": 11,
    "canonical_name": "The Walking Dead",
    "alternative_names": "[\"The Walking Dead: The Game\", \"TWD\", \"The Walking Dead: Season One\", \"The Walking Dead: A Telltale Games Series\", \"The Walking Dead: The Complete First Season\"]",
    "series_name": "The Walking Dead",
    "release_year": 2013,
    "first_played_date": "2025-04-17"
  },
  {
    "id": 34,
    "canonical_name": "The Callisto Protocol",
    "alternative_names": "[]",
    "series_name": "The Callisto Protocol",
    "release_year": 2022,
    "first_played_date": "2022-12-05"
  },
  {
    "id": 37,
    "canonical_name": "Alien: Isolation",
    "alternative_names": "[\"Alien: Isolation Mobile\", \"Alien Isolation iOS and Android\"]",
    "series_name": "Alien",
    "release_year": 2021,
    "first_played_date": "2022-10-13"
  },
  {
    "id": 30,
    "canonical_name": "Batman: Arkham Asylum",
    "alternative_names": "[\"Batman:AA\", \"B:AA\", \"Arkham Asylum\"]",
    "series_name": "Batman",
    "release_year": 2009,
    "first_played_date": "2023-05-14"
  },
  {
    "id": 20,
    "canonical_name": "Elden Ring",
    "alternative_names": "[\"Great Rune\", \"ELDEN RING\"]",
    "series_name": "Elden Ring",
    "release_year": 2022,
    "first_played_date": "2024-04-14"
  },
  {
    "id": 10,
    "canonical_name": "Gears of War 4",
    "alternative_names": "[\"GoW 4\", \"Gears 4\"]",
    "series_name": "Gears of War",
    "release_year": 2016,
    "first_played_date": "2024-08-22"
  },
  {
    "id": 39,
    "canonical_name": "Ghost of Tsushima",
    "alternative_names": "[]",
    "series_name": "Ghost Of Tsushima",
    "release_year": 2020,
    "first_played_date": "2022-06-19"
  },
  {
    "id": 12,
    "canonical_name": "Grand Theft Auto: San Andreas",
    "alternative_names": "[\"GTA: SA\", \"GTA: San Andreas\", \"San Andreas\", \"GTA San Andreas\"]",
    "series_name": "Grand Theft Auto",
    "release_year": 2015,
    "first_played_date": "2025-02-06"
  },
  {
    "id": 31,
    "canonical_name": "Grand Theft Auto IV",
    "alternative_names": "[\"The Lost and Damned\", \"The Ballad of Gay Tony\", \"GTAIV\", \"TLAD\", \"TBoGT\"]",
    "series_name": "Grand Theft Auto",
    "release_year": 2008,
    "first_played_date": "2023-03-02"
  },
  {
    "id": 38,
    "canonical_name": "Grand Theft Auto V",
    "alternative_names": "[\"GTA 5\", \"Grand Theft Auto V: Xbox One & Xbox Series Bundle\", \"Grand Theft Auto V: PS4 & PS5 Bundle\", \"Grand Theft Auto V Bundle\"]",
    "series_name": "Grand Theft Auto",
    "release_year": 2022,
    "first_played_date": "2022-08-10"
  },
  {
    "id": 60,
    "canonical_name": "Hellblade: Senua's Sacrifice",
    "alternative_names": "[\"Hellblade\", \"Hell Blade\", \"HellbladeGame.exe\"]",
    "series_name": "Hellblade",
    "release_year": 2025,
    "first_played_date": "2020-12-28"
  },
  {
    "id": 61,
    "canonical_name": "Little Misfortune",
    "alternative_names": "[\"Little Misfortune.exe\"]",
    "series_name": "Little Misfortune",
    "release_year": 2019,
    "first_played_date": "2020-12-15"
  },
  {
    "id": 24,
    "canonical_name": "Mafia II",
    "alternative_names": "[\"Mafia 2\"]",
    "series_name": "Mafia",
    "release_year": 2010,
    "first_played_date": "2023-08-24"
  },
  {
    "id": 125,
    "canonical_name": "Mafia: The Old Country",
    "alternative_names": "[\"Mafia: Domovina\", \"Mafia: Terra Madre\", \"Mafia 4\", \"Mafia: Dawne strony\"]",
    "series_name": "Mafia: The Old Country",
    "release_year": 2025,
    "first_played_date": "2025-12-05"
  },
  {
    "id": 46,
    "canonical_name": "Red Dead Redemption",
    "alternative_names": "[\"RDR\", \"Red Dead Revolver 2\"]",
    "series_name": "Red Dead",
    "release_year": 2010,
    "first_played_date": "2021-11-15"
  },
  {
    "id": 119,
    "canonical_name": "Resident Evil Village",
    "alternative_names": "[\"Resident Evil 8\", \"BIOHAZARD VILLAGE\", \"Resident Evil 8 Village\", \"re8.exe\", \"RE8 \"]",
    "series_name": "Resident Evil",
    "release_year": 2021,
    "first_played_date": "2025-09-08"
  },
  {
    "id": 114,
    "canonical_name": "Silent Hill f",
    "alternative_names": "[\"SILENT HILL \\u0192\", \"Codename Sakura\", \"SHf.exe\"]",
    "series_name": "Silent Hill",
    "release_year": 2025,
    "first_played_date": "2025-09-23"
  },
  {
    "id": 52,
    "canonical_name": "The Beast Inside",
    "alternative_names": "[\"TheBeastInside.exe\"]",
    "series_name": "The Beast Inside",
    "release_year": 2022,
    "first_played_date": "2021-03-25"
  },
  {
    "id": 45,
    "canonical_name": "Uncharted: Drake's Fortune",
    "alternative_names": "[\"Uncharted Drakes Schicksal\", \"Uncharted I\", \"Uncharted 1\", \"Project Big\", \"Drake's Fortune\"]",
    "series_name": "Uncharted",
    "release_year": 2007,
    "first_played_date": "2022-01-24"
  },
  {
    "id": 42,
    "canonical_name": "Uncharted 4: A Thief's End",
    "alternative_names": "[\"Uncharted: Kaizokuou to Saigo no Hihou\", \"Uncharted 4: Kres z\\u0142odzieja\", \"Uncharted 4\"]",
    "series_name": "Uncharted",
    "release_year": 2016,
    "first_played_date": "2022-04-13"
  },
  {
    "id": 47,
    "canonical_name": "Far Cry 6",
    "alternative_names": "[]",
    "series_name": "Far Cry",
    "release_year": 2021,
    "first_played_date": "2021-10-09"
  },
  {
    "id": 110,
    "canonical_name": "Cronos: The New Dawn",
    "alternative_names": "[]",
    "series_name": "Cronos: The New Dawn",
    "release_year": 2004,
    "first_played_date": "2025-09-10"
  },
  {
    "id": 14,
    "canonical_name": "Batman: Arkham Origins",
    "alternative_names": "[\"Batman: Arkham Origins Mobile\"]",
    "series_name": "Batman",
    "release_year": 2013,
    "first_played_date": "2024-12-05"
  },
  {
    "id": 32,
    "canonical_name": "Dead Space Remake",
    "alternative_names": "{}",
    "series_name": "Dead Space Remake",
    "release_year": 2023,
    "first_played_date": "2023-01-29"
  },
  {
    "id": 55,
    "canonical_name": "Blair Witch",
    "alternative_names": "[\"Blairwitch.exe\"]",
    "series_name": "Blair Witch",
    "release_year": 2019,
    "first_played_date": "2021-02-23"
  },
  {
    "id": 36,
    "canonical_name": "Dead Space 2",
    "alternative_names": "[]",
    "series_name": "Dead Space",
    "release_year": 2011,
    "first_played_date": "2022-07-09"
  },
  {
    "id": 51,
    "canonical_name": "Red Dead Redemption 2",
    "alternative_names": "[\"RDR 2\", \"RDR2\", \"Red Dead Redemption II\", \"PlayRDR2.exe\"]",
    "series_name": "Red Dead",
    "release_year": 2018,
    "first_played_date": "2021-04-03"
  },
  {
    "id": 49,
    "canonical_name": "Resident Evil 7: Biohazard",
    "alternative_names": "[\"RE7\", \"Resident Evil 7\", \"Resident Evil VII: Biohazard\", \"Resident Evil 7: Biohazard - Grotesque Version\", \"re7.exe\"]",
    "series_name": "Resident Evil",
    "release_year": 2017,
    "first_played_date": "2021-07-29"
  },
  {
    "id": 13,
    "canonical_name": "Wolfenstein: The New Order",
    "alternative_names": "[\"Wolfenstein: TNO\", \"WolfNewOrder_x64.exe\"]",
    "series_name": "Wolfenstein",
    "release_year": 2014,
    "first_played_date": "2025-01-09"
  },
  {
    "id": 122,
    "canonical_name": "Saints Row 2",
    "alternative_names": "[\"SR2, Saint's Row 2, SR\", \"Saints Row 3DS\", \"SR\", \"Saint's Row 2\", \"SR2\"]",
    "series_name": "Saints Row",
    "release_year": 2009,
    "first_played_date": "2025-11-03"
  },
  {
    "id": 57,
    "canonical_name": "The Medium",
    "alternative_names": "[\"Medium.exe\"]",
    "series_name": "The Medium",
    "release_year": 2021,
    "first_played_date": "2021-02-02"
  },
  {
    "id": 126,
    "canonical_name": "Thanks to",
    "alternative_names": "thanksmom.exe",
    "series_name": "Thanks to",
    "release_year": 2024,
    "first_played_date": "2025-12-03"
  },
  {
    "id": 44,
    "canonical_name": "Uncharted 2: Among Thieves",
    "alternative_names": "[\"Uncharted II\", \"Uncharted 2: Po\\u015br\\u00f3d z\\u0142odziei\"]",
    "series_name": "Uncharted",
    "release_year": 2009,
    "first_played_date": "2022-02-15"
  },
  {
    "id": 59,
    "canonical_name": "Layers of Fear 2",
    "alternative_names": "[]",
    "series_name": "Layers Of Fear",
    "release_year": 2023,
    "first_played_date": "2021-01-12"
  },
  {
    "id": 27,
    "canonical_name": "Batman: Arkham Knight",
    "alternative_names": "[]",
    "series_name": "Batman",
    "release_year": 2015,
    "first_played_date": "2023-07-06"
  },
  {
    "id": 81,
    "canonical_name": "Batman: Arkham City",
    "alternative_names": "[\"Batman: Arkham Asylum 2\", \"Arkham City\", \"Batman: AC\"]",
    "series_name": "Batman",
    "release_year": 2011,
    "first_played_date": "2023-07-06"
  },
  {
    "id": 7,
    "canonical_name": "The Evil Within",
    "alternative_names": "[\"Project Zwei\", \"Psycho Break\", \"evilwithin.exe\"]",
    "series_name": "The Evil Within",
    "release_year": 2014,
    "first_played_date": "2025-08-14"
  },
  {
    "id": 56,
    "canonical_name": "Assassin's Creed Valhalla",
    "alternative_names": "[\"Assassin's Creed\\u00ae Valhalla\", \"Assassin's Creed Kingdom\", \"Assassin's Creed: Valhalla\", \"AC Valhalla\", \"ACValhalla.exe\"]",
    "series_name": "Assassin's Creed",
    "release_year": 2020,
    "first_played_date": "2021-02-16"
  },
  {
    "id": 123,
    "canonical_name": "Platinum Push",
    "alternative_names": "",
    "series_name": "Platinum Push",
    "release_year": None,
    "first_played_date": "2025-11-14"
  },
  {
    "id": 22,
    "canonical_name": "Call of Duty: World at War",
    "alternative_names": "[\"CoD5\", \"World at War\", \"CoD:WaW\", \"Call of Duty 5\"]",
    "series_name": "Call of Duty",
    "release_year": 2008,
    "first_played_date": "2024-02-22"
  },
  {
    "id": 101,
    "canonical_name": "God of War II",
    "alternative_names": "[\"God of War 2\", \"God of War II: Sh\\u016ben no Jokyoku\", \"God of War II Overture to the End\", \"GOW2\", \"GOWII\"]",
    "series_name": "God of War",
    "release_year": 2007,
    "first_played_date": "2022-04-18"
  },
  {
    "id": 23,
    "canonical_name": "Call of Duty: Modern Warfare 3",
    "alternative_names": "[\"COD MW3\", \"Call of Duty 8\", \"CODMW3\", \"COD8\", \"MW3\"]",
    "series_name": "Call of Duty",
    "release_year": 2014,
    "first_played_date": "2024-01-01"
  },
  {
    "id": 111,
    "canonical_name": "Ghost of Yotei",
    "alternative_names": "[\"Ghost of Y\\u014dtei\"]",
    "series_name": "Ghost of Yotei",
    "release_year": 2025,
    "first_played_date": "2025-10-29"
  },
  {
    "id": 25,
    "canonical_name": "Spider-Man 2",
    "alternative_names": "[\"The Amazing Spider-Man 2\", \"Spider-Man 2: The Game\"]",
    "series_name": "Spider-Man",
    "release_year": 2004,
    "first_played_date": "2021-08-21"
  },
  {
    "id": 8,
    "canonical_name": "Until Dawn",
    "alternative_names": "[\"Until Dawn Remake\"]",
    "series_name": "Until Dawn",
    "release_year": 2024,
    "first_played_date": "2025-07-03"
  },
  {
    "id": 33,
    "canonical_name": "The Last of Us",
    "alternative_names": "[\"TLoU\"]",
    "series_name": "The Last of Us",
    "release_year": 2013,
    "first_played_date": "2021-08-28"
  },
  {
    "id": 21,
    "canonical_name": "Call of Duty: Black Ops II",
    "alternative_names": "[\"COD BO2\", \"CODBLOPS II\", \"BLOPS II\", \"BLOPS 2\", \"CODBLOPS 2\"]",
    "series_name": "Call of Duty",
    "release_year": 2012,
    "first_played_date": "2024-03-10"
  },
  {
    "id": 74,
    "canonical_name": "Sleeping Dogs",
    "alternative_names": "[\"Black Lotus\", \"True Crime: Hong Kong\", \"Sleeping Dogs: Hong Kong Himitsu Keisatsu\", \"HKShip.exe\"]",
    "series_name": "Sleeping Dogs Definitive Edition, Sleeping Dogs: Definitive Edition",
    "release_year": 2012,
    "first_played_date": "2025-10-23"
  },
  {
    "id": 127,
    "canonical_name": "Thank Goodness You're Here!",
    "alternative_names": "[\"Thank Goodness You're Here!.exe\"]",
    "series_name": "Thank Goodness You're Here!",
    "release_year": 2024,
    "first_played_date": "2025-12-01"
  },
  {
    "id": 40,
    "canonical_name": "Uncharted: The Lost Legacy",
    "alternative_names": "[\"Uncharted: Kodai Kami No Hihou\", \"Uncharted: Kay\\u0131p Miras\", \"Uncharted: Zaginione dziedzictwo\", \"Uncharted: L'Eredit\\u00e0 Perduta\", \"Uncharted: O Legado Perdido\"]",
    "series_name": "Uncharted",
    "release_year": 2017,
    "first_played_date": "2022-06-02"
  },
  {
    "id": 41,
    "canonical_name": "God of War III",
    "alternative_names": "[\"God of War 3\", \"GOW3\", \"GOWIII\"]",
    "series_name": "God of War",
    "release_year": 2010,
    "first_played_date": "2022-03-09"
  },
  {
    "id": 128,
    "canonical_name": "Star Wars Jedi: Fallen Order",
    "alternative_names": "[\"Star Wars Jedi: Gefallene Ordnung\", \"Star Wars Jedi: Ordem Ca\\u00edda\", \"Jedi: Fallen Order\"]",
    "series_name": "Star Wars",
    "release_year": None,
    "first_played_date": "2025-12-19"
  },
  {
    "id": 43,
    "canonical_name": "Uncharted 3: Drake's Deception",
    "alternative_names": "[\"Uncharted III: Drakes Deception\", \"Uncharted 3: Drakes Deception\", \"Uncharted 3: Oszustwo Drake'a\"]",
    "series_name": "Uncharted",
    "release_year": 2011,
    "first_played_date": "2022-03-29"
  }
]

# 2. SMART MAPPINGS
SMART_MAPPINGS = {
    # God of War Series
    "God of War": ["God of War 2018", "GoW 2018", "Dad of War"], 
    "God of War Ragnarök": ["GoW Ragnarok", "GoW 5", "Ragnarok"],
    "God of War II": ["God of War 2", "GoW 2", "GoW II"],
    "God of War III": ["God of War 3", "GoW 3", "GoW III"],

    # Resident Evil Series
    "Resident Evil 7: Biohazard": ["RE7", "Biohazard 7"],
    "Resident Evil Village": ["RE8", "Resident Evil 8", "Village"],

    # GTA Series
    "Grand Theft Auto V": ["GTA 5", "GTA V", "Grand Theft Auto 5"],
    "Grand Theft Auto IV": ["GTA 4", "GTA IV", "Grand Theft Auto 4"],
    "Grand Theft Auto: San Andreas": ["GTA SA", "San Andreas"],
    "Grand Theft Auto IV: The Ballad of Gay Tony": ["GTA Gay Tony", "TBoGT"],
    "Grand Theft Auto IV: The Lost and Damned": ["GTA Lost and Damned", "TLAD"],

    # Red Dead Series
    "Red Dead Redemption 2": ["RDR2", "RDR 2"],
    "Red Dead Redemption": ["RDR", "RDR1", "Red Dead 1"], 

    # Call of Duty
    "Call of Duty: Modern Warfare 3": ["MW3", "COD MW3"],
    "Call of Duty: World at War": ["COD WaW", "World at War"],
    "Call of Duty: Black Ops II": ["Black Ops 2", "BO2", "COD BO2"],

    # Uncharted Series
    "Uncharted: Drake's Fortune": ["Uncharted 1", "U1"],
    "Uncharted 2: Among Thieves": ["Uncharted 2", "U2"],
    "Uncharted 3: Drake's Deception": ["Uncharted 3", "U3"],
    "Uncharted 4: A Thief's End": ["Uncharted 4", "U4"],
    "Uncharted: The Lost Legacy": ["Lost Legacy", "ULL"],

    # Halo Series
    "Halo: Combat Evolved": ["Halo 1", "Halo CE"],
    "Halo 2": ["Halo 2", "Halo 2 Anniversary"],
    "Halo 3": ["Halo 3"],

    # Others
    "The Last of Us": ["TLOU", "TLOU1", "The Last of Us Part 1"],
    "Alien: Isolation": ["Alien Isolation"],
    "Detroit: Become Human": ["Detroit", "DBH"],
    "Fallout: New Vegas": ["FNV", "New Vegas"],
    "Silent Hill 2": ["SH2", "Silent Hill 2 Remake"],
    "Ghost of Tsushima": ["GoT"],
    "Bloodborne": ["BB"],
    "Elden Ring": ["ER"],
    "Dead Space Remake": ["Dead Space", "DS Remake"],
    "Dead Space 2": ["DS2"],
    "Star Wars Jedi: Fallen Order": ["Jedi Fallen Order", "Fallen Order"],
    "The Evil Within": ["TEW"],
    "Sleeping Dogs": ["Sleeping Dogs Definitive Edition"],
    "Mafia II": ["Mafia 2", "Mafia 2 Definitive Edition"],
    "Mafia: The Old Country": ["Mafia 4", "Mafia Old Country"]
}

def clean_messy_string(text):
    """Clean the corrupted string into a list of names"""
    if not text:
        return []
    
    cleaned = str(text).strip()
    
    if cleaned.startswith('[') and cleaned.endswith(']'):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass 

    if cleaned.startswith('{') and cleaned.endswith('}'):
        cleaned = cleaned[1:-1]
        
    import re
    items = re.findall(r'"([^"]*)"', cleaned)
    
    if not items and cleaned:
        items = cleaned.split(',')
        
    final_items = []
    for item in items:
        clean_item = item.replace('\\"', '').replace('\\', '').strip()
        if clean_item and clean_item not in ['{', '}', '""']:
            final_items.append(clean_item)
            
    return final_items

def generate_sql_updates():
    sql_statements = []
    
    # 1. APPLY MANUAL DATE FIXES
    print("Applying manual date fixes...")
    for game in RAW_DATA:
        name = game['canonical_name']
        if name in MANUAL_DATE_FIXES:
            game['first_played_date'] = MANUAL_DATE_FIXES[name]
            print(f"  Fixed date for '{name}' -> {game['first_played_date']}")

    # 2. STRICT DATE SORTING
    print(f"Sorting {len(RAW_DATA)} games by play date...")
    
    def sort_key(game):
        date_str = game.get('first_played_date')
        if not date_str:
            return datetime.max
        try:
            # Parse strictly as date object for correct sorting
            return datetime.strptime(str(date_str), "%Y-%m-%d")
        except ValueError:
            print(f"⚠️ Warning: Invalid date format for '{game['canonical_name']}': {date_str}")
            return datetime.max

    RAW_DATA.sort(key=sort_key)
    
    print(f"Generating updates for {len(RAW_DATA)} games...")
    
    for game in RAW_DATA:
        game_id = game['id']
        name = game['canonical_name']
        raw_alts = game.get('alternative_names', '')
        played_date = game.get('first_played_date', 'Unknown')
        
        # Clean existing data
        current_alts = clean_messy_string(raw_alts)
        
        # Add Smart Mappings
        if name in SMART_MAPPINGS:
            current_alts.extend(SMART_MAPPINGS[name])
            
        # Deduplicate and Sort
        unique_alts = sorted(list(set(current_alts)))
        unique_alts = [x for x in unique_alts if x.lower() != name.lower()]
        
        # Generate JSON string
        json_val = json.dumps(unique_alts)
        json_val_sql = json_val.replace("'", "''")
        
        # Update both Name AND Date (in case we fixed it)
        # Handle 'None' date for SQL
        date_val = f"'{played_date}'" if played_date else "NULL"
        
        sql = f"UPDATE played_games SET alternative_names = '{json_val_sql}', first_played_date = {date_val} WHERE id = {game_id};"
        sql_statements.append(sql)
        
    with open('update_names.sql', 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_statements))
        
    print(f"✅ Successfully generated update_names.sql with {len(sql_statements)} commands.")

if __name__ == "__main__":
    generate_sql_updates()