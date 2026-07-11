"""Tests for portal travel anchors (#2222 Task 1)."""

from __future__ import annotations

from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.magic.factories import PortalAnchorFactory, PortalAnchorKindFactory, TechniqueFactory
from world.magic.models import PortalAnchor, PortalAnchorKind


class PortalAnchorKindTests(TestCase):
    def test_str(self) -> None:
        kind = PortalAnchorKindFactory(name="Mirror")
        self.assertEqual(str(kind), "Mirror")

    def test_default_verbs(self) -> None:
        kind = PortalAnchorKindFactory()
        self.assertEqual(kind.arrival_verb, "steps out of")
        self.assertEqual(kind.departure_verb, "steps into")

    def test_name_unique(self) -> None:
        PortalAnchorKindFactory(name="Mirror")
        with self.assertRaises(IntegrityError):
            PortalAnchorKind.objects.create(name="Mirror")


class PortalAnchorQuerySetTests(TestCase):
    def test_active_excludes_dissolved(self) -> None:
        active_anchor = PortalAnchorFactory()
        dissolved_anchor = PortalAnchorFactory()
        dissolved_anchor.dissolved_at = dissolved_anchor.installed_at
        dissolved_anchor.save()

        active_ids = set(PortalAnchor.objects.active().values_list("id", flat=True))

        self.assertIn(active_anchor.id, active_ids)
        self.assertNotIn(dissolved_anchor.id, active_ids)

    def test_active_includes_undissolved(self) -> None:
        anchor = PortalAnchorFactory()
        self.assertIsNone(anchor.dissolved_at)
        self.assertIn(anchor.id, PortalAnchor.objects.active().values_list("id", flat=True))


class PortalAnchorConstraintTests(TestCase):
    def test_duplicate_active_room_kind_rejected(self) -> None:
        room = RoomProfileFactory()
        kind = PortalAnchorKindFactory()
        PortalAnchorFactory(room_profile=room, kind=kind)

        with self.assertRaises(IntegrityError):
            PortalAnchor.objects.create(room_profile=room, kind=kind, name="a second anchor")

    def test_dissolved_row_allows_fresh_install_of_same_kind(self) -> None:
        room = RoomProfileFactory()
        kind = PortalAnchorKindFactory()
        first = PortalAnchorFactory(room_profile=room, kind=kind)
        first.dissolved_at = first.installed_at
        first.save()

        second = PortalAnchor.objects.create(room_profile=room, kind=kind, name="a fresh anchor")

        self.assertIsNone(second.dissolved_at)
        self.assertNotEqual(first.id, second.id)

    def test_different_kind_same_room_allowed(self) -> None:
        room = RoomProfileFactory()
        PortalAnchorFactory(room_profile=room, kind=PortalAnchorKindFactory())
        # A different kind in the same room is not blocked by the constraint.
        PortalAnchorFactory(room_profile=room, kind=PortalAnchorKindFactory())


class PortalAnchorStrTests(TestCase):
    def test_str(self) -> None:
        kind = PortalAnchorKindFactory(name="Mirror")
        anchor = PortalAnchorFactory(kind=kind, name="a tall silvered mirror")
        result = str(anchor)
        self.assertIn("a tall silvered mirror", result)
        self.assertIn("Mirror", result)


class TechniqueTravelAnchorKindTests(TestCase):
    def test_default_is_none(self) -> None:
        technique = TechniqueFactory()
        self.assertIsNone(technique.travel_anchor_kind)

    def test_can_be_set_to_a_portal_anchor_kind(self) -> None:
        kind = PortalAnchorKindFactory(name="Mirror")
        technique = TechniqueFactory(travel_anchor_kind=kind)
        technique.refresh_from_db()
        self.assertEqual(technique.travel_anchor_kind, kind)

    def test_protected_on_delete(self) -> None:
        kind = PortalAnchorKindFactory()
        TechniqueFactory(travel_anchor_kind=kind)
        with self.assertRaises(ProtectedError):
            kind.delete()
