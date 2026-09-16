---
name: pylance_resolver
description: >-
  Automatically run pyright to find and fix Pylance/Type errors in recently modified code.
  Run this whenever code has been refactored or you need to ensure type safety.
---

# Pylance Error Resolver

This skill automates running the `pyright` type checker and parses the output to easily resolve module loading and type hinting errors. It strictly follows the `AGENTS.md` workflow.

## Workflow Instructions

When invoked, execute the following steps in order:

### 1. Pre-flight Validation
Verify that `pyright` is installed on the system and accessible in the environment.

### 2. Dry-Run Analysis
Run the script in dry-run mode to confirm the environment is capable of executing Pyright.
- *Action*: Run `python .agents/skills/pylance_resolver/scripts/run_pyright.py --dry-run`
- *Validation*: Verify that Pyright is found.
- *Reporting*: If not found, instruct the user to install it via `npm install -g pyright` or `pip install pyright`.

### 3. Execution
Execute the script to parse the JSON output of the type checker.
- *Action*: Run `python .agents/skills/pylance_resolver/scripts/run_pyright.py`
- *Validation*: The script will output a clean list of type errors, including the exact file name, line number, and rule broken.

### 4. Verification & Follow-up
Apply the necessary fixes using the `replace_file_content` tool:
- **`reportMissingImports` / `Cannot find module`**: Fix this by converting the absolute internal import to a relative import (e.g., `from .ai_tools import ...`).
- **Dynamic third-party imports**: Confidently apply `# type: ignore` to suppress the pyright error without breaking the code.
- Re-run the execution script to verify that the errors have disappeared.
