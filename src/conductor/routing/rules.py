import re
from dataclasses import dataclass

from conductor.contracts import Route
from conductor.registry import PREFIX_RULE, Registry

_PREFIX = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]{0,31}):(.*)$", re.DOTALL)
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class RuleRoute:
    route: Route
    request: str


@dataclass(frozen=True)
class RuleConflict:
    rule_ids: tuple[str, ...]


def words(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(text.lower()))


def match_rules(request: str, registry: Registry) -> RuleRoute | RuleConflict | None:
    found = _PREFIX.fullmatch(request)
    if found is not None:
        name = found.group(1).lower()
        if name in registry.names:
            return RuleRoute(
                Route(domain=name, decided_by="rule", rule_id=f"{name}.{PREFIX_RULE}"),
                found.group(2).strip(),
            )
    tokens = words(request)
    matched: list[str] = []
    for domain_name in registry.names:
        domain = registry.domain(domain_name)
        for rule in domain.rules:
            if any(_contains(tokens, phrase) for phrase in rule.phrases):
                matched.append(f"{domain_name}.{rule.name}")
    if not matched:
        return None
    domains = {rule_id.split(".", 1)[0] for rule_id in matched}
    if len(domains) > 1:
        return RuleConflict(tuple(matched))
    return RuleRoute(
        Route(domain=matched[0].split(".", 1)[0], decided_by="rule", rule_id=matched[0]),
        request,
    )


def _contains(tokens: tuple[str, ...], phrase: str) -> bool:
    wanted = tuple(phrase.split(" "))
    width = len(wanted)
    return any(tokens[start : start + width] == wanted for start in range(len(tokens) - width + 1))
