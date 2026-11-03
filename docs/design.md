# Design

How job-radar meets [requirements.md](requirements.md).

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

A run fetches postings from the start of its window to now:

- First run: the window is the lookback (a setting, 2 weeks by default)
- Later runs: the window starts at the last completed run. A failed or deleted run doesn't count
- If the last completed run is older than the lookback, the window is the lookback, and the report says so and which dates it covers
- With "new data only" turned off, the window is always the lookback

### Stages

```mermaid
flowchart LR
    Load --> Plan --> Fetch --> Dedupe --> Filter --> Classify --> Match --> Extract --> Aggregate --> Compare --> Report
```

1. **Load**: read the settings (defaults merged with the user's file) and the user input (CV, search criteria). Prompt in the terminal for anything missing; stop with an error if it is still invalid
2. **Plan**: for each source, turn each search into that source's query and set the time window (see above). Paid sources also get the credits left and a match count, estimate the cost, check it against the limits, and ask the user when it is over
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
- **Raw responses kept**: a parser fix can be re-run on stored data without spending credits again

### Volume

| | Postings per run | Description text (~5 to 10 KB each) |
|---|---|---|
| Typical (~1,600 per 7 days from the research funnel, 2-week window, plus Fast Forward) | ~4,500 | ~25 to 45 MB |
| Worst case (a whole Seeker month of 10,000 in one run, plus ~1,500 Fast Forward) | ~11,500 | ~60 to 120 MB, up to ~250 MB in memory |

- One run fits in memory, and the credit limits cap it. Stages pass plain lists; no streaming
- Raw responses are written to disk as they arrive and not kept in memory: nothing after the adapter reads them
- History grows with every run (at 10,000 jobs a month, ~120,000 a year). Trends read slim per-job records without descriptions (~1 KB each, ~120 MB a year at the full budget). Storage keeps descriptions apart (section 5)

## 2. Code structure

The goal is that reading `pipeline.py` shows what a run does.

### Top level

`run()` lists the stages and does nothing else (names are illustrative):

```python
def run(app: App) -> None:
    user = app.inputs.load()
    plans = app.planner.plan(user.criteria)
    postings = app.fetcher.fetch(plans)
    jobs = app.deduper.dedupe(postings)
    jobs = app.filter.apply(jobs, user.criteria)
    classified = app.classifier.classify(jobs)
    matched = app.matcher.match(classified, user.criteria)
    extracted = app.extractor.extract(matched)
    trends = app.trends.aggregate(extracted)
    gaps = app.gaps.find(extracted, user.cv)
    report = app.report_builder.build(extracted, trends, gaps, app.alerts)
    text = app.renderer.render(report)
    app.store.save_report(app.run.id, text)
```

`App` holds the configured objects. `config.py` builds it from the settings.

### Interfaces at the swap points

An interface exists where a second implementation exists or the requirements ask for a swap. Each one also has a test fake.

| Interface | Implementations | Why it is a swap point |
|---|---|---|
| `Source` | Getro, JobsPipe, fake | Sources are added without touching the rest |
| `LLM` | Claude CLI, fake (API later) | The way the LLM is called must be easy to swap |
| `RunStore` | Files, in-memory fake | Run data sits behind a format layer |
| `Renderer` | Markdown | The report sits behind a format layer |
| `Prompter` | Terminal, scripted fake | Runs are interactive; tests cannot type |

Interfaces are `typing.Protocol` classes: implementations and fakes don't inherit from them.

### Stages

Each stage is a small class in its own file. It takes its settings and collaborators in the constructor and has no interface of its own:

```python
deduper = Deduper(store=store, new_only=settings.new_only)
trends = TrendAggregator(store=store, period=settings.trend_period)
extractor = Extractor(llm=llm, batch_size=settings.llm.extract_batch)
```

### Declarative configuration

The settings pick implementations by name, and `config.py` builds them:

```yaml
sources:
  getro: {board: ffwd}
  jobspipe: {plan: seeker}
llm: {backend: claude_cli, model: haiku}
report: {format: markdown}
```

The stage order stays in code, not in settings.

### CLI

- `job-radar run`: one run (`--profile`, `--settings` to override paths)
- `job-radar runs`: list runs with their status
- `job-radar delete <run-id>`: delete a run, after confirmation

### Layout

```
job_radar/
  cli.py           commands: run, runs, delete
  pipeline.py      run(): the stages, nothing else
  model.py         Posting, Job, Classification, Match, Extraction, Run
  config.py        settings and defaults; builds App
  inputs.py        profile and CV (PDF via pypdf)
  sources/         base.py (Source), getro.py, jobspipe.py
  llm/             base.py (LLM), claude_cli.py, ask_json.py, prompts/
  store/           base.py (RunStore), files.py
  report/          base.py (Renderer), builder.py (ReportBuilder), markdown.py
  ui/              base.py (Prompter), terminal.py
  stages/          plan.py, fetch.py, dedupe.py, filter.py, classify.py, match.py, extract.py, trends.py, gaps.py
tests/
  fakes.py         FakeSource, FakeLLM, MemoryStore, ScriptedPrompter
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
    locations: list[Location]
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
    keys: list[str]         # identity keys: posting, ATS, fuzzy (section 8)
    postings: list[Posting] # primary first; the report shows its fields
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
    requirements: list[Requirement]
    prompt_version: str

class Match:                # one per matched job
    job_id: str
    searches: list[str]     # names of the searches it matched

class Requirement:
    type: RequirementType   # skill | tool | certification | years
    name: str               # normalized: "Python", "CISSP"
    years: int | None       # for type years: 5 in "5+ years of Python"

class Run:
    id: str                 # start time, e.g. "2026-11-03T14-05"
    started_at: datetime
    finished_at: datetime | None
    status: RunStatus       # running | completed | failed
    window: tuple[date, date]
    criteria: SearchCriteria    # snapshot of the profile's searches, to note changes between periods
    sources: list[SourceResult]

class SourceResult:
    source: str
    queries: list[dict]     # what was sent, one per search
    fetched: int
    estimate: int | None        # paid sources: sum of counts (section 12)
    credits_before: int | None
    credits_after: int | None
    credits_spent: int | None   # None for free sources
    decision: Decision | None   # auto | approved | skipped
    error: str | None
```

How the requirements map onto it:

- Trend date: the primary posting's `posted_at`, or `first_seen` when missing
- Traceability: a requirement belongs to an `Extraction`, which points to a `Job` and its postings
- Criteria changes: each `Run` keeps a snapshot of the criteria it used
- Monthly spend and source alerts: from `SourceResult`

### Model classes

- **Pydantic** (frozen) for everything that crosses a boundary: files, LLM output, APIs. That is every model above, plus settings and user input (section 7)
- **Pydantic inside each adapter** for that source's raw response, with only the fields used (extra fields ignored). An API change then fails with the field that broke, reported as a source warning. These models never leave the adapter
- **Dataclasses** for objects that live only in memory during a run: `App`, fetch plans, the `Report` passed to the renderer

### Left for later sections

- `SearchCriteria`, `Search`, `CV`, settings: section 7
- Seniority values, requirement name normalization: section 9
- Duplicate matching and job identity across runs: section 8
- Not modelled: whether a requirement is "must have" or "nice to have". Not in the requirements

## 4. Source integration

### Interface

```python
class Source(Protocol):
    name: str
    def plan(self, searches: list[Search], window: Window) -> FetchPlan: ...
    def fetch(self, plan: FetchPlan, sink: RawSink) -> list[Posting]: ...
    def parse(self, raw: RawPage) -> list[Posting]: ...

class PaidSource(Source, Protocol):
    def credits(self) -> Credits: ...             # left, and used this billing month
    def count(self, plan: FetchPlan) -> int: ...  # match count (JobsPipe: 1 credit)
```

- `plan` turns each search and the time window into a query for this source, recorded in `SourceResult.queries`. The cost estimate adds up the counts, so it can overestimate a little when searches overlap
- `fetch` pages through the API and writes each raw page to the `sink` as it arrives. It returns postings only if every page succeeded; otherwise it raises `SourceError`, the run drops that source's postings and adds a warning. That keeps fetches all-or-nothing
- `parse` is pure, raw page to postings. Used by `fetch`, by offline tests on recorded fixtures, and to re-parse stored raw pages after a parser fix
- Paid sources add `credits()` and `count()`. The Plan stage checks `isinstance(source, PaidSource)`; free sources carry no cost code
- `RawSink` comes from the store, so adapters don't know the disk layout

### Settings vs adapter module

| In settings | In the adapter module |
|---|---|
| Which sources are on | API calls, paging, auth |
| Per-source options: board name, plan, limits, request delay | Mapping raw fields to `Posting` (salary, work mode, location) |
| Source-only filters (JobsPipe: occupation group, ghost score, company size, no agencies) | How the common criteria become this source's query |
| Name of the API key variable (the key itself is in `.env`) | How this source reports credits |

Adding a source: a module under `sources/`, one line in the registry (name to class), and its settings. The test fake is registered the same way.

"Declarative where possible" (requirements) means settings configure and choose each source, and the field mapping stays in code. A generic adapter that maps JSON fields from settings pays off only when several sources share a shape (per-company Greenhouse, Lever and Ashby feeds, later).

### Common criteria applied twice

Each source applies what it can server-side, to save credits. The Filter stage then applies all criteria on source fields to every job regardless. Results are consistent across sources, with no bookkeeping of what each source applied. A posting the server matched may still be dropped locally (keyword matching can differ); the report counts these drops.

### Reliability

- HTTP: one shared `httpx` client, injected into adapters. Tests use `httpx.MockTransport`, so HTTP needs no interface of its own
- Retries: timeouts, 5xx and 429 get a few retries with backoff before the source fails
- Request delay per source in settings (Getro: 1s, from its robots.txt crawl delay)
- A failed paid fetch can't refund credits already spent. JobsPipe doesn't charge for repeats within the month, so a retry next run mostly costs nothing

### To check while building

- Whether JobsPipe's API reports credits used this month, or only credits left
- Whether Getro's search API filters by date. If not, fetch the whole board (~1,500 jobs, free); the seen check and window filter handle the rest

## 5. Run data storage

### Layout

One folder per run, all plain text:

```
output/                        (setting; default ./output, gitignored)
  runs/
    2026-11-03T14-05/
      run.json                 Run: schema version, status, window, criteria snapshot, SourceResults
      report.md                this run's report
      raw/getro/0001.json.gz   raw pages, written as they arrive
      raw/jobspipe/0001.json.gz
      jobs.jsonl               slim jobs this run classified or first matched (postings without descriptions)
      descriptions.jsonl       posting key, description
      classifications.jsonl    one Classification per job in jobs.jsonl
      extractions.jsonl        one Extraction per matched job in jobs.jsonl
      matches.jsonl            one Match per job this run owns
      pending.jsonl            full jobs the LLM couldn't process (usage limit), for the next run
  cv/
    <cv hash>.json             the CV's requirements and coverage judgments (section 10); not tied to a run
  ledger.jsonl                 spend per paid source, only if the API lacks monthly usage (section 12); not tied to a run
  .lock                        one run at a time
```

- JSON for the run record, JSONL for lists: one record per line, easy to append, `grep` and hand to an LLM
- Raw pages are gzipped: only the parser reads them, and they are the largest files (~10 KB per posting before compression)
- The report sits in the run folder, so deleting a run deletes its report. The terminal prints its path

### What a run stores

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

### Status lifecycle

- `run.json` is written at start with status `running`, and updated to `completed` or `failed` at the end. Writes go to a temp file, then rename, so a crash never leaves half a file
- A run still `running` when the next one starts means the process died: it is treated as failed, and the user is asked whether to delete it
- Only completed runs count: seen check, trends, window start. A kept failed run is for inspection only

### Interface

```python
class RunStore(Protocol):
    def start(self, run: Run) -> None: ...
    def raw_sink(self, run_id: str, source: str) -> RawSink: ...
    def save_jobs(self, run_id: str, jobs: list[Job]) -> None: ...   # splits off descriptions
    def save_classifications(self, run_id: str, items: list[Classification]) -> None: ...
    def save_matches(self, run_id: str, items: list[Match]) -> None: ...
    def save_extractions(self, run_id: str, items: list[Extraction]) -> None: ...
    def save_pending(self, run_id: str, jobs: list[Job]) -> None: ...
    def save_report(self, run_id: str, text: str) -> None: ...
    def finish(self, run: Run) -> None: ...
    def runs(self) -> list[Run]: ...
    def history(self) -> History: ...   # matched slim jobs + classifications + extractions, completed runs only
    def pending(self) -> list[Job]: ...  # from the last completed run
    def cached_classifications(self, job_ids: list[str]) -> dict[str, Classification]: ...
    def cached_extractions(self, job_ids: list[str]) -> dict[str, Extraction]: ...
    def cv_analysis(self, cv_hash: str) -> CvAnalysis | None: ...
    def save_cv_analysis(self, cv_hash: str, item: CvAnalysis) -> None: ...
    def record_spend(self, source: str, credits: int, at: datetime) -> None: ...   # ledger fallback
    def spend_since(self, source: str, start: date) -> int: ...
    def delete(self, run_id: str) -> None: ...
```

### Keeping other backends possible (SQLite later)

- Nothing outside `store/` touches `output/`. Stages, renderer and CLI go through `RunStore` methods that take and return models. So the renderer returns text and the store saves it
- Stable string IDs are the only links: run id, job id, and the `job_id` on `Classification`, `Match` and `Extraction`. Nothing points to data by file path or line number
- Contract tests: one suite runs against every `RunStore` implementation (`MemoryStore`, `FileStore`, later `SqliteStore`). A new backend is done when it passes
- Each `run.json` records a schema version, so old runs can be told apart and migrated when models change
- Raw pages stay gzipped files under any backend (`RawSink` keeps them separate). Trends stay in Python under any backend

### Disk use

At the research funnel's rate (~83,000 postings a year): descriptions ~1 GB a year, gzipped raw pages ~200 MB a year. Pruning old raw pages can be added later as a setting.

## 6. Testing

A plain `pytest` never touches the network, `claude`, or credits. `pytest-socket` blocks sockets, so a test that tries the network fails instead of calling an API.

### Layers

| Layer | What it tests | With what |
|---|---|---|
| Stages | Dedupe, filter, trends, gaps, plan | Real inputs from small factories (`make_posting(title=...)`), no fakes |
| Adapters | `parse` on recorded pages; `fetch` paging, retries, all-or-nothing (page 2 fails, nothing returned) | Recorded fixtures, `httpx.MockTransport` |
| LLM | Classify and Extract batching, retry and split, pending jobs on usage limit; `ClaudeCliLLM` output parsing, malformed JSON | `FakeLLM`; a fake command runner instead of `claude` |
| Contracts | Every `RunStore` (`MemoryStore`, `FileStore`) and every `Source` (adapters, `FakeSource`) | One suite each, run against every implementation |
| End to end | `run()` over several runs: the second finds nothing new, deleting a run makes its jobs unseen, trends span periods | Fakes, `FileStore` on a temp folder, `ScriptedPrompter` |
| Report | Markdown output | Golden files, regenerated with a flag and reviewed in the diff |

- Time: `App` gets a `now()` callable; tests pass a fixed time, so windows, periods and run ids are deterministic
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
local/                     gitignored as a whole
  profile.yaml             user input: searches, path to the CV
  cv.pdf                   the CV: PDF, Markdown or plain text
  settings.yaml            only the settings the user overrides
.env                       API keys
examples/
  profile.example.yaml
  cv.example.md            a fictional person
  settings.example.yaml    every setting with its default, commented
```

- One gitignored folder for everything personal: the repo is public, and one rule covers any personal file added later
- Paths can be overridden with `--profile` and `--settings`
- The CV is read locally (PDF via `pypdf`); the LLM sees only text. A scanned PDF with no text layer stops the run with an error asking for a text PDF. Word files later

### Profile

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

Every key has a default; the file can be missing.

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
alerts:
  low_credits: 500          # the only alert threshold; other alerts are fixed (section 13)
lookback_days: 14
new_only: true
trend_period: month
llm:
  backend: claude_cli
  model: haiku
  classify_batch: 50
  extract_batch: 10
  max_description_chars: 8000
  max_jobs_per_run: 1000    # above this, the run asks before Extract
  concurrency: 2
  timeout_seconds: 120
store: {backend: files, path: output}
sources:
  getro: {enabled: true, board: ffwd, delay_seconds: 1}
  jobspipe:
    enabled: true
    plan: seeker            # sets default monthly_budget and per_run_max
    api_key_env: JOBSPIPE_API_KEY
    filters: {occupations: [25], max_ghost_score: 40, exclude_agencies: true}
```

- Domains and job types ship with a starter list. Their descriptions guide the LLM. The profile refers to them by name; an unknown name is a validation error
- Plan limits (Free: 1,000 once; Seeker: 10,000 a month) are a table in the adapter; settings can override them

### Loading and validation

- Defaults live in the Pydantic settings model only. A test checks that `settings.example.yaml` parses and matches them
- The user's file is deep-merged over the defaults
- Unknown keys are errors, so typos are caught. Errors name the path: `sources.jobspipe.plan: must be one of free, seeker`

### Terminal input

- If `profile.yaml` is missing or a field is invalid, the `Prompter` asks for those fields only and validates each answer
- An empty answer stops the run with an error
- At the end it offers to save the answers to `local/profile.yaml`

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
- Title: lowercase, no punctuation, abbreviations expanded (Sr to senior, Eng to engineer), location text in brackets removed ("Engineer (Remote, US)")
- The fuzzy key uses country, not city: sources word cities differently ("NYC", "New York, NY")

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
class LLM(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...
```

JSON parsing and validation live in one shared helper (`ask_json(llm, prompt, Model)`), so a later API backend implements only `complete`.

### Claude CLI backend

- `claude -p` with the prompt on stdin, the model from settings (`haiku`), JSON output, no tools, one turn: a pure completion. Exact flags verified against the installed version while building
- Timeout per call (120 seconds) and small concurrency (2 by default), to go easy on subscription limits
- `claude` missing or not logged in: error "LLM not available", checked before Plan, so no credits are spent first
- Remaining subscription usage: check while building whether `claude` reports it in a scriptable form. If so, add a low-usage warning like `low_credits`

### Batches and failures

- Each job in a batch gets a short id (`j1`, `j2`); the answer must cover exactly those ids
- Invalid JSON or missing ids (including an answer cut off by the output limit): retry once with the validation error in the prompt, then split the batch in half and retry each half. A job that still fails counts toward the "LLM failed on N jobs" warning
- A job that fails Classify has all inferred fields missing (`if_missing` applies). A job that fails Extract is reported without requirements. Neither is retried in a later run, so a broken posting can't loop forever
- Batch sizes keep calls well inside the context window: an Extract batch is ~10 × 8,000 characters, about 20,000 tokens in and a few thousand out

### Usage limit and pending jobs

- When the subscription usage limit is hit mid-run, the run stops calling the LLM and asks: "N jobs not processed. Finish now and carry them over, or stop?" Default: finish
- Jobs not processed because of the usage limit, or because the LLM became unreachable, go to the run's `pending.jsonl` with descriptions
- The next run adds the last completed run's pending jobs before Filter: no re-fetch, no credits. JobsPipe's next window would not include them otherwise
- The run that processes a pending job owns it. If that run also hits the limit, leftovers carry over again. Deleting a run drops its pending jobs
- Terminal and report warn: how many jobs are pending, and when usage resets if the CLI says

### Volume guard

Before Extract, the run shows how many jobs and calls it is about to make. Above `llm.max_jobs_per_run` (default 1,000) it asks first, like the credit check.

### Seniority values

`intern`, `entry`, `mid`, `senior`, `lead` (staff, principal, tech lead), `manager`, `executive` (director and above), `unknown`. The prompt describes each.

### Requirement names

1. The Extract prompt includes the current vocabulary (the ~200 most frequent stored names), so the LLM reuses "Python" instead of writing "Python 3"
2. Deterministic cleanup after: trim, normalize case, strip version numbers
3. Later, if drift shows: an occasional consolidation pass builds an alias map applied when trends are read. Stored extractions never change

### CV

The Extract prompt also runs on the CV text, returning the requirements it covers, with estimated years per skill. Cached by the CV's content hash, so it re-runs only when the CV changes. When a requirement counts as covered: section 10.

### Prompts

Prompt files live in `llm/prompts/`, each with a version recorded on every classification and extraction. A changed prompt doesn't invalidate the cache; a re-extract command can target old versions later.

## 10. Trends and gaps

Input: `history()` (matched jobs from completed runs, with classifications and extractions) plus this run's matched jobs in memory.

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

### Experience to gain

1. The CV's requirement list comes from section 9
2. Exact match first: covered if the normalized name is in the CV list. Years requirements: covered if the CV's years reach the median asked, partly otherwise ("3 of 5 years")
3. One LLM call for the rest: the uncovered top requirements plus the CV text, judged covered, partly or missing, each with a one-line reason. Catches synonyms (Postgres, PostgreSQL) and implied experience (Airflow pipelines covering "workflow orchestration"). The same call writes a short "how to gain it" suggestion for the top 5 gaps
4. Shown: missing and partly covered requirements, most frequent first, with share and suggestion; covered ones listed and marked

The CV's requirements and coverage judgments are cached by CV content hash plus requirement name (section 5), so they stay stable and cost nothing on later runs.

## 11. Report and format layer

### A renderer that only formats

All numbers, sort orders, grouping and wording choices are made before the renderer. A `ReportBuilder` in the Report stage assembles a `Report` (plain dataclass) from the stage outputs; the renderer only formats it. A second format (JSON, HTML) is then a short file, logic is tested in the builder, and the Markdown is tested with golden files.

```python
@dataclass
class Report:
    header: Header                # date, window covered, lookback note, sources with counts and credits
    alerts: list[Alert]
    openings: list[OpeningGroup]  # headings from group_by, jobs inside
    trends: TrendSection          # table, partial-period notes, criteria change notes, breakdowns
    requirements: dict[RequirementType, list[RequirementRow]]
    gaps: GapSection              # missing and partly covered rows, covered list
    funnel: Funnel                # counts per stage

class Renderer(Protocol):
    extension: str                # ".md"
    def render(self, report: Report) -> str: ...
```

### Format layer

One interface per format the requirements put behind a format layer:

- Report format: `Renderer`. MVP: Markdown
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

### Limits from the plan

| Plan | Monthly budget | Per-run max (default) |
|---|---|---|
| Free | 1,000 once, no reset (budget = what is left) | 250 |
| Seeker | 10,000 | 2,500 (a quarter of the budget) |

Both can be overridden in settings. The per-run max is a default to tune to how often the user runs: at the research funnel's rate, a 2-week window (~3,200 jobs) is over 2,500 and triggers the question below.

### Plan stage, per paid source, before any fetch

1. `credits()`: credits left, used this billing month, reset date if the API gives one
2. `count()` per search: one call each, 1 credit each
3. Estimate: the counts added up. An upper bound: overlapping searches and repeats within the month are free
4. Checks: estimate ≤ per-run max; used this month + estimate ≤ monthly budget; estimate ≤ credits left

All paid sources are planned before any fetch, so the user decides once, up front.

### Outcomes

| Case | What happens |
|---|---|
| Within all limits | Show the estimate, go ahead |
| Over the per-run max or the monthly budget | Show the estimate, both limits and credits left; ask: go ahead, skip this source this run, or stop the run |
| Over credits left | Ask: skip this source, or stop. No "go ahead": running out mid-fetch would make it partial |

```
JobsPipe: about 3,240 jobs (3 searches, may overlap). Count queries used 3 credits.
Per-run max 2,500: over. Monthly budget 10,000: 6,900 used, 3,100 left: over.
Credits left: 3,180.
[g] go ahead  [s] skip JobsPipe this run  [x] stop the run
```

### During the fetch

- The fetch may spend at most the approved estimate plus 10% (new postings can appear between count and fetch)
- If it hits that cap, it stops and the source counts as failed, so fetches stay all-or-nothing. Rare, and the credits aren't lost: repeats within the month are free, so the next run gets those jobs again at no cost

### Monthly spend

- Preferred: the source's own credit data (requirements), so deleting runs or running often can't throw the budget off
- Fallback, if JobsPipe reports only credits left: a spend ledger at `output/ledger.jsonl`, outside run folders, so deleting a run doesn't erase its spend. Monthly spend = ledger sum for the billing month. Which case applies is on the section 4 check list
- Billing month: the reset date from the API if given, else the calendar month

### Recorded and alerted

- `SourceResult` records the estimate, credits before and after, and the decision (`auto`, `approved`, `skipped`)
- Warnings: credits left after the run below `low_credits`; monthly budget reached; source skipped for lack of credits
- Later, for scheduled runs: with no one to ask, over a limit means skip the source

## 13. Errors and warnings

### Mechanism

- Errors are exceptions: one base class `JobRadarError`; each subclass carries a message and a hint on what to do. Stages raise them; one wrapper around `run()` catches them, so `run()` stays a plain list of stages
- Warnings are collected, not raised: `App.alerts` is passed to stages, which call `alerts.warn(code, message, ...)`. Each is printed when it happens, saved in `run.json`, and shown at the top of the report
- Unexpected exceptions (bugs) and Ctrl+C take the same failed-run path. For a bug, the traceback goes to `error.log` in the run folder and the terminal shows one line pointing to it

### Preflight

Before a run folder exists, and before any credits or LLM calls:

1. Settings parse and validate
2. Profile and CV load (prompting for anything missing); CV text is extracted
3. The lock is taken; a lock left by a process that no longer exists is removed
4. A run still marked `running` is treated as failed, and the user is asked whether to delete it
5. `claude` is available and logged in
6. API keys are set for every enabled paid source

The run folder is created only after preflight passes, so a settings typo never leaves a failed run to clean up.

### Errors (the run stops)

| Code | Example message |
|---|---|
| `settings_invalid` | Settings invalid: `sources.jobspipe.plan` must be one of free, seeker (local/settings.yaml) |
| `input_invalid` | Profile still invalid: `searches.remote-us.locations`: "USA" is not an ISO code, try US |
| `cv_unreadable` | The CV has no text layer (a scanned PDF?). Export a text PDF, or use .md |
| `api_key_missing` | JOBSPIPE_API_KEY is not set. Add it to .env, or disable jobspipe in settings |
| `run_in_progress` | Another run is in progress (pid 4312) |
| `llm_unavailable` | `claude` not found or not logged in. Run `claude` once to log in |
| `no_source` | No source returned data: JobsPipe failed (timeout after 3 retries), Fast Forward failed (HTTP 503) |
| `stopped` | Stopped by you at the cost check |
| `unexpected` | Unexpected error. Details in output/runs/2026-11-03T14-05/error.log |

`no_source` applies only when every source failed; one failed source is a warning.

### Warnings (the run finishes)

| Code | Example message |
|---|---|
| `source_failed` | JobsPipe failed: HTTP 503 after 3 retries. Its postings are not in this run |
| `source_empty` | Fast Forward returned no postings |
| `source_skipped` | JobsPipe skipped: you chose to skip it / not enough credits |
| `no_new_postings` | No new postings matched your searches |
| `budget_reached` | JobsPipe monthly budget reached: 10,000 of 10,000 |
| `credits_low` | JobsPipe credits running low: 480 left (threshold 500) |
| `llm_failed` | LLM failed on 3 jobs: listed without classification or requirements |
| `llm_pending` | Usage limit reached: 120 jobs carried over to the next run (resets 18:00) |

Lookback capping and criteria changes are not alerts: they are notes in the report header and trends section.

### Failed run

- `run.json` gets status `failed` with the error code and message. No report is written
- The user is asked "Run failed: <message>. Delete its data? [Y/n]". Default yes: a failed run never counts, so keeping it is only for inspection
- Exit codes: 0 completed (with or without warnings), 1 error, 2 stopped by the user. Useful for scheduled runs later

## 14. Decisions and alternatives

| Decision | Alternatives considered | Why |
|---|---|---|
| Stages after Fetch see only `Posting` | Stages read each source's raw format | New sources plug in without changes elsewhere |
| Interfaces only at the five swap points | An interface per stage | Stages have one implementation and are pure logic, tested directly; extra interfaces add indirection. A `Protocol` can be added over an existing class later at no cost |
| Stages are small configured classes | Plain functions; interface plus implementation per stage | Settings and collaborators injected in one place, without empty abstractions |
| `typing.Protocol` for interfaces | `abc.ABC` | Structural: fakes need no inheritance |
| Stage order in code | Pipeline defined in settings | Reading `pipeline.py` shows the flow |
| Trends recomputed from slim per-job records | Running counters; per-run summaries split by period | Deleting a run needs no undo logic. Summaries can't be recomputed when metrics, groups, top-N or extraction change, and inferred labels drift between runs. Volume is small. Summaries may come later as a cache built from the records, never the source of truth |
| Raw responses saved with run data, written as they arrive | Save only parsed postings; keep raw in memory | Re-parse without spending credits; nothing after the adapter needs raw |
| Stages pass plain lists | Streaming with generators | A run fits in memory (see Volume); dedupe needs all postings and fetches are all-or-nothing |
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
| `now()` callable injected | A `Clock` interface; freezing time with a library | Deterministic tests with no extra abstraction or dependency |
| All personal files in one gitignored `local/` folder | Named files in .gitignore (`config.yaml`, ...) | Public repo: one rule covers files added later |
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
| Volume guard: ask above `max_jobs_per_run` | No limit | Subscription usage is a real limit |
| Current vocabulary in the prompt, deterministic cleanup; alias map later | Free naming; a fixed taxonomy | Stable names without maintaining a taxonomy |
| Prompt version recorded; cache kept when prompts change | Invalidate the cache on prompt change | No re-spend on every prompt tweak; re-extract can target old versions later |
| Periods track coverage; counts compared per covered day when partial | Raw counts only | Gaps and half periods don't read as market drops; run frequency doesn't change figures |
| Salary as median and 25th to 75th percentile of yearly midpoints, main currency | Min and max | Robust to outliers; no exchange rates |
| History not re-matched when criteria change; change noted in the report | Re-match history with current criteria | Unmatched jobs were never extracted, so re-matching only narrows; the requirements ask to keep and annotate |
| Requirement shares over a rolling window of one trend period | This run's jobs only; calendar period | Independent of run cadence; enough sample early in a period |
| CV coverage: exact match, then one LLM call with reasons and suggestions, cached by CV hash | Exact match only; LLM for everything | Catches synonyms and implied experience at one call per new requirement |
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
| Errors as exceptions caught by one wrapper; warnings collected in `App.alerts` | Result objects from every stage; a logging framework | `run()` stays a plain list of stages; warnings reach terminal, run data and report from one place |
| Preflight before the run folder exists | Create the folder first | Settings and input errors leave nothing to clean up, and no credits or LLM calls are spent |
| Failed-run delete prompt defaults to yes | Default no | A failed run never counts; keeping it is only for inspection |
| Exit codes 0, 1, 2 | Always 0 | Scheduled runs later can tell outcomes apart |
