"""Telnet E2E: weaving a RELATIONSHIP_TRACK thread + imbuing it (#2033, #3957).

Proves the ``weave track=<partner>/<type name>`` grammar added by #2033 reaches
the real ``WeaveThreadAction`` → ``weave_thread`` seam exactly like the
TRAIT-anchored reference grammar (#1337), and that the kind-agnostic
``imbue`` finisher accepts the resulting thread with no special-casing.

Steps:
  1. CmdRitual → Rite of Weaving ceremony  → PendingRitualEffect (weaving)
  2. CmdWeaveThread → ``weave resonance=<r> track=<partner>/<type>``
     → RELATIONSHIP_TRACK Thread row created, anchored to the caller's OWN
       ``CharacterRelationship`` side toward the partner, effect consumed
  3. CmdRitual → Rite of Imbuing ceremony  → PendingRitualEffect (imbuing)
  4. CmdImbue → imbue the woven thread     → developed_points advances,
     effect consumed (imbue is kind-agnostic — no RELATIONSHIP_TRACK-specific
     code path exists or is needed)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.imbue import CmdImbue
from commands.ritual import CmdRitual
from commands.weave import CmdWeaveThread
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    WeavingCeremonyFactory,
)
from world.magic.models import PendingRitualEffect, Thread
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipLabelFactory,
    RelationshipTypeFactory,
)


class WeaveRelationshipTrackImbueE2ETests(TestCase):
    """RELATIONSHIP_TRACK weave, end to end via telnet, then imbued."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        from world.magic.factories import CharacterAuraFactory

        CharacterAuraFactory(character=cls.sheet)  # Gifted: hedge gate (#3001)
        cls.partner_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory(name="Embers")
        cls.rel_type = RelationshipTypeFactory(name="Trust")

        cls.relationship = CharacterRelationshipFactory(source=cls.sheet, target=cls.partner_sheet)
        # invested_depth=50 → pair_depth()=50 (no reverse side, so pair_depth is just
        # this side's own depth) — RELATIONSHIP_TRACK anchor cap is the tie's pair
        # depth (#3957), plenty of room for the level-0 → 5 imbue advance below.
        # tier=2 clears the default RelationshipGrowthConfig.thread_min_tier gate.
        cls.relationship.invested_depth = 50
        cls.relationship.tier = 2
        cls.relationship.save()
        RelationshipLabelFactory(relationship=cls.relationship, type=cls.rel_type)

        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_type=cls.rel_type,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock, xp_spent=100)

        cls.weaving_ritual = WeavingCeremonyFactory()
        cls.imbuing_ritual = ImbuingRitualFactory()

        # Resonance balance: enough to imbue (amount=5).
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )

    def _cmd_ritual(self, character: object, ritual_name: str) -> None:
        cmd = CmdRitual()
        cmd.caller = character
        cmd.args = ritual_name
        cmd.raw_string = f"ritual {ritual_name}"
        cmd.func()

    def test_weave_relationship_track_then_imbue(self) -> None:
        character = self.sheet.character
        character.msg = MagicMock()
        character.search = MagicMock(return_value=self.partner_sheet.character)

        # Step 1: Rite of Weaving ceremony.
        self._cmd_ritual(character, self.weaving_ritual.name)
        self.assertTrue(
            PendingRitualEffect.objects.filter(
                character=self.sheet, ritual=self.weaving_ritual
            ).exists(),
            "Step 1: PendingRitualEffect for Rite of Weaving must exist after ceremony.",
        )

        # Step 2: weave the RELATIONSHIP_TRACK thread via the real telnet command.
        cmd = CmdWeaveThread()
        cmd.caller = character
        cmd.args = "resonance=Embers track=Partner/Trust name=Bound to Partner"
        cmd.raw_string = f"weave {cmd.args}"
        cmd.func()

        thread = Thread.objects.get(owner=self.sheet, name="Bound to Partner")
        self.assertEqual(thread.target_kind, TargetKind.RELATIONSHIP_TRACK)
        self.assertEqual(thread.target_relationship, self.relationship)
        self.assertEqual(thread.resonance, self.resonance)
        self.assertFalse(
            PendingRitualEffect.objects.filter(
                character=self.sheet, ritual=self.weaving_ritual
            ).exists(),
            "Step 2: PendingRitualEffect for Rite of Weaving must be consumed after weave.",
        )

        # Step 3: Rite of Imbuing ceremony.
        self._cmd_ritual(character, self.imbuing_ritual.name)
        self.assertTrue(
            PendingRitualEffect.objects.filter(
                character=self.sheet, ritual=self.imbuing_ritual
            ).exists(),
            "Step 3: PendingRitualEffect for Rite of Imbuing must exist after ceremony.",
        )

        # Step 4: imbue — kind-agnostic finisher accepts the RELATIONSHIP_TRACK thread.
        level_before = thread.level  # 0
        cmd_imbue = CmdImbue()
        cmd_imbue.caller = character
        cmd_imbue.args = "thread=Bound to Partner amount=5"
        cmd_imbue.raw_string = f"imbue {cmd_imbue.args}"
        cmd_imbue.func()

        thread.refresh_from_db()
        self.assertGreater(
            thread.level,
            level_before,
            "Step 4: Thread level must advance after imbuing 5 resonance.",
        )
        self.assertFalse(
            PendingRitualEffect.objects.filter(
                character=self.sheet, ritual=self.imbuing_ritual
            ).exists(),
            "Step 4: PendingRitualEffect for Rite of Imbuing must be consumed after imbue.",
        )
