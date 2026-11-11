# Tasks

**Status: the MVP is complete (Nov 10).** Tasks 1 to 26 are done; [acceptance.md](acceptance.md) maps every acceptance criterion to its tests (26 of 28 passing, 1 gap, 1 decided by the owner). Deferred after the MVP by the owner: 11c (keywords) and 12 (terminal prompts), left unticked below. Work after the MVP goes in [After the MVP](#after-the-mvp) at the end, one PR each, under the same definition of done.

Build order for the MVP in [design.md](design.md), following the classes in [architecture.md](architecture.md). First the whole run works end to end on made-up data, with every step in a simple form. Then a thin slice: one real run from Fast Forward to a report, one step per PR. Then each part grown until it meets its design section, then an acceptance pass.

## Definition of done

Every task, before its box is ticked:

1. The tests listed in the task exist and pass, and the full `uv run pytest` passes with no network
2. `uv run ruff check` and `uv run ruff format --check` are clean
3. Each acceptance criterion the task covers (from [requirements.md](requirements.md)) has a test named after it
4. If the code differs from design.md, design.md and its decisions log are updated in the same commit
5. No personal data: fixtures scrubbed, nothing from `config_local/`
6. The owner reviewed the PR; it is squash-merged after the owner's OK, one commit per task on main
7. If the flow changed, the diagrams in architecture.md are updated in the same PR
8. The box below is ticked (`- [x]`) in the same commit

## How a task runs

1. Propose the approach in a few lines; wait for the owner's OK
2. Write the tests first where there is logic to pin down
3. Write the code
4. Open a PR from a task branch; address review comments with new commits; squash-merge after the OK

## Phase 1: First real run

Goal: `job-radar run` fetches Fast Forward, recommends the top N jobs against the CV and preferences, and writes a report. `job-radar run --demo` runs the same steps on made-up postings from task 3 on; each later PR swaps one simple or demo part for the real one.

- [x] **1. Project setup**
  - Package layout, dependencies (pydantic, httpx, pyyaml, pypdf; dev: pytest-socket), `job-radar` entry point, sockets blocked in tests
  - Tests: the package imports; a test that opens a socket fails
  - Acceptance: Runs: tests run offline

- [x] **2. Skeleton**
  - Every class in architecture.md with its signatures and docstrings; methods raise `NotImplementedError` marked `TODO(task N)`
  - Models: the current ones plus `RawPage`, `Recommendation`, `Report`, `StepCount`, `CandidateProfile`
  - Tests: models round-trip to JSON; models are frozen; each concrete class satisfies its interface

- [x] **3. End to end with demo data**
  - `job-radar run --demo` goes through every step on made-up postings and writes a report: no network, no LLM, nothing from `config_local/`
  - `Pipeline.run`: steps in order, errors wrapped in `RunFailed`, discard on success; `FileCheckpoints`: one JSON Lines file per step (temp file, then rename), `manifest.json`, `funnel`; `RunSucceeded` and `RunFailed` messages and exit codes
  - `Cli` with `run` and `--demo`, `JobRadarApp`, `AppFactory`, `Settings` with defaults in code, `Clock`; exit codes 0 (success), 1 (failed run), 2 (setup error)
  - Every step in a simple form: fetch and convert complete; dedupe merges exact repeats only; filter keeps every job; recommend keeps the top N; a short report
  - Demo parts, kept for trying the tool and for tests: `DemoSource`, `DemoParser`, `KeywordRanker`, a made-up profile
  - Tests: a demo run end to end; a failing step keeps its files; funnel counts per step; exit codes 0, 1 and 2
  - Acceptance: Runs: a new source is added without changes downstream (the demo board)

- [x] **4. Time window, agreed before the run**
  - Moved up from tasks 12 to 14 on Nov 5, so runs build on each other early
  - `WindowPlanner`: a first run fetches the lookback (14 days); a later run starts one day before the last completed run's last day; never further back than the lookback. Whole days only
  - `WindowChooser` says which dates and why; it asks to continue on a first run or after a long break, and goes ahead after a recent run. "n" runs nothing
  - `Prompter` (`tell`, `confirm`) and `TerminalPrompter`: `(y/n, Enter for y)`; with no input to read, the default
  - `FileRunHistory` reads the last completed run's window; `manifest.json` records the window and whether the run completed; failed runs don't count
  - `FilterStep` drops jobs posted before the window; `ReportStep` shows the window; demo runs keep their own history under `output/demo/`
  - Tests: each window case; asking only when needed; a cancelled run leaves nothing; a second run starts from the first; failed and unreadable runs skipped
  - Acceptance: Job search: a run never looks further back than the lookback cap (the report note on the gap is task 14). Runs: a failed run doesn't count toward the next run's window

- [x] **5. Fast Forward**
  - Find the Getro search API endpoint; check whether it filters by date (it doesn't, but it lists newest first, so paging stops at the window's start). Notes in [research/sources.md](research/sources.md)
  - Record fixtures with a neutral query, scrubbed, reviewed by the owner
  - `GetroSource` with paging, 1s delay and retries; `GetroParser`; both wired in `AppFactory`. Until task 7 a real run ranks by `KeywordRanker` against the demo profile
  - Tests: `parse` on fixtures; paging, retries and failures with `MockTransport`; live check (opt-in: `uv run pytest -m live`)
  - Also done when: a real `job-radar run` saves Fast Forward postings in its run folder

- [x] **6. Dedupe and filter**
  - `JobKey` on normalized company, title and location; `FilterStep` on roles, any criterion left empty passes
  - `Normalizer` shared by both: legal suffixes, abbreviations, accents; an aside in brackets is dropped only when it is about place or work mode ("(Remote, US)" goes, "(Media and Communication)" stays)
  - Checked on real Fast Forward data: 400 postings became 392 jobs, all 8 merges real duplicates (mostly one job posted through both Wellfound and Greenhouse)
  - Tests: two postings of one job become one `Job`; a role match is kept, others dropped; an empty criterion keeps everything
  - Acceptance: Job search: a run keeps only postings that match the search criteria

- Task 7 split in two on Nov 6: the describe step first, then the LLM ranker

- [x] **7a. Describe step**
  - `DescribeStep` after filter: fills in the full description of each kept job's primary posting, through a `JobDescriber` picked by the posting's source; postings that have one, and boards with no describer, pass through. Says first how many jobs and roughly how long
  - `GetroDescriber`: one request per job by id (`GET api.getro.com/api/v1/jobs/{id}?collection_id=997`), paused 1s before each; a 404 or a job no longer active gets an empty description, other errors fail the step
  - `BoardClient`: pacing and retries, moved out of `GetroSource` and shared with the describer; `HtmlText`: HTML to plain text keeping paragraphs, line breaks and lists
  - Fixtures: two recorded job responses, one without a description
  - Tests: `HtmlText` cases; the describer on fixtures, with 404, inactive, retries and failures; the step describes, passes through, keeps order and says how long; live check (opt-in)

- [x] **7b. Recommend**
  - `ProfileLoader`: `cv.pdf`, `cv.md` or `cv.txt`, and `preferences.md`, from `config_local/`; missing, empty or scanned files are setup errors
  - `ClaudeCli`: flags verified on Claude Code 2.1.319; one plain turn from an empty folder, 120s limit, optional JSON schema; the login checked with `claude auth status` before the run
  - `LlmRanker`: 20 jobs a prompt under short ids, descriptions cut to 4,000 characters, a JSON schema; a bad answer asked again once with what was wrong, then the step fails; real runs switch from `KeywordRanker` and the demo profile
  - Tests, with a fake `Llm` and a fake command runner: batching and order; the prompt's contents; each kind of bad answer retried, then the step fails; the command's flags, folder, errors and login check; each profile case; live check (opt-in)
  - Acceptance: Runs: only filtered postings go to the LLM, in batches

- [x] **8. Report**
  - `ReportStep` complete: the funnel and the top N with score, title, company, location, work mode, salary, posted date, link and reason; YAML front matter
  - `ReportContent` built by the step and formatted by `MarkdownRenderer`, which decides nothing
  - `min_score` setting (40): only jobs at or above it are recommended; with none, the report says so
  - Tests: golden-file report; salary and date wording; the step's content; minimum score; `RunSucceeded` shows the report location
  - Acceptance: Runs: each run writes one report and saves its run data

- [x] **9. First real run, limited**
  - Fast Forward only, about 20 jobs to the LLM, a short window; check the report and the run folder end to end
  - Also done when: the owner has read the report
  - Done Nov 9: default roles in code (engineer, engineering, developer, tech lead, architect) until the settings file; Nov 6 to 9, 20 jobs, 1 prompt. Found and fixed: a place that repeats the work mode ("Remote. Remote."), salaries to the cent ("$128.88k")

## Phase 2: Components to ready

One line each for now; each task gets its detail, against the class names in architecture.md, when it starts.

- [x] **10. Settings file:** YAML with defaults, unknown keys rejected, an example file
  - `config_local/settings.yaml` over the defaults (nested: `llm`, `recommend`, `sources`), and the searches from `config_local/profile.yaml` (`common` and `searches`, roles only); errors name the file and the key's path
  - an example profile, now `config_local_example/profile.yaml`; the defaults moved into a YAML file in task 16, now `config/settings.yaml`, read first on every run
  - Fetch and filter take all the searches; a job is kept if any matches. The demo has its own search in code
- [x] **11a. Search criteria:** excluded titles, work mode, locations (ISO codes, read from the place text by `PlaceCodes`), minimum salary, each with `if_missing`; `JobMatcher` names the criterion a job fails
- [x] **11b. Dropped by the filter:** a `dropped.md` next to the report, titles by the reason they were dropped, so silent misses show; the report links it
- [ ] **11c. Keywords:** "the description mentions any", checked after the describe step (deferred after the MVP, Nov 10)
- [ ] **12. Terminal prompts:** ask for missing or invalid profile fields (`Prompter` exists since task 4) (deferred after the MVP, Nov 10)
- [x] **13a. Run history:** `job-radar runs` lists runs; `job-radar delete <id>...` and `--all` delete after asking, Enter meaning no; `--demo` for demo runs
- [x] **13b. Resume:** when the newest run failed, `job-radar run` offers to resume it; `Pipeline` skips the finished steps and loads the last saved output (moved from task 4 on Nov 5: nothing can choose a failed run before this task)
- [x] **14. Time window in the report:** when the lookback cap cut a gap, the report says so and which dates it covers (the window itself is task 4)
- [x] **15a. Stronger keys:** an ATS key from Greenhouse, Lever, Ashby and Workable links, a fuzzy key on company, title and country; postings sharing any key merge, transitively
- [x] **15b. Only new jobs:** each completed run keeps the jobs its filter passed (`jobs.jsonl`); `NewJobsFilterStep` (`new_jobs_filter`) after dedupe drops jobs an earlier completed run kept (fuzzy keys within 60 days, ATS keys always); `new_only` setting
- [x] **16. JobsPipe:** `JobsPipeSource` and `JobsPipeParser`, fixtures recorded with a few credits; off by default, key from `.env` (now `config_local/.env`), a per-run cap on jobs, JobsPipe-only filters in settings
- [x] **17. Cost checks:** estimate, limits, ask before spending, monthly spend; the estimate and the monthly spend come from free JobsPipe calls; `spend.jsonl` and a report line per paid source
- [x] **18a. Classify and match:** seniority, job type, domain and sector from the LLM (50 jobs a prompt); `seniority` and `domains` criteria; job types and domains in settings
- [x] **18b. Extract:** requirements (skills, tools, certifications, years) from matched jobs, 10 a prompt, kept with the job
- [x] **19. Usage-limit carry-over:** jobs the LLM couldn't reach move to the next run: `UsageLimit` from `claude`, one `UsageLimitGuard` (finish and carry over, or stop), `pending.jsonl`, a `carried_over` step after the filter, a report line
- [x] **20. Trends:** periods, coverage, comparisons, low-sample notes; each run's searches and sources kept in its manifest, changes noted
- [x] **21. What employers ask for:** requirement shares over a rolling window
- [x] **22. Experience to gain:** CV against requirements, with reasons and suggestions
  - One LLM call with this run's requirements, the CV text and the preferences; no separate CV extraction (dropped at the owner's ask): covered, partly or missing with a reason, and how to gain each gap
  - Kept in `output/cache/gaps.jsonl` by CV hash and requirement: only new requirements cost a call; a failed call or the usage limit leaves a note, not a failed run
  - The section after "What employers ask for": gaps most asked first, the top `gap_suggestions` (5) with how to gain them, then the covered ones; `KeywordGapJudge` for `--demo`
