"""Telnet-driven CHALLENGE dispatch E2E (#1336): DispatchCommand → resolve_challenge.

Proves the full chain:
  _ChallengeProbeCommand.func()
    → dispatch_player_action(CHALLENGE ref)
    → resolve_challenge(character, challenge_instance, approach, capability_source)

resolve_challenge is patched to write a CharacterChallengeRecord as its side
effect, so the assertion is a DB row query rather than a mock-call check.
This approach mirrors TestDispatchPlayerActionChallengeImmediate in
actions/tests/test_player_interface.py — which tests the same seam directly
without going through a command.

SQLite tier: passes cleanly.  The CHALLENGE hot path does not call
apply_condition (no DISTINCT ON) and does not touch the AreaClosure
materialized view in a non-combat context, so no @tag("postgres") is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from actions.constants import ActionBackend
from actions.types import ActionRef
from commands.command import DispatchCommand
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import CapabilityTypeFactory
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance, CharacterChallengeRecord


def _set_character_location(character: ObjectDB, room: ObjectDB) -> ObjectDB:
    """Place *character* in *room* without triggering Evennia's postsave hook.

    Uses a raw queryset update + in-memory patch on the SharedMemoryModel
    instance.  Mirrors the helper in actions/tests/test_player_interface.py.
    """
    ObjectDB.objects.filter(pk=character.pk).update(db_location=room)
    character.db_location = room
    return character


_MODERATE_DIFFICULTY_PATCH = patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)


class _ChallengeProbeCommand(DispatchCommand):
    """Minimal DispatchCommand that dispatches the CHALLENGE ref set at construction."""

    key = "probe_challenge"

    def __init__(self, ref: ActionRef) -> None:
        super().__init__()
        self._ref = ref

    def resolve_action_ref(self) -> ActionRef:
        return self._ref

    def resolve_action_args(self):
        return {}


def _make_cmd(ref: ActionRef, caller: ObjectDB) -> _ChallengeProbeCommand:
    cmd = _ChallengeProbeCommand(ref)
    cmd.caller = caller
    cmd.args = ""
    cmd.raw_string = "probe_challenge"
    cmd.cmdname = cmd.key
    return cmd


class ChallengeTelnetDispatchE2ETests(TestCase):
    """DispatchCommand.func() with a CHALLENGE ref reaches resolve_challenge.

    Uses setUp (not setUpTestData) for ObjectDB objects — Django's setUpTestData
    deepcopy machinery cannot copy DbHolder / SharedMemoryModel instances (raises
    copy.Error in CI shard runs).
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()

        self.room = ObjectDBFactory(db_key="ChallengeTelnetTestRoom")
        self.sheet = CharacterSheetFactory()
        self.character = _set_character_location(self.sheet.character, self.room)

        check_type = CheckTypeFactory()
        capability = CapabilityTypeFactory()
        prop = PropertyFactory()
        app = ApplicationFactory(capability=capability, target_property=prop)
        template = ChallengeTemplateFactory()
        template.properties.add(prop)
        self.approach = ChallengeApproachFactory(
            challenge_template=template,
            application=app,
            check_type=check_type,
            action_template=None,
        )
        self.challenge_instance = ChallengeInstance.objects.create(
            template=template,
            location=self.room,
            target_object=self.room,
            is_active=True,
            is_revealed=True,
        )

        # Give the character a technique that grants the capability so that
        # dispatch_player_action can validate the ref against current availability.
        from world.magic.factories import (
            CharacterTechniqueFactory,
            TechniqueCapabilityGrantFactory,
            TechniqueFactory,
        )

        technique = TechniqueFactory(damage_profile=False)
        TechniqueCapabilityGrantFactory(technique=technique, capability=capability, base_value=5)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def _resolve_challenge_patch(self) -> object:
        """Patch resolve_challenge; side-effect writes a CharacterChallengeRecord."""

        def _fake_resolve(character, challenge_instance, approach, capability_source):  # type: ignore[no-untyped-def]
            CharacterChallengeRecord.objects.create(
                character=character,
                challenge_instance=challenge_instance,
                approach=approach,
            )
            return MagicMock()

        return patch(
            "world.mechanics.challenge_resolution.resolve_challenge",
            side_effect=_fake_resolve,
        )

    def test_challenge_dispatch_via_telnet_command_reaches_resolve_challenge(
        self,
    ) -> None:
        """DispatchCommand.func() with CHALLENGE ref routes to resolve_challenge."""
        ref = ActionRef(
            backend=ActionBackend.CHALLENGE,
            challenge_instance_id=self.challenge_instance.pk,
            approach_id=self.approach.pk,
        )
        cmd = _make_cmd(ref, self.character)

        with self._resolve_challenge_patch():
            cmd.func()

        self.assertTrue(
            CharacterChallengeRecord.objects.filter(
                character=self.character,
                challenge_instance=self.challenge_instance,
            ).exists(),
            "CharacterChallengeRecord must exist — proves resolve_challenge was reached "
            "via DispatchCommand.func() → dispatch_player_action(CHALLENGE)",
        )
