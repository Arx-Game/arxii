"""End-to-end integration tests for #1052 (social deferred-declaration turn-taking).

These tests exercise the full dispatch path (``dispatch_player_action``) and the
scene-round resolution services to prove the issue's "Done when" criteria:

1. Declared CHALLENGE actions resolve together in INITIATIVE order — not in the
   order participants happened to type/dispatch (the not-fastest-typist guarantee).
2. An ABSENT participant is an implicit pass: the round resolves once every
   *present* ACTIVE participant has declared, even if an enrolled-but-absent
   participant never declares.
3. A GM force-resolve advances a partially-declared round (via the dispatch
   entry point — a REGISTRY ``force_resolve_round`` ref).
4. AFK-safety: with no turn-costing action dispatched, nothing ticks — the round
   stays DECLARING at the same round_number with no declaration bridge rows. The
   only thing that ever triggers resolution is an actual turn-costing action.

Setup mirrors ``actions/tests/test_dispatch_social_round.py`` (real typeclassed
room, two CharacterSheets each granted a technique against a shared challenge,
presence via ``db_location``).
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
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
)
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory

# Patch away difficulty computation so test characters (no traits) still get actions.
_MODERATE_DIFFICULTY_PATCH = patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)


def _set_character_location(character: ObjectDB, room: ObjectDB | None) -> ObjectDB:
    """Place *character* in *room* (or remove from any room when ``None``)."""
    character.db_location = room
    character.save(update_fields=["db_location"])
    return character


def _make_challenge(room: ObjectDB):
    """Create an active, revealed challenge instance in *room* targeting the room.

    Returns (challenge_instance, approach, capability). The capability is returned
    so each character can be granted its own technique against it.
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
    """Give *sheet*'s character a technique granting *capability* (challenge declarable)."""
    from world.magic.factories import (
        CharacterTechniqueFactory,
        TechniqueCapabilityGrantFactory,
        TechniqueFactory,
    )

    technique = TechniqueFactory(damage_profile=False)
    TechniqueCapabilityGrantFactory(technique=technique, capability=capability, base_value=5)
    CharacterTechniqueFactory(character=sheet, technique=technique)


def _challenge_ref(challenge_instance, approach):
    from actions.types import ActionRef

    return ActionRef(
        backend=ActionBackend.CHALLENGE,
        challenge_instance_id=challenge_instance.pk,
        approach_id=approach.pk,
    )


