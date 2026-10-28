"""Journey: a vow scales the surge a rallier gives (#4739, slice 3 of #4727).

Mira holds an engaged covenant vow with a thread on it. Staff open the vow-scaling admin
page, pick "Surges given by Rally" from the action drop-down and save a multiplier for
Mira's role. Mira then types ``combat rally Tomas``; her Rally roll's Success band is
worth 3 intensity, and her vow (thread level 2 x 0.5 = +1.0) doubles it, so Tomas surges
6 and his roll line ends "Intensity +6 · vow scaling +3", live over telnet and in his
round payload's ``roll``. Without the row, the same rally surges 3 with no vow note.

The rally roll is forced with ``force_check_outcome`` so the band is chosen by the test.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model

from integration_tests.test_surge_rolls_journeys import SUCCESS_INTENSITY, _SurgeField
from world.combat.constants import SurgeTriggerKind
from world.covenants.constants import CovenantScaledAction
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.models import CovenantRoleActionScaling
from world.covenants.services import set_engaged_membership
from world.magic.constants import TargetKind
from world.magic.factories import ThreadFactory

THREAD_LEVEL = 2
MULTIPLIER = "0.5"
# 1 + 2 x 0.5 = 2.0: the Success band's intensity, doubled.
VOWED_SUCCESS_INTENSITY = SUCCESS_INTENSITY * 2
# The roll line notes what the vow added: the scaled total minus the band's own 3.
VOW_EXTRA = VOWED_SUCCESS_INTENSITY - SUCCESS_INTENSITY


class AVowedRallySurgesMore(_SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira, self.tomas)
        self.author_tuning(
            SurgeTriggerKind.RALLIED,
            "Encourage",
            partial=1,
            success=SUCCESS_INTENSITY,
        )
        self.role = CovenantRoleFactory(name="Herald", crown_weight=1)
        membership = CharacterCovenantRoleFactory(
            character_sheet=self.mira.sheet_data,
            covenant=CovenantFactory(),
            covenant_role=self.role,
        )
        set_engaged_membership(membership=membership)
        ThreadFactory(
            owner=self.mira.sheet_data,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.role,
            target_trait=None,
            level=THREAD_LEVEL,
        )
        self.staff = get_user_model().objects.create_superuser(
            "vow_tuner", "vow@example.com", "pw-12345"
        )

    def staff_scale_surges_given(self) -> None:
        """Staff pick "Surges given by Rally" on the admin add page and save the row."""
        self.client.force_login(self.staff)
        page = self.client.get("/admin/arxii/covenantroleactionscaling/add/").content.decode()
        self.assertIn(
            f'<option value="{CovenantScaledAction.SURGES_GIVEN}">Surges given by Rally</option>',
            page,
        )
        response = self.client.post(
            "/admin/arxii/covenantroleactionscaling/add/",
            {
                "covenant_role": self.role.pk,
                "action_key": CovenantScaledAction.SURGES_GIVEN,
                "thread_level_multiplier": MULTIPLIER,
            },
        )
        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        row = CovenantRoleActionScaling.objects.get(covenant_role=self.role)
        self.assertEqual(row.action_key, CovenantScaledAction.SURGES_GIVEN)
        self.assertEqual(row.thread_level_multiplier, Decimal(MULTIPLIER))

    def test_mira_s_vow_doubles_the_surge_her_rally_gives_tomas(self) -> None:
        self.staff_scale_surges_given()

        told = self.telnet(self.mira, "combat rally Tomas")
        self.assertIn("You rally your ally.", told)
        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), VOWED_SUCCESS_INTENSITY)
        vowed_line = f"Success · Intensity +{VOWED_SUCCESS_INTENSITY} · vow scaling +{VOW_EXTRA}"
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

        self.assertEqual(self.intensity(self.tomas), SUCCESS_INTENSITY)
        told = self.told_roll_line(self.tomas)
        self.assertTrue(told.endswith(f"Success · Intensity +{SUCCESS_INTENSITY}"), told)
        self.assertNotIn("vow scaling", told)
        (beat,) = self.beats_seen_by(self.account_of(self.tomas))
        self.assertEqual(beat["amount"], SUCCESS_INTENSITY)
        self.assertEqual(beat["roll"], told)
