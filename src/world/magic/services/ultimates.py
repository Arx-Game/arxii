"""The Audere ultimate reveal and choice (#4098).

Reveal state is derived on read: a reveal is open while Audere or Audere Majora
holds, the character is in a COMBAT engagement, nothing is readied, and at least
one card exists. No offer row exists to clean up.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction

from world.covenants.constants import RoleArchetype
from world.magic.constants import AudereCeremony, GiftKind, UltimateCardKind, UltimateSource
from world.magic.types.ultimates import (
    AudereUltimateState,
    UltimateReveal,
    UltimateRevealCard,
    UltimateRevealGroup,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.classes.models import Path
    from world.companions.models import Companion
    from world.magic.models import Gift, KnownUltimate, Technique
    from world.worship.models import WorshippedBeing

logger = logging.getLogger(__name__)

_CATEGORY_ORDER = (RoleArchetype.SWORD, RoleArchetype.SHIELD, RoleArchetype.CROWN)
_KEY_SEP = ":"


def floor_ultimate_check(result: CheckResult, technique: Technique | None) -> CheckResult:
    """An ultimate never fails (#4147): raise a failed outcome to the lowest success.

    A roll with no technique behind it (a joust, a passive declaration) is never floored.

    Only the outcome changes; the points stay as rolled. Damage, conditions and success
    bands all read ``outcome``, so they all see the floored result.
    """
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    if technique is None or not technique.is_ultimate:
        return result
    if result.outcome is not None and result.outcome.success_level >= 1:
        return result
    floor = CheckOutcome.objects.filter(success_level__gte=1).order_by("success_level").first()
    if floor is None:
        return result
    return dataclasses.replace(result, outcome=floor)


@dataclass(frozen=True)
class _Pool:
    source: str
    source_id: int
    techniques: tuple[Technique, ...]
    path: Path | None = None
    gift: Gift | None = None
    being: WorshippedBeing | None = None
    companion: Companion | None = None


def active_ceremony(character: ObjectDB) -> str | None:  # noqa: OBJECTDB_PARAM - condition target
    """AUDERE_MAJORA when the Majora condition holds, else AUDERE when Audere holds."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.audere import (  # noqa: PLC0415
        AUDERE_CONDITION_NAME,
        AUDERE_MAJORA_CONDITION_NAME,
    )

    names = set(
        ConditionInstance.objects.filter(
            target=character,
            condition__name__in=[AUDERE_CONDITION_NAME, AUDERE_MAJORA_CONDITION_NAME],
        ).values_list("condition__name", flat=True)
    )
    if AUDERE_MAJORA_CONDITION_NAME in names:
        return AudereCeremony.AUDERE_MAJORA
    if AUDERE_CONDITION_NAME in names:
        return AudereCeremony.AUDERE
    return None


def _ordered(techniques: Iterable[Technique]) -> tuple[Technique, ...]:
    return tuple(sorted(techniques, key=lambda t: (t.level, t.name, t.pk)))


def _owned_pools(sheet: CharacterSheet) -> list[_Pool]:
    from world.magic.models import CharacterGift, PathGiftGrant  # noqa: PLC0415
    from world.progression.selectors import current_path_for_character  # noqa: PLC0415

    path = current_path_for_character(sheet.character)
    if path is None:
        return []
    major_ids = CharacterGift.objects.filter(
        character=sheet, gift__kind=GiftKind.MAJOR
    ).values_list("gift_id", flat=True)
    grants = list(
        PathGiftGrant.objects.filter(path=path, gift_id__in=major_ids)
        .select_related("gift")
        .order_by("gift__name", "pk")
    )
    links = PathGiftGrant.ultimate_techniques.through.objects.filter(
        pathgiftgrant_id__in=[g.pk for g in grants], technique__is_ultimate=True
    ).select_related("technique")
    by_grant: dict[int, list[Technique]] = {}
    for link in links:
        by_grant.setdefault(link.pathgiftgrant_id, []).append(link.technique)
    return [
        _Pool(UltimateSource.OWNED, g.pk, _ordered(by_grant.get(g.pk, [])), path=path, gift=g.gift)
        for g in grants
    ]


