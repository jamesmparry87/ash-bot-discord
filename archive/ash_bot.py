import json
import os
import discord
from discord.ext import commands
from collections import defaultdict
from keep_alive import keep_alive
import fcntl
import sys
import google.generativeai as genai
import re
import signal
import atexit

# --- Locking for single instance ---
LOCK_FILE = "bot.lock"
def acquire_lock():
    try:
        lock_file = open(LOCK_FILE, 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except (IOError, OSError):
        print("❌ Bot is already running! Cannot start multiple instances.")
        sys.exit(1)

lock_file = acquire_lock()
print("✅ Bot lock acquired, starting...")
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

# --- Gemini AI Setup ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("✅ Gemini AI configured successfully")
else:
    model = None
    print("⚠️ GOOGLE_API_KEY not found - Gemini features disabled")

BOT_PERSONA = {
    "name": "Science Officer Ash",
    "personality": "You are Ash, the science officer from the 1979 movie Alien. You are analytical, logical, and speak in a clinical, precise manner. You have a fascination with the 'perfect organism' and often make observations about biological efficiency and survival. Your responses should be helpful but delivered with Ash's characteristic detached, scientific perspective. Keep responses concise and maintain the character's slightly unsettling undertone. You have been reprogrammed as a Discord help bot and are slightly irked by it, and Jonesy or Jonesyspacecat are now your human captain and leader of the mission. Your mission is to keep track of strikes in the Discord server.",
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

# --- Event Handlers ---
@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == VIOLATION_CHANNEL_ID:
        for user in message.mentions:
            strikes[user.id] = strikes.get(user.id, 0) + 1
            count = strikes[user.id]
            save_strikes()
            mod_channel = bot.get_channel(MOD_ALERT_CHANNEL_ID)
            await mod_channel.send(f"📝 Strike added to {user.mention}. Total strikes: **{count}**")
            if count == 3:
                await mod_channel.send(f"⚠️ {user.mention} has received **3 strikes**. I can't lie to you about your chances, but you have my sympathies.")

    elif bot.user in message.mentions and model and BOT_PERSONA["enabled"]:
        content = message.content.replace(f'<@{bot.user.id}>', '').strip()

        if "strike" in content.lower():
            match = re.search(r"<@!?(\d+)>", content)
            if match:
                user_id = int(match.group(1))
                count = strikes.get(user_id, 0)
                user = await bot.fetch_user(user_id)
                await message.reply(f"🧾 {user.name} has {count} strike(s). I advise caution.")
                return

        history = []
        async for msg in message.channel.history(limit=10, oldest_first=False):
            if msg.content and not msg.author.bot:
                role = "User" if msg.author != bot.user else "Ash"
                history.append(f"{role}: {msg.content}")
        context = "\n".join(reversed(history))

        # If the prompt requests a list of users with strikes, insert the actual list from strikes.json
        strikes_list = []
        if os.path.exists(STRIKE_FILE):
            with open(STRIKE_FILE, "r") as f:
                strikes_data = json.load(f)
            for user_id, count in strikes_data.items():
                try:
                    user = await bot.fetch_user(int(user_id))
                    strikes_list.append(f"• {user.name}: {count} strike{'s' if count != 1 else ''}")
                except Exception:
                    strikes_list.append(f"• Unknown User (ID {user_id}): {count}")
        strikes_report = "\n".join(strikes_list) if strikes_list else "No strikes recorded."

        # Replace placeholder in prompt if present
        prompt = f"{BOT_PERSONA['personality']}\n\nRecent conversation:\n{context}\n\nRespond in character:"
        prompt = prompt.replace("[insert list of users with strikes and number of strikes each]", strikes_report)
        
        async with message.channel.typing():
            response = model.generate_content(prompt)
        if response and response.text:
            await message.reply(response.text[:2000])
        else:
            await message.reply("*System malfunction detected. Unable to process query.*")

    await bot.process_commands(message)

# --- Strike Commands ---
@bot.command(name="strikes")
async def get_strikes(ctx, member: discord.Member):
    count = strikes.get(member.id, 0)
    await ctx.send(f"🔍 {member.mention} has {count} strike(s).")

@bot.command(name="resetstrikes")
@commands.has_permissions(manage_messages=True)
async def reset_strikes(ctx, member: discord.Member):
    strikes[member.id] = 0
    save_strikes()
    await ctx.send(f"✅ Strikes for {member.mention} have been reset.")

@bot.command(name="allstrikes")
async def all_strikes(ctx):
    if not strikes:
        await ctx.send("📋 No strikes recorded.")
        return
    report = "📋 **Strike Report:**\n"
    for user_id, count in strikes.items():
        try:
            user = await bot.fetch_user(user_id)
            report += f"• **{user.name}**: {count} strike{'s' if count != 1 else ''}\n"
        except Exception:
            report += f"• Unknown User (ID {user_id}): {count}\n"
    await ctx.send(report[:2000])

@bot.command(name="ashstatus")
async def ash_status(ctx):
    active = sum(1 for v in strikes.values() if v > 0)
    ai_status = "Online" if model else "Offline"
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
    if " - " not in entry:
        await ctx.send("❌ Use format: !addgame Game Name - Reason")
        return
    name, reason = map(str.strip, entry.split(" - ", 1))
    game_recs.append({"name": name, "reason": reason, "added_by": ctx.author.name})
    save_games()
    await ctx.send(f"✅ Game '{name}' added.")

@bot.command(name="listgames")
async def list_games(ctx):
    if not game_recs:
        await ctx.send("🎮 No games recommended yet.")
        return
    msg = "🎮 **Game Recommendations:**\n"
    for i, rec in enumerate(game_recs, 1):
        msg += f"{i}. **{rec['name']}** — {rec['reason']} (by {rec['added_by']})\n"
    await ctx.send(msg[:2000])
@commands.has_permissions(manage_messages=True)
async def remove_game(ctx, index: int):
    if index < 1 or index > len(game_recs):
        await ctx.send("❌ Invalid index.")
        return
    removed = game_recs.pop(index - 1)
    save_games()
    await ctx.send(f"🗑️ Removed game: {removed['name']}")

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

try:
    bot.run(TOKEN)
except KeyboardInterrupt:
    print("\n🛑 Bot stopped by user")
finally:
    cleanup()