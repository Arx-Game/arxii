"""Objective-first encounter journeys (#3916).

These tests intentionally compose existing contracts: stake outcomes and lifecycle
matches for beat fights, and scenario routes for encounter options.  They do not
teach combat completion a new objective vocabulary.
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.combat.constants import EncounterOutcome, RiskLevel
from world.combat.factories import CombatEncounterFactory
from world.combat.models import EncounterOutcomeMapping
from world.combat.objective_branches import objective_snapshot
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionDeedRecord
from world.missions.services.encounter_option import complete_encounter_for_option
from world.societies.causal_recognition import record_envoy_rescue
from world.societies.models import LegendRecognitionEvidence, LegendRecognitionRule
from world.stories.constants import (
    BeatKind,
    BeatPredicateType,
    StakeOutcomeMethod,
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
from world.stories.services.beats import record_outcome_tier_completion
from world.stories.services.stakes import activate_stakes_contract
from world.traits.factories import CheckOutcomeFactory


class ObjectiveStakeJourneyTests(EvenniaTestCase):
    """Lifecycle and authored branch rows keep objective results independent."""

    def _contract(self, *, npc_state: str, success: bool):
        sheet = CharacterSheetFactory()
        npc = CharacterSheetFactory()
        npc.lifecycle_state = npc_state
        npc.save(update_fields=["lifecycle_state"])
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(
            episode=episode,
            kind=BeatKind.ENCOUNTER,
            predicate_type=BeatPredicateType.OUTCOME_TIER,
            player_hint="Hold the bridge while the envoy crosses.",
        )
        progress = StoryProgressFactory(story=story, character_sheet=sheet)
        boss = StakeFactory(beat=beat, subject_label="the bridge boss")
        StakeResolutionFactory(
            stake=boss,
            column=StakeResolutionColumn.WIN,
            outcome_key="boss_beaten",
            narrative_summary="The boss is beaten.",
        )
        StakeResolutionFactory(
            stake=boss,
            column=StakeResolutionColumn.LOSS,
            outcome_key="boss_not_beaten",
            narrative_summary="The boss remains standing.",
        )
        envoy = StakeFactory(
            beat=beat,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=npc,
            subject_label="the envoy",
        )
        StakeResolutionFactory(
            stake=envoy,
            column=StakeResolutionColumn.WIN,
            outcome_key="npc_saved",
            machine_match_lifecycle_state=LifecycleState.ALIVE,
            narrative_summary="The envoy survives.",
        )
        StakeResolutionFactory(
            stake=envoy,
            column=StakeResolutionColumn.WIN,
            outcome_key="npc_lost",
            machine_match_lifecycle_state=LifecycleState.DEAD,
            narrative_summary="The envoy is lost.",
        )
        StakeResolutionFactory(
            stake=envoy,
            column=StakeResolutionColumn.LOSS,
            outcome_key="npc_lost",
            machine_match_lifecycle_state=LifecycleState.DEAD,
            narrative_summary="The envoy is lost.",
        )
        activate_stakes_contract(beat, [sheet])
        tier = CheckOutcomeFactory(
            name="Objective success" if success else "Objective failure",
            success_level=3 if success else -3,
        )
        record_outcome_tier_completion(progress=progress, beat=beat, outcome_tier=tier)
        encounter = CombatEncounterFactory(story_beat=beat, outcome=EncounterOutcome.VICTORY)
        return encounter, beat, boss, envoy

    def test_boss_beaten_and_npc_saved_are_distinct_authored_branches(self):
        encounter, _beat, boss, envoy = self._contract(npc_state=LifecycleState.ALIVE, success=True)
        snapshot = objective_snapshot(encounter)
        self.assertEqual(
            [branch["key"] for branch in snapshot["branches"]],
            ["boss_beaten", "npc_saved"],
        )
        self.assertEqual(boss.outcomes.get().method, StakeOutcomeMethod.MACHINE)
        self.assertEqual(envoy.outcomes.get().column, StakeResolutionColumn.WIN)

    def test_boss_beaten_and_npc_lost_are_distinct_authored_branches(self):
        encounter, _beat, boss, envoy = self._contract(npc_state=LifecycleState.DEAD, success=True)
        snapshot = objective_snapshot(encounter)
        self.assertEqual(
            [branch["key"] for branch in snapshot["branches"]],
            ["boss_beaten", "npc_lost"],
        )
        self.assertEqual(boss.outcomes.get().column, StakeResolutionColumn.WIN)
        self.assertEqual(envoy.outcomes.get().column, StakeResolutionColumn.LOSS)

    def test_rescue_does_not_turn_a_lost_objective_into_a_win(self):
        encounter, beat, _boss, envoy = self._contract(npc_state=LifecycleState.DEAD, success=False)
        # The activation is closed by completion; find the same contract through the
        # evidence writer's explicit FK rather than inferring from combat outcome.
        from world.stories.models import StakeContractActivation

        activation = StakeContractActivation.objects.get(beat=beat)
        rule = LegendRecognitionRule.objects.create(
            key="envoy_rescue",
            source_kind="rescue",
            label="Rescued the envoy",
        )
        actor = beat.episode.chapter.story.character_sheet
        record_envoy_rescue(
            activation,
            actor,
            source_id=9001,
            source_action_id=9001,
            protected_sheet=envoy.subject_sheet,
        )
        self.assertEqual(LegendRecognitionEvidence.objects.get().rule, rule)
        self.assertEqual(envoy.outcomes.get().column, StakeResolutionColumn.LOSS)
        self.assertEqual(objective_snapshot(encounter)["branches"][-1]["key"], "npc_lost")


class ObjectiveScenarioJourneyTests(EvenniaTestCase):
    """Scenario encounter routes preserve retreat as a separate objective result."""

    def test_objective_secured_then_retreat_uses_fled_route(self):
        sheet = CharacterSheetFactory()
        template = MissionTemplateFactory()
        node = MissionNodeFactory(template=template, key="bridge", is_entry=True)
        next_node = MissionNodeFactory(template=template, key="safe-bank")
        instance = MissionInstanceFactory(template=template, source_beat=None)
        instance.current_node = node
        instance.save(update_fields=["current_node"])
        MissionParticipantFactory(instance=instance, character=sheet, is_contract_holder=True)
        option = MissionOptionFactory(
            node=node,
            key="secure-and-retreat",
            option_kind=OptionKind.ENCOUNTER,
            source_kind=OptionSource.AUTHORED,
            encounter_risk_level=RiskLevel.MODERATE,
            authored_ic_framing="Secure the bridge, then withdraw.",
        )
        tier = CheckOutcomeFactory(name="Secured before retreat", success_level=2)
        MissionOptionRouteFactory(
            option=option,
            outcome_tier=tier,
            target_node=next_node,
            outcome_text="The bridge is secured; the party withdraws safely.",
        )
        deed = MissionDeedRecord.objects.create(
            instance=instance,
            actor=sheet,
            node=node,
            option=option,
            outcome=None,
        )
        encounter = CombatEncounterFactory(scenario_deed=deed, risk_level=RiskLevel.MODERATE)
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.FLED,
            risk_level=RiskLevel.MODERATE,
            check_outcome=tier,
        )
        encounter.outcome = EncounterOutcome.FLED
        encounter.save(update_fields=["outcome"])

        complete_encounter_for_option(encounter)

        snapshot = objective_snapshot(encounter)
        self.assertEqual(encounter.outcome, EncounterOutcome.FLED)
        self.assertEqual(snapshot["branches"][0]["key"], "secure-and-retreat")
        self.assertEqual(snapshot["branches"][0]["outcome"], tier.name)
        self.assertIn("withdraws", snapshot["branches"][0]["label"])
