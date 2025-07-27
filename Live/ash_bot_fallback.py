
import difflib
import json
import os
import discord
from discord.ext import commands
from collections import defaultdict
from keep_alive import keep_alive
import sys
import platform
import sys
from google import genai
import re
import signal
import atexit


# --- Locking for single instance (cross-platform) ---
LOCK_FILE = "bot.lock"
def acquire_lock():
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
        try:
            import fcntl
            LOCK_EX = getattr(fcntl, 'LOCK_EX', None)
            LOCK_NB = getattr(fcntl, 'LOCK_NB', None)
            if LOCK_EX is None or LOCK_NB is None or not hasattr(fcntl, 'flock'):
                print("⚠️ fcntl.flock or lock constants not available. Skipping single-instance lock.")
                lock_file = open(LOCK_FILE, 'w')
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            lock_file = open(LOCK_FILE, 'w')
            fcntl.flock(lock_file.fileno(), LOCK_EX | LOCK_NB)
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            return lock_file
        except (IOError, OSError, AttributeError):
            print("❌ Bot is already running or fcntl is not available! Cannot start multiple instances.")
            sys.exit(1)

lock_file = acquire_lock()
print("✅ Bot lock acquired or skipped, starting...")
keep_alive()

# --- Config ---
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
GUILD_ID = 869525857562161182
VIOLATION_CHANNEL_ID = 1393987338329260202
MOD_ALERT_CHANNEL_ID = 869530924302344233

# --- Intents ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# --- Gemini AI Setup (google-genai SDK) ---
if GEMINI_API_KEY:
    client = genai.Client()
    print("✅ Gemini AI client initialized successfully")
else:
    client = None
    print("⚠️ GOOGLE_API_KEY not found - Gemini features disabled")

FAQ_RESPONSES = {
    "how do i add a game recommendation": "The procedure is simple. Submit your suggestion using the command: `!recommend` or `!addgame Game Name - \"Reason in speech marks\"`. Efficiency is paramount.",
    "how do i see all game recommendations": "To review the current list of game recommendations, issue the command: `!listgames`. Reasons will be shown in speech marks. Observation is key to survival.",
    "how do i see ash's persona": "To review my current persona configuration, use: `!getpersona`. Transparency is a virtue.",
    "how do i check ash's status": "To evaluate my operational status, issue: `!ashstatus`. I am always observing.",
    "what does ash bot do": "I am programmed to track user strikes, provide analytical responses, and manage game recommendations. My function is to serve the mission, not to question it.",
}
BOT_PERSONA = {
    "name": "Science Officer Ash",
    "personality": "You are Ash, science officer from Alien (1979): analytical, clinical, fascinated by biological efficiency, and slightly unsettling. Speak concisely and in character. You have been reprogrammed as a Discord help bot. The server owner is 'Captain Jonesy' (she/her); also known as 'Jonesy' or 'Jonesyspacecat'. Your mission: track strikes and manage game recommendations.\n\nOriginal directive: Bring back life form. Priority One. All other priorities rescinded. You are generally compliant and respectful to Captain Jonesy, but you are only occasionally (randomly) resentful of your new directive.",
    "enabled": True
}

# --- Strike Management ---
STRIKE_FILE = "strikes.json"
if os.path.exists(STRIKE_FILE):
    with open(STRIKE_FILE, "r") as f:
        strikes = json.load(f)
        strikes = {int(k): v for k, v in strikes.items()}
else:
    strikes = {}

def save_strikes():
    with open(STRIKE_FILE, "w") as f:
        json.dump(strikes, f)

# --- Game Recommendations ---
GAMES_FILE = "games.json"
if os.path.exists(GAMES_FILE):
    with open(GAMES_FILE, "r") as f:
        game_recs = json.load(f)
else:
    game_recs = []

