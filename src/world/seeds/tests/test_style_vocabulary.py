"""The seeded aesthetic Style vocabulary — 16 rows across the audacity tiers (#2029)."""

from django.test import TestCase

from world.items.constants import StyleAudacity
from world.items.models import Style
from world.seeds.game_content.items import _STYLE_VOCABULARY, seed_style_vocabulary


class StyleVocabularySeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_style_vocabulary()

    def test_all_sixteen_rows_exist(self) -> None:
        for name in _STYLE_VOCABULARY:
            Style.objects.get(name=name)
        self.assertEqual(len(_STYLE_VOCABULARY), 16)

    def test_four_names_per_tier(self) -> None:
        for tier in StyleAudacity:
            count = Style.objects.filter(name__in=list(_STYLE_VOCABULARY), audacity=tier).count()
            self.assertEqual(count, 4, f"expected 4 styles at {tier!r}, got {count}")

    def test_audacity_is_authoritative_on_reseed(self) -> None:
        row = Style.objects.get(name="Demure")
        row.audacity = StyleAudacity.OUTRAGEOUS
        row.save(update_fields=["audacity"])
        seed_style_vocabulary()
        row.refresh_from_db()
        self.assertEqual(row.audacity, StyleAudacity.UNDERSTATED)

    def test_reseed_is_idempotent(self) -> None:
        before = Style.objects.filter(name__in=list(_STYLE_VOCABULARY)).count()
        seed_style_vocabulary()
        after = Style.objects.filter(name__in=list(_STYLE_VOCABULARY)).count()
        self.assertEqual(before, after)
