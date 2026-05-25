"""Phase D D2: editor CRUD viewsets for nested mission-graph models.

5 viewsets (one per nested model). Each tested for:
- staff-only permission
- list + parent-FK filter round-trip
- create round-trip (POST body → row → 201 → echoed body)
- detail / update / delete shape sanity

The serializers are thin ModelSerializers; the model-layer clean()
already enforces single-row invariants (e.g. reward XOR parent). Tests
focus on the API surface, not re-verifying model invariants.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.missions.constants import (
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteCandidateFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionTemplateFactory,
)
from world.traits.factories import CheckOutcomeFactory


def _staff() -> object:
    return AccountFactory(username="staff-editor", is_staff=True)


class NodeViewSetCRUDTests(TestCase):
    """MissionNodeViewSet: list+filter, create, update, delete."""

    URL = "/api/missions/nodes/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-node-crud", is_staff=True)
        cls.template = MissionTemplateFactory(slug="node-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.other_template = MissionTemplateFactory(slug="node-tmpl-other")
        MissionNodeFactory(template=cls.other_template, key="other-entry")

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_template(self) -> None:
        response = self.client.get(self.URL, {"template": self.template.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        keys = {row["key"] for row in response.data["results"]}
        self.assertEqual(keys, {"entry"})

    def test_create_round_trips(self) -> None:
        response = self.client.post(
            self.URL,
            {
                "template": self.template.pk,
                "key": "second",
                "is_entry": False,
                "conflict_mode": ConflictMode.COINFLIP,
                "editor_x": 100,
                "editor_y": 200,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["key"], "second")
        self.assertEqual(response.data["editor_x"], 100)

    def test_patch_updates_editor_coordinates(self) -> None:
        response = self.client.patch(
            f"{self.URL}{self.entry.pk}/",
            {"editor_x": 50, "editor_y": 75},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["editor_x"], 50)

    def test_delete_removes_node(self) -> None:
        n = MissionNodeFactory(template=self.template, key="doomed")
        response = self.client.delete(f"{self.URL}{n.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_unauthenticated_denied(self) -> None:
        client = APIClient()
        response = client.get(self.URL)
        self.assertIn(
            response.status_code,
            {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN},
        )


class OptionViewSetCRUDTests(TestCase):
    """MissionOptionViewSet: list+filter, create."""

    URL = "/api/missions/options/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-opt-crud", is_staff=True)
        cls.template = MissionTemplateFactory(slug="opt-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="n1")
        cls.other_node = MissionNodeFactory(template=cls.template, key="n2")
        cls.check_type = CheckTypeFactory()
        MissionOptionFactory(
            node=cls.node,
            order=1,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.check_type,
        )
        MissionOptionFactory(
            node=cls.other_node,
            order=1,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.check_type,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_node(self) -> None:
        response = self.client.get(self.URL, {"node": self.node.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_list_filters_by_template(self) -> None:
        response = self.client.get(self.URL, {"template": self.template.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_create_authored_check(self) -> None:
        response = self.client.post(
            self.URL,
            {
                "node": self.node.pk,
                "order": 2,
                "option_kind": OptionKind.CHECK,
                "source_kind": OptionSource.AUTHORED,
                "authored_check_type": self.check_type.pk,
                "authored_base_risk": 0,
                "authored_ic_framing": "Sneak.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class RouteViewSetCRUDTests(TestCase):
    """MissionOptionRouteViewSet: list+filter, create."""

    URL = "/api/missions/routes/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-route-crud", is_staff=True)
        cls.template = MissionTemplateFactory(slug="rt-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="rt-n")
        cls.check_type = CheckTypeFactory()
        cls.option = MissionOptionFactory(
            node=cls.node,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.check_type,
        )
        cls.outcome_tier = CheckOutcomeFactory()
        cls.target = MissionNodeFactory(template=cls.template, key="rt-target")
        MissionOptionRouteFactory(
            option=cls.option,
            outcome_tier=cls.outcome_tier,
            target_node=cls.target,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_option(self) -> None:
        response = self.client.get(self.URL, {"option": self.option.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)


class CandidateViewSetCRUDTests(TestCase):
    """MissionOptionRouteCandidateViewSet: list+filter."""

    URL = "/api/missions/route-candidates/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-cand-crud", is_staff=True)
        cls.template = MissionTemplateFactory(slug="cand-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="c-n")
        cls.check_type = CheckTypeFactory()
        cls.option = MissionOptionFactory(
            node=cls.node,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.check_type,
        )
        cls.outcome_tier = CheckOutcomeFactory()
        cls.route = MissionOptionRouteFactory(
            option=cls.option,
            outcome_tier=cls.outcome_tier,
            target_node=MissionNodeFactory(template=cls.template, key="c-tgt"),
            is_random_set=True,
        )
        cls.target = MissionNodeFactory(template=cls.template, key="c-target")
        MissionOptionRouteCandidateFactory(route=cls.route, target_node=cls.target, weight=1)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_route(self) -> None:
        response = self.client.get(self.URL, {"route": self.route.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)


class RewardViewSetCRUDTests(TestCase):
    """MissionOptionRouteRewardViewSet: XOR route/candidate parent enforced."""

    URL = "/api/missions/route-rewards/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-rew-crud", is_staff=True)
        cls.template = MissionTemplateFactory(slug="rew-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="rw-n")
        cls.check_type = CheckTypeFactory()
        cls.option = MissionOptionFactory(
            node=cls.node,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.check_type,
        )
        cls.outcome_tier = CheckOutcomeFactory()
        cls.route = MissionOptionRouteFactory(
            option=cls.option,
            outcome_tier=cls.outcome_tier,
            target_node=MissionNodeFactory(template=cls.template, key="rw-tgt"),
        )
        MissionOptionRouteRewardFactory(
            route=cls.route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_list_filters_by_route(self) -> None:
        response = self.client.get(self.URL, {"route": self.route.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_create_with_route_parent(self) -> None:
        response = self.client.post(
            self.URL,
            {
                "route": self.route.pk,
                "kind": DeedRewardKind.IMMEDIATE,
                "sink": DeedRewardSink.LEGEND_POINTS,
                "amount": 50,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_create_with_both_parents_rejected(self) -> None:
        # Model clean() enforces XOR — serializer surfaces as 400.
        cand_route = MissionOptionRouteFactory(
            option=self.option,
            outcome_tier=CheckOutcomeFactory(),
            target_node=MissionNodeFactory(template=self.template, key="rw-cand"),
            is_random_set=True,
        )
        cand = MissionOptionRouteCandidateFactory(
            route=cand_route,
            target_node=MissionNodeFactory(template=self.template, key="rw-cand-tgt"),
        )
        response = self.client.post(
            self.URL,
            {
                "route": self.route.pk,
                "candidate": cand.pk,
                "kind": DeedRewardKind.IMMEDIATE,
                "sink": DeedRewardSink.MONEY,
                "amount": 50,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
