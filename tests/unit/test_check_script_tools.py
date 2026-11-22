import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"script_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPEC = """# Phase 4z: invented

## Acceptance

| Command | Must show |
|---|---|
| `echo one` | `one` |

### Searches

```sh
git grep -n -E 'never' -- src
```
"""

GUIDE = """# Verify Phase 4z: invented

## 1. Gates

| # | Command | Must show |
|---|---|---|
| G1 | `echo gate` | `gate` |

## 4. Searches

```sh
git grep -n -E 'never' -- src
```
"""


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "phases").mkdir(parents=True)
    (tmp_path / "docs" / "verification").mkdir(parents=True)
    (tmp_path / "docs" / "phases" / "phase-04z-invented.md").write_text(SPEC, encoding="utf-8")
    (tmp_path / "docs" / "verification" / "phase-04z-invented.md").write_text(
        GUIDE, encoding="utf-8"
    )
    return tmp_path


def _fake(seen: list[str]):
    def run(command: str, _cwd: Path) -> tuple[int, str]:
        seen.append(command)
        if command.startswith("git grep"):
            return 1, ""
        return 0, command.removeprefix("echo ") + "\n"

    return run


def test_accept_runs_the_spec_rows(tmp_path, capsys) -> None:
    accept = _load("accept")
    root = _repo(tmp_path)
    seen: list[str] = []
    code = accept.main(
        ["--phase", "4z", "--root", str(root), "--log-dir", str(tmp_path / "logs")], _fake(seen)
    )
    assert code == 0
    assert seen == ["echo one", "git grep -n -E 'never' -- src"]
    assert capsys.readouterr().out.splitlines() == [
        "A1: one",
        "Q1: empty",
        f"Logs: {tmp_path / 'logs'}",
    ]


def test_accept_runs_the_guide_gates_then_searches(tmp_path, capsys) -> None:
    accept = _load("accept")
    root = _repo(tmp_path)
    seen: list[str] = []
    argv = ["--phase", "4z", "--guide", "--root", str(root), "--log-dir", str(tmp_path / "l")]
    assert accept.main(argv, _fake(seen)) == 0
    assert seen == ["echo gate", "git grep -n -E 'never' -- src"]
    assert capsys.readouterr().out.splitlines()[:2] == ["G1: gate", "Q1: empty"]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--phase", "04z"], "Error: phase must be a phase id such as 5a"),
        (["--phase", "5c"], "Error: no spec for phase 5c"),
        (["--phase", "5c", "--guide"], "Error: no guide for phase 5c"),
    ],
    ids=["bad-id", "no-spec", "no-guide"],
)
def test_accept_refusals(tmp_path, capsys, argv: list[str], message: str) -> None:
    accept = _load("accept")
    root = _repo(tmp_path)
    assert accept.main([*argv, "--root", str(root)], _fake([])) == 2
    assert capsys.readouterr().err.strip() == message


def test_accept_refuses_a_spec_without_an_acceptance_heading(tmp_path, capsys) -> None:
    accept = _load("accept")
    root = _repo(tmp_path)
    (root / "docs" / "phases" / "phase-04z-invented.md").write_text("# Phase 4z\n", "utf-8")
    assert accept.main(["--phase", "4z", "--root", str(root)], _fake([])) == 2
    assert capsys.readouterr().err.strip() == "Error: no such heading: Acceptance"


PROGRESS = """# Progress

## Phase 1: invented start (2026-01-02)
- Tests: 0 -> 5 (given 5)
- New public names: None
- Changed files: 3
- Deviations:
  - None
- Follow-ups:
  - None
