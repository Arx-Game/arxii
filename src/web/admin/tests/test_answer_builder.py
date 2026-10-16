"""The Answer builder (#4333 slice 3): a being's written-ahead answers, one coverage
cell at a time, with their sacrifice lines and context. Answer text is labelled
placeholders: answer prose is staff-authored."""

from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.answer_builder.views import builder_url
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.factories import ClueFactory
from world.codex.factories import CodexEntryFactory
from world.contributors.factories import ContentContributorFactory
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import RiteTier
from world.worship.factories import (
    AnswerFactory,
    BeingFacetFactory,
    PledgeFactory,
    RiteKindFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
)
from world.worship.models import Answer, AnswerSacrificeLine, PendingAnswer

_OUTCOMES = (
    ("Critical Failure", -2),
    ("Failure", -1),
    ("Partial Success", 0),
    ("Success", 1),
    ("Critical Success", 2),
)


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class AnswerBuilderTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("abauthor")
        cls.writer = ContentContributorFactory(name="Answer Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("abunlinked")
        cls.tiers = {
            name: CheckOutcomeFactory(name=name, success_level=level) for name, level in _OUTCOMES
        }
        cls.being = WorshippedBeingFactory(name="Ombrin")
        cls.silk = BeingFacetFactory(being=cls.being, facet__name="Silk").facet
        cls.rite = WorshipRiteFactory(
            being=cls.being, kind=RiteKindFactory(tier=RiteTier.DEVOTIONAL), name="Small rite"
        )
        cls.pledge = PledgeFactory(
            being=cls.being, name="PLACEHOLDER pledge", closing_rite=cls.rite
        )
        cls.entry = CodexEntryFactory(name="Hidden entry", is_public=False)
        cls.fact_clue = ClueFactory(
            name="Ombrin codex clue",
            target_codex_entry=cls.entry,
            resolution_mode=ClueResolution.AUTOMATIC,
        )
        mission = MissionTemplateFactory()
        MissionNodeFactory(template=mission, key="entry", is_entry=True)
        cls.mission_clue = ClueFactory(
            name="Ombrin mission clue",
            target_kind=ClueTargetKind.MISSION,
            target_codex_entry=None,
            target_mission=mission,
        )

    def url(self, tier: str = "Success", pledge: str | None = None, answer: str = "") -> str:
        key = pledge if pledge is not None else str(self.pledge.pk)
        return builder_url(self.being, key, self.tiers[tier].pk, answer)

    def body(self, url: str | None = None, account=None) -> str:
        self.client.force_login(account or self.author)
        response = self.client.get(url or self.url())
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def post_data(self, tier: str = "Success", **overrides) -> dict:
        data = {
            "pledge": str(self.pledge.pk),
            "tier": str(self.tiers[tier].pk),
            "answer": "new",
            "answer-delay_text": "[staff-authored delay text]",
            "answer-answer_text": "[staff-authored answer text]",
            "answer-fact_text": "[staff-authored fact text]",
            "answer-fact_clue": str(self.fact_clue.pk),
            "answer-cost_text": "",
            "answer-cost_pool": "",
            "answer-follow_up_text": "[staff-authored follow-up text]",
            "answer-follow_up_clue": str(self.mission_clue.pk),
            "answer-onlooker_line": "[staff-authored onlooker line]",
            "answer-weight": "2",
            "answer-is_active": "on",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-facet": str(self.silk.pk),
            "lines-0-text": "[staff-authored sacrifice line: Silk facet]",
            "save_continue": "Save and continue editing",
        }
        data.update(overrides)
        return data


class AnswerBuilderPageTests(AnswerBuilderTestCase):
    def test_the_page_shows_coverage_by_pledge_type_and_tier(self) -> None:
        AnswerFactory(being=self.being, pledge=self.pledge, outcome_tier=self.tiers["Success"])
        AnswerFactory(being=self.being, outcome_tier=self.tiers["Critical Failure"])
        body = self.body()
        self.assertIn("Answer builder: Ombrin", body)
        self.assertIn("No pledge type (live answers)", body)
        self.assertIn("Pledge type: PLACEHOLDER pledge", body)
        self.assertIn("answer 1 of 1", body)
        self.assertIn("No Critical Success answer. Critical Success uses Success.", body)
        # The pledge row has no Critical Failure answer, but the being's general one covers it.
        self.assertIn(
            "No Critical Failure answer. Critical Failure uses the being&#x27;s general "
            "Critical Failure answer.",
            body,
        )

    def test_the_rail_previews_the_saved_answer_with_its_linked_rows(self) -> None:
        answer = AnswerFactory(
            being=self.being,
            pledge=self.pledge,
            outcome_tier=self.tiers["Success"],
            fact_clue=self.fact_clue,
            follow_up_clue=self.mission_clue,
        )
        AnswerSacrificeLine.objects.create(answer=answer, facet=self.silk, text="[silk line]")
        body = self.body()
        self.assertIn("Ombrin codex clue · Codex Entry · Automatic", body)
        self.assertIn("Grants the codex entry Hidden entry, which is not public", body)
        self.assertIn("Assigns the mission", body)
        self.assertIn("[staff-authored answer text] [silk line]", body)  # the preview
        self.assertIn("A clue came with it: Ombrin codex clue.", body)
        self.assertIn("The clue&#x27;s target is reachable only through clues.", body)

    def test_the_being_and_service_pages_link_here(self) -> None:
        self.client.force_login(self.author)
        change = self.client.get(
            reverse("admin:arxii_worshippedbeing_change", args=[self.being.pk])
        )
        self.assertContains(change, reverse("admin_answer_builder", args=[self.being.pk]))
        service = self.body(reverse("admin_being_service", args=[self.being.pk]))
        self.assertIn("Open in Answer builder", service)
        self.assertIn("0 of 5 outcome tiers written", service)

    def test_an_unlinked_operator_sees_setup_and_saves_nothing(self) -> None:
        self.client.force_login(self.unlinked)
        self.client.post(self.url(), self.post_data())
        self.assertFalse(Answer.objects.exists())


class AnswerBuilderSaveTests(AnswerBuilderTestCase):
    def test_one_save_writes_the_answer_and_its_sacrifice_lines(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(self.url(), self.post_data())

        answer = Answer.objects.get()
        self.assertRedirects(
            response, self.url(answer=str(answer.pk)), fetch_redirect_response=False
        )
        self.assertEqual(
            (answer.being, answer.pledge, answer.outcome_tier),
            (self.being, self.pledge, self.tiers["Success"]),
        )
        self.assertEqual(
            (answer.fact_clue, answer.follow_up_clue), (self.fact_clue, self.mission_clue)
        )
        self.assertEqual(answer.weight, 2)
        self.assertEqual(answer.written_by, self.writer)
        self.assertEqual(answer.sacrifice_lines.get().facet, self.silk)

    def test_a_fact_below_success_is_refused(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(self.url("Partial Success"), self.post_data("Partial Success"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fact text is allowed on Success and Critical Success only.")
        self.assertFalse(Answer.objects.exists())

    def test_a_follow_up_clue_on_failure_is_refused(self) -> None:
        self.client.force_login(self.author)
        data = self.post_data("Failure", **{"answer-fact_text": "", "answer-fact_clue": ""})
        response = self.client.post(self.url("Failure"), data)
        self.assertContains(response, "A follow-up clue is allowed on Partial Success and above")
        self.assertFalse(Answer.objects.exists())

    def test_a_mission_clue_cannot_state_the_fact(self) -> None:
        self.client.force_login(self.author)
        data = self.post_data(**{"answer-fact_clue": str(self.mission_clue.pk)})
        response = self.client.post(self.url(), data)
        self.assertContains(response, "A fact clue must point at a Codex entry or a secret.")

    def test_save_and_edit_the_next_tier(self) -> None:
        self.client.force_login(self.author)
        data = self.post_data(save_next_tier="Save and edit Critical Success")
        del data["save_continue"]
        response = self.client.post(self.url(), data)
        self.assertRedirects(response, self.url("Critical Success"), fetch_redirect_response=False)

    def test_a_general_answer_has_no_pledge_type(self) -> None:
        self.client.force_login(self.author)
        self.client.post(self.url(pledge="none"), self.post_data(pledge="none"))
        self.assertIsNone(Answer.objects.get().pledge)

    def test_mark_reviewed_and_delete(self) -> None:
        answer = AnswerFactory(
            being=self.being, pledge=self.pledge, outcome_tier=self.tiers["Success"]
        )
        self.client.force_login(self.author)
        self.client.post(reverse("admin_answer_builder_review", args=[self.being.pk, answer.pk]))
        self.assertEqual(Answer.objects.get(pk=answer.pk).reviewed_by, self.writer)
        self.client.post(reverse("admin_answer_builder_delete", args=[self.being.pk, answer.pk]))
        self.assertFalse(Answer.objects.filter(pk=answer.pk).exists())

    def test_a_held_answer_cannot_be_deleted(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.worship.pledge_services import take_pledge

        answer = AnswerFactory(
            being=self.being, pledge=self.pledge, outcome_tier=self.tiers["Success"]
        )
        details = take_pledge(CharacterSheetFactory(), self.pledge)
        PendingAnswer.objects.create(
            character_sheet=details.character_sheet, answer=answer, pledge_details=details
        )
        self.client.force_login(self.author)
        self.client.post(reverse("admin_answer_builder_delete", args=[self.being.pk, answer.pk]))
        self.assertTrue(Answer.objects.filter(pk=answer.pk).exists())


class AnswerBuilderStylingTest(AnswerBuilderTestCase):
    """Every rule the page's layout needs must reach the page (#3667's guard)."""

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")
    ADMIN_PROVIDED_CLASSES = frozenset(
        {
            "module",
            "aligned",
            "help",
            "errornote",
            "errors",
            "breadcrumbs",
            "submit-row",
            "button",
            "default",
            "tuning-table",
            "object-tools",
            "form-row",
            "flex-container",
            "inline-group",
            "vCheckboxLabel",
        }
    )

    def test_the_page_links_the_stylesheets_its_layout_needs(self) -> None:
        linked = stylesheet_hrefs(self.body())
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertEqual(missing, [], f"linked: {linked}")

    def test_every_class_the_page_emits_has_a_rule_that_reaches_the_page(self) -> None:
        AnswerFactory(being=self.being, pledge=self.pledge, outcome_tier=self.tiers["Success"])
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/answer_builder"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            emitted |= emitted_classes(path)
        css = reachable_css(self.body())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")
