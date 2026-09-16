---
name: stream_data_inspector
description: >-
  Pull raw JSON data from Twitch/YouTube APIs to debug missing games or mismatched titles.
  Run this whenever the user complains that a stream didn't sync correctly to the database.
---

# VOD & Stream Data Inspector

This skill automates the extraction and parsing of stream titles from Twitch and YouTube to diagnose synchronization failures, in accordance with the `AGENTS.md` standard.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Check that `.env` is loaded and contains `TWITCH_CLIENT_ID` or `YOUTUBE_API_KEY` depending on the requested platform.

### 2. Dry-Run Analysis
Validate credentials and test the script.
- *Action*: Run `python .agents/skills/stream_data_inspector/scripts/inspect_stream.py "<Stream Title>" --platform <twitch|youtube> --dry-run`
- *Validation*: Ensure the script reports "API Credentials validated."

### 3. Execution
Run the full inspection.
- *Action*: Run `python .agents/skills/stream_data_inspector/scripts/inspect_stream.py "<Stream Title>" --platform <twitch|youtube>`
- *Validation*: The script will output a diagnostic table comparing the Raw API Title to the Parsed Canonical Name.

### 4. Verification & Follow-up
- Compare the "Parsed Canonical Name" against the name stored in the PostgreSQL database.
- Clearly state to the user why the match failed (e.g. emojis breaking the regex) and propose adding a specific mapping to the aliases dictionary in `Live/bot/integrations/twitch.py` to resolve it.