"""

PROGRESS_ARGS = [
    "--phase",
    "2a",
    "--title",
    "invented step",
    "--date",
    "2026-03-04",
    "--tests-before",
    "5",
    "--tests-after",
    "9",
    "--given",
    "4",
    "--names",
    "None",
    "--changed",
    "2",
]


def test_progress_writes_the_entry(tmp_path, capsys) -> None:
    progress = _load("progress")
    log = tmp_path / "progress.md"
    log.write_text(PROGRESS, encoding="utf-8")
    argv = [*PROGRESS_ARGS, "--file", str(log), "--deviation", "one", "--follow-up", "two"]
    assert progress.main(argv) == 0
    assert capsys.readouterr().out == "Progress entry for Phase 2a written.\n"
    assert log.read_text(encoding="utf-8") == PROGRESS + (
        "\n## Phase 2a: invented step (2026-03-04)\n- Tests: 5 -> 9 (given 4)\n"
        "- New public names: None\n- Changed files: 2\n- Deviations:\n  - one\n"
        "- Follow-ups:\n  - two\n"
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("--date", "2026-02-30"), "Error: the date is not a real date"),
        (("--phase", "02a"), "Error: the entry does not match the progress form"),
    ],
    ids=["date", "form"],
)
def test_progress_refusals_leave_the_log(tmp_path, capsys, change, message: str) -> None:
    progress = _load("progress")
    log = tmp_path / "progress.md"
    log.write_text(PROGRESS, encoding="utf-8")
    argv = list(PROGRESS_ARGS)
    argv[argv.index(change[0]) + 1] = change[1]
    assert progress.main([*argv, "--file", str(log)]) == 2
    assert capsys.readouterr().err.strip() == message
    assert log.read_text(encoding="utf-8") == PROGRESS


def _scratch(tmp_path: Path) -> Path:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "limit.py").write_text("LIMIT = 3\n", encoding="utf-8")
    return tmp_path


def test_spot_check_prints_the_row_verdict(tmp_path, capsys) -> None:
    spot = _load("spot_check")
    root = _scratch(tmp_path)
    seen: list[tuple[str, Path, str]] = []

    def run(test: str, cwd: Path) -> tuple[int, str]:
        text = (cwd / "src" / "pkg" / "limit.py").read_text(encoding="utf-8")
        seen.append((test, cwd, text))
        return (1, "E   assert 4 == 3\n") if "4" in text else (0, "1 passed\n")

    argv = ["src/pkg/limit.py", "--old", "3", "--new", "4", "--test", "tests/t.py::a"]
    assert spot.main([*argv, "--row", "S1", "--root", str(root)], run) == 0
    assert capsys.readouterr().out == "S1 fails: assert 4 == 3\n"
    assert seen == [
        ("tests/t.py::a", root.resolve(), "LIMIT = 3\n"),
        ("tests/t.py::a", root.resolve(), "LIMIT = 4\n"),
    ]
    assert (root / "src" / "pkg" / "limit.py").read_text(encoding="utf-8") == "LIMIT = 3\n"


def test_spot_check_a_surviving_mutation_exits_one(tmp_path, capsys) -> None:
    spot = _load("spot_check")
    root = _scratch(tmp_path)
    argv = ["src/pkg/limit.py", "--old", "3", "--new", "4", "--test", "t", "--root", str(root)]
    assert spot.main(argv, lambda _test, _cwd: (0, "")) == 1
    assert capsys.readouterr().out == "passes\n"


@pytest.mark.parametrize(
    ("module", "old", "message"),
    [
        ("pkg/limit.py", "3", "Error: the module must be a file under src/"),
        ("src/pkg/none.py", "3", "Error: the module must be a file under src/"),
        ("src/pkg/limit.py", "9", "Error: the old text must match exactly once: found 0"),
    ],
    ids=["outside-src", "missing", "no-match"],
)
def test_spot_check_refusals(tmp_path, capsys, module: str, old: str, message: str) -> None:
    spot = _load("spot_check")
    root = _scratch(tmp_path)
    (root / "pkg").mkdir()
    (root / "pkg" / "limit.py").write_text("LIMIT = 3\n", encoding="utf-8")
    argv = [module, "--old", old, "--new", "4", "--test", "t", "--root", str(root)]
    assert spot.main(argv, lambda _test, _cwd: (0, "")) == 2
    assert capsys.readouterr().err.strip() == message


def test_spot_check_refuses_the_repository_itself(capsys) -> None:
    spot = _load("spot_check")
    root = SCRIPTS.parent
    argv = ["src/conductor/ids.py", "--old", "x", "--new", "y", "--test", "t", "--root", str(root)]
    assert spot.main(argv, lambda _test, _cwd: (0, "")) == 2
    message = "Error: run spot checks in a scratch copy, not the repository"
    assert capsys.readouterr().err.strip() == message


def test_check_quiet_logs_output_and_shows_a_failed_tail(tmp_path, capsys) -> None:
    check = _load("check")
    logs = tmp_path / "logs"
    calls: list[Path | None] = []

    def run(_command: list[str], _cwd: Path, log: Path | None) -> int:
        calls.append(log)
        assert log is not None
        log.write_text("\n".join(f"line {n}" for n in range(1, 31)) + "\n", encoding="utf-8")
        return 0 if len(calls) == 1 else 1

    assert check.main(["--quiet", "--log-dir", str(logs)], run) == 1
    assert calls == [logs / "lint.log", logs / "format.log"]
    out = capsys.readouterr().out.splitlines()
    assert "== lint" not in out
    tail = out.index(f"Last 20 lines of {logs / 'format.log'}:")
    assert out[tail + 1 : tail + 21] == [f"line {n}" for n in range(11, 31)]
    assert out[-2:] == [f"Logs: {logs}", "Check failed at: format"]


def test_check_quiet_section_shows_a_failed_tail(tmp_path, capsys) -> None:
    check = _load("check")
    logs = tmp_path / "logs"

    def run(_command: list[str], _cwd: Path, log: Path | None) -> int:
        assert log == logs / "section.log"
        log.write_text("boom\n", encoding="utf-8")
        return 1

    assert check.main(["--quiet", "--log-dir", str(logs), "--section", "scripts"], run) == 1
    assert capsys.readouterr().out.splitlines()[-4:] == [
        f"Last 20 lines of {logs / 'section.log'}:",
        "boom",
        "Section scripts: FAILED.",
        f"Logs: {logs}",
    ]


def test_check_log_names() -> None:
    check = _load("check")
    names = [check._log_name(name) for name in ("lint", "format", "tests", "tests (core)")]
    assert names == ["lint.log", "format.log", "tests.log", "tests-first.log"]
