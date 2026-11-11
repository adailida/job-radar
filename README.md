# job-radar

A personal job-search radar that runs in your terminal. Each run fetches new job postings, keeps the ones that match your searches, has Claude rank them against your CV, and writes a report: the best matches, market trends, what employers ask for, and the experience you could gain.

## Before you start

- **A Claude Pro or Max subscription: required.** job-radar sends jobs to Claude through Claude Code (`claude -p`), using your subscription's usage: no API key and no per-token bill, but runs count toward your plan's usage limits. Rough sizes: a run covering 7 days takes about 25 to 30 haiku prompts; a first run covering 14 days, about 40 to 50. If a limit hits mid-run, the run asks whether to finish with what's done and carry the rest over to the next run.
- **Claude Code, installed and logged in.** Install [Claude Code](https://claude.com/claude-code), run `claude` once and log in; `claude auth status` should say you're logged in. Every run checks this before it fetches anything.
- **git and a terminal**, on macOS or Linux. Python and the dependencies come from the setup script.
- **Optional: a [JobsPipe](https://jobspipe.dev) account**, for jobs from LinkedIn, Indeed and employers' own ATS. Free plan: 1,000 credits, once; Seeker: $19.60 a month for 10,000. One credit per job. Off by default; every run estimates the cost before spending anything, and asks when it's over a limit.
- **[Fast Forward](https://jobs.ffwd.org)** (tech nonprofits) is free and needs no key: every run uses it.

## Get started

1. **Get the code and set it up:**

        git clone https://github.com/adailida/job-radar.git && cd job-radar
        ./scripts/setup.sh

   The script installs [uv](https://docs.astral.sh/uv/) if it's missing, then Python and the dependencies (`uv sync`). It copies `config_local_example/` to `config_local/` only if you don't have a `config_local/` yet (it never overwrites one), and checks the Claude Code login. Run it again any time.

2. **Put yourself in `config_local/`.** It starts as a copy of a made-up person; it is gitignored and never committed. Edit:
   - `cv.md` or `cv.pdf`: your CV. Replace `cv.md`, or add `cv.pdf` (with a text layer, not a scan), which is read first
   - `preferences.md`: your ideal job in your own words: what you want to do, where, for whom, what matters to you. Claude reads it with your CV when it ranks jobs
   - `profile.yaml`: your searches: roles, excluded titles, work mode, places, minimum salary, seniority and cause areas. The comments explain each key
   - `settings.yaml`: only the settings you change; [config/settings.yaml](config/settings.yaml) lists every setting with its default
   - `.env`: only for JobsPipe: your `JOBSPIPE_API_KEY`

3. **Run it:**

        uv run job-radar run --demo   # try it: made-up postings, no network, no Claude
        uv run job-radar run          # for real: your searches, ranked by Claude

   The demo runs as the made-up person in [config_local_example/](config_local_example/), so it works before you edit anything. A real run's report lands in `output/runs/<time>/report.md` (demo runs: `output/demo/<time>/`), and the terminal gives the path. `uv run job-radar runs` lists earlier runs; `uv run job-radar delete <id>` deletes one, after asking.

## Commands

    uv run job-radar run --demo   # made-up postings, as the person in config_local_example/
    uv run job-radar run          # real jobs, ranked by Claude against your CV and preferences
    uv run job-radar runs         # list earlier runs, newest first
    uv run job-radar delete <id>  # delete a run after asking (Enter means no); --all for every run

Add `--demo` to `runs` or `delete` for demo runs. Add `--quiet` to `run` to hide the progress described below.

## What a run does

It agrees the dates first: the last `lookback_days` on a first run (or after a long break, when it asks before going ahead), and since the last run after that. Each source keeps its own dates: one that failed, was skipped or came back empty in the last run catches up from where it was last covered, without redoing the others. Then it fetches postings from Fast Forward and, when it's on, JobsPipe; merges the same job found in both; drops jobs an earlier run already found; and filters the rest against your searches. Claude labels each job left (seniority, job type, cause area), finds what the matching ones ask for, and ranks them against your CV and preferences. Only sources whose terms allow scripted access are used; nothing is scraped.

- If your Claude usage limit runs out mid-run, the run asks whether to finish with what's done and carry the rest over to the next run, or stop and resume after the reset
- If a run fails, run the same command again: it offers to resume after the last step that finished
- Problems that don't stop a run (a source down, credits running low, jobs Claude couldn't read) are listed under Alerts in the report and in the terminal. A run stops only when it can't start (invalid settings or profile, unreadable CV, missing key, `claude` not logged in, another run going) or no source returned data, with one message saying what to fix
- Deleting a run makes its jobs new again

A run shows what it is doing: a banner (config folder, searches, each source with its dates, limits, model, steps), then a numbered line per step with its count and time, such as `[ 2/13] convert         done: 470 jobs (0.1s)`. Slow steps (fetch, describe, the Claude steps) show live counts; on a terminal that line updates in place, and otherwise it is one line now and then. `--quiet`, or `verbose: false` in `config_local/settings.yaml`, turns it off.

## What the report holds

Each run writes `output/runs/<time>/report.md`, with `dropped.md` next to it (what the filter dropped, by reason). The sections, always in this order:

- **Alerts**: problems from this run, if any
- **Recommended jobs**: the best fits, with a score and why
- **New openings**: every new matching job, grouped by job type (or cause area, or both), with salary, place, date and link
- **Market trends**: postings per day, work mode, salary and seniority per period, against the last complete one
- **What employers ask for**: skills, tools, certifications and years, by how often they appear
- **Experience to gain**: what's asked that your CV doesn't cover yet, with how to gain the most asked. Each requirement is compared with your CV once (kept in `output/cache/gaps.jsonl`); a changed CV is compared again
- **About this run**: how many jobs each step kept

The header gives the dates covered (each source's own when they differ, as when one is catching up), how many postings each source gave and what a paid one cost.

## Settings worth knowing

Set these in `config_local/settings.yaml`; [config/settings.yaml](config/settings.yaml) has every setting with its default.

- `lookback_days` (14 by default; 7 in the copied file): how far back a first run, or one after a long break, reaches. For a small first run, try 1
- `llm.ask_above_jobs` (60): a run with more jobs for Claude asks you first; nothing is cut. Over it, the run asks whether to send them all, only the first 60 (the rest carry over to the next run, so none are lost), or stop
- `recommend.top_n` (10) and `recommend.min_score` (40): how many jobs are recommended, and the lowest score that counts
- JobsPipe, off by default. Put your key in `config_local/.env` and start with a low limit to ask above (the copied `settings.yaml` has this block commented out):

        sources:
          jobspipe:
            enabled: true
            ask_above_credits: 25

  Before fetching, a run estimates what JobsPipe will cost (the estimate is free) and checks it against `ask_above_credits`, the monthly budget and the credits left. Over a limit, it asks whether to go ahead, skip JobsPipe this run, or stop. If the fetch reaches what you agreed with jobs still to fetch (as when JobsPipe couldn't count a slow search), it asks whether to keep going for as many again, never past the credits left. Answering no leaves JobsPipe out of this run, as a fetch is all or nothing (the credits spent aren't lost: jobs paid for are free again this month). Compare what a run spent (in the report's header) with the estimate before you widen the limits, searches or lookback
- `verbose` (true): show the banner and a line per step; `run --quiet` turns it off for one run
- `new_only` (true): set it to false to see every matching job again, not only new ones
- `trend_period` (month) and `report.group_by` (job_type): how market trends and new openings are grouped

## Status

The MVP is done (Nov 10): every step of a run works on made-up data, on real Fast Forward jobs, and with JobsPipe on. [acceptance.md](docs/acceptance.md) maps each acceptance criterion to the tests that prove it: 26 of 28 pass, one is decided otherwise by the owner, and one gap is left (market trends broken down by sector and domain). Keywords in descriptions and terminal prompts for user input are deferred until after the MVP.

## Docs

- [Requirements](docs/requirements.md): what it does, acceptance criteria, non-goals
- [Acceptance](docs/acceptance.md): each acceptance criterion with the tests that prove it, and its status: the proof the MVP does what it promises
- [Design](docs/design.md): architecture, data model, decisions and alternatives
- [Architecture](docs/architecture.md): diagrams of the components and of one run, with where state lives
- [Tasks](docs/tasks.md): the build steps, and what comes after the MVP
- [Data sources](docs/research/sources.md): source research and why these two

## License

MIT
