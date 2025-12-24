import datetime
import json
import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def backup_table():
    # Get connection string from env var or args
    connection_string = os.getenv('DATABASE_URL')
    if not connection_string:
        # Fallback for manual running if env var isn't set
        if len(sys.argv) > 1:  # Check if passed as argument
            connection_string = sys.argv[1]
        else:
            print("❌ No connection string found. Set DATABASE_URL or pass as argument.")
            sys.exit(1)

    try:
        conn = psycopg2.connect(connection_string, cursor_factory=RealDictCursor)
        print("✅ Connected to database")

        table_name = "played_games"
        print(f"📦 Backing up '{table_name}'...")

        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {table_name}")
            rows = cur.fetchall()

            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"backup_{table_name}_{timestamp}.json"

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(rows, f, default=json_serial, indent=2, ensure_ascii=False)

            print(f"🎉 Success! Saved {len(rows)} rows to {filename}")

    except Exception as e:
        print(f"❌ Backup failed: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()


if __name__ == "__main__":
    backup_table()
