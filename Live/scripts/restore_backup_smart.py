"""
Smart Data Restoration Script

Restores clean alternative_names, series_name, and first_played_date from backup
while keeping HIGHER values for stats (views, episodes, playtime) from current data.

Usage:
    python Live/scripts/restore_backup_smart.py
"""

import json
import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from Live.bot.database_module import get_database

def parse_alternative_names(alt_names_value):
    """Parse alternative_names from various formats to Python list"""
    if not alt_names_value:
        return []
    
    if isinstance(alt_names_value, list):
        return alt_names_value
    
    if isinstance(alt_names_value, str):
        # Handle JSON string format: '["name1", "name2"]'
        if alt_names_value.startswith('[') and alt_names_value.endswith(']'):
            try:
                return json.loads(alt_names_value)
            except json.JSONDecodeError:
                pass
        # Handle empty or null strings
        if alt_names_value.lower() in ['null', '', '[]']:
            return []
        # Handle comma-separated format (legacy)
        return [name.strip() for name in alt_names_value.split(',') if name.strip()]
    
    return []

def smart_restore_from_backup():
    """
    Smart restoration that:
    1. Restores protected fields from backup (alternative_names, series_name, first_played_date)
    2. Keeps HIGHER values for stats (views, episodes, playtime) from current DB
    """
    db = get_database()
    
    # Load backup data
    backup_path = 'archive/backup_played_games_20251224_142749.json'
    if not os.path.exists(backup_path):
        print(f"❌ Backup file not found: {backup_path}")
        return
    
    with open(backup_path, 'r', encoding='utf-8') as f:
        backup_games = json.load(f)
    
    print(f"📦 Loaded {len(backup_games)} games from backup")
    print("=" * 80)
    
    restored_count = 0
    skipped_count = 0
    error_count = 0
    
    for backup_game in backup_games:
        game_id = backup_game.get('id')
        canonical_name = backup_game.get('canonical_name', 'Unknown')
        
        try:
            # Get current game data from database
            current_game = db.get_played_game_by_id(game_id)
            
            if not current_game:
                print(f"⚠️  Game ID {game_id} ({canonical_name}) not found in database, skipping")
                skipped_count += 1
                continue
            
            # Parse backup alternative names (handle JSON string format)
            backup_alt_names = parse_alternative_names(backup_game.get('alternative_names'))
            current_alt_names = current_game.get('alternative_names', [])
            
            # Build update params with smart merging
            update_params = {}
            
            # 1. ALWAYS restore alternative_names from backup (this is the clean data)
            if backup_alt_names:
                update_params['alternative_names'] = backup_alt_names
                print(f"✅ {canonical_name}: Restoring alternative_names: {backup_alt_names}")
            elif current_alt_names:
                # Keep current if backup is empty but current has data
                print(f"ℹ️  {canonical_name}: Keeping current alternative_names: {current_alt_names}")
            
            # 2. ALWAYS restore series_name from backup (doesn't change)
            backup_series = backup_game.get('series_name')
            if backup_series:
                update_params['series_name'] = backup_series
                print(f"✅ {canonical_name}: Restoring series_name: {backup_series}")
            
            # 3. ALWAYS restore first_played_date from backup (historical data)
            backup_date = backup_game.get('first_played_date')
            if backup_date:
                update_params['first_played_date'] = backup_date
                print(f"✅ {canonical_name}: Restoring first_played_date: {backup_date}")
            
            # 4. Keep HIGHER values for stats (current data may be more recent)
            backup_views = backup_game.get('youtube_views', 0) or 0
            current_views = current_game.get('youtube_views', 0) or 0
            if backup_views > current_views:
                update_params['youtube_views'] = backup_views
                print(f"📊 {canonical_name}: Using backup views: {backup_views} > {current_views}")
            
            backup_episodes = backup_game.get('total_episodes', 0) or 0
            current_episodes = current_game.get('total_episodes', 0) or 0
            if backup_episodes > current_episodes:
                update_params['total_episodes'] = backup_episodes
                print(f"📊 {canonical_name}: Using backup episodes: {backup_episodes} > {current_episodes}")
            
            backup_playtime = backup_game.get('total_playtime_minutes', 0) or 0
            current_playtime = current_game.get('total_playtime_minutes', 0) or 0
            if backup_playtime > current_playtime:
                update_params['total_playtime_minutes'] = backup_playtime
                print(f"📊 {canonical_name}: Using backup playtime: {backup_playtime} > {current_playtime}")
            
            # Apply updates if we have anything to update
            if update_params:
                success = db.update_played_game(game_id, **update_params)
                if success:
                    restored_count += 1
                    print(f"✅ Successfully updated game ID {game_id}")
                else:
                    print(f"❌ Failed to update game ID {game_id}")
                    error_count += 1
            else:
                print(f"ℹ️  {canonical_name}: No updates needed")
                skipped_count += 1
            
            print("-" * 80)
            
        except Exception as e:
            print(f"❌ Error processing game ID {game_id} ({canonical_name}): {e}")
            error_count += 1
            print("-" * 80)
            continue
    
    print("=" * 80)
    print(f"✅ Restoration complete!")
    print(f"   - Restored: {restored_count} games")
    print(f"   - Skipped: {skipped_count} games")
    print(f"   - Errors: {error_count} games")
    print("=" * 80)

if __name__ == "__main__":
    print("🔧 Smart Data Restoration Script")
    print("=" * 80)
    print("This will restore clean metadata from backup while keeping")
    print("higher stat values from the current database.")
    print("=" * 80)
    
    response = input("Proceed with restoration? (yes/no): ").strip().lower()
    if response == 'yes':
        smart_restore_from_backup()
    else:
        print("❌ Restoration cancelled")
