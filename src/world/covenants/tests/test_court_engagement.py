"""Tests for mission-driven Court engagement (#1589 Task 5).

A Court vow ENGAGES only while the member is conducting an active mission
*for the Court's backing organization* — "on the master's business." The gate
is the mission, not co-presence.

Confirmed join chain (verified against code):
  MissionInstance.participants (related_name) -> MissionParticipant.character
    (FK -> objects.ObjectDB, so filter by character_sheet.character)
  MissionInstance.status == MissionStatus.ACTIVE
  MissionInstance.source_offer -> NPCServiceOffer.role -> NPCRole.faction_affiliation
    matched against covenant.organization_id.
"""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.court_missions import has_active_court_mission, has_regarded_target_present
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.handlers import can_engage_membership
from world.covenants.services import evaluate_scene_engagement
from world.missions.constants import MissionStatus
from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory
from world.npc_services.factories import NpcRegardFactory, NPCRoleFactory, NPCServiceOfferFactory
from world.scenes.factories import SceneFactory


class CourtEngagementTests(TestCase):
    """End-to-end behaviour of the Court mission engagement gate."""

    def _court_membership(self):
        """A COURT covenant + an active COURT membership for a fresh servant."""
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        membership = CharacterCovenantRoleFactory(covenant=covenant, covenant_role=role)
        return covenant, membership

    def _offer_for_org(self, organization):
        """An NPCServiceOffer whose role fronts for ``organization``."""
        npc_role = NPCRoleFactory(faction_affiliation=organization)
        return NPCServiceOfferFactory(role=npc_role)

    def _put_on_mission(self, *, membership, organization, status=MissionStatus.ACTIVE):
        """Make the membership's servant a participant in a mission given by ``organization``."""
        offer = self._offer_for_org(organization)
        instance = MissionInstanceFactory(status=status, source_offer=offer)
        MissionParticipantFactory(
            instance=instance,
            character=membership.character_sheet.character,
        )
        return instance

    # -- has_active_court_mission / can_engage_membership ------------------

    def test_active_court_mission_makes_engageable(self):
        covenant, membership = self._court_membership()
        self._put_on_mission(membership=membership, organization=covenant.organization)

        self.assertTrue(
            has_active_court_mission(character_sheet=membership.character_sheet, covenant=covenant)
        )
        self.assertTrue(can_engage_membership(membership))

    def test_no_mission_is_not_engageable(self):
        covenant, membership = self._court_membership()

        self.assertFalse(
            has_active_court_mission(character_sheet=membership.character_sheet, covenant=covenant)
        )
        self.assertFalse(can_engage_membership(membership))

    def test_mission_for_different_org_is_not_engageable(self):
        _covenant, membership = self._court_membership()
        other_covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        self._put_on_mission(membership=membership, organization=other_covenant.organization)

        self.assertFalse(can_engage_membership(membership))

    def test_complete_mission_is_not_engageable(self):
        covenant, membership = self._court_membership()
        self._put_on_mission(
            membership=membership,
            organization=covenant.organization,
            status=MissionStatus.COMPLETE,
        )

        self.assertFalse(can_engage_membership(membership))

    def test_abandoned_mission_is_not_engageable(self):
        covenant, membership = self._court_membership()
        self._put_on_mission(
            membership=membership,
            organization=covenant.organization,
            status=MissionStatus.ABANDONED,
        )

        self.assertFalse(can_engage_membership(membership))

    def test_null_source_offer_does_not_match(self):
        """A trigger/legacy mission (source_offer NULL) is never a Court mission."""
        _covenant, membership = self._court_membership()
        instance = MissionInstanceFactory(status=MissionStatus.ACTIVE, source_offer=None)
        MissionParticipantFactory(
            instance=instance,
            character=membership.character_sheet.character,
        )

        self.assertFalse(can_engage_membership(membership))

    # -- evaluate_scene_engagement (auto-engage) --------------------------

    def test_auto_engage_engages_court_on_mission(self):
        covenant, membership = self._court_membership()
        self._put_on_mission(membership=membership, organization=covenant.organization)

        evaluate_scene_engagement(
            character_sheet=membership.character_sheet,
            room=membership.character_sheet.character.location,
        )

        membership.refresh_from_db()
        self.assertTrue(membership.engaged)

    def test_auto_engage_does_not_engage_off_mission(self):
        _covenant, membership = self._court_membership()

        evaluate_scene_engagement(
            character_sheet=membership.character_sheet,
            room=membership.character_sheet.character.location,
        )

        membership.refresh_from_db()
        self.assertFalse(membership.engaged)

    def test_going_on_mission_flips_engagement(self):
        covenant, membership = self._court_membership()
        room = membership.character_sheet.character.location

        # Off-mission: not engaged.
        evaluate_scene_engagement(character_sheet=membership.character_sheet, room=room)
        membership.refresh_from_db()
        self.assertFalse(membership.engaged)

        # On-mission: engages.
        self._put_on_mission(membership=membership, organization=covenant.organization)
        evaluate_scene_engagement(character_sheet=membership.character_sheet, room=room)
        membership.refresh_from_db()
        self.assertTrue(membership.engaged)