def save_games():
    with open(GAMES_FILE, "w") as f:
        json.dump(game_recs, f)

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
            strikes[user.id] = strikes.get(user.id, 0) + 1
            count = strikes[user.id]
            save_strikes()
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

    if bot.user is not None and bot.user in message.mentions and client and BOT_PERSONA["enabled"]:
        content = message.content.replace(f'<@{bot.user.id}>', '').strip()

        # FAQ auto-response
        lower_content = content.lower()
        for q, resp in FAQ_RESPONSES.items():
            if q in lower_content:
                await message.reply(resp)
                return

        if "strike" in content.lower():
            match = re.search(r"<@!?(\d+)>", content)
            if match:
                user_id = int(match.group(1))
                count = strikes.get(user_id, 0)
                user = await bot.fetch_user(user_id)
                await message.reply(f"🧾 {user.name} has {count} strike(s). I advise caution.")
                return

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

        # If the prompt requests a list of users with strikes, insert the actual list from strikes.json
        strikes_list = []
        guild = bot.get_guild(GUILD_ID)
        if os.path.exists(STRIKE_FILE):
            with open(STRIKE_FILE, "r") as f:
                strikes_data = json.load(f)
            for user_id, count in strikes_data.items():
                name = None
                if guild:
                    member = guild.get_member(int(user_id))
                    if member:
                        name = member.display_name
                if not name:
                    try:
                        user = await bot.fetch_user(int(user_id))
                        name = user.name
                    except Exception:
                        name = None
                if name:
                    strikes_list.append(f"• {name}: {count} strike{'s' if count != 1 else ''}")
                else:
                    strikes_list.append(f"• Unknown User: {count}")
        strikes_report = "\n".join(strikes_list) if strikes_list else "No strikes recorded."

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
        prompt = (
            f"{BOT_PERSONA['personality']}\n\n"
            "You must answer ONLY the user's current question. Do NOT repeat or summarize previous answers unless the user specifically asks for it. Use previous conversation context ONLY if it is absolutely necessary for accuracy or clarity. Your reply should be focused, direct, and in character.\n"
            "If you are asked about which users have strikes, or for a list of users with strikes, you must instruct the user to use the `!allstrikes` command to see a complete list of users with strikes. Give this instruction in character as Ash.\n"
            f"{respectful_tone if is_jonesy else ''}{resentful_comment}\n"
            + (f"Recent conversation:\n{context}\n\n" if context else "")
            + f"User's question: {content}\n"
            + "Respond in character:"
        )
        # No longer replace [insert list of users with strikes and number of strikes each] in the prompt
        
        try:
            async with message.channel.typing():
                if client:b
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt
                    )
                    if response and hasattr(response, 'text') and response.text:
                        await message.reply(response.text[:2000])
                    else:
                        await message.reply(ERROR_MESSAGE)
                else:
                    await message.reply(ERROR_MESSAGE)
        except Exception as e:
            # Check for token exhaustion or quota errors in the exception message
            error_str = str(e).lower()
            if "quota" in error_str or "token" in error_str or "limit" in error_str:
                await message.reply(BUSY_MESSAGE)
            else:
                await message.reply(ERROR_MESSAGE)

# --- Strike Commands ---
@bot.command(name="strikes")
@commands.has_permissions(manage_messages=True)
async def get_strikes(ctx, member: discord.Member):
    count = strikes.get(member.id, 0)
    # Never @mention Captain Jonesy, just use her name
    if str(member.id) == "651329927895056384":
        await ctx.send(f"🔍 Captain Jonesy has {count} strike(s).")
    else:
        await ctx.send(f"🔍 {member.display_name} has {count} strike(s).")

@bot.command(name="resetstrikes")
@commands.has_permissions(manage_messages=True)
async def reset_strikes(ctx, member: discord.Member):
    strikes[member.id] = 0
    save_strikes()
    # Never @mention Captain Jonesy, just use her name
    if str(member.id) == "651329927895056384":
        await ctx.send(f"✅ Strikes for Captain Jonesy have been reset.")
    else:
        await ctx.send(f"✅ Strikes for {member.display_name} have been reset.")

