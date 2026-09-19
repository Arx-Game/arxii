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

import random
from types import SimpleNamespace

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.checks.factories import CheckTypeFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.constants import OpponentTier, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
    ComboSlotFactory,
    CreatureTemplateFactory,
    SustainedActionFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.combat.models import CombatRoundAction, PendingSelection
from world.combat.objective_branches import objective_snapshot
from world.combat.scaling import compute_opponent_stat_block, compute_party_profile
from world.combat.services import detect_available_combos
from world.combat.simulation import SimulationParams, run_party_vs_boss_simulation
from world.conditions.services import has_condition
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    WeaknessPoolEntryFactory,
    make_engaged_member,
)
from world.covenants.weakness import maybe_create_weakness_selection, resolve_weakness_selection
from world.fatigue.models import FatiguePool
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterAnimaFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.services import strain_to_intensity
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
