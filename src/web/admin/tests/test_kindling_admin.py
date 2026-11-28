"""The kindled resonances admin pages (#5124, Screen 8) render and save for a staff user."""

from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tests.support import form_data
from world.covenants.perks.constants import Situation
from world.magic.factories import (
    AffinityFactory,
    KindledStrengthTierFactory,
    KindlingConfigFactory,
    KindlingFactory,
    KindlingSituationFactory,
    ReflectionFactory,
    ResonanceFactory,
    SettlingRiteFactory,
    WeeklyMarkReturnFactory,
)
from world.magic.models import (
    AnimaRitualResonanceAward,
    KindledDeedAward,
    KindledStrengthTier,
    KindlingConfig,
    KindlingSituation,
    RallyKindlingStrength,
    WeeklyMarkReturn,
)
from world.mechanics.factories import PropertyFactory
from world.missions.factories import MissionTemplateFactory
from world.traits.factories import CheckOutcomeFactory

PLAY_ROWS = ("kindling", "reflection", "settlingrite")


class KindlingAdminPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser(
            "kindling5124", "kindling5124@example.com", "pw-123456"
        )
        cls.affinity = AffinityFactory()
        cls.resonance = ResonanceFactory(affinity=cls.affinity)
        KindlingSituationFactory(resonance=None, for_affinity=cls.affinity)
        KindlingSituationFactory(resonance=cls.resonance)
        cls.tiers = [
            KindledStrengthTierFactory(rank=1, name="Faint"),
            KindledStrengthTierFactory(rank=2, name="Strong"),
            KindledStrengthTierFactory(rank=3, name="Blazing"),
        ]
        cls.config = KindlingConfigFactory()
        cls.kindling = KindlingFactory()
        cls.reflection = ReflectionFactory()
        cls.rite = SettlingRiteFactory()
        cls.mission = MissionTemplateFactory()

    def test_every_page_renders(self) -> None:
        self.client.force_login(self.staff)
        pages = [reverse(f"admin:arxii_{label}_changelist") for label in PLAY_ROWS]
        pages += [
            reverse("admin:arxii_missiontheme_changelist"),
            reverse("admin:arxii_missiontheme_add"),
            reverse("admin:arxii_kindlingconfig_change", args=[self.config.pk]),
            reverse("admin:arxii_resonance_change", args=[self.resonance.pk]),
            reverse("admin:arxii_affinity_change", args=[self.affinity.pk]),
            reverse("admin:arxii_driftcorrectionconfig_changelist"),
            reverse("admin:arxii_missiontemplate_change", args=[self.mission.pk]),
            reverse("admin:arxii_vowsituationalperk_add"),
            reverse("admin:arxii_missionoption_add"),
            reverse("admin:arxii_kindling_change", args=[self.kindling.pk]),
            reverse("admin:arxii_reflection_change", args=[self.reflection.pk]),
            reverse("admin:arxii_settlingrite_change", args=[self.rite.pk]),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_play_rows_cannot_be_added_by_hand(self) -> None:
        self.client.force_login(self.staff)
        for label in PLAY_ROWS:
            with self.subTest(label=label):
                response = self.client.get(reverse(f"admin:arxii_{label}_add"))
                self.assertEqual(response.status_code, 403)

    def test_kindling_config_list_opens_the_one_page(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:arxii_kindlingconfig_changelist"))
        self.assertRedirects(
            response, reverse("admin:arxii_kindlingconfig_change", args=[self.config.pk])
        )

    def test_resonance_page_names_strengths_and_the_affinity_list(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("admin:arxii_resonance_change", args=[self.resonance.pk])
        )
        inline = response.context["inline_admin_formsets"][0].formset
        choices = list(inline.forms[0].fields["strength"].choices)
        self.assertEqual(
            choices, [("", "From the source"), (1, "Faint"), (2, "Strong"), (3, "Blazing")]
        )
        self.assertContains(response, f"Also kindled by the {self.affinity.name} affinity")

    def test_the_situation_inline_has_the_demos_four_columns_and_no_raw_caption(self) -> None:
        self.client.force_login(self.staff)
        for url in (
            reverse("admin:arxii_resonance_change", args=[self.resonance.pk]),
            reverse("admin:arxii_affinity_change", args=[self.affinity.pk]),
        ):
            with self.subTest(url=url):
                page = self.client.get(url).content.decode()
                headers = ("Situation", "Setting", "Strength", "Delete?")
                positions = [page.index(f">{name}</th>") for name in headers]
                self.assertEqual(positions, sorted(positions))
                self.assertNotIn("KindlingSituation(", page)
                # Every setting field is still on the page; the script shows the applicable one.
                self.assertIn('data-param="mission_theme"', page)
                self.assertIn('id="kindling-param-map"', page)

    def test_a_situation_row_saves_through_the_resonance_admin(self) -> None:
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_resonance_change", args=[self.resonance.pk])
        data = form_data(self.client.get(url))
        prefix = "kindling_situations"
        new = int(data[f"{prefix}-TOTAL_FORMS"]) - 1  # the blank extra form
        data[f"{prefix}-{new}-situation"] = Situation.IN_MELEE
        data[f"{prefix}-{new}-strength"] = "2"
        data[f"{prefix}-{new}-reason_text"] = "Held in common"
        data["_save"] = "Save"
        response = self.client.post(url, data)
        self.assertEqual(
            response.status_code, 302, response.context and response.context.get("errors")
        )
        row = KindlingSituation.objects.get(resonance=self.resonance, reason_text="Held in common")
        self.assertEqual((row.situation, row.strength), (Situation.IN_MELEE, 2))

    def test_the_config_tables_show_no_raw_caption_and_fit_the_page(self) -> None:
        RallyKindlingStrength.objects.create(outcome_tier=CheckOutcomeFactory(), strength=2)
        KindledDeedAward.objects.create(outcome_tier=CheckOutcomeFactory(), amount=4)
        self.client.force_login(self.staff)
        page = self.client.get(
            reverse("admin:arxii_kindlingconfig_change", args=[self.config.pk])
        ).content.decode()
        # Saved rows read in words wherever the model is named, never as a constructor call.
        self.assertNotIn("KindledStrengthTier(", page)
        self.assertNotIn("KindlingSituation(", page)
        self.assertIn(str(KindledStrengthTier.objects.get(rank=1)), ["Faint"])
        # The stock caption cell is hidden and the table is fitted to the module, in a rule
        # on the page itself.
        self.assertIn(".kindling-config-inline td.original p { display: none; }", page)
        self.assertIn("table-layout: fixed", page)
        self.assertEqual(page.count('class="kindling-config-inline"'), 4)

    def test_the_config_page_saves_all_its_tables_in_one_submit(self) -> None:
        self.client.force_login(self.staff)
        url = reverse("admin:arxii_kindlingconfig_change", args=[self.config.pk])
        response = self.client.get(url)
        self.assertEqual(len(response.context["inline_admin_formsets"]), 4)
        tiers = response.context["inline_admin_formsets"][0].formset
        self.assertNotIn("rank", tiers.forms[0].fields)
        self.assertEqual(len(tiers.forms), 3)
        page = response.content.decode()
        self.assertIn("Staff can rename each strength", page)
        # The demo's order: strengths, then the harm property, then Rally, then earned.
        positions = [
            page.index(text)
            for text in ("What each strength gives", "Harm property", "Rally kindles at")
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(page.index("Rally kindles at"), page.index("Earned per result"))
        self.assertLess(page.index("Earned per result"), page.index("Anima ritual earns"))
        self.assertIn("Recorded act days", page)
        data = form_data(response)
        harm = PropertyFactory()
        success, good = CheckOutcomeFactory(), CheckOutcomeFactory()
        data["harm_property"] = str(harm.pk)
        data["kindledstrengthtier-0-name"] = "Glimmer"
        data["kindledstrengthtier-0-rank"] = "9"  # not a form field: must be ignored
        data["kindledstrengthtier-0-pull_levels"] = "4"
        rally = "rallykindlingstrength"
        data[f"{rally}-0-outcome_tier"] = str(success.pk)
        data[f"{rally}-0-strength"] = "2"
        earned = "kindleddeedaward"
        data[f"{earned}-0-outcome_tier"] = str(good.pk)
        data[f"{earned}-0-amount"] = "5"
        data["recorded_act_days"] = "60"
        ritual = "animaritualresonanceaward"
        data[f"{ritual}-0-outcome_tier"] = str(success.pk)
        data[f"{ritual}-0-amount"] = "7"
        data["_save"] = "Save"
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        config = KindlingConfig.objects.get(pk=self.config.pk)
        self.assertEqual(config.recorded_act_days, 60)
        self.assertEqual(config.harm_property, harm)
        tier = KindledStrengthTier.objects.get(rank=1)
        self.assertEqual((tier.name, tier.pull_levels), ("Glimmer", 4))
        self.assertFalse(KindledStrengthTier.objects.filter(rank=9).exists())
        self.assertEqual(RallyKindlingStrength.objects.get(outcome_tier=success).strength, 2)
        self.assertEqual(KindledDeedAward.objects.get(outcome_tier=good).amount, 5)
        self.assertEqual(AnimaRitualResonanceAward.objects.get(outcome_tier=success).amount, 7)


class WeeklyMarkReturnPageTests(TestCase):
    """The weekly table is one page: every step is a row of fields saved together (#5327)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser(
            "weekly5327", "weekly5327@example.com", "pw-123456"
        )
        cls.rows = [
            WeeklyMarkReturnFactory(gained_at_least=0, percent_paid=100),
            WeeklyMarkReturnFactory(gained_at_least=9, percent_paid=85),
            WeeklyMarkReturnFactory(gained_at_least=18, percent_paid=70),
        ]
        cls.url = reverse("admin:arxii_weeklymarkreturn_changelist")

    def test_the_page_lists_every_row_as_fields_under_the_demos_heading_and_help(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        formset = response.context["cl"].formset
        self.assertEqual(len(formset.forms), 3)
        page = response.content.decode()
        for index in range(3):
            self.assertIn(f'name="form-{index}-gained_at_least"', page)
            self.assertIn(f'name="form-{index}-percent_paid"', page)
        self.assertIn("One row for each step in the game week", page)
        self.assertIn(
            "A row applies once she has gained at least this much from marks this game week, "
            "before this mark. With no rows, nothing is reduced. Authored choices are never "
            "reduced.",
            page,
        )
        self.assertLess(
            page.index("One row for each step in the game week"),
            page.index('name="form-0-gained_at_least"'),
        )
        self.assertLess(page.index('name="form-2-percent_paid"'), page.index("A row applies"))

    def test_saving_the_page_changes_the_rows_it_shows(self) -> None:
        self.client.force_login(self.staff)
        formset = self.client.get(self.url).context["cl"].formset
        data = {
            "form-TOTAL_FORMS": "3",
            "form-INITIAL_FORMS": "3",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        for index, form in enumerate(formset.forms):
            data[f"form-{index}-id"] = str(form.instance.pk)
            data[f"form-{index}-gained_at_least"] = str(form.instance.gained_at_least)
            data[f"form-{index}-percent_paid"] = str(form.instance.percent_paid)
        data["form-1-percent_paid"] = "60"
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WeeklyMarkReturn.objects.get(gained_at_least=9).percent_paid, 60)
        self.assertEqual(WeeklyMarkReturn.objects.get(gained_at_least=0).percent_paid, 100)
        self.assertEqual(WeeklyMarkReturn.objects.get(gained_at_least=18).percent_paid, 70)
