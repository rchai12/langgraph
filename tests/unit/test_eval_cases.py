from pathlib import Path

import pytest

from conductor.domains import demo
from conductor.evals.cases import CaseFileError, EvalCase, load_cases
from conductor.registry import Registry

REGISTRY = Registry((demo.DOMAIN,))
GIVEN = Path(__file__).resolve().parents[2] / "evals" / "cases" / "demo.toml"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cases.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_given_demo_cases_load() -> None:
    cases = load_cases(GIVEN, REGISTRY)
    assert [case.id for case in cases] == [
        "repeat-hello",
        "note-milk",
        "echo-then-note",
        "no-action-fits",
        "no-domain-fits",
    ]
    assert cases[0] == EvalCase(
        id="repeat-hello",
        request="Please repeat after me: hello there",
        route="demo",
        plan=("echo",),
        args=({"text": "hello there"},),
    )
    assert (cases[3].plan, cases[4].route, cases[4].plan) == ("escalate", "escalate", None)
    assert cases[1].args is None


def problem(tmp_path: Path, text: str) -> str:
    path = write(tmp_path, text)
    with pytest.raises(CaseFileError) as raised:
        load_cases(path, REGISTRY)
    assert str(raised.value).startswith(f"{path}: ")
    return str(raised.value)[len(f"{path}: ") :]


CASE = '[[case]]\nid = "a"\nrequest = "Echo hi"\nroute = "demo"\nplan = ["echo"]\n'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[[case]\n", "the file is not TOML"),
        ('title = "x"\n', "unknown key title"),
        ("", "the file needs at least one [[case]]"),
        (CASE + 'colour = "red"\n', "case 1: unknown key colour"),
        (
            CASE.replace('id = "a"', 'id = "A b"'),
            "case 1: id must be lowercase letters, digits, and dashes",
        ),
        (CASE + CASE, "case 2: id a is used twice"),
        (
            CASE.replace('request = "Echo hi"', 'request = "  "'),
            "case 1: request must have 1 to 2000 characters",
        ),
        (
            CASE.replace('route = "demo"', 'route = "travel"'),
            "case 1: route must be a registered domain or escalate",
        ),
        (
            CASE.replace('["echo"]', '["send"]'),
            "case 1: plan must be a list of the domain's actions or escalate",
        ),
        (
            CASE.replace('route = "demo"', 'route = "escalate"'),
            "case 1: a case that expects a route escalation has no plan",
        ),
        (CASE.replace('plan = ["echo"]\n', ""), "case 1: a routed case needs a plan"),
        (
            CASE + 'args = [{ text = "hi" }, { text = "again" }]\n',
            "case 1: args must be one table per planned step",
        ),
        (
            CASE.replace('id = "a"\n', ""),
            "case 1: id must be lowercase letters, digits, and dashes",
        ),
    ],
)
def test_what_a_case_file_may_not_hold(tmp_path: Path, text: str, message: str) -> None:
    assert problem(tmp_path, text) == message


def test_a_problem_never_quotes_the_request(tmp_path: Path) -> None:
    text = CASE.replace('request = "Echo hi"', 'request = "SYNTHETIC-SECRET"').replace(
        'route = "demo"', 'route = "nowhere"'
    )
    assert "SYNTHETIC-SECRET" not in problem(tmp_path, text)
