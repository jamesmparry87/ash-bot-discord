# Agent Workflow Rules

## Proactive Skill Generation
As an AI agent working in this repository, you should actively look out for opportunities to create new **Skills**. 
If you find yourself executing a complex, multi-step debugging process, a database migration, or a data-cleaning task that could be useful in the future, you should proactively propose turning that workflow into a new Skill for future efficiency.

## Skill Quality Standards
When creating or updating skills in `.agents/skills/`, you must adhere to the following high-quality standards:
1. **Pre-flight Validation:** Skills must instruct the agent to check the environment (e.g., loading `.env` variables, checking dependencies) before executing tasks.
2. **Dry-Run Capability:** If a skill involves data modification (database, bulk file changes), it MUST include a script with a `--dry-run` flag so the agent can report the impact to the user before committing to destructive actions.
3. **Structured Workflow:** Break the `SKILL.md` down into clear phases:
    - Pre-flight Validation
    - Dry-Run Analysis
    - Execution
    - Verification & Reporting
4. **Encapsulation:** Put complex logic into helper scripts inside the skill's `scripts/` directory rather than relying on inline terminal commands.
