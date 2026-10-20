"""The Trial builder (#4513, slice 2 of #4343): a mission option's trial on one page.

Names are invented and staff-authored copy is left as bracketed slots. The rules that refuse a
row are slice 1's (``world/checks/tests/test_trial_rules.py`` proves them); these tests prove
the page asks them, shows their messages, and saves nothing when they refuse.
"""

from pathlib import Path
import re

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.tests.test_distinction_builder import (
    emitted_classes,
    reachable_css,
    stylesheet_hrefs,
)
from world.checks.constants import EffectType
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.models import Consequence, ConsequenceEffect
from world.codex.factories import CodexEntryFactory
from world.conditions.factories import ConditionTemplateFactory
from world.contributors.factories import ContentContributorFactory
from world.magic.factories import GiftFactory, TechniqueFactory
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionOptionRoute
from world.npc_services.factories import TrainOfferDetailsFactory
from world.progression.factories import CodexKnowledgeRequirementFactory
from world.societies.factories import OrganizationFactory
from world.traits.factories import CheckOutcomeFactory

_OUTCOMES = (
    ("Critical Success", 2),
    ("Success", 1),
    ("Partial Success", 0),
    ("Failure", -1),
    ("Critical Failure", -2),
)


def _superuser(name: str) -> AccountDB:
    return AccountDB.objects.create_superuser(name, f"{name}@example.com", "pw-123456")


class TrialBuilderCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = _superuser("tbauthor")
        cls.writer = ContentContributorFactory(name="Trial Writer")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = _superuser("tbunlinked")
        cls.tiers = {
            name: CheckOutcomeFactory(name=name, success_level=level) for name, level in _OUTCOMES
        }
        cls.technique = TechniqueFactory(name="Read the Cup", gift=GiftFactory(name="Sight"))
        cls.entry = CodexEntryFactory(name="What her sight truly sees")
        CodexKnowledgeRequirementFactory(codex_entry=cls.entry, path=None, technique=cls.technique)
        cls.dead = CodexEntryFactory(name="The dead poisoner")
        cls.fever = ConditionTemplateFactory(name="Crypt fever")
        template = MissionTemplateFactory(name="The poisoner's crypt")
        cls.node = MissionNodeFactory(template=template, key="jars", is_entry=True)
        cls.next_node = MissionNodeFactory(template=template, key="stairs")
        cls.option = MissionOptionFactory(
            node=cls.node,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=CheckTypeFactory(name="Name the poisons"),
            authored_base_risk=35,
        )

    # -- helpers ---------------------------------------------------------------------

    def url(self, option=None) -> str:
        return reverse("admin_trial_builder", args=[(option or self.option).pk])

    def tier_key(self, name: str, field: str) -> str:
        return f"tier{self.tiers[name].pk}-{field}"

    def valid_post(self, **overrides: str) -> dict[str, str]:
        """The demo's trial: Success and Critical Success open the technique and cost a scar."""
        data = {
            "trial-codex_entry": str(self.entry.pk),
            "trial-technique": str(self.technique.pk),
            "trial-meter_size": "40",
        }
        for name, _ in _OUTCOMES:
            data[self.tier_key(name, "label")] = f"Crypt jars, {name}"
            if name != "Critical Failure":
                data[self.tier_key(name, "outcome_text")] = f"[staff-authored {name} text]"
            data[self.tier_key(name, "codex_mode")] = "none"
            data[self.tier_key(name, "cost_kind")] = "none"
            data[self.tier_key(name, "reward_kind")] = "none"
        crit = "Critical Success"
        data[self.tier_key(crit, "codex_mode")] = "known"
        data[self.tier_key(crit, "grant_outright")] = "on"
        data[self.tier_key(crit, "cost_kind")] = "scar"
        data[self.tier_key(crit, "cost_severity")] = "2"
        data[self.tier_key(crit, "reward_kind")] = "cosmetic"
        data[self.tier_key(crit, "reward_tier")] = "3"
        data[self.tier_key(crit, "next_node")] = str(self.next_node.pk)
        win = "Success"
        data[self.tier_key(win, "codex_mode")] = "known"
        data[self.tier_key(win, "training_points")] = "15"
        data[self.tier_key(win, "cost_kind")] = "scar"
        data[self.tier_key(win, "cost_severity")] = "2"
        partial = "Partial Success"
        data[self.tier_key(partial, "codex_mode")] = "lead"
        data[self.tier_key(partial, "codex_entry")] = str(self.dead.pk)
        data[self.tier_key(partial, "cost_kind")] = "condition"
        data[self.tier_key(partial, "cost_template")] = str(self.fever.pk)
        data[self.tier_key(partial, "cost_severity")] = "1"
        failure = "Failure"
        data[self.tier_key(failure, "cost_kind")] = "condition"
        data[self.tier_key(failure, "cost_template")] = str(self.fever.pk)
        data[self.tier_key(failure, "cost_severity")] = "2"
        data.update(overrides)
        return data

    def post(self, data: dict[str, str], *, user=None, **extra: str):
        self.client.force_login(user or self.author)
        return self.client.post(self.url(), {**data, **extra})

    def routes(self):
        return {
            r.outcome_tier.name: r
            for r in MissionOptionRoute.objects.filter(option=self.option).select_related(
                "outcome_tier", "consequence"
            )
        }

    def effect_types(self, name: str) -> list[str]:
        route = self.routes()[name]
        return list(
            route.consequence.effects.order_by("execution_order").values_list(
                "effect_type", flat=True
            )
        )


