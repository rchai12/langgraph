import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from conductor.contracts import Contract

ActionKind = Literal["tool", "agent"]
Effect = Literal["read", "propose", "write", "implement"]

_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_TARGET = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_KINDS = ("tool", "agent")
_EFFECTS = ("read", "propose", "write", "implement")
_PHRASE = re.compile(r"^[a-z0-9]+(?: [a-z0-9]+){0,5}$")

RESERVED_DOMAIN = "unknown"
PREFIX_RULE = "prefix"
MAX_PHRASES = 20


@dataclass(frozen=True)
class McpServer:
    name: str
    env: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    name: str
    description: str
    kind: ActionKind
    target: str
    effect: Effect
    args: type[Contract]
    result: type[Contract]
    server: str | None = None


@dataclass(frozen=True)
class Rule:
    name: str
    phrases: tuple[str, ...]


@dataclass(frozen=True)
class Domain:
    name: str
    description: str
    actions: tuple[Action, ...]
    rules: tuple[Rule, ...] = ()
    servers: tuple[McpServer, ...] = ()


class RegistryError(Exception):
    pass


class NotRegistered(LookupError):
    pass


class Registry:
    def __init__(self, domains: Sequence[Domain]) -> None:
        seen: set[str] = set()
        servers: dict[str, str] = {}
        for domain in domains:
            _check_domain(domain, seen, servers)
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


def _check_domain(domain: Domain, seen: set[str], servers: dict[str, str]) -> None:
    if _NAME.fullmatch(domain.name) is None:
        raise RegistryError(f"domain {domain.name}: not a valid name")
    if domain.name == RESERVED_DOMAIN:
        raise RegistryError(f"domain {domain.name}: the name is reserved")
    if domain.name in seen:
        raise RegistryError(f"domain {domain.name}: declared twice")
    seen.add(domain.name)
    if _bad_length(domain.description):
        raise RegistryError(f"domain {domain.name}: description must be 1 to 200 characters")
    _check_servers(domain, servers)
    if not domain.actions:
        raise RegistryError(f"domain {domain.name}: has no actions")
    seen_actions: set[str] = set()
    known = {server.name for server in domain.servers}
    for action in domain.actions:
        _check_action(domain.name, action, seen_actions, known)
    _check_rules(domain.name, domain.rules)


def _check_servers(domain: Domain, declared: dict[str, str]) -> None:
    seen: set[str] = set()
    for server in domain.servers:
        where = f"server {domain.name}.{server.name}"
        if _NAME.fullmatch(server.name) is None:
            raise RegistryError(f"{where}: not a valid name")
        if server.name in seen:
            raise RegistryError(f"{where}: declared twice")
        seen.add(server.name)
        earlier = declared.get(server.name)
        if earlier is not None:
            raise RegistryError(f"{where}: also declared by {earlier}")
        declared[server.name] = domain.name
        for number, name in enumerate(server.env, start=1):
            if _ENV_NAME.fullmatch(name) is None or name.startswith("CONDUCTOR_"):
                raise RegistryError(f"{where}: environment name {number} is not valid")


def _check_action(domain_name: str, action: Action, seen: set[str], servers: set[str]) -> None:
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
    if action.server is not None and action.server not in servers:
        raise RegistryError(f"{where}: no server {action.server} in this domain")
    if action.kind == "tool" and action.server is None and servers:
        raise RegistryError(f"{where}: a tool action of a domain with servers names one")
    if action.kind != "tool" and action.server is not None:
        raise RegistryError(f"{where}: only a tool action names a server")


def _check_rules(domain_name: str, rules: tuple[Rule, ...]) -> None:
    seen: set[str] = set()
    for rule in rules:
        rule_id = f"{domain_name}.{rule.name}"
        where = f"rule {rule_id}"
        if _NAME.fullmatch(rule.name) is None:
            raise RegistryError(f"{where}: not a valid name")
        if rule.name == PREFIX_RULE:
            raise RegistryError(f"{where}: the name is reserved")
        if len(rule_id) > 64:
            raise RegistryError(f"{where}: the id is longer than 64 characters")
        if rule.name in seen:
            raise RegistryError(f"{where}: declared twice")
        seen.add(rule.name)
        if len(rule.phrases) < 1 or len(rule.phrases) > MAX_PHRASES:
            raise RegistryError(f"{where}: needs 1 to 20 phrases")
        for number, phrase in enumerate(rule.phrases, start=1):
            if len(phrase) > 64 or _PHRASE.fullmatch(phrase) is None:
                raise RegistryError(
                    f"{where}: phrase {number} must be 1 to 6 lowercase words"
                    " of at most 64 characters"
                )
