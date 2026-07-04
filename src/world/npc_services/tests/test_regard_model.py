"""Tests for the NpcRegard model — discriminator validation + uniqueness."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.npc_services.constants import RegardTargetType
from world.npc_services.factories import NpcRegardFactory
from world.npc_services.models import NpcRegard
from world.scenes.factories import PersonaFactory


class NpcRegardModelTests(TestCase):
    def test_persona_target_is_valid(self):
        regard = NpcRegardFactory(value=-500)
        self.assertEqual(regard.target_type, RegardTargetType.PERSONA)
        self.assertIsNotNone(regard.target_persona)
        self.assertIsNone(regard.target_organization)
        self.assertIsNone(regard.target_society)
        self.assertEqual(regard.get_active_target(), regard.target_persona)

    def test_organization_target_is_valid(self):
        regard = NpcRegardFactory(on_organization=True, value=300)
        self.assertEqual(regard.target_type, RegardTargetType.ORGANIZATION)
        self.assertIsNotNone(regard.target_organization)
        self.assertIsNone(regard.target_persona)
        self.assertIsNone(regard.target_society)

    def test_society_target_is_valid(self):
        regard = NpcRegardFactory(on_society=True, value=1)
        self.assertEqual(regard.target_type, RegardTargetType.SOCIETY)
        self.assertIsNotNone(regard.target_society)

    def test_mismatched_discriminator_rejected(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        regard = NpcRegard(
            holder_persona=holder,
            target_type=RegardTargetType.ORGANIZATION,
            target_persona=target,  # wrong column for ORGANIZATION
            value=-10,
        )
        with self.assertRaises(ValidationError):
            regard.save()

    def test_value_out_of_range_rejected(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        regard = NpcRegard(
            holder_persona=holder,
            target_type=RegardTargetType.PERSONA,
            target_persona=target,
            value=99999,
        )
        with self.assertRaises(ValidationError):
            regard.full_clean()

    def test_duplicate_active_regard_same_target_rejected(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        NpcRegardFactory(holder_persona=holder, target_persona=target, value=-50)
        with self.assertRaises(Exception):  # noqa: B017 — IntegrityError vs ValidationError varies
            NpcRegardFactory(holder_persona=holder, target_persona=target, value=50)

    def test_different_target_columns_do_not_collide(self):
        """Two active rows for the same holder — one PERSONA, one ORGANIZATION —
        must NOT trip each other's partial-unique constraint."""
        holder = PersonaFactory()
        persona_regard = NpcRegardFactory(holder_persona=holder, value=-10)
        org_regard = NpcRegardFactory(holder_persona=holder, on_organization=True, value=10)
        self.assertNotEqual(persona_regard.pk, org_regard.pk)
