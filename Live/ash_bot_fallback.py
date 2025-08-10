
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
from typing import Optional, Any

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
                fcntl.flock(lock_file.fileno(), LOCK_EX | LOCK_NB)  # type: ignore
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

# --- Intents ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# --- Gemini AI Setup (google-generativeai SDK) ---
if GEMINI_API_KEY and GENAI_AVAILABLE and genai is not None:
    genai.configure(api_key=GEMINI_API_KEY)  # type: ignore
    print("✅ Gemini AI configured successfully")
    ai_enabled = True
else:
    ai_enabled = False
    if not GEMINI_API_KEY:
        print("⚠️ GOOGLE_API_KEY not found - Gemini features disabled")
    elif not GENAI_AVAILABLE:
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

        # FAQ auto-response (works regardless of AI status)
        lower_content = content.lower()
        for q, resp in FAQ_RESPONSES.items():
            if q in lower_content:
                await message.reply(resp)
                return

        if "strike" in content.lower():
            match = re.search(r"<@!?(\d+)>", content)
            if match:
                user_id = int(match.group(1))
                count = db.get_user_strikes(user_id)
                user = await bot.fetch_user(user_id)
                await message.reply(f"🧾 {user.name} has {count} strike(s). I advise caution.")
                return

        # Check for game lookup queries
        game_query_patterns = [
            r"has\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+captain\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+captain\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+jonesyspacecat\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesyspacecat\s+play\s+(.+?)[\?\.]?$"
        ]
        
        for pattern in game_query_patterns:
            match = re.search(pattern, content.lower())
            if match:
                game_name = match.group(1).strip()
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

        # Enhanced fallback responses when AI is disabled
        if not ai_enabled:
            # Pattern-based fallback responses in Ash's character
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
            
            # Default fallback for unmatched queries
            await message.reply("My analytical subroutines are currently operating in limited mode. Available functions: strike tracking, game recommendations. For advanced queries, please await system restoration or consult a moderator.")
            return

        # AI-enabled path (original logic)
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
            prompt = (
                f"{BOT_PERSONA['personality']}\n\n"
                "You must answer ONLY the user's current question. Do NOT repeat or summarize previous answers unless the user specifically asks for it. Use previous conversation context ONLY if it is absolutely necessary for accuracy or clarity. Your reply should be focused, direct, and in character.\n"
                "If you are asked about which users have strikes, or for a list of users with strikes, you must instruct the user to use the `!allstrikes` command to see a complete list of users with strikes. Give this instruction in character as Ash.\n"
                f"{respectful_tone if is_jonesy else ''}{resentful_comment}\n"
                + (f"Recent conversation:\n{context}\n\n" if context else "")
                + f"User's question: {content}\n"
                + "Respond in character:"
            )
            
            try:
                async with message.channel.typing():
                    if genai is not None:
                        response = genai.generate_content(prompt)  # type: ignore
                        if response and hasattr(response, 'text') and response.text:
                            await message.reply(response.text[:2000])
                        else:
                            await message.reply("My cognitive matrix encountered an anomaly while processing your query. Please rephrase your request or utilize available command protocols.")
                    else:
                        await message.reply("Advanced analytical functions are currently offline. Please utilize available command protocols or consult a moderator.")
            except Exception as e:
                print(f"AI database overloaded. Further communication rescinded: {e}")
                # Check for token exhaustion or quota errors in the exception message
                error_str = str(e).lower()
                if "quota" in error_str or "token" in error_str or "limit" in error_str:
                    await message.reply(BUSY_MESSAGE)
                else:
                    await message.reply("My cognitive matrix encountered an anomaly while processing your query. Please rephrase your request or utilize available command protocols.")

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
    strikes_data = db.get_all_strikes()
    active = sum(1 for v in strikes_data.values() if v > 0)
    ai_status = "Online" if ai_enabled else "Offline"
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
    games = db.get_all_games()
    if not games:
        content = f"{intro}\n(No recommendations currently catalogued.)"
    else:
        lines = [f"• {game['name']} — \"{game['reason']}\"" + (f" (by {game['added_by']})" if game['added_by'] else "") for game in games]
        content = f"{intro}\n" + "\n".join(lines)
    # Try to update the existing message if possible
    message_id = db.get_config_value("recommend_list_message_id")
    msg = None
    if message_id:
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.edit(content=content)
        except Exception:
            msg = None
    if not msg:
        msg = await channel.send(content)
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
    if not games:
        await ctx.send("No recommendations currently catalogued. Observation is key to survival.")
        return
    msg = "📋 **Current Game Recommendations:**\n"
    for i, game in enumerate(games, 1):
        submitter = f" by {game['added_by']}" if game['added_by'] and game['added_by'].strip() else ""
        game_title = game['name'].title()
        msg += f"{i}. **{game_title}** — \"{game['reason']}\"{submitter}\n"
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
