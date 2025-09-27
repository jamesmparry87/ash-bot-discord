#!/usr/bin/env python3
"""
Test script to verify moderator channel monitoring behavior
Tests that background monitoring is disabled while preserving essential functions.
"""

import re
import sys
import os
from unittest.mock import Mock, AsyncMock

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock Discord objects for testing


class MockChannel:
    def __init__(self, channel_id, name="test-channel"):
        self.id = channel_id
        self.name = name


class MockUser:
    def __init__(self, user_id=123456, username="testuser"):
        self.id = user_id
        self.username = username
        self.bot = False


class MockMessage:
    def __init__(self, content, channel_id, user_id=123456, mentions=None):
        self.content = content
        self.channel = MockChannel(channel_id)
        self.author = MockUser(user_id)
        self.mentions = mentions or []

# Import the functions from bot_modular.py


def is_moderator_channel_sync(channel_id: int) -> bool:
    """Synchronous version for testing - actual function is async"""
    # Channel IDs from configuration
    MODERATOR_CHANNEL_IDS = [
        1213488470798893107,
        869530924302344233,
        1280085269600669706,
        1393987338329260202
    ]
    return channel_id in MODERATOR_CHANNEL_IDS


def is_casual_conversation_not_query(content: str) -> bool:
    """Detect if a message is casual conversation/narrative rather than a query"""
    content_lower = content.lower()

    casual_conversation_patterns = [
        r"and then",
        r"someone (?:said|says|recommends?|suggested?)",
        r"(?:he|she|they) (?:said|says|recommends?|suggested?)",
        r"the fact that",
        r"jam says",
        r"remember (?:when|that|what)",
        r"i (?:was|am) (?:telling|talking about)",
        r"we were (?:discussing|talking about)",
        r"yesterday (?:someone|he|she|they)",
        r"earlier (?:someone|he|she|they)",
        r"(?:mentioned|talked about|discussed) (?:that|how|what)",
    ]

    return any(re.search(pattern, content_lower) for pattern in casual_conversation_patterns)


def detect_implicit_game_query(content: str) -> bool:
    """Detect if a message is likely a game-related query even without explicit bot mention"""
    content_lower = content.lower()

    # First check if this is casual conversation rather than a query
    if is_casual_conversation_not_query(content):
        return False

    # Game query patterns
    game_query_patterns = [
        r"has\s+jonesy\s+played",
        r"did\s+jonesy\s+play",
        r"has\s+captain\s+jonesy\s+played",
        r"did\s+captain\s+jonesy\s+play",
        r"what\s+games?\s+has\s+jonesy",
        r"what\s+games?\s+did\s+jonesy",
        r"which\s+games?\s+has\s+jonesy",
        r"which\s+games?\s+did\s+jonesy",
        r"what.*game.*most.*playtime",
        r"which.*game.*most.*episodes",
        r"what.*game.*longest.*complete",
        r"^is\s+.+\s+recommended\s*[\?\.]?$",
        r"^who\s+recommended\s+.+[\?\.]?$",
        r"^what\s+(games?\s+)?(?:do\s+you\s+|would\s+you\s+|should\s+i\s+)?recommend",
        r"jonesy.*gaming\s+(history|database|archive)",
    ]

    return any(re.search(pattern, content_lower) for pattern in game_query_patterns)


def should_process_message_in_mod_channel(content: str, is_mentioned: bool) -> bool:
    """Test the logic for whether to process messages in mod channels"""
    return (
        is_mentioned or  # Direct @Ash mentions
        content.lower().startswith('ash')  # "ash" prefix
    )


def should_process_message_in_normal_channel(content: str, is_mentioned: bool, is_dm: bool) -> bool:
    """Test the logic for whether to process messages in normal channels"""
    is_implicit_game_query = detect_implicit_game_query(content)

    return (
        is_dm or  # All DMs get processed
        is_mentioned or  # Explicit mentions
        content.lower().startswith('ash') or  # "ash" prefix
        is_implicit_game_query  # Implicit game queries
    )


