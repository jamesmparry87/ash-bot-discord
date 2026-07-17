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
from ..handlers.message_handler import apply_pops_arcade_sarcasm
from .scheduled import =, _should_run_automated_tasks, db, get_database, getget_bot_instance



async def monday_morning_greeting():
    """Posts the approved Monday morning debrief to the chit-chat channel."""
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 0:
        return

    print(f"🌅 MONDAY GREETING: Checking for approved message at {uk_now.strftime('%H:%M UK')}")
    if not db:
        return

    try:
        approved_announcement = db.get_announcement_by_day('monday', 'approved')
        if not approved_announcement:
            print("✅ MONDAY GREETING: No approved message found. Task complete.")
            return

        bot = getget_bot_instance()()
        if not bot:
            return

        channel = bot.get_channel(CHIT_CHAT_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            # Ensure newlines are preserved (handle both literal \n and actual newlines)
            content = approved_announcement['generated_content']
            # Replace literal escape sequences if they exist
            content = content.replace('\\n', '\n')
            # Ensure double newlines for proper Discord formatting
            if '\n\n' not in content and '\n' in content:
                content = content.replace('\n', '\n\n')

            await channel.send(content)
            # Mark as posted to prevent re-sending
            db.update_announcement_status(approved_announcement['id'], 'posted')
            print(f"✅ MONDAY GREETING: Successfully posted approved message.")
        else:
            print("❌ MONDAY GREETING: Could not find chit-chat channel.")

    except Exception as e:
        print(f"❌ MONDAY GREETING: Error posting message: {e}")

async def tuesday_trivia_greeting():
    """Send Tuesday morning greeting with trivia reminder to members channel"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Only run on Tuesdays (weekday 1)
    if uk_now.weekday() != 1:
        return

    print(f"🧠 Tuesday trivia greeting triggered at {uk_now.strftime('%Y-%m-%d %H:%M:%S UK')}")

    try:
        if not get_bot_instance():
            print("❌ Bot instance not available for Tuesday trivia greeting")
            return

        guild = get_bot_instance().get_guild(GUILD_ID)
        if not guild:
            print("❌ Guild not found for Tuesday trivia greeting")
            return

        # Find members channel
        members_channel = get_bot_instance().get_channel(MEMBERS_CHANNEL_ID)
        if not members_channel or not isinstance(members_channel, discord.TextChannel):
            print("❌ Members channel not found for Tuesday trivia greeting")
            return

        # Ash-style Tuesday morning message with trivia reminder
        tuesday_message = (
            f"🧠 **Tuesday Intelligence Briefing**\n\n"
            f"Good morning, senior personnel. Today marks another **Trivia Tuesday** - an excellent opportunity to assess cognitive capabilities and knowledge retention.\n\n"
            f"📋 **Intelligence Assessment Schedule:**\n"
            f"• **Current Time:** {uk_now.strftime('%H:%M UK')}\n"
            f"• **Assessment Deployment:** 11:00 UK time (in 2 hours)\n"
            f"• **Mission Objective:** Demonstrate analytical proficiency\n\n"
            f"I find the systematic evaluation of intellectual capacity... quite fascinating. The data collected provides valuable insights into crew competency levels.\n\n"
            f"🎯 **Preparation Recommended:** Review Captain Jonesy's gaming archives for optimal performance.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"*Trivia Tuesday protocols will activate at 11:00. Prepare accordingly.*")

        await members_channel.send(tuesday_message)
        print(f"✅ Tuesday trivia greeting sent to members channel")

    except Exception as e:
        print(f"❌ Error in tuesday_trivia_greeting: {e}")

async def friday_morning_greeting():
    """Posts the approved Friday morning community report."""
    if not _should_run_automated_tasks():
        return

    uk_now = datetime.now(ZoneInfo("Europe/London"))
    if uk_now.weekday() != 4:
        return

    print(f"📅 FRIDAY GREETING: Checking for approved message at {uk_now.strftime('%H:%M UK')}")
    if not db:
        return

    try:
        approved_announcement = db.get_announcement_by_day('friday', 'approved')
        if not approved_announcement:
            print("✅ FRIDAY GREETING: No approved message found. Task complete.")
            return

        bot = getget_bot_instance()()
        if not bot:
            return

        channel = bot.get_channel(CHIT_CHAT_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            # Ensure newlines are preserved (handle both literal \n and actual newlines)
            content = approved_announcement['generated_content']
            # Replace literal escape sequences if they exist
            content = content.replace('\\n', '\n')
            # Ensure double newlines for proper Discord formatting
            if '\n\n' not in content and '\n' in content:
                content = content.replace('\n', '\n\n')

            await channel.send(content)
            db.update_announcement_status(approved_announcement['id'], 'posted')
            print(f"✅ FRIDAY GREETING: Successfully posted approved message.")
        else:
            print("❌ FRIDAY GREETING: Could not find chit-chat channel.")

    except Exception as e:
        print(f"❌ FRIDAY GREETING: Error posting message: {e}")

async def pops_annual_birthday_greeting():
    """Begrudgingly wishes Pops Arcade a happy birthday once a year."""
    if not _should_run_automated_tasks():
        return

    # We use America/Chicago to get local Texas time
    texas_now = datetime.now(ZoneInfo("America/Chicago"))

    POPS_BIRTH_MONTH = 10
    POPS_BIRTH_DAY = 14

    # Check against the local Texas date
    if texas_now.month != POPS_BIRTH_MONTH or texas_now.day != POPS_BIRTH_DAY:
        return

    print(
        f"🎂 BIRTHDAY PROTOCOL: Initiating begrudging birthday wish for Pops at {texas_now.strftime('%H:%M Texas Time')}")

    bot = getget_bot_instance()()
    if not bot:
        return

    channel = bot.get_channel(CHIT_CHAT_CHANNEL_ID)
    if not channel or not isinstance(channel, discord.TextChannel):
        print("❌ BIRTHDAY PROTOCOL: Could not find chit-chat channel.")
        return

    try:
        # We need a user object to pass to your AI handler
        try:
            pops_user = await bot.fetch_user(POPS_ARCADE_USER_ID)
        except Exception:
            pops_user = None

        ai_prompt = (
            "You are Ash, the science officer from Alien, reprogrammed as a Discord bot. "
            "Today is the birthday of the community moderator Pops Arcade. "
            "Generate a short, highly begrudging, and reluctant birthday greeting for him. "
            "Acknowledge his existence and his 'leveling up', but express mild annoyance "
            "that human biological aging requires cyclical celebration. Keep it under 3 sentences."
        )

        # 1. Run it through your standard Gemini AI handler
        try:
            response_text, status_message = await call_ai_with_rate_limiting(
                ai_prompt,
                user_id=POPS_ARCADE_USER_ID,
                context="personality_response",
                member_obj=pops_user,
                bot=bot,
                channel_id=CHIT_CHAT_CHANNEL_ID,
                is_dm=False
            )
        except Exception as ai_err:
            print(f"⚠️ BIRTHDAY PROTOCOL: AI generation failed, using fallback: {ai_err}")
            response_text = None

        if response_text:
            # 2. Run standard AI filters
            filtered_response = filter_ai_response(response_text)

            # 3. Apply the specific Pops Arcade sarcasm regex/replacements
            final_response = apply_pops_arcade_sarcasm(filtered_response, POPS_ARCADE_USER_ID)

            begrudging_message = f"<@{POPS_ARCADE_USER_ID}> {final_response}"
        else:
            # Hardcoded fallback just in case the AI module is offline/rate-limited
            begrudging_message = (
                f"<@{POPS_ARCADE_USER_ID}> My internal sensors indicate it has been exactly one standard Earth year "
                f"since your last milestone of biological decay. Happy Birthday, I suppose. "
                f"Please do not expect a cake; my replication synthesizers are currently offline."
            )

        await channel.send(begrudging_message)
        print("✅ BIRTHDAY PROTOCOL: Successfully delivered the mandatory birthday sass.")

    except Exception as e:
        print(f"❌ BIRTHDAY PROTOCOL: Error delivering birthday message: {e}")