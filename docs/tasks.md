# Tasks

Build order for the MVP in [design.md](design.md), following the classes in [architecture.md](architecture.md). First a thin slice: one real run from Fast Forward to a report, one step per PR. Then each part grown until it meets its design section, then an acceptance pass.

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

Goal: `job-radar run` fetches Fast Forward, recommends the top N jobs against the CV and preferences, and writes a report. Each PR takes the run one step further; until a step is built, the run ends with `RunFailed` at that step.

- [x] **1. Project setup**
  - Package layout, dependencies (pydantic, httpx, pyyaml, pypdf; dev: pytest-socket), `job-radar` entry point, sockets blocked in tests
  - Tests: the package imports; a test that opens a socket fails
  - Acceptance: Runs: tests run offline

- [x] **2. Skeleton**
  - Every class in architecture.md with its signatures and docstrings; methods raise `NotImplementedError` marked `TODO(task N)`
  - Models: the current ones plus `RawPage`, `Recommendation`, `Report`, `StepCount`, `CandidateProfile`
  - Tests: models round-trip to JSON; models are frozen; each concrete class satisfies its interface

- [ ] **3. Pipeline and checkpoints**
  - `Pipeline.run`: steps in order, resume after the last finished step, errors wrapped in `RunFailed`, discard on success; `FileCheckpoints`: one JSON Lines file per step, `manifest.json`, `funnel`; `RunSucceeded` and `RunFailed` messages and exit codes
  - Tests, with fake steps on a temp folder: a fresh run succeeds; a failing step keeps all files; a rerun resumes after the last finished step; funnel counts per step

- [ ] **4. Command to app**
  - `Cli`, `JobRadarApp`, `AppFactory`, `Settings` with defaults in code, `Clock`
  - Tests: `job-radar run` end to end with fake steps; exit codes 0 (success), 1 (failed run), 2 (setup error)

- [ ] **5. Fast Forward**
  - Find the Getro search API endpoint; check whether it filters by date
  - Record fixtures with a neutral query, scrubbed, reviewed by the owner
  - `GetroSource` with paging, 1s delay and retries; `GetroParser`; `FetchStep` and `ConvertStep`
  - Tests: `parse` on fixtures; paging with `MockTransport`; live check (opt-in)
  - Also done when: a real `job-radar run` saves Fast Forward postings in its run folder

- [ ] **6. Dedupe and filter**
  - `DedupeStep` with `JobKey` (normalized company, title, location); `FilterStep` on roles, any criterion left empty passes
  - Tests: two postings of one job become one `Job`; a role match is kept, others dropped; an empty criterion keeps everything
  - Acceptance: Job search: a run keeps only postings that match the search criteria

- [ ] **7. Recommend**
  - `ProfileLoader` (CV PDF, preferences Markdown); `ClaudeCli` (verify the `claude -p` flags); `LlmRanker` with batches, JSON checks, one retry; `RecommendTopJobsStep`
  - Tests, with a fake `Llm`: batching; a bad answer retried, then the step fails; top N kept; missing CV is a setup error
  - Acceptance: Runs: only filtered postings go to the LLM, in batches

- [ ] **8. Report**
  - `ReportStep`: the funnel and the top N with score, title, company, location, work mode, salary, link and reason; `FileReportWriter`
  - Tests: golden-file report; `RunSucceeded` shows the report location
  - Acceptance: Runs: each run writes one report and saves its run data

- [ ] **9. First real run, limited**
  - Fast Forward only, about 20 jobs to the LLM, a short window; check the report and the run folder end to end
  - Also done when: the owner has read the report

## Phase 2: Components to ready

One line each for now; each task gets its detail, against the class names in architecture.md, when it starts.

- [ ] **10. Settings file:** YAML with defaults, unknown keys rejected, an example file
- [ ] **11. Full search criteria:** locations, work mode, keywords, excluded titles, salary, `if_missing`
- [ ] **12. Terminal prompts:** ask for missing or invalid profile fields
- [ ] **13. Run history:** `job-radar runs` and `job-radar delete`; choosing to resume a failed run
- [ ] **14. Time window:** start from the last completed run, lookback cap noted in the report
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
