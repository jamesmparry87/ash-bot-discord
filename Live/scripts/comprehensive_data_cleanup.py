#!/usr/bin/env python3
"""
Comprehensive Data Cleanup Script

Fixes 4 major data quality issues:
1. Malformed alternative names (JSON/array corruption)
2. Wrong IGDB matches (alternative names from wrong games)
3. Non-game Twitch titles (stream descriptions saved as games)
4. DLC/skin suffixes on game names

Run with: python3 Live/comprehensive_data_cleanup.py --dry-run
"""

import asyncio
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from bot.database_module import get_database
from bot.integrations import igdb

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def is_already_clean(alt_names_field: Any) -> bool:
    """Check if alternative names are already in clean format."""
    if not alt_names_field:
        return True  # Empty is clean

    if isinstance(alt_names_field, list):
        return True  # List is clean

    if isinstance(alt_names_field, str):
        # Empty string or empty array representations are clean
        if alt_names_field.strip() in ['', '{}', '[]']:
            return True

        # Simple comma-separated without braces/quotes is clean
        if '{' not in alt_names_field and '"' not in alt_names_field and '\\' not in alt_names_field:
            return True

    return False


def parse_malformed_alternative_names(alt_names_field: Any) -> Optional[List[str]]:
    """
    Parse alternative names from various malformed formats.

    Returns:
        List of clean names, or None if parsing fails

    Handles:
    - PostgreSQL arrays: {"name1","name2","name3"}
    - Nested corruption: {Batman:AA,"{Batman:AA,\"Arkham Asylum\",B:AA}","Arkham Asylum",B:AA}
    - Empty/None values: {}, [], "", None
    """
    if not alt_names_field:
        return []

    if isinstance(alt_names_field, list):
        return alt_names_field  # Already clean

    if not isinstance(alt_names_field, str):
        return None

    text = alt_names_field.strip()

    # Empty array representations are clean (not malformed)
    if text in ['{}', '[]', '']:
        return []

    # If it's already clean (comma-separated, no special chars), return as-is
    if is_already_clean(text):
        return [name.strip() for name in text.split(',') if name.strip()]

    # Try to parse as PostgreSQL array first
    try:
        # Remove outer braces
        if text.startswith('{') and text.endswith('}'):
            text = text[1:-1]

        # Split by commas, handling quoted strings
        names = []
        current = ''
        in_quotes = False
        escape_next = False

        for char in text:
            if escape_next:
                current += char
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"':
                in_quotes = not in_quotes
                continue

            if char == ',' and not in_quotes:
                name = current.strip()
                if name and len(name) >= 2:  # Skip very short fragments
                    # Remove any remaining braces or quotes
                    name = name.strip('{}"\' ')
                    if name and not name.startswith('\\'):  # Skip backslash artifacts
                        names.append(name)
                current = ''
                continue

            current += char

        # Add last item
        if current:
            name = current.strip().strip('{}"\' ')
            if name and len(name) >= 2 and not name.startswith('\\'):
                names.append(name)

        # Deduplicate (case-insensitive)
        seen = set()
        cleaned = []
        for name in names:
            name_lower = name.lower()
            if name_lower not in seen:
                seen.add(name_lower)
                cleaned.append(name)

        return cleaned if cleaned else []

    except Exception as e:
        print(f"   ⚠️ Parsing error: {e}")
        return None


def detect_dlc_suffix(game_name: str) -> bool:
    """Detect if a game name has a DLC/skin/costume suffix."""
    # Keep complete editions
    if re.search(
        r'\b(GOTY|Game of the Year|Complete|Definitive|Ultimate|Remastered)\s+Edition\b',
        game_name,
            re.IGNORECASE):
        return False

    dlc_patterns = [
        r'\s+-\s+\d{4}\s+Movie\s+.*\s+Skin$',  # "- 2008 Movie Batman Skin"
        r'\s+-\s+.*\s+Skin$',                   # "- Batman Skin"
        r'\s+-\s+.*\s+DLC$',                    # "- Season Pass DLC"
        r'\s+-\s+.*\s+Pack$',                   # "- Weapon Pack"
        r'\s+-\s+.*\s+Costume$',                # "- Red Costume"
        r'\s+-\s+.*\s+Bundle$',                 # "- Starter Bundle"
    ]

    for pattern in dlc_patterns:
        if re.search(pattern, game_name, re.IGNORECASE):
            return True

    return False


