import os
import sys
import argparse
import psycopg2

def run_audit(dry_run=False):
    # Attempt to load DATABASE_URL from Live/.env if it exists
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "Live", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    os.environ["DATABASE_URL"] = line.strip().split("=")[1]

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found in environment or Live/.env")
        sys.exit(1)

    print("Connecting to database to audit clip_lore...")
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cursor:
            # Query to find rows where essential fields are missing or 'None'
            query1_select = """
                SELECT count(*) FROM clip_lore 
                WHERE notable_quote IS NULL OR notable_quote = 'None' OR notable_quote = ''
                   OR reaction IS NULL OR reaction = 'None' OR reaction = ''
                   OR clip_outcome IS NULL OR clip_outcome = 'None' OR clip_outcome = ''
            """
            cursor.execute(query1_select)
            null_count = cursor.fetchone()[0]
            
            # Query to find quotes less than 3 words
            query2_select = "SELECT count(*) FROM clip_lore WHERE array_length(regexp_split_to_array(trim(notable_quote), '\\s+'), 1) < 3;"
            cursor.execute(query2_select)
            short_count = cursor.fetchone()[0]
            
            total = null_count + short_count
            
            if dry_run:
                print(f"🔍 [DRY RUN] Audit complete. Found {total} anomalous clips:")
                print(f"   - {null_count} clips with missing critical data")
                print(f"   - {short_count} clips with unhelpful short quotes")
                print("\nRun without --dry-run to delete these records.")
                return

            if total > 0:
                print("🗑️ Deleting anomalous clips...")
                
                query1_delete = """
                    DELETE FROM clip_lore 
                    WHERE notable_quote IS NULL OR notable_quote = 'None' OR notable_quote = ''
                       OR reaction IS NULL OR reaction = 'None' OR reaction = ''
                       OR clip_outcome IS NULL OR clip_outcome = 'None' OR clip_outcome = ''
                """
                cursor.execute(query1_delete)
                
                query2_delete = "DELETE FROM clip_lore WHERE array_length(regexp_split_to_array(trim(notable_quote), '\\s+'), 1) < 3;"
                cursor.execute(query2_delete)
                
                conn.commit()
                
                print(f"✅ Audit complete. Flagged and deleted {total} anomalous clips for batch reprocessing:")
                print(f"   - {null_count} clips with missing critical data")
                print(f"   - {short_count} clips with unhelpful short quotes")
            else:
                print("✅ Audit complete. No anomalies found. Database is clean!")
                
    except Exception as e:
        conn.rollback()
        print(f"❌ Error during audit: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit and clean clip lore data.")
    parser.add_argument("--dry-run", action="store_true", help="Report anomalies without deleting them.")
    args = parser.parse_args()
    
    run_audit(dry_run=args.dry_run)
