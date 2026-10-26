import pytest
from pydantic import ValidationError

from conductor import contracts
from conductor.contracts import (
    MAX_STEPS,
    NOT_FINITE_MESSAGE,
    ONE_DOMAIN_MESSAGE,
    ROUTE_MESSAGE,
    Plan,
    Route,
    Step,
)


def problems(raised: pytest.ExceptionInfo[ValidationError]) -> list[tuple[str, str]]:
    return [
        (".".join(str(part) for part in error["loc"]), error["type"])
        for error in raised.value.errors()
    ]


def reason(raised: pytest.ExceptionInfo[ValidationError]) -> str:
    return str(raised.value.errors()[0]["ctx"]["error"])


def test_a_plan_from_the_models_json() -> None:
    plan = Plan.from_json(
        '{"steps":[{"action":"finance.get_spending","args":{"month":"2026-09","by":["category"]}},'
        '{"action":"finance.list_accounts","args":{}}]}'
    )
    assert plan == Plan(
        steps=(
            Step(action="finance.get_spending", args={"month": "2026-09", "by": ["category"]}),
            Step(action="finance.list_accounts", args={}),
        )
    )
    assert plan.domain == "finance"
    assert plan.steps[0].domain == "finance"
    assert MAX_STEPS == 8


def test_extra_fields_are_refused_and_code_may_pass_lists() -> None:
    with pytest.raises(ValidationError) as raised:
        Route.from_json('{"domain":"finance","decided_by":"model","rule_id":null,"extra":1}')
    assert problems(raised) == [("extra", "extra_forbidden")]
    built = Plan.model_validate({"steps": [{"action": "demo.echo", "args": {}}]})
    assert built.steps == (Step(action="demo.echo", args={}),)


@pytest.mark.parametrize(
    "action",
    [
        "echo",
        "Demo.echo",
        "demo.echo.twice",
        "demo.echo\n",
        "a" * 33 + ".echo",
    ],
)
def test_an_action_name_must_be_domain_dot_name(action: str) -> None:
    with pytest.raises(ValidationError) as raised:
        Step(action=action, args={})
    assert problems(raised) == [("action", "string_pattern_mismatch")]


def test_the_longest_names_are_accepted() -> None:
    name = "a" + "b" * 31
    assert Step(action=f"{name}.{name}", args={}).domain == name


@pytest.mark.parametrize(
    "text",
    [
        '{"action":"demo.echo","args":{"n":NaN}}',
        '{"action":"demo.echo","args":{"deep":{"n":-Infinity}}}',
    ],
)
def test_numbers_must_be_finite_in_json(text: str) -> None:
    with pytest.raises(ValidationError) as raised:
        Step.from_json(text)
    assert reason(raised) == NOT_FINITE_MESSAGE
    assert NOT_FINITE_MESSAGE == "numbers must be finite"


def test_numbers_must_be_finite_when_built() -> None:
    with pytest.raises(ValidationError) as raised:
        Step(action="demo.echo", args={"values": [1.5, {"x": float("nan")}]})
    assert reason(raised) == NOT_FINITE_MESSAGE


@pytest.mark.parametrize("count", [0, 9])
def test_a_plan_has_one_to_eight_steps(count: int) -> None:
    steps = [{"action": "demo.echo", "args": {"n": n}} for n in range(count)]
    with pytest.raises(ValidationError) as raised:
        Plan.model_validate({"steps": steps})
    assert [kind for _, kind in problems(raised)] == ["too_short" if count == 0 else "too_long"]


def test_a_plan_stays_in_one_domain() -> None:
    with pytest.raises(ValidationError) as raised:
        Plan(
            steps=(Step(action="demo.echo", args={}), Step(action="finance.list_accounts", args={}))
        )
    assert reason(raised) == ONE_DOMAIN_MESSAGE
    assert ONE_DOMAIN_MESSAGE == "every step must be in one domain"


@pytest.mark.parametrize(
    ("decided_by", "rule_id", "ok"),
    [
        ("rule", "finance.prefix", True),
        ("model", None, True),
        ("rule", None, False),
        ("model", "finance.prefix", False),
    ],
)
def test_a_route_names_its_rule_only_when_a_rule_decided(
    decided_by: str, rule_id: str | None, ok: bool
) -> None:
    if ok:
        route = Route(domain="finance", decided_by=decided_by, rule_id=rule_id)
        assert (route.decided_by, route.rule_id) == (decided_by, rule_id)
        return
    with pytest.raises(ValidationError) as raised:
        Route(domain="finance", decided_by=decided_by, rule_id=rule_id)
    assert reason(raised) == ROUTE_MESSAGE
    assert ROUTE_MESSAGE == "a rule route needs a rule_id and a model route has none"


@pytest.mark.parametrize(
    ("field", "value", "kind"),
    [
        ("domain", "Finance", "string_pattern_mismatch"),
        ("decided_by", "guess", "literal_error"),
    ],
)
def test_a_route_refuses_bad_values(field: str, value: str, kind: str) -> None:
    given = {"domain": "finance", "decided_by": "rule", "rule_id": "finance.prefix", field: value}
    with pytest.raises(ValidationError) as raised:
        Route.model_validate(given)
    assert problems(raised) == [(field, kind)]


def test_the_package_exports_exactly_its_public_names() -> None:
    assert sorted(contracts.__all__) == [
        "Contract",
        "DecidedBy",
        "Escalation",
        "EscalationKind",
        "FieldProblem",
        "JsonObject",
        "MAX_ATTEMPTS",
        "MAX_PROBLEMS",
        "MAX_STEPS",
        "NOT_FINITE_MESSAGE",
        "ONE_DOMAIN_MESSAGE",
        "Plan",
        "RESULT_MESSAGE",
        "ROUTE_MESSAGE",
        "Route",
        "Step",
        "TaskError",
        "TaskErrorKind",
        "TaskResult",
        "TaskSpec",
        "TaskStatus",
        "problems_from",
    ]
