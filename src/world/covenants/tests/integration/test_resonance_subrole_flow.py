"""End-to-end integration test for resonance sub-role resolution + discovery beat (#1277).

Full flow:
  seed_resonance_subrole_slice → character holds engaged parent role → weaves a
  COVENANT_ROLE thread at the sub-role's resonance → imbue past unlock_thread_level via
  spend_resonance_for_imbuing → sub-role resolves via currently_engaged_roles → discovery
  beat fires (Achievement + Codex + gamewide NarrativeMessage).
"""

from __future__ import annotations

from django.test import TestCase

from world.achievements.models import CharacterAchievement, Discovery
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import CharacterCodexKnowledge
from world.covenants.factories import (
    CovenantFactory,
    make_engaged_member,
    seed_resonance_subrole_slice,
)
from world.magic.constants import TargetKind
from world.magic.factories import CharacterResonanceFactory
from world.magic.models import Thread
from world.magic.services import spend_resonance_for_imbuing
from world.mechanics.services import covenant_role_base_total
from world.narrative.models import NarrativeMessageDelivery
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _make_active_sheet():
    """CharacterSheet with an active RosterTenure (active player)."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, end_date=None)
    return sheet


class ResonanceSubroleEndToEndTest(TestCase):
    """Full flow: imbue past unlock_thread_level → sub-role resolves + discovery fires."""

    def setUp(self) -> None:
        # Seed the parent role + two resonance sub-roles (unlock_thread_level=3 each).
        parent_role = None  # seed_resonance_subrole_slice creates the parent internally
        self.subroles = seed_resonance_subrole_slice(parent_role=parent_role)
        self.subrole = self.subroles[0]
        self.parent_role = self.subrole.parent_role
        self.resonance = self.subrole.resonance

        # Primary character: active roster tenure so they appear in active_player_character_sheets.
        self.sheet = _make_active_sheet()

        # Give the character a level so covenant_role_base_total returns > 0.
        CharacterClassLevelFactory(character=self.sheet, level=5, is_primary=True)
        self.sheet.invalidate_class_level_cache()

        # Covenant + engaged membership on the parent role.
        # make_engaged_member creates and engages the membership.
        self.covenant = CovenantFactory(covenant_type=self.parent_role.covenant_type)
        self.membership = make_engaged_member(
            character_sheet=self.sheet,
            covenant=self.covenant,
            covenant_role=self.parent_role,
        )

        # Second active sheet — must receive the gamewide narrative message.
        self.other_sheet = _make_active_sheet()

        # CharacterResonance row so spend_resonance_for_imbuing can find a balance.
        # Create at level 2 (one below unlock_thread_level=3); cost to advance is 1 dp.
        self.cr = CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=10,
        )

        # COVENANT_ROLE thread at level 2, anchored on parent_role with the sub-role's resonance.
        self.thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            level=2,
            developed_points=0,
            name=f"Thread for {self.parent_role.name}",
        )

    # ------------------------------------------------------------------
    # (a) Sub-role resolution
    # ------------------------------------------------------------------

    def test_currently_engaged_roles_returns_subrole_after_threshold(self) -> None:
        """After crossing unlock_thread_level, currently_engaged_roles() returns the sub-role."""
        spend_resonance_for_imbuing(self.sheet, self.thread, 1)

        char = self.sheet.character
        # Invalidate both the thread cache (so resolve_effective_role sees the updated level)
        # and the covenant-roles cache (which stores the resolved list).
        char.threads.invalidate()
        char.covenant_roles.invalidate()
        engaged = char.covenant_roles.currently_engaged_roles()

        self.assertIn(self.subrole, engaged, "Sub-role must appear in currently_engaged_roles().")
        self.assertNotIn(
            self.parent_role,
            engaged,
            "Parent role must NOT appear once sub-role resolves.",
        )

    # ------------------------------------------------------------------
    # (b) CovenantRoleBonus applies via covenant_role_base_total
    # ------------------------------------------------------------------

    def test_covenant_role_base_total_positive_after_resolution(self) -> None:
        """covenant_role_base_total returns > 0 once the sub-role resolves."""
        spend_resonance_for_imbuing(self.sheet, self.thread, 1)

        char = self.sheet.character
        char.threads.invalidate()
        char.covenant_roles.invalidate()

        # The sub-role has a CovenantRoleBonus row from seed_resonance_subrole_slice.
        bonus_row = self.subrole.role_bonuses.first()
        self.assertIsNotNone(bonus_row, "seed_resonance_subrole_slice must create a bonus row.")

        total = covenant_role_base_total(self.sheet, bonus_row.modifier_target)
        self.assertGreater(total, 0, "covenant_role_base_total must be > 0 once sub-role engaged.")

    # ------------------------------------------------------------------
    # (c) Discovery + CharacterAchievement + CharacterCodexKnowledge(KNOWN)
    # ------------------------------------------------------------------

    def test_discovery_created(self) -> None:
        """Discovery row is created for the sub-role's achievement on first crossing."""
        spend_resonance_for_imbuing(self.sheet, self.thread, 1)

        ach = self.subrole.discovery_achievement
        self.assertIsNotNone(ach)
        self.assertTrue(
            Discovery.objects.filter(achievement=ach).exists(),
            "Discovery must be created for the achievement on first crossing.",
        )

    def test_character_achievement_granted(self) -> None:
        """CharacterAchievement row is created for the discovering character."""
        spend_resonance_for_imbuing(self.sheet, self.thread, 1)

        ach = self.subrole.discovery_achievement
        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=ach
            ).exists(),
            "CharacterAchievement must be granted on threshold crossing.",
        )

    def test_codex_knowledge_created_with_known_status(self) -> None:
        """CharacterCodexKnowledge(status=KNOWN) is created for the sub-role's codex_entry."""
        spend_resonance_for_imbuing(self.sheet, self.thread, 1)

        entry = self.subrole.codex_entry
        self.assertIsNotNone(entry)
        roster_entry = self.sheet.roster_entry
        ck = CharacterCodexKnowledge.objects.get(roster_entry=roster_entry, entry=entry)
        self.assertEqual(ck.status, CodexKnowledgeStatus.KNOWN)

    # ------------------------------------------------------------------
    # (d) Gamewide NarrativeMessage on first-ever discovery
    # ------------------------------------------------------------------

    def test_gamewide_narrative_message_reaches_other_active_sheet(self) -> None:
        """First-ever discovery sends a gamewide message; the other active sheet receives it."""
        spend_resonance_for_imbuing(self.sheet, self.thread, 1)

        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.other_sheet
            ).exists(),
            "Gamewide message must reach other active sheet on first-ever discovery.",
        )

    def test_gamewide_narrative_message_reaches_discovering_sheet(self) -> None:
        """The discovering character also receives the gamewide message."""
        spend_resonance_for_imbuing(self.sheet, self.thread, 1)

        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=self.sheet).exists(),
            "Discovering sheet must also receive the gamewide message.",
        )

    # ------------------------------------------------------------------
    # Sanity: anchor_role_in still returns the stored parent
    # ------------------------------------------------------------------

    def test_anchor_role_in_returns_parent_after_subrole_resolution(self) -> None:
        """anchor_role_in() must return the stored parent role regardless of sub-role resolution."""
        spend_resonance_for_imbuing(self.sheet, self.thread, 1)

        char = self.sheet.character
        char.threads.invalidate()
        char.covenant_roles.invalidate()
        anchor = char.covenant_roles.anchor_role_in(self.covenant)
        self.assertEqual(anchor, self.parent_role)
