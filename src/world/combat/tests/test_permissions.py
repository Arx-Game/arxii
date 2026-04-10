"""Tests for combat permission classes."""

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.permissions import (
    IsEncounterGMOrStaff,
    IsEncounterParticipant,
    IsInEncounterRoom,
)
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


def _make_request(user: object) -> object:
    """Create a fake GET request authenticated as the given user."""
    factory = APIRequestFactory()
    request = factory.get("/fake/")
    request.user = user
    return request


class IsEncounterGMOrStaffTest(TestCase):
    """Tests for IsEncounterGMOrStaff permission."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.permission = IsEncounterGMOrStaff()
        cls.scene = SceneFactory()
        cls.encounter = CombatEncounterFactory(scene=cls.scene)

    def test_staff_allowed(self) -> None:
        staff = AccountFactory(is_staff=True)
        request = _make_request(staff)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_scene_gm_allowed(self) -> None:
        account = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=account, is_gm=True)
        request = _make_request(account)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_non_gm_participant_denied(self) -> None:
        account = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=account, is_gm=False)
        request = _make_request(account)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_non_participant_denied(self) -> None:
        account = AccountFactory()
        request = _make_request(account)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_no_scene_denied(self) -> None:
        encounter_no_scene = CombatEncounterFactory(scene=None)
        account = AccountFactory()
        request = _make_request(account)
        self.assertFalse(
            self.permission.has_object_permission(
                request,
                None,
                encounter_no_scene,
            ),
        )


class IsEncounterParticipantTest(TestCase):
    """Tests for IsEncounterParticipant permission."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.permission = IsEncounterParticipant()
        encounter = CombatEncounterFactory()

        # Create a character with roster entry linked to an account
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.tenure = RosterTenureFactory(
            roster_entry__character=cls.character,
            player_data__account=cls.account,
        )
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=cls.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        # Load with prefetch so participants_cached is populated
        from django.db.models import Prefetch

        from world.combat.models import CombatEncounter, CombatParticipant

        cls.encounter = CombatEncounter.objects.prefetch_related(
            Prefetch(
                "participants",
                queryset=CombatParticipant.objects.select_related(
                    "character_sheet__character",
                ).filter(status=ParticipantStatus.ACTIVE),
                to_attr="participants_cached",
            ),
        ).get(pk=encounter.pk)

    def test_participant_allowed(self) -> None:
        request = _make_request(self.account)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_non_participant_denied(self) -> None:
        other_account = AccountFactory()
        other_char = CharacterFactory()
        CharacterSheetFactory(character=other_char)
        RosterTenureFactory(
            roster_entry__character=other_char,
            player_data__account=other_account,
        )
        request = _make_request(other_account)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_fled_participant_denied(self) -> None:
        """A participant who has fled should not have active participant access."""
        fled_account = AccountFactory()
        fled_char = CharacterFactory()
        fled_sheet = CharacterSheetFactory(character=fled_char)
        RosterTenureFactory(
            roster_entry__character=fled_char,
            player_data__account=fled_account,
        )
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=fled_sheet,
            status=ParticipantStatus.FLED,
        )
        request = _make_request(fled_account)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_staff_allowed(self) -> None:
        staff = AccountFactory(is_staff=True)
        request = _make_request(staff)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.encounter),
        )


class IsInEncounterRoomTest(TestCase):
    """Tests for IsInEncounterRoom permission."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.permission = IsInEncounterRoom()
        cls.room = ObjectDBFactory(db_key="Combat Room")
        cls.scene = SceneFactory(location=cls.room)
        cls.encounter = CombatEncounterFactory(scene=cls.scene)

    def test_character_in_room_allowed(self) -> None:
        account = AccountFactory()
        character = CharacterFactory(location=self.room)
        RosterTenureFactory(
            roster_entry__character=character,
            player_data__account=account,
        )
        request = _make_request(account)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_character_elsewhere_denied(self) -> None:
        other_room = ObjectDBFactory(db_key="Other Room")
        account = AccountFactory()
        character = CharacterFactory(location=other_room)
        RosterTenureFactory(
            roster_entry__character=character,
            player_data__account=account,
        )
        request = _make_request(account)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_no_roster_entry_denied(self) -> None:
        account = AccountFactory()
        request = _make_request(account)
        self.assertFalse(
            self.permission.has_object_permission(request, None, self.encounter),
        )

    def test_no_scene_denied(self) -> None:
        encounter_no_scene = CombatEncounterFactory(scene=None)
        account = AccountFactory()
        request = _make_request(account)
        self.assertFalse(
            self.permission.has_object_permission(
                request,
                None,
                encounter_no_scene,
            ),
        )

    def test_staff_allowed(self) -> None:
        staff = AccountFactory(is_staff=True)
        request = _make_request(staff)
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.encounter),
        )
