"""Tests for scene action services: create_action_request and respond_to_action_request."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.factories import SocialConsentCategoryFactory
from world.consent.models import SocialConsentBlacklist
from world.progression.factories import seed_kudos_difficulty_weights
from world.progression.models import KudosPointsData, KudosSourceCategory, WeeklySocialEngagement
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
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
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.mock_accrue = self.accrue_patcher.start()

    def tearDown(self) -> None:
        """Stop mocking award_kudos."""
        self.accrue_patcher.stop()

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


class DenyBlacklistTests(TestCase):
    """DENY + blacklist_actor adds the initiator to the denier's antagonism blacklist (#1698)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.initiator_tenure = cls._tenure_for(cls.initiator)
        cls.target_tenure = cls._tenure_for(cls.target)
        cls.category = SocialConsentCategoryFactory(key="hostile")

    @staticmethod
    def _tenure_for(persona: object) -> object:
        entry = RosterEntryFactory(character_sheet=persona.character_sheet)
        return RosterTenureFactory(roster_entry=entry, end_date=None)

    def _request(self, *, with_category: bool = True):
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
        )
        template = ActionTemplateFactory(consent_category=self.category if with_category else None)
        request.action_template = template
        request.save(update_fields=["action_template"])
        return request

    def test_deny_with_blacklist_adds_entry(self) -> None:
        request = self._request()
        respond_to_action_request(
            action_request=request, decision=ConsentDecision.DENY, blacklist_actor=True
        )
        assert SocialConsentBlacklist.objects.filter(
            owner_tenure=self.target_tenure,
            blocked_tenure=self.initiator_tenure,
            category=self.category,
        ).exists()

    def test_deny_without_flag_adds_no_entry(self) -> None:
        request = self._request()
        respond_to_action_request(action_request=request, decision=ConsentDecision.DENY)
        assert not SocialConsentBlacklist.objects.exists()

    def test_deny_blacklist_no_category_is_noop(self) -> None:
        request = self._request(with_category=False)
        respond_to_action_request(
            action_request=request, decision=ConsentDecision.DENY, blacklist_actor=True
        )
        assert not SocialConsentBlacklist.objects.exists()


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
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.mock_accrue = self.accrue_patcher.start()

    def tearDown(self) -> None:
        """Stop mocking award_kudos."""
        self.accrue_patcher.stop()

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
    """Tests that accepting an action request accrues engagement credit (not instant kudos)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.action_template = ActionTemplateFactory()
        # The social_engagement category is seeded by world/progression/seeds.py
        # (via tools/build_schema.py), which the SQLite fast tier skips (#855) —
        # get_or_create so the fast tier gets the row and the PG tier
        # (where the seed function already seeded it) doesn't collide.
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

    @patch("world.scenes.action_services.accrue")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_accrue_called_for_target_on_accept(
        self, mock_resolve: MagicMock, mock_accrue: MagicMock
    ) -> None:
        """Accepting an action request calls accrue with the target account."""
        from evennia.accounts.models import AccountDB

        mock_resolve.return_value = _make_pending_resolution(success=True)

        # Attach accounts so the accrual path runs (both initiator and target need accounts).
        target_account = AccountDB.objects.create(username="kudos_target_acct")
        self.target.character_sheet.character.db_account = target_account
        self.target.character_sheet.character.save(update_fields=["db_account"])

        initiator_account = AccountDB.objects.create(username="kudos_initiator_acct")
        self.initiator.character_sheet.character.db_account = initiator_account
        self.initiator.character_sheet.character.save(update_fields=["db_account"])

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

        # Verify accrue was called with the target account.
        mock_accrue.assert_called_once()
        call_args = mock_accrue.call_args
        self.assertIsNotNone(call_args)
        self.assertEqual(call_args.args[0], target_account)
        self.assertEqual(call_args.args[1], initiator_account)

    @patch("world.scenes.action_services.accrue")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_no_accrue_call_on_deny(self, mock_resolve: MagicMock, mock_accrue: MagicMock) -> None:
        """Denying an action request does not call accrue."""
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

        respond_to_action_request(action_request=action_request, decision=ConsentDecision.DENY)
        mock_accrue.assert_not_called()

    @patch("world.scenes.action_services.accrue")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_no_accrue_when_target_has_no_account(
        self, mock_resolve: MagicMock, mock_accrue: MagicMock
    ) -> None:
        """Skip accrual when target's character has no linked account (NPC).

        Personas backed by characters without db_account (NPCs, test fixtures)
        are valid action_request targets; the accrual is a no-op for them.
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

        # Should not raise — and should not call accrue.
        respond_to_action_request(action_request=action_request, decision=ConsentDecision.ACCEPT)
        mock_accrue.assert_not_called()


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
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.mock_accrue = self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

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
    integration-test consent flows: CharacterSheet → primary_persona + wired account.
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

        # The social_engagement category is seeded by world/progression/seeds.py
        # (via tools/build_schema.py), which the SQLite fast tier skips (#855).
        # Create it so kudos award doesn't crash.
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
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.mock_accrue = self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

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
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.mock_accrue = self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

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


