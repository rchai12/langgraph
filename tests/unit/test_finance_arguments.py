import shlex
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from conductor import clock, domains
from conductor.config import get_settings
from conductor.diagnostics import Check, server_lines
from conductor.domains import demo, finance
from conductor.llm.points import build_request
from conductor.planning.plan import PlanInputs, plan_fields, plan_point


def test_a_left_out_argument_keeps_its_default_except_the_phrase() -> None:
    for action in finance.READS:
        given = '{"phrase": "grocer"}' if action.name == "find_merchants" else "{}"
        filled = action.args.from_json(given)
        for name in action.args.model_fields:
            omitted = filled.model_dump(mode="json")
            omitted.pop(name)
            if action.name == "find_merchants" and name == "phrase":
                with pytest.raises(ValidationError):
                    action.args.model_validate(omitted)
                continue
            assert action.args.model_validate(omitted) == filled


def test_a_missing_program_still_registers_finance_and_the_doctor_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "no-such-fin"
    monkeypatch.setenv("CONDUCTOR_MCP__FINANCES", shlex.quote(str(missing)))
    settings = get_settings()
    assert domains.registered(settings) == (finance.DOMAIN,)
    assert server_lines(settings) == [Check("FAIL", "server finances", "start_failed")]


def test_the_demo_plan_also_sends_16384(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: date(2026, 11, 10))
    point = plan_point(demo.DOMAIN)
    sent = build_request(
        point, PlanInputs(request="Echo hi"), model="m", fields=plan_fields(demo.DOMAIN)
    )
    assert sent.options["num_ctx"] == 16384
    assert point.context_tokens == 16384
