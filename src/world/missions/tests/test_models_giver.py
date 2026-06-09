"""Tests for the MissionGiver model (post-#686 trigger-only shape).

NPC-mediated mission givers migrated to ``NPCRole`` + ``NPCServiceOffer``
per #686. This file covers what's left: ``MissionGiver`` for the two
trigger-based kinds (ROOM_TRIGGER / ENVIRONMENTAL_DETAIL). Their dispatch
design lands with the trigger followup.

Mission-giver cooldown migrated to ``NPCRoleCooldown``; the offering
through-model is replaced by ``MissionOfferDetails`` (catalog row on the
``NPCServiceOffer``).
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.missions.constants import GiverKind
from world.missions.factories import MissionGiverFactory
from world.missions.models import MissionGiver
from world.societies.factories import OrganizationFactory


def _make_room():
    """Create an Evennia Room ObjectDB for ROOM_TRIGGER-kind targets."""
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


def _make_npc():
    """Create a Character-typeclass ObjectDB for NPC-kind targets."""
    return CharacterFactory()


def _make_detail():
    """Create a plain Object-typeclass ObjectDB for ENVIRONMENTAL_DETAIL targets.

    Default ObjectDBFactory uses ``typeclasses.objects.Object`` which is
    the right base for examinable items / room details (anything that is
    NOT a Character/Room/Exit).
    """
    return ObjectDBFactory()


def _make_exit():
    """Create an Exit-typeclass ObjectDB (used in negative ENV_DETAIL tests)."""
    return ObjectDBFactory(db_typeclass_path="typeclasses.exits.Exit")


class MissionGiverModelTests(TestCase):
    """MissionGiver: name, optional target/org, M2M to templates, is_active."""

    def test_create_minimal_giver(self) -> None:
        # Bare factory: ROOM_TRIGGER + target=None — a drafty, anchorless
        # giver. clean() permits this (loose-validation policy).
        giver = MissionGiverFactory()
        self.assertTrue(giver.is_active)
        self.assertIsNone(giver.target)
        self.assertIsNone(giver.org)

    def test_giver_with_target_and_org(self) -> None:
        room = _make_room()
        org = OrganizationFactory()
        giver = MissionGiverFactory(target=room, org=org, name="Guild Hall")
        self.assertEqual(giver.target, room)
        self.assertEqual(giver.org, org)
        self.assertEqual(str(giver), "Guild Hall")

    def test_inactive_giver(self) -> None:
        giver = MissionGiverFactory(is_active=False)
        self.assertFalse(giver.is_active)

    def test_target_set_null_on_delete(self) -> None:
        room = _make_room()
        giver = MissionGiverFactory(target=room)
        room.delete()
        # SET_NULL nulls the column at the DB level; read the persisted value
        # directly (SharedMemoryModel's identity map otherwise hands back the
        # cached in-memory FK — see test_models_instance for the same pattern).
        target_id = (
            MissionGiver.objects.filter(pk=giver.pk).values_list("target_id", flat=True).first()
        )
        self.assertIsNone(target_id)

    def test_org_set_null_on_delete(self) -> None:
        org = OrganizationFactory()
        giver = MissionGiverFactory(org=org)
        org.delete()
        org_id = MissionGiver.objects.filter(pk=giver.pk).values_list("org_id", flat=True).first()
        self.assertIsNone(org_id)


class MissionGiverKindTests(TestCase):
    """giver_kind discriminator + ``target`` typeclass validation.

    The schema is a single ``target = FK(ObjectDB)``; ``giver_kind`` says
    how to interpret it and ``clean()`` enforces the typeclass match
    when target is set. Validation is intentionally loose for drafty
    (target-less) rows — a giver authored without its target passes
    clean() but fails is_publishable.
    """

    # ---- happy paths: matching typeclass for each kind -------------------

    def test_default_kind_is_room_trigger(self) -> None:
        # Bare MissionGiverFactory() keeps existing callsites valid:
        # ROOM_TRIGGER + target=None is a valid (drafty) shape.
        giver = MissionGiverFactory()
        self.assertEqual(giver.giver_kind, GiverKind.ROOM_TRIGGER)
        self.assertIsNone(giver.target)

    def test_environmental_detail_kind_with_object_target_round_trips(self) -> None:
        detail = _make_detail()
        giver = MissionGiverFactory(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            target=detail,
        )
        self.assertEqual(giver.giver_kind, GiverKind.ENVIRONMENTAL_DETAIL)
        self.assertEqual(giver.target, detail)

    def test_room_trigger_with_room_target_round_trips(self) -> None:
        room = _make_room()
        giver = MissionGiverFactory(giver_kind=GiverKind.ROOM_TRIGGER, target=room)
        self.assertEqual(giver.giver_kind, GiverKind.ROOM_TRIGGER)
        self.assertEqual(giver.target, room)

    # ---- negative: wrong typeclass for the chosen kind -------------------

    def test_room_trigger_rejects_character_target(self) -> None:
        npc = _make_npc()
        giver = MissionGiverFactory.build(giver_kind=GiverKind.ROOM_TRIGGER, target=npc)
        with self.assertRaises(ValidationError):
            giver.full_clean()

    def test_environmental_detail_rejects_character_target(self) -> None:
        npc = _make_npc()
        giver = MissionGiverFactory.build(giver_kind=GiverKind.ENVIRONMENTAL_DETAIL, target=npc)
        with self.assertRaises(ValidationError):
            giver.full_clean()

    def test_environmental_detail_rejects_room_target(self) -> None:
        room = _make_room()
        giver = MissionGiverFactory.build(giver_kind=GiverKind.ENVIRONMENTAL_DETAIL, target=room)
        with self.assertRaises(ValidationError):
            giver.full_clean()

    def test_environmental_detail_rejects_exit_target(self) -> None:
        exit_obj = _make_exit()
        giver = MissionGiverFactory.build(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL, target=exit_obj
        )
        with self.assertRaises(ValidationError):
            giver.full_clean()

    def test_save_enforces_typeclass_invariant(self) -> None:
        # clean() runs on the real factory/create write path (regression I1).
        npc = _make_npc()
        with self.assertRaises(ValidationError):
            MissionGiverFactory(giver_kind=GiverKind.ROOM_TRIGGER, target=npc)


class MissionGiverIsPublishableTests(TestCase):
    """is_publishable: True iff ``target`` is set.

    Drafty givers (target unset) pass clean() at the model layer but
    fail is_publishable — the authoring UI / admin surface uses this
    as the gate before opening a template up (flipping
    ``MissionTemplate.visibility`` to OPEN, #870), and as a
    'needs-work' signal. Runtime enforcement in offer_missions is
    deferred to Phase D.
    """

    def test_room_trigger_publishable_when_target_set(self) -> None:
        room = _make_room()
        giver = MissionGiverFactory(giver_kind=GiverKind.ROOM_TRIGGER, target=room)
        self.assertTrue(giver.is_publishable)

    def test_room_trigger_drafty_when_no_target(self) -> None:
        # Factory default: ROOM_TRIGGER + target=None.
        giver = MissionGiverFactory()
        self.assertEqual(giver.giver_kind, GiverKind.ROOM_TRIGGER)
        self.assertIsNone(giver.target)
        self.assertFalse(giver.is_publishable)

    def test_environmental_detail_publishable_when_target_set(self) -> None:
        detail = _make_detail()
        giver = MissionGiverFactory(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            target=detail,
        )
        self.assertTrue(giver.is_publishable)

    def test_environmental_detail_drafty_when_no_target(self) -> None:
        giver = MissionGiverFactory(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            target=None,
        )
        self.assertFalse(giver.is_publishable)

    def test_is_publishable_reflects_mutation(self) -> None:
        # Plain @property (not cached_property) — re-computes each access so
        # SharedMemoryModel instance reuse doesn't freeze a stale value.
        giver = MissionGiverFactory()
        self.assertFalse(giver.is_publishable)
        giver.target = _make_room()
        giver.save()
        self.assertTrue(giver.is_publishable)
