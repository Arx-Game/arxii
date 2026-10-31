"""Journey: a vow scales the surge a rallier gives (#4739, slice 3 of #4727; #4783).

Mira holds an engaged covenant vow at thread level 2. Staff open the vow stat scaling admin
add page and save "+50 per level" for Mira's role on a "Rally: surge intensity" target (the
maneuver effect catalog, #4783). Mira then types ``combat rally Tomas``; her Rally roll's
Success band is worth 3 intensity, and her surge intensity is 100 + 2 x 50 = 200%, so Tomas
surges 6 and his roll line ends "Success · Intensity +6 · surge +3" (the intensity the
surge intensity added), live over telnet and in his round payload's ``roll``. Without the
row, the same rally surges 3 with no surge note.

The rally roll is forced with ``force_check_outcome`` so the band is chosen by the test.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from integration_tests.test_surge_rolls_journeys import _SurgeField
from world.combat.constants import SurgeTriggerKind
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, engage_vow_with_thread
from world.covenants.models import VowStatScaling
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, ManeuverEffectKey
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory

BAND_INTENSITY = 3
THREAD_LEVEL = 2
BONUS_PER_LEVEL = 50
# 100 + 2 x 50 = 200%: the Success band's intensity, doubled.
VOWED_SUCCESS_INTENSITY = BAND_INTENSITY * 2
# The roll line notes what the surge intensity added: the scaled total minus the band's 3.
SURGE_EXTRA = VOWED_SUCCESS_INTENSITY - BAND_INTENSITY


class AVowedRallySurgesMore(_SurgeField):
    def setUp(self) -> None:
        super().setUp()
        ensure_maneuver_effects()
        self.enter_combat(self.mira, self.tomas)
        self.author_tuning(
            SurgeTriggerKind.RALLIED,
            "Encourage",
            partial=1,
            success=BAND_INTENSITY,
        )
        self.role = CovenantRoleFactory(name="Herald", covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            self.mira.sheet_data,
            self.role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=THREAD_LEVEL,
        )
        self.target = ModifierTargetFactory(
            category=ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME),
            name="Rally: surge intensity",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.RALLY_SURGE_INTENSITY),
        )
        self.staff = get_user_model().objects.create_superuser(
            "vow_tuner", "vow@example.com", "pw-12345"
        )

    def staff_scale_surge_intensity(self) -> None:
        """Staff save "+50 per level" on the Rally surge intensity target in the admin."""
        self.client.force_login(self.staff)
        add_url = "/admin/arxii/vowstatscaling/add/"
        self.assertEqual(self.client.get(add_url).status_code, 200)
        response = self.client.post(
            add_url,
            {
                "covenant_role": self.role.pk,
                "modifier_target": self.target.pk,
                "bonus_per_level": BONUS_PER_LEVEL,
            },
        )
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        row = VowStatScaling.objects.get(covenant_role=self.role)
        self.assertEqual(row.modifier_target, self.target)
        self.assertEqual(row.bonus_per_level, BONUS_PER_LEVEL)

    def test_mira_s_vow_doubles_the_surge_her_rally_gives_tomas(self) -> None:
        self.staff_scale_surge_intensity()

        told = self.telnet(self.mira, "combat rally Tomas")
        self.assertIn("You rally your ally.", told)
        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), VOWED_SUCCESS_INTENSITY)
        vowed_line = f"Success · Intensity +{VOWED_SUCCESS_INTENSITY} · surge +{SURGE_EXTRA}"
        told = self.told_roll_line(self.tomas)
        self.assertTrue(told.endswith(vowed_line), told)
        (beat,) = self.beats_seen_by(self.account_of(self.tomas))
        self.assertEqual(beat["amount"], VOWED_SUCCESS_INTENSITY)
        self.assertEqual(beat["roll"], told)
        self.assertEqual(beat["trigger_kind"], SurgeTriggerKind.RALLIED)
        # The rallier is not the one surged.
        self.assertEqual(self.intensity(self.mira), 0)

    def test_without_the_row_the_same_rally_surges_the_band_amount(self) -> None:
        self.telnet(self.mira, "combat rally Tomas")
        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), BAND_INTENSITY)
        told = self.told_roll_line(self.tomas)
        self.assertTrue(told.endswith(f"Success · Intensity +{BAND_INTENSITY}"), told)
        self.assertNotIn("surge +", told)
        (beat,) = self.beats_seen_by(self.account_of(self.tomas))
        self.assertEqual(beat["amount"], BAND_INTENSITY)
        self.assertEqual(beat["roll"], told)
