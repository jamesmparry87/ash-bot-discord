import json
import re
from datetime import datetime

import requests

# --- CONFIGURATION ---
YOUTUBE_API_KEY = "AIzaSyC--8CymRuKHzSxznwqCrSh7TWftIM9hzI"
TWITCH_CLIENT_ID = "a4ywgixzibm7pfxe68i5mdw8es2ewj"
TWITCH_CLIENT_SECRET = "yfqgjp31cmletsk9n8iawo830pygkx"

# --- SMART MAPPINGS ---
SMART_MAPPINGS = {
    "God of War": ["God of War 2018", "GoW 2018", "Dad of War"],
    "God of War Ragnarök": ["GoW Ragnarok", "GoW 5", "Ragnarok"],
    "God of War II": ["God of War 2", "GoW 2", "GoW II"],
    "God of War III": ["God of War 3", "GoW 3", "GoW III"],
    "Resident Evil 7: Biohazard": ["RE7", "Biohazard 7"],
    "Resident Evil Village": ["RE8", "Resident Evil 8", "Village"],
    "Grand Theft Auto V": ["GTA 5", "GTA V"],
    "Grand Theft Auto IV": ["GTA 4", "GTA IV"],
    "Grand Theft Auto: San Andreas": ["GTA SA", "San Andreas"],
    "Grand Theft Auto IV: The Ballad of Gay Tony": ["GTA Gay Tony", "TBoGT"],
    "Grand Theft Auto IV: The Lost and Damned": ["GTA Lost and Damned", "TLAD"],
    "Red Dead Redemption 2": ["RDR2", "RDR 2"],
    "Red Dead Redemption": ["RDR", "RDR1", "Red Dead 1"],
    "Call of Duty: Modern Warfare 3": ["MW3", "COD MW3"],
    "Call of Duty: World at War": ["COD WaW", "World at War"],
    "Call of Duty: Black Ops II": ["Black Ops 2", "BO2", "COD BO2"],
    "Uncharted: Drake's Fortune": ["Uncharted 1", "U1"],
    "Uncharted 2: Among Thieves": ["Uncharted 2", "U2"],
    "Uncharted 3: Drake's Deception": ["Uncharted 3", "U3"],
    "Uncharted 4: A Thief's End": ["Uncharted 4", "U4"],
    "Uncharted: The Lost Legacy": ["Lost Legacy", "ULL"],
    "Halo: Combat Evolved": ["Halo 1", "Halo CE"],
    "Halo 2": ["Halo 2", "Halo 2 Anniversary"],
    "Halo 3": ["Halo 3"],
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

# --- YOUR DATA ---
RAW_DATA = [
    {"id": 53, "canonical_name": "Fallout: New Vegas", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcJtr4Ukkm83t-PBI4Y-zvOq"},
    {"id": 16, "canonical_name": "Gears of War", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcIAatluJYqU3vEQ5DENT9o2"},
    {"id": 1, "canonical_name": "God of War", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJ24tcv_zzSuBEDeOy3Uo9D"},
    {"id": 35, "canonical_name": "God of War Ragnarök", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcJwQ_4--jFvS3KIegNIH_yp"},
    {"id": 17, "canonical_name": "Halo 3", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKwfauRpHDAVcMoHBxiO0uk"},
    {"id": 28, "canonical_name": "Grand Theft Auto IV: The Ballad of Gay Tony", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJca7AVN5jFS2-mtezQdePm"},
    {"id": 29, "canonical_name": "Grand Theft Auto IV: The Lost and Damned", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcLcqF9Nx47UjRfwXiVVdWmV"},
    {"id": 19, "canonical_name": "Halo: Combat Evolved", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKSsaEr82Q28H-QJruwnlwe"},
    {"id": 18, "canonical_name": "Halo 2", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcIDWZTjsq4XNm04Au0FITTp"},
    {"id": 26, "canonical_name": "Outlast", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcLx6vIgMtf2yPj7CbAm4J9O"},
    {"id": 15, "canonical_name": "Silent Hill 2", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcLcfE9YPmO811DqPZn2X6BV"},
    {"id": 48, "canonical_name": "Bloodborne", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcKSoZzSAek-8xzxdELGEYJm"},
    {"id": 11, "canonical_name": "The Walking Dead", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJimMXQ8ULhD28EhCfsRbKC"},
    {"id": 34, "canonical_name": "The Callisto Protocol", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcI9v7lwV6MfKMU4MS4zuiKl"},
    {"id": 37, "canonical_name": "Alien: Isolation", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcI8Aa9UoPDIfgf4s5CyGxke"},
    {"id": 30, "canonical_name": "Batman: Arkham Asylum", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcLt6__M3JI02y9t-kaz8ynp"},
    {"id": 20, "canonical_name": "Elden Ring", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJtdaT_j77PYKmIPTChEVpO"},
    {"id": 10, "canonical_name": "Gears of War 4", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcK2nGilViSS-ETGjOqGAorr"},
    {"id": 39, "canonical_name": "Ghost of Tsushima", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJ1YwCfKGTwY43LYjvNzxAa"},
    {"id": 12, "canonical_name": "Grand Theft Auto: San Andreas", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKxrOz5HGhjVUXpB3sY4KY3"},
    {"id": 31, "canonical_name": "Grand Theft Auto IV", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcK5WpvPNODi1xxrhcU6gxZo"},
    {"id": 38, "canonical_name": "Grand Theft Auto V", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKGNBei5yt4It9j5QmqiFXr"},
    {"id": 60, "canonical_name": "Hellblade: Senua's Sacrifice", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcJCASCPBfZn7neB5lhqDU7l"},
    {"id": 61, "canonical_name": "Little Misfortune", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcKqfQi33nZcdUBBKEBbAJF5"},
    {"id": 24, "canonical_name": "Mafia II", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcI5A7NF6584-KT7PRhK6cg7"},
    {"id": 125, "canonical_name": "Mafia: The Old Country", "twitch_vod_urls": "{https://www.twitch.tv/videos/2638649402}"},
    {"id": 46, "canonical_name": "Red Dead Redemption", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcKtwQWqXcqoSe_DX1I2buUR"},
    {"id": 119, "canonical_name": "Resident Evil Village", "youtube_playlist_url": None},
    {"id": 114, "canonical_name": "Silent Hill f", "youtube_playlist_url": None},
    {"id": 52, "canonical_name": "The Beast Inside", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcK-HoNNt9HLEeyCtLYc97nE"},
    {"id": 45, "canonical_name": "Uncharted: Drake's Fortune", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcKxVsFooPJBro_GoPG1stpE"},
    {"id": 42, "canonical_name": "Uncharted 4: A Thief's End", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcIKpzIygLNwGiQtOmKjsb2R"},
    {"id": 47, "canonical_name": "Far Cry 6", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcKJOZZgb3R1wiua2lI2kdNA"},
    {"id": 110, "canonical_name": "Cronos: The New Dawn", "youtube_playlist_url": None},
    {"id": 14, "canonical_name": "Batman: Arkham Origins", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKZFjKFDupFiWB6GKnFVXFi"},
    {"id": 32, "canonical_name": "Dead Space Remake", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcItrPi8x4rkRUkH_6Tsew6t"},
    {"id": 55, "canonical_name": "Blair Witch", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcJa08MgxgxFtBdyCZrMZOo3"},
    {"id": 36, "canonical_name": "Dead Space 2", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcLDOX2BiGQu_1_fpjAii1P8"},
    {"id": 51, "canonical_name": "Red Dead Redemption 2", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcJMsHy5eDEg7-Fh57JT8Irw"},
    {"id": 49, "canonical_name": "Resident Evil 7: Biohazard", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcKCpAYuzBcu8SfMGrKmh3xQ"},
    {"id": 13, "canonical_name": "Wolfenstein: The New Order", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKYKOLHCnkUvnNDcxB7PDyA"},
    {"id": 122, "canonical_name": "Saints Row 2", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcK3yEKXeWkpxmT1C9uYwYRj"},
    {"id": 57, "canonical_name": "The Medium", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcLHaUBcHVE8dQxo7SAZDmbc"},
    {"id": 126, "canonical_name": "Thanks to", "twitch_vod_urls": "https://www.twitch.tv/videos/2634345165"},
    {"id": 44, "canonical_name": "Uncharted 2: Among Thieves", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcKUyWF4N-Lc4Mr1U4qDJmpp"},
    {"id": 59, "canonical_name": "Layers of Fear 2", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcJeexzw_m8XpeLBRJQltsFc"},
    {"id": 27, "canonical_name": "Batman: Arkham Knight", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKI1S-XNOHny5TBj9B-UWWm"},
    {"id": 81, "canonical_name": "Batman: Arkham City", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcK4sO0eQImV9NcjNz589LRl"},
    {"id": 7, "canonical_name": "The Evil Within", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJdS_dV8XO0zV9MkiGabQ_x"},
    {"id": 56, "canonical_name": "Assassin's Creed Valhalla", "youtube_playlist_url": "https://www.youtube.com/playlist?list=PLxgSRpBG9HcIDOtVxm6z71BxDPaUaeF7Q"},
    {"id": 123, "canonical_name": "Platinum Push", "youtube_playlist_url": None},
    {"id": 22, "canonical_name": "Call of Duty: World at War", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJKGT1nHMjKfQwhed0M_Oiq"},
    {"id": 101, "canonical_name": "God of War II", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJ24tcv_zzSuBEDeOy3Uo9D"},
    {"id": 23, "canonical_name": "Call of Duty: Modern Warfare 3", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcLZwM36NcHtQ8F85NdyuciW"},
    {"id": 111, "canonical_name": "Ghost of Yotei", "youtube_playlist_url": None},
    {"id": 25, "canonical_name": "Spider-Man 2", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKTWGiKrUWrkhFewbcSMHXl"},
    {"id": 8, "canonical_name": "Until Dawn", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJ4rRawvy89ElW8ga05TBtl"},
    {"id": 33, "canonical_name": "The Last of Us", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcIu26-jWv1atHtG8ZDvyJ19"},
    {"id": 21, "canonical_name": "Call of Duty: Black Ops II", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcJga3Exme50CzMYjgqzwjDa"},
    {"id": 74, "canonical_name": "Sleeping Dogs", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcIMeCMIJ-Do2kHUAz_ylS_T"},
    {"id": 127, "canonical_name": "Thank Goodness You're Here!", "twitch_vod_urls": "https://www.twitch.tv/videos/2632697948"},
    {"id": 40, "canonical_name": "Uncharted: The Lost Legacy", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcIdkqYSE20H9keIwa4hMrQJ"},
    {"id": 41, "canonical_name": "God of War III", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcKr1GCOBHWCFOWF_lqKK9tU"},
    {"id": 128, "canonical_name": "Star Wars Jedi: Fallen Order", "twitch_vod_urls": "https://www.twitch.tv/videos/2647827668"},
    {"id": 43, "canonical_name": "Uncharted 3: Drake's Deception", "youtube_playlist_url": "https://youtube.com/playlist?list=PLxgSRpBG9HcLzVU7j-rNvsp9hoaSCNVUP"}
]

# --- API HELPERS ---
_twitch_access_token = None


def get_twitch_token():
    global _twitch_access_token
    if _twitch_access_token:
        return _twitch_access_token

    try:
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
        response = requests.post(url, params=params)
        data = response.json()
        if "access_token" in data:
            _twitch_access_token = data["access_token"]
            return _twitch_access_token
    except Exception as e:
        print(f"❌ Twitch Auth Error: {e}")
    return None


def get_twitch_date(vod_url_field):
    if not vod_url_field:
        return None
    match = re.search(r'videos/(\d+)', str(vod_url_field))
    if not match:
        return None
    video_id = match.group(1)

    token = get_twitch_token()
    if not token:
        return None

    try:
        headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"}
        response = requests.get(f"https://api.twitch.tv/helix/videos?id={video_id}", headers=headers)
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["created_at"].split("T")[0]
    except Exception as e:
        print(f"  ⚠️ Twitch API Error for {video_id}: {e}")
    return None


def get_youtube_date(playlist_url):
    if not playlist_url:
        return None
    match = re.search(r'list=([a-zA-Z0-9_-]+)', playlist_url)
    if not match:
        return None
    playlist_id = match.group(1)

    try:
        # UPDATED LOGIC: Scan first 50 videos and find the earliest date
        url = "https://www.googleapis.com/youtube/v3/playlistItems"
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,  # Check first 50 items
            "key": YOUTUBE_API_KEY
        }
        response = requests.get(url, params=params)
        data = response.json()

        dates = []
        if "items" in data:
            for item in data["items"]:
                if "publishedAt" in item["snippet"]:
                    dates.append(item["snippet"]["publishedAt"])

        if dates:
            # Sort to find the true earliest date
            dates.sort()
            earliest = dates[0]
            return earliest.split("T")[0]

    except Exception as e:
        print(f"  ⚠️ YouTube Fetch Error: {e}")

    return None


def clean_messy_string(text):
    if not text:
        return []
    cleaned = str(text).strip()
    if cleaned.startswith('[') and cleaned.endswith(']'):
        try:
            return json.loads(cleaned)
        except BaseException:
            pass
    if cleaned.startswith('{') and cleaned.endswith('}'):
        cleaned = cleaned[1:-1]
    import re
    items = re.findall(r'"([^"]*)"', cleaned)
    if not items and cleaned:
        items = cleaned.split(',')
    return [
        item.replace(
            '\\"', '').strip() for item in items if item.replace(
            '\\"', '').strip() not in [
                '{', '}', '""']]


def process_data():
    print(f"🔄 Processing {len(RAW_DATA)} games...")

    # 1. FETCH DATES
    for game in RAW_DATA:
        name = game['canonical_name']
        original_date = game.get('first_played_date')
        new_date = None

        if game.get('youtube_playlist_url'):
            print(f"📺 Scanning playlist for '{name}'...")
            new_date = get_youtube_date(game['youtube_playlist_url'])

        if not new_date and game.get('twitch_vod_urls'):
            print(f"👾 Fetching Twitch date for '{name}'...")
            new_date = get_twitch_date(game['twitch_vod_urls'])

        if new_date:
            print(f"   ✅ Found: {new_date}")
            game['first_played_date'] = new_date
        else:
            print(f"   ⚠️ No date found (keeping {original_date})")

    # 2. SORT
    print("\n📅 Sorting chronologically...")
    RAW_DATA.sort(key=lambda x: datetime.strptime(str(x.get('first_played_date') or '9999-12-31'), "%Y-%m-%d"))

    # 3. GENERATE SQL
    sql_statements = []
    print("\n📝 Generating SQL...")

    for game in RAW_DATA:
        game_id = game['id']
        name = game['canonical_name']
        raw_alts = game.get('alternative_names', '')
        played_date = game.get('first_played_date')

        current_alts = clean_messy_string(raw_alts)
        if name in SMART_MAPPINGS:
            current_alts.extend(SMART_MAPPINGS[name])

        unique_alts = sorted(list(set(current_alts)))
        unique_alts = [x for x in unique_alts if x.lower() != name.lower()]

        json_val = json.dumps(unique_alts).replace("'", "''")
        date_val = f"'{played_date}'" if played_date else "NULL"

        sql = f"UPDATE played_games SET alternative_names = '{json_val}', first_played_date = {date_val} WHERE id = {game_id};"
        sql_statements.append(sql)

    with open('update_names.sql', 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_statements))

    print(f"✅ Done! Generated update_names.sql with {len(sql_statements)} commands.")


if __name__ == "__main__":
    process_data()
