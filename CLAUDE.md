# job-radar

Job search and job-market trends, pulled from job APIs. Built spec-first with Claude Code.

## Status
Spec phase, no code yet. Spec docs are written together with the owner, section by section, before any code.

## Docs
- docs/requirements.md: what it does, acceptance criteria, non-goals
- docs/design.md: architecture, data model, decisions and alternatives
- docs/tasks.md: small ordered steps, each checkable
- docs/research/sources.md: data source research

## Decided so far
- MVP sources: JobsPipe API (aggregator: LinkedIn, Indeed, Greenhouse, Lever, Ashby, Workday and others) and the Fast Forward job board through its Getro search API
- Run cadence configurable, freshness not critical
- MVP: LLM calls use the Claude subscription (claude -p, runs locally), not per-token API billing; may switch to per-token API later. So only filtered postings go to the LLM, batched, small model
- Proposed, not agreed: one adapter per source into a common posting format; filters, LLM extraction and the report work only on that format
- Python 3.12+, uv, pytest, ruff
- Public repo: personal config (config.yaml) and run output (output/) are never committed

## Working rules
- Propose before acting. No spec content or code without walking through it with the owner first
- No commit or push without the owner's OK
