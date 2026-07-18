"""TagRoomResonanceAction / UntagRoomResonanceAction (#2036) + the widened
``IsRoomTenantPrerequisite`` (owner-OR-tenant standing) it shares with
``SetPrimaryHomeAction``.
"""

from django.test import TestCase

from actions.tests.room_test_helpers import character_in_room
from evennia_extensions.factories import RoomProfileFactory
from world.locations.constants import KeyType, LocationParentType
from world.locations.factories import LocationOwnershipFactory, LocationTenancyFactory
from world.locations.models import LocationValueModifier
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.services.gain import ROOM_RESONANCE_TAG_SOURCE


class TagRoomResonanceActionTests(TestCase):
    def setUp(self) -> None:
        from actions.definitions.locations import TagRoomResonanceAction

        self.action_cls = TagRoomResonanceAction
        self.room_profile = RoomProfileFactory()
        self.sheet, self.character = character_in_room(self.room_profile)
        self.resonance = ResonanceFactory()

    def _tag_row(self):
        return LocationValueModifier.objects.filter(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=self.resonance,
            source=ROOM_RESONANCE_TAG_SOURCE,
        )

    def test_owner_with_no_tenancy_row_can_tag_claimed_resonance(self) -> None:
        """The fold-in fix: a pure owner (no LocationTenancy row) can still tag."""
        LocationOwnershipFactory(
            on_room=True,
            room_profile=self.room_profile,
            holder_persona=self.sheet.primary_persona,
        )
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

        result = self.action_cls().run(actor=self.character, resonance_id=self.resonance.pk)

        self.assertTrue(result.success, result.message)
        self.assertTrue(self._tag_row().exists())

    def test_tenant_can_tag_claimed_resonance(self) -> None:
        LocationTenancyFactory(
            room_profile=self.room_profile,
            tenant_persona=self.sheet.primary_persona,
        )
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

        result = self.action_cls().run(actor=self.character, resonance_id=self.resonance.pk)

        self.assertTrue(result.success, result.message)
        self.assertTrue(self._tag_row().exists())

    def test_unclaimed_resonance_rejected(self) -> None:
        LocationOwnershipFactory(
            on_room=True,
            room_profile=self.room_profile,
            holder_persona=self.sheet.primary_persona,
        )
        # No CharacterResonance row — the resonance is not claimed.

        result = self.action_cls().run(actor=self.character, resonance_id=self.resonance.pk)

        self.assertFalse(result.success)
        self.assertIn("haven't claimed", result.message)
        self.assertFalse(self._tag_row().exists())

    def test_no_standing_rejected(self) -> None:
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

        result = self.action_cls().run(actor=self.character, resonance_id=self.resonance.pk)

        self.assertFalse(result.success)
        self.assertIn("no standing", result.message)
        self.assertFalse(self._tag_row().exists())

    def test_no_such_resonance(self) -> None:
        LocationOwnershipFactory(
            on_room=True,
            room_profile=self.room_profile,
            holder_persona=self.sheet.primary_persona,
        )

        result = self.action_cls().run(actor=self.character, resonance_id=999999)

        self.assertFalse(result.success)
        self.assertIn("No such resonance", result.message)


class SetPrimaryHomeActionOwnerStandingTests(TestCase):
    """Fold-in fix (Task 1 review): a pure room owner with no LocationTenancy row
    could not reach the org-standing service branch via the Action/telnet/web seam
    because ``IsRoomTenantPrerequisite`` only checked ``is_tenant``. Now widened to
    owner-OR-tenant — this proves the Action-level path, not just the service.
    """

    def test_owner_with_no_tenancy_row_can_declare_residence_via_action(self) -> None:
        from actions.definitions.locations import SetPrimaryHomeAction
        from world.locations.models import LocationTenancy

        room_profile = RoomProfileFactory()
        sheet, character = character_in_room(room_profile)
        LocationOwnershipFactory(
            on_room=True,
            room_profile=room_profile,
            holder_persona=sheet.primary_persona,
        )
        self.assertFalse(
            LocationTenancy.objects.filter(
                tenant_persona=sheet.primary_persona, room_profile=room_profile
            ).exists()
        )

        result = SetPrimaryHomeAction().run(actor=character)

        self.assertTrue(result.success, result.message)
        sheet.refresh_from_db()
        self.assertEqual(sheet.current_residence, room_profile)


class UntagRoomResonanceActionTests(TestCase):
    def setUp(self) -> None:
        from actions.definitions.locations import TagRoomResonanceAction, UntagRoomResonanceAction

        self.tag_action_cls = TagRoomResonanceAction
        self.action_cls = UntagRoomResonanceAction
        self.room_profile = RoomProfileFactory()
        self.sheet, self.character = character_in_room(self.room_profile)
        self.resonance = ResonanceFactory()
        LocationOwnershipFactory(
            on_room=True,
            room_profile=self.room_profile,
            holder_persona=self.sheet.primary_persona,
        )
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

    def _tag_row(self):
        return LocationValueModifier.objects.filter(
            parent_type=LocationParentType.ROOM,
            room_profile=self.room_profile,
            key_type=KeyType.RESONANCE,
            resonance=self.resonance,
            source=ROOM_RESONANCE_TAG_SOURCE,
        )

    def test_owner_untags_existing_row(self) -> None:
        self.tag_action_cls().run(actor=self.character, resonance_id=self.resonance.pk)
        self.assertTrue(self._tag_row().exists())

        result = self.action_cls().run(actor=self.character, resonance_id=self.resonance.pk)

        self.assertTrue(result.success, result.message)
        self.assertFalse(self._tag_row().exists())

    def test_untag_is_idempotent_when_no_row_exists(self) -> None:
        result = self.action_cls().run(actor=self.character, resonance_id=self.resonance.pk)
        self.assertTrue(result.success, result.message)

    def test_no_standing_rejected(self) -> None:
        _stranger_sheet, stranger = character_in_room(self.room_profile)

        result = self.action_cls().run(actor=stranger, resonance_id=self.resonance.pk)

        self.assertFalse(result.success)
        self.assertIn("no standing", result.message)
