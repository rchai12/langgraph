import pytest

from tests.support import run

MCP_REFUSED = "Error: CONDUCTOR_MCP: must map server names to command lines\n"


@pytest.mark.parametrize("value", ["notjson", '{"ledger": 1}'], ids=["not json", "not text"])
def test_doctor_reports_a_bad_server_mapping_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("CONDUCTOR_MCP", value)
    result = run("doctor")
    assert (result.exit_code, result.stdout, result.stderr) == (1, "", MCP_REFUSED)
    assert result.exception is None or type(result.exception) is SystemExit
