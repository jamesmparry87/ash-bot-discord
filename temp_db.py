import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'Live'))
from bot.database import get_database
db = get_database()
if db:
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, canonical_name FROM games WHERE canonical_name ILIKE '%Assassin%'")
        games = cur.fetchall()
        for g in games:
            print(dict(g))
