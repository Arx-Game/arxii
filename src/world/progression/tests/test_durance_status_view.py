"""Tests for the web Durance readiness hub (#3045).

Mirrors the setUp pattern of ``test_convene_site.py`` (the service-layer tests for
``convene_durance_at_site``) but drives the REST views instead.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest import mock

from django.test import TestCase
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.areas.services import get_room_profile
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory, PathFactory
from world.classes.models import PathStage
from world.conditions.factories import ConditionStageFactory
from world.magic.audere_majora import AudereMajoraThreshold
from world.magic.factories import IntensityTierFactory, RitualOfTheDuranceFactory
from world.magic.models.sessions import RitualSession
from world.progression.factories import DuranceTrainingSiteFactory
from world.progression.models import CharacterPathHistory, CharacterUnlock, ClassLevelUnlock

_CHECK_PATH = "world.progression.services.spends.check_requirements_for_unlock"


def _wire_path(sheet, path) -> None:
    """Record *path* as the character's current path via CharacterPathHistory."""
    CharacterPathHistory.objects.create(character=sheet, path=path)


def _set_primary_level(sheet, *, character_class, level: int) -> None:
    """Give sheet.character a primary CharacterClassLevel at *level*."""
    CharacterClassLevelFactory(
        character=sheet,
        character_class=character_class,
        level=level,
        is_primary=True,
    )


def _place_in_room(sheet, room) -> None:
    """Move a character into *room* (ObjectDB) and persist the change."""
    sheet.character.location = room
    sheet.character.save()


def _purchase_unlock(sheet, unlock) -> None:
    """Record the XP-unlock purchase gate as satisfied for ``sheet`` (#2116)."""
    CharacterUnlock.objects.create(
        character=sheet,
        character_class=unlock.character_class,
        target_level=unlock.target_level,
    )


class _DuranceApiTestCase(TestCase):
    """Shared account/character/auth scaffolding for the Durance web endpoints."""

    def setUp(self):
        self.account: AccountDB = AccountFactory(
            username=f"durancetester{id(self)}",
            email=f"durance{id(self)}@example.com",
        )
        self.sheet = CharacterSheetFactory()
        self.character = cast(ObjectDB, self.sheet.character)
        self.character.db_account = self.account
        self.character.save()

        fake_user = SimpleNamespace(
            is_authenticated=True,
            is_staff=False,
            puppet=self.character,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=fake_user)  # type: ignore[arg-type]


