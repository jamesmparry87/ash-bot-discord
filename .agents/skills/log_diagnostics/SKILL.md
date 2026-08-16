---
name: log_diagnostics
description: Diagnose bot crashes or connection issues from discord logs or standard output.
---
# Log Diagnostics & DB Health Checker

When the user asks to diagnose an issue, crash, or inspect logs:

1. **Fetch Logs:**
   - Check the standard output from recent terminal crash dumps or fetch the latest `discord.log` entries from `Live/`.

2. **Railway Postgres Analysis:**
   - Specifically search for `Connection refused` or `server closed the connection unexpectedly`.
   - If found, explain that the Railway connection pool likely dropped due to idle timeout or concurrency limits, and suggest using local mocks or restarting the local development server.

3. **Trace Route Extraction:**
   - Follow stack traces specifically leading back to `bot/handlers/` or `bot/integrations/`.
   - Formulate a precise patch rather than a broad refactor. Do not suggest rewriting the database core to fix a single handler crash.
