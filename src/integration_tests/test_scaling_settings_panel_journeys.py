"""Journey for the Scaling settings panel on the Tuning dashboard (#5093).

A superuser opens the panel through the admin URL against the rows a fresh database is
seeded with, and reads the numbers staff tune by: the tier bonus and the worked example.
"""

from __future__ import annotations

from django.urls import reverse
from evennia.accounts.models import AccountDB

from integration_tests.harness import JourneyCase
from world.magic.constants import TargetKind
from world.magic.factories import ThreadPullCostFactory
from world.magic.models.resonance_environment import ResonanceEnvironmentConfig
from world.progression.seeds import seed_development_cost_config
from world.seeds.modifier_values import seed_check_scale_config, seed_modifier_value_tables
from world.traits.factories import ensure_level_ladder


class StaffReadTheScalingRowsOnTheTuningDashboard(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        seed_modifier_value_tables()
        seed_check_scale_config()
        seed_development_cost_config()
        ensure_level_ladder()
        ThreadPullCostFactory(tier=1, target_kind=TargetKind.GIFT, imbue_cost_multiplier=2)
        ResonanceEnvironmentConfig.objects.get_or_create(pk=1)
        self.root = AccountDB.objects.create_superuser("scalingroot", "r@example.com", "pw-123456")

    def test_a_superuser_reads_the_tier_bonus_and_the_worked_example(self) -> None:
        self.client.force_login(self.root)

        response = self.client.get(reverse("admin_tuning_scaling"))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # The tier row: the bonus on reaching level 6 is 24 points.
        self.assertIn('<td class="scaling-num scaling-jump">+24</td>', body)
        # The worked example, computed through the rank ladder from the seeded rows.
        self.assertIn("level 6 character stands 4 ranks above a level 5 NPC", body)
        self.assertIn("3 ranks for the tier bonus of 24 points", body)
