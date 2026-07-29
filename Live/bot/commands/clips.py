import asyncio
import json
import logging
import os
import re
import traceback
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import discord
from bot.config import JAM_USER_ID, JONESY_USER_ID
from bot.database import get_database
from bot.handlers.ai_handler import upload_and_analyze_media
from discord.ext import commands

logger = logging.getLogger(__name__)

TRIVIA_PROMPT = """
Watch this stream clip carefully. Analyse both the visual events in the game and the streamer's reaction and audio.
Return a strict JSON response with the following keys:
- "game_title": Name of the game being played (if recognizable, else "Unknown").
- "reaction": The streamer's exact reaction (e.g. screamed, rage quit, burst out laughing, fell off chair).
- "trigger": What happened in the game to cause this reaction.
- "lore_summary": A one-sentence trivia fact focused on the streamer's experience (e.g. "During a stream, Jonesy fell off the cliff after being startled by a chicken in Skyrim").
Ensure the response is ONLY valid JSON, without markdown formatting.
"""


def canonicalize_clip_url(url: str) -> str:
    """Strip tracking parameters to get a canonical clip URL for deduplication."""
    try:
        parsed = urlparse(url)

        # Specific logic for Twitch clips to handle both clips.twitch.tv and twitch.tv/streamer/clip formats
        if 'twitch.tv' in parsed.netloc:
            if 'clips.twitch.tv' in parsed.netloc:
                clip_id = parsed.path.strip('/')
                return f"https://clips.twitch.tv/{clip_id}".lower()
            elif '/clip/' in parsed.path:
                clip_id = parsed.path.split('/clip/')[-1].strip('/')
                return f"https://clips.twitch.tv/{clip_id}".lower()

        # Reconstruct without query parameters or fragments
        canonical = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
        return canonical.lower()
    except Exception:
        return url.lower()


