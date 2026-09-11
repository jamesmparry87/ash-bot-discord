import asyncio
import json
import logging
import os
import re
import traceback
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import discord
from discord.ext import commands

from ..config import JAM_USER_ID, JONESY_USER_ID
from ..database import get_database
from ..handlers.ai_handler import upload_and_analyze_media

logger = logging.getLogger(__name__)

TRIVIA_PROMPT = """
Watch this stream clip carefully. Analyse both the visual events in the game and the streamer's reaction and audio.
Return a strict JSON response with the following keys:
- "game_title": Name of the game being played (if recognizable, else "Unknown").
- "reaction": The streamer's exact reaction (e.g. screamed, rage quit, burst out laughing, fell off chair).
- "trigger": What happened in the game to cause this reaction.
- "lore_summary": A one-sentence trivia fact focused on the streamer's experience (e.g. "During a stream, Jonesy fell off the cliff after being startled by a chicken in Skyrim").
- "notable_quote": A memorable or funny direct quote spoken by the streamer during the clip. Capture a longer, full sentence or a few sentences to ensure there is enough context to understand what they are reacting to (if any, otherwise "").
- "emotion_category": MUST be exactly one of the following: ["Rage", "Joy", "Terror", "Confusion", "Amusement", "Frustration", "Shock", "Neutral"]. Do not use synonyms.
- "characters_involved": Any specific enemies, bosses, or NPCs involved. Format as a simple comma-separated string (e.g., "Banished Knight, Godrick Soldiers"). Do not use brackets, braces, or quotes.
- "clip_outcome": MUST be exactly one of the following: ["Success", "Failure", "Death", "Neutral"]. Do not use synonyms.
Ensure the response is ONLY valid JSON, without markdown formatting.
"""


def canonicalize_clip_url(url: str) -> str:
    """Strip tracking parameters to get a canonical clip URL for deduplication."""
    try:
        parsed = urlparse(url)

        # Specific logic for Twitch clips to handle both clips.twitch.tv and twitch.tv/streamer/clip formats
        if 'twitch.tv' in parsed.netloc:
            clip_id = None
            if 'clips.twitch.tv' in parsed.netloc:
                clip_id = parsed.path.strip('/')
            elif '/clip/' in parsed.path:
                clip_id = parsed.path.split('/clip/')[-1].strip('/')

            if clip_id:
                # We standardise all clips to the long format as it presents better in Discord
                return f"https://www.twitch.tv/jonesyspacecat/clip/{clip_id}"

        # Reconstruct without query parameters or fragments
        canonical = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
        return canonical
    except Exception:
        return url


