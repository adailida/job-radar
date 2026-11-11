# Design

How job-radar meets [requirements.md](requirements.md).

**Status: built.** The MVP is done (Nov 10): the code follows this design, and the decisions log (section 14) records where it changed. Changes after the MVP are logged there too, with their PR.

Redesigned on Nov 4: sections 1 to 6 and 9 follow the classes in [architecture.md](architecture.md). Sections 7, 8 and 10 to 12 still use some older names (`RunStore`, `Prompter`, `run()`, stages); each is brought in line by the task that builds it. Section 13 follows the code since task 24.

## 1. Pipeline

A run is one pass through these stages. The user starts it in the terminal.

### Inputs and outputs

Inputs

| Input | From | Notes |
|---|---|---|
| CV | PDF, Markdown or text file | Compared against what employers ask for |
| Search criteria | Profile file, or entered in the terminal | One or more searches; a job matches any of them (section 7) |
| Settings | Defaults, overridden by the user's settings file | Sources and limits, lookback, trend period, grouping, formats |
| Earlier runs | Run data from previous runs | Which postings were already seen, and the history behind the trends |

Outputs

| Output | Where | Who reads it |
|---|---|---|
| Report | One Markdown file per run under `output/` | The user, or an LLM |
| Run data | One folder per run under `output/` | Later runs, and the user when tracing a figure back to its postings |
| Terminal | During the run | The user: progress, cost estimate, prompts, alerts, and the path to the report at the end |

Side effect: credits spent on paid sources.

The report has the same sections every run (content only; formatting in section 11):

```
# job-radar report, 2026-11-03
Covers 2026-10-27 to 2026-11-03. Sources: JobsPipe, Fast Forward

## Alerts                   problems from this run, if any
## Recommended jobs         the top N against the CV and preferences, with a score and why
## New openings             matching postings not seen before, under job type, domain or both:
                            title, company, location or remote, salary, source, link,
                            searches matched
## Market trends            per period: new postings, seniority mix, salary range,
                            remote share, compared with earlier periods
## What employers ask for   top requirements by type, share of postings
## Experience to gain       frequent requirements missing from the CV; covered ones marked
## About this run           counts per stage, credits spent, LLM calls
```

Run data holds what the run used and found: criteria and sources, time window, credits spent, raw responses, postings, and what the LLM classified and extracted. Layout in section 5.

A run that stops with an error writes no report. The terminal shows why, and the user decides whether to delete its run data (section 13).

### Time window

A run fetches postings from the start of its window to today. Windows are whole days: postings usually carry only a date, so a time of day would add precision the data doesn't have. Each source has its own window (built after the MVP), from the dates it last covered in full; the run's window spans them, from the earliest source's start to today.

