# Architecture

How the code is put together: which classes exist, what each one is responsible for, which others it knows, and where state lives. Every box is a real class, named as in the code. The reasons behind each part are in [design.md](design.md).

**Shown now:** the design for the first real run, agreed on Nov 4. PR #2 builds it as a skeleton: every class and its signatures, no internals. Later PRs fill in one class at a time; each PR that changes the flow updates these diagrams.

The first real run: `job-radar run` fetches Fast Forward through its search API, turns the records into postings, dedupes them into jobs, keeps the jobs that match the search, asks the LLM which fit the CV best, and writes a report with the top N and a few counts.

## Rules the design follows

- **One responsibility per class**, and each class knows the fewest neighbours it can
- **Depend on interfaces.** Only `AppFactory` knows concrete classes
- **No state in memory.** Every class is configured once at creation and never changes. A run's state lives in its folder on disk, written only by `FileCheckpoints` and `FileReportWriter`
- **Steps exchange lists of models**, so one generic save and load works for every step

## Classes and dependencies

Two diagrams: the app and the pipeline that runs the steps, then the steps and what each one uses. Boxes marked with a pattern name (Repository, Adapter, Strategy) are interfaces.

### App and pipeline

```mermaid
classDiagram
    direction TB

    class Cli {
        +start()$
        +main(argv) int
    }
    class AppFactory {
        <<Factory>>
        -settings: Settings
        -clock: Clock
        +create() JobRadarApp
    }
    class JobRadarApp {
        -pipeline: Pipeline
        +run() RunResult
    }
    class RunResult {
        <<abstract>>
        +message() str
        +exit_code() int
    }
    class RunSucceeded {
        +location: str
        +summary: str
    }
    class RunFailed {
        +step: str
        +reason: str
    }
    class Pipeline {
        -steps: list~Step~
        -checkpoints: Checkpoints
        +run() RunResult
    }
    class Step {
        <<interface>>
        +name: str
        +output: type
        +run(data) list
    }
    class Checkpoints {
        <<Repository>>
        +has(step) bool
        +save(step, items)
        +load(step, kind) list
        +discard_all()
    }
    class RunStats {
        <<interface>>
        +funnel() list~StepCount~
    }
    class FileCheckpoints {
        -folder: Path
    }

    Cli ..> AppFactory : calls create
    Cli ..> JobRadarApp : calls run
    Cli ..> RunResult : calls message, exit_code
    AppFactory ..> JobRadarApp : creates
    AppFactory ..> Pipeline : creates
    AppFactory ..> FileCheckpoints : creates
    JobRadarApp o-- Pipeline : holds
    Pipeline o-- Step : holds, in order
    Pipeline o-- Checkpoints : holds
    Pipeline ..> RunSucceeded : creates
    Pipeline ..> RunFailed : creates
    RunResult <|-- RunSucceeded : extends
    RunResult <|-- RunFailed : extends
    Checkpoints <|.. FileCheckpoints : implements
    RunStats <|.. FileCheckpoints : implements
```

### Steps and what they use

```mermaid
classDiagram
    direction TB

    class Step {
        <<interface>>
        +name: str
        +output: type
        +run(data) list
    }
    class FetchStep {
        -sources: list~JobBoardSource~
        -search: Search
        -window: Window
    }
    class JobBoardSource {
        <<Adapter>>
        +name: str
        +fetch(search, window) list~RawPage~
    }
    class GetroSource {
        -board: str
    }
    class ConvertStep {
        -parsers: dict~str, JobBoardParser~
    }
    class JobBoardParser {
        <<Adapter>>
        +source: str
        +parse(page) list~Posting~
    }
    class GetroParser
    class DedupeStep {
        -key: JobKey
    }
    class JobKey {
        +of(posting) str
    }
    class FilterStep {
        -search: Search
        +matches(job) bool
    }
    class RecommendTopJobsStep {
        -ranker: JobRanker
        -profile: CandidateProfile
        -top_n: int
    }
    class JobRanker {
        <<Strategy>>
        +score(jobs, profile) list~Recommendation~
    }
    class LlmRanker {
        -llm: Llm
        -batch_size: int
    }
    class Llm {
        <<interface>>
        +complete(system, prompt) str
    }
    class ClaudeCli {
        -model: str
    }
    class ProfileLoader {
        +load() CandidateProfile
    }
    class CandidateProfile {
        <<immutable data>>
        +cv: str
        +preferences: str
    }
    class ReportStep {
        -stats: RunStats
        -writer: ReportWriter
    }
    class RunStats {
        <<interface>>
        +funnel() list~StepCount~
    }
    class ReportWriter {
        <<interface>>
        +write(text) str
    }
    class FileReportWriter {
        -folder: Path
    }

    Step <|.. FetchStep : implements
    Step <|.. ConvertStep : implements
    Step <|.. DedupeStep : implements
    Step <|.. FilterStep : implements
    Step <|.. RecommendTopJobsStep : implements
    Step <|.. ReportStep : implements
    FetchStep o-- JobBoardSource : holds, one per board
    JobBoardSource <|.. GetroSource : implements
    ConvertStep o-- JobBoardParser : holds, one per board
    JobBoardParser <|.. GetroParser : implements
    DedupeStep o-- JobKey : holds
    RecommendTopJobsStep o-- JobRanker : holds
    JobRanker <|.. LlmRanker : implements
    LlmRanker o-- Llm : holds
    Llm <|.. ClaudeCli : implements
    RecommendTopJobsStep o-- CandidateProfile : holds
    ProfileLoader ..> CandidateProfile : creates
    ReportStep o-- RunStats : holds
    ReportStep o-- ReportWriter : holds
    ReportWriter <|.. FileReportWriter : implements
```

