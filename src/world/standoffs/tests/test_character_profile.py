"""A player character's standoff profile: consent, the catalog and the lock (#4441)."""

from django.test import TestCase

from integration_tests.harness import JourneyCase
from world.combat.constants import CauseKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
)
from world.mechanics.factories import PropertyFactory
from world.scenes.constants import RoundStatus
from world.standoffs.constants import (
    PROFILE_LOCKED_MESSAGE,
    PROFILE_NO_SUCH_DRIVE_MESSAGE,
    DriveStrength,
    ProfileChange,
    StandoffGroupState,
)
from world.standoffs.factories import CreatureDriveFactory, StandoffGroupFactory
from world.standoffs.services.character_profile import (
    StandoffProfileError,
    apply_profile_change,
    build_profile_view,
    drive_catalog,
    is_in_live_standoff,
    may_stand_as_opponent,
    opted_in_personas,
)
from world.standoffs.services.view import build_standoff_view
from world.stories.services.cast import may_stand_persona


class CharacterProfileTests(TestCase):
    def setUp(self) -> None:
        room = JourneyCase.make_room("The Gate")
        self.maud = JourneyCase.make_player("Maud", room=room)
        self.ysmay = JourneyCase.make_player("Ysmay", room=room)
        self.sheet = self.maud.sheet_data
        self.persona = self.sheet.primary_persona
        self.greedy = PropertyFactory(name="Greedy (profile)")
        CreatureDriveFactory(creature_template=CreatureTemplateFactory(), property=self.greedy)
        self.encounter = CombatEncounterFactory(room=room)

    def stand_in_a_standoff(self, state: str = StandoffGroupState.OPEN):
        CombatOpponentFactory(encounter=self.encounter, persona=self.persona, name="Maud")
        return StandoffGroupFactory(
            encounter=self.encounter, creature_template=None, persona=self.persona, state=state
        )

    def test_a_gm_may_stand_only_an_opted_in_player(self) -> None:
        self.assertFalse(may_stand_persona(None, self.persona, is_staff=False))
        self.assertEqual(opted_in_personas(), [])
        apply_profile_change(self.sheet, ProfileChange.OPT_IN)
        self.assertTrue(may_stand_as_opponent(self.persona))
        self.assertTrue(may_stand_persona(None, self.persona, is_staff=False))
        self.assertEqual(opted_in_personas(), [self.persona])
        # An alt face is not a way around it: only the primary persona is offered.
        apply_profile_change(self.sheet, ProfileChange.OPT_OUT)
        self.assertEqual(opted_in_personas(), [])

    def test_a_drive_must_come_from_the_creature_catalog(self) -> None:
        invented = PropertyFactory(name="Invented (profile)")
        self.assertEqual(drive_catalog(), [self.greedy])
        with self.assertRaisesMessage(StandoffProfileError, PROFILE_NO_SUCH_DRIVE_MESSAGE):
            apply_profile_change(
                self.sheet, ProfileChange.DRIVE, property_id=invented.pk, strength=2
            )
        apply_profile_change(
            self.sheet, ProfileChange.DRIVE, property_id=self.greedy.pk, strength=3
        )
        apply_profile_change(
            self.sheet, ProfileChange.DRIVE, property_id=self.greedy.pk, strength=1
        )
        view = build_profile_view(self.sheet)
        self.assertEqual([(d.name, d.strength) for d in view.drives], [("Greedy (profile)", 1)])
        self.assertEqual([c.label for c in view.properties], ["Greedy (profile)"])
        self.assertEqual(DriveStrength.MINOR, view.drives[0].strength)

    def test_the_profile_is_locked_only_while_a_standoff_is_live(self) -> None:
        apply_profile_change(self.sheet, ProfileChange.OPT_IN)
        apply_profile_change(self.sheet, ProfileChange.CAUSE, cause=CauseKind.ORDERS)
        group = self.stand_in_a_standoff()
        self.assertTrue(is_in_live_standoff(self.sheet))
        view = build_profile_view(self.sheet)
        self.assertTrue(view.locked)
        self.assertEqual(view.locked_reason, PROFILE_LOCKED_MESSAGE)
        with self.assertRaisesMessage(StandoffProfileError, PROFILE_LOCKED_MESSAGE):
            apply_profile_change(self.sheet, ProfileChange.OPT_OUT)

        group.state = StandoffGroupState.SETTLED
        group.save(update_fields=["state"])
        self.assertFalse(is_in_live_standoff(self.sheet))
        apply_profile_change(self.sheet, ProfileChange.OPT_OUT)

    def test_a_standoff_that_ended_without_settling_does_not_hold_the_profile(self) -> None:
        self.stand_in_a_standoff()
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save(update_fields=["status"])
        self.assertFalse(is_in_live_standoff(self.sheet))

    def test_a_player_never_sees_their_own_character_as_a_group(self) -> None:
        apply_profile_change(self.sheet, ProfileChange.OPT_IN)
        group = self.stand_in_a_standoff()
        own = CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        other = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.ysmay.sheet_data
        )
        own_view = build_standoff_view(self.encounter, own.character_sheet)
        other_view = build_standoff_view(self.encounter, other.character_sheet)
        self.assertEqual([g.group_id for g in own_view.groups], [])
        self.assertEqual([g.group_id for g in other_view.groups], [group.pk])

    def test_an_unknown_change_and_a_non_player_are_refused(self) -> None:
        with self.assertRaises(StandoffProfileError):
            apply_profile_change(self.sheet, "wish")
        npc = CombatParticipantFactory().character_sheet
        with self.assertRaises(StandoffProfileError):
            apply_profile_change(npc, ProfileChange.OPT_IN)