class SavingATrialTests(TrialBuilderCase):
    def test_the_demo_trial_saves_in_one_post_with_each_tiers_effects_in_order(self) -> None:
        response = self.post(self.valid_post())
        self.assertEqual(response.status_code, 302, response.content[:2000])
        routes = self.routes()
        self.assertEqual(set(routes), {"Critical Success", "Success", "Partial Success", "Failure"})
        self.assertEqual(
            self.effect_types("Critical Success"),
            [
                EffectType.GRANT_CODEX,
                EffectType.TECHNIQUE_TRAINING,
                EffectType.MAGICAL_SCARS,
                EffectType.MAGICAL_SCARS,
            ],
        )
        crit = routes["Critical Success"]
        self.assertEqual(crit.target_node, self.next_node)
        self.assertEqual(crit.outcome_text, "[staff-authored Critical Success text]")
        effects = list(crit.consequence.effects.order_by("execution_order"))
        self.assertEqual([e.execution_order for e in effects], [0, 1, 2, 3])
        self.assertTrue(effects[0].grants_known)
        self.assertEqual(effects[0].codex_entry, self.entry)
        self.assertTrue(effects[1].grants_technique_outright)
        self.assertEqual(effects[1].technique, self.technique)
        self.assertEqual(effects[1].training_meter_size, 40)
        self.assertFalse(effects[2].scar_is_cosmetic)
        self.assertTrue(effects[3].scar_is_cosmetic)
        self.assertEqual(effects[3].condition_severity, 3)
        success = list(routes["Success"].consequence.effects.order_by("execution_order"))
        self.assertEqual(success[1].training_points, 15)
        self.assertEqual(success[1].training_meter_size, 40)
        partial = list(routes["Partial Success"].consequence.effects.order_by("execution_order"))
        self.assertFalse(partial[0].grants_known)
        self.assertEqual(partial[0].codex_entry, self.dead)

    def test_every_saved_row_is_credited_to_the_operators_contributor(self) -> None:
        self.post(self.valid_post())
        crit = self.routes()["Critical Success"]
        rows = [crit, crit.consequence, *crit.consequence.effects.all()]
        self.assertEqual({row.written_by for row in rows}, {self.writer})

    def test_a_tier_left_empty_keeps_no_route(self) -> None:
        self.post(self.valid_post())
        self.assertNotIn("Critical Failure", self.routes())

    def test_reopening_shows_what_was_saved_and_a_second_save_replaces_the_effects(self) -> None:
        self.post(self.valid_post())
        response = self.client.get(self.url())
        body = response.content.decode()
        self.assertContains(response, "Crypt jars, Success")
        self.assertIn(f'value="{self.entry.pk}" selected', body)
        self.assertIn('value="40"', body)
        self.post(self.valid_post())
        self.assertEqual(
            ConsequenceEffect.objects.filter(
                consequence=self.routes()["Critical Success"].consequence
            ).count(),
            4,
        )
        self.assertEqual(Consequence.objects.filter(label__startswith="Crypt jars").count(), 4)

    def test_effects_the_page_does_not_own_survive_a_save_after_the_ones_it_writes(self) -> None:
        self.post(self.valid_post())
        consequence = self.routes()["Success"].consequence
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.ADD_PROPERTY,
            execution_order=2,
            property=__import__(
                "world.mechanics.factories", fromlist=["PropertyFactory"]
            ).PropertyFactory(),
            property_value=1,
        )
        self.post(self.valid_post())
        types = list(
            consequence.effects.order_by("execution_order").values_list("effect_type", flat=True)
        )
        self.assertEqual(types[-1], EffectType.ADD_PROPERTY)
        self.assertEqual(types[0], EffectType.GRANT_CODEX)

    def test_an_unlinked_operator_sees_the_setup_guidance_and_nothing_is_saved(self) -> None:
        response = self.post(self.valid_post(), user=self.unlinked)
        self.assertContains(response, "Link a contributor first")
        self.assertFalse(MissionOptionRoute.objects.filter(option=self.option))