class TestEffortAndFatigueOnTargetedResolution(TestCase):
    """Targeted social-action resolution charges initiator effort + fatigue (Task A3)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from actions.factories import ActionTemplateFactory

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        # social_fatigue_cost=1 → HIGH effort multiplier 2.0 → 2 fatigue charged
        cls.action_template = ActionTemplateFactory(social_fatigue_cost=1)

    def setUp(self) -> None:
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.mock_accrue = self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    def _make_request(self, effort_level: str = "high") -> "SceneActionRequest":
        from world.scenes.action_models import SceneActionRequest

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="intimidate",
            effort_level=effort_level,
            status=ActionRequestStatus.PENDING,
        )
        SceneActionRequest.objects.filter(pk=request.pk).update(
            action_template=self.action_template
        )
        request.action_template = self.action_template
        return request

    @patch("world.scenes.action_services.start_action_resolution")
    def test_effort_charges_initiator_social_fatigue(self, mock_resolve: MagicMock) -> None:
        """HIGH-effort accept should increase the initiator's social_current fatigue."""
        from world.fatigue.services import get_or_create_fatigue_pool

        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request(effort_level="high")

        pool_before = get_or_create_fatigue_pool(self.initiator.character_sheet).get_current(
            "social"
        )

        respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        pool_after = get_or_create_fatigue_pool(self.initiator.character_sheet).get_current(
            "social"
        )
        self.assertGreater(pool_after, pool_before)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_difficulty_override_none_falls_back_to_normal(self, mock_resolve: MagicMock) -> None:
        """When difficulty_override=None, difficulty should match NORMAL default."""
        from world.scenes.action_services import _resolve_action_against_persona

        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request(effort_level="medium")

        _result, _interaction, difficulty = _resolve_action_against_persona(
            request, self.target, difficulty_override=None
        )
        self.assertEqual(difficulty, DIFFICULTY_VALUES[DifficultyChoice.NORMAL])

    @patch("world.scenes.action_services.start_action_resolution")
    def test_social_fatigue_penalty_applied_to_check_roll(self, mock_resolve: MagicMock) -> None:
        """#2241: accumulated social fatigue penalizes the initiator's check roll."""
        from world.fatigue.services import get_or_create_fatigue_pool
        from world.scenes.action_services import _resolve_action_against_persona

        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request(effort_level="medium")

        # Accumulate enough social fatigue to enter a penalized zone.
        # We add a large amount directly to guarantee we're past TIRED.
        sheet = self.initiator.character_sheet
        pool = get_or_create_fatigue_pool(sheet)
        pool.social_current = 1000
        pool.save(update_fields=["social_current"])

        _resolve_action_against_persona(request, self.target, difficulty_override=None)

        # The mock's call kwargs should include extra_modifiers with a negative
        # fatigue penalty folded in. EFFORT_CHECK_MODIFIER[MEDIUM] = 0, so the
        # only non-zero contribution to check_modifiers is the fatigue penalty.
        call_kwargs = mock_resolve.call_args.kwargs
        extra_modifiers = call_kwargs.get("extra_modifiers", 0)
        # The fatigue penalty is negative (−2 for TIRED, −3 for OVEREXERTED, etc.).
        self.assertLess(extra_modifiers, 0)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_no_fatigue_penalty_when_fresh(self, mock_resolve: MagicMock) -> None:
        """#2241: FRESH fatigue zone → zero penalty, check_modifiers unaffected."""
        from world.fatigue.services import get_or_create_fatigue_pool
        from world.scenes.action_services import _resolve_action_against_persona

        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request(effort_level="medium")

        # Ensure the pool exists and is at 0 (FRESH).
        pool = get_or_create_fatigue_pool(self.initiator.character_sheet)
        pool.social_current = 0
        pool.save(update_fields=["social_current"])

        _resolve_action_against_persona(request, self.target, difficulty_override=None)

        # MEDIUM effort modifier = 0, FRESH fatigue penalty = 0, so extra_modifiers
        # should be 0 (plus any breakdown contributions, which are 0 for a bare
        # test character with no conditions/modifiers).
        call_kwargs = mock_resolve.call_args.kwargs
        extra_modifiers = call_kwargs.get("extra_modifiers", 0)
        # Allow for breakdown.total being 0 in a bare test setup.
        self.assertEqual(extra_modifiers, 0)


