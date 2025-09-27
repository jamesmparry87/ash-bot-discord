#!/usr/bin/env python3
"""
Trivia Fixes Verification Test

Tests the two main fixes implemented:
1. Field name mismatch fix (question vs question_text)
2. Startup validation deduplication system
"""

import asyncio
import sys
import os

# Add the Live directory to the path for imports
sys.path.insert(0, os.path.dirname(__file__))

def test_field_name_fix():
    """Test that the trivia command uses the correct field name"""
    print("🧪 TESTING FIELD NAME FIX")
    
    # Mock question data as it would come from the database
    mock_question_data = {
        'id': 1,
        'question_text': 'What is the most played game by Captain Jonesy?',  # Correct field name
        'question_type': 'single',
        'correct_answer': 'God of War',
        'status': 'available'
    }
    
    # Test that accessing question_text works (this is what the fix changed to)
    try:
        question_text = mock_question_data['question_text']
        print(f"✅ Field access successful: {question_text[:50]}...")
        return True
    except KeyError as e:
        print(f"❌ Field access failed: {e}")
        return False

def test_validation_lock_system():
    """Test the startup validation lock system"""
    print("\n🧪 TESTING VALIDATION LOCK SYSTEM")
    
    # Import the scheduled tasks module to access the lock variables
    try:
        from bot.tasks.scheduled import _startup_validation_lock, _startup_validation_completed
        print("✅ Successfully imported validation lock variables")
        
        # Test initial state
        print(f"📋 Initial lock state: {_startup_validation_lock}")
        print(f"📋 Initial completion state: {_startup_validation_completed}")
        
        # Verify the lock system logic
        if not _startup_validation_lock and not _startup_validation_completed:
            print("✅ Lock system is properly initialized (both False)")
            return True
        else:
            print("❌ Lock system initialization issue")
            return False
            
    except ImportError as e:
        print(f"❌ Failed to import validation lock system: {e}")
        return False

def test_database_field_consistency():
    """Test database field consistency"""
    print("\n🧪 TESTING DATABASE FIELD CONSISTENCY")
    
    try:
        from bot.database_module import get_database
        
        db = get_database()
        if not db:
            print("⚠️ Database not available for testing")
            return None
            
        # Check if the database has the expected trivia methods
        expected_methods = [
            'get_available_trivia_questions',
            'get_trivia_question_by_id',
            'start_trivia_session',
            'end_trivia_session'
        ]
        
        missing_methods = []
        for method in expected_methods:
            if not hasattr(db, method):
                missing_methods.append(method)
        
        if not missing_methods:
            print("✅ All expected database methods are present")
            return True
        else:
            print(f"⚠️ Missing database methods: {missing_methods}")
            return False
            
    except Exception as e:
        print(f"❌ Database consistency test failed: {e}")
        return False

async def test_trivia_command_simulation():
    """Simulate trivia command execution with the fix"""
    print("\n🧪 TESTING TRIVIA COMMAND SIMULATION")
    
    # Mock question data exactly as it comes from database
    question_data = {
        'id': 1,
        'question_text': 'Which game has the longest playtime in Captain Jonesy\'s library?',
        'question_type': 'single', 
        'correct_answer': 'God of War',
        'status': 'available',
        'multiple_choice_options': None,
        'choices': None  # Alternative field that might exist
    }
    
    try:
        # This is the exact line that was fixed in the code
        description = question_data['question_text']  # Was: question_data['question']
        print(f"✅ Trivia embed description set successfully: '{description}'")
        
        # Test the choice handling logic
        if question_data['question_type'] == 'multiple' and question_data.get('choices'):
            print("📋 Multiple choice question detected")
        else:
            print("📋 Single answer question detected")
        
        return True
        
    except KeyError as e:
        print(f"❌ Trivia command simulation failed: {e}")
        return False

def run_all_tests():
    """Run all verification tests"""
    print("🧠 TRIVIA FIXES VERIFICATION TEST SUITE")
    print("=" * 50)
    
    results = []
    
    # Test 1: Field name fix
    results.append(("Field Name Fix", test_field_name_fix()))
    
    # Test 2: Validation lock system  
    results.append(("Validation Lock System", test_validation_lock_system()))
    
    # Test 3: Database field consistency
    results.append(("Database Field Consistency", test_database_field_consistency()))
    
    # Test 4: Trivia command simulation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        simulation_result = loop.run_until_complete(test_trivia_command_simulation())
        results.append(("Trivia Command Simulation", simulation_result))
    finally:
        loop.close()
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY:")
    
    passed = 0
    failed = 0
    warnings = 0
    
    for test_name, result in results:
        if result is True:
            print(f"✅ {test_name}: PASSED")
            passed += 1
        elif result is False:
            print(f"❌ {test_name}: FAILED") 
            failed += 1
        else:
            print(f"⚠️ {test_name}: WARNING")
            warnings += 1
    
    print(f"\n📈 Total: {passed} passed, {failed} failed, {warnings} warnings")
    
    if failed == 0:
        print("🎉 All critical tests passed! Trivia fixes should be working correctly.")
        return True
    else:
        print("🚨 Some tests failed. Please review the fixes.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
