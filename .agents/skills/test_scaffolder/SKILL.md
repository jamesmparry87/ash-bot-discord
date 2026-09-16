---
name: test_scaffolder
description: >-
  Automatically generate and scaffold pytest tests with database mocking boilerplate.
  Run this when asked to write or scaffold a test for a new bot feature.
---

# Test Scaffolding & Mock Generator

This skill automates the creation of robust `pytest` files conforming to the strict testing rules defined in `AGENTS.md`. It guarantees that new tests are properly mocked and will never accidentally hit the live Railway Postgres database.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Determine the name of the feature you are testing (e.g. `twitch_sync`, `ai_handler`). Ensure a test file with this name doesn't already exist in `Live/tests/`.

### 2. Dry-Run Analysis
Generate the template in dry-run mode to ensure it targets the correct directory and looks structurally sound.
- *Action*: Run `python .agents/skills/test_scaffolder/scripts/scaffold_test.py <feature_name> --dry-run`
- *Validation*: Review the generated template. Ensure it imports `db_with_mock_connection` and uses `@pytest.mark.asyncio`.

### 3. Execution
Run the script for real to write the file.
- *Action*: Run `python .agents/skills/test_scaffolder/scripts/scaffold_test.py <feature_name>`
- *Validation*: Confirm the file was successfully written to `Live/tests/test_<feature_name>.py`.

### 4. Verification & Follow-up
- Open the newly generated test file using the `replace_file_content` or `multi_replace_file_content` tools to adapt the generic `patch` mocks to target the specific functions the feature actually calls.
- If the feature interacts with external APIs (like Twitch or YouTube), add `aiohttp.ClientSession.get` mocks.
- Run `pytest Live/tests/test_<feature_name>.py` to verify the scaffolding passes before adding further logic.
