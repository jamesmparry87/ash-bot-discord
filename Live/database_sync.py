#!/usr/bin/env python3
"""
Database Sync Utility for Discord Bot
====================================

Syncs specific tables from live database to staging database.
Clears staging data first, then imports fresh data from live.

Usage:
    python database_sync.py
    python database_sync.py --tables played_games,trivia_questions
    python database_sync.py --dry-run
    python database_sync.py --force (skip confirmation)
"""

import os
import sys
import argparse
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection as Connection

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class DatabaseSyncManager:
    """Manages syncing data between live and staging databases"""
    
    def __init__(self):
        self.live_url = os.getenv("LIVE_DATABASE_URL")
        self.staging_url = os.getenv("DATABASE_URL")
        
        if not self.live_url:
            raise ValueError("LIVE_DATABASE_URL environment variable not found")
        if not self.staging_url:
            raise ValueError("DATABASE_URL environment variable not found")
            
        self.live_conn: Optional[Connection] = None
        self.staging_conn: Optional[Connection] = None
        
        # Tables to sync in dependency order (dependencies first)
        self.default_tables = [
            "played_games",           # Independent table
            "game_recommendations",   # Independent table  
            "trivia_questions",      # Independent table
            "trivia_sessions",       # Depends on trivia_questions
            "trivia_answers"         # Depends on trivia_sessions
        ]
        
    def connect_databases(self) -> bool:
        """Connect to both live and staging databases"""
        try:
            logger.info("🔗 Connecting to live database...")
            self.live_conn = psycopg2.connect(self.live_url, cursor_factory=RealDictCursor)
            logger.info("✓ Connected to live database")
            
            logger.info("🔗 Connecting to staging database...")
            self.staging_conn = psycopg2.connect(self.staging_url, cursor_factory=RealDictCursor)
            logger.info("✓ Connected to staging database")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False
    
    def close_connections(self):
        """Close database connections"""
        if self.live_conn and not self.live_conn.closed:
            self.live_conn.close()
            logger.info("🔐 Live database connection closed")
            
        if self.staging_conn and not self.staging_conn.closed:
            self.staging_conn.close()
            logger.info("🔐 Staging database connection closed")
    
    def table_exists(self, conn, table_name: str) -> bool:
        """Check if a table exists in the database"""
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    )
                """, (table_name,))
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error checking table {table_name}: {e}")
            return False
    
    def get_table_row_count(self, conn, table_name: str) -> int:
        """Get row count for a table"""
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                result = cur.fetchone()
                return int(result[0]) if result else 0
        except Exception as e:
            logger.error(f"Error getting row count for {table_name}: {e}")
            return 0
    
    def validate_tables(self, tables_to_sync: List[str]) -> Tuple[List[str], List[str]]:
        """Validate that tables exist in both databases"""
        valid_tables = []
        missing_tables = []
        
        for table in tables_to_sync:
            live_exists = self.table_exists(self.live_conn, table)
            staging_exists = self.table_exists(self.staging_conn, table)
            
            if live_exists and staging_exists:
                live_count = self.get_table_row_count(self.live_conn, table)
                staging_count = self.get_table_row_count(self.staging_conn, table)
                logger.info(f"📊 Table '{table}': Live={live_count} rows, Staging={staging_count} rows")
                valid_tables.append(table)
            else:
                missing_info = []
                if not live_exists:
                    missing_info.append("live")
                if not staging_exists:
                    missing_info.append("staging")
                logger.warning(f"⚠️  Table '{table}' missing in: {', '.join(missing_info)}")
                missing_tables.append(table)
                
        return valid_tables, missing_tables
    
    def clear_staging_table(self, table_name: str, dry_run: bool = False) -> int:
        """Clear all data from a staging table"""
        if dry_run:
            if self.staging_conn:
                return self.get_table_row_count(self.staging_conn, table_name)
            logger.info(f"🔍 [DRY RUN] Would clear staging table: {table_name}")
            return 0
        
        if not self.staging_conn:
            raise Exception("No staging database connection")
            
        try:
            with self.staging_conn.cursor() as cur:
                # Get count before clearing
                row_count = self.get_table_row_count(self.staging_conn, table_name)
                
                # Clear the table
                cur.execute(f"DELETE FROM {table_name}")
                self.staging_conn.commit()
                
                logger.info(f"🗑️  Cleared staging table '{table_name}': {row_count} rows deleted")
                return row_count
                
        except Exception as e:
            logger.error(f"❌ Error clearing table {table_name}: {e}")
            if self.staging_conn:
                self.staging_conn.rollback()
            raise
    
    def sync_table_data(self, table_name: str, dry_run: bool = False) -> int:
        """Sync data from live to staging for a specific table"""
        if dry_run:
            if self.live_conn:
                live_count = self.get_table_row_count(self.live_conn, table_name)
                logger.info(f"🔍 [DRY RUN] Would sync {live_count} rows to staging table: {table_name}")
                return live_count
            return 0
        
        if not self.live_conn or not self.staging_conn:
            raise Exception("Missing database connections")
        
        try:
            # Get all data from live table
            with self.live_conn.cursor() as live_cur:
                live_cur.execute(f"SELECT * FROM {table_name}")
                rows = live_cur.fetchall()
                
            if not rows:
                logger.info(f"📭 No data to sync for table '{table_name}'")
                return 0
            
            # Get column names from the first row (handle both dict and tuple results)
            first_row = rows[0]
            if hasattr(first_row, 'keys') and callable(getattr(first_row, 'keys', None)):
                # For RealDictRow objects, we can get keys
                columns = list(first_row.keys())  # type: ignore
            else:
                # Fallback: get column names from cursor description
                with self.live_conn.cursor() as desc_cur:
                    desc_cur.execute(f"SELECT * FROM {table_name} LIMIT 1")
                    columns = [desc[0] for desc in desc_cur.description] if desc_cur.description else []
            
            if not columns:
                logger.warning(f"⚠️  Could not determine columns for table {table_name}")
                return 0
            
            # Prepare insert statement
            placeholders = ', '.join(['%s'] * len(columns))
            insert_sql = f"""
                INSERT INTO {table_name} ({', '.join(columns)}) 
                VALUES ({placeholders})
            """
            
            # Insert data in batches
            with self.staging_conn.cursor() as staging_cur:
                batch_size = 100
                inserted_count = 0
                
                # Determine if we have dict-like rows (RealDictRow) or tuple-like rows
                is_dict_like = hasattr(first_row, 'keys')
                
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    # Handle both dict-like and tuple-like rows consistently
                    if is_dict_like:
                        # For RealDictRow objects, extract values by column name
                        batch_values = [tuple(row[col] for col in columns) for row in batch]
                    else:
                        # For tuple rows, use as-is
                        batch_values = [tuple(row) for row in batch]
                    
                    staging_cur.executemany(insert_sql, batch_values)
                    inserted_count += len(batch)
                    
                    # Show progress for large tables
                    if len(rows) > 1000 and i % 1000 == 0:
                        logger.info(f"   📥 Inserted {inserted_count}/{len(rows)} rows...")
                
                self.staging_conn.commit()
                logger.info(f"✅ Synced table '{table_name}': {inserted_count} rows imported")
                return inserted_count
                
        except Exception as e:
            logger.error(f"❌ Error syncing table {table_name}: {e}")
            if self.staging_conn:
                self.staging_conn.rollback()
            raise
    
    def sync_tables(self, tables_to_sync: List[str], dry_run: bool = False, force: bool = False) -> Dict[str, int]:
        """Main sync process - clear staging and import from live"""
        
        if not self.connect_databases():
            return {}
        
        try:
            # Validate tables exist
            logger.info("🔍 Validating tables...")
            valid_tables, missing_tables = self.validate_tables(tables_to_sync)
            
            if missing_tables:
                logger.error(f"❌ Cannot proceed - missing tables: {missing_tables}")
                return {}
            
            if not valid_tables:
                logger.error("❌ No valid tables to sync")
                return {}
            
            # Show sync summary
            logger.info(f"\n📋 Sync Summary:")
            logger.info(f"   Source: LIVE_DATABASE_URL")
            logger.info(f"   Target: DATABASE_URL (staging)")
            logger.info(f"   Tables: {', '.join(valid_tables)}")
            logger.info(f"   Mode: {'DRY RUN' if dry_run else 'LIVE SYNC'}")
            
            # Confirmation (unless forced or dry run)
            if not dry_run and not force:
                logger.warning(f"\n⚠️  WARNING: This will PERMANENTLY DELETE all data in staging tables!")
                confirmation = input(f"Type 'yes' to continue: ").strip().lower()
                if confirmation != 'yes':
                    logger.info("🚫 Sync cancelled by user")
                    return {}
            
            logger.info(f"\n🚀 Starting sync process...")
            
            # Clear staging tables in reverse order (to handle foreign keys)
            sync_results = {}
            clearing_order = list(reversed(valid_tables))
            
            logger.info(f"🗑️  Clearing staging tables...")
            for table in clearing_order:
                try:
                    cleared_count = self.clear_staging_table(table, dry_run)
                    sync_results[f"{table}_cleared"] = cleared_count
                except Exception as e:
                    logger.error(f"❌ Failed to clear {table}: {e}")
                    return {}
            
            # Import data in forward order (to respect dependencies)
            logger.info(f"📥 Importing data from live database...")
            for table in valid_tables:
                try:
                    imported_count = self.sync_table_data(table, dry_run)
                    sync_results[f"{table}_imported"] = imported_count
                except Exception as e:
                    logger.error(f"❌ Failed to sync {table}: {e}")
                    return {}
            
            return sync_results
            
        finally:
            self.close_connections()
    
    def print_results(self, results: Dict[str, int], dry_run: bool = False):
        """Print sync results summary"""
        if not results:
            return
            
        mode = "DRY RUN COMPLETED" if dry_run else "SYNC COMPLETED SUCCESSFULLY"
        logger.info(f"\n🎉 {mode}!")
        logger.info(f"=" * 50)
        
        # Group results by table
        tables = set()
        for key in results.keys():
            if key.endswith('_cleared') or key.endswith('_imported'):
                table_name = key.replace('_cleared', '').replace('_imported', '')
                tables.add(table_name)
        
        total_cleared = 0
        total_imported = 0
        
        for table in sorted(tables):
            cleared = results.get(f"{table}_cleared", 0)
            imported = results.get(f"{table}_imported", 0)
            
            logger.info(f"📊 {table}:")
            logger.info(f"   Cleared: {cleared:,} rows")
            logger.info(f"   Imported: {imported:,} rows")
            
            total_cleared += cleared
            total_imported += imported
        
        logger.info(f"-" * 50)
        logger.info(f"📈 Totals:")
        logger.info(f"   Total cleared: {total_cleared:,} rows")
        logger.info(f"   Total imported: {total_imported:,} rows")


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Sync specific tables from live database to staging database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python database_sync.py
  python database_sync.py --tables played_games,trivia_questions
  python database_sync.py --dry-run
  python database_sync.py --force
        """
    )
    
    parser.add_argument(
        "--tables", 
        type=str,
        help="Comma-separated list of tables to sync (default: played_games,game_recommendations,trivia_questions,trivia_sessions,trivia_answers)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without making changes"
    )
    
    parser.add_argument(
        "--force",
        action="store_true", 
        help="Skip confirmation prompt"
    )
    
    args = parser.parse_args()
    
    # Initialize sync manager
    try:
        sync_manager = DatabaseSyncManager()
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        sys.exit(1)
    
    # Determine tables to sync
    if args.tables:
        tables_to_sync = [table.strip() for table in args.tables.split(",")]
    else:
        tables_to_sync = sync_manager.default_tables
    
    # Validate table names
    if not tables_to_sync:
        logger.error("❌ No tables specified for sync")
        sys.exit(1)
    
    logger.info("🤖 Database Sync Utility")
    logger.info("=" * 50)
    
    try:
        # Perform sync
        results = sync_manager.sync_tables(
            tables_to_sync=tables_to_sync,
            dry_run=args.dry_run,
            force=args.force
        )
        
        # Print results
        sync_manager.print_results(results, args.dry_run)
        
        if results:
            sys.exit(0)  # Success
        else:
            sys.exit(1)  # Failure
            
    except KeyboardInterrupt:
        logger.info("\n🚫 Sync cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