- [x] **23. Complete report:** every section, grouping, terminal summary
  - Every section always present, in one order: Alerts ("None." until task 24), Recommended jobs, New openings, Market trends, What employers ask for, Experience to gain, About this run
  - A sources line in the header, with postings per source (counted by the convert step, `source_counts.jsonl`) and credits from the spend log; display names on links ("Fast Forward", "JobsPipe", "Demo board")
  - New openings: every matched job of the run, one line each, grouped by `report.group_by` (`job_type`, `domain` or `both`) by `OpeningGrouper`: settings order, then "Other", then "Not labelled", empty groups out, newest first
  - Terminal: "Run finished: 23 new openings, 10 recommended, 0 alerts." and the report path
- [x] **24. Complete errors and warnings:** every error and warning, at the top of the report and in the terminal
  - One failing source is a warning and the run goes on; only when every source tried fails does it stop: "No source returned data: JobsPipe failed (...), Fast Forward failed (...)". A paid source whose cost check fails is left out the same way
  - Warnings in `warnings.jsonl` in the run folder (`FileWarningLog`), each once: a source failed, returned nothing or was skipped by you; credits below `alerts.low_credits` (100); the monthly budget reached; the LLM couldn't label, read or rank some jobs (the ranker now splits a bad batch like the others); jobs carried over at the usage limit; requirements not compared with the CV; no new jobs matched; an unreadable run folder or kept jobs file. The report's Alerts lists them; the terminal ends with a line per alert. Outside a run, `TerminalWarnings` tells them once
  - Errors with the fix: settings and profile errors name the file, the key and where every key is listed; unreadable CV, missing API key, `claude` missing or logged out; "Another run is in progress (pid N)" (exit 2)
  - One run at a time: `output/run.lock` with the process id, a dead process's lock removed, released however the run ends
  - Unexpected errors: one line, the traceback in `error.log` in the run folder (a step) or the output folder (outside any step); Ctrl+C prints one line
  - Tests: failing fake sources (one, all); each warning recorded and shown in Alerts and the terminal; the lock (taken, released on success and failure, stale removed, live blocks); `error.log` and one line; setup error messages; unreadable runs and kept jobs

