"""E2E: the standoff verbs through ``dispatch_player_action``, from a mission to its deed."""

from types import SimpleNamespace
from unittest.mock import patch

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import CauseKind, EncounterOutcome, OpponentTier, RiskLevel
from world.combat.factories import CombatEncounterFactory
from world.combat.models import CombatEncounter, EncounterOutcomeMapping
from world.conditions.factories import ConditionTemplateFactory
from world.mechanics.factories import ApplicationFactory
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
)
from world.missions.services.resolution import resolve_option
from world.missions.tests.test_encounter_option import EncounterOptionTestBase
from world.standoffs.constants import DriveStrength, RevealKind, StandoffGroupState, TermsEffect
from world.standoffs.factories import (
    CreatureDriveFactory,
    StandoffApproachFactory,
    StandoffGroupFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import StandoffConfig
from world.traits.factories import CheckOutcomeFactory

CHECK = "world.standoffs.services.verbs.perform_check"


def _ref(key: str) -> ActionRef:
    return ActionRef(backend=ActionBackend.REGISTRY, registry_key=key)


def _roll(tier: CheckOutcomeFactory) -> SimpleNamespace:
    return SimpleNamespace(success_level=tier.success_level, outcome=tier)


class StandoffJourneyBase(EncounterOptionTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.option.opens_as_standoff = True
        self.option.save(update_fields=["opens_as_standoff"])
        self.next_node = MissionNodeFactory(template=self.template, key="next")
        self.success_tier = CheckOutcomeFactory(name="Journey success", success_level=1)
        self.botch_tier = CheckOutcomeFactory(name="Journey botch", success_level=-2)
        self.battle_tier = CheckOutcomeFactory(name="Journey battle", success_level=5)
        for tier in (self.success_tier, self.battle_tier):
            MissionOptionRouteFactory(
                option=self.option, outcome_tier=tier, target_node=self.next_node
            )
        EncounterOutcomeMapping.objects.create(
            outcome=EncounterOutcome.VICTORY,
            risk_level=RiskLevel.MODERATE,
            check_outcome=self.battle_tier,
        )
        config = StandoffConfig.load()
        config.read_check_type = CheckTypeFactory()
        config.terms_check_type = CheckTypeFactory()
        config.pass_condition = ConditionTemplateFactory()
        config.save()
        self.approach = StandoffApproachFactory()
        self.terms = StandoffTermsFactory(effect=TermsEffect.PASS)

    def _open(self) -> None:
        self.deed = resolve_option(self.instance, self.entry, self.option, self.participant)
        self.encounter = CombatEncounter.objects.get(scenario_deed=self.deed)
        self.group = self.encounter.standoff_groups.get()

    def _do(self, key: str, **kwargs: int | str) -> object:
        return dispatch_player_action(self.character, _ref(key), kwargs).detail


class MissionJourneyTests(StandoffJourneyBase):
    def setUp(self) -> None:
        super().setUp()
        self.creature.cause = CauseKind.NONE
        self.creature.save(update_fields=["cause"])
        self.drive = CreatureDriveFactory(
            creature_template=self.creature, strength=DriveStrength.MAJOR
        )
        ApplicationFactory(capability=self.approach.capability, target_property=self.drive.property)
        self._open()

    def test_read_press_terms_routes_the_deed_and_completes(self) -> None:
        with patch(CHECK, return_value=_roll(self.success_tier)):
            read = self._do(
                "standoff_read",
                group_id=self.group.pk,
                focus_kind=RevealKind.DRIVE,
                focus_drive_id=self.drive.pk,
            )
            self.assertTrue(read.success, read.message)
            self.assertTrue(self.group.reveals.filter(drive=self.drive).exists())
            press = self._do("standoff_press", group_id=self.group.pk, approach_id=self.approach.pk)
            self.assertTrue(press.success, press.message)
            self.group.refresh_from_db()
            self.assertEqual(self.group.terms_ease, 1)
            terms = self._do("standoff_terms", group_id=self.group.pk, terms_id=self.terms.pk)
            self.assertTrue(terms.success, terms.message)
        self.deed.refresh_from_db()
        self.assertEqual(self.deed.outcome, self.success_tier)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.next_node)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.outcome, EncounterOutcome.VICTORY)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.SETTLED)

    def test_a_verb_after_the_standoff_ended_is_refused(self) -> None:
        self.assertTrue(self._do("standoff_fight").success)
        with patch(CHECK) as roll:
            result = self._do(
                "standoff_press", group_id=self.group.pk, approach_id=self.approach.pk
            )
        self.assertFalse(result.success)
        roll.assert_not_called()

    def test_a_group_of_another_encounter_is_not_found(self) -> None:
        elsewhere = StandoffGroupFactory(encounter=CombatEncounterFactory())
        with patch(CHECK) as roll:
            result = self._do("standoff_read", group_id=elsewhere.pk)
        self.assertFalse(result.success)
        roll.assert_not_called()


class PredatorBase(StandoffJourneyBase):
    def setUp(self) -> None:
        super().setUp()
        self.creature.cause = CauseKind.PREDATION
        self.creature.cause_margin_percent = 0
        self.creature.tier = OpponentTier.MOOK
        self.creature.save(update_fields=["cause", "cause_margin_percent", "tier"])
        # Two level-10 characters against one level-10 creature: the party outweighs it two
        # to one, so only a run of botches (emboldening) can bring the group's force level.
        for line in self.option.opponent_lines.all():
            line.count = 1
            line.save(update_fields=["count"])
        ally = CharacterSheetFactory(character=CharacterFactory(location=self.room))
        MissionParticipantFactory(instance=self.instance, character=ally)
        for sheet in (self.sheet, ally):
            CharacterClassLevelFactory(character=sheet, level=10, is_primary=True)
        self._open()


class PredationJourneyTests(PredatorBase):
    def test_botched_presses_tip_the_predator_into_the_fight(self) -> None:
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.round_number, 0)
        with patch(CHECK, return_value=_roll(self.botch_tier)):
            for _ in range(20):
                self._do("standoff_press", group_id=self.group.pk, approach_id=self.approach.pk)
                self.encounter.refresh_from_db()
                if self.encounter.round_number != 0:
                    break
        self.assertEqual(self.encounter.round_number, 1)
        self.assertIs(self.encounter.initiated_by_pc_side, False)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.FIGHTING)


class NotInAStandoffTests(StandoffJourneyBase):
    def test_no_standoff_means_a_clear_refusal(self) -> None:
        result = self._do("standoff_fight")
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You are not in a standoff.")


class ReadMessageTests(PredatorBase):
    def test_a_read_tells_the_reader_what_it_found(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.creature, strength=DriveStrength.MAJOR)
        with patch(CHECK, return_value=_roll(CheckOutcomeFactory(name="Crit", success_level=2))):
            result = self._do("standoff_read", group_id=self.group.pk)
        self.assertIn("Cause: Predation.", result.message)
        self.assertIn(f"Drive: {drive.property.name} (Major).", result.message)
