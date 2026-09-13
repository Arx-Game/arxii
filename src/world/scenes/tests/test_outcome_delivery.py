"""Live delivery of resolved outcome rows (#3807).

Scene action result rows, treatment outcomes, and cast outcome poses were persisted
and delivered to nobody live -- no WebSocket push, no telnet line -- unlike every
other production ``create_interaction`` caller. These tests drive the real
production entry points (``respond_to_action_request``, ``_resolve_treatment_request``,
``create_cast_outcome_pose``) and assert the row actually reaches connected clients
on commit, via ``deliver_outcome_interaction``.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.db import transaction
from django.test import TestCase
from evennia.objects.objects import ObjectSessionHandler

from actions.constants import ActionTargetType, ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.types import CheckResult as RealCheckResult
from world.conditions.factories import ConditionInstanceFactory, TreatmentTemplateFactory
from world.conditions.types import TreatmentOutcome
from world.magic.factories import TechniqueFactory
from world.magic.services.cast_observation import CastAudience
from world.scenes.action_constants import ActionDelivery, ActionRequestStatus, ConsentDecision
from world.scenes.action_services import (
    _resolve_treatment_request,
    create_action_request,
    create_and_resolve_area_action,
    respond_to_action_request,
)
from world.scenes.cast_services import create_cast_outcome_pose
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneActionRequestFactory, SceneFactory
from world.scenes.interaction_services import create_interaction, deliver_outcome_interaction
from world.scenes.models import Persona
from world.scenes.types import EnhancedSceneActionResult
from world.traits.factories import CheckSystemSetupFactory


def _pending_resolution_with_chart(chart: object, outcome: object) -> PendingActionResolution:
    """A PendingActionResolution whose check_result is a REAL CheckResult, so
    check_outcome_faces() (chart bands, not a MagicMock) can build faces from it."""
    check_result = RealCheckResult(
        check_type=None,
        outcome=outcome,
        chart=chart,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )
    main_result = StepResult(step_label="main", check_result=check_result, consequence_id=None)
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


def _pending_resolution_partial_success() -> PendingActionResolution:
    """A mocked (chart-less) resolution whose outcome is a Partial Success --
    success_level 0, so the old wording rendered it as "Failure (Partial Success)"."""
    check_result = MagicMock()
    check_result.success_level = 0
    check_result.outcome_name = "Partial Success"
    main_result = StepResult(step_label="main", check_result=check_result, consequence_id=None)
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


def _placed_persona(room: object, db_key: str) -> Persona:
    """A PRIMARY persona whose character is actually located in `room`."""
    character = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _calls_for(mock_msg: MagicMock, obj: object) -> list:
    """Calls to ``obj.msg(...)`` when ``DefaultObject.msg`` is patched with autospec=True.

    Needed for a character reached only via a receiver query (Persona ->
    CharacterSheet -> character): the idmapper identity map does not dedupe an
    ObjectDB instance reached through that cross-model ``select_related`` chain (a
    pre-existing idmapper gotcha, distinct from #3807 -- confirmed empirically: the
    production delivery is correct, but ``character.msg = Mock()`` on an instance
    obtained one way silently never observes calls Evennia routes to the "same"
    character fetched via this different query path). Patching the class method once
    and filtering by pk sidesteps the identity gap entirely. Room-heard delivery
    (``location.contents``, ObjectDB's own manager) does not have this problem, so
    those tests mock ``.msg`` directly on the instance.
    """
    return [c for c in mock_msg.call_args_list if c.args[0].pk == obj.pk]


def _patch_sessions(sessions_by_pk: dict) -> object:
    """Patch `ObjectSessionHandler.all` per-character, mirroring test_threading.py."""

    def _fake_all(handler: ObjectSessionHandler) -> list[object]:
        return sessions_by_pk.get(handler.obj.pk, [])

    return patch.object(ObjectSessionHandler, "all", _fake_all)


class _ScenePipelineTestCase(TestCase):
    """Room + initiator/target/bystander personas, all actually located together."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        cls.initiator = _placed_persona(cls.room, "Initiator")
        cls.target = _placed_persona(cls.room, "Target")
        cls.bystander = _placed_persona(cls.room, "Bystander")
        cls.scene = SceneFactory(location=cls.room)

    def setUp(self) -> None:
        # accrue hits the DB for KudosSourceCategory/GameWeek, which may not be seeded
        # in the fast tier -- mirrors TestRespondToActionRequest in test_action_services.py.
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.mock_accrue = self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    def _accept(self, *, delivery: str = "", mock_resolve: MagicMock) -> None:
        from world.scenes.tests.test_action_services import _make_pending_resolution

        mock_resolve.return_value = _make_pending_resolution(success=True)
        template = ActionTemplateFactory()
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
            delivery=delivery,
        )
        request.action_template = template
        request.save(update_fields=["action_template"])
        with self.captureOnCommitCallbacks(execute=True):
            respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)


