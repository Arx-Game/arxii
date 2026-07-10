"""Clue model invariants (#1144) — a clue always points at exactly one target."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.clues.constants import ClueTargetKind
from world.clues.factories import ClueFactory
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
