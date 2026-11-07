"""Place names from a table on the Import Data hub (#5001): additions only, previewed, digested."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.import_hub.place_names import parse_table, table_digest
from world.character_creation.factories import RealmFactory
from world.npc_services.models import NameCulture, NameCultureEntry, NamePart
from world.societies.houses.almanach import plant_rung
from world.societies.houses.constants import TitleTier


class PlaceNamePasteTestCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "r@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("staffer", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()
        cls.realm = RealmFactory(name="Umbros")
        cls.vestyr = NameCulture.objects.create(name="Vestyr")
        cls.umbran = NameCulture.objects.create(name="Umbran", realm=cls.realm)
        NameCultureEntry.objects.create(
            culture=cls.vestyr, part=NamePart.PLACE, value="Carradyn", weight=9
        )
        NameCultureEntry.objects.create(culture=cls.vestyr, part=NamePart.GIVEN, value="Penmora")
        cls.url = reverse("admin_place_name_paste")


class ParseTableTest(PlaceNamePasteTestCase):
    def test_good_rows_read_create_with_the_weight_or_one(self) -> None:
        rows = parse_table("vestyr | Aberwen | 8\nUmbran | Fadehollow\n")
        assert [(r.status, r.culture_id, r.name, r.weight) for r in rows] == [
            ("create", self.vestyr.pk, "Aberwen", 8),
            ("create", self.umbran.pk, "Fadehollow", 1),
        ]
        assert rows[0].will_create == "Place name on Vestyr, weight 8"

    def test_an_existing_place_name_reads_skip_and_a_given_name_does_not_count(self) -> None:
        rows = parse_table("Vestyr | Carradyn | 2\nVestyr | Penmora | 2\n")
        assert [r.status for r in rows] == ["skip", "create"]

    def test_the_same_pair_twice_in_one_table_skips_the_second(self) -> None:
        rows = parse_table("Vestyr | Aberwen | 3\nvestyr | aberwen | 5\n")
        assert [r.status for r in rows] == ["create", "skip"]

    def test_errors_name_their_reason(self) -> None:
        text = "Nowhere | Aberwen\nVestyr |  | 3\nVestyr | Aber–wen\nVestyr | Aberwen | zero\n"
        notes = [(r.status, "; ".join(r.notes)) for r in parse_table(text)]
        assert notes[0] == ("error", "unknown culture")
        assert [n[0] for n in notes[1:]] == ["error", "error", "error"]
        assert "no name" in notes[1][1]
        assert "hyphen" in notes[2][1]
        assert "weight" in notes[3][1]
        assert parse_table("no pipes here\n")[0].status == "error"

    def test_a_name_over_a_hundred_characters_is_an_error_not_cut_short(self) -> None:
        [row] = parse_table(f"Vestyr | {'A' * 101}\n")
        assert row.status == "error"
        assert any("100" in n for n in row.notes)

    def test_a_weight_past_the_column_limit_is_an_error_not_a_500(self) -> None:
        [row] = parse_table("Vestyr | Aberwen | 3000000000\n")
        assert row.status == "error"
        assert any("weight" in n for n in row.notes)

    def test_a_skip_names_the_spelling_that_exists(self) -> None:
        [row] = parse_table("Vestyr | CARRADYN\n")
        assert row.status == "skip"
        assert any("Carradyn" in n for n in row.notes)

    def test_two_cultures_differing_only_in_case_are_ambiguous(self) -> None:
        NameCulture.objects.create(name="VESTYR")
        [row] = parse_table("vestyr | Aberwen\n")
        assert row.status == "error"
        assert "ambiguous culture" in row.notes

    def test_a_name_a_title_bears_creates_with_a_note(self) -> None:
        plant_rung(realm=self.realm, tier=TitleTier.KINGDOM, name="Aberwen")
        [row] = parse_table("Vestyr | Aberwen\n")
        assert row.status == "create"
        assert any("title" in n for n in row.notes)

    def test_parsing_runs_three_queries_however_many_rows(self) -> None:
        """Cultures, existing place names and title names are read once, not per row."""
        text = "".join(f"Vestyr | Name{i} | {i % 9 + 1}\n" for i in range(40))
        text += "Umbran | Fadehollow\nNowhere | Lost\nVestyr | Carradyn\n"
        with self.assertNumQueries(3):
            rows = parse_table(text)
        assert [r.status for r in rows[-3:]] == ["create", "error", "skip"]

    def test_the_digest_changes_when_the_database_does(self) -> None:
        before = table_digest(parse_table("Vestyr | Aberwen | 3\n"))
        NameCultureEntry.objects.create(culture=self.vestyr, part=NamePart.PLACE, value="Aberwen")
        assert table_digest(parse_table("Vestyr | Aberwen | 3\n")) != before


class PlaceNamePasteViewTest(PlaceNamePasteTestCase):
    TABLE = "Vestyr | Aberwen | 8\nVestyr | Tregarion | 7\nUmbran | Fadehollow\n"

    def _create(self, text: str):
        digest = table_digest(parse_table(text))
        return self.client.post(self.url, {"text": text, "action": "create", "digest": digest})

    def test_superuser_only(self) -> None:
        self.client.force_login(self.staff)
        assert self.client.get(self.url).status_code == 403

    def test_check_previews_without_writing(self) -> None:
        self.client.force_login(self.super)
        resp = self.client.post(self.url, {"text": self.TABLE, "action": "check"})
        assert resp.status_code == 200
        assert "3 to create" in resp.content.decode()
        assert not NameCultureEntry.objects.filter(value="Aberwen").exists()

    def test_create_writes_the_rows_with_their_weights_and_twice_adds_nothing(self) -> None:
        self.client.force_login(self.super)
        resp = self._create(self.TABLE)
        assert resp.status_code == 302
        assert resp.url == reverse("admin:arxii_nameculture_changelist")
        places = NameCultureEntry.objects.filter(part=NamePart.PLACE)
        assert places.count() == 4
        assert places.get(value="Aberwen").weight == 8
        assert places.get(value="Fadehollow").culture == self.umbran
        again = self.client.post(self.url, {"text": self.TABLE, "action": "check"})
        assert "3 skipped" in again.content.decode()
        self._create(self.TABLE)
        assert NameCultureEntry.objects.filter(part=NamePart.PLACE).count() == 4

    def test_create_refuses_any_error_row_and_a_stale_digest(self) -> None:
        self.client.force_login(self.super)
        bad = self.TABLE + "Nowhere | Lost\n"
        assert self._create(bad).status_code == 200
        assert not NameCultureEntry.objects.filter(value="Aberwen").exists()
        stale = self.client.post(
            self.url, {"text": self.TABLE, "action": "create", "digest": "not-the-digest"}
        )
        assert stale.status_code == 200
        assert not NameCultureEntry.objects.filter(value="Aberwen").exists()

    def test_the_name_culture_list_filters_by_realm(self) -> None:
        self.client.force_login(self.super)
        body = self.client.get(reverse("admin:arxii_nameculture_changelist")).content.decode()
        assert "realm__id__exact" in body
