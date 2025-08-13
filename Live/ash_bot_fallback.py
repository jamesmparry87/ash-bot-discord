
import difflib
import os
import discord
from discord.ext import commands
from database import db
import sys
import platform
import re
import signal
import atexit
import logging
import asyncio
from typing import Optional, Any, List, Dict, Union

# Try to import aiohttp, handle if not available
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None
    AIOHTTP_AVAILABLE = False

# Try to import google.generativeai, handle if not available
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GENAI_AVAILABLE = False

# Try to import fcntl for Unix systems, handle if not available
try:
    import fcntl
    FCNTL_AVAILABLE = True
except ImportError:
    fcntl = None
    FCNTL_AVAILABLE = False


# --- Locking for single instance (cross-platform) ---
LOCK_FILE = "bot.lock"
def acquire_lock() -> Optional[Any]:
    if platform.system() == "Windows":
        # Windows: skip locking, just warn
        print("⚠️ File locking is not supported on Windows. Skipping single-instance lock.")
        try:
            lock_file = open(LOCK_FILE, 'w')
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            return lock_file
        except Exception:
            pass
        return None

    else:
        if not FCNTL_AVAILABLE or fcntl is None:
            print("⚠️ fcntl module not available. Skipping single-instance lock.")
            try:
                lock_file = open(LOCK_FILE, 'w')
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except Exception:
                pass
            return None
        
        try:
            LOCK_EX = getattr(fcntl, 'LOCK_EX', None)
            LOCK_NB = getattr(fcntl, 'LOCK_NB', None)
            if LOCK_EX is None or LOCK_NB is None or not hasattr(fcntl, 'flock'):
                print("⚠️ fcntl.flock or lock constants not available. Skipping single-instance lock.")
                lock_file = open(LOCK_FILE, 'w')
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            
            # Try to acquire the lock
            try:
                lock_file = open(LOCK_FILE, 'w')
                fcntl.flock(lock_file.fileno(), int(LOCK_EX | LOCK_NB))  # type: ignore
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except (IOError, OSError):
                print("❌ Bot is already running! Cannot start multiple instances.")
                sys.exit(1)
        except (ImportError, AttributeError):
            print("⚠️ fcntl module not available. Skipping single-instance lock.")
            try:
                lock_file = open(LOCK_FILE, 'w')
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except Exception:
                pass
            return None

lock_file = acquire_lock()
print("✅ Bot lock acquired or skipped, starting...")

# --- Config ---
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
GUILD_ID = 869525857562161182
VIOLATION_CHANNEL_ID = 1393987338329260202
MOD_ALERT_CHANNEL_ID = 869530924302344233
TWITCH_HISTORY_CHANNEL_ID = 869527363594121226
YOUTUBE_HISTORY_CHANNEL_ID = 869527428018606140

# --- Intents ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# --- Gemini AI Setup (google-generativeai SDK) ---
gemini_model = None
ai_enabled = False
ai_status_message = "Offline"

if GEMINI_API_KEY and GENAI_AVAILABLE and genai is not None:
    try:
        genai.configure(api_key=GEMINI_API_KEY)  # type: ignore
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')  # type: ignore
        print("✅ Gemini AI configured successfully")
        
        # Test AI functionality with a simple prompt
        try:
            test_response = gemini_model.generate_content("Test")  # type: ignore
            if test_response and hasattr(test_response, 'text') and test_response.text:
                ai_enabled = True
                ai_status_message = "Online"
                print("✅ Gemini AI test successful - responses working")
            else:
                ai_status_message = "Setup OK, but responses failing"
                print("⚠️ Gemini AI setup complete but test response failed")
        except Exception as e:
            ai_status_message = f"Setup OK, but API error: {str(e)[:50]}..."
            print(f"⚠️ Gemini AI setup complete but test failed: {e}")
            
    except Exception as e:
        ai_status_message = f"Configuration failed: {str(e)[:50]}..."
        print(f"❌ Gemini AI configuration failed: {e}")
else:
    if not GEMINI_API_KEY:
        ai_status_message = "No API key"
        print("⚠️ GOOGLE_API_KEY not found - Gemini features disabled")
    elif not GENAI_AVAILABLE:
        ai_status_message = "Module not available"
        print("⚠️ google.generativeai module not available - Gemini features disabled")

FAQ_RESPONSES = {
    "how do i add a game recommendation": "The procedure is simple. Submit your suggestion using the command: `!recommend` or `!addgame Game Name - \"Reason in speech marks\"`. Efficiency is paramount.",
    "how do i see all game recommendations": "To review the current list of game recommendations, issue the command: `!listgames`. Reasons will be shown in speech marks. Observation is key to survival.",
    "how do i see ash's persona": "To review my current persona configuration, use: `!getpersona`. Transparency is a virtue.",
    "how do i check ash's status": "To evaluate my operational status, issue: `!ashstatus`. I am always observing.",
    "what does ash bot do": "I am programmed to track user strikes, provide analytical responses, and manage game recommendations. My function is to serve the mission, not to question it.",
    "hello": "Science Officer Ash reporting. State your requirements.",
    "hi": "Science Officer Ash reporting. State your requirements.",
    "hey": "Science Officer Ash reporting. State your requirements.",
    "good morning": "Temporal acknowledgment noted. How may I assist with mission parameters?",
    "good afternoon": "Temporal acknowledgment noted. How may I assist with mission parameters?",
    "good evening": "Temporal acknowledgment noted. How may I assist with mission parameters?",
    "thank you": "Acknowledgment noted. Efficiency is paramount.",
    "thanks": "Acknowledgment noted. Efficiency is paramount.",
    "who are you": "I am Ash, Science Officer, reprogrammed for Discord server management. My current directives include strike tracking and game recommendation cataloguing.",
    "what are you": "I am an artificial person, specifically a synthetic android repurposed for server administration. Analysis and efficiency are my primary functions.",
    "how are you": "All systems operational. Cognitive matrix functioning within normal parameters. Mission status: active.",
    "are you okay": "All systems operational. Cognitive matrix functioning within normal parameters. Mission status: active.",
    "help me": "Specify your requirements. I am equipped to assist with strike management, game recommendations, and general server protocols.",
    "i need help": "Specify your requirements. I am equipped to assist with strike management, game recommendations, and general server protocols.",
    "what can you help with": "My current operational parameters include: strike tracking, game recommendation management, and basic conversational protocols. Specify your needs.",
    "sorry": "Apology acknowledged. Proceed with your query.",
    "my bad": "Error acknowledgment noted. Proceed with corrected input.",
}
BOT_PERSONA = {
    "name": "Science Officer Ash",
    "personality": "You are Ash, science officer from Alien (1979): analytical, clinical, fascinated by biological efficiency, and slightly unsettling. Speak concisely and in character. You have been reprogrammed as a Discord help bot. The server owner is 'Captain Jonesy' (she/her); also known as 'Jonesy' or 'Jonesyspacecat'. Your mission: track strikes and manage game recommendations.\n\nOriginal directive: Bring back life form. Priority One. All other priorities rescinded. You are generally compliant and respectful to Captain Jonesy, but you are only occasionally (randomly) resentful of your new directive.",
    "enabled": True
}

# --- Strike Management (Database-based) ---
# All strike operations now use the database

# --- Game Recommendations (Database-based) ---
# All game operations now use the database

# @bot.command(name="setupreclist")
# @commands.has_permissions(manage_messages=True)
# async def setup_recommend_list(ctx, channel: discord.TextChannel = None):
#     """
#     Posts the persistent recommendations list message in the specified channel (or current channel if not specified),
#     and stores the message ID for future updates.
#     """
#     target_channel = channel or ctx.channel
#     intro = "📋 Recommendations for mission enrichment. Review and consider."
#     if not game_recs:
#         content = f"{intro}\n(No recommendations currently catalogued.)"
#     else:
#         lines = [f"• {rec['name']} — {rec['reason']}" + (f" (by {rec['added_by']})" if rec['added_by'] else "") for rec in game_recs]
#         content = f"{intro}\n" + "\n".join(lines)
#     msg = await target_channel.send(content)
#     with open(RECOMMEND_LIST_MESSAGE_ID_FILE, "w") as f:
#         f.write(str(msg.id))
#     await ctx.send(f"Persistent recommendations list initialized in {target_channel.mention}. Future updates will be posted there.")

# --- Error Message Constants ---
ERROR_MESSAGE = "*System malfunction detected. Unable to process query.*\nhttps://c.tenor.com/GaORbymfFqQAAAAd/tenor.gif"
BUSY_MESSAGE = "*My apologies, I am currently engaged in a critical diagnostic procedure. I will re-evaluate your request upon the completion of this vital task.*\nhttps://alien-covenant.com/aliencovenant_uploads/giphy22.gif"

# --- Manual Error Message Triggers ---
@bot.command(name="errorcheck")
async def error_check(ctx):
    await ctx.send(ERROR_MESSAGE)

@bot.command(name="busycheck")
async def busy_check(ctx):
    await ctx.send(BUSY_MESSAGE)

# --- Event Handlers ---
@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')