class ClipParsingService:
    def __init__(self):
        self.db = get_database()

    def _download_video_sync(self, url: str, output_path: str) -> Optional[str]:
        """Synchronous yt-dlp download to be run in a thread."""
        import yt_dlp

        ydl_opts = {
            'outtmpl': output_path,
            # Fallback to /best[ext=mp4]/best because Twitch clips often don't have separate video/audio tracks
            'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore
                ydl.download([url])
            return output_path
        except Exception as e:
            logger.error(f"yt-dlp download failed for {url}: {e}")
            return None

    async def process_clip(self, url: str, message: discord.Message) -> bool:
        """Download, analyze, and save clip lore. Returns True on success."""
        canonical_url = canonicalize_clip_url(url)

        # Pre-flight check
        if self.db.trivia.clip_lore_exists(canonical_url):
            logger.info(f"Clip {canonical_url} already exists in Lore Compendium. Skipping.")
            return False

        file_id = f"clip_{message.id}"
        local_filename = f"temp/{file_id}.mp4"
        os.makedirs("temp", exist_ok=True)

        try:
            # 1. Download asynchronously
            print(f"📥 Downloading clip: {url}")
            download_result = await asyncio.to_thread(self._download_video_sync, url, local_filename)
            if not download_result or not os.path.exists(local_filename):
                raise RuntimeError(f"Failed to download video from {url}")

            # 2. Upload and analyze via ai_handler (handles polling and deletion)
            response_text, status = await upload_and_analyze_media(local_filename, TRIVIA_PROMPT)

            if not response_text or status != "success":
                raise RuntimeError(f"Gemini analysis failed: {status}")

            # 3. Parse JSON
            try:
                # Remove markdown formatting if Gemini included it
                clean_text = response_text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]

                data = json.loads(clean_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini JSON: {response_text}")
                raise RuntimeError(f"JSON Parse Error: {e}")

            # 4. Save to Database
            success = self.db.trivia.add_clip_lore(
                canonical_url=canonical_url,
                original_url=url,
                game_title=data.get("game_title", "Unknown"),
                reaction=data.get("reaction", ""),
                trigger=data.get("trigger", ""),
                lore_summary=data.get("lore_summary", ""),
                submitted_by=str(message.author.id),
                message_id=message.id
            )

            return success

        except Exception as e:
            logger.error(f"Error processing clip {url}: {e}")
            return False

        finally:
            # Clean up local temp file
            if os.path.exists(local_filename):
                try:
                    os.remove(local_filename)
                except Exception as e:
                    logger.error(f"Failed to delete temp file {local_filename}: {e}")


class ClipTriviaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.parser = ClipParsingService()
        self.target_channel_id = 1210874007591718982
        self.url_pattern = re.compile(
            r'https?://(?:www\.|clips\.)?(?:twitch\.tv|youtube\.com|youtu\.be)/\S+'
        )

        # Background worker queue
        self.clip_queue = asyncio.Queue()
        self.expected_batch_size = 0
        self.current_batch_processed = 0
        self.worker_task = self.bot.loop.create_task(self.process_queue())

    async def cog_unload(self):
        self.worker_task.cancel()

    async def process_queue(self):
        """Background worker to process clips sequentially with cooldown."""
        while True:
            try:
                # Wait for next clip in queue
                message, clip_url = await self.clip_queue.get()

                # If we are starting a batch and expected_batch_size is 0 (ad hoc mode without tracking)
                # this shouldn't happen with our updates, but fallback to 1
                if self.expected_batch_size == 0:
                    self.expected_batch_size = 1

                self.current_batch_processed += 1

                print(f"🎬 Processing clip from queue: {clip_url}")
                success = await self.parser.process_clip(clip_url, message)

                # Update reactions based on success
                try:
                    await message.remove_reaction("👀", self.bot.user)
                    if success:
                        await message.add_reaction("✅")
                    else:
                        await message.add_reaction("❌")
                except Exception:
                    pass

                # DM Jam with updates
                try:
                    jam_user = await self.bot.fetch_user(JAM_USER_ID)
                    if jam_user:
                        is_first = (self.current_batch_processed == 1)
                        is_last = (self.current_batch_processed == self.expected_batch_size)
                        is_single = (self.expected_batch_size == 1)

                        date_str = message.created_at.strftime("%Y-%m-%d")

                        if is_single or is_first or is_last:
                            # Full info
                            clip_details = None
                            if success:
                                canonical_url = canonicalize_clip_url(clip_url)
                                clip_details = get_database().trivia.get_clip_lore(canonical_url)

                            if success and clip_details:
                                title = clip_details.get('game_title', 'Unknown Game')
                                reaction = clip_details.get('reaction', 'Reaction')
                                msg = f"🔬 **Archive Update** [{self.current_batch_processed}/{self.expected_batch_size}]\n"
                                msg += f"I have processed the clip from {date_str}: **{title}**.\n"
                                msg += f"Observed reaction: *{reaction}*."
                            else:
                                msg = f"⚠️ **Archive Update** [{self.current_batch_processed}/{self.expected_batch_size}]\n"
                                msg += f"I attempted to process the clip from {date_str}, but the analysis failed."
                        else:
                            # Short info
                            if success:
                                msg = f"🔬 Processing... [{self.current_batch_processed}/{self.expected_batch_size}] (Success)"
                            else:
                                msg = f"⚠️ Processing... [{self.current_batch_processed}/{self.expected_batch_size}] (Failed)"

                        await jam_user.send(msg)
                except Exception as e:
                    logger.error(f"Failed to DM Jam regarding clip processing: {e}")

                # Reset batch tracking if complete
                if self.current_batch_processed >= self.expected_batch_size:
                    self.expected_batch_size = 0
                    self.current_batch_processed = 0

                self.clip_queue.task_done()

                # Sleep for 60 seconds to prevent rate limits
                await asyncio.sleep(60.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in clip processing worker: {e}")
                await asyncio.sleep(10.0)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id != self.target_channel_id:
            return

        match = self.url_pattern.search(message.content)
        if match:
            clip_url = match.group(0)
            canonical_url = canonicalize_clip_url(clip_url)

            # Fast DB check before queuing
            db = get_database()
            if db.trivia.clip_lore_exists(canonical_url):
                return

            self.expected_batch_size += 1
            await message.add_reaction("👀")
            await self.clip_queue.put((message, clip_url))

    @commands.command(name="scan_clips")
    async def scan_clips(self, ctx, limit: int = 20):
        """[Admin] Scans the clips channel history for unprocessed clips backwards through time."""
        if ctx.author.id not in [JAM_USER_ID, JONESY_USER_ID]:
            await ctx.send("❌ Unauthorized.")
            return

        channel = self.bot.get_channel(self.target_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Could not find clips channel or it is not a text channel.")
            return

        # Load state
        state_file = "data/clip_scan_state.json"
        os.makedirs("data", exist_ok=True)
        last_scanned_id = None
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    last_scanned_id = state.get("last_scanned_message_id")
            except Exception as e:
                logger.error(f"Error reading clip scan state: {e}")

        before_obj = discord.Object(id=last_scanned_id) if last_scanned_id else None

        if last_scanned_id:
            await ctx.send(f"🔍 Resuming scan from where we left off. Scanning {limit} older messages in <#{self.target_channel_id}>...")
        else:
            await ctx.send(f"🔍 Scanning the most recent {limit} messages in <#{self.target_channel_id}> for clips...")

        found_count = 0
        db = get_database()

        oldest_message_id = None
        oldest_message_date = None

        clips_to_queue = []

        async for message in channel.history(limit=limit, before=before_obj):
            oldest_message_id = message.id
            oldest_message_date = message.created_at

            if message.author.bot:
                continue

            match = self.url_pattern.search(message.content)
            if match:
                clip_url = match.group(0)
                found_count += 1
                canonical_url = canonicalize_clip_url(clip_url)

                if not db.trivia.clip_lore_exists(canonical_url):
                    clips_to_queue.append((message, clip_url))

        queued_count = len(clips_to_queue)
        if queued_count > 0:
            self.expected_batch_size += queued_count
            for msg, curl in clips_to_queue:
                await msg.add_reaction("👀")
                await self.clip_queue.put((msg, curl))

        # Update state
        if oldest_message_id and oldest_message_date:
            try:
                with open(state_file, 'w') as f:
                    json.dump({"last_scanned_message_id": oldest_message_id}, f)
            except Exception as e:
                logger.error(f"Error writing clip scan state: {e}")

            date_str = oldest_message_date.strftime("%Y-%m-%d")
            await ctx.send(f"✅ Scan complete. Found {found_count} clips. Added {queued_count} new clips to the processing queue.\n"
                           f"🕒 We scanned back as far as **{date_str}**. Run `!scan_clips` again to keep going backwards in time!")
        else:
            # Optionally reset tracker if we hit the beginning
            await ctx.send("✅ Scan complete. Found 0 clips. Reached the beginning of the channel!")


async def setup(bot: commands.Bot):
    await bot.add_cog(ClipTriviaCog(bot))