class TargetedSocialCheckDeliveryTests(_ScenePipelineTestCase):
    """A resolved targeted social check reaches the room live (#3807)."""

    @patch("world.scenes.action_services.start_action_resolution")
    def test_accept_pushes_to_bystander_with_target_marked(self, mock_resolve: MagicMock) -> None:
        bystander_char = self.bystander.character_sheet.character
        bystander_char.msg = Mock()

        self._accept(mock_resolve=mock_resolve)

        assert bystander_char.msg.call_count >= 1
        interaction_calls = [
            call for call in bystander_char.msg.call_args_list if "interaction" in call.kwargs
        ]
        assert len(interaction_calls) == 1, bystander_char.msg.call_args_list
        payload = interaction_calls[0].kwargs["interaction"][1]
        assert self.target.pk in payload["target_persona_ids"]


class WhisperAndMutterDeliveryTests(_ScenePipelineTestCase):
    """WHISPER stays receiver-scoped; the MUTTER fragment reaches the room (#3807)."""

    @patch("evennia.objects.objects.DefaultObject.msg", autospec=True)
    @patch("world.scenes.action_services.start_action_resolution")
    def test_whisper_reaches_initiator_and_target_only(
        self, mock_resolve: MagicMock, mock_msg: MagicMock
    ) -> None:
        initiator_char = self.initiator.character_sheet.character
        target_char = self.target.character_sheet.character
        bystander_char = self.bystander.character_sheet.character

        self._accept(delivery=ActionDelivery.WHISPER, mock_resolve=mock_resolve)

        def _has_interaction(obj: object) -> bool:
            return any("interaction" in c.kwargs for c in _calls_for(mock_msg, obj))

        assert _has_interaction(initiator_char)
        assert _has_interaction(target_char)
        assert not _has_interaction(bystander_char)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_mutter_fragment_reaches_the_room(self, mock_resolve: MagicMock) -> None:
        bystander_char = self.bystander.character_sheet.character
        bystander_char.msg = Mock()

        self._accept(delivery=ActionDelivery.MUTTER, mock_resolve=mock_resolve)

        fragment_calls = [
            c
            for c in bystander_char.msg.call_args_list
            if "interaction" in c.kwargs
            and c.kwargs["interaction"][1]["mode"] == InteractionMode.MUTTER
        ]
        assert len(fragment_calls) == 1, bystander_char.msg.call_args_list


class TelnetSessionDeliveryTests(_ScenePipelineTestCase):
    """Telnet sessions get the plain-text line; web sessions get only the payload (#3807)."""

    @patch("world.scenes.action_services.start_action_resolution")
    def test_telnet_gets_text_web_does_not(self, mock_resolve: MagicMock) -> None:
        bystander_char = self.bystander.character_sheet.character
        bystander_char.msg = Mock()

        telnet_session = MagicMock()
        telnet_session.protocol_key = "telnet"
        with _patch_sessions({bystander_char.pk: [telnet_session]}):
            self._accept(mock_resolve=mock_resolve)

        text_calls = [
            c for c in bystander_char.msg.call_args_list if c.args and "interaction" not in c.kwargs
        ]
        assert len(text_calls) == 1, bystander_char.msg.call_args_list
        assert text_calls[0].kwargs.get("session") == [telnet_session]

    @patch("world.scenes.action_services.start_action_resolution")
    def test_web_session_gets_no_text_line(self, mock_resolve: MagicMock) -> None:
        bystander_char = self.bystander.character_sheet.character
        bystander_char.msg = Mock()

        web_session = MagicMock()
        web_session.protocol_key = "webclient/websocket"
        with _patch_sessions({bystander_char.pk: [web_session]}):
            self._accept(mock_resolve=mock_resolve)

        text_calls = [
            c for c in bystander_char.msg.call_args_list if c.args and "interaction" not in c.kwargs
        ]
        assert text_calls == []
        payload_calls = [c for c in bystander_char.msg.call_args_list if "interaction" in c.kwargs]
        assert len(payload_calls) == 1


