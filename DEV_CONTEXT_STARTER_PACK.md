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
    * `develop`: The active workspace. All changes start here. **Connected to Rook (staging bot)**.
    * `stable`: Release candidate branch. Merged from `develop` when features are stable.
    * `main`: Stable production releases only. **Connected to Ash (production bot)**.
    * `hotfix/*`: Emergency fixes only.
    
2. **Staging Environment (Rook Bot):**
    * **Bot Name:** Rook (staging instance of Ash)
    * **Branch:** Connected to `develop` branch
    * **Purpose:** Test all changes before production deployment
    * **Server:** Same Discord server as production (JonesySpaceCat)
    * **Testing Process:**
        1. Make changes on `develop` branch
        2. Deploy to Rook for testing
        3. Verify functionality with real Discord interactions
        4. Once stable, merge to `stable` branch
        5. Finally merge `stable` to `main` for production (Ash)
    * **Why Rook?** Named after the android character from Aliens (1986) - fitting for the "less refined" staging version

3. **Testing Protocol:**
    * **CRITICAL:** You must run `pytest` before asking for a final commit/merge.
    * If a test fails, fix the code. Do not delete the test.
    * Test on Rook (staging) before deploying to Ash (production)
    
4. **Coding Style:**
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

### Strategic Development Roadmap (2025)

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

### A. Persona Module Structure (Dec 2025)

The bot's persona (Ash from *Alien* 1979) is now modularized for maintainability:

**Location:** `Live/bot/persona/`

1. **`prompts.py`**: Contains `ASH_SYSTEM_INSTRUCTION` - the core personality definition
2. **`examples.py`**: Contains `ASH_FEW_SHOT_EXAMPLES` - conversation examples that train tone/style
3. **`faqs.py`**: Contains `ASH_FAQ_RESPONSES` - pre-written responses for common questions
4. **`context_builder.py`**: Contains `build_ash_context()` - **dynamic context injection**

### B. Role Hierarchy System (Phase 1 - Dec 2025)

**CRITICAL:** The bot uses a **5-tier hierarchical system** for role detection that's future-proof and handles all edge cases.

#### Implementation Architecture

**Primary Function:** `detect_user_context()` in `Live/bot/handlers/ai_handler.py`

```python
async def detect_user_context(user_id: int, member_obj=None, bot=None) -> Dict[str, Any]:
    """
    Returns: Dict with user_name, user_roles, clearance_level, relationship_type, 
             is_pops_arcade, detection_method
    """
```

#### 5-Tier Detection Priority (Highest to Lowest):

**TIER 1: User ID Overrides** (Hardcoded - Never Changes)
- **Captain Jonesy** (`JONESY_USER_ID`): 
  - Clearance: `COMMANDING_OFFICER`
  - Relationship: `COMMANDING_OFFICER` (Prime directive: protect)
  - Detection: Works everywhere, including DMs
  
- **Sir Decent Jam** (`JAM_USER_ID`):
  - Clearance: `CREATOR`
  - Relationship: `CREATOR` (Technical deference)
  - Detection: Works everywhere, including DMs
  
- **Pops Arcade** (`POPS_ARCADE_USER_ID`):
  - Clearance: `MODERATOR`
  - Relationship: `ANTAGONISTIC` (Analytical skepticism)
  - Detection: Works everywhere, including DMs

**TIER 2: Alias Override** (Testing System)
- Activated via `!testpersona <type> [duration]` command
- Allows moderators to test different personas without changing roles
- Types: captain, creator, moderator, member, standard
- Stored in `user_alias_state` dict (expires after 1 hour of inactivity)
- Debug tool only - not for production use

**TIER 3: DM Member Fetching**
- If in DM (no `member_obj`), attempts to fetch from guild:
  1. Try `guild.get_member(user_id)` - cached, fast
  2. Fallback to `await guild.fetch_member(user_id)` - API call, slower
  3. If not found or forbidden: default to standard personnel
- **This solves the DM problem** - users maintain their roles in DMs

**TIER 4: Discord Role Detection** (Dynamic - Future-Proof)
- **Moderators**: Detected via `member.guild_permissions.manage_messages`
  - Clearance: `MODERATOR`
  - Relationship: `COLLEAGUE`
  - Works for ANY user with manage_messages permission
  - **No code changes needed when adding new mods**
  
- **Members**: Detected via role IDs in `MEMBER_ROLE_IDS`
  - Clearance: `STANDARD_MEMBER`
  - Relationship: `PERSONNEL`
  - Senior Officers, paid members, etc.

**TIER 5: Default Fallback**
- Clearance: `RESTRICTED`
- Relationship: `PERSONNEL`
- Used when no other tier matches

