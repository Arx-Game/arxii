"""Tests for scene action services: create_action_request and respond_to_action_request."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.models import KudosSourceCategory
from world.scenes import action_services
from world.scenes.action_constants import (
    DIFFICULTY_VALUES,
    ActionRequestStatus,
    ConsentDecision,
    DifficultyChoice,
)
from world.scenes.action_models import SceneActionTarget
from world.scenes.action_resolvers import _RESOLVER_REGISTRY, register_resolver
from world.scenes.action_services import (
    _auto_resolve_npc_targets,
    create_action_request,
    respond_to_action_request,
    respond_to_action_target,
)
from world.scenes.factories import (
    PersonaFactory,
    SceneActionRequestFactory,
    SceneActionTargetFactory,
    SceneFactory,
)
from world.scenes.models import InteractionTargetPersona
from world.scenes.place_models import InteractionReceiver
from world.scenes.types import EnhancedSceneActionResult


def _make_pending_resolution(success: bool = True) -> PendingActionResolution:
    """Build a minimal PendingActionResolution for mocking."""
    check_result = MagicMock()
    check_result.success_level = 1 if success else -1
    check_result.outcome_name = "Success" if success else "Failure"
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


class TestCreateActionRequest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

    def test_creates_pending_request(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        assert request.pk is not None
        assert request.status == ActionRequestStatus.PENDING
        assert request.action_key == "intimidate"
        assert request.difficulty_choice == DifficultyChoice.NORMAL

    def test_create_persists_effort_not_initiator_difficulty(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
            effort_level="high",
        )
        self.assertEqual(request.effort_level, "high")
        self.assertEqual(request.difficulty_choice, DifficultyChoice.NORMAL)  # defender sets later


class TestRespondToActionRequest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

    def setUp(self) -> None:
        """Mock award_kudos for all tests in this class."""
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        """Stop mocking award_kudos."""
        self.award_kudos_patcher.stop()

    def test_deny_sets_status(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.DENY,
        )
        assert result is None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.DENIED
        assert request.resolved_at is not None

    @patch("world.scenes.action_services.start_action_resolution")
    def test_accept_resolves_and_creates_interaction(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)

        action_template = ActionTemplateFactory()
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        request.action_template = action_template
        request.save(update_fields=["action_template"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )
        assert result is not None
        assert isinstance(result, EnhancedSceneActionResult)
        assert result.action_key == "intimidate"
        assert result.action_resolution is not None

        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        assert request.resolved_at is not None
        assert request.result_interaction is not None

        # Result interaction should have the target as receiver
        receivers = InteractionReceiver.objects.filter(interaction=request.result_interaction)
        assert receivers.count() == 1
        assert receivers.first().persona == self.target

    def test_respond_to_non_pending_returns_none(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        request.status = ActionRequestStatus.RESOLVED
        request.save(update_fields=["status"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )
        assert result is None

    @patch("world.scenes.action_services.start_action_resolution")
    def test_accept_with_hard_difficulty(self, mock_resolve: MagicMock) -> None:
        """Defender sets difficulty_choice before accepting; resolved_difficulty reflects it."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        action_template = ActionTemplateFactory()
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="persuade",
        )
        # Defender sets difficulty at consent time (not the initiator at dispatch)
        request.difficulty_choice = DifficultyChoice.HARD
        request.action_template = action_template
        request.save(update_fields=["action_template", "difficulty_choice"])

        result = respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
        )
        assert result is not None
        request.refresh_from_db()
        assert request.resolved_difficulty == DIFFICULTY_VALUES[DifficultyChoice.HARD]

    def test_accept_without_template_raises(self) -> None:
        """No action_template raises ValueError (not silent failure)."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        # action_template is None by default

        with self.assertRaises(ValueError):
            respond_to_action_request(
                action_request=request,
                decision=ConsentDecision.ACCEPT,
            )


class TestResolverIntegration(TestCase):
    """Tests that the action_resolvers registry is invoked by respond_to_action_request."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

    def setUp(self) -> None:
        """Mock award_kudos for all tests in this class."""
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        """Stop mocking award_kudos."""
        self.award_kudos_patcher.stop()

    @patch("world.scenes.action_services.start_action_resolution")
    def test_resolver_called_on_accept(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)

        captured: list[tuple[int, object]] = []

        def fake_resolver(request, outcome):
            captured.append((request.pk, outcome))

        register_resolver("test_action", fake_resolver)
        self.addCleanup(lambda: _RESOLVER_REGISTRY.pop("test_action", None))

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="test_action",
        )
        action_request.action_template = self.action_template
        action_request.save(update_fields=["action_template"])

        respond_to_action_request(action_request=action_request, decision=ConsentDecision.ACCEPT)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], action_request.pk)

    def test_resolver_not_called_on_deny(self) -> None:
        captured: list[int] = []

        def _deny_resolver(_request, _outcome):
            captured.append(1)

        register_resolver("test_action_deny", _deny_resolver)
        self.addCleanup(lambda: _RESOLVER_REGISTRY.pop("test_action_deny", None))

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="test_action_deny",
        )
        respond_to_action_request(action_request=action_request, decision=ConsentDecision.DENY)
        self.assertEqual(captured, [])

    @patch("world.scenes.action_services.start_action_resolution")
    def test_no_resolver_registered_no_op(self, mock_resolve: MagicMock) -> None:
        """Accepting with no resolver registered should not raise."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="unknown_action_xyz",
        )
        action_request.action_template = self.action_template
        action_request.save(update_fields=["action_template"])

        # Should not raise
        result = respond_to_action_request(
            action_request=action_request, decision=ConsentDecision.ACCEPT
        )
        self.assertIsNotNone(result)


class GenericKudosOnAcceptTests(TestCase):
    """Tests that accepting an action request awards Kudos to the target."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.action_template = ActionTemplateFactory()
        # The social_engagement category is seeded by a RunPython migration
        # (progression 0003), which the SQLite fast tier skips (#855) —
        # get_or_create so the fast tier gets the row and the PG tier
        # (where the migration already seeded it) doesn't collide.
        KudosSourceCategory.objects.get_or_create(
            name="social_engagement",
            defaults={
                "display_name": "Social Engagement",
                "description": "Seeded for tests on the no-migrations fast tier.",
                "default_amount": 1,
            },
        )

    def setUp(self) -> None:
        # _get_social_engagement_category memoizes at module level; a row
        # cached from another test class's (rolled-back) transaction would
        # leak in. Reset around every test so each run re-fetches (#855).
        action_services._SOCIAL_ENGAGEMENT_CATEGORY = None
        self.addCleanup(setattr, action_services, "_SOCIAL_ENGAGEMENT_CATEGORY", None)

    @patch("world.scenes.action_services.award_kudos")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_kudos_awarded_to_target_on_accept(
        self, mock_resolve: MagicMock, mock_award_kudos: MagicMock
    ) -> None:
        """Accepting an action request calls award_kudos with target account."""
        from evennia.accounts.models import AccountDB

        mock_resolve.return_value = _make_pending_resolution(success=True)

        # Attach an account to the target's character so the kudos path runs.
        # (The default PersonaFactory wires a CharacterSheet with no db_account.)
        target_account = AccountDB.objects.create(username="kudos_target_acct")
        self.target.character_sheet.character.db_account = target_account
        self.target.character_sheet.character.save(update_fields=["db_account"])

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="generic",
            status=ActionRequestStatus.PENDING,
        )
        action_request.action_template = self.action_template
        action_request.save(update_fields=["action_template"])

        respond_to_action_request(action_request=action_request, decision=ConsentDecision.ACCEPT)

        # Verify award_kudos was called with the target account
        mock_award_kudos.assert_called_once()
        call_args = mock_award_kudos.call_args
        self.assertIsNotNone(call_args)
        # Check that source_category name is 'social_engagement'
        self.assertEqual(
            call_args.kwargs.get("source_category").name,
            "social_engagement",
        )

    @patch("world.scenes.action_services.start_action_resolution")
    def test_no_kudos_award_call_on_deny(self, mock_resolve: MagicMock) -> None:
        """Denying an action request does not call award_kudos."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="generic",
            status=ActionRequestStatus.PENDING,
        )
        action_request.action_template = self.action_template
        action_request.save(update_fields=["action_template"])

        with patch("world.scenes.action_services.award_kudos") as mock_award:
            respond_to_action_request(action_request=action_request, decision=ConsentDecision.DENY)
            # Verify award_kudos was NOT called
            mock_award.assert_not_called()

    @patch("world.scenes.action_services.award_kudos")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_no_kudos_when_target_has_no_account(
        self, mock_resolve: MagicMock, mock_award_kudos: MagicMock
    ) -> None:
        """Skip kudos award when target's character has no linked account.

        Personas backed by characters without db_account (NPCs, test fixtures)
        are valid action_request targets; the kudos award is a no-op for them
        rather than crashing on a NOT NULL constraint violation.
        """
        mock_resolve.return_value = _make_pending_resolution(success=True)

        # Detach the target character's account, simulating an NPC persona.
        self.target.character_sheet.character.db_account = None
        self.target.character_sheet.character.save(update_fields=["db_account"])

        action_request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="generic",
            status=ActionRequestStatus.PENDING,
        )
        action_request.action_template = self.action_template
        action_request.save(update_fields=["action_template"])

        # Should not raise — and should not call award_kudos.
        respond_to_action_request(action_request=action_request, decision=ConsentDecision.ACCEPT)
        mock_award_kudos.assert_not_called()


class TestCreateActionRequestSnapshotFields(TestCase):
    """Snapshot fields are populated when ritual_id is provided."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.constants import RitualExecutionKind
        from world.magic.factories import RitualCheckConfigFactory, RitualFactory

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        cls.config = RitualCheckConfigFactory(ritual=cls.ritual)

    def test_create_action_request_with_ritual_id_populates_snapshot(self) -> None:
        """When ritual_id is provided, all snapshot fields are populated from the ritual."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="anima_ritual",
            ritual_id=self.ritual.pk,
        )

        assert request.snapshot_ritual == self.ritual
        assert request.snapshot_stat == self.config.stat
        assert request.snapshot_skill == self.config.skill
        assert request.snapshot_specialization == self.config.specialization
        assert request.snapshot_resonance == self.config.resonance
        assert request.snapshot_check_type == self.config.check_type
        assert request.snapshot_target_difficulty == self.config.target_difficulty

    def test_create_action_request_without_ritual_id_leaves_snapshot_null(self) -> None:
        """Without ritual_id, all snapshot fields remain None."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )

        assert request.snapshot_stat is None
        assert request.snapshot_skill is None
        assert request.snapshot_specialization is None
        assert request.snapshot_resonance is None
        assert request.snapshot_check_type is None
        assert request.snapshot_target_difficulty is None


