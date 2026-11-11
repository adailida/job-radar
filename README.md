# job-radar

A personal job-search radar that runs in your terminal. It pulls job postings from job APIs, keeps the ones that match your searches, and writes a report each run:

- **New openings** that match your searches and that you haven't seen before
- **Market trends** for those searches over time: volume, seniority mix, salary range, remote share
- **What employers ask for**: skills, tools, certifications and years of experience, ranked by how often they appear
- **Experience to gain**: frequent requirements your CV doesn't cover yet, with suggestions

Each person runs their own copy. Everything about you (CV, searches, settings) stays in `config_local/`, a folder that is never committed.

## Status

The MVP is built: every step of a run works, on made-up data (`uv run job-radar run --demo`), on real Fast Forward jobs, and with JobsPipe turned on. Next are the first real runs with tight limits, widened step by step. See the docs below.

## How it works

Each run fetches postings, merges duplicates across sources, drops ones you've already seen, and filters them against your searches. A cheap LLM pass classifies each job (seniority, job type, cause area), a fuller pass extracts requirements from the ones that match, and the report is rendered as Markdown.

- **Sources**: [JobsPipe](https://jobspipe.dev) (an aggregator covering LinkedIn, Indeed, Greenhouse, Lever, Ashby, Workday and more; paid per job, with cost checks before every fetch) and the [Fast Forward](https://jobs.ffwd.org) job board for tech nonprofits (free). Only sources whose terms allow scripted access; no scraping
- **LLM**: runs through your Claude subscription with the Claude Code CLI (`claude -p`), not per-token API billing
- **Searches**: one or more named searches combined with OR, US states and other regions as ISO codes, cause areas, and a choice per criterion of keeping or dropping postings that lack the field (for example, no salary listed)

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://claude.com/claude-code), logged in
- A JobsPipe API key, if you use JobsPipe

## Usage

### First run

1. **Install.** With Python 3.12+ and uv:

        git clone https://github.com/adailida/job-radar.git
        cd job-radar
        uv sync

2. **Create your files in `config_local/`** (gitignored, never committed). Each has a same-named example or default in `config/`:
   - `profile.yaml`: what you're searching for: roles, excluded titles, work mode, places, minimum salary, seniority and domains (cause areas, as the settings name them). Copy [config/profile.example.yaml](config/profile.example.yaml) and change it
   - your CV as `cv.pdf` (with a text layer, not a scan), `cv.md` or `cv.txt`. [config/cv.example.md](config/cv.example.md) shows a made-up one
   - `preferences.md`: your ideal job in your own words (what you want to do, where, for whom, what matters to you). Claude reads it with your CV when it ranks jobs. [config/preferences.example.md](config/preferences.example.md) shows a made-up one
   - optionally `settings.yaml`, with only the settings you change. The app reads [config/settings.yaml](config/settings.yaml) first, every setting with its default, and merges yours over it

3. **Log in to Claude Code.** Install [Claude Code](https://claude.com/claude-code) and log in; `claude auth status` should say you are. A real run checks this before it fetches anything.

4. **Try the demo:** `uv run job-radar run --demo`. It runs every step on made-up postings: no network, no LLM, and nothing from `config_local/`. Its runs go under `output/demo/`, apart from real ones.

5. **Run for real:** `uv run job-radar run`. This fetches Fast Forward (free), filters the jobs against your searches, and has Claude label, read and rank the ones left. A first run fetches the last 14 days and asks before going ahead. For a small first run, put this in `config_local/settings.yaml`:

        lookback_days: 1
        llm:
          max_jobs_per_run: 20

   `llm.max_jobs_per_run` (60 by default) is a safety cap on how many jobs one run sends to Claude. Over it, the run asks: "75 jobs would go to Claude, over the cap of 60. Send them all, only the first 60, or stop? (a/f/s, Enter for f)". The first 60 go on and the rest are carried over to the next run, so none are lost; stop ends the run before any call to Claude, and running the same command again resumes it and asks again. Read the report at the path the terminal gives.

6. **Add JobsPipe** (paid, off by default), for LinkedIn, Indeed and employers' own ATS. Put `JOBSPIPE_API_KEY=...` in `config_local/.env` (never committed) and turn it on in `config_local/settings.yaml`, with a low per-run max to start:

        sources:
          jobspipe:
            enabled: true
            max_jobs_per_run: 25

   Before fetching, a run estimates what JobsPipe will cost (the estimate is free) and checks it against the per-run max, the monthly budget and the credits left. Within them it goes ahead and says so; over a limit, it asks whether to go ahead, skip JobsPipe this run, or stop (Enter skips). The plan (`free` or `seeker`) sets the limits unless `max_jobs_per_run` and `monthly_budget` say otherwise. Check what a run spent in the report's header against the estimate before you widen the limits, searches or lookback.

### Commands

    uv run job-radar run --demo   # a run on made-up postings: no network, no LLM, no CV needed
    uv run job-radar run          # real jobs, ranked by Claude against your CV and preferences
    uv run job-radar runs         # list earlier runs, newest first
    uv run job-radar delete <id>  # delete a run after asking (Enter means no); --all for every run

Add `--demo` to `runs` or `delete` for demo runs.

### What a run does

Each report has the same sections in the same order: alerts, the recommended jobs, every new opening that matched (grouped by job type; `report.group_by` in `settings.yaml` can say `domain` or `both`), market trends, what employers ask for, experience to gain, and about this run. The header says how many postings each source gave and what a paid one cost. At the end the terminal says, for example, "Run finished: 23 new openings, 10 recommended, 0 alerts." and where the report is.

The report also has a market trends section: postings per day, work mode, salary and seniority by month (`trend_period` in `settings.yaml`: week, month or quarter), compared with the last complete period.

It then compares what employers ask for with your CV, in "Experience to gain": each requirement covered, partly or missing, with a reason, and how to gain the five most asked gaps (`report.gap_suggestions`). Claude judges each requirement once per CV, kept in `output/cache/gaps.jsonl`, so later runs ask only about new requirements; a changed CV is judged again.

A run shows only jobs no earlier run found (set `new_only: false` in `settings.yaml` to see them all again). Deleting a run makes its jobs new again.

If your Claude usage limit runs out mid-run, the run asks whether to finish with what's done and carry the rest over to the next run, or stop and resume after the reset.

If a run fails, run the same command again: it offers to resume after the last step that finished.

Problems that don't stop a run are listed under Alerts at the top of the report, and at the end in the terminal: a source that failed or returned nothing (the other sources still run), credits running low (`alerts.low_credits` in `settings.yaml`, 100 by default), the monthly budget reached, jobs the LLM couldn't label, read or rank, jobs carried over at the usage limit or the LLM cap, no new jobs matched. A run stops only when it can't do anything useful (no source returned data) or can't start (invalid settings or profile, unreadable CV, missing API key, `claude` not logged in, another run in progress), with one message saying what to fix. An unexpected error shows one line and writes the details to `error.log`. Only one run goes at a time.

Each run says which dates it fetches: the last 14 days on a first run, since the last run after that. On a first run, or after a long break, it asks before going ahead.

Each run writes `output/runs/<run-id>/report.md`, with `dropped.md` next to it.

## Docs

- [Requirements](docs/requirements.md): what it does, acceptance criteria, non-goals
- [Acceptance](docs/acceptance.md): each acceptance criterion with the tests that prove it, and its status
- [Design](docs/design.md): architecture, data model, decisions and alternatives
- [Architecture](docs/architecture.md): diagrams of the components and of one run, with where state lives
- [Tasks](docs/tasks.md): build steps
- [Data sources](docs/research/sources.md): source research and why these two

## License

MIT
