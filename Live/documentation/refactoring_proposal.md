# Architectural Refactoring Proposal: Surgical Refactoring Sprint

This document outlines the architectural assessment and proposal for a surgical refactoring sprint targeting the **Ash Discord Bot** codebase. It ranks modules by risk, analyzes the decoupling impact on core workflows, catalogs technical debt items, and defines a tangible, step-by-step execution plan.

---

## 1. Brittleness & Risk Ranking

Below is the architectural ranking of the bot's modules, ordered from **Most Brittle / High Risk** (hotspots with high complexity and dependency coupling) to **Most Stable** (single-responsibility or data-only components).

```
[HIGH RISK]   1. Live/bot/tasks/scheduled.py           (Monolith, API/DB/Timing Bloat)
              2. Live/bot/handlers/ai_handler.py       (Monolith, Rates/Trivia Engine)
              3. Live/bot/handlers/message_handler.py  (Monolith, Regex Router, Parsing)
              4. Live/bot/database/core.py             (Incomplete Compatibility Facade)
              
[MEDIUM RISK] 5. Live/bot_modular.py                   (Entry Point, Import Fallbacks)
              6. Live/bot/commands/trivia.py           (Large Cog, delegates to Handlers)
              
[LOW RISK]    7. Live/bot/commands/* (Others)          (Isolated Discord Cogs)
              8. Live/bot/integrations/*               (Isolated API wrappers: YouTube/Twitch)
              
[STABLE]      9. Live/bot/persona/*                    (Static FAQ & Prompt mappings)
```

### Risk Rationale

*   **1. `Live/bot/tasks/scheduled.py` (Highest Risk):** Spans ~3,200 lines and is the most fragile module in the system. It mixes time-based loop triggers with raw network operations, custom title string cleaning regexes, template formatting for greetings, and database update writes. 
*   **2. `Live/bot/handlers/ai_handler.py` (High Risk):** Spans ~3,500 lines. Violates the Single Responsibility Principle (SRP) by combining core AI API calls (rate-limiting, model fallbacks) with the entire **Trivia Engine** logic (JSON templates, evaluation rules, db history checks).
*   **3. `Live/bot/handlers/message_handler.py` (High Risk):** Spans ~2,400 lines. Serves as the primary query gatekeeper, running a long dictionary iteration of hardcoded regular expressions, executing raw PostgreSQL queries, mixing presentation logic, and calling NLTK parsing stubs that are immediately discarded.
*   **4. `Live/bot/database/core.py` (High/Medium Risk):** Operates as the backward-compatibility facade for the modular database. It is incomplete; new methods added to domain modules (like `games.py`) are missing in `core.py`, creating `AttributeError` exceptions.

---

## 2. Decoupling Impact Analysis (Top 3 Monoliths)

Decoupling the top three high-risk modules from direct database queries and raw AI client details will yield the following architectural improvements:

### I. `Live/bot/tasks/scheduled.py`
*   **Decoupling Goal:** Extract YouTube content sync, Twitch VOD sync, and greeting message generation out of the timing loop.
*   **Benefit:** Separating database writes from the timing loop allows background sync runs to fail gracefully without halting the scheduler thread. This ensures reminder checks continue to execute even if YouTube APIs time out.

### II. `Live/bot/handlers/ai_handler.py`
*   **Decoupling Goal:** Extract the Trivia Question Generator and Answer Evaluator into a standalone `bot/handlers/trivia/` domain package, leaving `ai_handler.py` as a single-responsibility AI service client.
*   **Benefit:** Isolating question history verification and trivia rules prevents template schema changes from breaking basic conversation functionality. AI prompt generation can be tested via mocks without standing up a test database container.

### III. `Live/bot/handlers/message_handler.py`
*   **Decoupling Goal:** Separate query routing from database query execution and text presentation formatting.
*   **Benefit:** Moving response copy formatting (like sarcastic responses) to a presentation mapper ensures message handlers return structured outputs. Eliminates NLTK overhead that doesn't actually affect routing.

---

## 3. The Technical 'Debt' Register

