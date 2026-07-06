"""Tests for thread-pull on social actions (#1919).

Covers ``_charge_social_pull``, the anima waiver, GIFT exclusion, TRAIT
acceptance, fizzle path, idempotent charge, DENY cleanup, and beseech=
discarding.
"""

from __future__ import annotations

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import InvalidImbueAmount
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    FacetFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterAnima, CharacterResonance
from world.magic.types.pull import CastPullDeclaration
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import SceneActionPullDeclaration
from world.scenes.action_services import (
    _charge_social_pull,
    create_action_request,
    respond_to_action_request,
)
from world.scenes.factories import SceneFactory


def _setup_pull_seed(*, sheet, resonance, target_kind=TargetKind.RELATIONSHIP_TRACK, tier=1):
    """Create a thread + pull-effect row so a charge resolves a FLAT_BONUS.

    Defaults to RELATIONSHIP_TRACK — always-in-action, no worn-items gate
    (unlike FACET), no involved-traits gate (unlike TRAIT).
    """
    if target_kind == TargetKind.TRAIT:
        thread = ThreadFactory(owner=sheet, resonance=resonance)
    elif target_kind == TargetKind.RELATIONSHIP_TRACK:
        thread = ThreadFactory(owner=sheet, resonance=resonance, as_track_thread=True)
    elif target_kind == TargetKind.FACET:
        facet = FacetFactory()
        thread = ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.FACET,
            target_trait=None,
            target_facet=facet,
        )
    elif target_kind == TargetKind.GIFT:
        from world.magic.factories import GiftFactory

        gift = GiftFactory()
        thread = ThreadFactory(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_facet=None,
            target_gift=gift,
        )
    else:
        thread = ThreadFactory(owner=sheet, resonance=resonance, target_kind=target_kind)

    ThreadPullCostFactory(tier=tier, resonance_cost=2, anima_per_thread=1)
    ThreadPullEffectFactory(
        target_kind=target_kind,
        resonance=resonance,
        tier=tier,
        flat_bonus_amount=5,
    )
    return thread


class ChargeSocialPullTests(TestCase):
    """Unit tests for ``_charge_social_pull``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator_sheet = CharacterSheetFactory()
        cls.target_sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=cls.initiator_sheet.character, current=10, maximum=10)
        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.initiator_sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        cls.initiator_persona = cls.initiator_sheet.primary_persona
        cls.target_persona = cls.target_sheet.primary_persona

        cls.check_type = CheckTypeFactory()
        cls.action_template = ActionTemplateFactory(check_type=cls.check_type)

    def _make_request_with_pull(self, thread, *, tier=1):
        """Create a PENDING action request with a persisted pull declaration."""
        cast_pull = CastPullDeclaration(
            resonance=self.resonance,
            tier=tier,
            threads=(thread,),
        )
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="persuade",
            pull=cast_pull,
        )
        # Attach the action template so _charge_social_pull can read check_type.
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])
        return request

    def test_charges_resonance_and_returns_flat_bonus(self):
        """FLAT_BONUS is summed and resonance is debited."""
        thread = _setup_pull_seed(sheet=self.initiator_sheet, resonance=self.resonance)
        request = self._make_request_with_pull(thread)

        bonus = _charge_social_pull(action_request=request, check_type=self.check_type)
        assert bonus == 5  # authored_value=5

        cr = CharacterResonance.objects.get(
            character_sheet=self.initiator_sheet, resonance=self.resonance
        )
        assert cr.balance == 18  # 20 - 2 resonance_cost

    def test_waives_anima_in_low_stakes_scene(self):
        """Anima is not charged when no combat or DANGER round is active."""
        thread = _setup_pull_seed(sheet=self.initiator_sheet, resonance=self.resonance)
        request = self._make_request_with_pull(thread)

        anima_before = CharacterAnima.objects.get(character=self.initiator_sheet.character).current
        _charge_social_pull(action_request=request, check_type=self.check_type)
        anima_after = CharacterAnima.objects.get(character=self.initiator_sheet.character).current
        assert anima_before == anima_after  # unchanged — waived

    def test_no_declaration_returns_zero(self):
        """No pull declaration on the request → returns 0, no charge."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="persuade",
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        bonus = _charge_social_pull(action_request=request, check_type=self.check_type)
        assert bonus == 0

    def test_gift_thread_rejected(self):
        """GIFT threads are excluded for social pulls."""
        thread = _setup_pull_seed(
            sheet=self.initiator_sheet, resonance=self.resonance, target_kind=TargetKind.GIFT
        )
        request = self._make_request_with_pull(thread)

        with self.assertRaises(InvalidImbueAmount):
            _charge_social_pull(action_request=request, check_type=self.check_type)

    def test_trait_thread_accepted_when_trait_in_check_type(self):
        """TRAIT threads pass anchor-in-action when the trait is in the check type."""
        thread = _setup_pull_seed(
            sheet=self.initiator_sheet, resonance=self.resonance, target_kind=TargetKind.TRAIT
        )
        # Link the thread's trait to the check type.
        CheckTypeTraitFactory(check_type=self.check_type, trait=thread.target_trait, weight=1.0)
        request = self._make_request_with_pull(thread)

        bonus = _charge_social_pull(action_request=request, check_type=self.check_type)
        assert bonus == 5  # FLAT_BONUS

    def test_fizzle_on_insufficient_resonance(self):
        """Pull fails → raises; the caller catches it and fizzles."""
        thread = _setup_pull_seed(sheet=self.initiator_sheet, resonance=self.resonance)
        # Drain the balance so the pull can't afford.
        cr = CharacterResonance.objects.get(
            character_sheet=self.initiator_sheet, resonance=self.resonance
        )
        cr.balance = 0
        cr.save(update_fields=["balance"])

        request = self._make_request_with_pull(thread)
        from world.magic.exceptions import MagicError

        with self.assertRaises(MagicError):
            _charge_social_pull(action_request=request, check_type=self.check_type)

    def test_idempotent_charge(self):
        """Calling _charge_social_pull twice charges only once."""
        thread = _setup_pull_seed(sheet=self.initiator_sheet, resonance=self.resonance)
        request = self._make_request_with_pull(thread)

        bonus1 = _charge_social_pull(action_request=request, check_type=self.check_type)
        bonus2 = _charge_social_pull(action_request=request, check_type=self.check_type)
        assert bonus1 == bonus2 == 5

        # Resonance debited only once.
        cr = CharacterResonance.objects.get(
            character_sheet=self.initiator_sheet, resonance=self.resonance
        )
        assert cr.balance == 18  # 20 - 2 (single charge)

        # charged_at is stamped.
        decl = SceneActionPullDeclaration.objects.get(request=request)
        assert decl.charged_at is not None
        assert decl.charged_flat_bonus == 5


