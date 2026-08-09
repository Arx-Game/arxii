"""Tests for the consent-prompted GM summon (#3071).

Covers ``SummonPlayerAction`` (propose) + ``AcceptGMSummonAction``/
``DeclineGMSummonAction`` (target-side response): permission journeys (JUNIOR-GM
pass, non-GM refusal, non-scene-GM refusal, staff bypass) and the accept-moves /
decline-does-not-move consent journey.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.gm_adjudication import SummonPlayerAction
from actions.definitions.gm_summon_offers import AcceptGMSummonAction, DeclineGMSummonAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.gm.models import GMSummonOffer
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _room(*, db_key: str) -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _pc_in_room(room: object, *, db_key: str) -> tuple[object, object]:
    """Return (Character, Account) -- a PC with a live roster tenure, located in *room*."""
    from world.character_sheets.factories import CharacterSheetFactory

    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return char, tenure.player_data.account


class GMSummonActionsTestBase(TestCase):
    """Shared fixture: a GM's scene room, a JUNIOR GM running it, a target elsewhere.

    Built in ``setUp`` (per test), not ``setUpTestData`` -- mirrors
    ``GMAdjudicationActionsTestBase`` (Character typeclass instances hold an
    Evennia ``DbHolder`` attribute proxy that ``setUpTestData`` cannot deepcopy).
    """

    def setUp(self) -> None:
        self.gm_room = _room(db_key="GMSceneRoom")
        self.other_room = _room(db_key="ElsewhereRoom")
        self.scene = SceneFactory(location=self.gm_room)

        self.gm_actor, self.gm_account = _pc_in_room(self.gm_room, db_key="SummonGM")
        GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        self.player_actor, self.player_account = _pc_in_room(self.gm_room, db_key="NonGMPlayer")
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)

        # A GM profile, but not enrolled as GM of any scene at their own location —
        # IsSceneGMPrerequisite must still refuse them (#3071 "for tracking" shape:
        # a summon is always anchored to a scene the GM actually runs).
        self.roaming_gm_actor, self.roaming_gm_account = _pc_in_room(
            _room(db_key="UnstaffedRoom"), db_key="RoamingGM"
        )
        GMProfileFactory(account=self.roaming_gm_account, level=GMLevel.JUNIOR)

        self.staff_account = AccountFactory(username="staff_summon", is_staff=True)
        self.staff_actor = CharacterFactory(db_key="StaffSummoner", location=self.gm_room)
        self.staff_actor.db_account = self.staff_account
        self.staff_actor.save()

        self.target, self.target_account = _pc_in_room(self.other_room, db_key="SummonTarget")


class SummonPlayerActionPermissionTests(GMSummonActionsTestBase):
    def test_non_gm_is_refused(self) -> None:
        result = SummonPlayerAction().run(actor=self.player_actor, target=self.target)
        self.assertFalse(result.success)
        self.assertFalse(GMSummonOffer.objects.filter(target_sheet=self.target.sheet_data).exists())

    def test_junior_gm_can_summon(self) -> None:
        result = SummonPlayerAction().run(actor=self.gm_actor, target=self.target)
        self.assertTrue(result.success)
        offer = GMSummonOffer.objects.get(target_sheet=self.target.sheet_data)
        self.assertEqual(offer.room.objectdb_id, self.gm_room.pk)

    def test_gm_not_running_the_active_scene_is_refused(self) -> None:
        """A GM with a profile but no is_gm scene-participation is refused (#3071)."""
        result = SummonPlayerAction().run(actor=self.roaming_gm_actor, target=self.target)
        self.assertFalse(result.success)
        self.assertFalse(GMSummonOffer.objects.filter(target_sheet=self.target.sheet_data).exists())

    def test_staff_bypasses_gm_level_gate(self) -> None:
        result = SummonPlayerAction().run(actor=self.staff_actor, target=self.target)
        self.assertTrue(result.success)

    def test_cannot_summon_self(self) -> None:
        result = SummonPlayerAction().run(actor=self.gm_actor, target=self.gm_actor)
        self.assertFalse(result.success)


class GMSummonConsentJourneyTests(GMSummonActionsTestBase):
    def test_accept_moves_the_target(self) -> None:
        propose = SummonPlayerAction().run(actor=self.gm_actor, target=self.target)
        self.assertTrue(propose.success)

        result = AcceptGMSummonAction().run(actor=self.target)

        self.assertTrue(result.success)
        self.target.refresh_from_db()
        self.assertEqual(self.target.db_location_id, self.gm_room.pk)
        self.assertFalse(GMSummonOffer.objects.filter(target_sheet=self.target.sheet_data).exists())

    def test_decline_does_not_move_the_target(self) -> None:
        propose = SummonPlayerAction().run(actor=self.gm_actor, target=self.target)
        self.assertTrue(propose.success)

        result = DeclineGMSummonAction().run(actor=self.target)

        self.assertTrue(result.success)
        self.target.refresh_from_db()
        self.assertEqual(self.target.db_location_id, self.other_room.pk)
        self.assertFalse(GMSummonOffer.objects.filter(target_sheet=self.target.sheet_data).exists())

    def test_accept_with_no_pending_offer_is_refused(self) -> None:
        result = AcceptGMSummonAction().run(actor=self.target)
        self.assertFalse(result.success)

    def test_decline_with_no_pending_offer_is_refused(self) -> None:
        result = DeclineGMSummonAction().run(actor=self.target)
        self.assertFalse(result.success)

    def test_resummon_replaces_the_pending_offer(self) -> None:
        """Re-summoning the same target replaces, not stacks (#3071)."""
        SummonPlayerAction().run(actor=self.gm_actor, target=self.target)
        SummonPlayerAction().run(actor=self.gm_actor, target=self.target)

        self.assertEqual(
            GMSummonOffer.objects.filter(target_sheet=self.target.sheet_data).count(), 1
        )