class RefusalTests(TrialBuilderCase):
    """Each blocking warning, refused on save with slice 1's own message; nothing is written."""

    def refused(self, message: str, **overrides: str) -> None:
        response = self.post(self.valid_post(**overrides))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message)
        self.assertContains(response, "Nothing was saved")
        self.assertFalse(MissionOptionRoute.objects.filter(option=self.option))
        self.assertFalse(Consequence.objects.filter(label__startswith="Crypt jars"))

    def test_a_technique_opening_row_with_no_cost_is_refused(self) -> None:
        self.refused(
            "opens or trains a technique and has no cost",
            **{self.tier_key("Success", "cost_kind"): "none"},
        )

    def test_a_cosmetic_scar_is_a_reward_and_never_the_cost(self) -> None:
        self.refused(
            "A cosmetic Mage Scar is a reward, not a cost",
            **{self.tier_key("Critical Success", "cost_kind"): "none"},
        )

    def test_a_row_deliberately_free_with_a_reason_passes_and_without_one_is_refused(self) -> None:
        free = {
            self.tier_key("Success", "cost_kind"): "none",
            self.tier_key("Success", "deliberately_free"): "on",
        }
        self.refused("Say why this is deliberately free of cost.", **free)
        response = self.post(
            self.valid_post(**free, **{self.tier_key("Success", "free_reason"): "[reason]"})
        )
        self.assertEqual(response.status_code, 302)

    def test_a_known_grant_below_success_is_refused(self) -> None:
        self.refused(
            "An entry is made known only at Success or Critical Success.",
            **{
                self.tier_key("Partial Success", "codex_mode"): "known",
                self.tier_key("Partial Success", "codex_entry"): str(self.dead.pk),
            },
        )

    def test_a_gating_entry_on_a_failure_route_is_refused(self) -> None:
        self.refused(
            "This entry gates a technique; it may not be granted on a Failure",
            **{
                self.tier_key("Failure", "codex_mode"): "lead",
                self.tier_key("Failure", "codex_entry"): str(self.entry.pk),
            },
        )

    def test_training_with_no_meter_size_is_refused(self) -> None:
        self.refused("give the size", **{"trial-meter_size": ""})

    def test_training_with_no_technique_picked_is_refused(self) -> None:
        self.refused("Pick the technique this trial trains", **{"trial-technique": ""})

    def test_an_ultimate_cannot_be_trained(self) -> None:
        ultimate = TechniqueFactory(name="The Last Word", is_ultimate=True)
        self.refused("only at Audere", **{"trial-technique": str(ultimate.pk)})

    def test_grant_outright_below_critical_success_is_refused(self) -> None:
        self.refused(
            "Granting outright is for Critical Success only.",
            **{self.tier_key("Success", "grant_outright"): "on"},
        )

    def test_a_cosmetic_reward_below_success_is_refused(self) -> None:
        self.refused(
            "A cosmetic Mage Scar is a reward for Success or better.",
            **{
                self.tier_key("Partial Success", "reward_kind"): "cosmetic",
                self.tier_key("Partial Success", "reward_tier"): "1",
            },
        )

    def test_a_refusal_on_the_page_names_the_tier_it_came_from(self) -> None:
        response = self.post(self.valid_post(**{self.tier_key("Success", "cost_kind"): "none"}))
        tier = self.tiers["Success"]
        self.assertContains(response, f'id="tier-errors-{tier.pk}"')
        body = response.content.decode()
        block = re.search(rf'<ul[^>]*id="tier-errors-{tier.pk}"[^>]*>(.*?)</ul>', body, re.DOTALL)
        self.assertIn("has no cost", block.group(1))


