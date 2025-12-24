#!/usr/bin/env python3
"""
Comprehensive Data Cleanup Script

Fixes 4 major data quality issues:
1. Malformed alternative names (JSON/array corruption)
2. Wrong IGDB matches (alternative names from wrong games)
3. Non-game Twitch titles (stream descriptions saved as games)
4. DLC/skin suffixes on game names

Run with: python3 Live/comprehensive_data_cleanup.py
"""

import asyncio
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from bot.database_module import get_database
from bot.integrations import igdb

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def parse_malformed_alternative_names(alt_names_field: Any) -> List[str]:
    """
    Parse alternative names from various formats including malformed ones.

    Handles:
    - Comma-separated strings: "name1,name2,name3"
    - PostgreSQL arrays: {"name1","name2","name3"}
    - Nested corruption: {Batman:AA,"{Batman:AA,\"Arkham Asylum\",B:AA}","Arkham Asylum",B:AA}
    - Empty/None values
    """
    if not alt_names_field:
        return []

    if not isinstance(alt_names_field, str):
        return []

    # Remove outer braces if present (PostgreSQL array syntax)
    text = alt_names_field.strip()
    if text.startswith('{') and text.endswith('}'):
        text = text[1:-1]

    # Try to extract all quoted strings
    quoted_pattern = r'"([^"]*)"'
    quoted_matches = re.findall(quoted_pattern, text)

    # Also get unquoted items (split by comma, but be careful)
    all_items = []

    # Add quoted items
    all_items.extend(quoted_matches)

    # Remove quoted sections from text and split remainder
    text_without_quotes = re.sub(quoted_pattern, '', text)
    unquoted_items = [item.strip() for item in text_without_quotes.split(',') if item.strip()]
    all_items.extend(unquoted_items)

    # Clean up items
    cleaned = []
    seen = set()

    for item in all_items:
        # Remove any remaining braces
        item = item.strip('{}').strip()

        # Skip empty or very short items
        if len(item) < 2:
            continue

        # Skip duplicates (case-insensitive)
        if item.lower() in seen:
            continue

        seen.add(item.lower())
        cleaned.append(item)

    return cleaned


def detect_dlc_suffix(game_name: str) -> bool:
    """Detect if a game name has a DLC/skin/costume suffix."""
    dlc_patterns = [
        r'\s+-\s+\d{4}\s+Movie\s+.*\s+Skin$',  # "- 2008 Movie Batman Skin"
        r'\s+-\s+.*\s+Skin$',                   # "- Batman Skin"
        r'\s+-\s+.*\s+DLC$',                    # "- Season Pass DLC"
        r'\s+-\s+.*\s+Pack$',                   # "- Weapon Pack"
        r'\s+-\s+.*\s+Costume$',                # "- Red Costume"
        r'\s+-\s+.*\s+Bundle$',                 # "- Starter Bundle"
        r'\s+-\s+.*\s+Edition$',                # "- Special Edition" (but keep GOTY, Complete, etc.)
    ]

    for pattern in dlc_patterns:
        if re.search(pattern, game_name, re.IGNORECASE):
            # Exception: Keep "GOTY Edition", "Complete Edition", "Definitive Edition"
            if re.search(r'(GOTY|Game of the Year|Complete|Definitive|Ultimate|Remastered)', game_name, re.IGNORECASE):
                return False
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

    # Pattern 1: Special event streams
    event_patterns = [
        r'\*\*.*stream\*\*',           # **BIRTHDAY STREAM**
        r'\bbirthday\b',                # Birthday
        r'\bmarathon\b',                # Marathon
        r'\bcharity\b',                 # Charity stream
        r'\bspecial\b.*\bevent\b',      # Special event
    ]

    for pattern in event_patterns:
        if re.search(pattern, title_lower):
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

    # Pattern 3: Generic activity descriptions
    generic_patterns = [
        r'^(?:just|some|random)\s+',     # Just Gaming, Some Games
        r'^variety\s+',                   # Variety Stream
        r'^chill\s+',                     # Chill Stream
    ]

    for pattern in generic_patterns:
        if re.search(pattern, title_lower):
            return True, f"Generic activity pattern: {pattern}"

    # Pattern 4: Empty or very poor alternative names (indicates bad extraction)
    if not alternative_names or len(alternative_names) == 0:
        # If title is short and has no alternative names, likely bad
        if len(title) < 10:
            return True, "Very short title with no alternative names"

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

            # Check if malformed (contains braces or nested quotes)
            if isinstance(alt_names_raw, str) and ('{' in alt_names_raw or '\"' in alt_names_raw):
                stats['malformed_found'] += 1

                print(f"🔧 Malformed: {canonical_name}")
                print(f"   Raw: {alt_names_raw[:100]}...")

                # Parse and clean
                cleaned_names = parse_malformed_alternative_names(alt_names_raw)

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
    print(f"   Errors: {len(stats['errors'])}")

    return stats


async def cleanup_wrong_igdb_matches(db, dry_run: bool = True) -> Dict[str, Any]:
    """Re-validate games with suspicious alternative names."""
    print("\n" + "=" * 80)
    print("ISSUE 2: Fixing Wrong IGDB Matches")
    print("=" * 80 + "\n")

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
            # 1. Empty alternative names
            # 2. Alternative names that don't match canonical name at all
            # 3. Alternative names for clearly different games

            is_suspicious = False
            reason = ""

            if not alt_names or len(alt_names) == 0:
                is_suspicious = True
                reason = "No alternative names"
            elif release_year and alt_names:
                # Check if alternative names mention different numbered entries
                # e.g., "God of War" with "God of War 2" in alternatives
                base_name = re.sub(r'\s+\d+$', '', canonical_name).strip()
                base_name = re.sub(r'\s*:\s*.*$', '', base_name).strip()  # Remove subtitle

                for alt in alt_names:
                    # Check for conflicting numbers
                    canonical_numbers = re.findall(r'\d+', canonical_name)
                    alt_numbers = re.findall(r'\d+', alt)

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

            # Also check low confidence
            if not is_non_game and confidence and confidence < 0.3:
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
