---
name: trivia_generator_sandbox
description: >-
  Use this skill to test the AI trivia generation pipeline offline without running a live Discord session.
  Allows you to force specific categories, view the generated JSON payloads, and validate URLs.
---

# Trivia Generator Sandbox

This skill provides a testing environment for the `generate_ai_trivia_question` function. It allows agents or users to verify prompt changes, test new categories, and validate the final generated questions and dynamic query types without needing to initiate a live Trivia Tuesday session in Discord.

## Workflow Instructions

When invoked to test trivia generation, execute the following steps:

### 1. Pre-flight Validation
Verify that the bot environment is configured correctly. The script expects the `.env` file to contain a valid `DATABASE_URL` and AI API keys.
- *Action*: Ensure `Live/.env` is properly populated.

### 2. Execution (Dry-Run Simulation)
Run the sandbox script to generate questions. You can pass a specific category to force the generator to test a specific branch of logic.
- *Action*: Run `python .agents/skills/trivia_generator_sandbox/scripts/sandbox.py --category Clip_Famous_Last_Words`
- *Validation*: Review the output to verify the question text, decoys, and particularly the `dynamic_query_type` (like `clip_url` or `clip_index`) mapping.

### 3. Verification & Reporting
- Report the generated test questions to the user.
- If testing a prompt change, confirm whether the AI successfully followed the new prompt instructions based on the sandbox output.