class TheRailTests(TrialBuilderCase):
    def check(self, data: dict[str, str]) -> dict:
        self.client.force_login(self.author)
        response = self.client.post(
            reverse("admin_trial_builder_check", args=[self.option.pk]), data
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_the_live_check_returns_the_blocking_message_and_writes_nothing(self) -> None:
        data = self.valid_post(**{self.tier_key("Success", "cost_kind"): "none"})
        result = self.check(data)
        self.assertIn("Blocks save: Success:", result["rail"])
        self.assertIn("has no cost", " ".join(result["tier_errors"][str(self.tiers["Success"].pk)]))
        self.assertFalse(MissionOptionRoute.objects.filter(option=self.option))

    def test_the_live_check_says_the_same_thing_the_save_does(self) -> None:
        data = self.valid_post(**{self.tier_key("Success", "cost_kind"): "none"})
        live_message = self.check(data)["tier_errors"][str(self.tiers["Success"].pk)][0]
        saved = self.post(data)
        self.assertContains(saved, live_message.replace("'", "&#x27;"))

    def test_a_valid_trial_shows_the_all_clear_line(self) -> None:
        result = self.check(self.valid_post())
        self.assertIn("carries a real cost", result["rail"])
        self.assertNotIn("Blocks save", result["rail"])

    def test_partial_points_are_an_informational_warning_not_a_block(self) -> None:
        data = self.valid_post(**{self.tier_key("Partial Success", "training_points"): "5"})
        rail = self.check(data)["rail"]
        self.assertIn("apply only to a character who already knows the entry", rail)
        self.assertNotIn("Blocks save", rail)

    def test_a_technique_nobody_teaches_is_flagged_and_an_academy_offer_clears_it(self) -> None:
        self.assertIn("No teacher or Academy offers", self.check(self.valid_post())["rail"])
        TrainOfferDetailsFactory(
            technique=self.technique,
            learn_ap_cost=30,
            offer__role__faction_affiliation=OrganizationFactory(name="[Academy]"),
        )
        rail = self.check(self.valid_post())["rail"]
        self.assertNotIn("No teacher or Academy offers", rail)
        self.assertIn("30 point meter", rail)

    def test_a_cheaper_critical_success_cost_is_flagged(self) -> None:
        data = self.valid_post(**{self.tier_key("Critical Success", "cost_severity"): "1"})
        self.assertIn("Critical Success costs less than Success", self.check(data)["rail"])

    def test_an_empty_outcome_text_is_flagged(self) -> None:
        data = self.valid_post(**{self.tier_key("Failure", "outcome_text"): ""})
        self.assertIn("Failure: outcome text is empty.", self.check(data)["rail"])

    def test_the_same_entry_made_known_elsewhere_is_listed(self) -> None:
        other = ConsequenceFactory(outcome_tier=self.tiers["Success"], label="[another route]")
        ConsequenceEffectFactory(
            consequence=other,
            effect_type=EffectType.GRANT_CODEX,
            codex_entry=self.entry,
            grants_known=True,
        )
        self.assertIn("[another route]", self.check(self.valid_post())["rail"])

    def test_the_summary_line_reads_like_the_demos(self) -> None:
        rail = self.check(self.valid_post())["rail"]
        self.assertIn(
            "knows entry, technique outright, scar tier 2, reward: cosmetic scar tier 3", rail
        )

    def test_the_page_lists_the_technique_the_entry_opens(self) -> None:
        self.post(self.valid_post())
        response = self.client.get(self.url())
        self.assertContains(response, "Read the Cup")


class ThePageTests(TrialBuilderCase):
    def test_a_non_superuser_is_refused(self) -> None:
        staff = AccountDB.objects.create_user("tbplain", "p@example.com", "pw-123456")
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_a_branch_option_has_no_trial_page(self) -> None:
        branch = MissionOptionFactory(node=self.node, option_kind=OptionKind.BRANCH)
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(self.url(branch)).status_code, 404)

    def test_a_shared_consequence_is_shown_read_only_and_left_alone(self) -> None:
        shared = ConsequenceFactory(outcome_tier=self.tiers["Failure"], label="[shared]")
        other = MissionOptionFactory(
            node=self.node,
            option_kind=OptionKind.CHECK,
            authored_check_type=self.option.authored_check_type,
        )
        MissionOptionRouteFactory(
            option=other, outcome_tier=self.tiers["Failure"], consequence=shared
        )
        MissionOptionRouteFactory(
            option=self.option, outcome_tier=self.tiers["Failure"], consequence=shared
        )
        self.client.force_login(self.author)
        response = self.client.get(self.url())
        self.assertContains(response, f'data-testid="shared-{self.tiers["Failure"].pk}"')
        self.post(self.valid_post(**{self.tier_key("Failure", "label"): "[renamed]"}))
        shared.refresh_from_db()
        self.assertEqual(shared.label, "[shared]")

    def test_the_mission_option_page_links_to_the_builder(self) -> None:
        self.client.force_login(self.author)
        response = self.client.get(
            reverse("admin:arxii_missionoption_change", args=[self.option.pk])
        )
        self.assertContains(response, self.url())
        self.assertContains(response, "Open in Trial builder")

    def test_the_index_opens_an_option_by_id_and_lists_options_with_trials(self) -> None:
        self.client.force_login(self.author)
        index = reverse("admin_trial_builder_index")
        self.assertRedirects(
            self.client.get(index, {"option": str(self.option.pk)}),
            self.url(),
            fetch_redirect_response=False,
        )
        self.assertNotContains(self.client.get(index), self.option.key)
        self.post(self.valid_post())
        self.assertContains(self.client.get(index), self.option.key)

    def test_deleting_the_trial_routes_removes_them_and_their_consequences(self) -> None:
        self.post(self.valid_post())
        self.client.force_login(self.author)
        self.client.post(reverse("admin_trial_builder_delete", args=[self.option.pk]))
        self.assertFalse(MissionOptionRoute.objects.filter(option=self.option))
        self.assertFalse(Consequence.objects.filter(label__startswith="Crypt jars"))


