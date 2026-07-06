"""``steal`` service + ``set_container_policy`` tests (#1909 Task 4).

Covers the 5-case matrix from the task-4 brief plus the sheet-less-actor
assertion: sheet-less actors never steal (``take_requires_steal`` returns
False for a None sheet, so ``steal_permitted`` is False and ``steal`` raises
``TheftNotPermitted``) — they free-take instead.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import set_container_policy, steal, steal_permitted
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.consent.constants import ConsentMode
from world.consent.services import (
    add_social_consent_whitelist,
    set_social_consent_category_rule,
    set_social_consent_preference,
    theft_category,
)
from world.items.constants import ContainerAccessPolicy, OwnershipEventType
from world.items.exceptions import NotAContainer, NotInPossession, TheftNotPermitted
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance, OwnershipEvent
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterTenure
from world.societies.models import LegendEntry


class StealServiceTests(TestCase):
    """The 5-case matrix for ``steal`` + ``set_container_policy`` (#1909)."""

    def setUp(self) -> None:
        # Evennia typeclass instances cannot live on setUpTestData (DbHolder
        # deepcopy issue) — same per-test setUp pattern as test_access_policy.py.
        self.room = ObjectDBFactory(
            db_key="StealRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.victim = CharacterFactory(db_key="StealVictim", location=self.room)
        self.victim_sheet = CharacterSheetFactory(character=self.victim)
        self.thief = CharacterFactory(db_key="StealThief", location=self.room)
        self.thief_sheet = CharacterSheetFactory(character=self.thief)

        self.thief_state = CharacterState(self.thief, context=MagicMock())

    # ------------------------------------------------------------------
    # Fixture builders
    # ------------------------------------------------------------------

    def _room_item(self, *, holder: CharacterSheet | None) -> ItemState:
        item_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        item_obj.location = self.room
        item_obj.save()
        instance = ItemInstanceFactory(game_object=item_obj, holder_character_sheet=holder)
        return ItemState(instance, context=MagicMock())

    def _active_tenure(self, sheet: CharacterSheet) -> RosterTenure:
        return RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=sheet))

    def _allow_theft(self, *, owner_tenure: RosterTenure, actor_tenure: RosterTenure) -> None:
        preference = set_social_consent_preference(owner_tenure, allow_social_actions=True)
        set_social_consent_category_rule(preference, theft_category(), ConsentMode.ALLOWLIST)
        add_social_consent_whitelist(owner_tenure, actor_tenure, theft_category())

    # ------------------------------------------------------------------
    # Case 1: consent-allowed player-owned room item -> steal succeeds.
    # ------------------------------------------------------------------

    def test_consent_allowed_steal_succeeds_with_provenance_and_deed(self) -> None:
        owner_tenure = self._active_tenure(self.victim_sheet)
        actor_tenure = self._active_tenure(self.thief_sheet)
        self._allow_theft(owner_tenure=owner_tenure, actor_tenure=actor_tenure)

        item_state = self._room_item(holder=self.victim_sheet)
        self.assertTrue(steal_permitted(self.thief_sheet, item_state.instance))

        steal(self.thief_state, item_state)

        item_state.instance.refresh_from_db()
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.holder_character_sheet, self.thief_sheet)
        self.assertEqual(item_state.instance.game_object.location, self.thief)

        event = OwnershipEvent.objects.get(item_instance=item_state.instance)
        self.assertEqual(event.event_type, OwnershipEventType.STOLEN)
        self.assertEqual(event.from_character_sheet, self.victim_sheet)
        self.assertEqual(event.to_character_sheet, self.thief_sheet)

        thief_persona = self.thief_sheet.primary_persona
        self.assertTrue(LegendEntry.objects.filter(persona=thief_persona).exists())
        deed = LegendEntry.objects.get(persona=thief_persona)
        self.assertTrue(deed.crime_tags.exists())

    # ------------------------------------------------------------------
    # Case 2: blocked by consent (default-deny, no rule) -> TheftNotPermitted.
    # ------------------------------------------------------------------

    def test_consent_blocked_steal_raises_theft_not_permitted(self) -> None:
        self._active_tenure(self.victim_sheet)
        self._active_tenure(self.thief_sheet)

        item_state = self._room_item(holder=self.victim_sheet)
        self.assertFalse(steal_permitted(self.thief_sheet, item_state.instance))

        with self.assertRaises(TheftNotPermitted):
            steal(self.thief_state, item_state)

        item_state.instance.refresh_from_db()
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.holder_character_sheet, self.victim_sheet)
        self.assertEqual(item_state.instance.game_object.location, self.room)
        self.assertFalse(OwnershipEvent.objects.filter(item_instance=item_state.instance).exists())
        self.assertFalse(
            LegendEntry.objects.filter(persona=self.thief_sheet.primary_persona).exists()
        )

    # ------------------------------------------------------------------
    # Case 3: NPC-owned item (owner sheet has no active tenure) -> always
    # antagonism-allowed.
    # ------------------------------------------------------------------

    def test_npc_owned_item_steal_permitted_and_succeeds(self) -> None:
        # self.victim_sheet has no RosterTenure at all in this test -> NPC.
        item_state = self._room_item(holder=self.victim_sheet)
        self.assertTrue(steal_permitted(self.thief_sheet, item_state.instance))

        steal(self.thief_state, item_state)

        item_state.instance.refresh_from_db()
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.holder_character_sheet, self.thief_sheet)
        self.assertEqual(item_state.instance.game_object.location, self.thief)

    # ------------------------------------------------------------------
    # Case 4: item NOT requiring steal (unowned) -> TheftNotPermitted (steal
    # is not a synonym for take).
    # ------------------------------------------------------------------

    def test_unowned_item_steal_raises_theft_not_permitted(self) -> None:
        item_state = self._room_item(holder=None)
        self.assertFalse(steal_permitted(self.thief_sheet, item_state.instance))

        with self.assertRaises(TheftNotPermitted):
            steal(self.thief_state, item_state)

        item_state.instance.refresh_from_db()
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, self.room)
        self.assertFalse(OwnershipEvent.objects.filter(item_instance=item_state.instance).exists())

    # ------------------------------------------------------------------
    # Sheet-less actor: never steals — take_requires_steal returns False for
    # a None sheet, so steal_permitted is False and steal raises.
    # ------------------------------------------------------------------

    def test_sheetless_actor_steal_raises_theft_not_permitted(self) -> None:
        sheetless = CharacterFactory(db_key="StealSheetless", location=self.room)
        sheetless_state = CharacterState(sheetless, context=MagicMock())
        item_state = self._room_item(holder=self.victim_sheet)

        self.assertFalse(steal_permitted(None, item_state.instance))

        with self.assertRaises(TheftNotPermitted):
            steal(sheetless_state, item_state)

        item_state.instance.refresh_from_db()
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.holder_character_sheet, self.victim_sheet)
        self.assertEqual(item_state.instance.game_object.location, self.room)

    # ------------------------------------------------------------------
    # Case 5: set_container_policy — owner sets FRIENDS -> persisted;
    # non-owner raises NotInPossession; non-container raises NotAContainer.
    # ------------------------------------------------------------------

    def _container(self, *, owner_sheet: CharacterSheet | None) -> ItemInstance:
        template = ItemTemplateFactory(name="StealBox", is_container=True)
        container_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        container_obj.location = self.room
        container_obj.save()
        return ItemInstanceFactory(
            template=template,
            game_object=container_obj,
            holder_character_sheet=owner_sheet,
        )

    def test_owner_sets_container_policy_persisted(self) -> None:
        container_instance = self._container(owner_sheet=self.victim_sheet)
        victim_state = CharacterState(self.victim, context=MagicMock())
        container_state = ItemState(container_instance, context=MagicMock())

        set_container_policy(victim_state, container_state, ContainerAccessPolicy.FRIENDS)

        container_instance.refresh_from_db()
        self.assertEqual(container_instance.access_policy, ContainerAccessPolicy.FRIENDS)

    def test_non_owner_set_container_policy_raises_not_in_possession(self) -> None:
        container_instance = self._container(owner_sheet=self.victim_sheet)
        container_state = ItemState(container_instance, context=MagicMock())

        with self.assertRaises(NotInPossession):
            set_container_policy(self.thief_state, container_state, ContainerAccessPolicy.FRIENDS)

    def test_non_container_set_container_policy_raises_not_a_container(self) -> None:
        item_state = self._room_item(holder=self.thief_sheet)

        with self.assertRaises(NotAContainer):
            set_container_policy(self.thief_state, item_state, ContainerAccessPolicy.FRIENDS)

    def test_sheetless_actor_set_container_policy_raises_not_in_possession(self) -> None:
        """A sheet-less actor owns nothing so can't be the owner — refuse, don't crash."""
        sheetless = CharacterFactory(db_key="StealSheetlessPolicy", location=self.room)
        sheetless_state = CharacterState(sheetless, context=MagicMock())
        container_instance = self._container(owner_sheet=self.victim_sheet)
        container_state = ItemState(container_instance, context=MagicMock())

        with self.assertRaises(NotInPossession):
            set_container_policy(sheetless_state, container_state, ContainerAccessPolicy.FRIENDS)
