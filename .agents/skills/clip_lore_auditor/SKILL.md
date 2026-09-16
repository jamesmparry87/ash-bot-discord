---
name: clip_lore_auditor
description: >-
  Use this skill to audit and clean up poor quality clip lore data from the trivia database.
  This includes removing clips with null fields, hallucinated placeholders, or overly short unhelpful quotes.
  Run this whenever the user asks to check the quality of database quotes or clean up clip lore anomalies.
---

# Clip Lore Data Auditor

This skill provides a reliable, validated mechanism to automatically audit and sanitize the `clip_lore` table in the PostgreSQL database. 

Because the automated `scan_clips` batch job only skips clips that *already exist* in the database, the most robust way to force the bot to re-process "dud" clips (clips where the AI model failed to extract a good quote, reaction, or outcome) is to delete their corrupt rows entirely. The script provided handles this cleanup safely.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Verify that the bot environment is configured correctly before attempting an audit. The python script expects `DATABASE_URL` to be present either in the environment or in the local `.env` file (`Live/.env`).
- *Action*: Inspect the environment or ensure the `Live/.env` file exists and contains a valid database connection string.

### 2. Dry-Run Analysis (Required)
Before deleting any data, always run a dry-run analysis to see how many anomalies currently exist in the database.
- *Action*: Run `python .agents/skills/clip_lore_auditor/scripts/audit_and_clean.py --dry-run`
- *Validation*: Review the output to ensure the script connected successfully and correctly identified the count of anomalies (missing data vs. unhelpful short quotes).
- *Reporting*: If there are anomalies, report the numbers to the user and explain what kinds of anomalies were found. Proceed to step 3 unless the user explicitly requested just a report.

### 3. Execution (Deletion)
Once the dry-run is complete, execute the script for real to delete the anomalous rows.
- *Action*: Run `python .agents/skills/clip_lore_auditor/scripts/audit_and_clean.py`
- *Validation*: Ensure the output confirms that the correct number of rows were successfully deleted. 

### 4. Verification & Follow-up
- Confirm to the user that the anomalies have been successfully wiped from the database.
- Remind the user that these missing clips will automatically be picked up by the next nightly `process_backlog_batch` task and reprocessed with the current AI model.
