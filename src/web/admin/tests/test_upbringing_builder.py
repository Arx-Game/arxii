"""The Upbringing Builder: one page for an Upbringing, its questions and answers (#3660)."""

from pathlib import Path
import re

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
    """The page must draw itself with Django admin's CSS contract (#3667).

    #3660 shipped the Builder rendering ``{{ form.as_div }}`` and hand-written
    ``<p><label>`` rows inside panels that carried class hooks no stylesheet
    defined. Admin's CSS targets ``fieldset.module.aligned``, ``div.form-row``
    and ``div.help``; none of those appeared, so every field on the page fell
    back to browser defaults on production while CI stayed green - the existing
    tests only ever asserted that content was present, never that it was drawn.
    """

    #: Classes the builder templates may use without defining a rule, because
    #: Django admin's own stylesheets already style them. Anything else the
    #: markup carries is ours, and must have a rule on the page.
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
        resp = self.client.get(reverse("admin_upbringing_builder", args=[self.template.pk]))
        assert resp.status_code == 200
        return resp.content.decode()

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

    def test_every_class_the_builder_emits_has_a_rule_on_the_page(self):
        """The guard the original defect needed: a hook with no rule is the bug."""
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/upbringing_builder"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            if path.name == "_preview.html":
                continue  # a standalone document with its own <style>, not an admin page
            markup = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", path.read_text(), flags=re.DOTALL)
            for attr in re.findall(r'class="([^"]*)"', markup):
                emitted.update(token for token in attr.split() if token)

        body = self._body()
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in body
        )
        assert not undefined, f"class hooks with no CSS rule on the page: {undefined}"