class SocialRoundIntegrationBase(TestCase):
    """Shared setup: a real room, a shared challenge, two CharacterSheets granted a technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import ObjectDBFactory

        cls.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")

        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()
        cls.char_a = cls.sheet_a.character
        cls.char_b = cls.sheet_b.character

        cls.challenge_instance, cls.approach, capability = _make_challenge(cls.room)
        _grant_capability(cls.sheet_a, capability)
        _grant_capability(cls.sheet_b, capability)

    def setUp(self) -> None:
        # Both present by default; individual tests override placement as needed.
        _set_character_location(self.char_a, self.room)
        _set_character_location(self.char_b, self.room)
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()
        self.addCleanup(self._difficulty_patch.stop)

    def _ref(self):
        return _challenge_ref(self.challenge_instance, self.approach)

    def _make_round(self, **kwargs):
        """Create an OPT_IN DECLARING round with the given participants/initiative."""
        return SceneRoundFactory(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
            **kwargs,
        )

    def _add_participant(self, scene_round, sheet, *, initiative_order=0):
        return SceneRoundParticipantFactory(
            scene_round=scene_round,
            character_sheet=sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
            initiative_order=initiative_order,
        )


class TestResolvesInInitiativeOrder(SocialRoundIntegrationBase):
    """Declarations resolve in initiative order, not declaration (typing) order."""

    def test_resolution_follows_initiative_not_declaration_order(self) -> None:
        from actions.player_interface import dispatch_player_action

        scene_round = self._make_round()
        # B has the EARLIER initiative slot (0); A is later (1).
        self._add_participant(scene_round, self.sheet_b, initiative_order=0)
        self._add_participant(scene_round, self.sheet_a, initiative_order=1)

        resolved_order: list[int] = []

        def _record(character, *args, **kwargs):
            resolved_order.append(character.pk)

        # Patch resolve_challenge where _resolve_scene_declarations looks it up
        # (a local `from world.mechanics.challenge_resolution import resolve_challenge`
        # binds into that module's namespace at call time).
        with patch(
            "world.mechanics.challenge_resolution.resolve_challenge",
            side_effect=_record,
        ):
            # A declares FIRST (opposite of initiative order), then B.
            result_a = dispatch_player_action(self.char_a, self._ref(), {})
            self.assertTrue(result_a.deferred)
            result_b = dispatch_player_action(self.char_b, self._ref(), {})
            self.assertTrue(result_b.deferred)

        # The round resolved (both present participants declared).
        scene_round.refresh_from_db()
        self.assertEqual(scene_round.round_number, 2, "round should have advanced after resolving")

        # Both challenges resolved, and in INITIATIVE order (B before A), NOT
        # the declaration order (A first).
        self.assertEqual(
            resolved_order,
            [self.char_b.pk, self.char_a.pk],
            "challenges must resolve in initiative order (B then A), not declaration order",
        )


class TestAbsentParticipantImplicitPass(SocialRoundIntegrationBase):
    """An enrolled-but-absent participant never blocks resolution (implicit pass)."""

    def test_present_participant_dispatch_resolves_despite_absent_participant(self) -> None:
        from actions.player_interface import dispatch_player_action

        scene_round = self._make_round()
        self._add_participant(scene_round, self.sheet_a, initiative_order=0)
        self._add_participant(scene_round, self.sheet_b, initiative_order=1)

        # B is enrolled and ACTIVE but NOT in the room (absent → implicit pass).
        _set_character_location(self.char_b, None)

        with patch(
            "world.mechanics.challenge_resolution.resolve_challenge",
            return_value=None,
        ):
            # Only the present participant (A) declares.
            result_a = dispatch_player_action(self.char_a, self._ref(), {})
            self.assertTrue(result_a.deferred)

        # The round resolved on A's declaration alone — B's absence is an implicit pass.
        scene_round.refresh_from_db()
        self.assertEqual(
            scene_round.round_number,
            2,
            "round must resolve once every PRESENT participant declared (absent = implicit pass)",
        )
        self.assertEqual(
            scene_round.status,
            RoundStatus.DECLARING,
            "resolution advances into the next DECLARING round",
        )
        self.assertEqual(
            scene_round.action_declarations.filter(round_number=1).count(),
            0,
            "round-1 declaration bridge rows are deleted on resolution",
        )


class TestForceResolveViaDispatch(SocialRoundIntegrationBase):
    """A GM force-resolve (via dispatch) advances a partially-declared round."""

    def test_force_resolve_round_via_dispatch_advances_partial_round(self) -> None:
        from actions.player_interface import dispatch_player_action
        from actions.types import ActionRef

        scene_round = self._make_round()
        self._add_participant(scene_round, self.sheet_a, initiative_order=0)
        self._add_participant(scene_round, self.sheet_b, initiative_order=1)

        # Only A declares; B (present) has NOT declared — round is incomplete.
        with patch(
            "world.mechanics.challenge_resolution.resolve_challenge",
            return_value=None,
        ):
            result_a = dispatch_player_action(self.char_a, self._ref(), {})
            self.assertTrue(result_a.deferred)

            scene_round.refresh_from_db()
            self.assertEqual(
                scene_round.round_number,
                1,
                "round must NOT auto-resolve while a present participant is undeclared",
            )

            # GM force-resolves via the REGISTRY dispatch entry point.
            force_ref = ActionRef(
                backend=ActionBackend.REGISTRY,
                registry_key="force_resolve_round",
            )
            force_result = dispatch_player_action(self.char_a, force_ref, {})

        self.assertFalse(force_result.deferred, "force_resolve is immediate, not a declaration")
        self.assertTrue(force_result.detail.success)

        scene_round.refresh_from_db()
        self.assertEqual(scene_round.round_number, 2, "force-resolve advances the round")
        self.assertEqual(scene_round.status, RoundStatus.DECLARING)
        self.assertEqual(
            scene_round.action_declarations.filter(round_number=1).count(),
            0,
            "force-resolve deletes the round's bridge rows",
        )


class TestAfkSafetyNoActionNoResolution(SocialRoundIntegrationBase):
    """Structural AFK-safety: without a turn-costing dispatch, nothing ticks."""

    def test_round_does_not_advance_without_any_action(self) -> None:
        scene_round = self._make_round()
        self._add_participant(scene_round, self.sheet_a, initiative_order=0)
        self._add_participant(scene_round, self.sheet_b, initiative_order=1)

        # No dispatch_player_action call at all — both participants are AFK/idle.
        # Nothing should drive resolution: the round is only ever advanced by an
        # actual turn-costing action reaching dispatch_player_action.
        scene_round.refresh_from_db()
        self.assertEqual(
            scene_round.status,
            RoundStatus.DECLARING,
            "an idle round must stay DECLARING — no timer/scheduler advances it",
        )
        self.assertEqual(
            scene_round.round_number,
            1,
            "round_number must not advance with no action taken",
        )
        self.assertEqual(
            scene_round.action_declarations.filter(round_number=1).count(),
            0,
            "no declaration bridge rows are created without an action",
        )

    def test_maybe_resolve_is_noop_when_no_one_declared(self) -> None:
        """Even an explicit completion check is a no-op while nobody has declared."""
        from world.scenes.round_services import maybe_resolve_scene_round

        scene_round = self._make_round()
        self._add_participant(scene_round, self.sheet_a, initiative_order=0)
        self._add_participant(scene_round, self.sheet_b, initiative_order=1)

        maybe_resolve_scene_round(scene_round)

        scene_round.refresh_from_db()
        self.assertEqual(scene_round.status, RoundStatus.DECLARING)
        self.assertEqual(scene_round.round_number, 1)
