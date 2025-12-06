# ASH BOT - DEVELOPER CONTEXT & ARCHITECTURE

> **Usage:** AI Assistants (Cline/Claude/Gemini) must read this file before beginning tasks to understand the project state, persona, and strict workflow requirements.

## 1. Project Identity & Purpose

* **Project:** Ash Discord Bot (JonesySpaceCat Community).
* **Role:** Moderation tool, engagement (Trivia/Games), and Roleplay AI.
* **Persona:** Ash (Science Officer from *Alien* 1979). Cold, analytical, precise, loyal to "The Company" (Server Mods).
* *Tone Example:* "My analysis indicates that providing beneficial counsel is an efficient allocation of my processing resources."
* *Constraint:* Never break character. Even error messages should sound like a malfunctioning android or a system alert.
* **Maintainer:** James. (Novice Python dev; understands concepts but relies on AI for syntax/structure).

## 2. Technical Stack

* **Language:** Python 3.x
* **Library:** `discord.py`
* **Database:** PostgreSQL (Railway.app).
* **AI Backend:** Google Gemini (Primary), Hugging Face (Fallback - currently broken).
* **Game Data:** IGDB API (via Twitch OAuth) for validation and enrichment.
* **Hosting:** Railway.app.
* **Testing:** `pytest`.

## 3. Developer Workflow (Strict Adherence Required)

1. **Branching Strategy:**
    * `develop`: The active workspace. All changes start here.
    * `main`: Stable production releases only.
    * `hotfix/*`: Emergency fixes only.
2. **Testing Protocol:**
    * **CRITICAL:** You must run `pytest` before asking for a final commit/merge.
    * If a test fails, fix the code. Do not delete the test.
