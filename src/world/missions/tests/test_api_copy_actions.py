"""Phase D D4.2: copy actions (whole template / node / subtree)."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.missions.constants import MissionVisibility, OptionKind, OptionSource
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
        cls.source = MissionTemplateFactory(name="Source", visibility=MissionVisibility.OPEN)
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
        return f"/api/missions/templates/{self.source.pk}/copy/"

    def test_copy_returns_201_with_new_template(self) -> None:
        response = self.client.post(
            self._url(),
            {"new_name": "Source (Copy)"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["name"], "Source (Copy)")
        # Copy always lands staff-only (#870): RESTRICTED + emptied rule,
        # regardless of the source's visibility/rule.
        self.assertEqual(response.data["visibility"], MissionVisibility.RESTRICTED)
        self.assertEqual(response.data["availability_rule"], {})

    def test_copy_duplicates_all_nodes(self) -> None:
        res = self.client.post(
            self._url(),
            {"new_name": "Source Copy 2"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        new_template_pk = res.data["id"]
        new_template_nodes = MissionNode.objects.filter(template_id=new_template_pk)
        self.assertEqual(new_template_nodes.count(), 2)
        # Entry flag preserved on the copied entry node.
        self.assertEqual(new_template_nodes.filter(is_entry=True).count(), 1)

    def test_copy_repoints_internal_route_targets(self) -> None:
        res = self.client.post(
            self._url(),
            {"new_name": "Source Copy 3"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        new_template_pk = res.data["id"]
        # The copied route should target the COPIED 'target' node, not
        # the original 'target' node (re-pointing within the new template).
        copied_route = MissionOptionRoute.objects.filter(
            option__node__template_id=new_template_pk,
        ).get()
        self.assertEqual(copied_route.target_node.template_id, new_template_pk)

    def test_copy_flags_flavor_needs_rewrite(self) -> None:
        res = self.client.post(
            self._url(),
            {"new_name": "Source Copy 4"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        new_template_pk = res.data["id"]
        copied_node = MissionNode.objects.get(template_id=new_template_pk, key="entry")
        self.assertTrue(copied_node.flavor_text_needs_rewrite)
        copied_option = MissionOption.objects.get(node=copied_node)
        self.assertTrue(copied_option.authored_ic_framing_needs_rewrite)

    def test_copy_rejects_blank_new_name(self) -> None:
        res = self.client.post(
            f"/api/missions/templates/{self.source.pk}/copy/",
            {"new_name": "   "},  # whitespace-only
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("new_name", res.json())

    def test_copy_carries_source_categories(self) -> None:
        from world.missions.factories import (
            MissionCategoryFactory,
            MissionTemplateFactory,
        )

        # Use a local template (not self.source) so the M2M add doesn't
        # pollute the shared setUpTestData fixture for sibling tests.
        local_source = MissionTemplateFactory(name="cat-copy-source")
        cat_a = MissionCategoryFactory(name="copy-cat-a")
        cat_b = MissionCategoryFactory(name="copy-cat-b")
        local_source.categories.add(cat_a, cat_b)

        res = self.client.post(
            f"/api/missions/templates/{local_source.pk}/copy/", {}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(sorted(res.json()["categories"]), sorted([cat_a.pk, cat_b.pk]))

    def test_copy_auto_suffixes_when_source_already_copied(self) -> None:
        src = MissionTemplateFactory(name="Original")
        url = f"/api/missions/templates/{src.pk}/copy/"
        # First copy gets the default name.
        res1 = self.client.post(url, {}, format="json")
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(res1.json()["name"], "Original (copy)")
        # Second copy must suffix.
        res2 = self.client.post(url, {}, format="json")
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(res2.json()["name"], "Original (copy) 2")


class CopyNodeActionTests(TestCase):
    """Single-node copy: routes keep original targets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-copy-node", is_staff=True)
        cls.template = MissionTemplateFactory(name="cn-tmpl")
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
        cls.template = MissionTemplateFactory(name="cs-tmpl")
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
