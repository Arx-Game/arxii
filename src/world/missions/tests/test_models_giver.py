"""Tests for the Phase-5a MissionGiver + MissionGiverCooldown models.

A ``MissionGiver`` is an abstracted offer point (location/NPC/org desk)
that publishes a curated set of ``MissionTemplate`` rows; characters
draw available templates from a giver (see ``services.availability``).
A ``MissionGiverCooldown`` records when a given (giver, character) pair
becomes available again after an accept (the design §10 "contractual
consequence is the contract-holder's alone" cooldown).
"""

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.missions.factories import (
    MissionGiverCooldownFactory,
    MissionGiverFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionGiver, MissionGiverCooldown
from world.societies.factories import OrganizationFactory


def _make_room():
    """Create an Evennia Room ObjectDB for tests (no dedicated RoomFactory)."""
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


class MissionGiverModelTests(TestCase):
    """MissionGiver: name, optional location/org, M2M to templates, is_active."""

    def test_create_minimal_giver(self) -> None:
        giver = MissionGiverFactory()
        self.assertTrue(giver.is_active)
        self.assertIsNone(giver.location)
        self.assertIsNone(giver.org)
        self.assertEqual(list(giver.templates.all()), [])

    def test_giver_with_location_and_org(self) -> None:
        room = _make_room()
        org = OrganizationFactory()
        giver = MissionGiverFactory(location=room, org=org, name="Guild Hall")
        self.assertEqual(giver.location, room)
        self.assertEqual(giver.org, org)
        self.assertEqual(str(giver), "Guild Hall")

    def test_templates_m2m_reverse_relation(self) -> None:
        giver = MissionGiverFactory()
        tmpl_a = MissionTemplateFactory(slug="g-tmpl-a")
        tmpl_b = MissionTemplateFactory(slug="g-tmpl-b")
        giver.templates.add(tmpl_a, tmpl_b)
        self.assertEqual(set(giver.templates.all()), {tmpl_a, tmpl_b})
        # reverse: templates -> givers
        self.assertIn(giver, tmpl_a.givers.all())

    def test_inactive_giver(self) -> None:
        giver = MissionGiverFactory(is_active=False)
        self.assertFalse(giver.is_active)

    def test_location_set_null_on_delete(self) -> None:
        room = _make_room()
        giver = MissionGiverFactory(location=room)
        room.delete()
        # SET_NULL nulls the column at the DB level; read the persisted value
        # directly (SharedMemoryModel's identity map otherwise hands back the
        # cached in-memory FK — see test_models_instance for the same pattern).
        location_id = (
            MissionGiver.objects.filter(pk=giver.pk).values_list("location_id", flat=True).first()
        )
        self.assertIsNone(location_id)

    def test_org_set_null_on_delete(self) -> None:
        org = OrganizationFactory()
        giver = MissionGiverFactory(org=org)
        org.delete()
        org_id = MissionGiver.objects.filter(pk=giver.pk).values_list("org_id", flat=True).first()
        self.assertIsNone(org_id)


class MissionGiverCooldownModelTests(TestCase):
    """MissionGiverCooldown: (giver, character) unique; available_at gated."""

    def test_create_cooldown(self) -> None:
        giver = MissionGiverFactory()
        character = CharacterFactory()
        cd = MissionGiverCooldownFactory(giver=giver, character=character)
        self.assertEqual(cd.giver, giver)
        self.assertEqual(cd.character, character)
        self.assertIsNotNone(cd.available_at)

    def test_giver_character_uniqueness(self) -> None:
        giver = MissionGiverFactory()
        character = CharacterFactory()
        MissionGiverCooldownFactory(giver=giver, character=character)
        with self.assertRaises(IntegrityError):
            MissionGiverCooldown.objects.create(
                giver=giver,
                character=character,
                available_at=timezone.now() + timedelta(days=1),
            )

    def test_different_giver_same_character_allowed(self) -> None:
        character = CharacterFactory()
        g1 = MissionGiverFactory(name="g1")
        g2 = MissionGiverFactory(name="g2")
        MissionGiverCooldownFactory(giver=g1, character=character)
        MissionGiverCooldownFactory(giver=g2, character=character)
        self.assertEqual(
            MissionGiverCooldown.objects.filter(character=character).count(),
            2,
        )

    def test_giver_cascade_deletes_cooldowns(self) -> None:
        giver = MissionGiverFactory()
        MissionGiverCooldownFactory(giver=giver)
        MissionGiverCooldownFactory(giver=giver)
        giver.delete()
        self.assertEqual(MissionGiverCooldown.objects.count(), 0)
        # Giver itself is gone.
        self.assertFalse(MissionGiver.objects.filter(pk=giver.pk).exists())
