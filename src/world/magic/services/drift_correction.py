"""The rite of settling: one offering, one roll, every waiting reflection (#5124).

A character who has written reflections (a pose or a journal entry that names a deed, or the
resonance unsettling them, and Embrace or Disown) carries them all out with one rite. The rite
takes one qualifying offering, rolls the configured check with a focus bonus, reads the share
from the rolled tier's ``DriftCorrectionOutcomeShare`` and applies that share to each
reflection:

| Reflection                     | Effect at share s                                        |
| Embrace a deed                 | grant ``deed amount x s x direction rate`` of its        |
|                                | resonance (EMBRACED_DEED); see ``embraced_amount``       |
| Disown a deed                  | convert ``amount x disown_deed_percent x s`` toward the  |
|                                | main affinity; needs no open chance to atone             |
| Embrace the unsettling         | ``accept_aura_change(fraction=s)``                       |
| Disown the unsettling          | convert up to the open cap x s toward the main affinity  |

Everything runs in one transaction. A refusal (no waiting reflection, an unset rite, no
qualifying offering) writes nothing and leaves every reflection waiting. Once the roll
happens the offering is spent whatever the result, and every waiting reflection takes the
rite, even at a share of 0.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Max, QuerySet

from world.checks.services import difficulty_points, perform_check_with_modifiers
from world.items.services.materials import consume_materials
from world.magic.constants import GainSource, ReflectionChoice
from world.magic.exceptions import (
    ConversionMappingError,
    DriftCorrectionNotConfiguredError,
    NotUnsettledError,
    NoWaitingReflectionError,
    RitualComponentError,
)
from world.magic.models.aura import CharacterResonance
from world.magic.models.drift import (
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionConfig,
    DriftCorrectionOutcomeShare,
)
from world.magic.models.reflection import Reflection, SettlingRite
from world.magic.models.resonance_environment import AffinityInteraction
from world.magic.services.conversion import conversion_pair, convert_resonance_amount
from world.magic.services.drift import (
    accept_aura_change,
    close_spent_conversion_offers,
    drift_for,
    get_drift_correction_config,
    own_affinity,
    qualifying_components_by_target,
)
from world.magic.services.reflection import deed_what
from world.magic.services.resonance import grant_resonance
from world.magic.services.ritual_components import (
    resolve_ritual_components,
    target_resonance_meaning_bar,
)
from world.magic.services.touchstone import touchstone_cast_bonus
from world.magic.types.drift import (
    QualifyingComponent,
    ReflectionEffect,
    RiteOffering,
    SettlingRiteResult,
)
from world.mechanics.services import equipment_walk_total
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models.affinity import Resonance
    from world.magic.models.grant import ResonanceGrant
    from world.scenes.models import Scene


RITE_NOT_READY_MESSAGE = DriftCorrectionNotConfiguredError.user_message

_ONE_HUNDRED = Decimal(100)


def outcome_tiers_without_a_share() -> QuerySet[CheckOutcome]:
    """Every ``CheckOutcome`` with no ``DriftCorrectionOutcomeShare`` row.

    The roll can land on any tier, so one missing here leaves the rite unready. The
    Required content probe lists these by name; ``rite_is_ready`` asks whether any exist.
    """
    return CheckOutcome.objects.exclude(
        pk__in=DriftCorrectionOutcomeShare.objects.values("outcome_tier_id")
    )


def rite_is_ready(config: DriftCorrectionConfig | None = None) -> bool:
    """Whether the rite can be performed: a rite, a check type and a share for every tier.

    Costs one query (the share check), and none when the rite or check type is unset.
    While this is false the rite refuses with ``RITE_NOT_READY_MESSAGE``, and every
    surface that shows the rite says that instead of listing an offering. Pass the
    ``config`` the caller already holds to skip fetching it again.
    """
    if config is None:
        config = get_drift_correction_config()
    if config.rite_id is None or config.check_type_id is None:
        return False
    return not outcome_tiers_without_a_share().exists()


def focus_bonus(sheet: CharacterSheet, target: Resonance) -> int:
    """What the character's worn focus adds to the rite's check toward ``target``.

    The equipment walk total on the target's modifier target (0 when it has none) plus
    the touchstone bonus for that resonance (0 when no tied touchstone is worn).
    """
    try:
        modifier_target = target.modifier_target
    except ObjectDoesNotExist:
        modifier_target = None
    walk = 0 if modifier_target is None else equipment_walk_total(sheet, modifier_target)
    return walk + touchstone_cast_bonus(sheet, target)


def max_yield_per_earned_point(config: DriftCorrectionConfig) -> Decimal:
    """The most target resonance one point of deed gain can ever yield through the rite.

    ``cap_percent / 100 x the largest authored pair multiplier x the largest converted
    share``. Tuning keeps this below 1, so correcting drift never out-earns the deed itself.
    It is the per-point rate: a new cap row also opens at a floor of 1 point
    (``open_or_extend_conversion_offer``), once per offer and target resonance, on top of it.
    """
    max_multiplier = AffinityInteraction.objects.filter(
        conversion_multiplier__isnull=False
    ).aggregate(top=Max("conversion_multiplier"))["top"] or Decimal(0)
    max_share = DriftCorrectionOutcomeShare.objects.aggregate(top=Max("converted_share"))[
        "top"
    ] or Decimal(0)
    return Decimal(config.cap_percent) / Decimal(100) * max_multiplier * max_share


# ---------------------------------------------------------------------------
# What a waiting reflection reflects on, and what the rite can offer toward
# ---------------------------------------------------------------------------


def waiting_reflections(sheet: CharacterSheet) -> list[Reflection]:
    """Every reflection of ``sheet`` that no rite has taken yet, oldest first."""
    return list(
        Reflection.objects.filter(character_sheet=sheet, rite__isnull=True).select_related(
            "grant__resonance__affinity",
            "grant__source_kindling_situation",
            "resonance__affinity",
            "interaction",
            "journal_entry",
        )
    )


def reflected_resonance(reflection: Reflection) -> Resonance:
    """The resonance a reflection is about: the deed's, or the unsettling one."""
    if reflection.grant is not None:
        return reflection.grant.resonance
    return reflection.resonance