class TestRespondToActionTarget(TestCase):
    """Tests for the per-additional-target consent + resolution service."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

    def setUp(self) -> None:
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def _make_request_with_template(self) -> "SceneActionRequest":
        """Build a SceneActionRequest that has an action_template set (needed to resolve)."""
        from world.scenes.action_models import SceneActionRequest

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            action_key="intimidate",
            status=ActionRequestStatus.PENDING,
        )
        SceneActionRequest.objects.filter(pk=request.pk).update(
            action_template=self.action_template
        )
        request.action_template = self.action_template
        return request

    @patch("world.scenes.action_services.start_action_resolution")
    def test_respond_to_action_target_accept_resolves_only_that_row(
        self, mock_resolve: MagicMock
    ) -> None:
        """Accepting an action target resolves only that row; sibling stays PENDING."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = self._make_request_with_template()
        row = SceneActionTargetFactory(action_request=request)
        other = SceneActionTargetFactory(action_request=request)

        result = respond_to_action_target(action_target=row, decision=ConsentDecision.ACCEPT)

        row.refresh_from_db()
        other.refresh_from_db()

        self.assertEqual(row.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(row.result_interaction)
        self.assertEqual(other.status, ActionRequestStatus.PENDING)
        self.assertIsNotNone(result)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_respond_to_action_target_interaction_references_additional_target_persona(
        self, mock_resolve: MagicMock
    ) -> None:
        """The result_interaction for an additional target names THAT target, not the primary.

        Regression guard: _create_result_interaction previously always read
        action_request.target_persona (the primary), so every additional-target
        resolution silently created an interaction naming the WRONG persona.
        """
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = self._make_request_with_template()
        # request.target_persona is the PRIMARY target (set by the factory).
        primary_persona = request.target_persona
        # row.target_persona is the ADDITIONAL target — a distinct persona.
        row = SceneActionTargetFactory(action_request=request)
        additional_persona = row.target_persona
        # Sanity: they must actually be different personas.
        self.assertNotEqual(primary_persona.pk, additional_persona.pk)

        respond_to_action_target(action_target=row, decision=ConsentDecision.ACCEPT)
        row.refresh_from_db()

        self.assertIsNotNone(row.result_interaction)
        interaction = row.result_interaction

        # The InteractionTargetPersona through-table must point at the ADDITIONAL
        # target, NOT the primary.
        target_pks = list(
            InteractionTargetPersona.objects.filter(interaction=interaction).values_list(
                "persona_id", flat=True
            )
        )
        self.assertIn(
            additional_persona.pk,
            target_pks,
            "Additional-target persona must appear in InteractionTargetPersona",
        )
        self.assertNotIn(
            primary_persona.pk,
            target_pks,
            "Primary persona must NOT appear in the additional-target's interaction",
        )

    def test_respond_to_action_target_deny_marks_denied_no_interaction(self) -> None:
        """Denying an action target sets DENIED status and leaves result_interaction null."""
        row = SceneActionTargetFactory()

        result = respond_to_action_target(action_target=row, decision=ConsentDecision.DENY)

        row.refresh_from_db()

        self.assertEqual(row.status, ActionRequestStatus.DENIED)
        self.assertIsNone(row.result_interaction)
        self.assertIsNone(result)

    def test_respond_to_action_target_non_pending_returns_none(self) -> None:
        """Calling on a non-PENDING row is a no-op (idempotent guard)."""
        row = SceneActionTargetFactory(status=ActionRequestStatus.RESOLVED)

        result = respond_to_action_target(action_target=row, decision=ConsentDecision.ACCEPT)

        self.assertIsNone(result)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_respond_to_action_target_accept_sets_resolved_fields(
        self, mock_resolve: MagicMock
    ) -> None:
        """Accept path writes status, resolved_at, resolved_difficulty on the row."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = self._make_request_with_template()
        row = SceneActionTargetFactory(action_request=request)

        respond_to_action_target(action_target=row, decision=ConsentDecision.ACCEPT)

        row.refresh_from_db()
        self.assertEqual(row.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(row.resolved_at)
        self.assertIsNotNone(row.resolved_difficulty)
        self.assertEqual(row.resolved_difficulty, DIFFICULTY_VALUES[DifficultyChoice.NORMAL])


def _make_pc_persona():
    """Create a Persona backed by a Character that has a db_account (a real player).

    The result passes ``_persona_is_npc`` as False.  Mirrors the pattern used in
    test_targeted_action_e2e.py: CharacterSheet → primary_persona + wired account.
    """
    account = AccountFactory()
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    persona = sheet.primary_persona
    # Wire the account to the character so _persona_is_npc returns False.
    character.db_account = account
    character.save(update_fields=["db_account"])
    return persona, account


def _make_npc_persona():
    """Create a Persona whose character has no db_account (NPC).

    ``PersonaFactory`` leaves the underlying character without db_account by
    default, so the result passes ``_persona_is_npc`` as True.
    """
    return PersonaFactory()


class MultiTargetE2ETests(TestCase):
    """End-to-end service-layer test for multi-target dispatch (#572).

    Exercises the multi-target service pipeline covering:
    - One NPC additional target: auto-resolved at dispatch via ``_auto_resolve_npc_targets``.
    - Three PC additional targets: start PENDING.
    - PC-A accepts → RESOLVED with its own result_interaction naming PC-A.
    - PC-B denies → DENIED, no interaction.
    - PC-C (AFK) left PENDING; siblings resolve independently (non-blocking).

    The primary FK target on the request is a dedicated persona; all four personas
    under test are wired as ``SceneActionTarget`` additional-target rows so that
    ``respond_to_action_target`` drives their individual resolution.

    ``start_action_resolution`` is mocked (I/O stub), but every service function
    that matters — ``_auto_resolve_npc_targets``, ``respond_to_action_target`` —
    runs for real.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.primary_target = PersonaFactory()  # FK target; not under test here
        cls.action_template = ActionTemplateFactory()

        # NPC additional target — character has no db_account.
        cls.npc_persona = _make_npc_persona()

        # PC additional targets — characters have db_account.
        cls.pc_a_persona, cls.pc_a_account = _make_pc_persona()
        cls.pc_b_persona, cls.pc_b_account = _make_pc_persona()
        cls.pc_c_persona, cls.pc_c_account = _make_pc_persona()

        # The social_engagement category is seeded by a RunPython migration that
        # the SQLite fast tier skips (#855).  Create it so kudos award doesn't crash.
        KudosSourceCategory.objects.get_or_create(
            name="social_engagement",
            defaults={
                "display_name": "Social Engagement",
                "description": "Seeded for tests on the no-migrations fast tier.",
                "default_amount": 1,
            },
        )

    def setUp(self) -> None:
        # Reset memoized category so tests don't share stale state across transactions.
        action_services._SOCIAL_ENGAGEMENT_CATEGORY = None
        self.addCleanup(setattr, action_services, "_SOCIAL_ENGAGEMENT_CATEGORY", None)
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def _make_action_request(self, mock_resolve: MagicMock) -> "SceneActionRequest":
        """Build a multi-target request with 1 NPC + 3 PC additional target rows.

        ``create_action_request`` does not accept an action_template (it is attached
        by a separate pipeline step), but ``_auto_resolve_npc_targets`` calls
        ``_resolve_action_against_persona`` which requires the template.  To exercise
        the full service layer without modifying production code we:

          1. Create the request via ``SceneActionRequestFactory`` with the template
             already set (bypasses only the action_template wiring step, which has
             its own unit tests).
          2. Create ``SceneActionTarget`` rows for all four additional personas —
             exactly what ``create_action_request`` does at line 200.
          3. Call ``_auto_resolve_npc_targets`` directly — the same function
             ``create_action_request`` calls at line 202.
        """
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.primary_target,
            action_key="intimidate",
            action_template=self.action_template,
            status=ActionRequestStatus.PENDING,
        )
        for persona in [self.npc_persona, self.pc_a_persona, self.pc_b_persona, self.pc_c_persona]:
            SceneActionTarget.objects.create(action_request=request, target_persona=persona)
        _auto_resolve_npc_targets(request)
        return request

    @patch("world.scenes.action_services.start_action_resolution")
    def test_npc_target_auto_resolves_at_dispatch(self, mock_resolve: MagicMock) -> None:
        """NPC additional target is RESOLVED immediately; its interaction names the NPC."""
        request = self._make_action_request(mock_resolve)

        npc_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.npc_persona
        )
        self.assertEqual(
            npc_row.status,
            ActionRequestStatus.RESOLVED,
            "NPC target must be auto-resolved at dispatch",
        )
        self.assertIsNotNone(npc_row.result_interaction)

        # The interaction must name the NPC persona, not the primary FK target.
        npc_interaction_targets = list(
            InteractionTargetPersona.objects.filter(
                interaction=npc_row.result_interaction
            ).values_list("persona_id", flat=True)
        )
        self.assertIn(
            self.npc_persona.pk,
            npc_interaction_targets,
            "NPC result_interaction must reference the NPC persona",
        )
        self.assertNotIn(
            self.primary_target.pk,
            npc_interaction_targets,
            "Primary FK target must NOT appear in the NPC's interaction",
        )

    @patch("world.scenes.action_services.start_action_resolution")
    def test_pc_targets_start_pending(self, mock_resolve: MagicMock) -> None:
        """PC additional targets are NOT auto-resolved; they start PENDING."""
        request = self._make_action_request(mock_resolve)

        for persona in [self.pc_a_persona, self.pc_b_persona, self.pc_c_persona]:
            row = SceneActionTarget.objects.get(action_request=request, target_persona=persona)
            self.assertEqual(row.status, ActionRequestStatus.PENDING)
            self.assertIsNone(row.result_interaction)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_pc_a_accept_resolves_own_row_with_correct_persona(
        self, mock_resolve: MagicMock
    ) -> None:
        """PC-A accepts → its row is RESOLVED; interaction names PC-A, not NPC or PC-B."""
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_action_request(mock_resolve)

        pc_a_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.pc_a_persona
        )
        self.assertEqual(pc_a_row.status, ActionRequestStatus.PENDING)

        respond_to_action_target(action_target=pc_a_row, decision=ConsentDecision.ACCEPT)

        pc_a_row.refresh_from_db()
        self.assertEqual(pc_a_row.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(pc_a_row.result_interaction)

        pc_a_targets = list(
            InteractionTargetPersona.objects.filter(
                interaction=pc_a_row.result_interaction
            ).values_list("persona_id", flat=True)
        )
        self.assertIn(
            self.pc_a_persona.pk,
            pc_a_targets,
            "PC-A result_interaction must reference PC-A",
        )
        self.assertNotIn(
            self.npc_persona.pk,
            pc_a_targets,
            "NPC persona must NOT appear in PC-A's interaction",
        )
        self.assertNotIn(
            self.pc_b_persona.pk,
            pc_a_targets,
            "PC-B must NOT appear in PC-A's interaction",
        )

    @patch("world.scenes.action_services.start_action_resolution")
    def test_pc_b_deny_marks_denied_no_interaction(self, mock_resolve: MagicMock) -> None:
        """PC-B denies → its row is DENIED; no interaction; NPC and PC-C rows unaffected."""
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_action_request(mock_resolve)

        pc_b_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.pc_b_persona
        )
        result = respond_to_action_target(action_target=pc_b_row, decision=ConsentDecision.DENY)

        pc_b_row.refresh_from_db()
        self.assertEqual(pc_b_row.status, ActionRequestStatus.DENIED)
        self.assertIsNone(pc_b_row.result_interaction)
        self.assertIsNone(result)

        # NPC row should be unaffected (RESOLVED from dispatch).
        npc_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.npc_persona
        )
        self.assertEqual(npc_row.status, ActionRequestStatus.RESOLVED)

        # PC-C is still PENDING.
        pc_c_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.pc_c_persona
        )
        self.assertEqual(pc_c_row.status, ActionRequestStatus.PENDING)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_afk_pc_stays_pending_non_blocking(self, mock_resolve: MagicMock) -> None:
        """PC-C (AFK) remains PENDING after PC-A accepts and PC-B denies.

        Validates non-blocking independence: sibling resolutions must not touch
        the AFK row.
        """
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_action_request(mock_resolve)

        pc_a_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.pc_a_persona
        )
        pc_b_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.pc_b_persona
        )
        pc_c_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.pc_c_persona
        )

        # Resolve both siblings without touching PC-C.
        respond_to_action_target(action_target=pc_a_row, decision=ConsentDecision.ACCEPT)
        respond_to_action_target(action_target=pc_b_row, decision=ConsentDecision.DENY)

        # PC-C must still be PENDING.
        pc_c_row.refresh_from_db()
        self.assertEqual(
            pc_c_row.status,
            ActionRequestStatus.PENDING,
            "AFK PC-C must remain PENDING after siblings resolve",
        )
        self.assertIsNone(pc_c_row.result_interaction)

        # Verify sibling outcomes are intact.
        pc_a_row.refresh_from_db()
        self.assertEqual(pc_a_row.status, ActionRequestStatus.RESOLVED)
        pc_b_row.refresh_from_db()
        self.assertEqual(pc_b_row.status, ActionRequestStatus.DENIED)


