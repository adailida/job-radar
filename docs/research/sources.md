# Data source research

Research done on 2026-10-16 to pick the MVP sources. Endpoints were called live that day unless marked otherwise. Prices and vendor claims are as published on that date.

## Source survey

| Source | Access | What comes back | Limits |
|---|---|---|---|
| Greenhouse | Public JSON per company, no key | Title, location, department, first published, full description (HTML) | Need the company's board name first |
| Lever | Public JSON per company, no key | Title, team, location, workplace type, country, full description (HTML and plain) | Same, per company |
| Ashby | Public JSON per company, no key | Title, team, location, remote flag, full description, **structured salary** (min, max, currency) | Same, per company |
| Workable | Public JSON per company, no key | Title, city/country, remote flag, industry, function | No description in the list call; per company |
| Remotive | Public JSON, no key | Title, company, tags, job type, required location, salary (text), full description | Remote only. 24h delay, max ~4 calls/day, attribution required, no republishing |
| RemoteOK | Public JSON, no key | Position, company, tags, location, salary min/max (often 0), description | Remote only. Attribution required |
| Himalayas | Public JSON, no key, cursor paging | Title, company, seniority, categories, location and timezone restrictions, salary (often empty), description | Remote only. ~126k jobs |
| We Work Remotely | RSS | Title, region, category, type, description | Remote only |
| HN "Who is hiring" | Public API (Algolia), monthly thread | Free-text comments, ~400 a month | Needs LLM parsing, no structure |
| USAJOBS | Free API key by request | Federal jobs, structured | Key required (401 without) |
| LinkedIn | No official API. Guest search HTML responds | Cards only (title, company, location) | Scraping is against its terms. Not for the MVP |
| Indeed | Public API retired (per third-party sources, date unconfirmed) | n/a | Not for the MVP |
| 80,000 Hours | No public API or RSS found. Email subscription exists (not tested) | n/a | Not for the MVP |

## Job boards

| Board | How it serves data | Scripted access |
|---|---|---|
| Fast Forward (jobs.ffwd.org) | Getro platform. Search API returns JSON: title, skills, salary, work mode, locations, and the link to the employer's own ATS. ~1,480 jobs | Yes. robots.txt allows all, crawl delay 1s. Page URLs don't paginate, the API does |
| 80,000 Hours | No public API found | Parked |
| Climatebase | Behind a Cloudflare bot challenge (403 to scripts) | No |
| LinkedIn | See the survey above | No |

- Boards link out to the employer's own ATS (on Fast Forward: Greenhouse, Ashby, iCIMS, Paylocity, own sites). Small orgs use Greenhouse and Ashby too, not only big companies
- So a board can serve as discovery: find the company, then pull its ATS feed for the full posting

## Fast Forward's API on Getro (checked 2026-11-05)

Found from the board's own page code; called live with a few requests, 1s apart.

