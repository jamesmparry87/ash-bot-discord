import sys

sys.path.append('.')
from bot.database.core import DatabaseManager

db = DatabaseManager()
conn = db.pool.getconn()
try:
    with conn.cursor() as cur:
        # Check if the column exists
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='played_games' and column_name='completed_date'")
        if not cur.fetchone():
            print("Adding completed_date column to played_games...")
            cur.execute("ALTER TABLE played_games ADD COLUMN completed_date DATE")
            conn.commit()
            print("Column added successfully.")
        else:
            print("Column already exists.")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    db.pool.putconn(conn)