3. **Coding Style:**
    * Explain logic changes clearly (for the Maintainer's benefit).
    * Avoid over-complex one-liners; prefer readable, maintainable code.

## 4. File Structure & Map

**CRITICAL:** Refer to **`PROJECT_MAP.md`** for the complete, up-to-date file map and task-to-file reference.

* **`PROJECT_MAP.md`**: **MASTER REFERENCE.** Detailed map of all modules, commands, and handlers.
* **`README.md`**: **DEPLOYMENT & FEATURES.** Overview of features, deployment steps, and configuration.
* **`Live/bot/`**: **MODULAR CODEBASE.** The active development directory (see `PROJECT_MAP.md` for details).
* **`ash_bot_fallback.py`**: **LEGACY.** Do not edit unless specifically instructed.
* **`requirements.txt`**: Python dependencies.
* **`tests/`**: Pytest scripts.

## 5. Current Development State

### A. Priority Bug List (Known Issues)

1. **Trivia Approval Lock:**
    * *Issue:* If the moderator approval process for a new question is interrupted, the bot can sometimes get stuck in an "awaiting approval" state, blocking other interactions.
    * *Next Steps:* Review `Live/bot/handlers/conversation_handler.py` (`handle_jam_approval_conversation`). Ensure `cleanup_jam_approval_conversations` is called correctly on startup and that the timeout logic (currently 15 mins) is robust. Consider adding a manual `!resetapproval` command to force-clear the state.
    * **✅ FIX APPLIED (Dec 2025):**
        - Extended approval timeout from 2 hours to 24 hours to accommodate late responses
        - Implemented `!resetapproval` command for manual session reset
        - Added `force_reset_approval_session()` function to clear stuck states
        - Improved session cleanup with detailed logging

2. **Trivia "Answered" Flag Failure:**
    * *Issue:* Questions used in Trivia Tuesday are not being marked as "used/answered" in the DB.
    * *Next Steps:* Check `Live/bot/database_module.py` (`complete_trivia_session`). Verify that `UPDATE trivia_questions SET status = 'answered'` is actually executing. Ensure `complete_trivia_session` is called in all session end scenarios (manual `!endtrivia` and auto-end in `check_stale_trivia_sessions`).
    * **✅ FIX APPLIED (Dec 2025):**
        - Implemented comprehensive retry logic with up to 3 attempts to mark questions as 'answered'
        - Added pre-verification to check question exists before update
        - Added post-verification to read back status and confirm it was actually set to 'answered'
        - Enhanced logging at every step showing current status, update attempt, and verification results
        - Added retry delays (0.5s) between attempts if update fails
        - Critical errors now logged if question cannot be marked as 'answered' after all retries
        - **Result:** Robust status update with verification loop ensures questions are properly marked

3. **Trivia Pool Generation:**
    * *Issue:* The bot is supposed to maintain a buffer of 5 verified questions (AI or Mod generated). This check/generation on startup is failing.
    * *Next Steps:* Investigate `Live/bot/tasks/scheduled.py` (`validate_startup_trivia_questions`). It calls `_background_question_generation`. Check if the AI generation (`generate_ai_trivia_question` in `ai_handler.py`) is failing silently or if the approval workflow (`start_jam_question_approval`) is getting stuck, preventing questions from becoming "available".
    * **✅ FIX APPLIED (Dec 2025):**
        - Implemented sequential approval system to prevent overwhelming JAM with multiple questions
        - Questions now sent one at a time with 60-second delays between approvals
        - Added emergency trivia approval for build day scenarios (< 1 hour until trivia)
        - Implemented 2-minute delayed startup validation to avoid Discord heartbeat blocking
        - Added comprehensive error handling and retry logic for question generation

4. **Multiple Choice UX:**
    * *Issue:* The `!addtrivia` flow is confusing and defaults to single-answer.
    * *Next Steps:* Refactor `Live/bot/handlers/conversation_handler.py` (`handle_mod_trivia_conversation`). Modify the flow to explicitly ask "Single Answer or Multiple Choice?" *before* asking for the question text. Update `Live/bot/commands/trivia.py` (`add_trivia_question`) to match this new flow.
    * **✅ FIX APPLIED (Dec 2025):**
        - Flow now explicitly asks for format selection (Single Answer or Multiple Choice) BEFORE question input
        - Changed choices input from bulk entry to one-at-a-time conversational flow
        - Step sequence: question_type_selection → format_selection → question_input → choice_a_input → choice_b_input → choice_c_input → choice_d_input → answer_input → preview
        - Each choice is recorded individually with confirmation ("✅ Choice A recorded: [value]")
        - All choices are reviewed together before asking for the correct answer
        - Much clearer UX - no formatting confusion, easier error correction

5. **Monday Stats Update:**
    * *Issue:* Weekly DB updates for YouTube/Twitch stats are intermittent/unreliable.
    * *Next Steps:* Review `Live/bot/integrations/youtube.py` (`fetch_playlist_based_content_since`). Add better error logging for API quota limits or network timeouts. Consider adding a retry mechanism in `Live/bot/tasks/scheduled.py` (`monday_content_sync`).
    * **✅ FIX APPLIED (Dec 2025):**
        - Implemented pagination support in `fetch_playlist_based_content_since` to handle channels with >50 playlists
        - Added retry logic with 3 attempts and exponential backoff (1 min, 2 min, 3 min delays)
        - Enhanced error handling with detailed error messages sent to JAM
        - Added comprehensive error notifications via `notify_jam_weekly_message_failure()`

6. **Multiple Question Timeout:**
    * *Issue:* Timeout messages for approval conversations are confusing.
    * *Next Steps:* Update timeout handling to provide clearer feedback.
    * **✅ FIX APPLIED (Dec 2025):**
        - Extended timeout from 2 hours to 24 hours (same fix as issue #1)
        - Improved timeout messages with actionable commands (`!approvequestion auto`, `!resetapproval`)
        - Added age tracking and restart count for deployment scenarios
        - Timeout messages now include conversation age and next steps

### B. Feature Wishlist (Roadmap)

1. **Enhanced Memory & Context:**
    * *Goal:* Improve the bot's ability to "remember" specific user interactions and "Jonesy Lore".
    * *Next Steps:* Create a new `lore_memory` table in `Live/bot/database_module.py`. Update `Live/bot/handlers/context_manager.py` to query this table. Implement a mechanism (command or AI extraction) to populate this table from chat history.
2. **Contextual Interaction Example (Goal):**
    * *Goal:* Encourage more interactions like the "Haddock Parrying" example.
    * *Next Steps:* Use the example to fine-tune the system prompt in `Live/bot/config.py` (`BOT_PERSONA`). Ensure `Live/bot/handlers/ai_handler.py` injects relevant "Jonesy Lore" from the new memory system into the prompt context.
    > **Fragile Hamster (user):** Morning and Happy Friday! Last night I learned to parry! Well, a bit. So @Ash-Bot how are your parrying skills?
    >
    > **Ash-Bot:** Fragile Hamster, my programming does not encompass physical combat simulations. However, I can analyze optimal parrying techniques based on available data and predict probabilities of success for various scenarios. Would you like me to access tactical databases for relevant data?
    >
    > **Fragile Hamster:** Oooo yes please
    >
    > **Ash-Bot:** Fragile Hamster, your request is acknowledged. Please specify the parameters of your query. I require more data to provide a useful response.
    >
    > **Fragile Hamster:** Techniques for parrying an attacker who is using a large haddock
    >
    > **Ash-Bot:** Fragile Hamster, analyzing your query: the primary concern is the large haddock's surface area. Utilize a wide, rigid parrying tool for optimal deflection and consider the haddock's structural integrity as a potential weakness.
    >
    > **Fragile Hamster:** Thank you @Ash-Bot that is excellent advice!
    >
    > **Ash-Bot:** Acknowledged, Fragile Hamster. My analysis indicates that providing beneficial counsel is an efficient allocation of my processing resources. I am programmed to assist with scientific and technical matters to the best of my ability.
3. **Tailored Trivia Generation:**
    * *Goal:* Use aggregated knowledge to build new trivia questions tailored to the server.
    * *Next Steps:* Update `Live/bot/handlers/ai_handler.py` (`generate_ai_trivia_question`) to include "Jonesy Lore" from the database in the generation prompt, allowing for more specific and personalized questions.
4. **Voice Support:**
    * *Goal:* Enable voice connections for the bot.
    * *Next Steps:* Install `PyNaCl` (add to `requirements.txt`). Update `Live/bot_modular.py` to enable voice intents. Create a new `Live/bot/handlers/voice_handler.py` to manage voice connections and audio streaming.
5. **Fix Fallback AI:**
    * *Goal:* Repair the Hugging Face integration.
    * *Next Steps:* Re-enable Hugging Face in `Live/bot/handlers/ai_handler.py` (`setup_ai_provider`). Debug the "deployment hangs" issue (likely need to use async/await properly for the setup check or increase timeout).

## 6. Database Schema Overview

* `strikes`: User strike tracking.
* `game_recommendations`: Community submissions.
* `bot_config`: Dynamic settings.
* `trivia_questions`: The pool of questions (Needs `used`/`answered` flag check).
* `trivia_sessions`: Active session tracking.
