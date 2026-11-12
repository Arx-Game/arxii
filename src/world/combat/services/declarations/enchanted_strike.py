"""A weapon technique cast into a Strike (#5026): an enchanted Strike.

A weapon technique (one with a damage profile that uses the equipped weapon) is cast into
one Strike, from the Strike's "Enchant with" row; there is no second way to cast one. It is
a per-hit cast: the technique's cost is paid through ``use_technique`` on every attack, hit
or miss, and an overspend goes through the existing deficit and soulfray path behind the
accept box. Nothing lasts past the attack.

Order (spec Decision 8): pay the cast (the ``use_technique`` envelope), roll the technique,
roll the hit with the technique's to-hit line in it, then on a hit roll the Strike's damage
and apply each part.

Two rolls (owner ruling). The **technique roll** is the technique's cast check (its check
type and its technique skill, plus the combat pull), unopposed, and nothing else: no
intensity, bond, wind, effort, fatigue, style or compulsion term, which all belong to the
hit roll. Its power and success level set every addition through the formulas techniques
already use: the to-hit line (``Technique.strike_to_hit_size`` valued from the to-hit lane
at the cast's level) and each typed damage part (its profile's own budget, the technique
roll's damage multiplier, the technique-scoped damage modifiers). The **hit roll** is the
Strike's own, unchanged, plus that one labelled line.

A failed technique roll still pays; the additions that need a success do not appear, and
the Strike goes on as a plain Strike.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.checks.constants import CombatRollKind, ModifierLane, ModifierSourceKind
from world.checks.types import ModifierBreakdown, ModifierContribution
from world.combat.constants import ActionCategory, PullBurnAction

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.checks.types import CheckResult, RollSnapshot
    from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
    from world.combat.services.declarations.strike import StrikeLanding, StrikeRoll
    from world.combat.services.techniques.technique_resolver import (
        CombatTechniqueResolver,
        TechniqueDamageBonus,
    )
    from world.combat.types import ActionOutcome, StrikeWeapon
    from world.conditions.models import DamageType
    from world.magic.models import Technique
    from world.magic.models.techniques import AbstractDamageProfile
    from world.magic.types import CastCheck
    from world.magic.types.power_ledger import PowerLedger


@dataclass(frozen=True)
class TypedPart:
    """One damage part an enchantment adds to a landed Strike (#5026).

    ``damage_type`` None means the part joins the weapon's (an untyped weapon profile).
    ``profile`` carries the authored per-hit controls (soak piercing, resistance shift,
    execute) the part is applied with, as the profile's own hit in a cast would be.
    """

    amount: int
    damage_type: DamageType | None
    profile: AbstractDamageProfile


@dataclass
class StrikeEnchantment:
    """A technique cast into one Strike, rolled: what it adds to that Strike (#5026)."""

    technique: Technique
    display_name: str
    check_type: CheckType
    roll: CheckResult
    skill_name: str
    skill_rating: int | None
    to_hit: int
    resolver: CombatTechniqueResolver
    technique_bonus: TechniqueDamageBonus
    profiles: list[tuple[AbstractDamageProfile, int]]
    eff_intensity: int
    bounced: bool
    # Set once the cast has settled, for the technique roll's row.
    anima_cost: int = 0
    added_types: list[str] = field(default_factory=list)
    # Each typed part's amount as the technique roll set it, before the target's armor and
    # resistance, by type word; filled when the Strike lands (``typed_parts``).
    part_amounts: dict[str, int] = field(default_factory=dict)

    @property
    def to_hit_contribution(self) -> ModifierContribution:
        """The one line the technique adds to the hit roll, labelled with the technique."""
        return ModifierContribution(
            source_kind=ModifierSourceKind.TECHNIQUE,
            source_label=self.display_name,
            value=self.to_hit,
        )

    def typed_parts(
        self, target: CombatOpponent, weapon_type: DamageType | None
    ) -> list[TypedPart]:
        """Each damage part the enchantment adds to a landed Strike on ``target``.

        One ``(amount, damage type)`` per profile that reaches its minimum success level
        on the technique roll: its own budget at the technique roll's power and success
        level, scaled by the technique roll's damage multiplier, with the technique-scoped
        damage modifiers added once, as a technique's own damage adds them. A profile with
        no damage type of its own that uses the weapon joins the weapon's part, so its type
        comes back as None. Nothing after a ward bounced the cast.
        """
        from world.combat.services.damage.soak import target_soak_of  # noqa: PLC0415
        from world.conditions.services import get_damage_multiplier  # noqa: PLC0415

        if self.bounced:
            return []
        success_level = self.roll.success_level
        multiplier = get_damage_multiplier(success_level)
        if multiplier <= 0:
            return []
        self.technique_bonus.read_opponent(target.objectdb)
        parts: list[TypedPart] = []
        for profile, budget_bonus in self.profiles:
            joins_weapon = profile.damage_type is None and profile.uses_equipped_weapon
            hit_type = weapon_type if joins_weapon else profile.damage_type
            amount, part_type = self.resolver._profile_damage(  # noqa: SLF001 - one damage formula
                profile,
                None,
                target,
                sl=success_level,
                multiplier=multiplier,
                eff_intensity=self.eff_intensity,
                budget_bonus=budget_bonus,
                technique_bonus=self.technique_bonus,
                target_soak=target_soak_of(target, hit_type),
            )
            if amount <= 0:
                continue
            parts.append(TypedPart(amount, None if joins_weapon else part_type, profile))
            if not joins_weapon and part_type is not None:
                word = part_type.name.lower()
                self.part_amounts[word] = self.part_amounts.get(word, 0) + amount
        return parts

    def roll_row(self) -> StrikeRoll:
        """The technique roll as the first of the Strike's recorded rows."""
        from world.checks.types import RollSnapshot  # noqa: PLC0415

        snapshot: RollSnapshot = RollSnapshot(
            weapon_label=self.display_name,
            weapon_kind="",
            stat_label=self.skill_name,
            against_label=str(self.anima_cost),
        )
        return (
            self.check_type,
            ModifierBreakdown(
                contributions=[
                    ModifierContribution(
                        source_kind=ModifierSourceKind.PULL,
                        source_label="Combat pull",
                        value=self.resolver.pull_flat_bonus,
                    )
                ]
                if self.resolver.pull_flat_bonus
                else []
            ),
            self.result_line(),
            self.skill_rating,
            snapshot,
            CombatRollKind.TECHNIQUE,
        )

    def result_line(self) -> str:
        """ "Success: +2 to hit, 4 fire", "Success: +2 to hit, fire damage" (a miss), or
        "Failure: nothing added"."""
        added: list[str] = []
        if self.to_hit:
            added.append(f"+{self.to_hit} to hit")
        # "4 fire" once the blow landed and the amount is known; "fire damage" on a miss.
        added.extend(
            f"{self.part_amounts[word]} {word}" if word in self.part_amounts else f"{word} damage"
            for word in self.added_types
        )
        outcome = self.roll.outcome_name
        if self.bounced:
            return f"{outcome}: stopped by a ward"
        return f"{outcome}: {', '.join(added)}" if added else f"{outcome}: nothing added"


def _technique_skill(sheet: object, cast_check: CastCheck) -> tuple[str, int | None]:
    """The technique skill the cast adds (its name and the caster's rating), or ("", None)."""
    from world.traits.models import CharacterTraitValue  # noqa: PLC0415

    if not cast_check.extra_traits:
        return "", None
    trait = cast_check.extra_traits[0].trait
    rating = (
        CharacterTraitValue.objects.filter(character=sheet, trait=trait)
        .values_list("value", flat=True)
        .first()
    )
    return trait.name, rating


def strike_to_hit(technique: Technique, *, effective_power: int, success_level: int) -> int:
    """What ``technique`` adds to the Strike's hit roll (#5026): its ``strike_to_hit_size``
    valued from the to-hit lane at the level its cast resolves to, the same valuation a sized
    buff uses. 0 with no size, on a failed technique roll, or where no row covers it."""
    from world.checks.modifier_values import load_value_table  # noqa: PLC0415
    from world.magic.services.modifier_sizing import load_cast_level_table  # noqa: PLC0415

    size = technique.strike_to_hit_size
    if size is None or success_level < 1:
        return 0
    level = load_cast_level_table().level_for(
        effective_power=effective_power, success_level=success_level
    )
    if level is None:
        return 0
    return load_value_table(ModifierLane.TO_HIT).value(level, size) or 0


@dataclass
class EnchantedStrikeCast:
    """The ``resolve_fn`` ``use_technique`` runs once the cast is paid (#5026).

    Rolls the technique, then lands the Strike with what it added. Returns a
    ``CombatTechniqueResolution`` whose ``check_result`` is the technique roll, so a
    control mishap reads the cast's own roll.
    """

    participant: CombatParticipant
    action: CombatRoundAction
    target: CombatOpponent
    weapon: StrikeWeapon
    strike_check_type: CheckType
    cast_check: CastCheck
    display_name: str
    enchantment: StrikeEnchantment | None = None
    landing: StrikeLanding | None = None
    fired: list = field(default_factory=list)

    def __call__(
        self,
        *,
        power: int,  # noqa: ARG002 - the ledger carries it
        ledger: PowerLedger,
        extra_modifiers: int = 0,  # noqa: ARG002 - the pull is on the technique roll
    ) -> object:
        from world.combat.services.declarations.strike import land_strike  # noqa: PLC0415
        from world.combat.services.techniques.intensity import (  # noqa: PLC0415
            _sum_active_flat_bonuses,
        )
        from world.combat.services.techniques.technique_resolver import (  # noqa: PLC0415
            CombatTechniqueResolver,
            TechniqueDamageBonus,
        )
        from world.combat.types import CombatTechniqueResolution  # noqa: PLC0415
        from world.covenants.added_effects import (  # noqa: PLC0415
            record_vow_effect_firings,
            vow_damage_profiles,
        )
        from world.magic.constants import PowerStage  # noqa: PLC0415
        from world.magic.types.power_ledger import PowerLedgerBuilder  # noqa: PLC0415

        sheet = self.participant.character_sheet
        technique = self.action.focused_action
        resolver = CombatTechniqueResolver(
            participant=self.participant,
            action=self.action,
            pull_flat_bonus=_sum_active_flat_bonuses(
                self.participant, technique=technique, cast_check=self.cast_check
            ),
            fatigue_category=ActionCategory.PHYSICAL,
            offense_check_type=self.cast_check.check_type,
            offense_check_fn=None,
            offense_extra_traits=self.cast_check.extra_traits,
        )
        combat_ledger = (
            PowerLedgerBuilder.from_ledger(ledger)
            .add(
                PowerStage.COMBAT_PULL,
                "combat pulls",
                resolver._sum_intensity_bump_pulls(),  # noqa: SLF001 - the cast's own pulls
            )
            .build()
        )
        technique_roll = self._roll_technique(resolver)
        fired = resolver._fired_vow_effects(technique_roll)  # noqa: SLF001 - the cast's vows
        self.fired = fired
        profiles = [
            (profile, 0)
            for profile in resolver._effective_damage_profiles()  # noqa: SLF001 - its profiles
        ]
        profiles.extend(vow_damage_profiles(fired))
        bounced = False
        if not any(profile.bypasses_wards for profile, _ in profiles):
            combat_ledger, bounced = resolver._apply_penetration(  # noqa: SLF001 - the ward
                combat_ledger
            )
        eff_intensity = combat_ledger.total
        skill_name, skill_rating = _technique_skill(sheet, self.cast_check)
        self.enchantment = StrikeEnchantment(
            technique=technique,
            display_name=self.display_name,
            check_type=self.cast_check.check_type,
            roll=technique_roll,
            skill_name=skill_name,
            skill_rating=skill_rating,
            to_hit=0
            if bounced
            else strike_to_hit(
                technique,
                effective_power=eff_intensity,
                success_level=technique_roll.success_level,
            ),
            resolver=resolver,
            # Kind-wide damage modifiers reach the Strike once, through its weapon part.
            technique_bonus=TechniqueDamageBonus.for_cast(
                sheet, technique, technique_scoped_only=True
            ),
            profiles=profiles,
            eff_intensity=eff_intensity,
            bounced=bounced,
        )
        self.landing = land_strike(
            self.participant,
            self.action,
            self.target,
            self.weapon,
            self.strike_check_type,
            self.enchantment,
        )
        applied: list = []
        removed: list = []
        morale_shifts: list = []
        # The technique's conditions and morale ride the blow: they land only when the
        # Strike does, at the technique roll's success level, as a cast's own do. A limited
        # vow effect is spent only by a Strike that landed it.
        if self.landing.landed and not bounced:
            applied, removed = resolver._apply_conditions(  # noqa: SLF001 - its conditions
                technique_roll, eff_intensity=eff_intensity, fired_vow_effects=fired
            )
            morale_shifts = resolver._apply_morale(  # noqa: SLF001 - its morale row
                technique_roll, eff_intensity=eff_intensity
            )
            if technique_roll.success_level >= 1:
                record_vow_effect_firings(fired, encounter=self.participant.encounter)
        if technique_roll.success_level >= 1 and not bounced:
            from world.magic.services.effect_handlers import (  # noqa: PLC0415
                manifest_bound_entity,
            )

            manifest_bound_entity(participant=self.participant, technique=technique)
        return CombatTechniqueResolution(
            check_result=technique_roll,
            damage_results=list(self.landing.damage_results),
            applied_conditions=applied,
            pull_flat_bonus=resolver.pull_flat_bonus,
            scaled_damage=self.landing.damage_dealt or 0,
            power_ledger=combat_ledger,
            removed_conditions=removed,
            morale_shifts=morale_shifts,
        )

    def _roll_technique(self, resolver: CombatTechniqueResolver) -> CheckResult:
        """The technique roll: the cast check, unopposed, with the combat pull and the
        technique skill only (the "Counted once" table: every other term is the hit
        roll's).

        It is this attack's attack roll for a perk's "Applies to" (#5092), so a perk
        scoped to attack rolls answers here, and only such a perk; the hit roll then
        takes none. An unscoped or check-type perk and every outcome guarantee stay the
        hit roll's, counted once (ADR-5026).
        """
        from world.combat import services as _svc  # noqa: PLC0415
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
        from world.combat.services.techniques.technique_targets import (  # noqa: PLC0415
            _resolve_primary_target_sheet,
        )
        from world.covenants.perks.constants import PerkRollKind  # noqa: PLC0415
        from world.covenants.perks.context import SituationContext  # noqa: PLC0415

        sheet = self.participant.character_sheet
        return _svc.perform_check(
            sheet.character,
            self.cast_check.check_type,
            target_difficulty=0,
            extra_modifiers=resolver.pull_flat_bonus,
            extra_traits=self.cast_check.extra_traits,
            situation_ctx=SituationContext(
                holder=sheet,
                subject=sheet,
                target=_resolve_primary_target_sheet(self.action),
                resolution=CombatRoundContext(self.participant),
                roll_kind=PerkRollKind.ATTACK,
                roll_kind_perks_only=True,
            ),
        )


def resolve_enchanted_strike(
    participant: CombatParticipant,
    action: CombatRoundAction,
    outcome: ActionOutcome,
    weapon: StrikeWeapon,
    check_type: CheckType,
) -> ActionOutcome:
    """Resolve a Strike with a technique cast into it (#5026).

    The cast is paid through ``use_technique``, which runs the whole Strike inside its
    envelope: anima (and resonance where the cast takes it) on every attack, hit or miss;
    an overspend through the deficit and soulfray path. If the cast is stopped before it
    goes off (Soulfray worsened since the declaration and the risk was not accepted, or a
    pre-cast trigger), nothing is paid and the Strike goes on as a plain Strike.
    """
    from django.db import transaction  # noqa: PLC0415

    from world.combat.pull_helpers import round_pull_resonances  # noqa: PLC0415
    from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
    from world.combat.services.combos.combo_outcome import _apply_combo_rider  # noqa: PLC0415
    from world.combat.services.damage.vulnerability import (  # noqa: PLC0415
        _vulnerability_intensity_bonus,
    )
    from world.combat.services.declarations.strike import (  # noqa: PLC0415
        finish_strike,
        land_strike,
    )
    from world.combat.services.techniques.technique_targets import (  # noqa: PLC0415
        _build_affected_targets,
        _resolve_primary_target_sheet,
    )
    from world.magic.services import use_technique  # noqa: PLC0415
    from world.magic.services.magic_skills import resolve_cast_check  # noqa: PLC0415
    from world.magic.services.signature_effects import (  # noqa: PLC0415
        signature_intensity_delta,
    )
    from world.magic.services.technique_personalization import (  # noqa: PLC0415
        technique_display_name,
    )

    character = participant.character_sheet.character
    technique = action.focused_action
    target = action.focused_opponent_target
    display_name = technique_display_name(character, technique)
    cast_check = resolve_cast_check(character, technique)
    if cast_check is None or technique.action_template_id is None:
        message = f"Your {display_name} cannot be cast into a Strike; you strike without it."
        transaction.on_commit(lambda: character.msg(message))
        landing = land_strike(participant, action, target, weapon, check_type)
        finish_strike(participant, action, outcome, weapon, target, landing)
        return outcome

    cast = EnchantedStrikeCast(
        participant=participant,
        action=action,
        target=target,
        weapon=weapon,
        strike_check_type=check_type,
        cast_check=cast_check,
        display_name=display_name,
    )
    use = use_technique(
        character=character,
        technique=technique,
        resolve_fn=cast,
        confirm_soulfray_risk=action.confirm_soulfray_risk,
        strain_commitment=action.strain_commitment,
        combat_burn_for=PullBurnAction.CAST,
        targets=_build_affected_targets(participant, action),
        lethal=participant.encounter.is_lethal,
        cast_check=cast_check,
        power_intensity_bonus=signature_intensity_delta(character, technique)
        + _vulnerability_intensity_bonus(action),
        situation_ctx=CombatRoundContext(participant),
        target_sheet=_resolve_primary_target_sheet(action),
        pulled_resonances=round_pull_resonances(participant),
    )
    if not use.confirmed or cast.landing is None or cast.enchantment is None:
        # Stopped before it went off: nothing paid, and the blow lands plain.
        message = f"Your {display_name} falters before it can be cast; you strike without it."
        transaction.on_commit(lambda: character.msg(message))
        landing = land_strike(participant, action, target, weapon, check_type)
        finish_strike(participant, action, outcome, weapon, target, landing)
        return outcome

    enchantment = cast.enchantment
    enchantment.anima_cost = use.anima_cost.effective_cost
    enchantment.added_types = _authored_types(enchantment)
    # The technique roll's row is the first recorded; refresh it now the cost is known.
    cast.landing.rolls[0] = enchantment.roll_row()
    if action.combo_upgrade and target is not None:
        # A combo slot this enchanted Strike filled adds its rider, as a cast's does.
        _apply_combo_rider(participant, action, target, outcome)
    finish_strike(
        participant,
        action,
        outcome,
        weapon,
        target,
        cast.landing,
        enchantment=display_name,
    )
    return outcome


def _authored_types(enchantment: StrikeEnchantment) -> list[str]:
    """The typed parts the enchantment adds, by its profiles' types, for a Strike that
    missed or dealt none of them: what the technique roll set up, not what landed."""
    if enchantment.bounced:
        return []
    words: list[str] = []
    for profile, _bonus in enchantment.profiles:
        if profile.damage_type is None:
            continue
        if enchantment.roll.success_level < profile.minimum_success_level:
            continue
        word = profile.damage_type.name.lower()
        if word not in words:
            words.append(word)
    return words
