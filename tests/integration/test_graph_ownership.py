import gc
import itertools
import weakref
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from conductor import clock, ids
from conductor.domains import demo
from conductor.events import EventKind, EventLog
from conductor.graph.supervisor import Services, build_graph, start_run
from conductor.llm.model import ModelReply
from conductor.llm.scripted import ScriptedModel, ScriptedReply
from conductor.registry import Registry
from conductor.runtime import DemoRunner
from conductor.store import Store

RUN = "a" * 32


@pytest.fixture(autouse=True)
def fixed(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = itertools.count(1)
    monkeypatch.setattr(clock, "now", lambda: datetime(2031, 1, 2, tzinfo=UTC))
    monkeypatch.setattr(ids, "new_id", lambda: f"{next(counter):032x}")


def make_graph(folder: Path):
    log = EventLog(folder / "runs")
    services = Services(
        Registry((demo.DOMAIN,)),
        Store(folder / "conductor.db"),
        log,
        ScriptedModel(
            [
                ScriptedReply(
                    "plan", ModelReply(content='{"steps":[{"action":"echo","args":{"text":"hi"}}]}')
                ),
                ScriptedReply("answer", ModelReply(content='{"reply":"Done."}')),
            ]
        ),
        "test-model",
        DemoRunner(),
    )
    return build_graph(services, InMemorySaver()), log, weakref.ref(services)


def test_services_are_released_with_the_graph(tmp_path: Path) -> None:
    graph, log, reference = make_graph(tmp_path)
    gc.collect()
    assert reference() is not None
    del graph
    gc.collect()
    assert reference() is None
    assert log.runs() == []


def test_start_records_through_the_explicit_log(tmp_path: Path) -> None:
    graph, log, _ = make_graph(tmp_path / "graph")
    supplied = EventLog(tmp_path / "start")
    found = start_run(graph, "demo: say hi", run_id=RUN, log=supplied)
    assert (found.status, found.reply) == ("done", "Done.")
    events = supplied.read(RUN)
    assert [(e.kind, e.payload) for e in events] == [
        (EventKind.RUN_STARTED, {"request": "demo: say hi"})
    ]
    assert EventKind.RUN_STARTED not in [e.kind for e in log.read(RUN)]


def test_many_graphs_do_not_retain_services(tmp_path: Path) -> None:
    references = []
    for index in range(12):
        graph, _, reference = make_graph(tmp_path / str(index))
        references.append(reference)
        del graph
    gc.collect()
    assert all(reference() is None for reference in references)