def extract_base_game_name(game_name: str) -> str:
    """Extract base game name by removing DLC suffix."""
    # Remove DLC suffix patterns
    base_name = re.sub(r'\s+-\s+\d{4}\s+Movie\s+.*\s+Skin$', '', game_name, flags=re.IGNORECASE)
    base_name = re.sub(r'\s+-\s+.*\s+(?:Skin|DLC|Pack|Costume|Bundle)$', '', base_name, flags=re.IGNORECASE)

    return base_name.strip()


def detect_non_game_title(title: str, alternative_names: List[str]) -> Tuple[bool, str]:
    """
    Detect if a title is actually a stream description, not a game.

    Returns: (is_non_game, reason)
    """
    title_lower = title.lower()

    # Pattern 1: Special event streams with heavy formatting
    event_patterns = [
        r'\*\*.*stream\*\*',           # **BIRTHDAY STREAM**
        r'\*\*.*\*\*',                  # **ANY HEAVILY DECORATED TEXT**
    ]

    for pattern in event_patterns:
        if re.search(pattern, title, re.IGNORECASE):  # Use original case for ** detection
            return True, f"Event stream pattern: {pattern}"

    # Pattern 2: Achievement/trophy hunting (not game names)
    achievement_patterns = [
        r'^platinum\s+(?:push|hunt|trophy)',  # Platinum Push
        r'^(?:trophy|achievement)\s+hunt',     # Trophy Hunt
        r'^100%\s+completion',                 # 100% Completion
    ]

    for pattern in achievement_patterns:
        if re.search(pattern, title_lower):
            return True, f"Achievement hunting pattern: {pattern}"

    # Pattern 3: Generic Twitch categories (not actual games)
    generic_titles = [
        'just chatting',
        'music',
        'art',
        'talk shows',
        'special events',
    ]

    if title_lower in generic_titles:
        return True, f"Generic Twitch category"

    # REMOVED: "Very short title with no alternative names" pattern
    # This was flagging legitimate games like "Far Cry 6"

    return False, ""


async def cleanup_alternative_names(db, dry_run: bool = True) -> Dict[str, Any]:
    """Fix malformed alternative names in the database."""
    print("\n" + "=" * 80)
    print("ISSUE 1: Fixing Malformed Alternative Names")
    print("=" * 80 + "\n")

    stats = {
        'total_checked': 0,
        'malformed_found': 0,
        'fixed': 0,
        'skipped': 0,
        'errors': []
    }

    # Get all games
    games = db.get_all_played_games()
    stats['total_checked'] = len(games)

    for game in games:
        try:
            alt_names_raw = game.get('alternative_names')
            game_id = game['id']
            canonical_name = game['canonical_name']

            # Skip if already clean
            if is_already_clean(alt_names_raw):
                continue

            # Check if malformed (contains braces, nested quotes, or backslashes)
            if isinstance(
                    alt_names_raw, str) and (
                    '{' in alt_names_raw or '"' in alt_names_raw or '\\' in alt_names_raw):
                # Try to parse
                cleaned_names = parse_malformed_alternative_names(alt_names_raw)

                if cleaned_names is None:
                    # Parsing failed
                    stats['skipped'] += 1
                    print(f"⚠️ Skipped: {canonical_name}")
                    print(f"   Could not reliably parse: {alt_names_raw[:100]}...")
                    print()
                    continue

                # Validate that cleaned version is actually better
                if len(cleaned_names) == 0 and alt_names_raw not in ['{}', '[]', '']:
                    # Cleaning resulted in empty list from non-empty input - probably bad
                    stats['skipped'] += 1
                    print(f"⚠️ Skipped: {canonical_name}")
                    print(f"   Cleaning would lose data: {alt_names_raw[:100]}...")
                    print()
                    continue

                stats['malformed_found'] += 1

                print(f"🔧 Malformed: {canonical_name}")
                print(f"   Raw: {alt_names_raw[:100]}...")
                print(f"   Cleaned to: {cleaned_names}")

                if not dry_run:
                    # Update database with cleaned list
                    success = db.update_played_game(game_id, alternative_names=cleaned_names)
                    if success:
                        stats['fixed'] += 1
                        print(f"   ✅ Fixed")
                    else:
                        print(f"   ❌ Failed to update")
                        stats['errors'].append(f"{canonical_name}: Update failed")
                else:
                    print(f"   🔍 DRY RUN - Would fix")

                print()

        except Exception as e:
            stats['errors'].append(f"{game.get('canonical_name', 'Unknown')}: {str(e)}")
            print(f"❌ Error processing {game.get('canonical_name')}: {e}\n")

    print(f"\n📊 Summary:")
    print(f"   Total checked: {stats['total_checked']}")
    print(f"   Malformed found: {stats['malformed_found']}")
    print(f"   Fixed: {stats['fixed']}")
    print(f"   Skipped: {stats['skipped']}")
    print(f"   Errors: {len(stats['errors'])}")

    return stats