class TestDefenderSetsPlausibilityBandAtConsent(TestCase):
    """Task 4 (A4): defender supplies difficulty at consent; diverges per-target.

    One cast, two targets (primary + one SceneActionTarget).  Primary accepts
    with difficulty="easy"; additional accepts with difficulty="daunting".
    Asserts that resolved_difficulty diverges per-target and that
    resist_effort_level is persisted when provided.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.primary_target = PersonaFactory()
        cls.additional_target = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

    def setUp(self) -> None:
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    def _make_request(self) -> "SceneActionRequest":
        from world.scenes.action_models import SceneActionRequest

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.primary_target,
            action_key="intimidate",
            status=ActionRequestStatus.PENDING,
        )
        SceneActionRequest.objects.filter(pk=request.pk).update(
            action_template=self.action_template
        )
        request.action_template = self.action_template
        return request

    @patch("world.scenes.action_services.start_action_resolution")
    def test_primary_accepts_with_easy_difficulty(self, mock_resolve: MagicMock) -> None:
        """Primary target accepts with difficulty='easy'; resolved_difficulty == EASY."""
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.EASY,
        )

        request.refresh_from_db()
        self.assertEqual(request.resolved_difficulty, DIFFICULTY_VALUES[DifficultyChoice.EASY])

    @patch("world.scenes.action_services.start_action_resolution")
    def test_additional_accepts_with_daunting_difficulty(self, mock_resolve: MagicMock) -> None:
        """Additional target accepts with difficulty='daunting'; resolved_difficulty == DAUNTING."""
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()
        row = SceneActionTargetFactory(
            action_request=request,
            target_persona=self.additional_target,
        )

        respond_to_action_target(
            action_target=row,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.DAUNTING,
        )

        row.refresh_from_db()
        self.assertEqual(row.resolved_difficulty, DIFFICULTY_VALUES[DifficultyChoice.DAUNTING])

    @patch("world.scenes.action_services.start_action_resolution")
    def test_divergent_per_target_difficulty(self, mock_resolve: MagicMock) -> None:
        """Primary (easy) and additional (daunting) diverge on resolved_difficulty."""
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()
        row = SceneActionTargetFactory(
            action_request=request,
            target_persona=self.additional_target,
        )

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.EASY,
        )
        respond_to_action_target(
            action_target=row,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.DAUNTING,
        )

        request.refresh_from_db()
        row.refresh_from_db()
        self.assertEqual(request.resolved_difficulty, DIFFICULTY_VALUES[DifficultyChoice.EASY])
        self.assertEqual(row.resolved_difficulty, DIFFICULTY_VALUES[DifficultyChoice.DAUNTING])
        # Sanity: easy (30) != daunting (75)
        self.assertNotEqual(request.resolved_difficulty, row.resolved_difficulty)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_resist_effort_level_persisted_on_primary(self, mock_resolve: MagicMock) -> None:
        """resist_effort_level is persisted on the primary request when provided."""
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
            resist_effort="high",
        )

        request.refresh_from_db()
        self.assertEqual(request.resist_effort_level, "high")

    @patch("world.scenes.action_services.start_action_resolution")
    def test_resist_effort_level_persisted_on_additional_target(
        self, mock_resolve: MagicMock
    ) -> None:
        """resist_effort_level is persisted on the additional target row when provided."""
        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()
        row = SceneActionTargetFactory(
            action_request=request,
            target_persona=self.additional_target,
        )

        respond_to_action_target(
            action_target=row,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
            resist_effort="low",
        )

        row.refresh_from_db()
        self.assertEqual(row.resist_effort_level, "low")


class TestActiveResistanceRaisesDifficultyAndChargesFatigue(TestCase):
    """Task 8 (C3): when a defender spends resist-effort, difficulty rises by the
    Composure increment AND the defender is charged social fatigue.

    Covers both the primary path (respond_to_action_request) and the additional-
    target path (respond_to_action_target).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.checks.factories import create_resistance_check_types
        from world.traits.models import (
            CharacterTraitValue,
            PointConversionRange,
            Trait,
            TraitCategory,
            TraitType,
        )

        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.primary_target = PersonaFactory()
        cls.additional_target = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

        # PointConversionRange needed so _calculate_trait_points converts correctly.
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )

        # Seed Composure CheckType + willpower trait weight.
        create_resistance_check_types()

        willpower_trait, _ = Trait.objects.get_or_create(
            name="willpower",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.GENERAL,
            },
        )

        # Give both defenders a willpower value so compute_resist_increment > 0.
        CharacterTraitValue.objects.create(
            character=cls.primary_target.character_sheet, trait=willpower_trait, value=20
        )
        CharacterTraitValue.objects.create(
            character=cls.additional_target.character_sheet, trait=willpower_trait, value=20
        )

    def setUp(self) -> None:
        from world.checks.models import CheckType
        from world.traits.models import CharacterTraitValue

        CharacterTraitValue.flush_instance_cache()
        CheckType.flush_instance_cache()

        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    def _make_request(self):
        from world.scenes.action_models import SceneActionRequest

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.primary_target,
            action_key="intimidate",
            status=ActionRequestStatus.PENDING,
        )
        SceneActionRequest.objects.filter(pk=request.pk).update(
            action_template=self.action_template
        )
        request.action_template = self.action_template
        return request

    @patch("world.scenes.action_services.start_action_resolution")
    def test_primary_resist_raises_difficulty_and_charges_fatigue(
        self, mock_resolve: MagicMock
    ) -> None:
        """Primary target with resist_effort='high' → difficulty = base + increment;
        defender's social_current > 0 (fatigue charged)."""
        from world.checks.services import compute_resist_increment
        from world.fatigue.services import get_or_create_fatigue_pool

        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()

        base = DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
        defender_character = self.primary_target.character_sheet.character
        expected_increment = compute_resist_increment(defender_character, "high")
        assert expected_increment > 0, "Test precondition: increment must be > 0"

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
            resist_effort="high",
        )

        request.refresh_from_db()
        self.assertEqual(request.resolved_difficulty, base + expected_increment)

        pool = get_or_create_fatigue_pool(self.primary_target.character_sheet)
        self.assertGreater(pool.social_current, 0)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_primary_no_resist_uses_base_difficulty_no_fatigue(
        self, mock_resolve: MagicMock
    ) -> None:
        """Primary target with no resist_effort → resolved_difficulty == base,
        defender social fatigue unchanged."""
        from world.fatigue.services import get_or_create_fatigue_pool

        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()

        # Ensure pool exists with 0 to have a clean baseline.
        pool_before = get_or_create_fatigue_pool(self.primary_target.character_sheet)
        social_before = pool_before.social_current

        base = DIFFICULTY_VALUES[DifficultyChoice.NORMAL]

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
        )

        request.refresh_from_db()
        self.assertEqual(request.resolved_difficulty, base)

        pool_before.refresh_from_db()
        self.assertEqual(pool_before.social_current, social_before)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_additional_target_resist_raises_difficulty_and_charges_fatigue(
        self, mock_resolve: MagicMock
    ) -> None:
        """Additional target with resist_effort='high' → difficulty = base + increment;
        defender's social_current > 0 (fatigue charged)."""
        from world.checks.services import compute_resist_increment
        from world.fatigue.services import get_or_create_fatigue_pool

        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()
        row = SceneActionTargetFactory(
            action_request=request,
            target_persona=self.additional_target,
        )

        # Also accept the primary to not block the test object state.
        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
        )
        row.refresh_from_db()

        base = DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
        defender_character = self.additional_target.character_sheet.character
        expected_increment = compute_resist_increment(defender_character, "high")
        assert expected_increment > 0, "Test precondition: increment must be > 0"

        respond_to_action_target(
            action_target=row,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
            resist_effort="high",
        )

        row.refresh_from_db()
        self.assertEqual(row.resolved_difficulty, base + expected_increment)

        pool = get_or_create_fatigue_pool(self.additional_target.character_sheet)
        self.assertGreater(pool.social_current, 0)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_additional_target_no_resist_uses_base_difficulty_no_fatigue(
        self, mock_resolve: MagicMock
    ) -> None:
        """Additional target with no resist_effort → resolved_difficulty == base,
        defender social fatigue unchanged."""
        from world.fatigue.services import get_or_create_fatigue_pool

        mock_resolve.return_value = _make_pending_resolution(success=True)
        request = self._make_request()
        row = SceneActionTargetFactory(
            action_request=request,
            target_persona=self.additional_target,
        )

        # Accept primary first.
        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
        )
        row.refresh_from_db()

        pool_before = get_or_create_fatigue_pool(self.additional_target.character_sheet)
        social_before = pool_before.social_current

        base = DIFFICULTY_VALUES[DifficultyChoice.NORMAL]

        respond_to_action_target(
            action_target=row,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
        )

        row.refresh_from_db()
        self.assertEqual(row.resolved_difficulty, base)

        pool_before.refresh_from_db()
        self.assertEqual(pool_before.social_current, social_before)


