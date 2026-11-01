"""Add from a table on the Distinction Builder (#3709): additions only, previewed, digested."""

from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.distinction_builder.paste import parse_table, table_digest
from web.admin.tests.test_distinction_builder import (
    DistinctionBuilderStylingTest,
    emitted_classes,
    reachable_css,
)
from world.character_creation.constants import LifeStage, OfferArrival, OfferChapter
from world.character_creation.factories import (
    AppearanceSectionFactory,
    BeginningsFactory,
    EnemyReasonFactory,
    LifeBeatFactory,
)
from world.character_creation.models import DistinctionOffer
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionCategoryFactory, DistinctionFactory
from world.distinctions.models import Distinction
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.skills.factories import SkillTraitFactory

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

    def test_an_unlocked_token_names_the_card_that_opens_a_final_touches_line(self):
        """#4846: ``unlocked:<card>`` is the Final Touches opener; the card must exist."""
        jailbird = DistinctionFactory(name="Jailbird", slug="jailbird", category=self.category)
        (row,) = parse_table(
            "Escape Artist | Personality | 5 | 1 | Locks open. | | | unlocked:Jailbird |"
        )
        assert row.status == "create", row.notes
        (offer,) = row.offers
        assert offer.chapter == OfferChapter.FINAL_TOUCHES
        assert offer.arrives_as == OfferArrival.CHOICE
        assert (offer.opener_field, offer.opener_value) == ("unlocked_by_id", jailbird.pk)
        (missing,) = parse_table("Escape Artist | Personality | 5 | 1 | | | | unlocked:Nobody |")
        assert missing.status == "error"
        assert "unknown card 'Nobody'" in " ".join(missing.notes)

    def test_a_prestige_token_makes_the_starting_prestige_sidecar(self):
        """#4852: ``+150 prestige`` / ``-300 prestige`` is a grant, not a modifier effect."""
        (row,) = parse_table(
            "Renowned | Personality | 5 | 1 | Broadly admired. | | +150 prestige | rules |"
        )
        assert row.status == "create", row.notes
        assert row.prestige == 150
        assert row.effects == []
        assert "starts with +150 prestige" in row.will_create
        (infamous,) = parse_table(
            "Infamous | Personality | -10 | 1 | Wanted dead. | | -300 prestige; -Menace | rules |"
        )
        assert infamous.status == "create", infamous.notes
        assert infamous.prestige == -300
        assert len(infamous.effects) == 1
        (bare,) = parse_table("Bare | Personality | 5 | 1 | | | +prestige | rules |")
        assert bare.status == "error"
        assert "needs an amount" in " ".join(bare.notes)
        (twice,) = parse_table(
            "Twice | Personality | 5 | 1 | | | +150 prestige; +10 prestige | rules |"
        )
        assert twice.status == "error"
        assert "one starting prestige" in " ".join(twice.notes)

    def test_a_leading_star_marks_a_pin_as_the_suggested_life(self):
        """#4865: ``*Reavers, Underworld`` pins both and suggests the card for Reavers."""
        underworld = BeginningsFactory(name="Underworld")
        (row,) = parse_table(
            "Urchin | Personality | -10 | 1 | The street raised you. | | | rules | "
            "*Born to a Household, Underworld"
        )
        assert row.status == "create", row.notes
        assert row.first_look_ids == [self.beginning.pk, underworld.pk]
        assert row.preselected_ids == [self.beginning.pk]
        assert "suggested for Born to a Household" in row.will_create
        self.client.force_login(self.author)
        text = (
            "Urchin | Personality | -10 | 1 | The street raised you. | | | rules | "
            "*Born to a Household, Underworld"
        )
        digest = table_digest(parse_table(text))
        resp = self.client.post(self.url, {"text": text, "action": "create", "digest": digest})
        assert resp.status_code == 302
        (offer,) = DistinctionOffer.objects.filter(distinction__slug="urchin")
        flags = dict(offer.pins.values_list("beginning_id", "preselected"))
        assert flags == {self.beginning.pk: True, underworld.pk: False}

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

    def test_a_skill_with_no_target_yet_reads_create_and_names_the_target_it_makes(self):
        """+10 on a skill no target points at is not an error (#4820): the preview says the
        create step makes the target, and nothing is written at parse time."""
        SkillTraitFactory(name="Sailing")
        (row,) = parse_table("Shipboard | Personality | 10 | 1 | At sea. | | +10 sailing | rules |")
        assert row.status == "create", row.notes
        assert row.notes == ["makes the modifier target for the Sailing skill"]
        (effect,) = row.effects
        assert effect.target_id is None
        assert effect.value == 10
        assert not ModifierTarget.objects.filter(name="sailing").exists()

    def test_a_skill_name_with_a_space_or_underscore_resolves_the_same_skill(self):
        SkillTraitFactory(name="Melee Combat")
        (spaced,) = parse_table("A | Personality | 5 | 1 | a | | +5 melee combat | rules |")
        (underscored,) = parse_table("B | Personality | 5 | 1 | b | | +5 melee_combat | rules |")
        assert spaced.status == underscored.status == "create"
        assert spaced.effects[0].skill_trait_id == underscored.effects[0].skill_trait_id

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

    def test_an_unlocked_token_creates_a_final_touches_line_through_the_page(self):
        """#4846: the paste view previews and creates a line the named card unlocks."""
        jailbird = DistinctionFactory(name="Jailbird", slug="jailbird", category=self.category)
        text = "Escape Artist | Personality | 5 | 1 | Locks open. | | | unlocked:Jailbird |"
        self.client.force_login(self.author)
        resp = self._check(text)
        assert resp.status_code == 200
        assert "1 to create" in resp.content.decode()
        digest = table_digest(parse_table(text))
        resp = self.client.post(self.url, {"text": text, "action": "create", "digest": digest})
        assert resp.status_code == 302, resp.content
        created = Distinction.objects.get(slug="escape-artist")
        (offer,) = DistinctionOffer.objects.filter(distinction=created)
        assert offer.chapter == OfferChapter.FINAL_TOUCHES
        assert offer.unlocked_by == jailbird
        assert offer.opener_key == f"unlocked:{jailbird.pk}"
        assert offer.written_by == self.writer

    def test_create_makes_the_skill_target_and_the_effect_lands_on_it(self):
        """The create step makes the stat-category target for the skill's trait inside the
        batch, so the pasted +10 sailing reaches the Sailing roll (#4820)."""
        trait = SkillTraitFactory(name="Sailing")
        text = "Shipboard | Personality | 10 | 1 | At sea. | | +10 sailing | rules |"
        self.client.force_login(self.author)
        digest = table_digest(parse_table(text))
        resp = self.client.post(self.url, {"text": text, "action": "create", "digest": digest})
        assert resp.status_code == 302, resp.content
        target = ModifierTarget.objects.get(name="sailing")
        assert target.category.name == "stat"
        assert target.target_trait == trait
        (effect,) = Distinction.objects.get(slug="shipboard").effects.all()
        assert (effect.target, effect.value_per_rank) == (target, 10)
        # A second paste that names the skill finds the target the ordinary way.
        (row,) = parse_table("Wilderness | Personality | 10 | 1 | w | | +10 sailing | rules |")
        assert row.effects[0].target_id == target.pk
        assert row.notes == []

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


