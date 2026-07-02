"""Tests for the #1770 PR4 opt-in surfaces: boundary seam + stakes-summary API.

Boundary seam: the allow-all stub's contract, and that the authoring call
site (StakeSerializer) actually invokes it — asserted via mock.patch on the
ORIGIN module path (repo convention: lazy-import + patch-origin).

Stakes-summary endpoint: what is wagered is visible (player_summary /
severity / risk / readiness); branch contents are never included (pillar 9).
"""

from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.constants import RenownRisk
from world.stories.constants import StakeSeverity, StakeSubjectKind
from world.stories.factories import (
    BeatFactory,
    StakeFactory,
    StakeResolutionFactory,
    StakeTemplateFactory,
)
from world.stories.models import StakeContractActivation
from world.stories.services.boundaries import check_stake_boundaries
from world.stories.types import StakeBoundaryReport


class CheckStakeBoundariesStubTests(TestCase):
    """The allow-all stub: never blocks, never requires sign-off."""

    def test_allows_empty_everything(self):
        report = check_stake_boundaries([], [])
        self.assertTrue(report.allowed)
        self.assertEqual(report.requires_signoff, ())
        self.assertEqual(report.blocked_reason_private, "")

    def test_allows_real_stakes_and_sheets(self):
        stake = StakeFactory(severity=StakeSeverity.REMOVAL)
        sheet = CharacterSheetFactory()
        report = check_stake_boundaries([stake], [sheet])
        self.assertTrue(report.allowed)


class StakeSerializerBoundaryCallSiteTests(APITestCase):
    """Authoring a stake runs the boundary screen (with an empty sheet list)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = AccountFactory(is_staff=True)
        cls.beat = BeatFactory(risk=RenownRisk.HIGH, target_level=4)
        cls.template = StakeTemplateFactory(
            subject_kind=StakeSubjectKind.CUSTOM,
            severity=StakeSeverity.GRAVE,
        )

    def _post_stake(self):
        self.client.force_authenticate(user=self.staff)
        return self.client.post(
            reverse("stake-list"),
            {
                "beat": self.beat.pk,
                "template": self.template.pk,
                "subject_label": "The archive",
                "player_summary": "The archive may burn.",
            },
            format="json",
        )

    def test_create_invokes_boundary_check_with_empty_sheets(self):
        with mock.patch(
            "world.stories.services.boundaries.check_stake_boundaries",
            return_value=StakeBoundaryReport(allowed=True),
        ) as mocked:
            resp = self._post_stake()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mocked.assert_called_once()
        _stakes_arg, sheets_arg = mocked.call_args.args
        self.assertEqual(list(sheets_arg), [])

    def test_blocked_report_rejects_with_generic_message(self):
        blocked = StakeBoundaryReport(
            allowed=False,
            blocked_reason_private="player X never wagers pets",
        )
        with mock.patch(
            "world.stories.services.boundaries.check_stake_boundaries",
            return_value=blocked,
        ):
            resp = self._post_stake()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # The private reason must never leak into the response (ADR-0033).
        self.assertNotIn("pets", str(resp.data))


class BeatStakesSummaryEndpointTests(APITestCase):
    """GET /api/beats/{id}/stakes-summary/ — pillar 9 visibility contract."""

    @classmethod
    def setUpTestData(cls):
        cls.player = AccountFactory(is_staff=False)
        cls.beat = BeatFactory(risk=RenownRisk.HIGH, target_level=4)
        cls.stake = StakeFactory(
            beat=cls.beat,
            severity=StakeSeverity.DIRE,
            player_summary="The healer NPC may die.",
        )
        cls.resolution = StakeResolutionFactory(
            stake=cls.stake,
            narrative_summary="SECRET: she is assassinated by the cabal.",
        )

    def _get(self):
        self.client.force_authenticate(user=self.player)
        return self.client.get(
            reverse("beat-stakes-summary", kwargs={"pk": self.beat.pk}),
        )

    def test_returns_summaries_and_risk(self):
        resp = self._get()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["declared_risk"], RenownRisk.HIGH)
        # No open activation -> effective risk falls back to declared.
        self.assertEqual(resp.data["effective_risk"], RenownRisk.HIGH)
        self.assertFalse(resp.data["is_ready"])  # incomplete contract
        self.assertEqual(len(resp.data["stakes"]), 1)
        entry = resp.data["stakes"][0]
        self.assertEqual(entry["player_summary"], "The healer NPC may die.")
        self.assertEqual(entry["severity"], StakeSeverity.DIRE)
        self.assertEqual(entry["severity_label"], StakeSeverity.DIRE.label)

    def test_never_includes_resolution_or_branch_data(self):
        """Pillar 9: branch contents stay hidden — explicit privacy assertion."""
        resp = self._get()
        payload = str(resp.data)
        self.assertNotIn("assassinated", payload)
        self.assertNotIn("resolutions", payload)
        self.assertNotIn("consequence_pool", payload)

    def test_open_activation_drives_effective_risk(self):
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=10,
            declared_target_level=4,
            declared_risk=RenownRisk.HIGH,
            effective_risk=RenownRisk.LOW,
            is_ready=True,
        )
        resp = self._get()
        self.assertEqual(resp.data["effective_risk"], RenownRisk.LOW)

    def test_requires_authentication(self):
        resp = self.client.get(
            reverse("beat-stakes-summary", kwargs={"pk": self.beat.pk}),
        )
        self.assertIn(
            resp.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
