# Requirements

## Purpose

Help someone find their next job, and understand the market they're searching in:

- Less manual browsing: openings that match the search come to the user
- A wider search: openings the user would not find on their own
- Market trends and expectations: what employers ask for, summarized and tracked over time, to guide CV changes, experience to gain and interview prep

## Users

Anyone looking for a new job, or considering one. Each user runs their own copy. The code is generic: everything about the person comes from their user input.

## Inputs

Two kinds, kept separate:

- **User input**: what's specific to the person. It comes from a file, or the user enters it in the terminal
  - **CV**: their background, compared against what employers ask for
  - **Search criteria**: roles, locations, filters
- **Settings**: how runs work, the same for most users. For example: source plans and spend limits, lookback cap, trend period, report grouping, output formats, alert thresholds. Every setting has a default, so a new user only has to provide their user input

Example files show the format of each.

## Capabilities

MVP
1. **Job search**: openings that match the user's search criteria
2. **Market trends**: for the same criteria, how the market looks and how it changes over time (volume, seniority mix, salary, remote share)
3. **What employers ask for**: requirements extracted from postings, ranked by how often they appear (skills, tools, certifications, years of experience)
4. **Experience to gain**: frequent requirements compared with the CV, turned into suggestions for experience to get

After the MVP
5. **Adjacent roles**: openings in other domains or categories that fit the user's expertise
6. **Transition insights**: for an adjacent role, what carries over from the CV and what's missing. Inferred from requirement overlap between the CV and the role's postings, plus LLM reasoning. No source has data on real career moves, so these are suggestions, not measured outcomes

## Outputs

- **Report**: one per run, with a section for each MVP capability. Openings are grouped by domain, job type, or both, as set in the settings
- **Run data**: each run saves what it collected and derived, and later runs use it. The volume is small and nothing in it is critical
- **New data only**: by default a run covers only postings not seen in earlier runs, so duplicates and old postings are skipped and trends count each posting once. A setting turns this off so a run covers everything. A lookback cap (2 weeks by default) keeps a run from reaching far back when the last run was long ago
- **Deleting runs**: a failed run never counts: it doesn't mark postings as seen or add to trends, and is kept for inspection and to resume until deleted. Any run can also be deleted by hand. Deleting asks for confirmation first
- **Problem alerts**: anything that goes wrong (no data, credits used up, a failing source) is reported in the terminal and at the top of the report
- **Format**: plain text that both people and an LLM can read. The report is Markdown by default. The report and run data formats sit behind a format layer, so either can change without touching the rest. The data model underneath is defined in `design.md`

## Constraints

- **Sources**: only sources whose terms allow scripted access through an API. No scraping. MVP: JobsPipe and Fast Forward (Getro)
- **Adding sources**: more sources can be plugged in later without changing the rest. Each source's integration is declarative (settings) where possible, otherwise in its own module. Everything specific to a source stays inside its integration, including how it reports credits left and used
- **Cost**: paid sources charge per job returned (JobsPipe: 1 credit per job). The settings name the plan for each paid source, which sets the default limits: a monthly budget and a per-run maximum, both adjustable. A run estimates the cost before spending and checks it against the limits and the credits left
- **LLM**: in the MVP, calls use the user's Claude subscription through Claude Code (`claude -p`), not per-token API billing. So only filtered postings go to the LLM, batched, with a small model. Per-token API billing may replace this later, so the way the LLM is called must be easy to swap
- **Cadence**: in the MVP the user starts each run, at whatever interval they like. Freshness is not critical
- **Where it runs**: locally in the terminal in the MVP, and runs are interactive: the user can enter their user input, and confirms spending over a limit and deleting runs. Scheduled, fully automated cloud runs may come later
- **Stack**: Python 3.12+, uv, pytest, ruff

## Acceptance criteria

Job search
- A run fetches from JobsPipe and Fast Forward and keeps only the postings that match the search criteria
- A job found in both sources appears once
- By default, the report lists every matching posting not seen in an earlier run: everything new since the user last checked. With the setting off, it lists all matching postings
- A run never looks further back than the lookback cap (2 weeks by default). When the last run is older than the cap, the report says so and which dates it covers
- Each job in the report shows title, company, location or remote, salary if posted, source, and a link to the posting
- Openings are grouped by the grouping in the settings (domain, job type, or both). Group names come from the settings, and a posting that fits none goes under "Other"

Market trends
- The report shows, for the search criteria: number of new postings, seniority mix, salary range where posted, and remote share
- Trends are aggregated by period, a month by default. Each posting counts toward the period of its posting date (the date a run first saw it, when the posting date is missing). So one run can add to several periods, and how often the user runs doesn't change the figures
- A later run can still add postings to an earlier period (a posting dated last month but found only now). The current period is marked as partial
- Each figure is compared with earlier periods. When there are none yet, the report says there's nothing to compare
- Each run records the search criteria and sources it used. If they changed within the periods being compared, the trends are kept (not reset), and the report notes when the change happened and what changed, so figures before and after it aren't read as like for like
- Figures are also broken down by sector, domain and similar dimensions, inferred from the postings in the run rather than set in the settings. This breakdown is informational

What employers ask for
- The report lists the top requirements (how many is a setting), grouped by type: skills, tools, certifications, years. Each shows the share of postings that mention it
- Each requirement can be traced back to the postings it came from, through the run data

Experience to gain
- The report lists frequent requirements the CV doesn't cover, most frequent first, each with its share of postings. Requirements the CV already covers are shown as covered

Cost
- Before fetching from a paid source, a run gets the credits left from the source's API, and asks for the match count (JobsPipe: 1 credit) to estimate the cost of the full fetch
- Within the limits, the run shows the estimate and goes ahead
- Over the per-run maximum or the monthly budget, the run shows the estimate, both limits and the credits left, and asks the user whether to go ahead, skip that source for this run, or stop
- A fetch is never partial: a source is fetched in full or not at all, so trends can rely on complete data
- Monthly spend comes from the source's own credit data, so the budget holds whatever the number of runs

Runs
- Each run writes one report and saves its run data. The next run reads that data
- When a run fails, it asks whether to delete its data. Kept or deleted, a failed run doesn't count toward seen postings, trends or the next run's time window
- The user can delete any earlier run, after a confirmation prompt. Its postings count as unseen again, and its data drops out of the trends
- Only filtered postings go to the LLM, in batches
- A new source can be added with its own settings and, if needed, its own module, without changes to filtering, extraction or the report. Tests use a fake source added the same way
- Tests run offline, with no network and no credits spent

Problem alerts (in the terminal and at the top of the report)
- Errors stop the run with a clear message: invalid settings, user input still missing or invalid after the terminal prompt, no source reachable, LLM not available
- Warnings let the run finish: a source failed or returned nothing, no new postings after filtering, credit budget reached, credits running low (threshold is a setting), LLM failed on some postings

## Non-goals

For the MVP. Any of these may be revisited later.

- Applying to jobs or contacting employers
- Rewriting the CV: it suggests what to change or gain, but doesn't produce a tailored CV
- Job-board email alerts as a source, or scraping sites whose terms forbid it (LinkedIn, for example)
- Real-time job alerts: new openings show up in the next run
- A hosted service or user accounts: each user runs their own copy
- A UI beyond the report and terminal prompts: no web app or dashboard
