"""The #2862-review gap closures (#2869 follow-through). SQLite tier.

Each test pins a gap that shipped silently broken: content nothing created,
config nothing wrote, or a capability with no reachable surface.
"""

from django.test import TestCase, override_settings


class BaselineAreaLawTest(TestCase):
    """Crime minted zero heat everywhere because no AreaLaw row existed."""

    def test_laws_seed_at_the_reserved_area(self):
        from world.areas.constants import AreaLevel
        from world.areas.models import Area
        from world.justice.models import AreaLaw
        from world.seeds.justice import seed_crime_kinds
        from world.seeds.justice_laws import BASELINE_AREA_SLUG, seed_baseline_area_laws

        Area.objects.create(name="Arx", slug=BASELINE_AREA_SLUG, level=AreaLevel.CITY)
        seed_crime_kinds()
        seed_baseline_area_laws()
        self.assertGreater(AreaLaw.objects.count(), 0)

    def test_vice_is_criminal_but_not_capital(self):
        """Dealing is a living, not a hanging — and murder outweighs it."""
        from world.areas.constants import AreaLevel
        from world.areas.models import Area
        from world.justice.models import AreaLaw
        from world.seeds.justice import seed_crime_kinds
        from world.seeds.justice_laws import BASELINE_AREA_SLUG, seed_baseline_area_laws

        Area.objects.create(name="Arx", slug=BASELINE_AREA_SLUG, level=AreaLevel.CITY)
        seed_crime_kinds()
        seed_baseline_area_laws()
        contraband = AreaLaw.objects.get(crime_kind__slug="contraband")
        murder = AreaLaw.objects.get(crime_kind__slug="murder")
        self.assertGreater(contraband.heat_weight, 0)
        self.assertGreater(murder.heat_weight, contraband.heat_weight)

    def test_law_lookup_now_finds_something(self):
        """The whole point: law_for stops returning None for a real crime."""
        from world.areas.constants import AreaLevel
        from world.areas.models import Area
        from world.justice.models import CrimeKind
        from world.justice.services import law_for
        from world.seeds.justice import seed_crime_kinds
        from world.seeds.justice_laws import BASELINE_AREA_SLUG, seed_baseline_area_laws

        area = Area.objects.create(name="Arx", slug=BASELINE_AREA_SLUG, level=AreaLevel.CITY)
        seed_crime_kinds()
        seed_baseline_area_laws()
        crime = CrimeKind.objects.get(slug="contraband")
        self.assertIsNotNone(law_for(area, crime))

    def test_reseeding_never_overwrites_a_tuned_law(self):
        from world.areas.constants import AreaLevel
        from world.areas.models import Area
        from world.justice.models import AreaLaw
        from world.seeds.justice import seed_crime_kinds
        from world.seeds.justice_laws import BASELINE_AREA_SLUG, seed_baseline_area_laws

        Area.objects.create(name="Arx", slug=BASELINE_AREA_SLUG, level=AreaLevel.CITY)
        seed_crime_kinds()
        seed_baseline_area_laws()
        law = AreaLaw.objects.get(crime_kind__slug="theft")
        law.heat_weight = 999
        law.save(update_fields=["heat_weight"])
        seed_baseline_area_laws()
        law.refresh_from_db()
        self.assertEqual(law.heat_weight, 999)

    def test_missing_area_is_a_warning_not_a_crash(self):
        from world.seeds.justice_laws import seed_baseline_area_laws

        seed_baseline_area_laws()  # no area exists — must not raise


@override_settings(SEED_SAMPLE_CONTENT=True)
class ShadeContentTest(TestCase):
    """apply_shade_undeath had zero callers; its upkeep row was never created."""

    def test_shade_anchor_and_daily_drain_seed(self):
        from world.magic.models.appetites import AppetitePeriod, AppetiteUpkeep
        from world.seeds.character_creation import _seed_appetite_content
        from world.species.appetites import SHADE_SLUG

        _seed_appetite_content()
        upkeep = AppetiteUpkeep.objects.get(distinction__slug=SHADE_SLUG)
        self.assertEqual(upkeep.period, AppetitePeriod.DAILY)
        self.assertEqual(upkeep.floor_percent, 0)

    def test_shades_are_now_reachable_and_drain(self):
        """The GM tool makes a Shade, and the drain config exists for it."""
        from unittest.mock import patch

        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.models.appetites import AppetiteUpkeep
        from world.species.appetites import SHADE_SLUG
        from world.species.factories import apply_shade_undeath

        sheet = CharacterSheetFactory()
        with patch("world.conditions.services.apply_condition"):
            apply_shade_undeath(sheet.character)
        self.assertTrue(AppetiteUpkeep.objects.filter(distinction__slug=SHADE_SLUG).exists())
        from world.distinctions.models import CharacterDistinction

        self.assertTrue(
            CharacterDistinction.objects.filter(
                character=sheet, distinction__slug=SHADE_SLUG
            ).exists()
        )


class WeatherClusterTest(TestCase):
    """The transition graph never loaded on a seeded database."""

    def test_cluster_is_registered(self):
        from world.seeds.clusters import CLUSTER_SEEDERS

        self.assertIn("weather", CLUSTER_SEEDERS)

    def test_missing_corpus_warns_instead_of_crashing(self):
        from unittest.mock import patch

        from world.seeds.weather_content import seed_weather_content

        with patch(
            "world.seeds.weather_content.resolve_weather_fixtures_dir",
            return_value=None,
        ):
            seed_weather_content()  # must not raise
