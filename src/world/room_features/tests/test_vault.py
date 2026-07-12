"""Tests for the VAULT RoomFeatureKind (#2179).

Covers: vault install, access-list management, take-gate integration,
steal consent integration, drop deposit clearing, and capacity scaling.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import _vault_denies, drop, pick_up, steal, steal_permitted
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.consent.constants import ConsentMode
from world.consent.services import (
    set_social_consent_category_rule,
    set_social_consent_preference,
    theft_category,
)
from world.items.constants import OwnershipEventType
from world.items.exceptions import VaultAccessDenied, VaultFull
from world.items.factories import ItemInstanceFactory
from world.items.models import OwnershipEvent
from world.room_features.constants import (
    VAULT_MAX_ITEMS_PER_LEVEL,
    RoomFeatureServiceStrategy,
)
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.room_features.models import RoomFeatureInstance, VaultAccessEntry, VaultDetails
from world.room_features.vault_services import (
    add_vault_access,
    handle_vault_progression,
    has_vault_access,
    list_vault_access,
    remove_vault_access,
    vault_capacity_remaining,
    vault_for_location,
    vault_for_room,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class VaultTestCase(TestCase):
    """Base test case with a room, vault, and two characters."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="VaultRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.room_profile = RoomProfileFactory(objectdb=self.room)

        # Founder (vault owner)
        self.founder = CharacterFactory(db_key="VaultFounder", location=self.room)
        self.founder_sheet = CharacterSheetFactory(character=self.founder)
        self.founder_persona = self.founder_sheet.primary_persona
        self.founder_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.founder_sheet)
        )

        # Authorized user
        self.authorized = CharacterFactory(db_key="VaultAuthorized", location=self.room)
        self.authorized_sheet = CharacterSheetFactory(character=self.authorized)
        self.authorized_persona = self.authorized_sheet.primary_persona
        self.authorized_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.authorized_sheet)
        )

        # Unauthorized user
        self.unauthorized = CharacterFactory(db_key="VaultThief", location=self.room)
        self.unauthorized_sheet = CharacterSheetFactory(character=self.unauthorized)
        self.unauthorized_persona = self.unauthorized_sheet.primary_persona
        self.unauthorized_tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.unauthorized_sheet)
        )

        # Create the vault
        self.vault_kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.VAULT,
        )
        self.vault_instance = RoomFeatureInstanceFactory(
            room_profile=self.room_profile,
            feature_kind=self.vault_kind,
            level=1,
        )
        self.vault = VaultDetails.objects.create(
            feature_instance=self.vault_instance,
            founder_persona=self.founder_persona,
            max_items=VAULT_MAX_ITEMS_PER_LEVEL,
        )

        self.founder_state = CharacterState(self.founder, context=MagicMock())
        self.authorized_state = CharacterState(self.authorized, context=MagicMock())
        self.unauthorized_state = CharacterState(self.unauthorized, context=MagicMock())

    def _room_item(self, *, holder: CharacterSheet | None = None) -> ItemState:
        """Create an unheld room item in the vault room."""
        item_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        item_obj.location = self.room
        item_obj.save()
        instance = ItemInstanceFactory(game_object=item_obj, holder_character_sheet=holder)
        return ItemState(instance, context=MagicMock())

    def _held_item(self, holder: CharacterSheet) -> ItemState:
        """Create an item held by a character."""
        item_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        item_obj.location = holder.character
        item_obj.save()
        instance = ItemInstanceFactory(game_object=item_obj, holder_character_sheet=holder)
        return ItemState(instance, context=MagicMock())


