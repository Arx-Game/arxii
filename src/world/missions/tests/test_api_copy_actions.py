"""Phase D D4.2: copy actions (whole template / node / subtree)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.missions.constants import AccessTier, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionNode, MissionOption, MissionOptionRoute
from world.traits.factories import CheckOutcomeFactory


def _staff() -> object:
    return AccountFactory(username="staff-copy-act", is_staff=True)


class CopyTemplateActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-copy-tmpl", is_staff=True)
        cls.source = MissionTemplateFactory(
            slug="src-tmpl", name="Source", access_tier=AccessTier.OPEN
        )
        cls.entry = MissionNodeFactory(template=cls.source, key="entry", is_entry=True)
        cls.target = MissionNodeFactory(template=cls.source, key="target")
        cls.check_type = CheckTypeFactory()
        cls.option = MissionOptionFactory(
            node=cls.entry,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.check_type,
        )
        cls.outcome = CheckOutcomeFactory()
        MissionOptionRouteFactory(
            option=cls.option, outcome_tier=cls.outcome, target_node=cls.target
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def _url(self) -> str:
        return f"/api/missions/templates/{self.source.slug}/copy/"

    def test_copy_returns_201_with_new_template(self) -> None:
        response = self.client.post(
            self._url(),
            {"new_slug": "src-tmpl-copy", "new_name": "Source (Copy)"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["slug"], "src-tmpl-copy")
        # Copy always lands STAFF_ONLY regardless of source tier.
        self.assertEqual(response.data["access_tier"], AccessTier.STAFF_ONLY)

    def test_copy_duplicates_all_nodes(self) -> None:
        self.client.post(
            self._url(),
            {"new_slug": "src-tmpl-copy2", "new_name": "Source Copy 2"},
            format="json",
        )
        new_template_nodes = MissionNode.objects.filter(template__slug="src-tmpl-copy2")
        self.assertEqual(new_template_nodes.count(), 2)
        # Entry flag preserved on the copied entry node.
        self.assertEqual(new_template_nodes.filter(is_entry=True).count(), 1)

    def test_copy_repoints_internal_route_targets(self) -> None:
        self.client.post(
            self._url(),
            {"new_slug": "src-tmpl-copy3", "new_name": "Source Copy 3"},
            format="json",
        )
        # The copied route should target the COPIED 'target' node, not
        # the original 'target' node (re-pointing within the new template).
        copied_route = MissionOptionRoute.objects.filter(
            option__node__template__slug="src-tmpl-copy3",
        ).get()
        self.assertEqual(copied_route.target_node.template.slug, "src-tmpl-copy3")

    def test_copy_flags_flavor_needs_rewrite(self) -> None:
        self.client.post(
            self._url(),
            {"new_slug": "src-tmpl-copy4", "new_name": "Source Copy 4"},
            format="json",
        )
        copied_node = MissionNode.objects.get(template__slug="src-tmpl-copy4", key="entry")
        self.assertTrue(copied_node.flavor_text_needs_rewrite)
        copied_option = MissionOption.objects.get(node=copied_node)
        self.assertTrue(copied_option.authored_ic_framing_needs_rewrite)

    def test_copy_requires_both_slug_and_name(self) -> None:
        response = self.client.post(
            self._url(),
            {"new_slug": "no-name"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CopyNodeActionTests(TestCase):
    """Single-node copy: routes keep original targets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-copy-node", is_staff=True)
        cls.template = MissionTemplateFactory(slug="cn-tmpl")
        cls.source = MissionNodeFactory(template=cls.template, key="cn-source")
        cls.target = MissionNodeFactory(template=cls.template, key="cn-target")
        cls.check_type = CheckTypeFactory()
        cls.option = MissionOptionFactory(
            node=cls.source,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=cls.check_type,
        )
        MissionOptionRouteFactory(
            option=cls.option,
            outcome_tier=CheckOutcomeFactory(),
            target_node=cls.target,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_copy_node_returns_new_node_with_new_key(self) -> None:
        response = self.client.post(
            f"/api/missions/nodes/{self.source.pk}/copy/",
            {"new_key": "cn-source-copy"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["key"], "cn-source-copy")
        self.assertFalse(response.data["is_entry"])  # copies never inherit entry flag

    def test_copy_node_route_target_unchanged(self) -> None:
        self.client.post(
            f"/api/missions/nodes/{self.source.pk}/copy/",
            {"new_key": "cn-keeps-target"},
            format="json",
        )
        copy = MissionNode.objects.get(template=self.template, key="cn-keeps-target")
        copy_route = MissionOptionRoute.objects.get(option__node=copy)
        # Single-node copy doesn't re-point — keeps original target.
        self.assertEqual(copy_route.target_node_id, self.target.pk)


class CopySubtreeActionTests(TestCase):
    """Subtree copy: full-closure reachability; all internal routes re-pointed."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-copy-sub", is_staff=True)
        cls.template = MissionTemplateFactory(slug="cs-tmpl")
        # Reachable closure from A: A -> B -> C. D is an orphan (no
        # route from the A-reachable set points at it), so D stays out
        # of the copy.
        cls.a = MissionNodeFactory(template=cls.template, key="cs-a")
        cls.b = MissionNodeFactory(template=cls.template, key="cs-b")
        cls.c = MissionNodeFactory(template=cls.template, key="cs-c")
        cls.d = MissionNodeFactory(template=cls.template, key="cs-d-orphan")
        cls.check_type = CheckTypeFactory()

        def _link(src: MissionNode, dst: MissionNode) -> None:
            opt = MissionOptionFactory(
                node=src,
                option_kind=OptionKind.CHECK,
                source_kind=OptionSource.AUTHORED,
                authored_check_type=cls.check_type,
            )
            MissionOptionRouteFactory(
                option=opt,
                outcome_tier=CheckOutcomeFactory(),
                target_node=dst,
            )

        _link(cls.a, cls.b)
        _link(cls.b, cls.c)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(self.staff)

    def test_copy_subtree_clones_reachable_closure(self) -> None:
        self.client.post(
            f"/api/missions/nodes/{self.a.pk}/copy-subtree/",
            {"new_key_prefix": "x"},
            format="json",
        )
        # New keys: x-cs-a, x-cs-b, x-cs-c. Orphan D stays out.
        copied_keys = set(
            MissionNode.objects.filter(template=self.template, key__startswith="x-cs-").values_list(
                "key", flat=True
            )
        )
        self.assertEqual(copied_keys, {"x-cs-a", "x-cs-b", "x-cs-c"})

    def test_copy_subtree_repoints_internal_routes(self) -> None:
        self.client.post(
            f"/api/missions/nodes/{self.a.pk}/copy-subtree/",
            {"new_key_prefix": "y"},
            format="json",
        )
        copy_a = MissionNode.objects.get(template=self.template, key="y-cs-a")
        copy_b = MissionNode.objects.get(template=self.template, key="y-cs-b")
        # A-copy's route should target B-copy (not original B).
        a_route = MissionOptionRoute.objects.get(option__node=copy_a)
        self.assertEqual(a_route.target_node_id, copy_b.pk)
