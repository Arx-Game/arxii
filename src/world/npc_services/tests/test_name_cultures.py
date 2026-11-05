"""The place-name bank (#4983 slice 2, #4986): a culture names a realm's places as well
as its people, and the seed links each culture to its realm."""

from __future__ import annotations

from django.test import TestCase

from world.character_creation.factories import RealmFactory
from world.npc_services.models import NameCulture, NameCultureEntry, NamePart
from world.seeds.name_cultures import ensure_name_cultures


class PlaceNameBankTests(TestCase):
    def test_a_culture_links_to_its_realm_and_holds_place_names(self) -> None:
        realm = RealmFactory(name="Luxen")
        culture = NameCulture.objects.create(name="Luxenne test", realm=realm)
        NameCultureEntry.objects.create(culture=culture, part=NamePart.PLACE, value="Salvation")
        assert NameCulture.objects.get(realm=realm) == culture
        assert culture.entries.filter(part=NamePart.PLACE).count() == 1

    def test_the_seed_links_each_culture_to_its_realm(self) -> None:
        RealmFactory(name="Luxen")
        ensure_name_cultures()
        assert NameCulture.objects.get(name="Luxenne").realm.name == "Luxen"
        assert NameCulture.objects.get(name="Common Tongue").realm is None
