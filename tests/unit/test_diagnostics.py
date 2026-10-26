import sys

from conductor import diagnostics


def test_python_version_is_the_running_interpreter() -> None:
    assert diagnostics.python_version() == sys.version_info[:3]
