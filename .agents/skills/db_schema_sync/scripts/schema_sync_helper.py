import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import argparse
import re

def analyze_schema_sync(column_name, data_type, table_name="played_games", dry_run=False):
    repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    core_path = os.path.join(repo_dir, "Live", "bot", "database", "core.py")
    games_path = os.path.join(repo_dir, "Live", "bot", "database", "games.py")

    print(f"🔍 Analyzing schema sync for adding '{column_name}' ({data_type}) to table '{table_name}'...\n")
    
    if dry_run:
        print("🔍 [DRY RUN] Showing insertion points without making changes.\n")

    files_to_check = [core_path, games_path]
    for f in files_to_check:
        if not os.path.exists(f):
            print(f"❌ ERROR: Could not find {f}")
            return
            
    # Check core.py
    with open(core_path, 'r', encoding='utf-8') as f:
        core_content = f.read()
    
    print(f"--- Action Items for core.py ---")
    if f"{table_name.upper()}_COLUMNS" in core_content:
        print(f"✅ Found {table_name.upper()}_COLUMNS. You must add '{column_name}' to this list.")
    else:
        print(f"⚠️ Warning: Could not find {table_name.upper()}_COLUMNS whitelist. Check if it exists.")

    if f"CREATE TABLE IF NOT EXISTS {table_name}" in core_content:
        print(f"✅ Found table creation for {table_name}. Add '{column_name} {data_type}' to the schema.")
        print(f"✅ Add a migration block: ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {data_type};")
    
    # Check games.py
    print(f"\n--- Action Items for games.py ---")
    with open(games_path, 'r', encoding='utf-8') as f:
        games_content = f.read()
        
    if "def bulk_import" in games_content:
        print(f"✅ Found bulk_import function. Ensure '{column_name}' is handled during merge resolution.")
        print(f"✅ Ensure '{column_name}' is added to the INSERT INTO and ON CONFLICT DO UPDATE strings.")
        
    print("\n✅ Analysis complete. Follow these action items to safely sync the schema.")
    print("Next steps: Apply the changes using multi_replace_file_content, and write a test in test_database.py.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("column_name", help="Name of the new column")
    parser.add_argument("data_type", help="SQL data type (e.g. TEXT, INTEGER)")
    parser.add_argument("--table", default="played_games", help="Table name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    analyze_schema_sync(args.column_name, args.data_type, args.table, dry_run=args.dry_run)
