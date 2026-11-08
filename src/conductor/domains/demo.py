from typing import Literal

from pydantic import Field

from conductor.contracts.base import Contract, Id, Name
from conductor.llm.points import DecisionPoint
from conductor.registry import Action, Domain


class EchoArgs(Contract):
    text: str = Field(min_length=1, max_length=200)


class EchoResult(Contract):
    text: str


class NoteArgs(Contract):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(default="", max_length=2000)
    tags: tuple[Name, ...] = Field(default=(), max_length=5)


class NoteResult(Contract):
    note_id: Id


class DelegateArgs(Contract):
    task: str = Field(min_length=1, max_length=500)
    max_minutes: int = Field(default=10, ge=1, le=60)


class DelegateResult(Contract):
    summary: str = Field(min_length=1, max_length=2000)


DOMAIN = Domain(
    name="demo",
    description="A domain for tests: echo text, write a note, delegate a task.",
    actions=(
        Action(
            "echo",
            "Repeat the text back.",
            "tool",
            "echo",
            "read",
            EchoArgs,
            EchoResult,
        ),
        Action(
            "note",
            "Write a note with a title, a body, and tags.",
            "tool",
            "write_note",
            "write",
            NoteArgs,
            NoteResult,
        ),
        Action(
            "delegate",
            "Hand a task to the demo agent.",
            "agent",
            "demo_agent",
            "implement",
            DelegateArgs,
            DelegateResult,
        ),
    ),
)


class PickInputs(Contract):
    request: str = Field(min_length=1, max_length=2000)


class PickOutput(Contract):
    action: Literal["echo", "note", "delegate", "none"]


PICK = DecisionPoint(
    name="demo_pick",
    template="demo_pick.v1",
    inputs=PickInputs,
    output=PickOutput,
    think=True,
    max_reply_tokens=256,
)


def pick_fields() -> dict[str, str]:
    lines = [f"- {action.name}: {action.description}" for action in DOMAIN.actions]
    return {"actions": "\n".join(lines)}
