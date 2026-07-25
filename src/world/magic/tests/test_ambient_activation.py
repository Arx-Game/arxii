"""Tests for _anchor_ambiently_active — the passive sibling of _anchor_in_action (#2708).

The pull predicate lets a player ASSERT involvement because a pull is paid for. A free
passive contribution must be demonstrable, so this predicate is strictly stricter on the
assertion-based arms (GIFT, RELATIONSHIP_*) and identical on the arms that already test
real state (COVENANT_ROLE).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    make_engaged_member,
)
from world.items.factories import (
    EquippedItemFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    MantleFactory,
)
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.factories import (
    FacetFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
)
from world.magic.models import SanctumDetails, SanctumOwnerMode, Thread
from world.magic.services.resonance import _anchor_ambiently_active, _anchor_in_action
from world.magic.types.pull import PullActionContext
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipTrackProgressFactory,
)
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.societies.factories import OrganizationFactory


def _room() -> object:
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


class GiftArmTests(TestCase):
    """GIFT is always-in-action for a pull, but ambient only for its own gift."""

    def setUp(self) -> None:
        self.gift = GiftFactory()
        self.technique = TechniqueFactory(gift=self.gift)
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def _gift_thread(self) -> Thread:
        return ThreadFactory(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            target_trait=None,
        )

    def test_pull_predicate_accepts_gift_unconditionally(self) -> None:
        """Baseline: documents the behaviour we are deliberately tightening."""
        thread = self._gift_thread()
        self.assertTrue(_anchor_in_action(thread, PullActionContext()))

    def test_ambient_rejects_gift_outside_its_own_action(self) -> None:
        """The pyromancer-climbing case: a fire-gift thread must not raise limb_use."""
        thread = self._gift_thread()
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=self.character))

    def test_ambient_accepts_gift_when_action_uses_that_gift(self) -> None:
        thread = self._gift_thread()
        ctx = PullActionContext(involved_techniques=(self.technique.pk,))
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=self.character))


class TraitArmTests(TestCase):
    """TRAIT was already state-tested by _anchor_in_action; ambient behaves identically."""

    def test_ambient_accepts_trait_in_involved_traits(self) -> None:
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=sheet)  # default kind is TRAIT
        ctx = PullActionContext(involved_traits=(thread.target_trait_id,))
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=sheet.character))

    def test_ambient_rejects_trait_with_empty_context(self) -> None:
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=sheet)
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=sheet.character))


class TechniqueArmTests(TestCase):
    """TECHNIQUE was already state-tested by _anchor_in_action; ambient behaves identically."""

    def test_ambient_accepts_technique_in_involved_techniques(self) -> None:
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=sheet, as_technique_thread=True)
        ctx = PullActionContext(involved_techniques=(thread.target_technique_id,))
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=sheet.character))

    def test_ambient_rejects_different_technique(self) -> None:
        sheet = CharacterSheetFactory()
        thread = ThreadFactory(owner=sheet, as_technique_thread=True)
        other_technique = TechniqueFactory()
        ctx = PullActionContext(involved_techniques=(other_technique.pk,))
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=sheet.character))


class CovenantRoleArmTests(TestCase):
    """COVENANT_ROLE already tests real state; ambient delegates straight to the pull predicate."""

    def test_ambient_accepts_engaged_role(self) -> None:
        m = make_engaged_member()
        thread = ThreadFactory(
            owner=m.character_sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=m.covenant_role,
            target_trait=None,
        )
        ctx = PullActionContext()
        character = m.character_sheet.character
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=character))

    def test_ambient_rejects_unengaged_role(self) -> None:
        sheet = CharacterSheetFactory()
        cov = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov, covenant_role=role)
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=sheet.character))


class SanctumArmTests(TestCase):
    """SANCTUM: ambient requires the character's actual location, not an asserted object id."""

    def _make_sanctum_thread(self) -> tuple[Thread, object, object]:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        room_profile = RoomProfileFactory()
        sanctum_kind = RoomFeatureKindFactory(
            service_strategy=RoomFeatureServiceStrategy.SANCTUM,
        )
        instance = RoomFeatureInstanceFactory(
            room_profile=room_profile,
            feature_kind=sanctum_kind,
        )
        sanctum = SanctumDetails.objects.create(
            feature_instance=instance,
            resonance_type=resonance,
            owner_mode=SanctumOwnerMode.PERSONAL,
        )
        thread = Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.SANCTUM,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.HELPER,
        )
        return thread, sheet.character, room_profile.objectdb

    def test_ambient_accepts_character_physically_in_sanctum_room(self) -> None:
        thread, character, room = self._make_sanctum_thread()
        character.location = room
        ctx = PullActionContext()
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=character))

    def test_ambient_rejects_character_elsewhere(self) -> None:
        thread, character, _room_obj = self._make_sanctum_thread()
        character.location = _room()
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=character))


