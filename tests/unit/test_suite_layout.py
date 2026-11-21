import ast
import re
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[1]

# A test file is named for what it covers, never for when it was added (docs/testing.md rule 9).
SUFFIXED = re.compile(r"_(more|extra|again)(_|$)|_(phase_?)?\d+[a-z]?$")

# Files still waiting for their slice (9u, 9v). Each slice deletes its own lines.
PENDING = {
    "unit/test_answer_more.py",
    "unit/test_contracts_more.py",
    "unit/test_decide_more.py",
    "unit/test_decisions_more.py",
    "unit/test_diagnostics_more.py",
    "unit/test_dollars_more.py",
    "unit/test_eval_more.py",
    "unit/test_eval_more_reports.py",
    "unit/test_finance_catalog_more.py",
    "unit/test_finance_more.py",
    "unit/test_finance_proposals_more.py",
    "unit/test_graph_split_more.py",
    "unit/test_groundwork_more.py",
    "unit/test_mcp_declarations_more.py",
    "unit/test_mcp_runner_more.py",
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
