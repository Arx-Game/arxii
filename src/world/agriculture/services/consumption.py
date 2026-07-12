"""Weekly domain consumption tick for the agriculture system."""

from __future__ import annotations

import logging

from django.db import transaction

from world.agriculture.models import FoodStockpile
from world.agriculture.services.production import get_food_config

logger = logging.getLogger(__name__)


def domain_consumption_tick() -> dict[str, int]:
    """Weekly cron: each domain's population consumes food from its stockpile.

    For each ``Domain``:
    - If no ``FoodStockpile`` row exists: treats as perpetual shortage —
      applies unrest/prosperity penalties.
    - If stockpile exists: computes ``needed = population × consumption_per_capita``.
      Sufficient → subtract needed, no penalty. Insufficient → subtract what's
      available (→ 0), apply penalties.

    Per-domain atomic; exceptions isolated.

    Returns:
        Telemetry dict with ``domains_processed`` and ``shortages``.
    """
    from world.societies.houses.models import Domain  # noqa: PLC0415
    from world.societies.houses.services import maybe_open_unrest_crisis  # noqa: PLC0415

    config = get_food_config()

    domains = list(Domain.objects.all())
    domains_processed = 0
    shortages = 0
    crises_opened = 0

    for domain in domains:
        try:
            had_shortage = _consume_domain(domain, config)
            # After the food-driven civ update, simmering unrest may boil over (#2238).
            crisis = maybe_open_unrest_crisis(domain)
        except Exception:
            logger.exception(
                "Domain consumption tick failed for domain %s; continuing.",
                domain.pk,
            )
            continue
        domains_processed += 1
        if had_shortage:
            shortages += 1
        if crisis is not None:
            crises_opened += 1

    return {
        "domains_processed": domains_processed,
        "shortages": shortages,
        "crises_opened": crises_opened,
    }


@transaction.atomic
def _consume_domain(domain, config) -> bool:
    """Consume food for one domain. Returns True if a shortage occurred."""
    needed = domain.population * config.consumption_per_capita

    try:
        stockpile = domain.food_stockpile
    except FoodStockpile.DoesNotExist:
        # No stockpile → perpetual shortage.
        _apply_shortage(domain, config)
        return True

    if stockpile.stored >= needed:
        stockpile.stored -= needed
        stockpile.save(update_fields=["stored"])
        _apply_recovery(domain, config)
        return False

    # Shortage: consume what's available, apply penalties.
    stockpile.stored = 0
    stockpile.save(update_fields=["stored"])
    _apply_shortage(domain, config)
    return True


def _apply_shortage(domain, config) -> None:
    """Apply unrest/prosperity penalties for a food shortage."""
    domain.unrest = min(100, domain.unrest + config.shortage_unrest_penalty)
    domain.prosperity = max(0, domain.prosperity - config.shortage_prosperity_penalty)
    domain.save(update_fields=["unrest", "prosperity"])


def _apply_recovery(domain, config) -> None:
    """A well-fed week relaxes unrest and recovers prosperity toward equilibrium (#2238).

    Unrest always eases toward 0; prosperity only climbs back *up to* the
    equilibrium, so a single missed harvest isn't permanently punitive — but
    improvements that pushed prosperity above the equilibrium are left untouched.
    """
    unrest = max(0, domain.unrest - config.recovery_unrest_relief)
    prosperity = domain.prosperity
    if prosperity < config.prosperity_equilibrium:
        prosperity = min(
            config.prosperity_equilibrium, prosperity + config.recovery_prosperity_gain
        )
    if unrest != domain.unrest or prosperity != domain.prosperity:
        domain.unrest = unrest
        domain.prosperity = prosperity
        domain.save(update_fields=["unrest", "prosperity"])