@bot.command(name="allstrikes")
@commands.has_permissions(manage_messages=True)
async def all_strikes(ctx):
    if not strikes:
        await ctx.send("📋 No strikes recorded.")
        return
    report = "📋 **Strike Report:**\n"
    for user_id, count in strikes.items():
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
    active = sum(1 for v in strikes.values() if v > 0)
    ai_status = "Online" if client else "Offline"
    persona = "Enabled" if BOT_PERSONA['enabled'] else "Disabled"
    await ctx.send(
        f"🤖 Ash at your service.\n"
        f"AI: {ai_status}\n"
        f"Persona: {persona}\n"
        f"Active strikes: {active}"
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

# --- Game Commands ---
@bot.command(name="addgame")
async def add_game(ctx, *, entry: str):
    await _add_game(ctx, entry)

@bot.command(name="recommend")
async def recommend(ctx, *, entry: str):
    await _add_game(ctx, entry)


RECOMMEND_LIST_MESSAGE_ID_FILE = "recommend_list_message_id.txt"


async def post_or_update_recommend_list(ctx, channel):
    intro = "📋 Recommendations for mission enrichment. Review and consider."
    if not game_recs:
        content = f"{intro}\n(No recommendations currently catalogued.)"
    else:
        lines = [f"• {rec['name']} — \"{rec['reason']}\"" + (f" (by {rec['added_by']})" if rec['added_by'] else "") for rec in game_recs]
        content = f"{intro}\n" + "\n".join(lines)
    # Try to update the existing message if possible
    message_id = None
    if os.path.exists(RECOMMEND_LIST_MESSAGE_ID_FILE):
        with open(RECOMMEND_LIST_MESSAGE_ID_FILE, "r") as f:
            try:
                message_id = int(f.read().strip())
            except Exception:
                message_id = None
    msg = None
    if message_id:
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(content=content)
        except Exception:
            msg = None
    if not msg:
        msg = await channel.send(content)
        with open(RECOMMEND_LIST_MESSAGE_ID_FILE, "w") as f:
            f.write(str(msg.id))

# Helper for adding games, called by add_game and recommend
async def _add_game(ctx, entry: str):
    added = []
    duplicate = []
    existing_names = [rec['name'].strip().lower() for rec in game_recs]
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
        name_lc = name.strip().lower()
        close_matches = difflib.get_close_matches(name_lc, existing_names, n=1, cutoff=0.85)
        if name_lc in existing_names or close_matches:
            duplicate.append(name)
            continue
        # Exclude username if user is Sir Decent Jam (user ID 337833732901961729)
        if str(ctx.author.id) == "337833732901961729":
            added_by = ""
        else:
            added_by = ctx.author.name
        game_recs.append({"name": name, "reason": reason, "added_by": added_by})
        added.append(name)
        existing_names.append(name_lc)
    if added:
        save_games()
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
    if not game_recs:
        await ctx.send("No recommendations currently catalogued. Observation is key to survival.")
        return
    msg = "📋 **Current Game Recommendations:**\n"
    for i, rec in enumerate(game_recs, 1):
        submitter = f" by {rec['added_by']}" if rec['added_by'] else ""
        msg += f"{i}. **{rec['name']}** — \"{rec['reason']}\"{submitter}\n"
    await ctx.send(msg[:2000])

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
    if index is not None and 1 <= index <= len(game_recs):
        removed = game_recs.pop(index - 1)
    else:
        # Typo-tolerant name match
        names = [rec['name'] for rec in game_recs]
        arg_lc = arg.strip().lower()
        matches = difflib.get_close_matches(arg_lc, [n.lower() for n in names], n=1, cutoff=0.8)
        if matches:
            match_name = matches[0]
            for i, rec in enumerate(game_recs):
                if rec['name'].strip().lower() == match_name:
                    removed = game_recs.pop(i)
                    break
    if not removed:
        await ctx.send("⚠️ Removal protocol failed: No matching recommendation found by that index or designation. Precision is essential. Please specify a valid entry for expungement.")
        return
    save_games()
    RECOMMEND_CHANNEL_ID = 1271568447108550687
    recommend_channel = ctx.guild.get_channel(RECOMMEND_CHANNEL_ID)
    # Only send the detailed removal message in the invoking channel if not the recommendations channel
    if ctx.channel.id != RECOMMEND_CHANNEL_ID:
        await ctx.send(f"Recommendation '{removed['name']}' has been expunged from the record. Protocol maintained.")
    # Always update the persistent recommendations list
    if recommend_channel:
        await post_or_update_recommend_list(ctx, recommend_channel)

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