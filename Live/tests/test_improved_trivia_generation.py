#!/usr/bin/env python3
"""
Test Improved Trivia Question Generation
Tests the new diverse, engaging trivia question system vs the old statistical approach.
"""

import asyncio
import sys
from unittest.mock import MagicMock, patch

def test_template_system_diversity():
    """Test that the new template system provides more diverse categories"""
    print("🧪 Testing template system diversity...")
    
    try:
        from bot.handlers.ai_handler import get_question_templates
        
        templates = get_question_templates()
        
        # Check that we have the new engaging categories
        expected_categories = [
            "genre_adventures",
            "gaming_milestones", 
            "series_explorer",
            "gaming_stories",
            "timeline_fun",
            "fun_facts",
            "multiple_choice_fun"
        ]
        
        found_categories = list(templates.keys())
        print(f"✅ Found categories: {found_categories}")
        
        missing_categories = []
        for category in expected_categories:
            if category not in found_categories:
                missing_categories.append(category)
        
        if missing_categories:
            print(f"❌ Missing expected categories: {missing_categories}")
            return False
        
        # Check that legacy stats have low weights
        legacy_templates = templates.get("legacy_stats", [])
        if legacy_templates:
            for template in legacy_templates:
                weight = template.get("weight", 1.0)
                if weight > 0.5:
                    print(f"❌ Legacy template has high weight: {weight}")
                    return False
                print(f"✅ Legacy template properly weighted: {weight}")
        
        # Check that new categories have higher weights
        high_weight_found = False
        for category, template_list in templates.items():
            if category != "legacy_stats":
                for template in template_list:
                    weight = template.get("weight", 1.0)
                    if weight >= 1.5:
                        high_weight_found = True
                        print(f"✅ Found high-weight engaging template: {weight} in {category}")
                        break
        
        if not high_weight_found:
            print("❌ No high-weight engaging templates found")
            return False
        
        print("✅ Template system diversity test passed")
        return True
        
    except Exception as e:
        print(f"❌ Template system diversity test failed: {e}")
        return False


def test_question_phrasing_improvement():
    """Test that question phrasing is more casual and engaging"""
    print("\n🧪 Testing question phrasing improvement...")
    
    try:
        from bot.handlers.ai_handler import get_question_templates
        
        templates = get_question_templates()
        
        # Check for casual, engaging phrasing
        engaging_phrases = []
        academic_phrases = []
        
        for category, template_list in templates.items():
            for template in template_list:
                question = template.get("template", "")
                question_lower = question.lower()
                
                # Check for engaging, casual phrasing
                if any(phrase in question_lower for phrase in [
                    "what horror game", "which rpg", "how many", 
                    "what's the shortest", "most recent", "first completed",
                    "took jonesy", "jonesy played", "jonesy completed"
                ]):
                    engaging_phrases.append(question[:50] + "...")
                
                # Check for overly academic phrasing
                if any(phrase in question_lower for phrase in [
                    "considering", "efficiency", "statistical", "playtime per episode",
                    "database analysis", "comparative analysis"
                ]):
                    academic_phrases.append(question[:50] + "...")
        
        print(f"✅ Found {len(engaging_phrases)} engaging question phrasings:")
        for phrase in engaging_phrases[:3]:  # Show first 3 examples
            print(f"   - {phrase}")
        
        if academic_phrases:
            print(f"⚠️ Found {len(academic_phrases)} potentially academic phrasings:")
            for phrase in academic_phrases[:2]:  # Show examples
                print(f"   - {phrase}")
        
        # Good if we have more engaging than academic
        if len(engaging_phrases) > len(academic_phrases) * 2:
            print("✅ Question phrasing successfully improved - more engaging than academic")
            return True
        else:
            print("❌ Still too many academic phrasings compared to engaging ones")
            return False
        
    except Exception as e:
        print(f"❌ Question phrasing test failed: {e}")
        return False


