# Tasks

Build order for the MVP in [design.md](design.md). First a walking skeleton that runs end to end, then each component built out until it meets its design section, then an acceptance pass.

## Definition of done

Every task, before its box is ticked:

1. The tests listed in the task exist and pass, and the full `uv run pytest` passes with no network
2. `uv run ruff check` and `uv run ruff format --check` are clean
3. Each acceptance criterion the task covers (from [requirements.md](requirements.md)) has a test named after it
4. If the code differs from design.md, design.md and its decisions log are updated in the same commit
5. No personal data: fixtures scrubbed, nothing from `local/`
6. The owner reviewed the PR; it is squash-merged after the owner's OK, one commit per task on main
7. The box below is ticked (`- [x]`) in the same commit

## How a task runs

1. Propose the approach in a few lines; wait for the owner's OK
2. Write the tests first where there is logic to pin down
3. Write the code
4. Open a PR from a task branch; address review comments with new commits; squash-merge after the OK

## Phase 1: Walking skeleton

Goal: `job-radar run` goes through all 11 stages and writes a report, with the simplest version of each stage. Real Fast Forward data, no LLM yet.

- [x] **1. Project setup**
  - Package layout (design section 2), dependencies (pydantic, httpx, pyyaml, pypdf; dev: pytest-socket), `job-radar` entry point, sockets blocked in tests
  - Tests: the package imports; a test that opens a socket fails
  - Acceptance: Runs: tests run offline

- [ ] **2. Models and interfaces**
  - Pydantic models (section 3) with the fields the skeleton needs; the five `Protocol`s (section 2); `App`; `now()`
  - Tests: models round-trip to JSON; models are frozen

- [ ] **3. Fakes**
  - `FakeSource`, `FakeLLM`, `MemoryStore`, `ScriptedPrompter`, `make_posting` factory (section 6)
  - Tests: each fake satisfies its interface

- [ ] **4. Pipeline with stub stages**
  - `run()` lists all 11 stages; each stage is its own class at its simplest: dedupe by posting key, filter on roles only, Classify and Extract return empty, Match keeps all, trends count only, gaps empty
  - `JobRadarError` and `App.alerts` (section 13); Markdown renderer with every report section
  - Tests: end to end with fakes gives a report with every section; a warning raised in a stage shows at the top

- [ ] **5. Minimal FileStore and CLI**
  - Run folder with `run.json`, `jobs.jsonl`, `report.md`; status `running` to `completed`; `job-radar run` with default settings and a minimal profile (roles)
  - Tests: end to end on a temp folder; run status lifecycle
  - Acceptance: Runs: each run writes one report and saves its run data

- [ ] **6. Getro adapter**
  - Find the search API endpoint; check whether it filters by date (section 4)
  - Record fixtures with a neutral query, scrubbed, reviewed by the owner; `parse` to `Posting`; `fetch` with paging, 1s delay, retries, all-or-nothing, raw pages to `RawSink`
  - Tests: `parse` on fixtures; paging with `MockTransport`; page 2 fails, nothing returned; live check (opt-in)
  - Also done when: a real `job-radar run` writes a report listing Fast Forward jobs

## Phase 2: Components to ready

Each task brings one component up to its design section.

### Inputs

- [ ] **7. Settings**
  - Full settings model with defaults, YAML deep merge, unknown keys rejected, errors naming the path; `examples/settings.example.yaml` (section 7)
  - Tests: defaults load with no file; merge; typo rejected with its path; the example parses and matches the defaults
  - Acceptance: Problem alerts: invalid settings stop the run

- [ ] **8. Profile and CV**
  - Searches with `common`, ISO locations, `if_missing`, salary; CV from PDF, Markdown or text; scanned PDF error; `examples/profile.example.yaml`, `examples/cv.example.md` (section 7)
  - Tests: search override of `common`; invalid location code; CV text from a small PDF fixture; scanned PDF error

- [ ] **9. Terminal prompts**
  - Ask for missing or invalid profile fields, validate each answer, stop on empty, offer to save (section 7)
  - Tests: with `ScriptedPrompter`: missing field asked and saved; invalid answer asked again; empty answer stops
  - Acceptance: Problem alerts: user input still missing or invalid after the prompt stops the run

### Storage

- [ ] **10. Complete FileStore**
  - Full layout, temp-file writes, lock, stale `running` runs, history, LLM caches, CV cache, delete, schema version; `job-radar runs` and `job-radar delete` (section 5)
  - Tests: `RunStore` contract suite against `MemoryStore` and `FileStore`; only completed runs in `history()`; delete leaves no trace; stale lock removed
  - Acceptance: Runs: the next run reads earlier run data; the user can delete any run after confirmation, its postings unseen again and out of trends

- [ ] **11. Time window**
  - First run uses the lookback; later runs start at the last completed run; lookback cap with the report note; `new_only` off (section 1)
  - Tests: one per rule, with a fixed `now()`
  - Acceptance: Job search: never further back than the lookback cap, and the report says which dates it covers

### Filtering and identity

