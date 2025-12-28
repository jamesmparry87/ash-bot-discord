import json
import os
import re

import psycopg2
from psycopg2.extras import RealDictCursor


def parse_postgres_array(array_str):
    """
    Parses a PostgreSQL array string like '{"Item 1","Item 2"}'
    into a clean Python list.
    """
    if not array_str:
        return []

    # If it's already simple text (no braces), just return it as a single item list
    if not array_str.startswith('{') or not array_str.endswith('}'):
        return [array_str]

    # Remove the outer curly braces
    content = array_str[1:-1]

    # If empty, return empty list
    if not content:
        return []

    # Regex to handle quoted strings properly (e.g., "Game, The" vs "Game")
    # This splits by comma ONLY if it's outside of quotes
    pattern = r',(?=(?:[^"]*"[^"]*")*[^"]*$)'
    items = re.split(pattern, content)

    clean_items = []
    for item in items:
        # Strip whitespace and surrounding quotes
        clean = item.strip().strip('"')
        # Un-escape double quotes (Postgres escapes them as \" or "")
        clean = clean.replace('\\"', '"').replace('""', '"')
        if clean:
            clean_items.append(clean)

    return clean_items


def main():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor(cursor_factory=RealDictCursor)

    print("🧹 Starting formatting cleanup...")

    # Get all games with alternative names
    cur.execute("SELECT id, canonical_name, alternative_names FROM played_games WHERE alternative_names IS NOT NULL")
    games = cur.fetchall()

    updated_count = 0

    for game in games:
        raw_alt = game['alternative_names']

        # Skip if it's already a list (unlikely if fetched as text) or None
        if isinstance(raw_alt, list):
            continue

        # Check if it looks like a Postgres array or Python set string
        if isinstance(raw_alt, str) and (raw_alt.startswith('{') or raw_alt.startswith('[')):

            # 1. Parse the messy string into a clean list
            if raw_alt.startswith('['):
                # It might be a stringified JSON list already
                try:
                    clean_list = json.loads(raw_alt)
                except BaseException:
                    clean_list = parse_postgres_array(raw_alt)
            else:
                # It's a Postgres array string e.g. {"A","B"}
                clean_list = parse_postgres_array(raw_alt)

            # 2. Convert that list to a JSON string for storage
            # This ensures it looks like ["GTA 5", "Other Name"] in the DB
            new_json_str = json.dumps(clean_list)

            if new_json_str != raw_alt:
                cur.execute(
                    "UPDATE played_games SET alternative_names = %s WHERE id = %s",
                    (new_json_str, game['id'])
                )
                print(f"✨ Fixed '{game['canonical_name']}': {raw_alt[:30]}... -> {new_json_str[:30]}...")
                updated_count += 1

    conn.commit()
    conn.close()
    print(f"\n✅ Cleanup complete! Updated {updated_count} games.")


if __name__ == "__main__":
    main()
