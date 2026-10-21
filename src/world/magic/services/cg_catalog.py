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

from django.db.models import Prefetch, Q, QuerySet

from world.magic.models.grants import PathGiftGrant, TraditionGiftGrant
from world.magic.models.techniques import Technique
from world.magic.types.cg_catalog import TechniqueOptions
from world.species.models import SpeciesGiftGrant

if TYPE_CHECKING:
    from world.classes.models import Path
    from world.magic.models.gifts import Gift, Tradition
    from world.species.models import Species


def _gated_technique_ids() -> set[int]:
    """Technique pks carrying at least one active requirement row (#4097).

    One query per concrete ``AbstractUnlockRequirement`` subclass (a small, fixed
    set via ``concrete_requirement_types()``) — never one per technique. The
    resulting id set is applied with a single ``exclude(pk__in=...)`` by the caller.
    """
    from world.progression.services.spends import concrete_requirement_types  # noqa: PLC0415

    gated: set[int] = set()
    for req_type in concrete_requirement_types():
        gated.update(
            req_type.objects.filter(technique__isnull=False, is_active=True).values_list(
                "technique_id", flat=True
            )
        )
    return gated


def cg_technique_queryset(
    *, include_unready: bool = False, exclude_gated: bool = False
) -> QuerySet[Technique]:
    """The techniques character creation may put in a gift's pool, as one rule (#4545).

    Never an ultimate; with an action template unless ``include_unready``; and
    with no active requirement row when ``exclude_gated``. ``get_technique_options``
    and ``get_gift_options`` filter their pools through this queryset, and so does
    the Required content dashboard (``web/admin/tuning/required_content.py``), so
    the dashboard cannot count a technique the player is never shown. Add a CG
    readiness condition here, never beside a caller.
    """
    technique_qs = Technique.objects.select_related("effect_type").filter(is_ultimate=False)
    if exclude_gated:
        technique_qs = technique_qs.exclude(pk__in=_gated_technique_ids())
    if not include_unready:
        technique_qs = technique_qs.filter(action_template__isnull=False)
    return technique_qs


def cg_takeable_techniques() -> QuerySet[Technique]:
    """Techniques a new character can take at character creation (#4545).

    The rule the technique picker applies (``get_technique_options(...,
    exclude_gated=True)``): ready, not an ultimate, not gated by a requirement.
    A gift's pool that holds none of these offers the player nothing to pick.
    """
    return cg_technique_queryset(exclude_gated=True)


def get_technique_options(
    path: Path,
    gift: Gift,
    tradition: Tradition,
    *,
    include_unready: bool = False,
    exclude_gated: bool = False,
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

    ``exclude_gated=True`` (#4097) additionally excludes any technique carrying an
    active requirement row (``TechniqueKnownRequirement``, ``GiftHeldRequirement``,
    ...) — a draft has no character yet to evaluate
    ``check_requirements_for_technique`` against, so CG picks skip gated
    techniques outright rather than offering a pick nobody can finalize.
    Pass ``exclude_gated=True`` only from character-creation call sites that
    model what a new character can pick — ``character_creation.validators``/
    ``views`` and the starting-kit analytics report
    (``web/admin/tuning/technique_analytics.py``, which explicitly models "the
    picks a new character gets"). Any **in-play** caller — Academy TRAIN's
    eligibility check (``npc_services.effects._technique_available_to_learner``)
    is the one that exists today — keeps the default ``exclude_gated=False``:
    an in-play learner may already meet the prerequisite, and
    ``charge_and_learn``'s own per-character ``check_requirements_for_technique``
    call is the correct gate for them, not a blanket catalog-level exclusion.
    """
    technique_qs = cg_technique_queryset(
        include_unready=include_unready, exclude_gated=exclude_gated
    )

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


def get_species_technique_options(
    species: Species | None, *, include_unready: bool = False
) -> list[Technique]:
    """Return techniques belonging to the gifts granted by a species.

    A species receives its own grants plus inheritable grants from every ancestor.
    An empty result is valid while a species gift is still unwritten. Set
    ``include_unready`` for validation or finalization paths that need to
    classify a stale selection rather than treat it as unavailable.
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
    technique_qs = cg_technique_queryset(include_unready=include_unready)
    return list(technique_qs.filter(gift_id__in=gift_ids).order_by("name", "id"))


def get_gift_options(tradition: Tradition, path: Path) -> list[Gift]:
    """Gifts pickable under ``tradition`` that have >=1 technique available for ``path``.

    A gift with an authored ``TraditionGiftGrant`` row but zero combined
    (pool U tradition) techniques for this path has nothing to pick and is
    excluded. "Available" is ``cg_takeable_techniques``, the same rule the
    technique picker applies, so a gift whose pool holds only unready, ultimate
    or gated techniques is not offered with an empty picker behind it (#4545).
    Resolves both grant tables in two queries total — no per-gift query loop.
    """
    technique_qs = cg_takeable_techniques()

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