async def cleanup_wrong_igdb_matches(db, dry_run: bool = True) -> Dict[str, Any]:
    """Re-validate games with suspicious alternative names."""
    print("\n" + "=" * 80)
    print("ISSUE 2: Fixing Wrong IGDB Matches")
    print("=" * 80 + "\n")

    # Check if IGDB is configured
    try:
        test_result = await igdb.validate_and_enrich("Test")
        igdb_available = test_result.get('confidence', 0) >= 0 or 'error' not in test_result
    except Exception as e:
        igdb_available = False
        print(f"⚠️ IGDB not available: {e}")
        print("   Skipping IGDB validation step\n")
        return {
            'total_checked': 0,
            'suspicious_found': 0,
            'revalidated': 0,
            'fixed': 0,
            'errors': ['IGDB not configured']
        }

    stats = {
        'total_checked': 0,
        'suspicious_found': 0,
        'revalidated': 0,
        'fixed': 0,
        'errors': []
    }

    games = db.get_all_played_games()
    stats['total_checked'] = len(games)

    for game in games:
        try:
            canonical_name = game['canonical_name']
            alt_names = game.get('alternative_names', [])
            game_id = game['id']
            release_year = game.get('release_year')

            # Suspicious patterns:
            # Check if alternative names mention different numbered entries
            # e.g., "God of War (2018)" with "God of War 2" in alternatives
            is_suspicious = False
            reason = ""

            if release_year and alt_names:
                base_name = re.sub(r'\s+\d+$', '', canonical_name).strip()
                base_name = re.sub(r'\s*:\s*.*$', '', base_name).strip()  # Remove subtitle

                for alt in alt_names:
                    # Check for conflicting numbers
                    canonical_numbers = re.findall(r'\b\d+\b', canonical_name)
                    alt_numbers = re.findall(r'\b\d+\b', alt)

                    if canonical_numbers and alt_numbers:
                        if canonical_numbers != alt_numbers and base_name.lower() in alt.lower():
                            is_suspicious = True
                            reason = f"Conflicting game numbers: '{alt}' doesn't match '{canonical_name}'"
                            break

            if is_suspicious:
                stats['suspicious_found'] += 1
                print(f"🔍 Suspicious: {canonical_name}")
                print(f"   Reason: {reason}")
                print(f"   Current alternatives: {alt_names}")

                # Re-validate with IGDB
                print(f"   Re-validating with IGDB...")
                igdb_result = await igdb.validate_and_enrich(canonical_name)

                stats['revalidated'] += 1

                new_canonical = igdb_result.get('canonical_name', canonical_name)
                new_alt_names = igdb_result.get('alternative_names', [])
                confidence = igdb_result.get('confidence', 0.0)

                print(f"   IGDB result: '{new_canonical}' (confidence: {confidence:.2f})")
                print(f"   New alternatives: {new_alt_names}")

                if confidence >= 0.75 and (new_canonical != canonical_name or new_alt_names != alt_names):
                    if not dry_run:
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

                        success = db.update_played_game(game_id, **updates)
                        if success:
                            stats['fixed'] += 1
                            print(f"   ✅ Updated")
                        else:
                            print(f"   ❌ Failed to update")
                    else:
                        print(f"   🔍 DRY RUN - Would update")
                        stats['fixed'] += 1
                else:
                    print(f"   ⚠️ Low confidence or no changes needed")

                print()

        except Exception as e:
            stats['errors'].append(f"{game.get('canonical_name', 'Unknown')}: {str(e)}")
            print(f"❌ Error processing {game.get('canonical_name')}: {e}\n")

    print(f"\n📊 Summary:")
    print(f"   Total checked: {stats['total_checked']}")
    print(f"   Suspicious found: {stats['suspicious_found']}")
    print(f"   Revalidated: {stats['revalidated']}")
    print(f"   Fixed: {stats['fixed']}")
    print(f"   Errors: {len(stats['errors'])}")

    return stats