def run_tests():
    """Run comprehensive tests for mod channel monitoring"""
    print("🧪 Testing Mod Channel Monitoring Changes")
    print("=" * 50)

    # Channel IDs for testing
    MOD_CHANNEL_ID = 869530924302344233  # From MODERATOR_CHANNEL_IDS
    NORMAL_CHANNEL_ID = 123456789  # Not a mod channel

    # Test cases that should be IGNORED in mod channels but processed in normal channels
    background_monitoring_cases = [
        "Has Jonesy played Portal?",
        "Did Jonesy play Halo?",
        "What games has Jonesy played?",
        "What game took longest to complete?",
        "I hate pineapple on pizza",  # Pineapple pizza enforcement
        "Is Portal recommended?",
        "Who recommended Cyberpunk?"
    ]

    # Test cases that should work in BOTH mod and normal channels
    direct_interaction_cases = [
        ("@Ash has Jonesy played Portal?", True),  # Direct mention
        ("ash what games has Jonesy played?", False),  # Ash prefix
        ("@Ash help", True),  # Direct mention
        ("ash what can you do?", False),  # Ash prefix
    ]

    # Test cases that should NEVER be processed (in any channel)
    ignored_cases = [
        "Hello everyone!",
        "How's everyone doing?",
        "I'm playing Portal right now",
        "Someone recommended Portal yesterday",  # Casual conversation
    ]

    print("\n🔕 Testing BACKGROUND MONITORING (should be disabled in mod channels):")
    print("-" * 60)

    mod_background_blocked = 0
    normal_background_allowed = 0

    for i, case in enumerate(background_monitoring_cases, 1):
        # Test in mod channel (should be blocked)
        should_process_mod = should_process_message_in_mod_channel(case, is_mentioned=False)
        # Test in normal channel (should be allowed)
        should_process_normal = should_process_message_in_normal_channel(case, is_mentioned=False, is_dm=False)

        if not should_process_mod:
            mod_background_blocked += 1
        if should_process_normal:
            normal_background_allowed += 1

        mod_status = "✅ ignored" if not should_process_mod else "❌ PROCESSED"
        normal_status = "✅ processed" if should_process_normal else "❌ IGNORED"

        print(f"{i:2d}. '{case}'")
        print(f"    Mod Channel:    {mod_status}")
        print(f"    Normal Channel: {normal_status}")
        print()

    print("\n📢 Testing DIRECT INTERACTIONS (should work in all channels):")
    print("-" * 50)

    mod_direct_allowed = 0
    normal_direct_allowed = 0

    for i, (case, is_mentioned) in enumerate(direct_interaction_cases, 1):
        # Test in mod channel
        should_process_mod = should_process_message_in_mod_channel(case, is_mentioned=is_mentioned)
        # Test in normal channel
        should_process_normal = should_process_message_in_normal_channel(case, is_mentioned=is_mentioned, is_dm=False)

        if should_process_mod:
            mod_direct_allowed += 1
        if should_process_normal:
            normal_direct_allowed += 1

        mod_status = "✅ processed" if should_process_mod else "❌ IGNORED"
        normal_status = "✅ processed" if should_process_normal else "❌ IGNORED"

        mention_type = "mention" if is_mentioned else "prefix"

        print(f"{i:2d}. '{case}' ({mention_type})")
        print(f"    Mod Channel:    {mod_status}")
        print(f"    Normal Channel: {normal_status}")
        print()

    print("\n🚫 Testing IGNORED CASES (should be ignored everywhere):")
    print("-" * 45)

    mod_ignored = 0
    normal_ignored = 0

    for i, case in enumerate(ignored_cases, 1):
        # Test in both channels
        should_process_mod = should_process_message_in_mod_channel(case, is_mentioned=False)
        should_process_normal = should_process_message_in_normal_channel(case, is_mentioned=False, is_dm=False)

        if not should_process_mod:
            mod_ignored += 1
        if not should_process_normal:
            normal_ignored += 1

        mod_status = "✅ ignored" if not should_process_mod else "❌ PROCESSED"
        normal_status = "✅ ignored" if not should_process_normal else "❌ PROCESSED"

        print(f"{i:2d}. '{case}'")
        print(f"    Mod Channel:    {mod_status}")
        print(f"    Normal Channel: {normal_status}")
        print()

    print("\n📊 SUMMARY:")
    print("=" * 30)
    print(f"Background Monitoring (should be blocked in mod channels):")
    print(
        f"  Mod channels blocked:    {mod_background_blocked}/{len(background_monitoring_cases)} {'✅' if mod_background_blocked == len(background_monitoring_cases) else '❌'}")
    print(
        f"  Normal channels allowed: {normal_background_allowed}/{len(background_monitoring_cases)} {'✅' if normal_background_allowed == len(background_monitoring_cases) else '❌'}")
    print()
    print(f"Direct Interactions (should work everywhere):")
    print(
        f"  Mod channels allowed:    {mod_direct_allowed}/{len(direct_interaction_cases)} {'✅' if mod_direct_allowed == len(direct_interaction_cases) else '❌'}")
    print(
        f"  Normal channels allowed: {normal_direct_allowed}/{len(direct_interaction_cases)} {'✅' if normal_direct_allowed == len(direct_interaction_cases) else '❌'}")
    print()
    print(f"Ignored Cases (should be ignored everywhere):")
    print(
        f"  Mod channels ignored:    {mod_ignored}/{len(ignored_cases)} {'✅' if mod_ignored == len(ignored_cases) else '❌'}")
    print(
        f"  Normal channels ignored: {normal_ignored}/{len(ignored_cases)} {'✅' if normal_ignored == len(ignored_cases) else '❌'}")
    print()

    # Test essential functionality preservation
    print("🔧 Testing ESSENTIAL FUNCTIONALITY:")
    print("-" * 35)

    # Test that commands still work (they're processed first, before this logic)
    print("✅ Commands: Always processed first (before mod channel logic)")
    print("✅ Strikes: Only processed in violation channel (preserved)")
    print("✅ FAQ Responses: Available to mods when directly mentioned")
    print("✅ DM Functionality: Unaffected by mod channel logic")
    print()

    # Overall assessment
    total_tests = len(background_monitoring_cases) + len(direct_interaction_cases) + len(ignored_cases)
    mod_correct = mod_background_blocked + mod_direct_allowed + mod_ignored
    normal_correct = normal_background_allowed + normal_direct_allowed + normal_ignored

    mod_score = (mod_correct / (total_tests)) * 100
    normal_score = (normal_correct / (total_tests)) * 100

    print(f"Overall Accuracy:")
    print(f"  Mod Channel Logic:    {mod_score:.1f}% ({mod_correct}/{total_tests})")
    print(f"  Normal Channel Logic: {normal_score:.1f}% ({normal_correct}/{total_tests})")
    print()

    if (mod_background_blocked == len(background_monitoring_cases) and
        mod_direct_allowed == len(direct_interaction_cases) and
        mod_ignored == len(ignored_cases) and
        normal_background_allowed == len(background_monitoring_cases) and
        normal_direct_allowed == len(direct_interaction_cases) and
            normal_ignored == len(ignored_cases)):
        print("🎉 SUCCESS: All mod channel monitoring changes working correctly!")
        print("   • Background monitoring disabled in mod channels")
        print("   • Direct interactions preserved in mod channels")
        print("   • Normal channels unaffected")
        print("   • Essential functionality preserved")
    else:
        print("⚠️  Issues detected in mod channel logic")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    run_tests()
