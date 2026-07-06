"""Effect handler tests for the promotion mechanic (#1872)."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.assets.constants import AssetRoleContext
from world.assets.models import NPCAsset
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.models import CheckCategory, CheckType
from world.checks.test_helpers import force_check_outcome
from world.npc_services.constants import OfferKind
from world.npc_services.effects import dispatch_offer_effect
from world.npc_services.factories import FunctionaryFactory, NPCServiceOfferFactory
from world.npc_services.functionaries import functionaries_in_room
from world.scenes.services import persona_for_character
from world.traits.factories import CheckOutcomeFactory


class PromoteFunctionaryEffectTests(EvenniaTestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.areas.services import get_room_profile

        self.room = create_object("typeclasses.rooms.Room", key="Cultivation Room")
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.location = self.room
        self.character.save()
        self.persona = persona_for_character(self.character)
        self.room_profile = get_room_profile(self.room)
        self.functionary = FunctionaryFactory(room=self.room_profile)
        category, _ = CheckCategory.objects.get_or_create(
            name="Test Category", defaults={"display_order": 0}
        )
        self.check_type, _ = CheckType.objects.get_or_create(
            name="Test Cultivation Check", category=category, defaults={"is_active": True}
        )
        self.offer = NPCServiceOfferFactory(
            role=self.functionary.role,
            kind=OfferKind.INFORMANT,
            check_type=self.check_type,
        )

    def test_success_creates_asset_and_spawns_persona(self) -> None:
        success = CheckOutcomeFactory(name="Forced Promotion Success", success_level=3)
        with force_check_outcome(success):
            result = dispatch_offer_effect(self.offer, self.persona)
        self.assertEqual(result.kind, OfferKind.INFORMANT.value)
        asset = NPCAsset.objects.get(promoter_persona=self.persona)
        self.assertEqual(asset.role_context, AssetRoleContext.INFORMANT)
        self.assertEqual(asset.source_functionary, self.functionary)
        self.assertEqual(asset.asset_persona.character_sheet.character.location, self.room)

    def test_success_deactivates_the_source_functionary(self) -> None:
        success = CheckOutcomeFactory(name="Forced Promotion Success 2", success_level=3)
        with force_check_outcome(success):
            dispatch_offer_effect(self.offer, self.persona)
        # remove_functionary() bulk-updates via .filter().update(), bypassing
        # the SharedMemoryModel identity map — flush before refresh_from_db()
        # so it re-reads the true DB row instead of returning the stale
        # cached instance (see world/battles/tests/test_models.py for the
        # same idiom).
        self.functionary.flush_from_cache()
        self.functionary.refresh_from_db()
        self.assertFalse(self.functionary.is_active)
        self.assertNotIn(self.functionary, functionaries_in_room(self.room_profile))

    def test_check_failure_creates_no_asset(self) -> None:
        failure = CheckOutcomeFactory(name="Forced Promotion Failure", success_level=0)
        with force_check_outcome(failure):
            result = dispatch_offer_effect(self.offer, self.persona)
        self.assertFalse(NPCAsset.objects.filter(promoter_persona=self.persona).exists())
        self.assertIn("not", result.message.lower())

    def test_dedup_guard_blocks_second_promotion_of_same_functionary(self) -> None:
        success = CheckOutcomeFactory(name="Forced Promotion Success 3", success_level=3)
        with force_check_outcome(success):
            dispatch_offer_effect(self.offer, self.persona)
        with force_check_outcome(success):
            result = dispatch_offer_effect(self.offer, self.persona)
        self.assertEqual(NPCAsset.objects.filter(promoter_persona=self.persona).count(), 1)
        self.assertIn("already", result.message.lower())

    def test_functionary_no_longer_here_is_handled(self) -> None:
        from world.npc_services.functionaries import remove_functionary

        remove_functionary(role=self.functionary.role, room=self.room_profile)
        success = CheckOutcomeFactory(name="Forced Promotion Success 4", success_level=3)
        with force_check_outcome(success):
            result = dispatch_offer_effect(self.offer, self.persona)
        self.assertFalse(NPCAsset.objects.filter(promoter_persona=self.persona).exists())
        self.assertIn("no longer", result.message.lower())

    def test_no_functionary_ever_placed_here_is_handled(self) -> None:
        from evennia import create_object

        from world.areas.services import get_room_profile

        # A distinct room with no Functionary of this role ever placed —
        # the very first .first() lookup in _promote_functionary returns
        # None, which is a different code path from "was here, then
        # removed" (test_functionary_no_longer_here_is_handled above).
        other_room = create_object("typeclasses.rooms.Room", key="Never Cultivated Room")
        self.character.location = other_room
        self.character.save()
        other_room_profile = get_room_profile(other_room)
        offer = NPCServiceOfferFactory(
            role=self.functionary.role,
            kind=OfferKind.INFORMANT,
            check_type=self.check_type,
        )
        success = CheckOutcomeFactory(name="Forced Promotion Success 5", success_level=3)
        with force_check_outcome(success):
            result = dispatch_offer_effect(offer, self.persona)
        self.assertFalse(NPCAsset.objects.filter(promoter_persona=self.persona).exists())
        self.assertIn("no longer", result.message.lower())
        self.assertFalse(
            functionaries_in_room(other_room_profile).filter(role=self.functionary.role).exists()
        )

    def test_promote_as_guard_sets_guard_role_context(self) -> None:
        success = CheckOutcomeFactory(name="Guard Promotion Success", success_level=3)
        offer = NPCServiceOfferFactory(
            role=self.functionary.role,
            kind=OfferKind.GUARD,
            check_type=self.check_type,
        )
        with force_check_outcome(success):
            dispatch_offer_effect(offer, self.persona)
        asset = NPCAsset.objects.get(promoter_persona=self.persona)
        self.assertEqual(asset.role_context, AssetRoleContext.GUARD)

    def test_promote_as_fan_sets_fan_role_context(self) -> None:
        success = CheckOutcomeFactory(name="Fan Promotion Success", success_level=3)
        offer = NPCServiceOfferFactory(
            role=self.functionary.role,
            kind=OfferKind.FAN,
            check_type=self.check_type,
        )
        with force_check_outcome(success):
            dispatch_offer_effect(offer, self.persona)
        asset = NPCAsset.objects.get(promoter_persona=self.persona)
        self.assertEqual(asset.role_context, AssetRoleContext.FAN)

    def test_promote_as_minor_ally_sets_minor_ally_role_context(self) -> None:
        success = CheckOutcomeFactory(name="Minor Ally Promotion Success", success_level=3)
        offer = NPCServiceOfferFactory(
            role=self.functionary.role,
            kind=OfferKind.MINOR_ALLY,
            check_type=self.check_type,
        )
        with force_check_outcome(success):
            dispatch_offer_effect(offer, self.persona)
        asset = NPCAsset.objects.get(promoter_persona=self.persona)
        self.assertEqual(asset.role_context, AssetRoleContext.MINOR_ALLY)
