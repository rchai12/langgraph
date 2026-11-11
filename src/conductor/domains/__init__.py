from conductor.config import Settings
from conductor.registry import Domain

DOMAINS: tuple[Domain, ...] = ()


def registered(settings: Settings) -> tuple[Domain, ...]:
    found = DOMAINS
    if settings.mcp_command("finances") is not None:
        from conductor.domains.finance import DOMAIN as finance_domain

        found = (*found, finance_domain)
    if settings.demo_on:
        from conductor.domains.demo import DOMAIN as demo_domain

        found = (*found, demo_domain)
    return found
