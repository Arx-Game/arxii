"""Tests for CombatParticipant.available_strain + ParticipantSerializer (Phase 8)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.serializers import ParticipantSerializer
from world.magic.factories import CharacterAnimaFactory


class CombatParticipantStrainTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )

    def test_available_strain_reads_anima_current(self) -> None:
        CharacterAnimaFactory(character=self.sheet.character, current=7, maximum=10)
        # Invalidate any cached anima lookup on the typeclass instance.
        self.assertEqual(self.participant.available_strain, 7)

    def test_available_strain_defaults_to_zero_when_no_anima(self) -> None:
        # No CharacterAnima row — defensive 0 fallback.
        self.assertEqual(self.participant.available_strain, 0)


class ParticipantSerializerStrainTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        CharacterAnimaFactory(character=self.sheet.character, current=8, maximum=12)
        # Make the encounter's participants_cached attribute available for the
        # vitals-permission check that walks it.
        self.encounter.participants_cached = [self.participant]

    def _request_with_owner(self):
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = self.sheet.character.account
        request.user.is_staff = False
        return request

    def test_available_strain_field_visible_to_staff(self) -> None:
        factory = APIRequestFactory()
        request = factory.get("/")
        # Build a staff user.
        from evennia_extensions.factories import AccountFactory

        staff = AccountFactory()
        staff.is_staff = True
        staff.save()
        request.user = staff

        data = ParticipantSerializer(self.participant, context={"request": request}).data
        self.assertEqual(data["available_strain"], 8)

    def test_available_strain_field_hidden_from_outsiders(self) -> None:
        factory = APIRequestFactory()
        request = factory.get("/")
        from evennia_extensions.factories import AccountFactory

        outsider = AccountFactory()
        request.user = outsider

        data = ParticipantSerializer(self.participant, context={"request": request}).data
        self.assertIsNone(data["available_strain"])