class RollbackDeliveryTests(_ScenePipelineTestCase):
    """A row whose transaction never commits is never delivered (#3807)."""

    def test_rollback_discards_delivery(self) -> None:
        bystander_char = self.bystander.character_sheet.character
        bystander_char.msg = Mock()

        with self.captureOnCommitCallbacks(execute=True), self.assertRaises(RuntimeError):
            with transaction.atomic():
                interaction = create_interaction(
                    persona=self.initiator,
                    content="never seen.",
                    mode=InteractionMode.ACTION,
                    scene=self.scene,
                )
                deliver_outcome_interaction(interaction, location=self.room)
                msg = "boom"
                raise RuntimeError(msg)

        bystander_char.msg.assert_not_called()

    def test_uncaptured_commit_never_fires_in_test_transaction(self) -> None:
        """Without captureOnCommitCallbacks, TestCase's own wrapping transaction
        never commits, so the on_commit callback never runs -- byte-identical to a
        rollback from the caller's point of view."""
        bystander_char = self.bystander.character_sheet.character
        bystander_char.msg = Mock()

        interaction = create_interaction(
            persona=self.initiator,
            content="also never seen.",
            mode=InteractionMode.ACTION,
            scene=self.scene,
        )
        deliver_outcome_interaction(interaction, location=self.room)

        bystander_char.msg.assert_not_called()


class TreatmentOutcomeDeliveryTests(_ScenePipelineTestCase):
    """A resolved treat_condition outcome reaches the room live (#3807)."""

    @patch("world.conditions.services.perform_treatment")
    def test_treatment_outcome_delivered(self, mock_perform_treatment: MagicMock) -> None:
        bystander_char = self.bystander.character_sheet.character
        bystander_char.msg = Mock()

        mock_perform_treatment.return_value = TreatmentOutcome(
            attempt=MagicMock(),
            outcome=MagicMock(),
            effect_applied=False,
            severity_reduced=0,
            tiers_reduced=0,
            helper_backlash_applied=0,
            target_resolved=True,
        )
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="treat_condition",
            status=ActionRequestStatus.PENDING,
        )
        request.treatment = TreatmentTemplateFactory()
        request.target_condition_instance = ConditionInstanceFactory()
        request.save()

        with self.captureOnCommitCallbacks(execute=True):
            _resolve_treatment_request(request)

        interaction_calls = [
            c for c in bystander_char.msg.call_args_list if "interaction" in c.kwargs
        ]
        assert len(interaction_calls) == 1, bystander_char.msg.call_args_list
        payload = interaction_calls[0].kwargs["interaction"][1]
        assert self.target.pk in payload["target_persona_ids"]


class CastOutcomePoseDeliveryTests(_ScenePipelineTestCase):
    """Cast outcome poses reach the room / their receivers live (#3807)."""

    def _result(self) -> EnhancedSceneActionResult:
        action_resolution = SimpleNamespace(main_result=None)
        return EnhancedSceneActionResult(
            action_resolution=action_resolution,  # type: ignore[arg-type]
            action_key="cast",
            technique_result=None,
        )

    def test_unconcealed_pose_delivered_to_the_room(self) -> None:
        bystander_char = self.bystander.character_sheet.character
        bystander_char.msg = Mock()
        technique = TechniqueFactory(intensity=1, damage_profile=False)

        with self.captureOnCommitCallbacks(execute=True):
            pose = create_cast_outcome_pose(
                scene=self.scene,
                caster_persona=self.initiator,
                target_persona=self.target,
                technique=technique,
                result=self._result(),
                audience=CastAudience(concealed=False, full=[], vague=[], effect_only=[]),
            )

        interaction_calls = [
            c for c in bystander_char.msg.call_args_list if "interaction" in c.kwargs
        ]
        assert len(interaction_calls) == 1, bystander_char.msg.call_args_list
        payload = interaction_calls[0].kwargs["interaction"][1]
        assert payload["id"] == pose.pk
        assert self.target.pk in payload["target_persona_ids"]

    @patch("evennia.objects.objects.DefaultObject.msg", autospec=True)
    def test_concealed_tier_reaches_only_its_receivers(self, mock_msg: MagicMock) -> None:
        vague_char = self.target.character_sheet.character
        bystander_char = self.bystander.character_sheet.character
        technique = TechniqueFactory(intensity=1, damage_profile=False)

        with self.captureOnCommitCallbacks(execute=True):
            create_cast_outcome_pose(
                scene=self.scene,
                caster_persona=self.initiator,
                target_persona=None,
                technique=technique,
                result=self._result(),
                audience=CastAudience(
                    concealed=True,
                    full=[self.initiator],
                    vague=[self.target],
                    effect_only=[],
                ),
            )

        vague_calls = [c for c in _calls_for(mock_msg, vague_char) if "interaction" in c.kwargs]
        bystander_calls = [
            c for c in _calls_for(mock_msg, bystander_char) if "interaction" in c.kwargs
        ]
        assert vague_calls
        assert not bystander_calls


