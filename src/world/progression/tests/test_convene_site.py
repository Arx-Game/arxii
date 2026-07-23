"""Tests for convene_durance_at_site service + NoDuranceSiteError (#1700).

TDD: RED → GREEN.  The tests mirror the setUp pattern of test_durance_e2e.py.
Legend-gate (check_requirements_for_unlock) reads a PG-only materialized view,
so it is patched to return (True, []) in the happy-path tests.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.areas.services import get_room_profile
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import (
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathFactory,
)
from world.classes.models import PathStage
from world.magic.factories import RitualOfTheDuranceFactory
from world.magic.models.sessions import RitualSession
from world.progression.exceptions import (
    AdvancementRequirementsNotMet,
    AdvancementUnlockNotPurchasedError,
    NoDuranceSiteError,
    TierBoundaryRequiresCrossing,
)
from world.progression.factories import DuranceTrainingSiteFactory
from world.progression.models import CharacterPathHistory, CharacterUnlock, ClassLevelUnlock
from world.progression.services.advancement import convene_durance_at_site

# Patch target: the legend-gate function (called lazily inside convene_durance_at_site).
_CHECK_PATH = "world.progression.services.spends.check_requirements_for_unlock"


def _wire_path(sheet, path) -> None:
    """Record *path* as the character's current path via CharacterPathHistory."""
    CharacterPathHistory.objects.create(character=sheet, path=path)


def _set_primary_level(sheet, *, character_class, level: int) -> None:
    """Give sheet.character a primary CharacterClassLevel at *level*."""
    CharacterClassLevelFactory(
        character=sheet.character,
        character_class=character_class,
        level=level,
        is_primary=True,
    )


def _place_in_room(sheet, room) -> None:
    """Move a character into *room* (ObjectDB) and persist the change."""
    sheet.character.location = room
    sheet.character.save()


def _purchase_unlock(sheet, unlock) -> None:
    """Record the XP-unlock purchase gate as satisfied for ``sheet`` (#2116)."""
    CharacterUnlock.objects.create(
        character=sheet,
        character_class=unlock.character_class,
        target_level=unlock.target_level,
    )


class ConveneDuranceSiteEligibleTests(TestCase):
    """Happy path: eligible site → drafted session with trainer as initiator."""

    def setUp(self) -> None:
        # Shared path so the officiant-lineage guard passes.
        self.path = PathFactory(stage=PathStage.PROSPECT)

        # Trainer (officiant): same path, level 10 (strictly above inductee's target 3).
        self.trainer_sheet = CharacterSheetFactory()
        trainer_class = CharacterClassFactory()
        _set_primary_level(self.trainer_sheet, character_class=trainer_class, level=10)
        _wire_path(self.trainer_sheet, self.path)

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
        _purchase_unlock(self.inductee_sheet, self.unlock)

        # Durance Ritual row (get_or_create so safe to call multiple times).
        self.ritual = RitualOfTheDuranceFactory()

        # Place both characters in the same explicit room.
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.trainer_sheet, self.room)
        _place_in_room(self.inductee_sheet, self.room)

        # Training site keyed to the room's profile.
        self.site = DuranceTrainingSiteFactory(
            room_profile=get_room_profile(self.room),
            officiant=self.trainer_sheet,
            is_active=True,
        )

    def test_eligible_site_returns_session_with_trainer_as_initiator(self) -> None:
        """convene_durance_at_site returns a session whose initiator is the trainer."""
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            session = convene_durance_at_site(
                inductee_sheet=self.inductee_sheet,
                room=self.room,
            )

        self.assertIsInstance(session, RitualSession)
        self.assertEqual(session.initiator, self.trainer_sheet)

    def test_eligible_site_returns_session_with_inductee_invited(self) -> None:
        """The drafted session has the inductee as an INVITED participant."""
        from world.magic.constants import ParticipantState

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            session = convene_durance_at_site(
                inductee_sheet=self.inductee_sheet,
                room=self.room,
            )

        participant = session.participants.filter(
            character_sheet=self.inductee_sheet,
            state=ParticipantState.INVITED,
        )
        self.assertTrue(
            participant.exists(),
            "Inductee should appear as an INVITED participant in the drafted session.",
        )

    def test_eligible_site_links_the_durance_ritual(self) -> None:
        """The drafted session references the Ritual of the Durance row."""
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            session = convene_durance_at_site(
                inductee_sheet=self.inductee_sheet,
                room=self.room,
            )

        self.assertEqual(session.ritual, self.ritual)


