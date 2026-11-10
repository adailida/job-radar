# job-radar

A personal job-search radar that runs in your terminal. It pulls job postings from job APIs, keeps the ones that match your searches, and writes a report each run:

- **New openings** that match your searches and that you haven't seen before
- **Market trends** for those searches over time: volume, seniority mix, salary range, remote share
- **What employers ask for**: skills, tools, certifications and years of experience, ranked by how often they appear
- **Experience to gain**: frequent requirements your CV doesn't cover yet, with suggestions

Each person runs their own copy. Everything about you (CV, searches, settings) stays in a local folder that is never committed.

## Status

Design is complete; building Phase 1 (the first real run). The whole run already works end to end, on made-up data (`uv run job-radar run --demo`) and on real Fast Forward jobs (`uv run job-radar run`). See the docs below.

## How it works

Each run fetches postings, merges duplicates across sources, drops ones you've already seen, and filters them against your searches. A cheap LLM pass classifies each job (seniority, job type, cause area), a fuller pass extracts requirements from the ones that match, and the report is rendered as Markdown.

- **Sources**: [JobsPipe](https://jobspipe.dev) (an aggregator covering LinkedIn, Indeed, Greenhouse, Lever, Ashby, Workday and more; paid per job, with cost checks before every fetch) and the [Fast Forward](https://jobs.ffwd.org) job board for tech nonprofits (free). Only sources whose terms allow scripted access; no scraping
- **LLM**: runs through your Claude subscription with the Claude Code CLI (`claude -p`), not per-token API billing
- **Searches**: one or more named searches combined with OR, US states and other regions as ISO codes, cause areas, and a choice per criterion of keeping or dropping postings that lack the field (for example, no salary listed)

## Requirements (planned)

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://claude.com/claude-code), logged in
- A JobsPipe API key, if you use JobsPipe

## Usage

Works now:

    job-radar run --demo   # a run on made-up postings: no network, no LLM, no CV needed
    job-radar run          # real Fast Forward jobs, ranked by Claude against your CV and preferences
    job-radar runs         # list earlier runs, newest first
    job-radar delete <id>  # delete a run after asking (Enter means no); --all for every run

A real run needs, in `local/` (never committed):

- `profile.yaml`: what you're searching for: roles, excluded titles, work mode, places, minimum salary, seniority and domains (cause areas, as the settings name them). Start from [examples/profile.example.yaml](examples/profile.example.yaml)
- `cv.pdf` (or `cv.md`, `cv.txt`), and your ideal job in your own words in `preferences.md`
- optionally `settings.yaml`, with only the settings you change. The app reads [job_radar/default_settings.yaml](job_radar/default_settings.yaml) first, every setting with its default, and merges yours over it

and Claude Code logged in.

JobsPipe (paid, off by default) adds LinkedIn, Indeed and employers' own ATS. Put `JOBSPIPE_API_KEY=...` in `.env` (never committed) and set `sources.jobspipe.enabled: true` in `settings.yaml`; Before fetching, a run estimates what JobsPipe will cost (for free) and checks it against the per-run max, the monthly budget and the credits left; over a limit, it asks whether to go ahead, skip JobsPipe this run, or stop. The plan (`free` or `seeker`) sets the limits unless `max_jobs_per_run` and `monthly_budget` say otherwise.

The report also has a market trends section: postings per day, work mode, salary and seniority by month (`trend_period` in `settings.yaml`: week, month or quarter), compared with the last complete period.

It then compares what employers ask for with your CV, in "Experience to gain": each requirement covered, partly or missing, with a reason, and how to gain the five most asked gaps (`report.gap_suggestions`). Claude judges each requirement once per CV, kept in `output/cache/gaps.jsonl`, so later runs ask only about new requirements; a changed CV is judged again.

A run shows only jobs no earlier run found (set `new_only: false` in `settings.yaml` to see them all again). Deleting a run makes its jobs new again.

If your Claude usage limit runs out mid-run, the run asks whether to finish with what's done and carry the rest over to the next run, or stop and resume after the reset.

If a run fails, run the same command again: it offers to resume after the last step that finished.

Each run says which dates it fetches: the last 14 days on a first run, since the last run after that. On a first run, or after a long break, it asks before going ahead.

Each run writes `output/runs/<run-id>/report.md`, with `dropped.md` next to it. Add `--demo` to `runs` or `delete` for demo runs.

## Docs

- [Requirements](docs/requirements.md): what it does, acceptance criteria, non-goals
- [Design](docs/design.md): architecture, data model, decisions and alternatives
- [Architecture](docs/architecture.md): diagrams of the components and of one run, with where state lives
- [Tasks](docs/tasks.md): build steps
- [Data sources](docs/research/sources.md): source research and why these two

## License

MIT
