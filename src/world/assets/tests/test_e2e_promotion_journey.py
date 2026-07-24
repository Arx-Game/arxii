"""E2E journey: talk to a Functionary, build rapport, cultivate as an asset (#1872)."""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.assets.content import ensure_asset_promotion_content
from world.assets.models import NPCAsset
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.npc_services.functionaries import place_functionary
from world.npc_services.models import NPCServiceOffer
from world.traits.factories import CheckOutcomeFactory
from world.traits.models import CharacterTraitValue, Trait


class PromotionJourneyTests(EvenniaTestCase):
    def setUp(self) -> None:
        from evennia import create_object

        from world.areas.services import get_room_profile

        self.room = create_object("typeclasses.rooms.Room", key="Cultivation Journey Room")
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.character.location = self.room
        self.character.save()
        self.role = ensure_asset_promotion_content()
        self.room_profile = get_room_profile(self.room)
        self.functionary = place_functionary(role=self.role, room=self.room_profile)
        stealth = Trait.objects.get(name="Stealth")
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=stealth, value=5
        )
        # #1907 — also gate on Persuasion (the GUARD variant's min_trait) and
        # Scholarship (the MINOR_ALLY variant's min_trait) so the new offers are
        # eligible once rapport is met.
        persuasion = Trait.objects.get(name="Persuasion")
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=persuasion, value=5
        )
        scholarship = Trait.objects.get(name="Scholarship")
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=scholarship, value=5
        )

    def test_full_promotion_journey(self) -> None:
        from actions.definitions.npc_services import (
            ResolveNPCOfferAction,
            StartNPCInteractionAction,
        )
        from world.npc_services.services import available_offers

        start_result = StartNPCInteractionAction().run(actor=self.character, role_id=self.role.pk)
        self.assertTrue(start_result.success, start_result.message)
        session = start_result.data["session"]

        offer = NPCServiceOffer.objects.get(role=self.role, label="Cultivate as Informant")
        # Below the rapport_requirement (20) — not yet eligible.
        self.assertNotIn(offer, available_offers(session))

        session.current_rapport = 25
        self.assertIn(offer, available_offers(session))

        success = CheckOutcomeFactory(name="Journey Cultivation Success", success_level=3)
        with force_check_outcome(success):
            resolve_result = ResolveNPCOfferAction().run(
                actor=self.character,
                session=session,
                offer_id=offer.pk,
                acknowledge_risk=False,
            )
        self.assertTrue(resolve_result.success, resolve_result.message)

        asset = NPCAsset.objects.get(source_functionary=self.functionary)
        self.assertEqual(asset.asset_persona.character_sheet.character.location, self.room)
        # remove_functionary() bulk-updates via .filter().update(), which bypasses the
        # SharedMemoryModel identity map (see world/assets/effects.py's own note on this) —
        # flush the idmapper cache before refresh_from_db() so it doesn't just re-copy the
        # same stale cached instance onto itself.
        self.functionary.flush_from_cache(force=True)
        self.functionary.refresh_from_db()
        self.assertFalse(self.functionary.is_active)

        # A fresh interaction with the newly-named NPC tracks NPCStanding normally.
        from world.npc_services.models import NPCStanding
        from world.npc_services.services import end_interaction, start_interaction

        follow_up = start_interaction(
            role=self.role,
            persona=asset.promoter_persona,
            character=self.character,
            npc_persona=asset.asset_persona,
        )
        follow_up.current_rapport += 5
        end_interaction(follow_up)
        standing = NPCStanding.objects.get(
            persona=asset.promoter_persona, npc_persona=asset.asset_persona
        )
        self.assertEqual(standing.affection, 5)

    def test_guard_promotion_journey(self) -> None:
        """#1907 — a GUARD-variant cultivation through the full action seam."""
        from actions.definitions.npc_services import (
            ResolveNPCOfferAction,
            StartNPCInteractionAction,
        )
        from world.assets.constants import AssetRoleContext
        from world.npc_services.services import available_offers

        start_result = StartNPCInteractionAction().run(actor=self.character, role_id=self.role.pk)
        self.assertTrue(start_result.success, start_result.message)
        session = start_result.data["session"]

        offer = NPCServiceOffer.objects.get(role=self.role, label="Cultivate as Guard")
        # Below the rapport_requirement (20) — not yet eligible.
        self.assertNotIn(offer, available_offers(session))

        session.current_rapport = 25
        self.assertIn(offer, available_offers(session))

        success = CheckOutcomeFactory(name="Guard Journey Success", success_level=3)
        with force_check_outcome(success):
            resolve_result = ResolveNPCOfferAction().run(
                actor=self.character,
                session=session,
                offer_id=offer.pk,
                acknowledge_risk=False,
            )
        self.assertTrue(resolve_result.success, resolve_result.message)

        asset = NPCAsset.objects.get(source_functionary=self.functionary)
        self.assertEqual(asset.role_context, AssetRoleContext.GUARD)