How to read the arrows:

| Arrow | Means |
|---|---|
| `..\|>` dashed, hollow triangle | Implements the interface |
| `--\|>` solid, hollow triangle | Extends the class |
| `..>` dashed | Uses: calls the named functions, or creates the object |
| `o--` hollow diamond | Holds as a configured part, set once at creation, never changed |

### What each step takes and gives

The pipeline saves each step's output and passes it to the next step in memory. Only a resumed run reads from disk, once, to get the last saved output.

| Step | Name in the run folder | Takes | Gives |
|---|---|---|---|
| `FetchStep` | `fetch` | nothing | `RawPage`s from each job board |
| `ConvertStep` | `convert` | `RawPage`s | `Posting`s |
| `DedupeStep` | `dedupe` | `Posting`s | `Job`s, one per real job |
| `FilterStep` | `filter` | `Job`s | `Job`s that match the search |
| `RecommendTopJobsStep` | `recommend` | `Job`s | the top N `Recommendation`s, each with its `Job`, a score and a reason |
| `ReportStep` | `report` | `Recommendation`s | `Report`: where it is and a one-line summary |

## Responsibilities and neighbours

One responsibility per class. "Knows" is everything the class imports or calls; nothing else.

| Class | Pattern | Responsibility | Knows |
|---|---|---|---|
| `Cli` | Entry point | Turn the command line into a call; print the result; return the exit code | `AppFactory`, `JobRadarApp`, `RunResult` |
| `AppFactory` | Factory | Build the app for one command. The only class that knows concrete classes | all of them |
| `JobRadarApp` | | Launch the pipeline for one command and hand back how it ended | `Pipeline`, `RunResult` |
| `RunResult`, `RunSucceeded`, `RunFailed` | Polymorphism | Say how a run ended, in words and as an exit code | nothing |
| `Pipeline` | Pipeline | Run the steps in order; skip steps already saved; save each output; turn an error into `RunFailed` and the final `Report` into `RunSucceeded`; delete the checkpoints on success | `Step`, `Checkpoints`, `Report`, `RunResult` |
| `Step` | Interface | The shape every step shares | models |
| `Checkpoints` | Repository | Save and load each step's output for one run; record counts in the manifest; delete the outputs once the run succeeds | models |
| `RunStats` | Interface | Read-only: how many items each finished step produced | models |
| `FileCheckpoints` | Implements both | One JSON Lines file per step, plus `manifest.json`, in the run folder | its run folder |
| `FetchStep` | Step | Fetch raw pages from every configured job board | `JobBoardSource` |
| `JobBoardSource`, `GetroSource` | Adapter | Query one board's API, page by page | the board's API |
| `ConvertStep` | Step | Send each raw page to the parser for its board | `JobBoardParser` |
| `JobBoardParser`, `GetroParser` | Adapter | Turn one board's records into `Posting`s | the board's format |
| `DedupeStep` | Step | Group postings of the same job into one `Job` | `JobKey` |
| `JobKey` | | Decide which postings are the same job | `Posting` |
| `FilterStep` | Step | Keep the jobs that match every criterion set in the search | `Search` |
| `RecommendTopJobsStep` | Step | Keep the N best-scored jobs | `JobRanker`, `CandidateProfile` |
| `JobRanker`, `LlmRanker` | Strategy | Score jobs against the CV and preferences, in batches | `Llm` |
| `Llm`, `ClaudeCli` | Interface | Send one prompt to a language model; `ClaudeCli` runs `claude -p` on the subscription | `claude -p` |
| `ProfileLoader` | | Read the CV and preferences from `local/` into a `CandidateProfile` | `local/` |
| `ReportStep` | Step | Build the Markdown report: the funnel and the top N | `RunStats`, `ReportWriter` |
| `ReportWriter`, `FileReportWriter` | Interface | Store the finished report and say where it is | its run folder |
| `Clock` | | The current time, so tests can fix it | the system clock |
| Models | Immutable data | Passed between classes | nothing |

