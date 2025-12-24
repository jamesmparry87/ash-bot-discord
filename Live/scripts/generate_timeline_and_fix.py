import json
import re
from datetime import datetime

# --- 1. MANUAL TWITCH DATES ---
# Add your manual dates here. Format: "Game Name": "YYYY-MM-DD"
MANUAL_DATES = {
    "Mafia: The Old Country": "2025-12-05",
    "Saints Row 2": "2025-11-03",
    "Silent Hill f": "2025-09-23",
    "Cronos: The New Dawn": "2025-09-10",
    "Resident Evil Village": "2025-09-08",
    "Thank Goodness You're Here!": "2025-12-01",
    "Star Wars Jedi: Fallen Order": "2025-12-19",
    "Sleep Awake": "2025-12-03",
    "Ghost of Yotei": "2025-10-29"
}

# --- 2. YOUR DATA ---
RAW_DATA = [
    {"id": 53, "canonical_name": "Fallout: New Vegas", "first_played_date": "2021-03-19", "alternative_names": "[\"FNV\", \"New Vegas\", \"NV\"]"},
    {"id": 16, "canonical_name": "Gears of War", "first_played_date": "2024-07-30", "alternative_names": "[]"},
    {"id": 1, "canonical_name": "God of War", "first_played_date": "2021-06-28", "alternative_names": "[\"GOW\", \"God of War 2018\", \"Dad of War\"]"},
    {"id": 35, "canonical_name": "God of War Ragnarök", "first_played_date": "2022-11-09", "alternative_names": "[\"GoW Ragnarok\"]"},
    {"id": 17, "canonical_name": "Halo 3", "first_played_date": "2024-07-09", "alternative_names": "[\"H3\"]"},
    {"id": 28, "canonical_name": "Grand Theft Auto IV: The Ballad of Gay Tony", "first_played_date": "2023-07-09", "alternative_names": "[\"TBoGT\"]"},
    {"id": 29, "canonical_name": "Grand Theft Auto IV: The Lost and Damned", "first_played_date": "2023-06-01", "alternative_names": "[\"TLAD\"]"},
    {"id": 19, "canonical_name": "Halo: Combat Evolved", "first_played_date": "2024-05-01", "alternative_names": "[\"Halo 1\", \"Halo CE\"]"},
    {"id": 18, "canonical_name": "Halo 2", "first_played_date": "2024-05-30", "alternative_names": "[\"H2\"]"},
    {"id": 26, "canonical_name": "Outlast", "first_played_date": "2023-10-01", "alternative_names": "[\"Outlast 1\"]"},
    {"id": 15, "canonical_name": "Silent Hill 2", "first_played_date": "2024-10-28", "alternative_names": "[\"SH2\"]"},
    {"id": 48, "canonical_name": "Bloodborne", "first_played_date": "2021-09-29", "alternative_names": "[\"BB\"]"},
    {"id": 11, "canonical_name": "The Walking Dead", "first_played_date": "2025-04-17", "alternative_names": "[\"TWD\"]"},
    {"id": 34, "canonical_name": "The Callisto Protocol", "first_played_date": "2022-12-05", "alternative_names": "[]"},
    {"id": 37, "canonical_name": "Alien: Isolation", "first_played_date": "2022-10-13", "alternative_names": "[]"},
    {"id": 30, "canonical_name": "Batman: Arkham Asylum", "first_played_date": "2023-05-14", "alternative_names": "[\"Batman AA\"]"},
    {"id": 20, "canonical_name": "Elden Ring", "first_played_date": "2024-04-14", "alternative_names": "[\"ER\"]"},
    {"id": 10, "canonical_name": "Gears of War 4", "first_played_date": "2024-08-22", "alternative_names": "[\"Gears 4\"]"},
    {"id": 39, "canonical_name": "Ghost of Tsushima", "first_played_date": "2022-06-19", "alternative_names": "[\"GoT\"]"},
    {"id": 12, "canonical_name": "Grand Theft Auto: San Andreas", "first_played_date": "2025-02-06", "alternative_names": "[\"GTA SA\"]"},
    {"id": 31, "canonical_name": "Grand Theft Auto IV", "first_played_date": "2023-03-02", "alternative_names": "[\"GTA 4\"]"},
    {"id": 38, "canonical_name": "Grand Theft Auto V", "first_played_date": "2022-08-10", "alternative_names": "[\"GTA 5\"]"},
    {"id": 60, "canonical_name": "Hellblade: Senua's Sacrifice", "first_played_date": "2020-12-28", "alternative_names": "[\"Hellblade\"]"},
    {"id": 61, "canonical_name": "Little Misfortune", "first_played_date": "2020-12-15", "alternative_names": "[]"},
    {"id": 24, "canonical_name": "Mafia II", "first_played_date": "2023-08-24", "alternative_names": "[\"Mafia 2\"]"},
    {"id": 125, "canonical_name": "Mafia: The Old Country", "first_played_date": "2025-12-05", "alternative_names": "[]"},
    {"id": 46, "canonical_name": "Red Dead Redemption", "first_played_date": "2021-11-15", "alternative_names": "[\"RDR1\"]"},
    {"id": 119, "canonical_name": "Resident Evil Village", "first_played_date": "2025-09-08", "alternative_names": "[\"RE8\"]"},
    {"id": 114, "canonical_name": "Silent Hill f", "first_played_date": "2025-09-23", "alternative_names": "[]"},
    {"id": 52, "canonical_name": "The Beast Inside", "first_played_date": "2021-03-25", "alternative_names": "[]"},
    {"id": 45, "canonical_name": "Uncharted: Drake's Fortune", "first_played_date": "2022-01-24", "alternative_names": "[\"Uncharted 1\"]"},
    {"id": 42, "canonical_name": "Uncharted 4: A Thief's End", "first_played_date": "2022-04-13", "alternative_names": "[\"Uncharted 4\"]"},
    {"id": 47, "canonical_name": "Far Cry 6", "first_played_date": "2021-10-09", "alternative_names": "[]"},
    {"id": 110, "canonical_name": "Cronos: The New Dawn", "first_played_date": "2025-09-10", "alternative_names": "[]"},
    {"id": 14, "canonical_name": "Batman: Arkham Origins", "first_played_date": "2024-12-05", "alternative_names": "[]"},
    {"id": 32, "canonical_name": "Dead Space", "first_played_date": "2023-01-29", "alternative_names": "[]"},
    {"id": 55, "canonical_name": "Blair Witch", "first_played_date": "2021-02-23", "alternative_names": "[]"},
    {"id": 36, "canonical_name": "Dead Space 2", "first_played_date": "2022-07-09", "alternative_names": "[]"},
    {"id": 51, "canonical_name": "Red Dead Redemption 2", "first_played_date": "2021-04-03", "alternative_names": "[\"RDR2\"]"},
    {"id": 49, "canonical_name": "Resident Evil 7: Biohazard", "first_played_date": "2021-07-29", "alternative_names": "[\"RE7\"]"},
    {"id": 13, "canonical_name": "Wolfenstein: The New Order", "first_played_date": "2025-01-09", "alternative_names": "[]"},
    {"id": 122, "canonical_name": "Saints Row 2", "first_played_date": "2025-11-03", "alternative_names": "[]"},
    {"id": 57, "canonical_name": "The Medium", "first_played_date": "2021-02-02", "alternative_names": "[]"},
    {"id": 126, "canonical_name": "Sleep Awake", "first_played_date": "2025-12-03", "alternative_names": "[]"},
    {"id": 44, "canonical_name": "Uncharted 2: Among Thieves", "first_played_date": "2022-02-15", "alternative_names": "[\"Uncharted 2\"]"},
    {"id": 59, "canonical_name": "Layers of Fear 2", "first_played_date": "2021-01-12", "alternative_names": "[]"},
    {"id": 27, "canonical_name": "Batman: Arkham Knight", "first_played_date": "2023-07-06", "alternative_names": "[]"},
    {"id": 81, "canonical_name": "Batman: Arkham City", "first_played_date": "2023-07-06", "alternative_names": "[]"},
    {"id": 7, "canonical_name": "The Evil Within", "first_played_date": "2025-08-14", "alternative_names": "[]"},
    {"id": 56, "canonical_name": "Assassin's Creed Valhalla", "first_played_date": "2021-02-16", "alternative_names": "[\"AC Valhalla\"]"},
    {"id": 22, "canonical_name": "Call of Duty: World at War", "first_played_date": "2024-02-22", "alternative_names": "[\"WaW\"]"},
    {"id": 101, "canonical_name": "God of War II", "first_played_date": "2022-04-18", "alternative_names": "[\"GoW 2\"]"},
    {"id": 23, "canonical_name": "Call of Duty: Modern Warfare 3", "first_played_date": "2024-01-01", "alternative_names": "[\"MW3\"]"},
    {"id": 111, "canonical_name": "Ghost of Yotei", "first_played_date": "2025-10-29", "alternative_names": "[]"},
    {"id": 25, "canonical_name": "Spider-Man 2", "first_played_date": "2021-08-21", "alternative_names": "[]"},
    {"id": 8, "canonical_name": "Until Dawn", "first_played_date": "2025-07-03", "alternative_names": "[]"},
    {"id": 33, "canonical_name": "The Last of Us", "first_played_date": "2021-08-28", "alternative_names": "[\"TLOU\"]"},
    {"id": 21, "canonical_name": "Call of Duty: Black Ops II", "first_played_date": "2024-03-10", "alternative_names": "[\"BO2\"]"},
    {"id": 74, "canonical_name": "Sleeping Dogs", "first_played_date": "2025-10-23", "alternative_names": "[]"},
    {"id": 127, "canonical_name": "Thank Goodness You're Here!", "first_played_date": "2025-12-01", "alternative_names": "[]"},
    {"id": 40, "canonical_name": "Uncharted: The Lost Legacy", "first_played_date": "2022-06-02", "alternative_names": "[\"Lost Legacy\"]"},
    {"id": 41, "canonical_name": "God of War III", "first_played_date": "2022-03-09", "alternative_names": "[\"GoW 3\"]"},
    {"id": 128, "canonical_name": "Star Wars Jedi: Fallen Order", "first_played_date": "2025-12-19", "alternative_names": "[\"Fallen Order\"]"},
    {"id": 43, "canonical_name": "Uncharted 3: Drake's Deception", "first_played_date": "2022-03-29", "alternative_names": "[\"Uncharted 3\"]"}
]


