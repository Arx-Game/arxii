"""Name culture seed tests (#2827)."""

from django.test import TestCase

from world.npc_services.instantiation import generate_person_name
from world.npc_services.models import NameCulture
from world.seeds.name_cultures import ensure_name_cultures


class NameCultureSeedTests(TestCase):
    def test_seed_creates_all_regional_cultures(self):
        ensured = ensure_name_cultures()
        self.assertGreater(ensured, 0)
        names = set(NameCulture.objects.values_list("name", flat=True))
        self.assertTrue(
            {"Common Tongue", "Umbran", "Luxenne", "Ariwnese", "Aythirn", "Infernal"} <= names
        )
        # The global default resolves for rooms outside any authored region.
        default = NameCulture.objects.get(name="Common Tongue")
        self.assertIsNone(default.area)

    def test_seed_is_idempotent(self):
        ensure_name_cultures()
        self.assertEqual(ensure_name_cultures(), 0)

    def test_every_culture_generates_full_names(self):
        ensure_name_cultures()
        for culture in NameCulture.objects.all():
            full_name = generate_person_name(culture)
            self.assertGreaterEqual(len(full_name.split()), 2, culture.name)

    def test_seed_links_area_when_it_exists(self):
        from world.areas.factories import AreaFactory

        AreaFactory(name="Umbros")
        ensure_name_cultures()
        self.assertIsNotNone(NameCulture.objects.get(name="Umbran").area)
