---
name: test_scaffolder
description: Automatically generate and scaffold pytest tests with database mocking boilerplate.
---
# Test Scaffolding & Mock Generator

When asked to write or scaffold a test for a new bot feature:

1. **Required Architecture:**
   - Always place new test files in `tests/` named `test_<feature_name>.py`.
   - Ensure `pytest`, `pytest.mark.asyncio`, and `unittest.mock.patch` are imported.

2. **Database Mocking (Crucial):**
   - NEVER allow tests to connect to the live Railway PostgreSQL database.
   - Always implement or import the `db_with_mock_connection` fixture.
   - Mock `cursor.fetchall()` or `get_played_game` specifically so that the test can run purely in-memory.
   - Verify that data injection tests simulate correct return dictionaries matching `bot/database/games.py` schemas.

3. **External API Mocking:**
   - If the code interacts with `aiohttp`, Twitch, or YouTube, mock the `ClientSession` and the specific network `get()` calls so tests do not rely on live internet connections or API keys.
