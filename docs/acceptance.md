# Acceptance

Every acceptance criterion in [requirements.md](requirements.md), grouped as there, with the tests that prove it and a status. Written in task 25 (the acceptance pass), Nov 10.

Statuses:

- **passing**: the tests listed exist and pass
- **gap**: not built yet; one line says what's missing
- **decided by the owner**: the build differs from the wording on purpose, by a decision in [design.md](design.md)
- **deferred (owner, Nov 10)**: moved to "After the MVP" in requirements.md

Tests are written `file::test name`, all under `tests/`. Check them with `uv run pytest -q` (offline; live checks are opt-in with `-m live` and none is needed here).

## Summary

| Group | Criteria | Passing | Gap | Decided by the owner |
|---|---|---|---|---|
| Job search | 6 | 6 | 0 | 0 |
| Market trends | 6 | 5 | 1 | 0 |
| What employers ask for | 2 | 2 | 0 | 0 |
| Experience to gain | 1 | 1 | 0 | 0 |
| Cost | 5 | 5 | 0 | 0 |
| Runs | 6 | 5 | 0 | 1 |
| Problem alerts | 2 | 2 | 0 | 0 |
| **MVP total** | **28** | **26** | **1** | **1** |
| After the MVP | 2 | | | deferred (owner, Nov 10) |

## Job search

1. **A run fetches from JobsPipe and Fast Forward and keeps only the postings that match the search criteria.** Passing. JobsPipe is off by default (`sources.jobspipe.enabled`) until its limited first runs in task 26
   - `test_jobspipe.py::test_a_run_fetches_from_jobspipe_and_fast_forward`
   - `test_steps.py::test_fetch_takes_pages_from_every_board_in_order`
   - `test_filter.py::test_a_run_keeps_only_postings_that_match_the_search_criteria`
   - `test_filter.py::test_a_job_matching_any_search_is_kept`
   - `test_classify.py::test_the_match_step_keeps_jobs_that_match_any_search`
2. **A job found in both sources appears once.** Passing
   - `test_dedupe.py::test_a_job_found_in_both_sources_appears_once`
   - `test_dedupe.py::test_two_postings_of_one_job_become_one_job`
   - `test_dedupe.py::test_postings_linking_to_one_ats_opening_merge_whatever_their_titles`
3. **By default, the report lists every matching posting not seen in an earlier run; with the setting off, all matching postings.** Passing
   - `test_cli.py::test_the_report_lists_every_matching_posting_not_seen_in_an_earlier_run`
   - `test_cli.py::test_with_new_only_off_a_second_run_sees_every_job_again`
   - `test_seen.py::test_the_step_drops_jobs_with_any_seen_key`
   - `test_seen.py::test_with_new_only_off_every_job_passes`
   - `test_report.py::test_the_report_lists_every_new_matching_job_by_group`
4. **A run never looks further back than the lookback cap (2 weeks by default), for any source; when a source was last covered before the cap, the report says so and which dates it covers.** Passing. Reworded Nov 11 for per-source windows (owner to confirm)
   - `test_window.py::test_run_never_reaches_further_back_than_the_lookback`
   - `test_window.py::test_capped_run_asks_and_says_why`
   - `test_window.py::test_a_capped_run_names_the_days_it_leaves_out`
   - `test_window.py::test_catching_up_never_reaches_further_back_than_the_lookback`
   - `test_window.py::test_a_source_last_covered_before_the_lookback_says_which_days_it_leaves_out`
   - `test_cli.py::test_a_run_after_a_long_break_says_in_the_report_which_days_it_missed`
   - `test_report.py::test_a_long_break_is_noted_with_the_days_left_out`
   - `test_report.py::test_a_source_new_or_cut_by_the_lookback_says_so_in_the_header`
5. **Each job in the report shows title, company, location or remote, salary if posted, source, and a link to the posting.** Passing
   - `test_report.py::test_each_job_shows_title_company_location_or_remote_salary_if_posted_source_and_link`
   - `test_report.py::test_markdown_report_matches_the_golden_file`
   - `test_report.py::test_links_carry_the_source_name_for_people`
6. **Openings are grouped by the grouping in the settings (domain, job type, or both); group names come from the settings, and a posting that fits none goes under "Other".** Passing
   - `test_openings.py::test_openings_are_grouped_by_the_grouping_in_the_settings_and_other_goes_last`
   - `test_openings.py::test_grouped_by_both_each_job_type_holds_its_domains`
   - `test_cli.py::test_new_openings_are_grouped_as_the_settings_say`
   - `test_settings.py::test_new_openings_can_be_grouped_by_job_type_domain_or_both`

## Market trends

