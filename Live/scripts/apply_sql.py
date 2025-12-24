import os
import sys

import psycopg2


def apply_sql():
    # 1. Get Database URL
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ Error: DATABASE_URL is missing.")
        return

    # 2. Check for the SQL file
    sql_file = 'update_names.sql'
    if not os.path.exists(sql_file):
        print(f"❌ Error: '{sql_file}' not found in the current folder.")
        print("   Did you run generate_json_names.py yet?")
        return

    try:
        # 3. Connect to Database
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # 4. Read the SQL file
        print(f"📖 Reading {sql_file}...")
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # 5. Execute
        if not sql_content.strip():
            print("⚠️ SQL file is empty. Nothing to do.")
            return

        print("🚀 Applying updates... (This might take a moment)")
        cur.execute(sql_content)
        conn.commit()

        print("✅ Success! All game names have been updated.")

    except Exception as e:
        print(f"❌ Database Error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    apply_sql()