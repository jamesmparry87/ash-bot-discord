"""
Role Handler Module

Handles automated role promotion for members who are still on the
"Trainee Space Cadet" role after interacting with the server.

Background:
-----------
Carl-bot assigns "Trainee Space Cadet" to every new member on join as a
spam protection measure, then is supposed to promote them to "Spacecat"
automatically after 24 hours. In practice, some members slip through:
  - Carl-bot missed the promotion for whatever reason
  - The member now has both Trainee AND Spacecat (stale role)

This handler catches those cases lazily — it runs on every message sent
and every reaction added. Over time, the only members still on Trainee
will be those who have NEVER interacted with the server, making it easy
to identify genuine ghost accounts for manual review.

The two cases handled:
  1. OVERDUE PROMOTION: Member has Trainee only + has been in server >24h
     → Remove Trainee, add Spacecat, log to #member-logs
  2. DUPLICATE CLEANUP: Member has both Trainee AND Spacecat
     → Remove Trainee only (they're already a full member), log to #member-logs

⚠️ PERMISSION REQUIREMENT:
   Ash's role in the server hierarchy MUST be ranked ABOVE both
   "Trainee Space Cadet" and "Spacecat" for role assignments to succeed.
   If Ash's role is lower in the hierarchy, all attempts will fail silently
   with a Forbidden error.
"""

from datetime import timedelta

import discord

from ..config import MEMBER_LOGS_CHANNEL_ID, SPACECAT_ROLE_ID, TRAINEE_ROLE_ID


async def check_trainee_promotion(member: discord.Member, guild: discord.Guild) -> None:
    """
    Check if a member needs their Trainee role resolved and act if so.

    This function is called on every message and reaction event. It is
    designed to be fast — it exits immediately if the member has no
    Trainee role, so the vast majority of calls are a simple list check
    with negligible overhead.

    Args:
        member: The Discord Member who just interacted.
        guild:  The Guild (server) the interaction happened in.

    Cases handled:
        Case 1 - Overdue promotion:
            Member has Trainee role, does NOT have Spacecat, and has been
            in the server for more than 24 hours. This means Carl-bot's
            automatic promotion didn't fire. Ash promotes them now.

        Case 2 - Duplicate role cleanup:
            Member has BOTH Trainee and Spacecat. The promotion was done
            at some point but the Trainee role was never removed. Ash
            removes the stale Trainee role.
    """

    # --- Fast exit: nothing to do if member has no Trainee role ---
    has_trainee = any(role.id == TRAINEE_ROLE_ID for role in member.roles)
    if not has_trainee:
        return

    has_spacecat = any(role.id == SPACECAT_ROLE_ID for role in member.roles)

    trainee_role = guild.get_role(TRAINEE_ROLE_ID)
    spacecat_role = guild.get_role(SPACECAT_ROLE_ID)

    if not trainee_role:
        # Role not found in this guild — configuration issue, bail out
        print(f"⚠️ ROLE HANDLER: Trainee role ID {TRAINEE_ROLE_ID} not found in guild '{guild.name}'")
        return

    try:
        # ------------------------------------------------------------------
        # Case 2: Duplicate roles — member already has Spacecat
        # Just strip the leftover Trainee role silently
        # ------------------------------------------------------------------
        if has_spacecat:
            await member.remove_roles(
                trainee_role,
                reason="Ash cleanup: member already has Spacecat role (stale Trainee removed)"
            )
            print(
                f"🧹 ROLE CLEANUP: Removed stale Trainee role from {member.name} "
                f"(ID: {member.id}) — they already had Spacecat"
            )
            await _log_to_member_logs(
                guild,
                f"🧹 **Role Cleanup** | {member.mention} — Removed stale `Trainee Space Cadet` "
                f"role (member already had `Spacecat`)."
            )
            return

        # ------------------------------------------------------------------
        # Case 1: Overdue promotion — member has Trainee only
        # Only promote if they have been in the server for >24 hours.
        # This preserves Carl-bot's spam protection window for brand-new joins.
        # ------------------------------------------------------------------
        if member.joined_at is None:
            # joined_at can be None for very old accounts in rare cases
            print(f"⚠️ ROLE HANDLER: Could not determine join date for {member.name} — skipping promotion")
            return

        time_in_server = discord.utils.utcnow() - member.joined_at

        if time_in_server <= timedelta(hours=24):
            # Still within the 24-hour Carl-bot window — do nothing yet
            return

        if not spacecat_role:
            print(f"⚠️ ROLE HANDLER: Spacecat role ID {SPACECAT_ROLE_ID} not found in guild '{guild.name}'")
            return

        # Promote: add Spacecat, then remove Trainee
        await member.add_roles(
            spacecat_role,
            reason="Ash: overdue promotion — Trainee interacted after 24h, Carl-bot missed the auto-promote"
        )
        await member.remove_roles(
            trainee_role,
            reason="Ash: overdue promotion — Trainee interacted after 24h, Carl-bot missed the auto-promote"
        )

        days = time_in_server.days
        hours = time_in_server.seconds // 3600
        print(
            f"🚀 ROLE PROMOTION: {member.name} (ID: {member.id}) promoted "
            f"Trainee → Spacecat after {days}d {hours}h in server"
        )
        await _log_to_member_logs(
            guild,
            f"🚀 **Role Update** | {member.mention} — Promoted from `Trainee Space Cadet` to "
            f"`Spacecat` after interacting with the server "
            f"({days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''} after joining)."
        )

    except discord.Forbidden:
        print(
            f"⚠️ ROLE HANDLER: Missing permissions to update roles for {member.name} (ID: {member.id}). "
            f"Check that Ash's role is above 'Trainee Space Cadet' and 'Spacecat' in the server hierarchy."
        )
    except discord.HTTPException as e:
        print(f"❌ ROLE HANDLER: Discord API error updating roles for {member.name} (ID: {member.id}): {e}")


async def _log_to_member_logs(guild: discord.Guild, message: str) -> None:
    """
    Post a quiet log entry to the #member-logs channel.

    This mirrors what Carl-bot posts in the same channel for other role
    changes, so all role activity stays in one place for easy review.

    Args:
        guild:   The Guild to find the channel in.
        message: The plain-text message to post.
    """
    try:
        channel = guild.get_channel(MEMBER_LOGS_CHANNEL_ID)
        if channel is None:
            print(
                f"⚠️ ROLE HANDLER: Could not find #member-logs channel "
                f"(ID: {MEMBER_LOGS_CHANNEL_ID}) — log entry not posted to Discord"
            )
            return
        # Duck-typing: just call send() — if it doesn't support it, we'll catch the error
        await channel.send(message)
    except discord.Forbidden:
        print(f"⚠️ ROLE HANDLER: Missing permissions to post in #member-logs (ID: {MEMBER_LOGS_CHANNEL_ID})")
    except discord.HTTPException as e:
        print(f"❌ ROLE HANDLER: Failed to post to #member-logs: {e}")
    except AttributeError:
        print(f"⚠️ ROLE HANDLER: Channel {MEMBER_LOGS_CHANNEL_ID} does not support send() — not a text channel")
