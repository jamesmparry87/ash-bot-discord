"""
Tests for the Trainee Role Promotion Handler

Tests the check_trainee_promotion() function in bot/handlers/role_handler.py
using mock Discord objects to avoid needing a live bot connection.

Test cases:
    1. Member with Trainee only, joined >24h ago → gets promoted to Spacecat
    2. Member with Trainee only, joined <24h ago → no action (spam protection)
    3. Member with both Trainee + Spacecat → Trainee removed (cleanup only)
    4. Member with Spacecat only, no Trainee → no action at all
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure `Live/` is on sys.path so `bot.*` imports work.
# This file lives in Live/tests/, so we go up one level to reach Live/.
# ---------------------------------------------------------------------------
_live_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _live_dir not in sys.path:
    sys.path.insert(0, _live_dir)

# ---------------------------------------------------------------------------
# Import the function under test and the module-level guard set
# ---------------------------------------------------------------------------
import bot.handlers.role_handler as _role_handler_module  # noqa: E402
from bot.handlers.role_handler import check_trainee_promotion  # noqa: E402

# ---------------------------------------------------------------------------
# Constants matching config.py (duplicated here to avoid import side effects)
# ---------------------------------------------------------------------------
TRAINEE_ROLE_ID = 1134082966570668142
SPACECAT_ROLE_ID = 1393685422323929270
MEMBER_LOGS_CHANNEL_ID = 1303788504144285798

# Reason strings used in the handler (must match exactly for assertions)
REASON_PROMOTION = "Ash: overdue promotion — Trainee interacted after 24h, Carl-bot missed the auto-promote"
REASON_CLEANUP = "Ash cleanup: member already has Spacecat role (stale Trainee removed)"


# ---------------------------------------------------------------------------
# Helpers for building mock Discord objects
# ---------------------------------------------------------------------------

def make_role(role_id: int, name: str) -> MagicMock:
    """Create a minimal mock Discord Role."""
    role = MagicMock()
    role.id = role_id
    role.name = name
    return role


def make_member(
    roles: list,
    joined_ago: timedelta,
    name: str = "TestUser",
    member_id: int = 12345678,
) -> MagicMock:
    """
    Create a mock discord.Member with the given roles and join time.

    Args:
        roles:      List of mock Role objects to assign to the member.
        joined_ago: How long ago the member joined (e.g. timedelta(hours=48)).
        name:       Display name for the member.
        member_id:  Discord user ID for the member.
    """
    member = MagicMock()
    member.id = member_id
    member.name = name
    member.roles = roles
    member.joined_at = datetime.now(timezone.utc) - joined_ago
    member.mention = f"<@{member_id}>"

    # Make add_roles and remove_roles awaitable (async)
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()

    return member


def make_guild(trainee_role, spacecat_role) -> MagicMock:
    """Create a mock discord.Guild with the two key roles available."""
    guild = MagicMock()
    guild.name = "TestGuild"

    # Make a mock #member-logs text channel
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()

    # isinstance(channel, discord.TextChannel) check in the handler uses
    # isinstance() — MagicMock passes this when spec isn't set, because
    # MagicMock.__instancecheck__ returns True by default.
    guild.get_channel.return_value = mock_channel

    # Map role IDs to mock roles
    role_map = {
        TRAINEE_ROLE_ID: trainee_role,
        SPACECAT_ROLE_ID: spacecat_role,
    }
    guild.get_role.side_effect = lambda role_id: role_map.get(role_id)

    return guild


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def trainee_role():
    return make_role(TRAINEE_ROLE_ID, "Trainee Space Cadet")


@pytest.fixture
def spacecat_role():
    return make_role(SPACECAT_ROLE_ID, "Spacecat")


@pytest.fixture
def guild(trainee_role, spacecat_role):
    return make_guild(trainee_role, spacecat_role)


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overdue_promotion(trainee_role, spacecat_role, guild):
    """
    Case 1: Member has Trainee only and joined >24 hours ago.
    Expected: Spacecat added, Trainee removed, log message sent to #member-logs.
    """
    member = make_member(
        roles=[trainee_role],
        joined_ago=timedelta(days=3),   # 3 days ago — well past the 24h window
    )

    await check_trainee_promotion(member, guild)

    # Spacecat should have been added
    member.add_roles.assert_called_once_with(spacecat_role, reason=REASON_PROMOTION)

    # Trainee should have been removed
    member.remove_roles.assert_called_once_with(trainee_role, reason=REASON_PROMOTION)

    # Should log to #member-logs
    log_channel = guild.get_channel(MEMBER_LOGS_CHANNEL_ID)
    log_channel.send.assert_called_once()
    log_message = log_channel.send.call_args[0][0]
    assert "Promoted" in log_message
    assert "Trainee Space Cadet" in log_message
    assert "Spacecat" in log_message


@pytest.mark.asyncio
async def test_new_member_not_promoted(trainee_role, spacecat_role, guild):
    """
    Case 2: Member has Trainee only but joined <24 hours ago.
    Expected: No role changes — still within Carl-bot's spam protection window.
    """
    member = make_member(
        roles=[trainee_role],
        joined_ago=timedelta(hours=6),  # Only 6 hours ago
    )

    await check_trainee_promotion(member, guild)

    # Neither role action should have been taken
    member.add_roles.assert_not_called()
    member.remove_roles.assert_not_called()

    # No log message either
    log_channel = guild.get_channel(MEMBER_LOGS_CHANNEL_ID)
    log_channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_role_cleanup(trainee_role, spacecat_role, guild):
    """
    Case 3: Member has BOTH Trainee and Spacecat.
    Expected: Trainee removed only. Spacecat NOT added again. Log message sent.
    """
    member = make_member(
        roles=[trainee_role, spacecat_role],
        joined_ago=timedelta(days=30),  # Long-time member
    )

    await check_trainee_promotion(member, guild)

    # Trainee should be removed
    member.remove_roles.assert_called_once_with(trainee_role, reason=REASON_CLEANUP)

    # Spacecat should NOT be added (they already have it)
    member.add_roles.assert_not_called()

    # Should log to #member-logs
    log_channel = guild.get_channel(MEMBER_LOGS_CHANNEL_ID)
    log_channel.send.assert_called_once()
    log_message = log_channel.send.call_args[0][0]
    assert "Cleanup" in log_message or "cleanup" in log_message.lower()
    assert "Trainee Space Cadet" in log_message


@pytest.mark.asyncio
async def test_spacecat_only_no_action(trainee_role, spacecat_role, guild):
    """
    Case 4: Member has Spacecat only — no Trainee role at all.
    Expected: Nothing happens (fast exit path — first role check returns False).
    """
    member = make_member(
        roles=[spacecat_role],
        joined_ago=timedelta(days=10),
    )

    await check_trainee_promotion(member, guild)

    # Absolutely no role changes
    member.add_roles.assert_not_called()
    member.remove_roles.assert_not_called()

    # No log message
    log_channel = guild.get_channel(MEMBER_LOGS_CHANNEL_ID)
    log_channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_concurrency_guard_skips_duplicate(trainee_role, spacecat_role, guild):
    """
    Case 5: Concurrency guard — member ID already in _processing_members.

    Simulates a second promotion call arriving while the first is still
    awaiting the Discord API. The second call must exit immediately without
    making any role API calls.

    Expected: No role changes (guarded exit), guard set is clean after the call.
    """
    DUPLICATE_MEMBER_ID = 99999999

    member = make_member(
        roles=[trainee_role],
        joined_ago=timedelta(days=5),
        member_id=DUPLICATE_MEMBER_ID,
    )

    # Simulate the first call being in-flight: pre-populate the guard set
    _role_handler_module._processing_members.add(DUPLICATE_MEMBER_ID)

    try:
        await check_trainee_promotion(member, guild)
    finally:
        # Always clean up the guard set so other tests are unaffected
        _role_handler_module._processing_members.discard(DUPLICATE_MEMBER_ID)

    # The second call should have done nothing
    member.add_roles.assert_not_called()
    member.remove_roles.assert_not_called()

    log_channel = guild.get_channel(MEMBER_LOGS_CHANNEL_ID)
    log_channel.send.assert_not_called()

    # Guard set should be clean (our finally above cleaned it up,
    # and the function itself should not have removed it since it exited early)
    assert DUPLICATE_MEMBER_ID not in _role_handler_module._processing_members
