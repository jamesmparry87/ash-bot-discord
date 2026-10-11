import argparse
import os
import sys

# Ensure Windows prints emojis properly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Determine the absolute path to the Live directory
# File is in: <repo>/.agents/skills/db_clip_inspector/scripts/check_db_clips.py (5 levels deep)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LIVE_DIR = os.path.join(REPO_ROOT, "Live")
sys.path.insert(0, LIVE_DIR)

# Load environment variables, overriding any stale process variables
from dotenv import load_dotenv
env_path = os.path.join(LIVE_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)

try:
    from bot.database import get_database
except ImportError as e:
    print(f"❌ Failed to import bot database module: {e}")
    sys.exit(1)


def inspect_clip_lore(reset_stuck: bool = False, dry_run: bool = False):
    """Inspects the PostgreSQL database clip_lore table and reports status."""
    db = get_database()
    conn = db.get_connection()
    if not conn:
        print("❌ Could not establish database connection. Check DATABASE_URL in Live/.env.")
        sys.exit(1)

    try:
        with conn.cursor() as cur:
            # 1. Total clips
            cur.execute("SELECT COUNT(*) FROM clip_lore")
            total = cur.fetchone()['count']

            # 2. Status breakdown
            cur.execute("SELECT COALESCE(batch_status, 'COMPLETED (legacy)') as status, COUNT(*) as count FROM clip_lore GROUP BY batch_status")
            status_counts = cur.fetchall()

            # 3. Pending batches check
            cur.execute("SELECT id, canonical_url, batch_status, batch_job_id, created_at FROM clip_lore WHERE batch_status = 'PENDING'")
            pending_rows = cur.fetchall()

            # 4. Recent clips sample
            cur.execute("SELECT id, canonical_url, game_title, notable_quote, created_at FROM clip_lore ORDER BY id DESC LIMIT 5")
            recent_rows = cur.fetchall()

            has_pending = db.trivia.has_pending_batch()

            print("\n" + "=" * 50)
            print("📊 DATABASE CLIP LORE AUDIT REPORT")
            print("=" * 50)
            print(f"Total clip records in DB: {total}")
            print("\nStatus Breakdown:")
            for row in status_counts:
                print(f"  • {row['status']}: {row['count']}")

            print(f"\nBatch Job Status:")
            print(f"  • db.trivia.has_pending_batch(): {has_pending}")
            print(f"  • Active PENDING records: {len(pending_rows)}")

            if pending_rows:
                print("\n⚠️ Currently Pending Batches:")
                for r in pending_rows:
                    print(f"    - ID {r['id']} | Job: {r['batch_job_id']} | URL: {r['canonical_url']}")

                if reset_stuck:
                    if dry_run:
                        print(f"\n🔍 [DRY RUN] Would reset {len(pending_rows)} stuck PENDING records so they can be re-queued.")
                    else:
                        print(f"\n🧹 Resetting {len(pending_rows)} stuck PENDING records...")
                        cur.execute("DELETE FROM clip_lore WHERE batch_status = 'PENDING'")
                        conn.commit()
                        print(f"✅ Successfully cleared {len(pending_rows)} stuck pending records.")
            else:
                print("  • No batches currently blocking new batch submissions.")

            print("\nRecent 5 Clips in Database:")
            for r in recent_rows:
                quote = (r['notable_quote'][:40] + "...") if r['notable_quote'] and len(r['notable_quote']) > 40 else (r['notable_quote'] or "None")
                print(f"  • ID {r['id']} | Game: {r.get('game_title', 'Unknown')} | Quote: \"{quote}\"")

            print("=" * 50 + "\n")

    except Exception as e:
        print(f"❌ Error during clip lore inspection: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit and inspect database clip_lore status.")
    parser.add_argument("--reset-stuck-batches", action="store_true", help="Clear stuck PENDING records in clip_lore")
    parser.add_argument("--dry-run", action="store_true", help="Preview reset actions without modifying the database")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    inspect_clip_lore(reset_stuck=args.reset_stuck_batches, dry_run=args.dry_run)