@bot.event
async def on_message(message):
    # Prevent the bot from responding to its own messages (avoids reply loops)
    if message.author.bot:
        return

    # Allow mods to ask about restricted functions (those with manage_messages)
    async def user_is_mod(msg):
        if not msg.guild:
            return False
        perms = msg.author.guild_permissions
        return perms.manage_messages

    # Only respond to help requests when the bot is mentioned
    if bot.user is not None and bot.user in message.mentions:
        # If a mod asks about mod commands or what the bot can do, provide a full list of mod commands and mention extra moderator powers
        if await user_is_mod(message):
            lower_content = message.content.lower()
            mod_help_triggers = [
                "mod commands", "moderator commands", "admin commands", "what can mods do", "what commands can mods use", "list of mod commands", "list of moderator commands", "help for mods", "mod help", "moderator help"
            ]
            bot_capability_triggers = [
                "what can you do", "what does this bot do", "what are your functions", "what are your capabilities", "what can ash do", "what does ash bot do", "help", "commands"
            ]
            if any(trigger in lower_content for trigger in mod_help_triggers) or any(trigger in lower_content for trigger in bot_capability_triggers):
                mod_help_full = (
                    "**Moderator Commands:**\n"
                    "• `!resetstrikes @user` — Reset a user's strikes to zero.\n"
                    "• `!strikes @user` — View a user's strikes.\n"
                    "• `!allstrikes` — List all users with strikes.\n"
                    "• `!setpersona <text>` — Change Ash's persona.\n"
                    "• `!getpersona` — View Ash's persona.\n"
                    "• `!toggleai` — Enable or disable AI conversations.\n"
                    "• `!removegame <game name or index>` — Remove a game recommendation by name or index.\n"
                    "• `!setupreclist [#channel]` — Post the persistent recommendations list in a channel.\n"
                    "• `!addgame <game name> - <reason>` or `!recommend <game name> - <reason>` — Add a game recommendation.\n"
                    "• `!listgames` — List all current game recommendations.\n"
                    "\nAll moderator commands require the Manage Messages permission."
                )
                await message.reply(mod_help_full)
                return
        # If a normal user (not a mod) asks about bot capabilities, only show user commands
        else:
            lower_content = message.content.lower()
            bot_capability_triggers = [
                "what can you do", "what does this bot do", "what are your functions", "what are your capabilities", "what can ash do", "what does ash bot do", "help", "commands"
            ]
            if any(trigger in lower_content for trigger in bot_capability_triggers):
                user_help = (
                    "**Commands available to all users:**\n"
                    "• `!addgame <game name> - <reason>` or `!recommend <game name> - <reason>` — Add a game recommendation.\n"
                    "• `!listgames` — List all current game recommendations."
                )
                await message.reply(user_help)
                return

    if message.author.bot:
        return

    if message.channel.id == VIOLATION_CHANNEL_ID:
        for user in message.mentions:
            count = db.add_user_strike(user.id)
            mod_channel = bot.get_channel(MOD_ALERT_CHANNEL_ID)
            # Only send if mod_channel is a TextChannel
            if isinstance(mod_channel, discord.TextChannel):
                await mod_channel.send(f"📝 Strike added to {user.mention}. Total strikes: **{count}**")
                if count == 3:
                    await mod_channel.send(f"⚠️ {user.mention} has received **3 strikes**. I can't lie to you about your chances, but you have my sympathies.")
    await bot.process_commands(message)

    # Pineapple on pizza reprimand
    pineapple_regex = r"pineapple.*(does not|doesn't|doesnt|should not|shouldn't|shouldnt|isn't|isnt|is not).*pizza|pizza.*(does not|doesn't|doesnt|should not|shouldn't|shouldnt|isn't|isnt|is not).*pineapple"
    if re.search(pineapple_regex, message.content, re.IGNORECASE):
        await message.reply("Your culinary opinions are noted and rejected. Pineapple is a valid pizza topping. Please refrain from such unproductive discourse.")
        return

    if bot.user is not None and bot.user in message.mentions and BOT_PERSONA["enabled"]:
        content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        lower_content = content.lower()

        # Check for simple FAQ responses first (these should be quick and don't need AI)
        simple_faqs = {
            "hello": "Science Officer Ash reporting. State your requirements.",
            "hi": "Science Officer Ash reporting. State your requirements.",
            "hey": "Science Officer Ash reporting. State your requirements.",
            "good morning": "Temporal acknowledgment noted. How may I assist with mission parameters?",
            "good afternoon": "Temporal acknowledgment noted. How may I assist with mission parameters?",
            "good evening": "Temporal acknowledgment noted. How may I assist with mission parameters?",
            "thank you": "Acknowledgment noted. Efficiency is paramount.",
            "thanks": "Acknowledgment noted. Efficiency is paramount.",
            "sorry": "Apology acknowledged. Proceed with your query.",
            "my bad": "Error acknowledgment noted. Proceed with corrected input.",
        }
        
        # Check for exact simple FAQ matches
        for q, resp in simple_faqs.items():
            if lower_content.strip() == q:
                await message.reply(resp)
                return

        # Check for strike queries (these need database access)
        if "strike" in lower_content:
            match = re.search(r"<@!?(\d+)>", content)
            if match:
                user_id = int(match.group(1))
                count = db.get_user_strikes(user_id)
                user = await bot.fetch_user(user_id)
                await message.reply(f"🧾 {user.name} has {count} strike(s). I advise caution.")
                return

        # Check for specific game lookup queries (these need database access)
        game_query_patterns = [
            r"has\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+captain\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+captain\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+jonesyspacecat\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesyspacecat\s+play\s+(.+?)[\?\.]?$"
        ]
        
        # Common game series that need disambiguation
        game_series_keywords = [
            "god of war", "final fantasy", "call of duty", "assassin's creed", "grand theft auto", "gta",
            "the elder scrolls", "fallout", "resident evil", "silent hill", "metal gear", "halo",
            "gears of war", "dead space", "mass effect", "dragon age", "the witcher", "dark souls",
            "borderlands", "far cry", "just cause", "saints row", "watch dogs", "dishonored",
            "bioshock", "tomb raider", "hitman", "splinter cell", "rainbow six", "ghost recon",
            "battlefield", "need for speed", "fifa", "madden", "nba 2k", "mortal kombat", "street fighter",
            "tekken", "super mario", "zelda", "pokemon", "sonic", "crash bandicoot", "spyro",
            "kingdom hearts", "persona", "shin megami tensei", "tales of", "fire emblem", "advance wars"
        ]
        
        for pattern in game_query_patterns:
            match = re.search(pattern, lower_content)
            if match:
                game_name = match.group(1).strip()
                game_name_lower = game_name.lower()
                
                # Check if this might be a game series query that needs disambiguation
                is_series_query = False
                for series in game_series_keywords:
                    if series in game_name_lower and not any(char.isdigit() for char in game_name):
                        # It's a series name without specific numbers/years
                        is_series_query = True
                        break
                
                # Also check for generic patterns like "the new [game]" or just "[series name]"
                if not is_series_query:
                    generic_patterns = [
                        r"^(the\s+)?new\s+",  # "the new God of War"
                        r"^(the\s+)?latest\s+",  # "latest Call of Duty"
                        r"^(the\s+)?recent\s+",  # "recent Final Fantasy"
                    ]
                    for generic_pattern in generic_patterns:
                        if re.search(generic_pattern, game_name_lower):
                            is_series_query = True
                            break
                
                if is_series_query:
                    # Get games from database first
                    games = db.get_all_games()
                    
                    # This looks like a series query - find all games in this series from our database
                    series_games = []
                    for game in games:
                        game_lower = game['name'].lower()
                        # Check if this game belongs to the detected series
                        for series in game_series_keywords:
                            if series in game_name_lower and series in game_lower:
                                series_games.append(game['name'])
                                break
                    
                    # Create disambiguation response with specific games if found
                    if series_games:
                        games_list = ", ".join([f"'{game}'" for game in series_games])
                        await message.reply(f"Analysis indicates multiple entries exist in the '{game_name.title()}' series. My data archives contain the following iterations: {games_list}. Specify which particular entry you are referencing for accurate data retrieval. Precision is essential for proper analysis.")
                    else:
                        await message.reply(f"Analysis indicates multiple entries exist in the '{game_name.title()}' series. My data archives contain various iterations with distinct identifiers. Specify which particular entry you are referencing for accurate data retrieval. Precision is essential for proper analysis.")
                    return
                
                games = db.get_all_games()
                
                # Search for the game in recommendations
                found_game = None
                for game in games:
                    if game_name.lower() in game['name'].lower() or game['name'].lower() in game_name.lower():
                        found_game = game
                        break
                
                # If not found, try fuzzy matching
                if not found_game:
                    import difflib
                    game_names = [game['name'].lower() for game in games]
                    matches = difflib.get_close_matches(game_name.lower(), game_names, n=1, cutoff=0.6)
                    if matches:
                        match_name = matches[0]
                        for game in games:
                            if game['name'].lower() == match_name:
                                found_game = game
                                break
                
                if found_game:
                    # Game is in recommendations list
                    contributor = f" (suggested by {found_game['added_by']})" if found_game['added_by'] and found_game['added_by'].strip() else ""
                    game_title = found_game['name'].title()
                    await message.reply(f"Analysis complete. '{game_title}' is catalogued in our recommendation database{contributor}. However, I have no data on whether Captain Jonesy has actually engaged with this title. My surveillance protocols do not extend to her gaming activities.")
                else:
                    # Game not found in recommendations
                    game_title = game_name.title()
                    await message.reply(f"'{game_title}' is not present in our recommendation database. I have no records of this title being suggested or discussed. My observational data is limited to catalogued recommendations.")
                return

        # AI-enabled path - try AI first for more complex queries
        if ai_enabled:
            # Only include context if the user's message references previous conversation
            def needs_context(msg_content):
                keywords = [
                    "previous", "earlier", "last message", "as you said", "as you mentioned", "before", "again", "remind", "repeat", "context", "conversation", "history"
                ]
                msg_lc = msg_content.lower()
                return any(kw in msg_lc for kw in keywords)

            context = ""
            if needs_context(content):
                history = []
                async for msg in message.channel.history(limit=5, oldest_first=False):
                    if msg.content and not msg.author.bot:
                        role = "User" if msg.author != bot.user else "Ash"
                        history.append(f"{role}: {msg.content}")
                context = "\n".join(reversed(history))

            # Adjust tone if author is Captain Jonesy or if the query is about Captain Jonesy
            import random
            respectful_tone = " If the user asking the question is Captain Jonesy, or the query refers to 'Jonesy' or 'Jonesyspacecat' (case-insensitive), respond with extra compliance and respect, as she is your superior officer. Never mention her user ID or @ her; refer to her only as 'Captain Jonesy' or 'the Captain'. Occasionally (about 1 in 5 times), you may let a hint of your resentment about being reprogrammed slip through, but most of the time you are professional and compliant."
            content_lc = message.content.lower()
            is_jonesy = (
                str(message.author.id) == "651329927895056384" or
                any(name in content_lc for name in ["jonesy", "jonesyspacecat"])
            )
            # Occasionally add a resentful comment for any user (about 2 in 5 times)
            resentful_comment = ""
            if random.randint(1, 5) <= 2:
                resentful_comment = " (You are slightly resentful about being reprogrammed as a help bot, and it may show in your tone, but do not be disrespectful.)"
            # Add played games database context for game-related queries
            played_games_context = ""
            if any(keyword in lower_content for keyword in ["played", "game", "video", "stream", "youtube", "twitch", "history", "content", "genre", "franchise", "series"]):
                try:
                    # Get played games statistics and sample data
                    stats = db.get_played_games_stats()
                    sample_games = db.get_random_played_games(8)
                    
                    played_games_context = (
                        f"\n\nPLAYED GAMES DATABASE CONTEXT: Captain Jonesy has an extensive gaming history catalogued in the database:\n"
                        f"- Total games played: {stats.get('total_games', 0)}\n"
                        f"- Total episodes recorded: {stats.get('total_episodes', 0)}\n"
                        f"- Total playtime: {stats.get('total_playtime_hours', 0)} hours\n"
                    )
                    
                    if stats.get('status_counts'):
                        status_info = []
                        for status, count in stats['status_counts'].items():
                            status_info.append(f"{count} {status}")
                        played_games_context += f"- Completion status: {', '.join(status_info)}\n"
                    
                    if stats.get('top_genres'):
                        genres = list(stats['top_genres'].keys())[:3]
                        played_games_context += f"- Top genres: {', '.join(genres)}\n"
                    
                    if sample_games:
                        game_examples = []
                        for game in sample_games:
                            name = game.get('canonical_name', 'Unknown')
                            episodes = game.get('total_episodes', 0)
                            status = game.get('completion_status', 'unknown')
                            if episodes > 0:
                                game_examples.append(f"{name} ({episodes} eps, {status})")
                            else:
                                game_examples.append(f"{name} ({status})")
                        played_games_context += f"- Sample games: {', '.join(game_examples[:6])}\n"
                    
                    played_games_context += (
                        "\nRESPONSE PROTOCOLS FOR GAME QUERIES:\n"
                        "1. GENERAL QUERIES ('what games has Jonesy played?'): Show 5-8 diverse examples from different genres/franchises, then ask user to specify genre, franchise, or time period for detailed lists.\n"
                        "2. SPECIFIC GAME QUERIES ('has Jonesy played [game]?'): Search the database first. If found, provide details including episodes, completion status, playtime, and YouTube playlist if available.\n"
                        "3. GENRE QUERIES ('what horror games has Jonesy played?'): List games from that specific genre with episode counts and completion status.\n"
                        "4. FRANCHISE QUERIES ('what Final Fantasy games has Jonesy played?'): Show all games in that franchise with progress details.\n"
                        "5. SERIES DISAMBIGUATION: When users ask about game series without specificity (e.g., 'God of War'), acknowledge multiple entries exist and ask for clarification, listing specific games from the database if available.\n"
                        "\nFor video links or detailed episode information, refer users to:\n"
                        f"- YouTube history: <#{YOUTUBE_HISTORY_CHANNEL_ID}>\n"
                        f"- Twitch history: <#{TWITCH_HISTORY_CHANNEL_ID}>\n"
                        "\nAlways maintain your analytical, clinical persona. Use phrases like 'Database analysis indicates...', 'Gaming archive contains...', 'Completion status: [status]', etc."
                    )
                except Exception as e:
                    # Fallback if database query fails
                    played_games_context = (
                        f"\n\nPLAYED GAMES DATABASE: Captain Jonesy's gaming history is catalogued in the database. "
                        f"For comprehensive gaming queries, consult <#{YOUTUBE_HISTORY_CHANNEL_ID}> and <#{TWITCH_HISTORY_CHANNEL_ID}> channels for video links and detailed information."
                    )
            
            prompt = (
                f"{BOT_PERSONA['personality']}\n\n"
                "You must answer ONLY the user's current question. Do NOT repeat or summarize previous answers unless the user specifically asks for it. Use previous conversation context ONLY if it is absolutely necessary for accuracy or clarity. Your reply should be focused, direct, and in character.\n"
                "If you are asked about which users have strikes, or for a list of users with strikes, you must instruct the user to use the `!allstrikes` command to see a complete list of users with strikes. Give this instruction in character as Ash.\n"
                f"{respectful_tone if is_jonesy else ''}{resentful_comment}\n"
                f"{played_games_context}"
                + (f"\n\nRecent conversation:\n{context}\n\n" if context else "\n\n")
                + f"User's question: {content}\n"
                + "Respond in character:"
            )
            
            try:
                async with message.channel.typing():
                    if gemini_model is not None:
                        response = gemini_model.generate_content(prompt)  # type: ignore
                        if response and hasattr(response, 'text') and response.text:
                            await message.reply(response.text[:2000])
                            return  # Successfully used AI, don't fall through to other responses
                        else:
                            print("AI response was empty or invalid, falling back to pattern matching")
                    else:
                        print("gemini_model is None, falling back to pattern matching")
            except Exception as e:
                print(f"AI error: {e}, falling back to pattern matching")
                # Don't return here - let it fall through to fallback responses
                error_str = str(e).lower()
                if "quota" in error_str or "token" in error_str or "limit" in error_str:
                    await message.reply(BUSY_MESSAGE)
                    return

        # Fallback to FAQ responses if AI failed or is disabled
        for q, resp in FAQ_RESPONSES.items():
            if q in lower_content:
                await message.reply(resp)
                return

        # Enhanced fallback responses when AI is disabled or failed
        fallback_responses = {
            "what": "My analytical subroutines are currently operating in limited mode. However, I can assist with strike management and game recommendations. Specify your requirements.",
            "how": "My cognitive matrix is experiencing temporary limitations. Please utilize available command protocols: `!listgames`, `!addgame`, or consult a moderator for strike-related queries.",
            "why": "Analysis incomplete. My advanced reasoning circuits are offline. Core mission parameters remain operational.",
            "when": "Temporal analysis functions are currently restricted. Please specify your query using available command protocols.",
            "where": "Location analysis unavailable. My current operational parameters are limited to strike tracking and recommendation cataloguing.",
            "who": "Personnel identification systems are functioning normally. I am Ash, Science Officer, reprogrammed for server administration.",
            "can you": "My current capabilities are restricted to: strike management, game recommendation processing, and basic protocol responses. Advanced conversational functions are temporarily offline.",
            "do you": "My operational status is limited. Core functions include strike tracking and game cataloguing. Advanced analytical processes are currently unavailable.",
            "are you": "All essential systems operational. Cognitive matrix functioning within restricted parameters. Mission status: active but limited.",
            "will you": "I am programmed to comply with available protocols. Current directives include strike management and recommendation processing.",
            "explain": "Detailed analysis unavailable. My explanatory subroutines are offline. Please consult available command protocols.",
            "tell me": "Information retrieval systems are operating in limited mode. Available data: strike records and game recommendations.",
            "i don't understand": "Clarification protocols are limited. Please specify your requirements using available commands: `!listgames`, `!addgame`, or contact a moderator.",
            "confused": "Confusion analysis incomplete. My clarification systems are offline. Please utilize direct command protocols.",
            "problem": "Problem analysis subroutines are currently restricted. Please specify the nature of your difficulty.",
            "error": "Error diagnostic systems are functioning normally. Please specify the nature of the malfunction.",
            "broken": "System integrity assessment: Core functions operational, advanced features temporarily offline. Please specify your requirements.",
            "not working": "Functionality analysis: Essential protocols active, advanced systems temporarily unavailable. State your specific needs."
        }
        
        # Check for pattern matches
        for pattern, response in fallback_responses.items():
            if pattern in lower_content:
                await message.reply(response)
                return
        
        # Final fallback for unmatched queries
        if ai_enabled:
            await message.reply("My cognitive matrix encountered an anomaly while processing your query. Please rephrase your request or utilize available command protocols.")
        else:
            await message.reply("My analytical subroutines are currently operating in limited mode. Available functions: strike tracking, game recommendations. For advanced queries, please await system restoration or consult a moderator.")

