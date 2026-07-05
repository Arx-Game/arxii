"""Contract tests for ImbueAction crossing-requirement surfacing (#1885).

Verifies that when spend_resonance_for_imbuing returns
blocked_by="CROSSING_REQUIREMENT", the action's ActionResult carries the
failed-requirement messages and success=True (matching the XP_LOCK precedent).
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.imbue import ImbueAction
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemTemplateFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterResonanceFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
    ThreadFactory,
)
from world.magic.models import PendingRitualEffect, ThreadCrossingThreshold
from world.progression.models import ItemRequirement


class ImbueActionCrossingRequirementTests(TestCase):
    """ImbueAction surfaces crossing-requirement blocks correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.resonance, balance=9999)
        cls.template = ItemTemplateFactory()
        cls.ritual = ImbuingRitualFactory()

    def setUp(self) -> None:
        # Each test needs a fresh PendingRitualEffect since the action consumes it.
        PendingRitualEffect.objects.get_or_create(character=self.sheet, ritual=self.ritual)

    def _make_thread_at_level(self, level: int):
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            level=level,
            developed_points=0,
            _trait_value=999,
        )

    def test_crossing_block_returns_success_with_messages(self) -> None:
        """When blocked_by=CROSSING_REQUIREMENT, action returns success=True
        with the failed-requirement messages in the message text."""
        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=3)
        ItemRequirement.objects.create(
            thread_crossing_threshold=threshold,
            item_template=self.template,
            quantity=1,
        )
        thread = self._make_thread_at_level(2)

        action = ImbueAction()
        result = action.run(
            actor=self.sheet.character,
            thread=thread,
            amount=1,
        )
        self.assertTrue(result.success, f"Expected success=True, got: {result.message}")
        assert "crossing requirements" in result.message.lower()
        assert "Need" in result.message

    def test_crossing_block_consumes_pending_effect(self) -> None:
        """The PendingRitualEffect is still consumed on a crossing block
        (the rite completed; re-attempting requires a new rite)."""
        threshold = ThreadCrossingThreshold.objects.create(target_kind=TargetKind.TRAIT, level=3)
        ItemRequirement.objects.create(
            thread_crossing_threshold=threshold,
            item_template=self.template,
            quantity=1,
        )
        thread = self._make_thread_at_level(2)

        action = ImbueAction()
        action.run(actor=self.sheet.character, thread=thread, amount=1)

        assert not PendingRitualEffect.objects.filter(
            character=self.sheet, ritual=self.ritual
        ).exists()

    def test_no_crossing_block_returns_normal_message(self) -> None:
        """When not blocked by a crossing, the normal imbue message is returned."""
        thread = self._make_thread_at_level(2)

        action = ImbueAction()
        result = action.run(
            actor=self.sheet.character,
            thread=thread,
            amount=1,
        )
        self.assertTrue(result.success)
        assert "crossing requirements" not in result.message.lower()
