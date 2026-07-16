"""CG gift/technique availability service (#2426).

Character creation's magic stage lets a player pick a Gift (from their chosen
Tradition) and then techniques for that Gift, pooled from two curated authoring
tables: the (path, gift) starter set (``PathGiftGrant``, #1579) and the
(tradition, gift) signature set (``TraditionGiftGrant``, #2426). This module is
the read-only availability seam the CG catalog and pick-budget validators
consume — it mints no rows (contrast with ``services.path_magic.grant_path_magic``,
which mints ``CharacterGift``/``CharacterTechnique`` rows on a live path crossing).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch

from world.magic.models.grants import PathGiftGrant, TraditionGiftGrant
from world.magic.models.techniques import Technique
from world.magic.types.cg_catalog import TechniqueOptions

if TYPE_CHECKING:
    from world.classes.models import Path
    from world.magic.models.gifts import Gift, Tradition


def get_technique_options(path: Path, gift: Gift, tradition: Tradition) -> TechniqueOptions:
    """The pool U signature availability set for one (path, gift, tradition) pick.

    ``pool`` comes from the path's curated starter set (``PathGiftGrant``);
    ``signature`` comes from the tradition's curated signature set
    (``TraditionGiftGrant``). Either grant row may be absent (no authored row for
    that combination), in which case that half of the pool is simply empty.
    """
    technique_qs = Technique.objects.select_related("effect_type")

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
                "signature_techniques",
                queryset=technique_qs,
                to_attr="cached_signature_techniques",
            )
        )
        .first()
    )

    pool = path_grant.cached_starter_techniques if path_grant else []
    signature = tradition_grant.cached_signature_techniques if tradition_grant else []
    return TechniqueOptions(pool=pool, signature=signature)


def get_gift_options(tradition: Tradition, path: Path) -> list[Gift]:
    """Gifts pickable under ``tradition`` that have >=1 technique available for ``path``.

    A gift with an authored ``TraditionGiftGrant`` row but zero combined
    (pool U signature) techniques for this path has nothing to pick and is
    excluded. Resolves both grant tables in two queries total — no per-gift
    query loop.
    """
    technique_qs = Technique.objects.select_related("effect_type")

    tradition_grants = list(
        TraditionGiftGrant.objects.filter(tradition=tradition)
        .select_related("gift")
        .prefetch_related(
            Prefetch(
                "signature_techniques",
                queryset=technique_qs,
                to_attr="cached_signature_techniques",
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
        if pool_counts.get(grant.gift_id, 0) or grant.cached_signature_techniques
    ]
