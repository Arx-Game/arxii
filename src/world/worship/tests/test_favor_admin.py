"""Favor authoring in admin (#4333 slice 1): Devotion config, Chosen favor config,
the per-being check type, the Distinction Builder's favor targets, the sentinels.

Driven as a staff member through the real admin pages with the test client.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from evennia.accounts.models import AccountDB

from web.admin.tuning import required_content as rc
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.game_clock.week_services import get_current_game_week
from world.mechanics.constants import FAVOR_EARNING_CATEGORY_NAME, FAVOR_INVOCATION_CATEGORY_NAME
from world.mechanics.models import ModifierTarget
from world.traits.factories import CheckOutcomeFactory
from world.worship.admin import invocation_difficulty_rows
from world.worship.constants import FavorAwardKind
from world.worship.factories import (
    DevotionConfigFactory,
    DevotionStandingFactory,
    FavorInvocationFactory,
    FavorOutcomeAwardFactory,
    WorshippedBeingFactory,
)
from world.worship.favor_services import ensure_being_modifier_targets
from world.worship.invocation_services import get_devotion_config
from world.worship.models import FavorOutcomeAward, PatronageValence


def _probe(key: str) -> rc.ProbeResult:
    probe = next(dep.probe for dep in rc._declarations() if dep.key == key)
    return probe.resolve(None)


class DevotionConfigAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("favoradmin", "fa@example.com", "pw-1234567")
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.failure = CheckOutcomeFactory(name="Failure", success_level=-1)

    def setUp(self) -> None:
        self.client.force_login(self.staff)

    def test_changelist_opens_the_singleton(self) -> None:
        response = self.client.get(reverse("admin:arxii_devotionconfig_changelist"))
        config = get_devotion_config()
        self.assertRedirects(
            response, reverse("admin:arxii_devotionconfig_change", args=(config.pk,))
        )

    def test_change_form_shows_terms_awards_and_context(self) -> None:
        config = DevotionConfigFactory()
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.INVOCATION, outcome_tier=self.success, amount=10
        )
        FavorInvocationFactory(outcome_tier=self.success, game_week=get_current_game_week())

        body = self.client.get(
            reverse("admin:arxii_devotionconfig_change", args=(config.pk,))
        ).content.decode()

        for text in (
            "Invocation check",
            "Daunting (75 points)",
            "Favor ease low threshold",
            "Invocations per week",
            "Earning rate",
            "Favor outcome awards: one table, two kinds",
            "Resulting invocation difficulty",
            "Invocations last week",
        ):
            self.assertIn(text, body, text)

    def test_odds_table_is_read_from_the_result_charts(self) -> None:
        from world.traits.factories import CheckRankFactory, ResultChartFactory
        from world.traits.models import ResultChart, ResultChartOutcome

        for rank, points in ((0, 0), (1, 25), (2, 50), (3, 75)):
            CheckRankFactory(rank=rank, min_points=points, name=f"Rank {rank}")
        # Reference roller 48 (rank 1). Daunting 75 is rank 3, eased 10 a point: 65 and 55
        # are rank 2 (gap -1), 45 and 35 rank 1 (gap 0), 25 rank 1, then the 15 floor
        # rank 0 (gap +1).
        for gap, success_width in ((-1, 20), (0, 50), (1, 80)):
            chart = ResultChartFactory(rank_difference=gap)
            ResultChartOutcome.objects.create(
                chart=chart, min_roll=1, max_roll=100 - success_width, outcome=self.failure
            )
            ResultChartOutcome.objects.create(
                chart=chart, min_roll=101 - success_width, max_roll=100, outcome=self.success
            )
        ResultChart.clear_cache()
        config = get_devotion_config()

        body = self.client.get(
            reverse("admin:arxii_devotionconfig_change", args=(config.pk,))
        ).content.decode()

        self.assertIn("Odds at these settings", body)
        # Merged by chart, derived from the config and charts, not listed in code.
        self.assertIn("1 to 2 points", body)
        self.assertIn("20%", body)
        self.assertIn("3 to 5 points", body)
        self.assertIn("50%", body)
        self.assertIn("6 or more points", body)
        self.assertIn("80%", body)

    def test_saving_an_invocation_award(self) -> None:
        config = DevotionConfigFactory()
        check_type = CheckTypeFactory(name="Invocation")
        url = reverse("admin:arxii_devotionconfig_change", args=(config.pk,))
        response = self.client.post(
            url,
            {
                "invocation_check_type": str(check_type.pk),
                "base_difficulty": "daunting",
                "favor_ease_low_threshold": "30",
                "favor_ease_low_points": "15",
                "favor_ease_high_threshold": "60",
                "favor_ease_high_points": "30",
                "invocations_per_week": "3",
                "favored_deed_percent": "100",
                "associated_deed_percent": "50",
                "weekly_deed_favor_cap": "8",
                "sacrifice_min_carried_days": "14",
                "sacrifice_carried_days_per_point": "90",
                "sacrifice_carried_max_points": "3",
                "maker_tie_max_points": "3",
                "made_for_max_points": "4",
                "made_from_max_points": "3",
                "shown_window_weeks": "4",
                "shown_engagements_per_point": "2",
                "shown_max_points": "3",
                "sacrifice_ease_per_point": "10",
                "sacrifices_per_week": "3",
                "odds_reference_roller_points": "48",
                "worn_item_max_points": "8",
                "worn_items_counted": "3",
                "resonance_fed_per_point": "10",
                "resonance_fed_max_points": "3",
                "invocation_meaning_ease_max": "40",
                "outcome_awards-TOTAL_FORMS": "1",
                "outcome_awards-INITIAL_FORMS": "0",
                "outcome_awards-MIN_NUM_FORMS": "0",
                "outcome_awards-MAX_NUM_FORMS": "1000",
                "outcome_awards-0-kind": FavorAwardKind.INVOCATION,
                "outcome_awards-0-outcome_tier": str(self.success.pk),
                "outcome_awards-0-amount": "10",
            },
        )
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        config.refresh_from_db()
        self.assertEqual(config.invocation_check_type, check_type)
        award = FavorOutcomeAward.objects.get(config=config)
        self.assertEqual(
            (award.kind, award.outcome_tier, award.amount), ("invocation", self.success, 10)
        )

    def test_difficulty_table_follows_the_terms(self) -> None:
        config = DevotionConfigFactory()
        rows = invocation_difficulty_rows(config, chosen_ease=30)
        self.assertEqual(
            rows,
            [
                ["1 to 29", "Daunting", "Hard", "Normal", "Easy"],
                ["30 to 59", "Hard", "Normal", "Easy", "Trivial"],
                ["60 or more", "Normal", "Easy", "Trivial", "Trivial"],
            ],
        )

    def test_sentinels(self) -> None:
        config = DevotionConfigFactory(invocation_check_type=None)
        self.assertFalse(_probe("favor-invocation-check-type").present)
        self.assertFalse(_probe("favor-invocation-awards").present)
        config.invocation_check_type = CheckTypeFactory()
        config.save()
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.INVOCATION, outcome_tier=self.success
        )
        self.assertTrue(_probe("favor-invocation-check-type").present)
        self.assertTrue(_probe("favor-invocation-awards").present)


class ChosenAndBeingAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser(
            "chosenadmin", "ca@example.com", "pw-1234567"
        )
        cls.being = WorshippedBeingFactory(name="Ombrin")
        DevotionStandingFactory(
            character_sheet=CharacterSheetFactory(),
            being=cls.being,
            favor=1,
            valence=PatronageValence.DEVOTIONAL,
            established_at=timezone.now(),
        )

    def setUp(self) -> None:
        self.client.force_login(self.staff)

    def test_chosen_favor_config_shows_the_new_terms(self) -> None:
        from world.worship.services import get_chosen_favor_config

        config = get_chosen_favor_config()
        body = self.client.get(
            reverse("admin:arxii_chosenfavorconfig_change", args=(config.pk,))
        ).content.decode()
        for text in (
            "Earn bonus percent",
            "Invocation ease points",
            "Chosen per being",
            "Ombrin 1",
        ):
            self.assertIn(text, body, text)

    def test_being_change_form_has_the_check_type_override(self) -> None:
        body = self.client.get(
            reverse("admin:arxii_worshippedbeing_change", args=(self.being.pk,))
        ).content.decode()
        self.assertIn("Invocation check type", body)


class DistinctionBuilderFavorTargetTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.models import PlayerData
        from world.contributors.factories import ContentContributorFactory

        cls.staff = AccountDB.objects.create_superuser("dbfavor", "db@example.com", "pw-1234567")
        PlayerData.objects.create(
            account=cls.staff, contributor=ContentContributorFactory(name="Favor Writer")
        )
        cls.being = WorshippedBeingFactory(name="Ombrin")
        ensure_being_modifier_targets(cls.being)
        cls.distinction = DistinctionFactory(name="Touched by Ombrin")
        for category in (FAVOR_INVOCATION_CATEGORY_NAME, FAVOR_EARNING_CATEGORY_NAME):
            DistinctionEffectFactory(
                distinction=cls.distinction,
                target=ModifierTarget.objects.get(category__name=category, target_being=cls.being),
                value_per_rank=15,
            )

    def test_effect_rows_name_the_being_and_the_unit(self) -> None:
        self.client.force_login(self.staff)
        body = self.client.get(
            reverse("admin_distinction_builder", args=[self.distinction.pk])
        ).content.decode()
        self.assertIn("Being: Ombrin. Value is difficulty points eased; 15 is one band.", body)
        self.assertIn("Being: Ombrin. Value is percent added to the earning rate.", body)
        self.assertIn('two "any being" targets', body)

    def test_target_picker_finds_favor_targets_by_being(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(
            "/admin/autocomplete/",
            {
                "app_label": "arxii",
                "model_name": "distinctioneffect",
                "field_name": "target",
                "term": "Ombrin",
            },
        )
        texts = sorted(row["text"] for row in response.json()["results"])
        self.assertEqual(
            texts,
            [
                "Ombrin favor earning (favor_earning)",
                "Ombrin favor invocation (favor_invocation)",
            ],
        )
