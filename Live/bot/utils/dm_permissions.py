"""
DM-aware permission checks for commands that need to work in both guild and DM contexts
"""

from typing import Callable

import discord
from discord.ext import commands

from ..config import JAM_USER_ID, JONESY_USER_ID


def is_moderator_or_authorized():
    """
    Custom check that allows commands to work in DMs for authorized users
    or in guilds for users with manage_messages permission.
    
    Authorized users: JAM_USER_ID, JONESY_USER_ID
    """
    async def predicate(ctx: commands.Context) -> bool:
        # Always allow JAM and Jonesy (authorized users)
        if ctx.author.id in [JAM_USER_ID, JONESY_USER_ID]:
            return True
        
        # In DMs, only authorized users can use this
        if isinstance(ctx.channel, discord.DMChannel):
            return False
        
        # In guilds, check for manage_messages permission
        if ctx.guild and hasattr(ctx.author, 'guild_permissions'):
            return ctx.author.guild_permissions.manage_messages
        
        return False
    
    return commands.check(predicate)
