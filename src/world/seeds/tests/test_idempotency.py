from django.test import TestCase

from world.seeds.database import seed_dev_database


class TestSeedIdempotency(TestCase):
    def test_second_run_creates_nothing(self) -> None:
        first = seed_dev_database()
        self.assertGreater(first.created_total, 0)
        second = seed_dev_database()
        self.assertEqual(second.created_total, 0)

    def test_edit_survives_reseed(self) -> None:
        from world.magic.models import Resonance

        seed_dev_database()
        res = Resonance.objects.first()
        assert res is not None
        res.description = "STAFF-EDITED — must survive re-seed"
        res.save()
        seed_dev_database()
        res.refresh_from_db()
        self.assertEqual(res.description, "STAFF-EDITED — must survive re-seed")