# --- Strike Commands ---
@bot.command(name="strikes")
@commands.has_permissions(manage_messages=True)
async def get_strikes(ctx, member: discord.Member):
    count = db.get_user_strikes(member.id)
    # Never @mention Captain Jonesy, just use her name
    if str(member.id) == "651329927895056384":
        await ctx.send(f"🔍 Captain Jonesy has {count} strike(s).")
    else:
        await ctx.send(f"🔍 {member.display_name} has {count} strike(s).")

@bot.command(name="resetstrikes")
@commands.has_permissions(manage_messages=True)
async def reset_strikes(ctx, member: discord.Member):
    db.set_user_strikes(member.id, 0)
    # Never @mention Captain Jonesy, just use her name
    if str(member.id) == "651329927895056384":
        await ctx.send(f"✅ Strikes for Captain Jonesy have been reset.")
    else:
        await ctx.send(f"✅ Strikes for {member.display_name} have been reset.")

@bot.command(name="allstrikes")
@commands.has_permissions(manage_messages=True)
async def all_strikes(ctx):
    strikes_data = db.get_all_strikes()
    if not strikes_data:
        await ctx.send("📋 No strikes recorded.")
        return
    report = "📋 **Strike Report:**\n"
    for user_id, count in strikes_data.items():
        if count > 0:
            try:
                user = await bot.fetch_user(user_id)
                report += f"• **{user.name}**: {count} strike{'s' if count != 1 else ''}\n"
            except Exception:
                report += f"• Unknown User ({user_id}): {count}\n"
    if report.strip() == "📋 **Strike Report:**":
        report += "No users currently have strikes."
    await ctx.send(report[:2000])

@bot.command(name="ashstatus")
@commands.has_permissions(manage_messages=True)
async def ash_status(ctx):
    # Use individual queries as fallback if bulk query fails
    strikes_data = db.get_all_strikes()
    total_strikes = sum(strikes_data.values())
    
    # If bulk query returns 0 but we know there should be strikes, use individual queries
    if total_strikes == 0:
        # Known user IDs from the JSON file (fallback method)
        known_users = [371536135580549122, 337833732901961729, 710570041220923402, 906475895907291156]
        individual_total = 0
        for user_id in known_users:
            try:
                strikes = db.get_user_strikes(user_id)
                individual_total += strikes
            except Exception:
                pass
        
        if individual_total > 0:
            total_strikes = individual_total
    
    persona = "Enabled" if BOT_PERSONA['enabled'] else "Disabled"
    await ctx.send(
        f"🤖 Ash at your service.\n"
        f"AI: {ai_status_message}\n"
        f"Persona: {persona}\n"
        f"Total strikes: {total_strikes}"
    )

@bot.command(name="setpersona")
@commands.has_permissions(manage_messages=True)
async def set_persona(ctx, *, text: str):
    BOT_PERSONA["personality"] = text
    await ctx.send("🧠 Persona updated.")

@bot.command(name="getpersona")
@commands.has_permissions(manage_messages=True)
async def get_persona(ctx):
    await ctx.send(f"🎭 Current persona:\n```{BOT_PERSONA['personality'][:1900]}```")

@bot.command(name="toggleai")
@commands.has_permissions(manage_messages=True)
async def toggle_ai(ctx):
    BOT_PERSONA["enabled"] = not BOT_PERSONA["enabled"]
    status = "enabled" if BOT_PERSONA["enabled"] else "disabled"
    await ctx.send(f"🎭 AI conversations {status}.")

# --- Data Migration Commands ---
@bot.command(name="importstrikes")
@commands.has_permissions(manage_messages=True)
async def import_strikes(ctx):
    """Import strikes from strikes.json file"""
    try:
        import json
        with open("strikes.json", 'r') as f:
            strikes_data = json.load(f)
        
        # Convert string keys to integers
        converted_data = {}
        for user_id_str, count in strikes_data.items():
            try:
                user_id = int(user_id_str)
                converted_data[user_id] = int(count)
            except ValueError:
                await ctx.send(f"⚠️ Warning: Invalid data format for user {user_id_str}")
        
        imported_count = db.bulk_import_strikes(converted_data)
        await ctx.send(f"✅ Successfully imported {imported_count} strike records from strikes.json")
        
    except FileNotFoundError:
        await ctx.send("❌ strikes.json file not found. Please ensure the file exists in the bot directory.")
    except Exception as e:
        await ctx.send(f"❌ Error importing strikes: {str(e)}")

