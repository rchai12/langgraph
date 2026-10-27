import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from conductor.contracts import Contract

ActionKind = Literal["tool", "agent"]
Effect = Literal["read", "propose", "write", "implement"]

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_TARGET = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_KINDS = ("tool", "agent")
_EFFECTS = ("read", "propose", "write", "implement")


@dataclass(frozen=True)
class Action:
    name: str
    description: str
    kind: ActionKind
    target: str
    effect: Effect
    args: type[Contract]
    result: type[Contract]


@dataclass(frozen=True)
class Domain:
    name: str
    description: str
    actions: tuple[Action, ...]


class RegistryError(Exception):
    pass


class NotRegistered(LookupError):
    pass


class Registry:
    def __init__(self, domains: Sequence[Domain]) -> None:
        seen: set[str] = set()
        for domain in domains:
            _check_domain(domain, seen)
        self._domains = tuple(domains)
        self._by_name = {domain.name: domain for domain in self._domains}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(domain.name for domain in self._domains)

    def domain(self, name: str) -> Domain:
        found = self._by_name.get(name)
        if found is None:
            raise NotRegistered(f"no domain {name}")
        return found

    def action(self, full_name: str) -> Action:
        if "." not in full_name:
            raise NotRegistered(f"no action {full_name}")
        domain_name, action_name = full_name.split(".", 1)
        try:
            found = self.domain(domain_name)
        except NotRegistered:
            raise NotRegistered(f"no action {full_name}") from None
        for item in found.actions:
            if item.name == action_name:
                return item
        raise NotRegistered(f"no action {full_name}")


def _bad_length(text: str) -> bool:
    return len(text) < 1 or len(text) > 200


def _is_contract(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, Contract)


def _check_domain(domain: Domain, seen: set[str]) -> None:
    if _NAME.fullmatch(domain.name) is None:
        raise RegistryError(f"domain {domain.name}: not a valid name")
    if domain.name in seen:
        raise RegistryError(f"domain {domain.name}: declared twice")
    seen.add(domain.name)
    if _bad_length(domain.description):
        raise RegistryError(f"domain {domain.name}: description must be 1 to 200 characters")
    if not domain.actions:
        raise RegistryError(f"domain {domain.name}: has no actions")
    seen_actions: set[str] = set()
    for action in domain.actions:
        _check_action(domain.name, action, seen_actions)


def _check_action(domain_name: str, action: Action, seen: set[str]) -> None:
    where = f"action {domain_name}.{action.name}"
    if _NAME.fullmatch(action.name) is None:
        raise RegistryError(f"{where}: not a valid name")
    if action.name in seen:
        raise RegistryError(f"{where}: declared twice")
    seen.add(action.name)
    if _bad_length(action.description):
        raise RegistryError(f"{where}: description must be 1 to 200 characters")
    if action.kind not in _KINDS:
        raise RegistryError(f"{where}: kind must be tool or agent")
    if action.effect not in _EFFECTS:
        raise RegistryError(f"{where}: effect must be read, propose, write, or implement")
    if _TARGET.fullmatch(action.target) is None:
        raise RegistryError(f"{where}: target is not a valid name")
    if not _is_contract(action.args):
        raise RegistryError(f"{where}: args must be a Contract")
    if not _is_contract(action.result):
        raise RegistryError(f"{where}: result must be a Contract")
    if action.effect == "implement" and action.kind != "agent":
        raise RegistryError(f"{where}: implement needs an agent action")
