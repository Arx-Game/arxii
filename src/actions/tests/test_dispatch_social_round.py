"""Tests that a turn-costing declaration auto-resolves a social scene round.

Task 5 of #1052 (social deferred-declaration turn-taking): after a CHALLENGE
declaration is recorded into a DECLARING social (OPT_IN/GM) round,
``dispatch_player_action`` attempts presence-gated resolution. The round only
resolves once every ACTIVE participant present in the room has declared.

Coverage:
- First present participant's CHALLENGE dispatch defers WITHOUT resolving the
  round (still DECLARING, same round_number, a SceneActionDeclaration row exists).
- Second (and last) present participant's CHALLENGE dispatch resolves the round:
  the round's declaration bridge rows are gone and round_number advanced.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance
from world.scenes.constants import (
    RoundStatus,
    SceneRoundMode,
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
)
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory

# Patch away difficulty computation so test characters (no traits) still get actions.
_MODERATE_DIFFICULTY_PATCH = patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)

# Patch resolve_challenge to avoid needing a full ResultChart setup. We are only
# asserting the round lifecycle (defer vs resolve), not challenge outcomes.
_RESOLVE_CHALLENGE_PATCH = patch(
    "world.mechanics.challenge_resolution.resolve_challenge",
    return_value=None,
)


def _set_character_location(character: ObjectDB, room: ObjectDB) -> ObjectDB:
    """Place *character* in *room* so it appears in ``room.contents`` (presence gate)."""
    character.db_location = room
    character.save(update_fields=["db_location"])
    return character


def _make_challenge(room: ObjectDB):
    """Create an active, revealed challenge instance in *room* targeting the room.

    Returns (challenge_instance, approach, property, capability). The capability is
    returned so each character can be granted its own technique against it.
    """
    from world.checks.factories import CheckTypeFactory
    from world.conditions.factories import CapabilityTypeFactory

    check_type = CheckTypeFactory()
    capability = CapabilityTypeFactory()
    prop = PropertyFactory()
    app = ApplicationFactory(capability=capability, target_property=prop)
    template = ChallengeTemplateFactory()
    template.properties.add(prop)
    approach = ChallengeApproachFactory(
        challenge_template=template,
        application=app,
        check_type=check_type,
        action_template=None,
    )
    challenge_instance = ChallengeInstance.objects.create(
        template=template,
        location=room,
        target_object=room,
        is_active=True,
        is_revealed=True,
    )
    return challenge_instance, approach, capability


def _grant_capability(sheet, capability) -> None:
    """Give *sheet*'s character a technique that grants *capability* (so the challenge
    is declarable for that character)."""
    from world.magic.factories import (
        CharacterTechniqueFactory,
        TechniqueCapabilityGrantFactory,
        TechniqueFactory,
    )

    technique = TechniqueFactory(damage_profile=False)
    TechniqueCapabilityGrantFactory(technique=technique, capability=capability, base_value=5)
    CharacterTechniqueFactory(character=sheet, technique=technique)


class TestSocialRoundAutoResolvesOnLastDeclaration(TestCase):
    """A social round resolves only once every present ACTIVE participant has declared."""

    def setUp(self) -> None:
        # Build Evennia objects per-test in setUp (NOT setUpTestData): class-level Evennia
        # objects carry a DbHolder that Django's setUpTestData deep-copy cannot handle,
        # which surfaces only under CI's larger shard runs (idmapper contamination).
        from evennia_extensions.factories import ObjectDBFactory

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")

        self.sheet_a = CharacterSheetFactory()
        self.sheet_b = CharacterSheetFactory()
        self.char_a = _set_character_location(self.sheet_a.character, self.room)
        self.char_b = _set_character_location(self.sheet_b.character, self.room)

        self.challenge_instance, self.approach, capability = _make_challenge(self.room)
        _grant_capability(self.sheet_a, capability)
        _grant_capability(self.sheet_b, capability)

        # STRICT (social) round in DECLARING; both participants ACTIVE and present.
        self.scene_round = SceneRoundFactory(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
            mode=SceneRoundMode.STRICT,
        )
        self.participant_a = SceneRoundParticipantFactory(
            scene_round=self.scene_round,
            character_sheet=self.sheet_a,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        self.participant_b = SceneRoundParticipantFactory(
            scene_round=self.scene_round,
            character_sheet=self.sheet_b,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()
        self.addCleanup(self._difficulty_patch.stop)

    def _ref(self):
        from actions.types import ActionRef

        return ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=self.challenge_instance.pk,
            approach_id=self.approach.pk,
        )

    def test_round_resolves_only_after_all_present_participants_declare(self) -> None:
        from actions.player_interface import dispatch_player_action

        # Participant A declares: deferred, round NOT yet resolved.
        with _RESOLVE_CHALLENGE_PATCH:
            result_a = dispatch_player_action(self.char_a, self._ref(), {})

        self.assertTrue(result_a.deferred, "A's CHALLENGE in a DECLARING round should defer")

        self.scene_round.refresh_from_db()
        self.assertEqual(
            self.scene_round.status,
            RoundStatus.DECLARING,
            "round must remain DECLARING until every present participant has declared",
        )
        self.assertEqual(
            self.scene_round.round_number,
            1,
            "round_number must not advance after only one of two declarations",
        )
        self.assertEqual(
            self.scene_round.action_declarations.filter(round_number=1).count(),
            1,
            "A's declaration row should exist for round 1",
        )

        # Participant B declares: completion rule now met -> round resolves and advances.
        with _RESOLVE_CHALLENGE_PATCH:
            result_b = dispatch_player_action(self.char_b, self._ref(), {})

        self.assertTrue(result_b.deferred, "B's CHALLENGE declaration is also deferred")

        self.scene_round.refresh_from_db()
        self.assertEqual(
            self.scene_round.action_declarations.filter(round_number=1).count(),
            0,
            "round-1 declaration bridge rows should be deleted on resolution",
        )
        self.assertEqual(
            self.scene_round.round_number,
            2,
            "round should advance to the next round after resolving",
        )
        self.assertEqual(
            self.scene_round.status,
            RoundStatus.DECLARING,
            "resolve_scene_round advances into the next DECLARING round",
        )