1. **The report shows, for the search criteria: number of new postings, seniority mix, salary range where posted, and remote share.** Passing
   - `test_trends.py::test_the_trends_section_renders_periods_change_notes_and_low_samples`
   - `test_trends.py::test_coverage_marks_partial_periods_and_postings_count_per_covered_day`
   - `test_trends.py::test_seniority_mix_leaves_out_unknown_and_unlabelled_jobs`
   - `test_trends.py::test_salary_quartiles_from_yearly_usd_midpoints`
   - `test_trends.py::test_work_mode_shares_leave_out_jobs_that_dont_say`
   - `test_cli.py::test_a_demo_run_reports_market_trends`
2. **Trends are aggregated by period, a month by default; each posting counts toward the period of its posting date (first seen when missing), so one run can add to several periods, and how often the user runs doesn't change the figures.** Passing
   - `test_trends.py::test_one_run_adds_to_each_period_its_postings_are_dated_in`
   - `test_trends.py::test_how_often_the_user_runs_doesnt_change_the_figures`
   - `test_trends.py::test_a_job_counts_on_its_earliest_posted_date_else_when_first_seen`
   - `test_trends.py::test_a_job_found_by_two_runs_counts_once`
   - `test_trends.py::test_periods`
   - `test_cli.py::test_a_demo_run_reports_market_trends` (by month with the default settings)
3. **A later run can still add postings to an earlier period; the current period is marked as partial.** Passing
   - `test_trends.py::test_a_later_run_can_still_add_postings_to_an_earlier_period_and_the_current_is_partial`
   - `test_trends.py::test_coverage_marks_partial_periods_and_postings_count_per_covered_day`
4. **Each figure is compared with earlier periods; with none yet, the report says there's nothing to compare.** Passing
   - `test_trends.py::test_the_latest_period_is_compared_with_the_last_complete_one`
   - `test_trends.py::test_nothing_to_compare_without_a_complete_period_before_the_latest`
   - `test_trends.py::test_a_single_period_says_there_is_nothing_to_compare`
5. **Each run records the search criteria and sources it used; when they changed within the periods compared, trends are kept and the report notes when and what changed.** Passing
   - `test_trends.py::test_the_manifest_keeps_the_runs_config_and_history_reads_it`
   - `test_trends.py::test_changes_to_sources_and_searches_are_noted_from_the_first_period_shown`
   - `test_trends.py::test_a_change_before_the_periods_shown_is_not_noted`
   - `test_trends.py::test_the_trends_section_renders_periods_change_notes_and_low_samples`
6. **Figures are also broken down by sector, domain and similar dimensions, inferred from the postings; informational.** Gap: the labels exist (classify gives sector, domain and job type for every job), but the trends section has no breakdown yet; design.md section 10 "Breakdowns" describes it (share of the top 10 values of each, current period against the previous one, sector labels cleaned up like requirement names)

## What employers ask for

1. **The report lists the top requirements (how many is a setting), grouped by type (skills, tools, certifications, years), each with the share of postings that mention it.** Passing
   - `test_asks.py::test_the_report_lists_the_top_requirements_grouped_by_type_with_their_share`
   - `test_asks.py::test_the_section_shows_a_table_per_type_with_share_and_change`
   - `test_cli.py::test_how_many_requirements_the_report_lists_is_a_setting`
2. **Each requirement can be traced back to the postings it came from, through the run data.** Passing
   - `test_asks.py::test_each_requirement_can_be_traced_back_to_the_postings_it_came_from`
   - `test_extract.py::test_a_completed_run_keeps_the_extracted_jobs`

## Experience to gain

1. **The report lists frequent requirements the CV doesn't cover, most frequent first, each with its share of postings; those the CV covers are shown as covered.** Passing
   - `test_gaps.py::test_the_report_lists_frequent_requirements_the_cv_doesnt_cover_with_their_share`
   - `test_gaps.py::test_gaps_come_first_most_asked_first_then_the_covered_ones`
   - `test_cli.py::test_a_demo_run_reports_experience_to_gain`

## Cost

1. **Before fetching from a paid source, a run gets the credits left from the source's API and the match count to estimate the cost of the full fetch.** Passing. The estimate comes from JobsPipe's free estimate call, not count queries at 1 credit each (design.md section 12, task 17), so planning costs nothing
   - `test_jobspipe.py::test_plan_adds_up_free_estimates_and_reads_the_credits`
   - `test_jobspipe.py::test_when_jobspipe_cant_count_the_estimate_is_the_ask_above_limit`
2. **Within the limits, the run shows the estimate and goes ahead.** Passing
   - `test_cost.py::test_within_every_limit_it_goes_ahead_with_ten_percent_to_spare`
   - `test_cost.py::test_an_estimate_jobspipe_couldnt_count_says_at_most`
