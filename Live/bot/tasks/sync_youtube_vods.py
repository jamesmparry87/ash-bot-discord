import asyncio
import logging
from zoneinfo import ZoneInfo
from datetime import datetime
import discord

from ..config import YOUTUBE_VODS_CHANNEL_ID, JAM_USER_ID
from ..database import get_database
from ..integrations.youtube import fetch_vods_channel_recent_videos
from .utils import _should_run_automated_tasks, get_bot_instance

logger = logging.getLogger(__name__)

db = get_database()

async def sync_youtube_vods_channel():
    """
    Weekly standalone task to fetch videos from the VODs channel and
    update playtime for existing games or alert if the game isn't found.
    """
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    # Run on Monday (weekday 0)
    if uk_now.weekday() != 0:
        return

    print("🔄 VODS SYNC (Monday): Starting VODs channel sync...")

    if not db:
        print("❌ VODS SYNC: Database not available")
        return

    try:
        videos_data = await fetch_vods_channel_recent_videos(YOUTUBE_VODS_CHANNEL_ID)
        if not videos_data:
            print("⚠️ VODS SYNC: No data returned from VODs channel")
            return
            
        bot = get_bot_instance()

        for video in videos_data:
            canonical_name = video['canonical_name']
            playtime = video['playtime_minutes']
            is_completed = video['is_completed']
            title = video['title']

            game = db.get_played_game(canonical_name)
            
            if game:
                # Targeted playtime update bypasses standard merge logic
                success = db.games.update_vod_playtime(canonical_name, playtime, is_completed)
                if success:
                    print(f"✅ VODS SYNC: Updated '{canonical_name}' (Playtime: {playtime}m, Completed: {is_completed})")
            else:
                print(f"⚠️ VODS SYNC: Game '{canonical_name}' not found in DB. Alerting DecentJam...")
                
                # Alert JAM
                if bot and JAM_USER_ID:
                    try:
                        jam_user = bot.get_user(JAM_USER_ID) or await bot.fetch_user(JAM_USER_ID)
                        if jam_user:
                            embed = discord.Embed(
                                title="⚠️ Unmatched VOD Game Detected",
                                description=f"I found a new VOD on the VODs channel, but I don't have a matching database record for it.",
                                color=discord.Color.orange()
                            )
                            embed.add_field(name="Parsed Game Name", value=canonical_name, inline=False)
                            embed.add_field(name="VOD Title", value=title, inline=False)
                            embed.add_field(name="Action Required", value="Please verify the game name or ensure it exists in the database so I can link it up!", inline=False)
                            
                            await jam_user.send(embed=embed)
                    except Exception as alert_e:
                        print(f"❌ VODS SYNC: Failed to alert JAM: {alert_e}")

    except Exception as e:
        print(f"❌ VODS SYNC: Failed: {e}")
