"""E2E tests for ASSET_TASK_INTEL offer (#1905).

Tests the full resolve_offer → dispatch_offer_effect → run_asset_intel_task
pipeline: PC interacts with their asset, selects the intel task offer, check
is rolled, and a CharacterClue is granted on success.
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from world.assets.constants import AssetStatus
from world.assets.factories import NPCAssetFactory
from world.assets.models import AssetTaskIntelDetails
from world.clues.factories import ClueFactory
from world.npc_services.constants import OfferKind
from world.npc_services.effects import dispatch_offer_effect, reset_offer_effect_handlers
from world.npc_services.factories import NPCRoleFactory
from world.npc_services.models import NPCServiceOffer
from world.roster.factories import RosterEntryFactory


class AssetTaskIntelHandlerTests(EvenniaTestCase):
    """Tests for the ASSET_TASK_INTEL offer effect handler (#1905)."""

    def setUp(self) -> None:
        super().setUp()
        # Ensure the AssetsConfig.ready() handlers are registered.
        from world.assets.apps import AssetsConfig  # noqa: F401

        # Build a promoter with a roster entry (needed for CharacterClue).
        self.roster_entry = RosterEntryFactory()
        self.sheet = self.roster_entry.character_sheet
        self.promoter = self.sheet.primary_persona
        self.character = self.sheet.character

        # Build an active asset owned by the promoter.
        self.asset = NPCAssetFactory(promoter_persona=self.promoter)

        # Build a Clue for the intel task to grant.
        self.clue = ClueFactory()

        # Build an NPCRole + an ASSET_TASK_INTEL offer + details.
        self.role = NPCRoleFactory()
        self.offer = NPCServiceOffer.objects.create(
            role=self.role,
            kind=OfferKind.ASSET_TASK_INTEL,
            label="Gather Intel",
            is_final=True,
        )
        AssetTaskIntelDetails.objects.create(
            offer=self.offer,
            clue=self.clue,
        )

    def tearDown(self) -> None:
        reset_offer_effect_handlers()
        super().tearDown()

    def test_successful_intel_task_grants_clue(self) -> None:
        """A successful intel task grants a CharacterClue to the promoter."""
        result = dispatch_offer_effect(self.offer, self.promoter)

        self.assertTrue(result.message.startswith("Your asset brings back word"))
        self.assertEqual(result.object_label, self.clue.name)
        # CharacterClue should be created for the promoter's roster entry.
        from world.clues.models import CharacterClue

        clue_held = CharacterClue.objects.filter(
            roster_entry=self.roster_entry, clue=self.clue
        ).exists()
        self.assertTrue(clue_held)

    def test_no_active_asset_returns_failure(self) -> None:
        """When the promoter has no active asset, the handler returns a failure."""
        # Compromise the asset so it's no longer ACTIVE.
        self.asset.status = AssetStatus.COMPROMISED
        self.asset.save(update_fields=["status"])

        result = dispatch_offer_effect(self.offer, self.promoter)

        self.assertEqual(result.message, "This asset is not available for tasking.")

    def test_missing_details_returns_authoring_error(self) -> None:
        """When the offer has no AssetTaskIntelDetails, returns an authoring error."""
        offer_without_details = NPCServiceOffer.objects.create(
            role=self.role,
            kind=OfferKind.ASSET_TASK_INTEL,
            label="Broken Intel Task",
            is_final=True,
        )

        result = dispatch_offer_effect(offer_without_details, self.promoter)

        self.assertIn("Authoring error", result.message)
