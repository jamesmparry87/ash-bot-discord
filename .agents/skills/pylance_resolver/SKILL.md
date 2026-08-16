---
name: pylance_resolver
description: Automatically run pyright to find and fix Pylance/Type errors in recently modified code.
---
# Pylance Error Resolver

When the user asks to "resolve pylance errors" or requests a check of recent edits:

1. **Scan the Project:**
   - Run `pipenv run pyright` in the `C:\Users\james\Git\discord\Live` root.
   - Parse the output for common missing imports, `reportArgumentType`, or `reportUndefinedVariable` errors.

2. **Automated Fixes:**
   - For unresolved dynamic third-party imports (e.g. `import isodate`, `import aiohttp` missing from global scope), confidently apply `# type: ignore` to suppress the pyright error without breaking the code.
   - For dictionary-based type errors, inject explicit `Dict[str, Any]` typing instead of letting Python infer generic `dict`.
   - Never remove imports that appear "unused" if they are part of a `discord.ext.commands` setup or similar dynamic loading structure.

3. **Validation:**
   - Re-run `pipenv run pyright` after edits to confirm zero errors remaining.
