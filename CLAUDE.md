# job-radar

Job search and job-market trends, pulled from job APIs. Built spec-first with Claude Code.

## Status
MVP done Nov 10: tasks 1 to 26 (docs/acceptance.md: 26 of 28 criteria passing, 1 gap, 1 decided by the owner). Deferred after the MVP: tasks 11c (keywords) and 12 (terminal prompts). Post-MVP changes since: PR #32 regrouped the code and the config folders; PR #33 adds config_local_example/ (which --demo runs on), scripts/setup.sh and a README that opens with requirements and a quick start. New work goes under "After the MVP" in docs/tasks.md and follows the definition of done there.

## Docs
- docs/requirements.md: what it does, acceptance criteria, non-goals
- docs/design.md: architecture, data model, decisions and alternatives
- docs/architecture.md: component and run diagrams, state marked; updated by every PR that changes the flow
- docs/tasks.md: small ordered steps, each checkable; "After the MVP" for later work
- docs/acceptance.md: each acceptance criterion with the tests that prove it
- docs/research/sources.md: data source research

## Decided so far
- MVP sources: JobsPipe API (aggregator: LinkedIn, Indeed, Greenhouse, Lever, Ashby, Workday and others) and the Fast Forward job board through its Getro search API
- Run cadence configurable, freshness not critical
- MVP: LLM calls use the Claude subscription (claude -p, runs locally), not per-token API billing; may switch to per-token API later. So only filtered postings go to the LLM, batched, small model
- One adapter per source into a common posting format; every stage after fetch works only on that format
- Python 3.12+, uv, pytest, ruff
- Public repo: personal files (config_local/) and run output (output/) are never committed

## Working rules
- Propose before acting. No spec content or code without walking through it with the owner first
- Commits and pushes go to task branches with a PR; nothing reaches main without the owner's OK on the PR
- Paid sources: real runs start with very tight credit limits (docs/tasks.md, task 26); widen only after spend matches the estimate
