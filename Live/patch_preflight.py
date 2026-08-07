import re
import sys

with open(r'bot\tasks\trivia_preflight.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the randomized logic in _background_question_generation
random_logic = """                # ✅ FIX #2: Pass recently generated questions AND templates to avoid repetition
                import random

                from ..handlers.ai_handler import generate_contextual_trivia

                # 50% chance to use the new contextual clip/game lore generator
                if random.random() < 0.5:
                    print("🔄 BACKGROUND GENERATION: Using new contextual/clip trivia generator")
                    question_data = await generate_contextual_trivia()
                else:
                    print("🔄 BACKGROUND GENERATION: Using classic Trivia Director")
                    question_data = await generate_ai_trivia_question(
                        unique_context,
                        avoid_questions=generated_question_texts,
                        avoid_templates=used_template_ids  # ✅ NEW: Prevent template reuse in batch
                    )"""

replacement_logic = """                # ✅ FIX #2: Pass recently generated questions AND templates to avoid repetition
                print("🔄 BACKGROUND GENERATION: Using unified Trivia Director")
                question_data = await generate_ai_trivia_question(
                    unique_context,
                    avoid_questions=generated_question_texts,
                    avoid_templates=used_template_ids  # ✅ NEW: Prevent template reuse in batch
                )"""

content = content.replace(random_logic, replacement_logic)

with open(r'bot\tasks\trivia_preflight.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied for trivia_preflight.py")
