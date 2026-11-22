import ast
import re
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[1]

# A test file is named for what it covers, never for when it was added (docs/testing.md rule 9).
SUFFIXED = re.compile(r"_(more|extra|again)(_|$)|_(phase_?)?\d+[a-z]?$")

# Files still waiting for their slice (9v), which deletes these lines.
PENDING = {
    "unit/test_ollama_more.py",
    "unit/test_plan_more.py",
    "unit/test_points_more.py",
    "unit/test_policy_more.py",
    "unit/test_private_more.py",
    "unit/test_registry_more.py",
    "unit/test_reports_more.py",
    "unit/test_reports_phase_more.py",
    "unit/test_route_more.py",
    "unit/test_rules_more.py",
    "unit/test_shared_rules_more.py",
    "unit/test_store_more.py",
    "unit/test_tags_more.py",
    "unit/test_tool_check_more.py",
    "unit/test_web_handlers_more.py",
    "unit/test_web_jobs_lifecycle_more.py",
}

# Where the tests of each folded file live now, and every test function the file holds.
MOVED = {
    "e2e/test_cli_approvals.py": {
        "test_nothing_pending",
        "test_the_pending_list",
        "test_show_a_pending_request",
        "test_show_a_decided_request",
        "test_approve_asks_first",
        "test_approve_can_be_declined",
        "test_approve_with_yes_and_reject_do_not_ask",
        "test_an_edit_shows_the_new_arguments_before_asking",
        "test_an_edit_that_does_not_fit",
        "test_edit_arguments_must_be_a_json_object",
        "test_errors",
        "test_an_action_that_is_not_registered",
        "test_show_json_includes_an_answer",
        "test_a_declined_retry_records_nothing",
        "test_a_declined_edit_records_nothing",
        "test_infinity_is_refused_and_an_empty_object_is_judged",
        "test_a_bad_decided_by_prints_the_settings_error",
        "test_an_approval_without_a_note_shows_who_approved",
        "test_a_cancellation_without_a_note_shows_who_cancelled",
    },
    "e2e/test_cli_ask.py": {
        "test_a_read_only_request_is_answered",
        "test_each_decision_resumes_the_run",
        "test_a_rejection_ends_the_run",
        "test_no_resume_only_records_and_resume_continues",
        "test_an_escalation_and_its_answers",
        "test_json_output",
        "test_a_busy_run_keeps_the_decision_and_says_why",
        "test_errors",
        "test_a_finished_run_is_not_resumed",
        "test_a_run_stopped_at_a_model_call_is_resumed",
        "test_resume_json_of_a_waiting_run_and_a_bad_demo_setting",
        "test_stopped_plain_rejection_and_escalation_problems",
        "test_an_edit_resumes_with_the_new_arguments_and_a_decline_waits",
        "test_retry_without_resume_and_cancel_that_resumes",
        "test_a_busy_reject_keeps_the_rejection",
        "test_a_request_of_2001_characters_is_refused",
    },
    "e2e/test_cli_doctor_not_writable.py": {
        "test_an_open_folder_that_cannot_be_written_says_not_writable",
        "test_a_data_path_under_a_file_says_not_writable",
    },
    "e2e/test_cli_tool_check_commands.py": {
        "test_registered_appends_the_demo_domain_only_when_asked",
        "test_open_runtime_starts_nothing_and_ask_lists_tools_once",
        "test_resume_and_retry_print_the_failed_check",
        "test_cancel_without_resuming_starts_no_server",
        "test_an_unset_command_fails_the_doctor",
        "test_two_problems_count_as_two_failed_checks",
        "test_a_server_with_no_tool_action_reports_zero_actions",
    },
    "e2e/test_cli_decide_without_asking.py": {
        "test_bad_edit_args_open_no_runtime",
        "test_reject_decides_without_asking",
        "test_cancel_decides_without_asking",
    },
    "e2e/test_web_resume.py": {
        "test_the_button_shows_only_when_a_resume_can_start",
        "test_a_resume_post_starts_the_run_and_records_nothing",
        "test_a_post_that_cannot_start_only_redirects",
        "test_a_post_is_checked_like_every_form",
        "test_the_recorded_failure_is_shown",
        "test_a_record_followed_by_a_success_is_not_shown",
        "test_a_store_that_fails_hides_the_button_and_refuses_the_post",
        "test_an_answered_escalation_shows_the_button_and_an_open_one_does_not",
        "test_a_missing_or_unreadable_state_is_refused",
        "test_a_broken_log_and_a_non_text_type_show_no_failure",
        "test_an_empty_log_and_a_different_error_show_no_failure",
        "test_a_busy_run_keeps_the_record_off_the_page",
    },
    "integration/test_mcp_client.py": {
        "test_the_tools_of_a_server",
        "test_a_call_and_a_failed_call",
        "test_the_server_sees_only_safe_and_declared_variables",
        "test_the_server_log_is_private_and_appended",
        "test_a_server_without_a_command_line",
        "test_a_command_that_cannot_start",
        "test_a_server_that_stops",
        "test_a_server_that_takes_too_long_is_ended",
        "test_the_sdk_and_no_telemetry",
        "test_two_calls_start_two_processes_and_a_thread_can_call",
        "test_a_declared_variable_that_is_unset_stays_unset",
        "test_an_existing_log_folder_keeps_its_mode",
        "test_a_string_result_is_structured",
        "test_a_program_that_is_not_executable_fails_to_start",
        "test_an_unexpected_session_error_passes_through",
        "test_a_bare_connection_error_is_closed",
        "test_a_closed_connection_and_a_mixed_group",
    },
    "integration/test_runtime.py": {
        "test_the_settings",
        "test_the_demo_setting_is_true_or_false",
        "test_without_the_demo_setting_no_domain_is_registered",
        "test_a_run_survives_a_restart_in_private_files",
        "test_the_demo_runner",
        "test_a_busy_run_is_refused",
        "test_the_lease_is_held_only_during_a_call_and_renewed_before_each_model_call_and_step",
        "test_a_run_that_raises_releases_its_lease_and_stops",
        "test_a_lost_lease_stops_the_run_before_its_step_runs",
        "test_private_files_are_kept_and_the_connection_closes",
        "test_domains_and_the_runner_follow_the_setting",
        "test_a_blank_request_and_an_unknown_run_leave_no_lease",
        "test_a_lease_taken_during_the_step_stops_the_answer",
        "test_state_answers_while_another_holder_has_the_lease",
        "test_a_classifier_error_stops_at_route",
        "test_run_errors_name_the_run_and_the_node",
    },
    "integration/test_supervisor_step_runs.py": {
        "test_a_delegate_step_asks_and_a_mixed_plan_runs_the_read_first",
        "test_resuming_twice_does_not_duplicate_an_approval",
        "test_a_list_result_escalates_and_a_runner_error_passes",
        "test_retry_runs_a_plan_and_an_answer_again",
        "test_run_state_names_an_escalation_and_a_cancelled_run_is_not_waiting",
        "test_a_rejected_step_logs_the_request_the_error_and_the_finish",
        "test_a_secret_stays_out_of_every_escalation",
    },
    "e2e/test_web_decide_forms.py": {
        "test_parse_json_object_keeps_only_objects",
        "test_a_valid_cookie_is_kept_and_the_forms_carry_it",
        "test_a_bad_token_does_not_open_the_store",
        "test_an_unknown_action_is_refused_and_a_broken_store_is_unavailable",
        "test_a_second_decision_links_back_to_the_request",
        "test_a_refused_edit_and_a_conflict_start_no_extra_resume",
        "test_finished_runs_show_their_line",
    },
    "e2e/test_web_page_safety.py": {
        "test_two_host_headers_are_refused_and_localhost_is_answered",
        "test_a_lifespan_message_reaches_the_app",
        "test_post_and_a_broken_store_carry_every_header",
        "test_a_plan_shows_both_steps_and_escalations_are_oldest_first",
        "test_a_note_a_detail_and_an_action_are_escaped",
        "test_a_capital_id_is_not_found_without_opening_the_store",
    },
    "integration/test_mcp_step_runners.py": {
        "test_demo_and_lab_echo_use_their_own_runners",
        "test_a_write_call_starts_the_server_only_after_step_approval",
    },
    "integration/test_resume_failed_note.py": {
        "test_a_failed_note_records_its_type_and_keeps_both_decisions",
    },
    "integration/test_dollars_spending_run.py": {
        "test_a_spending_run_keeps_cents_in_the_log_and_sends_dollars",
    },
    "integration/test_finance_prefixed_request.py": {
        "test_a_prefixed_balance_request_runs_to_done",
    },
    "integration/test_finance_proposal_approvals.py": {
        "test_advice_waits_for_both_approvals_and_keeps_its_text",
        "test_a_rejected_plan_calls_no_tool",
    },
    "unit/test_answer.py": {
        "test_the_answer_point_and_its_prompt",
        "test_an_answer",
        "test_a_blank_reply_escalates",
        "test_a_model_that_cannot_answer_escalates",
        "test_an_answer_needs_1_to_8_results",
        "test_the_request_is_checked_as_in_routing",
        "test_a_full_request_and_eight_results_reach_the_model_and_the_request_is_first",
        "test_an_invalid_reply_is_the_escalation_and_a_script_error_passes",
        "test_a_reply_of_2000_characters_is_kept_and_2001_is_too_long",
    },
    "unit/test_decisions.py": {
        "test_an_approval_is_checked_then_recorded",
        "test_an_edit_and_a_rejection",
        "test_a_refused_edit_records_nothing",
        "test_a_decided_request_is_refused_before_the_policy",
        "test_an_unknown_request",
        "test_a_note_that_is_too_long",
        "test_an_escalation_is_answered_once",
        "test_who_decides_is_a_setting",
        "test_a_bad_label_is_refused",
        "test_a_note_of_500_is_kept_and_a_longer_one_is_refused_first",
        "test_a_store_that_lost_the_race_passes_already_decided",
        "test_an_unregistered_action_records_nothing",
        "test_an_unknown_escalation_is_missing_and_an_answered_one_skips_the_clock",
        "test_a_refused_edit_leaves_the_pending_list",
    },
    "unit/test_diagnostics.py": {
        "test_python_version_is_the_running_interpreter",
        "test_a_bad_digest_is_missing_and_a_latest_tag_is_shown",
    },
    "unit/test_finance_catalog.py": {
        "test_finance_is_a_package_of_three_modules",
        "test_each_half_holds_its_own_actions",
        "test_a_half_defines_exactly_the_contracts_of_its_actions",
        "test_common_holds_only_what_both_halves_share",
        "test_the_package_defines_no_contract",
        "test_each_module_imports_only_the_layer_below",
        "test_a_name_in_use_today_still_imports_from_finance",
        "test_the_planner_lists_every_finance_action_in_order",
        "test_a_transaction_limit_and_a_note_subject_keep_their_bounds",
    },
    "unit/test_finance_proposals.py": {
        "test_eleven_proposal_actions_after_the_reads",
        "test_the_required_fields_and_the_defaults",
        "test_arguments_at_their_bounds_are_sent",
        "test_arguments_past_their_bounds_are_refused",
        "test_the_fake_server_returns_a_result_each_proposal_accepts",
        "test_proposal_words_route_by_rule",
        "test_a_proposal_word_and_a_demo_word_conflict",
        "test_each_finding_type_can_be_ignored",
        "test_a_deleted_rule_sends_no_other_change_and_a_long_rename_is_refused",
        "test_advice_keeps_a_line_break_and_refuses_a_long_subject",
    },
    "unit/test_mcp_declarations.py": {
        "test_the_declarations",
        "test_server_declarations_are_checked",
        "test_the_mcp_settings",
        "test_bad_mcp_settings",
        "test_a_long_environment_name_is_refused_before_an_action",
        "test_a_domain_without_servers_keeps_tool_actions",
        "test_bad_server_names_follow_the_timeout_in_sorted_order",
        "test_a_quoted_command_keeps_a_path_with_spaces",
    },
    "unit/test_mcp_runner.py": {
        "test_the_failure_codes",
        "test_a_call_with_the_declared_server_and_the_arguments_as_json",
        "test_fields_the_contract_does_not_name_are_dropped",
        "test_each_failure_has_its_code",
        "test_a_result_over_256_kb_fails",
        "test_the_domain_runner_sends_each_action_to_its_runner",
        "test_without_the_demo_setting_demo_actions_do_not_run",
        "test_an_unknown_code_is_dropped_and_the_detail_names_a_real_one",
        "test_each_action_calls_its_own_server_once",
        "test_a_failure_carries_no_secret_and_no_cause",
        "test_unknown_keys_only_give_nothing_and_the_graph_refuses_it",
    },
    "unit/test_contracts_edge_cases.py": {
        "test_assigning_to_a_field_is_refused",
        "test_a_task_error_message_of_500_characters_is_kept",
        "test_task_output_and_args_refuse_nan_from_json",
        "test_a_task_spec_keeps_seven_earlier_results",
        "test_an_escalation_refuses_an_empty_detail_and_a_bad_run_id",
        "test_problems_name_the_whole_object_and_mask_long_or_unsafe_keys",
    },
    "unit/test_decide_failures.py": {
        "test_the_request_is_on_disk_when_chat_is_called",
        "test_a_script_error_leaves_only_the_request",
        "test_any_done_reason_but_stop_is_cut_off_without_parsing",
        "test_two_bad_fields_are_both_reported",
        "test_a_timeout_is_logged_with_no_status",
        "test_a_failing_reply_is_asked_once",
        "test_every_unavailable_code_escalates_within_the_detail_limit",
    },
    "unit/test_dollars_and_days.py": {
        "test_amounts_near_a_whole_dollar",
        "test_an_invalid_id_is_reported_before_an_invalid_today",
        "test_plan_request_plans_on_the_given_day_without_the_clock",
    },
    "unit/test_eval_case_runs.py": {
        "test_an_id_from_an_earlier_file_is_used_twice",
        "test_a_number_plan_and_args_on_an_escalation_are_refused",
        "test_a_request_of_2000_characters_loads",
        "test_args_missing_a_key_are_not_right",
        "test_actions_in_another_order_are_not_right",
        "test_an_invalid_model_output_is_not_the_expected_escalation",
        "test_a_classifier_route_and_a_plan_sum_both_times",
        "test_one_run_has_equal_percentiles_and_overall_without_args_prints_a_dash",
        "test_model_for_uses_the_configured_ollama",
        "test_too_many_runs_are_refused",
        "test_a_folder_runs_each_file_in_order",
        "test_a_file_that_is_not_toml_is_not_a_case_file",
    },
    "unit/test_eval_report_history.py": {
        "test_one_run_keeps_its_id",
        "test_two_files_and_two_results_keep_their_order",
        "test_two_digests_are_kept_sorted",
        "test_a_run_with_no_log_adds_nothing",
        "test_a_report_that_is_not_utf8_is_refused",
        "test_a_removed_case_and_an_escalation_are_named_alone",
        "test_notes_are_not_a_previous_report",
        "test_a_bad_run_count_wins_over_an_unreadable_report",
    },
    "unit/test_finance_arguments.py": {
        "test_a_left_out_argument_keeps_its_default_except_the_phrase",
        "test_a_missing_program_still_registers_finance_and_the_doctor_fails",
        "test_the_demo_plan_also_sends_16384",
    },
    "unit/test_graph_step_failures.py": {
        "test_a_propose_without_a_result_and_a_failed_read",
        "test_a_retried_write_waits_for_a_new_step_approval",
    },
    "unit/test_groundwork_limits.py": {
        "test_a_late_offset_just_after_midnight_is_the_local_day",
        "test_plan_fields_reads_today_once_and_leap_day_is_tuesday",
        "test_both_caps_at_8192_are_sent_and_a_missing_context_is_refused",
        "test_no_results_are_refused_and_two_results_together_escalate",
    },
}


def functions_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    }


def test_only_the_pending_files_are_named_for_when_they_were_added() -> None:
    found = {
        path.relative_to(TESTS).as_posix()
        for path in TESTS.rglob("test_*.py")
        if SUFFIXED.search(path.stem)
    }
    assert sorted(found) == sorted(PENDING)


@pytest.mark.parametrize("target", sorted(MOVED), ids=lambda target: Path(target).stem)
def test_moved_tests_live_in_their_new_file(target: str) -> None:
    path = TESTS / target
    assert path.is_file()
    assert sorted(functions_in(path)) == sorted(MOVED[target])


@pytest.mark.parametrize(
    ("stem", "suffixed"),
    [
        ("test_store_more", True),
        ("test_eval_more_reports", True),
        ("test_web_extra", True),
        ("test_runtime_9p", True),
        ("test_runtime_phase_9p", True),
        ("test_reports_phase", False),
        ("test_check_reports_phase", False),
        ("test_cli_doctor_digest", False),
        ("test_event_appends", False),
    ],
)
def test_a_name_says_what_it_covers_not_when(stem: str, suffixed: bool) -> None:
    assert bool(SUFFIXED.search(stem)) is suffixed