- First run, or a source no completed run covered in full: its window is the lookback (a setting, 2 weeks by default)
- Later runs: a source's window starts one day before the last day of the last completed run that covered it in full. That day is fetched again because that run may have been early in it, and the day before because boards can list a posting a day after its date. Repeats cost nothing on Fast Forward or on JobsPipe (repeats within a month are free), and recognising jobs already seen removes them (task 15). A failed or deleted run doesn't count
- Covered in full: the fetch step got everything the source had for its window. Not covered: it failed, it was skipped or failed at the cost check, or it came back with nothing although its count (a paid source's counted estimate) found jobs. A source that came back with nothing and no count saying otherwise is covered, with the usual warning. The fetch step records each source's coverage in the manifest
- A source the newest completed run didn't cover catches up: its window starts from where it was last covered, so its missed dates are fetched again without redoing the other sources or deleting the run. Jobs already seen are still dropped, so a catch-up never shows a job twice
- If a source was last covered before the lookback, its window is the lookback, and the report says so and which dates it leaves out (task 14)
- With "new data only" turned off, the window is always the lookback
- Before anything is fetched, the terminal says which dates the run covers and why: once when every source shares them, else a line per source ("JobsPipe: Oct 27 to Nov 5, catching up (not covered in the last run; last covered on Oct 28)."). When a source was never covered, or was last covered before the lookback, it asks to continue, since the run reaches back further than usual; otherwise it goes ahead. "n" runs nothing and creates no run folder
- A board that returns everything it has (Fast Forward) is cut to its window by the filter: jobs whose postings are all dated before their source's window are dropped, jobs with no date are kept

### Stages

```mermaid
flowchart LR
    Load --> Plan --> Fetch --> Dedupe --> Filter --> Classify --> Match --> Extract --> Aggregate --> Compare --> Report
```

The first real run has six steps: fetch, convert (Fetch above, split in two), dedupe, filter, recommend (new: the top N against the CV and preferences) and report. The other stages become steps the same way, one task each.

1. **Load**: read the settings (defaults merged with the user's file) and the user input (CV, search criteria). Prompt in the terminal for anything missing; stop with an error if it is still invalid
2. **Plan**: for each source, turn each search into that source's query and set its own time window (see above). Paid sources also get the credits left and a match count, estimate the cost, check it against the limits, and ask the user when it is over
3. **Fetch**: each source fetches in full or not at all. Its adapter turns raw records into `Posting`s. Raw responses are saved with the run data
4. **Dedupe**: merge the same job found in more than one source, then drop postings seen in earlier runs (unless the setting turns this off). Jobs left pending by the last completed run are added here (section 9)
5. **Filter**: apply the criteria on source fields (title, keywords, location, work mode, salary) to every job, whatever the source applied server-side. A job passes if it can still match some search
6. **Classify**: a cheap LLM pass on title, company and the start of the description. It returns seniority, job type, domain and sector
7. **Match**: apply the criteria on inferred fields (seniority, domain) and record which searches each job matched. Only matched jobs go on
8. **Extract**: a full LLM pass on matched jobs only. It returns requirements
9. **Aggregate**: compute trends per period from all stored runs, not only this one
10. **Compare**: match the top requirements against the CV (exact match, then one LLM call for the rest) to find experience to gain
11. **Report**: render through the format layer, with problem alerts at the top, and mark the run complete

### Principles

- **Adapter boundary**: everything after Fetch works only on `Posting` and never sees a source's raw format. A new source plugs in without changes to the stages after it
- **I/O at the edges**: network, disk, LLM and terminal sit behind small interfaces (section 2). The stages in between are plain logic, so tests run offline and the LLM backend can be swapped
- **Trends recomputed from stored data**: no running counters. Deleting a run removes its data, and the next report is correct without undo logic
- **Raw pages kept until the run succeeds**: a failed parse resumes from the saved pages without spending credits again

### Volume

| | Postings per run | Description text (~5 to 10 KB each) |
|---|---|---|
| Typical (~1,600 per 7 days from the research funnel, 2-week window, plus Fast Forward) | ~4,500 | ~25 to 45 MB |
| Worst case (a whole Seeker month of 10,000 in one run, plus ~1,500 Fast Forward) | ~11,500 | ~60 to 120 MB, up to ~250 MB in memory |

- One run fits in memory, and the credit limits cap it. Steps pass plain lists; dedupe and recommend need all their input at once anyway
- Raw pages are saved as the fetch step's output; only the convert step reads them
- History grows with every run (at 10,000 jobs a month, ~120,000 a year). Trends read slim per-job records without descriptions (~1 KB each, ~120 MB a year at the full budget). Storage keeps descriptions apart (section 5)

## 2. Code structure

The classes, how they depend on each other and how a run flows through them are drawn in [architecture.md](architecture.md). This section gives the rules behind them and the file layout.

### Shape of a run

- `Cli` asks `AppFactory` for a `JobRadarApp`, runs it, and prints the `RunResult` it gets back. It never checks which kind of result it got: each result gives its own message and exit code
- `JobRadarApp` lives for one terminal command and launches the `Pipeline` as a black box
- `Pipeline` knows only the steps and their order. It saves every step's output through `Checkpoints` and passes it to the next step in memory, skips steps an earlier attempt already saved (loading the last saved output from disk), turns any error into `RunFailed` and the final `Report` into `RunSucceeded`
- Every step implements `Step`: it takes the previous step's output as a list and gives its own. Steps never save or read run data themselves

The first real run has six steps: fetch, convert, dedupe, filter, recommend, report. The later stages in section 1 become steps the same way.

### State

No class holds changing state in memory. Every class gets its configuration and collaborators in its constructor and never changes after. A run's state is its run folder: the saved step outputs, the manifest and the report. Each class's docstring says what it holds.

### Interfaces

Every class depends on interfaces only; `AppFactory` is the only class that knows concrete classes.

| Interface | Pattern | Implementations |
|---|---|---|
| `Step` | Pipeline step | `FetchStep`, `ConvertStep`, `DedupeStep`, `FilterStep`, `DescribeStep`, `RecommendTopJobsStep`, `ReportStep` |
| `Checkpoints`, `RunStats` | Repository, with a read-only view | `FileCheckpoints` (a database later) |
| `RunHistory` | Repository, read-only | `FileRunHistory` |
| `Prompter` | | `TerminalPrompter` |
| `JobBoardSource`, `JobBoardParser` | Adapter | `GetroSource`, `GetroParser` (JobsPipe later); `DemoSource`, `DemoParser` |
| `JobDescriber` | Adapter, only for boards whose postings come without descriptions | `GetroDescriber` |
| `JobRanker` | Strategy | `LlmRanker`; `KeywordRanker` |
| `Llm` | | `ClaudeCli` (per-token API later) |
| `ReportWriter` | | `FileReportWriter` |

Interfaces are `typing.Protocol` classes, so implementations and test fakes don't inherit from them. The exception is `RunResult`, an abstract class that `RunSucceeded` and `RunFailed` extend. Interfaces grow with the build: each starts with the methods the first run calls.

### Everything is a class

No free functions: every behaviour belongs to a class with one responsibility, one main class per file, with its small helpers beside it. Data models are immutable Pydantic classes.

### Settings

`Settings` says which board, model and limits to use; `AppFactory` builds the classes from them. The step order stays in code, in `AppFactory`. The defaults live in `config/settings.yaml`; `config_local/settings.yaml` overrides them (section 7).

### CLI

- `job-radar run`: one run
- `job-radar run --demo`: one run on a made-up board as the made-up person in `config_local_example/` (its searches, CV and preferences), with keyword scoring in place of the LLM: no network, no LLM, nothing personal from `config_local/`. For trying the tool and for the end-to-end tests. A flag, not a setting: a demo is a one-off choice for one command. Demo runs keep their own run folders and history under `output/demo/`, so they never move a real run's window
- `job-radar runs` lists runs, newest first: status, window, and what a run recommended or the last step a failed one finished. `job-radar delete <run-id>...` deletes runs after confirmation; `--all` deletes every run. `--demo` works on demo runs

### Run progress

A run shows what it is doing, on by default: a start banner, a numbered line per step, and live counts inside the slow steps. `job-radar run --quiet`, or `verbose: false` in the settings, turns it off (`--quiet` wins); quiet output is what it was before progress existed.

- **Banner**, after the dates and the spend are agreed and before the first step: the config folder, the searches by name, each source with its own dates (and "catching up"), the limits the run asks above, the model, and the step list with its count. A demo shows the example folder and no model. Built by `RunBanner`
- **A line per step**, from the `Pipeline`: `[ 2/13] convert         done: 470 jobs (0.1s)`. A resumed run says `saved earlier` for the steps it skips; a failed step's line ends as `failed`, before the usual failure message
- **Live counts** inside slow steps, through the `Progress` object: fetch (Fast Forward per page; JobsPipe per search and day, with the jobs so far), describe (per job), and each Claude pass (per prompt, `prompt 4 of 9`; the gap judge says it is comparing the CV). The factory hands the same `Progress` to the pipeline and to the steps and sources that report; the pipeline and the others depend on the `Progress` interface only
- **In place or by line.** On a terminal (`TerminalProgress`) the current step is one line, redrawn in place, that settles to its done line. Otherwise (`LineProgress`: a pipe or a file) each update is its own line, at most one every 5 seconds per step, the first of a step always; the done line is always printed. `NoProgress` shows nothing (quiet, and tests)
- **One writer.** Everything that talks to the user goes through one `Terminal`: the prompter, the warnings (through the prompter), and the progress. Before it writes a line or asks a question it clears the live line, and it draws the line again after, so a question during a fetch (the JobsPipe keep-going question) or a usage-limit question never lands on a half-drawn line. With no live line, `Terminal` prints and reads exactly as `print` and `input` do
- Timing uses the `Clock`, so tests can step it. The terminal and line classes hold the current step's label and start; the `Terminal` holds the live line (stateful, in memory only; nothing is saved)

### Layout

Folders by responsibility, read from the command down. A module with one main class is named after that class in snake_case; a module with an interface and its implementations is named after the interface; a step's module is named after the step.

```
job_radar/
  cli.py              Cli: the entry point
  app/                job_radar_app.py (JobRadarApp), app_factory.py (AppFactory),
                      window.py (WindowPlanner, WindowChooser), resume_offer.py (ResumeOffer),
                      runs_command.py (RunsCommand), run_result.py (RunResult and its kinds),
                      cost_check.py (CostCheck)
  pipeline/           pipeline.py (Pipeline, Step)
    steps/            one module per step, named after it: fetch.py, convert.py, dedupe.py,
                      new_jobs_filter.py, filter.py, carried_over.py, describe.py, llm_cap.py,
                      classify.py, match.py, extract.py, recommend.py, report.py
  sources/            base.py (the board interfaces), board_client.py (BoardClient), getro.py,
                      jobspipe.py, demo.py
  llm/                llm.py (Llm, ClaudeCli), job_ranker.py, classifier.py, extractor.py,
                      gap_judge.py, usage_limit_guard.py (UsageLimitGuard)
  matching/           job_matcher.py, job_key.py, ats_links.py, place_codes.py, normalizer.py
  report/             report_renderer.py, report_writer.py, words.py, trends.py, asks.py,
                      gaps.py, opening_grouper.py
  storage/            checkpoints.py, run_history.py, seen_jobs.py, spend_log.py, drop_log.py,
                      pending_log.py, warning_log.py, error_log.py, source_count_log.py,
                      run_lock.py, gap_cache.py
  config/             settings.py, profile_loader.py, searches_file.py, secrets.py, yaml_file.py
  utils/              clock.py, prompter.py, html_text.py, errors.py
  models/             the data models, by area: posting.py, llm.py, search.py, run.py, spend.py,
                      report.py, and model.py (their base); import them from `job_radar.models`
```

## 3. Data model

Each type is made by one stage and never changed after:

| Type | Made by | Means |
|---|---|---|
| `Posting` | Source adapter | What one source says about one opening |
| `Job` | Dedupe | One opening, backed by 1 or more postings |
| `Classification` | Classify (LLM) | Seniority, job type, domain, sector of one job |
| `Match` | Match | Which searches a job matched |
| `Extraction` | Extract (LLM) | Requirements of one matched job |

So the LLM can re-run without a re-fetch, a parser fix doesn't touch extractions, and "a job found in both sources appears once" is a type, not a flag.

```python
class Posting:              # built by the adapter
    source: str             # "jobspipe", "getro"
    source_id: str          # id inside that source; key = "source:source_id"
    title: str
    company: str
    locations: tuple[Location, ...]
    work_mode: WorkMode     # onsite | hybrid | remote | unknown
    salary: Salary | None
    url: str                # link to the posting
    posted_at: date | None
    description: str        # plain text; the adapter strips HTML

class Location:
    text: str               # as the source wrote it
    country: str | None     # ISO 3166 code when known: "US"
    region: str | None      # ISO 3166-2 code when known: "US-NY"

class Salary:
    min: Decimal | None
    max: Decimal | None
    currency: str
    period: Period          # year | month | hour, so ranges compare like for like
    text: str | None        # original wording

class Job:                  # one opening after dedupe
    id: str                 # stable across runs: an earlier job's id when keys overlap, else the primary posting's key
    keys: tuple[str, ...]   # identity keys: posting, ATS, fuzzy (section 8)
    postings: tuple[Posting, ...]  # primary first; the report shows its fields
    first_seen: date        # date of the run that first saw it

class Classification:       # one per classified job
    job_id: str
    seniority: Seniority    # values in section 9
    job_type: str | None    # a job type from settings, "Other", or None when unclear
    domain: str | None      # a domain (cause area) from settings, "Other", or None when unclear
    sector: str | None      # free label, for the informational breakdown
    prompt_version: str

class Extraction:           # one per matched job
    job_id: str
    requirements: tuple[Requirement, ...]
    prompt_version: str

class Match:                # one per matched job
    job_id: str
    searches: tuple[str, ...]  # names of the searches it matched

class Requirement:
    type: RequirementType   # skill | tool | certification | years
    name: str               # normalized: "Python", "CISSP"
    years: int | None       # for type years: 5 in "5+ years of Python"

class Window:               # dates a run covers, both ends included; start after end is rejected
    start: date
    end: date

class SourceWindow:         # one source's dates in a run, kept in the manifest
    source: str
    window: Window
    reason: WindowReason | None  # first_run | since_last_run | catching_up | capped
    not_covered: Window | None   # days the lookback left out, before its window
    covered: bool               # set by the fetch step: fetched in full

class RunWindows:           # what the app agrees and the pipeline is built for
    window: Window          # spans every source's window
    not_covered: Window | None   # when every source shares it
    sources: tuple[SourceWindow, ...]

class RawPage:              # one page as a job board returned it, before parsing
    source: str
    page: int
    body: str               # the response text, unchanged

class CandidateProfile:     # what a good job is for the user
    cv: str                 # text taken from the CV file
    preferences: str        # the ideal job, in the user's own words

class Recommendation:       # one recommended job
    job: Job
    score: int              # 0 to 100
    reason: str             # one line

class Report:               # the finished report
    location: str           # e.g. a file path
    summary: str            # "23 new openings, 10 recommended, 0 alerts"

class StepCount:            # how many items one finished step produced
    step: str
    count: int
```

A record of each run (when it ran, its window, criteria snapshot, what each source spent) comes back with run history and cost checks (tasks 13 and 17). For the first run, the manifest in the run folder is the record (section 5).

How the requirements map onto it:

- Trend date: the primary posting's `posted_at`, or `first_seen` when missing
- Traceability: a requirement belongs to an `Extraction`, which points to a `Job` and its postings
- Criteria changes, monthly spend and source alerts: from the run record, once it comes back (tasks 13 and 17)

### Model classes

- **Pydantic** (frozen) for everything that crosses a boundary: files, LLM output, APIs. That is every model above, plus settings and user input (section 7)
- Frozen means frozen: collections are tuples, so `job.postings.append(...)` fails like `job.id = ...` does. Lists passed in are converted
- Unknown fields are rejected (`extra="forbid"`), so a typo in saved data fails to load instead of being dropped. Optional fields default to `None`
- **Pydantic inside each adapter** for that source's raw response, with only the fields used (extra fields ignored). An API change then fails with the field that broke, reported as a source warning. These models never leave the adapter
- **Frozen dataclasses** for objects that never leave memory: `RunSucceeded` and `RunFailed`

### Left for later sections

- `SearchCriteria`, `Search`, `CV`, settings: section 7
- Seniority values, requirement name normalization: section 9
- Duplicate matching and job identity across runs: section 8
- Not modelled: whether a requirement is "must have" or "nice to have". Not in the requirements

## 4. Source integration

### Interface

Each job board brings two classes: one fetches, one parses.

```python
class JobBoardSource(Protocol):     # Adapter: talks to one board's API
    name: str
    def fetch(self, criteria: SearchCriteria, window: Window) -> list[RawPage]: ...

class JobBoardParser(Protocol):     # Adapter: turns one board's records into postings
    source: str
    def parse(self, page: RawPage) -> list[Posting]: ...
```

- `FetchStep` asks each source in turn. `fetch` turns the search and window into the board's own query and pages through the API. The pages are the fetch step's output, so the pipeline saves them like any other step's
- A board that fails part way raises, and the step fails: fetches stay all-or-nothing. Once there is a second board, skipping the failed one with a warning comes with the cost checks
- `ConvertStep` sends each page to the parser for its board. `parse` is pure: tested offline on recorded fixtures, and after a parser fix a failed run resumes at convert from the saved pages, without fetching again
- Paid sources (JobsPipe) add their credit and match-count calls when cost checks are built (task 17); free sources carry no cost code

### Settings vs adapter module

| In settings | In the adapter module |
|---|---|
| Which sources are on | API calls, paging, auth |
| Per-source options: board name, plan, limits, request delay | Mapping raw fields to `Posting` (salary, work mode, location) |
| Source-only filters (JobsPipe: occupation group, ghost score, company size, no agencies) | How the common criteria become this source's query |
| Name of the API key variable (the key itself is in `config_local/.env`) | How this source reports credits |

Adding a source: a module under `sources/` with its source and parser classes, wired in `AppFactory`, and its settings.

"Declarative where possible" (requirements) means settings configure and choose each source, and the field mapping stays in code. A generic adapter that maps JSON fields from settings pays off only when several sources share a shape (per-company Greenhouse, Lever and Ashby feeds, later).

### Common criteria applied twice

Each source applies what it can server-side, to save credits. The Filter stage then applies all criteria on source fields to every job regardless. Results are consistent across sources, with no bookkeeping of what each source applied. A posting the server matched may still be dropped locally (keyword matching can differ); the report counts these drops.

### Reliability

- HTTP: one shared `httpx` client, injected into adapters. Tests use `httpx.MockTransport`, so HTTP needs no interface of its own
- Retries: timeouts, 5xx and 429 get a few retries with backoff before the source fails
- Request delay per source in settings (Getro: 1s, from its robots.txt crawl delay)
- A failed paid fetch can't refund credits already spent. JobsPipe doesn't charge for repeats within the month, so a retry next run mostly costs nothing

### Checked while building

- JobsPipe reports credits used this month: `GET /v1/account` (free) gives the plan, credits used and left; every search response gives `credits_charged` and `credits_remaining`. `POST /v1/jobs/export/estimate` counts the matches for the same filters, free. Its sandbox returns two made-up records, too few for fixtures
- Getro's search API doesn't filter by date: the whole board is fetched (~1,500 jobs, free); the seen check and window filter handle the rest

### JobsPipe (built, task 16)

- Off by default (`sources.jobspipe.enabled`); the key from `JOBSPIPE_API_KEY` in the environment or `config_local/.env`. On without a key is a setup error
- One search per user search and day of the window (built after the MVP; until then one per user search, from the window's start): roles to `job_title_or`, excluded titles to `job_title_not`, work mode to `work_arrangement_or`, countries to `job_country_code_or` and US or Canadian regions to `region_or`, a USD minimum to `min_salary_usd`, the day to both `posted_at_gte` and `posted_at_lte` (inclusive, by calendar day). A criterion whose `if_missing` keeps jobs also sends `include_unknown`, unless `match_if_missing: false`
- Order: each search in turn, its days newest first, each day paged with its own cursor. A 14-day window with 3 searches is 42 counts and 42 searches at the least, each request paused `delay_seconds` after the last: one day at a time, a phrase search answers; over 3 days or more it timed out (Nov 11, [research/sources.md](research/sources.md))
- A day the cost check counted jobs for that comes back empty (no jobs on its first page) is JobsPipe timing out without saying so: the fetch fails with `JobsPipeError` ("the search for remote-us on 3 Nov came back empty though its count found 12, so it probably timed out; ..."), so JobsPipe isn't covered and the next run fetches its dates again. A day counted 0, or not counted, may come back empty. The counts reach the fetch through the plan and the approval (`SpendPlan.counts`, `Approval.counts`, then `fetch_paid(..., counts)`), so the source stays stateless
- `filters` in settings are JobsPipe-only, sent as written (tech occupations, no agencies, ghost score, mission phrases, seniority)
- `max_jobs_per_run` (25) caps the jobs returned, and so the credits, until task 17's cost checks. Now `ask_above_credits`: a run that needs more asks first (section 12)
- Measured Nov 9 with the owner's searches and filters: about 84 jobs a day with unknowns asked for, about 18 without

## 5. Run data storage

### Layout

One folder per run, all plain text:

```
output/                        (setting; default ./output, gitignored)
  runs/
    2026-11-05T10-00-00/       named by the start time, to the second
      01-fetch.jsonl           raw pages, as the boards returned them
      02-convert.jsonl         postings
      03-dedupe.jsonl          jobs
      04-new_jobs_filter.jsonl jobs no earlier completed run found
      05-filter.jsonl          jobs that match the search
      06-carried_over.jsonl    the same jobs, plus those the last run carried over
      07-describe.jsonl        the same jobs, with full descriptions
      08-llm_cap.jsonl         the jobs that go on to the LLM: all, or the first ones up to the cap
      09-classify.jsonl        the same jobs, with labels: seniority, job type, domain, sector
      10-match.jsonl           jobs that meet every criterion of a search, labels included
      11-extract.jsonl         the same jobs, with their requirements
      12-recommend.jsonl       the top N recommendations at or above the minimum score
      13-report.jsonl          the Report: where it is, one-line summary
      manifest.json            schema version; the window and any days a long break left out; each source's window and whether it was covered in full; each finished step and its count, in order
      report.md                this run's report
      dropped.md               what the filter dropped, grouped by why
      jobs.jsonl               after success: the extract step's output (matched jobs, labels, requirements), kept so later runs know these jobs
      source_counts.jsonl      how many postings each source gave, for the report's header
      spend.jsonl              what each paid source spent: estimate, decision, credits used and left
      pending.jsonl            jobs the usage limit stopped or the LLM cap held back, carried over to the next run
```

- One JSON Lines file per step, named after the step and numbered in the order the steps ran, so the folder lists them in run order: one record per line, easy to `grep` and hand to an LLM
- After a successful run only `manifest.json`, `report.md`, `dropped.md`, `jobs.jsonl` and `source_counts.jsonl` remain, with `spend.jsonl` and `pending.jsonl` when the run has them. A failed run keeps everything, ready to resume
- The report sits in the run folder, so deleting a run deletes its report. The terminal prints its path
- Outside any run folder: the CV comparison cache, `output/cache/gaps.jsonl` (built, task 22; demo runs keep `demo-gaps.jsonl`; section 10). Later: the spend ledger if the API lacks monthly usage (section 12), and a lock for one run at a time

### What a run stores

Built so far (task 15b): a completed run keeps the jobs its filter passed as `jobs.jsonl`, and `NewJobsFilterStep` (after dedupe) drops jobs sharing any key with them: strong keys (ATS, a posting's own key) for good, fuzzy keys for 60 days. `new_only: false` lets every job through. Ids and LLM results aren't reused yet (task 18). The full design:

Once run history is built, runs also store and read what earlier runs found:

- Every job it sent to the LLM, matched or not, with its classification; matched jobs also with their extraction
- A `Match` for each job it matched that no earlier completed run matched. That run owns the job
- A job matched now, with a classification or extraction reused from an earlier run, is copied in with them. Each run folder holds everything its matched jobs need, so deleting one run never breaks another

What counts:

- Seen: jobs with a `Match` in a completed run. A job extracted but not matched stays unseen, so after a criteria change it can still show up as new
- Trends: matched jobs only, each counted once, in the run that owns it
- LLM cache: before calling the LLM, Classify and Extract reuse any stored result for the job. A reused job that still doesn't match isn't stored again. This matters most for Getro, which returns the whole board every run
- Pending jobs: the next run takes the last completed run's pending jobs (section 9)
- With "new data only" off, the report also lists seen jobs, reusing their extractions; no new `Match` is stored
- Deleting a run removes what it stored: its matched jobs become unseen, its results leave the cache, its pending jobs are dropped
- The cache is keyed by job id, which stays the same across runs and sources (section 8)

The CV cache and the spend ledger are not part of any run: deleting runs leaves them. A new CV hash starts a new cache entry.

### Progress and resume

- After each step, the pipeline saves its output and adds the step and its count to `manifest.json`. A step listed there is finished
- The manifest also records the run's window, each source's own window and, once the fetch step has run, whether it covered that source in full, and once every step has finished, that the run completed. Run history reads them: each source's next window starts from the last completed run that covered it. Version 3 added the sources; a version 2 manifest counts as covering its window for every source its config lists (every source when it lists none), as before
- A failed run keeps every file. When the newest run failed, the next `job-radar run` (or `run --demo`) asks "Resume it?" (Enter for yes): yes reruns it in its folder with its windows, skipping the finished steps and starting at the step that failed; no starts a new run and leaves the failed one, which never counts toward the next window. Only the newest run is offered
- Outputs pass between steps in memory. A resumed run starts with nothing in memory, so it loads the last saved output from disk once, then carries on in memory
- Writes go to a temp file, then rename, so a crash never leaves half a file

### Interface

```python
class Checkpoints(Protocol):        # Repository: one run's step outputs
    def has(self, step: str) -> bool: ...
    def save(self, step: str, items: Sequence[Model]) -> None: ...   # also records the count
    def load(self, step: str, kind: type[M]) -> list[M]: ...
    def complete(self) -> None: ...                                  # once the run succeeded

class RunStats(Protocol):           # read-only view for the report
    def funnel(self) -> list[StepCount]: ...

class ReportWriter(Protocol):       # where the finished report goes
    def write(self, text: str) -> str: ...   # returns its location
```

- `FileCheckpoints` implements both `Checkpoints` and `RunStats`; `FileReportWriter` writes `report.md`. `AppFactory` creates them with the run's folder, so they never start or track a run: they are born for one
- Only `Pipeline` uses `Checkpoints`. `ReportStep` gets the same object as `RunStats`, so it can read the counts but not save or delete
- `RunHistory` is read-only and starts with one method, `last_window()`, which `FileRunHistory` reads from the manifests. Listing runs (`runs()`) came with task 13a, and `last_covered(source)`, a source's window in the last completed run that covered it, with per-source coverage; deleting is `RunFolders`, a separate class, since it changes the folders, and a deleted run's coverage goes with it
- `FileCheckpoints` also implements `CoverageLog` (`record(covered)`), which the fetch step uses to mark each source covered or not in the manifest; a fetch done again on resume replaces it

### Keeping other backends possible (SQLite later)

- Nothing outside `FileCheckpoints` and `FileReportWriter` touches `output/`. Steps take and return models
- Stable string IDs are the only links: job id, and the `job_id` on `Classification`, `Match` and `Extraction`. Nothing points to data by file path or line number
- Contract tests: one suite runs against every `Checkpoints` implementation. A database backend is done when it passes; `funnel()` becomes a query
- The manifest records a schema version, so old runs can be told apart and migrated when models change
- Trends stay in Python under any backend

### Disk use

At the research funnel's rate (~83,000 postings a year): descriptions ~1 GB a year, gzipped raw pages ~200 MB a year. Pruning old raw pages can be added later as a setting.

## 6. Testing

A plain `pytest` never touches the network, `claude`, or credits. `pytest-socket` blocks sockets, so a test that tries the network fails instead of calling an API.

### Layers

| Layer | What it tests | With what |
|---|---|---|
| Steps | Each step on its own: dedupe, filter, recommend, report, and later trends and gaps | Real inputs from small factories (`make_posting(title=...)`); fakes only for the interfaces a step holds (`JobRanker`, `RunStats`, `ReportWriter`) |
| Adapters | `parse` on recorded pages; `fetch` paging, retries, all-or-nothing (page 2 fails, nothing returned) | Recorded fixtures, `httpx.MockTransport` |
| LLM | `LlmRanker` batching, JSON checks and retry (later Classify and Extract); `ClaudeCli` output parsing | A fake `Llm`; a fake command runner instead of `claude` |
| Contracts | Every `Checkpoints` implementation (`FileCheckpoints`, later a database) | One suite, run against every implementation |
| Pipeline | Steps in order, resume after the last finished step, errors become `RunFailed`, checkpoints deleted on success | Fake steps, `FileCheckpoints` on a temp folder |
| End to end | `job-radar run --demo` from `Cli` to the report; later over several runs (nothing new the second time, trends span periods) | The demo board and `KeywordRanker`, a fixed `Clock`, a temp folder |
| Report | Markdown output | Golden files, regenerated with a flag and reviewed in the diff |

- Time: `AppFactory` gets a `Clock`; tests pass one with a fixed time, so windows, periods and run folders are deterministic
- Each acceptance criterion in requirements.md has at least one test named after it. No coverage percentage target

### Recorded fixtures

The repo is public, so:

- `scripts/record_fixture.py <source>` calls the real API with a neutral query (for example "software engineer"), never the user's settings, and keeps a handful of records
- It strips auth headers and keys, and replaces emails and phone numbers in descriptions
- At least one description stays long and in HTML, to test HTML stripping
- Every fixture is reviewed by the owner before commit
- Recording JobsPipe costs a few credits, once

### Live checks

Opt-in (`@pytest.mark.live`, skipped by default), run by hand to catch API changes before a real run:

- Getro: fetch one page and check it parses (free)
- JobsPipe: one count query (1 credit)

### Later

- A GitHub Action running `ruff` and `pytest` on push

## 7. Settings and user input

### Files

```
config/                    committed: only the defaults the app reads
  settings.yaml            every setting with its default, commented: read first, every run
config_local_example/      committed: a copy-and-edit template of config_local/, for a made-up person;
                           --demo runs on it
  settings.yaml            a few common overrides, commented
  profile.yaml             the searches, with the profile keys explained
  cv.md                    a fictional person's CV
  preferences.md           the same person's ideal job
  .env                     the API key names, with no values
config_local/              gitignored as a whole: the user's overrides and personal files
  settings.yaml            only the settings the user overrides
  profile.yaml             user input: the searches
  cv.pdf                   the CV: PDF, Markdown or plain text
  preferences.md           the ideal job, in the user's own words
  .env                     API keys
```

- Defaults and overrides in two folders with the same file names: `config_local/settings.yaml` is merged over `config/settings.yaml`
- `config_local_example/` mirrors `config_local/` file for file, so a first setup is `cp -r config_local_example config_local`, then editing. `.env` is ignored everywhere but there, where it holds no key
- One gitignored folder for everything personal: the repo is public, and one rule covers any personal file added later
- Paths can be overridden with `--profile` and `--settings`
- The CV is read locally (PDF via `pypdf`); the LLM sees only text. A scanned PDF with no text layer stops the run with an error asking for a text PDF. Word files later

### Profile

Built so far: `common` and `searches` with `roles`, `exclude_titles`, `work_mode`, `locations` and `min_salary` (task 11a), and `seniority` and `domains` (task 18a), all but the first two with `if_missing`. `keywords` is deferred after the MVP (owner, Nov 10); built, it would come after the describe step (descriptions aren't there when the filter runs). Domain names must be ones the settings define. The CV keeps its fixed names in `config_local/` (no `cv:` key).

```yaml
cv: cv.pdf
common:                                   # applies to every search
  roles: [software engineer, data engineer]   # title contains any
  exclude_titles: [intern, sales]
  keywords: [python]                      # description mentions any
  min_salary: {amount: 120000, currency: USD, period: year, if_missing: keep}
  seniority: [senior, lead]               # short form: if_missing defaults to keep
  domains: {values: [climate, global-health], if_missing: drop}
searches:                                 # a job matches if it matches any search
  remote-us:  {work_mode: [remote], locations: [US]}
  nyc-office: {work_mode: [onsite, hybrid], locations: [US-NY]}
```

- A job matches a search when every field matches (AND); a field matches when any of its values does (OR); a job matches the profile when any search matches (OR)
- A field in a search replaces the same field from `common`
- Locations are ISO codes: `US` is anywhere in the US, `US-NY` is New York only. A posting that gives only the country counts as region missing for `US-NY`. Locations apply to remote jobs too ("Remote, US only")
- `if_missing: keep | drop` works on every field a posting may lack (salary, location, work mode, seniority, domain). Default `keep`
- Salary periods convert (hourly × 2,080, monthly × 12). A salary in another currency counts as missing
- Seniority and domain are inferred by the LLM (Classify), so the Match stage applies them; the rest is applied by Filter (section 1)

### Settings

Every key has a default; the file can be missing. The sample shows the full design; built so far: `output`, `lookback_days`, `new_only`, `llm` (`model`, `timeout_seconds`, `batch_size`, `max_description_chars`, `ask_above_jobs`), `recommend` (`top_n`, `min_score`), `report.group_by`, `report.requirements_per_type`, `report.gap_suggestions`, `alerts.low_credits` and `sources.getro.network`. The others come with their tasks; [config/settings.yaml](../config/settings.yaml) holds what exists.

```yaml
domains:                    # cause areas or fields: used by the domains filter and report headings
  climate: "climate change mitigation and adaptation"
  global-health: "health in low and middle income countries"
  education: "..."
  ai-safety: "..."
  fintech: "..."
job_types:                  # what the person would do
  engineering: "builds software"
  data: "..."
  product: "..."
report:
  format: markdown
  group_by: job_type        # job_type | domain | both: headings in "New openings" only
  requirements_per_type: 20 # rows per type in "What employers ask for"
  gap_suggestions: 5        # gaps shown with how to gain them in "Experience to gain"
alerts:
  low_credits: 100          # the only alert threshold; other alerts are fixed (section 13)
lookback_days: 14
new_only: true
trend_period: month
llm:
  backend: claude_cli
  model: haiku
  classify_batch: 50
  extract_batch: 10
  max_description_chars: 4000
  ask_above_jobs: 60        # above this, the run asks before Classify; nothing is cut
  concurrency: 2
  timeout_seconds: 120
store: {backend: files, path: output}
sources:
  getro: {enabled: true, network: "997", delay_seconds: 1}   # 997: Fast Forward
  jobspipe:
    enabled: true
    plan: seeker            # sets default monthly_budget and ask_above_credits
    api_key_env: JOBSPIPE_API_KEY
    filters: {occupations: [25], max_ghost_score: 40, exclude_agencies: true}
```

- Domains and job types ship with a starter list. Their descriptions guide the LLM. The profile refers to them by name; an unknown name is a validation error
- Plan limits (Free: 1,000 once; Seeker: 10,000 a month) are a table in the adapter; settings can override them

### Loading and validation

- Defaults live in `config/settings.yaml` only, read first on every run. The Pydantic model holds types and limits and no defaults, so a setting missing from that file is an error
- The user's file is deep-merged over the defaults
- Unknown keys are errors, so typos are caught. Errors name the path: `sources.jobspipe.plan: must be one of free, seeker`

### Terminal input

- If `profile.yaml` is missing or a field is invalid, the `Prompter` asks for those fields only and validates each answer
- An empty answer stops the run with an error
- At the end it offers to save the answers to `config_local/profile.yaml`

```python
class Prompter(Protocol):
    def tell(self, message: str) -> None: ...     # built in task 4
    def confirm(self, question: str) -> bool: ... # built in task 4: yes or no, yes by default
    def ask(self, question: str) -> str: ...      # task 12, deferred after the MVP: free text; "" when the user gives none
    def choose(self, question: str, options: Sequence[str], default: str | None = None) -> str: ...  # task 17
```

- `confirm` covers yes/no questions (the window, deleting a run, the failed-run prompt). It shows `(y/n, Enter for y)`, or `(y/n, Enter for n)` when no is the default: always lowercase, with the default spelled out. Any other answer asks again. Deleting defaults to no
- `choose` covers the cost-check outcomes (section 12), the usage limit and the LLM cap (section 9)
- With no input to read, as in a script, `TerminalPrompter` takes the default

## 8. Cross-source dedup and job identity

The same opening can appear in both sources (Fast Forward links to the employer's ATS, which JobsPipe often has too), twice inside JobsPipe (LinkedIn and Greenhouse), again in a later run through either source, or as a repost under a new id.

### Identity keys

Each posting gets several keys. Two postings are the same job if they share any key.

| Key | Example | Strength |
|---|---|---|
| Posting key | `getro:48213` | Exact, within one source |
| ATS key, parsed from the URL | `greenhouse:acme:4012345`, `lever:acme:<uuid>`, `ashby:acme:<uuid>` | Strong: the employer's own id for the opening |
| Fuzzy key | `acme\|senior software engineer\|US` | Weaker: normalized company, title, country |

- URLs: lowercase host; strip tracking parameters (`utm_*`, `gh_src`) and trailing slashes; known ATS URL shapes parse into an ATS key
- Company: lowercase, no punctuation, legal suffixes dropped (Inc, LLC, Ltd, GmbH)
- Title: lowercase, no punctuation, abbreviations expanded (Sr to senior, Eng to engineer), an aside in brackets removed only when it is about place or work mode ("Engineer (Remote, US)"). Other asides stay: on real data, "Specialist (Media and Communication)" and "Specialist (Media development, journalism...)" are different roles
- The fuzzy key uses country, not city: sources word cities differently ("NYC", "New York, NY")
- Built so far (task 15a): the ATS key for Greenhouse, Lever, Ashby and Workable links, and the fuzzy key on company, title and countries; a place with no country code counts by its text ("remote"). Postings sharing any key merge transitively; the job's id is its primary posting's strongest key. On real data 67 of 400 Fast Forward postings link to one of these four. Keys from earlier runs come with task 15b

### Dedupe stage

1. Compute keys for every posting
2. Group this run's postings that share a key, transitively (A and B share an ATS key, B and C a fuzzy key: one job)
3. Look each group up in a key index built from stored jobs (matched and classified jobs, completed runs only). On a hit, the job takes the earlier job's id. A seen job is then recognized whichever source found it, and the LLM cache hits
4. Pick the primary posting: longest description, then has a salary, then source order in settings. Fields the primary lacks (salary, posted date) are filled from the other postings. The posted date is the earliest, so a repost doesn't look new in trends

### Trade-offs

- Same-title openings merge: two real "Software Engineer" openings at one company in one country become one job. Small harm for a job seeker (one link instead of two, trends undercount slightly); splitting by city would miss far more real duplicates
- Repost window: fuzzy keys match jobs from earlier runs only within 60 days, so a genuinely new opening with the same title later is not seen forever. ATS keys always match: the employer's id isn't reused. 60 days is fixed in code; it can become a setting if it needs tuning

### Visibility

Each run records how many merges came from each kind of key, and `jobs.jsonl` keeps the keys, so a wrong merge can be traced. Normalization is tested on real examples from the fixtures.

### Not chosen

- Asking the LLM whether two postings match: costs calls and isn't deterministic
- Comparing descriptions: expensive, and reposts often edit the text

## 9. LLM layer

### Two passes

Built so far (task 18a): Classify, after describe (it reads the start of each description, which Fast Forward only has after describe), then a match step for `seniority` and `domains`. A job the LLM can't label keeps no labels, so `if_missing` decides. Built (task 18b): Extract, right after match, on every matched job (not only the recommended ones): 10 jobs a prompt, descriptions up to 8,000 characters, the same retry and split. Names are only trimmed here; merging variants ("Python 3", "python") is left to where requirements are counted (task 21).


```
... Filter --> Classify --> Match --> Extract --> Aggregate ...
```

| Pass | Input per job | Output | Batch | Runs on |
|---|---|---|---|---|
| Classify | Title, company, first ~1,000 characters of the description | seniority, job type, domain, sector | ~50 jobs | Every job that passed Filter |
| Extract | Full description, capped at 8,000 characters | requirements | ~10 jobs | Matched jobs only |

- Classify costs roughly a tenth of Extract per job, so full extraction runs only on jobs that reach the report
- When Classify can't tell (the domain of an unknown small org), the field is missing and the profile's `if_missing` rule applies

### Interface

```python
class Llm(Protocol):                # any language model
    def complete(self, system: str, prompt: str, schema: dict | None = None) -> str: ...

class JobRanker(Protocol):          # Strategy: scores jobs against the CV and preferences
    def score(self, jobs: Sequence[Job], profile: CandidateProfile) -> list[Recommendation]: ...
```

- `ClaudeCli` implements `Llm`; a per-token API backend later implements only `complete`
- `LlmRanker` implements `JobRanker`: it builds the prompts, sends jobs in batches, and checks the JSON answers. `RecommendTopJobsStep` keeps the best N and knows nothing about the LLM
- With a JSON schema, the model is held to that shape (`claude -p --json-schema`; the per-token API has the same). The class that asks still checks what it needs (the right ids, each once), so `Llm` stays one method. If Classify and Extract (task 18) repeat the checks, they move to a shared class then

### Claude CLI backend

- `claude -p --model haiku --output-format json --tools "" --system-prompt <ours> --no-session-persistence --strict-mcp-config --setting-sources ""`, with `--json-schema` when the caller gives one: one turn, no tools, nothing saved, no MCP servers or settings. The prompt goes on stdin. Verified on Claude Code 2.1.319
- Run from an empty temporary folder: from the repo folder the same call reads the project's CLAUDE.md (1,568 input tokens against 981)
- `--bare` can't be used: it reads only an API key, never the subscription login
- Timeout per call (120 seconds). Calls go one at a time for now; concurrency (2) comes when runs send enough jobs to need it
- `claude` missing or not logged in: a setup error, checked with `claude auth status` (free) before the window is agreed, so nothing is fetched first
- Remaining subscription usage: `claude` doesn't report it in a scriptable form (2.1.319), so no low-usage warning yet

### Batches and failures

- Each job in a batch gets a short id (`j1`, `j2`); the answer must cover exactly those ids
- Invalid JSON or missing ids (including an answer cut off by the output limit): retry once with the validation error in the prompt, then split the batch in half and retry each half. A job that still fails counts toward the "LLM failed on N jobs" warning
- A job that fails Classify has all inferred fields missing (`if_missing` applies). A job that fails Extract is reported without requirements. Neither is retried in a later run, so a broken posting can't loop forever
- Batch sizes keep calls well inside the context window: an Extract batch is ~10 × 8,000 characters, about 20,000 tokens in and a few thousand out

### Usage limit and pending jobs

Built (task 19): `ClaudeCli` raises `UsageLimit` when an error answer matches a usage-limit pattern (not yet seen on a real limit; to confirm in task 26). The ranker, classifier and extractor then raise `UsageLimitReached` with what they did and the jobs from the unfinished batch on, and one `UsageLimitGuard` asks, for every step alike: "N jobs not ranked: usage limit reached. Finish with what's done and carry them over, or stop? (f/s, Enter for f)". Finish: the step passes on what's done and the rest go to `pending.jsonl`; stop: the step fails, and the same command resumes it after the reset. The next run's `carried_over` step adds them after the filter (see the decision below), skipping any this run found again. The report says how many were carried over. An unreachable LLM (other errors) still fails the step, so it is resumed rather than carried over. The LLM cap (volume guard, below) carries jobs over the same way.


- When the subscription usage limit is hit mid-run, the run stops calling the LLM and asks: "N jobs not processed. Finish now and carry them over, or stop?" Default: finish
- Jobs not processed because of the usage limit, or because the LLM became unreachable, go to the run's `pending.jsonl` with descriptions
- The next run adds the last completed run's pending jobs before Filter: no re-fetch, no credits. JobsPipe's next window would not include them otherwise
- The run that processes a pending job owns it. If that run also hits the limit, leftovers carry over again. Deleting a run drops its pending jobs
- Terminal and report warn: how many jobs are pending, and when usage resets if the CLI says

### Volume guard

Built (task 26): a safety cap on the jobs one run sends to the LLM, `llm.ask_above_jobs` (60; `max_jobs_per_run` until renamed after the MVP, as a limit that asks, not one that cuts), checked by its own step, `llm_cap`, after describe and right before classify, the first LLM step and the one that sees the most jobs. Under the cap nothing is asked. Over it, the run asks: "75 jobs would go to Claude, over the cap of 60. Send them all, only the first 60, or stop? (a/f/s, Enter for f)". All: every job goes on. First: the first 60, in the order they come, go on; the rest go to the run's `pending.jsonl` with their descriptions, like jobs the usage limit stopped, so the next run's `carried_over` step takes them, the report's carried-over line counts them, and an `llm_capped` warning says how many. Stop: the step fails before any LLM call, and the same command resumes it and asks again (with a changed cap, if `config_local/settings.yaml` now says one). The cap starts low for the first real runs and goes up as they show what a run costs in usage.

### Seniority values

`intern`, `entry`, `mid`, `senior`, `lead` (staff, principal, tech lead), `manager`, `executive` (director and above), `unknown`. The prompt describes each.

### Requirement names

1. The Extract prompt includes the current vocabulary (the ~200 most frequent stored names), so the LLM reuses "Python" instead of writing "Python 3"
2. Deterministic cleanup after: trim, normalize case, strip version numbers
3. Later, if drift shows: an occasional consolidation pass builds an alias map applied when trends are read. Stored extractions never change

Built (task 21): `RequirementNames` applies the cleanup when "What employers ask for" is counted, not when names are stored: lowercase, hyphens and spacing, outer brackets, quotes and trailing punctuation, a trailing version number of one or two digits ("Python 3.11", "Java 17", while "ISO 27001" stays), a trailing "programming" or "language", and a short alias list (postgres and postgresql, js and javascript, k8s and kubernetes, gcp and google cloud, amazon web services and aws, and a few more). The report shows the most common original spelling.

### CV

Planned: the Extract prompt also runs on the CV text, returning the requirements it covers, with estimated years per skill, cached by the CV's content hash. Dropped in task 22 at the owner's ask: the CV text goes straight into the one call that compares it with the requirements (section 10), so there is no separate CV extraction.

### Prompts

Prompt files live in `llm/prompts/`, each with a version recorded on every classification and extraction. A changed prompt doesn't invalidate the cache; a re-extract command can target old versions later.

## 10. Trends and gaps

Input: `history()` (matched jobs from completed runs, with classifications and extractions) plus this run's matched jobs in memory.

Built so far (task 20): the market trends section. `MarketTrends` reads (through `MarketRuns`, since task 21) each completed run's `jobs.jsonl`, window and config (searches and sources, now kept in its manifest), adds this run's kept output (the extract step's, read before the run completes), and `TrendBuilder` works out the last six periods with a covered day (`trend_period`: week, month or quarter), a job counting once even if several runs found it. Figures: postings and postings per covered day; remote, hybrid and onsite shares of jobs that say, with the rest counted; salary median and 25th to 75th percentile from yearly USD midpoints (hourly times 2,080, monthly times 12; other currencies left out), and the share listing any salary; the seniority mix of labelled jobs, unknown counted apart. The change compares the latest period with the last complete period before it (percent for postings per day and salary, points for shares); with none, the report says there's nothing to compare yet. Notes list added or removed sources and added, removed or changed searches between runs, from the first period shown. Breakdowns by sector, domain and job type come later.

### Periods

- Length from `trend_period`: `week`, `month` (default) or `quarter`
- A job counts toward the period of its trend date: earliest posted date, else `first_seen`. A posting dated last month but found now goes into last month
- Coverage: each period records which of its days fell inside some completed run's window. A period is partial when coverage is under 100%: the current period, the first one (a first run mid-month reaches back only 2 weeks), and gaps where the lookback cap cut off a long break between runs
- When a period is partial, counts are compared per covered day, so a gap or half month doesn't look like a market drop. Shares need no adjustment

### Figures per period

| Figure | How |
|---|---|
| New postings | Count, covered days, count per covered day |
| Seniority mix | Share of each value; `unknown` on its own row, left out of the other shares |
| Salary range | Yearly-normalized midpoints in the main currency (the profile's `min_salary` currency, else USD): median, 25th to 75th percentile, and the share of postings that list a salary |
| Remote share | Remote, hybrid and onsite shares; unknown left out |

- Shown as a table of the last 6 periods, partial ones marked, with a change column against the last complete period
- With no earlier period, the report says there is nothing to compare yet
- A figure based on fewer than 20 jobs is marked "low sample"

### Criteria and source changes

- Each run stores a snapshot of its criteria and sources. If they differ across the periods shown, the report notes it ("2026-10-21: added search `nyc-office`; removed keyword `python`") and marks the boundary in the table
- Old jobs are not re-matched against new criteria: jobs that never matched were never extracted, so re-matching could only narrow history, which misleads in another way

### Breakdowns (informational)

Share by sector (free label from Classify), domain and job type: top 10 values, current period against the previous one. Sector labels get the same cleanup as requirement names.

### What employers ask for

- Basis: a rolling window one trend period long, ending today, compared with the window before it. Independent of how often the user runs, and not tiny early in a month
- Share: jobs mentioning the requirement over jobs with an extraction in the window (failed extractions left out)
- The top `requirements_per_type` per type, with share and change. Years requirements show the median years asked ("Python: 5 years")
- Traceable through run data: `Extraction.job_id` leads to the job and its postings. A `job-radar trace "Python"` command may come later

Built (task 21): the section, right after "Market trends". `MarketRuns` gives both market sections the same runs (every completed run's `jobs.jsonl`, plus this run's kept output); `MarketAsks` hands their matched jobs to `AskBuilder` with the run's last day. The window is 7, 30 or 91 days for `trend_period` week, month or quarter, ending on the run's last day, and the window before is as long. A job counts on its trend date (as in the trends), once even if several runs found it; jobs whose extraction failed are left out of both the count and the base. Per type (skills, tools, certifications, years), the top `report.requirements_per_type` (20) by jobs asking, ties by name, each with its share and the change in points; a requirement the window before didn't have changes from 0. Years rows show the median of each job's highest years asked ("Python: 5 years"). Each row keeps the ids of the jobs it came from (in the content, not printed). Fewer than 20 jobs with requirements in the window is marked as a low sample; with none in the window before, the report says there's no change yet and leaves the change column out. Free: counting only, no LLM.

### Experience to gain

1. The CV's requirement list comes from section 9
2. Exact match first: covered if the normalized name is in the CV list. Years requirements: covered if the CV's years reach the median asked, partly otherwise ("3 of 5 years")
3. One LLM call for the rest: the uncovered top requirements plus the CV text, judged covered, partly or missing, each with a one-line reason. Catches synonyms (Postgres, PostgreSQL) and implied experience (Airflow pipelines covering "workflow orchestration"). The same call writes a short "how to gain it" suggestion for the top 5 gaps
4. Shown: missing and partly covered requirements, most frequent first, with share and suggestion; covered ones listed and marked

The CV's requirements and coverage judgments are cached by CV content hash plus requirement name (section 5), so they stay stable and cost nothing on later runs.

Built (task 22), with steps 1 and 2 replaced at the owner's ask: there is no separate CV extraction and no exact match first. One LLM call takes the requirements "What employers ask for" lists this run (every type, up to `requirements_per_type` each), the CV text and `preferences.md`, and judges each requirement covered, partly or missing with a one-line reason, catching synonyms and implied experience. The same call writes a one-line "how to gain it" suggestion for every gap (missing or partly) that fits the preferences, such as hands-on or mission work; the report shows it for the top `report.gap_suggestions` (5) gaps only. Asking for every gap, not only the top 5, keeps the cache complete: a gap that later climbs into the top 5 already has its suggestion, with no extra call. Years requirements go in with the median years asked ("software engineering, 5 years").

- Classes: `CvGaps` (the report's `GapSource`) reads the cache, has the judge judge only the requirements it lacks, keeps the answers and has `GapBuilder` put the section together. `GapJudge` is a Strategy: `LlmGapJudge` asks the model (short ids `r1`, `r2`, most asked first, a JSON schema, one retry with what was wrong); `KeywordGapJudge` is the no-LLM judge for `--demo` and tests (covered when the CV names the requirement as a whole word, else missing, with one fixed suggestion). `FileGapCache` holds the cache file. `ReportStep` passes the asks section it already has to `CvGaps` and puts both into `ReportContent`; `MarkdownRenderer` only formats
- Cache: `output/cache/gaps.jsonl`, outside the run folders, so deleting runs keeps it; one line per requirement, keyed by the CV's SHA-256 content hash plus the requirement's type and name in one form (`RequirementNames`), with the judgment, its suggestion and the prompt version. Only requirements new to the list cost a call; none new means no call. A new CV is judged afresh, and adding its judgments drops the old CV's. A changed `preferences.md`, or a changed median of years asked, doesn't re-judge a cached requirement. A line that can't be read is skipped and judged again
- Shown after "What employers ask for": a table Requirement, Share, Status ("missing: reason", "partly: reason"), How to gain it, gaps most asked first (missing and partly together, by share), then "Covered:" with the covered names. With no requirements yet, the section says so; when every requirement is covered, it says that instead of a table
- Failures: a bad answer twice, or an `LlmError`, leaves the section with what earlier runs judged and a note that N requirements couldn't be compared this run; at the usage limit the call is skipped with a note (no carry-over: it is one call). Either way the run goes on, and the next run tries them again

## 11. Report and format layer

### A renderer that only formats

All numbers, sort orders, grouping and wording choices are made before the renderer. The report step assembles a `ReportContent` (immutable model) from the stage outputs; the renderer only formats it. A second format (JSON, HTML) is then a short file, logic is tested without Markdown, and the Markdown is tested with golden files. `ReportStep` assembles the content itself: each section with real logic has its own class (`TrendSource`, `AskSource`, `GapSource`, `OpeningGrouper`), so no `ReportBuilder` was needed.

Built (task 23): every section, always present, in this order: Alerts, Recommended jobs, New openings, Market trends, What employers ask for, Experience to gain, About this run. A section with nothing to show says so ("None." under Alerts).

- Header: the window, a line per source with its own dates and why when the sources' dates differ ("JobsPipe: 28 Oct to 11 Nov 2026, catching up (missed in the last run)."; front matter `covers_by_source`), any days a long break left out, then a sources line: "Sources: Fast Forward 200 postings, JobsPipe 18 postings (18 credits)." The convert step records each source's postings (zero included) in `source_counts.jsonl`; credits come from the spend log, and a skipped paid source reads "JobsPipe skipped by you". Front matter adds `sources` (by source key), `new_openings`, `recommended` and `alerts`
- Alerts: the run's warnings, one line each, from `warnings.jsonl` (task 24, section 13); "None." when there are none
- New openings: every matched job of this run (the extract step's kept output, carried-over jobs included), one line each: title, company, work mode, places, salary, posted date, the score when it was recommended, and a link per posting. `OpeningGrouper` puts them under `report.group_by` (`job_type` by default, `domain`, or `both`: domains as subheadings inside job types), names as the settings write them, in the settings' order, then "Other" (a label the settings don't have), then "Not labelled" (no label, or the LLM couldn't label it); empty groups are left out, newest posted first
- Links are labelled with each source's name for people (`label` on the source: "Fast Forward" for Getro network 997, "JobsPipe", "Demo board"); the data keeps the source keys. The paid sources lines use the same names
- Terminal, at the end: "Run finished: 23 new openings, 10 recommended, 0 alerts.", a line per alert (task 24), then "Report: <path>". The report step writes the summary line and the alerts into the `Report`; `RunSucceeded` puts its message together

The full content, section by section as later tasks add them:

```python
class ReportContent(Model):
    run: str                      # the header: the run, the window covered, any lookback note
    window: Window                # spans every source's window
    not_covered: Window | None
    source_windows: tuple[SourceWindow] # each source's own dates, only when they differ
    sources: tuple[SourceSummary] # name for people, postings, credits or skipped
    alerts: tuple[Alert]
    min_score: int
    recommendations: tuple[Recommendation]
    openings: tuple[OpeningGroup] # headings from group_by, jobs inside (or groups, for both)
    funnel: tuple[StepCount]      # counts per step
    spends: tuple[Spend]          # what each paid source spent
    carried_over: int             # jobs the usage limit or the LLM cap carried over
    trends: Trends                # table, partial-period notes, criteria change notes
    asks: Asks                    # top requirements by type, with shares and changes
    gaps: Gaps                    # missing and partly covered rows, covered list

class ReportRenderer(Protocol):
    def render(self, content: ReportContent) -> str: ...
```

### Format layer

One interface per format the requirements put behind a format layer:

- Report format: `ReportRenderer`. MVP: Markdown (`MarkdownRenderer`)
- Run data format: `RunStore` (section 5). MVP: JSON and JSONL files

### Layout rules

- YAML front matter with run id, dates, counts and sources: tools like Obsidian show it as properties, and an LLM gets the key facts without parsing the page
- Every section is always present; with no alerts the section says "None". Same shape every run
- Jobs are list items, not a table: seven columns wrap badly in a terminal or editor
- Groups follow the settings order, "Other" last, empty groups left out. Within a group, newest posted first
- A job found in several sources links to each
- Plain text: words instead of emoji or symbols, "to" for ranges, no HTML
- "About this run" at the end: the funnel (fetched, merged, already seen, filtered out, classified, matched, extracted, pending), credits spent, LLM calls. Shows where postings went, including server vs local filter drops (section 4)

The terminal prints a short summary at the end (new openings, alerts, report path), from the same `Report`.

### Sample

```markdown
---
run: 2026-11-03T14-05
covers: [2026-10-27, 2026-11-03]
new_openings: 42
sources: {jobspipe: 412, getro: 1478}
---

# job-radar report, 3 Nov 2026

Covers postings from 27 Oct to 3 Nov 2026 (since the last run). Sources: JobsPipe (412 fetched, 412 credits), Fast Forward (1,478 fetched).

## Alerts

- Warning: credits running low, 480 left on JobsPipe (threshold 500)

## New openings (42)

### Engineering (18)

- **Senior Data Engineer**, Acme Climate
  Remote (US). $150k to $180k a year. Senior. Climate. Posted 1 Nov.
  Searches: remote-us. Links: [JobsPipe](...), [Fast Forward](...)

## Market trends (by month)

| | Jul | Aug | Sep | Oct | Nov (partial, 3 of 30 days) | Change |
|---|---|---|---|---|---|---|
| New postings per day | 7.1 | 6.8 | 7.4 | 8.0 | 9.3 | up 16% |
| Remote share | 41% | 39% | 43% | 40% | 38% (low sample) | down 2 pts |

Note: on 21 Oct the search `nyc-office` was added.

## What employers ask for

### Skills

| Requirement | Share | Change |
|---|---|---|
| Python | 72% | up 3 pts |

## Experience to gain

| Requirement | Share | Status | How to gain it |
|---|---|---|---|
| dbt | 34% | missing | Build a small dbt project on a public dataset |
| Python, 5 years | 41% | partly (3 of 5) | |

Covered: Python, SQL, Airflow, AWS

## About this run

Fetched 1,890. Merged 37. Already seen 1,402. Filtered out 389. Classified 62. Matched 42. Extracted 42. Pending 0. LLM calls 6.
```

## 12. Cost checks

Applies to `PaidSource`s only; free sources skip it.

Built (task 17), with two changes from the plan below, both from the JobsPipe API check: the estimate is free (`POST /v1/jobs/export/estimate` per search, added up; per search and day since the change after the MVP), not count queries at 1 credit each; and monthly spend comes from `GET /v1/account` (free), so there is no ledger. The check runs in `JobRadarApp` after the windows are agreed and before the run folder exists, each paid source for its own window, so stopping leaves nothing behind; a resumed run checks again (free). When JobsPipe can't count a search on a day (slow phrase searches time out), the estimate is the ask-above limit, and the terminal says "at most". Counting one day at a time, phrase searches answer: over 3 days or more they timed out (Nov 11). Seen Nov 9: `/v1/account` lagged the credits left that searches report (867 against 844); the fetch records the search's own figure.

### Limits from the plan

| Plan | Monthly budget | Ask above, a run (default) |
|---|---|---|
| Free | 1,000 once, no reset (budget = what is left) | 250 |
| Seeker | 10,000 | 2,500 (a quarter of the budget) |

Both can be overridden in settings (`sources.jobspipe.ask_above_credits`, `monthly_budget`). The ask-above limit is not a cut: a run that needs more asks first. It is a default to tune to how often the user runs: at the research funnel's rate, a 2-week window (~3,200 jobs) is over 2,500 and triggers the question below.

### Plan stage, per paid source, before any fetch

1. `credits()`: credits left, used this billing month, reset date if the API gives one
2. `count()` per search: one call each, 1 credit each
3. Estimate: the counts added up. An upper bound: overlapping searches and repeats within the month are free
4. Checks: estimate ≤ ask-above limit; used this month + estimate ≤ monthly budget; estimate ≤ credits left

All paid sources are planned before any fetch, so the user decides once, up front.

### Outcomes

| Case | What happens |
|---|---|
| Within all limits | Show the estimate, go ahead |
| Over the ask-above limit or the monthly budget | Show the estimate, both limits and credits left; ask: go ahead, skip this source this run, or stop the run |
| Over credits left | Ask: skip this source, or stop. No "go ahead": running out mid-fetch would make it partial |

```
JobsPipe: about 3,240 jobs (3 searches, may overlap). Count queries used 3 credits.
Ask above 2,500: over. Monthly budget 10,000: 6,900 used, 3,100 left: over.
Credits left: 3,180.
[g] go ahead  [s] skip JobsPipe this run  [x] stop the run
```

### During the fetch

- The fetch may spend the approved estimate plus 10% (new postings can appear between count and fetch) without asking again
- Reaching that cap with jobs still to fetch, or with a search not yet asked, it asks (built after the MVP): "JobsPipe: 330 jobs fetched (330 credits) and more to go. Keep going for up to 330 more? (y/n, Enter for n)". Yes fetches on from where it stopped (the same search and cursor, then the searches left) for up to another cap's worth, never past the credits left, and asks again each time that runs out. No, Enter or no one to answer fails the source as before. Most useful when JobsPipe couldn't count and the cap is only the ask-above limit plus 10%, but it asks the same when a count was low
- A day the cost check counted jobs for that comes back empty fails the fetch the same way (built after the MVP): JobsPipe answers a search that timed out with 200 and no jobs, and only the count tells it from a day with none
- A fetch stays all or nothing: failing, it raises `JobsPipeError` after saying what was spent, and the fetch step warns that JobsPipe failed, as for any failing source. Credits run out with jobs left: it fails without asking. The credits aren't lost: repeats within the month are free, so the next run gets those jobs again at no cost
- Built in task 25 (found by the acceptance pass): until then the fetch stopped at the cap and kept what it had. Until the change after the MVP, reaching the cap failed the source without asking

### Monthly spend

- Preferred: the source's own credit data (requirements), so deleting runs or running often can't throw the budget off
- Fallback, if JobsPipe reports only credits left: a spend ledger at `output/ledger.jsonl`, outside run folders, so deleting a run doesn't erase its spend. Monthly spend = ledger sum for the billing month. Which case applies is on the section 4 check list
- Billing month: the reset date from the API if given, else the calendar month

### Recorded and alerted

- `spend.jsonl` records each paid source's approval (the estimate and whether the source could count it, the count per search and day for JobsPipe, credits before, what the monthly budget still allowed, the decision: `auto`, `approved`, `skipped`, or `failed` when the cost check itself failed) and what the fetch charged and left, with the credits agreed during the fetch past the cap (`extra_approved`, 0 when none); the report says them as "20 more approved by you during the fetch"
- Warnings (built, task 24): credits left after the fetch below `alerts.low_credits` (100 by default); the monthly budget reached (the fetch charged at least what the budget had left); a source skipped by you at the cost check
- A paid source whose cost check fails (JobsPipe down, say) is told in the terminal and left out of the run as `failed`; the fetch step warns about it like any failed source, so the free sources still run
- Later, for scheduled runs: with no one to ask, over a limit means skip the source

## 13. Errors and warnings

Built (task 24), as below.

### Mechanism

- Errors that the app expects are exceptions under one base class, `JobRadarError`, whose message says what's wrong and how to fix it. `SetupError` is the kind that stops a run before it starts: settings or profile invalid (`ConfigError`), CV unreadable (`ProfileError`), `claude` missing or logged out (`LlmUnavailable`), another run in progress (`RunInProgress`). A step's expected errors (`LlmError`, `JobsPipeError`, `BoardError`, `NoSourceData`) fail the run with their message
- Anything else is unexpected, a bug: the full traceback goes to `error.log` (`FileErrorLog`) and the terminal shows one line pointing to it. In a step, `Pipeline` writes it to the run folder and the run fails as usual, ready to resume. Outside any step (setting up, choosing the window, the cost check), `Cli` writes it to the output folder
- Warnings are collected, not raised: one `WarningLog` per run, `FileWarningLog`, writes `warnings.jsonl` in the run folder, which stays after the run. The factory hands it to the steps that warn, which call `warn(code, message)`; a warning already there is not added again, so a resumed run doesn't repeat it. The report step reads them last, as the report's Alerts and the terminal's alert lines
- Outside a run (choosing the window, offering a resume, `job-radar runs`), there is no run folder to record in, so `TerminalWarnings` tells each warning once in the terminal ("Warning: ...")
- Ctrl+C stops with one line, "Stopped by you", and exit code 1; a run that had started keeps its saved steps, and the same command offers to resume it
- `Cli` turns every ending into a short message and an exit code; no traceback reaches the terminal

### Preflight

Before a run folder exists, and before any credits or LLM calls, in this order:

1. Settings parse and validate (`Cli.start`)
2. The searches, then the CV and preferences load (the factory, for a real run)
3. API keys are set for every enabled paid source
4. `claude` is available and logged in
5. The lock is taken (the app, around everything that follows): `output/run.lock` holds the process id; a lock whose process no longer exists is removed; a live one stops the run. It is released when the run ends, however it ends
6. The newest run, if it failed, is offered for resuming (section 5)

The run folder is created only after the window and the spend are agreed, so a settings typo never leaves a failed run to clean up. Prompting for missing profile fields (task 12) is deferred after the MVP (owner, Nov 10); a missing or invalid field is a setup error that names the file, the key and the fix.

### Errors (the run stops)

| Kind | Example message |
|---|---|
| Settings invalid | Could not set up the run: config_local/settings.yaml: recommend.min_scor: unknown key. Fix it in config_local/settings.yaml; config/settings.yaml lists every setting with its default |
| Profile invalid | Could not set up the run: config_local/profile.yaml: searches.one.rols: unknown key. Fix it in config_local/profile.yaml; config_local_example/profile.yaml shows every key |
| CV unreadable | Could not set up the run: config_local/cv.pdf has no text (a scanned PDF? Export a text PDF, or use cv.md) |
| API key missing | Could not set up the run: JOBSPIPE_API_KEY is not set: add it to config_local/.env, or set sources.jobspipe.enabled: false in config_local/settings.yaml |
| LLM unavailable | Could not set up the run: `claude` is not logged in: run `claude auth login` |
| Run in progress | Could not start the run: Another run is in progress (pid 4312). Wait for it to finish; if no run is going, delete output/run.lock |
| No source | Run failed at step 'fetch': No source returned data: JobsPipe failed (no answer in time after 3 retries), Fast Forward failed (HTTP 503 after 3 retries) |
| Unexpected, in a step | Run failed at step 'classify': KeyError: 'id', then "Unexpected error: details in output/runs/2026-11-03T14-05-00/error.log" |
| Unexpected, outside a step | Run stopped: unexpected error (TypeError: ...). Details in output/error.log |

"No source" applies only when every source the run tried failed; one failed source is a warning. Stopping at the cost check is not an error: it cancels the run (exit 0).

A source fails when it raises after its retries. `BoardClient` says why in a few words: "HTTP 503 after 3 retries", "HTTP 404", "no answer in time after 3 retries", "can't connect after 3 retries"; JobsPipe adds what it said ("HTTP 402: No credits left."). An unexpected error in a source (an API that changed shape) also counts as the source failing, named with its type.

### Warnings (the run finishes)

| Code | Recorded by | Example message |
|---|---|---|
| `source_failed` | fetch step | JobsPipe failed: HTTP 503 after 3 retries. Its postings are not in this run. |
| `source_empty` | fetch step (no pages), convert step (pages with no postings) | Fast Forward returned no postings. With a counted estimate above 0: JobsPipe returned no postings, though its count found 46: the next run fetches these dates again. |
| `source_skipped` | fetch step | JobsPipe skipped by you at the cost check: its postings are not in this run. |
| `budget_reached` | fetch step | JobsPipe monthly budget reached: this run used 120 credits, and the budget had 120 left this month. |
| `credits_low` | fetch step | JobsPipe credits running low: 80 left (alerts.low_credits is 100). |
| `llm_failed` | classify, extract and recommend steps | The LLM couldn't label 3 of 40 jobs: their seniority and domain count as not given. Also "couldn't read the requirements of" (left out of What employers ask for) and "couldn't rank" (they can't be recommended) |
| `llm_pending` | `UsageLimitGuard` | Usage limit reached: 12 jobs not ranked, carried over to the next run. |
| `llm_capped` | `llm_cap` step | Over the LLM cap: 15 of 75 jobs not sent to Claude, carried over to the next run (llm.ask_above_jobs is 60). |
| `gaps_skipped` | `CvGaps` | Experience to gain: 5 requirements weren't compared with your CV (the LLM gave no usable answer). The next run asks again. |
| `no_new_jobs` | report step | No new jobs matched your searches. |
| `run_unreadable` | `FileRunHistory` | Run 2026-11-01T09-00-00 can't be read, so it is left out: its manifest.json is not as expected (window: Field required). `job-radar delete` removes it. |
| `kept_jobs_unreadable` | `FileSeenJobs` | The jobs run 2026-11-01T09-00-00 kept can't be read, so they count as new again and are left out of the market sections: its jobs.jsonl is not as expected (...). |

The classify and extract steps also tell their LLM warning in the terminal when it happens, as before. The ranker now handles a bad answer like the classifier and the extractor: ask again once, then split the batch, and a job that still fails gets no score.

The report lists every warning under Alerts ("None." when there are none) and counts them in the front matter. The terminal ends with "Run finished: 23 new openings, 10 recommended, 2 alerts.", one line per alert ("- JobsPipe failed: ..."), then the report's path.

Lookback capping and criteria changes are not alerts: they are notes in the report header and trends section. Built (task 14): after a long break the report says, under "Covers postings from ...", "Not covered: 1 Oct to 21 Oct 2026. The last run was on 30 Sep, and a run reaches back at most 14 days.", and the front matter has `not_covered`.

### Failed run

- The manifest stays not completed, every saved step stays, and an unexpected error leaves `error.log` next to them. No report is written
- Nothing is asked when a run fails: the message says the same command resumes it, and the next run offers to (section 5). `job-radar delete` removes it. It never counts toward seen postings, trends or the next window
- Exit codes: 0 completed (with or without warnings) or called off by you, 1 a run that failed or stopped, 2 a setup error (including another run in progress). Useful for scheduled runs later

## 14. Decisions and alternatives

| Decision | Alternatives considered | Why |
|---|---|---|
| Stages after Fetch see only `Posting` | Stages read each source's raw format | New sources plug in without changes elsewhere |
| Every step implements one `Step` interface; every collaborator sits behind an interface; only `AppFactory` knows concrete classes | Interfaces only at the swap points (the earlier choice) | The pipeline runs steps as black boxes, and each class knows the fewest neighbours. Changed on Nov 4, when the swap-point design felt coupled |
| Stages are small configured classes | Plain functions; interface plus implementation per stage | Settings and collaborators injected in one place, without empty abstractions |
| `typing.Protocol` for interfaces | `abc.ABC` | Structural: fakes need no inheritance |
| Step order in code, in `AppFactory` | Pipeline defined in settings | One place shows the flow; settings choose what each step uses, not the order |
| Trends recomputed from slim per-job records | Running counters; per-run summaries split by period | Deleting a run needs no undo logic. Summaries can't be recomputed when metrics, groups, top-N or extraction change, and inferred labels drift between runs. Volume is small. Summaries may come later as a cache built from the records, never the source of truth |
| Raw pages are the fetch step's saved output | Save only parsed postings; keep raw in memory | A failed parse resumes at convert without fetching again |
| Every step's output is saved | Checkpoint only the expensive steps (fetch, recommend) | One rule with no exceptions: no per-step settings, one way to count for the funnel, one way to resume. Saving the cheap steps costs seconds |
| Outputs pass between steps in memory; the disk is read only when resuming | Each step reads its input back from disk, also in a fresh run | With lists, passing in memory is as short and avoids a read per step. The JSON round trip that resume relies on is covered by the model tests and a resume test |
| Steps take and give lists | Streams (iterators), with per-item steps | Dedupe and recommend need all their input at once anyway, a stream can only be read once, and a run fits in memory. Volume that grows is across runs, which gets its own storage (task 13) |
| Three model layers: `Posting`, `Job`, `Extraction` | One posting type with derived fields added in place | Re-extract without re-fetch; dedupe result is a type |
| Pydantic for models that cross a boundary; dataclasses for in-memory only | Pydantic only for external input; dataclasses everywhere | Every domain model is saved and read back, so it needs parsing anyway; one model per concept, no converters |
| Per-source Pydantic models for raw responses, inside the adapter | Plain dict access | API changes fail with a clear field error |
| `PaidSource` extends `Source` with `credits()` and `count()` | Cost methods on every source, returning None when free | Free sources carry no cost code |
| Settings configure sources; field mapping in code | Generic adapter mapping JSON fields from settings | The two MVP sources share no shape; revisit when several sources do |
| Filter stage reapplies all common criteria | Track which criteria each source applied server-side | Consistent across sources, no bookkeeping; drops are counted |
| `httpx` injected, tests use `MockTransport` | An HTTP interface with a fake | Offline tests without another abstraction |
| Files: one folder per run, JSON and JSONL | SQLite | Plain text is a requirement; volume is small. `RunStore` contract tests keep SQLite possible later |
| A job is owned by the run that first matched it | Store every job each run sees | Counted once in trends; deleting a run frees its jobs to be owned again |
| Store every classified job, matched or not, as an LLM cache; only matched jobs count as seen | Store matched jobs only | Jobs dropped by Match aren't re-classified every run (Getro returns the whole board); a criteria change can still surface them |
| Matched jobs copied into the owning run with their extraction | Reference the earlier run's record | Deleting one run never breaks another |
| Failed runs never count (seen, trends, window) | A kept failed run marks postings as seen | A run failing after fetch would hide jobs never extracted or reported |
| Report saved in the run folder by the store; renderer returns text | Renderer writes its own file to a reports folder | Deleting a run removes its report; only the store knows the disk layout |
| Raw pages gzipped | Plain JSON | Largest files, read only by the parser |
| Sockets blocked in tests (`pytest-socket`) | Rely on discipline | A test that reaches the network fails instead of spending credits |
| Fixtures recorded with neutral queries, scrubbed, reviewed | Record with the user's settings; hand-written fixtures | Public repo: no search strategy or personal data. Recorded pages catch real API quirks |
| Acceptance criteria as the test list | Coverage percentage target | "Done" means the criteria pass |
| A `Clock` class injected | A `now()` callable; freezing time with a library | Deterministic tests with no dependency; the same clock stamps run folders and report dates |
| All personal files in one gitignored `config_local/` folder | Named files in .gitignore (`config.yaml`, ...) | Public repo: one rule covers files added later |
| CV as PDF, Markdown or text; PDF read locally with `pypdf` | Text only; let the LLM read the PDF | PDF is the standard CV format; local extraction is free and deterministic |
| Profile as named searches: AND within, OR across | One flat criteria set; an expression language | Covers real combinations ("remote in US, or onsite in NY") without a parser |
| `if_missing: keep \| drop` per criterion | Fixed rule per field | Missing data is common (about half of postings lack salary); the user decides |
| Locations as ISO 3166 / 3166-2 codes | Free text; country only | US states needed; codes match without fuzzy text |
| One `domains` list for cause areas, used by the filter and report headings | Separate mission list and grouping list | One taxonomy, defined once, with descriptions for the LLM |
| Two filter stages: Filter (source fields) before the LLM, Match (inferred fields) after Classify | Filter everything after extraction; skip inferred criteria | Cheap fields cut LLM work first; seniority and domain exist only after Classify |
| Several identity keys per posting (posting, ATS, fuzzy); any shared key means the same job | One key per posting; exact URL match | Same job arrives with different ids and URLs; ATS ids are the employer's own |
| Job id inherited from earlier runs via the key index | Primary posting key every run | Seen check and LLM cache work whichever source finds the job |
| Fuzzy key on company, title, country | Include city; compare descriptions; ask the LLM | Cities are worded differently; the other two are costly or non-deterministic. Accepts merging same-title openings |
| Fuzzy keys match history within 60 days; ATS keys always | No window | A new opening with an old title isn't seen forever |
| Two LLM passes: Classify (cheap, every filtered job), then Extract (full, matched jobs only) | One full pass on every filtered job, then Match | Full extraction only for jobs that reach the report; Classify is ~10x cheaper per job |
| `LLM.complete` text in, text out; JSON validated in a shared helper | Structured-output method on the interface | A new backend implements one method |
| Invalid output: retry once, then split the batch; no retry in later runs | Retry until success; drop the whole batch | Isolates bad jobs without looping forever |
| Jobs skipped by the usage limit carried over in `pending.jsonl` | Drop them; widen the next window to re-fetch | No re-fetch or credits; JobsPipe's next window wouldn't include them |
| Volume guard: ask above `ask_above_jobs` | No limit | Subscription usage is a real limit |
| Current vocabulary in the prompt, deterministic cleanup; alias map later | Free naming; a fixed taxonomy | Stable names without maintaining a taxonomy |
| Prompt version recorded; cache kept when prompts change | Invalidate the cache on prompt change | No re-spend on every prompt tweak; re-extract can target old versions later |
| Periods track coverage; counts compared per covered day when partial | Raw counts only | Gaps and half periods don't read as market drops; run frequency doesn't change figures |
| Salary as median and 25th to 75th percentile of yearly midpoints, main currency | Min and max | Robust to outliers; no exchange rates |
| History not re-matched when criteria change; change noted in the report | Re-match history with current criteria | Unmatched jobs were never extracted, so re-matching only narrows; the requirements ask to keep and annotate |
| Requirement shares over a rolling window of one trend period | This run's jobs only; calendar period | Independent of run cadence; enough sample early in a period |
| CV coverage: one LLM call on the requirements, the CV text and the preferences, with reasons and suggestions, cached by CV hash and requirement | Extract the CV's requirements first, exact match, then the LLM for the rest (the earlier choice); exact match only | Changed Nov 10 at the owner's ask: a separate CV extraction is a second prompt to keep right, and the comparison call catches synonyms and implied experience anyway. Still one call per new requirement, none once the list settles |
| The comparison call writes a suggestion for every gap; the report shows the top 5 | Suggestions for the top 5 gaps only, as first planned | A gap that climbs into the top 5 later already has one in the cache; otherwise it would stay empty, or cost a call with nothing new to judge |
| A failed CV comparison doesn't fail the run: the section shows what was judged before and says what wasn't | Fail the report step; carry over at the usage limit | The report is still worth having; the next run asks again, and it is only one call |
| `ReportBuilder` decides everything; renderer only formats | Logic in the Markdown renderer | A new format is a short file; logic tested once, Markdown by golden files |
| Jobs as list items | A table per group | Seven columns wrap badly in terminals and editors |
| YAML front matter with key facts | No metadata | Note tools show it as properties; an LLM reads key facts directly |
| Every section always present | Omit empty sections | Same shape every run, for people and LLMs |
| Funnel in "About this run" | No stage counts | Shows where postings went, including filter drops |
| All paid sources planned and approved before any fetch | Ask per source as it fetches | One decision up front |
| "Skip this source" offered when over a limit | Only go ahead or stop | Free sources still run when a paid one is over budget |
| No "go ahead" when the estimate exceeds credits left | Allow it, hoping overlap makes it fit | Running out mid-fetch would make the fetch partial |
| Fetch capped at estimate plus 10%; over the cap the source fails | No cap; hard cap at the estimate | Keeps fetches all-or-nothing and spend near what was approved; repeats within the month are free |
| Monthly spend from the source's credit data; ledger outside run folders as fallback | Sum spend recorded in run data | Deleting runs must not reset the budget |
| Errors as exceptions, caught by `Pipeline` and turned into `RunFailed`; warnings collected in a per-run `WarningLog` (task 24) | Result objects from every step; a logging framework | Steps stay plain; one place decides how a run ends |
| Preflight before the run folder exists | Create the folder first | Settings and input errors leave nothing to clean up, and no credits or LLM calls are spent |
| Failed-run delete prompt defaults to no | Default yes (the earlier choice) | A kept failed run can be resumed after its last finished step; it still never counts |
| Exit codes 0, 1, 2 | Always 0 | Scheduled runs later can tell outcomes apart |
| One failing source is a warning; only when every source the run tried fails does the fetch step fail (`NoSourceData`), naming each | Fail the run on the first failing source | A report from the other sources is worth having; the warning says whose postings are missing. A run with nothing fetched can't do anything useful |
| Any exception from a source counts as that source failing, named with its type when unexpected | Only expected errors (HTTP, JobsPipe) make a source fail; anything else fails the run | From the user's view, a board whose API changed shape has failed like one that is down; the other boards still give a report |
| `BoardClient` turns a failed request into a `BoardError` in a few words ("HTTP 503 after 3 retries"), also when the last try gets no answer | Pass httpx's own errors on | Its messages are long and name URLs; the warning should read as one line |
| A paid source whose cost check fails is left out as `failed`, and the fetch step warns about it | Stop the run; let it fail as an unexpected error | JobsPipe being down shouldn't stop Fast Forward; nothing is spent on a source that can't say what it costs |
| A failed paid fetch writes no spend record | Record it with nothing charged | What it charged before failing isn't known; the next run's cost check reads the account's credits anyway |
| Expected errors under one base class `JobRadarError`, setup errors under `SetupError`; anything else is a bug with its traceback in `error.log` | A code per error in a table (the earlier plan); catch everything the same way | The type decides what the user sees: a message with the fix, or one line pointing to the details. Existing errors (`ConfigError`, `ProfileError`, `LlmError`, `JobsPipeError`) just changed their base |
| `error.log` in the run folder for a step's bug, in the output folder for a bug outside any step | Always the output folder | The details stay with the run they belong to, and go when it is deleted |
| One run at a time through `output/run.lock`, taken by the app around the resume offer, the window, the cost check and the run | A lock per runs folder (real and demo apart); a lock only around the pipeline | Two commands would otherwise both offer to resume the same failed run. One lock is simpler, and a demo run takes seconds. `runs` and `delete` don't take it yet |
| A stale lock is one whose process id no longer runs, or that can't be read | A time limit | A run can take hours (descriptions at 1s each), so age says nothing; a dead process says it all |
| Warnings outside a run told in the terminal once, by `TerminalWarnings` | Drop them; keep them for the next run | Before a run folder exists there is nowhere to record them, and an unreadable run folder is worth knowing about when choosing the window. The same warning inside the run is recorded and shown again in the report |
| A warning equal to one already recorded is kept once | Keep duplicates | A resumed run redoes the failed step, and several readers of the history meet the same unreadable folder |
| The classify and extract steps keep telling their LLM failures as they happen, besides recording them | Record only | A long run shows progress; the summary at the end repeats it next to the other alerts |
| Exit codes: 0 completed or called off, 1 a run that failed or stopped, 2 a setup error or another run in progress | 2 for stopped by you (the earlier plan) | Calling a run off was already 0 (task 4); 2 has meant a setup error since task 3 |
| Models store collections as tuples | Lists, relying on "frozen" | Pydantic's frozen blocks `job.id = ...` but not `job.postings.append(...)`; tuples make "never changed after" hold |
| Interfaces start with the methods the skeleton calls and grow per task | Full interfaces from the start | No placeholder types (`History`, `CvAnalysis`, `Credits`) before their sections are built; fakes don't carry unused methods |
| Build a walking skeleton first: every step works end to end in a simple form, then each grows | Build each step complete, in order | The whole flow runs and is tested from the start; each later PR swaps one simple part for the real one. Changed on Nov 5 |
| A demo board, demo profile and `KeywordRanker`, kept for good behind `run --demo` | Fakes that live only in tests; throwaway scaffolding | The end-to-end test stays offline, and anyone can try the tool without credits, an LLM or a CV. The demo board plugs in like a real one, which also tests that a new source needs no changes downstream |
| Run folders named to the second | To the minute | Two runs in the same minute would share a folder |
| Windows in whole days, starting one day before the last run's last day | Times of day; one day after the last run; a later run the same day replaces the earlier one | Postings carry only a date, so a time would be false precision. Repeating the last day covers a run made early in it, the extra day covers postings listed late; repeats are free and removed by the seen check. Replacing runs would delete history and needs extra logic |
| Ask before a first run or a long-break run; just say the dates after a recent run | Ask every time; never ask | The unusual cases reach back further than usual, so they're worth a look; asking every time trains you to press Enter |
| Cancelling at the prompt exits with 0 | 1, like an error | Calling a run off isn't a failure; nothing was started |
| Demo runs keep their own history under `output/demo/` | Demo runs among real runs | A demo run must never move a real run's window |
| Run completion recorded in the manifest, by `Checkpoints.complete()` | Infer it from which files remain; a separate marker file | One place says what a run covered and whether it completed; replaces `discard_all`, which ran at the same moment |
| Fast Forward paged newest first, stopping at the page that reaches past the window | Fetch the whole board every run | The search has no date filter but sorts by listing time, so a 14-day window takes about 2 requests instead of 8 |
| Full descriptions fetched after the filter, only for jobs kept, through a describer per board (task 7a) | Fetch every description during fetch; no descriptions | Getro needs one request per job at 1s each: about 400 for a first run, mostly for jobs the filter drops. Boards that already send descriptions skip the step |
| One description request per job, for its primary posting only | Describe every posting of a merged job | Merged postings are the same job, so one text is enough for ranking; a second copy costs another second |
| A job the board no longer has (404) or no longer lists as active keeps an empty description | Drop it; fail the run | Dropping is the filter's job, and one closed job shouldn't fail a run; the ranker still sees the title |
| Pacing and retries in one `BoardClient`, shared by a board's source and describer | Each class retries on its own | One retry rule per board, written once |
| HTML turned into text with the standard library's `html.parser` | BeautifulSoup, html2text | No new dependency; job descriptions use a handful of tags |
| The ranker asks with a JSON schema | Plain text answers parsed by the ranker | The CLI holds the answer to the shape, so fewer retries and no code fences to strip; one optional parameter on `Llm` |
| A bad ranking answer is asked again once, with what was wrong, then the batch is split; a job that still fails gets no score and a warning (changed in task 24) | Fail the step (the earlier choice, until warnings existed) | Same rule as classify and extract (section 9): one bad job no longer fails a run, and the warning says how many weren't ranked |
| Ranking sees each description cut to 4,000 characters, 20 jobs a prompt | The full description; the Extract cap of 8,000 | About 25,000 tokens a prompt; the start of a posting says most of what fit depends on |
| The CV is `cv.pdf`, `cv.md` or `cv.txt` in `config_local/`, the preferences `preferences.md`; both required | A path in a profile file; preferences optional | The profile file comes with settings (task 10). Ranking without preferences would judge experience only, so a missing file is more likely a mistake |
| Title asides in brackets dropped only when about place or work mode | Drop every bracketed aside | Real Fast Forward titles use brackets to tell roles apart ("Specialist (Media and Communication)") |
| Until country codes exist, the job key compares places as written | Leave places out of the key | Same title in different cities is common on Fast Forward (one org posts a role per district); leaving places out would merge them |
| `Clock.now()` returns local time with its UTC offset | UTC; naive local time | Run folders and report dates match the user's clock; saved times stay unambiguous |
| One `FileCheckpoints` per run, created by `AppFactory` with the run's folder | A store for all runs that starts a writer per run (`RunStore.start` returning a `RunWriter`, the earlier choice) | Born for one run, it never starts or tracks a run and holds no state in memory. Run history gets its own interface with task 13 |
| Code comments say what a class or function does, never cite design sections; temporary notes are `TODO(task N)` | Section references in docstrings | Code reads on its own; temporary notes are findable and removed by their task |
| No state in memory: every class is configured once; a run's state is its folder | A few named in-memory holders (the earlier choice) | Nothing to track or reset; a crash loses nothing that resume needs |
| `Pipeline` saves and loads every step's output; steps never touch storage | Steps save their own output; a saving decorator around each step | Resume decides where a run starts, which is about step order, so it belongs to the pipeline. A decorator per step would load every earlier output just to pass it along, with the skip logic spread over six wrappers |
| A run's warnings in `warnings.jsonl` in its run folder, through a `FileWarningLog` the factory builds per run and hands to the steps that warn (task 24) | An in-memory `Alerts` created per run and passed per call (the earlier plan); `App.alerts` | Like the spend log: no state in memory, the file stays with the run for later reading, and a resumed run keeps the warnings of the steps it skips. Steps hold it like any other configured part |
| `RunResult` with `RunSucceeded` and `RunFailed`, each giving its own `message()` and `exit_code()` | One result class with an `ok` flag | Each outcome carries only its own data; `Cli` shows any result without checking its kind, so a new outcome needs no change there |
| `JobRadarApp` between `Cli` and `Pipeline` | `Cli` calls the pipeline directly | Thin today; later commands (`runs`, `delete`) become its methods while `Cli` keeps talking to one object |
| Steps exchange lists of models | Any Python object | One generic save and load works for every step, with files now and a database later |
| A source and a parser per board | One `Source` class that fetches and parses | Parsers are tested on saved pages with no network; a failed parse resumes without fetching again, which matters when fetching costs credits |
| One `FilterStep` that knows the `Search` model; an empty criterion lets every job through | A filter class per criterion | Flexibility comes from the search settings, not from more classes |
| `CandidateProfile` is the CV and free-text preferences; the search is not passed to the ranker | Ranker also gets the search criteria | The search decides what gets in, the profile what ranks well; soft wishes like salary go in the preferences |
| Ranking is a Strategy (`JobRanker`) over an `Llm` interface | The step calls `claude -p` itself | Another ranker, or the per-token API, is a new class; tests use a fake ranker or a fake `Llm` |
| The report reads counts through a read-only `RunStats`, from the manifest | A shared context all steps read and write; the report asks for each step by name | No hidden coupling between steps: a new step shows up in the funnel on its own, and the report can't save or delete |
| On success, delete every checkpoint; keep the manifest and the report | Keep every step's output; keep chosen outputs such as the deduped jobs | Checkpoints are only for resuming, which a successful run no longer needs. Jobs kept for history get their own storage with task 13 |
| Files for checkpoints; SQLite considered again at task 13 | SQLite now; MySQL | Plain text is a requirement and lets you read a step's output directly while building. SQLite wins once data spans runs (history, seen jobs, trends); `Checkpoints` is an interface, so switching is one class. A database server is too much for a local tool |
| Step files are numbered by their place in the manifest, the order the steps finished in; a step saved again keeps its number | `AppFactory` passes the step order to `FileCheckpoints`; `Pipeline` passes each step's position | `ReportStep` needs the checkpoints before the step list exists, so the factory would have to write the order twice. Steps run in order, so the manifest already holds it, and nothing outside `FileCheckpoints` changes. Two digits keep the order past 9 steps |
| Recommend only jobs scoring at least `min_score` (40 by default, the bottom of "partial fit" in the ranker's guide); with none, the report says so | Always list the top N; list them all and mark the weak ones | A list of poor fits looks like advice. The first real run's best job scored 18 |
| Roles cut what reaches the LLM (task 9; now set in `profile.yaml`) | No roles (every job goes to the LLM) | Without roles, 380 of 391 jobs in 14 days reached the LLM and almost none were software. Engineer, engineering, developer, tech lead and architect cut that to 51; construction engineers still pass until excluded titles (task 11) |
| Salaries show whole thousands ("$129k"); a place that only repeats the work mode is left out | The amounts as posted; every place | Boards post salaries to the cent, and Fast Forward gives "Remote" as a place for remote jobs |
| Places in the report are separated by "; " | ", " | Places contain commas ("Amsterdam, Netherlands"), so commas between them were ambiguous |
| Settings are nested from the start (`llm`, `recommend`, `sources`), with only the keys that do something today | Flat keys now, nested later; every key in the sample above now | The file format doesn't change as tasks add keys; a key that does nothing would mislead |
| `profile.yaml` is required for a real run (terminal prompts, task 12, deferred after the MVP on Nov 10); the demo reads the example's, in `config_local_example/` | Default roles in code when the file is missing | A run without the user's searches sends the wrong jobs to the LLM; a clear error costs one copy of the example |
| The settings are read in `Cli.start`, before the factory | The factory reads them | `AppFactory` keeps taking `Settings`, so tests pass settings directly. A bad file still exits with 2 |
| Fetch and filter take all the searches (`SearchCriteria`); a job is kept if any search matches | One search until task 11 | `profile.yaml` lists several searches; boards with server-side queries (JobsPipe) will need them all |
| `--settings` and `--profile` flags wait until something needs another path | Add them now | The fixed files in `config_local/` are enough for one person |
| Places get ISO codes when parsed, by `PlaceCodes` with `pycountry`; the country is the last part of the text, the region any other part naming a subdivision | A hand-made country table; codes at filter time; a geocoding service | Boards write places as free text in many forms (130 in two weeks of Fast Forward). `pycountry` knows every country and subdivision; a few aliases (UK, DRC) fill its gaps. Done once, every later stage sees codes |
| A place counts as missing only when the posting names no country, or the wanted country without the wanted region | Any unreadable place makes the posting missing | "India; Remote" names a country, just not a wanted one; counting it missing kept five India-based jobs |
| A salary meets the minimum when the top of its range does | The bottom; the middle | A range that reaches the minimum is worth a look; the LLM sees the range |
| `JobMatcher` checks one job against one search and names the first criterion it fails | The checks inside `FilterStep` | One responsibility each; the dropped list (task 11b) needs the reason |
| `keywords` move after the describe step | Describe every job before the filter | Descriptions take a request per job; the filter cuts 380 jobs to 10 first |
| The filter hands the jobs it dropped, with why, to a `DropLog`, which writes `dropped.md` next to the report | The report rebuilds the list from the dedupe and filter outputs; dropped jobs in the report itself | The report would need other steps' outputs by name and the matcher again. The list is long (329 titles in two weeks), so it gets its own file; the report links it. Jobs dated before the window are only counted, since a board like Fast Forward sends everything it has |
| Deleting a run asks with no as the default, also when there's no input to read | Yes as the default, like the other questions | A stray Enter or a script must never delete runs; the other questions only start or skip work |
| Deleting runs lives in `RunFolders`, apart from the read-only `RunHistory` | One repository that reads and deletes | Most users of the history only read it (the window chooser); only the delete command gets the power to delete |
| The next run offers to resume a failed run; nothing is asked when it fails | Ask "Delete its data?" when it fails (the earlier design) | One question instead of two, asked when the user wants to go on; `job-radar delete` covers the rest |
| Only the newest run is offered for resuming | A list of failed runs to pick from | A failed run followed by another run is stale; its window has been fetched again |
| The days a long break left out are worked out from the window plan once and saved in the manifest | Work them out again when the report is written | A resumed run (13b) has no plan in memory; the manifest keeps what the report needs. The field is optional, so older manifests still read |
| A place with no country code counts by its text in the fuzzy key | Leave it out of the key; one "unknown" for every such place | "Remote" and a posting with no place at all are different facts; leaving it out would merge them |
| Seen jobs are the filter's output of completed runs, kept as `jobs.jsonl` by `FileCheckpoints` on success | A separate writer; a store outside run folders | The output is already saved as a checkpoint, so keeping one file costs nothing; deleting a run makes its jobs unseen with no extra logic |
| Dropping seen jobs is its own step, `new_jobs_filter`, after dedupe | Inside dedupe | One responsibility each, and the funnel shows how many jobs were new |
| JobsPipe-only narrowing lives in settings (`sources.jobspipe.filters`), passed through as written, not in the profile | Mission phrases as profile keywords | Fast Forward lists only mission orgs; the phrases are needed only to narrow JobsPipe's mainstream feed. Passing filters through needs no code per JobsPipe field |
| Keys come from the environment, else `config_local/.env`, through a `Secrets` interface | `python-dotenv`; settings | No new dependency for a NAME=value file; the environment wins for one-off runs; tests pass a plain dict |
| Defaults are a real YAML file the app reads (`config/settings.yaml`), the user's file merged over it | Defaults in the model, with an example file a test keeps in sync (the earlier choice) | Changed Nov 9 at the owner's ask: the full config you read is the one the app uses. Still one place for defaults: the model has none |
| The cost check runs in the app, before the run folder exists | Inside the fetch step | Stopping at the check leaves no failed run to resume or delete; the fetch step only spends within the approvals |
| Enter at a cost question means skip the source | Go ahead; stop | Skipping spends nothing and still gives a report from the free sources |
| Order: filter, describe, classify, match, recommend | Classify before describe | Labels need the description; Fast Forward gives it only after describe. Describing jobs that match then drops costs free requests only |
| Match is its own step after classify, reusing `JobMatcher`; the filter skips seniority and domain until a job has labels | One filter after classify | The cheap filter still cuts most jobs before any LLM call; one matcher keeps the rules in one place |
| The kept `jobs.jsonl` is the extract step's output | The match step's output; the filter's | Seen jobs are matched jobs (section 5); the extract step keeps exactly those, and adds requirements for task 21 |
| Extract runs before recommend, on every matched job | Only on recommended jobs | "What employers ask for" describes the market for your searches, not the few that fit your CV best |
| Carried-over jobs join after the filter, not before | Before the filter, as first planned | They passed the filter in their own run, and are usually dated before this run's window, which the filter would drop |
| One `UsageLimitGuard` for classify, extract and rank; the LLM passes signal partial progress with `UsageLimitReached` | Each step handles the limit itself | One rule and one question, and the passes stay unaware of prompts and files |
| Only the usage limit carries jobs over; other LLM errors fail the step | Carry over on any LLM error | A failed step resumes from its saved input; carrying over is for a limit that resets on its own |
| A cap on the jobs one run sends to the LLM (`llm.ask_above_jobs`, 60), in its own `llm_cap` step right before classify; over it, ask: all, the first 60 (the rest carried over in `pending.jsonl`, a warning), or stop (Enter for the first 60) | Before Extract at 1,000, as first planned; a cap inside each LLM step; cut silently | Classify is the first LLM call and sees the most jobs, so one check bounds every pass; carrying over reuses the usage-limit path, so nothing is lost; asking keeps a surprise volume from using the subscription unseen. Set low for the first real runs (task 26) |
| Each run's searches and sources are kept in its manifest, and trends compare them run to run | Compare against the current profile only | A jump after adding JobsPipe or a search is otherwise read as the market; older manifests without it are skipped |
| Only periods with a covered day are shown; a job dated in a period no run covered counts nowhere | Show every period back to the oldest posting | A period no run covered has no denominator for postings per day |
| "What employers ask for" uses a rolling window of 7, 30 or 91 days ending on the run's last day | Calendar periods, as the trends use | Independent of how often the user runs, and not tiny early in a month; the trends already show calendar periods |
| Requirement names are put in one form when counted, by rules and a short alias list | Cleanup when extracted and stored; merging by LLM | Stored extractions never change, so the rules can improve and old runs count the new way; free and repeatable |
| Version numbers are dropped only when one or two digits ("Java 17") | Any trailing number | Standards such as ISO 27001 or IEC 62443 keep their number |
| A job asking a requirement's years twice counts its highest in the median | Every mention | One job, one figure, as with the shares |
| Both market sections read their runs through one `MarketRuns` | Each section reads the run folders itself | One place knows how runs are read; each section only counts |
| Everything is a class, no free functions | Module-level functions for small helpers | One way to find any behaviour, and each class names its single responsibility |
| Postings per source are counted by the convert step, in `source_counts.jsonl` next to `spend.jsonl` | Counted by the fetch step; the report reads the convert step's output by name | The fetch step has only raw pages, and postings first exist in the convert step; a record of its own keeps the report from knowing other steps' outputs, and stays after the run |
| A source's name for people is its `label`; the factory hands the report a map from source key to label | Names hard-coded in the renderer; a setting per source | Each source knows its own board ("Fast Forward" is Getro network 997); the data keeps stable keys. A job carried over from a source that is now off shows its key |
| New openings are this run's matched jobs, with a score only on the recommended ones | Keep every job's score from the recommend step | The recommend step's output is the top N; keeping every score would change what it saves. Recommended jobs show both in their section and in their group |
| Grouped by both, domains are subheadings inside job types | One heading per pair ("engineering, climate") | Each job type reads as one block; pairs would repeat each job type once per domain |
| "Other" (a label the settings don't name) and "Not labelled" (no label) are separate groups, in that order | Unlabelled jobs under "Other" | "Other" says the job fits none of your types; "Not labelled" says the LLM couldn't tell, which is worth seeing apart |
| Group headings use the names as the settings write them ("engineering-management") | Capitalised or prettified names | The names are the user's; the same name appears in `profile.yaml` and in the report |
| A new opening's line includes the salary | Title, company, place, date, score and link only | The acceptance criteria ask for the salary on each job in the report |
| The demo classifier labels job types from title words | Leave job types unknown in the demo | The demo run shows real grouping, and the end-to-end test checks it |
| The code is grouped in folders by responsibility (app, pipeline and its steps, sources, llm, matching, report, storage, config, utils, models), read from the command down; a module is named after its main class, its interface, or its step | One flat package (the earlier layout); folders by layer only | Changed Nov 10 (PR #32): with over 40 modules in one folder, finding a class meant searching. Folders say what each part is for, and the naming rule says where a class lives without searching |
| Defaults in a committed `config/`, the user's overrides and personal files in a gitignored `config_local/`, and a committed `config_local_example/` that mirrors `config_local/` file for file | Examples beside the defaults in `config/` (PR #32); defaults inside the package (`job_radar/default_settings.yaml`), examples in `examples/`, personal files in `local/` and keys in `.env` at the repo root (the earlier layout) | Changed Nov 11 (PR #33): `config/` holds only what the app reads, so it is plain which files are defaults. Set up by copying one folder (`cp -r config_local_example config_local`) and editing, with every file already under its right name. Keys live in `config_local/` too, so one ignored folder holds everything personal |
| The demo runs on `config_local_example/`: its searches, CV and preferences, read by `SearchesFile` and `ProfileLoader` | A demo search and profile as constants in code (`--demo` before PR #33) | The demo shows what a fresh copy of the example would do, through the same readers as a real run, so the example files are tested on every demo run and can't go stale. The demo keeps its made-up board, keyword scoring and `output/demo/` |
| Per-run limits are named for what they do: `llm.ask_above_jobs` and `sources.jobspipe.ask_above_credits` (were `max_jobs_per_run`); reaching the JobsPipe cap with jobs left asks to keep going for another cap's worth, within the credits left, and the spend record keeps the credits agreed during the fetch | Keep the names; fail the source at the cap, as since task 25 | Changed Nov 11 at the owner's ask: "max" read as a cut, but both limits only ask first. A slow phrase search can't be counted, so its cap is a guess, and failing at it wasted the credits spent for that run. Asking keeps the fetch all or nothing and every credit agreed to |
| Each source tracks the dates it covered in full, in the manifest (version 3), and gets its own window from them; the run's window spans the sources' windows. A source that failed, was skipped or came back empty although its count found jobs (or, for a paid source, couldn't count) catches up in the next run | One window for every source, the whole window counting as covered once the run completes; deleting the run to recover a source's missed dates | Changed Nov 11 at the owner's ask: JobsPipe answered a 14-day phrase search with no jobs (its search silently timed out) and the run completed on Fast Forward's postings, so JobsPipe's dates were lost. Deleting the run redid the good sources and the LLM work. A paid source that comes back empty without a count is not covered either, as that is how the timeout looked (re-fetching an empty window costs nothing); a free source with nothing is still covered. Older manifests count as covering every source they list, as before |
| JobsPipe is searched and counted one day at a time: one query per search and day, with `posted_at_gte` and `posted_at_lte` set to that day; a day its count said had jobs that comes back empty fails JobsPipe for the run | Fewer mission phrases; one query per search, split into days only when it times out | Changed Nov 11 at the owner's ask: with the phrases, counts over 3, 7 and 14 days answered 504 while one day answered, and the 14-day search answered 200 with no jobs and no error, so a run got nothing without knowing. Fewer phrases narrows what is found; splitting on timeout misses the silent empty answer, which only a per-day count catches. More requests (84 a 14-day run with 3 searches, at the least: 42 counts and 42 searches) are paced and cost no more credits, one a job either way; the count per day keeps the estimate real. The counts travel in the plan and the approval rather than staying in the source, which keeps it stateless; `fetch_paid` takes them as an optional argument |
| A run shows its progress by default: a start banner, a numbered line per step, live counts in the slow steps; `--quiet` or `verbose: false` turns it off. On a terminal the current step is one line redrawn in place; elsewhere, one line per update, at most one every 5 seconds | Quiet by default with a `--verbose` flag; a progress-bar library (`rich`, `tqdm`) | Changed Nov 11 at the owner's ask: long steps looked frozen and it wasn't clear which step ran or what came next. A library was not chosen: the need is one line redrawn and a few counts, about 60 lines with `\r` and a clear-line code, and a bar needs totals most steps don't have (a search's day count is known, a Claude retry is not). `rich` would also bring its own live display, which would have to be kept apart from the prompts; one `Terminal` that the prompter and the progress share guarantees a question never lands on the live line, and keeps the quiet output unchanged |
