"""The authored scandal vocabulary (#1464/#1806) — nine categories, correct signs."""

from django.test import TestCase

from world.seeds.scandal_archetypes import _SCANDAL_ARCHETYPES, seed_scandal_archetypes
from world.societies.models import PhilosophicalArchetype


class ScandalArchetypeSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_scandal_archetypes()

    def test_all_nine_rows_exist(self) -> None:
        for name in _SCANDAL_ARCHETYPES:
            PhilosophicalArchetype.objects.get(name=name)
        self.assertEqual(len(_SCANDAL_ARCHETYPES), 9)

    def test_vectors_are_authoritative_on_reseed(self) -> None:
        row = PhilosophicalArchetype.objects.get(name="Merciless Scandal")
        row.mercy_delta = 0
        row.save(update_fields=["mercy_delta"])
        seed_scandal_archetypes()
        row.refresh_from_db()
        self.assertEqual(row.mercy_delta, -4)

    def test_pole_signs_read_correctly(self) -> None:
        """Treachery must offend loyalists/traditionalists — the sign-trap pin.

        Loyalty and Tradition are the NEGATIVE poles of their axes, so the
        deltas are POSITIVE; a loyalist-traditionalist-honorable society must
        read the row negatively.
        """
        from world.societies.factories import SocietyFactory
        from world.societies.renown import _archetype_dot_product

        row = PhilosophicalArchetype.objects.get(name="Treacherous Scandal")
        honorbound = SocietyFactory(method=5, allegiance=-3, change=-3)
        self.assertLess(_archetype_dot_product([row], honorbound), -10)

    def test_placeholder_drafts_are_retired(self) -> None:
        self.assertFalse(
            PhilosophicalArchetype.objects.filter(
                name__in=["PLACEHOLDER Oathbreaking", "PLACEHOLDER Insolence"]
            ).exists()
        )
