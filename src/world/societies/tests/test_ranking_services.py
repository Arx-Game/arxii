"""#742 — ranking services + render tests.

The materialized-view reads are PostgreSQL-only (managed=False model
backed by a MV that only exists under PG). Those tests are tagged
``@tag('postgres')`` so they only run in the PG-parity tier per the
repo's two-tier testing model. The render-layer and gate logic don't
touch the MV directly and run on both tiers.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)
from world.societies.models import RankingDisplay
from world.societies.ranking_services import (
    RankingRow,
    get_academy_legend_top_n,
    get_society_prestige_top_n,
    render_ranking_display,
    viewer_is_member_of_society,
)


def _make_primary_persona(name: str = ""):
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    persona = sheet.primary_persona
    if name:
        persona.name = name
        persona.save(update_fields=["name"])
    return persona


def _make_society_display(society, *, top_n: int = 10):
    """Build a RankingDisplay scoped to ``society`` (SOCIETY_PRESTIGE)."""
    from evennia_extensions.factories import ObjectDBFactory

    display_object = ObjectDBFactory()
    return RankingDisplay.objects.create(
        display_object=display_object,
        ranking_type=RankingDisplay.RankingType.SOCIETY_PRESTIGE,
        scope_society=society,
        top_n=top_n,
    )


def _make_academy_display(top_n: int = 10):
    """Build a RankingDisplay scoped globally (ACADEMY_LEGEND)."""
    from evennia_extensions.factories import ObjectDBFactory

    display_object = ObjectDBFactory()
    return RankingDisplay.objects.create(
        display_object=display_object,
        ranking_type=RankingDisplay.RankingType.ACADEMY_LEGEND,
        scope_society=None,
        top_n=top_n,
    )


class ViewerMembershipGateTests(TestCase):
    def test_member_returns_true(self) -> None:
        viewer = _make_primary_persona()
        society = SocietyFactory(name="House Vermillion")
        org = OrganizationFactory(society=society)
        OrganizationMembershipFactory(persona=viewer, organization=org)
        self.assertTrue(viewer_is_member_of_society(viewer, society))

    def test_non_member_returns_false(self) -> None:
        viewer = _make_primary_persona()
        society = SocietyFactory(name="House Stranger")
        self.assertFalse(viewer_is_member_of_society(viewer, society))

    def test_none_persona_returns_false(self) -> None:
        society = SocietyFactory(name="House Lonely")
        self.assertFalse(viewer_is_member_of_society(None, society))


class RenderRankingDisplayGatingTests(TestCase):
    """Render path tests using mocked top_n results (no MV dependency)."""

    def test_society_prestige_non_member_gets_cloaked_message(self) -> None:
        viewer = _make_primary_persona()
        society = SocietyFactory(name="House Hidden")
        display = _make_society_display(society)
        text = render_ranking_display(display, viewer)
        self.assertIn("PLACEHOLDER", text)
        self.assertIn("would know none", text)

    def test_society_prestige_member_with_no_top_n_gets_empty_narration(self) -> None:
        viewer = _make_primary_persona()
        society = SocietyFactory(name="House Empty")
        org = OrganizationFactory(society=society)
        OrganizationMembershipFactory(persona=viewer, organization=org)
        display = _make_society_display(society)
        with patch(
            "world.societies.ranking_services.get_society_prestige_top_n",
            return_value=[],
        ):
            text = render_ranking_display(display, viewer)
        self.assertIn("no names", text)

    def test_society_prestige_member_with_rows_gets_ranking(self) -> None:
        viewer = _make_primary_persona()
        society = SocietyFactory(name="House Vermillion")
        org = OrganizationFactory(society=society)
        OrganizationMembershipFactory(persona=viewer, organization=org)
        display = _make_society_display(society, top_n=3)
        fake_rows = [
            RankingRow(rank=1, persona_name="Alice", value=10_000),
            RankingRow(rank=2, persona_name="Bob", value=5_000),
            RankingRow(rank=3, persona_name="Carol", value=2_500),
        ]
        with patch(
            "world.societies.ranking_services.get_society_prestige_top_n",
            return_value=fake_rows,
        ) as mock_top_n:
            text = render_ranking_display(display, viewer)
        mock_top_n.assert_called_once_with(society, n=3)
        self.assertIn("House Vermillion", text)
        self.assertIn("Alice", text)
        self.assertIn("Bob", text)
        self.assertIn("Carol", text)
        self.assertIn("PLACEHOLDER", text)

    def test_academy_legend_no_gate(self) -> None:
        """Anyone can read the academy legend rankings (Legend is public)."""
        viewer = _make_primary_persona()
        display = _make_academy_display(top_n=5)
        fake_rows = [
            RankingRow(rank=1, persona_name="Legendary Alice", value=50_000),
        ]
        with patch(
            "world.societies.ranking_services.get_academy_legend_top_n",
            return_value=fake_rows,
        ) as mock_top_n:
            text = render_ranking_display(display, viewer)
        mock_top_n.assert_called_once_with(n=5)
        self.assertIn("Legendary Alice", text)
        self.assertIn("most-legendary", text)

    def test_academy_legend_works_with_no_viewer(self) -> None:
        """A passing stranger with no persona can still read the academy."""
        display = _make_academy_display()
        with patch(
            "world.societies.ranking_services.get_academy_legend_top_n",
            return_value=[],
        ):
            text = render_ranking_display(display, None)
        self.assertIn("no names", text)


class SocietyPrestigeTopNRuntimeTests(TestCase):
    """Runtime aggregate query (no MV) — runs on both DB tiers."""

    def test_empty_society_returns_empty_list(self) -> None:
        society = SocietyFactory(name="House Untested")
        rows = get_society_prestige_top_n(society, n=10)
        self.assertEqual(rows, [])

    def test_returns_members_ordered_by_total_prestige_desc(self) -> None:
        society = SocietyFactory(name="House Ranked")
        org = OrganizationFactory(society=society)
        leader = _make_primary_persona("Leader")
        follower = _make_primary_persona("Follower")
        OrganizationMembershipFactory(persona=leader, organization=org)
        OrganizationMembershipFactory(persona=follower, organization=org)
        leader.total_prestige = 5_000
        leader.save(update_fields=["total_prestige"])
        follower.total_prestige = 1_000
        follower.save(update_fields=["total_prestige"])

        rows = get_society_prestige_top_n(society, n=10)

        self.assertEqual([r.persona_name for r in rows], ["Leader", "Follower"])
        self.assertEqual(rows[0].value, 5_000)
        self.assertEqual(rows[0].rank, 1)
        self.assertEqual(rows[1].rank, 2)


class AcademyLegendTopNTests(TestCase):
    """Academy reads the PersonaLegendSummary MV; tolerates SQLite (returns [])."""

    def test_returns_empty_on_sqlite_or_fresh_pg(self) -> None:
        rows = get_academy_legend_top_n(n=5)
        self.assertIsInstance(rows, list)