class ClipParsingService:
    def __init__(self):
        self.db = get_database()

    def _download_video_sync(self, url: str, output_path: str) -> Optional[str]:
        """Synchronous yt-dlp download to be run in a thread."""
        import yt_dlp

        ydl_opts = {
            'outtmpl': output_path,
            # Fallback to /best[ext=mp4]/best because Twitch clips often don't have separate video/audio tracks
            'format': 'bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
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
            return True

        file_id = f"clip_{message.id}"
        local_filename = f"temp/{file_id}.mp4"
        os.makedirs("temp", exist_ok=True)

        try:
            # 1. Download asynchronously
            print(f"📥 Downloading clip: {url}")
            download_result = await asyncio.to_thread(self._download_video_sync, url, local_filename)
            if not download_result or not os.path.exists(local_filename):
                raise RuntimeError(f"Failed to download video from {url}")

            # Prepare dynamic prompt with known games list
            played_games = self.db.games.get_all_played_games()
            game_titles = [str(g.get('canonical_name')) for g in played_games if g.get('canonical_name')]
            prompt = TRIVIA_PROMPT

            if game_titles:
                game_list_str = ", ".join(game_titles)
                prompt += f"\n\nCRITICAL INSTRUCTION FOR 'game_title': Whenever possible, match the game to one of our known played games: [{game_list_str}]. For example, if it looks like Hitman 2, use 'Hitman: World of Assassination' if that is in the list. Only use a new name if it definitely does not match any game in this list."

            # 2. Upload and analyze via ai_handler (handles polling and deletion)
            response_text, status = await upload_and_analyze_media(local_filename, prompt)

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
                notable_quote=data.get("notable_quote", ""),
                emotion_category=data.get("emotion_category", ""),
                characters_involved=data.get("characters_involved", ""),
                clip_outcome=data.get("clip_outcome", ""),
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
            r'https?://(?:www\.)?(?:clips\.twitch\.tv/\S+|twitch\.tv/\w+/clip/\S+|youtube\.com/clip/\S+|youtube\.com/shorts/\S+|youtu\.be/clip/\S+)'
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.channel.id != self.target_channel_id:
            return

        # Allow both live and staging bots to acknowledge with 👀
        # (This helps verify the bot is seeing the clips in all environments)

        match = self.url_pattern.search(message.content)
        if match:
            clip_url = match.group(0)
            canonical_url = canonicalize_clip_url(clip_url)

            # Fast DB check
            db = get_database()
            if db.trivia.clip_lore_exists(canonical_url):
                return

            # Acknowledge visually so users know it's in the queue for 8 PM
            await message.add_reaction("👀")

    async def process_backlog_batch(self, search_limit: int = 200, max_process: int = 50,
                                    ctx=None, dryrun: bool = False, resume_from_state: bool = True) -> tuple[int, int]:
        """Scans the clips channel history for unprocessed clips backwards through time.
        Uploads clips to Gemini Files API and creates a batch job.
        Returns (found_count, queued_count)."""
        channel = self.bot.get_channel(self.target_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            if ctx:
                await ctx.send("❌ Could not find clips channel or it is not a text channel.")
            else:
                logger.error("Could not find clips channel or it is not a text channel.")
            return 0, 0

        db = get_database()

        # 1. Enforce only 1 batch job at a time
        if not dryrun and db.trivia.has_pending_batch():
            msg = "⏳ A clip batch job is currently PENDING. Aborting new batch creation."
            if ctx:
                await ctx.send(msg)
            else:
                logger.info(msg)
            return 0, 0

        # Load state
        state_file = "data/clip_scan_state.json"
        os.makedirs("data", exist_ok=True)
        last_scanned_id = None
        if resume_from_state and os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    last_scanned_id = state.get("last_scanned_message_id")
            except Exception as e:
                logger.error(f"Error reading clip scan state: {e}")

        before_obj = discord.Object(id=last_scanned_id) if last_scanned_id else None

        if ctx:
            if last_scanned_id:
                await ctx.send(f"🔍 Resuming scan. Scanning up to {search_limit} older messages in <#{self.target_channel_id}>...")
            else:
                await ctx.send(f"🔍 Scanning the most recent {search_limit} messages in <#{self.target_channel_id}> for clips...")

        found_count = 0
        total_unprocessed = 0
        clips_to_queue = []
        oldest_message_id = None

        async for message in channel.history(limit=search_limit, before=before_obj):
            oldest_message_id = message.id
            if message.author.bot:
                continue

            match = self.url_pattern.search(message.content)
            if match:
                clip_url = match.group(0)
                found_count += 1
                canonical_url = canonicalize_clip_url(clip_url)

                if not db.trivia.clip_lore_exists(canonical_url):
                    total_unprocessed += 1
                    if len(clips_to_queue) < max_process:
                        clips_to_queue.append((message, clip_url, canonical_url))
                else:
                    # Clip already processed in DB - ensure it has the ✅ reaction ONLY if it is completed
                    if db.trivia.is_clip_completed(canonical_url):
                        has_tick = any(str(r.emoji) == "✅" for r in message.reactions)
                        if not has_tick:
                            try:
                                await message.add_reaction("✅")
                                await message.remove_reaction("👀", self.bot.user)  # type: ignore
                                await message.remove_reaction("❌", self.bot.user)  # type: ignore
                            except Exception:
                                pass

        queued_count = len(clips_to_queue)
        if queued_count == 0:
            if ctx:
                await ctx.send("✅ No unprocessed clips found in this scan segment.")
            if resume_from_state and oldest_message_id:
                with open(state_file, 'w') as f:
                    json.dump({"last_scanned_message_id": oldest_message_id}, f)
            return found_count, 0

        if dryrun:
            msg = f"🏜️ **DRY RUN COMPLETE** 🏜️\nFound **{found_count}** total clip URLs in the scan range.\nQueued **{queued_count}** clips that need processing.\n\n"
            if queued_count > 0:
                msg += "**Clips that would be processed in this batch:**\n"
                for m, curl, canon in clips_to_queue[:10]:
                    msg += f"- <{canon}>\n"
                if queued_count > 10:
                    msg += f"...and {queued_count - 10} more.\n"

                # Mock JSONL preview for the first clip
                first_msg, first_curl, first_canon = clips_to_queue[0]
                mock_jsonl = {
                    "request": {
                        "contents": [
                            {"role": "user", "parts": [
                                {"fileData": {"fileUri": "https://generativelanguage.googleapis.com/v1beta/files/mockfile123", "mimeType": "video/mp4"}},
                                {"text": TRIVIA_PROMPT[:50] + "..."}
                            ]}
                        ]
                    },
                    "id": f"{first_canon}|{first_msg.id}"
                }
                msg += f"\n**JSONL Preview (Line 1):**\n```json\n{json.dumps(mock_jsonl, indent=2)}\n```\n"

            if ctx:
                await ctx.send(msg)
            return found_count, queued_count

        # Create batch job
        import asyncio

        from ..handlers.ai_handler import gemini_batch_client

        if not gemini_batch_client:
            msg = "❌ gemini_batch_client is not initialized. Cannot create batch."
            logger.error(msg)
            if ctx:
                await ctx.send(msg)
            return found_count, 0

        if ctx:
            await ctx.send(f"🎬 Downloading and uploading {queued_count} clips for Batch processing...")

        played_games = db.games.get_all_played_games()
        game_titles = [str(g.get('canonical_name')) for g in played_games if g.get('canonical_name')]
        prompt = TRIVIA_PROMPT
        if game_titles:
            game_list_str = ", ".join(game_titles)
            prompt += f"\n\nCRITICAL INSTRUCTION FOR 'game_title': Whenever possible, match the game to one of our known played games: [{game_list_str}]. Only use a new name if it definitely does not match any game in this list."

        os.makedirs("temp", exist_ok=True)
        jsonl_lines = []
        uploaded_files = []

        try:
            for idx, (msg, curl, canonical_url) in enumerate(clips_to_queue):
                # Acknowledge visually
                try:
                    await msg.add_reaction("👀")
                except Exception:
                    pass

                file_id = f"clip_{msg.id}"
                local_filename = f"temp/{file_id}.mp4"

                # Download
                logger.info(f"Downloading clip {idx+1}/{queued_count}: {curl}")
                download_result = await asyncio.to_thread(self.parser._download_video_sync, curl, local_filename)
                if not download_result or not os.path.exists(local_filename):
                    logger.error(f"Failed to download video from {curl}")
                    try:
                        await msg.add_reaction("❌")
                    except Exception:
                        pass
                    continue

                # Upload to Files API
                logger.info(f"Uploading clip {idx+1} to Gemini Files API")
                uploaded_file = await asyncio.to_thread(
                    gemini_batch_client.files.upload,
                    file=local_filename,
                    config={'mime_type': 'video/mp4'}
                )
                uploaded_files.append(uploaded_file)

                # Append to JSONL
                jsonl_obj = {
                    "request": {
                        "contents": [
                            {"role": "user", "parts": [
                                {"fileData": {"fileUri": uploaded_file.uri, "mimeType": "video/mp4"}}, {"text": prompt}]}
                        ]
                    },
                    "id": f"{canonical_url}|{msg.id}"  # Store both URL and Discord message ID as custom_id
                }
                jsonl_lines.append(json.dumps(jsonl_obj))

                # Cleanup local file
                os.remove(local_filename)

            if not jsonl_lines:
                if ctx:
                    await ctx.send("❌ All clips failed to download or upload.")
                return found_count, 0

            # Create JSONL file
            jsonl_path = "temp/batch_requests.jsonl"
            with open(jsonl_path, "w") as f:
                f.write("\n".join(jsonl_lines))

            # Upload JSONL file
            jsonl_upload = await asyncio.to_thread(
                gemini_batch_client.files.upload,
                file=jsonl_path,
                config={'mime_type': 'application/jsonl'}
            )
            uploaded_files.append(jsonl_upload)

            # Start batch
            from google.genai import types

            from ..config import GEMINI_BATCH_MODEL
            logger.info("Submitting batch job...")
            batch_job = await asyncio.to_thread(
                gemini_batch_client.batches.create,
                model=GEMINI_BATCH_MODEL,
                src=jsonl_upload.name
            )
            job_id = batch_job.name

            # Add to DB
            for msg, curl, canonical_url in clips_to_queue:
                # Add a dummy row to track the batch ID
                db.trivia.add_pending_batch_clip(canonical_url, "Batch Pending Video")
                db.trivia.update_clip_batch_job(canonical_url, job_id)

            msg = f"🚀 Batch Job {job_id} successfully submitted with {len(jsonl_lines)} clips!"
            remaining = total_unprocessed - len(jsonl_lines)
            if remaining > 0:
                msg += f"\n📊 There are at least **{remaining}** more unprocessed clips in the current scan range."
            else:
                msg += f"\n✅ All clips in the current scan range have been processed."

            logger.info(msg)
            if ctx:
                await ctx.send(msg)
            else:
                try:
                    jam = await self.bot.fetch_user(JAM_USER_ID)
                    if jam:
                        scan_type = "Historical Backlog" if resume_from_state else "Recent Clips"
                        await jam.send(f"🤖 **Automated Clip Scan ({scan_type})**\n{msg}")
                except Exception as e:
                    logger.error(f"Failed to DM JAM about automated batch submission: {e}")

            os.remove(jsonl_path)

            # Update state
            if resume_from_state and oldest_message_id:
                with open(state_file, 'w') as f:
                    json.dump({"last_scanned_message_id": oldest_message_id}, f)

            return found_count, len(jsonl_lines)

        except Exception as e:
            logger.error(f"Batch processing error: {e}")
            if ctx:
                await ctx.send(f"❌ Error creating batch: {str(e)[:100]}")
            return found_count, 0

    @commands.command(name="scan_clips")
    async def scan_clips(self, ctx, limit: int = 20):
        """[Admin] Scans the clips channel history for unprocessed clips backwards through time."""
        if ctx.author.id not in [JAM_USER_ID, JONESY_USER_ID]:
            await ctx.send("❌ Unauthorized.")
            return

        await self.process_backlog_batch(search_limit=2000, max_process=limit, ctx=ctx)

    @commands.command(name="scan_clips_dryrun")
    async def scan_clips_dryrun(self, ctx, limit: int = 20):
        """[Admin] Performs a dry run of the clip backlog scan without actually downloading or submitting to Gemini."""
        if ctx.author.id not in [JAM_USER_ID, JONESY_USER_ID]:
            await ctx.send("❌ Unauthorized.")
            return

        await self.process_backlog_batch(search_limit=2000, max_process=limit, ctx=ctx, dryrun=True)

    @commands.command(name="reset_clips")
    async def reset_clips(self, ctx):
        """[Admin] Deletes all clip lore from the database so they can be re-processed."""
        if ctx.author.id not in [JAM_USER_ID, JONESY_USER_ID]:
            await ctx.send("❌ Unauthorized.")
            return

        db = get_database()
        try:
            conn = db.get_connection()
            cursor = conn.cursor()  # type: ignore
            cursor.execute("DELETE FROM clip_lore")
            deleted_count = cursor.rowcount
            conn.commit()  # type: ignore
            conn.close()  # type: ignore

            await ctx.send(f"✅ **Database Reset:** Successfully deleted **{deleted_count}** processed clips from the database.\n"
                           f"They will be picked up as 'new' clips and re-processed using the strict formatting rules on the next scan!")
        except Exception as e:
            logger.error(f"Error resetting clips: {e}")
            await ctx.send(f"❌ Error resetting clips: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ClipTriviaCog(bot))
