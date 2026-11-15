"""The Scaling settings panel on the Tuning dashboard (#5093).

The panel reads every scaling row live and shows it with a link to its admin page. These
tests seed the rows the way a fresh database gets them, check the numbers against the seeded
ladder, and pin that the panel loads each table once, never writes, and carries a rule for
every class it emits.
"""

from decimal import Decimal
from pathlib import Path
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from evennia.accounts.models import AccountDB

from web.admin.tuning import scaling_settings
from web.admin.tuning.scaling_settings import PATH_CHANGE_LEVELS, build_scaling_settings_panel
from world.checks.constants import ModifierLane
from world.checks.modifier_models import LevelTier, ModifierLevelBaseline, ModifierSizeFraction
from world.checks.scale_config import CheckScaleConfig
from world.checks.services import difficulty_points, level_points
from world.checks.slide import load_ranks, resolve_standing
from world.fatigue.models import FatigueConfig
from world.magic.constants import TargetKind
from world.magic.factories import ThreadPullCostFactory
from world.magic.models.resonance_environment import ResonanceEnvironmentConfig
from world.progression.models import DevelopmentCostConfig
from world.progression.seeds import seed_development_cost_config
from world.seeds.modifier_values import (
    seed_check_scale_config,
    seed_level_tiers,  # noqa: F401 - seeded by the tables
    seed_modifier_value_tables,
)
from world.traits.factories import ensure_level_ladder


def _seed_everything() -> None:
    seed_modifier_value_tables()
    seed_check_scale_config()
    seed_development_cost_config()
    ensure_level_ladder()
    ThreadPullCostFactory(tier=1, target_kind=TargetKind.GIFT, imbue_cost_multiplier=2)
    ResonanceEnvironmentConfig.objects.get_or_create(pk=1)


def _row(panel: scaling_settings.ScalingSettingsPanel, label_start: str):
    return next(row for row in panel.strength if row.label.startswith(label_start))


class ScalingPanelReaderTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        _seed_everything()
        cls.panel = build_scaling_settings_panel()

    def test_the_strength_table_reads_the_seeded_ladder_at_the_path_levels(self) -> None:
        self.assertEqual(self.panel.levels, PATH_CHANGE_LEVELS)
        baseline = [cell.value for cell in _row(self.panel, "Baseline").cells]
        self.assertEqual(baseline, [18, 34, 58, 98, 138, 178, 218])
        width = {cell.value for cell in _row(self.panel, "One level").cells}
        self.assertEqual(width, {8})

    def test_the_tier_row_shows_the_jump_on_reaching_each_level(self) -> None:
        jumps = _row(self.panel, "Tier bonus").cells
        self.assertEqual([cell.value for cell in jumps], [0, 0, 24, 24, 24, 24, 24])
        self.assertEqual(
            [cell.text for cell in jumps], ["0", "+0", "+24", "+24", "+24", "+24", "+24"]
        )

    def test_the_level_term_and_opposition_come_from_the_real_helpers(self) -> None:
        term = [cell.value for cell in _row(self.panel, "A character's level term").cells]
        opposition = [cell.value for cell in _row(self.panel, "An NPC's opposition").cells]
        self.assertEqual(term, [level_points(level) for level in PATH_CHANGE_LEVELS])
        self.assertEqual(opposition, [difficulty_points(level) for level in PATH_CHANGE_LEVELS])
        self.assertEqual(term[:3], [9, 17, 53])
        self.assertEqual(opposition[:3], [18, 34, 82])

    def test_the_worked_example_is_computed_through_the_rank_ladder(self) -> None:
        ranks = load_ranks()
        for line in self.panel.example.lines:
            standing = resolve_standing(
                difficulty_points(line.character_level),
                difficulty_points(line.npc_level),
                ranks=ranks,
            )
            self.assertEqual(float(line.ranks_above), round(standing.difference, 1))
        first, second, _third = self.panel.example.lines
        self.assertEqual(first.ranks_above, Decimal(1))
        self.assertEqual(second.ranks_above, Decimal(4))
        self.assertIn(
            "level 5 character stands 1 rank above a level 4 NPC", self.panel.example.text
        )
        self.assertIn(
            "level 6 character stands 4 ranks above a level 5 NPC", self.panel.example.text
        )
        self.assertIn("3 ranks for the tier bonus of 24 points", self.panel.example.text)

    def test_the_worked_example_follows_the_tier_rows(self) -> None:
        tier = LevelTier.objects.get(start_level=6)
        tier.bonus_points = 16
        tier.save()
        line = build_scaling_settings_panel().example.lines[1]
        self.assertEqual(line.ranks_above, Decimal(3))

    def test_every_setting_links_to_an_admin_page(self) -> None:
        names = [row.name for row in self.panel.settings]
        self.assertEqual(
            names,
            [
                "Level share",
                "Tier rows",
                "Buff sizes on rolls",
                "Value overrides",
                "Development cost",
                "Fatigue",
                "Backfire difficulty",
            ],
        )
        for row in self.panel.settings:
            self.assertTrue(row.edit.url.startswith("/admin/"), row.name)
        values = {row.name: row.value for row in self.panel.settings}
        self.assertEqual(values["Level share"], "0.5")
        self.assertEqual(
            values["Tier rows"],
            "level 3: +0 · level 6: +24 · level 11: +24 · level 16: +24 "
            "· level 21: +24 · level 26: +24",
        )
        self.assertTrue(values["Buff sizes on rolls"].startswith("Minor 0.125 · Moderate 0.25"))
        self.assertEqual(values["Value overrides"], "0 rows")
        self.assertEqual(values["Development cost"], "start 1 · base 100 · growth 150%")

    def test_development_cost_reads_the_curve_and_the_gift_multiplier(self) -> None:
        one_step, gift = self.panel.dev_cost.rows
        self.assertEqual(one_step.costs, (10, 10, 15, 22, 33, 50))
        self.assertEqual(gift.label, "Gift thread step (×2)")
        self.assertEqual(gift.costs, (20, 20, 30, 44, 66, 100))

    def test_pools_show_each_lane_at_the_path_levels_and_say_when_one_has_no_rows(self) -> None:
        pools = {row.label: row for row in self.panel.pools}
        self.assertEqual(len(pools), 12)
        anima = pools["Anima pool"]
        self.assertEqual(
            [cell.value for cell in anima.cells], [100, 300, 600, 1100, 1600, 2100, 2600]
        )
        fatigue = pools["Fatigue level bonus"]
        self.assertFalse(fatigue.has_rows)
        self.assertEqual(fatigue.empty_note, "no rows yet, so it adds nothing")
        for label in ("Moon tuning from a thread", "Vow effect damage", "Facet effect bonus"):
            self.assertTrue(pools[label].has_rows, label)

    def test_buff_sizes_are_points_at_the_path_levels(self) -> None:
        (rolls,) = self.panel.rolls.rows
        self.assertEqual(rolls.label, "At any level")
        self.assertEqual(rolls.points, (1, 2, 4, 6, 8))
        self.assertEqual(
            [table.title for table in self.panel.buff_tables],
            ["Stats", "To-hit", "Damage", "Protection"],
        )
        for table in self.panel.buff_tables:
            self.assertEqual(len(table.rows), len(PATH_CHANGE_LEVELS), table.title)
            self.assertTrue(table.has_sizes, table.title)

    def test_the_panel_writes_nothing(self) -> None:
        with CaptureQueriesContext(connection) as queries:
            build_scaling_settings_panel()
        writes = [q["sql"] for q in queries if not q["sql"].lstrip().upper().startswith("SELECT")]
        self.assertEqual(writes, [])


class ScalingPanelEmptyDatabaseTests(TestCase):
    def test_a_database_with_no_rows_reads_not_set_and_never_raises(self) -> None:
        panel = build_scaling_settings_panel()
        self.assertFalse(CheckScaleConfig.objects.exists())
        self.assertFalse(DevelopmentCostConfig.objects.exists())
        self.assertFalse(FatigueConfig.objects.exists())
        self.assertTrue(all(cell.value is None for cell in _row(panel, "Baseline").cells))
        self.assertTrue(all(cell.value is None for cell in _row(panel, "One level").cells))
        self.assertIn("cannot be worked out", panel.example.text)
        values = {row.name: row.value for row in panel.settings}
        self.assertEqual(values["Level share"], "not set")
        self.assertEqual(values["Tier rows"], "no rows yet")
        self.assertEqual(values["Buff sizes on rolls"], "no rows yet")
        self.assertEqual(panel.dev_cost.rows, ())
        self.assertTrue(all(not row.has_rows for row in panel.pools))
        self.assertFalse(panel.rolls.has_sizes)

    def test_a_lane_with_one_row_has_no_width_and_reads_not_set(self) -> None:
        ModifierLevelBaseline.objects.create(lane=ModifierLane.CHECK, level=1, baseline=18)
        ModifierSizeFraction.objects.create(
            lane=ModifierLane.CHECK, size=3, fraction=Decimal("0.5")
        )
        panel = build_scaling_settings_panel()
        self.assertTrue(all(cell.value is None for cell in _row(panel, "One level").cells))
        self.assertEqual(panel.rolls.rows[0].points, (None, None, None, None, None))


