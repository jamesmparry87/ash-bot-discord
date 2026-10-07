---
name: discord_clip_backlog_checker
description: >-
  Use this skill to check the Discord clips channel for any unprocessed clips that are waiting in the backlog.
  This skill fetches recent messages from the Discord channel and counts how many clips have not yet received a ✅ reaction, which indicates they have been successfully processed by the batch job.
---

# Discord Clip Backlog Checker

This skill provides a quick way to audit the Discord clips channel and estimate the size of the remaining clip backlog. It is particularly useful for forecasting compute needs or estimating costs before a large batch job runs.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Verify that the bot environment is configured correctly before checking the backlog. The python script expects `DISCORD_TOKEN` to be present either in the environment or in the local `.env` file (`Live/.env`).
- *Action*: Inspect the environment or ensure the `Live/.env` file exists and contains a valid discord token.

### 2. Dry-Run Analysis
Before reporting full details, you can run a dry-run to get a quick summary.
- *Action*: Run `python .agents/skills/discord_clip_backlog_checker/scripts/check_backlog.py --dry-run`
- *Validation*: Review the output to ensure the script connected to Discord successfully and counted the unprocessed clips.

### 3. Execution & Reporting
Execute the script to see the backlog report.
- *Action*: Run `python .agents/skills/discord_clip_backlog_checker/scripts/check_backlog.py`
- *Reporting*: Report the number of unprocessed clips back to the user. You can also estimate the token usage or compute required based on the current Gemini Batch model configured in `config.py`.