class ConveneDuranceSiteNoSiteTests(TestCase):
    """No active site in the room → NoDuranceSiteError."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)

        self.inductee_sheet = CharacterSheetFactory()
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=2)
        _wire_path(self.inductee_sheet, self.path)

        unlock = ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        _purchase_unlock(self.inductee_sheet, unlock)
        RitualOfTheDuranceFactory()

        # An explicit room with no DuranceTrainingSite.
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.inductee_sheet, self.room)

    def test_no_site_raises_no_durance_site_error(self) -> None:
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            with self.assertRaises(NoDuranceSiteError):
                convene_durance_at_site(
                    inductee_sheet=self.inductee_sheet,
                    room=self.room,
                )


class ConveneDuranceSiteUnmetRequirementsTests(TestCase):
    """Unmet requirements → AdvancementRequirementsNotMet before site check."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)

        self.trainer_sheet = CharacterSheetFactory()
        trainer_class = CharacterClassFactory()
        _set_primary_level(self.trainer_sheet, character_class=trainer_class, level=10)
        _wire_path(self.trainer_sheet, self.path)

        self.inductee_sheet = CharacterSheetFactory()
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=2)
        _wire_path(self.inductee_sheet, self.path)

        ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        RitualOfTheDuranceFactory()

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.inductee_sheet, self.room)
        DuranceTrainingSiteFactory(
            room_profile=get_room_profile(self.room),
            officiant=self.trainer_sheet,
            is_active=True,
        )

    def test_unmet_requirements_raise_advancement_requirements_not_met(self) -> None:
        with mock.patch(_CHECK_PATH, return_value=(False, ["Requires 50 Legend"])):
            with self.assertRaises(AdvancementRequirementsNotMet) as ctx:
                convene_durance_at_site(
                    inductee_sheet=self.inductee_sheet,
                    room=self.room,
                )

        self.assertIn("Requires 50 Legend", ctx.exception.failed)


class ConveneDuranceSiteTierBoundaryTests(TestCase):
    """Tier-boundary level → TierBoundaryRequiresCrossing (checked before site lookup)."""

    def setUp(self) -> None:
        from world.conditions.factories import ConditionStageFactory
        from world.magic.audere_majora import AudereMajoraThreshold
        from world.magic.factories import IntensityTierFactory

        self.path = PathFactory(stage=PathStage.PROSPECT)

        self.trainer_sheet = CharacterSheetFactory()
        trainer_class = CharacterClassFactory()
        _set_primary_level(self.trainer_sheet, character_class=trainer_class, level=10)
        _wire_path(self.trainer_sheet, self.path)

        # Inductee at level 5 → boundary_level=5 triggers TierBoundaryRequiresCrossing.
        self.inductee_sheet = CharacterSheetFactory()
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=5)
        _wire_path(self.inductee_sheet, self.path)

        ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=6,
        )
        RitualOfTheDuranceFactory()

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.inductee_sheet, self.room)
        DuranceTrainingSiteFactory(
            room_profile=get_room_profile(self.room),
            officiant=self.trainer_sheet,
            is_active=True,
        )

        # Seed the threshold row at boundary_level=5 so the check fires.
        self.threshold = AudereMajoraThreshold.objects.create(
            boundary_level=5,
            target_stage=PathStage.POTENTIAL,
            minimum_intensity_tier=IntensityTierFactory(),
            minimum_warp_stage=ConditionStageFactory(),
            vision_text="placeholder",
            manifestation_text="placeholder",
        )

    def tearDown(self) -> None:
        self.threshold.delete()

    def test_tier_boundary_raises_tier_boundary_requires_crossing(self) -> None:
        with self.assertRaises(TierBoundaryRequiresCrossing):
            convene_durance_at_site(
                inductee_sheet=self.inductee_sheet,
                room=self.room,
            )


class ConveneDuranceSiteUnlockNotPurchasedTests(TestCase):
    """Requirements met + a real site present, but the XP unlock is unpurchased (#2116).

    convene_durance_at_site pre-checks the purchase gate up front — a doomed session
    (one that would fail the same gate at fire time) is never drafted.
    """

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)

        self.trainer_sheet = CharacterSheetFactory()
        trainer_class = CharacterClassFactory()
        _set_primary_level(self.trainer_sheet, character_class=trainer_class, level=10)
        _wire_path(self.trainer_sheet, self.path)

        self.inductee_sheet = CharacterSheetFactory()
        self.inductee_class = CharacterClassFactory()
        _set_primary_level(self.inductee_sheet, character_class=self.inductee_class, level=2)
        _wire_path(self.inductee_sheet, self.path)

        self.unlock = ClassLevelUnlock.objects.create(
            character_class=self.inductee_class,
            target_level=3,
        )
        # Deliberately NOT purchased.
        RitualOfTheDuranceFactory()

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        _place_in_room(self.inductee_sheet, self.room)
        DuranceTrainingSiteFactory(
            room_profile=get_room_profile(self.room),
            officiant=self.trainer_sheet,
            is_active=True,
        )

    def test_unpurchased_unlock_raises_before_drafting_a_session(self) -> None:
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            with self.assertRaises(AdvancementUnlockNotPurchasedError) as ctx:
                convene_durance_at_site(
                    inductee_sheet=self.inductee_sheet,
                    room=self.room,
                )
        self.assertIn(self.inductee_class.name, ctx.exception.user_message)

    def test_purchase_then_convene_succeeds(self) -> None:
        CharacterUnlock.objects.create(
            character=self.inductee_sheet,
            character_class=self.inductee_class,
            target_level=3,
        )
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            session = convene_durance_at_site(
                inductee_sheet=self.inductee_sheet,
                room=self.room,
            )
        self.assertIsInstance(session, RitualSession)