def main_affinity_rows(sheet: CharacterSheet) -> list[CharacterResonance]:
    """The character's resonances of their main affinity, largest lifetime first."""
    main = own_affinity(sheet)
    if main is None:
        return []
    return list(
        CharacterResonance.objects.filter(character_sheet=sheet, resonance__affinity=main)
        .select_related("resonance__affinity")
        .order_by("-lifetime_earned", "resonance_id")
    )


def rite_resonances(sheet: CharacterSheet, reflections: Iterable[Reflection]) -> list[Resonance]:
    """The resonances the rite moves, which an offering may be tied to.

    Each reflection's own resonance, then (when any reflection disowns, so something converts)
    the character's main-affinity resonances, which conversions turn toward. In that order,
    each once.
    """
    moved: dict[int, Resonance] = {}
    disowns = False
    for reflection in reflections:
        resonance = reflected_resonance(reflection)
        moved.setdefault(resonance.pk, resonance)
        disowns = disowns or reflection.choice == ReflectionChoice.DISOWN
    if disowns:
        for row in main_affinity_rows(sheet):
            moved.setdefault(row.resonance_id, row.resonance)
    return list(moved.values())


def offerings_for(
    sheet: CharacterSheet, reflections: Iterable[Reflection], items: Iterable[ItemInstance]
) -> list[RiteOffering]:
    """The carried ``items`` that count as the rite's offering, each under its first resonance.

    An item qualifies when it counts toward any resonance the rite moves
    (``qualifying_components_by_target`` over them, in ``rite_resonances`` order); it is
    listed once, under the first of those it counts toward, with the worn focus's bonus
    toward that resonance. Empty while the rite is unset.
    """
    config = get_drift_correction_config()
    if config.rite_id is None:
        return []
    resonances = rite_resonances(sheet, reflections)
    by_target = qualifying_components_by_target(
        sheet, resonances, items, min_item_meaning=target_resonance_meaning_bar(config.rite)
    )
    listed: dict[int, RiteOffering] = {}
    for resonance in resonances:
        # The bonus depends on the resonance alone, so it is worked out once per resonance and
        # only when an item is listed under it.
        bonus: int | None = None
        component: QualifyingComponent
        for component in by_target[resonance.pk]:
            if component.item.pk in listed:
                continue
            if bonus is None:
                bonus = focus_bonus(sheet, resonance)
            listed[component.item.pk] = RiteOffering(
                component=component, resonance=resonance, focus_bonus=bonus
            )
    return list(listed.values())


