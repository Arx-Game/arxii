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