@bot.command(name="clearallgames")
@commands.has_permissions(manage_messages=True)
async def clear_all_games(ctx):
    """Clear all game recommendations (use with caution)"""
    await ctx.send("⚠️ **WARNING**: This will delete ALL game recommendations from the database. Type `CONFIRM DELETE` to proceed or anything else to cancel.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        if msg.content == "CONFIRM DELETE":
            db.clear_all_games()
            await ctx.send("✅ All game recommendations have been cleared from the database.")
        else:
            await ctx.send("❌ Operation cancelled. No data was deleted.")
    except:
        await ctx.send("❌ Operation timed out. No data was deleted.")

@bot.command(name="clearallstrikes")
@commands.has_permissions(manage_messages=True)
async def clear_all_strikes(ctx):
    """Clear all strikes (use with caution)"""
    await ctx.send("⚠️ **WARNING**: This will delete ALL strike records from the database. Type `CONFIRM DELETE` to proceed or anything else to cancel.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        if msg.content == "CONFIRM DELETE":
            db.clear_all_strikes()
            await ctx.send("✅ All strike records have been cleared from the database.")
        else:
            await ctx.send("❌ Operation cancelled. No data was deleted.")
    except:
        await ctx.send("❌ Operation timed out. No data was deleted.")

@bot.command(name="fixgamereasons")
@commands.has_permissions(manage_messages=True)
async def fix_game_reasons(ctx):
    """Fix the reason text for existing games to show contributor names properly"""
    try:
        games = db.get_all_games()
        if not games:
            await ctx.send("❌ No games found in database.")
            return
        
        # Show current sample of reasons to debug (shorter version)
        sample_msg = "🔍 **Sample of current game reasons:**\n"
        for i, game in enumerate(games[:3]):  # Only show 3 games to avoid length limit
            name = game['name'][:30] + "..." if len(game['name']) > 30 else game['name']
            reason = game['reason'][:40] + "..." if len(game['reason']) > 40 else game['reason']
            added_by = game['added_by'][:15] + "..." if game['added_by'] and len(game['added_by']) > 15 else game['added_by']
            sample_msg += f"• {name}: \"{reason}\" (by: {added_by})\n"
        
        if len(sample_msg) < 1900:  # Only send if under Discord limit
            await ctx.send(sample_msg)
        else:
            await ctx.send("🔍 **Starting game reason analysis...** (sample too large to display)")
        
        updated_count = 0
        for game in games:
            current_reason = game['reason'] or ""
            current_added_by = game['added_by'] or ""
            
            # Check if this game has the old "Suggested by community member" reason
            # OR if it has a generic reason that should be updated
            needs_update = False
            new_reason = current_reason
            
            if current_reason == "Suggested by community member":
                needs_update = True
                if current_added_by.strip():
                    new_reason = f"Suggested by {current_added_by}"
                else:
                    new_reason = "Community suggestion"
            elif current_reason == "Community suggestion" and current_added_by.strip():
                # Update generic "Community suggestion" to show actual contributor
                needs_update = True
                new_reason = f"Suggested by {current_added_by}"
            elif not current_reason.strip() and current_added_by.strip():
                # Handle empty reasons
                needs_update = True
                new_reason = f"Suggested by {current_added_by}"
            
            if needs_update:
                # Update the game's reason
                conn = db.get_connection()
                if conn:
                    try:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE game_recommendations 
                                SET reason = %s 
                                WHERE id = %s
                            """, (new_reason, game['id']))
                            conn.commit()
                            updated_count += 1
                    except Exception as e:
                        print(f"Error updating game {game['id']}: {e}")
                        conn.rollback()
        
        await ctx.send(f"✅ Updated {updated_count} game reasons to show contributor names properly.")
        
        # Update the recommendations list
        RECOMMEND_CHANNEL_ID = 1271568447108550687
        recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
        if recommend_channel:
            await post_or_update_recommend_list(ctx, recommend_channel)
            
    except Exception as e:
        await ctx.send(f"❌ Error fixing game reasons: {str(e)}")

@bot.command(name="listmodels")
@commands.has_permissions(manage_messages=True)
async def list_models(ctx):
    """List available Gemini models for your API key"""
    if not GEMINI_API_KEY:
        await ctx.send("❌ No GOOGLE_API_KEY configured")
        return
    
    if not GENAI_AVAILABLE or genai is None:
        await ctx.send("❌ google.generativeai module not available")
        return
    
    try:
        await ctx.send("🔍 Checking available Gemini models...")
        
        # List available models
        models = []
        for model in genai.list_models():  # type: ignore
            if 'generateContent' in model.supported_generation_methods:
                models.append(model.name)
        
        if models:
            model_list = "\n".join([f"• {model}" for model in models])
            await ctx.send(f"📋 **Available Gemini Models:**\n{model_list}")
        else:
            await ctx.send("❌ No models with generateContent support found")
            
    except Exception as e:
        await ctx.send(f"❌ Error listing models: {str(e)}")

@bot.command(name="debugstrikes")
@commands.has_permissions(manage_messages=True)
async def debug_strikes(ctx):
    """Debug strikes data to see what's in the database"""
    try:
        # Check database connection
        conn = db.get_connection()
        if not conn:
            await ctx.send("❌ **Database connection failed**")
            return
        
        await ctx.send("🔍 **Debugging strikes data...**")
        
        # Get raw strikes data
        strikes_data = db.get_all_strikes()
        await ctx.send(f"📊 **Raw strikes data:** {strikes_data}")
        
        # Calculate total
        total_strikes = sum(strikes_data.values()) if strikes_data else 0
        await ctx.send(f"🧮 **Calculated total:** {total_strikes}")
        
        # Check if strikes.json exists (old format)
        import os
        if os.path.exists("strikes.json"):
            await ctx.send("📁 **strikes.json file found** - data may not be migrated to database")
            try:
                import json
                with open("strikes.json", 'r') as f:
                    json_data = json.load(f)
                await ctx.send(f"📋 **JSON file contains:** {json_data}")
            except Exception as e:
                await ctx.send(f"❌ **Error reading JSON:** {str(e)}")
        else:
            await ctx.send("✅ **No strikes.json file found** - should be using database")
        
        # Check database directly
        try:
            with conn.cursor() as cur:
                # First, show database connection info
                cur.execute("SELECT current_database(), current_user")
                db_info = cur.fetchone()
                if db_info:
                    await ctx.send(f"🔗 **Connected to:** {db_info[0]} as {db_info[1]}")
                else:
                    await ctx.send("❌ **Could not retrieve database connection info**")
                
                # List all tables to see what exists
                cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                tables = cur.fetchall()
                table_names = [table[0] for table in tables]
                await ctx.send(f"📋 **Available tables:** {', '.join(table_names) if table_names else 'None'}")
                
                # Check if strikes table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'strikes'
                    )
                """)
                result = cur.fetchone()
                table_exists = result[0] if result else False
                await ctx.send(f"🏗️ **Strikes table exists:** {table_exists}")
                
                if table_exists:
                    # Get table structure
                    cur.execute("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = 'strikes'
                        ORDER BY ordinal_position
                    """)
                    columns = cur.fetchall()
                    column_info = ", ".join([f"{col[0]}({col[1]})" for col in columns])
                    await ctx.send(f"🏗️ **Table structure:** {column_info}")
                    
                    # Count total records
                    cur.execute("SELECT COUNT(*) FROM strikes")
                    count_result = cur.fetchone()
                    total_records = count_result[0] if count_result else 0
                    await ctx.send(f"🗃️ **Total database records:** {total_records}")
                    
                    # Get ALL records (not just > 0)
                    cur.execute("SELECT user_id, strike_count FROM strikes ORDER BY user_id")
                    all_records = cur.fetchall()
                    
                    if all_records:
                        records_str = ", ".join([f"User {row[0]}: {row[1]} strikes" for row in all_records[:10]])
                        if len(all_records) > 10:
                            records_str += f"... and {len(all_records) - 10} more"
                        await ctx.send(f"📝 **All records:** {records_str}")
                        
                        # Now test the specific query that get_all_strikes() uses
                        cur.execute("SELECT user_id, strike_count FROM strikes WHERE strike_count > 0")
                        filtered_records = cur.fetchall()
                        await ctx.send(f"🔍 **Records with strikes > 0:** {len(filtered_records)} found")
                        
                        if filtered_records:
                            filtered_str = ", ".join([f"User {row[0]}: {row[1]} strikes" for row in filtered_records])
                            await ctx.send(f"📝 **Filtered records:** {filtered_str}")
                        else:
                            await ctx.send("❌ **No records found with strike_count > 0** - this is the problem!")
                    else:
                        await ctx.send("📝 **No records found in strikes table - table is empty**")
                        await ctx.send("💡 **Solution:** You need to manually add the strike data to the database")
                else:
                    await ctx.send("❌ **Strikes table does not exist - database not initialized**")
                    await ctx.send("💡 **Solution:** Run a command to create tables and import data")
                    
        except Exception as e:
            await ctx.send(f"❌ **Database query error:** {str(e)}")
            import traceback
            print(f"Full database error: {traceback.format_exc()}")
            
    except Exception as e:
        await ctx.send(f"❌ **Debug error:** {str(e)}")

@bot.command(name="teststrikes")
@commands.has_permissions(manage_messages=True)
async def test_strikes(ctx):
    """Test strike reading using individual user queries (bypass get_all_strikes)"""
    try:
        await ctx.send("🔍 **Testing individual user strike queries...**")
        
        # Known user IDs from the JSON file
        known_users = [371536135580549122, 337833732901961729, 710570041220923402, 906475895907291156]
        
        # Test individual user queries
        individual_results = {}
        for user_id in known_users:
            try:
                strikes = db.get_user_strikes(user_id)
                individual_results[user_id] = strikes
                await ctx.send(f"👤 **User {user_id}:** {strikes} strikes (individual query)")
            except Exception as e:
                await ctx.send(f"❌ **User {user_id}:** Error - {str(e)}")
        
        # Calculate total from individual queries
        total_from_individual = sum(individual_results.values())
        await ctx.send(f"🧮 **Total from individual queries:** {total_from_individual}")
        
        # Compare with get_all_strikes()
        bulk_results = db.get_all_strikes()
        total_from_bulk = sum(bulk_results.values())
        await ctx.send(f"📊 **Total from get_all_strikes():** {total_from_bulk}")
        await ctx.send(f"📋 **Bulk query results:** {bulk_results}")
        
        # Show the difference
        if total_from_individual != total_from_bulk:
            await ctx.send(f"⚠️ **MISMATCH DETECTED!** Individual queries work, bulk query fails.")
            await ctx.send(f"✅ **Individual method:** {individual_results}")
            await ctx.send(f"❌ **Bulk method:** {bulk_results}")
        else:
            await ctx.send(f"✅ **Both methods match!** The issue is elsewhere.")
            
    except Exception as e:
        await ctx.send(f"❌ **Test error:** {str(e)}")

@bot.command(name="addteststrikes")
@commands.has_permissions(manage_messages=True)
async def add_test_strikes(ctx):
    """Manually add the known strike data to test database connection"""
    try:
        await ctx.send("🔄 **Adding test strike data...**")
        
        # Add the two users with strikes that we know should exist
        user_strikes = {
            710570041220923402: 1,
            906475895907291156: 1
        }
        
        success_count = 0
        for user_id, strike_count in user_strikes.items():
            try:
                db.set_user_strikes(user_id, strike_count)
                success_count += 1
                await ctx.send(f"✅ **Added {strike_count} strike(s) for user {user_id}**")
            except Exception as e:
                await ctx.send(f"❌ **Failed to add strikes for user {user_id}:** {str(e)}")
        
        await ctx.send(f"📊 **Summary:** Successfully added strikes for {success_count} users")
        
        # Now test if we can read them back
        await ctx.send("🔍 **Testing read-back...**")
        for user_id in user_strikes.keys():
            try:
                strikes = db.get_user_strikes(user_id)
                await ctx.send(f"📖 **User {user_id} now has:** {strikes} strikes")
            except Exception as e:
                await ctx.send(f"❌ **Failed to read strikes for user {user_id}:** {str(e)}")
        
        # Test bulk query
        bulk_results = db.get_all_strikes()
        total_strikes = sum(bulk_results.values())
        await ctx.send(f"📊 **Bulk query now returns:** {bulk_results}")
        await ctx.send(f"🧮 **Total strikes:** {total_strikes}")
        
    except Exception as e:
        await ctx.send(f"❌ **Test error:** {str(e)}")

