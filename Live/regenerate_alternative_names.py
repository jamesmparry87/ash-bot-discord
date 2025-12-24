#!/usr/bin/env python3
"""
Alternative Names Regeneration Script

Clears all existing alternative names and regenerates them fresh from IGDB.
This is cleaner than trying to parse corrupted data.

Usage:
    python Live/regenerate_alternative_names.py --dry-run    # Preview changes
    python Live/regenerate_alternative_names.py               # Apply changes
"""

import asyncio
import os
import sys
from typing import Any, Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bot.database_module import get_database
from bot.integrations import igdb


async def regenerate_all_alternative_names(db, dry_run: bool = True) -> Dict[str, Any]:
    """
    Clear all alternative names and regenerate from IGDB.
    
    This is a nuclear option that guarantees clean data by:
    1. Clearing all existing alternative names
    2. Querying IGDB for each game
    3. Updating with fresh validated data
    """
    print("\n" + "=" * 80)
    print("ALTERNATIVE NAMES REGENERATION")
    print("=" * 80)
    print(f"\nMode: {'🔍 DRY RUN (no changes will be made)' if dry_run else '✍️  LIVE MODE (changes will be applied)'}\n")
    
    # Check if IGDB is available
    try:
        test_result = await igdb.validate_and_enrich("Test Game")
        igdb_available = test_result.get('confidence', 0) >= 0 or 'error' not in test_result
        if not igdb_available:
            print("⚠️ IGDB returned 0 confidence for test query")
    except Exception as e:
        print(f"❌ IGDB not available: {e}")
        print("   This script requires IGDB API access to regenerate alternative names.\n")
        return {
            'total_games': 0,
            'cleared': 0,
            'regenerated': 0,
            'failed': 0,
            'skipped': 0,
            'errors': ['IGDB not configured']
        }
    
    stats = {
        'total_games': 0,
        'cleared': 0,
        'regenerated': 0,
        'failed': 0,
        'skipped': 0,
        'errors': []
    }
    
    # Get all games
    games = db.get_all_played_games()
    stats['total_games'] = len(games)
    
    print(f"📊 Found {len(games)} games in database\n")
    print("=" * 80)
    print("PHASE 1: Clearing Existing Alternative Names")
    print("=" * 80 + "\n")
    
    # Phase 1: Clear all alternative names
    for game in games:
        canonical_name = game['canonical_name']
        game_id = game['id']
        current_alt_names = game.get('alternative_names', [])
        
        print(f"🧹 Clearing: {canonical_name}")
        if current_alt_names:
            print(f"   Removing: {current_alt_names}")
        
        if not dry_run:
            try:
                success = db.update_played_game(game_id, alternative_names=[])
                if success:
                    stats['cleared'] += 1
                    print(f"   ✅ Cleared")
                else:
                    stats['failed'] += 1
                    print(f"   ❌ Failed to clear")
            except Exception as e:
                stats['errors'].append(f"{canonical_name}: Clear failed - {str(e)}")
                print(f"   ❌ Error: {e}")
        else:
            stats['cleared'] += 1
            print(f"   🔍 DRY RUN - Would clear")
        
        print()
    
    print(f"\n📊 Phase 1 Summary:")
    print(f"   Games processed: {len(games)}")
    print(f"   Cleared: {stats['cleared']}")
    print(f"   Failed: {stats['failed']}")
    
    # Phase 2: Regenerate from IGDB
    print("\n" + "=" * 80)
    print("PHASE 2: Regenerating Alternative Names from IGDB")
    print("=" * 80 + "\n")
    print("⏱️  Note: This may take a few minutes due to API rate limiting...\n")
    
    for i, game in enumerate(games, 1):
        canonical_name = game['canonical_name']
        game_id = game['id']
        
        print(f"[{i}/{len(games)}] 🔄 Regenerating: {canonical_name}")
        
        try:
            # Query IGDB for fresh data
            igdb_result = await igdb.validate_and_enrich(canonical_name)
            
            if not igdb_result:
                stats['failed'] += 1
                print(f"   ❌ IGDB returned no result")
                print()
                continue
            
            confidence = igdb_result.get('confidence', 0.0)
            new_alt_names = igdb_result.get('alternative_names', [])
            new_canonical = igdb_result.get('canonical_name', canonical_name)
            
            print(f"   IGDB: '{new_canonical}' (confidence: {confidence:.2f})")
            print(f"   Alternative names: {new_alt_names}")
            
            # Only update if we have good confidence
            if confidence >= 0.7:
                if not dry_run:
                    # Update with fresh IGDB data
                    updates = {
                        'canonical_name': new_canonical,
                        'alternative_names': new_alt_names,
                        'genre': igdb_result.get('genre'),
                        'series_name': igdb_result.get('series_name'),
                        'release_year': igdb_result.get('release_year'),
                        'igdb_id': igdb_result.get('igdb_id'),
                        'data_confidence': confidence
                    }
                    
                    # Remove None values
                    updates = {k: v for k, v in updates.items() if v is not None}
                    
                    try:
                        success = db.update_played_game(game_id, **updates)
                        if success:
                            stats['regenerated'] += 1
                            print(f"   ✅ Regenerated with {len(new_alt_names)} alternative names")
                        else:
                            stats['failed'] += 1
                            print(f"   ❌ Failed to update")
                    except Exception as e:
                        stats['errors'].append(f"{canonical_name}: Update failed - {str(e)}")
                        stats['failed'] += 1
                        print(f"   ❌ Error: {e}")
                else:
                    stats['regenerated'] += 1
                    print(f"   🔍 DRY RUN - Would regenerate with {len(new_alt_names)} alternative names")
            
            elif confidence >= 0.4:
                # Medium confidence - note it but skip
                stats['skipped'] += 1
                print(f"   ⚠️ Medium confidence ({confidence:.2f}) - skipping for safety")
            
            else:
                # Low confidence - skip
                stats['skipped'] += 1
                print(f"   ⚠️ Low confidence ({confidence:.2f}) - skipping")
            
            print()
            
            # Add small delay to respect API rate limits (if not dry-run)
            if not dry_run and i < len(games):
                await asyncio.sleep(0.5)  # 500ms between requests
        
        except Exception as e:
            stats['errors'].append(f"{canonical_name}: Regeneration failed - {str(e)}")
            stats['failed'] += 1
            print(f"   ❌ Error: {e}\n")
    
    # Final summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80 + "\n")
    
    print(f"Total games: {stats['total_games']}")
    print(f"Cleared: {stats['cleared']}")
    print(f"Regenerated: {stats['regenerated']}")
    print(f"Skipped (low confidence): {stats['skipped']}")
    print(f"Failed: {stats['failed']}")
    print(f"Errors: {len(stats['errors'])}")
    
    if stats['errors']:
        print(f"\n⚠️  Errors encountered:")
        for error in stats['errors'][:10]:  # Show first 10 errors
            print(f"   • {error}")
        if len(stats['errors']) > 10:
            print(f"   ... and {len(stats['errors']) - 10} more")
    
    success_rate = (stats['regenerated'] / stats['total_games'] * 100) if stats['total_games'] > 0 else 0
    print(f"\n✅ Success rate: {success_rate:.1f}% ({stats['regenerated']}/{stats['total_games']})")
    
    if dry_run:
        print("\n🔍 DRY RUN COMPLETE - No changes were made")
        print("   Run without --dry-run to apply these changes")
    else:
        print("\n✅ REGENERATION COMPLETE")
        print("   All alternative names have been regenerated from IGDB")
    
    return stats


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Regenerate alternative names from IGDB (clears existing data)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying them'
    )
    
    args = parser.parse_args()
    
    if not args.dry_run:
        print("\n" + "=" * 80)
        print("⚠️  WARNING: This will CLEAR all existing alternative names!")
        print("=" * 80)
        print("\nThis script will:")
        print("  1. Clear ALL existing alternative names from the database")
        print("  2. Query IGDB for fresh data for each game")
        print("  3. Update with validated alternative names from IGDB")
        print("\nThis is a destructive operation and cannot be undone.")
        print("Make sure you have a database backup before proceeding!\n")
        
        confirm = input("Are you sure you want to continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("\nAborted. No changes were made.")
            return
        
        print("\n✅ Proceeding with regeneration...\n")
    
    # Get database instance
    db = get_database()
    
    # Run regeneration
    stats = await regenerate_all_alternative_names(db, dry_run=args.dry_run)
    
    # Exit with appropriate code
    if stats.get('errors'):
        sys.exit(1)  # Errors occurred
    else:
        sys.exit(0)  # Success


if __name__ == "__main__":
    asyncio.run(main())
