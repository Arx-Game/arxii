"""Predation through the real spawn path: a mission option spawns the creature template.

Nothing is patched but ``perform_check`` where a roll happens. Opponents are scaled to
the party by the real spawn, so these assert what a player's standoff would do.
"""

from types import SimpleNamespace
from unittest.mock import patch

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import CauseKind, OpponentStatus, OpponentTier
from world.combat.models import CombatEncounter, CombatParticipant
from world.combat.morale import apply_morale_damage
from world.missions.factories import MissionParticipantFactory
from world.missions.services.resolution import resolve_option
from world.standoffs.factories import StandoffApproachFactory, StandoffGroupFactory
from world.standoffs.models import StandoffConfig
from world.standoffs.services.force import cause_fires, group_force, party_force
from world.standoffs.services.verbs import standoff_press
from world.traits.factories import CheckOutcomeFactory

CHECK = "world.standoffs.services.verbs.perform_check"
PARTY_LEVEL = 5

from world.missions.tests.test_encounter_option import EncounterOptionTestBase  # noqa: E402


class SpawnedPredationBase(EncounterOptionTestBase):
    """Three level-5 characters, an unlevelled PREDATION mook line, a mission band."""

    BAND = (3, 5)
    MOOKS = 3

    def setUp(self) -> None:
        super().setUp()
        self.template.level_band_min, self.template.level_band_max = self.BAND
        self.template.save(update_fields=["level_band_min", "level_band_max"])
        self.creature.tier = OpponentTier.MOOK
        self.creature.cause = CauseKind.PREDATION
        self.creature.cause_margin_percent = 0
        self.creature.save(update_fields=["tier", "cause", "cause_margin_percent"])
        line = self.option.opponent_lines.get()
        line.count = self.MOOKS
        line.save(update_fields=["count"])
        allies = [
            CharacterSheetFactory(character=CharacterFactory(location=self.room)) for _ in (1, 2)
        ]
        for ally in allies:
            MissionParticipantFactory(instance=self.instance, character=ally)
        for sheet in (self.sheet, *allies):
            CharacterClassLevelFactory(character=sheet, level=PARTY_LEVEL, is_primary=True)
        self.config = StandoffConfig.load()

    def _spawn(self, *, open_standoff: bool) -> CombatEncounter:
        self.option.opens_as_standoff = open_standoff
        self.option.save(update_fields=["opens_as_standoff"])
        deed = resolve_option(self.instance, self.entry, self.option, self.participant)
        return CombatEncounter.objects.get(scenario_deed=deed)


class HeadcountTests(SpawnedPredationBase):
    def _opened_fight(self) -> bool:
        return self._spawn(open_standoff=True).round_number != 0

    def test_three_level_five_mooks_match_the_party_and_fire(self) -> None:
        encounter = self._spawn(open_standoff=False)
        self.assertEqual({o.level for o in encounter.opponents.all()}, {PARTY_LEVEL})
        group = StandoffGroupFactory(encounter=encounter, creature_template=self.creature)
        self.assertEqual(party_force(encounter, self.config), 15)
        self.assertEqual(group_force(group, self.config), 15)
        self.assertTrue(self._opened_fight())


class FewMooksTests(SpawnedPredationBase):
    MOOKS = 2

    def test_two_mooks_do_not_fire_on_a_party_of_three(self) -> None:
        encounter = self._spawn(open_standoff=True)
        self.assertEqual(encounter.round_number, 0)


class ManyMooksTests(SpawnedPredationBase):
    MOOKS = 4

    def test_four_mooks_fire(self) -> None:
        self.assertTrue(self._spawn(open_standoff=True).round_number != 0)


class OverLeveledMissionTests(SpawnedPredationBase):
    BAND = (1, 2)

    def test_the_same_three_mooks_do_not_fire_on_an_over_leveled_party(self) -> None:
        # average 5 is three above the band top: one tier, +25% party force
        encounter = self._spawn(open_standoff=True)
        self.assertEqual(encounter.round_number, 0)


class WellOverLeveledTests(SpawnedPredationBase):
    BAND = (1, 1)
    MOOKS = 4

    def test_four_mooks_do_not_fire_when_the_party_is_two_tiers_over(self) -> None:
        # four over the band: two tiers, +50%; 22.5 against 20
        self.assertEqual(self._spawn(open_standoff=True).round_number, 0)


class LiveStateTests(SpawnedPredationBase):
    MOOKS = 4

    def _group(self, encounter: CombatEncounter):
        return StandoffGroupFactory(encounter=encounter, creature_template=self.creature)

    def test_a_group_whittled_down_stops_firing(self) -> None:
        encounter = self._spawn(open_standoff=False)
        group = self._group(encounter)
        self.assertTrue(cause_fires(group, self.config))
        for opponent in list(encounter.opponents.all())[:2]:
            opponent.status = OpponentStatus.FLED
            opponent.save(update_fields=["status"])
        self.assertFalse(cause_fires(group, self.config))

    def test_a_badly_wounded_group_stops_firing(self) -> None:
        encounter = self._spawn(open_standoff=False)
        group = self._group(encounter)
        self.assertTrue(cause_fires(group, self.config))
        for opponent in encounter.opponents.all():
            opponent.health = opponent.max_health // 5
            opponent.save(update_fields=["health"])
        self.assertFalse(cause_fires(group, self.config))


class WoundedPartyTests(SpawnedPredationBase):
    MOOKS = 2

    def test_wounded_party_members_let_a_smaller_group_fire(self) -> None:
        from world.vitals.factories import CharacterVitalsFactory

        encounter = self._spawn(open_standoff=False)
        group = StandoffGroupFactory(encounter=encounter, creature_template=self.creature)
        self.assertFalse(cause_fires(group, self.config))
        for participant in CombatParticipant.objects.filter(encounter=encounter):
            CharacterVitalsFactory(
                character_sheet=participant.character_sheet, health=50, max_health=100
            )
        self.assertTrue(cause_fires(group, self.config))


class IntimidationTests(SpawnedPredationBase):
    MOOKS = 3

    def test_an_intimidation_press_that_breaks_morale_stops_the_group_firing(self) -> None:
        encounter = self._spawn(open_standoff=False)
        group = StandoffGroupFactory(encounter=encounter, creature_template=self.creature)
        for opponent in encounter.opponents.all():
            apply_morale_damage(opponent, opponent.morale - 55)  # shaken but steady
        self.assertTrue(cause_fires(group, self.config))
        approach = StandoffApproachFactory(damages_morale=True)
        crit = CheckOutcomeFactory(name="Spawned crit", success_level=2)
        roll = SimpleNamespace(success_level=2, outcome=crit, chart=None)
        participant = CombatParticipant.objects.get(encounter=encounter, character_sheet=self.sheet)
        with patch(CHECK, return_value=roll):
            result = standoff_press(participant, group, approach)
        self.assertFalse(result.fight_started)
        encounter.refresh_from_db()
        self.assertEqual(encounter.round_number, 0)
        self.assertFalse(cause_fires(group, self.config))
