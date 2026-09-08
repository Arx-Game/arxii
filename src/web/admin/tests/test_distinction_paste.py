"""Add from a table on the Distinction Builder (#3709): additions only, previewed, digested."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.distinction_builder.paste import parse_table, table_digest
from world.character_creation.constants import OfferArrival, OfferChapter
from world.character_creation.factories import (
    AppearanceSectionFactory,
    BeginningsFactory,
    EnemyReasonFactory,
)
from world.character_creation.models import DistinctionOffer
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionCategoryFactory, DistinctionFactory
from world.distinctions.models import Distinction
from world.mechanics.factories import ModifierTargetFactory

ROW = (
    "Oath-Bound | Personality | 5 | 1 | A word given is kept. | Long prose. | +Bonds goals | "
    "rules | Born to a Household"
)
SKIP_ROW = (
    "Secretive | Personality | 25 | 1 | What you know stays. | | +Deception | "
    "rules; reason:You know what they did |"
)
AWARD_ROW = (
    "Squeamish | Personality | -5 | 1 | Never the helpless. | | -Menace; immune:Intoxication | "
    "rules; appearance:Frame |"
)


class PasteTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = AccountDB.objects.create_superuser("paster", "p@example.com", "pw-123456")
        cls.writer = ContentContributorFactory(name="Table Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = AccountDB.objects.create_superuser("unlinked", "u@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("plain", "pl@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()
        cls.category = DistinctionCategoryFactory(name="Personality")
        cls.bonds = ModifierTargetFactory(name="bonds_goals")
        cls.deception = ModifierTargetFactory(name="deception")
        cls.menace = ModifierTargetFactory(name="menace")
        cls.drink = ModifierTargetFactory(name="intoxication")
        cls.beginning = BeginningsFactory(name="Born to a Household")
        cls.reason = EnemyReasonFactory(name="You know what they did")
        cls.frame = AppearanceSectionFactory(name="Frame")
        cls.existing = DistinctionFactory(name="Secretive", slug="secretive", category=cls.category)
        cls.url = reverse("admin_distinction_paste")


class ParseTableTest(PasteTestCase):
    def test_a_good_row_resolves_every_name_and_reads_create(self):
        (row,) = parse_table(ROW)
        assert row.status == "create"
        assert row.slug == "oath-bound"
        assert row.category_id == self.category.pk
        assert row.cost_per_rank == 5
        assert [(e.target_id, e.value, e.immune) for e in row.effects] == [
            (self.bonds.pk, 1, False)
        ]
        assert [(o.chapter, o.opener_field, o.opener_value) for o in row.offers] == [
            (OfferChapter.ACTORS_SHEET, "prompt", "never_do")
        ]
        assert row.first_look_ids == [self.beginning.pk]

    def test_an_existing_slug_reads_skip_never_update(self):
        (row,) = parse_table(SKIP_ROW)
        assert row.status == "skip"
        assert "already exists" in row.notes[0]

    def test_an_unresolved_name_reads_error_and_names_the_row(self):
        rows = parse_table("Ghost | Nowhere | 5 | 1 | | | +Nothing | reason:Nobody | Elsewhere")
        (row,) = rows
        assert row.status == "error"
        notes = " ".join(row.notes)
        assert "unknown category 'Nowhere'" in notes
        assert "unknown modifier target 'Nothing'" in notes
        assert "unknown reason 'Nobody'" in notes
        assert "unknown Beginning 'Elsewhere'" in notes

    def test_a_degree_opener_must_mark_and_arrives_bundled(self):
        (bad,) = parse_table("Marked | Personality | 0 | 1 | | | | degree:thwarted |")
        assert bad.status == "error"
        (good,) = parse_table("Marked | Personality | 0 | 1 | | | | degree:ruined |")
        assert good.status == "create"
        assert good.offers[0].arrives_as == OfferArrival.BUNDLED
        assert good.offers[0].opener_value == "ruined"

    def test_immunity_and_signed_effects_parse(self):
        (row,) = parse_table(AWARD_ROW)
        assert row.status == "create"
        assert [(e.target_id, e.value, e.immune) for e in row.effects] == [
            (self.menace.pk, -1, False),
            (self.drink.pk, None, True),
        ]
        assert [o.opener_field for o in row.offers] == ["prompt", "appearance_section_id"]

    def test_the_same_slug_twice_in_one_table_is_an_error(self):
        rows = parse_table(ROW + "\n" + ROW)
        assert [r.status for r in rows] == ["create", "error"]

    def test_the_digest_changes_when_the_database_does(self):
        before = table_digest(parse_table(ROW))
        DistinctionFactory(name="Oath-Bound", slug="oath-bound", category=self.category)
        after = table_digest(parse_table(ROW))
        assert before != after


class PasteViewTest(PasteTestCase):
    def _check(self, text: str):
        return self.client.post(self.url, {"text": text, "action": "check"})

    def test_superuser_only(self):
        """Staff who are not superusers are blocked, as on every tuning-surface page."""
        self.client.force_login(self.staff)
        assert self.client.get(self.url).status_code == 403

    def test_get_renders_the_form(self):
        self.client.force_login(self.author)
        resp = self.client.get(self.url)
        assert resp.status_code == 200
        assert b"Paste rows" in resp.content

    def test_check_previews_without_writing(self):
        self.client.force_login(self.author)
        resp = self._check(ROW + "\n" + SKIP_ROW)
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "1 to create" in body
        assert "1 skipped" in body
        assert not Distinction.objects.filter(slug="oath-bound").exists()

    def test_create_writes_rows_effects_offers_and_pins_and_credits(self):
        self.client.force_login(self.author)
        digest = table_digest(parse_table(ROW + "\n" + SKIP_ROW))
        resp = self.client.post(
            self.url, {"text": ROW + "\n" + SKIP_ROW, "action": "create", "digest": digest}
        )
        assert resp.status_code == 302
        created = Distinction.objects.get(slug="oath-bound")
        assert created.written_by == self.writer
        assert created.cost_per_rank == 5
        (effect,) = created.effects.all()
        assert effect.target == self.bonds
        assert effect.value_per_rank == 1
        (offer,) = DistinctionOffer.objects.filter(distinction=created)
        assert offer.chapter == OfferChapter.ACTORS_SHEET
        assert offer.prompt == "never_do"
        assert offer.player_line == "A word given is kept."
        assert list(offer.first_look.all()) == [self.beginning]
        assert offer.written_by == self.writer
        # The skipped row was never touched.
        self.existing.refresh_from_db()
        assert self.existing.cost_per_rank != 25
        assert not DistinctionOffer.objects.filter(distinction=self.existing).exists()

    def test_create_refuses_any_error_row_and_writes_nothing(self):
        self.client.force_login(self.author)
        text = ROW + "\nGhost | Nowhere | 5 | 1 | | | | rules |"
        digest = table_digest(parse_table(text))
        resp = self.client.post(self.url, {"text": text, "action": "create", "digest": digest})
        assert resp.status_code == 200
        assert not Distinction.objects.filter(slug="oath-bound").exists()

    def test_create_refuses_a_stale_digest(self):
        self.client.force_login(self.author)
        resp = self.client.post(self.url, {"text": ROW, "action": "create", "digest": "stale"})
        assert resp.status_code == 200
        assert not Distinction.objects.filter(slug="oath-bound").exists()

    def test_unlinked_contributor_cannot_create(self):
        self.client.force_login(self.unlinked)
        digest = table_digest(parse_table(ROW))
        resp = self.client.post(self.url, {"text": ROW, "action": "create", "digest": digest})
        assert resp.status_code == 200
        assert not Distinction.objects.filter(slug="oath-bound").exists()

    def test_pasting_the_same_table_twice_adds_nothing_the_second_time(self):
        self.client.force_login(self.author)
        digest = table_digest(parse_table(ROW))
        self.client.post(self.url, {"text": ROW, "action": "create", "digest": digest})
        again = table_digest(parse_table(ROW))
        resp = self.client.post(self.url, {"text": ROW, "action": "create", "digest": again})
        assert resp.status_code == 200
        assert Distinction.objects.filter(slug="oath-bound").count() == 1