def _owned_known_pools(sheet: CharacterSheet) -> list[_Pool]:
    """Every KNOWN ultimate, grouped by the (Path x Gift) grant that offers it,
    regardless of the character's CURRENT path (#4098 fix round 1, I1).

    An owned ultimate the character has already discovered must stay listed (and
    choosable) through every later Audere/Majora even after a Crossing moves them
    off the path that originally offered it -- decisions 4 and 12. The gate is
    "gift still held as MAJOR", not "grant belongs to the current path": a
    ``KnownUltimate`` whose technique sits in any ``PathGiftGrant.ultimate_techniques``
    for a MAJOR-held gift qualifies, from any Path. Batched: known-technique ids (1
    query) + one through-table join (1 query, with the MAJOR-gift-id and
    known-technique-id filters both compiled as nested subqueries) -- no query
    inside a loop. A technique still offered by the character's CURRENT path's own
    grant is naturally deduplicated by ``_pools``'s cross-pool ``seen`` set, so it
    is never double-listed.
    """
    from world.magic.models import CharacterGift, KnownUltimate, PathGiftGrant  # noqa: PLC0415

    known_ids = set(
        KnownUltimate.objects.filter(character=sheet).values_list("technique_id", flat=True)
    )
    if not known_ids:
        return []
    major_gift_ids = CharacterGift.objects.filter(
        character=sheet, gift__kind=GiftKind.MAJOR
    ).values_list("gift_id", flat=True)
    links = (
        PathGiftGrant.ultimate_techniques.through.objects.filter(
            pathgiftgrant__gift_id__in=major_gift_ids,
            technique_id__in=known_ids,
            technique__is_ultimate=True,
        )
        .select_related("pathgiftgrant__path", "pathgiftgrant__gift", "technique")
        .order_by(
            "pathgiftgrant__path__name",
            "pathgiftgrant__gift__name",
            "pathgiftgrant_id",
            "technique_id",
        )
    )
    # Deterministic tie-break when more than one grant offers the same known
    # technique: the first one in (path name, gift name, grant pk) order.
    seen_techniques: set[int] = set()
    grant_by_pk: dict[int, PathGiftGrant] = {}
    techniques_by_grant: dict[int, list[Technique]] = {}
    for link in links:
        if link.technique_id in seen_techniques:
            continue
        seen_techniques.add(link.technique_id)
        grant = link.pathgiftgrant
        grant_by_pk[grant.pk] = grant
        techniques_by_grant.setdefault(grant.pk, []).append(link.technique)
    return [
        _Pool(
            UltimateSource.OWNED,
            grant_pk,
            _ordered(techs),
            path=grant_by_pk[grant_pk].path,
            gift=grant_by_pk[grant_pk].gift,
        )
        for grant_pk, techs in techniques_by_grant.items()
    ]


def _patron_pools(sheet: CharacterSheet) -> list[_Pool]:
    from world.worship.models import WorshippedBeing  # noqa: PLC0415
    from world.worship.services import active_patronage_for  # noqa: PLC0415

    beings = sorted({s.being for s in active_patronage_for(sheet)}, key=lambda b: (b.name, b.pk))
    links = WorshippedBeing.ultimate_techniques.through.objects.filter(
        worshippedbeing_id__in=[b.pk for b in beings], technique__is_ultimate=True
    ).select_related("technique")
    by_being: dict[int, list[Technique]] = {}
    for link in links:
        by_being.setdefault(link.worshippedbeing_id, []).append(link.technique)
    return [
        _Pool(UltimateSource.PATRON, b.pk, _ordered(by_being.get(b.pk, [])), being=b)
        for b in beings
    ]


def _companion_pools(sheet: CharacterSheet) -> list[_Pool]:
    from world.companions.models import Companion, CompanionArchetype  # noqa: PLC0415

    companions = list(
        Companion.objects.filter(owner=sheet, released_at__isnull=True)
        .select_related("archetype")
        .order_by("name", "pk")
    )
    links = CompanionArchetype.ultimate_techniques.through.objects.filter(
        companionarchetype_id__in={c.archetype_id for c in companions},
        technique__is_ultimate=True,
    ).select_related("technique")
    by_archetype: dict[int, list[Technique]] = {}
    for link in links:
        by_archetype.setdefault(link.companionarchetype_id, []).append(link.technique)
    return [
        _Pool(
            UltimateSource.COMPANION,
            c.pk,
            _ordered(by_archetype.get(c.archetype_id, [])),
            companion=c,
        )
        for c in companions
    ]