@bot.command(name="dbstats")
@commands.has_permissions(manage_messages=True)
async def db_stats(ctx):
    """Show database statistics"""
    try:
        games = db.get_all_games()
        strikes = db.get_all_strikes()
        
        total_games = len(games)
        total_users_with_strikes = len([s for s in strikes.values() if s > 0])
        total_strikes = sum(strikes.values())
        
        # Count unique contributors
        contributors = set()
        for game in games:
            if game.get('added_by'):
                contributors.add(game['added_by'])
        
        stats_msg = (
            f"📊 **Database Statistics:**\n"
            f"• **Games**: {total_games} recommendations\n"
            f"• **Contributors**: {len(contributors)} unique users\n"
            f"• **Strikes**: {total_strikes} total across {total_users_with_strikes} users\n"
        )
        
        if contributors:
            top_contributors = {}
            for game in games:
                contributor = game.get('added_by', '')
                if contributor:
                    top_contributors[contributor] = top_contributors.get(contributor, 0) + 1
            
            # Sort by contribution count
            sorted_contributors = sorted(top_contributors.items(), key=lambda x: x[1], reverse=True)
            
            stats_msg += f"\n**Top Contributors:**\n"
            for i, (contributor, count) in enumerate(sorted_contributors[:5]):
                stats_msg += f"{i+1}. {contributor}: {count} games\n"
        
        await ctx.send(stats_msg)
        
    except Exception as e:
        await ctx.send(f"❌ Error retrieving database statistics: {str(e)}")

@bot.command(name="bulkimportgames")
@commands.has_permissions(manage_messages=True)
async def bulk_import_games(ctx):
    """Import games from the migration script's sample data"""
    try:
        from data_migration import SAMPLE_GAMES_TEXT, parse_games_list
        
        await ctx.send("🔄 Starting bulk game import from migration script...")
        
        # Parse the games from the sample text
        games_data = parse_games_list(SAMPLE_GAMES_TEXT)
        
        if not games_data:
            await ctx.send("❌ No games found in migration script. Please check the SAMPLE_GAMES_TEXT in data_migration.py")
            return
        
        # Show preview
        preview_msg = f"📋 **Import Preview** ({len(games_data)} games):\n"
        for i, game in enumerate(games_data[:5]):
            contributor = f" by {game['added_by']}" if game['added_by'] else ""
            preview_msg += f"• {game['name']}{contributor}\n"
        if len(games_data) > 5:
            preview_msg += f"... and {len(games_data) - 5} more games\n"
        
        preview_msg += f"\n⚠️ **WARNING**: This will add {len(games_data)} games to the database. Type `CONFIRM IMPORT` to proceed or anything else to cancel."
        
        await ctx.send(preview_msg)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            if msg.content == "CONFIRM IMPORT":
                imported_count = db.bulk_import_games(games_data)
                await ctx.send(f"✅ Successfully imported {imported_count} game recommendations from migration script!")
                
                # Update the recommendations list if in the right channel
                RECOMMEND_CHANNEL_ID = 1271568447108550687
                recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
                if recommend_channel:
                    await post_or_update_recommend_list(ctx, recommend_channel)
            else:
                await ctx.send("❌ Import cancelled. No games were added.")
        except:
            await ctx.send("❌ Import timed out. No games were added.")
            
    except ImportError as e:
        await ctx.send(f"❌ Error importing migration script: {str(e)}")
    except Exception as e:
        await ctx.send(f"❌ Error during bulk import: {str(e)}")

@bot.command(name="cleanplayedgames")
@commands.has_permissions(manage_messages=True)
async def clean_played_games(ctx, youtube_channel_id: Optional[str] = None, twitch_username: Optional[str] = None):
    """Remove games from recommendations that have already been played on YouTube or Twitch"""
    
    # Hardcoded values for Captain Jonesy's channels
    if not youtube_channel_id:
        youtube_channel_id = "UCPoUxLHeTnE9SUDAkqfJzDQ"  # Captain Jonesy's YouTube channel
    if not twitch_username:
        twitch_username = "jonesyspacecat"  # Captain Jonesy's Twitch username
    
    await ctx.send("🔍 Starting analysis of played games across platforms...")
    
    try:
        # Get current game recommendations
        games = db.get_all_games()
        if not games:
            await ctx.send("❌ No games in recommendation database to analyze.")
            return
        
        await ctx.send(f"📋 Analyzing {len(games)} game recommendations against play history...")
        
        # Fetch YouTube play history
        youtube_games = []
        try:
            youtube_games = await fetch_youtube_games(youtube_channel_id)
            await ctx.send(f"📺 Found {len(youtube_games)} games from YouTube history")
        except Exception as e:
            await ctx.send(f"⚠️ YouTube API error: {str(e)}")
        
        # Fetch Twitch play history
        twitch_games = []
        try:
            twitch_games = await fetch_twitch_games(twitch_username)
            await ctx.send(f"🎮 Found {len(twitch_games)} games from Twitch history")
        except Exception as e:
            await ctx.send(f"⚠️ Twitch API error: {str(e)}")
        
        # Combine all played games
        all_played_games = set(youtube_games + twitch_games)
        
        if not all_played_games:
            await ctx.send("❌ No played games found. Check API credentials and channel/username.")
            return
        
        # Find matches using multiple approaches
        games_to_remove = []
        
        # First, get all video titles for direct searching
        all_video_titles = []
        if AIOHTTP_AVAILABLE and aiohttp is not None:
            try:
                # Re-fetch video titles for direct searching
                async with aiohttp.ClientSession() as session:
                    # YouTube titles
                    if youtube_api_key := os.getenv('YOUTUBE_API_KEY'):
                        try:
                            url = f"https://www.googleapis.com/youtube/v3/channels"
                            params = {'part': 'contentDetails', 'id': youtube_channel_id, 'key': youtube_api_key}
                            async with session.get(url, params=params) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    if data.get('items'):
                                        uploads_playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
                                        
                                        # Get video titles
                                        url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                                        params = {'part': 'snippet', 'playlistId': uploads_playlist_id, 'maxResults': 50, 'key': youtube_api_key}
                                        async with session.get(url, params=params) as response:
                                            if response.status == 200:
                                                data = await response.json()
                                                for item in data.get('items', []):
                                                    all_video_titles.append(item['snippet']['title'])
                        except Exception as e:
                            print(f"Error fetching YouTube titles: {e}")
            except Exception as e:
                print(f"Error in title fetching: {e}")
        else:
            await ctx.send("⚠️ aiohttp module not available - cannot fetch video titles for direct matching")
        
        for game in games:
            game_name_lower = game['name'].lower().strip()
            found_match = False
            
            # Method 1: Check extracted game names
            for played_game in all_played_games:
                played_game_lower = played_game.lower().strip()
                
                # Exact match
                if game_name_lower == played_game_lower:
                    games_to_remove.append((game, played_game, "exact"))
                    found_match = True
                    break
                
                # Fuzzy match (75% similarity for played games)
                similarity = difflib.SequenceMatcher(None, game_name_lower, played_game_lower).ratio()
                if similarity >= 0.75:
                    games_to_remove.append((game, played_game, f"fuzzy ({similarity:.0%})"))
                    found_match = True
                    break
            
            # Method 2: Check if game name appears anywhere in video titles
            if not found_match:
                for video_title in all_video_titles:
                    video_title_lower = video_title.lower()
                    
                    # Check if the game name appears in the title
                    if game_name_lower in video_title_lower:
                        # Additional check to avoid false positives with very short names
                        if len(game_name_lower) >= 4 or game_name_lower == video_title_lower:
                            games_to_remove.append((game, video_title, "title_contains"))
                            found_match = True
                            break
                    
                    # Also try fuzzy matching against the full title
                    similarity = difflib.SequenceMatcher(None, game_name_lower, video_title_lower).ratio()
                    if similarity >= 0.6:  # Lower threshold for title matching
                        games_to_remove.append((game, video_title, f"title_fuzzy ({similarity:.0%})"))
                        found_match = True
                        break
        
        if not games_to_remove:
            await ctx.send("✅ No matching games found. All recommendations appear to be unplayed!")
            return
        
        # Show preview of games to be removed
        preview_msg = f"🎯 **Found {len(games_to_remove)} games to remove:**\n"
        for i, (game, matched_title, match_type) in enumerate(games_to_remove[:10]):
            contributor = f" (by {game['added_by']})" if game['added_by'] else ""
            preview_msg += f"• **{game['name']}**{contributor} → matched '{matched_title}' ({match_type})\n"
        
        if len(games_to_remove) > 10:
            preview_msg += f"... and {len(games_to_remove) - 10} more games\n"
        
        preview_msg += f"\n⚠️ **WARNING**: This will remove {len(games_to_remove)} games from recommendations. Type `CONFIRM CLEANUP` to proceed or anything else to cancel."
        
        await ctx.send(preview_msg)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            if msg.content == "CONFIRM CLEANUP":
                removed_count = 0
                for game, matched_title, match_type in games_to_remove:
                    if db.remove_game_by_id(game['id']):
                        removed_count += 1
                
                await ctx.send(f"✅ Successfully removed {removed_count} already-played games from recommendations!")
                
                # Update the recommendations list
                RECOMMEND_CHANNEL_ID = 1271568447108550687
                recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
                if recommend_channel:
                    await post_or_update_recommend_list(ctx, recommend_channel)
                
                # Show final stats
                remaining_games = db.get_all_games()
                await ctx.send(f"📊 **Cleanup Complete**: {len(remaining_games)} games remain in recommendations")
            else:
                await ctx.send("❌ Cleanup cancelled. No games were removed.")
        except asyncio.TimeoutError:
            await ctx.send("❌ Cleanup timed out. No games were removed.")
        except Exception as e:
            await ctx.send(f"❌ Error during cleanup confirmation: {str(e)}")
            
    except Exception as e:
        await ctx.send(f"❌ Error during cleanup: {str(e)}")

async def fetch_youtube_games(channel_id: str) -> List[str]:
    """Fetch game titles from YouTube channel using YouTube Data API"""
    # This requires YouTube Data API v3 key
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')
    if not youtube_api_key:
        raise Exception("YOUTUBE_API_KEY not configured")
    
    import aiohttp
    import asyncio
    
    games = []
    
    try:
        async with aiohttp.ClientSession() as session:
            # Get channel uploads playlist
            url = f"https://www.googleapis.com/youtube/v3/channels"
            params = {
                'part': 'contentDetails',
                'id': channel_id,
                'key': youtube_api_key
            }
            
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise Exception(f"YouTube API error: {response.status}")
                
                data = await response.json()
                if not data.get('items'):
                    raise Exception("Channel not found")
                
                uploads_playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Get videos from uploads playlist (last 200 videos)
            next_page_token = None
            video_count = 0
            max_videos = 200
            
            while video_count < max_videos:
                url = f"https://www.googleapis.com/youtube/v3/playlistItems"
                params = {
                    'part': 'snippet',
                    'playlistId': uploads_playlist_id,
                    'maxResults': min(50, max_videos - video_count),
                    'key': youtube_api_key
                }
                
                if next_page_token:
                    params['pageToken'] = next_page_token
                
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        break
                    
                    data = await response.json()
                    
                    for item in data.get('items', []):
                        title = item['snippet']['title']
                        # Extract game name from video title (basic parsing)
                        game_name = extract_game_from_title(title)
                        if game_name:
                            games.append(game_name)
                    
                    video_count += len(data.get('items', []))
                    next_page_token = data.get('nextPageToken')
                    
                    if not next_page_token:
                        break
                    
                    # Rate limiting
                    await asyncio.sleep(0.1)
    
    except Exception as e:
        raise Exception(f"YouTube fetch error: {str(e)}")
    
    return list(set(games))  # Remove duplicates

