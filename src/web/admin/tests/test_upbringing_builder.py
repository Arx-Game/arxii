"""The Upbringing Builder: one page for an Upbringing, its questions and answers (#3660)."""

from pathlib import Path
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from world.character_creation.constants import AnchorSource, QuestionKind
from world.character_creation.factories import (
    GroupPromptFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.models import (
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
)
from world.contributors.factories import ContentContributorFactory
from world.distinctions.factories import DistinctionFactory
from world.roster.factories import FamilyFactory, FamilyKindFactory
from world.societies.factories import OrganizationFactory


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class BuilderTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("builderauthor")
        cls.writer = ContentContributorFactory(name="Builder Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("builderunlinked")
        cls.template = OriginTemplateFactory(
            name="Born to a Household", allows_name_family=False, allows_no_family=True
        )
        cls.q1 = GroupPromptFactory(template=cls.template, sort_order=0, name="House")
        cls.q1.anchor_orgs.add(OrganizationFactory(name="House Orisant"))
        cls.livery = OriginTemplateSlotChoiceFactory(slot=cls.q1, name="Livery at table")


class BuilderGetTest(BuilderTestCase):
    def test_renders_upbringing_questions_and_answers(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Born to a Household" in body
        assert "Pick a group" in body
        assert "Livery at table" in body
        assert "Matches 1 group today" in body  # live line for the LISTED source
        assert "House Orisant" in body

    def test_unlinked_contributor_sees_setup_guidance(self):
        self.client.force_login(self.unlinked)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        assert "link a contributor" in resp.content.decode().lower()

    def test_add_answer_button_clones_the_formsets_empty_form(self):
        """Ruling H: "Add answer" is a client-side clone, not an HTMX round trip."""
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        body = resp.content.decode()
        assert f"a{self.q1.pk}-__prefix__-name" in body
        assert "Add answer" in body


class BuilderAutocompleteWidgetsTest(BuilderTestCase):
    """The Builder's autocomplete widgets' AJAX calls (#3670 regression).

    Both ``QuestionForm.anchor_orgs`` and ``AnswerForm.grants_distinction`` are
    built with ``Autocomplete(Select|SelectMultiple)(<field>, admin.site)``. Each
    widget must be constructed from the **forward** field itself, not its
    ``.remote_field`` (the reverse relation on the target model) - the reverse
    relation has no ``get_limit_choices_to()``, so a request built off it 500s
    inside Django's own ``AutocompleteJsonView`` (Sentry ARX2-C, filed as #3670).
    """

    def test_anchor_orgs_widget_points_the_ajax_call_at_the_forward_field(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        body = resp.content.decode()
        assert 'data-app-label="arxii"' in body
        assert 'data-model-name="origintemplateslot"' in body
        assert 'data-field-name="anchor_orgs"' in body

    def test_anchor_orgs_autocomplete_endpoint_returns_matching_organizations(self):
        self.client.force_login(self.author)
        resp = self.client.get(
            "/admin/autocomplete/",
            {"app_label": "arxii", "model_name": "origintemplateslot", "field_name": "anchor_orgs"},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert any(r["text"].startswith("House Orisant") for r in results)

    def test_grants_distinction_widget_points_the_ajax_call_at_the_forward_field(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        body = resp.content.decode()
        assert 'data-model-name="origintemplateslotchoice"' in body
        assert 'data-field-name="grants_distinction"' in body

    def test_grants_distinction_autocomplete_endpoint_returns_matching_distinctions(self):
        DistinctionFactory(name="Kept Close")
        self.client.force_login(self.author)
        resp = self.client.get(
            "/admin/autocomplete/",
            {
                "app_label": "arxii",
                "model_name": "origintemplateslotchoice",
                "field_name": "grants_distinction",
            },
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert any(r["text"].startswith("Kept Close") for r in results)


class BuilderSaveTest(BuilderTestCase):
    def _post_data(self, **overrides):
        data = {
            "beginning": self.template.beginning_id,
            "name": "Born to a Household",
            "frame_narrative": "You stood through dinners.",
            "cg_point_cost": "0",
            "trust_required": "0",
            "allows_no_family": "on",
            "is_active": "on",
            "sort_order": "1",
            # question formset: one existing question
            "q-TOTAL_FORMS": "1",
            "q-INITIAL_FORMS": "1",
            "q-MIN_NUM_FORMS": "0",
            "q-MAX_NUM_FORMS": "1000",
            "q-0-id": str(self.q1.pk),
            "q-0-name": "House",
            "q-0-prompt": "Which Humble house kept you",
            "q-0-example": "",
            "q-0-sort_order": "0",
            "q-0-is_required": "on",
            "q-0-applies_to": "any",
            "q-0-kind": QuestionKind.GROUP,
            "q-0-connection_kind": "served",
            "q-0-life_stage": "childhood",
            "q-0-anchor_source": AnchorSource.LISTED,
            "q-0-exclude_covert": "on",
            "q-0-anchor_orgs": [str(self.q1.anchor_orgs.first().pk)],
            # answers formset for q1
            f"a{self.q1.pk}-TOTAL_FORMS": "1",
            f"a{self.q1.pk}-INITIAL_FORMS": "1",
            f"a{self.q1.pk}-MIN_NUM_FORMS": "0",
            f"a{self.q1.pk}-MAX_NUM_FORMS": "1000",
            f"a{self.q1.pk}-0-id": str(self.livery.pk),
            f"a{self.q1.pk}-0-name": "Livery at table",
            f"a{self.q1.pk}-0-description": "You stood through the dinners.",
            f"a{self.q1.pk}-0-cg_point_cost": "5",
            f"a{self.q1.pk}-0-cost_per_influence": "1",
            f"a{self.q1.pk}-0-reputation_seed": "100",
            f"a{self.q1.pk}-0-trust_required": "0",
            f"a{self.q1.pk}-0-is_active": "on",
            f"a{self.q1.pk}-0-sort_order": "0",
        }
        data.update(overrides)
        return data

    def test_save_writes_rows_and_credits_the_operator(self):
        self.client.force_login(self.author)
        kept = DistinctionFactory(name="Kept Close")
        resp = self.client.post(
            reverse("admin_upbringing_builder", args=[self.template.pk]),
            self._post_data(**{f"a{self.q1.pk}-0-grants_distinction": str(kept.pk)}),
        )
        assert resp.status_code == 302
        self.template.refresh_from_db()
        assert self.template.written_by == self.writer
        choice = OriginTemplateSlotChoice.objects.get(pk=self.livery.pk)
        assert choice.cg_point_cost == 5
        assert choice.grants_distinction == kept
        assert choice.written_by == self.writer
        assert OriginTemplateSlot.objects.get(pk=self.q1.pk).written_by == self.writer

    def test_save_with_a_text_question_succeeds(self):
        """Ruling G: a TEXT/PERSON question has no answers formset to bind."""
        self.client.force_login(self.author)
        text_q = OriginTemplateSlotFactory(
            template=self.template, sort_order=1, kind=QuestionKind.TEXT
        )
        data = self._post_data(
            **{
                "q-TOTAL_FORMS": "2",
                "q-INITIAL_FORMS": "2",
                "q-1-id": str(text_q.pk),
                "q-1-name": text_q.name,
                "q-1-prompt": "Where did you grow up",
                "q-1-example": "",
                "q-1-sort_order": "1",
                "q-1-is_required": "on",
                "q-1-applies_to": "any",
                "q-1-kind": QuestionKind.TEXT,
            }
        )
        resp = self.client.post(reverse("admin_upbringing_builder", args=[self.template.pk]), data)
        assert resp.status_code == 302
        assert OriginTemplateSlot.objects.get(pk=text_q.pk).prompt == "Where did you grow up"

    def test_naming_path_saves_with_the_family_template_the_operator_just_picked(self):
        """Reported from production: the name path could never be saved (#3673).

        ``OriginTemplate.clean()`` asked ``self.family_templates.exists()`` - the
        rows already in the database. A ModelForm runs the instance's
        ``full_clean()`` in ``_post_clean()``, which is before ``save_m2m()``, so
        the check read the state the operator was trying to change and rejected
        every save of an Upbringing whose name path was being turned on. Ticking
        the box and highlighting the one Family Template in the box failed
        identically, because what was selected was never what got looked at.
        """
        from world.societies.houses.factories import HouseTemplateFactory

        self.client.force_login(self.author)
        self.template.family_templates.clear()
        charter = HouseTemplateFactory(name="Caretaker Household")
        resp = self.client.post(
            reverse("admin_upbringing_builder", args=[self.template.pk]),
            self._post_data(
                allows_name_family="on",
                family_templates=[str(charter.pk)],
            ),
        )
        assert resp.status_code == 302, (
            "the name path was refused with the Family Template the operator picked: "
            f"{resp.context['form'].errors.as_text() if resp.context else resp.status_code}"
        )
        self.template.refresh_from_db()
        assert list(self.template.family_templates.all()) == [charter]

    def test_naming_path_is_still_refused_with_no_family_template_picked(self):
        """The rule itself stands: it now reads what was submitted (#3673)."""
        self.client.force_login(self.author)
        self.template.family_templates.clear()
        resp = self.client.post(
            reverse("admin_upbringing_builder", args=[self.template.pk]),
            self._post_data(allows_name_family="on", family_templates=[]),
        )
        assert resp.status_code == 200
        assert "family_templates" in resp.context["form"].errors

    def test_add_answer_row_saves_a_second_choice(self):
        """Ruling H: the client-cloned second row posts and saves like any other."""
        self.client.force_login(self.author)
        data = self._post_data(
            **{
                f"a{self.q1.pk}-TOTAL_FORMS": "2",
                f"a{self.q1.pk}-1-name": "Cold shoulder",
                f"a{self.q1.pk}-1-description": "",
                f"a{self.q1.pk}-1-cg_point_cost": "0",
                f"a{self.q1.pk}-1-cost_per_influence": "0",
                f"a{self.q1.pk}-1-reputation_seed": "0",
                f"a{self.q1.pk}-1-trust_required": "0",
                f"a{self.q1.pk}-1-is_active": "on",
                f"a{self.q1.pk}-1-sort_order": "1",
            }
        )
        resp = self.client.post(reverse("admin_upbringing_builder", args=[self.template.pk]), data)
        assert resp.status_code == 302
        assert OriginTemplateSlotChoice.objects.filter(slot=self.q1).count() == 2

    def test_review_stamps_review_only(self):
        self.client.force_login(self.author)
        resp = self.client.post(reverse("admin_upbringing_builder_review", args=[self.template.pk]))
        assert resp.status_code == 302
        template = OriginTemplate.objects.get(pk=self.template.pk)
        assert template.reviewed_by == self.writer
        assert template.written_by is None

    def test_unlinked_contributor_cannot_save(self):
        self.client.force_login(self.unlinked)
        resp = self.client.post(
            reverse("admin_upbringing_builder", args=[self.template.pk]), self._post_data()
        )
        assert resp.status_code == 200  # re-rendered with the setup guidance
        assert OriginTemplateSlotChoice.objects.get(pk=self.livery.pk).cg_point_cost == 0


class BuilderLiveTest(BuilderTestCase):
    def test_rail_counts_and_checks(self):
        from web.admin.upbringing_builder import live

        counts = live.rail_counts(self.template)
        assert counts["questions"] == 1
        assert counts["groups_asked_about"] == 1
        assert counts["answers"] == 1
        panel = live.for_template(self.template, self.author)
        assert [org.name for org in panel.groups_by_slot[self.q1.pk]] == ["House Orisant"]
        assert any(kind == "ok" for kind, _ in panel.checks)

    def test_inactive_granted_distinction_is_a_warn_check(self):
        from web.admin.upbringing_builder import live

        inactive = DistinctionFactory(name="Faded Claim", is_active=False)
        OriginTemplateSlotChoiceFactory(
            slot=self.q1, name="Old promise", grants_distinction=inactive
        )
        panel = live.for_template(self.template, self.author)
        assert any(kind == "warn" and "Faded Claim" in text for kind, text in panel.checks)

    def test_group_question_with_no_anchor_source_is_a_warn_check(self):
        from web.admin.upbringing_builder import live

        OriginTemplateSlotFactory(
            template=self.template,
            sort_order=1,
            kind=QuestionKind.GROUP,
            anchor_source="",
            name="No source",
        )
        panel = live.for_template(self.template, self.author)
        assert any(kind == "warn" and "No source" in text for kind, text in panel.checks)

    def test_own_family_group_with_a_houseless_claimable_family_is_a_warn_check(self):
        from web.admin.upbringing_builder import live

        OriginTemplateSlotFactory(
            template=self.template,
            sort_order=1,
            kind=QuestionKind.GROUP,
            anchor_source=AnchorSource.OWN_FAMILY,
            name="Own family",
        )
        FamilyFactory(is_playable=True)  # no Organization behind it
        panel = live.for_template(self.template, self.author)
        assert any(
            kind == "warn" and "own-family group cannot resolve" in text
            for kind, text in panel.checks
        )

    def test_own_family_group_with_every_claimable_family_housed_is_not_a_warn_check(self):
        from web.admin.upbringing_builder import live

        OriginTemplateSlotFactory(
            template=self.template,
            sort_order=1,
            kind=QuestionKind.GROUP,
            anchor_source=AnchorSource.OWN_FAMILY,
            name="Own family",
        )
        housed = FamilyFactory(is_playable=True)
        OrganizationFactory(name="Its House", family=housed)
        panel = live.for_template(self.template, self.author)
        assert not any("own-family group cannot resolve" in text for _, text in panel.checks)

    def test_own_family_check_narrows_to_claimable_kinds_when_set(self):
        from web.admin.upbringing_builder import live

        OriginTemplateSlotFactory(
            template=self.template,
            sort_order=1,
            kind=QuestionKind.GROUP,
            anchor_source=AnchorSource.OWN_FAMILY,
            name="Own family",
        )
        offered_kind = FamilyKindFactory(name="Offered Kind")
        self.template.claimable_kinds.add(offered_kind)
        FamilyFactory(is_playable=True)  # a different (default) kind, houseless, but not offered
        panel = live.for_template(self.template, self.author)
        assert not any("own-family group cannot resolve" in text for _, text in panel.checks)

    def test_shown_for_choices_without_follow_up_is_a_warn_check(self):
        from web.admin.upbringing_builder import live

        branchy = OriginTemplateSlotFactory(
            template=self.template,
            sort_order=1,
            kind=QuestionKind.TEXT,
            name="Branchy",
        )
        branchy.shown_for_choices.add(self.livery)
        panel = live.for_template(self.template, self.author)
        assert any(kind == "warn" and "Branchy" in text for kind, text in panel.checks)

    def test_open_places_unavailable_on_error(self):
        from unittest.mock import patch

        from django.db import DatabaseError

        from web.admin.upbringing_builder import live

        with patch(
            "web.admin.upbringing_builder.live.reachable_vacancies",
            side_effect=DatabaseError("boom"),
        ):
            panel = live.for_template(self.template, self.author)
        assert panel.open_places == live.OPEN_PLACES_UNAVAILABLE

    def test_page_still_renders_when_open_places_check_raises(self):
        """Ruling I (amended): a side tile must never take the whole Builder page down."""
        from unittest.mock import patch

        from django.db import DatabaseError

        self.client.force_login(self.author)
        with patch(
            "web.admin.upbringing_builder.live.reachable_vacancies",
            side_effect=DatabaseError("boom"),
        ):
            resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        assert resp.status_code == 200
        assert "unavailable" in resp.content.decode()

    def test_inactive_answers_are_excluded_from_rail_counts_and_checks(self):
        """Ruling 2: an inactive answer is never offered to a player, so it never counts."""
        from web.admin.upbringing_builder import live

        template = OriginTemplateFactory(name="Isolated Rail Counts")
        slot = OriginTemplateSlotFactory(
            template=template, kind=QuestionKind.PICK, is_required=True
        )
        OriginTemplateSlotChoiceFactory(
            slot=slot, name="Cheap and active", cg_point_cost=5, is_active=True
        )
        inactive_dist = DistinctionFactory(name="Retired Claim", is_active=False)
        OriginTemplateSlotChoiceFactory(
            slot=slot,
            name="Retired and pricey",
            cg_point_cost=50,
            is_active=False,
            grants_distinction=inactive_dist,
        )

        counts = live.rail_counts(template)
        assert counts["answers"] == 1
        assert counts["cheapest_complete_answer"] == 5
        assert counts["dearest_complete_answer"] == 5

        panel = live.for_template(template, self.author)
        assert not any("Retired Claim" in text for _, text in panel.checks)


class BuilderPreviewTest(BuilderTestCase):
    def test_preview_renders_the_question_and_first_group(self):
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder_preview", args=[self.template.pk]))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "House" in body
        assert "House Orisant" in body


class BuilderStylingTest(BuilderTestCase):
    """Every rule the page's layout needs must REACH the page (#3667).

    Two rounds of this defect, both invisible to a test that reads the response
    body alone. #3660 shipped the Builder rendering ``{{ form.as_div }}`` inside
    panels whose class hooks no stylesheet defined. The first fix converted the
    markup to admin's own ``fieldset.module.aligned`` / ``div.form-row`` /
    ``div.help`` - and the page still rendered with browser defaults on
    production, because ``.form-row``, ``.aligned label``, ``.flex-container``,
    ``.checkbox-row`` and ``.submit-row`` are defined in ``admin/css/forms.css``,
    which Django links from ``change_form.html``'s ``extrastyle`` block and this
    page never loaded.

    Asserting a class NAME appears in the HTML proves nothing: it is satisfied by
    markup nobody styles. Asserting the name appears in the page's reachable CSS
    is not enough either - ``responsive.css`` (which ``base.html`` does link)
    mentions every one of those names inside media queries, so that check passes
    with the whole layout still missing. The stylesheet has to be named.
    """

    #: Stylesheets this page has to link for itself. ``admin/base.html`` links
    #: ``base.css``, ``dark_mode.css`` and ``responsive.css``; ``forms.css`` is
    #: linked by ``change_form.html`` only, so any custom admin page that renders
    #: form rows has to ask for it in its own ``extrastyle`` block.
    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css")

    #: Classes our own templates carry that Django admin already styles; the rest
    #: of what they carry is ours, and must have a rule in CSS the page loads.
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

    #: A class the page's own script selects on and nothing styles. Named rather
    #: than allowlisted loosely, so a genuine missing rule cannot hide here.
    JS_ONLY_CLASSES = frozenset({"add-answer-btn"})

    def _body(self) -> str:
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
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

    def _reachable_css(self, body: str) -> str:
        """The page's inline ``<style>`` blocks plus every stylesheet it links.

        Each ``<link>`` is resolved through the staticfiles finders and read off
        disk. One that resolves to nothing is a failure in itself: the page is
        asking for a stylesheet that will 404.
        """
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", body, flags=re.DOTALL))
        missing: list[str] = []
        for href in self._stylesheet_hrefs(body):
            if not href.startswith(settings.STATIC_URL):
                continue  # an absolute URL elsewhere; nothing to read off disk
            found = finders.find(href[len(settings.STATIC_URL) :])
            if found is None:
                missing.append(href)
                continue
            css += "\n" + Path(found).read_text()
        assert not missing, f"the page links stylesheets that do not resolve: {missing}"
        return css

    def test_the_page_links_the_stylesheets_its_layout_needs(self):
        """The guard the second round needed: correct markup, no stylesheet behind it."""
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

    def test_fields_render_through_admins_fieldset_contract(self):
        body = self._body()
        assert 'class="module aligned' in body, "fields are not in an admin fieldset"
        assert "form-row" in body, "no admin form rows - labels will not align"
        assert 'class="help"' in body, "field help text is not in admin's help markup"
        assert 'class="submit-row"' in body, "the save buttons are not in a submit row"

    def test_the_page_is_laid_out_two_column_with_the_rail_on_the_right(self):
        body = self._body()
        assert 'class="ub-columns"' in body
        assert 'class="ub-rail"' in body
        assert "grid-template-columns" in body, "the two-column shell has no rule"

    def test_every_class_the_builder_emits_has_a_rule_that_reaches_the_page(self):
        """The guard the first round needed, asked of the CSS rather than the HTML."""
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/upbringing_builder"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            if path.name == "_preview.html":
                continue  # a standalone document with its own <style>, not an admin page
            markup = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", path.read_text(), flags=re.DOTALL)
            for attr in re.findall(r'class="([^"]*)"', markup):
                emitted.update(token for token in attr.split() if token)

        css = self._reachable_css(self._body())
        ignored = self.ADMIN_PROVIDED_CLASSES | self.JS_ONLY_CLASSES
        undefined = sorted(token for token in emitted - ignored if f".{token}" not in css)
        assert not undefined, f"class hooks with no CSS rule reaching the page: {undefined}"


class BuilderDemoFidelityTest(BuilderTestCase):
    """Where a piece sits, not just that it is present (#3667 demo-fidelity review).

    Every one of these was rendered on the page and read as content by the
    earlier tests while sitting in the wrong place, or missing entirely, against
    the design the demo approved. "Is the string in the body" cannot tell the
    difference; each of these asks about position or about the piece itself.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.q2 = OriginTemplateSlotFactory(
            template=cls.template,
            sort_order=1,
            name="Who looked after you",
            kind=QuestionKind.PERSON,
            same_anchor_as=cls.q1,
        )
        cls.q3 = OriginTemplateSlotFactory(
            template=cls.template,
            sort_order=2,
            name="How you left",
            kind=QuestionKind.TEXT,
            follow_up_to=cls.q1,
        )

    def _body(self) -> str:
        self.client.force_login(self.author)
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        assert resp.status_code == 200
        return resp.content.decode()

    def test_the_live_match_line_sits_under_the_rule_it_reports_on(self):
        """It used to trail the whole question, several screens from the field."""
        body = self._body()
        live_line = body.index("Matches 1 group today")
        answers_table = body.index('class="tuning-table answers-table"')
        rule_row = body.index("field-anchor_org_type")
        assert rule_row < live_line < answers_table, (
            "the live match line must sit between the type/realm row it reports on and "
            "the answers table, not after the whole question"
        )

    def test_a_question_names_the_earlier_one_it_hangs_off(self):
        # Compared against whitespace-collapsed markup, which is what a reader
        # sees: the chip's number sits on its own line to stay inside the line
        # limit, and the browser renders that as a single space.
        text = re.sub(r"\s+", " ", self._body())
        assert "About the group from Question 1" in text, "reused-anchor chip missing"
        assert "Branches off Question 1" in text, "follow-up chip missing"

    def test_the_rail_runs_route_checks_credit_preview(self):
        body = self._body()
        wanted = ("This route", "Checks", "Credit", "Preview")
        order = [body.index(f"<h2>{name}</h2>") for name in wanted]
        assert order == sorted(order), f"the rail's panels are out of the demo's order {wanted}"


class BuilderFieldWidthTest(BuilderStylingTest):
    """Fields must be sized for the column they sit in (#3673).

    The Builder runs a ~1050px main column beside the rail, and admin's own
    widths were drawn for a narrow change form: Name came out 184px and cut off
    the template name it is a natural key for, Card text 309px for the longest
    prose on the page, Claimable kinds 90px. Measured in a browser after the
    fix: Name 622px, Card text 846px, Claimable kinds 512px, Point cost and
    Trust required side by side (both at y=786) instead of stacked with the
    first one's help line pressed against the second one's label.

    No test here runs a browser, so none of them can measure a rendered width.
    Two things they can ask, and both fail against the state that shipped: does
    a rule sizing each field kind reach the page at all, and does the page still
    render that field where the rule's selector looks for it. The second is the
    one that rots quietly - a Django release or a fieldset change moves the
    input out of ``div.flex-container`` and every width silently reverts.
    """

    #: id -> the CSS the sheet must carry for that field's kind. A field whose
    #: rule is gone falls back to admin's default width with nothing to notice.
    SIZED_FIELDS = {
        "id_name": '.form-row .flex-container > input[type="text"]',
        "id_frame_narrative": ".form-row .flex-container > textarea",
        "id_claimable_kinds": (
            ".form-row .flex-container > select[multiple]:not(.admin-autocomplete)"
        ),
        "id_q-0-prompt": ".form-row .flex-container > textarea",
    }

    #: The row that holds two or three fields. Admin sizes those boxes to their
    #: content, which put Point cost's help line directly above Trust required's
    #: label; a flex basis gives each field a column of its own.
    MULTILINE_RULE = ".form-row .form-multiline > div"

    def _parent_classes(self, body: str, element_id: str) -> list[list[str]]:
        """Class lists of every open ancestor of ``element_id``, outermost first."""
        from html.parser import HTMLParser

        void = {"input", "br", "img", "hr", "meta", "link", "source", "col"}

        class _Ancestry(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.stack: list[list[str]] = []
                self.found: list[list[str]] | None = None

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if attrs.get("id") == element_id and self.found is None:
                    self.found = list(self.stack)
                if tag not in void:
                    self.stack.append((attrs.get("class") or "").split())

            def handle_endtag(self, tag):
                if tag not in void and self.stack:
                    self.stack.pop()

        parser = _Ancestry()
        parser.feed(body)
        assert parser.found is not None, f"#{element_id} is not on the page at all"
        return parser.found

    def test_every_widened_field_sits_where_its_rule_looks_for_it(self):
        body = self._body()
        for element_id in self.SIZED_FIELDS:
            ancestors = self._parent_classes(body, element_id)
            parent = ancestors[-1] if ancestors else []
            assert "flex-container" in parent, (
                f"#{element_id} is not a direct child of div.flex-container "
                f"(parent classes: {parent}); its width rule matches nothing and the "
                f"field reverts to admin's default."
            )
            assert any("form-row" in classes for classes in ancestors), (
                f"#{element_id} is not inside a div.form-row; its width rule matches nothing."
            )

    def test_a_width_rule_for_every_field_kind_reaches_the_page(self):
        css = self._reachable_css(self._body())
        wanted = set(self.SIZED_FIELDS.values()) | {self.MULTILINE_RULE}
        missing = sorted(rule for rule in wanted if rule not in css)
        assert not missing, (
            f"no width rule reaches the page for: {missing}; those fields render at "
            f"admin's default width in this page's much wider column."
        )
