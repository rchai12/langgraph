from conductor.config import Settings
from conductor.registry import Domain

DOMAINS: tuple[Domain, ...] = ()


def registered(settings: Settings) -> tuple[Domain, ...]:
    if not settings.demo_on:
        return DOMAINS
    from conductor.domains.demo import DOMAIN

    return (*DOMAINS, DOMAIN)
