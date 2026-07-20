"""Clue model invariants (#1144) — a clue always points at exactly one target."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.natural_keys import NaturalKeyMixin
from evennia_extensions.factories import RoomProfileFactory
from world.clues.constants import ClueTargetKind
from world.clues.factories import ClueFactory, ClueTriggerFactory, RoomClueFactory
from world.clues.models import Clue
from world.missions.factories import MissionTemplateFactory


class ClueInvariantTests(TestCase):
    def test_codex_clue_is_valid_and_points_at_its_entry(self) -> None:
        clue = ClueFactory()  # codex-targeted by default
        clue.full_clean()  # does not raise
        assert clue.get_active_target() == clue.target_codex_entry

    def test_mission_clue_points_at_its_mission(self) -> None:
        template = MissionTemplateFactory()
        clue = ClueFactory(
            target_kind=ClueTargetKind.MISSION,
            target_codex_entry=None,
            target_mission=template,
        )
        clue.full_clean()
        assert clue.get_active_target() == template

    def test_clue_cannot_exist_without_a_target(self) -> None:
        # No red herrings, no empty clues: kind set, but no matching target FK.
        clue = Clue(target_kind=ClueTargetKind.CODEX, name="Empty", description="x")
        with self.assertRaises(ValidationError):
            clue.full_clean()

    def test_target_kind_must_match_the_set_fk(self) -> None:
        # kind=CODEX but only the mission FK is populated — rejected.
        clue = Clue(
            target_kind=ClueTargetKind.CODEX,
            target_mission=MissionTemplateFactory(),
            name="Mismatch",
            description="x",
        )
        with self.assertRaises(ValidationError):
            clue.full_clean()

    def test_persona_link_clue_is_valid_with_both_fks(self) -> None:
        # PERSONA_LINK is a documented multi-discriminator exception (#2120) — it
        # needs BOTH target_persona and target_persona_linked set together.
        from world.scenes.factories import PersonaFactory

        mask = PersonaFactory(is_fake_name=True)
        real = PersonaFactory()
        clue = Clue(
            target_kind=ClueTargetKind.PERSONA_LINK,
            target_persona=mask,
            target_persona_linked=real,
            name="A signet ring",
            description="x",
        )
        clue.full_clean()  # does not raise
        assert clue.get_active_target() == mask

    def test_persona_link_clue_requires_both_fks(self) -> None:
        from world.scenes.factories import PersonaFactory

        # Only target_persona set — target_persona_linked missing.
        clue = Clue(
            target_kind=ClueTargetKind.PERSONA_LINK,
            target_persona=PersonaFactory(is_fake_name=True),
            name="A signet ring",
            description="x",
        )
        with self.assertRaises(ValidationError) as ctx:
            clue.full_clean()
        assert "target_persona_linked" in ctx.exception.message_dict

    def test_persona_link_linked_fk_must_be_null_for_other_kinds(self) -> None:
        from world.scenes.factories import PersonaFactory

        clue = Clue(
            target_kind=ClueTargetKind.CODEX,
            target_codex_entry=None,
            target_persona_linked=PersonaFactory(),
            name="Mismatch",
            description="x",
        )
        with self.assertRaises(ValidationError):
            clue.full_clean()


class RoomClueFixtureKeyTests(TestCase):
    def test_fixture_key_defaults_to_none(self) -> None:
        room_clue = RoomClueFactory()
        self.assertIsNone(room_clue.fixture_key)

    def test_fixture_key_is_settable_and_unique(self) -> None:
        RoomClueFactory(fixture_key="arx-city/golden-hart-taproom/torn-letter")
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoomClueFactory(fixture_key="arx-city/golden-hart-taproom/torn-letter")


class ClueTriggerFixtureKeyTests(TestCase):
    def test_fixture_key_defaults_to_none(self) -> None:
        trigger = ClueTriggerFactory()
        self.assertIsNone(trigger.fixture_key)

    def test_fixture_key_is_settable_and_unique(self) -> None:
        ClueTriggerFactory(fixture_key="arx-city/golden-hart-taproom/whisper")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClueTriggerFactory(fixture_key="arx-city/golden-hart-taproom/whisper")


class RoomClueUniqueRoomClueConstraintTests(TestCase):
    """DB-level backing for the `update_or_create(room_profile=..., clue=...)`
    idempotency `StaffPlaceClueAction` relies on (#2451 whole-branch review)."""

    def test_room_profile_clue_pair_is_unique(self) -> None:
        room_profile = RoomProfileFactory()
        clue = ClueFactory()
        RoomClueFactory(room_profile=room_profile, clue=clue)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoomClueFactory(room_profile=room_profile, clue=clue)


class ClueTriggerUniqueRoomClueConstraintTests(TestCase):
    """DB-level backing for `StaffPlaceClueTriggerAction`'s `update_or_create`
    idempotency (#2451 whole-branch review)."""

    def test_room_profile_clue_pair_is_unique(self) -> None:
        room_profile = RoomProfileFactory()
        clue = ClueFactory()
        ClueTriggerFactory(room_profile=room_profile, clue=clue)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClueTriggerFactory(room_profile=room_profile, clue=clue)


class ClueNaturalKeyTests(TestCase):
    def test_clue_is_a_natural_key_mixin(self) -> None:
        self.assertTrue(issubclass(Clue, NaturalKeyMixin))

    def test_slug_defaults_to_none_and_is_unique(self) -> None:
        clue = ClueFactory(slug=None)
        self.assertIsNone(clue.slug)
        ClueFactory(slug="torn-letter")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClueFactory(slug="torn-letter")

    def test_natural_key_round_trip(self) -> None:
        clue = ClueFactory(slug="torn-letter")
        self.assertEqual(clue.natural_key(), ("torn-letter",))
        self.assertEqual(Clue.objects.get_by_natural_key("torn-letter"), clue)
