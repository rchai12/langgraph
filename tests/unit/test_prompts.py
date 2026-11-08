import hashlib
from pathlib import Path

import pytest

from conductor.llm.prompts import PROMPTS_DIR, PromptError, load_template


def test_the_demo_template_loads() -> None:
    template = load_template("demo_pick.v1")
    raw = (PROMPTS_DIR / "demo_pick.v1.md").read_bytes()
    assert template.name == "demo_pick.v1"
    assert template.text == raw.decode("utf-8")
    assert template.sha256 == hashlib.sha256(raw).hexdigest()
    assert template.fields == ("actions",)
    assert PROMPTS_DIR.resolve() == (Path(__file__).parents[2] / "src/conductor/prompts").resolve()


@pytest.mark.parametrize(
    "name",
    [
        "demo_pick",
        "Demo_pick.v1",
        "demo_pick.v0",
        "demo_pick.v1.md",
        "../demo_pick.v1",
        "demo_pick.v1000",
    ],
)
def test_a_template_name_needs_a_name_and_a_version(name: str) -> None:
    with pytest.raises(PromptError) as raised:
        load_template(name)
    assert str(raised.value) == f"prompt {name}: not a valid template name"


def test_a_missing_template(tmp_path: Path) -> None:
    with pytest.raises(PromptError) as raised:
        load_template("absent.v1", tmp_path)
    assert str(raised.value) == "prompt absent.v1: not found"


def test_a_template_that_is_not_utf8(tmp_path: Path) -> None:
    (tmp_path / "latin.v1.md").write_bytes("caf\xe9".encode("latin-1"))
    with pytest.raises(PromptError) as raised:
        load_template("latin.v1", tmp_path)
    assert str(raised.value) == "prompt latin.v1: not UTF-8"


@pytest.mark.parametrize("text", ["Pay $5 now.", "A lone $ sign."])
def test_a_template_with_a_stray_dollar(tmp_path: Path, text: str) -> None:
    (tmp_path / "money.v2.md").write_text(text, encoding="utf-8")
    with pytest.raises(PromptError) as raised:
        load_template("money.v2", tmp_path)
    assert str(raised.value) == "prompt money.v2: not a valid template"


def test_fields_are_sorted_and_named_once(tmp_path: Path) -> None:
    (tmp_path / "pair.v12.md").write_text("$b then $a then ${b}; costs $$5\n", encoding="utf-8")
    template = load_template("pair.v12", tmp_path)
    assert template.fields == ("a", "b")
    assert template.sha256 == hashlib.sha256(b"$b then $a then ${b}; costs $$5\n").hexdigest()
