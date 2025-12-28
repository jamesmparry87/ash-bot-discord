"""
Reset played_games IDs to Chronological Order (Refill Method)
Date: 2025-12-26
Purpose: Renumber game IDs based on first_played_date (oldest = 1)
Safeguards: Uses TRUNCATE + INSERT to avoid dropping tables/sequences.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from bot.database_module import get_database
except ImportError:
    print("❌ Error: Could not import database_module.")
    sys.exit(1)


def get_val(row, key, index):
    """Helper to get value from either dict or tuple row"""
    try:
        return row[key]
    except (TypeError, KeyError):
        return row[index]


def get_table_columns(cur, table_name):
    """Dynamically fetch column names excluding 'id'"""
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s AND column_name != 'id'
        ORDER BY ordinal_position
    """, (table_name,))
    return [get_val(row, 'column_name', 0) for row in cur.fetchall()]


def reset_ids_chronological(dry_run=True):
    print("=" * 80)
    print("🔄 RESET IDS TO CHRONOLOGICAL ORDER (REFILL METHOD)")
    print("=" * 80)

    if dry_run:
        print("\n⚠️ DRY RUN MODE - No changes will be made")
    else:
        print("\n🚨 LIVE MODE - Database will be modified!")
        print("⚠️ ENSURE YOU HAVE A BACKUP BEFORE PROCEEDING!")
        response = input("\nType 'CONFIRM' to proceed: ")
        if response != "CONFIRM":
            print("❌ Operation cancelled.")
            return False

    db = get_database()
    conn = db.get_connection()
    if not conn:
        print("❌ Failed to connect to database")
        return False

    try:
        with conn.cursor() as cur:
            # Step 1: Detect Columns
            columns = get_table_columns(cur, 'played_games')
            col_str = ", ".join(columns)
            print(f"\n🔍 Step 1: Detected {len(columns)} columns to preserve.")

            # Step 2: Fetch ALL Data Sorted by Date
            print("\n📋 Step 2: Fetching data in chronological order...")
            query = f"""
                SELECT {col_str}
                FROM played_games
                ORDER BY first_played_date ASC NULLS LAST, created_at ASC
            """
            cur.execute(query)
            # Store all rows in memory (list of tuples/dicts)
            all_games = cur.fetchall()
            total_games = len(all_games)
            print(f"✅ Loaded {total_games} games into memory.")

            if dry_run:
                print("\n📊 Preview (Top 5):")
                # Just grabbing the first column (likely canonical_name) to show preview
                for i, game in enumerate(all_games[:5], 1):
                    # Trying to find the name column dynamically or falling back to index 0
                    try:
                        name = game['canonical_name']
                    except BaseException:
                        name = game[0]  # Fallback if columns are ordered
                    print(f"   New ID {i:3} : {name}")
                return True

            # Step 3: Nuke the Data (But keep the table structure!)
            print("\n💣 Step 3: Clearing table data...")
            cur.execute("TRUNCATE TABLE played_games RESTART IDENTITY")

            # Step 4: Re-Insert Data
            print("\n🔄 Step 4: Refilling table with new IDs...")

            insert_query = f"""
                INSERT INTO played_games (id, {col_str})
                VALUES (%s, {', '.join(['%s'] * len(columns))})
            """

            for new_id, game in enumerate(all_games, start=1):
                # Convert row object to list of values matching 'columns' order
                if isinstance(game, dict):
                    values = [game[col] for col in columns]
                else:
                    values = list(game)  # tuple to list

                # Prepend the new ID
                insert_args = [new_id] + values

                cur.execute(insert_query, insert_args)

                if new_id % 10 == 0:
                    sys.stdout.write(f"\r   Restored {new_id}/{total_games} games...")
                    sys.stdout.flush()

            print(f"\n✅ Successfully restored {total_games} games.")

            # Step 5: Fix Sequence (Just in case TRUNCATE didn't reset it perfectly)
            print("\n🔢 Step 5: Syncing ID sequence...")
            cur.execute("SELECT setval('played_games_id_seq', %s, true)", (total_games,))

            conn.commit()

            print("\n" + "=" * 80)
            print("✅ SUCCESS: IDs Reset Complete")
            print("=" * 80)
            print(f"Timeline is now perfect. Next game ID will be: {total_games + 1}")
            return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Reset IDs')
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    args = parser.parse_args()

    reset_ids_chronological(dry_run=not args.apply)
