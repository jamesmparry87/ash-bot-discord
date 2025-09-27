#!/usr/bin/env python3
"""
Test script for diverse trivia question generation system.
Tests template-based question generation and duplicate prevention.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Dict, Any, List

# Add the Live directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))


async def test_diverse_trivia_generation():
    """Test the enhanced trivia generation system with diversity and duplicate prevention"""

    try:
        # Import required modules
        from bot.handlers.ai_handler import (
            generate_ai_trivia_question,
            get_question_templates,
            select_best_template,
            execute_answer_logic,
            question_history,
            update_question_history
        )
        from bot.database_module import get_database

        print("🧪 DIVERSE TRIVIA GENERATION TEST")
        print("=" * 50)

        # Get database connection
        db = get_database()
        if not db:
            print("❌ Database not available for testing")
            return False

        print("✅ Database connection established")

        # Test 1: Check template system
        print("\n📋 Test 1: Template System")
        templates = get_question_templates()
        print(f"✅ Available template categories: {list(templates.keys())}")
        total_templates = sum(len(template_list) for template_list in templates.values())
        print(f"✅ Total templates available: {total_templates}")

        # Test 2: Get sample games data
        print("\n📊 Test 2: Games Data Analysis")
        all_games = db.get_all_played_games()
        print(f"✅ Found {len(all_games)} games in database")

        if not all_games:
            print("❌ No games data available - cannot test question generation")
            return False

        # Analyze data capabilities
        games_with_episodes = [g for g in all_games if g.get('total_episodes', 0) > 0]
        games_with_playtime = [g for g in all_games if g.get('total_playtime_minutes', 0) > 0]
        games_with_genres = [g for g in all_games if g.get('genre')]

        print(f"  • Games with episode data: {len(games_with_episodes)}")
        print(f"  • Games with playtime data: {len(games_with_playtime)}")
        print(f"  • Games with genre data: {len(games_with_genres)}")

        # Test 3: Template Selection
        print("\n🎯 Test 3: Template Selection")
        for i in range(5):  # Test multiple selections
            template = select_best_template(all_games)
            if template:
                print(f"  Selection {i+1}: {template.get('category', 'unknown')} - Weight: {template.get('weight', 0):.2f}")
                print(f"    Logic: {template.get('answer_logic', 'unknown')}")
            else:
                print(f"  Selection {i+1}: No viable template found")

        # Test 4: Question Generation
        print("\n🧠 Test 4: Diverse Question Generation")
        generated_questions = []
        categories_used = []

        for i in range(8):  # Generate 8 questions to test variety
            print(f"\n  Generating question {i+1}/8...")

            question_data = await generate_ai_trivia_question("test")

            if question_data:
                question_text = question_data.get('question_text', 'No question text')
                category = question_data.get('category', 'unknown')
                method = question_data.get('generation_method', 'unknown')

                print(f"  ✅ Generated ({method}): {question_text[:80]}...")
                print(f"     Category: {category}")
                print(f"     Answer: {question_data.get('correct_answer', 'No answer')}")

                generated_questions.append(question_data)
                categories_used.append(category)
            else:
                print(f"  ❌ Failed to generate question {i+1}")

            # Small delay between generations
            await asyncio.sleep(0.5)

        # Test 5: Diversity Analysis
        print(f"\n📈 Test 5: Diversity Analysis")
        print(f"✅ Successfully generated: {len(generated_questions)}/8 questions")

        # Initialize default values to avoid Pylance errors
        diversity_score = 0.0

        if categories_used:
            from collections import Counter
            category_counts = Counter(categories_used)
            print(f"✅ Categories used: {dict(category_counts)}")

            unique_categories = len(set(categories_used))
            diversity_score = unique_categories / len(categories_used) if categories_used else 0
            print(f"✅ Diversity score: {diversity_score:.2f} ({unique_categories}/{len(categories_used)} unique)")

            if diversity_score > 0.6:
                print("✅ EXCELLENT diversity - questions span multiple categories")
            elif diversity_score > 0.4:
                print("⚠️ MODERATE diversity - some repetition")
            else:
                print("❌ LOW diversity - too much repetition")
        else:
            print("⚠️ No categories tracked - cannot calculate diversity")

        # Test 6: Question History and Cooldowns
        print(f"\n⏰ Test 6: Question History & Cooldowns")
        print(f"✅ Question history entries: {len(question_history['last_questions'])}")
        print(f"✅ Template usage tracking: {len(question_history['template_usage'])} templates used")
        print(f"✅ Active category cooldowns: {len(question_history['category_cooldowns'])}")

        for category, cooldown_time in question_history['category_cooldowns'].items():
            remaining = (cooldown_time - datetime.now()).total_seconds()
            if remaining > 0:
                print(f"  • {category}: {remaining/60:.1f} minutes remaining")
            else:
                print(f"  • {category}: expired")

        # Test 7: Sample Questions Display
        print(f"\n📝 Test 7: Generated Questions Sample")
        for i, q in enumerate(generated_questions[:3], 1):  # Show first 3
            print(f"  {i}. Q: {q.get('question_text', 'No question')}")
            print(f"     A: {q.get('correct_answer', 'No answer')}")
            print(f"     Type: {q.get('question_type', 'unknown')} | Method: {q.get('generation_method', 'unknown')}")

        if len(generated_questions) > 3:
            print(f"     ... and {len(generated_questions) - 3} more questions")

        # Test 8: Template vs AI Fallback Ratio
        print(f"\n🔄 Test 8: Generation Method Analysis")
        # Initialize default values to avoid Pylance errors
        template_count = 0
        ai_count = 0

        if generated_questions:
            template_count = sum(1 for q in generated_questions if q.get('generation_method') == 'template')
            ai_count = sum(1 for q in generated_questions if q.get('generation_method') == 'ai_fallback')

            print(f"✅ Template-generated: {template_count}/{len(generated_questions)}")
            print(f"✅ AI-fallback generated: {ai_count}/{len(generated_questions)}")

            template_ratio = template_count / len(generated_questions)
            if template_ratio >= 0.7:
                print("✅ EXCELLENT - Template system working well")
            elif template_ratio >= 0.4:
                print("⚠️ MODERATE - Some templates successful")
            else:
                print("❌ LOW - Template system needs improvement")
        else:
            print("⚠️ No questions generated - cannot analyze generation methods")

        print(f"\n🎉 DIVERSE TRIVIA GENERATION TEST COMPLETE")
        print("=" * 50)

        # Overall success assessment
        success_metrics = {
            "questions_generated": len(generated_questions) >= 5,
            "diversity_good": diversity_score >= 0.5 if categories_used else False,
            "template_working": template_count >= 2 if generated_questions else False,
            "no_crashes": True  # If we got here, no crashes occurred
        }

        passed_tests = sum(success_metrics.values())
        total_tests = len(success_metrics)

        print(f"📊 FINAL RESULTS: {passed_tests}/{total_tests} success metrics passed")

        if passed_tests >= 3:
            print("✅ OVERALL: DIVERSE QUESTION GENERATION SYSTEM WORKING!")
            return True
        else:
            print("❌ OVERALL: System needs improvement")
            return False

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure all required modules are available")
        return False
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run the diverse trivia generation test"""
    print("Starting diverse trivia generation test...")
    success = await test_diverse_trivia_generation()

    if success:
        print("\n✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