class ScalingPanelQueryCountTests(TestCase):
    def _count(self) -> int:
        with CaptureQueriesContext(connection) as queries:
            build_scaling_settings_panel()
        return len(queries)

    def test_each_table_loads_once_however_many_rows_it_holds(self) -> None:
        _seed_everything()
        baseline_count = self._count()
        # Rows in every table the panel reads: more tiers, more levels, more overrides.
        for start in (2, 4, 5, 7, 8):
            LevelTier.objects.create(start_level=start, bonus_points=1)
        ModifierLevelBaseline.objects.get_or_create(
            lane=ModifierLane.ANIMA_POOL, level=40, defaults={"baseline": 4000}
        )
        from world.checks.modifier_models import ModifierValue

        for level in range(1, 12):
            ModifierValue.objects.create(lane=ModifierLane.CHECK, size=3, level=level, value=level)
        self.assertEqual(self._count(), baseline_count)
        self.assertLessEqual(baseline_count, 20)


class ScalingPanelViewTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("scalingroot", "r@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("scalingstaff", "s@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()
        _seed_everything()

    def test_a_superuser_gets_the_panel(self) -> None:
        self.client.force_login(self.root)
        response = self.client.get(reverse("admin_tuning_scaling"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for heading in (
            "How strong each level is on a roll",
            "Settings",
            "Development cost per step",
            "Pools and caps",
            "Buff sizes in points",
        ):
            self.assertIn(f"<h3>{heading}</h3>", body)
        self.assertIn("Level baselines", body)
        self.assertNotIn("lane", body.lower().replace("lane__exact", "").replace("ladder", ""))

    def test_staff_who_are_not_superusers_are_refused(self) -> None:
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin_tuning_scaling")).status_code, 403)

    def test_an_anonymous_visitor_is_sent_to_log_in(self) -> None:
        self.assertEqual(self.client.get(reverse("admin_tuning_scaling")).status_code, 302)

    def test_the_dashboard_loads_the_panel(self) -> None:
        self.client.force_login(self.root)
        body = self.client.get(reverse("admin_tuning")).content.decode()
        self.assertIn('id="panel-scaling"', body)
        self.assertIn(reverse("admin_tuning_scaling"), body)


class ScalingPanelStylingTest(TestCase):
    """Every class the panel emits has a rule that reaches the dashboard page (#3667)."""

    #: Classes Django admin or the dashboard's shared panel CSS already style.
    ADMIN_PROVIDED_CLASSES = frozenset({"tuning-panel", "tuning-table"})

    @classmethod
    def setUpTestData(cls) -> None:
        cls.root = AccountDB.objects.create_superuser("stylingroot", "t@example.com", "pw-123456")
        _seed_everything()

    def _reachable_css(self, body: str) -> str:
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", body, flags=re.DOTALL))
        for tag in re.findall(r"<link[^>]*>", body):
            match = re.search(r'href="([^"]+)"', tag)
            if 'rel="stylesheet"' not in tag or match is None:
                continue
            href = match.group(1)
            if not href.startswith(settings.STATIC_URL):
                continue
            found = finders.find(href[len(settings.STATIC_URL) :])
            assert found is not None, f"the page links a stylesheet that does not resolve: {href}"
            css += "\n" + Path(found).read_text()
        return css

    def test_every_class_the_panel_emits_has_a_rule_on_the_dashboard(self) -> None:
        self.client.force_login(self.root)
        fragment = self.client.get(reverse("admin_tuning_scaling")).content.decode()
        emitted: set[str] = set()
        for attr in re.findall(r'class="([^"]*)"', fragment):
            emitted.update(token for token in attr.split() if token)
        template = (
            Path(__file__).resolve().parents[2] / "templates/admin/tuning/_scaling_panel.html"
        )
        source = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", template.read_text(), flags=re.DOTALL)
        for attr in re.findall(r'class="([^"]*)"', source):
            emitted.update(token for token in attr.split() if token)

        dashboard = self.client.get(reverse("admin_tuning")).content.decode()
        css = self._reachable_css(dashboard)
        undefined = sorted(
            token for token in emitted - self.ADMIN_PROVIDED_CLASSES if f".{token}" not in css
        )
        self.assertEqual(undefined, [], "class hooks with no CSS rule reaching the page")