def _resolve_offering(
    config: DriftCorrectionConfig,
    sheet: CharacterSheet,
    components: list[ItemInstance],
    resonances: list[Resonance],
) -> tuple[Resonance, list[tuple[ItemInstance, int]]]:
    """Pick the resonance the offering is tied to and the allocations that pay for it.

    Tries each resonance the rite moves in order and takes the first the offering satisfies,
    spending nothing.

    Raises:
        RitualComponentError: The offering satisfies the rite for none of them.
    """
    refusal: RitualComponentError | None = None
    for resonance in resonances:
        try:
            allocations = resolve_ritual_components(
                ritual=config.rite,
                components=components,
                performer_sheet=sheet,
                resonance_context=resonance,
            )
        except RitualComponentError as exc:
            refusal = exc
            continue
        return resonance, allocations
    raise refusal if refusal is not None else RitualComponentError


# ---------------------------------------------------------------------------
# Applying one reflection at the rite's share
# ---------------------------------------------------------------------------


def open_caps(sheet: CharacterSheet) -> dict[int, int]:
    """Resonance id -> what the character's open chance to atone still allows toward it."""
    return {
        cap.target_resonance_id: cap.cap
        for cap in DriftConversionCap.objects.filter(offer__character_sheet=sheet, cap__gt=0)
    }


def disowns_unsettling(reflections: Iterable[Reflection]) -> bool:
    """Whether any reflection disowns the unsettling resonance itself (not a deed)."""
    return any(r.grant_id is None and r.choice == ReflectionChoice.DISOWN for r in reflections)


def fallback_conversion_target(
    main_rows: list[CharacterResonance], caps: Mapping[int, int] | None = None
) -> Resonance | None:
    """The resonance a conversion turns toward when the offering is not tied to a main-affinity
    one: with open ``caps`` (given when the rite disowns the unsettling resonance), the
    main-affinity resonance with the largest open cap toward it; with none, the character's
    largest main-affinity resonance; or nowhere. The rite and its preview both read it, so what
    the sheet says is where the rite sends it."""
    if not main_rows:
        return None
    if caps:
        best = max(main_rows, key=lambda row: caps.get(row.resonance_id, 0))
        if caps.get(best.resonance_id, 0) > 0:
            return best.resonance
    return main_rows[0].resonance


def _conversion_target(
    sheet: CharacterSheet,
    offered_for: Resonance,
    main_rows: list[CharacterResonance],
    caps: Mapping[int, int] | None = None,
) -> Resonance | None:
    """Where a conversion turns: the offering's own resonance when it is of the main affinity,
    else ``fallback_conversion_target``."""
    main = own_affinity(sheet)
    if main is None:
        return None
    if offered_for.affinity_id == main.pk:
        return offered_for
    return fallback_conversion_target(main_rows, caps)


def _convert(
    sheet: CharacterSheet,
    source: Resonance,
    target: Resonance | None,
    wanted: int,
    *,
    limit_to_excess: bool,
) -> tuple[int, int]:
    """Convert up to ``wanted`` lifetime of ``source`` toward ``target``; return (moved, granted).

    Never raises for what it cannot do: no target, no authored pair or nothing held converts
    nothing. The amount is at most the source's lifetime, and, with ``limit_to_excess``, what
    its affinity stands past who the character is. The Mire's excess converts first.
    """
    if wanted <= 0 or target is None or source.pk == target.pk:
        return 0, 0
    try:
        pair = conversion_pair(source.affinity, target.affinity)
    except ConversionMappingError:
        return 0, 0
    rows = CharacterResonance.objects.filter(character_sheet=sheet, resonance=source)
    list(rows.select_for_update())
    lifetime, row_mire = rows.values_list("lifetime_earned", "mire_lifetime").first() or (0, 0)
    reading = drift_for(sheet)
    amount = min(wanted, lifetime)
    if limit_to_excess:
        amount = min(amount, reading.convertible_points(source.affinity_id, row_mire))
    if amount <= 0:
        return 0, 0
    mire_part = min(amount, reading.mire_excess_points.get(source.affinity_id, 0))
    granted, _ = convert_resonance_amount(
        sheet,
        source_resonance=source,
        target_resonance=target,
        amount=amount,
        multiplier=pair.conversion_multiplier,
        gain_source=GainSource.DRIFT_CORRECTION,
        mire_amount=mire_part,
    )
    return amount, granted


def _turned_line(source: Resonance, target: Resonance, moved: int, granted: int) -> str:
    if granted == 0:
        return f"{moved} {source.name} turned to {target.name}."
    return f"{moved} {source.name} became {granted} {target.name}."


def _open_cap_toward(sheet: CharacterSheet, target: Resonance) -> int:
    """What the character's open chance to atone still allows toward ``target`` (0 if none)."""
    offers = list(DriftConversionOffer.objects.select_for_update().filter(character_sheet=sheet))
    if not offers:
        return 0
    stored = DriftConversionCap.objects.filter(offer__in=offers, target_resonance=target)
    return stored.values_list("cap", flat=True).first() or 0


