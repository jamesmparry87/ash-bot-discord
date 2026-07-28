import asyncio
import json
import uuid
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Dict, Optional, cast
from zoneinfo import ZoneInfo

import discord
from discord.ext import tasks

from ..config import (
    CHIT_CHAT_CHANNEL_ID,
    GAME_RECOMMENDATION_CHANNEL_ID,
    GUILD_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    MEMBERS_CHANNEL_ID,
    POPS_ARCADE_USER_ID,
)
from ..database import get_database
from ..handlers.ai_handler import call_ai_with_rate_limiting, filter_ai_response
from ..persona.sarcasm import apply_pops_arcade_sarcasm

try:
    from ..utils.data_quality import GameDataValidator
    DATA_QUALITY_AVAILABLE = True
except ImportError:
    DATA_QUALITY_AVAILABLE = False
    GameDataValidator = None

try:
    from ..integrations.twitch import detect_multiple_games_in_title
    from ..integrations.twitch import extract_game_name_from_title as extract_game_from_twitch
    from ..integrations.twitch import fetch_new_vods_since
    from ..integrations.youtube import fetch_playlist_based_content_since
except ImportError:
    detect_multiple_games_in_title = None
    extract_game_from_twitch = None
    fetch_new_vods_since = None
    fetch_playlist_based_content_since = None

try:
    from ..handlers.conversation_handler import notify_jam_weekly_message_failure, start_weekly_announcement_approval
except ImportError:
    notify_jam_weekly_message_failure = None
    start_weekly_announcement_approval = None

from ..database import get_database
from .utils import _should_run_automated_tasks, get_bot_instance

db = get_database()


