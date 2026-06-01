"""Phase D D5: predicate-leaf catalog endpoint."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory


class PredicateLeafCatalogTests(TestCase):
    URL = "/api/missions/predicate-leaves/"

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="staff-leaf-cat", is_staff=True)
        cls.player = AccountFactory(username="player-leaf-cat", is_staff=False)

    def test_staff_can_list(self) -> None:
        client = APIClient()
        client.force_authenticate(self.staff)
        response = client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_player_denied(self) -> None:
        client = APIClient()
        client.force_authenticate(self.player)
        response = client.get(self.URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_response_includes_known_leaves(self) -> None:
        client = APIClient()
        client.force_authenticate(self.staff)
        response = client.get(self.URL)
        names = {row["name"] for row in response.data}
        # Phase 0 + Phase C resolvers (subset of the union).
        self.assertIn("has_distinction", names)
        self.assertIn("min_character_level", names)
        self.assertIn("has_codex_entry", names)
        self.assertIn("has_resonance", names)
        self.assertIn("min_npc_standing", names)
        self.assertIn("is_member_of_org", names)
        self.assertIn("min_society_standing", names)

    def test_each_leaf_carries_param_names_and_types(self) -> None:
        """E6 follow-up: params now include type tags so the Studio's tree
        builder can coerce ``<Input>`` strings before save."""
        client = APIClient()
        client.force_authenticate(self.staff)
        response = client.get(self.URL)
        by_name = {row["name"]: row for row in response.data}
        # has_distinction takes `slug` (str).
        self.assertEqual(by_name["has_distinction"]["params"], [{"name": "slug", "type": "str"}])
        # has_codex_entry takes `subject` + `name`, both str.
        self.assertEqual(
            {p["name"] for p in by_name["has_codex_entry"]["params"]},
            {"subject", "name"},
        )
        self.assertTrue(
            all(p["type"] == "str" for p in by_name["has_codex_entry"]["params"]),
        )
        # min_org_reputation takes `org` + `tier`.
        self.assertEqual(
            {p["name"] for p in by_name["min_org_reputation"]["params"]},
            {"org", "tier"},
        )
        # min_character_level's `level` is int — the bug this whole pass fixes.
        level_params = by_name["min_character_level"]["params"]
        self.assertEqual(len(level_params), 1)
        self.assertEqual(level_params[0], {"name": "level", "type": "int"})
        # has_thread takes no authored params.
        self.assertEqual(by_name["has_thread"]["params"], [])

    def test_response_alphabetically_ordered(self) -> None:
        client = APIClient()
        client.force_authenticate(self.staff)
        response = client.get(self.URL)
        names = [row["name"] for row in response.data]
        self.assertEqual(names, sorted(names))