def test_weight_based_selection():
    """Test that the weight-based template selection works"""
    print("\n🧪 Testing weight-based template selection...")
    
    try:
        from bot.handlers.ai_handler import select_best_template, calculate_template_weights
        
        # Create mock games data
        mock_games = [
            {
                "canonical_name": "Resident Evil 4",
                "total_episodes": 20,
                "total_playtime_minutes": 1200,
                "genre": "horror",
                "completion_status": "completed"
            },
            {
                "canonical_name": "The Witcher 3",
                "total_episodes": 45,
                "total_playtime_minutes": 2700,
                "genre": "rpg", 
                "completion_status": "completed"
            },
            {
                "canonical_name": "Dead Space",
                "total_episodes": 12,
                "total_playtime_minutes": 720,
                "genre": "horror",
                "completion_status": "completed"
            }
        ]
        
        # Test template selection multiple times to check weight distribution
        selected_templates = []
        for i in range(10):
            selected = select_best_template(mock_games)
            if selected:
                category = selected.get("category", "unknown")
                weight = selected.get("weight", 0)
                selected_templates.append((category, weight))
        
        if not selected_templates:
            print("❌ No templates were selected")
            return False
        
        print(f"✅ Selected {len(selected_templates)} templates over 10 iterations")
        
        # Check category distribution
        categories = [cat for cat, _ in selected_templates]
        unique_categories = set(categories)
        print(f"✅ Found {len(unique_categories)} unique categories: {list(unique_categories)}")
        
        # Check that higher weight templates are more likely
        weights = [weight for _, weight in selected_templates]
        avg_weight = sum(weights) / len(weights)
        print(f"✅ Average selected template weight: {avg_weight:.2f}")
        
        if avg_weight > 1.0:
            print("✅ Weight-based selection favors higher-weight templates")
            return True
        else:
            print("⚠️ Average weight is not higher than 1.0, selection may not be working optimally")
            return avg_weight > 0.8  # Accept if reasonably weighted
        
    except Exception as e:
        print(f"❌ Weight-based selection test failed: {e}")
        return False


