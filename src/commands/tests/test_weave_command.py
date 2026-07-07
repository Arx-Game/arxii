"""Tests for CmdWeaveThread — the thin telnet shell over WeaveThreadAction (#1337, #2033)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.exceptions import CommandError
from commands.weave import CmdWeaveThread
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    WeavingCeremonyFactory,
)
from world.magic.models import PendingRitualEffect, Thread
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.traits.factories import TraitFactory


class CmdWeaveThreadTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory(name="Embers")
        cls.trait = TraitFactory()
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=cls.trait)
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock, xp_spent=100)
        cls.weaving_ritual = WeavingCeremonyFactory()

    def setUp(self) -> None:
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        # Each test needs a fresh PendingRitualEffect since the action consumes it.
        PendingRitualEffect.objects.get_or_create(character=self.sheet, ritual=self.weaving_ritual)

    def _run(self, args: str) -> None:
        cmd = CmdWeaveThread()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"weave {args}"
        cmd.func()

    def test_weave_creates_thread(self) -> None:
        self._run(f"resonance=Embers trait={self.trait.pk}")
        self.assertTrue(Thread.objects.filter(owner=self.sheet, resonance=self.resonance).exists())
        self.character.msg.assert_called()

    def test_weave_passes_optional_name(self) -> None:
        self._run(f"resonance=Embers trait={self.trait.pk} name=My Bright Thread")
        thread = Thread.objects.get(owner=self.sheet, resonance=self.resonance)
        self.assertEqual(thread.name, "My Bright Thread")

    def test_unknown_resonance_reports_error(self) -> None:
        self._run(f"resonance=Nope trait={self.trait.pk}")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()

    def test_missing_trait_reports_error(self) -> None:
        self._run("resonance=Embers")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()

    def test_unknown_trait_reports_error(self) -> None:
        self._run("resonance=Embers trait=99999")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()

    def test_weave_fails_without_pending_effect(self) -> None:
        PendingRitualEffect.objects.filter(
            character=self.sheet, ritual=self.weaving_ritual
        ).delete()
        self._run(f"resonance=Embers trait={self.trait.pk}")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()

    def test_resolve_trait_by_name(self) -> None:
        self._run(f"resonance=Embers trait={self.trait.name}")
        self.assertTrue(Thread.objects.filter(owner=self.sheet, resonance=self.resonance).exists())

    def test_resolve_trait_by_pk(self) -> None:
        # Re-create the effect because the name test above consumed it.
        PendingRitualEffect.objects.get_or_create(character=self.sheet, ritual=self.weaving_ritual)
        self._run(f"resonance=Embers trait={self.trait.pk}")
        self.assertTrue(Thread.objects.filter(owner=self.sheet, resonance=self.resonance).exists())

    def test_specifying_two_anchors_reports_error(self) -> None:
        self._run(f"resonance=Embers trait={self.trait.pk} facet=1")
        self.assertFalse(Thread.objects.filter(owner=self.sheet, resonance=self.resonance).exists())
        self.character.msg.assert_called()


class CmdWeaveThreadRelationshipTrackTests(TestCase):
    """``weave track=<partner>/<track name>`` — RELATIONSHIP_TRACK anchor (#2033)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.partner_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory(name="Embers")
        cls.track = RelationshipTrackFactory(name="Trust")
        cls.relationship = CharacterRelationshipFactory(source=cls.sheet, target=cls.partner_sheet)
        cls.progress = RelationshipTrackProgressFactory(
            relationship=cls.relationship, track=cls.track, developed_points=10
        )
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=cls.track,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock, xp_spent=100)
        cls.weaving_ritual = WeavingCeremonyFactory()

    def setUp(self) -> None:
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        self.character.search = MagicMock(return_value=self.partner_sheet.character)
        PendingRitualEffect.objects.get_or_create(character=self.sheet, ritual=self.weaving_ritual)

    def _run(self, args: str) -> None:
        cmd = CmdWeaveThread()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"weave {args}"
        cmd.func()

    def test_weave_creates_relationship_track_thread(self) -> None:
        self._run("resonance=Embers track=Marcus/Trust")
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet,
                resonance=self.resonance,
                target_kind=TargetKind.RELATIONSHIP_TRACK,
                target_relationship_track=self.progress,
            ).exists()
        )
        self.character.msg.assert_called()

    def test_weave_track_missing_slash_reports_error(self) -> None:
        self._run("resonance=Embers track=Marcus")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()

    def test_weave_track_unknown_partner_reports_error(self) -> None:
        self.character.search = MagicMock(return_value=None)
        self._run("resonance=Embers track=Nobody/Trust")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()

    def test_weave_track_undeveloped_track_reports_error(self) -> None:
        self._run("resonance=Embers track=Marcus/Respect")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()


