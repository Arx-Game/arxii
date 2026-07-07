"""Board postings service — preview-only eligibility filter (#2044).

Reuses the same ``template_visible_to`` gate as trigger dispatch but
WITHOUT the grant / cooldown / announce side effects. The preview list
is what examine renders; ``take_from_board`` re-runs eligibility before
granting (never trusts the stale preview).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.missions.constants import GiverKind, MissionVisibility
from world.missions.factories import (
    MissionGiverFactory,
    MissionNodeFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionGiverCooldown, MissionInstance
from world.missions.services.boards import (
    MAX_BOARD_POSTINGS,
    BoardPosting,
    postings_for_giver,
)


def _template_with_entry(name: str) -> object:
    """Create a template with an entry node (required for staff_assign_mission)."""
    template = MissionTemplateFactory(name=name)
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


class PostingsForGiverTests(TestCase):
    """``postings_for_giver`` returns eligible templates without granting."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        cls.board_obj = ObjectDBFactory()  # plain Object typeclass
        cls.template_open = _template_with_entry("board-mission-open")

    def test_returns_eligible_templates(self) -> None:
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        giver.templates.add(self.template_open)
        postings = postings_for_giver(giver, self.character)
        self.assertEqual(len(postings), 1)
        self.assertEqual(postings[0].template_id, self.template_open.pk)
        self.assertEqual(postings[0].name, self.template_open.name)

    def test_excludes_restricted_templates_for_non_staff(self) -> None:
        restricted = _template_with_entry("board-mission-restricted")
        restricted.visibility = MissionVisibility.RESTRICTED
        restricted.save(update_fields=["visibility"])
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        giver.templates.add(self.template_open, restricted)
        postings = postings_for_giver(giver, self.character)
        template_ids = {p.template_id for p in postings}
        self.assertIn(self.template_open.pk, template_ids)
        self.assertNotIn(restricted.pk, template_ids)

    def test_no_grant_side_effects(self) -> None:
        """Preview must NOT create a mission instance or write a cooldown."""
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        giver.templates.add(self.template_open)
        postings_for_giver(giver, self.character)
        self.assertFalse(
            MissionInstance.objects.filter(participants__character=self.character).exists()
        )
        self.assertFalse(
            MissionGiverCooldown.objects.filter(giver=giver, character=self.character).exists()
        )

    def test_capped_at_max(self) -> None:
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        for _ in range(MAX_BOARD_POSTINGS + 5):
            t = _template_with_entry(f"capped-{_}")
            giver.templates.add(t)
        postings = postings_for_giver(giver, self.character)
        self.assertEqual(len(postings), MAX_BOARD_POSTINGS)

    def test_returns_board_posting_dataclass(self) -> None:
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        giver.templates.add(self.template_open)
        postings = postings_for_giver(giver, self.character)
        self.assertIsInstance(postings[0], BoardPosting)
        self.assertEqual(postings[0].giver_name, giver.name)

    def test_empty_pool_returns_empty_list(self) -> None:
        giver = MissionGiverFactory(giver_kind=GiverKind.BOARD, target=self.board_obj)
        postings = postings_for_giver(giver, self.character)
        self.assertEqual(postings, [])
