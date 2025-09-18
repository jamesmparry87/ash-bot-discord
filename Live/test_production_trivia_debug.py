#!/usr/bin/env python3
"""
Production Trivia Reply Detection Debugger

This script helps diagnose where the reply-based trivia system is failing in production.
Run this to check each step of the workflow and identify the exact failure point.
"""

import asyncio
import os
import sys
from datetime import datetime

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_database_connection():
    """Test basic database connectivity"""
    print("🔍 Testing Database Connection...")
    try:
        from Live.database import get_database
        db = get_database()
        
        if not db:
            print("❌ Database instance is None")
            return False
            
        # Test connection
        conn = db.get_connection()
        if not conn:
            print("❌ Cannot establish database connection")
            return False
            
        print("✅ Database connection successful")
        
        # Check if required methods exist
        required_methods = [
            'update_trivia_session_messages',
            'get_trivia_session_by_message_id',
            'get_active_trivia_session'
        ]
        
        for method in required_methods:
            if hasattr(db, method):
                print(f"✅ Method {method} exists")
            else:
                print(f"❌ Method {method} missing")
                return False
                
        return True
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_trivia_session_storage():
    """Test if trivia sessions are being stored with message tracking"""
    print("\n🔍 Testing Trivia Session Message Tracking...")
    try:
        from Live.database import get_database
        db = get_database()
        
        # Check for any trivia sessions with message tracking
        conn = db.get_connection()
        if not conn:
            print("❌ Cannot get database connection")
            return False
            
        with conn.cursor() as cur:
            # Check if columns exist
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'trivia_sessions' 
                AND column_name IN ('question_message_id', 'confirmation_message_id', 'channel_id')
            """)
            columns = cur.fetchall()
            
            if len(columns) < 3:
                print(f"❌ Missing message tracking columns. Found: {[col[0] for col in columns]}")
                return False
                
            print("✅ Message tracking columns exist")
            
            # Check for recent sessions with message tracking
            cur.execute("""
                SELECT id, question_id, question_message_id, confirmation_message_id, channel_id, status, started_at
                FROM trivia_sessions
                WHERE started_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                ORDER BY started_at DESC
                LIMIT 5
            """)
            sessions = cur.fetchall()
            
            if not sessions:
                print("⚠️ No recent trivia sessions found")
                return True
                
            print(f"📊 Found {len(sessions)} recent trivia sessions:")
            for session in sessions:
                session_dict = dict(session)
                session_id = session_dict['id']
                q_msg_id = session_dict['question_message_id']
                c_msg_id = session_dict['confirmation_message_id']
                channel_id = session_dict['channel_id']
                status = session_dict['status']
                started_at = session_dict['started_at']
                
                print(f"  • Session {session_id} ({status}): Q:{q_msg_id}, C:{c_msg_id}, Ch:{channel_id} [{started_at}]")
                
                if not q_msg_id or not c_msg_id or not channel_id:
                    print(f"    ❌ Session {session_id} missing message tracking data!")
                    return False
                    
            print("✅ All recent sessions have message tracking data")
            return True
            
    except Exception as e:
        print(f"❌ Session storage test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_session_lookup():
    """Test if we can lookup sessions by message ID"""
    print("\n🔍 Testing Session Lookup by Message ID...")
    try:
        from Live.database import get_database
        db = get_database()
        
        # Get a recent session with message tracking
        conn = db.get_connection()
        if not conn:
            print("❌ Cannot get database connection")
            return False
            
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, question_message_id, confirmation_message_id
                FROM trivia_sessions
                WHERE question_message_id IS NOT NULL 
                AND confirmation_message_id IS NOT NULL
                AND started_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                ORDER BY started_at DESC
                LIMIT 1
            """)
            session = cur.fetchone()
            
            if not session:
                print("⚠️ No recent sessions with message tracking found to test")
                return True
                
            session_dict = dict(session)
            session_id = session_dict['id']
            q_msg_id = session_dict['question_message_id']
            c_msg_id = session_dict['confirmation_message_id']
            
            print(f"📝 Testing lookups for Session {session_id}")
            
            # Test question message lookup
            result1 = db.get_trivia_session_by_message_id(q_msg_id)
            if result1:
                print(f"✅ Question message lookup successful: {q_msg_id} → Session {result1.get('id')}")
            else:
                print(f"❌ Question message lookup failed: {q_msg_id}")
                return False
                
            # Test confirmation message lookup
            result2 = db.get_trivia_session_by_message_id(c_msg_id)
            if result2:
                print(f"✅ Confirmation message lookup successful: {c_msg_id} → Session {result2.get('id')}")
            else:
                print(f"❌ Confirmation message lookup failed: {c_msg_id}")
                return False
                
            # Test non-existent message ID
            fake_id = 999999999999999999
            result3 = db.get_trivia_session_by_message_id(fake_id)
            if result3 is None:
                print(f"✅ Non-existent message lookup correctly returns None")
            else:
                print(f"⚠️ Non-existent message lookup returned unexpected result: {result3}")
                
            return True
            
    except Exception as e:
        print(f"❌ Session lookup test error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_active_session_detection():
    """Test if we can detect active trivia sessions"""
    print("\n🔍 Testing Active Session Detection...")
    try:
        from Live.database import get_database
        db = get_database()
        
        active_session = db.get_active_trivia_session()
        
        if active_session:
            print(f"✅ Found active trivia session: {active_session.get('id')}")
            print(f"   Question: {active_session.get('question_text', 'Unknown')[:50]}...")
            print(f"   Channel: {active_session.get('channel_id')}")
            print(f"   Q Message: {active_session.get('question_message_id')}")
            print(f"   C Message: {active_session.get('confirmation_message_id')}")
            
            # Check if message tracking is complete
            if active_session.get('question_message_id') and active_session.get('confirmation_message_id'):
                print("✅ Active session has complete message tracking")
            else:
                print("❌ Active session missing message tracking data")
                return False
                
        else:
            print("ℹ️ No active trivia session found (this is normal if no session is running)")
            
        return True
        
    except Exception as e:
        print(f"❌ Active session detection error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_reply_processing_logic():
    """Test the reply processing logic with mock data"""
    print("\n🔍 Testing Reply Processing Logic...")
    try:
        from Live.bot.main import normalize_trivia_answer
        
        # Test answer normalization
        test_cases = [
            ("God of War", "god of war"),
            ("I think it's Mario", "mario"), 
            ("The answer is Zelda", "zelda"),
            ("A", "A"),
            ("b", "B"),
            ("Maybe Sonic?", "maybe sonic")
        ]
        
        print("📝 Testing answer normalization:")
        for original, expected in test_cases:
            normalized = normalize_trivia_answer(original)
            if normalized == expected:
                print(f"  ✅ '{original}' → '{normalized}'")
            else:
                print(f"  ❌ '{original}' → '{normalized}' (expected: '{expected}')")
        
        print("✅ Reply processing logic tests completed")
        return True
        
    except Exception as e:
        print(f"❌ Reply processing logic error: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_debug_command():
    """Create a debug command that can be added to the bot for live testing"""
    debug_command = '''
@bot.command(name="debugtrivia")
@commands.has_permissions(manage_messages=True)
async def debug_trivia(ctx):
    """Debug trivia reply detection in production"""
    try:
        embed = discord.Embed(
            title="🔧 Trivia Debug Report",
            color=0xff9900,
            timestamp=datetime.now(ZoneInfo("Europe/London"))
        )
        
        # Check active session
        active_session = db.get_active_trivia_session()
        if active_session:
            embed.add_field(
                name="Active Session",
                value=f"Session {active_session.get('id')} - Q:{active_session.get('question_message_id')} C:{active_session.get('confirmation_message_id')}",
                inline=False
            )
        else:
            embed.add_field(name="Active Session", value="None", inline=False)
        
        # Test message lookup with fake ID
        test_result = db.get_trivia_session_by_message_id(999999999999999999)
        embed.add_field(
            name="Database Lookup Test", 
            value="✅ Working" if test_result is None else "❌ Unexpected result",
            inline=True
        )
        
        # Recent sessions
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as recent_count
                FROM trivia_sessions 
                WHERE started_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                AND question_message_id IS NOT NULL
            """)
            result = cur.fetchone()
            recent_count = result[0] if result else 0
            
        embed.add_field(
            name="Recent Sessions (24h)",
            value=f"{recent_count} with message tracking",
            inline=True
        )
        
        embed.set_footer(text="Use this to verify reply detection is working")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Debug error: {str(e)}")
'''
    
    print("\n📋 Production Debug Command:")
    print("Add this command to your bot for live testing:")
    print("=" * 60)
    print(debug_command)
    print("=" * 60)

def main():
    """Run all production debugging tests"""
    print("🔧 **PRODUCTION TRIVIA REPLY DETECTION DEBUGGER**")
    print("=" * 60)
    print(f"Timestamp: {datetime.now()}")
    print(f"Testing environment: {'Production' if os.getenv('DATABASE_URL') else 'Development'}")
    print("=" * 60)
    
    test_results = []
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Session Storage", test_trivia_session_storage),
        ("Session Lookup", test_session_lookup), 
        ("Active Session Detection", test_active_session_detection),
        ("Reply Processing Logic", test_reply_processing_logic)
    ]
    
    for test_name, test_function in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_function()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            test_results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("🏁 **DEBUGGING RESULTS SUMMARY**")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:<10} {test_name}")
        if result:
            passed += 1
    
    print("=" * 60)
    print(f"📊 **OVERALL: {passed}/{total} tests passed ({(passed/total)*100:.1f}%)**")
    
    if passed == total:
        print("\n🎉 **All tests passed!** The reply detection system should be working.")
        print("\n📋 **Next Steps:**")
        print("1. Check that users are actually replying to trivia messages (not just posting answers)")
        print("2. Verify the bot has proper message permissions in trivia channels")
        print("3. Test with a real trivia session using the debug command below")
    else:
        print(f"\n⚠️ **{total - passed} tests failed.** These issues need to be fixed:")
        for test_name, result in test_results:
            if not result:
                print(f"   • {test_name}")
    
    # Show debug command
    create_debug_command()
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