class CmdWeaveThreadRelationshipCapstoneTests(TestCase):
    """``weave capstone=<id or title>`` — RELATIONSHIP_CAPSTONE anchor (#2033)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.partner_sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory(name="Embers")
        cls.track = RelationshipTrackFactory(name="Trust")
        cls.relationship = CharacterRelationshipFactory(source=cls.sheet, target=cls.partner_sheet)
        cls.capstone = RelationshipCapstoneFactory(
            relationship=cls.relationship,
            author=cls.sheet,
            track=cls.track,
            title="TheVow",
        )
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=cls.track,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=unlock, xp_spent=100)
        cls.weaving_ritual = WeavingCeremonyFactory()

    def setUp(self) -> None:
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        PendingRitualEffect.objects.get_or_create(character=self.sheet, ritual=self.weaving_ritual)

    def _run(self, args: str) -> None:
        cmd = CmdWeaveThread()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"weave {args}"
        cmd.func()

    def test_weave_creates_capstone_thread_by_id(self) -> None:
        self._run(f"resonance=Embers capstone={self.capstone.pk}")
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet,
                target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
                target_capstone=self.capstone,
            ).exists()
        )
        self.character.msg.assert_called()

    def test_weave_creates_capstone_thread_by_title(self) -> None:
        self._run("resonance=Embers capstone=TheVow")
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet,
                target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
                target_capstone=self.capstone,
            ).exists()
        )

    def test_weave_capstone_unknown_reports_error(self) -> None:
        self._run("resonance=Embers capstone=99999")
        self.assertFalse(Thread.objects.filter(owner=self.sheet).exists())
        self.character.msg.assert_called()


class CmdWeaveThreadAnchorResolutionTests(TestCase):
    """Direct ``resolve_action_args()`` calls proving each new anchor kwarg dispatches
    to the correct ``TargetKind`` and resolves the right target object (#2033).

    Full weave-success gating for these anchor kinds (unlock/ownership/mantle
    clearance) is already covered by the service-level tests in
    ``world/magic/tests/``; this class proves only the command-layer parsing +
    resolution wiring this issue adds.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory(name="Embers")

    def setUp(self) -> None:
        self.character = self.sheet.character

    def _cmd(self, args: str) -> CmdWeaveThread:
        cmd = CmdWeaveThread()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"weave {args}"
        return cmd

    def test_resolve_facet_anchor_by_id(self) -> None:
        from world.magic.factories import FacetFactory

        facet = FacetFactory()
        result = self._cmd(f"resonance=Embers facet={facet.pk}").resolve_action_args()
        self.assertEqual(result["target_kind"], TargetKind.FACET)
        self.assertEqual(result["target"], facet)

    def test_resolve_facet_anchor_unknown_reports_error(self) -> None:
        with self.assertRaises(CommandError):
            self._cmd("resonance=Embers facet=NoSuchFacet").resolve_action_args()

    def test_resolve_technique_anchor_by_id(self) -> None:
        from world.magic.factories import TechniqueFactory

        technique = TechniqueFactory()
        result = self._cmd(f"resonance=Embers technique={technique.pk}").resolve_action_args()
        self.assertEqual(result["target_kind"], TargetKind.TECHNIQUE)
        self.assertEqual(result["target"], technique)

    def test_resolve_technique_anchor_unknown_reports_error(self) -> None:
        with self.assertRaises(CommandError):
            self._cmd("resonance=Embers technique=999999").resolve_action_args()

    def test_resolve_role_anchor_by_id(self) -> None:
        from world.covenants.factories import CovenantRoleFactory

        role = CovenantRoleFactory()
        result = self._cmd(f"resonance=Embers role={role.pk}").resolve_action_args()
        self.assertEqual(result["target_kind"], TargetKind.COVENANT_ROLE)
        self.assertEqual(result["target"], role)

    def test_resolve_role_anchor_unknown_reports_error(self) -> None:
        with self.assertRaises(CommandError):
            self._cmd("resonance=Embers role=NoSuchRole").resolve_action_args()

    def test_resolve_mantle_anchor_by_id(self) -> None:
        from world.items.factories import MantleFactory

        mantle = MantleFactory()
        result = self._cmd(f"resonance=Embers mantle={mantle.pk}").resolve_action_args()
        self.assertEqual(result["target_kind"], TargetKind.MANTLE)
        self.assertEqual(result["target"], mantle)

    def test_resolve_mantle_anchor_unknown_reports_error(self) -> None:
        with self.assertRaises(CommandError):
            self._cmd("resonance=Embers mantle=NoSuchMantle").resolve_action_args()

    def test_specifying_no_anchor_reports_error(self) -> None:
        with self.assertRaises(CommandError):
            self._cmd("resonance=Embers").resolve_action_args()
