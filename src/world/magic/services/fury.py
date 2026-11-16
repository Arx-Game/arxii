"""Fury lever resolution service (#4738: Fury is surrendering control for intensity).

A Fury tier is a preset amount of control the character surrenders. Her control roll's
outcome picks the share (``FuryDegreeShare``) of the full trade she buys; the trade lands
on her ``CharacterEngagement`` and lasts for the rest of the engagement. The deepest tiers
are Berserk: choosing one applies Berserk whatever the roll.

``resolve_fury`` is the pure computation. ``FuryCast`` (built by ``fury_cast_for``) runs
inside ``use_technique``: it rolls the check and writes the engagement only once the cast's
gates have passed, takes the trade back if the cast is cancelled, and applies Berserk and
tells her when the cast proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from evennia.objects.models import ObjectDB

from world.character_sheets.models import CharacterSheet
from world.magic.models import FuryConfig, FuryDegreeShare, FuryTier, KindledStrengthTier

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.checks.models import CheckOutcome, CheckType
    from world.conditions.models import ConditionTemplate
    from world.magic.models import Resonance

NO_ENGAGEMENT_MESSAGE = "Fury needs something at stake: you are not engaged."


@dataclass(frozen=True)
class FuryResolution:
    """Outcome of a Fury declaration: control surrendered and the intensity it bought."""

    realized_tier: FuryTier | None
    control_surrendered: int
    intensity_gained: int
    berserk_severity: int
    outcome: CheckOutcome | None = None


def _config() -> FuryConfig:
    return FuryConfig.objects.filter(pk=1).first() or FuryConfig()


def _sheet_of(character: CharacterSheet | ObjectDB) -> CharacterSheet:
    return character if isinstance(character, CharacterSheet) else character.sheet_data


def give_in_strength(
    character: CharacterSheet | ObjectDB | None, resonance: Resonance | None
) -> KindledStrengthTier | None:
    """The kindled strength row of the resonance she gives in to, or None.

    None when there is no character or resonance, she does not hold the resonance, or it is
    not kindled now. Read in her live fight and mission (``kindling_context_for``), the same
    context a cast and the "Your resonances" panel read, so the three never disagree. The
    row carries what the trade reads: ``give_in_max_depth``, ``give_in_bonus_percent`` and
    ``give_in_ease_tenths``.
    """
    if character is None or resonance is None:
        return None
    from world.magic.services.kindling import (  # noqa: PLC0415
        kindled_for,
        kindling_context_for,
    )

    sheet = _sheet_of(character)
    if not any(held.resonance_id == resonance.pk for held in sheet.cached_resonances):
        return None
    context = kindling_context_for(sheet)
    return kindled_for(
        sheet, resonance, resolution=context.resolution, mission=context.mission
    ).tier


def provocation_cap(strength: KindledStrengthTier | None) -> int:
    """Ceiling on fury depth: the deepest tier depth the strength row lets her give in.

    0 when she cannot give in (no kindled strength).
    """
    return strength.give_in_max_depth if strength is not None else 0


def provocation_bonus_percent(strength: KindledStrengthTier | None) -> int:
    """Percent the intensity Fury buys grows at this strength (0 when none)."""
    return strength.give_in_bonus_percent if strength is not None else 0


def provocation_ease(strength: KindledStrengthTier | None, at_level: int) -> int:
    """Check-difficulty reduction in points at this strength (0 when none).

    The strength row holds tenths of one level's width; ``at_level`` is the level the base
    check difficulty is read at (the Fury tier's ``base_check_difficulty_level``), so the ease
    is a share of the width of the very level it eases.
    """
    if strength is None:
        return 0
    from world.checks.services import difficulty_step_points  # noqa: PLC0415

    return difficulty_step_points(strength.give_in_ease_tenths, at_level)


def give_in_refusal(
    character: CharacterSheet | ObjectDB, resonance: Resonance | None, tier: FuryTier
) -> str | None:
    """Why she cannot give in to ``resonance`` as deep as ``tier``, or None when she can.

    The one check a declaration (scene, combat, telnet) and a cast make. An unkindled
    resonance, or one she does not hold, is refused in words, never clamped to nothing; a
    tier deeper than the strength allows is refused too, since a Berserk tier is offered only
    where the strength reaches it.
    """
    if resonance is None:
        return "Name the resonance you give in to."
    strength = give_in_strength(character, resonance)
    if strength is None:
        return fury_not_kindled_message(resonance)
    if provocation_cap(strength) < tier.depth:
        return fury_over_cap_message(tier, resonance)
    return None


def clamp_tier(declared_tier: FuryTier, cap: int) -> FuryTier | None:
    """Deepest authored tier with depth <= cap.

    Returns None if cap is 0 or below the shallowest available tier.
    """
    if cap <= 0:
        return None
    if declared_tier.depth <= cap:
        return declared_tier
    return FuryTier.objects.filter(depth__lte=cap).order_by("-depth").first()


def get_fury_config() -> FuryConfig:
    """Public singleton accessor."""
    return _config()


def get_berserk_template() -> ConditionTemplate | None:
    """The condition template that IS Berserk, or ``None`` when unset (#4739).

    Read from ``FuryConfig.berserk_condition`` with one ``cached_singleton()`` read,
    so renaming the template changes nothing. ``None`` means no config row or an
    unset field; the Required content dashboard flags it.
    """
    config = FuryConfig.objects.cached_singleton()
    return None if config is None else config.berserk_condition


def berserk_condition_id() -> int | None:
    """Primary key of the condition template that IS Berserk, or ``None`` when unset.

    Same single ``cached_singleton()`` read as ``get_berserk_template()``, for callers
    that compare ids (``is_berserk``). Guard on ``None`` before filtering a nullable
    column by it: ``filter(x_id=None)`` is ``IS NULL``.
    """
    config = FuryConfig.objects.cached_singleton()
    return None if config is None else config.berserk_condition_id


def _ensure_fury_check_type(trait_name: str) -> CheckType:
    """Return the CheckType for a fury control-retention check keyed on trait_name.

    Lazy-creates the CheckType + CheckCategory if not present (mirrors
    fatigue._ensure_endurance_check_type). Requires the trait fixture row to exist.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    check_category, _ = CheckCategory.objects.get_or_create(
        name="Fury",
        defaults={"description": "Fury control-retention checks", "display_order": 98},
    )
    check_type_name = f"fury_control_retention_{trait_name}"
    check_type, _ = CheckType.objects.get_or_create(
        name=check_type_name,
        category=check_category,
        defaults={"description": f"Control-retention check for fury ({trait_name})"},
    )
    # Unconditional so a pre-existing (e.g. fixture-supplied) bare CheckType still gets
    # its trait attached (#2724); get_or_create's defaults let an authored weight survive
    # a re-run. Deliberately still tolerant of a missing Trait (skip rather than create) —
    # unlike fatigue's endurance/willpower checks, trait_name here comes from
    # FuryConfig.check_trait, a DB-configurable column, not a code string literal, so
    # #2724's "named by a string literal in code is config" rule doesn't reach it: there
    # is no fixed authored Trait row this function could reliably create on staff's
    # behalf. The composition self-heals via this same unchanged gameplay call site once
    # the configured trait's Trait row exists.
    trait = Trait.objects.filter(name=trait_name, trait_type=TraitType.STAT).first()
    if trait is not None:
        CheckTypeTrait.objects.get_or_create(
            check_type=check_type, trait=trait, defaults={"weight": Decimal("1.0")}
        )
    return check_type


def _trade_rate() -> Decimal:
    from world.combat.services.encounter.config import get_strain_config  # noqa: PLC0415

    return get_strain_config().intensity_per_control_surrendered


def _full_trade(tier: FuryTier, *, rate: Decimal, bonus_percent: int) -> Decimal:
    """The unfloored intensity ``tier`` buys at a 100% share: control x rate x bonus scale."""
    scale = Decimal(100 + bonus_percent) / 100
    return Decimal(tier.control_surrendered) * rate * scale


def _floor(amount: Decimal) -> int:
    return max(int(amount.to_integral_value(rounding=ROUND_FLOOR)), 0)


def top_share_percent() -> int:
    """The highest authored ``FuryDegreeShare.intensity_percent``, or 0 when none exists."""
    from django.db.models import Max  # noqa: PLC0415

    return FuryDegreeShare.objects.aggregate(top=Max("intensity_percent"))["top"] or 0


def full_trade_intensities(
    tiers: Iterable[FuryTier], bonus_percent: int = 0, *, top_percent: int | None = None
) -> dict[int, int]:
    """The most intensity each tier can buy at strength bonus ``bonus_percent``, by tier pk.

    The declaration picker's "up to" figures: the trade at the highest authored
    ``FuryDegreeShare.intensity_percent`` (``top_share_percent``; 0 when no share row
    exists, so nothing can be bought). With ``bonus_percent`` 0 the strength adds no scaling. A
    caller pricing several resonances passes ``top_percent`` once instead of re-reading it.
    """
    if top_percent is None:
        top_percent = top_share_percent()
    rate = _trade_rate()
    return {
        tier.pk: _floor(
            _full_trade(tier, rate=rate, bonus_percent=bonus_percent) * Decimal(top_percent) / 100
        )
        if tier.control_surrendered > 0 and top_percent > 0
        else 0
        for tier in tiers
    }


def fury_intensity_for(tier: FuryTier, bonus_percent: int, outcome: CheckOutcome | None) -> int:
    """Intensity the Fury trade buys for ``tier`` at strength bonus ``bonus_percent`` and roll.

    ``floor(control_surrendered x StrainConfig.intensity_per_control_surrendered
    x (100 + give_in_bonus_percent) / 100 x intensity_percent / 100)``, floored
    once at the end. An outcome with no ``FuryDegreeShare`` row (or no outcome) buys 0.
    """
    if outcome is None or tier.control_surrendered <= 0:
        return 0
    share = FuryDegreeShare.objects.filter(outcome_tier=outcome).first()
    if share is None or share.intensity_percent <= 0:
        return 0
    full = _full_trade(tier, rate=_trade_rate(), bonus_percent=bonus_percent)
    return _floor(full * Decimal(share.intensity_percent) / 100)


def fury_over_cap_message(tier: FuryTier, resonance: Resonance) -> str:
    """The refusal for a tier deeper than the resonance's strength allows (scene and combat)."""
    return f"Your {resonance.name} is not kindled enough to give in as far as {tier.name}."


def fury_not_kindled_message(resonance: Resonance) -> str:
    """The refusal for a resonance she does not hold or that is not kindled now."""
    return f"Your {resonance.name} is not kindled right now, so you cannot give in to it."


def fury_tier_label(tier: FuryTier) -> str:
    """How a tier reads to the player: ``Seething: surrender 6 control``, ``(Berserk)`` added."""
    label = f"{tier.name}: surrender {tier.control_surrendered} control"
    return f"{label} (Berserk)" if tier.berserk_severity > 0 else label


def fury_lapsed_message(resonance: Resonance) -> str:
    """The caster's own line when the resonance stopped being kindled before the cast went off."""
    return f"Your {resonance.name} is no longer kindled, so you hold steady."


def fury_trade_message(fury_res: FuryResolution) -> str:
    """The caster's own line for a landed trade: ``You surrender 6 control: intensity +8.``"""
    return (
        f"You surrender {fury_res.control_surrendered} control: "
        f"intensity +{fury_res.intensity_gained}."
    )


def resolve_fury(*, tier, strength, check_result) -> FuryResolution:
    """Assemble a FuryResolution from the given parameters.

    Args:
        tier: The FuryTier the player declared.
        strength: The kindled strength row of the resonance she gives in to (None means
            unavailable).
        check_result: The control roll's CheckResult (its ``outcome`` picks the share);
            None buys nothing.

    The declared tier is always clamped to the depth cap the strength allows; a cap of 0
    (not kindled) yields an empty resolution. Berserk is the realized tier's own
    ``berserk_severity``: chosen, never rolled into.
    """
    realized = clamp_tier(tier, provocation_cap(strength))
    if realized is None:
        return FuryResolution(None, 0, 0, 0)
    outcome = check_result.outcome if check_result is not None else None
    return FuryResolution(
        realized_tier=realized,
        control_surrendered=realized.control_surrendered,
        intensity_gained=fury_intensity_for(realized, provocation_bonus_percent(strength), outcome),
        berserk_severity=realized.berserk_severity,
        outcome=outcome,
    )


def engagement_of(character: ObjectDB):
    """The character's engagement of any type, or None."""
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    return CharacterEngagement.objects.filter(character_id=character.pk).first()


def shift_engagement(engagement, *, intensity: int, control: int, surrendered: int) -> None:
    """Add the deltas to the engagement's intensity, control and surrendered tally.

    Written on the identity-mapped instance (the one ``get_runtime_technique_stats`` reads
    back), under a row lock re-read as values so a write another request just made is not
    lost.
    """
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    with transaction.atomic():
        held_intensity, held_control, held_surrendered = (
            CharacterEngagement.objects.select_for_update()
            .filter(pk=engagement.pk)
            .values_list("intensity_modifier", "control_modifier", "fury_control_surrendered")
            .get()
        )
        engagement.intensity_modifier = held_intensity + intensity
        engagement.control_modifier = held_control + control
        engagement.fury_control_surrendered = held_surrendered + surrendered
        engagement.save(
            update_fields=["intensity_modifier", "control_modifier", "fury_control_surrendered"]
        )


class FuryCast:
    """One declared Fury, run inside the cast it was declared with (#4738).

    ``use_technique(fury=...)`` drives it, so the trade lands only on a cast that
    actually goes off, and that same cast channels it:

    - ``surrender()`` runs once the Soulfray gate has passed: it rolls the control check
      and lands the trade on her engagement. ``use_technique`` then re-reads her runtime
      stats.
    - ``withdraw()`` takes the trade back off the engagement when the cast is then
      cancelled before it resolves (a ``TECHNIQUE_PRE_CAST`` cancel). The roll stands.
    - ``settle()`` runs when the cast proceeds: it tells her (on commit) and applies
      Berserk for a Berserk tier, or tells her she holds steady when the resonance is no
      longer kindled.

    A cast stopped before ``surrender`` changes nothing and tells her nothing.
    ``resolution`` is None until ``surrender`` runs.
    """

    def __init__(
        self,
        *,
        character: ObjectDB,
        tier: FuryTier,
        resonance: Resonance | None,
        source_technique=None,
    ) -> None:
        self.character = character
        self.tier = tier
        self.resonance = resonance
        self.source_technique = source_technique
        self.resolution: FuryResolution | None = None
        self._engagement = None
        self._lapsed = False

    @property
    def realized_tier(self) -> FuryTier | None:
        """The tier the cast actually surrendered at (the audit value), or None."""
        return self.resolution.realized_tier if self.resolution is not None else None

    def surrender(self) -> bool:
        """Roll the control check and land the trade. True when the engagement changed.

        No engagement, or a tier her strength clamps to nothing: nothing is rolled
        and nothing changes.
        """
        self._engagement = engagement_of(self.character)
        if self._engagement is None:
            return False
        strength = give_in_strength(self.character, self.resonance)
        if clamp_tier(self.tier, provocation_cap(strength)) is None:
            self.resolution = FuryResolution(None, 0, 0, 0)
            # Kindled when she declared, not now: she holds steady, and is told.
            self._lapsed = strength is None
            return False

        from world.checks.services import (  # noqa: PLC0415
            difficulty_points,
            perform_check_with_modifiers,
        )
        from world.magic.constants import MagicActivity  # noqa: PLC0415
        from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

        check_type = _ensure_fury_check_type(_config().check_trait)
        ease = provocation_ease(strength, self.tier.base_check_difficulty_level)
        check = perform_check_with_modifiers(
            self.character,
            check_type,
            target_difficulty=max(
                difficulty_points(self.tier.base_check_difficulty_level) - ease, 0
            ),
            extra_traits=activity_skill_terms(MagicActivity.FURY_CONTROL),
        )
        self.resolution = resolve_fury(tier=self.tier, strength=strength, check_result=check)
        if self.resolution.realized_tier is None:
            return False
        shift_engagement(
            self._engagement,
            intensity=self.resolution.intensity_gained,
            control=-self.resolution.control_surrendered,
            surrendered=self.resolution.control_surrendered,
        )
        return True

    def withdraw(self) -> None:
        """Take a landed trade back off the engagement: the cast it rode never went off."""
        res = self.resolution
        if res is None or res.realized_tier is None or self._engagement is None:
            return
        shift_engagement(
            self._engagement,
            intensity=-res.intensity_gained,
            control=res.control_surrendered,
            surrendered=-res.control_surrendered,
        )
        self.resolution = None

    def settle(self) -> None:
        """The cast proceeds: tell her what she traded (on commit) and apply Berserk."""
        res = self.resolution
        if self._lapsed and self.resonance is not None:
            character = self.character
            lapsed = fury_lapsed_message(self.resonance)
            transaction.on_commit(lambda: character.msg(lapsed))
            return
        if res is None or res.realized_tier is None:
            return
        character = self.character
        message = fury_trade_message(res)
        # Told to the caster alone, once the cast's transaction commits.
        transaction.on_commit(lambda: character.msg(message))
        berserk_template = get_berserk_template()
        if res.berserk_severity > 0 and berserk_template is not None:
            from world.conditions.services import apply_condition  # noqa: PLC0415

            apply_condition(
                character,
                berserk_template,
                severity=res.berserk_severity,
                duration_rounds=_config().default_berserk_duration_rounds,
                source_character=character,
                source_technique=self.source_technique,
            )


def fury_cast_for(
    *,
    character: ObjectDB,
    fury_commitment: FuryTier | None,
    fury_resonance: Resonance | None,
    source_technique=None,
) -> FuryCast | None:
    """The ``FuryCast`` for a declaration, or None when no Fury was declared.

    Shared by the combat, scene-cast and technique-enhanced action paths; each passes it
    to ``use_technique(fury=...)`` and reads ``realized_tier`` back as the audit value.
    """
    if fury_commitment is None:
        return None
    return FuryCast(
        character=character,
        tier=fury_commitment,
        resonance=fury_resonance,
        source_technique=source_technique,
    )
