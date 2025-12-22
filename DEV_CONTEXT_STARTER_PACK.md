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

## 5B. Strategic Development Roadmap (2025)

### 🧠 Priority 1: The "Server Cortex" (Memory & Lore)

**Goal:** Create a persistent memory of "Jonesy Lore" to make Ash feel like a long-term crew member, not just a chatbot.

* **1.1 The Lore Database (PostgreSQL)**
    * **Task:** Create `lore_memory` table (`id`, `category`, `content`, `added_by`, `date`).
    * **Usage:** Store funny quotes, community "wins" (like the Haddock Parry), and notable stream moments.
* **1.2 Active Learning (`!remember`)**
    * **Task:** Command for Mods to inject lore on the fly.
    * **Example:** `!remember quote "I don't need a map, I have instincts" - Jonesy, Subnautica Stream.`
* **1.3 Context Injection**
    * **Task:** When Ash generates text (Greetings or Trivia), he queries this DB to reference past events, making the content feel specific to this server.

### 🧹 Priority 2: Data Integrity & Game Knowledge (The DB Overhaul)
**Goal:** Fix the "Played Games" database once and for all. Bad data = bad trivia = low engagement.

* **2.1 The "Cline Audit" (Diagnosis)**
    * **Task:** Write a script (`scripts/audit_games_db.py`) to dump a sample of raw rows from the `played_games` table.
    * **Objective:** Visually inspect why alternate names are trapped in moustache brackets `{}` and why IGDB data isn't sticking.
* **2.2 Schema Normalization**
    * **Task:** Move from "ugly JSON strings" to proper PostgreSQL `JSONB` columns or a separate `game_aliases` table.
    * **Fix:** Write a migration script to clean existing `{}` artifacts.
* **2.3 Aggressive IGDB Resync**
    * **Task:** Re-write the IGDB integration to be authoritative. If a game exists in our DB, force-update its metadata (Genre, Release Year, Developer) from IGDB to ensure trivia questions have valid facts to pull from.

### 📢 Priority 3: "Report to the Bridge" (Monday/Friday Greeting Overhaul)
**Goal:** Transform "Cold Stats" into "Ash's Mission Report."

* **3.1 Source Expansion (The "Clips" Pipeline)**
    * **Problem:** Currently only checks 2 sources.
    * **Solution:** Integrate a "Clips Scanner" that pulls the *titles and descriptions* of the top 5 clips from the #clips Discord channel or Twitch directly.
    * **Output:** Ash uses these titles to summarize the week's "tactical highlights."
* **3.2 "Verve" Injection (LLM Editorializing)**
    * **Problem:** Monday stats are just numbers.
    * **Solution:** Feed the raw stats (Subs, Views, Watch time) into Gemini with the prompt: *"Analyze these performance metrics as a Science Officer reporting to the Captain. Highlight anomalies. Be precise but complimentary where warranted."*
    * **Result:** Instead of "Views: 500", Ash says: *"Captain, visual engagement has increased by 15% efficiency. The crew responded well to the Subnautica operations."*

### 👾 Priority 4: Cross-Platform Operations (Twitch Integration)
**Goal:** Expand Ash's territory beyond Discord.

* **4.1 "Ash Raid" Capability (Experimental)**
    * **Task:** Investigate `TwitchIO` (Python library).
    * **Concept:** Ash connects to the Twitch chat as a bot user.
    * **Feature:** Periodic "Status Checks." Once per stream, Ash joins chat, drops a specialized greeting or lore-based comment (e.g., *"Scanners indicate high stress levels, Captain. Recommend hydration."*), and then leaves or lurks.
    * **Constraint:** Must be strictly rate-limited to avoid spamming.

### 🔊 Priority 5: The "Voice" of Ash (Long Term)
* **5.1 Voice Synthesis:** Integration with ElevenLabs/OpenAI for VC announcements.
* **5.2 Entry/Exit Protocols:** "Captain on deck" audio cues when Jonesy joins a voice channel.

## 6. Persona Architecture & Context System

### A. Persona Module Structure (New - Dec 2025)

The bot's persona (Ash from *Alien* 1979) is now modularized for maintainability:

**Location:** `Live/bot/persona/`

