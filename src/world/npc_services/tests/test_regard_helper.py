"""Tests for get_regard — the NpcRegard read helper."""

from django.test import TestCase

from world.npc_services.factories import NpcRegardFactory
from world.npc_services.regard import get_regard
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, SocietyFactory


class GetRegardTests(TestCase):
    def test_no_row_returns_zero(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        self.assertEqual(get_regard(holder, target), 0)

    def test_persona_target_returns_value(self):
        holder = PersonaFactory()
        target = PersonaFactory()
        NpcRegardFactory(holder_persona=holder, target_persona=target, value=-750)
        self.assertEqual(get_regard(holder, target), -750)

    def test_organization_target_returns_value(self):
        holder = PersonaFactory()
        org = OrganizationFactory()
        NpcRegardFactory(
            holder_persona=holder, on_organization=True, target_organization=org, value=400
        )
        self.assertEqual(get_regard(holder, org), 400)

    def test_society_target_returns_value(self):
        holder = PersonaFactory()
        society = SocietyFactory()
        NpcRegardFactory(holder_persona=holder, on_society=True, target_society=society, value=-1)
        self.assertEqual(get_regard(holder, society), -1)

    def test_ended_regard_is_not_active(self):
        from django.utils import timezone

        holder = PersonaFactory()
        target = PersonaFactory()
        regard = NpcRegardFactory(holder_persona=holder, target_persona=target, value=-900)
        regard.ended_at = timezone.now()
        regard.save()
        self.assertEqual(get_regard(holder, target), 0)

    def test_unsupported_target_type_raises(self):
        holder = PersonaFactory()
        with self.assertRaises(TypeError):
            get_regard(holder, object())
