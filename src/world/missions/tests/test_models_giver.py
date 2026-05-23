"""Tests for the MissionGiver + MissionGiverStanding + MissionGiverOffering models.

A ``MissionGiver`` is an abstracted offer point (location/NPC/org desk)
that publishes a curated set of ``MissionTemplate`` rows; characters
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
    """giver_kind discriminator (NPC / ENVIRONMENTAL_DETAIL / ROOM_TRIGGER).

    Validation is intentionally loose: clean() enforces consistency (NPC
    kind permits an npc FK and forbids environmental_detail; ENVIRONMENTAL_
    DETAIL the reverse; ROOM_TRIGGER forbids both typed FKs) but does NOT
    require completeness. A giver authored without its kind-specific FK is
    a 'draft' that runtime offering simply doesn't surface.
    """

    def test_default_kind_is_room_trigger(self) -> None:
        # Bare MissionGiverFactory() keeps existing callsites valid:
        # ROOM_TRIGGER + everything else null is a valid (drafty) shape.
        giver = MissionGiverFactory()
        self.assertEqual(giver.giver_kind, GiverKind.ROOM_TRIGGER)
        self.assertIsNone(giver.npc)
        self.assertIsNone(giver.environmental_detail)

    def test_npc_kind_with_npc_round_trips(self) -> None:
        npc = ObjectDBFactory()
        giver = MissionGiverFactory(giver_kind=GiverKind.NPC, npc=npc)
        self.assertEqual(giver.giver_kind, GiverKind.NPC)
        self.assertEqual(giver.npc, npc)

    def test_environmental_detail_kind_with_detail_round_trips(self) -> None:
        detail = ObjectDBFactory()
        giver = MissionGiverFactory(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            environmental_detail=detail,
        )
        self.assertEqual(giver.giver_kind, GiverKind.ENVIRONMENTAL_DETAIL)
        self.assertEqual(giver.environmental_detail, detail)

    def test_room_trigger_with_location_round_trips(self) -> None:
        room = _make_room()
        giver = MissionGiverFactory(giver_kind=GiverKind.ROOM_TRIGGER, location=room)
        self.assertEqual(giver.giver_kind, GiverKind.ROOM_TRIGGER)
        self.assertEqual(giver.location, room)

    def test_npc_fk_forbidden_when_kind_is_not_npc(self) -> None:
        npc = ObjectDBFactory()
        giver = MissionGiverFactory.build(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            npc=npc,
        )
        with self.assertRaises(ValidationError):
            giver.full_clean()

    def test_environmental_detail_fk_forbidden_when_kind_is_not_detail(self) -> None:
        detail = ObjectDBFactory()
        giver = MissionGiverFactory.build(
            giver_kind=GiverKind.NPC,
            environmental_detail=detail,
        )
        with self.assertRaises(ValidationError):
            giver.full_clean()

    def test_room_trigger_kind_forbids_npc_and_detail(self) -> None:
        npc = ObjectDBFactory()
        giver = MissionGiverFactory.build(giver_kind=GiverKind.ROOM_TRIGGER, npc=npc)
        with self.assertRaises(ValidationError):
            giver.full_clean()

    def test_save_enforces_kind_invariants(self) -> None:
        # clean() runs on the real factory/create write path (regression I1).
        detail = ObjectDBFactory()
        with self.assertRaises(ValidationError):
            MissionGiverFactory(
                giver_kind=GiverKind.NPC,
                environmental_detail=detail,
            )


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
    """is_publishable: True iff the kind-specific target FK is set.

    Drafty givers (kind set, target unset) pass clean() at the model layer
    but fail is_publishable — the authoring UI / admin surface uses this
    as the gate before flipping a template from STAFF_ONLY to OPEN
    (Phase-B7 access_tier transition), and as a 'needs-work' signal.
    Runtime enforcement in offer_missions is deferred to Phase D.
    """

    def test_room_trigger_publishable_when_location_set(self) -> None:
        room = _make_room()
        giver = MissionGiverFactory(giver_kind=GiverKind.ROOM_TRIGGER, location=room)
        self.assertTrue(giver.is_publishable)

    def test_room_trigger_drafty_when_no_location(self) -> None:
        # Factory default: ROOM_TRIGGER + location=None.
        giver = MissionGiverFactory()
        self.assertEqual(giver.giver_kind, GiverKind.ROOM_TRIGGER)
        self.assertIsNone(giver.location)
        self.assertFalse(giver.is_publishable)

    def test_npc_publishable_when_npc_set(self) -> None:
        npc = ObjectDBFactory()
        giver = MissionGiverFactory(giver_kind=GiverKind.NPC, npc=npc)
        self.assertTrue(giver.is_publishable)

    def test_npc_drafty_when_no_npc(self) -> None:
        giver = MissionGiverFactory(giver_kind=GiverKind.NPC, npc=None)
        self.assertFalse(giver.is_publishable)

    def test_environmental_detail_publishable_when_detail_set(self) -> None:
        detail = ObjectDBFactory()
        giver = MissionGiverFactory(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            environmental_detail=detail,
        )
        self.assertTrue(giver.is_publishable)

    def test_environmental_detail_drafty_when_no_detail(self) -> None:
        giver = MissionGiverFactory(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            environmental_detail=None,
        )
        self.assertFalse(giver.is_publishable)

    def test_is_publishable_reflects_mutation(self) -> None:
        # Plain @property (not cached_property) — re-computes each access so
        # SharedMemoryModel instance reuse doesn't freeze a stale value.
        giver = MissionGiverFactory()
        self.assertFalse(giver.is_publishable)
        giver.location = _make_room()
        giver.save()
        self.assertTrue(giver.is_publishable)