async def test_ai_prompt_improvement():
    """Test that the AI prompt generates more casual questions"""
    print("\n🧪 Testing AI prompt improvement...")
    
    try:
        # Mock the AI call to test the prompt structure
        mock_prompt = None
        
        async def mock_ai_call(prompt, user_id, context=""):
            nonlocal mock_prompt
            mock_prompt = prompt
            # Return a mock casual response
            return '''{"question_text": "What horror game did Jonesy play most recently?", "question_type": "single_answer", "correct_answer": "Dead Space", "is_dynamic": false, "category": "ai_generated"}''', "success"
        
        # Patch the AI handler
        with patch('bot.handlers.ai_handler.call_ai_with_rate_limiting', mock_ai_call):
            with patch('bot.handlers.ai_handler.db') as mock_db:
                # Mock database responses
                mock_db.get_all_played_games.return_value = [
                    {"canonical_name": "Dead Space", "genre": "horror", "total_episodes": 10}
                ]
                mock_db.get_played_games_stats.return_value = {"total_games": 1}
                
                from bot.handlers.ai_handler import generate_ai_trivia_question
                
                # This should fall back to AI generation
                with patch('bot.handlers.ai_handler.select_best_template', return_value=None):
                    result = await generate_ai_trivia_question("test")
        
        if mock_prompt is None:
            print("❌ AI prompt was not captured")
            return False
        
        print(f"✅ AI prompt captured ({len(mock_prompt)} characters)")
        
        # Check for improved prompt characteristics
        prompt_lower = mock_prompt.lower()
        
        # Check for casual, engaging language
        engaging_indicators = [
            "fun trivia question", "casual and interesting", "friends chatting",
            "gaming experiences", "conversational and engaging"
        ]
        
        academic_indicators = [
            "statistical breakdown", "comparative analysis", "database analysis",
            "playtime efficiency", "considering"
        ]
        
        engaging_found = sum(1 for phrase in engaging_indicators if phrase in prompt_lower)
        academic_found = sum(1 for phrase in academic_indicators if phrase in prompt_lower)
        
        print(f"✅ Found {engaging_found} engaging indicators in prompt")
        print(f"⚠️ Found {academic_found} academic indicators in prompt")
        
        # Check for specific question type suggestions
        if "genre adventures" in prompt_lower and "gaming milestones" in prompt_lower:
            print("✅ Prompt includes diverse question type suggestions")
        else:
            print("⚠️ Prompt may be missing diverse question type suggestions")
        
        if engaging_found > academic_found:
            print("✅ AI prompt successfully improved - more engaging than academic")
            return True
        else:
            print("❌ AI prompt still contains too much academic language")
            return False
        
    except Exception as e:
        print(f"❌ AI prompt improvement test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_question_generation_end_to_end():
    """Test complete question generation with improved system"""
    print("\n🧪 Testing end-to-end question generation...")
    
    try:
        # Mock a comprehensive games database
        mock_games = [
            {
                "canonical_name": "Resident Evil 4",
                "total_episodes": 20,
                "total_playtime_minutes": 1200,
                "genre": "horror",
                "completion_status": "completed",
                "series_name": "Resident Evil"
            },
            {
                "canonical_name": "The Witcher 3",
                "total_episodes": 45, 
                "total_playtime_minutes": 2700,
                "genre": "rpg",
                "completion_status": "completed",
                "series_name": "The Witcher"
            },
            {
                "canonical_name": "Dead Space",
                "total_episodes": 12,
                "total_playtime_minutes": 720,
                "genre": "horror", 
                "completion_status": "completed",
                "series_name": "Dead Space"
            },
            {
                "canonical_name": "Cyberpunk 2077",
                "total_episodes": 8,
                "total_playtime_minutes": 480,
                "genre": "rpg",
                "completion_status": "ongoing",
                "series_name": None
            }
        ]
        
        # Test template-based generation
        from bot.handlers.ai_handler import select_best_template, execute_answer_logic
        
        generated_questions = []
        
        for attempt in range(5):
            selected_template = select_best_template(mock_games)
            if selected_template:
                question_data = execute_answer_logic(
                    selected_template["answer_logic"],
                    mock_games,
                    selected_template
                )
                
                if question_data and question_data.get("question_text"):
                    generated_questions.append({
                        "question": question_data["question_text"],
                        "answer": question_data.get("correct_answer", "Unknown"),
                        "category": selected_template.get("category", "unknown"),
                        "generation_method": "template"
                    })
        
        print(f"✅ Generated {len(generated_questions)} template-based questions:")
        for i, q in enumerate(generated_questions[:3], 1):  # Show first 3
            print(f"   {i}. [{q['category']}] {q['question']}")
            print(f"      Answer: {q['answer']}")
        
        if len(generated_questions) >= 3:
            # Check diversity
            categories = [q['category'] for q in generated_questions]
            unique_categories = len(set(categories))
            
            if unique_categories >= 2:
                print(f"✅ Generated questions span {unique_categories} different categories")
            else:
                print(f"⚠️ Generated questions only span {unique_categories} category")
            
            # Check question quality (not all about playtime)
            playtime_questions = [q for q in generated_questions if 'playtime' in q['question'].lower() or 'longest' in q['question'].lower()]
            
            if len(playtime_questions) < len(generated_questions) / 2:
                print(f"✅ Only {len(playtime_questions)}/{len(generated_questions)} questions are about playtime - good diversity!")
                return True
            else:
                print(f"⚠️ {len(playtime_questions)}/{len(generated_questions)} questions still focus on playtime")
                return False
        else:
            print("❌ Not enough questions generated for diversity testing")
            return False
        
    except Exception as e:
        print(f"❌ End-to-end generation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test execution"""
    print("🚀 Starting Improved Trivia Question Generation Tests...")
    print("=" * 60)
    
    # Run all tests
    tests = [
        ("Template System Diversity", test_template_system_diversity),
        ("Question Phrasing Improvement", test_question_phrasing_improvement),
        ("Weight-Based Selection", test_weight_based_selection),
        ("Question Generation End-to-End", test_question_generation_end_to_end),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Run async AI prompt test
    print("\n" + "=" * 60)
    try:
        ai_prompt_result = asyncio.run(test_ai_prompt_improvement())
        results.append(("AI Prompt Improvement", ai_prompt_result))
    except Exception as e:
        print(f"❌ AI Prompt test crashed: {e}")
        results.append(("AI Prompt Improvement", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print("=" * 60)
    print(f"📈 OVERALL: {passed}/{len(results)} tests passed ({passed/len(results)*100:.1f}%)")
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! Trivia question generation successfully improved.")
        print("\n🎯 KEY IMPROVEMENTS:")
        print("   • More casual, engaging question phrasing")
        print("   • Diverse categories beyond playtime statistics")
        print("   • Weight-based selection favoring interesting questions")
        print("   • Template system with gaming milestones and stories")
        return True
    else:
        print(f"⚠️  {failed} test(s) failed - review implementation")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
