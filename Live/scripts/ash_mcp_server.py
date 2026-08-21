import asyncio
import os
import sys
from typing import Optional

import aiohttp
from bot.database import get_database
from mcp.server.fastmcp import FastMCP

# Determine the absolute path to the Live directory
LIVE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(LIVE_DIR)

# --- Manual .env loader (prevents needing python-dotenv dependency) ---
env_path = os.path.join(LIVE_DIR, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()


# Initialize MCP server
mcp = FastMCP("AshBotContext")

# Initialize database connection via Ash Bot's modular manager
db = get_database()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


@mcp.tool()
async def get_played_games(series_name: Optional[str] = None) -> str:
    """Fetch played games from the Ash Bot PostgreSQL database.

    Args:
        series_name: Optional filter for a specific game series franchise.
    """
    if not db.database_url:
        return "Error: DATABASE_URL not configured. Cannot access database."

    games = await asyncio.to_thread(db.games.get_all_played_games, series_name)
    if not games:
        return f"No games found{' for series ' + series_name if series_name else ''}."

    result = ["# Played Games Data\n"]
    for g in games:
        result.append(
            f"**{g.get('canonical_name')}** (ID: {g.get('id')})\n"
            f"- Series: {g.get('series_name', 'N/A')}\n"
            f"- Playtime: {g.get('total_playtime_minutes', 0)} mins\n"
            f"- Status: {g.get('completion_status', 'unknown')}\n"
            f"- YouTube Views: {g.get('youtube_views', 0)} | Twitch Views: {g.get('twitch_views', 0)}\n"
        )
    return "\n".join(result)


@mcp.tool()
async def get_user_strikes(user_id: int) -> str:
    """Fetch strike count for a specific user ID from the database.

    Args:
        user_id: The Discord user ID to look up.
    """
    if not db.database_url:
        return "Error: DATABASE_URL not configured. Cannot access database."

    strikes = await asyncio.to_thread(db.users.get_user_strikes, user_id)
    return f"User {user_id} currently has {strikes} strike(s)."


@mcp.tool()
async def get_discord_channel_history(channel_id: str, limit: int = 50) -> str:
    """Fetch recent messages from a Discord channel.

    Args:
        channel_id: The Discord Channel ID to fetch messages from.
        limit: Number of messages to retrieve (max 100).
    """
    if not DISCORD_TOKEN:
        return "Error: DISCORD_TOKEN environment variable not set. Cannot authenticate with Discord API."

    # Cap limit to prevent rate limits or abuse
    limit = min(max(1, limit), 100)

    headers = {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "User-Agent": "DiscordBot (Ash MCP Server, 1.0)"
    }

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                return f"Error fetching channel history: HTTP {response.status}\n{error_text}"

            messages = await response.json()

            if not messages:
                return "No messages found in this channel."

            result = [f"# Channel {channel_id} History (Last {len(messages)} messages)\n"]
            # Messages come newest first, reverse them for chronological reading
            for msg in reversed(messages):
                author = msg.get("author", {}).get("username", "Unknown")
                content = msg.get("content", "")
                result.append(f"**[{author}]**: {content}")

            return "\n".join(result)

if __name__ == "__main__":
    # Diagnostics for local startup
    if not DISCORD_TOKEN:
        print("⚠️ Warning: DISCORD_TOKEN environment variable not found. Channel history will not work.", file=sys.stderr)
    if not os.getenv("DATABASE_URL"):
        print("⚠️ Warning: DATABASE_URL environment variable not found. Database features will not work.", file=sys.stderr)

    print("🚀 Ash Bot MCP Server is ready. Waiting for connections over stdio...", file=sys.stderr)
    mcp.run(transport='stdio')
