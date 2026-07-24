"""E2E integration test: craft facet → wear item → pull on a FACET thread.

Proves the full loop: craft_attach_facet (Enchanting check) attaches the facet,
equipping the item satisfies the worn-items gate, and spend_resonance_for_pull
debits resonance correctly.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import (
    EquippedItemFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.items.services.crafting import craft_attach_facet
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    FacetFactory,
    ResonanceFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterResonance, Thread
from world.magic.services import spend_resonance_for_pull
from world.magic.types import PullActionContext
from world.traits.factories import CharacterTraitValueFactory, CheckOutcomeFactory
from world.traits.models import Trait


class CraftedFacetPowersFacetPullTest(TestCase):
    """E2E: craft → wear → pull on a FACET thread."""

    def setUp(self) -> None:
        # Wire the Enchanting skill + CheckType + crafting config singleton.
        wire_enchanting_crafting(base_difficulty=0)

        # requires_station defaults True (#1234) — put the crafter in a room
        # with a full Lab station so the craft step passes the station gate.
        self.room_profile = RoomProfileFactory()
        install_full_lab_station(self.room_profile)

        # A wide quality tier so any score resolves to something.
        QualityTierFactory(name="Common", numeric_min=0, numeric_max=9999, sort_order=0)

        # Character sheet + the prerequisites the pull service requires.
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room_profile.objectdb
        self.sheet.character.save()
        CharacterAnimaFactory(character=self.sheet.character, current=10, maximum=10)
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
            lifetime_earned=10,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)

        # The facet that will be crafted onto the item.
        self.facet = FacetFactory()

        # Give the crafter the Enchanting trait so perform_check has something to roll.
        CharacterTraitValueFactory(
            character=self.sheet,
            trait=Trait.objects.get(name="Enchanting"),
            value=50,
        )

        # An item that can hold at least one facet.
        self.item = ItemInstanceFactory(template=ItemTemplateFactory(facet_capacity=3))

        # The AccountDB used as crafter_account.
        self.account = AccountFactory()

    def test_crafted_facet_powers_a_facet_pull_once_worn(self) -> None:
        # ── 1. CRAFT ────────────────────────────────────────────────────────────
        with force_check_outcome(CheckOutcomeFactory(name="Ok", success_level=2)):
            result = craft_attach_facet(
                crafter_account=self.account,
                crafter_character=self.sheet.character,
                item_instance=self.item,
                facet=self.facet,
            )

        self.assertTrue(result.attached)
        self.assertIsNotNone(result.quality_tier)

        # ── 2. WEAR ─────────────────────────────────────────────────────────────
        EquippedItemFactory(character=self.sheet.character, item_instance=self.item)
        # Invalidate so the handler re-loads from DB (setUp may have touched the cache).
        self.sheet.character.equipped_items.invalidate()

        # ── 3. PULL ─────────────────────────────────────────────────────────────
        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.FACET,
            target_facet=self.facet,
            level=0,
            developed_points=0,
        )
        # Add a NARRATIVE_ONLY tier-1 effect so resolve_pull_effects doesn't fail.
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=self.resonance,
            tier=1,
            as_narrative_only=True,
        )

        ctx = PullActionContext(combat_encounter=None, participant=None)
        pull_result = spend_resonance_for_pull(
            self.sheet,
            self.resonance,
            tier=1,
            threads=[thread],
            action_context=ctx,
        )

        # ── 4. ASSERT ───────────────────────────────────────────────────────────
        self.assertEqual(pull_result.resonance_spent, 2)
        cr = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        )
        self.assertEqual(cr.balance, 8)  # 10 − 2