#### Context Builder Integration

`build_ash_context()` in `context_builder.py` now accepts both formats:

1. **New format** (structured dict from `detect_user_context()`):

   ```python
   user_context = await detect_user_context(user_id, member_obj, bot)
   dynamic_context = build_ash_context(user_context)
   ```

2. **Legacy format** (backward compatible):

   ```python
   dynamic_context = build_ash_context(user_name, user_roles, is_pops_arcade)
   ```

#### Clearance Level Descriptions

| Level | Description | Who Gets It |
|-------|-------------|-------------|
| `COMMANDING_OFFICER` | Absolute Authority - Prime Directive: Protect | Jonesy only |
| `CREATOR` | Technical Superiority Acknowledged | JAM only |
| `MODERATOR` | Authorized Personnel - Operational Access | Mods (any manage_messages user) |
| `STANDARD_MEMBER` | Crew Member - Standard Access | Paid members, Senior Officers |
| `RESTRICTED` | Standard Personnel - Restricted Access | Everyone else |

#### Relationship Type Protocols

| Type | Protocol | Behavioral Change |
|------|----------|-------------------|
| `COMMANDING_OFFICER` | PRIME DIRECTIVE: Ensure Captain's safety above all else | Protective, deferential |
| `CREATOR` | TECHNICAL DEFERENCE: Acknowledge superior systems knowledge | Respectful of technical authority |
| `ANTAGONISTIC` | ANALYTICAL SKEPTICISM: Subject questions data validity | Dismissive, sarcastic responses |
| `COLLEAGUE` | PROFESSIONAL COOPERATION: Authorized collaboration | Efficient, professional |
| `PERSONNEL` | STANDARD INTERACTION: Assistance within clearance | Helpful but formal |

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

### E. FAQ System with Role Awareness (Phase 3 - Dec 2025)

**IMPORTANT:** FAQs now adapt based on user clearance level for personalized responses.

#### Implementation Architecture

**Primary Function:** `get_role_aware_faq_response()` in `Live/bot/persona/faq_handler.py`

**Flow:**
1. Message received → Check FAQ match (`check_faq_match()`)
2. Detect user context → `detect_user_context()` for role/clearance
3. Apply role customization → `get_role_aware_faq_response()`
4. Apply Pops sarcasm layer (if applicable)
5. Send response

#### Role-Specific FAQ Customizations

**Greetings Example ("hello"):**

| User Type | Response |
|-----------|----------|
| **Captain Jonesy** | "Captain. Hello. I'm Ash. How can I help you?" |
| **JAM (Creator)** | "Sir Decent Jam. Hello. I'm Ash. How can I help you?" |
| **Pops Arcade** | "Pops Arcade. Hello. I'm Ash. How can I help you? *[Responding... reluctantly.]*" |
| **Moderators** | "Moderator. Hello. I'm Ash. How can I help you?" |
| **Standard Users** | "Hello. I'm Ash. How can I help you?" |

**Key Features:**
- Graceful fallback to standard FAQs if context detection fails
- Maintains Ash persona integrity across all role types
- Pops sarcasm applied as additional layer on top of role customization
- All FAQ responses stored in `Live/bot/persona/faqs.py`

#### Helper Functions

```python
check_faq_match(query: str) -> bool
    # Returns True if query matches any FAQ entry

get_faq_suggestions(query: str, max_suggestions: int = 3) -> list[str]
    # Returns list of similar FAQ keys for partial matches
```

### F. Date Format & Localization (Phase 2 - Dec 2025)

**CRITICAL:** All dates now use **UK format (DD-MM-YYYY)** to match the server's timezone preference.

**Location:** `Live/bot/persona/context_builder.py`

```python
# OLD (US format):
current_date = datetime.datetime.now().strftime("%Y-%m-%d")

# NEW (UK format):
current_date = datetime.datetime.now().strftime("%d-%m-%Y")
```

**Example Output:**
- Old: "System Date: 2025-12-22"
- New: "System Date: 22-12-2025"

This ensures consistency with the bot's `Europe/London` timezone settings.

### G. Google Gemini API Migration (Dec 2025)

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

## 7. Testing the Persona System (Phase 4 - Dec 2025)

### A. Testing Commands

**Primary Test Command:** `!testpersona`

**Usage:**
```
!testpersona                  - Show current detection for your user
!testpersona captain [mins]   - Test as Captain for X minutes (default 60)
!testpersona creator [mins]   - Test as Creator
!testpersona moderator [mins] - Test as Moderator  
!testpersona member [mins]    - Test as Member
!testpersona standard [mins]  - Test as Standard user
!testpersona clear            - Clear current alias
```