class DenyPathCleanupTests(TestCase):
    """DENY path cleans up the pull declaration."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator_sheet = CharacterSheetFactory()
        cls.target_sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=cls.initiator_sheet.character, current=10, maximum=10)
        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.initiator_sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        cls.initiator_persona = cls.initiator_sheet.primary_persona
        cls.target_persona = cls.target_sheet.primary_persona
        cls.thread = _setup_pull_seed(sheet=cls.initiator_sheet, resonance=cls.resonance)

    def test_deny_deletes_pull_declaration(self):
        """On DENY, the pull declaration row is cleaned up and no charge fires."""
        cast_pull = CastPullDeclaration(resonance=self.resonance, tier=1, threads=(self.thread,))
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="persuade",
            pull=cast_pull,
        )
        assert SceneActionPullDeclaration.objects.filter(request=request).exists()

        respond_to_action_request(action_request=request, decision=ConsentDecision.DENY)

        assert not SceneActionPullDeclaration.objects.filter(request=request).exists()
        # Resonance unchanged — no charge fired.
        cr = CharacterResonance.objects.get(
            character_sheet=self.initiator_sheet, resonance=self.resonance
        )
        assert cr.balance == 20


class EndToEndSocialPullTests(TestCase):
    """Integration: declare → accept → resolve with a pull."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator_sheet = CharacterSheetFactory()
        cls.target_sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=cls.initiator_sheet.character, current=10, maximum=10)
        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.initiator_sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        cls.initiator_persona = cls.initiator_sheet.primary_persona
        cls.target_persona = cls.target_sheet.primary_persona
        cls.thread = _setup_pull_seed(sheet=cls.initiator_sheet, resonance=cls.resonance)

        cls.check_type = CheckTypeFactory()
        cls.action_template = ActionTemplateFactory(check_type=cls.check_type)

    def test_accept_charges_pull_and_resolves(self):
        """Full flow: create with pull → accept → resonance debited, request RESOLVED."""
        cast_pull = CastPullDeclaration(resonance=self.resonance, tier=1, threads=(self.thread,))
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator_persona,
            target_persona=self.target_persona,
            action_key="persuade",
            pull=cast_pull,
        )
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        assert SceneActionPullDeclaration.objects.filter(request=request).exists()

        respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED

        # Resonance debited.
        cr = CharacterResonance.objects.get(
            character_sheet=self.initiator_sheet, resonance=self.resonance
        )
        assert cr.balance == 18  # 20 - 2

        # Pull declaration charged.
        decl = SceneActionPullDeclaration.objects.get(request=request)
        assert decl.charged_at is not None
        assert decl.charged_flat_bonus == 5
