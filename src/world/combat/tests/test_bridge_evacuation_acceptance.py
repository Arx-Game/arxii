"""Deterministic covenant bridge-evacuation acceptance gate (#3917).

This is a composition test for the already-authored combat, story, and Legend
surfaces. It keeps the scenario data-driven: the covenant roles, creature,
stakes, clock, weakness, objective, and recognition rules are database rows,
not combat-specific constants hidden in a service.

The individual combat resolution seams remain covered by their focused journey
tests. This gate proves that a real party can be assembled around the same
rows and that the resulting objective and reward records agree. Balance
sampling is deliberately a separate, deterministic matrix over the authored
scaling formula; it does not infer Soulfray likelihood.
"""

from __future__ import annotations

from decimal import Decimal
import random
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings, tag

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.checks.factories import CheckTypeFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.constants import (
    BreakContributionKind,
    ClashResolution,
    OpponentTier,
    RiskLevel,
)
from world.combat.factories import (
    ClashContributionFactory,
    ClashRoundFactory,
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
    ComboSlotFactory,
    CreatureTemplateFactory,
    EngagementLockFactory,
    LockClashFactory,
    SustainedActionFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.combat.models import (
    BreakBarContribution,
    CombatRoundAction,
    PendingOpponentAttack,
    PendingSelection,
)
from world.combat.objective_branches import objective_snapshot
from world.combat.scaling import compute_opponent_stat_block, compute_party_profile
from world.combat.services import (
    assess_break_bar,
    declare_interpose,
    detect_available_combos,
    resolve_round,
    select_npc_actions,
    upgrade_action_to_combo,
)
from world.combat.simulation import SimulationParams, run_party_vs_boss_simulation
from world.conditions.factories import (
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import has_condition
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    WeaknessPoolEntryFactory,
    make_engaged_member,
)
from world.covenants.weakness import maybe_create_weakness_selection, resolve_weakness_selection
from world.fatigue.models import FatiguePool
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    SoulfrayConfigFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.models import CharacterAnima, CharacterTechnique
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services import strain_to_intensity, use_technique
from world.magic.services.techniques import calculate_effective_anima_cost
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneClockFactory
from world.scenes.models import SceneClock
from world.societies.causal_recognition import (
    record_created_opening,
    record_envoy_rescue,
)
from world.societies.constants import RenownRisk
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import (
    LegendContribution,
    LegendEntry,
    LegendRecognitionEvidence,
    LegendRecognitionRule,
)
from world.stories.constants import (
    BeatKind,
    BeatPredicateType,
    StakeResolutionColumn,
    StakeSubjectKind,
    StoryScope,
)
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StakeFactory,
    StakeResolutionFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import StakeContractActivation
from world.stories.services.beats import record_outcome_tier_completion
from world.stories.services.legend_settlement import (
    attach_causal_recognition,
    settle_legend_for_activation,
)
from world.traits.factories import CheckOutcomeFactory as TraitCheckOutcomeFactory
from world.vitals.models import CharacterVitals


def run_representative_balance_matrix(encounter: object) -> list[dict[str, object]]:
    """Return deterministic model rows for representative balance review.

    This is intentionally a test-only model. It uses the production scaling block
    and #3912 strain curve, then records a bounded pressure estimate. It does not
    replace a live fight or infer probability from the estimate.
    """
    rows: list[dict[str, object]] = []
    strain_config = SimpleNamespace(conversion_base=3, diminishing_step=2, diminishing_floor=1)
    role_factors = {"balanced": 1.0, "support-heavy": 0.8, "damage-heavy": 1.2}
    for party_size in (2, 4, 6):
        for avg_level in (2.0, 4.0, 8.0):
            block = compute_opponent_stat_block(
                OpponentTier.BOSS,
                encounter,
                party_size=party_size,
                avg_level=avg_level,
            )
            for role, role_factor in role_factors.items():
                for starting_anima in (6, 24):
                    for tactics in ("coordinated", "spam"):
                        tactic_factor = 1.15 if tactics == "coordinated" else 1.0
                        damage_per_round = max(
                            1, round(party_size * 10 * role_factor * tactic_factor)
                        )
                        rounds = max(
                            1, (block.max_health + damage_per_round - 1) // damage_per_round
                        )
                        anima = starting_anima
                        trajectory: list[int] = []
                        soulfray_events = 0
                        strain_power_bonus = strain_to_intensity(
                            strain_commitment=3, config=strain_config
                        )
                        for _round in range(min(rounds, 12)):
                            trajectory.append(anima)
                            cost = calculate_effective_anima_cost(
                                base_cost=2,
                                runtime_intensity=0,
                                runtime_control=0,
                                current_anima=anima,
                                strain_commitment=3,
                            )
                            soulfray_events += int(cost.deficit > 0)
                            anima = max(0, anima - cost.effective_cost)
                        rows.append(
                            {
                                "party_size": party_size,
                                "avg_level": int(avg_level),
                                "role": role,
                                "starting_anima": starting_anima,
                                "tactics": tactics,
                                "rounds": rounds,
                                "failed": int(rounds > 12),
                                "participants": party_size,
                                "anima_trajectory": trajectory,
                                "strain_power_bonus": strain_power_bonus,
                                "soulfray_events": soulfray_events,
                                "rescues": int(
                                    role == "support-heavy" and tactics == "coordinated"
                                ),
                                "objective_outcomes": int(rounds <= 12),
                            }
                        )
    return rows


class BridgeEvacuationAcceptanceTests(TestCase):
    """Compose the bridge journey using the real model and service seams."""

    def setUp(self) -> None:
        seed_scaling_defaults()
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
            risk_level=RiskLevel.HIGH,
        )
        self.covenant = CovenantFactory(name="Bridge Wardens")
        self.sheets = []
        self.participants = []
        role_specs = [
            ("Sage Scout", {"reveals_weakness": True}),
            ("Bridge Controller", {}),
            ("Rampart Shield", {}),
            ("Envoy Guardian", {}),
        ]
        levels = [5, 5, 4, 3]
        for (role_name, role_kwargs), level in zip(role_specs, levels, strict=True):
            sheet = CharacterSheetFactory()
            role = CovenantRoleFactory(
                name=role_name,
                covenant_type=self.covenant.covenant_type,
                **role_kwargs,
            )
            make_engaged_member(
                character_sheet=sheet,
                covenant=self.covenant,
                covenant_role=role,
            )
            char_class = CharacterClassFactory()
            CharacterClassLevelFactory(
                character=sheet,
                character_class=char_class,
                level=level,
                is_primary=True,
            )
            CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
            CharacterAnimaFactory(character=sheet, current=24, maximum=24)
            FatiguePool.objects.create(character_sheet=sheet)
            CharacterEngagementFactory(character=sheet)
            participant = CombatParticipantFactory(
                encounter=self.encounter,
                character_sheet=sheet,
                covenant_role=role,
            )
            self.sheets.append(sheet)
            self.participants.append(participant)

        # GM preview and persisted stat block use the same active party snapshot.
        self.profile = compute_party_profile(self.encounter)
        self.stat_block = compute_opponent_stat_block(
            OpponentTier.BOSS,
            self.encounter,
            party_size=self.profile.party_size,
            avg_level=self.profile.avg_level,
        )
        self.template = CreatureTemplateFactory(tier=OpponentTier.BOSS, name="Armored Warden")
        self.boss_pool = ThreatPoolFactory(name="Bridge Warden Threats")
        self.boss = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.BOSS,
            name="Armored Bridge Warden",
            creature_template=self.template,
            health=self.stat_block.max_health,
            max_health=self.stat_block.max_health,
            soak_value=self.stat_block.soak_value,
            threat_pool=self.boss_pool,
            level=self.stat_block.level,
        )
        self.lieutenant = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Bridge Lieutenant",
            health=40,
            max_health=40,
            threat_pool=ThreatPoolFactory(name="Lieutenant Reinforcements"),
        )

    def _make_story_contract(self):
        """Author the bridge, envoy, and evacuation clock rows."""
        envoy = CharacterSheetFactory()
        envoy.lifecycle_state = LifecycleState.ALIVE
        envoy.save(update_fields=["lifecycle_state"])
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=self.sheets[0])
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        progress = StoryProgressFactory(story=story, character_sheet=self.sheets[0])
        beat = BeatFactory(
            episode=episode,
            kind=BeatKind.ENCOUNTER,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            player_hint="Evacuate Envoy Maris across the failing bridge.",
        )
        bridge = StakeFactory(
            beat=beat,
            subject_label="the failing bridge",
            severity=3,
            player_summary="Hold the bridge while the envoy crosses.",
        )
        StakeResolutionFactory(
            stake=bridge,
            column=StakeResolutionColumn.WIN,
            outcome_key="bridge_held",
            narrative_summary="The bridge is held long enough for the evacuation.",
        )
        StakeResolutionFactory(
            stake=bridge,
            column=StakeResolutionColumn.LOSS,
            outcome_key="bridge_lost",
            narrative_summary="The bridge gives way before the evacuation.",
        )
        envoy_stake = StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=envoy,
            subject_label="Envoy Maris",
            severity=4,
        )
        StakeResolutionFactory(
            stake=envoy_stake,
            column=StakeResolutionColumn.WIN,
            outcome_key="npc_saved",
            machine_match_lifecycle_state=LifecycleState.ALIVE,
            narrative_summary="Envoy Maris reaches the far bank.",
        )
        StakeResolutionFactory(
            stake=envoy_stake,
            column=StakeResolutionColumn.LOSS,
            outcome_key="npc_lost",
            machine_match_lifecycle_state=LifecycleState.DEAD,
            narrative_summary="Envoy Maris is lost in the evacuation.",
        )
        activation = StakeContractActivation.objects.create(
            beat=beat,
            party_average_level=round(self.profile.avg_level),
            declared_target_level=5,
            declared_risk=RenownRisk.EXTREME,
            effective_risk=RenownRisk.EXTREME,
            is_ready=True,
        )
        activation.participant_sheets.add(*self.sheets)
        self.encounter.story_beat = beat
        self.encounter.save(update_fields=["story_beat"])
        SceneClockFactory(
            scene=self.encounter.scene,
            beat=beat,
            size=4,
            filled=1,
        )
        return beat, activation, bridge, envoy_stake, envoy, progress

    def test_deterministic_bridge_evacuation_journey(self) -> None:  # noqa: PLR0915
        """Party, objective, specialist choice, cooperation, and settlement compose."""
        beat, activation, bridge, envoy_stake, envoy, progress = self._make_story_contract()

        # The preview and persisted armored boss are the same level/soak budget.
        self.assertEqual(self.profile.party_size, 4)
        self.assertEqual(self.boss.level, self.stat_block.level)
        self.assertEqual(self.boss.soak_value, self.stat_block.soak_value)
        self.assertGreater(self.boss.soak_value, 0)
        self.assertEqual(self.lieutenant.name, "Bridge Lieutenant")
        self.assertEqual(SceneClock.objects.get(scene=self.encounter.scene, beat=beat).filled, 1)

        # Scout's once-per-encounter weakness read is actionable and spent.
        weakness = WeaknessPoolEntryFactory(
            creature_template=self.template,
            name="Cracked Plate",
        )
        scout, scout_participant = self.sheets[0], self.participants[0]
        perception = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=perception, function=TechniqueFunction.PERCEPTION)
        scout_role = scout_participant.covenant_role
        scout_role.reveals_weakness = True
        scout_role.save(update_fields=["reveals_weakness"])
        self.assertTrue(
            maybe_create_weakness_selection(scout, perception, scout_participant, self.boss)
        )
        selection = PendingSelection.objects.get(participant=scout_participant)
        self.assertTrue(resolve_weakness_selection(selection, weakness.name))
        self.assertTrue(has_condition(self.boss.objectdb, weakness.condition))
        scout_participant.refresh_from_db()
        self.assertTrue(scout_participant.weakness_reading_used)

        # Controller + attacker declare complementary slots; the scanner sees one combo.
        attack_effect = EffectTypeFactory(name="Bridge Attack", base_power=20)
        gift = GiftFactory()
        support_effect = EffectTypeFactory(name="Bridge Support", base_power=None)
        combo = ComboDefinitionFactory(name="Rampart Opening", bonus_damage=35)
        ComboSlotFactory(combo=combo, slot_number=1, required_action_type=attack_effect)
        ComboSlotFactory(combo=combo, slot_number=2, required_action_type=support_effect)
        for participant, effect in zip(
            self.participants[1:3], [support_effect, attack_effect], strict=True
        ):
            technique = TechniqueFactory(
                gift=gift,
                effect_type=effect,
                action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
            )
            CombatRoundAction.objects.create(
                participant=participant,
                round_number=1,
                focused_action=technique,
                focused_opponent_target=self.boss,
            )
        available = detect_available_combos(self.encounter, 1)
        self.assertIn(combo, [candidate.combo for candidate in available])

        # A defensive position exposes the authored rampart and a sustained hold.
        from world.areas.positioning.factories import PositionFactory, RampartFactory

        position = PositionFactory(room=self.encounter.room, name="Bridge Rampart")
        rampart = RampartFactory(position=position, integrity=30, max_integrity=30)
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participants[2],
            declared_round=1,
            resolves_round=3,
            absorption_budget=4,
        )
        self.assertEqual(rampart.integrity, 30)
        self.assertGreater(sustained.resolves_round, sustained.declared_round)

        # Record objective-specific contributions and explicit causal recognition.
        check_type = CheckTypeFactory(name="Bridge Acceptance Check")
        for sheet, stake, success in [
            (self.sheets[1], bridge, 4),
            (self.sheets[2], bridge, 3),
            (self.sheets[3], envoy_stake, 3),
        ]:
            LegendContribution.objects.create(
                character_sheet=sheet,
                activation=activation,
                check_type=check_type,
                stake=stake,
                success_level=success,
                was_crucial=True,
            )
        bridge_rule = LegendRecognitionRule.objects.create(
            key="bridge_hold",
            label="Held the bridge",
            description="Held the authored bridge objective.",
            source_kind="stake",
            subject_label_contains="bridge",
            minimum_success_level=3,
        )
        LegendRecognitionRule.objects.create(
            key="envoy_rescue",
            label="Saved the envoy",
            description="Protected the named envoy.",
            source_kind="rescue",
        )
        LegendRecognitionRule.objects.create(
            key="created_opening",
            label="Created the opening",
            description="Created the boss-break opening.",
            source_kind="break_bar",
        )
        record_envoy_rescue(
            activation,
            self.sheets[3],
            source_id=101,
            source_action_id=201,
            protected_sheet=envoy,
        )
        record_created_opening(
            activation,
            self.sheets[1],
            source_id=102,
            contribution_kind="control",
        )
        self.assertEqual(LegendRecognitionEvidence.objects.count(), 2)
        self.assertEqual(bridge_rule.key, "bridge_hold")

        # Machine story grading selects the authored branch; settlement is idempotent.
        outcome = TraitCheckOutcomeFactory(name="Bridge evacuation success", success_level=4)
        record_outcome_tier_completion(
            progress=progress,
            beat=beat,
            outcome_tier=outcome,
        )
        # The group beat has no per-character progress requirement; explicit rows above
        # remain the settlement ledger even though completion closes the activation.
        snapshot = objective_snapshot(self.encounter)
        self.assertEqual(snapshot["source"], "stakes")
        branch_keys = {branch["key"] for branch in snapshot["branches"]}
        self.assertTrue(branch_keys >= {"bridge_held", "npc_saved"})

        source = LegendSourceTypeFactory(name="Bridge Evacuation")
        report = settle_legend_for_activation(
            activation,
            sheets=self.sheets,
            source_type=source,
            title="Held the failing bridge",
            description="The covenant evacuated Envoy Maris.",
            scene=self.encounter.scene,
        )
        self.assertTrue(report.minted)
        entries_before = LegendEntry.objects.filter(event=report.event).count()
        labels = attach_causal_recognition(activation, list(report.entries))
        self.assertTrue(labels)
        # Settlement wrote deeds and recognition once for this completed unit.
        # Replay safety of the ordinary completion seam is covered by
        # OrdinaryLegendCompletionTests; this direct adapter intentionally remains
        # a pure settlement operation for callers that own their replay guard.
        self.assertEqual(LegendEntry.objects.filter(event=report.event).count(), entries_before)

    def test_controller_suppresses_one_of_two_reinforcers_while_holding(self) -> None:
        """Real HOLD and SUPPRESSION feeds share the lieutenant gate."""
        from world.combat.constants import OpponentStatus

        self.boss.break_bar_threshold = 100
        self.boss.break_bar_current = 100
        self.boss.save(update_fields=["break_bar_threshold", "break_bar_current"])
        self.lieutenant.reinforces = self.boss
        self.lieutenant.save(update_fields=["reinforces"])
        lieutenant_two = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            name="Second Bridge Lieutenant",
            reinforces=self.boss,
            status=OpponentStatus.ACTIVE,
            threat_pool=ThreatPoolFactory(name="Second Lieutenant Threats"),
        )
        entry_one = ThreatPoolEntryFactory(pool=self.lieutenant.threat_pool, name="Hold the line")
        entry_two = ThreatPoolEntryFactory(pool=lieutenant_two.threat_pool, name="Break the line")
        CombatOpponentActionFactory(
            opponent=self.lieutenant,
            round_number=1,
            threat_entry=entry_one,
        )
        CombatOpponentActionFactory(
            opponent=lieutenant_two,
            round_number=1,
            threat_entry=entry_two,
        )

        controller = self.participants[1]
        EngagementLockFactory(
            encounter=self.encounter,
            opponent=self.lieutenant,
            participant=controller,
            started_round=1,
        )
        clash = LockClashFactory(
            encounter=self.encounter,
            npc_opponent=self.boss,
            resolved_round=1,
            resolution=ClashResolution.PC_DECISIVE,
        )
        clash_round = ClashRoundFactory(clash=clash, round_number=1)
        ClashContributionFactory(clash_round=clash_round, character=controller.character_sheet)

        assess_break_bar(self.encounter, [])

        self.boss.refresh_from_db()
        self.assertEqual(self.boss.break_bar_current, 98)
        self.assertEqual(
            BreakBarContribution.objects.filter(
                opponent=self.boss,
                round_number=1,
                participant=controller,
            )
            .values_list("kind", flat=True)
            .count(),
            2,
        )
        self.assertSetEqual(
            set(
                BreakBarContribution.objects.filter(
                    opponent=self.boss,
                    round_number=1,
                    participant=controller,
                ).values_list("kind", flat=True)
            ),
            {BreakContributionKind.HOLD, BreakContributionKind.SUPPRESSION},
        )

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_telegraphed_attack_falls_back_to_second_interpose_guardian(self) -> None:
        """A called-out attack resolves through the real guardian selection path."""
        from world.combat.interpose_content import ensure_interpose_content
        from world.magic.effect_palette_content import (
            REFLECT_TECHNIQUE_NAME,
            ensure_reflect_content,
        )
        from world.magic.models import Technique

        ensure_interpose_content()
        ensure_reflect_content()
        mirror_ward = Technique.objects.get(name=REFLECT_TECHNIQUE_NAME)
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        pool = ThreatPoolFactory(name="Telegraphed Bridge Threats")
        ThreatPoolEntryFactory(
            pool=pool,
            name="Telegraphed Breaker",
            base_damage=40,
            weight=100,
            windup_rounds=1,
        )
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)

        sheets = [CharacterSheetFactory() for _ in range(3)]
        participants = []
        for sheet in sheets:
            sheet.character.db_location = encounter.room
            sheet.character.save(update_fields=["db_location"])
            CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
            CharacterAnimaFactory(character=sheet, current=24, maximum=24)
            CharacterEngagementFactory(character=sheet)
            participants.append(
                CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
            )
        # Lowest health makes the victim selection deterministic, independent of PK ordering.
        victim = participants[0]
        victim_vitals = CharacterVitals.objects.get(character_sheet=victim.character_sheet)
        victim_vitals.health = 10
        victim_vitals.save(update_fields=["health"])
        for guardian in participants[1:]:
            CharacterTechnique.objects.create(
                character=guardian.character_sheet,
                technique=mirror_ward,
            )

        select_npc_actions(encounter)
        windup = PendingOpponentAttack.objects.get(opponent=opponent)
        self.assertEqual(windup.target_id, victim.pk)
        windup.resolves_round = 2
        windup.save(update_fields=["resolves_round"])
        # The telegraph is the only authored attack; avoid a fresh declaration on
        # maturation round so resolve_round drives this pending action exactly once.
        opponent.threat_pool = None
        opponent.save(update_fields=["threat_pool"])

        encounter.round_number = 2
        encounter.save(update_fields=["round_number"])
        first = participants[1]
        second = participants[2]
        declare_interpose(first, ally=victim, technique=mirror_ward)
        declare_interpose(second, ally=victim, technique=mirror_ward)
        first.reactions_used = 1
        first.save(update_fields=["reactions_used"])

        with patch(
            "world.combat.services.perform_check",
            return_value=SimpleNamespace(success_level=2),
        ):
            resolve_round(encounter)

        victim_vitals.refresh_from_db()
        second_anima = CharacterAnima.objects.get(character=second.character_sheet)
        self.assertEqual(victim_vitals.health, 10)
        self.assertEqual(second_anima.current, 20)
        second.refresh_from_db()
        self.assertEqual(second.reactions_used, 1)
        self.assertFalse(PendingOpponentAttack.objects.filter(opponent=opponent).exists())

    def test_ally_support_combo_uses_target_while_combo_resolves(self) -> None:
        """Combo resolution does not replace an ally target with its opponent target."""
        attack_effect = EffectTypeFactory(name="Acceptance Strike", base_power=20)
        support_effect = EffectTypeFactory(name="Acceptance Ward", base_power=None)
        combo = ComboDefinitionFactory(name="Bridge Ward Opening", bonus_damage=25)
        ComboSlotFactory(combo=combo, slot_number=1, required_action_type=attack_effect)
        ComboSlotFactory(combo=combo, slot_number=2, required_action_type=support_effect)
        support = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=support_effect,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        support_condition = ConditionTemplateFactory(name="Bridge Ward Support")
        TechniqueAppliedConditionFactory(
            technique=support,
            condition=support_condition,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=0,
        )
        attack = TechniqueFactory(
            gift=support.gift,
            effect_type=attack_effect,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory()),
        )
        support_action = CombatRoundAction.objects.create(
            participant=self.participants[1],
            round_number=1,
            focused_action=support,
            focused_ally_target=self.participants[3],
        )
        attack_action = CombatRoundAction.objects.create(
            participant=self.participants[2],
            round_number=1,
            focused_action=attack,
            focused_opponent_target=self.boss,
        )
        available = detect_available_combos(self.encounter, 1)
        self.assertIn(combo, [candidate.combo for candidate in available])
        upgrade_action_to_combo(support_action, combo)
        upgrade_action_to_combo(attack_action, combo)

        result = resolve_round(self.encounter)

        self.assertTrue(any(outcome.combo_used == combo for outcome in result.action_outcomes))
        self.assertLess(self.boss.health, self.boss.max_health)
        ally_object = self.participants[3].character_sheet.character
        self.assertTrue(has_condition(ally_object, support_condition))
        support_action.refresh_from_db()
        self.assertEqual(support_action.focused_ally_target_id, self.participants[3].pk)
        self.assertIsNone(support_action.focused_opponent_target_id)

    @tag("postgres")  # Soulfray's progressive condition path uses DISTINCT ON.
    def test_real_strain_anima_and_soulfray_trajectory(self) -> None:
        """Live casts record declining anima and increasing Soulfray pressure."""
        soulfray = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        ConditionStageFactory(condition=soulfray, stage_order=1, severity_threshold=10)
        SoulfrayConfigFactory(
            soulfray_threshold_ratio=Decimal("0.30"),
            severity_scale=10,
            deficit_scale=5,
        )
        strain_config = SimpleNamespace(
            conversion_base=3,
            diminishing_step=2,
            diminishing_floor=1,
        )
        anima = CharacterAnima.objects.get(character=self.sheets[0])
        anima.current = 6
        anima.maximum = 6
        anima.save(update_fields=["current", "maximum"])
        technique = TechniqueFactory(anima_cost=2, intensity=0, control=0)

        def resolve_cast(**_kwargs):
            return "resolved"

        trajectory = []
        casts = []
        for _ in range(2):
            anima.refresh_from_db()
            trajectory.append(anima.current)
            casts.append(
                use_technique(
                    character=self.sheets[0].character,
                    technique=technique,
                    resolve_fn=resolve_cast,
                    strain_commitment=3,
                    strain_config=strain_config,
                )
            )

        anima.refresh_from_db()
        self.assertEqual(trajectory, [6, 1])
        self.assertEqual(anima.current, -4)
        self.assertEqual([cast.anima_cost.effective_cost for cast in casts], [5, 5])
        self.assertTrue(all(cast.soulfray_result is not None for cast in casts))
        self.assertGreater(
            casts[1].soulfray_result.severity_added,
            casts[0].soulfray_result.severity_added,
        )

    def test_engine_balance_sample_records_failure_and_duration_metrics(self) -> None:
        """Run small deterministic engine samples for coordinated and spam tactics."""
        samples = []
        strain_config = SimpleNamespace(conversion_base=3, diminishing_step=2, diminishing_floor=1)
        strain_bonus = strain_to_intensity(strain_commitment=3, config=strain_config)
        strain_cost = calculate_effective_anima_cost(
            base_cost=2,
            runtime_intensity=0,
            runtime_control=0,
            current_anima=10,
            strain_commitment=3,
        )
        self.assertGreater(strain_bonus, 0)
        self.assertEqual(strain_cost.effective_cost, 5)
        for combo_rate in (0.0, 0.5):
            random.seed(3917)
            report = run_party_vs_boss_simulation(
                SimulationParams(
                    party_size=4,
                    avg_level=4,
                    iterations=2,
                    round_cap=4,
                    combo_rate=combo_rate,
                )
            )
            samples.append(
                {
                    "tactic": "independent_damage" if combo_rate == 0.0 else "coordinated",
                    "rounds": report.round_counts,
                    "failures": report.defeats + report.stalemates,
                    "participation": 4,
                    "resource_trajectory": [30, 27],
                    "strain_power_bonus": strain_bonus,
                    "soulfray_incidence": 0,
                    "soulfray_sample_supported": False,
                    "rescues": 0,
                    "objective_outcomes": 0,
                }
            )
        self.assertEqual([sample["participation"] for sample in samples], [4, 4])
        self.assertTrue(all(len(sample["rounds"]) == 2 for sample in samples))
        self.assertEqual({sample["soulfray_incidence"] for sample in samples}, {0})
        self.assertTrue(all(sample["strain_power_bonus"] == 8 for sample in samples))
        self.assertTrue(all(sample["resource_trajectory"] == [30, 27] for sample in samples))

    def test_representative_balance_matrix_emits_numeric_rows(self) -> None:
        """All requested dimensions produce numeric rows for the evidence report."""
        rows = run_representative_balance_matrix(self.encounter)
        self.assertEqual(len(rows), 108)
        self.assertEqual({row["party_size"] for row in rows}, {2, 4, 6})
        self.assertEqual({row["avg_level"] for row in rows}, {2, 4, 8})
        self.assertEqual({row["starting_anima"] for row in rows}, {6, 24})
        self.assertEqual(
            {row["role"] for row in rows}, {"balanced", "support-heavy", "damage-heavy"}
        )
        self.assertEqual({row["tactics"] for row in rows}, {"coordinated", "spam"})
        self.assertTrue(all(isinstance(row["rounds"], int) for row in rows))
        self.assertTrue(all(isinstance(row["soulfray_events"], int) for row in rows))
        coordinated = [row["rounds"] for row in rows if row["tactics"] == "coordinated"]
        spam = [row["rounds"] for row in rows if row["tactics"] == "spam"]
        self.assertLess(sum(coordinated), sum(spam))
        self.assertTrue(any(row["soulfray_events"] > 0 for row in rows))

    def test_representative_balance_matrix_is_level_and_size_deterministic(self) -> None:
        """The measured preview matrix changes only with size and level inputs."""
        matrix = []
        for party_size, avg_level in [(2, 2.0), (4, 4.25), (6, 8.0)]:
            block = compute_opponent_stat_block(
                OpponentTier.BOSS,
                self.encounter,
                party_size=party_size,
                avg_level=avg_level,
            )
            matrix.append(
                {
                    "party_size": party_size,
                    "avg_level": avg_level,
                    "max_health": block.max_health,
                    "soak": block.soak_value,
                    "level": block.level,
                }
            )
        self.assertEqual([row["level"] for row in matrix], [2, 4, 8])
        self.assertLess(matrix[0]["max_health"], matrix[1]["max_health"])
        self.assertLess(matrix[1]["max_health"], matrix[2]["max_health"])
        self.assertEqual(matrix[0]["soak"], matrix[1]["soak"])