def _gift_pools(sheet: CharacterSheet) -> list[_Pool]:
    from world.magic.models import CharacterGift, Gift  # noqa: PLC0415

    gifts = sorted(
        {
            row.gift
            for row in CharacterGift.objects.filter(
                character=sheet, gift__kind=GiftKind.MINOR
            ).select_related("gift")
        },
        key=lambda g: (g.name, g.pk),
    )
    links = Gift.ultimate_techniques.through.objects.filter(
        gift_id__in=[g.pk for g in gifts], technique__is_ultimate=True
    ).select_related("technique")
    by_gift: dict[int, list[Technique]] = {}
    for link in links:
        by_gift.setdefault(link.gift_id, []).append(link.technique)
    return [
        _Pool(UltimateSource.GIFT, g.pk, _ordered(by_gift.get(g.pk, [])), gift=g)
        for g in gifts
        if by_gift.get(g.pk)
    ]


def _pools(sheet: CharacterSheet) -> list[_Pool]:
    """Every source pool, a technique appearing in an earlier pool dropped from later ones."""
    seen: set[int] = set()
    pools: list[_Pool] = []
    every_pool = (
        _owned_pools(sheet)
        + _owned_known_pools(sheet)
        + _patron_pools(sheet)
        + _companion_pools(sheet)
        + _gift_pools(sheet)
    )
    for pool in every_pool:
        fresh = tuple(t for t in pool.techniques if t.pk not in seen)
        seen.update(t.pk for t in fresh)
        pools.append(dataclasses.replace(pool, techniques=fresh))
    return pools


def _category_key(pool: _Pool, category: str) -> str:
    return _KEY_SEP.join((UltimateCardKind.CATEGORY, pool.source, str(pool.source_id), category))


def _build_reveal(sheet: CharacterSheet, ceremony: str) -> UltimateReveal | None:
    """Assemble the reveal; None when there is no card (decision 15 fallback)."""
    from world.magic.audere import AudereThreshold  # noqa: PLC0415
    from world.magic.models import KnownUltimate  # noqa: PLC0415
    from world.progression.models import TechniqueKnownRequirement  # noqa: PLC0415
    from world.progression.services.spends import (  # noqa: PLC0415
        exclude_unmet_technique_requirements,
    )

    threshold = AudereThreshold.objects.cached_singleton()
    if threshold is None:
        return None
    pools = _pools(sheet)
    every = [t for pool in pools for t in pool.techniques]
    known_ids = set(
        KnownUltimate.objects.filter(character=sheet).values_list("technique_id", flat=True)
    )
    unknown = [t for t in every if t.pk not in known_ids]
    allowed_ids = {t.pk for t in exclude_unmet_technique_requirements(sheet.character, unknown)}
    # A dict comprehension keeps the LAST value written per key, and the queryset
    # below is ordered ascending by the required technique's level/name/pk - so when
    # an upgrade technique has more than one qualifying TechniqueKnownRequirement row
    # (several known prior ultimates it could be shown as an upgrade of), the
    # highest-ordered one (by level, then name, then pk) is the one that survives
    # into `upgrade_of` and is shown on the UPGRADE card (#4098 final review item 8).
    upgrade_of = {
        req.technique_id: req.required_technique
        for req in TechniqueKnownRequirement.objects.filter(
            technique_id__in=allowed_ids, required_technique_id__in=known_ids, is_active=True
        )
        .select_related("required_technique")
        .order_by("required_technique__level", "required_technique__name", "required_technique__pk")
    }

    groups: list[UltimateRevealGroup] = []
    for pool in pools:
        cards: list[UltimateRevealCard] = [
            UltimateRevealCard(
                choice_key=f"{UltimateCardKind.KNOWN}{_KEY_SEP}{t.pk}",
                kind=UltimateCardKind.KNOWN,
                category=t.archetype_alignment,
                label=threshold.label_for_category(t.archetype_alignment),
                technique=t,
            )
            for t in pool.techniques
            if t.pk in known_ids
        ]
        cards.extend(
            UltimateRevealCard(
                choice_key=f"{UltimateCardKind.UPGRADE}{_KEY_SEP}{t.pk}",
                kind=UltimateCardKind.UPGRADE,
                category=t.archetype_alignment,
                label=threshold.label_for_category(t.archetype_alignment),
                technique=t,
                upgrade_of=upgrade_of[t.pk],
            )
            for t in pool.techniques
            if t.pk in upgrade_of
        )
        hidden = {
            t.archetype_alignment
            for t in pool.techniques
            if t.pk in allowed_ids and t.pk not in upgrade_of
        }
        cards.extend(
            UltimateRevealCard(
                choice_key=_category_key(pool, category),
                kind=UltimateCardKind.CATEGORY,
                category=category,
                label=threshold.label_for_category(category),
            )
            for category in _CATEGORY_ORDER
            if category in hidden
        )
        if cards:
            groups.append(
                UltimateRevealGroup(
                    source=pool.source,
                    source_id=pool.source_id,
                    cards=tuple(cards),
                    path=pool.path,
                    gift=pool.gift,
                    being=pool.being,
                    companion=pool.companion,
                )
            )
    if not groups:
        return None
    return UltimateReveal(
        ceremony=ceremony,
        framing_text=threshold.reveal_framing_text,
        groups=tuple(groups),
        sheet=sheet,
    )


