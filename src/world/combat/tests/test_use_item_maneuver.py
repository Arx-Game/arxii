"""Tests for CombatManeuver.USE_ITEM dispatch (#2023).

USE_ITEM admits on-use items (smoke bombs, thrown alchemicals, signal flares)
into the combat round as a primary maneuver. Using an item costs the round's
focused action — a tactical choice, not an anti-attrition effect.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.combat.constants import CombatManeuver
from world.combat.factories import CombatParticipantFactory
from world.combat.models import CombatRoundAction
from world.combat.services import _resolve_use_item
from world.combat.types import ActionOutcome


class UseItemManeuverConstantsTests(TestCase):
    def test_use_item_maneuver_exists(self):
        assert hasattr(CombatManeuver, "USE_ITEM")
        assert CombatManeuver.USE_ITEM == "use_item"


class ResolveUseItemTests(TestCase):
    """_resolve_use_item dispatches UseItemAction.run() and wraps its result."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatEncounterFactory
        from world.scenes.constants import RoundStatus
        from world.vitals.models import CharacterVitals

        cls.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        cls.char = CharacterFactory(db_key="useitemchar")
        cls.sheet = CharacterSheetFactory(character=cls.char)
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=cls.sheet,
            defaults={"health": 50, "max_health": 100},
        )

    def test_no_item_instance_returns_empty_outcome(self):
        """When item_instance is None, the outcome has no damage results."""
        action = CombatRoundAction(
            participant=self.participant,
            round_number=1,
            maneuver=CombatManeuver.USE_ITEM,
            item_instance=None,
        )
        outcome = _resolve_use_item(self.participant, action)
        assert isinstance(outcome, ActionOutcome)
        assert outcome.damage_results == []

    def test_dispatches_use_item_action(self):
        """When item_instance is set, UseItemAction.run() is called."""
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        item = ItemInstanceFactory(template=ItemTemplateFactory())
        action = CombatRoundAction(
            participant=self.participant,
            round_number=1,
            maneuver=CombatManeuver.USE_ITEM,
            item_instance=item,
        )
        with patch("actions.definitions.items.UseItemAction") as mock_action_cls:
            mock_action = MagicMock()
            mock_action.run.return_value = MagicMock(success=True)
            mock_action_cls.return_value = mock_action
            _resolve_use_item(self.participant, action)
            assert mock_action.run.called

    def test_failed_action_still_returns_outcome(self):
        """When UseItemAction.run() returns failure, an outcome is still returned."""
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        item = ItemInstanceFactory(template=ItemTemplateFactory())
        action = CombatRoundAction(
            participant=self.participant,
            round_number=1,
            maneuver=CombatManeuver.USE_ITEM,
            item_instance=item,
        )
        with patch("actions.definitions.items.UseItemAction") as mock_action_cls:
            mock_action = MagicMock()
            mock_action.run.return_value = MagicMock(success=False)
            mock_action_cls.return_value = mock_action
            outcome = _resolve_use_item(self.participant, action)
            assert isinstance(outcome, ActionOutcome)
