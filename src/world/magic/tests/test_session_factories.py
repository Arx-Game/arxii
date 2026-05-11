from django.test import TestCase


class SessionFactorySmokeTests(TestCase):
    def test_ritual_session_factory_creates(self):
        from world.magic.factories import RitualSessionFactory

        s = RitualSessionFactory()
        self.assertIsNotNone(s.pk)

    def test_session_with_participant_and_reference(self):
        from world.magic.factories import (
            RitualSessionCovenantRoleRefFactory,
            RitualSessionFactory,
            RitualSessionParticipantFactory,
        )

        s = RitualSessionFactory()
        p = RitualSessionParticipantFactory(session=s)
        RitualSessionCovenantRoleRefFactory(session=s, participant=p)
        self.assertEqual(s.participants.count(), 1)
        self.assertEqual(p.references.count(), 1)


class CovenantRitualFactoryTests(TestCase):
    def test_formation_ritual_factory_idempotent(self):
        """Calling the factory twice returns the same row (django_get_or_create)."""
        from world.magic.factories import CovenantFormationRitualFactory

        a = CovenantFormationRitualFactory()
        b = CovenantFormationRitualFactory()
        self.assertEqual(a.pk, b.pk)

    def test_induction_ritual_factory_idempotent(self):
        from world.magic.factories import CovenantInductionRitualFactory

        a = CovenantInductionRitualFactory()
        b = CovenantInductionRitualFactory()
        self.assertEqual(a.pk, b.pk)

    def test_formation_ritual_dispatches_to_create_covenant_via_session(self):
        from world.magic.factories import CovenantFormationRitualFactory

        r = CovenantFormationRitualFactory()
        self.assertEqual(
            r.service_function_path,
            "world.covenants.services.create_covenant_via_session",
        )

    def test_induction_ritual_dispatches_to_induct_member_via_session(self):
        from world.magic.factories import CovenantInductionRitualFactory

        r = CovenantInductionRitualFactory()
        self.assertEqual(
            r.service_function_path,
            "world.covenants.services.induct_member_via_session",
        )
