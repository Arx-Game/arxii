"""Tests for fire_subrole_discoveries — the sub-role discovery beat (#1277 Task 5).

TDD: write failing tests first, then implement fire_subrole_discoveries.

Covered cases:
1. First-ever crossing → Discovery created + CharacterAchievement + CharacterCodexKnowledge
   (status=KNOWN) + gamewide NarrativeMessage (recipients include other active sheets).
2. Second character crossing same combo → no new Discovery; personal message only.
3. Replay / re-imbue with no new level → idempotency gate; no duplicate achievement/message.
4. Thread resonance has no authored sub-role → no beat (silent no-op).
5. Sub-role with null discovery_achievement / null codex_entry → no crash; graceful skip.
"""

from __future__ import annotations

from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.achievements.models import CharacterAchievement, Discovery
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.covenants.factories import SubroleCovenantRoleFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
)
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


def _make_active_sheet():
    """Create a CharacterSheet with a current RosterTenure (active player)."""
    from world.character_sheets.factories import CharacterSheetFactory

    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, end_date=None)
    return sheet


def _make_covenant_role_thread(*, sheet, resonance, role, level=0, developed_points=0):
    """Create a COVENANT_ROLE Thread for sheet with the given role + resonance.

    Uses Thread.objects.create directly to avoid the ThreadFactory's default
    target_trait SubFactory, which would violate the COVENANT_ROLE payload
    CHECK constraint.
    """
    from world.magic.models import Thread

    return Thread.objects.create(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.COVENANT_ROLE,
        target_covenant_role=role,
        level=level,
        developed_points=developed_points,
        name=f"Thread for {role.name}",
    )


class FireSubroleDiscoveriesFirstEverTest(TestCase):
    """Case 1: First-ever crossing unlocks achievement + codex + gamewide message."""

    def setUp(self):
        self.resonance = ResonanceFactory()
        self.ach = AchievementFactory(slug="sub-discovery-first-1")
        self.codex_entry = CodexEntryFactory()

        from world.covenants.factories import CovenantRoleFactory

        self.parent_role = CovenantRoleFactory()
        self.sub = SubroleCovenantRoleFactory(
            parent_role=self.parent_role,
            resonance=self.resonance,
            unlock_thread_level=5,
            discovery_achievement=self.ach,
            codex_entry=self.codex_entry,
        )

        # Primary character: has an active tenure + a CharacterResonance
        self.sheet = _make_active_sheet()
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

        # Second active sheet — must receive the gamewide message
        self.other_sheet = _make_active_sheet()

        self.thread = _make_covenant_role_thread(
            sheet=self.sheet,
            resonance=self.resonance,
            role=self.parent_role,
        )

    def test_discovery_created_on_first_crossing(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        self.assertTrue(Discovery.objects.filter(achievement=self.ach).exists())

    def test_character_achievement_created(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=self.sheet, achievement=self.ach
            ).exists()
        )

    def test_codex_knowledge_created_with_known_status(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        roster_entry = self.sheet.roster_entry
        ck = CharacterCodexKnowledge.objects.get(roster_entry=roster_entry, entry=self.codex_entry)
        self.assertEqual(ck.status, CodexKnowledgeStatus.KNOWN)

    def test_gamewide_narrative_message_includes_other_active_sheet(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        deliveries = NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=self.other_sheet,
        )
        self.assertTrue(
            deliveries.exists(),
            "Gamewide message should reach other active sheet on first-ever discovery.",
        )

    def test_gamewide_narrative_message_includes_discovering_sheet(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        deliveries = NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=self.sheet,
        )
        self.assertTrue(deliveries.exists())

    def test_narrative_message_category_covenant(self):
        from world.covenants.discovery import fire_subrole_discoveries
        from world.narrative.constants import NarrativeCategory

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        msg = NarrativeMessage.objects.order_by("-id").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.category, NarrativeCategory.COVENANT)


class FireSubroleDiscoveriesSecondCharacterTest(TestCase):
    """Case 2: Second character crosses — no new Discovery; personal message only."""

    def setUp(self):
        self.resonance = ResonanceFactory()
        self.ach = AchievementFactory(slug="sub-discovery-second-1")
        self.codex_entry = CodexEntryFactory()

        from world.covenants.factories import CovenantRoleFactory

        self.parent_role = CovenantRoleFactory()
        self.sub = SubroleCovenantRoleFactory(
            parent_role=self.parent_role,
            resonance=self.resonance,
            unlock_thread_level=5,
            discovery_achievement=self.ach,
            codex_entry=self.codex_entry,
        )

        # First character — already earned the achievement
        self.sheet1 = _make_active_sheet()
        CharacterResonanceFactory(character_sheet=self.sheet1, resonance=self.resonance)
        thread1 = _make_covenant_role_thread(
            sheet=self.sheet1,
            resonance=self.resonance,
            role=self.parent_role,
        )

        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=thread1, starting_level=4, new_level=5)

        # Second character
        self.sheet2 = _make_active_sheet()
        CharacterResonanceFactory(character_sheet=self.sheet2, resonance=self.resonance)
        self.thread2 = _make_covenant_role_thread(
            sheet=self.sheet2,
            resonance=self.resonance,
            role=self.parent_role,
        )

    def test_no_new_discovery_for_second_character(self):
        from world.covenants.discovery import fire_subrole_discoveries

        before = Discovery.objects.filter(achievement=self.ach).count()
        fire_subrole_discoveries(thread=self.thread2, starting_level=4, new_level=5)
        after = Discovery.objects.filter(achievement=self.ach).count()
        self.assertEqual(before, after, "No new Discovery should be created for second character.")

    def test_second_character_gets_personal_message_only(self):
        from world.covenants.discovery import fire_subrole_discoveries

        # Clear any messages from the first character's discovery
        NarrativeMessage.objects.all().delete()
        NarrativeMessageDelivery.objects.all().delete()

        fire_subrole_discoveries(thread=self.thread2, starting_level=4, new_level=5)

        # sheet2 should get a message
        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=self.sheet2).exists()
        )

        # sheet1 should NOT get a message (personal only)
        self.assertFalse(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=self.sheet1).exists(),
            "Second character's message should be personal — sheet1 must not receive it.",
        )