class StylingTests(TrialBuilderCase):
    """A rule has to REACH the page, not just a class name appear in the markup (#3667)."""

    REQUIRED_STYLESHEETS = ("admin/css/base.css", "admin/css/forms.css", "admin/css/widgets.css")
    ADMIN_PROVIDED_CLASSES = frozenset(
        {
            "module",
            "aligned",
            "help",
            "errornote",
            "errorlist",
            "breadcrumbs",
            "submit-row",
            "button",
            "default",
            "tuning-panel",
            "form-row",
            "flex-container",
            "object-tools",
            "vCheckboxLabel",
            "vTextField",
            "vLargeTextField",
            "vIntegerField",
            "errors",
        }
    )

    def body(self) -> str:
        self.post(self.valid_post())
        return self.client.get(self.url()).content.decode()

    def test_the_page_links_the_stylesheets_its_layout_needs(self) -> None:
        linked = stylesheet_hrefs(self.body())
        missing = [s for s in self.REQUIRED_STYLESHEETS if not any(h.endswith(s) for h in linked)]
        self.assertEqual(missing, [], f"linked: {linked}")

    def test_every_class_the_page_emits_has_a_rule_that_reaches_the_page(self) -> None:
        template_dir = Path(__file__).resolve().parents[2] / "templates/admin/trial_builder"
        emitted: set[str] = set()
        for path in sorted(template_dir.glob("*.html")):
            if path.name != "index.html":
                emitted |= emitted_classes(path)
        css = reachable_css(self.body())
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")

    def test_the_page_links_its_live_check_script_and_it_exists(self) -> None:
        body = self.body()
        self.assertIn("admin/js/trial_builder.js", body)
        self.assertTrue(
            (Path(__file__).resolve().parents[2] / "static/admin/js/trial_builder.js").exists()
        )
