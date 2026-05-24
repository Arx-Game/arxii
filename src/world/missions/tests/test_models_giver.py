"""Tests for the MissionGiver + MissionGiverStanding + MissionGiverOffering models.

A ``MissionGiver`` is an abstracted offer point (Room/NPC/detail) bound to
one Evennia ``target`` whose typeclass matches ``giver_kind``. Characters
draw available templates from a giver (see ``services.availability``).
A ``MissionGiverStanding`` records (per giver, per character) both the
cooldown available_at and an affection integer; cooldown is set by
accept_mission (design §10 — contractual consequence is the
contract-holder's alone), affection is moved by future flirt/seduce
gameplay against the NPC.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.missions.constants import GiverKind
from world.missions.factories import (
    MissionGiverFactory,
    MissionGiverOfferingFactory,
    MissionGiverStandingFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionGiver, MissionGiverOffering, MissionGiverStanding
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
        self.assertEqual(list(giver.templates.all()), [])

    def test_giver_with_target_and_org(self) -> None:
        room = _make_room()
        org = OrganizationFactory()
        giver = MissionGiverFactory(target=room, org=org, name="Guild Hall")
        self.assertEqual(giver.target, room)
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


class MissionGiverStandingModelTests(TestCase):
    """MissionGiverStanding: (giver, character) unique; cooldown + affection."""

    def test_create_standing(self) -> None:
        giver = MissionGiverFactory()
        character = CharacterFactory()
        standing = MissionGiverStandingFactory(giver=giver, character=character)
        self.assertEqual(standing.giver, giver)
        self.assertEqual(standing.character, character)
        self.assertIsNotNone(standing.available_at)

    def test_affection_defaults_to_zero(self) -> None:
        standing = MissionGiverStandingFactory()
        self.assertEqual(standing.affection, 0)

    def test_affection_round_trips(self) -> None:
        standing = MissionGiverStandingFactory(affection=42)
        standing.refresh_from_db()
        self.assertEqual(standing.affection, 42)

    def test_affection_accepts_negative(self) -> None:
        # IntegerField — affection can swing negative for disliked characters.
        standing = MissionGiverStandingFactory(affection=-5)
        standing.refresh_from_db()
        self.assertEqual(standing.affection, -5)

    def test_giver_character_uniqueness(self) -> None:
        giver = MissionGiverFactory()
        character = CharacterFactory()
        MissionGiverStandingFactory(giver=giver, character=character)
        with self.assertRaises(IntegrityError):
            MissionGiverStanding.objects.create(
                giver=giver,
                character=character,
                available_at=timezone.now() + timedelta(days=1),
            )

    def test_different_giver_same_character_allowed(self) -> None:
        character = CharacterFactory()
        g1 = MissionGiverFactory(name="g1")
        g2 = MissionGiverFactory(name="g2")
        MissionGiverStandingFactory(giver=g1, character=character)
        MissionGiverStandingFactory(giver=g2, character=character)
        self.assertEqual(
            MissionGiverStanding.objects.filter(character=character).count(),
            2,
        )

    def test_giver_cascade_deletes_standings(self) -> None:
        giver = MissionGiverFactory()
        MissionGiverStandingFactory(giver=giver)
        MissionGiverStandingFactory(giver=giver)
        giver.delete()
        self.assertEqual(MissionGiverStanding.objects.count(), 0)
        # Giver itself is gone.
        self.assertFalse(MissionGiver.objects.filter(pk=giver.pk).exists())


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

    def test_npc_kind_with_character_target_round_trips(self) -> None:
        npc = _make_npc()
        giver = MissionGiverFactory(giver_kind=GiverKind.NPC, target=npc)
        self.assertEqual(giver.giver_kind, GiverKind.NPC)
        self.assertEqual(giver.target, npc)

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

    def test_npc_kind_rejects_room_target(self) -> None:
        room = _make_room()
        giver = MissionGiverFactory.build(giver_kind=GiverKind.NPC, target=room)
        with self.assertRaises(ValidationError):
            giver.full_clean()

    def test_npc_kind_rejects_plain_object_target(self) -> None:
        detail = _make_detail()
        giver = MissionGiverFactory.build(giver_kind=GiverKind.NPC, target=detail)
        with self.assertRaises(ValidationError):
            giver.full_clean()

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
        room = _make_room()
        with self.assertRaises(ValidationError):
            MissionGiverFactory(giver_kind=GiverKind.NPC, target=room)


class MissionGiverOfferingTests(TestCase):
    """Through-model: per-(giver, template) optional odds/requirements overrides."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.giver = MissionGiverFactory(name="offering-giver")
        cls.template = MissionTemplateFactory(slug="offering-tmpl")

    def test_offering_round_trips_with_overrides(self) -> None:
        offering = MissionGiverOfferingFactory(
            giver=self.giver,
            template=self.template,
            weight_override=5,
            requirements_override={"leaf": "has_distinction", "params": {"slug": "vip"}},
        )
        fetched = MissionGiverOffering.objects.get(pk=offering.pk)
        self.assertEqual(fetched.weight_override, 5)
        self.assertEqual(fetched.requirements_override["leaf"], "has_distinction")

    def test_offering_defaults_no_overrides(self) -> None:
        offering = MissionGiverOfferingFactory(giver=self.giver, template=self.template)
        self.assertIsNone(offering.weight_override)
        self.assertEqual(offering.requirements_override, {})

    def test_offering_unique_per_giver_template(self) -> None:
        MissionGiverOfferingFactory(giver=self.giver, template=self.template)
        with self.assertRaises(IntegrityError):
            MissionGiverOffering.objects.create(giver=self.giver, template=self.template)

    def test_templates_m2m_uses_through_model(self) -> None:
        # The M2M's .add() creates MissionGiverOffering rows transparently
        # because the through-model has no required fields beyond giver+template.
        self.giver.templates.add(self.template)
        offerings = list(
            MissionGiverOffering.objects.filter(giver=self.giver, template=self.template)
        )
        self.assertEqual(len(offerings), 1)
        self.assertIn(self.template, self.giver.templates.all())
        self.assertIn(self.giver, self.template.givers.all())

    def test_clean_rejects_zero_weight_override(self) -> None:
        # weight_override=0 would silently disable the offering at draw time
        # (select_weighted yields nothing for weight 0). clean() forbids it
        # so authors use null (= fall back to template.base_weight) or >=1.
        offering = MissionGiverOfferingFactory.build(
            giver=self.giver,
            template=self.template,
            weight_override=0,
        )
        with self.assertRaises(ValidationError):
            offering.full_clean()

    def test_save_enforces_weight_override_invariant(self) -> None:
        # clean() runs on the real factory/create write path (regression I1).
        with self.assertRaises(ValidationError):
            MissionGiverOfferingFactory(
                giver=self.giver,
                template=MissionTemplateFactory(slug="offering-save-tmpl"),
                weight_override=0,
            )


class MissionGiverIsPublishableTests(TestCase):
    """is_publishable: True iff ``target`` is set.

    Drafty givers (target unset) pass clean() at the model layer but
    fail is_publishable — the authoring UI / admin surface uses this
    as the gate before flipping a template from STAFF_ONLY to OPEN
    (Phase-B7 access_tier transition), and as a 'needs-work' signal.
    Runtime enforcement in offer_missions is deferred to Phase D.
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

    def test_npc_publishable_when_target_set(self) -> None:
        npc = _make_npc()
        giver = MissionGiverFactory(giver_kind=GiverKind.NPC, target=npc)
        self.assertTrue(giver.is_publishable)

    def test_npc_drafty_when_no_target(self) -> None:
        giver = MissionGiverFactory(giver_kind=GiverKind.NPC, target=None)
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