class CheckOutcomeTheaterDeliveryTests(_ScenePipelineTestCase):
    """The #3807 Part B roulette wheel reaches the roller and target, on commit only."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        setup = CheckSystemSetupFactory.create()
        cls.chart = setup["charts"][0]
        cls.outcome = setup["outcomes"]["partial"]

    def _accept_with_chart(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _pending_resolution_with_chart(self.chart, self.outcome)
        template = ActionTemplateFactory()
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        request.action_template = template
        request.save(update_fields=["action_template"])
        respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_initiator_and_target_get_roulette_not_bystander(self, mock_resolve: MagicMock) -> None:
        initiator_char = self.initiator.character_sheet.character
        target_char = self.target.character_sheet.character
        bystander_char = self.bystander.character_sheet.character
        initiator_char.msg = Mock()
        target_char.msg = Mock()
        bystander_char.msg = Mock()

        with self.captureOnCommitCallbacks(execute=True):
            self._accept_with_chart(mock_resolve)

        def _has_roulette(mock_msg: Mock) -> bool:
            return any("roulette_result" in c.kwargs for c in mock_msg.call_args_list)

        assert _has_roulette(initiator_char.msg)
        assert _has_roulette(target_char.msg)
        assert not _has_roulette(bystander_char.msg)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_roulette_never_fires_without_a_commit(self, mock_resolve: MagicMock) -> None:
        """Mirrors RollbackDeliveryTests: TestCase's own wrapping transaction never
        commits without captureOnCommitCallbacks, so the on_commit callback never runs."""
        initiator_char = self.initiator.character_sheet.character
        initiator_char.msg = Mock()

        self._accept_with_chart(mock_resolve)

        assert not any("roulette_result" in c.kwargs for c in initiator_char.msg.call_args_list)


class AreaActionTheaterDeliveryTests(_ScenePipelineTestCase):
    """An area action's roulette wheel reaches the roller only (#3807 Part B) --
    no target persona means no target to reveal it to."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        setup = CheckSystemSetupFactory.create()
        cls.chart = setup["charts"][0]
        cls.outcome = setup["outcomes"]["success"]

    @patch("world.scenes.action_services.start_action_resolution")
    def test_area_action_roulette_reaches_roller_only(self, mock_resolve: MagicMock) -> None:
        initiator_char = self.initiator.character_sheet.character
        bystander_char = self.bystander.character_sheet.character
        initiator_char.msg = Mock()
        bystander_char.msg = Mock()

        mock_resolve.return_value = _pending_resolution_with_chart(self.chart, self.outcome)
        template = ActionTemplateFactory(target_type=ActionTargetType.AREA, category="social")
        ActionPointPool.get_or_create_for_character(initiator_char)

        with self.captureOnCommitCallbacks(execute=True):
            create_and_resolve_area_action(
                scene=self.scene,
                initiator_persona=self.initiator,
                action_template=template,
                action_key="spread_a_tale",
            )

        assert any("roulette_result" in c.kwargs for c in initiator_char.msg.call_args_list)
        assert not any("roulette_result" in c.kwargs for c in bystander_char.msg.call_args_list)


class PartialSuccessWordingTests(_ScenePipelineTestCase):
    """A Partial Success is stored as the outcome name alone, no "Failure" prefix

    (success_level 0 previously read as status_word "Failure", so a Partial
    Success was stored as "Failure (Partial Success)" -- #3807 Part B)."""

    @patch("world.scenes.action_services.start_action_resolution")
    def test_partial_success_content_has_no_failure_prefix(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _pending_resolution_partial_success()
        template = ActionTemplateFactory()
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="persuade",
        )
        request.action_template = template
        request.save(update_fields=["action_template"])

        respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        request.refresh_from_db()
        content = request.result_interaction.content
        assert "Partial Success" in content
        assert "Failure" not in content
