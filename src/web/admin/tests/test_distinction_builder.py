"""The Distinction Builder: effects, exclusions and offers on one page (#3675)."""

from pathlib import Path
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.character_creation.constants import OfferArrival, OfferChapter
from world.character_creation.factories import (
    DistinctionOfferFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.models import DistinctionOffer
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import (
    DistinctionCategoryFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.distinctions.models import Distinction, DistinctionEffect
from world.mechanics.factories import ModifierTargetFactory


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class BuilderTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("dbauthor")
        cls.writer = ContentContributorFactory(name="Distinction Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("dbunlinked")
        cls.category = DistinctionCategoryFactory(name="Arcane")
        cls.distinction = DistinctionFactory(
            name="Tradition Training",
            category=cls.category,
            cost_per_rank=1,
            max_rank=2,
            description="Years spent under a tradition's tutelage.",
        )
        cls.target = ModifierTargetFactory(name="Starting technique picks")
        cls.effect = DistinctionEffectFactory(
            distinction=cls.distinction, target=cls.target, value_per_rank=1
        )
        cls.other = DistinctionFactory(name="Unbound")
        cls.slot = OriginTemplateSlotFactory(name="Who taught you")
        cls.choice = OriginTemplateSlotChoiceFactory(slot=cls.slot, name="The hold's arms-master")


class BuilderGetTest(BuilderTestCase):
    def test_renders_the_four_panels_and_the_rail(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_distinction_builder", args=[self.distinction.pk]))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "The distinction" in body
        assert "What it does" in body
        assert "Cannot be held with" in body
        assert "Where it is offered" in body
        assert "This distinction" in body
        assert "Tradition Training" in body

    def test_unlinked_contributor_sees_setup_guidance(self):
        self.client.force_login(self.unlinked)
        resp = self.client.get(reverse("admin_distinction_builder", args=[self.distinction.pk]))
        assert "link a contributor" in resp.content.decode().lower()

    def test_origin_choice_autocomplete_label_is_the_full_chain(self):
        self.client.force_login(self.author)
        resp = self.client.get(
            "/admin/autocomplete/",
            {
                "app_label": "arxii",
                "model_name": "distinctionoffer",
                "field_name": "origin_choice",
            },
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert any(
            r["text"]
            == (
                f"{self.slot.template.name} › Q{self.slot.sort_order + 1} · "
                f"{self.slot.name} › {self.choice.name}"
            )
            for r in results
        )

    def test_opened_by_cell_links_the_origin_choice_opener_to_its_question(self):
        """#3675 Task 10: the "Opened by" cell links an offer's opener to where it's edited."""
        DistinctionOfferFactory(
            distinction=self.distinction,
            chapter=OfferChapter.LINEAGE,
            origin_choice=self.choice,
            arrives_as=OfferArrival.BUNDLED,
        )
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_distinction_builder", args=[self.distinction.pk]))
        body = resp.content.decode()
        expected_href = (
            f"{reverse('admin_upbringing_builder', args=[self.slot.template.pk])}"
            f"#question-{self.slot.pk}"
        )
        assert expected_href in body


class BuilderSaveTest(BuilderTestCase):
    def _post_data(self, **overrides):
        data = {
            "name": "Tradition Training",
            "category": str(self.category.pk),
            "cost_per_rank": "1",
            "max_rank": "2",
            "description": "Years spent under a tradition's tutelage.",
            "slug": self.distinction.slug,
            "is_active": "on",
            "default_secret_level": "1",
            "mutually_exclusive_with": [str(self.other.pk)],
            "effects-TOTAL_FORMS": "2",
            "effects-INITIAL_FORMS": "1",
            "effects-MIN_NUM_FORMS": "0",
            "effects-MAX_NUM_FORMS": "1000",
            "effects-0-id": str(self.effect.pk),
            "effects-0-target": str(self.target.pk),
            # 2, not the factory's own 1 - the formset only stamps a row it
            # actually changed (matches the tradition slate page's own rule).
            "effects-0-value_per_rank": "2",
            "effects-1-id": "",
            "effects-1-target": "",
            "effects-1-value_per_rank": "",
            "offers-TOTAL_FORMS": "1",
            "offers-INITIAL_FORMS": "0",
            "offers-MIN_NUM_FORMS": "0",
            "offers-MAX_NUM_FORMS": "1000",
            "offers-0-id": "",
            "offers-0-chapter": OfferChapter.LINEAGE,
            "offers-0-arrives_as": OfferArrival.CHOICE,
            "offers-0-name": "",
            "offers-0-player_line": "Drilled by the arms-master",
            "offers-0-schooling_line": "",
            "offers-0-glimpse_tag": "",
            "offers-0-origin_choice": str(self.choice.pk),
            "offers-0-sort_order": "0",
        }
        data.update(overrides)
        return data

    def test_save_writes_the_effect_exclusion_and_offer_and_credits_the_operator(self):
        self.client.force_login(self.author)
        resp = self.client.post(
            reverse("admin_distinction_builder", args=[self.distinction.pk]), self._post_data()
        )
        assert resp.status_code == 302
        self.distinction.refresh_from_db()
        assert self.distinction.written_by == self.writer
        assert self.other in self.distinction.mutually_exclusive_with.all()
        effect = DistinctionEffect.objects.get(pk=self.effect.pk)
        assert effect.value_per_rank == 2
        assert effect.written_by == self.writer
        offer = DistinctionOffer.objects.get(
            distinction=self.distinction, chapter=OfferChapter.LINEAGE
        )
        assert offer.origin_choice_id == self.choice.pk
        assert offer.player_line == "Drilled by the arms-master"
        assert offer.written_by == self.writer

    def test_unlinked_contributor_cannot_save(self):
        self.client.force_login(self.unlinked)
        resp = self.client.post(
            reverse("admin_distinction_builder", args=[self.distinction.pk]), self._post_data()
        )
        assert resp.status_code == 200
        assert not DistinctionOffer.objects.filter(distinction=self.distinction).exists()

    def test_review_stamps_review_only(self):
        self.client.force_login(self.author)
        resp = self.client.post(
            reverse("admin_distinction_builder_review", args=[self.distinction.pk])
        )
        assert resp.status_code == 302
        distinction = Distinction.objects.get(pk=self.distinction.pk)
        assert distinction.reviewed_by == self.writer
        assert distinction.written_by is None

    def test_delete_checkbox_removes_the_effect(self):
        # A fresh effect, not the shared `cls.effect` other tests in this class
        # also post back - deleting a SharedMemoryModel row nulls its pk on the
        # idmapper-cached Python instance itself, which a rolled-back test
        # transaction does not undo, so a later test referencing `cls.effect`
        # would post a stale, now-invalid id (idmapper delete/rollback gotcha).
        extra_target = ModifierTargetFactory(name="Extra target")
        extra_effect = DistinctionEffectFactory(
            distinction=self.distinction, target=extra_target, value_per_rank=3
        )
        self.client.force_login(self.author)
        data = self._post_data(
            **{
                "effects-TOTAL_FORMS": "3",
                "effects-INITIAL_FORMS": "2",
                "effects-1-id": str(extra_effect.pk),
                "effects-1-target": str(extra_target.pk),
                "effects-1-value_per_rank": "3",
                "effects-1-DELETE": "on",
                "effects-2-id": "",
                "effects-2-target": "",
                "effects-2-value_per_rank": "",
                # Leave effects-0 (`cls.effect`) untouched by this save.
                "effects-0-value_per_rank": "1",
            }
        )
        resp = self.client.post(
            reverse("admin_distinction_builder", args=[self.distinction.pk]), data
        )
        assert resp.status_code == 302
        assert not DistinctionEffect.objects.filter(pk=extra_effect.pk).exists()
        assert DistinctionEffect.objects.filter(pk=self.effect.pk).exists()

    def test_delete_checkbox_removes_the_offer(self):
        from world.character_creation.factories import DistinctionOfferFactory

        offer = DistinctionOfferFactory(
            distinction=self.distinction,
            chapter=OfferChapter.APPEARANCE,
            arrives_as=OfferArrival.CHOICE,
        )
        self.client.force_login(self.author)
        data = self._post_data(
            **{
                "offers-TOTAL_FORMS": "2",
                "offers-INITIAL_FORMS": "1",
                "offers-0-id": str(offer.pk),
                "offers-0-chapter": OfferChapter.APPEARANCE,
                "offers-0-arrives_as": OfferArrival.CHOICE,
                "offers-0-name": offer.name,
                "offers-0-player_line": offer.player_line,
                "offers-0-schooling_line": "",
                "offers-0-glimpse_tag": "",
                "offers-0-origin_choice": "",
                "offers-0-sort_order": "0",
                "offers-0-DELETE": "on",
                "offers-1-id": "",
                "offers-1-chapter": "",
                "offers-1-arrives_as": OfferArrival.CHOICE,
                "offers-1-name": "",
                "offers-1-player_line": "",
                "offers-1-schooling_line": "",
                "offers-1-glimpse_tag": "",
                "offers-1-origin_choice": "",
                "offers-1-sort_order": "0",
            }
        )
        resp = self.client.post(
            reverse("admin_distinction_builder", args=[self.distinction.pk]), data
        )
        assert resp.status_code == 302
        assert not DistinctionOffer.objects.filter(pk=offer.pk).exists()

    def test_tradition_step_offer_wording_ignores_posted_values(self):
        """Demo-fidelity defect A: a TRADITION_STEP row's name/player_line are derived."""
        from world.character_creation.factories import DistinctionOfferFactory, SchoolingLineFactory

        line = SchoolingLineFactory(
            rank=2,
            name="Trained for years",
            player_line="Trained since youth.",
            grants=self.distinction,
        )
        offer = DistinctionOfferFactory(
            distinction=self.distinction,
            chapter=OfferChapter.TRADITION_STEP,
            arrives_as=OfferArrival.CHOICE,
            schooling_line=line,
            name=line.name,
            player_line=line.player_line,
        )
        self.client.force_login(self.author)
        data = self._post_data(
            **{
                "offers-TOTAL_FORMS": "2",
                "offers-INITIAL_FORMS": "1",
                "offers-0-id": str(offer.pk),
                "offers-0-chapter": OfferChapter.TRADITION_STEP,
                "offers-0-arrives_as": OfferArrival.CHOICE,
                "offers-0-name": "A different name entirely",
                "offers-0-player_line": "Some other wording.",
                "offers-0-schooling_line": str(line.pk),
                "offers-0-glimpse_tag": "",
                "offers-0-origin_choice": "",
                "offers-0-sort_order": "0",
                "offers-1-id": "",
                "offers-1-chapter": "",
                "offers-1-arrives_as": OfferArrival.CHOICE,
                "offers-1-name": "",
                "offers-1-player_line": "",
                "offers-1-schooling_line": "",
                "offers-1-glimpse_tag": "",
                "offers-1-origin_choice": "",
                "offers-1-sort_order": "0",
            }
        )
        resp = self.client.post(
            reverse("admin_distinction_builder", args=[self.distinction.pk]), data
        )
        assert resp.status_code == 302
        offer.refresh_from_db()
        assert offer.name == "Trained for years"
        assert offer.player_line == "Trained since youth."


class BuilderNewRouteTest(BuilderTestCase):
    def test_new_route_creates_a_distinction(self):
        self.client.force_login(self.author)
        data = {
            "name": "Fresh Distinction",
            "category": str(self.category.pk),
            "cost_per_rank": "0",
            "max_rank": "1",
            "description": "",
            "slug": "fresh-distinction",
            "is_active": "on",
            "default_secret_level": "1",
            "mutually_exclusive_with": [],
            "effects-TOTAL_FORMS": "1",
            "effects-INITIAL_FORMS": "0",
            "effects-MIN_NUM_FORMS": "0",
            "effects-MAX_NUM_FORMS": "1000",
            "effects-0-id": "",
            "effects-0-target": "",
            "effects-0-value_per_rank": "",
            "offers-TOTAL_FORMS": "1",
            "offers-INITIAL_FORMS": "0",
            "offers-MIN_NUM_FORMS": "0",
            "offers-MAX_NUM_FORMS": "1000",
            "offers-0-id": "",
            "offers-0-chapter": "",
            "offers-0-arrives_as": OfferArrival.CHOICE,
            "offers-0-name": "",
            "offers-0-player_line": "",
            "offers-0-schooling_line": "",
            "offers-0-glimpse_tag": "",
            "offers-0-origin_choice": "",
            "offers-0-sort_order": "0",
        }
        resp = self.client.post(reverse("admin_distinction_builder_new"), data)
        assert resp.status_code == 302
        assert Distinction.objects.filter(name="Fresh Distinction").exists()

    def test_new_route_get_renders_with_no_rail(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_distinction_builder_new"))
        assert resp.status_code == 200
        assert "New Distinction" in resp.content.decode()


class BuilderLiveTest(BuilderTestCase):
    def test_rail_counts(self):
        from web.admin.distinction_builder import live

        counts = live.rail_counts(self.distinction)
        assert counts.effects == 1
        assert counts.exclusions == 0
        assert counts.offered_in == 0
        assert counts.held_by == 0

    def test_checks_warn_with_no_offer(self):
        from web.admin.distinction_builder import live

        result = live.checks(self.distinction)
        assert ("warn", "Not offered anywhere; a player can never reach it in CG.") in result

    def test_checks_warn_when_description_is_a_placeholder(self):
        from web.admin.distinction_builder import live

        self.distinction.description = "PLACEHOLDER needs real prose"
        result = live.checks(self.distinction)
        assert any(kind == "warn" and "PLACEHOLDER" in text for kind, text in result)

    def test_checks_ok_once_offered(self):
        from web.admin.distinction_builder import live
        from world.character_creation.factories import DistinctionOfferFactory

        DistinctionOfferFactory(
            distinction=self.distinction,
            chapter=OfferChapter.APPEARANCE,
            arrives_as=OfferArrival.CHOICE,
        )
        result = live.checks(self.distinction)
        assert ("ok", "Offered somewhere; a player can reach it.") in result


class BuilderOrderingTest(BuilderTestCase):
    """Demo-fidelity defect B: chapter's declared order, not the DB's alphabetical one."""

    def _make_tied_offers(self):
        from world.character_creation.factories import DistinctionOfferFactory, SchoolingLineFactory

        line = SchoolingLineFactory(
            rank=2,
            name="Trained for years",
            player_line="Trained since youth.",
            grants=self.distinction,
        )
        DistinctionOfferFactory(
            distinction=self.distinction,
            chapter=OfferChapter.LINEAGE,
            arrives_as=OfferArrival.CHOICE,
            origin_choice=self.choice,
            sort_order=0,
            name="Drilled by the arms-master",
            player_line="An arms-master's patience.",
        )
        DistinctionOfferFactory(
            distinction=self.distinction,
            chapter=OfferChapter.TRADITION_STEP,
            arrives_as=OfferArrival.CHOICE,
            schooling_line=line,
            sort_order=0,
            name=line.name,
            player_line=line.player_line,
        )

    def test_tradition_step_offer_renders_before_lineage_at_the_same_sort_order(self):
        self._make_tied_offers()
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_distinction_builder", args=[self.distinction.pk]))
        body = resp.content.decode()
        assert body.index("Trained for years") < body.index("Drilled by the arms-master")

    def test_preview_prefers_tradition_step_over_lineage_at_the_same_sort_order(self):
        from web.admin.distinction_builder import live

        self._make_tied_offers()
        preview = live.preview_line(self.distinction)
        assert preview.name == "Trained for years"


class BuilderObjectToolTest(BuilderTestCase):
    def test_open_in_distinction_builder_appears_on_the_stock_change_form(self):
        self.client.force_login(self.author)
        resp = self.client.get(
            reverse("admin:arxii_distinction_change", args=[self.distinction.pk])
        )
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Open in Distinction Builder" in body
        assert reverse("admin_distinction_builder", args=[self.distinction.pk]) in body


class DistinctionBuilderStylingTest(BuilderTestCase):
    """Every rule the page's layout needs must REACH the page (#3667, mirrored for #3675).

    Copied from ``BuilderStylingTest``/``SlateStylingTest``: asserting a class NAME
    appears in the HTML proves nothing, and neither does asserting the name appears
    anywhere in the page's reachable CSS - ``responsive.css`` (linked by ``base.html``)
    mentions admin's own class names inside media queries. The stylesheet has to be named.
    """

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")
    REQUIRED_SCRIPTS = ("admin/js/builder_formsets.js",)

    ADMIN_PROVIDED_CLASSES = frozenset(
        {
            "module",
            "aligned",
            "description",
            "help",
            "errornote",
            "breadcrumbs",
            "submit-row",
            "button",
            "default",
            "tuning-panel",
            "tuning-table",
            "stat-tiles",
            "stat-tile",
            "stat-value",
            "stat-label",
        }
    )

    def _body(self) -> str:
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_distinction_builder", args=[self.distinction.pk]))
        assert resp.status_code == 200
        return resp.content.decode()

    def _stylesheet_hrefs(self, body: str) -> list[str]:
        hrefs = []
        for tag in re.findall(r"<link[^>]*>", body):
            if 'rel="stylesheet"' not in tag:
                continue
            match = re.search(r'href="([^"]+)"', tag)
            if match is not None:
                hrefs.append(match.group(1))
        return hrefs

    def _script_srcs(self, body: str) -> list[str]:
        return re.findall(r'<script[^>]*\bsrc="([^"]+)"', body)

    def _reachable_css(self, body: str) -> str:
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", body, flags=re.DOTALL))
        missing: list[str] = []
        for href in self._stylesheet_hrefs(body):
            if not href.startswith(settings.STATIC_URL):
                continue
            found = finders.find(href[len(settings.STATIC_URL) :])
            if found is None:
                missing.append(href)
                continue
            css += "\n" + Path(found).read_text()
        assert not missing, f"the page links stylesheets that do not resolve: {missing}"
        return css

    def test_the_page_links_the_stylesheets_its_layout_needs(self):
        linked = self._stylesheet_hrefs(self._body())
        missing = [
            sheet
            for sheet in self.REQUIRED_STYLESHEETS
            if not any(href.endswith(sheet) for href in linked)
        ]
        assert not missing, (
            f"the page does not link {missing}; its admin markup has no rules behind it. "
            f"Linked: {linked}"
        )

    def test_the_page_links_the_shared_builder_formsets_script(self):
        body = self._body()
        srcs = self._script_srcs(body)
        missing = [
            script
            for script in self.REQUIRED_SCRIPTS
            if not any(src.endswith(script) for src in srcs)
        ]
        assert not missing, f"the page does not link {missing}. Linked scripts: {srcs}"
        for script in self.REQUIRED_SCRIPTS:
            src = next(s for s in srcs if s.endswith(script))
            if src.startswith(settings.STATIC_URL):
                found = finders.find(src[len(settings.STATIC_URL) :])
                assert found is not None, f"the page links a script that does not resolve: {src}"

    def test_the_page_is_laid_out_two_column_with_the_rail_on_the_right(self):
        body = self._body()
        assert 'class="db-columns"' in body
        assert 'class="db-rail"' in body
        assert "grid-template-columns" in body, "the two-column shell has no rule"

    def test_check_kind_classes_both_have_rules_reaching_the_page(self):
        css = self._reachable_css(self._body())
        assert ".distinction-check--ok" in css
        assert ".distinction-check--warn" in css

    def test_every_class_the_page_emits_has_a_rule_that_reaches_the_page(self):
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/distinction_builder"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            markup = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", path.read_text(), flags=re.DOTALL)
            for attr in re.findall(r'class="([^"]*)"', markup):
                emitted.update(token for token in attr.split() if token)

        css = self._reachable_css(self._body())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        assert not undefined, f"class hooks with no CSS rule reaching the page: {undefined}"