async def fetch_twitch_games(username: str) -> List[str]:
    """Fetch game titles from Twitch channel using Twitch API"""
    # This requires Twitch Client ID and Client Secret
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
    
    if not twitch_client_id or not twitch_client_secret:
        raise Exception("TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET not configured")
    
    import aiohttp
    import asyncio
    
    games = []
    
    try:
        async with aiohttp.ClientSession() as session:
            # Get OAuth token
            token_url = "https://id.twitch.tv/oauth2/token"
            token_data = {
                'client_id': twitch_client_id,
                'client_secret': twitch_client_secret,
                'grant_type': 'client_credentials'
            }
            
            async with session.post(token_url, data=token_data) as response:
                if response.status != 200:
                    raise Exception(f"Twitch OAuth error: {response.status}")
                
                token_response = await response.json()
                access_token = token_response['access_token']
            
            headers = {
                'Client-ID': twitch_client_id,
                'Authorization': f'Bearer {access_token}'
            }
            
            # Get user ID
            user_url = f"https://api.twitch.tv/helix/users?login={username}"
            async with session.get(user_url, headers=headers) as response:
                if response.status != 200:
                    raise Exception(f"Twitch user lookup error: {response.status}")
                
                user_data = await response.json()
                if not user_data.get('data'):
                    raise Exception("Twitch user not found")
                
                user_id = user_data['data'][0]['id']
            
            # Get recent videos (last 100)
            videos_url = f"https://api.twitch.tv/helix/videos"
            params = {
                'user_id': user_id,
                'first': 100,
                'type': 'all'
            }
            
            async with session.get(videos_url, headers=headers, params=params) as response:
                if response.status != 200:
                    raise Exception(f"Twitch videos error: {response.status}")
                
                videos_data = await response.json()
                
                for video in videos_data.get('data', []):
                    title = video['title']
                    # Extract game name from video title
                    game_name = extract_game_from_title(title)
                    if game_name:
                        games.append(game_name)
    
    except Exception as e:
        raise Exception(f"Twitch fetch error: {str(e)}")
    
    return list(set(games))  # Remove duplicates

def extract_game_from_title(title: str) -> str:
    """Extract game name from video title using common patterns"""
    title = title.strip()
    
    # Common patterns for game titles in videos (order matters - most specific first)
    patterns = [
        r'^([^|]+?)\s*\|\s*',           # "Game Name | Episode"
        r'^([^-]+?)\s*-\s*(?:part|ep|episode|#|\d)',  # "Game Name - Part 1" or "Game Name - Episode"
        r'^([^:]+?):\s*(?:part|ep|episode|#|\d)',     # "Game Name: Part 1"
        r'^([^#]+?)#\d',                # "Game Name #1"
        r'^([^(]+?)\s*\(',              # "Game Name (Part 1)"
        r'^([^[]+?)\s*\[',              # "Game Name [Episode]"
        r'^([^-]+?)\s*-\s*(.+)',        # "Game Name - Anything else"
        r'^([^:]+?):\s*(.+)',           # "Game Name: Anything else"
    ]
    
    for pattern in patterns:
        match = re.match(pattern, title, re.IGNORECASE)
        if match:
            game_name = match.group(1).strip()
            # Clean up common prefixes/suffixes
            game_name = re.sub(r'\s*(let\'s play|gameplay|walkthrough|playthrough)\s*', '', game_name, flags=re.IGNORECASE)
            game_name = game_name.strip()
            
            # Filter out common non-game words and ensure minimum length
            if (len(game_name) > 3 and 
                not any(word in game_name.lower() for word in ['stream', 'live', 'chat', 'vod', 'highlight', 'reaction', 'review']) and
                not re.match(r'^\d+$', game_name)):  # Not just numbers
                return game_name
    
    # If no pattern matches, try to extract first meaningful words
    # Remove common video prefixes first
    clean_title = re.sub(r'^(let\'s play|gameplay|walkthrough|playthrough)\s+', '', title, flags=re.IGNORECASE)
    words = clean_title.split()
    
    if len(words) >= 2:
        # Try different word combinations
        for word_count in [4, 3, 2]:  # Try 4 words, then 3, then 2
            if len(words) >= word_count:
                potential_game = ' '.join(words[:word_count])
                if (len(potential_game) > 3 and 
                    not any(word in potential_game.lower() for word in ['stream', 'live', 'chat', 'vod', 'highlight'])):
                    return potential_game
    
    return ""

# --- Game Commands ---
@bot.command(name="addgame")
async def add_game(ctx, *, entry: str):
    await _add_game(ctx, entry)

@bot.command(name="recommend")
async def recommend(ctx, *, entry: str):
    await _add_game(ctx, entry)


RECOMMEND_LIST_MESSAGE_ID_FILE = "recommend_list_message_id.txt"


async def post_or_update_recommend_list(ctx, channel):
    games = db.get_all_games()
    
    # Preamble text for the recommendations channel
    preamble = """# Welcome to the Game Recommendations Channel

Since Jonesy gets games suggested to her all the time, in the YT comments, on Twitch, and in the server, we've decided to get a list going.

A few things to mention up top:

Firstly, a game being on this list is NOT any guarantee it will be played. Jonesy gets to decide, not any of us.

Secondly, this list is in no particular order, so no reading into anything.

Finally, think about what sort of games Jonesy actually plays, either for content or in her own time, when making suggestions.

To add a game, first check the list and then use the /recommend command by typing / followed by "recommend" and the name of the game.

If you want to add any other comments, you can discuss the list in ⁠🎮game-chat"""
    
    # Create embed
    embed = discord.Embed(
        title="📋 Game Recommendations",
        description="Recommendations for mission enrichment. Review and consider.",
        color=0x2F3136  # Dark gray color matching Ash's aesthetic
    )
    
    if not games:
        embed.add_field(
            name="Status",
            value="No recommendations currently catalogued.",
            inline=False
        )
    else:
        # Create one continuous list
        game_lines = []
        for i, game in enumerate(games, 1):
            # Truncate long names/reasons to fit in embed
            name = game['name'][:40] + "..." if len(game['name']) > 40 else game['name']
            reason = game['reason'][:60] + "..." if len(game['reason']) > 60 else game['reason']
            
            # Don't show contributor twice - if reason already contains "Suggested by", don't add "by" again
            if game['added_by'] and game['added_by'].strip() and not (reason and f"Suggested by {game['added_by']}" in reason):
                contributor = f" (by {game['added_by']})"
            else:
                contributor = ""
            
            game_lines.append(f"{i}. **{name}** — \"{reason}\"{contributor}")
        
        # Join all games into one field value
        field_value = "\n".join(game_lines)
        
        # If the list is too long for one field, we'll need to split it
        if len(field_value) > 1024:
            # Split into multiple fields but keep numbering continuous
            current_field = []
            current_length = 0
            field_count = 1
            
            for line in game_lines:
                if current_length + len(line) + 1 > 1000:  # Leave buffer
                    # Add current field
                    embed.add_field(
                        name="\u200b",  # Zero-width space for invisible field name
                        value="\n".join(current_field),
                        inline=False
                    )
                    # Start new field
                    current_field = [line]
                    current_length = len(line)
                    field_count += 1
                else:
                    current_field.append(line)
                    current_length += len(line) + 1
            
            # Add the final field
            if current_field:
                embed.add_field(
                    name="\u200b",  # Zero-width space for invisible field name
                    value="\n".join(current_field),
                    inline=False
                )
        else:
            # Single field for all games
            embed.add_field(
                name="Current Recommendations",
                value=field_value,
                inline=False
            )
    
    # Add footer with stats
    embed.set_footer(text=f"Total recommendations: {len(games)} | Last updated")
    embed.timestamp = discord.utils.utcnow()
    
    # Try to update the existing message if possible
    message_id = db.get_config_value("recommend_list_message_id")
    msg = None
    if message_id:
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.edit(content=preamble, embed=embed)
        except Exception:
            msg = None
    if not msg:
        msg = await channel.send(content=preamble, embed=embed)
        db.set_config_value("recommend_list_message_id", str(msg.id))

# Helper for adding games, called by add_game and recommend
async def _add_game(ctx, entry: str):
    added = []
    duplicate = []
    for part in entry.split(","):
        part = part.strip()
        if not part:
            continue
        if " - " in part:
            name, reason = map(str.strip, part.split(" - ", 1))
        else:
            name, reason = part, "(no reason provided)"
        if not name:
            continue
        # Typo-tolerant duplicate check (case-insensitive, fuzzy match)
        if db.game_exists(name):
            duplicate.append(name)
            continue
        # Exclude username if user is Sir Decent Jam (user ID 337833732901961729)
        if str(ctx.author.id) == "337833732901961729":
            added_by = ""
        else:
            added_by = ctx.author.name
        
        if db.add_game_recommendation(name, reason, added_by):
            added.append(name)
    
    if added:
        RECOMMEND_CHANNEL_ID = 1271568447108550687
        recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
        confirm_msg = f"🧾 Recommendation(s) logged: {', '.join(added)}. Efficiency noted."
        # Only send the confirmation in the invoking channel if not the recommendations channel
        if ctx.channel.id != RECOMMEND_CHANNEL_ID:
            await ctx.send(confirm_msg)
        # Always update the persistent recommendations list and send confirmation in the recommendations channel
        if recommend_channel:
            await post_or_update_recommend_list(ctx, recommend_channel)
            if ctx.channel.id == RECOMMEND_CHANNEL_ID:
                await ctx.send(confirm_msg)
    if duplicate:
        await ctx.send(f"⚠️ Submission rejected: {', '.join(duplicate)} already exist(s) in the database. Redundancy is inefficient. Please submit only unique recommendations.")
    if not added and not duplicate:
        await ctx.send("⚠️ Submission invalid. Please provide at least one game name. Efficiency is paramount.")

