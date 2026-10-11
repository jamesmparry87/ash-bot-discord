---
name: db_clip_inspector
description: >-
  Use this skill to inspect the PostgreSQL database clip_lore table status, count stored clips,
  check batch statuses (PENDING, COMPLETED, FAILED), view recent batch jobs, and detect stuck or pending
  batches that might block automated clip processing. Run this whenever asked to check database clip status.
---

# Database Clip Lore Inspector

This skill provides a standardized tool to inspect the state of video clips stored in the PostgreSQL database (`clip_lore` table). It reports on total stored clips, completion breakdowns, and whether any pending batch jobs are currently blocking the automated nightly ingestion pipeline.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Verify that the database environment is configured correctly before attempting an inspection. The script expects `DATABASE_URL` to be present in the local `Live/.env` file.
- **Action**: Ensure `Live/.env` exists and contains a valid PostgreSQL connection string.

### 2. Execution & Reporting (Read-Only Inspection)
Run the inspector script to view the full audit report.
- **Action**: Run `python .agents/skills/db_clip_inspector/scripts/check_db_clips.py`
- **Output Validation**:
  - Check the total clip records count.
  - Review the status breakdown (`COMPLETED`, `PENDING`, etc.).
  - Check `db.trivia.has_pending_batch()` — if this is `True`, new batch submissions are blocked until the pending job resolves or is reset.
  - Review the sample of recently stored clips.

### 3. Dry-Run Analysis (If Clearing Stuck Batches)
If the inspection indicates that old batches are stuck in `PENDING` status and blocking new processing, run a dry-run before making any modifications:
- **Action**: Run `python .agents/skills/db_clip_inspector/scripts/check_db_clips.py --reset-stuck-batches --dry-run`
- **Reporting**: Report to the user the exact number of stuck records that would be cleared.

### 4. Remediation (If Approved)
If clearing stuck pending records was requested and confirmed:
- **Action**: Run `python .agents/skills/db_clip_inspector/scripts/check_db_clips.py --reset-stuck-batches`
- **Verification**: Run `python .agents/skills/db_clip_inspector/scripts/check_db_clips.py` again to confirm that `has_pending_batch()` is now `False`.
