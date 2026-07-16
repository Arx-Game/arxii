"""Tests that dispatching a CHALLENGE action in a scene round ticks the round.

Task 5 of the #520 acute tier: post-dispatch tick hook.

Coverage:
- CHALLENGE dispatch inside a scene round triggers advance_scene_round_for_action
  and the DoT rounds_remaining decrements.
- REGISTRY dispatch ("look") does NOT tick — rounds_remaining unchanged.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance
from world.scenes.constants import RoundStatus, SceneRoundParticipantStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory

# Patch away difficulty computation so test characters (no traits) still get actions.
_MODERATE_DIFFICULTY_PATCH = patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)

# Patch resolve_challenge to avoid needing a full ResultChart setup.
# We just need to confirm that the tick fired.
_RESOLVE_CHALLENGE_PATCH = patch(
    "world.mechanics.challenge_resolution.resolve_challenge",
    return_value=None,
)


def _set_character_location(character: ObjectDB, room: ObjectDB) -> ObjectDB:
    """Bypass Evennia's at_db_location_postsave hook."""
    ObjectDB.objects.filter(pk=character.pk).update(db_location=room)
    character.db_location = room
    return character


def _make_challenge_setup(sheet, room: ObjectDB) -> tuple:
    """Wire capability + challenge + approach so the character can act in *room*.

    Returns (challenge_instance, approach).
    """
    from world.checks.factories import CheckTypeFactory
    from world.conditions.factories import CapabilityTypeFactory
    from world.magic.factories import (
        CharacterTechniqueFactory,
        TechniqueCapabilityGrantFactory,
        TechniqueFactory,
    )

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
    technique = TechniqueFactory(damage_profile=False)
    TechniqueCapabilityGrantFactory(technique=technique, capability=capability, base_value=5)
    CharacterTechniqueFactory(character=sheet, technique=technique)

    return challenge_instance, approach


class TestChallengeDispatchTicksSceneRound(TestCase):
    """CHALLENGE dispatch inside a scene round ticks the round (DoT decrements)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(db_key="SceneTickRoom")
        cls.sheet = CharacterSheetFactory()
        cls.character = _set_character_location(cls.sheet.character, cls.room)

        # Wire challenge availability.
        cls.challenge_instance, cls.approach = _make_challenge_setup(cls.sheet, cls.room)

        # Create an ACTIVE scene round the character participates in.
        # Factory creates BETWEEN_ROUNDS; advance_scene_round_for_action expects that.
        cls.scene_round = SceneRoundFactory(
            room=cls.room,
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
        )
        SceneRoundParticipantFactory(
            scene_round=cls.scene_round,
            character_sheet=cls.sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

    def setUp(self) -> None:
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def test_challenge_dispatch_ticks_dot_condition(self) -> None:
        """DoT rounds_remaining decrements after a CHALLENGE dispatch in a scene round."""
        # Create a ROUNDS-duration DoT on the character.
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(
            target=self.character, condition=template, rounds_remaining=3
        )

        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef

        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=self.challenge_instance.pk,
            approach_id=self.approach.pk,
        )
        with _RESOLVE_CHALLENGE_PATCH:
            dispatch_player_action(self.character, ref, {})

        inst.refresh_from_db()
        self.assertEqual(
            inst.rounds_remaining,
            2,
            "rounds_remaining should have decremented from 3 to 2 after the scene round ticked",
        )


class TestRegistryDispatchDoesNotTickSceneRound(TestCase):
    """REGISTRY dispatch (look) must NOT tick the scene round."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(db_key="RegistryTickRoom")
        cls.sheet = CharacterSheetFactory()
        cls.character = _set_character_location(cls.sheet.character, cls.room)

        cls.scene_round = SceneRoundFactory(
            room=cls.room,
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
        )
        SceneRoundParticipantFactory(
            scene_round=cls.scene_round,
            character_sheet=cls.sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

    def test_registry_dispatch_does_not_tick(self) -> None:
        """rounds_remaining is unchanged after a REGISTRY ('look') dispatch."""
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(
            target=self.character, condition=template, rounds_remaining=3
        )

        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef

        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="look")
        dispatch_player_action(self.character, ref, {})

        inst.refresh_from_db()
        self.assertEqual(
            inst.rounds_remaining,
            3,
            "rounds_remaining must NOT change after a REGISTRY dispatch",
        )
