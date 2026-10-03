"""Soulfray stage draws spin the #924 outcome wheel; the wheel never shows what was removed."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.db import transaction
from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.models import Consequence
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.factories import SoulfrayConfigFactory
from world.magic.services.soulfray import (
    _fire_stage_consequence_pool,
    accumulate_soulfray,
    deliver_soulfray_reveal,
)
from world.magic.types import SoulfrayResult, SoulfrayReveal
from world.traits.factories import CheckOutcomeFactory

_FACE_KEYS = {"label", "tier_name", "weight", "is_selected"}
_PAYLOAD_KEYS = {"template_name", "consequences", "stage_label"}


def _stage_label_of(call) -> str:
    """The stage label a roulette_result msg() call carried, or "chart" for none."""
    return call.kwargs["roulette_result"][1].get("stage_label") or "chart"


class SoulfrayRevealTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.botch = CheckOutcomeFactory(name="Critical Failure", success_level=-3)
        cls.config = SoulfrayConfigFactory(
            resilience_check_type=CheckTypeFactory(name="Magical Endurance")
        )
        cls.template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)

    def _stage(self, *rows: Consequence):
        pool = ConsequencePoolFactory()
        for row in rows:
            ConsequencePoolEntryFactory(pool=pool, consequence=row)
        return ConditionStageFactory(
            condition=self.template, stage_order=5, name="Unravelling", consequence_pool=pool
        )

    def _row(self, label: str, **flags) -> Consequence:
        return ConsequenceFactory(outcome_tier=self.botch, label=label, **flags)

    def _draw(self, stage, *, lethal: bool, character=None):
        character = character or CharacterFactory()  # no CharacterSheet: death seam skips it
        with patch(
            "world.checks.services.perform_check_with_modifiers",
            return_value=MagicMock(outcome=self.botch),
        ):
            _check, _applied, reveal = _fire_stage_consequence_pool(
                character=character,
                current_stage=stage,
                soulfray_config=self.config,
                technique_check_result=None,
                lethal=lethal,
            )
        return character, reveal

    def test_a_ticked_row_reveals(self) -> None:
        _character, reveal = self._draw(
            self._stage(self._row("PLACEHOLDER scar", theater=True)), lethal=True
        )
        self.assertIsNotNone(reveal)
        self.assertEqual(reveal.selected.label, "PLACEHOLDER scar")
        self.assertEqual(reveal.stage_label, "Soulfray · Unravelling")
        self.assertEqual(reveal.title, "Magical Endurance")

    def test_a_can_kill_row_reveals(self) -> None:
        _character, reveal = self._draw(
            self._stage(self._row("PLACEHOLDER death", character_loss=True)), lethal=True
        )
        self.assertIsNotNone(reveal)
        self.assertTrue(reveal.selected.character_loss)

    def test_a_plain_row_does_not_reveal(self) -> None:
        _character, reveal = self._draw(
            self._stage(self._row("PLACEHOLDER ache"), self._row("PLACEHOLDER chill")),
            lethal=True,
        )
        self.assertIsNone(reveal)

    def test_an_excluded_option_appears_and_is_never_the_landed_face(self) -> None:
        stage = self._stage(
            self._row("PLACEHOLDER death", character_loss=True, weight=1000),
            self._row("PLACEHOLDER wound", weight=1),
        )
        for _ in range(5):  # weight 1000 would land on death every time if it were drawable
            _character, reveal = self._draw(stage, lethal=False)
            self.assertIsNotNone(reveal)
            labels = [face.label for face in reveal.faces]
            self.assertIn("PLACEHOLDER death", labels)
            self.assertEqual(reveal.selected.label, "PLACEHOLDER wound")
            self.assertFalse(reveal.selected.character_loss)

    def test_a_positive_rollmod_redirect_still_shows_the_death_face(self) -> None:
        """A positive rollmod turns a drawn Can kill row into its worst non-loss sibling
        (filter_character_loss). The wheel still shows death and lands on the redirect."""
        sheet = CharacterSheetFactory()
        sheet.rollmod = 10
        sheet.save(update_fields=["rollmod"])
        stage = self._stage(
            self._row("PLACEHOLDER death", character_loss=True, weight=1000),
            self._row("PLACEHOLDER wound", weight=1),
        )
        with patch("world.vitals.services.defer_or_apply_certain_death") as seam:
            _character, reveal = self._draw(stage, lethal=True, character=sheet.character)
        seam.assert_not_called()
        self.assertIsNotNone(reveal)
        self.assertIn("PLACEHOLDER death", [face.label for face in reveal.faces])
        self.assertEqual(reveal.selected.label, "PLACEHOLDER wound")

    def test_the_payload_carries_no_excluded_marker(self) -> None:
        stage = self._stage(
            self._row("PLACEHOLDER death", character_loss=True),
            self._row("PLACEHOLDER wound"),
        )
        character, reveal = self._draw(stage, lethal=False)
        with patch.object(character, "msg") as msg:
            self.assertTrue(deliver_soulfray_reveal(character, reveal))
        payload = msg.call_args.kwargs["roulette_result"][1]
        self.assertEqual(set(payload), _PAYLOAD_KEYS)
        for face in payload["consequences"]:
            self.assertEqual(set(face), _FACE_KEYS)
        death = next(f for f in payload["consequences"] if f["label"] == "PLACEHOLDER death")
        self.assertFalse(death["is_selected"])

    def test_a_tier_emptied_by_filtering_sends_no_wheel(self) -> None:
        _character, reveal = self._draw(
            self._stage(self._row("PLACEHOLDER death", character_loss=True)), lethal=False
        )
        self.assertIsNone(reveal)


class NonSoulfrayCallersUnchangedTests(TestCase):
    """select_consequence_from_result still emits nothing; the scene second-stage wheel still
    skips a single-candidate tier."""

    def test_select_consequence_from_result_never_spins(self) -> None:
        from actions.types import WeightedConsequence
        from world.checks.consequence_resolution import (
            select_consequence_from_result,
        )

        tier = CheckOutcomeFactory(name="Failure", success_level=-1)
        row = ConsequenceFactory(outcome_tier=tier, label="PLACEHOLDER mishap", theater=True)
        character = CharacterFactory()
        with patch.object(character, "msg") as msg:
            pending = select_consequence_from_result(
                character,
                MagicMock(outcome=tier),
                [WeightedConsequence(consequence=row, weight=1, character_loss=False)],
            )
        self.assertEqual(pending.selected_consequence.consequence, row)
        msg.assert_not_called()

    def test_scene_second_stage_still_needs_two_faces(self) -> None:
        from actions.types import WeightedConsequence
        from world.checks.theater import consequence_pool_faces

        tier = CheckOutcomeFactory(name="Success", success_level=1)
        row = ConsequenceFactory(outcome_tier=tier, theater=True)
        faces, selected = consequence_pool_faces(
            consequences=[WeightedConsequence(consequence=row, weight=1, character_loss=False)],
            outcome=tier,
            selected_consequence_id=row.pk,
        )
        self.assertEqual((faces, selected), ([], None))


class SoulfrayRevealDeliveryTests(TestCase):
    """Delivery happens on commit, and the scene path plays it after the action's own wheel."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.botch = CheckOutcomeFactory(name="Critical Failure", success_level=-3)

    def _reveal(self) -> SoulfrayReveal:
        face = Consequence(
            outcome_tier=self.botch, label="PLACEHOLDER scar", weight=1, theater=True
        )
        return SoulfrayReveal(
            title="Magical Endurance",
            stage_label="Soulfray · Tearing",
            faces=(face,),
            selected=face,
        )

    # --- accumulate_soulfray: default on-commit delivery, deferral, rollback -------------

    def _accumulate(self, character, *, defer_reveal: bool) -> SoulfrayResult | None:
        held = SoulfrayResult(
            severity_added=3, stage_name="Tearing", stage_advanced=True, reveal=self._reveal()
        )
        with (
            patch("world.magic.services.soulfray.calculate_soulfray_severity", return_value=3),
            patch(
                "world.magic.services.soulfray._handle_soulfray_accumulation",
                return_value=held,
            ),
        ):
            return accumulate_soulfray(
                character=character,
                anima=MagicMock(),
                deficit=5,
                soulfray_config=MagicMock(),
                check_result=None,
                defer_reveal=defer_reveal,
            )

    def test_accumulate_delivers_the_reveal_on_commit_by_default(self) -> None:
        character = CharacterFactory()
        with patch.object(character, "msg") as msg:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self._accumulate(character, defer_reveal=False)
            msg.assert_not_called()  # nothing reaches the client before commit
            for callback in callbacks:
                callback()
        self.assertEqual([_stage_label_of(c) for c in msg.call_args_list], ["Soulfray · Tearing"])

    def test_a_rolled_back_cast_never_spins(self) -> None:
        character = CharacterFactory()
        with (
            patch.object(character, "msg") as msg,
            self.captureOnCommitCallbacks(execute=True) as callbacks,
        ):
            try:
                with transaction.atomic():
                    self._accumulate(character, defer_reveal=False)
                    raise RuntimeError
            except RuntimeError:
                pass
        self.assertEqual(callbacks, [])
        msg.assert_not_called()

    def test_a_deferred_reveal_is_held_on_the_result_not_sent(self) -> None:
        character = CharacterFactory()
        with (
            patch.object(character, "msg") as msg,
            self.captureOnCommitCallbacks(execute=True) as callbacks,
        ):
            result = self._accumulate(character, defer_reveal=True)
        self.assertEqual(callbacks, [])
        msg.assert_not_called()
        self.assertIsNotNone(result.reveal)

    # --- the scene path plays the held reveal ------------------------------------------

    def _schedule(self, *, roller, target, faces_return, **kwargs) -> None:
        from world.scenes.action_services import (
            _schedule_check_outcome_theater,
        )

        request = SimpleNamespace(action_template_id=None, action_key="flirt")
        with (
            patch("world.scenes.action_services.check_outcome_faces", return_value=faces_return),
            self.captureOnCommitCallbacks(execute=True),
        ):
            _schedule_check_outcome_theater(
                action_request=request,
                initiator_character=roller,
                target_character=target,
                soulfray_reveal=self._reveal(),
                **kwargs,
            )

    def test_scene_theater_plays_the_soulfray_reveal_last_and_to_the_roller_only(self) -> None:
        roller = CharacterFactory()
        target = CharacterFactory()
        chart_face = Consequence(outcome_tier=self.botch, label="Critical Failure", weight=1)
        with patch.object(roller, "msg") as roller_msg, patch.object(target, "msg") as target_msg:
            self._schedule(
                roller=roller,
                target=target,
                faces_return=([chart_face], chart_face),
                check_result=MagicMock(),
            )
        self.assertEqual(
            [_stage_label_of(c) for c in roller_msg.call_args_list],
            ["chart", "Soulfray · Tearing"],
        )
        self.assertEqual([_stage_label_of(c) for c in target_msg.call_args_list], ["chart"])

    def test_the_held_reveal_plays_when_the_action_has_no_wheel_of_its_own(self) -> None:
        """No chart on the action's check: the action spins nothing, the backlash still does."""
        roller = CharacterFactory()
        with patch.object(roller, "msg") as roller_msg:
            self._schedule(
                roller=roller, target=None, faces_return=([], None), check_result=MagicMock()
            )
        self.assertEqual(
            [_stage_label_of(c) for c in roller_msg.call_args_list], ["Soulfray · Tearing"]
        )

    def test_the_held_reveal_plays_when_the_action_has_no_steps(self) -> None:
        """Before #4089 an action with no check steps returned before scheduling anything,
        which would have dropped a held reveal."""
        roller = CharacterFactory()
        with patch.object(roller, "msg") as roller_msg:
            self._schedule(
                roller=roller,
                target=None,
                faces_return=([], None),
                check_result=None,
                resolution=SimpleNamespace(gate_results=[], main_result=None),
            )
        self.assertEqual(
            [_stage_label_of(c) for c in roller_msg.call_args_list], ["Soulfray · Tearing"]
        )

    def test_the_enhanced_scene_action_defers_and_hands_the_reveal_on(self) -> None:
        """The one route that defers (_resolve_enhanced_action) asks use_technique to hold
        the reveal, and _soulfray_reveal_of reads it back off the result it returns."""
        from world.scenes.action_services import (
            _resolve_enhanced_action,
            _soulfray_reveal_of,
        )

        reveal = self._reveal()
        technique_result = MagicMock()
        technique_result.soulfray_result = SoulfrayResult(
            severity_added=1, stage_name="Tearing", stage_advanced=True, reveal=reveal
        )
        with (
            patch(
                "world.magic.services.use_technique", return_value=technique_result
            ) as use_technique,
            patch("world.magic.services.cast_threads.applicable_threads_for_cast", return_value=[]),
            patch("world.magic.services.fury.run_fury_for_action", return_value=None),
        ):
            result = _resolve_enhanced_action(
                character=MagicMock(),
                technique=MagicMock(),
                action_template=MagicMock(),
                action_key="flirt",
                difficulty=10,
                context=MagicMock(),
            )
        self.assertIs(use_technique.call_args.kwargs["defer_soulfray_reveal"], True)
        self.assertIs(_soulfray_reveal_of(result), reveal)