class TestPerTargetResolverIntegration(TestCase):
    """The resolver registry fires once per accepted additional target (#1178)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

    def setUp(self) -> None:
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def _make_request(self, action_key: str) -> "SceneActionRequest":
        from world.scenes.action_models import SceneActionRequest

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            action_key=action_key,
            status=ActionRequestStatus.PENDING,
        )
        SceneActionRequest.objects.filter(pk=request.pk).update(
            action_template=self.action_template
        )
        request.action_template = self.action_template
        return request

    @patch("world.scenes.action_services.start_action_resolution")
    def test_resolver_fires_for_accepted_additional_target(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)
        captured: list[tuple[int, object]] = []

        def fake_resolver(request, outcome):
            captured.append((request.pk, outcome))

        register_resolver("test_target_resolver", fake_resolver)
        self.addCleanup(lambda: _RESOLVER_REGISTRY.pop("test_target_resolver", None))

        request = self._make_request("test_target_resolver")
        accepted = SceneActionTargetFactory(action_request=request)
        denied = SceneActionTargetFactory(action_request=request)

        result = respond_to_action_target(action_target=accepted, decision=ConsentDecision.ACCEPT)
        respond_to_action_target(action_target=denied, decision=ConsentDecision.DENY)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], request.pk)
        self.assertIs(captured[0][1], result)  # resolver gets THIS target's result

    @patch("world.scenes.action_services.start_action_resolution")
    def test_no_resolver_registered_is_noop(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request("unregistered_target_action")
        row = SceneActionTargetFactory(action_request=request)

        result = respond_to_action_target(action_target=row, decision=ConsentDecision.ACCEPT)
        self.assertIsNotNone(result)  # must not raise
