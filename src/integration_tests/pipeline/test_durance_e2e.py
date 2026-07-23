"""End-to-end user-journey tests for the Ritual of the Durance (#1352).

Drives the real draft_session → accept_session → fire_session pipeline, verifying
that advance_class_level_via_session:
  - bumps the inductee's class level,
  - writes a ClassLevelAdvancement receipt with the correct fields, and
  - posts the testament oration as a POSE Interaction in the active scene.

Legend-gate (check_requirements_for_unlock) reads a PG-only materialized view, so
it is patched to return (True, []) throughout.  The real PG-tier legend-gate is
tested in world.progression.tests.test_advancement (tagged @tag("postgres")).

Web-path confirmation: the Durance ritual is a standard INDUCTION SERVICE ritual
and is fully dispatchable through the existing generic RitualSessionViewSet.
The view tests in world.magic.tests.test_session_views already cover the generic
draft → accept → fire flow via the API (including 201 draft, 200 accept, 200 fire
for INDUCTION-rule rituals).  No separate web-path test is added here — the
Durance ritual is structurally identical to CovenantInductionRitual, which those
tests exercise.  See test_session_views.RitualSessionFireTests for the canonical
web-path coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import (
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathFactory,
)
from world.classes.models import PathStage
from world.magic.factories import RitualOfTheDuranceFactory
from world.magic.models.sessions import RitualSession
from world.magic.services.sessions import accept_session, draft_session, fire_session
from world.progression.models import CharacterPathHistory, ClassLevelAdvancement
from world.progression.models.unlocks import CharacterUnlock, ClassLevelUnlock
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction

# Patch target: the legend-gate function called inside advance_class_level_via_session.
# It is imported lazily inside that function from world.progression.services.spends,
# so we patch it at its definition module (matching the pattern in test_advancement.py).
_CHECK_PATH = "world.progression.services.spends.check_requirements_for_unlock"

_ORATION = "I have stood in the crucible and I am ready."


def _wire_path(sheet, path) -> None:
    """Record *path* as the character's current path via CharacterPathHistory."""
    CharacterPathHistory.objects.create(character=sheet, path=path)


def _set_primary_level(sheet, *, character_class, level: int) -> None:
    """Give sheet.character a primary CharacterClassLevel at *level*."""
    CharacterClassLevelFactory(
        character=sheet,
        character_class=character_class,
        level=level,
        is_primary=True,
    )


