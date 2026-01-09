#!/usr/bin/env python3
"""
Script to update all database_module imports to use the new modular structure
"""

import os
import re

# Files to update (relative to Live/)
files_to_update = [
    "scripts/add_god_of_war_1.py",
    "scripts/bulk_update_twitch_stats.py",
    "scripts/bulk_update_youtube_stats.py",
    "scripts/comprehensive_data_cleanup.py",
    "scripts/manual_twitch_mapping.py",
    "scripts/regenerate_alternative_names.py",
    "scripts/reset_ids_chronological.py",
    "scripts/update_zombie_army_4.py",
    "tests/test_database.py",
    "tests/test_functional_core.py",
    "tests/test_twitch_data_quality.py",
]

# Replacement patterns
patterns = [
    # Pattern 1: from bot.database_module import X
    (
        r'from bot\.database_module import (.+)',
        r'from bot.database import \1'
    ),
    # Pattern 2: from database_module import X (in tests)
    (
        r'from database_module import (.+)',
        r'from bot.database import \1'
    ),
]

def update_file(filepath):
    """Update database imports in a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        modified = False
        
        for pattern, replacement in patterns:
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                content = new_content
                modified = True
        
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, "Updated"
        else:
            return False, "No changes needed"
            
    except FileNotFoundError:
        return False, "File not found"
    except Exception as e:
        return False, f"Error: {e}"

# Update all files
print("=" * 60)
print("DATABASE IMPORT UPDATER - Modular Structure Migration")
print("=" * 60)

updated_count = 0
skipped_count = 0
error_count = 0

for rel_path in files_to_update:
    filepath = os.path.join("Live", rel_path)
    print(f"\n📄 {rel_path}")
    
    success, message = update_file(filepath)
    
    if success:
        print(f"   ✅ {message}")
        updated_count += 1
    elif "not found" in message.lower():
        print(f"   ⚠️ {message}")
        skipped_count += 1
    else:
        print(f"   ❌ {message}")
        error_count += 1

print("\n" + "=" * 60)
print(f"SUMMARY: {updated_count} updated, {skipped_count} skipped, {error_count} errors")
print("=" * 60)

if updated_count > 0:
    print("\n✅ Import migration complete!")
    print("🔄 Next step: Redeploy to Rook to test new structure")
else:
    print("\n⚠️ No files were updated")
