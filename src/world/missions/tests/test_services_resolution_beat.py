"""Phase 5b.3 — terminal-path integration tests for the Mission→Beat seam.

When ``_finish_terminal`` fires (the single chokepoint for SOLO and JOINT
terminal completion), ``on_mission_complete_for_beat`` runs. With
``source_beat`` set we expect exactly one trigger record per termination;
with ``source_beat=None`` we expect none.

These tests exercise the wiring, not the engine — there is no Beat-flip
to assert in 5b.3.
"""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.missions.constants import (
    ConflictMode,
    JointCombine,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance, MissionNode, MissionOption
from world.missions.services import beat as beat_service, group_resolve_node, resolve_option
from world.stories.factories import BeatFactory
from world.stories.models import Beat
from world.traits.factories import CheckOutcomeFactory

_PERFORM_CHECK = "world.missions.services.resolution.perform_check"


def _result_for(check_type: object, outcome: object) -> CheckResult:
    """A minimal deterministic CheckResult (no dice) for patched checks.

    Mirrors the helper in :mod:`world.missions.tests.test_services_multiplayer`.
    """
    return CheckResult(
        check_type=check_type,
        outcome=outcome,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


class SoloTerminalBeatSeamTests(TestCase):
    """SOLO ``_finish_terminal`` → exactly one trigger when beat-bound, zero
    otherwise."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        CharacterSheetFactory(character=cls.character)
        cls.template = MissionTemplateFactory(slug="beat-seam-solo-tmpl", risk_tier=2)

    def setUp(self) -> None:
        beat_service.clear_triggers()

    def _make_terminal_run(
        self,
        *,
        source_beat: Beat | None,
    ) -> tuple[MissionInstance, MissionNode, object, MissionOption]:
        instance = MissionInstanceFactory(template=self.template, source_beat=source_beat)
        entry = MissionNodeFactory(template=self.template, key="entry", is_entry=True)
        actor = MissionParticipantFactory(
            instance=instance,
            character=self.character,
            is_contract_holder=True,
        )
        option = MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        return instance, entry, actor, option

    def test_solo_terminal_of_beat_bound_records_one_trigger(self) -> None:
        beat = BeatFactory()
        instance, entry, actor, option = self._make_terminal_run(source_beat=beat)

        # BRANCH option with no branch_target / null-tier route → terminal.
        resolve_option(instance, entry, option, actor, None)

        triggers = beat_service.get_triggers()
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].instance_pk, instance.pk)
        self.assertEqual(triggers[0].beat_pk, beat.pk)

    def test_solo_terminal_of_free_instance_records_no_trigger(self) -> None:
        instance, entry, actor, option = self._make_terminal_run(source_beat=None)

        resolve_option(instance, entry, option, actor, None)

        self.assertEqual(beat_service.get_triggers(), ())


class JointTerminalBeatSeamTests(TestCase):
    """JOINT ``_finish_terminal`` runs exactly once (Phase 4 invariant) — so
    the seam fires exactly once even though there are N participants."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.char_h = CharacterFactory()
        cls.char_2 = CharacterFactory()
        CharacterSheetFactory(character=cls.char_h)
        CharacterSheetFactory(character=cls.char_2)
        cls.template = MissionTemplateFactory(slug="beat-seam-joint-tmpl", risk_tier=2)
        cls.success = CheckOutcomeFactory(name="BeatJSuccess", success_level=3)
        cls.sneak = CheckTypeFactory(name="BeatJSneak")

    def setUp(self) -> None:
        beat_service.clear_triggers()

    def _setup_joint_run(
        self,
        source_beat: Beat,
    ) -> tuple[MissionInstance, MissionNode, dict]:
        instance = MissionInstanceFactory(template=self.template, source_beat=source_beat)
        node = MissionNodeFactory(
            template=self.template,
            key="entry",
            is_entry=True,
            conflict_mode=ConflictMode.JOINT,
            joint_combine=JointCombine.ANY,
        )
        holder = MissionParticipantFactory(
            instance=instance,
            character=self.char_h,
            is_contract_holder=True,
        )
        p2 = MissionParticipantFactory(instance=instance, character=self.char_2)

        option = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.sneak,
        )
        # Terminal route on holder pick's success — _combined_route routes
        # by combined bucket via the holder's authored route-set.
        # _combined_route also requires a non-empty failure pool to exist
        # only when combined result is failure; here we force all-success.
        MissionOptionRouteFactory(
            option=option,
            outcome_tier=self.success,
            target_node=None,  # terminal
        )

        picks = {holder: option, p2: option}
        return instance, node, picks

    def test_joint_terminal_of_beat_bound_records_one_trigger(self) -> None:
        beat = BeatFactory()
        instance, node, picks = self._setup_joint_run(source_beat=beat)

        # Every per-attempt perform_check returns success → JointCombine.ANY
        # ⇒ combined success ⇒ terminal route via _combined_route.
        with patch(
            _PERFORM_CHECK,
            return_value=_result_for(self.sneak, self.success),
        ):
            group_resolve_node(instance, node, picks)

        triggers = beat_service.get_triggers()
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].instance_pk, instance.pk)
        self.assertEqual(triggers[0].beat_pk, beat.pk)