class VaultLookupTests(VaultTestCase):
    """Tests for vault_for_location, vault_for_room, has_vault_access."""

    def test_vault_for_location_finds_vault(self) -> None:
        vault = vault_for_location(self.room)
        self.assertIsNotNone(vault)
        self.assertEqual(vault.founder_persona, self.founder_persona)

    def test_vault_for_room_finds_vault(self) -> None:
        vault = vault_for_room(self.room_profile)
        self.assertIsNotNone(vault)
        self.assertEqual(vault.founder_persona, self.founder_persona)

    def test_vault_for_location_no_vault(self) -> None:
        other_room = ObjectDBFactory(
            db_key="NoVaultRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.assertIsNone(vault_for_location(other_room))

    def test_has_vault_access_founder_implicit(self) -> None:
        self.assertTrue(has_vault_access(self.founder_persona, self.vault))

    def test_has_vault_access_unauthorized_denied(self) -> None:
        self.assertFalse(has_vault_access(self.unauthorized_persona, self.vault))

    def test_has_vault_access_authorized_persona(self) -> None:
        add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        self.assertTrue(has_vault_access(self.authorized_persona, self.vault))

    def test_has_vault_access_after_removal(self) -> None:
        add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        remove_vault_access(self.vault, holder_persona=self.authorized_persona)
        self.assertFalse(has_vault_access(self.authorized_persona, self.vault))


class VaultTakeGateTests(VaultTestCase):
    """Tests for _vault_denies and the take-gate integration."""

    def test_vault_denies_unauthorized_room_item(self) -> None:
        item_state = self._room_item()
        self.assertTrue(_vault_denies(self.unauthorized_sheet, item_state.instance))

    def test_vault_allows_founder_room_item(self) -> None:
        item_state = self._room_item()
        self.assertFalse(_vault_denies(self.founder_sheet, item_state.instance))

    def test_vault_allows_authorized_room_item(self) -> None:
        add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        item_state = self._room_item()
        self.assertFalse(_vault_denies(self.authorized_sheet, item_state.instance))

    def test_vault_does_not_gate_held_items(self) -> None:
        """Held items are governed by ownership, not the vault."""
        item_state = self._held_item(self.founder_sheet)
        self.assertFalse(_vault_denies(self.unauthorized_sheet, item_state.instance))

    def test_vault_denies_sheetless_actor(self) -> None:
        item_state = self._room_item()
        self.assertTrue(_vault_denies(None, item_state.instance))

    def test_unauthorized_pick_up_blocked(self) -> None:
        item_state = self._room_item()
        with self.assertRaises(VaultAccessDenied):
            pick_up(self.unauthorized_state, item_state)

    def test_authorized_pick_up_succeeds(self) -> None:
        add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        item_state = self._room_item()
        pick_up(self.authorized_state, item_state)
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, self.authorized)

    def test_founder_pick_up_succeeds(self) -> None:
        item_state = self._room_item()
        pick_up(self.founder_state, item_state)
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, self.founder)


class VaultStealConsentTests(VaultTestCase):
    """Tests for the steal_permitted vault-founder consent integration."""

    def test_steal_permitted_unowned_vault_item_default_deny(self) -> None:
        """Without founder consent, steal from vault is denied."""
        item_state = self._room_item()
        # Founder has default-deny (ALLOWLIST) consent — no whitelist entry for thief.
        pref = set_social_consent_preference(self.founder_tenure, allow_social_actions=True)
        set_social_consent_category_rule(pref, theft_category(), ConsentMode.ALLOWLIST)
        result = steal_permitted(self.unauthorized_sheet, item_state.instance)
        self.assertFalse(result)

    def test_steal_permitted_unowned_vault_item_with_consent(self) -> None:
        """With founder consent (EVERYONE), steal from vault is allowed."""
        pref = set_social_consent_preference(self.founder_tenure, allow_social_actions=True)
        set_social_consent_category_rule(pref, theft_category(), ConsentMode.EVERYONE)
        item_state = self._room_item()
        result = steal_permitted(self.unauthorized_sheet, item_state.instance)
        self.assertTrue(result)

    def test_steal_from_vault_creates_ownership_event(self) -> None:
        """Stealing from a vault with consent creates an OwnershipEvent(STOLEN)."""
        pref = set_social_consent_preference(self.founder_tenure, allow_social_actions=True)
        set_social_consent_category_rule(pref, theft_category(), ConsentMode.EVERYONE)
        item_state = self._room_item()
        steal(self.unauthorized_state, item_state)
        event = OwnershipEvent.objects.filter(
            item_instance=item_state.instance,
            event_type=OwnershipEventType.STOLEN,
        )
        self.assertTrue(event.exists())


