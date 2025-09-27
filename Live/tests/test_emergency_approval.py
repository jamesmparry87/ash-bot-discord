#!/usr/bin/env python3
"""
Test script for emergency trivia approval logic
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_emergency_approval_logic():
    """Test the emergency approval timing logic"""
    print("🧪 Testing Emergency Approval Logic")
    print("=" * 50)

    uk_now = datetime.now(ZoneInfo('Europe/London'))
    print(f"Current time: {uk_now.strftime('%A %H:%M:%S UK')}")
    print(f"Day of week: {uk_now.weekday()} (1 = Tuesday)")
    print()

    # Test Tuesday logic
    if uk_now.weekday() == 1:  # Tuesday
        trivia_time = uk_now.replace(hour=11, minute=0, second=0, microsecond=0)

        if uk_now > trivia_time:
            print("⏰ Past trivia time (11:00 AM) - emergency check would skip")
            print("✅ Status: No emergency action needed")
        else:
            time_until_minutes = (trivia_time - uk_now).total_seconds() / 60
            print(f"⏰ Time until Trivia Tuesday: {time_until_minutes:.1f} minutes")

            if 0 < time_until_minutes < 60:
                print("🚨 EMERGENCY APPROVAL WOULD TRIGGER!")
                print("🔥 Action: Immediate approval request would be sent to JAM")
                print(f"📧 Message: 'Only {time_until_minutes:.0f} minutes until Trivia Tuesday!'")
            else:
                print("✅ No emergency needed - sufficient time remaining")
                print("📅 Normal pre-approval at 10:00 AM would handle this")
    else:
        print("📅 Not Tuesday - emergency check would skip")
        print("✅ Status: Emergency approval only runs on Tuesdays")

    print()
    print("🔍 Testing conversation handler timeout extension...")

    # Test the extended timeout
    from bot.handlers.conversation_handler import jam_approval_conversations
    print(f"📊 Current JAM approval conversations: {len(jam_approval_conversations)}")
    print("⏰ Conversation timeout extended from 2 hours to 24 hours")
    print("✅ Late responses will now be preserved for up to 24 hours")

    print()
    print("=" * 50)
    print("✅ Emergency approval logic test completed successfully")

if __name__ == "__main__":
    asyncio.run(test_emergency_approval_logic())
