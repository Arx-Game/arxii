"""CombatTechniqueResolver: resolves a technique cast inside combat."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from world.checks.constants import ModifierSourceKind
from world.checks.services import level_opposition
from world.checks.types import ModifierContribution
from world.combat import services as _svc
from world.combat.constants import (
    CHARGE_CHECK_BONUS,
    CHARGE_DAMAGE_BONUS,
    LANCE_UNMOUNTED_PENALTY,
    CombatAllegiance,
    CombatManeuver,
    OpponentStatus,
    wind_penalty,
)
from world.combat.models import (
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
    SpectacleConfig,
)
from world.combat.morale import (
    apply_morale_damage,
    mindless_share,
    morale_state_for,
    tier_morale_map,
)
from world.combat.services.encounter.check_types import get_penetration_check_type
from world.combat.services.equipment.equipped_weapon import (
    _equipped_weapon_archetype,
    _weapon_augmented_budget,
    _wear_equipped_weapon,
    effective_weapon_profile,
)
from world.combat.services.techniques.technique_targets import (
    _resolve_condition_target,
    _resolve_enemy_condition_targets,
    _resolve_primary_target_sheet,
    aoe_opponent_candidates,
    opponents_in_reach,
)
from world.combat.types import CombatTechniqueResolution, OpponentDamageResult, SpectacleShift
from world.conditions.constants import Allegiance
from world.conditions.services import spend_contributing_conditions
from world.fatigue.services import get_fatigue_penalty
from world.magic.constants import EffectKind

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from world.checks.models import CheckType
    from world.checks.types import CheckResult, ExtraTraitTerm
    from world.combat.types import WeaponContribution
    from world.conditions.models import DamageType
    from world.conditions.types import AppliedConditionResult, RemovedConditionResult
    from world.covenants.types import FiredVowEffect
    from world.magic.models.techniques import AbstractDamageProfile
    from world.magic.types.power_ledger import PowerLedger

    PerformCheckFn = Callable[..., CheckResult]


# ---------------------------------------------------------------------------
# CombatTechniqueResolver - Damage and condition resolution for combat techniques
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CombatTechniqueResolver:
    """Resolves the inner step of a combat-cast technique. Single class
    handles both damage and condition application; behavior differences
    live in technique-authored data (base_power, TechniqueAppliedCondition rows).
    """

    participant: CombatParticipant
    action: CombatRoundAction
    pull_flat_bonus: int
    fatigue_category: str
    offense_check_type: CheckType
    offense_check_fn: PerformCheckFn | None
    # Skill terms the cast adds to the offense roll (the technique skill, #4450).
    offense_extra_traits: tuple[ExtraTraitTerm, ...] = ()

    def _roll_check(self) -> CheckResult:
        """Roll the offense check with effort + pull-bonus modifiers."""
        check_fn = self.offense_check_fn or _svc.perform_check
        penalty = get_fatigue_penalty(
            self.participant.character_sheet,
            self.fatigue_category,
        )

        # Route the combat-pull flat bonus through the shared modifier seam so
        # the combat check honors condition + rollmod sources (the #851
        # individualization lever) and the recorded ModifierBreakdown is exhaustive:
        # every point that shifts the roll is a labeled contribution, so the
        # provenance UI can attribute it.  breakdown.extra_modifiers_total alone is the
        # roll shift from outside perform_check (CAPABILITY points are in the breakdown
        # for provenance but perform_check adds them itself, #4453) — no out-of-band
        # additive the breakdown can't see.
        # Effort is NOT folded in here (#3066) — it is threaded straight into
        # check_fn's own effort_level parameter below, which applies the exact
        # same EFFORT_CHECK_MODIFIER internally (perform_check._compute_check_breakdown)
        # AND is perform_check's own signal for check-based development-point
        # accrual (#3039). Folding it into extra_contributions here as well would
        # double-count the roll bonus.
        extra_contributions: list[ModifierContribution] = []
        if self.pull_flat_bonus:
            extra_contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.PULL,
                    source_label="Combat pull",
                    value=self.pull_flat_bonus,
                )
            )
        # Bond combat bonus (#2021): relationship co-combatant passive.
        from world.relationships.services import bond_combat_bonus  # noqa: PLC0415

        extra_contributions.extend(
            bond_combat_bonus(
                self.participant.character_sheet,
                self.participant.encounter,
            )
        )

        # Mounted-combat bonuses/penalties (#1843), composed at the same seam
        # as every other check contribution — provenance stays exhaustive.
        from world.items.constants import GearArchetype  # noqa: PLC0415

        character = self.participant.character_sheet.character
        weapon_archetype = _equipped_weapon_archetype(character)

        if self.action.maneuver == CombatManeuver.CHARGE:
            charge_bonus = CHARGE_CHECK_BONUS
            if weapon_archetype == GearArchetype.LANCE:
                charge_bonus *= 2
            extra_contributions.append(
                ModifierContribution(
                    source_kind=ModifierSourceKind.CHARACTER,
                    source_label="Charge",
                    value=charge_bonus,
                )
            )

        if weapon_archetype == GearArchetype.LANCE:
            from world.companions.mount_content import MOUNTED_CONDITION_NAME  # noqa: PLC0415
            from world.conditions.models import ConditionTemplate  # noqa: PLC0415
            from world.conditions.services import has_condition  # noqa: PLC0415

            mounted_template = ConditionTemplate.get_by_name(MOUNTED_CONDITION_NAME)
            if not has_condition(character, mounted_template):
                extra_contributions.append(
                    ModifierContribution(
                        source_kind=ModifierSourceKind.CHARACTER,
                        source_label="Unmounted Lance",
                        value=LANCE_UNMOUNTED_PENALTY,
                    )
                )

        # Wind-as-mechanic (#1555): a banded SCENE penalty on missile attacks
        # only. Guarded cheaply — skip the felt_exposure room lookup entirely
        # for melee/lance attacks, which stay untouched.
        if (
            weapon_archetype in (GearArchetype.RANGED, GearArchetype.THROWN)
            and self.participant.encounter.room is not None
        ):
            from world.locations.constants import StatKey  # noqa: PLC0415
            from world.locations.services import felt_exposure  # noqa: PLC0415

            wind_mod = wind_penalty(
                felt_exposure(self.participant.encounter.room, stat_key=StatKey.WIND)
            )
            if wind_mod:
                extra_contributions.append(
                    ModifierContribution(
                        source_kind=ModifierSourceKind.SCENE,
                        source_label="Wind",
                        value=wind_mod,
                    )
                )

        breakdown = _svc.collect_check_modifiers(
            self.participant.character_sheet,
            self.offense_check_type,
            scene=self.participant.encounter.scene,
            extra_contributions=extra_contributions,
            extra_traits=self.offense_extra_traits,
        )
        extra_modifiers = breakdown.extra_modifiers_total

        # #2536 Task 5: thread the live round context so CHECK_BONUS situational
        # perks can fire on the technique's own offense check — the check-side
        # sibling of resolve_combat_technique's POWER_BONUS threading above.
        # holder/subject are both the checking character's own sheet (perform_check
        # only reads .resolution/.target off this); target mirrors the cast's
        # POWER_BONUS target resolution (_resolve_primary_target_sheet) so the same
        # target-keyed situations are reachable for CHECK_BONUS perks too.
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
        from world.covenants.perks.context import SituationContext  # noqa: PLC0415

        situation_ctx = SituationContext(
            holder=self.participant.character_sheet,
            subject=self.participant.character_sheet,
            target=_resolve_primary_target_sheet(self.action),
            resolution=CombatRoundContext(self.participant),
        )
        # #2707: the first time an attack has been rolled against anything but
        # zero. The focused opponent's level (and its aspect match on this
        # offense check) sets the difficulty via level_opposition — a stab at
        # a level 5 adept used to roll against a difficulty of 0 no matter who
        # she was. No focused opponent (untargeted/ally-targeted technique)
        # stays unopposed at 0.
        focused = self.action.focused_opponent_target
        target_difficulty = (
            level_opposition(
                self.offense_check_type,
                level=focused.level,
                character=focused.objectdb,
            )
            if focused is not None
            else 0
        )
        from world.combat.stat_mapping import weapon_stat_override  # noqa: PLC0415

        stat_override = weapon_stat_override(character)
        result = check_fn(
            character,
            self.offense_check_type,
            target_difficulty=target_difficulty,
            extra_modifiers=extra_modifiers,
            effort_level=self.action.effort_level,
            fatigue_penalty=penalty,
            situation_ctx=situation_ctx,
            stat_override=stat_override,
            extra_traits=self.offense_extra_traits,
        )
        spend_contributing_conditions(breakdown)
        from world.magic.services.ultimates import floor_ultimate_check  # noqa: PLC0415

        return floor_ultimate_check(result, self.action.focused_action)

    def _sum_intensity_bump_pulls(self) -> int:
        """Sum INTENSITY_BUMP scaled_values from active CombatPulls."""
        encounter = self.participant.encounter
        character = self.participant.character_sheet.character
        pull_bonus = 0
        for pull in character.combat_pulls.active_for_encounter(encounter):
            for eff in pull.resolved_effects_cached:
                if eff.kind == EffectKind.INTENSITY_BUMP and eff.scaled_value:
                    pull_bonus += eff.scaled_value
        return pull_bonus

    def _resolved_opponent_targets(self) -> list[CombatOpponent]:
        """Return the ordered list of CombatOpponents to act on for this action.

        - AREA: returns ALL non-DEFEATED opponents in the encounter, enumerated
          directly from the encounter (one query, no join table required).
          The client does NOT need to enumerate them at declaration time —
          the encounter is the source of truth for "who is targetable".
        - FILTERED_GROUP: returns only the opponents stored in the
          ``CombatRoundActionTarget`` join table (the explicitly-stored subset).
          Falls back to the single ``focused_opponent_target`` when no join rows
          exist (e.g. direct callers that bypass dispatch).
        - SINGLE / SELF (default): returns a one-element list containing only
          ``focused_opponent_target``, preserving pre-AoE behavior exactly.

        DEFEATED opponents are NOT filtered here for FILTERED_GROUP / SINGLE —
        callers skip them individually so that per-target status checks are fresh
        after each preceding target's damage write.  AREA is the exception: it
        pre-filters to exclude DEFEATED so clients never need to enumerate the
        full list.

        AREA and FILTERED_GROUP additionally run technique.target_prerequisites
        through ``aoe_opponent_candidates`` (silent filter, #1793) — the
        SINGLE/SELF branch does not, since that case is hard-gated pre-flight by
        ``_check_combat_target_prerequisites`` in ``resolve_combat_technique``
        before this method is ever reached for an AoE-independent enumeration.

        AREA additionally drops any opponent whose EFFECTIVE allegiance is
        ALLY_OF_CASTER (a summon, or a charmed NPC) — a PC's AoE spares the party's
        own side (Decision 4, #4091); a TURNED or calmed opponent stays in the AoE
        set, since neither fights for the party.

        AREA and FILTERED_GROUP finally keep only the opponents ``technique_can_reach``
        allows from the caster's live position (#4607); an opponent with no game object
        or either side unplaced stays (lenient).
        """
        from actions.constants import ActionTargetType  # noqa: PLC0415

        technique = self.action.focused_action
        if technique is None:
            primary = self.action.focused_opponent_target
            return [primary] if primary is not None else []

        target_type = technique.target_type
        if target_type in (ActionTargetType.AREA, ActionTargetType.FILTERED_GROUP):
            # Reach is checked live (#4607): a target that moved out of reach since
            # the declaration drops out of the area, silently, like a failed prerequisite.
            return opponents_in_reach(
                self.participant.character_sheet.character,
                technique,
                aoe_opponent_candidates(self.participant, self.action, technique),
            )

        # SINGLE / SELF: single target only
        primary = self.action.focused_opponent_target
        return [primary] if primary is not None else []

    def _apply_profiles_to_target(  # noqa: PLR0913
        self,
        target: CombatOpponent,
        profiles: list[tuple[AbstractDamageProfile, int]],
        weapon: WeaponContribution | None,
        *,
        sl: int,
        multiplier: Decimal,
        eff_intensity: int,
    ) -> tuple[list[OpponentDamageResult], bool]:
        """Apply each damage profile to a single target, returning results and weapon-hit flag.

        Each entry pairs a profile with the flat budget bonus it carries: 0 for the
        technique's own and its signature's profiles, the fired row's
        ``damage_bonus`` for a vow added effect's (#4581).

        Skips profiles that deal zero damage and aborts early if the target is
        defeated mid-loop (can happen when a preceding profile triggers a kill).
        """
        results: list[OpponentDamageResult] = []
        weapon_landed = False
        for profile, budget_bonus in profiles:
            scaled, profile_damage_type = self._profile_damage(
                profile,
                weapon,
                target,
                sl=sl,
                multiplier=multiplier,
                eff_intensity=eff_intensity,
                budget_bonus=budget_bonus,
            )
            if scaled <= 0:
                continue
            target.refresh_from_db()
            if target.status == OpponentStatus.DEFEATED:
                break
            results.append(
                _svc.apply_damage_to_opponent(
                    target,
                    scaled,
                    damage_type=profile_damage_type,
                    ignores_soak=profile.ignores_soak,
                    resistance_shift=profile.resistance_shift,
                    source_sheet=self.participant.character_sheet,
                    # #2643: the profile IS in hand here — the cleanest seam to thread
                    # execute from (mirrors how damage_intensity_multiplier reaches
                    # compute_damage_budget above, in _profile_damage).
                    execute_missing_health_multiplier=profile.execute_missing_health_multiplier,
                )
            )
            weapon_landed = weapon_landed or (profile.uses_equipped_weapon and weapon is not None)
        return results, weapon_landed

    def _effective_damage_profiles(self) -> list[AbstractDamageProfile]:
        """Collect resolved technique and active signature rows for this cast."""
        from world.magic.services.signature_effects import (  # noqa: PLC0415
            signature_damage_profiles,
        )
        from world.magic.specialization.services import (  # noqa: PLC0415
            resolve_specialized_variant,
        )

        attacker = self.participant.character_sheet.character
        technique = resolve_specialized_variant(
            entity=self.action.focused_action,
            character=attacker,
            _sheet=self.participant.character_sheet,
        )
        return [
            *technique.cached_damage_profiles,
            *signature_damage_profiles(attacker, technique),
        ]

    def _apply_damage(
        self,
        check_result: CheckResult,
        *,
        eff_intensity: int,
        profiles: list[tuple[AbstractDamageProfile, int]] | None = None,
    ) -> list[OpponentDamageResult]:
        """Iterate technique.damage_profiles against all resolved opponent targets.

        For AREA / FILTERED_GROUP techniques every opponent in the join table is
        attacked separately with the same profile contest (per-target soak /
        resistance applies independently).  SINGLE / SELF techniques are unchanged
        — only ``focused_opponent_target`` is used.

        Combines the technique's own profiles with its signed
        SignatureMotifBonus's profiles, if any (#1728) — both are
        ``AbstractDamageProfile`` subclasses, so weapon-augment, SL-multiplier,
        property-bonus, and multi-target all apply uniformly to both.

        ``profiles`` includes the fired vow added effects' damage profiles, each with
        its row's ``damage_bonus`` (``vow_damage_profiles``, #4581). They follow
        the technique's and signature's profiles (which carry no bonus) through
        the same per-target loop, so a technique with no damage of its own still
        deals a vow's.

        Per opponent:
        - skip if DEFEATED (checked fresh after each preceding write)
        - for each damage profile: compute budget, apply SL multiplier, call
          apply_damage_to_opponent (subtracts soak + resistance)

        Returns one OpponentDamageResult per successfully applied profile×target
        combination.
        """
        from world.conditions.services import get_damage_multiplier  # noqa: PLC0415

        targets = self._resolved_opponent_targets()
        if not targets:
            return []
        attacker = self.participant.character_sheet.character
        if profiles is None:
            profiles = [(profile, 0) for profile in self._effective_damage_profiles()]
        if not profiles:
            return []

        sl = check_result.success_level
        multiplier = get_damage_multiplier(sl)
        if multiplier <= 0:
            return []

        weapon = effective_weapon_profile(attacker)
        any_weapon_landed = False

        results: list[OpponentDamageResult] = []
        for target in targets:
            target.refresh_from_db()
            if target.status == OpponentStatus.DEFEATED:
                continue
            target_results, weapon_landed = self._apply_profiles_to_target(
                target, profiles, weapon, sl=sl, multiplier=multiplier, eff_intensity=eff_intensity
            )
            results.extend(target_results)
            any_weapon_landed = any_weapon_landed or weapon_landed

        if any_weapon_landed:
            _wear_equipped_weapon(attacker)
        return results

    def _profile_damage(  # noqa: PLR0913
        self,
        profile: AbstractDamageProfile,
        weapon: WeaponContribution | None,
        target: CombatOpponent,
        *,
        sl: int,
        multiplier: Decimal,
        eff_intensity: int,
        budget_bonus: int = 0,
    ) -> tuple[int, DamageType | None]:
        """Scaled damage + effective damage_type for one profile (0 if it skips).

        Returns ``(0, None)`` when the profile's minimum_success_level exceeds
        ``sl``; otherwise folds the equipped weapon's contribution, a CHARGE
        maneuver's flat CHARGE_DAMAGE_BONUS (#1843, doubled for a LANCE), and
        the target's Property-driven damage bonus (#1793) into the formula
        budget, then applies the success-level multiplier and the attacker's
        condition damage-dealt percent for the profile's type (#4742). Budget
        is floored at 0 after the (possibly negative) property bonus, and the
        result at 0 after the (possibly negative) percent.

        ``budget_bonus`` is a flat amount added to the budget right after the
        weapon augment, before the CHARGE and property bonuses and the floor: a
        vow added effect's thread-level ``damage_bonus`` (#4581). Default 0.
        """
        from world.conditions.services import (  # noqa: PLC0415
            resolved_damage_type,
            scaled_outgoing_damage,
        )
        from world.mechanics.services import property_damage_bonus  # noqa: PLC0415

        if sl < profile.minimum_success_level:
            return 0, None
        budget = profile.compute_damage_budget(
            effective_power=eff_intensity,
            success_level=sl,
        )
        budget, profile_damage_type = _weapon_augmented_budget(
            profile, budget, weapon, self.participant.character_sheet
        )
        budget += budget_bonus
        if self.action.maneuver == CombatManeuver.CHARGE:
            from world.items.constants import GearArchetype  # noqa: PLC0415

            charge_damage_bonus = CHARGE_DAMAGE_BONUS
            character = self.participant.character_sheet.character
            if _equipped_weapon_archetype(character) == GearArchetype.LANCE:
                charge_damage_bonus *= 2
            budget += charge_damage_bonus
        # Untyped damage is Physical (#4742), for the bonus below and the attacker's
        # own damage-dealt rows (a smoke form's Physical -75 leaves Fire untouched).
        profile_damage_type = resolved_damage_type(profile_damage_type)
        budget = max(0, budget + property_damage_bonus(target.objectdb, profile_damage_type))
        scaled = scaled_outgoing_damage(
            self.participant.character_sheet.character,
            int(budget * multiplier),
            profile_damage_type,
        )
        return scaled, profile_damage_type

    def _apply_conditions(
        self,
        check_result: CheckResult,
        *,
        eff_intensity: int,
        fired_vow_effects: Sequence[FiredVowEffect] = (),
    ) -> tuple[list[AppliedConditionResult], list[RemovedConditionResult]]:
        """Apply technique-authored conditions to appropriate targets.

        Resolves each ConditionTargetKind (SELF/ALLY/ENEMY) to a concrete list
        of ObjectDBs, builds the ``targets_by_kind`` mapping, and delegates to
        the shared ``apply_technique_conditions`` service — then runs the
        ``remove_technique_conditions`` dispel sibling over the same resolved
        targets (#1585).

        For AREA / FILTERED_GROUP techniques the ENEMY slot is expanded to ALL
        active (non-DEFEATED) opponents in ``_resolved_opponent_targets()`` rather
        than just the single ``focused_opponent_target``.

        ``eff_intensity`` is the combined effective intensity (injected power + pull bumps)
        computed by ``__call__`` and forwarded here.

        ``fired_vow_effects`` are the vow added effects riding this cast (#4581).
        Their conditions, treatments and removals run through
        ``apply_vow_effect_payloads`` over the same ``targets_by_kind``, after
        the technique's own treatments and before its own removals; their
        applied and removed results join the returned lists.

        Returns:
            ``(applied, removed)`` — the apply results and the dispel results, both
            over the same resolved ``targets_by_kind``.
        """
        from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415
        from world.magic.services.condition_application import (  # noqa: PLC0415
            apply_technique_conditions,
            remove_technique_conditions,
        )

        technique = self.action.focused_action
        caster_od = self.participant.character_sheet.character

        targets_by_kind: dict[str, list] = {}

        # SELF and ALLY resolve to a single target (unchanged)
        for kind in (ConditionTargetKind.SELF, ConditionTargetKind.ALLY):
            target = _resolve_condition_target(kind, self.action, caster_od)
            if target is not None:
                targets_by_kind[kind] = [target]

        # ENEMY: expand to all resolved opponents for AoE; single for SINGLE/SELF
        enemy_objectdbs = _resolve_enemy_condition_targets(
            self._resolved_opponent_targets(), self.action, caster_od
        )
        if enemy_objectdbs:
            targets_by_kind[ConditionTargetKind.ENEMY] = enemy_objectdbs

        position_params: dict[str, int] = {}
        if self.action.cast_destination_id:
            position_params["destination_position_id"] = self.action.cast_destination_id
        if self.action.cast_position_a_id and self.action.cast_position_b_id:
            position_params["position_a_id"] = self.action.cast_position_a_id
            position_params["position_b_id"] = self.action.cast_position_b_id

        applied = apply_technique_conditions(
            technique=technique,
            success_level=check_result.success_level,
            eff_intensity=eff_intensity,
            targets_by_kind=targets_by_kind,
            source_character=caster_od,
            position_params=position_params or None,
            soulfray_consented=self.action.confirm_soulfray_risk,
        )
        # Signature-motif bonus (#1582): apply the signed technique's bonus conditions
        # through the SAME shared seam, over the same resolved targets. No-op when the
        # technique is not signed or the bonus carries no condition rows.
        from world.magic.services.signature_effects import (  # noqa: PLC0415
            apply_signature_bonus_conditions,
        )

        applied.extend(
            apply_signature_bonus_conditions(
                character=caster_od,
                technique=technique,
                success_level=check_result.success_level,
                eff_intensity=eff_intensity,
                targets_by_kind=targets_by_kind,
                source_character=caster_od,
                soulfray_consented=self.action.confirm_soulfray_risk,
            )
        )
        # Technique treatment (#2668): perform bounded-mend treatments on resolved
        # targets. Fires BEFORE remove_technique_conditions. No-op when the
        # technique has no treatment rows.
        from world.magic.services.condition_application import (  # noqa: PLC0415
            apply_technique_treatments,
        )

        apply_technique_treatments(
            technique=technique,
            success_level=check_result.success_level,
            eff_intensity=eff_intensity,
            targets_by_kind=targets_by_kind,
            source_character=caster_od,
            scene=self.participant.encounter.scene,
        )
        # Vow added effects (#4581): the payloads of the covenant vow rows riding this
        # cast, over the same resolved targets (SELF is the caster). An NPC enemy is
        # an ObjectDB in targets_by_kind, so a vow's enemy condition lands on it. After
        # the technique's treatments and before its removals: the seam runs every vow
        # treatment before any vow removal, so all treatments precede all removals.
        vow_removed: list[RemovedConditionResult] = []
        if fired_vow_effects:
            from world.covenants.added_effects import (  # noqa: PLC0415
                apply_vow_effect_payloads,
            )

            vow_applied, vow_removed = apply_vow_effect_payloads(
                fired_vow_effects,
                technique=technique,
                success_level=check_result.success_level,
                eff_intensity=eff_intensity,
                targets_by_kind=targets_by_kind,
                source_character=caster_od,
                scene=self.participant.encounter.scene,
                soulfray_consented=self.action.confirm_soulfray_risk,
            )
            applied.extend(vow_applied)
        # Dispel/cleanse sibling (#1585): strip technique-authored conditions from
        # the same resolved targets. No-op when the technique has no
        # removed_conditions rows.
        removed = remove_technique_conditions(
            technique=technique,
            success_level=check_result.success_level,
            eff_intensity=eff_intensity,
            targets_by_kind=targets_by_kind,
            source_character=caster_od,
        )
        removed.extend(vow_removed)
        return applied, removed

    def _apply_morale(
        self, check_result: CheckResult, *, eff_intensity: int
    ) -> list[SpectacleShift]:
        """Shake each enemy the cast resolved on by the technique's own morale row (#4619).

        Reads the cast's existing ``check_result``; it adds no roll. Nothing
        happens below the row's ``minimum_success_level`` or when the row scales
        to no morale. Runs after damage, so an opponent this cast defeated (or
        one already fled or removed) is skipped by its status. AREA keeps
        TURNED and NEUTRAL opponents and ally-side summons in the resolved set,
        so the side is filtered here: only a combat ENEMY whose effective
        allegiance is not ALLY_OF_CASTER is shaken. A mindless tier takes
        ``SpectacleConfig.mindless_percent`` of the hit. A ward bounce never
        reaches here (``__call__`` returns first), so it shakes nothing.

        Returns:
            One ``SpectacleShift`` per opponent whose morale state changed, its
            state before and after. An opponent already past the floor (or one
            the hit leaves in the same state) records none.
        """
        from world.npc_services.allegiance import effective_allegiances  # noqa: PLC0415

        row = self.action.focused_action.cached_morale_effect
        success_level = check_result.success_level
        if row is None or success_level < row.minimum_success_level:
            return []
        amount = row.compute_morale(effective_power=eff_intensity, success_level=success_level)
        if amount <= 0:
            return []
        targets = self._resolved_opponent_targets()
        if not targets:
            return []
        allegiances = effective_allegiances(targets)
        has_morale = tier_morale_map()
        mindless_percent = SpectacleConfig.load().mindless_percent
        shifts: list[SpectacleShift] = []
        for opponent in targets:
            if (
                opponent.status != OpponentStatus.ACTIVE
                or opponent.allegiance != CombatAllegiance.ENEMY
                or allegiances[opponent.pk] == Allegiance.ALLY_OF_CASTER
            ):
                continue
            hit = amount
            if not has_morale.get(opponent.tier, True):
                hit = mindless_share(amount, mindless_percent=mindless_percent)
            before = morale_state_for(opponent)
            apply_morale_damage(opponent, hit)
            after = morale_state_for(opponent)
            if after != before:
                shifts.append(SpectacleShift(opponent.pk, before.value, after.value))
        return shifts

    def _apply_penetration(self, combat_ledger: PowerLedger) -> tuple[PowerLedger, bool]:
        """Run the penetration-vs-resistance contest (#639) against the ward.

        The penetration difficulty is the focused opponent's
        ``barrier_strength`` (the ward ONLY — damage-type resistance is soaked
        once downstream in ``apply_damage_to_opponent``; never consumed here).

        Caster-side modifiers flow through ``collect_check_modifiers`` (the
        same seam as the offense check), so condition/equipment and
        check-scoped CharacterModifier sources all apply (#767).

        Returns ``(ledger, bounced)``:

        - No focused opponent / no barrier (None or 0) → UNOPPOSED: returns
          the ledger unchanged and ``bounced=False``, rolls NO check, adds NO
          entry. Inert for every existing combat path (those targets carry no
          barrier) — a zero-power unwarded cast still flows to its base_damage.
        - factor == 0 → bounce: a PENETRATION ``set 0`` entry and
          ``bounced=True`` (the caller short-circuits damage/conditions).
        - pct == 0 (factor 1.00, clean penetration) → a PENETRATION ``set``
          entry with the unchanged total and ``bounced=False``. Power is
          unmodified, but the entry lets narration distinguish a
          warded-but-cleanly-penetrated cast from an unwarded one.
        - pct != 0 (partial or overpenetration) → a PENETRATION ``multiply``
          entry by ``(factor - 1) * 100`` pct and ``bounced=False``.
        """
        from world.conditions.services import get_penetration_factor  # noqa: PLC0415
        from world.magic.constants import PowerStage  # noqa: PLC0415
        from world.magic.types.power_ledger import PowerLedgerBuilder  # noqa: PLC0415

        target = self.action.focused_opponent_target
        ward = (target.barrier_strength or 0) if target is not None else 0
        if ward <= 0:
            return combat_ledger, False

        caster = self.participant.character_sheet.character
        pen_check_type = get_penetration_check_type()
        # The penetration roll keeps its own check type and adds only the cast's skill
        # terms (the technique skill), the same terms the offense roll carries.
        pen_extra_traits = self.offense_extra_traits
        # Mirror _roll_check: route through the shared modifier seam so the
        # penetration contest honors condition / rollmod / equipment
        # and CHARACTER (#767, e.g. "+penetration vs warded foes") sources.
        # Effort and pull bonuses stay offense-only, exactly as #639 decided.
        pen_breakdown = _svc.collect_check_modifiers(
            self.participant.character_sheet,
            pen_check_type,
            scene=self.participant.encounter.scene,
            extra_traits=pen_extra_traits,
        )
        # #2536 Task 5 review fix: thread the same live round context the
        # offense check gets (_roll_check) — same class, same self.participant,
        # same target resolution. A future CHECK_BONUS perk scoped to the
        # penetration CheckType must not silently never fire just because this
        # sibling roll skipped the seam every other combat check now honors.
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
        from world.covenants.perks.context import SituationContext  # noqa: PLC0415

        situation_ctx = SituationContext(
            holder=self.participant.character_sheet,
            subject=self.participant.character_sheet,
            target=_resolve_primary_target_sheet(self.action),
            resolution=CombatRoundContext(self.participant),
        )
        # #2707 decision 6: additive on top of the authored ward -- the level
        # term never replaces barrier_strength. A warded high-level mage is
        # harder to penetrate than a warded low-level one with the identical ward.
        pen_result = _svc.perform_check(
            caster,
            pen_check_type,
            target_difficulty=ward
            + level_opposition(pen_check_type, level=target.level, character=target.objectdb),
            extra_modifiers=pen_breakdown.extra_modifiers_total,
            situation_ctx=situation_ctx,
            extra_traits=pen_extra_traits,
        )
        spend_contributing_conditions(pen_breakdown)
        factor = get_penetration_factor(pen_result.success_level)
        builder = PowerLedgerBuilder.from_ledger(combat_ledger)
        if factor == 0:
            return builder.set_value(PowerStage.PENETRATION, "ward (bounced)", 0).build(), True
        pct = round((float(factor) - 1.0) * 100)
        if pct == 0:
            # Clean full penetration: record the event without changing power so
            # narration can distinguish a warded-but-cleanly-penetrated cast from
            # an unwarded one (which records NO entry at all).
            return (
                builder.set_value(
                    PowerStage.PENETRATION, "ward (penetrated)", combat_ledger.total
                ).build(),
                False,
            )
        return builder.multiply(PowerStage.PENETRATION, "ward", pct).build(), False

    def _fired_vow_effects(self, check_result: CheckResult) -> list[FiredVowEffect]:
        """The covenant vow added effects riding this cast (#4581).

        Read before the ward check so eligible vow profiles can bypass wards.
        This read spends nothing; firings are recorded only after an unbounced cast.
        ``[]`` when the action carries no technique, and ``[]`` below success
        level 1: the same gate that spends a once-per-round or once-per-fight
        row, so a cast that could not spend a row cannot use it either (a
        payload row authored with ``minimum_success_level=0`` would otherwise
        land on every partial success without ever being spent).
        """
        technique = self.action.focused_action
        if technique is None or (check_result.success_level or 0) < 1:
            return []
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415
        from world.covenants.added_effects import vow_added_effects_for_cast  # noqa: PLC0415

        return vow_added_effects_for_cast(
            self.participant.character_sheet,
            technique,
            resolution=CombatRoundContext(self.participant),
            target=_resolve_primary_target_sheet(self.action),
        )

    def __call__(
        self,
        *,
        power: int,  # noqa: ARG002
        ledger: PowerLedger,
        extra_modifiers: int = 0,  # noqa: ARG002
    ) -> CombatTechniqueResolution:
        """Resolve the combat technique inner step.

        ``power`` is injected by ``use_technique`` after the PRE_CAST envelope
        (it equals stats.intensity including identity modifiers, and may have
        been further modified by a pre-cast MODIFY_PAYLOAD hook).  INTENSITY_BUMP
        pull bonuses from the current round are added on top inside this method
        so the final effective intensity = power + pull intensity bumps.

        ``ledger`` is the per-cast :class:`PowerLedger` carrying all stages up
        to and including the environment power-shift.  The resolver appends a
        ``COMBAT_PULL`` stage for the INTENSITY_BUMP bonuses sourced from active
        :class:`~world.combat.models.CombatPull` rows and builds a per-target
        ledger whose ``total`` equals the final effective intensity forwarded to
        damage and condition resolution.
        """
        from world.magic.constants import PowerStage  # noqa: PLC0415
        from world.magic.types.power_ledger import PowerLedgerBuilder  # noqa: PLC0415

        pull_bonus = self._sum_intensity_bump_pulls()
        combat_ledger = (
            PowerLedgerBuilder.from_ledger(ledger)
            .add(PowerStage.COMBAT_PULL, "combat pulls", pull_bonus)
            .build()
        )
        check_result = self._roll_check()

        # Penetration-vs-resistance contest (#639): if the focused target has a
        # ward (barrier_strength > 0), the caster rolls a penetration check
        # against the ward and the resulting factor SCALES power before it
        # enters the unchanged damage/condition path. Unwarded targets are
        # unopposed — no check, no ledger entry, behavior identical to pre-#639.
        from world.covenants.added_effects import (  # noqa: PLC0415
            record_vow_effect_firings,
            vow_damage_profiles,
        )

        fired = self._fired_vow_effects(check_result)
        profiles = [(profile, 0) for profile in self._effective_damage_profiles()]
        profiles.extend(vow_damage_profiles(fired))
        bounced = False
        if not any(profile.bypasses_wards for profile, _ in profiles):
            combat_ledger, bounced = self._apply_penetration(combat_ledger)
        eff_intensity = combat_ledger.total

        if bounced:
            # Bounced off the ward: no damage, no conditions. The returned
            # ledger still records the bounce so narration can pose it. (A
            # legitimately zero-power UNWARDED cast does NOT take this path —
            # it still flows to base_damage downstream.)
            return CombatTechniqueResolution(
                check_result=check_result,
                damage_results=[],
                applied_conditions=[],
                pull_flat_bonus=self.pull_flat_bonus,
                scaled_damage=0,
                power_ledger=combat_ledger,
            )

        damage_results = self._apply_damage(
            check_result, eff_intensity=eff_intensity, profiles=profiles
        )
        applied_conditions, removed_conditions = self._apply_conditions(
            check_result, eff_intensity=eff_intensity, fired_vow_effects=fired
        )
        morale_shifts = self._apply_morale(check_result, eff_intensity=eff_intensity)
        # A manifesting technique brings the caster's bound entity into the fight (#4118),
        # but only on a successful, unbounced cast: a failed roll manifests nothing.
        if (check_result.success_level or 0) >= 1:
            # A once-per-round or once-per-fight vow effect is spent only by a cast
            # that landed (#4581): a failed roll, like a bounce (returned above),
            # leaves it for the holder's next cast. ``fired`` is empty below this
            # same gate, so the effects used and the effects spent always agree.
            record_vow_effect_firings(fired, encounter=self.participant.encounter)
            from world.magic.services.effect_handlers import (  # noqa: PLC0415
                manifest_bound_entity,
            )

            manifest_bound_entity(
                participant=self.participant, technique=self.action.focused_action
            )
        return CombatTechniqueResolution(
            check_result=check_result,
            damage_results=damage_results,
            applied_conditions=applied_conditions,
            pull_flat_bonus=self.pull_flat_bonus,
            scaled_damage=sum(r.damage_dealt for r in damage_results),
            power_ledger=combat_ledger,
            removed_conditions=removed_conditions,
            morale_shifts=morale_shifts,
        )