| Debt ID | System Area | File / Path Reference | Description & Architectural Impact |
| :--- | :--- | :--- | :--- |
| **D-01** | Database Facade | `database/core.py` ──► `database/games.py` | **Facade Method Omission:** Modular methods like `get_games_by_series_organized` were never added to the compatibility facade, causing `AttributeError` failures in tests. |
| **D-02** | Database Imports | `bot_modular.py` ──► `database_module.py` | **Import Fallback Duplication:** The bot maintains two completely separate database managers. This fallback must be removed to avoid duplication. |
| **D-03** | Query Parsing | `handlers/message_handler.py` | **Dead NLTK Execution Overhead:** Incoming queries run through `enhance_query_parsing()` which downloads/executes NLTK, but the output is discarded. |
| **D-04** | Content Coupling | `handlers/message_handler.py` | **Hardcoded Sarcasm Copy:** Sarcastic response lists are hardcoded inline, coupling copy alterations directly with deploy cycles. |
| **D-05** | Trivia Systems | `handlers/ai_handler.py` | **Trivia Engine Monolithic Coupling:** Trivia generation and validation algorithms are fused inside `ai_handler.py`, bloating the AI client. |
| **D-06** | Scheduled Tasks | `tasks/scheduled.py` | **Task Congestion:** A single timing loops thread handles diverse domain tasks. A crash in one blocks the rest. |
| **D-07** | Test Suite | `utils/test_gemini_models.py` | **Pytest Collection Interceptor:** The script's `test_` prefix causes Pytest to attempt to run it, triggering an exit code 1 if API keys are missing. |

---

## 4. Tangible Execution Plan (Prioritized Steps)

The following steps provide a clear, one-by-one refactoring roadmap. **Phase 1** must be completed immediately to unblock testing and DB integrity.

### Phase 1: Test Suite & Database Stabilization (Priority: P0 - Immediate)
Addresses critical test failures and ensures the database facade is fully operational.

- **Step 1.1:** Edit `Live/bot/database/core.py` to add missing delegation methods (specifically map `get_games_by_series_organized` to `self.games`). *Resolves D-01.*
- **Step 1.2:** Rename `Live/bot/utils/test_gemini_models.py` to `verify_gemini_models.py` to prevent Pytest from incorrectly collecting it as a test file and crashing. *Resolves D-07.*
- **Step 1.3:** Update `Live/tests/test_trivia_response_simple.py` and `test_basic_modules.py` to use `assert` statements instead of returning booleans, fixing Pytest warnings.
- **Step 1.4:** Remove legacy fallback import logic from `Live/bot_modular.py` and safely delete `Live/bot/database_module.py`. *Resolves D-02.*

### Phase 2: AI Handler Deconstruction (Priority: P1 - High)
Isolates the AI client from the monolithic Trivia Engine.

- **Step 2.1:** Create a new modular directory: `Live/bot/handlers/trivia/`.
- **Step 2.2:** Extract trivia template loading, duplication checking, and batch generation logic from `ai_handler.py` into `Live/bot/handlers/trivia/generator.py`.
- **Step 2.3:** Extract trivia answer matching/score evaluation logic into `Live/bot/handlers/trivia/evaluator.py`.
- **Step 2.4:** Refactor `ai_handler.py` to strictly handle Gemini API rate limiting, connections, and basic conversational prompt generation. *Resolves D-05.*

### Phase 3: Scheduled Tasks Modularization (Priority: P1 - High)
Removes business logic from the central timing loop.

- **Step 3.1:** Extract VOD and YouTube sync logic from `scheduled.py` into a new file `Live/bot/tasks/sync_vods.py`.
- **Step 3.2:** Extract Monday/Friday greeting generation into `Live/bot/tasks/greetings.py`.
- **Step 3.3:** Extract background trivia preflight logic into `Live/bot/tasks/trivia_preflight.py`.
- **Step 3.4:** Refactor `scheduled.py` into a lightweight job dispatcher that purely triggers these external functions. *Resolves D-06.*

### Phase 4: Message Router & NLTK Cleanup (Priority: P2 - Medium)
Simplifies message ingestion and extracts presentation copy.

- **Step 4.1:** Delete the dead `enhance_query_parsing()` NLTK function from `Live/bot/handlers/message_handler.py` to remove unnecessary dependency overhead. *Resolves D-03.*
- **Step 4.2:** Extract hardcoded sarcastic responses (like pizza warnings) from `message_handler.py` into a new `Live/bot/content/responses.yaml` file. *Resolves D-04.*
- **Step 4.3:** Update `message_handler.py` to load and parse strings dynamically from the new content YAML.
