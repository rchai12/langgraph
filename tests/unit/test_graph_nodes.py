from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from conductor.domains import demo
from conductor.events import EventLog
from conductor.graph import nodes, supervisor
from conductor.graph.status import NODES
from conductor.llm.scripted import ScriptedModel
from conductor.registry import Registry
from conductor.store import Store


class Unused:
    def run(self, action, args):
        raise AssertionError("no step runs here")


def services(tmp_path: Path) -> "nodes.Services":
    return nodes.Services(
        registry=Registry((demo.DOMAIN,)),
        store=Store(tmp_path / "conductor.db"),
        log=EventLog(tmp_path / "runs"),
        model=ScriptedModel([]),
        model_name="test-model:1b",
        runner=Unused(),
    )


def test_build_nodes_makes_every_node_in_order(tmp_path: Path) -> None:
    built = nodes.build_nodes(services(tmp_path))
    assert list(built) == list(NODES)
    assert all(callable(node) for node in built.values())


def test_the_supervisor_keeps_its_names() -> None:
    assert (supervisor.Services, supervisor.State) == (nodes.Services, nodes.State)


def test_the_compiled_graph_has_the_same_nodes(tmp_path: Path) -> None:
    graph = supervisor.build_graph(services(tmp_path), InMemorySaver())
    assert sorted(set(graph.nodes) - {"__start__"}) == sorted(NODES)