- [ ] **12. Filter**
  - Searches (AND within, OR across), locations, work mode, roles, excluded titles, keywords, salary conversion, `if_missing`, drop counts (sections 7, 4)
  - Tests: each criterion; `if_missing` keep and drop; salary in another currency treated as missing; a job matching only the second search
  - Acceptance: Job search: a run keeps only postings that match the search criteria

- [ ] **13. Dedupe and identity**
  - Posting, ATS and fuzzy keys; URL, company and title normalization; transitive grouping; key index from history; inherited ids; primary choice; 60-day window; merge counts (section 8)
  - Tests: ATS URL parsing on real examples from fixtures; transitive merge; id inherited across sources; fuzzy match outside 60 days ignored
  - Acceptance: Job search: a job found in both sources appears once; by default only postings not seen before; with the setting off, all matching postings

### LLM

- [ ] **14. Claude CLI backend and ask_json**
  - Verify `claude -p` flags; timeout, concurrency, availability check, usage-limit detection; `ask_json` with retry, then batch split; check whether remaining usage is scriptable (section 9)
  - Tests: fake command runner: valid answer, malformed JSON retried, missing ids split, usage limit detected, `claude` missing
  - Acceptance: Problem alerts: LLM not available stops the run

- [ ] **15. Classify and Match**
  - Classify prompt v1, seniority values, domains and job types from settings, cache, inferred criteria with `if_missing`, matched searches (section 9)
  - Tests: with `FakeLLM`: batching; cache hit skips the LLM; failed job has missing fields; Match by seniority and domain
  - Acceptance: Runs: only filtered postings go to the LLM, in batches

- [ ] **16. Extract**
  - Extract prompt v1 with vocabulary, name cleanup, cache, volume guard (section 9)
  - Tests: vocabulary in the prompt; cleanup; cache hit; volume guard asks above the limit
  - Acceptance: Problem alerts: LLM failed on some postings is a warning

- [ ] **17. Pending carry-over**
  - Usage-limit prompt, `pending.jsonl`, next run picks the jobs up, deleting a run drops them (section 9)
  - Tests: limit hit mid-run; next run processes the pending jobs and owns them; leftovers carried again

### Paid source

- [ ] **18. JobsPipe adapter**
  - Record fixtures (a few credits, owner review); queries from searches and source filters; `parse`, `fetch`, `credits`, `count`. Confirm whether the API reports monthly usage, and the free tier size (section 4)
  - Tests: `parse` on fixtures; query building per search; credits and count with `MockTransport`; live count check (opt-in, 1 credit)
  - Acceptance: Job search: a run fetches from JobsPipe and Fast Forward

- [ ] **19. Cost checks**
  - Plan limits, estimate, the three outcomes and the prompt, fetch cap, monthly spend from the API or the ledger, warnings (section 12)
  - Tests: within limits goes ahead; over per-run max asks; over credits left offers no "go ahead"; fetch over the cap fails the source; skip keeps other sources
  - Acceptance: all Cost criteria; Problem alerts: credit budget reached, credits running low

### Output

- [ ] **20. Trends**
  - Periods, coverage, figures, comparison table, low sample, criteria change notes, breakdowns (section 10)
  - Tests: posting counted in its posting-date period; late posting added to an earlier period; partial period per covered day; no earlier period; criteria change noted
  - Acceptance: all Market trends criteria

- [ ] **21. What employers ask for**
  - Rolling window, shares, top N per type, median years, traceability (section 10)
  - Tests: shares over the window; failed extractions out of the denominator; top N per type; requirement traced to its postings
  - Acceptance: all What employers ask for criteria

- [ ] **22. Experience to gain**
  - CV requirements cached by hash, exact match, LLM judgment with reasons and suggestions (section 10)
  - Tests: exact match covered; years partly covered; LLM judgment cached; new CV hash re-runs
  - Acceptance: Experience to gain criteria

- [ ] **23. Complete report**
  - `ReportBuilder`, front matter, grouping, every section, funnel, terminal summary (section 11)
  - Tests: golden files for a full report and an empty one; grouping order with "Other" last; job lines show every required field
  - Acceptance: Job search: each job shows title, company, location or remote, salary if posted, source, link; openings grouped per the settings, "Other" for the rest

- [ ] **24. Complete errors and warnings**
  - Preflight order, every error and warning code, failed-run prompt, exit codes (section 13)
  - Tests: one per code; nothing spent before preflight passes; failed run prompt; exit codes
  - Acceptance: Runs: a failed run asks whether to delete its data; Problem alerts: errors stop the run, warnings let it finish, both in the terminal and at the top of the report

## Phase 3: MVP ready

- [ ] **25. Acceptance pass**
  - A checklist below mapping every acceptance criterion in requirements.md to its passing test; fill any gaps

- [ ] **26. Real runs, limited first, and docs**
  - Step 1: Fast Forward only, with a low `llm.max_jobs_per_run` (about 20) and a 1-day lookback. Check the report and run data end to end
  - Step 2: add JobsPipe with very tight limits: `per_run_max` about 25, one narrow search, 1-day lookback. Check that credits spent (before and after) match the estimate, then the report and run data
  - Step 3: widen step by step (limits, searches, lookback), checking spend against the estimate each time, before switching to the full settings
  - `examples/` complete; README usage moved from "planned" to real
