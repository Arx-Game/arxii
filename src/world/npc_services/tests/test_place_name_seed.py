"""The place-name banks (#4983 slice 4, #4994): their data is clean and the seed is safe."""

from __future__ import annotations

from collections import Counter

from django.test import SimpleTestCase, TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_creation.factories import RealmFactory
from world.npc_services.instantiation import generate_person_name, name_culture_for_room
from world.npc_services.models import NameCulture, NameCultureEntry, NamePart
from world.seeds.name_cultures import ensure_name_cultures
from world.seeds.place_names import (
    PLACE_BANKS,
    REGIONAL_CULTURES,
    UMBRAN,
    VESTYR,
    ensure_place_names,
)

# canon the banks must leave alone: each is already a named place
CANON = {"Salvation", "Absolution", "Tenebrum", "Perdition", "Ember", "Piropa", "Vampa"}


class PlaceBankDataTests(SimpleTestCase):
    def test_no_name_repeats_across_banks_because_a_title_name_is_unique(self) -> None:
        counts = Counter(name for bank in PLACE_BANKS.values() for name in bank)
        assert [n for n, c in counts.items() if c > 1] == []

    def test_every_name_is_plain_letters_with_no_accent_or_dash(self) -> None:
        for culture, bank in PLACE_BANKS.items():
            for name in bank:
                assert name.replace(" ", "").isascii(), (culture, name)
                assert name.replace(" ", "").isalpha(), (culture, name)

    def test_canon_places_stay_out_of_every_bank(self) -> None:
        taken = {name for bank in PLACE_BANKS.values() for name in bank} & CANON
        assert taken == set()

    def test_every_weight_is_positive(self) -> None:
        for culture, bank in PLACE_BANKS.items():
            assert min(bank.values()) >= 1, culture


class EnsurePlaceNamesTests(TestCase):
    def test_creates_every_bank_and_a_regional_culture_has_no_realm(self) -> None:
        created = ensure_place_names()
        assert created == sum(len(bank) for bank in PLACE_BANKS.values())
        for culture_name, bank in PLACE_BANKS.items():
            culture = NameCulture.objects.get(name=culture_name)
            assert culture.entries.filter(part=NamePart.PLACE).count() == len(bank)
        for name in REGIONAL_CULTURES:
            assert NameCulture.objects.get(name=name).realm_id is None

    def test_a_second_run_changes_nothing_and_keeps_a_staff_edited_weight(self) -> None:
        ensure_place_names()
        entry = NameCultureEntry.objects.get(culture__name=VESTYR, value="Carradyn")
        entry.weight = 1
        entry.save()
        assert ensure_place_names() == 0
        entry.refresh_from_db()
        assert entry.weight == 1

    def test_runs_beside_the_name_seed_in_either_order(self) -> None:
        realm = RealmFactory(name="Umbros")
        ensure_place_names()
        ensure_name_cultures()
        umbran = NameCulture.objects.get(name=UMBRAN)
        assert umbran.realm_id == realm.pk
        assert umbran.entries.filter(part=NamePart.PLACE).exists()
        assert umbran.entries.filter(part=NamePart.GIVEN).exists()
        assert NameCulture.objects.filter(name=UMBRAN).count() == 1

    def test_a_culture_with_only_place_names_is_never_the_global_default_for_npc_names(
        self,
    ) -> None:
        ensure_place_names()  # eight cultures, none of them with a single given name
        common = NameCulture.objects.create(name="Common Tongue")
        NameCultureEntry.objects.create(culture=common, part=NamePart.GIVEN, value="Marta")
        NameCultureEntry.objects.create(culture=common, part=NamePart.SURNAME, value="Vane")
        culture = name_culture_for_room(RoomProfileFactory())
        assert culture == common
        assert generate_person_name(culture) == "Marta Vane"