1. **`prompts.py`**: Contains `ASH_SYSTEM_INSTRUCTION` - the core personality definition
2. **`examples.py`**: Contains `ASH_FEW_SHOT_EXAMPLES` - conversation examples that train tone/style
3. **`faqs.py`**: Contains `ASH_FAQ_RESPONSES` - pre-written responses for common questions
4. **`context_builder.py`**: Contains `build_ash_context()` - **dynamic context injection**

### B. Dynamic Context System

The context builder (`context_builder.py`) creates user-specific context that's injected into every AI request:

```python
def build_ash_context(user_name, user_roles, is_pops_arcade=False):
    """
    Dynamically adjusts Ash's behavior based on WHO is talking to him.
    Uses case-insensitive matching for robustness.
    """
```

**Key Features:**

1. **Clearance Levels** (Case-insensitive role matching):
   - `COMMANDING OFFICER`: Captain Jonesy (Owner)
   - `CREATOR/MODERATOR`: DecentJam, Moderators, Admins
   - `STANDARD PERSONNEL`: Everyone else

2. **Relationship Protocols**:
   - `ANTAGONISTIC`: Pops Arcade (questions his analysis, sarcastic tone)
   - `CREATOR`: DecentJam (technical deference)
   - `COMMANDING OFFICER`: Captain Jonesy (protect at all costs)
   - `Neutral/Personnel`: Default for regular members

3. **User Identification** (in `ai_handler.py` → `_build_full_system_instruction()`):
   ```python
   if user_id == JONESY_USER_ID:
       user_name = "Captain Jonesy"
       user_roles = ["Captain", "Owner"]
   elif user_id == JAM_USER_ID:
       user_name = "Sir Decent Jam"
       user_roles = ["Creator", "Admin", "Moderator"]
   elif user_id == POPS_ARCADE_USER_ID:
       user_name = "Pops Arcade"
       user_roles = ["Moderator"]
   ```

### C. Configuration Constants (`Live/bot/config.py`)

**Critical User IDs:**
```python
JONESY_USER_ID = 651329927895056384
JAM_USER_ID = 337833732901961729
POPS_ARCADE_USER_ID = 371536135580549122
```

**Moderator Role IDs:**
```python
DISCORD_MOD_ROLE_ID = 1188135626185396376
TWITCH_MOD_ROLE_ID = 1280124521008857151
```

**NOTE:** Role matching is now **case-insensitive** for robustness. The system normalizes both user names and role lists before comparison.

### D. Testing the Context System

**Test Trigger:** Use `"simulate_pops"` in any message to test the Pops Arcade antagonistic persona without logging in as Pops:

```
User: "Hey Ash, simulate_pops what do you think?"
Logs: 🧪 TEST MODE: Simulating Pops Arcade persona
Response: [Dismissive, questioning tone]
```

**Debug Logs to Watch For:**
```
🔍 CONTEXT DEBUG: Name='Sir Decent Jam', Roles=['Creator', 'Admin', 'Moderator'], ID=337833732901961729, Pops=False
📊 Context Built: Clearance='CREATOR/MODERATOR (Authorized for Operational Data)', Relationship='CREATOR (Technical Deference)'
```

### E. Google Gemini API Migration (Dec 2025)

**CRITICAL:** The bot now uses `google-genai>=1.56.0` (NEW Client API), not the old `google-generativeai`:

**Old API (Deprecated):**
```python
import google.generativeai as genai
genai.configure(api_key=KEY)
model = genai.GenerativeModel('gemini-pro')
```

**New API (Current):**
```python
from google import genai
client = genai.Client(api_key=KEY)
response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
```

**Active Models:**
- Primary: `gemini-2.5-flash`
- Backup: `gemini-2.0-flash-001`

**Key Changes:**
- No more `GenerativeModel` objects - all calls go through the `Client`
- User context injection happens via `_build_full_system_instruction(user_id, user_input)`
- System instructions are prepended to the prompt (new API handles differently than old)

## 7. Database Schema Overview

* `strikes`: User strike tracking.
* `game_recommendations`: Community submissions.
* `bot_config`: Dynamic settings.
* `trivia_questions`: The pool of questions (Needs `used`/`answered` flag check).
* `trivia_sessions`: Active session tracking.
