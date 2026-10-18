"""The Standoff Profile Builder (#4354): one creature's cause, drives and faction rules."""

from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind, OpponentTier
from world.combat.factories import CreatureTemplateFactory
from world.combat.models import CreatureTemplate
from world.conditions.factories import CapabilityTypeFactory
from world.contributors.factories import ContentContributorFactory
from world.mechanics.factories import ApplicationFactory, PropertyFactory
from world.standoffs.constants import CauseEffect, DriveStrength
from world.standoffs.factories import (
    CreatureDriveFactory,
    FactionRuleFactory,
    StandoffApproachFactory,
)
from world.standoffs.models import CreatureDrive, FactionRule
from world.stories.factories import BeatOpponentLineFactory


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class ProfileBuilderTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("spauthor")
        cls.writer = ContentContributorFactory(name="Standoff Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("spunlinked")
        cls.template = CreatureTemplateFactory(
            name="Gate Sellsword", tier=OpponentTier.MOOK, cause=CauseKind.NONE
        )
        cls.greed = PropertyFactory(name="PLACEHOLDER greedy", description="PLACEHOLDER means")
        cls.fear = PropertyFactory(name="PLACEHOLDER fearful")
        cls.drive = CreatureDriveFactory(
            creature_template=cls.template, property=cls.greed, strength=DriveStrength.MAJOR
        )
        capability = CapabilityTypeFactory()
        ApplicationFactory(capability=capability, target_property=cls.greed)
        cls.approach = StandoffApproachFactory(
            name="PLACEHOLDER bribe", capability=capability, check_type=CheckTypeFactory()
        )
        cls.rule = FactionRuleFactory(creature_template=cls.template, rule={})
        BeatOpponentLineFactory(creature_template=cls.template, count=6, opens_as_standoff=True)

    def url(self) -> str:
        return reverse("admin_standoff_profile", args=[self.template.pk])

    def body(self, account=None, query: str = "") -> str:
        self.client.force_login(account or self.author)
        response = self.client.get(self.url() + query)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def post_data(self, **overrides) -> dict:
        data = {
            "cause": CauseKind.ORDERS,
            "cause_margin_percent": "10",
            "drives-TOTAL_FORMS": "2",
            "drives-INITIAL_FORMS": "1",
            "drives-MIN_NUM_FORMS": "0",
            "drives-MAX_NUM_FORMS": "1000",
            "drives-0-id": str(self.drive.pk),
            "drives-0-creature_template": str(self.template.pk),
            "drives-0-property": str(self.greed.pk),
            "drives-0-strength": str(DriveStrength.DEFINING),
            "drives-1-creature_template": str(self.template.pk),
            "drives-1-property": str(self.fear.pk),
            "drives-1-strength": str(DriveStrength.MINOR),
            "rules-TOTAL_FORMS": "2",
            "rules-INITIAL_FORMS": "1",
            "rules-MIN_NUM_FORMS": "0",
            "rules-MAX_NUM_FORMS": "1000",
            "rules-0-id": str(self.rule.pk),
            "rules-0-creature_template": str(self.template.pk),
            "rules-0-rule": "{}",
            "rules-0-difficulty_shift_bands": "1",
            "rules-0-drive_shift": "0",
            "rules-0-cause_effect": "none",
            "rules-0-angle_text": "PLACEHOLDER angle",
            "rules-0-revealed_text": "",
            "rules-1-creature_template": str(self.template.pk),
            "rules-1-rule": '{"leaf": "has_capability", "params": {"name": "Warding"}}',
            "rules-1-difficulty_shift_bands": "-1",
            "rules-1-drive_shift": "0",
            "rules-1-cause_effect": "provoke",
            "rules-1-angle_text": "PLACEHOLDER second angle",
            "rules-1-revealed_text": "PLACEHOLDER revealed",
            "save": "Save",
        }
        data.update(overrides)
        return data


class ProfileBuilderPageTests(ProfileBuilderTestCase):
    def test_the_page_shows_the_profile_and_its_context(self) -> None:
        body = self.body()
        self.assertIn("Standoff Profile Builder", body)
        self.assertIn("PLACEHOLDER means", body)  # what the drive means
        self.assertIn("PLACEHOLDER bribe", body)  # the approach that hits it, and its grade
        self.assertIn("used in 1 placement", body)
        self.assertIn("opens as a standoff", body)
        self.assertIn("Cause check", body)

    def test_the_preview_reads_the_example_level_from_the_query(self) -> None:
        body = self.body(query="?level=9&party=3")
        self.assertIn("A level 9 character", body)

    def test_the_creature_change_page_links_here(self) -> None:
        self.client.force_login(self.author)
        response = self.client.get(
            reverse("admin:arxii_creaturetemplate_change", args=[self.template.pk])
        )
        self.assertContains(response, self.url())
        self.assertNotContains(response, "Faction rules")  # the stock inline is gone

    def test_an_unlinked_operator_sees_setup_and_saves_nothing(self) -> None:
        self.client.force_login(self.unlinked)
        self.client.post(self.url(), self.post_data())
        self.template.refresh_from_db()
        self.assertEqual(self.template.cause, CauseKind.NONE)


class ProfileBuilderSaveTests(ProfileBuilderTestCase):
    def test_save_and_continue_stays_on_the_builder(self) -> None:
        self.client.force_login(self.author)
        data = self.post_data()
        data.pop("save")
        data["save_continue"] = "Save and continue editing"
        response = self.client.post(self.url(), data)
        self.assertRedirects(response, self.url(), fetch_redirect_response=False)

    def test_one_save_writes_the_creature_its_drives_and_its_rules(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(self.url(), self.post_data())
        self.assertRedirects(
            response,
            reverse("admin:arxii_creaturetemplate_change", args=[self.template.pk]),
            fetch_redirect_response=False,
        )
        self.template.refresh_from_db()
        self.assertEqual(
            (self.template.cause, self.template.cause_margin_percent), (CauseKind.ORDERS, 10)
        )
        self.assertEqual(self.template.written_by, self.writer)
        drives = {
            d.property_id: d.strength
            for d in CreatureDrive.objects.filter(creature_template=self.template)
        }
        self.assertEqual(
            drives, {self.greed.pk: DriveStrength.DEFINING, self.fear.pk: DriveStrength.MINOR}
        )
        rules = list(FactionRule.objects.filter(creature_template=self.template).order_by("pk"))
        self.assertEqual(
            [r.angle_text for r in rules], ["PLACEHOLDER angle", "PLACEHOLDER second angle"]
        )
        self.assertEqual(rules[1].cause_effect, CauseEffect.PROVOKE)
        self.assertEqual(rules[1].rule["leaf"], "has_capability")

    def test_a_malformed_rule_is_refused_and_nothing_saves(self) -> None:
        self.client.force_login(self.author)
        response = self.client.post(
            self.url(), self.post_data(**{"rules-1-rule": '{"op": "XOR", "of": []}'})
        )
        self.assertEqual(response.status_code, 200)
        stored = CreatureTemplate.objects.filter(pk=self.template.pk).values_list(
            "cause", flat=True
        )
        self.assertEqual(list(stored), [CauseKind.NONE])
        # The refused edit does not linger in the identity map either.
        self.assertEqual(CreatureTemplate.objects.get(pk=self.template.pk).cause, CauseKind.NONE)
        self.assertEqual(FactionRule.objects.filter(creature_template=self.template).count(), 1)


class ProfileBuilderStylingTest(ProfileBuilderTestCase):
    """Every rule the page's layout needs must reach the page (#3667's guard)."""

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")
    ADMIN_PROVIDED_CLASSES = frozenset(
        {
            "module",
            "help",
            "errornote",
            "breadcrumbs",
            "submit-row",
            "button",
            "default",
            "tuning-table",
        }
    )

    def test_the_page_links_the_stylesheets_its_layout_needs(self) -> None:
        linked = stylesheet_hrefs(self.body())
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertEqual(missing, [], f"linked: {linked}")

    def test_every_class_the_page_emits_has_a_rule_that_reaches_the_page(self) -> None:
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/standoff_profile"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            emitted |= emitted_classes(path)
        css = reachable_css(self.body())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")