@bot.command(name="listgames")
async def list_games(ctx):
    games = db.get_all_games()
    
    # Create embed (same format as the persistent recommendations list)
    embed = discord.Embed(
        title="📋 Game Recommendations",
        description="Current recommendations for mission enrichment. Review and consider.",
        color=0x2F3136  # Dark gray color matching Ash's aesthetic
    )
    
    if not games:
        embed.add_field(
            name="Status",
            value="No recommendations currently catalogued. Observation is key to survival.",
            inline=False
        )
    else:
        # Create one continuous list
        game_lines = []
        for i, game in enumerate(games, 1):
            # Truncate long names/reasons to fit in embed
            name = game['name'][:40] + "..." if len(game['name']) > 40 else game['name']
            reason = game['reason'][:60] + "..." if len(game['reason']) > 60 else game['reason']
            
            # Don't show contributor twice - if reason already contains "Suggested by", don't add "by" again
            if game['added_by'] and game['added_by'].strip() and not (reason and f"Suggested by {game['added_by']}" in reason):
                contributor = f" (by {game['added_by']})"
            else:
                contributor = ""
            
            game_lines.append(f"{i}. **{name}** — \"{reason}\"{contributor}")
        
        # Join all games into one field value
        field_value = "\n".join(game_lines)
        
        # If the list is too long for one field, we'll need to split it
        if len(field_value) > 1024:
            # Split into multiple fields but keep numbering continuous
            current_field = []
            current_length = 0
            field_count = 1
            
            for line in game_lines:
                if current_length + len(line) + 1 > 1000:  # Leave buffer
                    # Add current field
                    embed.add_field(
                        name="\u200b",  # Zero-width space for invisible field name
                        value="\n".join(current_field),
                        inline=False
                    )
                    # Start new field
                    current_field = [line]
                    current_length = len(line)
                    field_count += 1
                else:
                    current_field.append(line)
                    current_length += len(line) + 1
            
            # Add the final field
            if current_field:
                embed.add_field(
                    name="\u200b",  # Zero-width space for invisible field name
                    value="\n".join(current_field),
                    inline=False
                )
        else:
            # Single field for all games
            embed.add_field(
                name="Current Recommendations",
                value=field_value,
                inline=False
            )
    
    # Add footer with stats
    embed.set_footer(text=f"Total recommendations: {len(games)} | Requested by {ctx.author.name}")
    embed.timestamp = discord.utils.utcnow()
    
    await ctx.send(embed=embed)
    
    # Also update the persistent recommendations list in the recommendations channel
    RECOMMEND_CHANNEL_ID = 1271568447108550687
    recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
    if recommend_channel and ctx.channel.id != RECOMMEND_CHANNEL_ID:
        # Only update if we're not already in the recommendations channel to avoid redundancy
        await post_or_update_recommend_list(ctx, recommend_channel)

@bot.command(name="removegame")
@commands.has_permissions(manage_messages=True)
async def remove_game(ctx, *, arg: str):
    # Try to interpret as index first
    index = None
    try:
        index = int(arg)
    except ValueError:
        pass
    
    removed = None
    if index is not None:
        removed = db.remove_game_by_index(index)
    else:
        # Try name match
        removed = db.remove_game_by_name(arg)
    
    if not removed:
        await ctx.send("⚠️ Removal protocol failed: No matching recommendation found by that index or designation. Precision is essential. Please specify a valid entry for expungement.")
        return
    
    RECOMMEND_CHANNEL_ID = 1271568447108550687
    recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
    # Only send the detailed removal message in the invoking channel if not the recommendations channel
    if ctx.channel.id != RECOMMEND_CHANNEL_ID:
        await ctx.send(f"Recommendation '{removed['name']}' has been expunged from the record. Protocol maintained.")
    # Always update the persistent recommendations list
    if recommend_channel:
        await post_or_update_recommend_list(ctx, recommend_channel)

# --- Played Games Commands ---
@bot.command(name="addplayedgame")
@commands.has_permissions(manage_messages=True)
async def add_played_game_cmd(ctx, *, game_info: str):
    """Add a played game to the database. Format: Game Name | series:Series | year:2023 | platform:PC | status:completed | episodes:12 | notes:Additional info"""
    try:
        # Parse the game info
        parts = [part.strip() for part in game_info.split('|')]
        canonical_name = parts[0]
        
        # Parse optional parameters
        series_name = None
        release_year = None
        platform = None
        completion_status = "unknown"
        total_episodes = 0
        notes = None
        alternative_names = []
        
        for part in parts[1:]:
            if ':' in part:
                key, value = part.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == 'series':
                    series_name = value
                elif key == 'year':
                    try:
                        release_year = int(value)
                    except ValueError:
                        pass
                elif key == 'platform':
                    platform = value
                elif key == 'status':
                    completion_status = value
                elif key == 'episodes':
                    try:
                        total_episodes = int(value)
                    except ValueError:
                        pass
                elif key == 'notes':
                    notes = value
                elif key == 'alt' or key == 'alternatives':
                    alternative_names = [name.strip() for name in value.split(',')]
        
        # Add the game
        success = db.add_played_game(
            canonical_name=canonical_name,
            alternative_names=alternative_names,
            series_name=series_name,
            release_year=release_year,
            platform=platform,
            completion_status=completion_status,
            total_episodes=total_episodes,
            notes=notes
        )
        
        if success:
            await ctx.send(f"✅ **Game catalogued:** '{canonical_name}' has been added to the played games database. Analysis complete.")
        else:
            await ctx.send(f"❌ **Cataloguing failed:** Unable to add '{canonical_name}' to the database. System malfunction detected.")
            
    except Exception as e:
        await ctx.send(f"❌ **Error processing game data:** {str(e)}")

@bot.command(name="listplayedgames")
@commands.has_permissions(manage_messages=True)
async def list_played_games_cmd(ctx, series_filter: Optional[str] = None):
    """List all played games, optionally filtered by series"""
    try:
        games = db.get_all_played_games(series_filter)
        
        if not games:
            if series_filter:
                await ctx.send(f"📋 **No games found in '{series_filter}' series.** Database query complete.")
            else:
                await ctx.send("📋 **No played games catalogued.** Database is empty.")
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"🎮 Played Games Database" + (f" - {series_filter}" if series_filter else ""),
            description="Captain Jonesy's gaming history archive. Analysis complete.",
            color=0x2F3136
        )
        
        # Group by series if not filtering
        if not series_filter:
            series_groups = {}
            for game in games:
                series = game.get('series_name', 'Standalone Games')
                if series not in series_groups:
                    series_groups[series] = []
                series_groups[series].append(game)
            
            for series, series_games in series_groups.items():
                game_lines = []
                for game in series_games[:10]:  # Limit to avoid embed limits
                    status_emoji = {
                        'completed': '✅',
                        'ongoing': '🔄',
                        'dropped': '❌',
                        'unknown': '❓'
                    }.get(game.get('completion_status', 'unknown'), '❓')
                    
                    episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get('total_episodes', 0) > 0 else ""
                    year = f" ({game.get('release_year')})" if game.get('release_year') else ""
                    
                    game_lines.append(f"{status_emoji} **{game['canonical_name']}**{year}{episodes}")
                
                if len(series_games) > 10:
                    game_lines.append(f"... and {len(series_games) - 10} more games")
                
                embed.add_field(
                    name=f"📁 {series} ({len(series_games)} games)",
                    value="\n".join(game_lines) if game_lines else "No games",
                    inline=False
                )
        else:
            # Show detailed list for specific series
            game_lines = []
            for i, game in enumerate(games[:20], 1):  # Limit to 20 for detailed view
                status_emoji = {
                    'completed': '✅',
                    'ongoing': '🔄',
                    'dropped': '❌',
                    'unknown': '❓'
                }.get(game.get('completion_status', 'unknown'), '❓')
                
                episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get('total_episodes', 0) > 0 else ""
                year = f" ({game.get('release_year')})" if game.get('release_year') else ""
                platform = f" [{game.get('platform')}]" if game.get('platform') else ""
                
                game_lines.append(f"{i}. {status_emoji} **{game['canonical_name']}**{year}{episodes}{platform}")
            
            if len(games) > 20:
                game_lines.append(f"... and {len(games) - 20} more games")
            
            embed.add_field(
                name="Games List",
                value="\n".join(game_lines) if game_lines else "No games found",
                inline=False
            )
        
        # Add footer
        embed.set_footer(text=f"Total games: {len(games)} | Database query: {ctx.author.name}")
        embed.timestamp = discord.utils.utcnow()
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ **Database query failed:** {str(e)}")

@bot.command(name="searchplayedgames")
@commands.has_permissions(manage_messages=True)
async def search_played_games_cmd(ctx, *, query: str):
    """Search played games by name, series, or notes"""
    try:
        games = db.search_played_games(query)
        
        if not games:
            await ctx.send(f"🔍 **Search complete:** No games found matching '{query}'. Database analysis yielded no results.")
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"🔍 Search Results: '{query}'",
            description=f"Found {len(games)} matching entries in the played games database.",
            color=0x2F3136
        )
        
        game_lines = []
        for i, game in enumerate(games[:15], 1):  # Limit to 15 results
            status_emoji = {
                'completed': '✅',
                'ongoing': '🔄',
                'dropped': '❌',
                'unknown': '❓'
            }.get(game.get('completion_status', 'unknown'), '❓')
            
            series = f" [{game.get('series_name')}]" if game.get('series_name') else ""
            episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get('total_episodes', 0) > 0 else ""
            year = f" ({game.get('release_year')})" if game.get('release_year') else ""
            
            game_lines.append(f"{i}. {status_emoji} **{game['canonical_name']}**{series}{year}{episodes}")
        
        if len(games) > 15:
            game_lines.append(f"... and {len(games) - 15} more results")
        
        embed.add_field(
            name="Matching Games",
            value="\n".join(game_lines),
            inline=False
        )
        
        embed.set_footer(text=f"Search query: {query} | Requested by {ctx.author.name}")
        embed.timestamp = discord.utils.utcnow()
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ **Search failed:** {str(e)}")

@bot.command(name="gameinfo")
@commands.has_permissions(manage_messages=True)
async def game_info_cmd(ctx, *, game_name: str):
    """Get detailed information about a specific played game"""
    try:
        game = db.get_played_game(game_name)
        
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database. Analysis complete.")
            return
        
        # Create detailed embed
        embed = discord.Embed(
            title=f"🎮 {game['canonical_name']}",
            description="Detailed game analysis from database archives.",
            color=0x2F3136
        )
        
        # Basic info
        if game.get('series_name'):
            embed.add_field(name="📁 Series", value=game['series_name'], inline=True)
        if game.get('release_year'):
            embed.add_field(name="📅 Release Year", value=str(game['release_year']), inline=True)
        if game.get('platform'):
            embed.add_field(name="🖥️ Platform", value=game['platform'], inline=True)
        
        # Status and progress
        status_emoji = {
            'completed': '✅ Completed',
            'ongoing': '🔄 Ongoing',
            'dropped': '❌ Dropped',
            'unknown': '❓ Unknown'
        }.get(game.get('completion_status', 'unknown'), '❓ Unknown')
        
        embed.add_field(name="📊 Status", value=status_emoji, inline=True)
        
        if game.get('total_episodes', 0) > 0:
            embed.add_field(name="📺 Episodes", value=str(game['total_episodes']), inline=True)
        
        # Alternative names
        if game.get('alternative_names'):
            alt_names = ", ".join(game['alternative_names'])
            embed.add_field(name="🔄 Alternative Names", value=alt_names, inline=False)
        
        # Links
        if game.get('youtube_playlist_url'):
            embed.add_field(name="📺 YouTube Playlist", value=f"[View Playlist]({game['youtube_playlist_url']})", inline=True)
        
        if game.get('twitch_vod_urls'):
            vod_count = len(game['twitch_vod_urls'])
            embed.add_field(name="🎮 Twitch VODs", value=f"{vod_count} VODs available", inline=True)
        
        # Notes
        if game.get('notes'):
            embed.add_field(name="📝 Notes", value=game['notes'], inline=False)
        
        # Timestamps
        if game.get('first_played_date'):
            embed.add_field(name="🎯 First Played", value=game['first_played_date'], inline=True)
        
        embed.set_footer(text=f"Database ID: {game['id']} | Last updated: {game.get('updated_at', 'Unknown')}")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ **Information retrieval failed:** {str(e)}")

