"""CG gift/technique availability service (#2426).

Character creation's magic stage lets a player pick a Gift (from their chosen
Tradition) and then techniques for that Gift, pooled from two curated authoring
tables: the (path, gift) starter set (``PathGiftGrant``, #1579) and the
(tradition, gift) special technique set (``TraditionGiftGrant``, #2426). This
module is the read-only availability seam the CG catalog and pick-budget
validators consume — it mints no rows (contrast with
``services.path_magic.grant_path_magic``, which mints
``CharacterGift``/``CharacterTechnique`` rows on a live path crossing).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch, Q

from world.magic.models.grants import PathGiftGrant, TraditionGiftGrant
from world.magic.models.techniques import Technique
from world.magic.types.cg_catalog import TechniqueOptions
from world.species.models import SpeciesGiftGrant

if TYPE_CHECKING:
    from world.classes.models import Path
    from world.magic.models.gifts import Gift, Tradition
    from world.species.models import Species


def get_technique_options(
    path: Path, gift: Gift, tradition: Tradition, *, include_unready: bool = False
) -> TechniqueOptions:
    """Return the ready technique pool for one CG pick.

    ``pool`` comes from the path's curated starter set (``PathGiftGrant``);
    ``tradition`` comes from the tradition's special technique set
    (``TraditionGiftGrant``). Either grant row may be absent (no authored row
    for that combination), in which case that half of the pool is simply empty.

    A technique without an action template is unfinished and is not offered as
    a CG pick. ``include_unready`` is reserved for validation, which needs to
    distinguish an unavailable technique from an unfinished one when reporting
    a stale or tampered selection.
    """
    technique_qs = Technique.objects.select_related("effect_type")
    if not include_unready:
        technique_qs = technique_qs.filter(action_template__isnull=False)

    path_grant = (
        PathGiftGrant.objects.filter(path=path, gift=gift)
        .prefetch_related(
            Prefetch(
                "starter_techniques", queryset=technique_qs, to_attr="cached_starter_techniques"
            )
        )
        .first()
    )
    tradition_grant = (
        TraditionGiftGrant.objects.filter(tradition=tradition, gift=gift)
        .prefetch_related(
            Prefetch(
                "special_techniques",
                queryset=technique_qs,
                to_attr="cached_special_techniques",
            )
        )
        .first()
    )

    pool = path_grant.cached_starter_techniques if path_grant else []
    tradition_techniques = tradition_grant.cached_special_techniques if tradition_grant else []
    return TechniqueOptions(pool=pool, tradition=tradition_techniques)


def get_species_technique_options(species: Species | None) -> list[Technique]:
    """Return techniques belonging to the gifts granted by a species.

    A species receives its own grants plus inheritable grants from every ancestor.
    An empty result is valid while a species gift is still unwritten.
    """
    if species is None:
        return []

    lineage = species.lineage
    own_species = lineage[0]
    ancestor_species = lineage[1:]
    grant_filter = Q(species_id=own_species.id) | Q(
        species_id__in=[ancestor.id for ancestor in ancestor_species], inheritable=True
    )
    gift_ids = SpeciesGiftGrant.objects.filter(grant_filter).values_list("gift_id", flat=True)
    return list(
        Technique.objects.filter(gift_id__in=gift_ids, action_template__isnull=False)
        .select_related("effect_type")
        .order_by("name", "id")
    )


def get_gift_options(tradition: Tradition, path: Path) -> list[Gift]:
    """Gifts pickable under ``tradition`` that have >=1 technique available for ``path``.

    A gift with an authored ``TraditionGiftGrant`` row but zero combined
    (pool U tradition) techniques for this path has nothing to pick and is
    excluded. Resolves both grant tables in two queries total — no per-gift
    query loop.
    """
    technique_qs = Technique.objects.select_related("effect_type").filter(
        action_template__isnull=False
    )

    tradition_grants = list(
        TraditionGiftGrant.objects.filter(tradition=tradition)
        .select_related("gift")
        .prefetch_related(
            Prefetch(
                "special_techniques",
                queryset=technique_qs,
                to_attr="cached_special_techniques",
            )
        )
    )
    if not tradition_grants:
        return []

    gift_ids = [grant.gift_id for grant in tradition_grants]
    path_grants = PathGiftGrant.objects.filter(path=path, gift_id__in=gift_ids).prefetch_related(
        Prefetch("starter_techniques", queryset=technique_qs, to_attr="cached_starter_techniques")
    )
    pool_counts = {grant.gift_id: len(grant.cached_starter_techniques) for grant in path_grants}

    return [
        grant.gift
        for grant in tradition_grants
        if pool_counts.get(grant.gift_id, 0) or grant.cached_special_techniques
    ]