def clean_messy_string(text):
    if not text:
        return []
    cleaned = str(text).strip()
    if cleaned.startswith('[') and cleaned.endswith(']'):
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
    return []


def process_data():
    # 1. APPLY MANUAL DATES
    print("🔄 Applying manual date fixes...")
    for game in RAW_DATA:
        name = game['canonical_name']
        if name in MANUAL_DATES:
            game['first_played_date'] = MANUAL_DATES[name]
            print(f"  Fixed: '{name}' -> {game['first_played_date']}")

    # 2. SORT CHRONOLOGICALLY
    print("\n📅 Sorting...")
    RAW_DATA.sort(key=lambda x: datetime.strptime(str(x.get('first_played_date') or '9999-12-31'), "%Y-%m-%d"))

    # 3. GENERATE VISUAL REPORT
    print("\n📄 Generating 'gaming_timeline.txt' for validation...")
    with open('gaming_timeline.txt', 'w', encoding='utf-8') as report:
        report.write("--- JONESY'S GAMING TIMELINE (SORTED) ---\n")
        report.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        current_year = None
        for game in RAW_DATA:
            date = game.get('first_played_date', 'Unknown')
            name = game['canonical_name']

            # Add year headers
            if date != 'Unknown':
                year = date.split('-')[0]
                if year != current_year:
                    report.write(f"\n[{year}]\n")
                    current_year = year

            report.write(f"{date} : {name}\n")

    print("✅ Report generated: gaming_timeline.txt (Check this file to verify order!)")

    # 4. GENERATE SQL
    print("\n📝 Generating SQL...")
    sql_statements = []

    for game in RAW_DATA:
        game_id = game['id']
        name = game['canonical_name']
        raw_alts = game.get('alternative_names', '')
        played_date = game.get('first_played_date')

        # Clean existing names (assuming they are already JSON from your backup)
        try:
            current_alts = json.loads(raw_alts) if raw_alts else []
        except BaseException:
            current_alts = []  # Fallback

        # Deduplicate
        unique_alts = sorted(list(set(current_alts)))
        unique_alts = [x for x in unique_alts if x.lower() != name.lower()]

        # Prepare SQL values
        json_val = json.dumps(unique_alts).replace("'", "''")
        date_val = f"'{played_date}'" if played_date else "NULL"
        sql_name = name.replace("'", "''")

        # SQL now updates NAME + DATE + ALTERNATIVE NAMES
        sql = f"UPDATE played_games SET canonical_name = '{sql_name}', alternative_names = '{json_val}', first_played_date = {date_val} WHERE id = {game_id};"
        sql_statements.append(sql)

    with open('update_names.sql', 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_statements))

    print(f"✅ SQL generated: update_names.sql with {len(sql_statements)} commands.")


if __name__ == "__main__":
    process_data()