class DuranceStatusViewTests(_DuranceApiTestCase):
    """Tests for GET /api/progression/durance/status/."""

    def test_requires_played_character(self):
        """A request with no puppeted character is refused."""
        fake_user = SimpleNamespace(is_authenticated=True, is_staff=False, puppet=None)
        self.client.force_authenticate(user=fake_user)
        response = self.client.get("/api/progression/durance/status/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_class_level_reports_gate_unavailable(self):
        """A character with no CharacterClassLevel row gets an honest not-ready gate."""
        response = self.client.get("/api/progression/durance/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["level"], 0)
        self.assertEqual(response.data["target_level"], 1)
        self.assertFalse(response.data["is_tier_boundary"])
        gate = response.data["unlock_gate"]
        self.assertFalse(gate["has_class_level"])
        self.assertFalse(gate["ready"])

    def test_ready_when_requirements_met_and_unlock_purchased(self):
        """met + purchased => ready, mirroring telnet's 'You are ready to advance' line."""
        character_class = CharacterClassFactory()
        _set_primary_level(self.sheet, character_class=character_class, level=2)
        unlock = ClassLevelUnlock.objects.create(character_class=character_class, target_level=3)
        _purchase_unlock(self.sheet, unlock)

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            response = self.client.get("/api/progression/durance/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        gate = response.data["unlock_gate"]
        self.assertTrue(gate["has_class_level"])
        self.assertTrue(gate["advancement_authored"])
        self.assertTrue(gate["requirements_met"])
        self.assertTrue(gate["purchased"])
        self.assertIsNone(gate["xp_cost"])
        self.assertTrue(gate["ready"])
        self.assertEqual(gate["class_level_unlock_id"], unlock.pk)

    def test_not_ready_surfaces_failed_requirements_and_cost(self):
        """Unmet requirements + unpurchased unlock surfaces both, with an honest cost."""
        character_class = CharacterClassFactory()
        _set_primary_level(self.sheet, character_class=character_class, level=2)
        ClassLevelUnlock.objects.create(character_class=character_class, target_level=3)

        with mock.patch(_CHECK_PATH, return_value=(False, ["Requires 50 Legend"])):
            response = self.client.get("/api/progression/durance/status/")

        gate = response.data["unlock_gate"]
        self.assertFalse(gate["requirements_met"])
        self.assertIn("Requires 50 Legend", gate["failed_requirements"])
        self.assertFalse(gate["purchased"])
        self.assertFalse(gate["ready"])
        # No ClassXPCost row authored => the fallback-to-0 case (#3045 decision 3).
        self.assertEqual(gate["xp_cost"], 0)

    def test_no_advancement_authored(self):
        """No ClassLevelUnlock row for the target level is reported, not a 500."""
        character_class = CharacterClassFactory()
        _set_primary_level(self.sheet, character_class=character_class, level=2)

        response = self.client.get("/api/progression/durance/status/")

        gate = response.data["unlock_gate"]
        self.assertTrue(gate["has_class_level"])
        self.assertFalse(gate["advancement_authored"])
        self.assertFalse(gate["ready"])

    def test_tier_boundary_reports_no_unlock_gate(self):
        """A tier-boundary level belongs to Audere Majora — the hub says so, no gate."""
        character_class = CharacterClassFactory()
        _set_primary_level(self.sheet, character_class=character_class, level=5)
        AudereMajoraThreshold.objects.create(
            boundary_level=5,
            target_stage=PathStage.POTENTIAL,
            minimum_intensity_tier=IntensityTierFactory(),
            minimum_warp_stage=ConditionStageFactory(),
            vision_text="placeholder",
            manifestation_text="placeholder",
        )

        response = self.client.get("/api/progression/durance/status/")

        self.assertTrue(response.data["is_tier_boundary"])
        self.assertIsNone(response.data["unlock_gate"])

    def test_site_present_reflects_active_training_site_in_room(self):
        """A room with an active DuranceTrainingSite reports site_present=True."""
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.sheet, room)
        officiant = CharacterSheetFactory()
        DuranceTrainingSiteFactory(
            room_profile=get_room_profile(room),
            officiant=officiant,
            is_active=True,
        )

        response = self.client.get("/api/progression/durance/status/")

        self.assertTrue(response.data["site_present"])

    def test_site_absent_when_no_training_site_in_room(self):
        """A room with no active training site reports site_present=False."""
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.sheet, room)

        response = self.client.get("/api/progression/durance/status/")

        self.assertFalse(response.data["site_present"])


class DuranceConveneViewTests(_DuranceApiTestCase):
    """Tests for POST /api/progression/durance/convene/."""

    def _wire_eligible_site(self):
        """Wire an eligible trainer-of-record site in the caller's room; return the unlock."""
        path = PathFactory(stage=PathStage.PROSPECT)

        trainer_sheet = CharacterSheetFactory()
        trainer_class = CharacterClassFactory()
        _set_primary_level(trainer_sheet, character_class=trainer_class, level=10)
        _wire_path(trainer_sheet, path)

        inductee_class = CharacterClassFactory()
        _set_primary_level(self.sheet, character_class=inductee_class, level=2)
        _wire_path(self.sheet, path)

        unlock = ClassLevelUnlock.objects.create(character_class=inductee_class, target_level=3)
        _purchase_unlock(self.sheet, unlock)

        RitualOfTheDuranceFactory()

        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(trainer_sheet, room)
        _place_in_room(self.sheet, room)
        DuranceTrainingSiteFactory(
            room_profile=get_room_profile(room),
            officiant=trainer_sheet,
            is_active=True,
        )
        return unlock

    def test_requires_played_character(self):
        """A request with no puppeted character is refused."""
        fake_user = SimpleNamespace(is_authenticated=True, is_staff=False, puppet=None)
        self.client.force_authenticate(user=fake_user)
        response = self.client.post("/api/progression/durance/convene/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_convene_opens_a_session_at_an_eligible_site(self):
        """A convene call opens a RitualSession with the site's trainer as initiator."""
        self._wire_eligible_site()

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            response = self.client.post("/api/progression/durance/convene/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session_id = response.data["session_id"]
        session = RitualSession.objects.get(pk=session_id)
        self.assertEqual(session.session_kwargs.get("site_convened"), "1")

    def test_convene_without_a_site_returns_400(self):
        """No active training site in the caller's room surfaces a clean 400."""
        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.sheet, room)

        response = self.client.post("/api/progression/durance/convene/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_convene_without_a_room_returns_400(self):
        """A character with no location cannot convene."""
        response = self.client.post("/api/progression/durance/convene/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
