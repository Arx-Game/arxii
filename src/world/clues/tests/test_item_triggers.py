"""Item-acquisition clue triggers (#1160) — maybe_grant_item_acquisition_clues + the hook."""

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import give, pick_up
from world.clues.constants import ClueResolution
from world.clues.factories import ClueFactory, ItemClueTriggerFactory
from world.clues.models import CharacterClue
from world.clues.services import acquire_clue, maybe_grant_item_acquisition_clues
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.items.factories import ItemInstanceFactory
from world.roster.factories import RosterEntryFactory


def _acquirer():
    roster = RosterEntryFactory()
    return roster, roster.character_sheet.character


class ItemClueTriggerServiceTests(TestCase):
    """The grant logic, exercised directly on the service (no inventory flow)."""

    def test_eligible_acquirer_is_granted_the_clue(self) -> None:
        roster, character = _acquirer()
        trigger = ItemClueTriggerFactory()
        item = ItemInstanceFactory(template=trigger.item_template)

        granted = maybe_grant_item_acquisition_clues(character, item)

        assert granted == [trigger.clue]
        assert CharacterClue.objects.filter(roster_entry=roster, clue=trigger.clue).exists()

    def test_other_item_kind_does_not_fire(self) -> None:
        _, character = _acquirer()
        ItemClueTriggerFactory()  # trigger anchored to its own template
        other_item = ItemInstanceFactory()  # a different template

        assert maybe_grant_item_acquisition_clues(character, other_item) == []

    def test_already_held_clue_is_not_regranted(self) -> None:
        roster, character = _acquirer()
        trigger = ItemClueTriggerFactory()
        item = ItemInstanceFactory(template=trigger.item_template)
        acquire_clue(roster, trigger.clue)

        granted = maybe_grant_item_acquisition_clues(character, item)

        assert granted == []
        assert CharacterClue.objects.filter(roster_entry=roster, clue=trigger.clue).count() == 1

    def test_ineligible_acquirer_is_skipped(self) -> None:
        roster, character = _acquirer()
        trigger = ItemClueTriggerFactory(eligibility_rule={"op": "OR", "of": []})
        item = ItemInstanceFactory(template=trigger.item_template)

        granted = maybe_grant_item_acquisition_clues(character, item)

        assert granted == []
        assert not CharacterClue.objects.filter(roster_entry=roster).exists()

    def test_inactive_trigger_does_not_fire(self) -> None:
        _, character = _acquirer()
        trigger = ItemClueTriggerFactory(is_active=False)
        item = ItemInstanceFactory(template=trigger.item_template)

        assert maybe_grant_item_acquisition_clues(character, item) == []

    def test_no_triggers_is_a_noop(self) -> None:
        _, character = _acquirer()
        item = ItemInstanceFactory()

        assert maybe_grant_item_acquisition_clues(character, item) == []

    def test_automatic_codex_clue_resolves_on_acquire(self) -> None:
        roster, character = _acquirer()
        entry = CodexEntryFactory(learn_threshold=5)
        clue = ClueFactory(target_codex_entry=entry, resolution_mode=ClueResolution.AUTOMATIC)
        trigger = ItemClueTriggerFactory(clue=clue)
        item = ItemInstanceFactory(template=trigger.item_template)

        maybe_grant_item_acquisition_clues(character, item)

        knowledge = CharacterCodexKnowledge.objects.get(roster_entry=roster, entry=entry)
        assert knowledge.status == CodexKnowledgeStatus.KNOWN


class ItemClueTriggerOnAcquireTests(TestCase):
    """The inventory chokepoint fires the trigger after commit, on both acquisition paths."""

    def _room(self, key: str):
        return ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")

    def _item_in(self, room, template, key: str):
        item_obj = ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.objects.Object")
        item_obj.location = room
        item_obj.save()
        return ItemInstanceFactory(
            game_object=item_obj, template=template, holder_character_sheet=None
        )

    def test_picking_up_an_item_fires_the_trigger(self) -> None:
        roster = RosterEntryFactory()
        character = roster.character_sheet.character
        room = self._room("ItemTriggerPickupRoom")
        character.location = room
        character.save()
        trigger = ItemClueTriggerFactory()
        item = self._item_in(room, trigger.item_template, "ItemTriggerPickupObj")
        ctx = MagicMock()

        with self.captureOnCommitCallbacks(execute=True):
            pick_up(CharacterState(character, context=ctx), ItemState(item, context=ctx))

        assert CharacterClue.objects.filter(roster_entry=roster, clue=trigger.clue).exists()

    def test_being_given_an_item_fires_the_trigger_for_the_recipient(self) -> None:
        giver_roster = RosterEntryFactory()
        giver = giver_roster.character_sheet.character
        recipient_roster = RosterEntryFactory()
        recipient = recipient_roster.character_sheet.character
        room = self._room("ItemTriggerGiveRoom")
        giver.location = room
        giver.save()
        recipient.location = room
        recipient.save()
        trigger = ItemClueTriggerFactory()
        item = self._item_in(room, trigger.item_template, "ItemTriggerGiveObj")
        item.holder_character_sheet = giver.sheet_data
        item.save()
        item.game_object.location = giver
        item.game_object.save()
        ctx = MagicMock()

        with self.captureOnCommitCallbacks(execute=True):
            give(
                CharacterState(giver, context=ctx),
                CharacterState(recipient, context=ctx),
                ItemState(item, context=ctx),
            )

        assert CharacterClue.objects.filter(
            roster_entry=recipient_roster, clue=trigger.clue
        ).exists()
        # The giver, who parted with it, gets nothing.
        assert not CharacterClue.objects.filter(roster_entry=giver_roster).exists()
