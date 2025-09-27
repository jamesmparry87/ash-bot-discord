#!/usr/bin/env python3
"""
Test script to verify that the trivia session bug is fixed.

This test simulates the trivia session workflow:
1. Start a trivia session
2. End the trivia session 
3. Verify that the session completes without SQL errors

This addresses the original issue where !endtrivia was failing with:
ERROR:database:Error ending trivia session 1: column tq.calculated_answer does not exist
"""

import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from bot.database_module import get_database
    from bot.config import JAM_USER_ID, JONESY_USER_ID
    print("✅ Successfully imported bot modules")
except ImportError as e:
    print(f"❌ Failed to import bot modules: {e}")
    print("Make sure you're running this from the Live directory")
    sys.exit(1)

def test_trivia_session_fix():
    """Test the trivia session start/end workflow"""
    print("\n🧠 Testing Trivia Session Fix")
    print("=" * 50)
    
    db = get_database()
    
    if not db or not db.database_url:
        print("❌ Database not available for testing")
        return False
    
    try:
        # Step 1: Add a test trivia question
        print("📝 Adding test trivia question...")
        question_id = db.add_trivia_question(
            question_text="What is the capital of France?",
            question_type="single",
            correct_answer="Paris",
            category="test_geography",
            submitted_by_user_id=JAM_USER_ID
        )
        
        if not question_id:
            print("❌ Failed to add test question")
            return False
        
        print(f"✅ Added test question with ID: {question_id}")
        
        # Step 2: Start a trivia session
        print("🚀 Starting trivia session...")
        session_id = db.start_trivia_session(
            question_id=question_id,
            started_by=JAM_USER_ID
        )
        
        if not session_id:
            print("❌ Failed to start trivia session")
            return False
        
        print(f"✅ Started trivia session with ID: {session_id}")
        
        # Step 3: Verify session is active
        print("🔍 Checking active session...")
        active_session = db.get_active_trivia_session()
        
        if not active_session:
            print("❌ No active session found")
            return False
        
        if active_session['id'] != session_id:
            print(f"❌ Session ID mismatch: expected {session_id}, got {active_session['id']}")
            return False
        
        print(f"✅ Active session found: {active_session['id']}")
        print(f"   Question: {active_session['question_text']}")
        print(f"   Status: {active_session['status']}")
        
        # Step 4: Submit a test answer
        print("💬 Submitting test answer...")
        answer_id = db.submit_trivia_answer(
            session_id=session_id,
            user_id=JONESY_USER_ID,  # Different user to avoid conflict
            answer_text="Paris"
        )
        
        if answer_id:
            print(f"✅ Submitted test answer with ID: {answer_id}")
        else:
            print("⚠️ Failed to submit answer, but continuing test...")
        
        # Step 5: End the trivia session (this was the failing operation)
        print("🏁 Ending trivia session...")
        session_results = db.end_trivia_session(
            session_id=session_id,
            ended_by=JAM_USER_ID
        )
        
        if not session_results:
            print("❌ Failed to end trivia session - this was the original bug!")
            return False
        
        print(f"✅ Successfully ended trivia session!")
        print(f"   Question: {session_results['question']}")
        print(f"   Correct Answer: {session_results['correct_answer']}")
        print(f"   Participants: {session_results['total_participants']}")
        print(f"   Correct Answers: {session_results['correct_answers']}")
        
        # Step 6: Verify no active session remains
        print("🔍 Verifying session cleanup...")
        active_session_after = db.get_active_trivia_session()
        
        if active_session_after:
            print(f"⚠️ Warning: Active session still exists: {active_session_after['id']}")
            # This might be expected if there are other active sessions
        else:
            print("✅ No active session found - cleanup successful")
        
        # Step 7: Check that question status changed to 'answered'
        print("🔍 Checking question status...")
        question = db.get_trivia_question_by_id(question_id)
        
        if question:
            print(f"✅ Question status: {question.get('status', 'unknown')}")
            if question.get('status') == 'answered':
                print("✅ Question correctly marked as 'answered'")
            else:
                print(f"⚠️ Question status is '{question.get('status')}' (expected 'answered')")
        
        print("\n🎉 Trivia Session Fix Test PASSED!")
        print("The SQL column reference error has been resolved.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_column_reference_directly():
    """Test the specific SQL query that was failing"""
    print("\n🔍 Testing SQL Query Fix Directly")
    print("=" * 50)
    
    db = get_database()
    
    if not db or not db.database_url:
        print("❌ Database not available for testing")
        return False
    
    try:
        conn = db.get_connection()
        if not conn:
            print("❌ Could not get database connection")
            return False
        
        with conn.cursor() as cur:
            # Test the fixed query structure
            print("📝 Testing fixed SQL query structure...")
            
            # This query should now work (using ts.calculated_answer instead of tq.calculated_answer)
            cur.execute("""
                SELECT ts.*, tq.question_text, tq.correct_answer, ts.calculated_answer
                FROM trivia_sessions ts
                JOIN trivia_questions tq ON ts.question_id = tq.id
                WHERE ts.id = %s
            """, (-1,))  # Using -1 as a test ID that won't exist
            
            # If we get here without an exception, the query syntax is correct
            result = cur.fetchone()
            print("✅ Fixed SQL query executed successfully")
            print("   Query structure: SELECT ts.*, tq.question_text, tq.correct_answer, ts.calculated_answer")
            print("   The 'calculated_answer' column is now correctly referenced from ts (trivia_sessions)")
            
        return True
        
    except Exception as e:
        print(f"❌ SQL query test failed: {e}")
        return False

def main():
    """Run all trivia session tests"""
    print("🧪 Trivia Session Fix Verification")
    print("=" * 60)
    
    # Test 1: Direct SQL query fix
    sql_test_passed = test_column_reference_directly()
    
    # Test 2: Full workflow test
    workflow_test_passed = test_trivia_session_fix()
    
    print("\n📊 TEST SUMMARY")
    print("=" * 60)
    print(f"SQL Query Fix Test:     {'✅ PASSED' if sql_test_passed else '❌ FAILED'}")
    print(f"Workflow Test:          {'✅ PASSED' if workflow_test_passed else '❌ FAILED'}")
    
    if sql_test_passed and workflow_test_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("The trivia session bug has been successfully fixed.")
        print("Users should now be able to:")
        print("  • Start trivia sessions with !starttrivia")
        print("  • End trivia sessions with !endtrivia") 
        print("  • No more 'column tq.calculated_answer does not exist' errors")
        return True
    else:
        print("\n❌ SOME TESTS FAILED!")
        print("The fix may need additional work.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