3. **Over the per-run ask-above limit or the monthly budget, the run shows the estimate, both limits and the credits left, and asks: go ahead, skip that source, or stop.** Passing
   - `test_cost.py::test_over_a_limit_the_run_shows_the_estimate_both_limits_and_the_credits_left_and_asks`
   - `test_cost.py::test_over_the_ask_above_limit_the_user_chooses`
   - `test_cost.py::test_over_the_budget_left_the_user_chooses`
   - `test_cost.py::test_stopping_stops_the_run`
   - `test_cost.py::test_over_the_credits_left_only_skip_or_stop`
   - `test_resume.py::test_stopping_at_the_cost_check_builds_no_run`
4. **A fetch is never partial: a source is fetched in full or not at all.** Passing, after a fix in this task: a JobsPipe fetch that reached its cap kept the jobs it had; now it fails as a whole and the run warns that JobsPipe failed (design.md section 12, "During the fetch"). After the MVP, reaching the cap first asks to keep going; no (or no credits left) fails it as a whole, as before
   - `test_jobspipe.py::test_a_fetch_is_never_partial`
   - `test_jobspipe.py::test_a_search_the_cap_leaves_unasked_asks_too`
   - `test_jobspipe.py::test_keep_going_never_goes_past_the_credits_left`
   - `test_jobspipe.py::test_keep_going_with_no_one_to_answer_means_no`
   - `test_getro.py::test_fetch_fails_as_a_whole_when_a_later_page_fails`
   - `test_warnings.py::test_warnings_let_the_run_finish_when_a_source_failed`
5. **Monthly spend comes from the source's own credit data, so the budget holds whatever the number of runs.** Passing
   - `test_jobspipe.py::test_a_monthly_budget_is_what_the_month_has_left`

## Runs

1. **Each run writes one report and saves its run data; the next run reads that data.** Passing
   - `test_cli.py::test_each_run_writes_one_report_and_saves_its_run_data`
   - `test_cli.py::test_next_run_fetches_since_the_last_one_without_asking`
   - `test_checkpoints.py::test_complete_keeps_manifest_and_report`
