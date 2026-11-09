# Tasks

Build order for the MVP in [design.md](design.md), following the classes in [architecture.md](architecture.md). First the whole run works end to end on made-up data, with every step in a simple form. Then a thin slice: one real run from Fast Forward to a report, one step per PR. Then each part grown until it meets its design section, then an acceptance pass.

## Definition of done

Every task, before its box is ticked:

1. The tests listed in the task exist and pass, and the full `uv run pytest` passes with no network
2. `uv run ruff check` and `uv run ruff format --check` are clean
3. Each acceptance criterion the task covers (from [requirements.md](requirements.md)) has a test named after it
4. If the code differs from design.md, design.md and its decisions log are updated in the same commit
5. No personal data: fixtures scrubbed, nothing from `local/`
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
  - `job-radar run --demo` goes through every step on made-up postings and writes a report: no network, no LLM, nothing from `local/`
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
  - `ProfileLoader`: `cv.pdf`, `cv.md` or `cv.txt`, and `preferences.md`, from `local/`; missing, empty or scanned files are setup errors
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

- [ ] **10. Settings file:** YAML with defaults, unknown keys rejected, an example file
- [ ] **11. Full search criteria:** locations, work mode, keywords, excluded titles, salary, `if_missing`; a "Dropped by the filter" list in the report, so silent role misses ("Engineer, Data", "ML Engineer") show
- [ ] **12. Terminal prompts:** ask for missing or invalid profile fields (`Prompter` exists since task 4)
- [ ] **13. Run history:** `job-radar runs` and `job-radar delete`; choosing to resume a failed run, and `Pipeline` resuming after the last finished step (moved from task 4 on Nov 5: nothing can choose a failed run before this task)
- [ ] **14. Time window in the report:** when the lookback cap cut a gap, the report says so and which dates it covers (the window itself is task 4)
- [ ] **15. Smarter dedupe:** ATS and fuzzy keys; across runs, so only new jobs by default
- [ ] **16. JobsPipe:** `JobsPipeSource` and `JobsPipeParser`, fixtures recorded with a few credits
- [ ] **17. Cost checks:** estimate, limits, ask before spending, monthly spend
- [ ] **18. Classify and extract:** seniority, domain and requirements from the LLM, cached
- [ ] **19. Usage-limit carry-over:** jobs the LLM couldn't reach move to the next run
- [ ] **20. Trends:** periods, coverage, comparisons, low-sample notes
- [ ] **21. What employers ask for:** requirement shares over a rolling window
- [ ] **22. Experience to gain:** CV against requirements, with reasons and suggestions
- [ ] **23. Complete report:** every section, grouping, terminal summary
- [ ] **24. Complete errors and warnings:** every error and warning, at the top of the report and in the terminal

## Phase 3: MVP ready

- [ ] **25. Acceptance pass**
  - A checklist mapping every acceptance criterion in requirements.md to its passing test; fill any gaps

- [ ] **26. Real runs, limited first, and docs**
  - Step 1: Fast Forward with the full settings, a low LLM job limit and a 1-day lookback
  - Step 2: add JobsPipe with very tight limits: per-run max about 25 credits, one narrow search, 1-day lookback. Check that credits spent (before and after) match the estimate, then the report and run data
  - Step 3: widen step by step (limits, searches, lookback), checking spend against the estimate each time, before switching to the full settings
  - `examples/` complete; README usage moved from "planned" to real
