"""Tests for the combat-agnostic RoundContext seam.

Covers:
- get_active_round_context returns None for a character with no active combat participation.
- Returns a RoundContext with is_declaration_open=True when character is ACTIVE in a
  DECLARING encounter.
- is_declaration_open is False when encounter status is not DECLARING (e.g. RESOLVING).
- round_id returns the expected (encounter_id, round_number) tuple.
- record_declaration mutual exclusion: COMBAT clears challenge rows, CHALLENGE clears round
  action rows, and both directions work.
- record_declaration raises ActionDispatchError when the encounter is not DECLARING.
"""

import django.test

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.factories import ActionTemplateFactory
from actions.types import ActionRef, PlayerAction
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import EncounterStatus, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import TechniqueFactory
from world.mechanics.factories import ChallengeApproachFactory, ChallengeInstanceFactory
from world.vitals.constants import CharacterStatus
from world.vitals.models import CharacterVitals


class TestGetActiveRoundContextNoParticipation(django.test.TestCase):
    """Character with no combat participation → returns None."""

    def test_no_participation_returns_none(self) -> None:
        sheet = CharacterSheetFactory()
        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNone(result)


class TestGetActiveRoundContextDeclaring(django.test.TestCase):
    """Character ACTIVE in a DECLARING encounter → is_declaration_open=True."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        self.sheet = self.participant.character_sheet

    def test_returns_round_context_instance(self) -> None:
        from actions.round_context import RoundContext, get_active_round_context

        result = get_active_round_context(self.sheet)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, RoundContext)

    def test_is_declaration_open_true_when_declaring(self) -> None:
        from actions.round_context import get_active_round_context

        result = get_active_round_context(self.sheet)
        assert result is not None
        self.assertTrue(result.is_declaration_open)

    def test_round_id_matches_encounter(self) -> None:
        from actions.round_context import get_active_round_context

        result = get_active_round_context(self.sheet)
        assert result is not None
        self.assertEqual(result.round_id, (self.encounter.pk, self.encounter.round_number))


class TestGetActiveRoundContextNotDeclaring(django.test.TestCase):
    """Character ACTIVE in a non-DECLARING encounter → is_declaration_open=False."""

    def test_is_declaration_open_false_when_resolving(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.RESOLVING,
            round_number=2,
        )
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.is_declaration_open)

    def test_is_declaration_open_false_when_between_rounds(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.BETWEEN_ROUNDS,
            round_number=3,
        )
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.is_declaration_open)


class TestGetActiveRoundContextCompletedEncounter(django.test.TestCase):
    """Character in a COMPLETED encounter → returns None (encounter is over)."""

    def test_completed_encounter_returns_none(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.COMPLETED)
        CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        sheet = (
            encounter.participants.filter(status=ParticipantStatus.ACTIVE).first().character_sheet
        )

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNone(result)


class TestGetActiveRoundContextInactiveParticipant(django.test.TestCase):
    """Character with FLED/REMOVED participant status → returns None."""

    def test_fled_participant_returns_none(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING)
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.FLED,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNone(result)

    def test_removed_participant_returns_none(self) -> None:
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING)
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.REMOVED,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context

        result = get_active_round_context(sheet)
        self.assertIsNone(result)


class TestRoundContextRecordDeclarationStub(django.test.TestCase):
    """record_declaration no longer raises NotImplementedError (P2T8 implemented)."""

    def test_record_declaration_raises_not_implemented(self) -> None:
        """Kept as a placeholder; the stub test is superseded by P2T8 tests below."""


def _make_declaring_encounter_with_vitals() -> tuple:
    """Create a DECLARING encounter, ACTIVE participant, and ALIVE CharacterVitals."""
    encounter = CombatEncounterFactory(
        status=EncounterStatus.DECLARING,
        round_number=1,
    )
    participant = CombatParticipantFactory(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    )
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet,
        health=100,
        max_health=100,
        status=CharacterStatus.ALIVE,
    )
    return encounter, participant


def _make_combat_player_action(technique: object) -> PlayerAction:
    """Build a COMBAT PlayerAction whose ref.technique_id points at technique."""
    check_type = CheckTypeFactory()
    action_template = ActionTemplateFactory(check_type=check_type)
    ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=technique.pk)  # type: ignore[attr-defined]
    return PlayerAction(
        backend=ActionBackend.COMBAT,
        action_template=action_template,
        display_name="Test Combat Action",
        ref=ref,
    )


def _make_challenge_player_action(
    challenge_instance: object, challenge_approach: object
) -> PlayerAction:
    """Build a CHALLENGE PlayerAction whose ref points at challenge_instance + approach."""
    check_type = CheckTypeFactory()
    action_template = ActionTemplateFactory(check_type=check_type)
    ref = ActionRef(
        backend=ActionBackend.CHALLENGE,
        challenge_instance_id=challenge_instance.pk,  # type: ignore[attr-defined]
        approach_id=challenge_approach.pk,  # type: ignore[attr-defined]
    )
    return PlayerAction(
        backend=ActionBackend.CHALLENGE,
        action_template=action_template,
        display_name="Test Challenge Action",
        ref=ref,
    )


class TestRecordDeclarationCombatFirst(django.test.TestCase):
    """COMBAT declaration clears any prior challenge declaration."""

    def setUp(self) -> None:
        from actions.round_context import get_active_round_context

        self.encounter, self.participant = _make_declaring_encounter_with_vitals()
        self.sheet = self.participant.character_sheet
        ctx = get_active_round_context(self.sheet)
        assert ctx is not None
        self.ctx = ctx

        # A technique with no damage profile (no base_power) and no condition rows
        # so declare_action does not require a focused_opponent_target.
        self.technique = TechniqueFactory(damage_profile=False)
        # Ensure the technique has no base_power to avoid the "damage requires target" check.
        from world.magic.factories import EffectTypeFactory

        no_power_effect_type = EffectTypeFactory(base_power=None)
        self.technique.effect_type = no_power_effect_type
        self.technique.save()

        self.challenge_instance = ChallengeInstanceFactory()
        self.challenge_approach = ChallengeApproachFactory()

    def test_combat_declaration_creates_round_action_no_challenge_row(self) -> None:
        """COMBAT record_declaration creates CombatRoundAction, no RoundChallengeDeclaration."""
        from world.combat.models import CombatRoundAction, RoundChallengeDeclaration

        player_action = _make_combat_player_action(self.technique)
        self.ctx.record_declaration(
            self.sheet,
            player_action,
            {"effort_level": EffortLevel.MEDIUM},
        )

        self.assertTrue(
            CombatRoundAction.objects.filter(
                participant=self.participant,
                round_number=self.encounter.round_number,
            ).exists(),
            "CombatRoundAction should exist after COMBAT declaration",
        )
        self.assertFalse(
            RoundChallengeDeclaration.objects.filter(
                encounter=self.encounter,
                round_number=self.encounter.round_number,
                participant=self.participant,
            ).exists(),
            "RoundChallengeDeclaration should NOT exist after COMBAT declaration",
        )

    def test_challenge_after_combat_clears_round_action(self) -> None:
        """After COMBAT, a CHALLENGE declaration removes CombatRoundAction, creates bridge row."""
        from world.combat.models import CombatRoundAction, RoundChallengeDeclaration

        # First: combat
        combat_action = _make_combat_player_action(self.technique)
        self.ctx.record_declaration(
            self.sheet,
            combat_action,
            {"effort_level": EffortLevel.MEDIUM},
        )
        self.assertTrue(CombatRoundAction.objects.filter(participant=self.participant).exists())

        # Then: challenge (same encounter, same round)
        challenge_action = _make_challenge_player_action(
            self.challenge_instance, self.challenge_approach
        )
        self.ctx.record_declaration(self.sheet, challenge_action, {})

        # CombatRoundAction must be gone
        self.assertFalse(
            CombatRoundAction.objects.filter(
                participant=self.participant,
                round_number=self.encounter.round_number,
            ).exists(),
            "CombatRoundAction should be deleted after CHALLENGE declaration",
        )
        # Exactly one RoundChallengeDeclaration
        declarations = RoundChallengeDeclaration.objects.filter(
            encounter=self.encounter,
            round_number=self.encounter.round_number,
            participant=self.participant,
        )
        self.assertEqual(declarations.count(), 1)
        decl = declarations.first()
        assert decl is not None
        self.assertEqual(decl.challenge_instance_id, self.challenge_instance.pk)
        self.assertEqual(decl.challenge_approach_id, self.challenge_approach.pk)


class TestRecordDeclarationChallengeFirst(django.test.TestCase):
    """CHALLENGE declaration clears any prior CombatRoundAction."""

    def setUp(self) -> None:
        from actions.round_context import get_active_round_context

        self.encounter, self.participant = _make_declaring_encounter_with_vitals()
        self.sheet = self.participant.character_sheet
        ctx = get_active_round_context(self.sheet)
        assert ctx is not None
        self.ctx = ctx

        from world.magic.factories import EffectTypeFactory

        no_power_effect_type = EffectTypeFactory(base_power=None)
        self.technique = TechniqueFactory(damage_profile=False)
        self.technique.effect_type = no_power_effect_type
        self.technique.save()

        self.challenge_instance = ChallengeInstanceFactory()
        self.challenge_approach = ChallengeApproachFactory()

    def test_challenge_first_creates_bridge_row(self) -> None:
        """CHALLENGE record_declaration creates bridge row, no CombatRoundAction."""
        from world.combat.models import CombatRoundAction, RoundChallengeDeclaration

        challenge_action = _make_challenge_player_action(
            self.challenge_instance, self.challenge_approach
        )
        self.ctx.record_declaration(self.sheet, challenge_action, {})

        self.assertFalse(
            CombatRoundAction.objects.filter(
                participant=self.participant,
                round_number=self.encounter.round_number,
            ).exists(),
            "CombatRoundAction should NOT exist after CHALLENGE declaration",
        )
        self.assertTrue(
            RoundChallengeDeclaration.objects.filter(
                encounter=self.encounter,
                round_number=self.encounter.round_number,
                participant=self.participant,
            ).exists(),
            "RoundChallengeDeclaration should exist after CHALLENGE declaration",
        )

    def test_combat_after_challenge_clears_bridge_row(self) -> None:
        """After CHALLENGE, a COMBAT declaration removes bridge row, creates CombatRoundAction."""
        from world.combat.models import CombatRoundAction, RoundChallengeDeclaration

        # First: challenge
        challenge_action = _make_challenge_player_action(
            self.challenge_instance, self.challenge_approach
        )
        self.ctx.record_declaration(self.sheet, challenge_action, {})
        self.assertTrue(
            RoundChallengeDeclaration.objects.filter(participant=self.participant).exists()
        )

        # Then: combat
        combat_action = _make_combat_player_action(self.technique)
        self.ctx.record_declaration(
            self.sheet,
            combat_action,
            {"effort_level": EffortLevel.MEDIUM},
        )

        # Bridge row must be gone
        self.assertFalse(
            RoundChallengeDeclaration.objects.filter(
                encounter=self.encounter,
                round_number=self.encounter.round_number,
                participant=self.participant,
            ).exists(),
            "RoundChallengeDeclaration should be deleted after COMBAT declaration",
        )
        # CombatRoundAction must exist
        self.assertTrue(
            CombatRoundAction.objects.filter(
                participant=self.participant,
                round_number=self.encounter.round_number,
            ).exists(),
            "CombatRoundAction should exist after COMBAT declaration",
        )


class TestRecordDeclarationClosedWindow(django.test.TestCase):
    """record_declaration raises ActionDispatchError when encounter is RESOLVING."""

    def test_resolving_encounter_raises_dispatch_error(self) -> None:
        """RESOLVING encounter → ROUND_DECLARATION_CLOSED."""
        encounter = CombatEncounterFactory(
            status=EncounterStatus.RESOLVING,
            round_number=2,
        )
        participant = CombatParticipantFactory(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        )
        sheet = participant.character_sheet

        from actions.round_context import get_active_round_context
        from world.magic.factories import EffectTypeFactory

        ctx = get_active_round_context(sheet)
        assert ctx is not None

        no_power_effect_type = EffectTypeFactory(base_power=None)
        technique = TechniqueFactory(damage_profile=False)
        technique.effect_type = no_power_effect_type
        technique.save()

        player_action = _make_combat_player_action(technique)
        with self.assertRaises(ActionDispatchError) as cm:
            ctx.record_declaration(sheet, player_action, {"effort_level": EffortLevel.MEDIUM})

        self.assertEqual(cm.exception.code, ActionDispatchError.ROUND_DECLARATION_CLOSED)
