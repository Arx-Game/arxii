"""Tests for strain on ordinary combat-round casts (#3446).

``CombatRoundAction`` has always inherited ``strain_commitment`` from
``CommittingDeclaration``, but nothing wrote or read it on the round path:
``declare_action`` never accepted it and ``resolve_combat_technique`` never
forwarded it into ``use_technique``. These tests pin the new wiring.
"""

import contextlib
from unittest.mock import patch

from django.test import TestCase

from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.services import declare_action
from world.magic.factories import CharacterAnimaFactory
from world.scenes.constants import RoundStatus


class StrainDeclarationTests(TestCase):
    """declare_action accepts, caps, and persists strain_commitment."""

    def setUp(self) -> None:
        self.enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        self.participant = CombatParticipantFactory(encounter=self.enc)
        CharacterAnimaFactory(character=self.participant.character_sheet, current=20, maximum=50)

    def test_declaration_persists_strain(self) -> None:
        action = declare_action(
            self.participant,
            effort_level="medium",
            strain_commitment=5,
        )
        self.assertEqual(action.strain_commitment, 5)

    def test_strain_beyond_available_anima_is_rejected(self) -> None:
        with self.assertRaisesMessage(ValueError, "exceeds available"):
            declare_action(
                self.participant,
                effort_level="medium",
                strain_commitment=21,
            )

    def test_negative_strain_is_rejected(self) -> None:
        with self.assertRaisesMessage(ValueError, "cannot be negative"):
            declare_action(
                self.participant,
                effort_level="medium",
                strain_commitment=-1,
            )

    def test_redeclaration_without_strain_resets_to_zero(self) -> None:
        declare_action(self.participant, effort_level="medium", strain_commitment=5)
        action = declare_action(self.participant, effort_level="medium")
        self.assertEqual(action.strain_commitment, 0)


class StrainKeywordParseTests(TestCase):
    """Telnet ``cast ... strain=<n>`` grammar (#3446), mirroring the clash keyword."""

    def test_strain_keyword_stripped_and_parsed(self) -> None:
        from commands.combat import CmdDeclareTechnique

        remainder, strain = CmdDeclareTechnique._extract_strain_keyword(
            "Fireball at Goblin strain=7 effort=high"
        )
        self.assertEqual(strain, 7)
        self.assertEqual(remainder, "Fireball at Goblin effort=high")

    def test_absent_keyword_defaults_to_zero(self) -> None:
        from commands.combat import CmdDeclareTechnique

        remainder, strain = CmdDeclareTechnique._extract_strain_keyword("Fireball at Goblin")
        self.assertEqual(strain, 0)
        self.assertEqual(remainder, "Fireball at Goblin")

    def test_non_integer_value_raises(self) -> None:
        from commands.combat import CmdDeclareTechnique
        from commands.exceptions import CommandError

        with self.assertRaises(CommandError):
            CmdDeclareTechnique._extract_strain_keyword("Fireball strain=lots")


class StrainResolutionForwardingTests(TestCase):
    """resolve_combat_technique threads the declared strain into use_technique."""

    def test_use_technique_receives_declared_strain(self) -> None:
        from world.checks.factories import CheckTypeFactory
        from world.combat.factories import CombatOpponentFactory
        from world.combat.services import resolve_combat_technique
        from world.magic.factories import TechniqueFactory

        enc = CombatEncounterFactory(status=RoundStatus.DECLARING)
        participant = CombatParticipantFactory(encounter=enc)
        CharacterAnimaFactory(character=participant.character_sheet, current=20, maximum=50)
        opponent = CombatOpponentFactory(encounter=enc)
        technique = TechniqueFactory()

        action = declare_action(
            participant,
            focused_action=technique,
            effort_level="medium",
            focused_opponent_target=opponent,
            strain_commitment=7,
        )

        # The mocked envelope returns None; downstream unpacking may fail
        # after the call we care about - the assertion below is the oracle,
        # not the full resolution.
        with (
            patch("world.magic.services.use_technique") as mocked,
            contextlib.suppress(AttributeError, TypeError),
        ):
            mocked.return_value = None
            resolve_combat_technique(
                participant=participant,
                action=action,
                fatigue_category="physical",
                offense_check_type=CheckTypeFactory(),
                offense_check_fn=None,
            )

        self.assertTrue(mocked.called)
        self.assertEqual(mocked.call_args.kwargs.get("strain_commitment"), 7)