def _in_combat(sheet: CharacterSheet) -> bool:
    from world.mechanics.constants import EngagementType  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    return CharacterEngagement.objects.filter(
        character_id=sheet.pk, engagement_type=EngagementType.COMBAT
    ).exists()


def _has_readied(sheet: CharacterSheet) -> bool:
    from world.magic.models import KnownUltimate  # noqa: PLC0415

    return KnownUltimate.objects.filter(character=sheet, readied=True).exists()


def ultimate_reveal_for(sheet: CharacterSheet) -> UltimateReveal | None:
    """The open reveal, or None (no ceremony, not in combat, already chosen, no cards)."""
    ceremony = active_ceremony(sheet.character)
    if ceremony is None or not _in_combat(sheet) or _has_readied(sheet):
        return None
    return _build_reveal(sheet, ceremony)


def has_reveal_cards(sheet: CharacterSheet) -> bool:
    """Whether accepting Audere now would show this character anything (offer framing).

    Gated on the same COMBAT engagement check as `ultimate_reveal_for` (#4098 final
    review item 5): without it, a challenge or mission Audere offer with cards in a
    character's pools showed the reveal framing sentence even though no reveal would
    ever follow acceptance - the reveal itself only ever opens in combat.
    """
    return _in_combat(sheet) and _build_reveal(sheet, AudereCeremony.AUDERE) is not None


def _resolve_card(sheet: CharacterSheet, reveal: UltimateReveal, choice_key: str) -> Technique:
    from world.magic.exceptions import UltimateChoiceUnavailable  # noqa: PLC0415
    from world.magic.models import KnownUltimate  # noqa: PLC0415
    from world.progression.services.spends import (  # noqa: PLC0415
        exclude_unmet_technique_requirements,
    )

    for group, card in reveal.flat_cards():
        if card.choice_key != choice_key:
            continue
        if card.technique is not None:
            return card.technique
        pool = next(
            p for p in _pools(sheet) if (p.source, p.source_id) == (group.source, group.source_id)
        )
        known_ids = set(
            KnownUltimate.objects.filter(character=sheet).values_list("technique_id", flat=True)
        )
        upgrade_ids = {c.technique.pk for c in group.cards if c.kind == UltimateCardKind.UPGRADE}
        candidates = [
            t
            for t in pool.techniques
            if t.archetype_alignment == card.category
            and t.pk not in known_ids
            and t.pk not in upgrade_ids
        ]
        allowed = exclude_unmet_technique_requirements(sheet.character, candidates)
        if allowed:
            return allowed[0]  # already (level, name, pk) ordered
    raise UltimateChoiceUnavailable


@transaction.atomic
def choose_ultimate(sheet: CharacterSheet, choice_key: str) -> KnownUltimate:
    """Reveal + ready the chosen ultimate for this Audere (decisions 2, 4)."""
    from world.achievements.discovery import fire_first_discoveries  # noqa: PLC0415
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.magic.audere_majora import AudereMajoraCrossing  # noqa: PLC0415
    from world.magic.exceptions import UltimateRevealClosed  # noqa: PLC0415
    from world.magic.models import KnownUltimate  # noqa: PLC0415

    locked = CharacterSheet.objects.select_for_update().get(pk=sheet.pk)
    reveal = ultimate_reveal_for(locked)
    if reveal is None:
        raise UltimateRevealClosed
    technique = _resolve_card(locked, reveal, choice_key)
    crossing = None
    if reveal.ceremony == AudereCeremony.AUDERE_MAJORA:
        crossing = (
            AudereMajoraCrossing.objects.filter(character_sheet=locked).order_by("-pk").first()
        )
    try:
        with transaction.atomic():
            known, created = KnownUltimate.objects.get_or_create(
                character=locked,
                technique=technique,
                defaults={"crossing": crossing, "readied": True},
            )
            if not created:
                known.readied = True
                known.save(update_fields=["readied"])
    except IntegrityError as exc:
        # one_readied_ultimate_per_character: a race slipped a second readied row
        # past the _has_readied gate above. Surface the same clean refusal a
        # same-request double-submit gets, never a raw IntegrityError (#4098 fix
        # round 1, M2).
        raise UltimateRevealClosed from exc
    transaction.on_commit(lambda: _route_ultimate_chosen(locked, technique))
    if created:
        fire_first_discoveries(locked, [technique])
    return known


