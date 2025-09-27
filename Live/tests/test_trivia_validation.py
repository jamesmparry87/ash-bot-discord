#!/usr/bin/env python3
"""
Test script to validate trivia startup without full bot environment
This will test the trivia validation function with mock data
"""

import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock

# Add the bot directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

async def test_trivia_validation():
    """Test the trivia validation function with mocked dependencies"""
    
    print("🧪 TESTING: Trivia startup validation function...")
    
    try:
        # Mock the database
        mock_db = Mock()
        mock_db.get_available_trivia_questions = Mock(return_value=[])
        
        # Mock the AI handler
        async def mock_generate_question():
            return {
                'question_text': 'Test trivia question about Jonesy\'s gaming?',
                'correct_answer': 'Test answer',
                'question_type': 'single_answer'
            }
        
        # Mock the conversation handler
        async def mock_start_jam_approval(question_data):
            print(f"📧 MOCK: Would send DM to JAM with question: {question_data['question_text'][:50]}...")
            return True
        
        # Import the function we want to test
        try:
            from bot.tasks.scheduled import validate_startup_trivia_questions
            print("✅ Successfully imported validate_startup_trivia_questions")
        except ImportError as e:
            print(f"❌ Import failed: {e}")
            return False
        
        # Patch the database to use our mock
        import bot.tasks.scheduled as scheduled_module
        original_db = getattr(scheduled_module, 'db', None)
        scheduled_module.db = mock_db
        
        # Patch the AI and conversation handlers
        try:
            import bot.handlers.ai_handler
            import bot.handlers.conversation_handler
            
            bot.handlers.ai_handler.generate_ai_trivia_question = mock_generate_question
            bot.handlers.conversation_handler.start_jam_question_approval = mock_start_jam_approval
            print("✅ Successfully patched AI and conversation handlers")
        except ImportError:
            print("⚠️ AI/Conversation handlers not available - testing with mocks")
        
        # Run the validation function
        print("\n" + "="*60)
        print("🔬 RUNNING VALIDATION FUNCTION WITH ENHANCED LOGGING:")
        print("="*60)
        
        await validate_startup_trivia_questions()
        
        print("="*60)
        print("🔬 VALIDATION FUNCTION COMPLETE")
        print("="*60 + "\n")
        
        # Restore original db
        if original_db is not None:
            scheduled_module.db = original_db
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main test function"""
    print("🧪 Starting trivia validation test...")
    
    success = await test_trivia_validation()
    
    if success:
        print("✅ Test completed successfully!")
        print("\n📋 If you saw detailed STARTUP TRIVIA VALIDATION logs above,")
        print("   then the function is working and will run when the bot starts.")
        print("\n🚀 The next time your bot starts up with a properly configured")
        print("   environment, you should receive DMs for trivia question approval!")
    else:
        print("❌ Test failed - there may be import or other issues to resolve.")

if __name__ == "__main__":
    asyncio.run(main())
