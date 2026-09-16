---
name: log_diagnostics
description: >-
  Diagnose bot crashes or connection issues from discord logs or standard output.
  Run this when the user asks to diagnose an issue, crash, or inspect logs.
---

# Log Diagnostics & DB Health Checker

This skill automates the extraction and diagnosis of stack traces and database connection issues from the local `discord.log`, conforming to the strict workflow guidelines in `AGENTS.md`.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Ensure that the `Live/discord.log` file exists and is accessible.

### 2. Dry-Run Analysis
Run the script in dry-run mode to verify log existence and size.
- *Action*: Run `python .agents/skills/log_diagnostics/scripts/analyze_logs.py --dry-run`
- *Validation*: Verify that the script successfully detects the log file and prints its size.

### 3. Execution
Run the full log parsing script to extract recent errors.
- *Action*: Run `python .agents/skills/log_diagnostics/scripts/analyze_logs.py`
- *Validation*: The script will parse the last 1000 lines, extract the latest Python stack trace, and count instances of Railway connection drops.

### 4. Verification & Follow-up
- If Railway connection errors are found, explain to the user that the Railway connection pool likely dropped due to idle timeout or concurrency limits, and suggest using local mocks or restarting the local development server.
- If a stack trace is found, follow it specifically back to `bot/handlers/` or `bot/integrations/`. Formulate a precise patch rather than a broad refactor. Do not suggest rewriting the database core to fix a single handler crash.