def _route_ultimate_chosen(sheet: CharacterSheet, technique: Technique) -> None:
    """The reveal's pick is a narratable Audere moment for the scene GM (#4101).

    The subject exclusion (the choosing character is never addressed about
    their own pick) now lives inside ``route_narratable_event`` itself (#4101
    fix round 2, ruling R7-1) -- this just calls the plain candidate path (no
    ``candidates=``).

    The scene lookup and ``route_narratable_event`` call run inside their own
    ``transaction.atomic()`` (#4101 fix round 2, ruling R7-2/R7-3) -- that is
    the savepoint that actually contains a ``DatabaseError`` here, matching the
    shape of ``_announce_surge``/``_route_crossing`` even though this one fires
    via ``transaction.on_commit`` (the enclosing transaction has already
    committed by the time it runs). ``_deliver()`` is a no-op -- no authored
    default line exists for an ultimate pick (#4101) -- kept as an explicit
    function rather than a bare ``pass`` so this stays the same shape as its
    two siblings if one is ever authored.
    """
    from django.db import DatabaseError  # noqa: PLC0415

    from world.gm.constants import GMPromptKind  # noqa: PLC0415
    from world.gm.prompt_services import route_narratable_event  # noqa: PLC0415
    from world.gm.types import NarratableEvent  # noqa: PLC0415
    from world.scenes.models import Scene  # noqa: PLC0415

    def _deliver() -> None:
        return

    try:
        with transaction.atomic():
            scene = Scene.objects.active_for_room(sheet.character.location).first()
            prompts = route_narratable_event(
                NarratableEvent(
                    kind=GMPromptKind.AUDERE_ULTIMATE,
                    scene=scene,
                    character_sheet=sheet,
                    technique=technique,
                ),
            )
    except DatabaseError:
        logger.exception(
            "Ultimate-choice routing failed to create GM prompts for sheet %s (#4101).",
            sheet.pk,
        )
        prompts = []
    if not prompts:
        _deliver()


def readied_ultimate(sheet: CharacterSheet) -> KnownUltimate | None:
    """This Audere's pick, castable only while the ceremony holds (decision 4)."""
    from world.magic.models import KnownUltimate  # noqa: PLC0415

    if active_ceremony(sheet.character) is None:
        return None
    return (
        KnownUltimate.objects.filter(character=sheet, readied=True)
        .select_related("technique", "technique__action_template")
        .first()
    )


def clear_readied_ultimate(sheet: CharacterSheet) -> None:
    """Clear any readied pick for this character (a stale Audere's end, a Crossing)."""
    from world.magic.models import KnownUltimate  # noqa: PLC0415

    # Iterate + save rather than a bulk .update(): a bulk update leaves any
    # cached idmapper KnownUltimate instance stale (sharedmemory-model skill).
    # At most one row exists, by the one_readied_ultimate_per_character constraint.
    for known in KnownUltimate.objects.filter(character=sheet, readied=True):
        known.readied = False
        known.save(update_fields=["readied"])


def castable_technique_named(sheet: CharacterSheet, name: str) -> Technique | None:
    """A known technique by name, else this Audere's readied ultimate by name."""
    from world.magic.models import CharacterTechnique  # noqa: PLC0415

    link = (
        CharacterTechnique.objects.filter(character=sheet, technique__name__iexact=name)
        .select_related("technique")
        .first()
    )
    if link is not None:
        return link.technique
    readied = readied_ultimate(sheet)
    if readied is not None and readied.technique.name.lower() == name.lower():
        return readied.technique
    return None


def audere_ultimate_state(sheet: CharacterSheet) -> AudereUltimateState:
    """Owner-facing Audere state: open reveal, readied pick, deferred-death line."""
    from world.magic.audere import AudereThreshold  # noqa: PLC0415
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    pending = CharacterVitals.objects.filter(
        character_sheet=sheet, death_certain_pending=True
    ).exists()
    threshold = AudereThreshold.objects.cached_singleton()
    death_text = threshold.deferred_death_text if pending and threshold is not None else ""
    return AudereUltimateState(
        reveal=ultimate_reveal_for(sheet),
        readied=readied_ultimate(sheet),
        deferred_death_text=death_text,
    )
