---
name: bot_code_reviewer
description: Review uncommitted or modified bot code against the project's ways of working.
---
# Discord Bot Code Reviewer

When requested to review code:

1. **Verify "Baby Steps" Philosophy:**
   - Check if changes are sprawling across too many modules without prior testing. If so, advise the user to commit or test current changes before expanding scope.

2. **Validate Testing Requirements:**
   - Ensure every new feature or major modification has a corresponding test case in `tests/` utilizing the `db_with_mock_connection` fixture. Do not accept untested logic changes.

3. **Protect Legacy Architecture:**
   - Explicitly warn the user if any modifications touch `Live/ash_bot_fallback.py` or unrelated legacy logic outside the main `Live/bot/` modules.

4. **Formatting Rules:**
   - Check that `copy-pasteable snippets` are possible without massive file diff overhead.
   - Ensure original docstrings and comments are perfectly preserved—don't strip comments for the sake of "cleaning up".
