"""Tests for CombatManeuver.USE_ITEM dispatch (#2023, #2120).

USE_ITEM admits on-use items (smoke bombs, thrown alchemicals, signal flares)
into the combat round as a primary maneuver. Using an item costs the round's
focused action — a tactical choice, not an anti-attrition effect.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
import pytest

from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.factories import CombatParticipantFactory
from world.combat.models import CombatRoundAction
from world.combat.services import _resolve_use_item, declare_use_item
from world.combat.types import ActionOutcome
from world.scenes.constants import RoundStatus


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
        """When item_instance is set (with a game_object), UseItemAction.run() is called."""
        from evennia_extensions.factories import ObjectDBFactory
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        item_obj = ObjectDBFactory(db_key="dispatchpotion", location=self.char)
        item = ItemInstanceFactory(template=ItemTemplateFactory(), game_object=item_obj)
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
            # The #2120 fix: the ObjectDB (not the ItemInstance row) is passed as
            # ``item``, and the (absent) target forwards as None, not dropped.
            assert mock_action.run.call_args.kwargs["item"] == item_obj
            assert mock_action.run.call_args.kwargs["target"] is None

    def test_failed_action_still_returns_outcome(self):
        """When UseItemAction.run() returns failure, an outcome is still returned."""
        from evennia_extensions.factories import ObjectDBFactory
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        item_obj = ObjectDBFactory(db_key="failpotion", location=self.char)
        item = ItemInstanceFactory(template=ItemTemplateFactory(), game_object=item_obj)
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

    def test_item_instance_without_game_object_is_a_noop(self):
        """A factory-bare ItemInstance (no game_object) resolves to a no-op, not a crash.

        Regression guard for the #2120 item-resolution fix: UseItemAction.run()
        expects an ObjectDB for its ``item`` kwarg, not the ItemInstance row
        itself -- resolved via ``action.item_instance.game_object``.
        """
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        item = ItemInstanceFactory(template=ItemTemplateFactory())  # game_object=None
        action = CombatRoundAction(
            participant=self.participant,
            round_number=1,
            maneuver=CombatManeuver.USE_ITEM,
            item_instance=item,
        )
        outcome = _resolve_use_item(self.participant, action)  # must not raise
        assert isinstance(outcome, ActionOutcome)

    def test_targeted_item_heals_the_declared_ally_not_the_actor(self):
        """Regression test for the #2120 target-forwarding bug (real dispatch, no mocks).

        A healing item declared with ``focused_ally_target`` set must apply its
        effect to the ally, not silently self-target the user. Also exercises the
        item-resolution fix end-to-end (real ItemInstance -> real game_object ->
        real UseItemAction.run() -> real use_item() service) and the charge
        decrement the spec's Testing section calls for.
        """
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.checks.constants import EffectTarget
        from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
        from world.combat.factories import CombatEncounterFactory
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.models import ConditionInstance
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        actor_char = CharacterFactory(db_key="UseItemHealer")
        actor_sheet = CharacterSheetFactory(character=actor_char)
        actor_participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=actor_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        ally_char = CharacterFactory(db_key="UseItemAlly", location=actor_char.location)
        ally_sheet = CharacterSheetFactory(character=ally_char)
        ally_participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        from world.vitals.models import CharacterVitals

        CharacterVitals.objects.get_or_create(
            character_sheet=actor_sheet, defaults={"health": 50, "max_health": 100}
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=ally_sheet, defaults={"health": 50, "max_health": 100}
        )

        condition = ConditionTemplateFactory()
        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(label="UseItemHealTarget")
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type="apply_condition",
            target=EffectTarget.TARGET,
            condition_template=condition,
        )
        template = ItemTemplateFactory(
            name="UseItemHealPotion",
            is_consumable=True,
            max_charges=2,
            on_use_pool=pool,
            on_use_check_type=None,
            on_use_target_kind="character",
        )
        item_obj = ObjectDBFactory(db_key="UseItemHealPotionObj", location=actor_char)
        item_instance = ItemInstanceFactory(template=template, game_object=item_obj, charges=2)

        action = declare_use_item(actor_participant, item_instance, target=ally_participant)
        assert action.focused_ally_target == ally_participant

        _resolve_use_item(actor_participant, action)

        assert ConditionInstance.objects.filter(target=ally_char, condition=condition).exists()
        assert not ConditionInstance.objects.filter(target=actor_char, condition=condition).exists()
        item_instance.refresh_from_db()
        assert item_instance.charges == 1  # charge decremented


class DeclareUseItemTests(TestCase):
    """Tests for declare_use_item service function (#2120), mirroring DeclareCoverTest."""

    def setUp(self) -> None:
        super().setUp()
        from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.factories import CombatEncounterFactory
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.vitals.models import CharacterVitals

        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.char = CharacterFactory(db_key="DeclareUseItemChar")
        self.sheet = CharacterSheetFactory(character=self.char)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.ally = CombatParticipantFactory(encounter=self.encounter)
        CharacterVitals.objects.get_or_create(
            character_sheet=self.sheet, defaults={"health": 50, "max_health": 100}
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=self.ally.character_sheet, defaults={"health": 50, "max_health": 100}
        )
        item_obj = ObjectDBFactory(db_key="DeclareUseItemObj", location=self.char)
        self.item = ItemInstanceFactory(template=ItemTemplateFactory(), game_object=item_obj)

    def test_declare_use_item_sets_maneuver_and_item(self) -> None:
        action = declare_use_item(self.participant, self.item)
        assert action.maneuver == CombatManeuver.USE_ITEM
        assert action.item_instance == self.item
        assert action.focused_ally_target is None
        assert action.focused_opponent_target is None
        assert action.is_ready is True

    def test_declare_use_item_with_ally_target(self) -> None:
        action = declare_use_item(self.participant, self.item, target=self.ally)
        assert action.focused_ally_target == self.ally
        assert action.focused_opponent_target is None

    def test_declare_use_item_with_opponent_target(self) -> None:
        from world.combat.factories import CombatOpponentFactory

        opponent = CombatOpponentFactory(encounter=self.encounter)
        action = declare_use_item(self.participant, self.item, target=opponent)
        assert action.focused_opponent_target == opponent
        assert action.focused_ally_target is None

    def test_declare_use_item_rejects_unheld_item(self) -> None:
        from evennia_extensions.factories import ObjectDBFactory
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        loose_obj = ObjectDBFactory(db_key="LooseItem")  # not on the participant
        loose_item = ItemInstanceFactory(template=ItemTemplateFactory(), game_object=loose_obj)
        with pytest.raises(ValueError, match="aren't holding"):
            declare_use_item(self.participant, loose_item)

    def test_declare_use_item_rejects_outside_declaring(self) -> None:
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        with pytest.raises(ValueError, match="expected 'Declaring'"):
            declare_use_item(self.participant, self.item)

    def test_declare_use_item_rejects_inactive_participant(self) -> None:
        self.participant.status = ParticipantStatus.FLED
        self.participant.save(update_fields=["status"])
        with pytest.raises(ValueError, match="no longer active"):
            declare_use_item(self.participant, self.item)

    def test_declare_use_item_rejects_foreign_ally(self) -> None:
        from world.combat.factories import CombatEncounterFactory

        other_encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        foreign_ally = CombatParticipantFactory(encounter=other_encounter)
        with pytest.raises(ValueError, match="active participant in this encounter"):
            declare_use_item(self.participant, self.item, target=foreign_ally)
