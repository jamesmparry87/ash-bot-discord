---
name: db_schema_sync
description: >-
  Safely add and sync new columns or data types to the PostgreSQL database schema.
  Run this when the user asks to track a new piece of data or modify an existing table.
---

# Database Schema Synchronizer

This skill ensures that database schema modifications are safely applied across initialization logic, bulk import operations, and whitelists, in accordance with `AGENTS.md`.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Ensure you know the exact column name, SQL data type, and target table name.

### 2. Dry-Run Analysis
Run the helper script to analyze where the code needs to be modified.
- *Action*: Run `python .agents/skills/db_schema_sync/scripts/schema_sync_helper.py <column_name> <data_type> --table <table_name> --dry-run`
- *Validation*: Review the output to ensure the script has identified the correct insertion points in `core.py` and `games.py`.
- *Reporting*: Outline the targeted files and changes to the user.

### 3. Execution
Use the `multi_replace_file_content` tool to apply the changes highlighted by the script:
- Add the `ALTER TABLE` execution block inside the database initialization function in `core.py`.
- Add the new parameter to the column whitelist in `core.py`.
- Carefully trace the logic inside `bulk_import` functions in `games.py` to handle duplicate merge resolution and upsert SQL strings.

### 4. Verification & Follow-up
- Create or modify a corresponding test in `Live/tests/test_database.py` that verifies the new schema parameter can be written and read without triggering a Postgres mapping error.
- Run `pytest Live/tests/test_database.py` to confirm the mock database accepts the schema change.