## One run

### From the command to the result

The pipeline's view: every step is a black box. The run folder is the only state.

```mermaid
sequenceDiagram
    autonumber
    actor U as You
    participant cli as Cli
    participant f as AppFactory
    participant app as JobRadarApp
    participant p as Pipeline
    participant s as each Step
    box rgba(255, 193, 7, 0.25) STATE: the run folder on disk
        participant cp as FileCheckpoints
    end

    U->>cli: job-radar run
    cli->>f: create()
    f->>f: load the profile, build the steps, FileCheckpoints and Pipeline
    f-->>cli: JobRadarApp
    cli->>app: run()
    app->>p: run()
    p->>cp: has(step), for each step
    cp-->>p: steps already done (none on a fresh run)
    opt resuming: some steps already done
        p->>cp: load(last done step)
        cp-->>p: its output, read from disk
    end
    loop each step not done yet, in order
        p->>s: run(data)
        s-->>p: output, passed on in memory as the next data
        p->>cp: save(step, output)
        Note right of cp: writes step.jsonl and adds its count to manifest.json
    end
    alt every step succeeded
        p->>cp: load(report)
        p->>cp: discard_all()
        p-->>app: RunSucceeded(location, summary)
    else a step raised an error
        p-->>app: RunFailed(step, reason)
        Note right of cp: all files stay, ready to resume
    end
    app-->>cli: RunResult
    cli-->>U: result.message(), exit with result.exit_code()
```

- `Cli` never checks which result it got; each result knows its own message and exit code
- A failed run keeps every saved step, so a later run can resume after the last one that finished
- Outputs pass between steps in memory; the disk is read only when resuming, since nothing is in memory yet

### Inside the steps

The same run, opening the black boxes. The save and load around each step (above) are left out.

```mermaid
sequenceDiagram
    autonumber
    participant p as Pipeline
    participant fetch as FetchStep
    participant gs as GetroSource
    participant conv as ConvertStep
    participant gp as GetroParser
    participant dd as DedupeStep
    participant fl as FilterStep
    participant rec as RecommendTopJobsStep
    participant rk as LlmRanker
    participant llm as ClaudeCli
    participant rep as ReportStep
    box rgba(255, 193, 7, 0.25) STATE: the run folder on disk
        participant cp as FileCheckpoints
        participant rw as FileReportWriter
    end

    p->>fetch: run(nothing)
    loop each job board
        fetch->>gs: fetch(search, window)
        gs-->>fetch: RawPages, paging through the API
    end
    fetch-->>p: RawPages
    p->>conv: run(RawPages)
    loop each page
        conv->>gp: parse(page)
        gp-->>conv: Postings
    end
    conv-->>p: Postings
    p->>dd: run(Postings)
    dd->>dd: group by JobKey.of(posting)
    dd-->>p: Jobs
    p->>fl: run(Jobs)
    fl->>fl: matches(job), against the Search
    fl-->>p: matching Jobs
    p->>rec: run(Jobs)
    rec->>rk: score(jobs, profile)
    loop each batch of jobs
        rk->>llm: complete(system, prompt)
        llm-->>rk: a score and reason per job, as JSON
    end
    rk-->>rec: Recommendations
    rec->>rec: keep the top N
    rec-->>p: top N Recommendations
    p->>rep: run(Recommendations)
    rep->>cp: funnel()
    cp-->>rep: count per finished step
    rep->>rw: write(markdown)
    rw-->>rep: location
    rep-->>p: Report(location, summary)
```

## The run folder

Each run gets its own folder, named by its start time:

```
output/runs/2026-11-05T10-00/
    fetch.jsonl  convert.jsonl  dedupe.jsonl  filter.jsonl  recommend.jsonl  report.jsonl
    manifest.json     # each finished step and how many items it produced
    report.md
```

After a successful run only `manifest.json` and `report.md` remain. After a failed run everything stays, ready to resume.