def _spend_cap(sheet: CharacterSheet, target: Resonance, spent: int) -> None:
    """Shrink the open cap toward ``target`` by ``spent``; an exhausted cap is deleted."""
    cap = DriftConversionCap.objects.filter(
        offer__character_sheet=sheet, target_resonance=target
    ).first()
    if cap is None or spent <= 0:
        return
    remaining = (
        DriftConversionCap.objects.filter(pk=cap.pk).values_list("cap", flat=True).get() - spent
    )
    if remaining > 0:
        cap.cap = remaining
        cap.save(update_fields=["cap"])
    else:
        cap.delete()


def _disown_deed(
    sheet: CharacterSheet,
    reflection: Reflection,
    share: Decimal,
    target: Resonance | None,
    percent: int,
) -> str:
    grant = reflection.grant
    what = deed_what(grant) or f"your {grant.resonance.name}"
    wanted = int(Decimal(grant.amount) * Decimal(percent) / _ONE_HUNDRED * share)
    moved, granted = _convert(sheet, grant.resonance, target, wanted, limit_to_excess=False)
    if moved == 0 or target is None:
        return f"You disown {what}, but the rite turns nothing of it away."
    return f"You disown {what}: {_turned_line(grant.resonance, target, moved, granted)}"


def _disown_unsettling(
    sheet: CharacterSheet, reflection: Reflection, share: Decimal, target: Resonance | None
) -> str:
    source = reflection.resonance
    cap = _open_cap_toward(sheet, target) if target is not None else 0
    moved, granted = _convert(
        sheet, source, target, int(Decimal(cap) * share), limit_to_excess=True
    )
    if moved == 0 or target is None:
        return f"You disown your {source.name}, but the rite turns nothing of it away."
    _spend_cap(sheet, target, moved)
    return f"You disown your {source.name}: {_turned_line(source, target, moved, granted)}"


def embraced_amount(sheet: CharacterSheet, grant: ResonanceGrant, share: Decimal) -> int:
    """What embracing ``grant`` at ``share`` grants, rounded down (#4751).

    The deed's amount times the share. When the deed is of an affinity other than the
    character's main one, also times the direction rate authored for converting the main
    affinity into the deed's: a fall toward the Abyss pays more than the deed was worth and
    a climb pays less, as disowning already does. No main affinity, the same affinity or no
    authored pair leaves the rate at 1. The rite and its preview both call this.
    """
    rate = Decimal(1)
    main = own_affinity(sheet)
    if main is not None and main.pk != grant.resonance.affinity_id:
        with suppress(ConversionMappingError):
            rate = conversion_pair(main, grant.resonance.affinity).conversion_multiplier
    return int(Decimal(grant.amount) * share * rate)


def _embrace_deed(
    sheet: CharacterSheet, reflection: Reflection, rite: SettlingRite, share: Decimal
) -> str:
    grant = reflection.grant
    what = deed_what(grant) or f"your {grant.resonance.name}"
    amount = embraced_amount(sheet, grant, share)
    if amount <= 0:
        return f"You embrace {what}, but the rite carries none of it through."
    grant_resonance(
        sheet,
        grant.resonance,
        amount,
        source=GainSource.EMBRACED_DEED,
        settling_rite=rite,
        reflection=reflection,
    )
    return f"You embrace {what}: your {grant.resonance.name} grows by {amount}."


def _embrace_unsettling(sheet: CharacterSheet, share: Decimal) -> str:
    if share <= 0:
        return "You accept what you have become, but the rite carries none of it through."
    try:
        result = accept_aura_change(sheet, fraction=share)
    except NotUnsettledError:
        return "You are already settled; there is nothing left to accept."
    grown = result.grown_affinity
    more = f"more {grown.name.lower()}" if grown is not None else "who you have become"
    if share >= 1:
        return f"You become {more}." if grown is not None else "You settle into who you are."
    return f"You move part of the way toward being {more}."


def _active_scene(sheet: CharacterSheet) -> Scene | None:
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    scene = get_active_scene(sheet.character.location)
    if scene is None or not scene.is_active or scene.is_finished:
        return None
    return scene


