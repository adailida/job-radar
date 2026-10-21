# Requirements

## Purpose

Help someone find their next job, and understand the market they're searching in:

- Less manual browsing: openings that match the search come to the user
- A wider search: openings the user would not find on their own
- Market trends and expectations: what employers ask for, summarized and tracked over time, to guide CV changes, experience to gain and interview prep

## Users

Anyone looking for a new job, or considering one. Each user runs their own copy with their own inputs. Nothing about a specific user lives in the code or the repo.

## Inputs

- **Search settings**: the user's criteria (roles, locations, filters) and run settings, in `config.yaml`
- **CV**: the user's background, used to compare against what employers ask for

Both are personal and never committed. `config.example.yaml` shows the format.

## Capabilities

MVP
1. **Job search**: openings that match the user's search settings
2. **Market trends**: for the same criteria, how the market looks and how it changes over time (volume, seniority mix, salary, remote share)
3. **What employers ask for**: requirements extracted from postings, ranked by how often they appear (skills, tools, certifications, years of experience)
4. **Experience to gain**: frequent requirements compared with the CV, turned into suggestions for experience to get

After the MVP
5. **Adjacent roles**: openings in other domains or categories that fit the user's expertise
6. **Transition insights**: for an adjacent role, what carries over from the CV and what's missing. Inferred from requirement overlap between the CV and the role's postings, plus LLM reasoning. No source has data on real career moves, so these are suggestions, not measured outcomes

## Outputs

- **Report**: one per run, with a section for each MVP capability. Markdown by default. Openings are grouped by domain, job type, or both, as set in the config
- **Run data**: each run saves what it collected and derived, and later runs use it. The volume is small and nothing in it is critical
- **New data only**: by default a run covers only postings not seen in earlier runs, so duplicates and old postings are skipped and trends count each posting once. Configurable, so a run can also cover everything. A lookback cap (2 weeks by default, configurable) keeps a run from reaching far back when the last run was long ago
- **Problem alerts**: anything that goes wrong (no data, credits used up, a failing source) is reported in the terminal and at the top of the report
- **Format**: plain text an LLM can read. The report and run data formats sit behind a format layer, so either can change without touching the rest. The data model underneath is defined in `design.md`

Reports and run data live in `output/` and are never committed.

## Constraints

- **Sources**: only sources whose terms allow scripted access through an API. No scraping. MVP: JobsPipe and Fast Forward (Getro)
- **Cost**: paid sources charge per job returned (JobsPipe: 1 credit per job). The config names the user's plan, which sets the default spend limits: a monthly budget and a per-run maximum, both adjustable. A run checks the cost before spending, and never goes over either limit
- **LLM**: in the MVP, calls use the user's Claude subscription through Claude Code (`claude -p`), not per-token API billing. So only filtered postings go to the LLM, batched, with a small model. Per-token API billing may replace this later, so the way the LLM is called must be easy to swap
- **Cadence**: in the MVP the user starts each run, at whatever interval they like. Freshness is not critical
- **Where it runs**: locally in the MVP. Scheduled, fully automated cloud runs may come later
- **Stack**: Python 3.12+, uv, pytest, ruff

## Acceptance criteria

Job search
- A run fetches from JobsPipe and Fast Forward and keeps only the postings that match the search settings
- A job found in both sources appears once
- By default, the report lists every matching posting not seen in an earlier run: everything new since the user last checked. With the setting off, it lists all matching postings
- A run never looks further back than the lookback cap (2 weeks by default, configurable). When the last run is older than the cap, the report says so and which dates it covers
- Each job in the report shows title, company, location or remote, salary if posted, source, and a link to the posting
- Openings are grouped by the configured grouping (domain, job type, or both). Group names come from the config, and a posting that fits none goes under "Other"

Market trends
- The report shows, for the search criteria: number of new postings, seniority mix, salary range where posted, and remote share
- Trends are aggregated by period, a month by default (configurable). Each posting counts toward the period of its posting date (the date a run first saw it, when the posting date is missing). So one run can add to several periods, and how often the user runs doesn't change the figures
- A later run can still add postings to an earlier period (a posting dated last month but found only now). The current period is marked as partial
- Each figure is compared with earlier periods. When there are none yet, the report says there's nothing to compare

What employers ask for
- The report lists the top requirements (how many is configurable), grouped by type: skills, tools, certifications, years. Each shows the share of postings that mention it
- Each requirement can be traced back to the postings it came from, through the run data

Experience to gain
- The report lists frequent requirements the CV doesn't cover, most frequent first, each with its share of postings. Requirements the CV already covers are shown as covered

Runs
- Each run writes one report and saves its run data in `output/`. The next run reads that data
- Before fetching from a paid source, a run asks it for the match count (JobsPipe: 1 credit) to estimate the cost of the full fetch
- If the estimate is over the per-run maximum or what's left of the monthly budget, the run stops before spending anything and alerts, showing the estimate and both limits, so the user can narrow the search or raise a limit
- Credits spent are tracked across runs, so the monthly budget holds whatever the number of runs
- Only filtered postings go to the LLM, in batches
- Tests run offline, with no network and no credits spent

Problem alerts (in the terminal and at the top of the report)
- Errors stop the run with a clear message: missing or invalid config or CV, no source reachable, LLM not available, search too expensive for the limits
- Warnings let the run finish: a source failed or returned nothing, no new postings after filtering, credit budget reached, credits running low (threshold configurable), LLM failed on some postings

## Non-goals

For the MVP. Any of these may be revisited later.

- Applying to jobs or contacting employers
- Rewriting the CV: it suggests what to change or gain, but doesn't produce a tailored CV
- Job-board email alerts as a source, per-site setups, or scraping sites whose terms forbid it (LinkedIn, for example)
- Real-time job alerts: new openings show up in the next run
- A hosted service or user accounts: each user runs their own copy
- A UI beyond the report: no web app or dashboard