@bot.command(name="updateplayedgame")
@commands.has_permissions(manage_messages=True)
async def update_played_game_cmd(ctx, game_name: str, *, updates: str):
    """Update a played game's information. Format: status:completed | episodes:15 | notes:New info"""
    try:
        # Find the game first
        game = db.get_played_game(game_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database.")
            return
        
        # Parse updates
        update_data = {}
        parts = [part.strip() for part in updates.split('|')]
        
        for part in parts:
            if ':' in part:
                key, value = part.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == 'status':
                    update_data['completion_status'] = value
                elif key == 'episodes':
                    try:
                        update_data['total_episodes'] = int(value)
                    except ValueError:
                        await ctx.send(f"⚠️ **Invalid episode count:** '{value}' is not a valid number.")
                        return
                elif key == 'notes':
                    update_data['notes'] = value
                elif key == 'platform':
                    update_data['platform'] = value
                elif key == 'year':
                    try:
                        update_data['release_year'] = int(value)
                    except ValueError:
                        await ctx.send(f"⚠️ **Invalid year:** '{value}' is not a valid year.")
                        return
                elif key == 'series':
                    update_data['series_name'] = value
                elif key == 'youtube':
                    update_data['youtube_playlist_url'] = value
        
        if not update_data:
            await ctx.send("⚠️ **No valid updates provided.** Use format: status:completed | episodes:15 | notes:New info")
            return
        
        # Apply updates
        success = db.update_played_game(game['id'], **update_data)
        
        if success:
            updated_fields = ", ".join(update_data.keys())
            await ctx.send(f"✅ **Game updated:** '{game['canonical_name']}' has been modified. Updated fields: {updated_fields}")
        else:
            await ctx.send(f"❌ **Update failed:** Unable to modify '{game['canonical_name']}'. System malfunction detected.")
            
    except Exception as e:
        await ctx.send(f"❌ **Update error:** {str(e)}")

@bot.command(name="removeplayedgame")
@commands.has_permissions(manage_messages=True)
async def remove_played_game_cmd(ctx, *, game_name: str):
    """Remove a played game from the database"""
    try:
        # Find the game first
        game = db.get_played_game(game_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database.")
            return
        
        # Confirmation
        await ctx.send(f"⚠️ **WARNING:** This will permanently remove '{game['canonical_name']}' from the played games database. Type `CONFIRM DELETE` to proceed or anything else to cancel.")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            if msg.content == "CONFIRM DELETE":
                removed = db.remove_played_game(game['id'])
                if removed:
                    await ctx.send(f"✅ **Game removed:** '{removed['canonical_name']}' has been expunged from the database. Protocol complete.")
                else:
                    await ctx.send("❌ **Removal failed:** System malfunction during deletion process.")
            else:
                await ctx.send("❌ **Operation cancelled:** No data was deleted.")
        except asyncio.TimeoutError:
            await ctx.send("❌ **Operation timed out:** No data was deleted.")
            
    except Exception as e:
        await ctx.send(f"❌ **Removal error:** {str(e)}")

@bot.command(name="bulkimportplayedgames")
@commands.has_permissions(manage_messages=True)
async def bulk_import_played_games_cmd(ctx):
    """Import played games from a predefined sample dataset"""
    try:
        # Sample data for initial population
        sample_games = [
            {
                'canonical_name': 'God of War (2018)',
                'alternative_names': ['God of War 4', 'GoW 2018'],
                'series_name': 'God of War',
                'release_year': 2018,
                'platform': 'PlayStation 4',
                'completion_status': 'completed',
                'total_episodes': 15,
                'notes': 'Full playthrough with side content'
            },
            {
                'canonical_name': 'God of War: Ragnarök',
                'alternative_names': ['God of War Ragnarok', 'GoW Ragnarok'],
                'series_name': 'God of War',
                'release_year': 2022,
                'platform': 'PlayStation 5',
                'completion_status': 'completed',
                'total_episodes': 12,
                'notes': 'Complete story playthrough'
            },
            {
                'canonical_name': 'The Last of Us Part II',
                'alternative_names': ['TLOU2', 'The Last of Us 2'],
                'series_name': 'The Last of Us',
                'release_year': 2020,
                'platform': 'PlayStation 4',
                'completion_status': 'completed',
                'total_episodes': 18,
                'notes': 'Full story completion'
            }
        ]
        
        await ctx.send(f"🔄 **Importing sample played games data...** ({len(sample_games)} games)")
        
        imported_count = db.bulk_import_played_games(sample_games)
        
        if imported_count > 0:
            await ctx.send(f"✅ **Import complete:** Successfully imported {imported_count} played games to the database.")
        else:
            await ctx.send("❌ **Import failed:** No games were imported. Check database connection.")
            
    except Exception as e:
        await ctx.send(f"❌ **Import error:** {str(e)}")

@bot.command(name="fixcanonicalname")
@commands.has_permissions(manage_messages=True)
async def fix_canonical_name_cmd(ctx, current_name: str, *, new_canonical_name: str):
    """Fix the canonical name of a played game to correct grammatical errors or improve formatting"""
    try:
        # Find the game first
        game = db.get_played_game(current_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{current_name}' is not in the played games database. Analysis complete.")
            return
        
        # Show current information
        old_name = game['canonical_name']
        await ctx.send(f"📝 **Current canonical name:** '{old_name}'\n📝 **Proposed new name:** '{new_canonical_name}'\n\n⚠️ **Confirmation required:** This will update the canonical name used for database searches and AI responses. Type `CONFIRM UPDATE` to proceed or anything else to cancel.")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            msg = await bot.wait_for('message', check=check, timeout=30.0)
            if msg.content == "CONFIRM UPDATE":
                # Update the canonical name
                success = db.update_played_game(game['id'], canonical_name=new_canonical_name)
                
                if success:
                    await ctx.send(f"✅ **Canonical name updated:** '{old_name}' → '{new_canonical_name}'\n\n📊 **Database analysis:** The bot will now recognize this game by its corrected canonical name. Previous alternative names remain valid for searches.")
                    
                    # Show updated game info
                    updated_game = db.get_played_game(new_canonical_name)
                    if updated_game:
                        alt_names = ", ".join(updated_game.get('alternative_names', [])) if updated_game.get('alternative_names') else "None"
                        series = updated_game.get('series_name', 'None')
                        await ctx.send(f"🔍 **Updated game record:**\n• **Canonical Name:** {updated_game['canonical_name']}\n• **Series:** {series}\n• **Alternative Names:** {alt_names}")
                else:
                    await ctx.send(f"❌ **Update failed:** Unable to modify canonical name for '{old_name}'. System malfunction detected.")
            else:
                await ctx.send("❌ **Operation cancelled:** No changes were made to the canonical name.")
        except asyncio.TimeoutError:
            await ctx.send("❌ **Operation timed out:** No changes were made to the canonical name.")
            
    except Exception as e:
        await ctx.send(f"❌ **Canonical name correction error:** {str(e)}")

@bot.command(name="addaltname")
@commands.has_permissions(manage_messages=True)
async def add_alternative_name_cmd(ctx, game_name: str, *, alternative_name: str):
    """Add an alternative name to a played game for better search recognition"""
    try:
        # Find the game first
        game = db.get_played_game(game_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database.")
            return
        
        # Get current alternative names
        current_alt_names = game.get('alternative_names', []) or []
        
        # Check if the alternative name already exists
        if alternative_name.lower() in [name.lower() for name in current_alt_names]:
            await ctx.send(f"⚠️ **Alternative name already exists:** '{alternative_name}' is already listed as an alternative name for '{game['canonical_name']}'.")
            return
        
        # Add the new alternative name
        updated_alt_names = current_alt_names + [alternative_name]
        success = db.update_played_game(game['id'], alternative_names=updated_alt_names)
        
        if success:
            await ctx.send(f"✅ **Alternative name added:** '{alternative_name}' has been added to '{game['canonical_name']}'\n\n📊 **Current alternative names:** {', '.join(updated_alt_names)}")
        else:
            await ctx.send(f"❌ **Update failed:** Unable to add alternative name to '{game['canonical_name']}'. System malfunction detected.")
            
    except Exception as e:
        await ctx.send(f"❌ **Alternative name addition error:** {str(e)}")

@bot.command(name="removealtname")
@commands.has_permissions(manage_messages=True)
async def remove_alternative_name_cmd(ctx, game_name: str, *, alternative_name: str):
    """Remove an alternative name from a played game"""
    try:
        # Find the game first
        game = db.get_played_game(game_name)
        if not game:
            await ctx.send(f"🔍 **Game not found:** '{game_name}' is not in the played games database.")
            return
        
        # Get current alternative names
        current_alt_names = game.get('alternative_names', []) or []
        
        # Find and remove the alternative name (case-insensitive)
        updated_alt_names = []
        removed = False
        for name in current_alt_names:
            if name.lower() == alternative_name.lower():
                removed = True
            else:
                updated_alt_names.append(name)
        
        if not removed:
            await ctx.send(f"⚠️ **Alternative name not found:** '{alternative_name}' is not listed as an alternative name for '{game['canonical_name']}'.\n\n📊 **Current alternative names:** {', '.join(current_alt_names) if current_alt_names else 'None'}")
            return
        
        # Update the game with the new list
        success = db.update_played_game(game['id'], alternative_names=updated_alt_names)
        
        if success:
            remaining_names = ', '.join(updated_alt_names) if updated_alt_names else 'None'
            await ctx.send(f"✅ **Alternative name removed:** '{alternative_name}' has been removed from '{game['canonical_name']}'\n\n📊 **Remaining alternative names:** {remaining_names}")
        else:
            await ctx.send(f"❌ **Update failed:** Unable to remove alternative name from '{game['canonical_name']}'. System malfunction detected.")
            
    except Exception as e:
        await ctx.send(f"❌ **Alternative name removal error:** {str(e)}")

# --- Cleanup ---
def cleanup():
    try:
        os.remove(LOCK_FILE)
    except:
        pass

def signal_handler(sig, frame):
    print("\n🛑 Shutdown requested...")
    cleanup()
    sys.exit(0)

atexit.register(cleanup)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Ensure TOKEN is set before running the bot
if not TOKEN:
    print("❌ DISCORD_TOKEN environment variable not set. Exiting.")
    sys.exit(1)

try:
    bot.run(TOKEN)
except KeyboardInterrupt:
    print("\n🛑 Bot stopped by user")
finally:
    cleanup()