class RelationshipTrackArmTests(TestCase):
    """RELATIONSHIP_TRACK: ambient requires the other party physically present."""

    def _make_track_thread(self) -> tuple[Thread, object, object]:
        sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        relationship = CharacterRelationshipFactory(source=sheet, target=target_sheet)
        progress = RelationshipTrackProgressFactory(relationship=relationship)
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target_relationship_track=progress,
            target_trait=None,
        )
        return thread, sheet.character, target_sheet.character

    def test_ambient_accepts_target_present_in_same_room(self) -> None:
        thread, character, target_character = self._make_track_thread()
        room = _room()
        character.location = room
        target_character.location = room
        ctx = PullActionContext()
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=character))

    def test_ambient_rejects_target_elsewhere(self) -> None:
        thread, character, target_character = self._make_track_thread()
        character.location = _room()
        target_character.location = _room()
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=character))


class RelationshipCapstoneArmTests(TestCase):
    """RELATIONSHIP_CAPSTONE: same presence rule, reached via target_capstone.relationship."""

    def _make_capstone_thread(self) -> tuple[Thread, object, object]:
        sheet = CharacterSheetFactory()
        target_sheet = CharacterSheetFactory()
        relationship = CharacterRelationshipFactory(source=sheet, target=target_sheet)
        capstone = RelationshipCapstoneFactory(relationship=relationship)
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=capstone,
            target_trait=None,
        )
        return thread, sheet.character, target_sheet.character

    def test_ambient_accepts_target_present_in_same_room(self) -> None:
        thread, character, target_character = self._make_capstone_thread()
        room = _room()
        character.location = room
        target_character.location = room
        ctx = PullActionContext()
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=character))

    def test_ambient_rejects_target_elsewhere(self) -> None:
        thread, character, target_character = self._make_capstone_thread()
        character.location = _room()
        target_character.location = _room()
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=character))


class FacetArmTests(TestCase):
    """FACET: ambient requires an equipped item actually carrying the facet."""

    def _make_facet_thread(self) -> tuple[Thread, object, object, object]:
        sheet = CharacterSheetFactory()
        facet = FacetFactory()
        thread = Thread.objects.create(
            owner=sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.FACET,
            target_facet=facet,
        )
        return thread, sheet, sheet.character, facet

    def test_ambient_accepts_equipped_facet(self) -> None:
        thread, sheet, character, facet = self._make_facet_thread()
        item_instance = ItemInstanceFactory()
        ItemFacetFactory(item_instance=item_instance, facet=facet)
        # EquippedItem.character FKs to CharacterSheet (not ObjectDB) — pass the sheet.
        EquippedItemFactory(character=sheet, item_instance=item_instance)
        ctx = PullActionContext()
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=character))

    def test_ambient_rejects_unequipped_facet(self) -> None:
        thread, _sheet, character, _facet = self._make_facet_thread()
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=character))


class MantleArmTests(TestCase):
    """MANTLE: ambient requires the mantle's ItemInstance to actually be equipped."""

    def _make_mantle_thread(self) -> tuple[Thread, object, object, object]:
        sheet = CharacterSheetFactory()
        mantle = MantleFactory()
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.MANTLE,
            target_mantle=mantle,
            target_trait=None,
        )
        return thread, sheet, sheet.character, mantle

    def test_ambient_accepts_worn_mantle(self) -> None:
        thread, sheet, character, mantle = self._make_mantle_thread()
        # EquippedItem.character FKs to CharacterSheet (not ObjectDB) — pass the sheet.
        EquippedItemFactory(character=sheet, item_instance=mantle.item_instance)
        ctx = PullActionContext()
        self.assertTrue(_anchor_ambiently_active(thread, ctx, character=character))

    def test_ambient_rejects_unworn_mantle(self) -> None:
        thread, _sheet, character, _mantle = self._make_mantle_thread()
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=character))


class OrganizationArmTests(TestCase):
    """ORGANIZATION always returns False — no marker exists yet to test real state (#2708)."""

    def test_ambient_always_rejects_organization(self) -> None:
        sheet = CharacterSheetFactory()
        org = OrganizationFactory()
        thread = ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.ORGANIZATION,
            target_organization=org,
            target_trait=None,
        )
        ctx = PullActionContext()
        self.assertFalse(_anchor_ambiently_active(thread, ctx, character=sheet.character))