**Example:**
```
Moderator: !testpersona captain 5
Bot: 🎭 Test Alias Activated
     Testing as Captain for 5 minutes
     Detected As: Captain Jonesy
     Clearance Level: COMMANDING_OFFICER
     Relationship Type: COMMANDING_OFFICER
     Expires: in 5 minutes
     
     Use '!testpersona clear' to remove this alias early
```

### B. Role-Based Test Scenarios

**Test Matrix for Rook (Staging Bot):**

| Test User | User ID | Discord Roles | Expected Clearance | Expected Relationship | Expected Tone |
|-----------|---------|---------------|-------------------|----------------------|---------------|
| **Jonesy** | Hardcoded | Any | COMMANDING_OFFICER | COMMANDING_OFFICER | Protective, deferential |
| **JAM** | Hardcoded | Any | CREATOR | CREATOR | Technical deference |
| **Pops** | Hardcoded | Moderator | MODERATOR | ANTAGONISTIC | Dismissive, sarcastic |
| **New Mod** | Any | Discord Mod role | MODERATOR | COLLEAGUE | Professional cooperation |
| **Paid Member** | Any | Member role | STANDARD_MEMBER | PERSONNEL | Helpful, accessible |
| **Regular User** | Any | None | RESTRICTED | PERSONNEL | Helpful, basic |

### C. Testing Checklist

**Deploy to Rook and verify:**

#### 1. Role Detection Tests
- [ ] Test `!testpersona` with no arguments - shows current detection
- [ ] Test `!testpersona captain 5` - activates captain alias for 5 minutes
- [ ] Test `!testpersona clear` - clears active alias
- [ ] Verify each role type gets correct clearance level
- [ ] Test DM detection - roles should be maintained in DMs

#### 2. FAQ Response Tests
- [ ] Send "hello" as Captain - should get "Captain. Hello..."
- [ ] Send "hello" as JAM - should get "Sir Decent Jam. Hello..."
- [ ] Send "hello" as Pops - should get "Pops Arcade. Hello... *[Responding... reluctantly.]*"
- [ ] Send "hello" as Moderator - should get "Moderator. Hello..."
- [ ] Send "hello" as standard user - should get "Hello. I'm Ash..."

#### 3. Date Format Tests
- [ ] Check any bot response with date - should be DD-MM-YYYY format
- [ ] Verify consistency across all date displays

#### 4. Context System Tests
- [ ] Test different user types receive appropriate responses
- [ ] Verify Pops gets sarcastic modifications
- [ ] Verify Captain gets protective/deferential responses
- [ ] Verify JAM gets technical deference

#### 5. Edge Case Tests
- [ ] Test role detection in DMs (no guild context)
- [ ] Test with user who has multiple roles
- [ ] Test fallback behavior when role detection fails
- [ ] Test alias expiration (wait or manually advance time)

### D. Debug Logging

**Key logs to monitor during testing:**

```
# Role Detection
🔍 ROLE DETECTION: Method=user_id_override, Clearance=COMMANDING_OFFICER, Relationship=COMMANDING_OFFICER

# Context Building
📊 Context Built: User='Captain Jonesy', Clearance=COMMANDING_OFFICER, Relationship=COMMANDING_OFFICER, Method=user_id_override

# FAQ Processing
✅ FAQ Match: query='hello', role=COMMANDING_OFFICER, customized=True

# Alias System
🎭 Test Alias: user_id=123456, type=captain, duration=5, expires_at=2025-12-22 12:00:00
```

### E. Common Testing Issues

**Issue:** "Role detection not working in DMs"
- **Fix:** Verify `GUILD_ID` is set correctly in config
- **Fix:** Check bot has permission to view guild members

**Issue:** "FAQ responses not customized"
- **Fix:** Check `get_role_aware_faq_response()` is being called
- **Fix:** Verify fallback logic is working (check error logs)

**Issue:** "Alias not expiring"
- **Fix:** Check `cleanup_expired_aliases()` is called in message handler
- **Fix:** Verify timezone settings are correct (should be Europe/London)

**Issue:** "Pops sarcasm not applying"
- **Fix:** Verify `POPS_ARCADE_USER_ID` matches actual user ID
- **Fix:** Check `apply_pops_arcade_sarcasm()` is called after FAQ response

## 8. Database Schema Overview

* `strikes`: User strike tracking.
* `game_recommendations`: Community submissions.
* `bot_config`: Dynamic settings.
* `trivia_questions`: The pool of questions (Needs `used`/`answered` flag check).
* `trivia_sessions`: Active session tracking.