class DuranceE2ESingleInducteeTests(TestCase):
    """Full lifecycle: draft → accept → fire → level bump + receipt + POSE."""

    def setUp(self) -> None:
        # Shared path so the officiant-lineage guard passes.
        self.path = PathFactory(stage=PathStage.PROSPECT)

        # Officiant: same path, level 10 (strictly above inductee's target 3).
        self.officiant_sheet = CharacterSheetFactory()
        officiant_class = CharacterClassFactory()
        _set_primary_level(self.officiant_sheet, character_class=officiant_class, level=10)
        _wire_path(self.officiant_sheet, self.path)

        # Inductee: same path, level 2 → will advance to 3.
        self.inductee_sheet = CharacterSheetFactory()
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=2)
        _wire_path(self.inductee_sheet, self.path)

        # ClassLevelUnlock for (inductee class, target level 3).
        self.unlock = ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        CharacterUnlock.objects.create(
            character=self.inductee_sheet,
            character_class=self.inductee_class,
            target_level=3,
        )

        # Active scene at the shared location so the testament POSE is posted.
        self.scene = SceneFactory(
            location=self.inductee_sheet.character.location,
            is_active=True,
        )

        self.ritual = RitualOfTheDuranceFactory()

    def test_fire_bumps_inductee_level_and_writes_receipt(self) -> None:
        """Full journey: inductee reaches level 3; receipt has correct fields."""
        session = draft_session(
            ritual=self.ritual,
            initiator=self.officiant_sheet,
            proposed_terms="Durance rite — one inductee.",
            session_kwargs={},
            invitee_sheets=[self.inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session_pk = session.pk

        inductee_participant = session.participants.get(character_sheet=self.inductee_sheet)
        accept_session(
            participant=inductee_participant,
            participant_kwargs={"testament": _ORATION},
            references=[],
        )

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            receipts = fire_session(session=session)

        # Session deleted after fire.
        self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())

        # Exactly one receipt.
        self.assertEqual(len(receipts), 1)
        receipt = receipts[0]

        # Level bump fields.
        self.assertEqual(receipt.level_before, 2)
        self.assertEqual(receipt.level_after, 3)
        self.assertEqual(receipt.character_sheet, self.inductee_sheet)
        self.assertEqual(receipt.character_class, self.inductee_class)
        self.assertEqual(receipt.officiant, self.officiant_sheet)
        self.assertEqual(receipt.ritual, self.ritual)
        # Scene attached.
        self.assertIsNotNone(receipt.scene)

        # current_level reflects the bump.
        self.inductee_sheet.invalidate_class_level_cache()
        self.assertEqual(self.inductee_sheet.current_level, 3)

        # DB row exists.
        self.assertTrue(
            ClassLevelAdvancement.objects.filter(
                character_sheet=self.inductee_sheet,
                level_before=2,
                level_after=3,
            ).exists()
        )

    def test_fire_posts_testament_interaction_in_scene(self) -> None:
        """The testament oration appears as a POSE Interaction in the active scene."""
        session = draft_session(
            ritual=self.ritual,
            initiator=self.officiant_sheet,
            proposed_terms="Durance rite — testament check.",
            session_kwargs={},
            invitee_sheets=[self.inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        inductee_participant = session.participants.get(character_sheet=self.inductee_sheet)
        accept_session(
            participant=inductee_participant,
            participant_kwargs={"testament": _ORATION},
            references=[],
        )

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            fire_session(session=session)

        posed = Interaction.objects.filter(content__startswith=_ORATION)
        self.assertTrue(posed.exists(), "No POSE Interaction was posted for the testament oration.")


class DuranceE2EMultiInducteeTests(TestCase):
    """Two inductees in one session → two receipts, one shared scene."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)

        # Officiant at level 10.
        self.officiant_sheet = CharacterSheetFactory()
        officiant_class = CharacterClassFactory()
        _set_primary_level(self.officiant_sheet, character_class=officiant_class, level=10)
        _wire_path(self.officiant_sheet, self.path)

        # Two inductees sharing the same class (both at level 2 → advance to 3).
        self.shared_class = CharacterClassFactory()
        self.inductee_a = CharacterSheetFactory()
        self.inductee_b = CharacterSheetFactory()
        _set_primary_level(self.inductee_a, character_class=self.shared_class, level=2)
        _set_primary_level(self.inductee_b, character_class=self.shared_class, level=2)
        _wire_path(self.inductee_a, self.path)
        _wire_path(self.inductee_b, self.path)

        ClassLevelUnlock.objects.create(character_class=self.shared_class, target_level=3)
        for inductee in (self.inductee_a, self.inductee_b):
            CharacterUnlock.objects.create(
                character=inductee,
                character_class=self.shared_class,
                target_level=3,
            )

        # Scene at the officiant's location (advance_class_level_via_session uses
        # the inductee's location via _post_declaration → _post_testament; locate
        # all three at the same spot).
        shared_room = ObjectDBFactory()
        self.officiant_sheet.character.location = shared_room
        self.officiant_sheet.character.save()
        self.inductee_a.character.location = shared_room
        self.inductee_a.character.save()
        self.inductee_b.character.location = shared_room
        self.inductee_b.character.save()

        self.scene = SceneFactory(location=shared_room, is_active=True)

        self.ritual = RitualOfTheDuranceFactory()

    def test_fire_produces_two_receipts_one_per_inductee(self) -> None:
        """Both inductees advance; each gets a separate ClassLevelAdvancement row."""
        session = draft_session(
            ritual=self.ritual,
            initiator=self.officiant_sheet,
            proposed_terms="Durance rite — two inductees.",
            session_kwargs={},
            invitee_sheets=[self.inductee_a, self.inductee_b],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        for inductee_sheet in (self.inductee_a, self.inductee_b):
            participant = session.participants.get(character_sheet=inductee_sheet)
            accept_session(
                participant=participant,
                participant_kwargs={"testament": f"Testament from {inductee_sheet.pk}."},
                references=[],
            )

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            receipts = fire_session(session=session)

        self.assertEqual(len(receipts), 2)
        sheets = {r.character_sheet for r in receipts}
        self.assertIn(self.inductee_a, sheets)
        self.assertIn(self.inductee_b, sheets)

        for receipt in receipts:
            self.assertEqual(receipt.level_before, 2)
            self.assertEqual(receipt.level_after, 3)
            self.assertEqual(receipt.officiant, self.officiant_sheet)
            self.assertEqual(receipt.ritual, self.ritual)

        # Both inductees are now level 3.
        for sheet in (self.inductee_a, self.inductee_b):
            sheet.invalidate_class_level_cache()
            self.assertEqual(sheet.current_level, 3)


class DuranceSemiCrossingE2ETests(DuranceE2ESingleInducteeTests):
    """Full draft → accept → fire journey for the level-3 POTENTIAL semi-crossing (#1579):
    the inductee declares a Potential path, and firing the Durance switches them onto it
    and grants its gift + techniques — no Audere Majora involved."""

    def setUp(self) -> None:
        super().setUp()
        from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory
        from world.magic.models import PathGiftGrant

        # A Potential-stage child of the shared prospect path, with a gift + technique.
        self.potential = PathFactory(stage=PathStage.POTENTIAL)
        self.potential.parent_paths.add(self.path)
        self.gift = GiftFactory(name="Pyromancy_durance_e2e")
        self.gift.resonances.add(ResonanceFactory(name="Ember_durance_e2e"))
        self.tech = TechniqueFactory(name="Flame Lash_durance_e2e", gift=self.gift)
        grant = PathGiftGrant.objects.create(path=self.potential, gift=self.gift)
        grant.starter_techniques.add(self.tech)

    def test_fire_semi_crossing_switches_path_and_grants_magic(self) -> None:
        from world.magic.constants import TargetKind
        from world.magic.models import CharacterGift, CharacterTechnique, Thread
        from world.progression.selectors import current_path_for_character

        session = draft_session(
            ritual=self.ritual,
            initiator=self.officiant_sheet,
            proposed_terms="Durance rite — the Potential semi-crossing.",
            session_kwargs={},
            invitee_sheets=[self.inductee_sheet],
            session_references=[],
            initiator_participant_kwargs={},
            initiator_references=[],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        inductee_participant = session.participants.get(character_sheet=self.inductee_sheet)
        # Declare the chosen Potential path at the rite (the level-3 semi-crossing target).
        accept_session(
            participant=inductee_participant,
            participant_kwargs={"testament": _ORATION, "path_id": self.potential.pk},
            references=[],
        )

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            fire_session(session=session)

        # Level bumped to 3 (POTENTIAL).
        self.inductee_sheet.invalidate_class_level_cache()
        self.assertEqual(self.inductee_sheet.current_level, 3)
        # Path switched onto the chosen Potential path — no Audere Majora crossing.
        self.assertEqual(
            current_path_for_character(self.inductee_sheet.character).pk, self.potential.pk
        )
        # The Potential path's gift + technique were granted, latent thread provisioned.
        self.assertTrue(
            CharacterGift.objects.filter(character=self.inductee_sheet, gift=self.gift).exists()
        )
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.inductee_sheet, technique=self.tech
            ).exists()
        )
        self.assertTrue(
            Thread.objects.filter(
                owner=self.inductee_sheet,
                target_kind=TargetKind.GIFT,
                target_gift=self.gift,
            ).exists()
        )
