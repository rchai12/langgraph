import pytest

from conductor.spotcheck import (
    BASELINE_MESSAGE,
    MATCH_MESSAGE,
    SpotError,
    mutate,
    spot_check,
    verdict,
)

SOURCE = "def limit():\n    return 3\n"


@pytest.mark.parametrize("old", ["return 4", "e"], ids=["none", "many"])
def test_the_old_text_must_match_once(old: str) -> None:
    with pytest.raises(SpotError) as caught:
        mutate(SOURCE, old, "x")
    count = SOURCE.count(old)
    assert str(caught.value) == f"{MATCH_MESSAGE}: found {count}"


def test_mutate_replaces_the_one_match() -> None:
    assert mutate(SOURCE, "return 3", "return 4") == "def limit():\n    return 4\n"


def test_spot_check_runs_before_and_after_and_restores_the_bytes(tmp_path) -> None:
    module = tmp_path / "limit.py"
    module.write_bytes(SOURCE.encode("utf-8"))
    seen: list[str] = []

    def run() -> tuple[int, str]:
        seen.append(module.read_text(encoding="utf-8"))
        if "return 4" in seen[-1]:
            return 1, "tests/unit/test_x.py:7: assert 4 == 3\n"
        return 0, "1 passed\n"

    found = spot_check(module, "return 3", "return 4", run)
    assert found == "fails: assert 4 == 3"
    assert seen == [SOURCE, "def limit():\n    return 4\n"]
    assert module.read_bytes() == SOURCE.encode("utf-8")


def test_a_test_that_fails_before_the_change_is_refused_untouched(tmp_path) -> None:
    module = tmp_path / "limit.py"
    module.write_bytes(SOURCE.encode("utf-8"))
    runs: list[str] = []

    def run() -> tuple[int, str]:
        runs.append(module.read_text(encoding="utf-8"))
        return 1, "failed\n"

    with pytest.raises(SpotError) as caught:
        spot_check(module, "return 3", "return 4", run)
    assert str(caught.value) == BASELINE_MESSAGE
    assert runs == [SOURCE]
    assert module.read_bytes() == SOURCE.encode("utf-8")


class _Interrupted(Exception):
    pass


def test_the_module_is_restored_when_the_run_raises(tmp_path) -> None:
    module = tmp_path / "limit.py"
    module.write_bytes(SOURCE.encode("utf-8"))
    calls = [0]

    def run() -> tuple[int, str]:
        calls[0] += 1
        if calls[0] == 2:
            raise _Interrupted
        return 0, ""

    with pytest.raises(_Interrupted):
        spot_check(module, "return 3", "return 4", run)
    assert module.read_bytes() == SOURCE.encode("utf-8")


@pytest.mark.parametrize(
    ("output", "code", "expected"),
    [
        ("1 passed\n", 0, "passes"),
        ("tests/unit/test_x.py:12: AssertionError\n", 1, "fails: AssertionError"),
        ("E   assert 'a' == 'b'\n", 1, "fails: assert 'a' == 'b'"),
        ("1 failed\n", 1, "fails"),
        ("E   ImportError: no name 'x'\n", 2, "error: ImportError: no name 'x'"),
        ("interrupted\n", 2, "error: collection"),
        ("", 4, "no test ran"),
        ("", 5, "no test ran"),
        ("timed out", 124, "error: exit 124"),
        (f"tests/a.py:1: {'x' * 150}\n", 1, f"fails: {'x' * 140}..."),
    ],
    ids=[
        "passes",
        "path-line",
        "e-line",
        "bare-failure",
        "collection-message",
        "collection",
        "usage",
        "none-collected",
        "other-exit",
        "cut",
    ],
)
def test_verdicts(output: str, code: int, expected: str) -> None:
    assert verdict(output, code) == expected
