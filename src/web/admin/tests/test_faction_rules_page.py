"""The Faction Rules page and the Placement page (#4361)."""

from datetime import timedelta
from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import CharacterFactory
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CauseKind, OpponentTier
from world.combat.factories import CreatureTemplateFactory
from world.mechanics.factories import PropertyFactory
from world.missions.factories import MissionOptionOpponentLineFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    OrganizationReputationFactory,
    SocietyFactory,
)
from world.standoffs.constants import DriveStrength
from world.standoffs.factories import CreatureDriveFactory, FactionRuleFactory
from world.standoffs.models import (
    FactionRule,
    OpponentLineDrive,
    OpponentLineFactionRuleSuppression,
)
from world.stories.factories import BeatOpponentLineFactory

TEMPLATES = Path(__file__).resolve().parents[2] / "templates/admin"
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
HONORED = 600


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class _Seed(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.author = _superuser("frauthor")
        cls.society = SocietyFactory(name="PLACEHOLDER Riverland")
        cls.parent = OrganizationFactory(name="PLACEHOLDER Guilds", society=cls.society)
        cls.company = OrganizationFactory(
            name="PLACEHOLDER Company", parent_org=cls.parent, society=cls.society
        )
        cls.harbor = OrganizationFactory(name="PLACEHOLDER Harbor", society=cls.society)
        cls.template = CreatureTemplateFactory(
            name="PLACEHOLDER Sellsword",
            tier=OpponentTier.MOOK,
            cause=CauseKind.ORDERS,
            organization=cls.company,
        )
        cls.greedy = PropertyFactory(name="PLACEHOLDER Greedy")
        cls.fearful = PropertyFactory(name="PLACEHOLDER Fearful")
        CreatureDriveFactory(
            creature_template=cls.template, property=cls.greedy, strength=DriveStrength.MAJOR
        )
        CreatureDriveFactory(
            creature_template=cls.template, property=cls.fearful, strength=DriveStrength.MINOR
        )
        cls.associated_rule = FactionRuleFactory(
            creature_template=None,
            organization=cls.company,
            rule={"leaf": "associated_with_org", "params": {"org": cls.company.name}},
            difficulty_shift_bands=-1,
        )
        cls.harbor_rule = FactionRuleFactory(
            creature_template=None,
            organization=cls.company,
            rule={
                "leaf": "min_org_reputation",
                "params": {"org": cls.harbor.name, "tier": "honored"},
            },
        )
        cls.parent_rule = FactionRuleFactory(
            creature_template=None, organization=cls.parent, rule={}
        )
        cls.society_rule = FactionRuleFactory(creature_template=None, society=cls.society, rule={})
        cls.line = BeatOpponentLineFactory(creature_template=cls.template, count=6)

    def get(self, url: str, query: dict | None = None) -> str:
        self.client.force_login(self.author)
        response = self.client.get(url, query or {})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class FactionRulesPageTests(_Seed):
    def url(self) -> str:
        return reverse("admin_faction_rules_organization", args=[self.company.pk])

    def test_the_page_lists_the_rules_the_inherited_ones_and_the_reach(self) -> None:
        body = self.get(self.url())
        self.assertIn("Faction rules: PLACEHOLDER Company", body)
        self.assertIn("associated_with_org: PLACEHOLDER Company", body)
        self.assertIn("PLACEHOLDER Guilds", body)  # the parent's rule, inherited
        self.assertIn("PLACEHOLDER Riverland", body)  # the society's rule
        self.assertIn("PLACEHOLDER Sellsword", body)  # an affiliated template it reaches
        self.assertIn("pred-host", body)  # the predicate widget, not a raw JSON field

    def test_the_change_pages_link_here(self) -> None:
        self.client.force_login(self.author)
        response = self.client.get(
            reverse("admin:arxii_organization_change", args=[self.company.pk])
        )
        self.assertContains(response, self.url())
        response = self.client.get(reverse("admin:arxii_society_change", args=[self.society.pk]))
        self.assertContains(
            response, reverse("admin_faction_rules_society", args=[self.society.pk])
        )

    def test_the_character_test_says_why_each_rule_matched(self) -> None:
        sheet = CharacterSheetFactory(character=CharacterFactory(db_key="PLACEHOLDER Ottilie"))
        persona = sheet.primary_persona
        membership = OrganizationMembershipFactory(persona=persona, organization=self.company)
        membership.left_at = timezone.now() - timedelta(days=100)
        membership.save(update_fields=["left_at"])
        OrganizationReputationFactory(persona=persona, organization=self.harbor, value=HONORED)
        body = self.get(self.url(), {"character": "PLACEHOLDER Ottilie"})
        self.assertIn("association: formerly a member of PLACEHOLDER Company", body)
        self.assertIn("PLACEHOLDER Harbor holds you in high regard (Honored)", body)

    def test_an_unknown_character_is_named_back(self) -> None:
        body = self.get(self.url(), {"character": "PLACEHOLDER Nobody"})
        self.assertIn("No character is called", body)

    def test_one_save_writes_the_organizations_rules(self) -> None:
        self.client.force_login(self.author)
        data = {
            "rules-TOTAL_FORMS": "3",
            "rules-INITIAL_FORMS": "2",
            "rules-MIN_NUM_FORMS": "0",
            "rules-MAX_NUM_FORMS": "1000",
            "rules-0-id": str(self.associated_rule.pk),
            "rules-0-organization": str(self.company.pk),
            "rules-0-rule": (
                '{"leaf": "associated_with_org", "params": {"org": "PLACEHOLDER Company"}}'
            ),
            "rules-0-difficulty_shift_bands": "-2",
            "rules-0-drive_shift": "0",
            "rules-0-cause_effect": "none",
            "rules-0-angle_text": "PLACEHOLDER angle",
            "rules-0-revealed_text": "",
            "rules-1-id": str(self.harbor_rule.pk),
            "rules-1-organization": str(self.company.pk),
            "rules-1-rule": "{}",
            "rules-1-difficulty_shift_bands": "0",
            "rules-1-drive_shift": "0",
            "rules-1-cause_effect": "none",
            "rules-1-DELETE": "on",
            "rules-2-organization": str(self.company.pk),
            "rules-2-rule": (
                '{"leaf": "max_org_reputation", "params": {"org": "PLACEHOLDER Harbor", '
                '"tier": "despised"}}'
            ),
            "rules-2-difficulty_shift_bands": "-1",
            "rules-2-drive_shift": "0",
            "rules-2-cause_effect": "none",
            "rules-2-angle_text": "PLACEHOLDER enemy angle",
            "save_continue": "Save and continue editing",
        }
        response = self.client.post(self.url(), data)
        self.assertRedirects(response, self.url(), fetch_redirect_response=False)
        rules = list(FactionRule.objects.filter(organization=self.company).order_by("pk"))
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0].difficulty_shift_bands, -2)
        self.assertEqual(rules[1].rule["leaf"], "max_org_reputation")

    def test_a_malformed_test_is_refused(self) -> None:
        self.client.force_login(self.author)
        data = {
            "rules-TOTAL_FORMS": "1",
            "rules-INITIAL_FORMS": "0",
            "rules-MIN_NUM_FORMS": "0",
            "rules-MAX_NUM_FORMS": "1000",
            "rules-0-organization": str(self.company.pk),
            "rules-0-rule": '{"leaf": "max_org_reputation", "params": {"org": "x", "tier": "?"}}',
            "rules-0-difficulty_shift_bands": "0",
            "rules-0-drive_shift": "0",
            "rules-0-cause_effect": "none",
            "save": "Save",
        }
        response = self.client.post(self.url(), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(FactionRule.objects.filter(organization=self.company).count(), 2)


class PlacementPageTests(_Seed):
    def url(self) -> str:
        return reverse("admin_placement_beat", args=[self.line.pk])

    def test_the_page_shows_template_values_and_inherited_rules(self) -> None:
        body = self.get(self.url())
        self.assertIn("Placement: PLACEHOLDER Sellsword x6", body)
        self.assertIn("(same: Major)", body)  # the template's strength beside the pick
        self.assertIn("(template: Orders)", body)
        self.assertIn("PLACEHOLDER Guilds", body)  # an inherited rule and its source
        self.assertIn("6 PLACEHOLDER Sellsword. Cause Orders, margin 0.", body)

    def test_the_beat_inline_links_here(self) -> None:
        self.client.force_login(self.author)
        response = self.client.get(reverse("admin:arxii_beat_change", args=[self.line.beat_id]))
        self.assertContains(response, self.url())

    def test_one_save_writes_the_line_its_drives_and_its_switch_offs(self) -> None:
        self.client.force_login(self.author)
        added = PropertyFactory(name="PLACEHOLDER Prudent")
        data = {
            "opens_as_standoff": "on",
            "cause_override": CauseKind.PREDATION,
            "cause_margin_override": "15",
            "organization": "",
            f"drive_{self.greedy.pk}": str(DriveStrength.DEFINING),
            f"drive_{self.fearful.pk}": "remove",
            "added-TOTAL_FORMS": "1",
            "added-INITIAL_FORMS": "0",
            "added-MIN_NUM_FORMS": "0",
            "added-MAX_NUM_FORMS": "1000",
            "added-0-property": str(added.pk),
            "added-0-strength": str(DriveStrength.MINOR),
            "switched_off": [str(self.society_rule.pk)],
            "save": "Save",
        }
        response = self.client.post(self.url(), data)
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.line.refresh_from_db()
        self.assertTrue(self.line.opens_as_standoff)
        self.assertEqual(
            (self.line.cause_override, self.line.cause_margin_override), (CauseKind.PREDATION, 15)
        )
        self.assertEqual(
            dict(OpponentLineDrive.objects.values_list("property_id", "strength")),
            {
                self.greedy.pk: DriveStrength.DEFINING,
                self.fearful.pk: None,
                added.pk: DriveStrength.MINOR,
            },
        )
        self.assertEqual(
            list(OpponentLineFactionRuleSuppression.objects.values_list("faction_rule", flat=True)),
            [self.society_rule.pk],
        )

    def test_a_mission_option_line_has_its_own_placement_page(self) -> None:
        line = MissionOptionOpponentLineFactory(creature_template=self.template)
        url = reverse("admin_placement_mission", args=[line.pk])
        body = self.get(url)
        self.assertIn("level band", body)
        self.client.force_login(self.author)
        response = self.client.get(
            reverse("admin:arxii_missionoptionopponentline_change", args=[line.pk])
        )
        self.assertContains(response, url)


class StylingTests(_Seed):
    """Every class the new pages emit has a rule that reaches the page (#3667's guard)."""

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")

    def _check(self, url: str, template_dir: str) -> None:
        body = self.get(url)
        linked = stylesheet_hrefs(body)
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertEqual(missing, [], f"linked: {linked}")
        emitted: set[str] = set()
        for path in sorted((TEMPLATES / template_dir).glob("*.html")):
            emitted |= emitted_classes(path)
        css = reachable_css(body)
        undefined = sorted(
            token for token in emitted - ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")

    def test_the_faction_rules_page(self) -> None:
        self._check(
            reverse("admin_faction_rules_organization", args=[self.company.pk]), "faction_rules"
        )

    def test_the_placement_page(self) -> None:
        self._check(reverse("admin_placement_beat", args=[self.line.pk]), "standoff_placement")
