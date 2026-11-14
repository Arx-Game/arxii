"""The unsettled reading, the focus check, and the conversion offer a deed opens.

A character is unsettled (#5123) when an affinity other than their main one has grown
past who they are: its share of their aura (their lifetime resonance) stands over its
settled share by more than the tolerance. A Sineater's Mire burden is read apart and has
its own allowance. ``drift_for`` is that reading, on the true aura; ``check_resonance_focus``
runs once per cast, before the cast's modifiers are gathered, and on a failed focus roll
applies (or deepens) the authored conflict condition, whose own check modifier then reaches
the same cast's roll. Its numbers live in ``DriftConfig``.

Atoning (#4733, #5123) is read on lifetime, so it works even when the excess was already
spent: ``drift_holdings`` is resonance held in a non-main affinity that has grown past who
the character is. A deed (a grant from a ``DEED_GAIN_SOURCES`` source) that grows a
resonance of the character's main affinity, made in a live scene by a character who is
unsettled and has convertible drift, opens a ``DriftConversionOffer`` for that scene and adds
to the cap of converting drift toward the resonance the deed grew. The offer lapses when the
scene finishes. The other exit, ``accept_aura_change``, moves who the character is to where
they have got to.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from math import ceil
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from world.magic.constants import DEED_GAIN_SOURCES, ComponentMode
from world.magic.exceptions import ConversionMappingError, NotUnsettledError
from world.magic.models.aura import CharacterResonance
from world.magic.models.drift import (
    DriftConfig,
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionConfig,
)
from world.magic.models.motifs import MotifResonanceAssociation
from world.magic.services.conversion import conversion_pair
from world.magic.types.drift import (
    AcceptAuraResult,
    DriftReading,
    FocusOutcome,
    QualifyingComponent,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models import Technique
    from world.magic.models.affinity import Affinity, Resonance
    from world.magic.models.aura import CharacterAura
    from world.magic.models.gain import ResonanceGrant
    from world.scenes.models import Scene

_ONE_HUNDRED = Decimal(100)
# (exclusive upper bound as a fraction of the whole, words); the first bound a share is
# under wins, and a share past the last reads "nearly all".
_SHARE_WORDS: tuple[tuple[Decimal, str], ...] = (
    (Decimal("0.08"), "a trace"),
    (Decimal("0.18"), "a tenth"),
    (Decimal("0.28"), "a fifth"),
    (Decimal("0.4"), "a third"),
    (Decimal("0.58"), "half"),
    (Decimal("0.8"), "most"),
)
_SHARE_WORDS_NONE = "none"
_SHARE_WORDS_MOST = "nearly all"


def get_drift_config() -> DriftConfig:
    """Get-or-create the drift config singleton (pk=1)."""
    cfg = DriftConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = DriftConfig.objects.get_or_create(pk=1)
    return cfg


def _main_affinity(aura: CharacterAura | None) -> Affinity | None:
    """The affinity holding the largest settled share (ties: lowest affinity id), or None.

    None when there is no aura or none of its shares has been settled yet.
    """
    if aura is None:
        return None
    settled = [share for share in aura.cached_shares if share.settled_percent > 0]
    if not settled:
        return None
    return min(settled, key=lambda share: (-share.settled_percent, share.affinity_id)).affinity


def _share_of(part: int, whole: int) -> Decimal:
    """``part`` as a percent of ``whole``; 0 when there is no whole."""
    return Decimal(part) * _ONE_HUNDRED / Decimal(whole) if whole else Decimal(0)


def drift_for(sheet: CharacterSheet) -> DriftReading:
    """Whether ``sheet``'s character is unsettled, and by how much (#5123).

    Read on the true aura: a worn alternate self does not change who the character is.
    An affinity's own share is its lifetime resonance less the part taken from the Mire,
    as a percent of all the character's own lifetime resonance; its Mire share is the
    Mire part as a percent of all lifetime resonance. For every affinity other than the
    main one (the largest settled share), the excess is how far its own share stands past
    its settled share plus ``unsettled_tolerance_percent``, plus how far its Mire share
    stands past ``mire_allowance_percent``. ``steps_past`` is the total excess in
    ``unsettled_step_percent`` bands, rounded up.

    A character with no aura, or an aura with nothing settled yet, reads zero.
    """
    aura = sheet.aura_or_none
    main = _main_affinity(aura)
    if aura is None or main is None:
        return DriftReading(
            steps_past=0,
            main_affinity=None,
            leading_excess_resonance=None,
            excess_percent=Decimal(0),
            mire_share_percent=Decimal(0),
            own_shares={},
            settled_shares={},
        )

    cfg = get_drift_config()
    settled_shares = {share.affinity_id: share.settled_percent for share in aura.cached_shares}
    rows = list(
        CharacterResonance.objects.filter(character_sheet=sheet).select_related(
            "resonance__affinity"
        )
    )
    total_lifetime = sum(row.lifetime_earned for row in rows)
    total_own = total_lifetime - sum(row.mire_lifetime for row in rows)
    own_lifetime: dict[int, int] = {}
    mire_lifetime: dict[int, int] = {}
    for row in rows:
        affinity_id = row.resonance.affinity_id
        own_lifetime[affinity_id] = own_lifetime.get(affinity_id, 0) + (
            row.lifetime_earned - row.mire_lifetime
        )
        mire_lifetime[affinity_id] = mire_lifetime.get(affinity_id, 0) + row.mire_lifetime
    own_shares = {aff: _share_of(life, total_own) for aff, life in own_lifetime.items()}

    excess_by_affinity: dict[int, Decimal] = {}
    own_excess_points: dict[int, int] = {}
    mire_excess_points: dict[int, int] = {}
    for affinity_id in own_shares.keys() | mire_lifetime.keys() | settled_shares.keys():
        if affinity_id == main.pk:
            continue
        past_settled = (
            own_shares.get(affinity_id, Decimal(0))
            - settled_shares.get(affinity_id, Decimal(0))
            - cfg.unsettled_tolerance_percent
        )
        past_allowance = (
            _share_of(mire_lifetime.get(affinity_id, 0), total_lifetime)
            - cfg.mire_allowance_percent
        )
        excess = max(Decimal(0), past_settled) + max(Decimal(0), past_allowance)
        if excess > 0:
            excess_by_affinity[affinity_id] = excess
        # The same excess as lifetime points, rounded up so a sliver past the line can
        # still be atoned for: what the rite may convert away from this affinity.
        if past_settled > 0:
            own_excess_points[affinity_id] = ceil(past_settled * total_own / _ONE_HUNDRED)
        if past_allowance > 0:
            mire_excess_points[affinity_id] = ceil(past_allowance * total_lifetime / _ONE_HUNDRED)

    excess_total = sum(excess_by_affinity.values(), Decimal(0))
    leading: Resonance | None = None
    if excess_by_affinity:
        worst = min(excess_by_affinity, key=lambda aff: (-excess_by_affinity[aff], aff))
        in_worst = [row for row in rows if row.resonance.affinity_id == worst]
        leading = min(in_worst, key=lambda row: (-row.lifetime_earned, row.resonance_id)).resonance
    return DriftReading(
        steps_past=ceil(excess_total / cfg.unsettled_step_percent),
        main_affinity=main,
        leading_excess_resonance=leading,
        excess_percent=excess_total,
        mire_share_percent=_share_of(sum(mire_lifetime.values()), total_lifetime),
        own_shares=own_shares,
        settled_shares=settled_shares,
        own_excess_points=own_excess_points,
        mire_excess_points=mire_excess_points,
    )


def share_in_words(percent: Decimal) -> str:
    """A share of a whole, in words, never a number (#5123).

    ``percent`` is 0-100. The same scale as the sheet's ``shareInWords``
    (``frontend/src/magic/aura.ts``), so the aura reads the same in
    every surface.
    """
    if percent <= 0:
        return _SHARE_WORDS_NONE
    part = percent / _ONE_HUNDRED
    for ceiling, words in _SHARE_WORDS:
        if part < ceiling:
            return words
    return _SHARE_WORDS_MOST


def unsettled_line(reading: DriftReading) -> str:
    """The sentence naming what has made the character unsettled; blank when settled."""
    leading = reading.leading_excess_resonance
    if reading.steps_past <= 0 or leading is None:
        return ""
    return f"Your {leading.name} has grown strong enough to make you unsettled."


def check_resonance_focus(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - rolls, conditions and messages take the character
    technique: Technique,
) -> FocusOutcome | None:
    """Roll the caster's focus while she is unsettled, once per cast.

    ``use_technique`` calls it for every cast, after anima is deducted and before
    ``resolve_fn`` gathers the cast's check modifiers, so a condition applied here
    reaches the same cast's roll. Only being unsettled calls for the roll: a pull
    outside her main affinity adds no steps of its own (#5123).

    Returns None, rolling nothing, when the config's focus check type or conflict
    condition is unset (the Required content dashboard lists both) or when there are
    no steps. On a failed roll (success level below 1) the conflict condition is
    applied at ``steps + (1 - success_level)`` severity, so a worse roll never costs
    less; if she already holds it, its severity advances by one instead.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        apply_condition,
        get_condition_instance,
    )
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    cfg = get_drift_config()
    if cfg.focus_check_type_id is None or cfg.conflict_condition_id is None:
        return None
    try:
        sheet = character.sheet_data
    except ObjectDoesNotExist:
        return None
    reading = drift_for(sheet)
    steps = reading.steps_past
    if steps <= 0:
        return None

    difficulty = cfg.focus_base_difficulty + steps * cfg.focus_difficulty_per_step
    lines: list[str] = []
    if reading.leading_excess_resonance is not None:
        lines.append(f"{unsettled_line(reading)} You must keep your focus.")
        character.msg(lines[0])
    result = perform_check_with_modifiers(
        character,
        cfg.focus_check_type,
        difficulty,
        extra_traits=activity_skill_terms(MagicActivity.KEEPING_FOCUS),
    )
    success_level = result.success_level
    if success_level >= 1:
        return FocusOutcome(
            success_level=success_level, steps=steps, applied_severity=0, lines=tuple(lines)
        )

    condition = cfg.conflict_condition
    existing = get_condition_instance(character, condition)
    if existing is not None:
        applied = 1
        advance_condition_severity(existing, applied)
    else:
        applied = steps + (1 - success_level)
        apply_condition(
            character,
            condition,
            severity=applied,
            source_technique=technique,
        )
    lost_line = f"You lose your focus as you work {technique.name}: {condition.name}."
    lines.append(lost_line)
    character.msg(lost_line)
    return FocusOutcome(
        success_level=success_level, steps=steps, applied_severity=applied, lines=tuple(lines)
    )


def get_drift_correction_config() -> DriftCorrectionConfig:
    """Lazy-create the DriftCorrectionConfig singleton at pk=1."""
    config = DriftCorrectionConfig.objects.cached_singleton()
    if config is None:
        config, _ = DriftCorrectionConfig.objects.get_or_create(pk=1)
    return config


def own_affinity(sheet: CharacterSheet) -> Affinity | None:
    """The character's main affinity (the largest settled share), or None.

    None when the sheet has no aura yet or nothing in it is settled. Never raises.
    """
    return _main_affinity(sheet.aura_or_none)


def drift_holdings(sheet: CharacterSheet) -> list[CharacterResonance]:
    """Resonance held in an affinity that has grown past who the character is.

    Read on lifetime, not balance, so a streak whose points were already spent still
    counts (#5123): every resonance of a non-main affinity with lifetime earned, in an
    affinity whose excess (own, or the Mire's past its allowance) is above zero. Largest
    lifetime first. Empty when the character is settled or has no main affinity.
    """
    own = own_affinity(sheet)
    if own is None:
        return []
    reading = drift_for(sheet)
    rows = (
        CharacterResonance.objects.filter(character_sheet=sheet, lifetime_earned__gt=0)
        .exclude(resonance__affinity=own)
        .select_related("resonance__affinity")
        .order_by("-lifetime_earned", "resonance_id")
    )
    return [row for row in rows if reading.convertible_points(row.resonance.affinity_id) > 0]


@transaction.atomic
def settle_shares(sheet: CharacterSheet) -> dict[int, Decimal]:
    """Set each ``settled_percent`` to the aura's own share now: who she is becomes who she is.

    Recomputes the aura first, so a row exists for every affinity held and the percents sum
    to exactly 100.00 to be settled as they stand, then writes each share's ``settled_percent``
    to its ``percent``. ``steps_past`` reads 0 afterwards. The one settle step both accepting
    the aura's change and a Fall or Redemption use (#5123). Returns affinity id -> settled share.
    """
    from world.magic.services.aura import recompute_aura  # noqa: PLC0415

    recompute_aura(sheet)
    aura = sheet.aura_or_none
    settled: dict[int, Decimal] = {}
    for share in aura.cached_shares if aura is not None else []:
        settled[share.affinity_id] = share.percent
        if share.settled_percent != share.percent:
            share.settled_percent = share.percent
            share.save(update_fields=["settled_percent"])
    return settled


def accept_aura_change(sheet: CharacterSheet) -> AcceptAuraResult:
    """Accept the changes to the aura: who the character is becomes who they have become.

    Refused unless ``sheet`` is unsettled. A Sineater's Mire lifetime becomes their own
    (``mire_lifetime`` is set to 0 on every row), then each ``settled_percent`` is set to
    the resulting own share, so ``steps_past`` is 0 afterwards and the main affinity is the
    largest share. Writes no corruption: Abyssal resonance brings corruption the usual way
    (#5123, rulings 8 and 28).

    Raises:
        NotUnsettledError: The character is not unsettled.
    """
    reading = drift_for(sheet)
    if reading.steps_past <= 0:
        raise NotUnsettledError
    leading = reading.leading_excess_resonance
    grown = leading.affinity if leading is not None else None
    mire_moved = 0
    for row in list(
        CharacterResonance.objects.select_for_update().filter(
            character_sheet=sheet, mire_lifetime__gt=0
        )
    ):
        mire_moved += row.mire_lifetime
        row.mire_lifetime = 0
        row.save(update_fields=["mire_lifetime"])
    settled = settle_shares(sheet)
    aura = sheet.aura_or_none
    close_spent_conversion_offers(sheet)
    return AcceptAuraResult(
        mire_moved=mire_moved,
        main_affinity=_main_affinity(aura),
        grown_affinity=grown,
        settled_shares=settled,
    )


def _has_conversion(source: Affinity, target: Affinity) -> bool:
    try:
        conversion_pair(source, target)
    except ConversionMappingError:
        return False
    return True


def convertible_drift(sheet: CharacterSheet, target: Resonance) -> list[CharacterResonance]:
    """``drift_holdings`` narrowed to rows with an authored conversion into target's affinity."""
    return [
        row
        for row in drift_holdings(sheet)
        if _has_conversion(row.resonance.affinity, target.affinity)
    ]


_OFFER_OPENED_TEXT = "You have grown unsettled. Use |waura|n to see how you can atone."
_OFFER_LAPSED_TEXT = "The chance to atone passes with the scene."


def _tell_non_web(character: ObjectDB, text: str) -> None:
    """Send ``text`` to the character's telnet sessions only.

    Web players learn of an offer from the polled pending endpoint, so a bare ``msg``
    would show them the line twice.
    """
    from world.scenes.interaction_services import send_text_to_non_web  # noqa: PLC0415

    send_text_to_non_web(character, text)


def open_or_extend_conversion_offer(grant: ResonanceGrant) -> DriftConversionOffer | None:
    """Open (or extend) the character's conversion offer for the scene a deed grant happened in.

    Returns None, changing nothing, unless all of these hold: the grant is a deed; it grew a
    resonance of the character's own affinity; the configured ``cap_percent`` is above 0;
    the character has convertible drift toward that resonance; and the character stands in
    a live scene. A deed made outside a live scene opens no offer and is not an error.

    The cap toward the granted resonance grows by ``floor(grant.amount x cap_percent / 100)``,
    and the grant is linked to that cap. Only the grant that creates the cap row is floored
    at 1, so a first small deed still opens a usable cap; a later small deed can add 0. A
    cap therefore never exceeds ``cap_percent / 100`` of the deed points linked to it, plus
    that one floored point.

    A NEW offer or a NEW cap row (a new target resonance) tells the character, once the
    surrounding transaction commits (``grant_resonance`` is atomic); bumping an existing cap
    says nothing.
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    if grant.source not in DEED_GAIN_SOURCES:
        return None
    sheet = grant.character_sheet
    own = own_affinity(sheet)
    if own is None or grant.resonance.affinity_id != own.pk:
        return None
    percent = get_drift_correction_config().cap_percent
    if percent == 0:
        return None
    # The scene lookup is cached on the room, so a character outside a scene costs no
    # query; the drift query below only runs for someone who could hold an offer.
    scene = get_active_scene(sheet.character.location)
    # The room's cached scene can outlive the scene's end; a finished scene is no scene.
    if scene is None or not scene.is_active or scene.is_finished:
        return None
    if not convertible_drift(sheet, grant.resonance):
        return None
    # A decline or a lapse can delete the offer between get_or_create and the lock; one
    # retry then opens a fresh offer instead of writing a cap onto a vanished row.
    for _attempt in range(2):
        with transaction.atomic():
            offer, offer_created = DriftConversionOffer.objects.get_or_create(
                character_sheet=sheet, scene=scene
            )
            # Lock the offer row so concurrent grants for it serialize. A filter, not
            # get(): the identity map would answer get() without the database or the lock.
            if not list(DriftConversionOffer.objects.select_for_update().filter(pk=offer.pk)):
                continue
            _extend_cap(offer, grant, percent, announce=offer_created)
            return offer
    return None


def _extend_cap(
    offer: DriftConversionOffer, grant: ResonanceGrant, percent: int, *, announce: bool
) -> None:
    """Add ``grant`` to the offer's cap toward its resonance, under the offer's row lock."""
    cap, cap_created = DriftConversionCap.objects.get_or_create(
        offer=offer, target_resonance=grant.resonance, defaults={"cap": 0}
    )
    if cap.grants.filter(pk=grant.pk).exists():
        return
    # Read the stored cap, not the cached one: a rolled-back outer transaction can leave
    # the shared instance holding a cap the table never kept.
    stored = DriftConversionCap.objects.filter(pk=cap.pk).values_list("cap", flat=True).get()
    increment = grant.amount * percent // 100
    if cap_created:
        increment = max(1, increment)
    cap.cap = stored + increment
    cap.save(update_fields=["cap"])
    cap.grants.add(grant)
    if announce or cap_created:
        character = offer.character_sheet.character
        transaction.on_commit(lambda: _tell_non_web(character, _OFFER_OPENED_TEXT))


def lapse_conversion_offers(scene: Scene) -> int:
    """Delete every conversion offer the scene opened (their caps go with them).

    Returns how many offers lapsed.
    """
    offers = DriftConversionOffer.objects.filter(scene=scene)
    characters = [
        offer.character_sheet.character
        for offer in offers.select_related("character_sheet__character")
    ]
    lapsed = offers.count()
    offers.delete()
    for character in characters:
        transaction.on_commit(
            lambda character=character: _tell_non_web(character, _OFFER_LAPSED_TEXT)
        )
    return lapsed


def close_spent_conversion_offers(sheet: CharacterSheet) -> int:
    """Delete the caps of ``sheet``'s open offers that have nothing left to convert.

    The one writer that ends an offer early (#5123): a cap whose target has no convertible
    drift behind it is deleted, and an offer left with no cap goes with them. A character
    who is no longer unsettled has no convertible drift, so atoning or accepting that
    settles her closes every offer she holds, while an offer with drift still left to atone
    for stays open. Returns how many offers closed. Called by the rite and by
    ``accept_aura_change``, after they write.
    """
    closed = 0
    for offer in DriftConversionOffer.objects.filter(character_sheet=sheet):
        for cap in list(
            DriftConversionCap.objects.filter(offer=offer).select_related(
                "target_resonance__affinity"
            )
        ):
            if not convertible_drift(sheet, cap.target_resonance):
                cap.delete()
        if not DriftConversionCap.objects.filter(offer=offer).exists():
            offer.delete()
            closed += 1
    return closed


def qualifying_components(
    sheet: CharacterSheet,
    target: Resonance,
    items: Iterable[ItemInstance],
    *,
    min_item_meaning: int | None = None,
) -> list[QualifyingComponent]:
    """The items that count toward a target-resonance offering, each under its first route.

    Three routes, tried in this order: ``MATERIAL`` (the item's template is tied to
    ``target``), ``FACET`` (it carries a live facet that the performer's own motif ties to
    ``target``), and ``KEEPSAKE`` (it means at least ``min_item_meaning`` points to the
    performer; the route is off when that is None). An item qualifies at most once. The list
    is ordered by route (material, facet, keepsake), then as given, so an offering that is
    spent in order burns a plain material before a keepsake. A destroyed or empty item never
    qualifies. One target of ``qualifying_components_by_target``.
    """
    return qualifying_components_by_target(
        sheet, [target], items, min_item_meaning=min_item_meaning
    )[target.pk]


def _component_mode(
    item: ItemInstance,
    target_id: int,
    target_facets: set[int],
    facets_by_item: dict[int, set[int]],
    keepsake_ids: set[int],
) -> ComponentMode | None:
    """Select the strongest qualifying route for an item and target."""
    if item.template.tied_resonance_id == target_id:
        return ComponentMode.MATERIAL
    if facets_by_item.get(item.pk, set()) & target_facets:
        return ComponentMode.FACET
    if item.pk in keepsake_ids:
        return ComponentMode.KEEPSAKE
    return None


def qualifying_components_by_target(
    sheet: CharacterSheet,
    targets: Iterable[Resonance],
    items: Iterable[ItemInstance],
    *,
    min_item_meaning: int | None = None,
) -> dict[int, list[QualifyingComponent]]:
    """``qualifying_components`` for several targets at once, keyed by resonance pk.

    The query count does not grow with the number of targets: one motif-facet query, one
    item-facet query, and (with a keepsake bar) one meaning reading per carried item, read
    once and shared by every target.
    """
    from world.items.models import ItemFacet  # noqa: PLC0415
    from world.items.services.meaning import item_meaning  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    target_list = list(targets)
    live = [item for item in items if item.destroyed_at is None and item.quantity > 0]
    facets_by_target: dict[int, set[int]] = {target.pk: set() for target in target_list}
    for resonance_id, facet_id in MotifResonanceAssociation.objects.filter(
        motif_resonance__motif__character=sheet,
        motif_resonance__resonance_id__in=list(facets_by_target),
    ).values_list("motif_resonance__resonance_id", "facet_id"):
        facets_by_target[resonance_id].add(facet_id)
    all_facet_ids = set().union(*facets_by_target.values())
    facets_by_item: dict[int, set[int]] = {}
    if all_facet_ids and live:
        for item_id, facet_id in ItemFacet.objects.filter(
            item_instance__in=live, facet_id__in=all_facet_ids, removed_at__isnull=True
        ).values_list("item_instance_id", "facet_id"):
            facets_by_item.setdefault(item_id, set()).add(facet_id)
    keepsake_ids: set[int] = set()
    if min_item_meaning is not None:
        config = get_devotion_config()
        keepsake_ids = {
            item.pk
            for item in live
            if item_meaning(item, sheet, config=config).points >= min_item_meaning
        }

    route_rank = {mode: rank for rank, mode in enumerate(ComponentMode)}
    result: dict[int, list[QualifyingComponent]] = {}
    for target in target_list:
        target_facets = facets_by_target[target.pk]
        qualifying: list[QualifyingComponent] = []
        for item in live:
            mode = _component_mode(item, target.pk, target_facets, facets_by_item, keepsake_ids)
            if mode is not None:
                qualifying.append(QualifyingComponent(item=item, mode=mode))
        qualifying.sort(key=lambda component: route_rank[component.mode])
        result[target.pk] = qualifying
    return result
