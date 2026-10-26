"""CG gift/technique availability service (#2426).

Character creation's magic stage lets a player pick a Major Gift (any Tradition may
teach any of them, #4659) and then techniques for that Gift. Two curated authoring tables decide
which (#4555): the (path, gift) list (``PathGiftGrant.starter_techniques``, #1579)
holds the techniques for that Path and Gift, and the (tradition, gift) list
(``TraditionGiftGrant.special_techniques``, #2426) restricts. A technique no
Tradition grant lists is open to every Tradition; a technique one or more
Tradition grants list is open only to those Traditions. A technique is offered
only on the Paths whose list holds it, Tradition or not.

This module is the read-only availability seam the CG catalog and pick-budget
validators consume; it mints no rows. ``tradition_listings`` and
``offered_to_tradition`` are the restriction half of the rule, shared with
``services.path_magic.grant_path_magic`` (which mints
``CharacterGift``/``CharacterTechnique`` rows on a live path crossing) and the
Required content dashboard.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db.models import Prefetch, Q, QuerySet

from world.magic.constants import GiftKind
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


def tradition_listings(gift_ids: Iterable[int] | None = None) -> dict[int, frozenset[int]]:
    """Technique pk -> pks of the Traditions whose grant lists it (#4555).

    A technique absent from the result is listed by no Tradition grant and is open
    to every Tradition. One query; ``gift_ids`` narrows it to those gifts' grants, so a
    narrowed and an unnarrowed read agree on every row a grant holds.
    """
    through = TraditionGiftGrant.special_techniques.through
    rows = through.objects.all()
    if gift_ids is not None:
        rows = rows.filter(traditiongiftgrant__gift_id__in=list(gift_ids))
    listed: dict[int, set[int]] = {}
    for technique_id, tradition_id in rows.values_list(
        "technique_id", "traditiongiftgrant__tradition_id"
    ):
        listed.setdefault(technique_id, set()).add(tradition_id)
    return {technique_id: frozenset(ids) for technique_id, ids in listed.items()}


def offered_to_tradition(
    technique_id: int, tradition_id: int | None, listings: dict[int, frozenset[int]]
) -> bool:
    """Whether a member of ``tradition_id`` may be offered the technique (#4555).

    True when no Tradition grant lists the technique, or this Tradition's does.
    ``tradition_id`` None (no Tradition) is offered only unlisted techniques.
    ``listings`` is :func:`tradition_listings`' result.
    """
    listed_by = listings.get(technique_id)
    return listed_by is None or tradition_id in listed_by


def get_technique_options(
    path: Path,
    gift: Gift,
    tradition: Tradition | None,
    *,
    include_unready: bool = False,
    exclude_gated: bool = False,
) -> TechniqueOptions:
    """Return the ready technique pool for one CG pick.

    Both halves come from the Path's list for the Gift (``PathGiftGrant``), since a
    technique is offered only on its Paths (#4555). ``pool`` holds the ones no
    Tradition grant lists (open to every Tradition); ``tradition`` holds the ones
    ``tradition``'s grant lists. A technique another Tradition's grant lists is in
    neither. No authored ``PathGiftGrant`` for the combination means both are empty.

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
    if path_grant is None:
        return TechniqueOptions()

    listings = tradition_listings([gift.pk])
    tradition_id = tradition.pk if tradition is not None else None
    path_techniques = path_grant.cached_starter_techniques
    return TechniqueOptions(
        pool=[technique for technique in path_techniques if technique.pk not in listings],
        tradition=[
            technique
            for technique in path_techniques
            if tradition_id in listings.get(technique.pk, frozenset())
        ],
    )


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
    """Major Gifts pickable under ``tradition`` with >=1 technique available for ``path``.

    Every Tradition may teach every Major Gift (#4659): a ``TraditionGiftGrant`` row
    marks a Gift the Tradition favors, it no longer gates the pick. A Gift is offered
    when ``path``'s list for it holds a technique offered to ``tradition`` (listed by
    no Tradition grant, or by this one's, #4555). "Available" is
    ``cg_takeable_techniques``, the same rule the technique picker applies, so a gift
    whose pool holds only unready, ultimate or gated techniques is not offered with an
    empty picker behind it (#4545). A fixed query count, no per-gift query loop.
    """
    path_grants = list(
        PathGiftGrant.objects.filter(path=path, gift__kind=GiftKind.MAJOR)
        .select_related("gift")
        .prefetch_related(
            Prefetch(
                "starter_techniques",
                queryset=cg_takeable_techniques(),
                to_attr="cached_starter_techniques",
            )
        )
    )
    listings = tradition_listings([grant.gift_id for grant in path_grants])
    offered = [
        grant.gift
        for grant in path_grants
        if any(
            offered_to_tradition(technique.pk, tradition.pk, listings)
            for technique in grant.cached_starter_techniques
        )
    ]
    return sorted(offered, key=lambda gift: (gift.name, gift.pk))
