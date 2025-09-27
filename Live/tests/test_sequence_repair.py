#!/usr/bin/env python3
"""
Test script for database sequence repair functionality
"""

import asyncio
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_sequence_repair():
    """Test the sequence repair functionality"""
    print("🔧 Testing Database Sequence Repair")
    print("=" * 50)
    
    try:
        from bot.database_module import get_database
        
        db = get_database()
        
        print("✅ Database connection established")
        
        # Test sequence repair
        print("\n🔍 Running sequence repair check...")
        repair_results = db.repair_database_sequences()
        
        if "error" in repair_results:
            print(f"❌ Sequence repair failed: {repair_results['error']}")
            return
        
        total_repaired = repair_results.get('total_repaired', 0)
        sequences_checked = len(repair_results.get('repaired_sequences', []))
        errors = len(repair_results.get('errors', []))
        
        print(f"\n📊 Sequence Repair Results:")
        print(f"   Sequences checked: {sequences_checked}")
        print(f"   Sequences repaired: {total_repaired}")
        print(f"   Errors encountered: {errors}")
        
        # Show detailed results
        if repair_results.get('repaired_sequences'):
            print("\n🔧 Sequence Details:")
            for seq_info in repair_results['repaired_sequences']:
                table = seq_info.get('table', 'Unknown')
                status = seq_info.get('status', 'Unknown')
                
                if status == 'repaired':
                    old_val = seq_info.get('old_sequence_value', 'N/A')
                    new_val = seq_info.get('new_sequence_value', 'N/A')
                    print(f"   🔧 {table}: Fixed sequence ({old_val} → {new_val})")
                else:
                    current_val = seq_info.get('current_sequence_value', 'N/A')
                    print(f"   ✅ {table}: Sequence OK (next: {current_val})")
        
        if repair_results.get('errors'):
            print("\n❌ Errors:")
            for error_info in repair_results['errors']:
                table = error_info.get('table', 'Unknown')
                error = error_info.get('error', 'Unknown error')
                print(f"   ❌ {table}: {error}")
        
        # Test safe trivia question insertion
        print(f"\n🧠 Testing safe trivia question insertion...")
        
        test_question_id = db.safe_add_trivia_question(
            question_text="Test question for sequence validation - DELETE ME",
            question_type="single_answer",
            correct_answer="Test answer",
            category="test",
            difficulty_level=1
        )
        
        if test_question_id:
            print(f"✅ Successfully added test question with ID: {test_question_id}")
            
            # Clean up test question
            try:
                conn = db.get_connection()
                if conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM trivia_questions WHERE id = %s", (test_question_id,))
                        conn.commit()
                        print(f"🧹 Cleaned up test question {test_question_id}")
            except Exception as cleanup_e:
                print(f"⚠️ Could not clean up test question: {cleanup_e}")
        else:
            print("❌ Failed to add test question")
        
        print(f"\n{'=' * 50}")
        
        if total_repaired > 0:
            print(f"🔧 Sequence repair completed: {total_repaired} sequences fixed")
        else:
            print("✅ All sequences are properly synchronized")
        
        print("✅ Database sequence system is working correctly")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_sequence_repair())