2. **When a run fails, nothing is asked: the next run offers to resume it, and `job-radar delete` removes it; kept or deleted, a failed run doesn't count toward seen postings, trends or the next run's time windows; nor does a source that failed, was skipped or came back empty although its count found jobs (or, for a paid source, couldn't count), so the next run fetches its dates again.** Decided by the owner: the criterion used to say a failed run asks whether to delete its data; requirements.md was reworded on Nov 10 to match the decision (design.md decisions: "The next run offers to resume a failed run; nothing is asked when it fails"). Reworded again Nov 11 for per-source coverage (owner to confirm). The rest is passing
   - `test_history.py::test_failed_run_doesnt_count_toward_the_next_window`
   - `test_history.py::test_a_failed_run_covers_no_source`
   - `test_history.py::test_a_source_counts_as_covered_only_by_the_runs_that_covered_it`
   - `test_history.py::test_deleting_a_run_drops_its_coverage`
   - `test_cost.py::test_a_source_that_failed_is_not_covered`
   - `test_cost.py::test_a_source_skipped_or_failed_at_the_cost_check_is_not_covered`
   - `test_cost.py::test_a_source_empty_although_its_count_found_jobs_is_not_covered_and_says_so`
   - `test_cost.py::test_a_paid_source_empty_that_couldnt_count_is_not_covered_and_says_so`
   - `test_cost.py::test_a_source_genuinely_empty_is_covered`
   - `test_window.py::test_each_source_gets_its_own_window_from_where_it_was_last_covered`
   - `test_seen.py::test_a_failed_runs_jobs_are_not_seen`
   - `test_trends.py::test_a_failed_run_doesnt_count_toward_the_trends`
   - `test_cli.py::test_a_failed_demo_run_is_resumed_by_the_same_command`
   - `test_resume.py::test_offers_the_newest_run_when_it_failed`
3. **The user can delete any earlier run, after a confirmation prompt; its postings count as unseen again, and its data drops out of the trends.** Passing
   - `test_cli.py::test_a_deleted_runs_postings_count_as_unseen_again_and_its_data_drops_out_of_the_trends`
   - `test_runs_command.py::test_delete_asks_about_the_run_then_deletes_it`
   - `test_runs_command.py::test_saying_no_deletes_nothing`
   - `test_runs_command.py::test_delete_all_asks_once_for_every_run`
   - `test_history.py::test_run_folders_delete_one_run_and_nothing_else`
4. **Only filtered postings go to the LLM, in batches.** Passing
   - `test_ranking.py::test_only_filtered_postings_go_to_the_llm_in_batches`
   - `test_classify.py::test_batches_go_a_set_number_at_a_time`
   - `test_extract.py::test_jobs_go_a_set_number_to_a_prompt`
   - `test_cli.py::test_new_source_plugs_in_without_changes_downstream` (the funnel: filter before classify, extract and recommend)
5. **A new source can be added with its own settings and, if needed, its own module, without changes to filtering, extraction or the report; tests use a fake source added the same way.** Passing
   - `test_cli.py::test_new_source_plugs_in_without_changes_downstream`
   - `test_skeleton.py::test_class_satisfies_its_interface`
6. **Tests run offline, with no network and no credits spent.** Passing: sockets are blocked in every test; live checks run only with `-m live`
   - `test_setup.py::test_tests_run_offline`

## Problem alerts

Errors stop the run before or during it and are told in the terminal; a stopped run writes no report (design.md section 13, "Failed run"), so only warnings reach the report's Alerts.

1. **Errors stop the run with a clear message: invalid settings, user input missing or invalid, no source reachable, LLM not available.** Passing
   - Invalid settings: `test_errors.py::test_errors_stop_the_run_with_a_clear_message_for_invalid_settings`, `test_settings.py::test_a_bad_settings_file_stops_the_command_as_a_setup_error`
   - User input missing or invalid: `test_errors.py::test_errors_stop_the_run_with_a_clear_message_for_invalid_user_input`, `test_errors.py::test_an_unreadable_cv_names_the_file_and_the_fix`, `test_profile.py::test_missing_cv_is_a_setup_error`, `test_searches.py::test_no_file_is_an_error_pointing_at_the_example`
   - No source reachable: `test_warnings.py::test_errors_stop_the_run_with_a_clear_message_when_no_source_is_reachable`, `test_warnings.py::test_a_demo_run_with_its_only_board_down_fails_with_no_source`
   - LLM not available: `test_errors.py::test_errors_stop_the_run_with_a_clear_message_when_the_llm_is_not_available`
2. **Warnings let the run finish, in the terminal and at the top of the report: a source failed or returned nothing, no new postings after filtering, credit budget reached, credits running low (threshold is a setting), LLM failed on some postings.** Passing
   - A source failed: `test_warnings.py::test_warnings_let_the_run_finish_when_a_source_failed`
   - A source returned nothing: `test_warnings.py::test_warnings_let_the_run_finish_when_a_source_returned_nothing`, `test_warnings.py::test_a_board_whose_pages_hold_no_postings_is_a_warning`
   - No new postings after filtering: `test_warnings.py::test_warnings_let_the_run_finish_when_no_new_postings_matched`
   - Credit budget reached: `test_warnings.py::test_warnings_let_the_run_finish_when_the_credit_budget_is_reached`
   - Credits running low: `test_warnings.py::test_warnings_let_the_run_finish_when_credits_run_low`, `test_warnings.py::test_low_credits_is_a_setting_of_100_by_default`
   - LLM failed on some postings: `test_warnings.py::test_warnings_let_the_run_finish_when_the_llm_failed_on_some_postings`
   - In the terminal and at the top of the report: `test_warnings.py::test_the_runs_warnings_are_the_reports_alerts_and_the_terminals`, `test_report.py::test_alerts_are_listed_at_the_top`, `test_warnings.py::test_a_demo_run_shows_its_warnings_in_the_report_and_the_terminal`

## After the MVP

Deferred (owner, Nov 10); requirements.md lists them under "After the MVP".

1. **Keywords: a search can require the description to mention any of its keywords** (task 11c). Deferred (owner, Nov 10). Building it would take: a `keywords` criterion in `Search` and `profile.yaml`, checked by `JobMatcher` in a step after describe (descriptions aren't there when the filter runs), dropped jobs added to `dropped.md`, and JobsPipe's query sending the keywords
2. **Terminal prompts: a run asks for user input that is missing or invalid, and errors only if it is still missing or invalid after that** (task 12). Deferred (owner, Nov 10). Building it would take: `Prompter.ask` for free text, a prompt for each missing or invalid profile field (and a missing CV or preferences file) before the setup error, and the answers saved back to `config_local/` so the next run doesn't ask again

## Non-goals

Re-checked against requirements.md on Nov 10: nothing built contradicts them.

- **Applying to jobs or contacting employers**: nothing applies or contacts; the report only links to postings
- **Rewriting the CV**: "Experience to gain" judges and suggests; nothing writes a CV
- **Job-board email alerts as a source, or scraping**: both sources are APIs that allow scripted access (Fast Forward's Getro search API, robots.txt allowing it, 1s between requests; JobsPipe's paid API); no email or HTML scraping
- **Real-time job alerts**: the user starts each run; nothing runs in the background or notifies
- **A hosted service or user accounts**: everything runs locally from the user's own copy and `config_local/` folder
- **A UI beyond the report and terminal prompts**: the outputs are `report.md`, `dropped.md` and terminal lines
