"""Journey: staff build a mission in the Mission Studio through its endpoints (#4558).

Staff create a template, an entry node, a check option with routes for some tiers and a
second node. The graph check names the tiers still missing and the second node nothing
leads to. They add the missing routes and point one at the second node: the check comes
back empty. They delete the second node, and the route that led there now has no target,
which ends the mission.
"""

from __future__ import annotations

from rest_framework import status

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.missions.constants import ConflictMode, GraphProblemKind, OptionKind, OptionSource
from world.missions.models import MissionOptionRoute
from world.traits.factories import (
    CheckOutcomeFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)

TIERS = [
    ("Critical Failure", -2),
    ("Failure", -1),
    ("Partial Success", 0),
    ("Success", 1),
    ("Critical Success", 2),
]


class BuildingAMissionInTheStudioJourneyTests(JourneyCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="studio-builder", is_staff=True)
        cls.check_type = CheckTypeFactory()
        cls.tiers = {name: CheckOutcomeFactory(name=name, success_level=lvl) for name, lvl in TIERS}
        chart = ResultChartFactory()
        for roll, tier in enumerate(cls.tiers.values(), start=1):
            ResultChartOutcomeFactory(chart=chart, outcome=tier, min_roll=roll, max_roll=roll)

    def _post(self, client, url: str, body: dict) -> dict:
        response = client.post(url, body, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data

    def _check(self, client, template_id: int) -> list[dict]:
        response = client.get(f"/api/missions/templates/{template_id}/graph-check/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data["problems"]

    def test_build_check_fix_and_delete(self) -> None:
        client = self.api(self.staff)
        template = self._post(
            client,
            "/api/missions/templates/",
            {
                "name": "Studio Journey Heist",
                "summary": "An opening.",
                "level_band_min": 1,
                "level_band_max": 5,
                "risk_tier": 2,
                "arc_scope": "global",
                "cooldown": "P1D",
            },
        )
        entry = self._post(
            client,
            "/api/missions/nodes/",
            {
                "template": template["id"],
                "key": "gate",
                "is_entry": True,
                "conflict_mode": ConflictMode.GROUP_VOTE,
            },
        )
        option = self._post(
            client,
            "/api/missions/options/",
            {
                "node": entry["id"],
                "order": 1,
                "key": "pick-lock",
                "option_kind": OptionKind.CHECK,
                "source_kind": OptionSource.AUTHORED,
                "authored_check_type": self.check_type.pk,
                "authored_base_risk": 0,
                "authored_ic_framing": "Work the lock.",
            },
        )
        for name in ("Failure", "Success"):
            self._post(
                client,
                "/api/missions/routes/",
                {"option": option["id"], "outcome_tier": self.tiers[name].pk},
            )
        second = self._post(
            client,
            "/api/missions/nodes/",
            {
                "template": template["id"],
                "key": "vault",
                "conflict_mode": ConflictMode.GROUP_VOTE,
            },
        )

        problems = self._check(client, template["id"])
        by_kind = {p["kind"]: p for p in problems}
        self.assertEqual(
            set(by_kind),
            {GraphProblemKind.MISSING_TIERS, GraphProblemKind.UNREACHABLE_NODE},
        )
        self.assertEqual(
            by_kind[GraphProblemKind.MISSING_TIERS]["missing_tiers"],
            ["Critical Failure", "Partial Success", "Critical Success"],
        )
        self.assertEqual(by_kind[GraphProblemKind.UNREACHABLE_NODE]["node"], second["id"])

        for name in ("Critical Failure", "Partial Success", "Critical Success"):
            self._post(
                client,
                "/api/missions/routes/",
                {"option": option["id"], "outcome_tier": self.tiers[name].pk},
            )
        into_vault = MissionOptionRoute.objects.get(
            option_id=option["id"], outcome_tier=self.tiers["Success"]
        )
        response = client.patch(
            f"/api/missions/routes/{into_vault.pk}/",
            {"target_node": second["id"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self._check(client, template["id"]), [])

        response = client.delete(f"/api/missions/nodes/{second['id']}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Read the column itself: the identity map still holds the pre-delete instance.
        target = MissionOptionRoute.objects.filter(pk=into_vault.pk).values_list(
            "target_node", flat=True
        )
        self.assertEqual(list(target), [None])
        self.assertEqual(self._check(client, template["id"]), [])