- **Board id:** Getro network `997` (in the page's embedded data as `network.id`)
- **Search:** `POST https://api.getro.com/api/v2/collections/997/search/jobs`, body `{"hits_per_page": 200, "page": 0, "filters": "", "query": ""}`, header `Accept: application/json` (406 without it). No key. Returns `{"results": {"jobs": [...], "count": 1452}}`
- **Paging:** pages from 0, up to 200 jobs a page, so the whole board is about 8 pages
- **Order:** newest first by `created_at` (Unix time, UTC; the moment the job was listed on the board, equal to the job's `posted_at`). No date filter, so a run stops paging at the first page that reaches past its window: about 2 pages for 14 days
- **Fields per job:** id, slug, title, organization (name, slug, topics, industry tags, head count), locations (text list, 18% empty), location details with coordinates, `work_mode` (`on_site`, `remote` seen), compensation (min and max in cents, currency, period `year`/`month`/`hour`/`period_not_defined`, public flag), seniority, skills, url (the employer's own posting), source, `has_description`
- **Salary:** about 30% of jobs (57 of 200): mostly USD a year, some hourly, a few EUR, GBP and INR. When an amount is set, the currency and period are too
- **No description in search results.** It comes from `GET https://api.getro.com/api/v1/jobs/{slug}?collection_id=997` (HTML, about 3 in 4 jobs), one request per job, along with `posted_at`, status, employment types and job functions. The bare id works in place of the slug (checked 2026-11-06); a job that doesn't exist gets 404 `{"error": "Job not found"}`; a job with no description has `"description": null`. Fetched only for jobs that pass the filter (task 7a)

## Paid aggregators

| Aggregator | Price (pricing page, 2026-10-16) | Sources | Notes |
|---|---|---|---|
| JobsPipe | Free: 1,000 jobs once. Seeker plan $19.60/mo for 10,000 jobs | LinkedIn, Indeed, Greenhouse, Lever, Ashby, Workday, Workable, SmartRecruiters, Paylocity, Pinpoint and 4 more | Not: iCIMS, JazzHR, BambooHR, USAJOBS. No niche boards named. Salary filled ~47% (their docs) |
| TheirStack | $49/mo for 1,500 jobs | LinkedIn, Indeed, ATS (self-reported 300k+ sources) | Built for sales intelligence, ~5x JobsPipe per job |
| JSearch (Google for Jobs, RapidAPI) | ~$10 to $200/mo (vendor blogs, unverified) | Whatever Google for Jobs indexes | Might reach niche boards, untested |
| Coresignal | Enterprise | Largest dataset | Too expensive for this project |

JobsPipe billing (docs, verified 2026-10-16)
- 1 credit = 1 job returned, not tokens
- Empty results and repeats within the month are free
- `include_total_results: true` with `limit: 1` returns the match count for 1 credit, so market questions can run as counts

## Coverage test: JobsPipe vs Fast Forward

Method: pull all Fast Forward jobs through Getro (1,478 jobs, 228 orgs). Check which ATS each job links to. Then ask JobsPipe for each org's job count (1 credit if found, 0 if not) and compare. 118 credits used.

Where Fast Forward jobs are hosted

| Scope | On an ATS JobsPipe collects | On an ATS it doesn't | On own sites |
|---|---|---|---|
| Tech roles (218 jobs, 75 orgs) | 33% (Greenhouse 37, Ashby 29, LinkedIn 5) | 6% | 61% |
| All jobs (1,478 jobs, 228 orgs) | 27% | 7% | 66% |

These are floors: own-site jobs may also be on LinkedIn or Indeed, which JobsPipe collects.

Results
- Fast Forward orgs found in JobsPipe: 44% to 50% (101 to 116 of 228). It's a range because name matching is partial: 15 hits look like name collisions (Restor 4,705 jobs, Thorn 4,270)
- Fast Forward jobs matched: at most 39% (587 of 1,478)
- Biggest misses: small mission orgs on own sites, many non-US (Immigration Policy Lab, Talent Beyond Boundaries, Adalat AI, We Vote, BetaNYC, GovAI)
- No aggregator lists 80,000 Hours, Climatebase or Getro boards as sources
- Verdict: JobsPipe alone misses about half of mission orgs. It needs Fast Forward next to it

## Filter volumes (JobsPipe counts, 2026-10-16)

Measured to check that filtered fetches fit the Seeker budget (10,000 jobs/month). Counts use a 7-day posting window as an example: the run cadence is configurable, and what has to fit is the monthly total. The filters are examples too, not the final profile.

Cumulative funnel, US jobs posted in the last 7 days

| Layer (cumulative) | Jobs per 7 days |
|---|---|
| US, posted in last 7 days | 833,729 |
| + tech occupations (ISCO 25) | 52,218 |
| + no agencies or brokers | 45,282 |
| + remote only | 8,989 |
| + one seniority band | 5,324 |
| + ghost score ≤ 40 | 4,625 |
| + keyword list in description | 1,609 |

Narrowing a wide search (remote, US, no agencies, ghost score ≤ 40, keyword list, any occupation, any level)

| Narrowing | Jobs per 7 days |
|---|---|
| Baseline | 11,938 |
| + exclude unwanted title words | 9,293 |
| Stricter keyword list instead | 4,650 |
| + company ≤ 1,000 employees | 4,253 |
| + occupation groups (ISCO 21, 24, 25, 26) | 5,784 |
| All four combined | 631 |

(Each "+" row applies to the baseline alone, except the combined row.)

Findings
- Filtering server-side makes fetching every match affordable: the full funnel is ~1,600 per 7 days, roughly 6,900 a month. Without it, even one occupation group (52,218 per 7 days) is far over budget
- A wide search is too big to fetch whole. Options: counts plus a capped sample, or several narrowing filters combined
- A minimum-salary filter drops every posting without a salary (about half), so it can't run server-side
- Count queries cost 1 credit or nothing, so market questions are cheap. Example: US security-titled roles in the last 30 days: 4,316; of those mentioning CISSP: 1,523 (35%)
- A keyword list may miss orgs that don't use those words. Fast Forward covers part of that gap

Unchecked
- The "mid" seniority value returned only 131 jobs. The label is probably wrong; check the allowed values
- The employee-count filter probably drops companies of unknown size (`include_unknown` takes a list of field names, test later)

## Where jobs get posted

Research from 2026-10-16, mostly vendor and blog sources, so directional only.

- The employer's ATS or career page is the source of truth. LinkedIn and Indeed are mostly distribution: Greenhouse auto-posts free listings to Indeed and LinkedIn Limited Listings, and Indeed also indexes career pages and ATS feeds. Cross-posting is the default
- LinkedIn and Indeed lead employer adoption (all industries, ~28% and ~32%). LinkedIn is stronger for mid-senior tech
- Startups also use Wellfound, YC Work at a Startup and HN "Who is hiring" (backend, infra and AI roles are common). Remote-first startups may skip LinkedIn
- Impact-focused boards: Climatebase (the main climate hub), Tech Jobs for Good, Idealist (nonprofit, volunteering), 80,000 Hours, Fast Forward. Smaller: Climate People, ZeroHero
- Market: senior roles were 71% of the posting increase from May 2025 to May 2026 (Indeed Hiring Lab via CNBC); AI-titled roles are growing fastest; application volume per opening is way up; referrals are a large share of hires
- For this project: an ATS-level aggregator catches the original posting. The gap is LinkedIn-only posters (small orgs without an ATS) and nonprofits that post on their own sites

## Takeaways

- There are two kinds of source: per-company ATS feeds (rich, full text, need a company list) and aggregators (broad, keyword-searchable, terms vary)
- Every source has a different shape (location, salary, remote flag), so each needs its own adapter into one common posting format
- Full description text is available almost everywhere, and requirement and trend extraction depend on it
- Boards without open data are reached through an aggregator instead of email alerts or per-site setups

## Decision: MVP sources (2026-10-16)

1. **JobsPipe**: mainstream coverage (ATS feeds, LinkedIn, Indeed). Free credits for building, Seeker plan for scheduled runs
2. **Fast Forward via Getro**: mission orgs, free, scripted access allowed

Not in the MVP
- 80,000 Hours: no public API. Revisit only with their permission
- Climatebase: blocks scripts
- LinkedIn: no API, scraping is against its terms. Covered partly through JobsPipe
- Wellfound: no public API, not in JobsPipe's source list
- Email alerts and per-site setups: dropped
