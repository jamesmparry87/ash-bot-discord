---
name: ai_parameter_auditor
description: >-
  Use this skill to audit the Python codebase for deprecated Gemini API configuration parameters
  (like temperature, top_k, top_p, thinking_budget) and legacy models (like gemini-1.5, gemini-2.0, gemini-2.5).
  Run this skill periodically or whenever an API deprecation notice is received.
---

# AI Parameter Auditor

This skill provides an automated mechanism to scan the `Live/bot/` codebase for the usage of deprecated Gemini API generation parameters and outdated AI models. It helps maintain the repository against API changes.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Dry-Run Analysis
Before attempting to remove anything, use the script to scan the codebase and print out any potential violations.
- *Action*: Run `python .agents/skills/ai_parameter_auditor/scripts/audit_ai_params.py --dry-run`
- *Validation*: Review the output to see how many files contain legacy models or deprecated parameters.

### 2. Execution & Refactoring
If issues are found, use Antigravity's `multi_replace_file_content` tool to safely strip the deprecated parameters from the configurations or update the legacy model strings to current ones (e.g. `gemini-3.8-flash`).
- *Action*: Run `python .agents/skills/ai_parameter_auditor/scripts/audit_ai_params.py` to confirm the final state.
- *Reporting*: Report the findings and fixes to the user.
