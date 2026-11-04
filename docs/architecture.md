# Architecture

How the parts of job-radar connect, who owns what, and where state lives. The details behind each part are in [design.md](design.md).

These diagrams grow with the build: each PR that changes the flow updates them.

## Components

```mermaid
flowchart TB
    CLI["cli.main<br/>command line"]
    App["App<br/>built once, holds the configured parts"]
    Once["run_once<br/>one run's lifecycle"]
    Run["run()<br/>stages in order"]

    subgraph RunState["STATE: one run"]
        Writer["RunWriter<br/>this run's record"]
        Alerts["Alerts<br/>this run's warnings"]
    end

    subgraph Parts["Configured parts: stateless"]
        Inputs["InputLoader<br/>profile and CV"]
        Stages["Stages<br/>plan, fetch, dedupe, filter,<br/>classify, match, extract,<br/>trends, requirements, gaps, report"]
        Sources["Sources<br/>Getro, JobsPipe"]
        LLM["LLM<br/>claude -p"]
        Store["RunStore<br/>all runs on disk"]
        Prompter["Prompter<br/>questions in the terminal"]
        Renderer["Renderer<br/>Markdown"]
    end

    CLI -->|builds| App
    App -->|owns| Parts
    CLI -->|calls| Once
    Once -->|creates| Alerts
    Store -->|hands out| Writer
    Once -->|calls| Run
    Once -.->|preflight| Inputs
    Inputs -.-> Prompter
    Run -.->|reads earlier runs| Store
    Run -.->|calls| Stages
    Run -.->|saves each result| Writer
    Run -.-> Renderer
    Stages -.-> Sources
    Stages -.-> LLM
    Stages -.-> Prompter
    Stages -.->|warn| Alerts
    Sources -.->|raw pages| Writer

    style RunState fill:#ffc10733,stroke:#c79100
    classDef slice stroke:#2e7d32,stroke-width:4px
    class CLI,Once,Run,Sources,Store,Writer slice
```

- **Solid arrow**: creates or owns. **Dashed arrow**: calls
- **Yellow box**: the only state, and it lasts one run. Everything else is configured once and keeps nothing between calls
- **Thick green border**: built and running. Until the first slice is merged, it marks what that slice builds: `job-radar run` fetches Fast Forward, turns each record into a `Posting`, and saves the postings in a run folder

## One run

```mermaid
sequenceDiagram
    autonumber
    actor U as You
    participant CLI as cli.main
    participant Once as run_once
    participant Store as RunStore
    box rgba(255, 193, 7, 0.25) STATE, one run
        participant W as RunWriter
        participant A as Alerts
    end
    participant Run as run()
    participant St as Stages
    participant Ext as Sources, LLM, Prompter

    U->>CLI: job-radar run
    CLI->>Once: run_once(app)
    Once->>Ext: preflight, load profile and CV, check the LLM, ask for anything missing
    Once->>Store: start(run)
    Store-->>Once: RunWriter for this run
    Once->>A: create
    Once->>Run: run(user, writer, alerts)
    Run->>Store: read earlier runs
    Run->>St: plan and fetch
    St->>Ext: query sources, the cost check may ask you
    Ext->>W: raw pages as they arrive
    St-->>Run: postings
    Run->>W: save source results
    Run->>St: dedupe, filter, classify, match, extract
    St->>Ext: LLM calls
    St->>A: warnings
    St-->>Run: jobs, labels, requirements
    Run->>W: save jobs, labels, matches, requirements
    Run->>St: trends, gaps, build and render the report
    St-->>Run: report text
    Run->>W: save report
    Run-->>Once: done
    Once->>W: finish, completed
    Once-->>CLI: exit code
    CLI-->>U: summary and report path
```

- `run_once` opens and closes the run. On any error after step 4, it closes the run as failed instead
- `run()` is the only part that reads earlier runs from the store and writes through the writer
- Stages compute and return data; they hold no state and no reference to the writer or the alerts
