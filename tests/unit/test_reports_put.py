from datetime import date

import pytest

from conductor.reports import ENTRY_MESSAGE, ProgressEntry, format_entry, parse_progress, put_entry

FIRST = """# Progress

## Phase 1: invented start (2026-01-02)
- Tests: 0 -> 5 (given 5)
- New public names: None
- Changed files: 3
- Deviations:
  - None
- Follow-ups:
  - None
"""


def _entry(phase: str = "2a", title: str = "invented step", **changes: object) -> ProgressEntry:
    base = ProgressEntry(
        phase=phase,
        title=title,
        date=date(2026, 3, 4),
        tests_before=5,
        tests_after=9,
        given=4,
        new_names="`conductor.x`: `y`",
        changed_files=2,
        deviations=(),
        follow_ups=("Stopped: R1 | a test fails | a fixed spec",),
        line=0,
    )
    return ProgressEntry(**{**base.__dict__, **changes})


ENTRY_TEXT = """## Phase 2a: invented step (2026-03-04)
- Tests: 5 -> 9 (given 4)
- New public names: `conductor.x`: `y`
- Changed files: 2
- Deviations:
  - None
- Follow-ups:
  - Stopped: R1 | a test fails | a fixed spec
"""


def test_format_entry_writes_none_for_an_empty_list() -> None:
    assert format_entry(_entry()) == ENTRY_TEXT


def test_put_entry_appends_after_one_blank_line() -> None:
    assert put_entry(FIRST, _entry()) == FIRST + "\n" + ENTRY_TEXT


def test_put_entry_into_an_empty_log() -> None:
    assert put_entry("", _entry()) == ENTRY_TEXT


def test_put_entry_replaces_its_own_last_entry() -> None:
    once = put_entry(FIRST, _entry())
    again = put_entry(once, _entry(deviations=("one choice",), follow_ups=()))
    entries, problems = parse_progress(again)
    assert problems == []
    assert [entry.phase for entry in entries] == ["1", "2a"]
    assert entries[1].deviations == ("one choice",)
    assert entries[1].follow_ups == ("None",)


def test_put_entry_replaces_an_entry_in_the_middle_and_keeps_the_next() -> None:
    log = put_entry(put_entry(FIRST, _entry()), _entry(phase="2b", title="later step"))
    updated = put_entry(log, _entry(tests_after=11))
    assert updated == FIRST + "\n" + ENTRY_TEXT.replace("5 -> 9", "5 -> 11") + "\n" + format_entry(
        _entry(phase="2b", title="later step")
    )


@pytest.mark.parametrize(
    "changes",
    [{"phase": "02a"}, {"title": ""}, {"deviations": ("two\nlines",)}],
    ids=["padded-id", "empty-title", "item-newline"],
)
def test_an_entry_out_of_form_is_refused(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError) as caught:
        put_entry(FIRST, _entry(**changes))
    assert str(caught.value) == ENTRY_MESSAGE