LAP = "The Lap of Luxury | Personality | 15 | 1 | A great house. | Long prose. | +Bonds goals | "


class BeatOpenerTest(PasteTestCase):
    """``beat:<stage>/<beat>`` places a card on a Life beat (#4655)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.early = LifeBeatFactory(name="Early Upbringing", life_stage=LifeStage.CHILDHOOD)
        cls.child_moments = LifeBeatFactory(name="Defining Moments", life_stage=LifeStage.CHILDHOOD)
        cls.youth_moments = LifeBeatFactory(name="Defining Moments", life_stage=LifeStage.YOUTH)
        cls.before = LifeBeatFactory(name="Past Careers", life_stage=LifeStage.ADULTHOOD)

    def _offer(self, token: str):
        (row,) = parse_table(LAP + token)
        return row

    def test_a_beat_token_resolves_to_a_backgrounds_choice_on_that_beat(self):
        row = self._offer("beat:childhood/Early Upbringing")
        assert row.status == "create"
        (spec,) = row.offers
        assert (spec.chapter, spec.arrives_as, spec.opener_field, spec.opener_value) == (
            OfferChapter.BACKGROUNDS,
            OfferArrival.CHOICE,
            "beat_id",
            self.early.pk,
        )

    def test_the_stage_picks_between_beats_that_share_a_name(self):
        child = self._offer("beat:childhood/Defining Moments")
        youth = self._offer("beat:youth/Defining Moments")
        assert child.offers[0].opener_value == self.child_moments.pk
        assert youth.offers[0].opener_value == self.youth_moments.pk

    def test_the_stage_may_be_written_as_its_label_and_the_name_in_any_case(self):
        row = self._offer("beat:Before the Glimpse/past careers")
        assert row.status == "create"
        assert row.offers[0].opener_value == self.before.pk

    def test_a_beat_that_does_not_exist_is_an_error_and_is_not_created(self):
        row = self._offer("beat:childhood/Nowhere")
        assert row.status == "error"
        assert "unknown beat 'Nowhere' in Childhood" in row.notes[0]

    def test_a_name_without_a_stage_is_an_error_that_shows_the_form(self):
        row = self._offer("beat:Early Upbringing")
        assert row.status == "error"
        assert "beat:childhood/Early Upbringing" in row.notes[0]

    def test_an_unknown_stage_is_an_error_that_lists_the_stages(self):
        row = self._offer("beat:midlife/Early Upbringing")
        assert row.status == "error"
        assert "unknown life stage 'midlife'" in row.notes[0]
        assert "childhood" in row.notes[0]

    def test_create_makes_the_answer_on_the_beat_with_the_players_line_and_credit(self):
        self.client.force_login(self.author)
        text = LAP + "beat:childhood/Early Upbringing; beat:youth/Defining Moments"
        digest = table_digest(parse_table(text))
        resp = self.client.post(self.url, {"text": text, "action": "create", "digest": digest})
        assert resp.status_code == 302
        card = Distinction.objects.get(slug="the-lap-of-luxury")
        offers = DistinctionOffer.objects.filter(distinction=card).order_by("beat_id")
        assert [o.beat for o in offers] == [self.early, self.youth_moments]
        for offer in offers:
            assert offer.chapter == OfferChapter.BACKGROUNDS
            assert offer.arrives_as == OfferArrival.CHOICE
            assert offer.player_line == "A great house."
            assert offer.written_by == self.writer
        assert [o.distinction for o in self.early.answers] == [card]


class PasteStylingTest(PasteTestCase):
    """Every class paste.html emits must have a rule reaching THIS page (#3667 shape).

    The Builder page's own guard (``DistinctionBuilderStylingTest``) resolves classes
    against the Builder page's CSS, which is not what this page links: a class the
    Builder's ``_css.html`` styles under ``#distinction-builder-root`` never reaches
    here. Found by the demo-fidelity review of #3709, hence its own guard.
    """

    ADMIN_PROVIDED_CLASSES = DistinctionBuilderStylingTest.ADMIN_PROVIDED_CLASSES | {
        # forms.css widget classes, linked by this page's own extrastyle
        "vLargeTextField",
    }

    def _rendered(self) -> str:
        self.client.force_login(self.author)
        resp = self.client.post(self.url, {"text": ROW + "\n" + SKIP_ROW, "action": "check"})
        assert resp.status_code == 200
        return resp.content.decode()

    def test_every_class_the_page_emits_has_a_rule_that_reaches_the_page(self):
        template = (
            Path(__file__).resolve().parents[2] / "templates/admin/distinction_builder/paste.html"
        )
        emitted = emitted_classes(template)
        css = reachable_css(self._rendered())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        assert not undefined, f"class hooks with no CSS rule reaching the page: {undefined}"
