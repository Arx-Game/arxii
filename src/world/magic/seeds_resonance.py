"""Resolve authored ``Resonance`` rows for seeders (#2967).

Seeders regularly need *a* Resonance to hang config off — a reference
Corruption condition, a cascade-tagged demo room, a reference pull chain.
Before #2967 each one named its own ("Fervor", "Reflection", "Wild Hunt",
"Web of Spiders", "Light", "Sanctity", "Radiance", "Dissolution", "Tideborne")
and pushed it through ``authored_or_sample``, so invented resonances landed in
the dev database and shipped back out of the next content export looking
authored — and, since nobody can claim a resonance that exists only in a
seeder, every feature keyed to one was unreachable.

The canonical set is the 24 Latin-ish resonances in the content repo, in 12
opposed pairs, and **no seeder may add to it**. Seeders ask for resonances by
*affinity* instead, and skip the config that depends on one when the content
repo has authored none.

**Picking one must be stable, not merely deterministic.** "First by name" is
only stable while the catalog is; a second press after new resonances land
would otherwise pick a different row and seed a *second* reference set beside
the first. So ``reference_resonance`` takes the resonance an existing row
already points at, and only falls back to first-by-name when there is no
existing row to follow. The reference set, once placed, stays where it is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.exceptions import AffinityNotConfigured
from world.magic.models import Resonance

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import QuerySet

    from world.magic.models import Affinity


def authored_resonances(affinity: Affinity | None = None) -> list[Resonance]:
    """Every authored Resonance, optionally narrowed to one affinity."""
    queryset = Resonance.objects.all()
    if affinity is not None:
        queryset = queryset.filter(affinity=affinity)
    return list(queryset.order_by("name"))


def first_authored_resonance(affinity: Affinity) -> Resonance | None:
    """The first authored Resonance of an affinity, or ``None`` if it has none."""
    return Resonance.objects.filter(affinity=affinity).order_by("name").first()


def first_canonical_resonance(get_affinity: Callable[[], Affinity]) -> Resonance | None:
    """``first_authored_resonance`` for a canonical affinity getter, ``None`` when unconfigured.

    A database with no Affinity rows yet has no resonance to hang config off either, so the
    seeder skips exactly as it does for an affinity with no authored resonance.
    """
    try:
        affinity = get_affinity()
    except AffinityNotConfigured:
        return None
    return first_authored_resonance(affinity)


def reference_resonance(
    existing: QuerySet,
    *,
    resonance_field: str = "resonance",
    affinity: Affinity | None = None,
) -> Resonance | None:
    """Resolve the resonance a re-runnable reference seed should hang off.

    *existing* is a queryset of whatever rows this seed writes, already narrowed
    to the ones it owns. When it holds a row, that row's resonance is the answer
    — re-pressing the Big Button after the catalog has grown must not seed a
    second reference set beside the first. Otherwise the first authored
    resonance (optionally of *affinity*) is taken, or ``None`` when the
    content repo has authored none.
    """
    placed = existing.values_list(resonance_field, flat=True).first()
    if placed is not None:
        return Resonance.objects.filter(pk=placed).first()
    if affinity is not None:
        return first_authored_resonance(affinity)
    return next(iter(authored_resonances()), None)
