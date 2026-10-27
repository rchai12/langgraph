from pydantic import Field

from conductor.contracts.base import Contract, Id, Name
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
