import os
import subprocess
import sys

from conductor.graph import TRACING_VARIABLES, tracing_off


def test_tracing_off_sets_each_variable_false(monkeypatch) -> None:
    for name in TRACING_VARIABLES:
        monkeypatch.setenv(name, "true")
    tracing_off()
    assert [os.environ[name] for name in TRACING_VARIABLES] == ["false"] * len(TRACING_VARIABLES)


def test_importing_the_package_turns_tracing_off() -> None:
    env = os.environ.copy()
    env["LANGSMITH_TRACING"] = "true"
    code = "import os; import conductor.graph; print(os.environ['LANGSMITH_TRACING'])"
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "false"