def _make_room(key: str = "CourtRegardTestRoom"):
    return ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")


def _place_character_in_room(character, room) -> None:
    character.db_location = room
    character.save(update_fields=["db_location"])


class CourtRegardEngagementTests(TestCase):
    """A Court servant's vow also engages when a regarded persona is present (#1717)."""

    def _court_membership_with_leader(self):
        leader_sheet = CharacterSheetFactory()
        covenant = CovenantFactory(covenant_type=CovenantType.COURT, leader=leader_sheet)
        role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        membership = CharacterCovenantRoleFactory(covenant=covenant, covenant_role=role)
        return covenant, membership, leader_sheet

    def test_no_leader_is_not_engageable_via_regard(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)  # leader=None
        role = CovenantRoleFactory(covenant_type=CovenantType.COURT)
        membership = CharacterCovenantRoleFactory(covenant=covenant, covenant_role=role)

        self.assertFalse(
            has_regarded_target_present(
                character_sheet=membership.character_sheet, covenant=covenant
            )
        )

    def test_regarded_persona_present_makes_engageable(self):
        covenant, membership, leader_sheet = self._court_membership_with_leader()
        room = _make_room()
        _place_character_in_room(membership.character_sheet.character, room)
        SceneFactory(location=room, is_active=True)

        target_sheet = CharacterSheetFactory()
        _place_character_in_room(target_sheet.character, room)
        NpcRegardFactory(
            holder_persona=leader_sheet.primary_persona,
            target_persona=target_sheet.primary_persona,
            value=-800,
        )

        self.assertTrue(
            has_regarded_target_present(
                character_sheet=membership.character_sheet, covenant=covenant
            )
        )
        self.assertTrue(can_engage_membership(membership))

    def test_favorably_regarded_persona_present_also_engages(self):
        """Positive regard (a courting target, not just an enemy) also engages."""
        covenant, membership, leader_sheet = self._court_membership_with_leader()
        room = _make_room()
        _place_character_in_room(membership.character_sheet.character, room)
        SceneFactory(location=room, is_active=True)

        target_sheet = CharacterSheetFactory()
        _place_character_in_room(target_sheet.character, room)
        NpcRegardFactory(
            holder_persona=leader_sheet.primary_persona,
            target_persona=target_sheet.primary_persona,
            value=600,
        )

        self.assertTrue(
            has_regarded_target_present(
                character_sheet=membership.character_sheet, covenant=covenant
            )
        )

    def test_unregarded_persona_present_is_not_engageable(self):
        covenant, membership, _leader_sheet = self._court_membership_with_leader()
        room = _make_room()
        _place_character_in_room(membership.character_sheet.character, room)
        SceneFactory(location=room, is_active=True)

        stranger_sheet = CharacterSheetFactory()
        _place_character_in_room(stranger_sheet.character, room)
        # No NpcRegard row authored — a stranger, not a regarded target.

        self.assertFalse(
            has_regarded_target_present(
                character_sheet=membership.character_sheet, covenant=covenant
            )
        )
        self.assertFalse(can_engage_membership(membership))

    def test_regarded_persona_absent_from_scene_is_not_engageable(self):
        covenant, membership, leader_sheet = self._court_membership_with_leader()
        room = _make_room()
        _place_character_in_room(membership.character_sheet.character, room)
        SceneFactory(location=room, is_active=True)

        # Regarded target exists but is NOT placed in the room.
        target_sheet = CharacterSheetFactory()
        NpcRegardFactory(
            holder_persona=leader_sheet.primary_persona,
            target_persona=target_sheet.primary_persona,
            value=-800,
        )

        self.assertFalse(
            has_regarded_target_present(
                character_sheet=membership.character_sheet, covenant=covenant
            )
        )

    def test_mission_still_engages_without_any_regard(self):
        """Regression: the pre-existing mission-driven engagement path still works."""
        covenant, membership, _leader_sheet = self._court_membership_with_leader()
        npc_role = NPCRoleFactory(faction_affiliation=covenant.organization)
        offer = NPCServiceOfferFactory(role=npc_role)
        instance = MissionInstanceFactory(status=MissionStatus.ACTIVE, source_offer=offer)
        MissionParticipantFactory(instance=instance, character=membership.character_sheet.character)

        self.assertTrue(can_engage_membership(membership))
