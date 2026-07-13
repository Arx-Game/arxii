"""E2E tests for ASSET_TASK_INTEL offer (#1905, #2293).

Tests the full resolve_offer → dispatch_offer_effect → run_asset_intel_task
pipeline: PC interacts with their asset, selects the intel task offer, check
is rolled, and a CharacterClue is drawn from the pool and granted on success.

#2293: the single fixed clue is replaced with a CluePool. Tests cover pool
draw, exclusion of already-held clues, pool-exhaustion hiding, and weighted
distribution.
"""

from __future__ import annotations

from collections import Counter

from evennia.utils.test_resources import EvenniaTestCase

from world.assets.constants import AssetStatus
from world.assets.factories import CluePoolEntryFactory, CluePoolFactory, NPCAssetFactory
from world.assets.models import AssetTaskIntelDetails
from world.clues.factories import ClueFactory
from world.clues.models import CharacterClue
from world.npc_services.constants import OfferKind
from world.npc_services.effects import dispatch_offer_effect, reset_offer_effect_handlers
from world.npc_services.factories import NPCRoleFactory
from world.npc_services.models import NPCServiceOffer
from world.npc_services.services import available_offers, start_interaction
from world.roster.factories import RosterEntryFactory


class AssetTaskIntelHandlerTests(EvenniaTestCase):
    """Tests for the ASSET_TASK_INTEL offer effect handler (#1905, #2293)."""

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

        # Build a CluePool with 3 clues for the intel task to draw from.
        self.pool = CluePoolFactory()
        self.clue_a = ClueFactory()
        self.clue_b = ClueFactory()
        self.clue_c = ClueFactory()
        CluePoolEntryFactory(pool=self.pool, clue=self.clue_a, weight=1)
        CluePoolEntryFactory(pool=self.pool, clue=self.clue_b, weight=1)
        CluePoolEntryFactory(pool=self.pool, clue=self.clue_c, weight=1)

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
            clue_pool=self.pool,
        )

    def tearDown(self) -> None:
        reset_offer_effect_handlers()
        super().tearDown()

    def test_successful_intel_task_grants_clue_from_pool(self) -> None:
        """A successful intel task grants a CharacterClue drawn from the pool."""
        result = dispatch_offer_effect(self.offer, self.promoter)

        self.assertTrue(result.message.startswith("Your asset brings back word"))
        # The granted clue must be one of the pool's clues.
        granted_clue_ids = set(
            CharacterClue.objects.filter(roster_entry=self.roster_entry).values_list(
                "clue_id", flat=True
            )
        )
        pool_clue_ids = {self.clue_a.pk, self.clue_b.pk, self.clue_c.pk}
        self.assertTrue(granted_clue_ids.issubset(pool_clue_ids))
        self.assertEqual(len(granted_clue_ids), 1)

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

    def test_pool_excludes_already_held_clues(self) -> None:
        """Already-held clues are never drawn from the pool."""
        # Pre-grant clue_a to the promoter.
        CharacterClue.objects.create(
            roster_entry=self.roster_entry,
            clue=self.clue_a,
        )

        # Draw multiple times — should never return clue_a.
        for _ in range(10):
            result = dispatch_offer_effect(self.offer, self.promoter)
            self.assertNotEqual(result.object_label, self.clue_a.name)

    def test_pool_exhaustion_returns_nothing_new(self) -> None:
        """When all clues are held, the handler returns 'nothing new to report'."""
        # Grant all three clues.
        CharacterClue.objects.create(roster_entry=self.roster_entry, clue=self.clue_a)
        CharacterClue.objects.create(roster_entry=self.roster_entry, clue=self.clue_b)
        CharacterClue.objects.create(roster_entry=self.roster_entry, clue=self.clue_c)

        result = dispatch_offer_effect(self.offer, self.promoter)

        self.assertIn("nothing new to report", result.message.lower())

    def test_pool_exhaustion_hides_offer(self) -> None:
        """When all clues are held, the offer is ineligible (hidden from available_offers)."""
        # Grant all three clues.
        CharacterClue.objects.create(roster_entry=self.roster_entry, clue=self.clue_a)
        CharacterClue.objects.create(roster_entry=self.roster_entry, clue=self.clue_b)
        CharacterClue.objects.create(roster_entry=self.roster_entry, clue=self.clue_c)

        session = start_interaction(
            role=self.role,
            persona=self.promoter,
            character=self.character,
        )
        offers = available_offers(session)
        self.assertNotIn(self.offer, offers)

    def test_pool_not_exhausted_shows_offer(self) -> None:
        """When some clues remain unheld, the offer is still eligible."""
        # Grant only one clue — two remain.
        CharacterClue.objects.create(roster_entry=self.roster_entry, clue=self.clue_a)

        session = start_interaction(
            role=self.role,
            persona=self.promoter,
            character=self.character,
        )
        offers = available_offers(session)
        self.assertIn(self.offer, offers)

    def test_weighted_draw_distribution(self) -> None:
        """Weighted clues appear at roughly the expected frequency."""
        # Rebuild the pool with weights 3:1.
        weighted_pool = CluePoolFactory()
        clue_common = ClueFactory()
        clue_rare = ClueFactory()
        CluePoolEntryFactory(pool=weighted_pool, clue=clue_common, weight=3)
        CluePoolEntryFactory(pool=weighted_pool, clue=clue_rare, weight=1)

        weighted_offer = NPCServiceOffer.objects.create(
            role=self.role,
            kind=OfferKind.ASSET_TASK_INTEL,
            label="Weighted Intel",
            is_final=True,
        )
        AssetTaskIntelDetails.objects.create(
            offer=weighted_offer,
            clue_pool=weighted_pool,
        )

        # Draw 40 times (resetting the held clue each time so the pool
        # doesn't exhaust). With weight 3:1, we expect ~30 common / ~10 rare.
        # Use a loose assertion: common should appear more than half the time.
        results: list[str] = []
        for _ in range(40):
            result = dispatch_offer_effect(weighted_offer, self.promoter)
            results.append(result.object_label)
            # Clear the granted clue so the next draw is from the full pool.
            CharacterClue.objects.filter(
                roster_entry=self.roster_entry,
                clue__in=[clue_common, clue_rare],
            ).delete()

        counts = Counter(results)
        self.assertGreater(counts[clue_common.name], counts[clue_rare.name])
