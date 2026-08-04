"""Resolve authored ``Resonance`` rows for seeders (#2967).

Seeders regularly need *a* Resonance to hang config off — a reference
Corruption condition, a cascade-tagged demo room, a relationship pull chain.
Before #2967 each one named its own ("Fervor", "Reflection", "Wild Hunt",
"Web of Spiders", "Light", "Sanctity", "Radiance", "Dissolution") and pushed
it through ``authored_or_sample``, so invented resonances landed in the dev
database and shipped back out of the next content export looking authored.

The canonical set is the 24 Latin-ish resonances in the content repo, in 12
opposed pairs, and **no seeder may add to it**. Seeders ask for resonances by
*affinity* instead, and skip the config that depends on one when the content
repo has authored none. Ordering by name keeps a re-press deterministic — the
same row every time, so ``get_or_create`` config stays idempotent.
"""

from __future__ import annotations

from world.magic.models import Resonance


def authored_resonances(affinity_name: str | None = None) -> list[Resonance]:
    """Every authored Resonance, optionally narrowed to one affinity."""
    queryset = Resonance.objects.all()
    if affinity_name is not None:
        queryset = queryset.filter(affinity__name=affinity_name)
    return list(queryset.order_by("name"))


def first_authored_resonance(affinity_name: str) -> Resonance | None:
    """The first authored Resonance of an affinity, or ``None`` if it has none."""
    return Resonance.objects.filter(affinity__name=affinity_name).order_by("name").first()