class FireSubroleDiscoveriesIdempotencyTest(TestCase):
    """Case 3: Re-imbue / no level gain — idempotency gate."""

    def setUp(self):
        self.resonance = ResonanceFactory()
        self.ach = AchievementFactory(slug="sub-discovery-idempotency-1")

        from world.covenants.factories import CovenantRoleFactory

        self.parent_role = CovenantRoleFactory()
        self.sub = SubroleCovenantRoleFactory(
            parent_role=self.parent_role,
            resonance=self.resonance,
            unlock_thread_level=5,
            discovery_achievement=self.ach,
            codex_entry=None,
        )

        self.sheet = _make_active_sheet()
        self.thread = _make_covenant_role_thread(
            sheet=self.sheet,
            resonance=self.resonance,
            role=self.parent_role,
        )

    def test_no_beat_when_no_level_gain(self):
        from world.covenants.discovery import fire_subrole_discoveries

        # Same level — no crossing
        fire_subrole_discoveries(thread=self.thread, starting_level=5, new_level=5)

        self.assertFalse(CharacterAchievement.objects.filter(achievement=self.ach).exists())

    def test_no_duplicate_achievement_on_replay(self):
        from world.covenants.discovery import fire_subrole_discoveries

        # First crossing
        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)
        count_after_first = CharacterAchievement.objects.filter(
            character_sheet=self.sheet, achievement=self.ach
        ).count()

        # Replay with same or higher range (idempotency gate must skip)
        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)
        count_after_replay = CharacterAchievement.objects.filter(
            character_sheet=self.sheet, achievement=self.ach
        ).count()

        self.assertEqual(count_after_first, count_after_replay)

    def test_no_duplicate_message_on_replay(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)
        count_after_first = NarrativeMessage.objects.count()

        # Replay — idempotency gate means no new message
        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)
        count_after_replay = NarrativeMessage.objects.count()

        self.assertEqual(count_after_first, count_after_replay)


class FireSubroleDiscoveriesNoSubroleTest(TestCase):
    """Case 4: Thread resonance has no authored sub-role → no beat."""

    def setUp(self):
        self.resonance = ResonanceFactory()
        from world.covenants.factories import CovenantRoleFactory

        self.parent_role = CovenantRoleFactory()
        # No SubroleCovenantRoleFactory created for this resonance + parent combo.

        self.sheet = _make_active_sheet()
        self.thread = _make_covenant_role_thread(
            sheet=self.sheet,
            resonance=self.resonance,
            role=self.parent_role,
        )

    def test_no_achievement_when_no_subrole_authored(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        self.assertEqual(CharacterAchievement.objects.count(), 0)

    def test_no_message_when_no_subrole_authored(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        self.assertEqual(NarrativeMessage.objects.count(), 0)


class FireSubroleDiscoveriesNullFKsTest(TestCase):
    """Case 5: Sub-role with null discovery_achievement / null codex_entry — no crash."""

    def setUp(self):
        self.resonance = ResonanceFactory()
        from world.covenants.factories import CovenantRoleFactory

        self.parent_role = CovenantRoleFactory()
        # Sub-role with both FKs null
        self.sub = SubroleCovenantRoleFactory(
            parent_role=self.parent_role,
            resonance=self.resonance,
            unlock_thread_level=3,
            discovery_achievement=None,
            codex_entry=None,
        )

        self.sheet = _make_active_sheet()
        self.thread = _make_covenant_role_thread(
            sheet=self.sheet,
            resonance=self.resonance,
            role=self.parent_role,
        )

    def test_no_crash_with_null_achievement_and_codex(self):
        from world.covenants.discovery import fire_subrole_discoveries

        # Must not raise
        fire_subrole_discoveries(thread=self.thread, starting_level=2, new_level=3)

    def test_no_achievement_created_when_null(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=2, new_level=3)

        self.assertEqual(CharacterAchievement.objects.count(), 0)

    def test_message_still_sent_when_null_fks(self):
        """Even with null achievement/codex, a personal narrative message is still fired."""
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=2, new_level=3)

        # is_first=False because no achievement was granted; personal message to sheet
        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=self.sheet).exists()
        )


class FireSubroleDiscoveriesNonCovenantThreadTest(TestCase):
    """Non-COVENANT_ROLE thread → early return (no-op)."""

    def setUp(self):
        self.sheet = _make_active_sheet()
        self.thread = ThreadFactory(
            owner=self.sheet,
            target_kind=TargetKind.TRAIT,
            level=5,
        )

    def test_no_beat_for_non_covenant_role_thread(self):
        from world.covenants.discovery import fire_subrole_discoveries

        fire_subrole_discoveries(thread=self.thread, starting_level=4, new_level=5)

        self.assertEqual(NarrativeMessage.objects.count(), 0)
        self.assertEqual(CharacterAchievement.objects.count(), 0)
