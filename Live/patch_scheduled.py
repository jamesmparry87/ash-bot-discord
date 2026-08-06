import re
import sys

with open(r'bot\tasks\scheduled.py', 'r', encoding='utf-8') as f:
    content = f.read()

fallback_block = """            # STEP 2: Fallback to querying available questions (same logic as manual !starttrivia)
            print("🔄 TRIVIA AUTO-START: No pre-approved question, querying available pool...")
            try:
                available_questions = db.get_available_trivia_questions()  # type: ignore

                if not available_questions or len(available_questions) == 0:
                    error_msg = "No available questions found in pool - trivia cannot run automatically. Use !starttrivia with a specific question ID or add new questions."
                    await notify_scheduled_message_error("Trivia Tuesday", error_msg, uk_now)
                    print(f"❌ TRIVIA BLOCKED: {error_msg}")
                    return

                # Select first available (highest priority - matches manual !starttrivia logic)
                question_data = available_questions[0]
                print(
                    f"✅ TRIVIA AUTO-START: Auto-selected question #{question_data['id']} from available pool ({len(available_questions)} questions available)")

                # NOTIFY JAM ABOUT FALLBACK
                try:
                    from ..config import JAM_USER_ID
                    if bot:
                        user = await bot.fetch_user(JAM_USER_ID)
                        if user:
                            await user.send(
                                f"⚠️ **Trivia Tuesday Auto-Fallback Triggered**\\n\\n"
                                f"No pre-approved question was found for today's Trivia Tuesday.\\n"
                                f"The system has automatically selected and posted question #{question_data['id']} from the available pool.\\n"
                                f"Pool size remaining: {len(available_questions) - 1}"
                            )
                except Exception as notify_err:
                    print(f"⚠️ Failed to send fallback notification: {notify_err}")

            except Exception as pool_error:"""

# Let's use string replace for safety.
search_str = """            # STEP 2: Fallback to querying available questions (same logic as manual !starttrivia)
            print("🔄 TRIVIA AUTO-START: No pre-approved question, querying available pool...")
            try:
                available_questions = db.get_available_trivia_questions()  # type: ignore

                if not available_questions or len(available_questions) == 0:
                    error_msg = "No available questions found in pool - trivia cannot run automatically. Use !starttrivia with a specific question ID or add new questions."
                    await notify_scheduled_message_error("Trivia Tuesday", error_msg, uk_now)
                    print(f"❌ TRIVIA BLOCKED: {error_msg}")
                    return

                # Select first available (highest priority - matches manual !starttrivia logic)
                question_data = available_questions[0]
                print(
                    f"✅ TRIVIA AUTO-START: Auto-selected question #{question_data['id']} from available pool ({len(available_questions)} questions available)")

            except Exception as pool_error:"""

# The line break before except is tricky. We'll find the precise block.
pattern = re.compile(r"            # STEP 2: Fallback to querying available questions.*?print\(\s*f\"✅ TRIVIA AUTO-START: Auto-selected question #\{question_data\['id'\]\}.*?\)", re.DOTALL)

replacement = """            # STEP 2: Fallback to querying available questions (same logic as manual !starttrivia)
            print("🔄 TRIVIA AUTO-START: No pre-approved question, querying available pool...")
            try:
                available_questions = db.get_available_trivia_questions()  # type: ignore

                if not available_questions or len(available_questions) == 0:
                    error_msg = "No available questions found in pool - trivia cannot run automatically. Use !starttrivia with a specific question ID or add new questions."
                    await notify_scheduled_message_error("Trivia Tuesday", error_msg, uk_now)
                    print(f"❌ TRIVIA BLOCKED: {error_msg}")
                    return

                # Select first available (highest priority - matches manual !starttrivia logic)
                question_data = available_questions[0]
                print(
                    f"✅ TRIVIA AUTO-START: Auto-selected question #{question_data['id']} from available pool ({len(available_questions)} questions available)")

                # NOTIFY JAM ABOUT FALLBACK
                try:
                    from ..config import JAM_USER_ID
                    if bot:
                        user = await bot.fetch_user(JAM_USER_ID)
                        if user:
                            await user.send(
                                f"⚠️ **Trivia Tuesday Auto-Fallback Triggered**\\n\\n"
                                f"No pre-approved question was found for today's Trivia Tuesday.\\n"
                                f"The system has automatically selected and posted question #{question_data['id']} from the available pool.\\n"
                                f"Pool size remaining: {len(available_questions) - 1}"
                            )
                except Exception as notify_err:
                    print(f"⚠️ Failed to send fallback notification: {notify_err}")"""

content = pattern.sub(replacement, content)

with open(r'bot\tasks\scheduled.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied for scheduled.py")
