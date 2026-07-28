"""Dual-mode recruitment tests (#2827 phase 3)."""

from django.test import TestCase

from world.assets.factories import NPCAssetFactory
from world.assets.services import ExtractionError, extract_asset
from world.npc_services.factories import FunctionaryFactory
from world.npc_services.models import Functionary
from world.scenes.factories import PersonaFactory


class ExtractAssetTests(TestCase):
    def _recruited_in_place(self):
        """An asset whose persona still holds an active placement."""
        from world.npc_services.instantiation import materialize_functionary

        functionary = FunctionaryFactory()
        npc_persona = materialize_functionary(functionary)
        asset = NPCAssetFactory(asset_persona=npc_persona, source_functionary=functionary)
        return asset, functionary

    def test_extraction_vacates_the_placement_and_keeps_identity(self):
        asset, functionary = self._recruited_in_place()
        vacated = extract_asset(asset, asset.promoter_persona)
        self.assertEqual(vacated, 1)
        self.assertFalse(Functionary.objects.filter(pk=functionary.pk, is_active=True).exists())
        functionary.refresh_from_db()
        # Identity survives extraction — the persona link is history until
        # the refill sweep resets the slot for a fresh hire.
        self.assertEqual(functionary.persona, asset.asset_persona)
        asset.refresh_from_db()
        self.assertEqual(asset.status, "active")

    def test_only_the_controller_extracts(self):
        asset, _ = self._recruited_in_place()
        with self.assertRaises(ExtractionError):
            extract_asset(asset, PersonaFactory())

    def test_in_place_recruitment_keeps_them_on_the_job(self):
        """The promotion handler no longer consumes the placement."""
        from django.core.exceptions import ObjectDoesNotExist  # noqa: F401

        from evennia_extensions.factories import RoomProfileFactory
        from world.assets.effects import promote_as_informant
        from world.character_sheets.factories import CharacterSheetFactory
        from world.checks.test_helpers import force_check_outcome
        from world.npc_services.factories import NPCServiceOfferFactory
        from world.traits.factories import CheckOutcomeFactory

        room = RoomProfileFactory()
        functionary = FunctionaryFactory(room=room)
        from world.checks.factories import CheckTypeFactory

        offer = NPCServiceOfferFactory(role=functionary.role, check_type=CheckTypeFactory())
        sheet = CharacterSheetFactory()
        recruiter = sheet.primary_persona
        character = sheet.character
        character.db_location = room.objectdb
        character.save()

        win = CheckOutcomeFactory(name="in-place recruit", success_level=2)
        with force_check_outcome(win):
            result = promote_as_informant(offer, recruiter)

        self.assertIsNotNone(result.object_pk)
        functionary.refresh_from_db()
        self.assertTrue(functionary.is_active)
        self.assertIsNotNone(functionary.persona)