class TestGradedAccrualOnAccept(TestCase):
    """Task 12 (B3): accepting accrues graded good-sport credit, not instant kudos.

    Verifies:
    - Others-initiated accept → pending_points increases by default_amount * weight_for(band).
    - KudosPointsData.total_earned is NOT changed (no instant grant).
    - Self-initiated accept (initiator account == target account) → no accrual.
    - Both primary path (respond_to_action_request) and additional-target path
      (respond_to_action_target) are covered.

    Uses setUp (not setUpTestData) for fresh per-test DB state to avoid idmapper
    contamination between parallel sessions and cross-test cache leakage.
    """

    def setUp(self) -> None:
        from world.progression.models import KudosDifficultyWeight

        self.scene = SceneFactory()
        self.action_template = ActionTemplateFactory()

        # Seed difficulty weights (idempotent get_or_create).
        seed_kudos_difficulty_weights()

        # Seed social_engagement category — world/progression/seeds.py (via
        # tools/build_schema.py) is skipped on the SQLite fast tier.
        KudosSourceCategory.objects.get_or_create(
            name="social_engagement",
            defaults={
                "display_name": "Social Engagement",
                "description": "Seeded for tests on the no-migrations fast tier.",
                "default_amount": 1,
            },
        )

        # Reset memoized social engagement category so each test re-fetches it.
        action_services._SOCIAL_ENGAGEMENT_CATEGORY = None
        self.addCleanup(setattr, action_services, "_SOCIAL_ENGAGEMENT_CATEGORY", None)

        # Build initiator (PC) and target (PC) — both with real accounts.
        self.initiator_account = AccountFactory()
        initiator_character = CharacterFactory()
        initiator_sheet = CharacterSheetFactory(character=initiator_character)
        self.initiator_persona = initiator_sheet.primary_persona
        initiator_character.db_account = self.initiator_account
        initiator_character.save(update_fields=["db_account"])

        self.target_account = AccountFactory()
        target_character = CharacterFactory()
        target_sheet = CharacterSheetFactory(character=target_character)
        self.target_persona = target_sheet.primary_persona
        target_character.db_account = self.target_account
        target_character.save(update_fields=["db_account"])

        # A separate additional-target PC.
        self.additional_account = AccountFactory()
        additional_character = CharacterFactory()
        additional_sheet = CharacterSheetFactory(character=additional_character)
        self.additional_persona = additional_sheet.primary_persona
        additional_character.db_account = self.additional_account
        additional_character.save(update_fields=["db_account"])

        self.normal_weight = KudosDifficultyWeight.weight_for(DifficultyChoice.NORMAL)
        self.easy_weight = KudosDifficultyWeight.weight_for(DifficultyChoice.EASY)

    def _make_primary_request(self, band: str = DifficultyChoice.NORMAL) -> "SceneActionRequest":
        """Create a pending SceneActionRequest with initiator→target, template set."""
        from world.scenes.action_models import SceneActionRequest

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="intimidate",
            status=ActionRequestStatus.PENDING,
            difficulty_choice=band,
        )
        SceneActionRequest.objects.filter(pk=request.pk).update(
            action_template=self.action_template
        )
        request.action_template = self.action_template
        return request

    @patch("world.scenes.action_services.start_action_resolution")
    def test_others_initiated_primary_accept_accrues_pending_points(
        self, mock_resolve: MagicMock
    ) -> None:
        """Accepting a primary request (initiator ≠ target) accrues pending_points."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = self._make_primary_request(band=DifficultyChoice.NORMAL)

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
        )

        ledger = WeeklySocialEngagement.objects.get(account=self.target_account)
        expected = Decimal(1) * self.normal_weight  # default_amount=1
        self.assertEqual(ledger.pending_points, expected)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_others_initiated_primary_accept_does_not_instantly_grant_kudos(
        self, mock_resolve: MagicMock
    ) -> None:
        """Accepting a primary request does NOT increase KudosPointsData.total_earned."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = self._make_primary_request(band=DifficultyChoice.NORMAL)

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
        )

        # KudosPointsData should not be created (or remain at 0 if pre-existing).
        data = KudosPointsData.objects.filter(account=self.target_account).first()
        if data is not None:
            self.assertEqual(data.total_earned, 0)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_self_initiated_primary_accept_accrues_nothing(self, mock_resolve: MagicMock) -> None:
        """Self-targeted action (initiator == target account) accrues nothing."""
        from world.scenes.action_models import SceneActionRequest

        mock_resolve.return_value = _make_pending_resolution(success=True)

        # Build a persona where initiator and target share the SAME account.
        same_account = AccountFactory()
        self_character = CharacterFactory()
        self_sheet = CharacterSheetFactory(character=self_character)
        self_persona = self_sheet.primary_persona
        self_character.db_account = same_account
        self_character.save(update_fields=["db_account"])

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self_persona,
            target_persona=self_persona,  # same persona → same account
            action_key="intimidate",
            status=ActionRequestStatus.PENDING,
            difficulty_choice=DifficultyChoice.NORMAL,
        )
        SceneActionRequest.objects.filter(pk=request.pk).update(
            action_template=self.action_template
        )
        request.action_template = self.action_template

        respond_to_action_request(
            action_request=request,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.NORMAL,
        )

        # No ledger should exist for the self-targeting account.
        self.assertFalse(WeeklySocialEngagement.objects.filter(account=same_account).exists())

    @patch("world.scenes.action_services.start_action_resolution")
    def test_others_initiated_additional_target_accept_accrues_pending_points(
        self, mock_resolve: MagicMock
    ) -> None:
        """Accepting an additional-target row (initiator ≠ additional target) accrues points."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = self._make_primary_request(band=DifficultyChoice.EASY)
        row = SceneActionTargetFactory(
            action_request=request,
            target_persona=self.additional_persona,
            difficulty_choice=DifficultyChoice.EASY,
        )

        respond_to_action_target(
            action_target=row,
            decision=ConsentDecision.ACCEPT,
            difficulty=DifficultyChoice.EASY,
        )

        ledger = WeeklySocialEngagement.objects.get(account=self.additional_account)
        expected = Decimal(1) * self.easy_weight
        self.assertEqual(ledger.pending_points, expected)


class TestNPCAndAreaFallbackDifficulty(TestCase):
    """Task 14 (X1): NPC/area difficulty-fallback regression.

    Proves that when there is NO consenting player:
    1. An NPC additional target auto-resolves at the authored difficulty_choice
       default (NORMAL == 45) — never an initiator pick.
    2. An area action resolves at the difficulty_choice passed to
       create_and_resolve_area_action (HARD == 60), unaffected by consent rework.

    Neither path calls respond_to_action_request / respond_to_action_target.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        # NPC additional target: PersonaFactory leaves db_account as None by default.
        cls.npc_persona = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

        # The social_engagement category is seeded by world/progression/seeds.py
        # (via tools/build_schema.py), which the SQLite fast tier skips (#855);
        # get_or_create so the fast tier gets the row.
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
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    @patch("world.scenes.action_services.start_action_resolution")
    def test_npc_additional_target_auto_resolves_at_normal_difficulty(
        self, mock_resolve: MagicMock
    ) -> None:
        """NPC additional target auto-resolves at NORMAL (45) — the authored default.

        No defender call is needed or made; difficulty_choice defaults to NORMAL and
        _auto_resolve_npc_targets accepts on the NPC's behalf with no override.
        """
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=None,
            action_key="intimidate",
            action_template=self.action_template,
            status=ActionRequestStatus.PENDING,
        )
        SceneActionTarget.objects.create(action_request=request, target_persona=self.npc_persona)
        _auto_resolve_npc_targets(request)

        npc_row = SceneActionTarget.objects.get(
            action_request=request, target_persona=self.npc_persona
        )
        self.assertEqual(
            npc_row.status,
            ActionRequestStatus.RESOLVED,
            "NPC target must be auto-resolved at dispatch without any defender call",
        )
        self.assertEqual(
            npc_row.resolved_difficulty,
            DIFFICULTY_VALUES[DifficultyChoice.NORMAL],
            "NPC auto-resolve must use the authored NORMAL default (45), not an initiator pick",
        )

    @patch("world.scenes.action_services.start_action_resolution")
    def test_area_action_resolves_at_authored_difficulty_choice(
        self, mock_resolve: MagicMock
    ) -> None:
        """Area action (no target, no consent) resolves at the passed difficulty_choice.

        Using HARD (60) to prove the authored-difficulty param is honoured and is
        unaffected by the effort/difficulty consent-rework (there is no defender).
        """
        from world.scenes.action_services import create_and_resolve_area_action

        mock_resolve.return_value = _make_pending_resolution(success=True)

        create_and_resolve_area_action(
            scene=self.scene,
            initiator_persona=self.initiator,
            action_template=self.action_template,
            action_key="tell_tale",
            difficulty_choice=DifficultyChoice.HARD,
        )

        from world.scenes.action_models import SceneActionRequest

        area_request = SceneActionRequest.objects.filter(
            scene=self.scene,
            initiator_persona=self.initiator,
            action_key="tell_tale",
        ).latest("pk")

        self.assertEqual(area_request.status, ActionRequestStatus.RESOLVED)
        self.assertEqual(
            area_request.resolved_difficulty,
            DIFFICULTY_VALUES[DifficultyChoice.HARD],
            "Area action must resolve at the authored HARD difficulty (60), not NORMAL",
        )


