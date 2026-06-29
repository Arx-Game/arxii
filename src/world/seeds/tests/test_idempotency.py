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
        res = Resonance.objects.order_by("pk").first()
        assert res is not None
        res.description = "STAFF-EDITED — must survive re-seed"
        res.save()
        seed_dev_database()
        res.refresh_from_db()
        self.assertEqual(res.description, "STAFF-EDITED — must survive re-seed")

    def test_edited_cg_row_survives_reseed(self) -> None:
        """The #651 non-overwrite gate for the character_creation cluster."""
        from world.species.models import Species

        seed_dev_database()
        sp = Species.objects.get(name="Human")
        sp.description = "HAND-EDITED"
        sp.save()

        seed_dev_database()  # re-seed must NOT overwrite

        sp.refresh_from_db()
        self.assertEqual(sp.description, "HAND-EDITED")
