---
name: pylance_resolver
description: Automatically run pyright to find and fix Pylance/Type errors in recently modified code.
---
# Pylance Error Resolver

When the user asks to "resolve pylance errors", requests a check of recent edits, or pastes errors with red squiggly lines from VS Code (e.g., `Could not find name`, `Cannot find module`):

1. **Scan the Project or Analyze User Paste:**
   - Review any Pylance errors pasted by the user directly from their VS Code Problems tab.
   - If no errors were provided, run `pyright` or `pipenv run pyright` in the `C:\Users\james\Git\discord\Live` root to scan for errors.
   - Parse the output for missing imports, `reportArgumentType`, `reportUndefinedVariable`, `Could not find name`, or `Cannot find module`.

2. **Automated Fixes - Name / Module Errors:**
   - **`Could not find name 'X'`**: 
     - Ensure the variable/function/module is imported at the top of the file (e.g., `import random` or `import asyncio`).
     - If the name refers to an internal function or variable (e.g., a scheduled task or handler) that was recently deleted or renamed during a refactor, search the file and remove or update the stale references.
   - **`Cannot find module 'X'`**:
     - Check if absolute imports (e.g., `from bot.handlers.ai_tools import ...` inside a file that is *already* in `bot.handlers`) are causing Pylance to fail because it thinks the project root is elsewhere.
     - Fix this by converting the absolute internal import to a relative import (e.g., `from .ai_tools import ...`).

3. **Automated Fixes - Type Errors:**
   - For unresolved dynamic third-party imports (e.g. `import isodate`, `import aiohttp` missing from global scope), confidently apply `# type: ignore` to suppress the pyright error without breaking the code.
   - For dictionary-based type errors, inject explicit `Dict[str, Any]` typing instead of letting Python infer generic `dict`.
   - Never remove imports that appear "unused" if they are part of a `discord.ext.commands` setup or similar dynamic loading structure.

4. **Validation:**
   - If you can run `pyright` locally, re-run it after edits to confirm zero errors remaining.
   - Otherwise, ask the user to verify if the red squiggly lines have disappeared in their IDE.
