---
name: stream_data_inspector
description: Pull raw JSON data from Twitch/YouTube APIs to debug missing games or mismatched titles.
---
# VOD & Stream Data Inspector

When asked to inspect or debug data synchronization for a specific game:

1. **Pull Raw Data:**
   - Use a scratch script to query the relevant YouTube/Twitch endpoint using the keys in `.env` to fetch the raw JSON payload for the specific game or channel.

2. **Run Through Internal Parser:**
   - Pass the raw JSON string through `bot.integrations.twitch.cleanup_game_name` or the equivalent YouTube parsing logic.
   - Observe if emojis, special characters, or alternate localized names are breaking the regex or strict string matching.

3. **Output Diagnostic Table:**
   - Present a clear Markdown table to the user comparing:
     - `Raw API Title`
     - `Parsed Canonical Name`
     - `Existing Database Canonical Name`
   - Clearly state why the match failed and propose adding a specific mapping to the aliases dictionary to resolve it.
