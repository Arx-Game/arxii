"""The healing clock: a wound's healable limit shrinks by round in its own fight (#4810).

Wounds that land in a fight are stamped with its encounter and round. A mend in
that same fight loses ``MovementConfig.wound_cap_shrink_per_round`` percent of its
fraction per round since the wound landed; a wound from another fight, or with no round, never
shrinks. Built in ``setUp``: the tests mutate vitals and wound rows.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.models import ConditionTemplate
from world.conditions.services import get_active_conditions
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import WOUND_CRIPPLING_NAME
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.models import WoundDetails
from world.vitals.seeds import seed_survivability_content
from world.vitals.services import mend_wound, process_damage_consequences


class WoundClockTests(TestCase):
    """A mend three rounds on closes less than one in the same round."""

    def _wounded(self, encounter, *, wound_encounter=None, wound_round=None):
        vitals = CharacterVitalsFactory(health=0, max_health=200)
        CombatParticipantFactory(encounter=encounter, character_sheet=vitals.character_sheet)
        instance = ConditionInstanceFactory(target=vitals.character_sheet.character)
        WoundDetails.objects.create(
            condition_instance=instance,
            damage_taken=100,
            created_encounter=wound_encounter,
            created_round=wound_round,
        )
        return vitals, instance

    def _mend(self, vitals, instance) -> int:
        return mend_wound(CharacterSheetFactory(), vitals.character_sheet, instance, amount=200)

    def test_a_mend_three_rounds_later_closes_less(self) -> None:
        now = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        later = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=4)
        same_round = self._mend(*self._wounded(now, wound_encounter=now, wound_round=1))
        three_on = self._mend(*self._wounded(later, wound_encounter=later, wound_round=1))

        self.assertEqual(same_round, 75)  # NEVER_TO_FULL_FRACTION 0.75 x 100
        self.assertEqual(three_on, 60)  # (0.75 - 3 x 0.05) x 100
        self.assertLess(three_on, same_round)

    def test_a_wound_from_another_fight_does_not_shrink(self) -> None:
        old_fight = CombatEncounterFactory(status=RoundStatus.COMPLETED, round_number=9)
        this_fight = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=4)

        mended = self._mend(*self._wounded(this_fight, wound_encounter=old_fight, wound_round=1))

        self.assertEqual(mended, 75)

    def test_a_wound_with_no_round_does_not_shrink(self) -> None:
        fight = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=4)

        mended = self._mend(*self._wounded(fight, wound_encounter=None, wound_round=None))

        self.assertEqual(mended, 75)


@override_settings(SEED_SAMPLE_CONTENT=True)
class WoundStampTests(TestCase):
    """A wound that lands in a fight records the fight and its round."""

    def _wound(self, vitals) -> WoundDetails:
        failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        with force_check_outcome(failure):
            process_damage_consequences(
                character_sheet=vitals.character_sheet, damage_dealt=60, damage_type=None
            )
        crippling = ConditionTemplate.objects.get(name=WOUND_CRIPPLING_NAME)
        instance = get_active_conditions(
            vitals.character_sheet.character, condition=crippling
        ).first()
        return WoundDetails.objects.get(condition_instance=instance)

    def test_a_wound_in_a_fight_is_stamped_with_its_round(self) -> None:
        seed_survivability_content()
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=3)
        vitals = CharacterVitalsFactory(health=40, max_health=100)
        CombatParticipantFactory(encounter=encounter, character_sheet=vitals.character_sheet)

        details = self._wound(vitals)

        self.assertEqual(details.created_encounter_id, encounter.pk)
        self.assertEqual(details.created_round, 3)

    def test_a_wound_out_of_combat_is_not_stamped(self) -> None:
        seed_survivability_content()
        vitals = CharacterVitalsFactory(health=40, max_health=100)

        details = self._wound(vitals)

        self.assertIsNone(details.created_encounter_id)
        self.assertIsNone(details.created_round)