async def cleanup_non_game_titles(db, dry_run: bool = True) -> Dict[str, Any]:
    """Remove entries that are stream descriptions, not games."""
    print("\n" + "=" * 80)
    print("ISSUE 3: Removing Non-Game Twitch Titles")
    print("=" * 80 + "\n")

    stats = {
        'total_checked': 0,
        'non_games_found': 0,
        'removed': 0,
        'errors': []
    }

    games = db.get_all_played_games()
    stats['total_checked'] = len(games)

    for game in games:
        try:
            canonical_name = game['canonical_name']
            alt_names = game.get('alternative_names', [])
            game_id = game['id']
            confidence = game.get('data_confidence', 1.0)

            # Check if this is a non-game title
            is_non_game, reason = detect_non_game_title(canonical_name, alt_names)

            # Also check very low confidence (but not missing confidence)
            if not is_non_game and confidence is not None and confidence < 0.2:
                is_non_game = True
                reason = f"Very low confidence: {confidence:.2f}"

            if is_non_game:
                stats['non_games_found'] += 1
                print(f"🗑️  Non-game detected: {canonical_name}")
                print(f"   Reason: {reason}")
                print(f"   Alternatives: {alt_names}")
                print(f"   Confidence: {confidence}")

                if not dry_run:
                    removed = db.remove_played_game(game_id)
                    if removed:
                        stats['removed'] += 1
                        print(f"   ✅ Removed")
                    else:
                        print(f"   ❌ Failed to remove")
                else:
                    print(f"   🔍 DRY RUN - Would remove")
                    stats['removed'] += 1

                print()

        except Exception as e:
            stats['errors'].append(f"{game.get('canonical_name', 'Unknown')}: {str(e)}")
            print(f"❌ Error processing {game.get('canonical_name')}: {e}\n")

    print(f"\n📊 Summary:")
    print(f"   Total checked: {stats['total_checked']}")
    print(f"   Non-games found: {stats['non_games_found']}")
    print(f"   Removed: {stats['removed']}")
    print(f"   Errors: {len(stats['errors'])}")

    return stats


