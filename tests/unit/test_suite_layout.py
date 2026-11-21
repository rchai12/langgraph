import ast
import re
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parents[1]

# A test file is named for what it covers, never for when it was added (docs/testing.md rule 9).
SUFFIXED = re.compile(r"_(more|extra|again)(_|$)|_(phase_?)?\d+[a-z]?$")

# Files still waiting for their slice (9t, 9u, 9v). Each slice deletes its own lines.
PENDING = {
    "e2e/test_web_decide_more.py",
    "e2e/test_web_pages_more.py",
    "e2e/test_web_resume_more.py",
    "integration/test_dollars_more.py",
    "integration/test_finance_more.py",
    "integration/test_finance_proposals_more.py",
    "integration/test_mcp_client_more.py",
    "integration/test_mcp_steps_more.py",
    "integration/test_resume_evidence_more.py",
    "integration/test_runtime_more.py",
    "integration/test_supervisor_more.py",
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