def _apply_reflections(  # noqa: PLR0913 - the rite's inputs, handed on as they are
    sheet: CharacterSheet,
    reflections: list[Reflection],
    rite: SettlingRite,
    share: Decimal,
    target: Resonance | None,
    disown_deed_percent: int,
) -> list[ReflectionEffect]:
    """Apply ``share`` to each reflection: disowned deeds, the disowned unsettling resonance,
    embraced deeds, then accepting last so it settles on everything the rite has done."""
    effects: list[ReflectionEffect] = []

    def run(*, deed: bool, choice: str, apply: Callable[[Reflection], str]) -> None:
        effects.extend(
            ReflectionEffect(reflection.pk, apply(reflection))
            for reflection in reflections
            if (reflection.grant_id is not None) is deed and reflection.choice == choice
        )

    run(
        deed=True,
        choice=ReflectionChoice.DISOWN,
        apply=lambda r: _disown_deed(sheet, r, share, target, disown_deed_percent),
    )
    run(
        deed=False,
        choice=ReflectionChoice.DISOWN,
        apply=lambda r: _disown_unsettling(sheet, r, share, target),
    )
    run(
        deed=True,
        choice=ReflectionChoice.EMBRACE,
        apply=lambda r: _embrace_deed(sheet, r, rite, share),
    )
    run(
        deed=False,
        choice=ReflectionChoice.EMBRACE,
        apply=lambda _r: _embrace_unsettling(sheet, share),
    )
    return effects


@transaction.atomic
def perform_settling_rite(
    sheet: CharacterSheet, *, components: list[ItemInstance]
) -> SettlingRiteResult:
    """Perform the rite of settling: one offering, one roll, every waiting reflection.

    Refuses before anything is written: with no waiting reflection, with the rite unset (or a
    tier with no share), and with an offering that satisfies the rite for no resonance it
    moves. Then it rolls the configured check with ``focus_bonus`` toward the resonance the
    offering is tied to, writes a ``SettlingRite`` holding the outcome and the share, spends
    the offering, and applies the share to each reflection: disowned deeds first, then the
    disowned unsettling resonance (up to the open cap), then embraced deeds, then accepting
    last so it settles on everything the rite has done. Every reflection then takes the rite,
    even at a share of 0.

    Conversions turn toward the main-affinity resonance the offering is tied to, or else (see
    ``fallback_conversion_target``) the main-affinity resonance with the largest open cap when
    the rite disowns the unsettling resonance, else the character's largest main-affinity
    resonance. Nothing below the roll raises: what cannot be
    done (no resonance to turn toward, nothing held to convert, already settled) is a line
    saying so.

    Raises:
        NoWaitingReflectionError: Nothing waits.
        DriftCorrectionNotConfiguredError: Rite, check type or a tier's share is unauthored.
        RitualComponentError: The offering does not satisfy the rite.

    Component ownership is not checked here: the caller (the action or API layer) resolves
    ``components`` from the performer's own inventory before calling.
    """
    reflections = waiting_reflections(sheet)
    if not reflections:
        raise NoWaitingReflectionError
    config = get_drift_correction_config()
    if not rite_is_ready(config):
        raise DriftCorrectionNotConfiguredError

    # Every step that can refuse runs before anything is written: the offering is only chosen
    # here, and spent after the roll. A raise after a write would roll the tables back but
    # leave the shared cached rows (the item's quantity, the resonance balances) ahead of them.
    offered_for, allocations = _resolve_offering(
        config, sheet, components, rite_resonances(sheet, reflections)
    )
    bonus = focus_bonus(sheet, offered_for)
    check = perform_check_with_modifiers(
        sheet.character,
        config.check_type,
        difficulty_points(config.check_difficulty_level),
        extra_modifiers=bonus,
    )
    outcome = check.outcome
    # Safety net: rite_is_ready already refused a table with a missing tier.
    if outcome is None:
        raise DriftCorrectionNotConfiguredError
    share_row = DriftCorrectionOutcomeShare.objects.filter(outcome_tier=outcome).first()
    if share_row is None:
        raise DriftCorrectionNotConfiguredError
    share = share_row.converted_share

    rite = SettlingRite.objects.create(
        character_sheet=sheet, scene=_active_scene(sheet), outcome=outcome, share=share
    )
    consume_materials(allocations)

    target = _conversion_target(
        sheet,
        offered_for,
        main_affinity_rows(sheet),
        open_caps(sheet) if disowns_unsettling(reflections) else None,
    )
    effects = _apply_reflections(
        sheet, reflections, rite, share, target, config.disown_deed_percent
    )

    for reflection in reflections:
        reflection.rite = rite
        reflection.save(update_fields=["rite"])
    close_spent_conversion_offers(sheet)

    return SettlingRiteResult(
        outcome_name=outcome.name,
        success_level=outcome.success_level,
        share=share,
        focus_bonus=bonus,
        effects=tuple(effects),
    )