async def cleanup_dlc_suffixes(db, dry_run: bool = True) -> Dict[str, Any]:
    """Remove DLC/skin suffixes from game names."""
    print("\n" + "=" * 80)
    print("ISSUE 4: Cleaning DLC/Skin Suffixes")
    print("=" * 80 + "\n")

    # Check if IGDB is configured
    try:
        test_result = await igdb.validate_and_enrich("Test")
        igdb_available = test_result.get('confidence', 0) >= 0 or 'error' not in test_result
    except Exception as e:
        igdb_available = False
        print(f"⚠️ IGDB not available: {e}")
        print("   DLC cleanup requires IGDB validation - skipping\n")
        return {
            'total_checked': 0,
            'dlc_found': 0,
            'fixed': 0,
            'errors': ['IGDB not configured']
        }

    stats = {
        'total_checked': 0,
        'dlc_found': 0,
        'fixed': 0,
        'errors': []
    }

    games = db.get_all_played_games()
    stats['total_checked'] = len(games)

    for game in games:
        try:
            canonical_name = game['canonical_name']
            game_id = game['id']

            if detect_dlc_suffix(canonical_name):
                stats['dlc_found'] += 1

                base_name = extract_base_game_name(canonical_name)

                print(f"🎯 DLC detected: {canonical_name}")
                print(f"   Base game: {base_name}")

                # Re-validate base game with IGDB
                print(f"   Validating base game with IGDB...")
                igdb_result = await igdb.validate_and_enrich(base_name)

                new_canonical = igdb_result.get('canonical_name', base_name)
                confidence = igdb_result.get('confidence', 0.0)

                print(f"   IGDB result: '{new_canonical}' (confidence: {confidence:.2f})")

                if confidence >= 0.7:
                    if not dry_run:
                        updates = {
                            'canonical_name': new_canonical,
                            'alternative_names': igdb_result.get('alternative_names', []),
                            'genre': igdb_result.get('genre'),
                            'series_name': igdb_result.get('series_name'),
                            'release_year': igdb_result.get('release_year'),
                            'igdb_id': igdb_result.get('igdb_id'),
                            'data_confidence': confidence
                        }

                        # Remove None values
                        updates = {k: v for k, v in updates.items() if v is not None}

                        success = db.update_played_game(game_id, **updates)
                        if success:
                            stats['fixed'] += 1
                            print(f"   ✅ Updated to base game")
                        else:
                            print(f"   ❌ Failed to update")
                    else:
                        print(f"   🔍 DRY RUN - Would update")
                        stats['fixed'] += 1
                else:
                    print(f"   ⚠️ Low confidence, keeping as-is")

                print()

        except Exception as e:
            stats['errors'].append(f"{game.get('canonical_name', 'Unknown')}: {str(e)}")
            print(f"❌ Error processing {game.get('canonical_name')}: {e}\n")

    print(f"\n📊 Summary:")
    print(f"   Total checked: {stats['total_checked']}")
    print(f"   DLC/skins found: {stats['dlc_found']}")
    print(f"   Fixed: {stats['fixed']}")
    print(f"   Errors: {len(stats['errors'])}")

    return stats


async def main():
    """Main cleanup function."""
    import argparse

    parser = argparse.ArgumentParser(description='Comprehensive data cleanup for played games')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying them')
    parser.add_argument('--skip-alt-names', action='store_true', help='Skip alternative names cleanup')
    parser.add_argument('--skip-igdb', action='store_true', help='Skip IGDB validation')
    parser.add_argument('--skip-non-games', action='store_true', help='Skip non-game removal')
    parser.add_argument('--skip-dlc', action='store_true', help='Skip DLC suffix cleanup')

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("COMPREHENSIVE DATA CLEANUP SCRIPT")
    print("=" * 80)
    print(f"\nMode: {'🔍 DRY RUN (no changes will be made)' if args.dry_run else '✍️  LIVE MODE (changes will be applied)'}\n")

    if not args.dry_run:
        confirm = input("⚠️  Are you sure you want to apply changes? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return

    db = get_database()

    all_stats = {}

    # Issue 1: Fix alternative names
    if not args.skip_alt_names:
        all_stats['alt_names'] = await cleanup_alternative_names(db, args.dry_run)

    # Issue 2: Fix wrong IGDB matches
    if not args.skip_igdb:
        all_stats['igdb'] = await cleanup_wrong_igdb_matches(db, args.dry_run)

    # Issue 3: Remove non-game titles
    if not args.skip_non_games:
        all_stats['non_games'] = await cleanup_non_game_titles(db, args.dry_run)

    # Issue 4: Clean DLC suffixes
    if not args.skip_dlc:
        all_stats['dlc'] = await cleanup_dlc_suffixes(db, args.dry_run)

    # Final summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80 + "\n")

    for issue, stats in all_stats.items():
        print(f"{issue.upper()}:")
        print(f"  Fixed: {stats.get('fixed', 0)}")
        print(f"  Errors: {len(stats.get('errors', []))}")

    print(f"\n{'🔍 DRY RUN COMPLETE - No changes were made' if args.dry_run else '✅ CLEANUP COMPLETE'}")
    print("\nRecommendation: Run with --dry-run first to preview changes!")


if __name__ == "__main__":
    asyncio.run(main())