async def monday_content_sync():
    """Syncs new content and generates a debrief for approval."""
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 0:
        return

    print("🔄 SYNC & DEBRIEF (Monday): Starting weekly content sync...")

    if not db:
        print("❌ SYNC & DEBRIEF (Monday): Database not available")
        await notify_jam_weekly_message_failure(
            'monday',
            'Database unavailable',
            'The database connection is not available. Cannot proceed with content sync.'
        )
        return

    try:
        # Always use exactly 7 days for Monday greeting (matches "168-hour operational cycle" message)
        start_sync_time = uk_now - timedelta(days=7)

        # Ensure timezone-aware
        if start_sync_time.tzinfo is None:
            start_sync_time = start_sync_time.replace(tzinfo=ZoneInfo("Europe/London"))

        print(
            f"🔄 SYNC & DEBRIEF (Monday): Using fixed 7-day window from {start_sync_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # Perform content sync with retry logic
        max_retries = 3
        analysis_results = None
        last_error = None

        for attempt in range(max_retries):
            try:
                print(f"🔄 SYNC & DEBRIEF (Monday): Attempt {attempt + 1}/{max_retries}...")
                analysis_results = await perform_full_content_sync(start_sync_time, is_scheduled=True)
                break  # Success!
            except Exception as sync_error:
                last_error = sync_error
                print(f"⚠️ SYNC & DEBRIEF (Monday): Attempt {attempt + 1} failed: {sync_error}")
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 60  # 1 min, 2 min, etc.
                    print(f"⏳ Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)

        if not analysis_results:
            print(f"❌ SYNC & DEBRIEF (Monday): All sync attempts failed. Last error: {last_error}")
            await notify_jam_weekly_message_failure(
                'monday',
                'YouTube/Twitch integration failure',
                f'Failed to fetch new content after {max_retries} attempts. Last error: {str(last_error)[:200]}'
            )
            return

        if analysis_results.get("status") == "no_new_content":
            print("✅ SYNC & DEBRIEF (Monday): No new content found. No message to generate.")
            await notify_jam_weekly_message_failure(
                'monday',
                'No new content found',
                'No new YouTube/Twitch content was found for the past week. No message will be generated.'
            )
            return

        import random
        intros = [
            "Analysis of the previous 168-hour operational cycle is complete.",
            "I have compiled the latest broadcast analytics for the crew's review.",
            "Data ingestion complete. The weekend's media transmissions have been cataloged.",
            "Good morning. The weekly content synchronization protocol has finished processing."
        ]

        # --- Content Generation ---
        debrief = (
            f"🌅 **Monday Morning Protocol Initiated**\n\n"
            f"{random.choice(intros)} **{analysis_results.get('new_content_count', 0)}** new transmissions were logged, "
            f"accumulating **{analysis_results.get('new_hours', 0)} hours** of new mission data and **{analysis_results.get('new_views', 0):,}** viewer engagements.")

        # Add completion status announcements
        completed_games = analysis_results.get('completed_games', [])
        if completed_games:
            debrief += "\n\n🎯 **Mission Completion Detected:**\n> "
            completions = []
            for game in completed_games:
                completions.append(f"**{game['series_name']}** - All {game['total_episodes']} episodes archived ({game['total_playtime_hours']}h total)")
            debrief += "\n> ".join(completions) + "\n> \n> *Mission parameters fulfilled.*"

        top_video = analysis_results.get("top_video")
        if top_video:
            debrief += f"\n\nMaximum engagement was recorded on the transmission titled **'{top_video['title']}'**."
            if "finale" in top_video['title'].lower() or "ending" in top_video['title'].lower():
                debrief += " This concludes all active mission parameters for this series."

        # --- Approval Workflow ---
        announcement_id = db.create_weekly_announcement('monday', debrief, analysis_results)

        if announcement_id:
            await start_weekly_announcement_approval(announcement_id, debrief, 'monday')
        else:
            print("❌ SYNC & DEBRIEF (Monday): Failed to create announcement record in database.")
            await notify_jam_weekly_message_failure(
                'monday',
                'Database insertion failure',
                'Failed to create the announcement record in the database.'
            )

    except Exception as e:
        print(f"❌ SYNC & DEBRIEF (Monday): Critical error during sync: {e}")
        await notify_jam_weekly_message_failure(
            'monday',
            'Unexpected error',
            f'An unexpected error occurred during the Monday content sync: {str(e)[:200]}'
        )


def clean_series_name(series_name: str) -> str:
    """Remove completion markers from series names"""
    import re
    if not series_name:
        return series_name

    # Remove (Completed), [Completed], (completed), [completed] patterns
    cleaned = re.sub(r'\s*[\(\[]completed[\)\]]\s*', '', series_name, flags=re.IGNORECASE)
    return cleaned.strip()


def map_genre_to_standard(igdb_genre: str) -> str:
    """Map IGDB genre to standardized genre list"""
    from ..config import DEFAULT_GENRE, STANDARD_GENRES

    if not igdb_genre:
        return DEFAULT_GENRE

    # Try direct match first (case-insensitive)
    genre_lower = igdb_genre.lower().strip()
    if genre_lower in STANDARD_GENRES:
        return STANDARD_GENRES[genre_lower]

    # Return default if no match
    return DEFAULT_GENRE


async def perform_full_content_sync(start_sync_time: datetime, is_scheduled: bool = False) -> Dict[str, Any]:
    """
    Performs a full sync of new content from YouTube and Twitch with IGDB enrichment.

    This function:
    - Fetches playlists from YouTube with new content since start_sync_time
    - Fetches VODs from Twitch since start_sync_time
    - Validates/enriches game data with IGDB API
    - Cleans series names (removes completion markers)
    - Maps genres to standardized list
    - Ensures all fields are properly populated
    - Updates or adds games to the database with full metadata
    - Deduplicates and aggregates statistics
    - Returns analysis dictionary for Monday morning message

    Args:
        start_sync_time: Start time for content sync window
        is_scheduled: True if called from automated scheduled task (enables longer manual input timeout)
    """
    if not db:
        raise RuntimeError("Database not available for sync.")

    print(f"🔄 SYNC: Fetching new content since {start_sync_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize staging table (auto-creates if not exists)
    db.games.create_staging_table_if_not_exists()

    # Generate unique session ID for this sync
    sync_session_id = str(uuid.uuid4())
    print(f"🔄 SYNC: Starting sync session {sync_session_id}")

    # Import IGDB integration
    try:
        from ..integrations.igdb import should_use_igdb_data, validate_and_enrich
        igdb_available = True
        print("✅ SYNC: IGDB integration available for data enrichment")
    except ImportError:
        igdb_available = False
        print("⚠️ SYNC: IGDB integration not available, proceeding without enrichment")
        # Define stub functions for type safety

        async def validate_and_enrich(game_name: str) -> Dict[str, Any]:
            return {'match_found': False}

        def should_use_igdb_data(confidence: float) -> bool:
            return False

    # --- Data Gathering: YouTube playlists ---
    playlist_games = []
    try:
        playlist_games = await fetch_playlist_based_content_since(
            "UCPoUxLHeTnE9SUDAkqfJzDQ",  # Jonesy's channel
            start_sync_time
        )

        print(f"🔄 SYNC: Found {len(playlist_games)} game playlists with new content (YouTube)")

    except Exception as fetch_error:
        print(f"❌ SYNC: Failed to fetch YouTube playlist-based content: {fetch_error}")

    # --- Data Gathering: Twitch VODs ---
    twitch_vods = []
    try:
        twitch_vods = await fetch_new_vods_since("jonesyspacecat", start_sync_time)
        print(f"🔄 SYNC: Found {len(twitch_vods)} new Twitch VODs")
    except Exception as twitch_error:
        print(f"❌ SYNC: Failed to fetch Twitch VODs: {twitch_error}")

    # Check if we have any content
    if not playlist_games and not twitch_vods:
        return {"status": "no_new_content"}

    # --- Performance Optimization: Pre-fetch all games ---
    print("🔄 SYNC: Building in-memory game cache to prevent N+1 queries...")
    all_played_games = db.get_all_played_games()
    
    # Create exact and normalized indices for lightning fast O(1) lookups
    import string
    
    def normalize_name(name):
        return name.lower().translate(str.maketrans('', '', string.punctuation)).replace(' ', '')
        
    game_cache_exact = {}
    game_cache_normalized = {}
    game_cache_alt = {}
    
    for game in all_played_games:
        canonical = game.get('canonical_name', '')
        if not canonical:
            continue
            
        exact_lower = canonical.lower().strip()
        norm = normalize_name(canonical)
        
        game_cache_exact[exact_lower] = game
        game_cache_normalized[norm] = game
        
        alt_names_raw = game.get('alternative_names', [])
        if isinstance(alt_names_raw, str):
            import json
            try:
                alt_names = json.loads(alt_names_raw) if alt_names_raw else []
            except (json.JSONDecodeError, TypeError):
                alt_names = [n.strip() for n in alt_names_raw.split(',') if n.strip()]
        else:
            alt_names = alt_names_raw or []
            
        for alt in alt_names:
            game_cache_alt[alt.lower().strip()] = game

    def find_game_in_cache(name: str):
        if not name:
            return None
            
        name_lower = name.lower().strip()
        name_norm = normalize_name(name)
        
        # 1. Exact canonical
        if name_lower in game_cache_exact:
            return game_cache_exact[name_lower]
            
        # 2. Normalized canonical
        if name_norm in game_cache_normalized:
            return game_cache_normalized[name_norm]
            
        # 3. Exact alternative
        if name_lower in game_cache_alt:
            return game_cache_alt[name_lower]
            
        # 4. Normalized alternative
        for alt_lower, game in game_cache_alt.items():
            if normalize_name(alt_lower) == name_norm:
                return game
                
        return None

    # --- Processing with Complete Metadata ---
    new_views = 0
    total_new_minutes = 0
    actual_new_minutes = 0  # True delta
    actual_new_episodes = 0 # True delta
    most_engaging_video = None
    games_added = 0
    games_updated = 0
    completed_games = []  # Track games that changed to 'completed'

    # Process YouTube playlist games
    for game_data in playlist_games:
        try:
            # Check if this playlist has been previously skipped
            playlist_url = game_data.get('youtube_playlist_url', '')
            if playlist_url and db and db.games.is_vod_skipped(playlist_url):
                canonical_name = game_data.get('canonical_name', 'Unknown')
                print(f"⏭️ SYNC: Skipping previously ignored YouTube playlist: {canonical_name}")
                continue

            # Normalize data before processing (if available)
            if DATA_QUALITY_AVAILABLE and GameDataValidator:
                game_data = GameDataValidator.normalize_game_data(game_data)

                # Validate data quality
                is_valid, errors = GameDataValidator.validate_game_data(game_data)
                if not is_valid:
                    print(
                        f"⚠️ SYNC: Data validation errors for '{game_data.get('canonical_name', 'Unknown')}': {errors}")
                    continue

            canonical_name = game_data['canonical_name']
            series_name = game_data.get('series_name', canonical_name)
            completion_status = game_data.get('completion_status', 'in_progress')

            print(f"✅ SYNC: Processing '{canonical_name}' ({completion_status})")

            # IGDB Enrichment - validate and enrich game data
            # Skip if this is an existing game whose metadata is already complete (saves API quota)
            _existing_for_igdb = find_game_in_cache(canonical_name)
            _igdb_metadata_complete = bool(
                _existing_for_igdb and
                _existing_for_igdb.get('genre') and
                _existing_for_igdb.get('release_year') and
                _existing_for_igdb.get('alternative_names')
            )
            if _igdb_metadata_complete:
                print(f"⏭️ SYNC: Skipping IGDB for '{canonical_name}' - metadata already complete")
            if igdb_available and not _igdb_metadata_complete:
                try:
                    print(f"🔍 SYNC: Querying IGDB for '{canonical_name}'...")
                    igdb_data = await validate_and_enrich(canonical_name)

                    if igdb_data and igdb_data.get('match_found'):
                        confidence = igdb_data.get('confidence', 0.0)
                        print(f"✅ SYNC: IGDB match found (confidence: {confidence:.2f})")

                        # Use IGDB data if confidence is high enough
                        if should_use_igdb_data(confidence):
                            # Update canonical name if IGDB provides better one
                            if igdb_data.get('canonical_name') and confidence >= 0.95:
                                canonical_name = igdb_data['canonical_name']
                                # ← FIX: Update game_data so approval shows IGDB name
                                game_data['canonical_name'] = canonical_name
                                print(f"📝 SYNC: Updated canonical name from IGDB: '{canonical_name}'")

                            # Enrich missing fields with IGDB data
                            if not game_data.get('genre') and igdb_data.get('genre'):
                                standardized_genre = map_genre_to_standard(igdb_data['genre'])
                                game_data['genre'] = standardized_genre
                                print(f"🎮 SYNC: Added genre from IGDB: {standardized_genre}")

                            if not game_data.get('release_year') and igdb_data.get('release_year'):
                                game_data['release_year'] = igdb_data['release_year']
                                print(f"📅 SYNC: Added release year from IGDB: {igdb_data['release_year']}")

                            # Merge alternative names (check exclusion flag first)
                            # Check if this game is excluded from IGDB enrichment
                            # Reuse the lookup already done above to avoid a second DB call
                            existing_game = _existing_for_igdb
                            skip_igdb = existing_game.get('skip_igdb_enrichment', False) if existing_game else False

                            if skip_igdb:
                                print(
                                    f"⏭️ SYNC: Skipping IGDB alternative names for '{canonical_name}' (user excluded)")
                            else:
                                existing_alt_names = existing_game.get('alternative_names', []) if existing_game else []
                                if isinstance(existing_alt_names, str):
                                    import json
                                    try:
                                        existing_alt_names = json.loads(existing_alt_names) if existing_alt_names else []
                                    except (json.JSONDecodeError, TypeError):
                                        existing_alt_names = [n.strip() for n in existing_alt_names.split(',') if n.strip()]
                                        
                                igdb_alt_names = igdb_data.get('alternative_names', [])
                                if igdb_alt_names or existing_alt_names:
                                    # Combine and deduplicate
                                    all_alt_names = list(set(existing_alt_names + igdb_alt_names))
                                    game_data['alternative_names'] = all_alt_names[:10]  # Limit to 10
                                    print(f"🔤 SYNC: Merged alternative names ({len(all_alt_names)} total)")

                            # Use IGDB series name if not present
                            if not series_name or series_name == canonical_name:
                                if igdb_data.get('series_name'):
                                    series_name = igdb_data['series_name']
                                    print(f"📚 SYNC: Added series from IGDB: '{series_name}'")
                        else:
                            print(f"⚠️ SYNC: IGDB confidence too low ({confidence:.2f}), keeping original data")
                            # Low-confidence games will be shown with ⚠️ warning in final approval summary
                    else:
                        print(f"ℹ️ SYNC: No IGDB match found for '{canonical_name}'")

                except Exception as igdb_error:
                    print(f"⚠️ SYNC: IGDB enrichment failed for '{canonical_name}': {igdb_error}")
                    # Continue with original data

            # Clean series name (remove completion markers)
            if series_name:
                cleaned_series = clean_series_name(series_name)
                if cleaned_series != series_name:
                    print(f"🧹 SYNC: Cleaned series name: '{series_name}' -> '{cleaned_series}'")
                    series_name = cleaned_series
                game_data['series_name'] = series_name

            # Ensure genre is standardized
            if game_data.get('genre'):
                standardized_genre = map_genre_to_standard(game_data['genre'])
                if standardized_genre != game_data['genre']:
                    print(f"🎯 SYNC: Standardized genre: '{game_data['genre']}' -> '{standardized_genre}'")
                    game_data['genre'] = standardized_genre

            # Aggregate views
            new_views += game_data.get('youtube_views', 0)

            # Check if game exists in database
            existing_game = find_game_in_cache(canonical_name)

            if existing_game:
                # Calculate true delta for reporting
                existing_episodes = existing_game.get('total_episodes', 0)
                existing_playtime = existing_game.get('total_playtime_minutes', 0)
                
                new_episodes = game_data.get('total_episodes', 0)
                new_playtime = game_data.get('total_playtime_minutes', 0)
                
                if new_episodes > existing_episodes:
                    actual_new_episodes += (new_episodes - existing_episodes)
                if new_playtime > existing_playtime:
                    actual_new_minutes += (new_playtime - existing_playtime)
                    
                # Detect completion status change
                old_status = existing_game.get('completion_status', 'in_progress')
                new_status = completion_status

                if old_status == 'in_progress' and new_status == 'completed':
                    completed_games.append({
                        'name': canonical_name,
                        'series_name': series_name,
                        'total_episodes': game_data.get('total_episodes', 0),
                        'total_playtime_hours': round(game_data.get('total_playtime_minutes', 0) / 60, 1)
                    })
                    print(
                        f"🎯 SYNC: Detected completion for '{canonical_name}' - {game_data.get('total_episodes', 0)} episodes")

                # FIXED: Only update dynamic stats, protect metadata fields
                existing_episodes = existing_game.get('total_episodes', 0)
                existing_playtime = existing_game.get('total_playtime_minutes', 0)
                
                new_episodes = game_data.get('total_episodes', 0)
                new_playtime = game_data.get('total_playtime_minutes', 0)
                
                # Check if we actually need to update this game
                needs_update = (
                    new_episodes > existing_episodes or
                    new_playtime > existing_playtime or
                    completion_status != old_status
                )
                
                if not needs_update:
                    print(f"⏭️ SYNC: Skipping '{canonical_name}' - no new episodes or playtime")
                    continue

                game_data['existing_episodes'] = existing_episodes
                
                update_params = {
                    'total_playtime_minutes': new_playtime,
                    'total_episodes': new_episodes,
                    'youtube_views': game_data.get('youtube_views', 0),
                    'youtube_playlist_url': game_data.get('youtube_playlist_url'),
                    'completion_status': completion_status,
                    'existing_episodes': existing_episodes
                }

                # PROTECTED FIELDS (never overwritten by sync):
                # ❌ alternative_names - Manually curated JSON data
                # ❌ series_name - Doesn't change over time
                # ❌ notes - Manually added annotations
                # ❌ first_played_date - Historical record

                # Stage update for approval
                db.games.stage_game_for_approval(
                    sync_session_id=sync_session_id,
                    game_data=game_data,
                    action_type='update',
                    confidence_score=1.0,  # High confidence for YouTube playlist data
                    source_platform='youtube'
                )
                print(
                    f"✅ SYNC: Staged update for '{canonical_name}' - {new_episodes} episodes, status: {completion_status}")
                games_updated += 1

            else:
                # Stage new game for approval
                
                # All episodes and minutes are considered "new" for a completely new game
                actual_new_episodes += game_data.get('total_episodes', 0)
                actual_new_minutes += game_data.get('total_playtime_minutes', 0)
                
                full_game_data = {
                    'canonical_name': canonical_name,
                    'series_name': series_name,
                    'total_playtime_minutes': game_data.get(
                        'total_playtime_minutes',
                        0),
                    'total_episodes': game_data.get(
                        'total_episodes',
                        0),
                    'youtube_views': game_data.get(
                        'youtube_views',
                        0),
                    'youtube_playlist_url': game_data.get('youtube_playlist_url'),
                    'completion_status': completion_status,
                    'alternative_names': game_data.get(
                        'alternative_names',
                        []),
                    'first_played_date': game_data.get('first_played_date'),
                    'notes': game_data.get(
                        'notes',
                        f"Auto-synced from YouTube on {datetime.now(ZoneInfo('Europe/London')).strftime('%Y-%m-%d')}")}

                db.games.stage_game_for_approval(
                    sync_session_id=sync_session_id,
                    game_data=full_game_data,
                    action_type='add',
                    confidence_score=1.0,  # High confidence for YouTube playlist data
                    source_platform='youtube'
                )
                print(
                    f"✅ SYNC: Staged new game '{canonical_name}' - {game_data.get('total_episodes', 0)} episodes, {game_data.get('youtube_views', 0):,} views")
                games_added += 1

        except Exception as game_error:
            print(f"⚠️ SYNC: Error processing game '{game_data.get('canonical_name', 'Unknown')}': {game_error}")
            continue

    # Process Twitch VODs with smart extraction and IGDB enrichment
    bot = get_bot_instance()
    skipped_vods = []  # Track VODs that couldn't be named this run (timed out or explicitly skipped)
    for vod in twitch_vods:
        try:
            title = vod['title']
            vod_url = vod.get('url', '')
            duration_minutes = vod.get('duration_seconds', 0) // 60
            view_count = vod.get('view_count', 0)  # NEW: Capture Twitch views from VOD

            # Phase 2.2: Check for multi-game streams.
            # _manual_game_name: if set by the DM below, single-game processing
            # uses it directly and skips smart_extract_with_validation.
            _manual_game_name = None
            try:
                potential_games = detect_multiple_games_in_title(title)

                if len(potential_games) >= 2:
                    print(f"🔍 SYNC: Ambiguous multi-game title — requesting manual confirmation")
                    print(f"   Detected candidates: {potential_games}")

                    from ..handlers.manual_game_input import request_manual_game_name

                    vod_data = {
                        'title': title,
                        'url': vod_url,
                        'source': 'twitch',
                        'extracted_name': ', '.join(potential_games),
                        'confidence': 0.5  # Force DM path; user decides which game to credit
                    }

                    multi_response = await request_manual_game_name(bot, vod_data, is_scheduled=is_scheduled)

                    if multi_response == "skip":
                        if db:
                            db.games.add_skipped_vod(vod_url, 'twitch', title, JAM_USER_ID)
                        skipped_vods.append({'title': title, 'url': vod_url, 'reason': 'skipped'})
                        print(f"⏭️ SYNC: User skipped ambiguous multi-game VOD: {title[:50]}")
                        continue
                    elif multi_response:
                        # Store name; fall through to single-game processing below (no continue)
                        _manual_game_name = multi_response
                        print(f"✅ SYNC: Manual name '{multi_response}' received for ambiguous multi-game VOD")
                    else:
                        # Timeout — offer again on next sync
                        skipped_vods.append({'title': title, 'url': vod_url, 'reason': 'timed_out'})
                        print(f"⏭️ SYNC: Multi-game DM timed out for: {title[:50]}")
                        continue

            except Exception as detection_error:
                print(f"⚠️ SYNC: Multi-game detection failed for '{title}': {detection_error}")
                # Fall through to normal single-game processing

            # Initialize variables early to avoid unbound variable errors (single-game processing)
            is_low_confidence = False
            confidence = 0.0

            # Check if VOD was previously skipped
            if vod_url and db and db.games.is_vod_skipped(vod_url):
                print(f"⏭️ SYNC: Skipping previously ignored VOD: {title[:50]}")
                continue

            if _manual_game_name:
                # Name provided via multi-game DM — skip extraction entirely
                game_name = _manual_game_name
                confidence = 1.0
                is_low_confidence = False
                print(f"✅ SYNC: Using manual name '{game_name}' (from multi-game DM, skipping extraction)")
            else:
                # Use smart extraction with IGDB validation (Phase 1.2) for single-game streams
                try:
                    from ..integrations.twitch import smart_extract_with_validation
                    extracted_name, confidence = await smart_extract_with_validation(title)

                    # Low confidence - request manual input
                    if not extracted_name or confidence < 0.65:
                        print(f"⚠️ SYNC: Low confidence ({confidence:.2f}) for Twitch title - requesting manual input")

                        from ..handlers.manual_game_input import request_manual_game_name

                        vod_data = {
                            'title': title,
                            'url': vod_url,
                            'source': 'twitch',
                            'extracted_name': extracted_name or '',
                            'confidence': confidence
                        }

                        # Request manual input (blocks until response)
                        manual_response = await request_manual_game_name(bot, vod_data, is_scheduled=is_scheduled)

                        if manual_response == "skip":
                            # Add to permanent skip list so it won't be offered again
                            if db:
                                db.games.add_skipped_vod(vod_url, 'twitch', title, JAM_USER_ID)
                            skipped_vods.append({'title': title, 'url': vod_url, 'reason': 'skipped'})
                            print(f"⏭️ User skipped VOD: {title[:50]}")
                            continue
                        elif manual_response:
                            # Use manual name
                            game_name = manual_response
                            confidence = 1.0  # High confidence for manual input
                            is_low_confidence = False
                            print(f"✅ SYNC: Using manual name '{game_name}' from user input")
                        else:
                            # Timeout - VOD not named this run; will be offered again on next sync
                            skipped_vods.append({'title': title, 'url': vod_url, 'reason': 'timed_out'})
                            print(f"⏭️ Manual input timed out - skipping: {title[:50]}")
                            continue
                    else:
                        # Good confidence - use extracted name
                        game_name = extracted_name
                        is_low_confidence = confidence < 0.85
                        print(
                            f"✅ SYNC: Extracted '{game_name}' from Twitch with {confidence:.2f} confidence{' (medium - review recommended)' if is_low_confidence else ''}")

                except ImportError:
                    # Fallback to basic extraction if smart extraction not available
                    print("⚠️ SYNC: Smart extraction not available, falling back to basic extraction")
                    game_name = extract_game_from_twitch(title)
                    confidence = 0.0
                    is_low_confidence = False  # Reset for fallback case

                    if not game_name:
                        print(f"⚠️ SYNC: Could not extract game from Twitch title: '{title}'")
                        continue

            print(f"✅ SYNC: Processing Twitch VOD '{game_name}'")

            duration_minutes = vod.get('duration_seconds', 0) // 60
            actual_new_minutes += duration_minutes
            actual_new_episodes += 1

            # FIX 4: Check if game exists in database (searches both canonical and alternative names)
            existing_game = find_game_in_cache(game_name)

            if existing_game:
                # FIX 4: Ensure extracted name is stored as alternative name if different from canonical
                canonical_name = existing_game.get('canonical_name', '')
                existing_alt_names = existing_game.get('alternative_names', [])

                # If extracted name differs from canonical and isn't already an alias, add it
                if game_name.lower() != canonical_name.lower():
                    if game_name not in existing_alt_names:
                        updated_alt_names = existing_alt_names + [game_name]
                        print(f"🔤 FIX 4: Adding '{game_name}' as alternative name for '{canonical_name}'")
                    else:
                        updated_alt_names = existing_alt_names
                else:
                    updated_alt_names = existing_alt_names

                # Stage single-game Twitch update (use DB canonical name, not extracted)
                update_data = {
                    'canonical_name': canonical_name,
                    'total_playtime_minutes': existing_game.get('total_playtime_minutes', 0) + duration_minutes,
                    'total_episodes': existing_game.get('total_episodes', 0) + 1,
                    'twitch_views': existing_game.get('twitch_views', 0) + view_count,
                    'alternative_names': updated_alt_names
                }
                if vod_url:
                    existing_vods = existing_game.get('twitch_vod_urls', [])
                    if isinstance(existing_vods, str):
                        existing_vods = [v.strip() for v in existing_vods.split(',') if v.strip()]
                    elif not isinstance(existing_vods, list):
                        existing_vods = []
                    if vod_url not in existing_vods:
                        existing_vods.append(vod_url)
                        update_data['twitch_vod_urls'] = existing_vods[-10:]
                        print(f"📎 SYNC: Added VOD URL to '{canonical_name}' ({len(existing_vods)} total)")

                db.games.stage_game_for_approval(
                    sync_session_id=sync_session_id,
                    game_data=update_data,
                    action_type='update',
                    confidence_score=confidence,
                    source_platform='twitch'
                )
                print(f"✅ SYNC: Staged Twitch update for '{game_name}' ({duration_minutes} mins, {view_count:,} views)")
                games_updated += 1

            else:
                # VOD URL deduplication: skip if this URL is already in the DB under another game name.
                # This prevents re-staging VODs that were manually named via !namevod on a previous sync.
                if vod_url:
                    _existing_owner = db.games.get_game_by_vod_url(vod_url)
                    if _existing_owner:
                        print(
                            f"⏭️ SYNC: Skipping '{game_name}' — VOD URL already recorded under '{_existing_owner['canonical_name']}'")
                        continue

                # Stage new Twitch game
                game_data = {
                    'canonical_name': game_name,
                    'series_name': game_name,
                    'total_playtime_minutes': duration_minutes,
                    'total_episodes': 1,
                    'youtube_views': 0,  # Explicit 0 for Twitch-only content (not NULL)
                    'twitch_views': view_count,
                    'first_played_date': vod['published_at'].date(),
                    'notes': f"Auto-synced from Twitch VOD on {datetime.now(ZoneInfo('Europe/London')).strftime('%Y-%m-%d')}"}

                if vod_url:
                    game_data['twitch_vod_urls'] = [vod_url]

                # IGDB enrichment for high-confidence matches
                if igdb_available and confidence >= 0.75:
                    try:
                        igdb_data = await validate_and_enrich(game_name)
                        if igdb_data and igdb_data.get('match_found'):
                            if igdb_data.get('genre'):
                                game_data['genre'] = map_genre_to_standard(igdb_data['genre'])
                            if igdb_data.get('release_year'):
                                game_data['release_year'] = igdb_data['release_year']
                            if igdb_data.get('series_name'):
                                game_data['series_name'] = igdb_data['series_name']
                            if igdb_data.get('alternative_names'):
                                game_data['alternative_names'] = igdb_data['alternative_names'][:5]
                    except Exception as igdb_error:
                        print(f"⚠️ SYNC: IGDB enrichment failed: {igdb_error}")

                db.games.stage_game_for_approval(
                    sync_session_id=sync_session_id,
                    game_data=game_data,
                    action_type='add',
                    confidence_score=confidence,
                    source_platform='twitch'
                )
                print(f"✅ SYNC: Staged new Twitch game '{game_name}' ({duration_minutes} mins)")
                games_added += 1

        except Exception as vod_error:
            print(f"⚠️ SYNC: Error processing Twitch VOD '{vod.get('title', 'Unknown')}': {vod_error}")
            continue

    # --- Get Staging Summary ---
    summary = db.games.get_staging_session_summary(sync_session_id)
    print(f"🔄 SYNC: Session {sync_session_id} complete - {summary['total_count']} games staged for approval")

    # --- Trigger Approval Conversation via Queue System ---
    from ..handlers.conversation_handler import add_to_approval_queue, process_next_approval

    if bot:
        try:
            # Add to approval queue with appropriate priority
            queue_position = add_to_approval_queue(
                item_type='sync_approval',
                data={'sync_session_id': sync_session_id, 'summary': summary},
                priority=6,  # Between weekly announcements (5) and trivia (5)
                source='monday_content_sync'
            )
            print(f"✅ SYNC: Added to approval queue at position {queue_position}")

            # Trigger queue processor
            await process_next_approval()
            print(f"✅ SYNC: Queue processor triggered for session {sync_session_id}")
        except Exception as conversation_error:
            print(f"❌ SYNC: Failed to queue approval conversation: {conversation_error}")
    else:
        print("❌ SYNC: Bot instance not available for approval conversation")

    # NOTE: Last sync timestamp will be updated AFTER approval in conversation_handler
    # This ensures timestamp only advances when changes are actually committed

    # --- Post-sync summary DM to JAM ---
    if bot and skipped_vods:
        try:
            user = await bot.fetch_user(JAM_USER_ID)
            if user:
                timed_out = [v for v in skipped_vods if v['reason'] == 'timed_out']
                explicitly_skipped = [v for v in skipped_vods if v['reason'] == 'skipped']

                dm_lines = [
                    f"📋 **Sync complete** — {summary['total_count']} game(s) staged for approval "
                    f"({games_added} new, {games_updated} updated)."
                ]

                if timed_out:
                    dm_lines.append(
                        f"\n⏱️ **{len(timed_out)} VOD(s) timed out** (no name provided — will be offered again next sync):"
                    )
                    for v in timed_out:
                        dm_lines.append(f"  • {v['title'][:80]}")

                if explicitly_skipped:
                    dm_lines.append(
                        f"\n⏭️ **{len(explicitly_skipped)} VOD(s) permanently skipped:**"
                    )
                    for v in explicitly_skipped:
                        dm_lines.append(f"  • {v['title'][:80]}")

                dm_lines.append(
                    "\n*Use `!namevod <url_or_id> <game name>` to retroactively name a timed-out VOD.*"
                )

                await user.send("\n".join(dm_lines))
                print(f"📬 SYNC: Post-sync summary DM sent to JAM ({len(skipped_vods)} skipped VOD(s) noted)")
        except Exception as dm_err:
            print(f"⚠️ SYNC: Could not send post-sync summary DM: {dm_err}")

    # --- Enhanced Reporting ---
    return {
        "status": "pending_approval",
        "sync_session_id": sync_session_id,
        "new_content_count": actual_new_episodes,
        "new_hours": round(actual_new_minutes / 60, 1),
        "new_views": new_views,
        "games_staged": summary['total_count'],
        "games_added": games_added,
        "games_updated": games_updated,
        "completed_games": completed_games,
        "skipped_vods": skipped_vods
    }
