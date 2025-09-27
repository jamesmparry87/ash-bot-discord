#!/usr/bin/env python3
"""
Test script for manual approval system functionality
"""

import asyncio
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_manual_approval_system():
    """Test the manual approval command system"""
    print("🧠 Testing Manual Approval System")
    print("=" * 50)

    try:
        from bot.database_module import get_database

        db = get_database()

        print("✅ Database connection established")

        # Test database methods used by approval system
        print("\n🔍 Testing required database methods...")

        required_methods = [
            'get_next_trivia_question',
            'get_trivia_question_by_id',
            'calculate_dynamic_answer',
            'add_trivia_question'
        ]

        method_status = {}
        for method in required_methods:
            if hasattr(db, method):
                method_status[method] = "✅ Available"
                print(f"   ✅ {method}: Available")
            else:
                method_status[method] = "❌ Missing"
                print(f"   ❌ {method}: Missing")

        # Test conversation handler imports
        print("\n🔗 Testing conversation handler integration...")
        try:
            from bot.handlers.conversation_handler import start_jam_question_approval
            print("   ✅ start_jam_question_approval: Available")
        except ImportError as e:
            print(f"   ❌ start_jam_question_approval: Missing - {e}")

        try:
            from bot.handlers.conversation_handler import jam_approval_conversations
            print("   ✅ jam_approval_conversations: Available")
        except ImportError as e:
            print(f"   ❌ jam_approval_conversations: Missing - {e}")

        # Test AI handler integration
        print("\n🤖 Testing AI handler integration...")
        try:
            from bot.handlers.ai_handler import ai_enabled
            print(f"   ✅ AI system status: {'Enabled' if ai_enabled else 'Disabled'}")
        except ImportError as e:
            print(f"   ❌ AI handler: Not available - {e}")

        # Test question database operations
        print("\n📊 Testing question database operations...")

        try:
            # Test getting next question (auto-selection)
            if hasattr(db, 'get_next_trivia_question'):
                next_question = db.get_next_trivia_question()
                if next_question:
                    print(f"   ✅ Auto-selection: Found question #{next_question.get('id', 'Unknown')}")
                    print(f"      Question: {next_question.get('question_text', 'No text')[:50]}...")
                else:
                    print("   ⚠️ Auto-selection: No available questions found")
            else:
                print("   ❌ Auto-selection: Method not available")
        except Exception as e:
            print(f"   ❌ Auto-selection error: {e}")

        try:
            # Test getting available questions
            if hasattr(db, 'get_available_trivia_questions'):
                available = db.get_available_trivia_questions()
                print(f"   ✅ Available questions: {len(available)} found")
            elif hasattr(db, 'get_pending_trivia_questions'):
                pending = db.get_pending_trivia_questions()
                print(f"   ✅ Pending questions: {len(pending)} found")
            else:
                print("   ❌ Question listing: No available methods")
        except Exception as e:
            print(f"   ❌ Question listing error: {e}")

        # Test question statistics
        print("\n📈 Testing trivia question statistics...")

        try:
            if hasattr(db, 'get_trivia_question_statistics'):
                stats = db.get_trivia_question_statistics()
                print(f"   ✅ Question statistics:")
                print(f"      Total questions: {stats.get('total_questions', 0)}")
                print(f"      Available: {stats.get('available_questions', 0)}")
                print(f"      Answered: {stats.get('answered_questions', 0)}")
            else:
                print("   ⚠️ Question statistics: Method not available")
        except Exception as e:
            print(f"   ❌ Statistics error: {e}")

        print(f"\n{'=' * 50}")

        # Summary
        missing_methods = [method for method, status in method_status.items() if "Missing" in status]

        if missing_methods:
            print(f"⚠️ Manual approval system has some limitations:")
            for method in missing_methods:
                print(f"   • {method} method needs implementation")
        else:
            print("✅ All required database methods are available")

        print(f"\n🎯 Manual Approval Commands:")
        print(f"   • !approvequestion <id> - Send specific question for approval")
        print(f"   • !approvequestion auto - Send auto-selected question")
        print(f"   • !approvequestion generate - Generate and send AI question")
        print(f"   • !approvestatus - Check pending approval status")

        print(f"\n✅ Manual approval system testing complete")

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_manual_approval_system())