## Phase 3: MVP ready

- [x] **25. Acceptance pass**
  - A checklist mapping every acceptance criterion in requirements.md to its passing test; fill any gaps
  - [acceptance.md](acceptance.md): 28 MVP criteria, 26 passing, 1 gap, 1 decided by the owner; tests added named after the criteria they prove. Found and fixed: a JobsPipe fetch that reached its cap kept the jobs it had; now it fails as a whole, so a fetch is never partial
  - Gap left: trends broken down by sector, domain and job type (design.md section 10, "Breakdowns")
  - Decided by the owner: nothing is asked when a run fails; the next run offers to resume it
  - Deferred after the MVP by the owner (Nov 10), moved to "After the MVP" in requirements.md: keywords in descriptions (task 11c) and terminal prompts for missing or invalid user input (task 12)

- [x] **26. Real runs, limited first, and docs**
  - Step 1: Fast Forward with the full settings, a low LLM job limit and a 1-day lookback
  - Step 2: add JobsPipe with very tight limits: per-run max about 25 credits, one narrow search, 1-day lookback. Check that credits spent (before and after) match the estimate, then the report and run data
  - Step 3: widen step by step (limits, searches, lookback), checking spend against the estimate each time, before switching to the full settings
  - Examples complete (now in `config_local_example/`); README usage moved from "planned" to real
  - Built: llm.max_jobs_per_run (60; now `llm.ask_above_jobs`), README First run, an example CV (now `config_local_example/cv.md`)
  - Done Nov 9 to 10, narrowed by the owner to short windows (no widening: the owner runs the full thing after his code changes):
    - Nov 9: Fast Forward 1 and 14 days; JobsPipe Nov 8 to 9 (18 credits, matched the estimate within the cap; 10 recommended, top 86)
    - Nov 10: every step on, Nov 8 to 10: the cost check estimated 46 JobsPipe credits, over the 25 cap, and the owner skipped JobsPipe; Fast Forward only, 3 haiku prompts, one alert. Found and fixed: "Myanmar (Burma)" wasn't read as a country, so an on-site job in Yangon passed the `seattle` search as "no place given"
    - Not seen yet: a real usage-limit answer from `claude` (the pattern stays to confirm)

## After the MVP

Changes since the MVP, one PR each, newest last.

- [x] **PR #32. Regroup the code and the config folders** (Nov 11): code in folders by responsibility; defaults in `config/`, personal files in `config_local/`
- [x] **PR #33. Example folder and quick start:** `config_local_example/` mirrors `config_local/` and `--demo` runs on it; `scripts/setup.sh`; the README opens with requirements and a quick start; the docs show the MVP as done
- [x] **Ask above limits:** `llm.ask_above_jobs` and `sources.jobspipe.ask_above_credits` replace `max_jobs_per_run`; reaching the JobsPipe cap with jobs left asks to keep going for another cap's worth, within the credits left, instead of failing the source; the credits agreed during the fetch are kept in `spend.jsonl` and the report
- [ ] **Trend breakdowns:** market trends by sector, domain and job type, the gap left by the acceptance pass (design.md section 10, "Breakdowns")
- [ ] **Deferred tasks:** 11c (keywords) and 12 (terminal prompts), above