class TestSingleTargetNPCAutoResolve(TestCase):
    """#2214: a single-target (no additional_target_personas) NPC-primary request
    auto-resolves at create_action_request time, mirroring the existing multi-target
    NPC behavior (#572) instead of staying PENDING forever.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        # NPC primary: PersonaFactory leaves db_account None by default.
        cls.npc_persona = PersonaFactory()
        cls.action_template = ActionTemplateFactory(name="Intimidate")

        KudosSourceCategory.objects.get_or_create(
            name="social_engagement",
            defaults={
                "display_name": "Social Engagement",
                "description": "Seeded for tests on the no-migrations fast tier.",
                "default_amount": 1,
            },
        )

    def setUp(self) -> None:
        action_services._SOCIAL_ENGAGEMENT_CATEGORY = None
        self.addCleanup(setattr, action_services, "_SOCIAL_ENGAGEMENT_CATEGORY", None)
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    @patch("world.scenes.action_services.start_action_resolution")
    def test_single_target_npc_primary_resolves_at_create(self, mock_resolve: MagicMock) -> None:
        """A lone NPC target_persona (no additional targets) is RESOLVED, not PENDING."""
        mock_resolve.return_value = _make_pending_resolution(success=True)

        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.npc_persona,
            action_key="intimidate",
        )

        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(request._auto_resolve_result)
        self.assertEqual(request._auto_resolve_result.action_key, "intimidate")

    def test_unresolvable_single_target_stays_pending(self) -> None:
        """No ActionTemplate, no custom resolver, not a standalone cast -> stays PENDING.

        Guards the fixture/data-gap case from crashing (ValueError) instead of resolving.
        """
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.npc_persona,
            action_key="totally_unregistered_key",
        )
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.PENDING)
        self.assertIsNone(request._auto_resolve_result)


class SocialModifierSeamTests(TestCase):
    """The social/scene action path funnels its check through ``collect_check_modifiers`` (#1696).

    Combat / challenge / vitals already honor the modifier seam; the social path did not, so no
    condition / rollmod / scene / equipment / CHARACTER / fashion (and, once scoped, allure)
    modifier reached a social check. These tests pin the wiring: the initiator's breakdown total
    is folded into ``extra_modifiers`` for plain (non-technique) actions, scene-scoped.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.action_template = ActionTemplateFactory()

    def setUp(self) -> None:
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    def _make_request(self) -> "SceneActionTarget":
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
        return SceneActionTargetFactory(action_request=request)

    @patch("world.checks.services.collect_check_modifiers")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_breakdown_total_folded_into_extra_modifiers(
        self, mock_resolve: MagicMock, mock_collect: MagicMock
    ) -> None:
        from world.fatigue.constants import EFFORT_CHECK_MODIFIER

        mock_resolve.return_value = _make_pending_resolution(success=True)
        mock_collect.return_value = SimpleNamespace(total=7)

        row = self._make_request()
        request = row.action_request
        respond_to_action_target(action_target=row, decision=ConsentDecision.ACCEPT)

        # collect_check_modifiers is asked for the initiator's sheet + the action's check type,
        # scene-scoped so the perception-relative fashion bonus can resolve. No gating
        # relationship exists here, so extra_contributions is empty (#1696).
        mock_collect.assert_called_once_with(
            request.initiator_persona.character_sheet,
            request.action_template.check_type,
            scene=request.scene,
            extra_contributions=[],
        )
        expected = EFFORT_CHECK_MODIFIER.get(request.effort_level, 0) + 7
        self.assertEqual(mock_resolve.call_args.kwargs["extra_modifiers"], expected)

    @patch("world.checks.services.collect_check_modifiers")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_target_attraction_folds_initiator_allure_as_contribution(
        self, mock_resolve: MagicMock, mock_collect: MagicMock
    ) -> None:
        """When the TARGET is Attracted to the initiator, the allure rides along (#1696)."""
        from world.checks.constants import ModifierSourceKind
        from world.mechanics.factories import CharacterModifierFactory
        from world.relationships.factories import (
            CharacterRelationshipFactory,
            RelationshipConditionFactory,
        )

        mock_resolve.return_value = _make_pending_resolution(success=True)
        mock_collect.return_value = SimpleNamespace(total=0)

        row = self._make_request()
        request = row.action_request
        initiator_sheet = request.initiator_persona.character_sheet
        target_sheet = row.target_persona.character_sheet

        # Initiator carries an allure modifier; the TARGET is Attracted To the initiator.
        modifier = CharacterModifierFactory(character=initiator_sheet, value=10)
        condition = RelationshipConditionFactory(name="Attracted To")
        condition.gates_modifiers.add(modifier.target)
        rel = CharacterRelationshipFactory(
            source=target_sheet, target=initiator_sheet, is_active=True
        )
        rel.conditions.add(condition)

        respond_to_action_target(action_target=row, decision=ConsentDecision.ACCEPT)

        contributions = mock_collect.call_args.kwargs["extra_contributions"]
        self.assertEqual(len(contributions), 1)
        self.assertEqual(contributions[0].value, 10)
        self.assertEqual(contributions[0].source_kind, ModifierSourceKind.RELATIONSHIP)
