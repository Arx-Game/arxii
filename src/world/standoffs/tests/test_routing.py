"""Settling every group completes the encounter and routes the mission once, on the terms."""

from types import SimpleNamespace
from unittest.mock import patch

from flows.events.payloads import EncounterCompletedPayload
from world.checks.factories import CheckTypeFactory
from world.combat.beat_wiring import encounter_completed_beat_handler
from world.combat.constants import CauseKind, EncounterOutcome, RiskLevel
from world.combat.models import CombatEncounter, EncounterOutcomeMapping
from world.conditions.factories import ConditionTemplateFactory
from world.missions.factories import MissionNodeFactory, MissionOptionRouteFactory
from world.missions.services.encounter_option import complete_encounter_for_option
from world.missions.services.resolution import resolve_option
from world.missions.tests.test_encounter_option import EncounterOptionTestBase
from world.standoffs.constants import StandoffGroupState, TermsEffect
from world.standoffs.factories import StandoffTermsFactory
from world.standoffs.models import StandoffConfig
from world.standoffs.services.verbs import standoff_terms
from world.traits.factories import CheckOutcomeFactory

CHECK = "world.standoffs.services.verbs.perform_check"
ROUTE = "world.missions.services.encounter_option._route_graded_outcome"


class StandoffRoutingTests(EncounterOptionTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.creature.cause = CauseKind.NONE
        self.creature.save(update_fields=["cause"])
        self.option.opens_as_standoff = True
        self.option.save(update_fields=["opens_as_standoff"])
        self.next_node = MissionNodeFactory(template=self.template, key="next")
        self.success_tier = CheckOutcomeFactory(name="Routing success", success_level=1)
        self.partial_tier = CheckOutcomeFactory(name="Routing partial", success_level=0)
        self.battle_tier = CheckOutcomeFactory(name="Routing battle", success_level=5)
        for tier in (self.success_tier, self.partial_tier, self.battle_tier):
            MissionOptionRouteFactory(
                option=self.option, outcome_tier=tier, target_node=self.next_node
            )
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=self.battle_tier,
        )
        config = StandoffConfig.load()
        config.terms_check_type = CheckTypeFactory()
        config.pass_condition = ConditionTemplateFactory()
        config.save()
        self.deed = resolve_option(self.instance, self.entry, self.option, self.participant)
        self.encounter = CombatEncounter.objects.get(scenario_deed=self.deed)
        self.group = self.encounter.standoff_groups.get()
        self.combat_participant = self.encounter.participants.get()
        self.terms = StandoffTermsFactory(effect=TermsEffect.PASS)

    def _terms(self, tier: CheckOutcomeFactory) -> object:
        roll = SimpleNamespace(success_level=tier.success_level, outcome=tier)
        with patch(CHECK, return_value=roll):
            return standoff_terms(self.combat_participant, self.group, self.terms)

    def test_mission_routes_once_on_the_terms_tier(self) -> None:
        with patch(
            ROUTE,
            wraps=__import__(
                "world.missions.services.resolution", fromlist=["x"]
            )._route_graded_outcome,
        ) as routed:
            result = self._terms(self.partial_tier)
            self.assertTrue(result.settled)
            payload = EncounterCompletedPayload(
                encounter=self.encounter,
                outcome=str(EncounterOutcome.VICTORY),
                scene=self.scene,
                room=self.room,
            )
            encounter_completed_beat_handler(payload=payload)
            self.assertIsNone(complete_encounter_for_option(self.encounter))
        self.assertEqual(routed.call_count, 1)
        self.assertEqual(routed.call_args.args[4], self.partial_tier)
        self.deed.refresh_from_db()
        self.assertEqual(self.deed.outcome, self.partial_tier)
        self.instance.refresh_from_db()
        self.assertFalse(self.instance.is_paused)
        self.assertEqual(self.instance.current_node, self.next_node)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.outcome, EncounterOutcome.VICTORY)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.SETTLED)