class VaultDropTests(VaultTestCase):
    """Tests for drop integration — deposit clearing + capacity."""

    def test_drop_into_vault_clears_ownership(self) -> None:
        """Dropping an item into a vault room clears holder_character_sheet."""
        item_state = self._held_item(self.founder_sheet)
        drop(self.founder_state, item_state)
        item_state.instance.refresh_from_db()
        self.assertIsNone(item_state.instance.holder_character_sheet)

    def test_drop_into_non_vault_retains_ownership(self) -> None:
        """Dropping an item into a non-vault room retains holder_character_sheet."""
        other_room = ObjectDBFactory(
            db_key="PlainRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.founder.location = other_room
        self.founder.save()
        item_state = self._held_item(self.founder_sheet)
        drop(self.founder_state, item_state)
        item_state.instance.refresh_from_db()
        self.assertEqual(item_state.instance.holder_character_sheet, self.founder_sheet)

    def test_drop_at_capacity_raises_vault_full(self) -> None:
        """Dropping into a full vault raises VaultFull."""
        # Set max_items to 1 and place one unheld item in the room.
        self.vault.max_items = 1
        self.vault.save(update_fields=["max_items"])
        self._room_item()  # fills the vault
        item_state = self._held_item(self.founder_sheet)
        with self.assertRaises(VaultFull):
            drop(self.founder_state, item_state)

    def test_vault_capacity_remaining(self) -> None:
        self.assertEqual(vault_capacity_remaining(self.vault), VAULT_MAX_ITEMS_PER_LEVEL)
        self._room_item()
        self.assertEqual(vault_capacity_remaining(self.vault), VAULT_MAX_ITEMS_PER_LEVEL - 1)


class VaultAccessListTests(VaultTestCase):
    """Tests for add/remove/list vault access entries."""

    def test_add_persona_access(self) -> None:
        entry = add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        self.assertEqual(entry.holder_persona, self.authorized_persona)
        self.assertEqual(entry.added_by, self.founder_persona)

    def test_add_duplicate_persona_idempotent(self) -> None:
        """Adding the same persona twice doesn't create a duplicate (unique constraint)."""
        add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        # Second add should not create a duplicate row.
        add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        count = VaultAccessEntry.objects.filter(
            vault_details=self.vault, holder_persona=self.authorized_persona
        ).count()
        self.assertEqual(count, 1)

    def test_remove_persona_access(self) -> None:
        add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        count = remove_vault_access(self.vault, holder_persona=self.authorized_persona)
        self.assertEqual(count, 1)
        self.assertFalse(has_vault_access(self.authorized_persona, self.vault))

    def test_remove_nonexistent_returns_zero(self) -> None:
        count = remove_vault_access(self.vault, holder_persona=self.authorized_persona)
        self.assertEqual(count, 0)

    def test_list_vault_access(self) -> None:
        add_vault_access(
            self.vault,
            holder_persona=self.authorized_persona,
            added_by=self.founder_persona,
        )
        entries = list_vault_access(self.vault)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().holder_persona, self.authorized_persona)


class VaultProgressionTests(VaultTestCase):
    """Tests for handle_vault_progression."""

    def test_handle_vault_progression_creates_vault_details(self) -> None:
        from world.projects.factories import ProjectFactory
        from world.room_features.factories import RoomFeatureProgressionDetailsFactory

        # Use a fresh room so we don't collide with the existing vault instance.
        fresh_room = ObjectDBFactory(
            db_key="FreshVaultRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        fresh_profile = RoomProfileFactory(objectdb=fresh_room)

        project = ProjectFactory(owner_persona=self.founder_persona)
        RoomFeatureProgressionDetailsFactory(
            project=project,
            target_room_profile=fresh_profile,
            target_feature_kind=self.vault_kind,
            target_level=2,
        )
        handle_vault_progression(project, target_level=2)
        instance = (
            RoomFeatureInstance.objects.filter(
                room_profile=fresh_profile,
                feature_kind=self.vault_kind,
            )
            .active()
            .first()
        )
        self.assertIsNotNone(instance)
        vault = VaultDetails.objects.filter(feature_instance=instance).first()
        self.assertIsNotNone(vault)
        self.assertEqual(vault.founder_persona, self.founder_persona)
        self.assertEqual(vault.max_items, 2 * VAULT_MAX_ITEMS_PER_LEVEL)
