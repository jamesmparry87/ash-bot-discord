---
name: bot_code_reviewer
description: >-
  Review uncommitted or modified bot code against the project's ways of working.
  Run this whenever you are about to finalize a feature, or if the user explicitly asks for a code review.
---

# Discord Bot Code Reviewer

This skill automates the review of uncommitted or modified bot code to ensure it adheres to the "Baby Steps" philosophy and testing requirements defined in `AGENTS.md`.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Ensure that you are operating within the repository root where `git` is available.
- *Action*: Run `git status` to verify the workspace is a valid git repository and see if there are any uncommitted changes.

### 2. Dry-Run Analysis
Before running full automated test suites, do a quick pass to see what files have been modified.
- *Action*: Run `python .agents/skills/bot_code_reviewer/scripts/review_code.py --dry-run`
- *Validation*: Review the list of modified files.
- *Reporting*: Present the list of modified files to the user and warn them if legacy files (e.g. `ash_bot_fallback.py`) have been touched.

### 3. Execution (Full Review & Test)
Run the script for real to enforce testing rules and execute `pytest`.
- *Action*: Run `python .agents/skills/bot_code_reviewer/scripts/review_code.py`
- *Validation*: The script will check if tests were updated alongside logic changes, and will run the full `pytest` suite.

### 4. Verification & Follow-up
- If the script outputs warnings about "Code Sprawl" (too many modules modified without tests), strongly advise the user to commit or test current changes before expanding the scope further.
- Ensure original docstrings and comments are perfectly preserved—don't strip comments for the sake of "cleaning up".
- If `pytest` fails, provide the user with the stack trace and propose a fix.
