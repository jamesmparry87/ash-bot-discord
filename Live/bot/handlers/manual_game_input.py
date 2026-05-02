"""
Manual Game Input Handler
Handles DM-based manual game name input during sync operations
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import discord

from ..config import JAM_USER_ID

# Track ongoing manual input requests
pending_manual_inputs = {}  # {user_id: {'vod_data': ..., 'future': asyncio.Future}}


async def request_manual_game_name(
    bot,
    vod_data: dict,
    is_scheduled: bool = False
) -> Optional[str]:
    """
    Send DM requesting manual game name and wait for response.
    
    Args:
        bot: Discord bot instance
        vod_data: VOD information dict with 'title', 'url', 'source', etc.
        is_scheduled: True if from automated sync (longer timeout)
    
    Returns:
        Game name string, "skip", or None if timeout
    """
    user_id = JAM_USER_ID
    timeout_seconds = 900 if is_scheduled else 300  # 15 min vs 5 min
    timeout_text = "15 minutes" if is_scheduled else "5 minutes"
    
    try:
        user = await bot.fetch_user(user_id)
        if not user:
            print(f"❌ Could not fetch user {user_id} for manual input")
            return None
        
        # Build DM message
        title = vod_data.get('title', 'Unknown')
        source = vod_data.get('source', 'unknown')
        url = vod_data.get('url', '')
        guess = vod_data.get('extracted_name', '')
        confidence = vod_data.get('confidence', 0.0)
        
        embed = discord.Embed(
            title="🤔 Manual Game Identification Needed",
            color=0xff9900,
            description=f"Sync {'(automated)' if is_scheduled else ''} paused - need your help!"
        )
        
        embed.add_field(name="Platform", value=source.title(), inline=True)
        embed.add_field(name="Confidence", value=f"{confidence:.0%}", inline=True)
        embed.add_field(name="📺 Title", value=f"```{title[:200]}```", inline=False)
        
        if guess:
            embed.add_field(name="My Guess", value=f"`{guess}`", inline=False)
        else:
            embed.add_field(name="My Guess", value="*(no match found)*", inline=False)
        
        if url:
            embed.add_field(name="🔗 URL", value=url[:100], inline=False)
        
        response_options = []
        if guess:
            response_options.append(f"• `accept` → Use my guess")
        response_options.append(f"• `skip` → Ignore this VOD permanently")
        response_options.append(f"• `<game name>` → Provide correct name")
        
        embed.add_field(
            name="💬 Reply with:",
            value="\n".join(response_options),
            inline=False
        )
        
        embed.set_footer(text=f"⏳ Waiting {timeout_text} for response...")
        
        await user.send(embed=embed)
        print(f"📨 Sent manual input request to JAM for: {title[:50]}")
        
        # Create future to wait for response
        future = asyncio.Future()
        pending_manual_inputs[user_id] = {
            'vod_data': vod_data,
            'future': future,
            'guess': guess
        }
        
        # Wait for response with timeout
        try:
            response = await asyncio.wait_for(future, timeout=timeout_seconds)
            return response
        except asyncio.TimeoutError:
            await user.send(f"⏱️ **No response received** - auto-skipping this VOD and continuing sync.")
            print(f"⏱️ Manual input timeout for: {title[:50]}")
            return "skip"
        finally:
            # Clean up
            if user_id in pending_manual_inputs:
                del pending_manual_inputs[user_id]
    
    except Exception as e:
        print(f"❌ Error in manual game input: {e}")
        return None


async def handle_manual_input_response(message: discord.Message):
    """
    Handle user's DM response for manual game input.
    Called from message handler when user responds in DM.
    """
    user_id = message.author.id
    
    if user_id not in pending_manual_inputs:
        return False  # Not waiting for input from this user
    
    request_data = pending_manual_inputs[user_id]
    future = request_data['future']
    guess = request_data.get('guess', '')
    
    if future.done():
        return False  # Already resolved
    
    response = message.content.strip().lower()
    
    # Handle special responses
    if response == "skip":
        future.set_result("skip")
        await message.add_reaction("✅")
        return True
    elif response == "accept" and guess:
        future.set_result(guess)
        await message.add_reaction("✅")
        await message.channel.send(f"✅ Using: `{guess}`")
        return True
    elif response == "accept" and not guess:
        await message.channel.send("❌ No guess available - please provide the game name or use `skip`")
        return True
    else:
        # Treat as game name
        game_name = message.content.strip()
        if len(game_name) > 0 and len(game_name) < 200:
            future.set_result(game_name)
            await message.add_reaction("✅")
            await message.channel.send(f"✅ Using: `{game_name}`")
            return True
        else:
            await message.channel.send("❌ Invalid game name - try again or use `skip`")
            return True


# Export
__all__ = ['request_manual_game_name', 'handle_manual_input_response', 'pending_manual_inputs']
