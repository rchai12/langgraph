from dataclasses import replace
from pathlib import Path
from string import Template

import pytest

from conductor.domains import demo
from conductor.llm.points import SCHEMA_INTRO, SEED, build_request
from conductor.llm.prompts import PromptError, load_template


def test_a_name_of_32_characters_loads_and_version_999_is_a_name(tmp_path: Path) -> None:
    short = "a" * 32
    (tmp_path / f"{short}.v1.md").write_text("Hello.\n", encoding="utf-8")
    loaded = load_template(f"{short}.v1", tmp_path)
    assert loaded.name == f"{short}.v1"
    assert loaded.text == "Hello.\n"

    long = "a" * 33 + ".v1"
    with pytest.raises(PromptError) as raised:
        load_template(long, tmp_path)
    assert str(raised.value) == f"prompt {long}: not a valid template name"

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(PromptError) as raised:
        load_template("x.v999", empty)
    assert str(raised.value) == "prompt x.v999: not found"


def test_a_bad_name_is_refused_before_the_file(tmp_path: Path) -> None:
    (tmp_path / "Bad.v1.md").write_text("Hello.\n", encoding="utf-8")
    with pytest.raises(PromptError) as raised:
        load_template("Bad.v1", tmp_path)
    assert str(raised.value) == "prompt Bad.v1: not a valid template name"


def test_a_bad_name_is_named_before_bad_inputs() -> None:
    point = replace(demo.PICK, name="Demo_pick", inputs=dict)
    with pytest.raises(PromptError) as raised:
        build_request(point, demo.PickInputs(request="x"), model="m", fields=demo.pick_fields())
    assert str(raised.value) == "point Demo_pick: not a valid name"


def test_think_is_named_before_the_reply_cap() -> None:
    point = replace(demo.PICK, think=1, max_reply_tokens=0)
    with pytest.raises(PromptError) as raised:
        build_request(point, demo.PickInputs(request="x"), model="m", fields=demo.pick_fields())
    assert str(raised.value) == "point demo_pick: think must be true or false"


def test_the_reply_cap_bounds_are_accepted() -> None:
    for cap in (1, 8192):
        point = replace(demo.PICK, max_reply_tokens=cap)
        request = build_request(
            point, demo.PickInputs(request="x"), model="m", fields=demo.pick_fields()
        )
        assert request.options["num_predict"] == cap


def test_trailing_whitespace_leaves_one_blank_line() -> None:
    value = "kept\n\n  "
    request = build_request(
        demo.PICK,
        demo.PickInputs(request="x"),
        model="m",
        fields={"actions": value},
    )
    filled = Template(load_template("demo_pick.v1").text).substitute({"actions": value})
    assert filled.endswith("\n\n  \n")
    before = request.system.split(SCHEMA_INTRO, 1)[0]
    assert before.endswith("kept\n\n")
    assert not before.endswith("\n\n\n")


def test_changing_the_body_does_not_change_the_request() -> None:
    request = build_request(
        demo.PICK,
        demo.PickInputs(request="x"),
        model="m",
        fields=demo.pick_fields(),
    )
    request.body()["options"]["seed"] = 1
    assert request.options["seed"] == SEED
    assert request.body()["options"]["seed"] == SEED


def test_pick_fields_follows_the_domain() -> None:
    lines = demo.pick_fields()["actions"].split("\n")
    assert lines == [f"- {action.name}: {action.description}" for action in demo.DOMAIN.actions]
    assert len(lines) == len(demo.DOMAIN.actions)
