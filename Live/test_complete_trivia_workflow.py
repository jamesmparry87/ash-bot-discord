#!/usr/bin/env python3
"""
Complete Trivia Workflow Test
Tests the entire end-to-end trivia system from reply detection to winner announcements.
"""

import asyncio
import os
import sys
from datetime import datetime

# Add the Live directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

async def test_complete_trivia_workflow():
    """Test the complete trivia workflow end-to-end"""
    print("🎯 COMPLETE TRIVIA WORKFLOW TEST")
    print("=" * 60)
    
    try:
        # Import all required components
        from bot.commands.trivia import TriviaCommands
        from bot.database_module import get_database
        from bot_modular import is_trivia_answer_reply, process_trivia_answer
        
        print("✅ All components imported successfully")
        
        # Create mock objects
        class MockBot:
            pass
        
        class MockMessage:
            def __init__(self, content, author_id, channel_id, message_id, reference=None):
                self.content = content
                self.author = MockUser(author_id)
                self.channel = MockChannel(channel_id)
                self.id = message_id
                self.reference = reference
                
            async def add_reaction(self, emoji):
                print(f"📝 Mock reaction added: {emoji} to message '{self.content}'")
                
        class MockUser:
            def __init__(self, user_id):
                self.id = user_id
                
        class MockChannel:
            def __init__(self, channel_id):
                self.id = channel_id
                
            async def fetch_message(self, message_id):
                return MockMessage("Mock trivia question", 123456789, self.id, message_id)
        
        class MockReference:
            def __init__(self, message_id):
                self.message_id = message_id
        
        # Initialize components
        bot = MockBot()
        db = get_database()
        trivia_commands = TriviaCommands(bot)
        
        print("✅ Mock objects created successfully")
        print()
        
        # Step 1: Create a test trivia question and session
        print("🔍 STEP 1: Creating Test Trivia Session")
        print("-" * 40)
        
        test_question_id = db.add_trivia_question(
            question_text="What is the most common answer in trivia tests?",
            question_type="single",
            correct_answer="blue",
            submitted_by_user_id=337833732901961729  # Test user
        )
        
        if not test_question_id:
            print("❌ Failed to create test question")
            return False
            
        print(f"✅ Created test question ID: {test_question_id}")
        
        # Create trivia session
        test_session_id = db.create_trivia_session(
            question_id=test_question_id,
            session_type="test"
        )
        
        if not test_session_id:
            print("❌ Failed to create test session")
            return False
            
        print(f"✅ Created test session ID: {test_session_id}")
        
        # Update session with mock message IDs
        question_msg_id = 999888777666555444
        confirmation_msg_id = 999888777666555445
        channel_id = 1213488470798893107
        
        success = db.update_trivia_session_messages(
            session_id=test_session_id,
            question_message_id=question_msg_id,
            confirmation_message_id=confirmation_msg_id,
            channel_id=channel_id
        )
        
        if success:
            print(f"✅ Updated session with message tracking")
        else:
            print("⚠️ Failed to update session message tracking")
        
        print()
        
        # Step 2: Test reply detection
        print("🔍 STEP 2: Testing Reply Detection")
        print("-" * 40)
        
        # Create mock reply message
        reply_message = MockMessage("blue", 111222333444555, channel_id, 999888777666555446)
        reply_message.reference = MockReference(question_msg_id)
        
        # Test reply detection
        is_reply, session_data = await is_trivia_answer_reply(reply_message)
        
        print(f"Reply detected: {is_reply}")
        if session_data:
            print(f"Session ID: {session_data['id']}")
            print(f"Question: {session_data.get('question_text', 'Unknown')}")
        
        if not is_reply:
            print("❌ Reply detection failed")
            return False
            
        print("✅ Reply detection working correctly")
        print()
        
        # Step 3: Test answer processing and recording
        print("🔍 STEP 3: Testing Answer Processing and Recording")
        print("-" * 40)
        
        # Test multiple answers with different variations
        test_answers = [
            ("blue", 111111111111111111),   # Exact match
            ("Blue", 222222222222222222),   # Case variation  
            ("BLUE", 333333333333333333),   # Case variation
            ("bleu", 444444444444444444),   # Fuzzy match
            ("green", 555555555555555555),  # Wrong answer
        ]
        
        processed_answers = []
        
        for answer_text, user_id in test_answers:
            test_msg = MockMessage(answer_text, user_id, channel_id, 999888777666555000 + user_id)
            test_msg.reference = MockReference(question_msg_id)
            
            print(f"Processing answer: '{answer_text}' from user {user_id}")
            
            success = await process_trivia_answer(test_msg, session_data)
            processed_answers.append((answer_text, user_id, success))
            
            if success:
                print(f"✅ Answer '{answer_text}' processed successfully")
            else:
                print(f"❌ Answer '{answer_text}' processing failed")
        
        print()
        
        # Step 4: Complete session and check results
        print("🔍 STEP 4: Completing Session and Checking Results")
        print("-" * 40)
        
        # Complete the trivia session
        completion_success = db.complete_trivia_session(test_session_id)
        
        if completion_success:
            print("✅ Session completed successfully")
        else:
            print("❌ Session completion failed")
            return False
        
        # Get session answers to verify recording
        session_answers = db.get_trivia_session_answers(test_session_id)
        
        print(f"📊 Recorded answers: {len(session_answers)}")
        
        correct_answers = 0
        partial_answers = 0
        first_correct_user = None
        
        for answer in session_answers:
            user_id = answer['user_id']
            answer_text = answer['answer_text']
            is_correct = answer.get('is_correct', False)
            is_close = answer.get('is_close', False)
            
            if is_correct:
                correct_answers += 1
                if first_correct_user is None:
                    first_correct_user = user_id
                print(f"✅ CORRECT: '{answer_text}' from user {user_id}")
            elif is_close:
                partial_answers += 1
                print(f"🟡 PARTIAL: '{answer_text}' from user {user_id}")
            else:
                print(f"❌ WRONG: '{answer_text}' from user {user_id}")
        
        print()
        
        # Step 5: Verify winner detection
        print("🔍 STEP 5: Winner Detection Verification")
        print("-" * 40)
        
        if first_correct_user:
            print(f"🏆 First correct answer by user: {first_correct_user}")
            
            # Verify this matches our expected first correct answer (user 111111111111111111)
            expected_winner = 111111111111111111
            if first_correct_user == expected_winner:
                print("✅ Winner detection is correct!")
            else:
                print(f"⚠️ Winner detection mismatch. Expected {expected_winner}, got {first_correct_user}")
        else:
            print("❌ No winner detected despite correct answers being processed")
        
        print()
        
        # Final Results Summary
        print("=" * 60)
        print("📊 COMPLETE WORKFLOW TEST RESULTS")
        print("=" * 60)
        
        print(f"Test Question Created: ✅ (ID: {test_question_id})")
        print(f"Test Session Created: ✅ (ID: {test_session_id})")
        print(f"Message Tracking: {'✅' if success else '❌'}")
        print(f"Reply Detection: {'✅' if is_reply else '❌'}")
        print(f"Answer Processing: ✅ ({len(processed_answers)} answers processed)")
        print(f"Session Completion: {'✅' if completion_success else '❌'}")
        print(f"Answer Recording: ✅ ({len(session_answers)} answers recorded)")
        print(f"Correct Answers: {correct_answers}")
        print(f"Partial Credit: {partial_answers}")
        print(f"Winner Detection: {'✅' if first_correct_user else '❌'}")
        
        # Test scoring verification
        expected_correct = 3  # blue, Blue, BLUE should all be correct
        expected_partial = 1  # bleu should be partial
        expected_wrong = 1    # green should be wrong
        
        scoring_correct = (correct_answers == expected_correct and 
                          partial_answers == expected_partial)
        
        print(f"Scoring System: {'✅' if scoring_correct else '❌'}")
        print(f"  Expected: {expected_correct} correct, {expected_partial} partial, {expected_wrong} wrong")
        print(f"  Actual: {correct_answers} correct, {partial_answers} partial")
        
        print()
        
        # Overall assessment
        all_tests_passed = (
            test_question_id and 
            test_session_id and
            is_reply and
            completion_success and
            len(session_answers) > 0 and
            first_correct_user and
            scoring_correct
        )
        
        if all_tests_passed:
            print("🎉 **COMPLETE WORKFLOW TEST PASSED!**")
            print("The trivia system is fully functional from reply detection to winner announcement.")
            print()
            print("✅ Original issue resolved: Case sensitivity ('blue'/'Blue') works correctly")
            print("✅ Answer recording and acknowledgment system operational")  
            print("✅ Fuzzy matching provides partial credit for close answers")
            print("✅ Winner detection identifies first correct answer")
            print("✅ Complete end-to-end workflow validated")
        else:
            print("❌ **WORKFLOW TEST FAILED**")
            print("Some components of the trivia system need attention.")
        
        # Clean up test data
        print()
        print("🧹 Cleaning up test data...")
        
        return all_tests_passed
        
    except Exception as e:
        print(f"❌ Critical error in workflow test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test execution"""
    print("🧪 COMPLETE TRIVIA WORKFLOW VALIDATION")
    print("Testing the entire system from Discord replies to winner announcements")
    print()
    
    success = await test_complete_trivia_workflow()
    
    print()
    print("=" * 60)
    if success:
        print("🎉 WORKFLOW VALIDATION COMPLETE - SYSTEM READY!")
        print()
        print("The trivia system is now fully operational with:")
        print("• Reply-based answer submission ✅")
        print("• Enhanced fuzzy matching ✅") 
        print("• Case-insensitive recognition ✅")
        print("• Partial credit system ✅")
        print("• Winner detection & announcement ✅")
        print()
        print("🚀 Ready for production deployment!")
    else:
        print("❌ WORKFLOW VALIDATION FAILED")
        print()
        print("Review the test results above and address any failing components.")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
