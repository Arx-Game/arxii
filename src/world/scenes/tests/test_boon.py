"""Boon slice 2 (#2540): ask validation, NPC cost band, resolver fulfillment, affection.

The E2E class drives the real consent pipeline (``create_action_request`` →
NPC auto-accept → the registered ``boon`` resolver) with only the check roll mocked,
mirroring ``test_action_services``' pattern.
"""

from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import AccountFactory
from world.currency.services import get_or_create_purse
from world.relationships.models import AffectionShift
from world.scenes.action_constants import BoonKind, BoonSumTier
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_services import create_action_request
from world.scenes.boon_models import Boon
from world.scenes.boon_services import (
    BOON_AFFECTION_COST,
    BoonAsk,
    boon_sum_values,
    fulfill_boon,
    npc_boon_tier_shift,
)
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory


def _fund(sheet, amount: int) -> None:
    purse = get_or_create_purse(sheet)
    purse.balance = amount
    purse.save(update_fields=["balance"])


def _balance(sheet) -> int:
    purse = get_or_create_purse(sheet)
    purse.refresh_from_db()
    return purse.balance


def _pilot(persona) -> None:
    """Attach an account so the persona reads as a PC."""
    character = persona.character_sheet.character
    character.db_account = AccountFactory()
    character.save(update_fields=["db_account"])


def _success_resolution(success: bool = True) -> PendingActionResolution:
    check_result = MagicMock()
    check_result.success_level = 1 if success else -1
    check_result.outcome_name = "Success" if success else "Failure"
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=StepResult(step_label="main", check_result=check_result, consequence_id=None),
    )


class FulfillBoonTests(TestCase):
    def setUp(self) -> None:
        self.request = SceneActionRequestFactory()
        self.asker_sheet = self.request.initiator_persona.character_sheet
        self.target_sheet = self.request.target_persona.character_sheet

    def test_money_boon_moves_coppers_target_to_asker(self) -> None:
        _fund(self.target_sheet, 500)
        boon = Boon.objects.create(action_request=self.request, kind=BoonKind.MONEY, amount=200)
        self.assertTrue(fulfill_boon(boon))
        self.assertEqual(_balance(self.target_sheet), 300)
        self.assertEqual(_balance(self.asker_sheet), 200)
        boon.refresh_from_db()
        self.assertIsNotNone(boon.fulfilled_at)

    def test_fulfillment_is_idempotent(self) -> None:
        _fund(self.target_sheet, 500)
        boon = Boon.objects.create(action_request=self.request, kind=BoonKind.MONEY, amount=200)
        self.assertTrue(fulfill_boon(boon))  # this call fulfilled it
        self.assertFalse(fulfill_boon(boon))  # second call is a no-op
        self.assertEqual(_balance(self.asker_sheet), 200)  # not doubled

    def test_deed_boon_fulfills_without_moving_value(self) -> None:
        boon = Boon.objects.create(
            action_request=self.request, kind=BoonKind.DEED, deed_text="Guard the gate"
        )
        self.assertTrue(fulfill_boon(boon))  # newly fulfilled (RP-only)
        self.assertEqual(_balance(self.asker_sheet), 0)  # nothing moved
        boon.refresh_from_db()
        self.assertIsNotNone(boon.fulfilled_at)

    def test_targetless_request_is_rejected(self) -> None:
        request = SceneActionRequestFactory(target_persona=None)
        boon = Boon.objects.create(action_request=request, kind=BoonKind.MONEY, amount=100)
        with self.assertRaises(ValidationError):
            fulfill_boon(boon)
        boon.refresh_from_db()
        self.assertIsNone(boon.fulfilled_at)  # never claimed as fulfilled


class BoonAskValidationTests(TestCase):
    """Dial 1 — ask-time eligibility: ineligible asks never create a request."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.asker = PersonaFactory()
        cls.target = PersonaFactory()

    def _ask(self, **kwargs) -> SceneActionRequest:
        return create_action_request(
            scene=self.scene,
            initiator_persona=self.asker,
            target_persona=self.target,
            action_key="boon",
            boon=BoonAsk(**kwargs),
        )

    def test_penniless_target_presents_no_money_option(self) -> None:
        # #2540 ruling: impossible asks never exist — and no orphan request either.
        with self.assertRaises(ValidationError):
            self._ask(kind=BoonKind.MONEY, sum_tier=BoonSumTier.FAIR)
        self.assertFalse(SceneActionRequest.objects.exists())  # no orphan row
        self.assertEqual(boon_sum_values(self.target.character_sheet), {})  # UI hides it

    def test_money_ask_names_a_tier_never_a_raw_amount(self) -> None:
        _fund(self.target.character_sheet, 500)
        with self.assertRaises(ValidationError):
            self._ask(kind=BoonKind.MONEY, sum_tier="")  # no tier → no ask

    def test_sum_tier_freezes_concrete_coppers_at_ask_time(self) -> None:
        _fund(self.target.character_sheet, 500)
        request = self._ask(kind=BoonKind.MONEY, sum_tier=BoonSumTier.FAIR)
        self.assertEqual(request.boon.sum_tier, BoonSumTier.FAIR)
        self.assertEqual(request.boon.amount, 100)  # 20% of 500, shown pre-consent
        # The display seam the ask UI uses: tier → coppers, relative to THIS target.
        self.assertEqual(
            boon_sum_values(self.target.character_sheet),
            {BoonSumTier.MINOR: 25, BoonSumTier.FAIR: 100, BoonSumTier.GREAT: 250},
        )

    def test_held_item_ask_requires_the_target_to_hold_it(self) -> None:
        with self.assertRaises(ValidationError):
            self._ask(kind=BoonKind.HELD_ITEM, item_instance_id=999999)

    def test_vault_ask_requires_target_withdraw_authority(self) -> None:
        # No vaulted item / no authority — ineligible.
        with self.assertRaises(ValidationError):
            self._ask(kind=BoonKind.VAULT_ITEM, item_instance_id=999999)

    def test_deed_ask_requires_text(self) -> None:
        with self.assertRaises(ValidationError):
            self._ask(kind=BoonKind.DEED, deed_text="  ")

    def test_targetless_boon_ask_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.asker,
                target_persona=None,
                action_key="boon",
                boon=BoonAsk(kind=BoonKind.DEED, deed_text="x"),
            )


class NpcBoonBandTests(TestCase):
    """Dial 2 — the mandatory NPC-side relative-cost band; piloted targets unshifted."""

    def _request_with_money_boon(self, *, sum_tier: str) -> SceneActionRequest:
        request = SceneActionRequestFactory(action_key="boon")
        _fund(request.target_persona.character_sheet, 1000)
        Boon.objects.create(action_request=request, kind=BoonKind.MONEY, sum_tier=sum_tier)
        return request

    def test_minor_sum_adds_no_tiers(self) -> None:
        request = self._request_with_money_boon(sum_tier=BoonSumTier.MINOR)
        self.assertEqual(npc_boon_tier_shift(request), 0)

    def test_fair_sum_adds_a_tier(self) -> None:
        request = self._request_with_money_boon(sum_tier=BoonSumTier.FAIR)
        self.assertEqual(npc_boon_tier_shift(request), 1)

    def test_great_sum_adds_the_top_band(self) -> None:
        request = self._request_with_money_boon(sum_tier=BoonSumTier.GREAT)
        self.assertEqual(npc_boon_tier_shift(request), 2)

    def test_piloted_target_is_never_band_shifted(self) -> None:
        request = self._request_with_money_boon(sum_tier=BoonSumTier.GREAT)
        _pilot(request.target_persona)  # their difficulty choice rules
        self.assertEqual(npc_boon_tier_shift(request), 0)

    def test_non_boon_request_is_unshifted(self) -> None:
        request = SceneActionRequestFactory(action_key="persuade")
        self.assertEqual(npc_boon_tier_shift(request), 0)


class BoonResolverE2ETests(TestCase):
    """The full consent path: dispatch → NPC auto-accept → resolver fulfills + charges."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.seeds.checks import seed_check_resolution_tables
        from world.seeds.relationship_scale import seed_relationship_scale_content
        from world.seeds.social_actions import seed_social_action_content
        from world.seeds.social_checks import seed_social_check_content
        from world.seeds.social_relationships import seed_social_relationship_content

        seed_check_resolution_tables()
        seed_social_check_content()
        seed_social_relationship_content()
        seed_social_action_content()  # seeds the "Boon" ActionTemplate
        seed_relationship_scale_content()  # Regard/Friction system tracks
        cls.scene = SceneFactory()

    def setUp(self) -> None:
        self.asker = PersonaFactory()
        self.npc_target = PersonaFactory()  # no db_account → NPC, auto-accepts
        _fund(self.npc_target.character_sheet, 1000)
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    def _dispatch(self, *, success: bool, sum_tier: str = BoonSumTier.FAIR) -> SceneActionRequest:
        with patch(
            "world.scenes.action_services.start_action_resolution",
            return_value=_success_resolution(success=success),
        ):
            return create_action_request(
                scene=self.scene,
                initiator_persona=self.asker,
                target_persona=self.npc_target,
                action_key="boon",
                boon=BoonAsk(kind=BoonKind.MONEY, sum_tier=sum_tier),
            )

    def test_granted_boon_fulfills_and_charges_affection(self) -> None:
        request = self._dispatch(success=True)  # fair sum of 1000 = 200 coppers
        self.assertEqual(_balance(self.asker.character_sheet), 200)
        self.assertEqual(_balance(self.npc_target.character_sheet), 800)
        request.boon.refresh_from_db()
        self.assertIsNotNone(request.boon.fulfilled_at)
        shift = AffectionShift.objects.get(boon=request.boon)
        self.assertEqual(shift.amount, -BOON_AFFECTION_COST)
        self.assertEqual(
            shift.relationship.source_id, self.npc_target.character_sheet_id
        )  # the granter's regard for the asker is what drops

    def test_failed_roll_moves_nothing(self) -> None:
        request = self._dispatch(success=False)
        self.assertEqual(_balance(self.asker.character_sheet), 0)
        request.boon.refresh_from_db()
        self.assertIsNone(request.boon.fulfilled_at)
        self.assertFalse(AffectionShift.objects.exists())

    def test_serial_boons_in_one_scene_stack_the_affection_cost(self) -> None:
        self._dispatch(success=True, sum_tier=BoonSumTier.MINOR)  # 5% of 1000 = 50
        self._dispatch(success=True, sum_tier=BoonSumTier.MINOR)  # 5% of 950 = 47
        self.assertEqual(_balance(self.asker.character_sheet), 97)  # tiers re-derive per ask
        self.assertEqual(AffectionShift.objects.count(), 2)  # per-Boon dedup — both landed

    def test_granted_vault_boon_withdraws_to_the_asker(self) -> None:
        from world.items.factories import ItemInstanceFactory
        from world.items.org_vault_models import VaultHolding
        from world.items.services.org_vault import deposit_item_to_vault
        from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory

        org = OrganizationFactory()
        OrganizationMembershipFactory(persona=self.npc_target, organization=org, rank=1)
        item = ItemInstanceFactory(holder_character_sheet=self.npc_target.character_sheet)
        deposit_item_to_vault(organization=org, persona=self.npc_target, item_instance=item)

        with patch(
            "world.scenes.action_services.start_action_resolution",
            return_value=_success_resolution(success=True),
        ):
            request = create_action_request(
                scene=self.scene,
                initiator_persona=self.asker,
                target_persona=self.npc_target,
                action_key="boon",
                boon=BoonAsk(kind=BoonKind.VAULT_ITEM, item_instance_id=item.pk),
            )
        item.refresh_from_db()
        self.assertEqual(item.holder_character_sheet, self.asker.character_sheet)
        self.assertFalse(VaultHolding.objects.exists())  # left the vault, audited
        request.boon.refresh_from_db()
        self.assertIsNotNone(request.boon.fulfilled_at)

    def test_granted_held_item_boon_hands_the_item_over(self) -> None:
        from world.items.constants import OwnershipEventType
        from world.items.factories import ItemInstanceFactory
        from world.items.models import OwnershipEvent

        item = ItemInstanceFactory(holder_character_sheet=self.npc_target.character_sheet)
        with patch(
            "world.scenes.action_services.start_action_resolution",
            return_value=_success_resolution(success=True),
        ):
            request = create_action_request(
                scene=self.scene,
                initiator_persona=self.asker,
                target_persona=self.npc_target,
                action_key="boon",
                boon=BoonAsk(kind=BoonKind.HELD_ITEM, item_instance_id=item.pk),
            )
        item.refresh_from_db()
        self.assertEqual(item.holder_character_sheet, self.asker.character_sheet)
        event = OwnershipEvent.objects.get(event_type=OwnershipEventType.TRANSFERRED)
        self.assertEqual(event.notes, "boon")
        self.assertEqual(event.from_persona_display, self.npc_target)  # the presented faces
        self.assertEqual(event.to_persona_display, self.asker)
        request.boon.refresh_from_db()
        self.assertIsNotNone(request.boon.fulfilled_at)

    def test_held_item_gone_by_accept_leaves_boon_unfulfilled(self) -> None:
        from world.items.factories import ItemInstanceFactory
        from world.scenes.boon_services import fulfill_boon

        item = ItemInstanceFactory(holder_character_sheet=self.npc_target.character_sheet)
        request = SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.asker,
            target_persona=self.npc_target,
            action_key="boon",
        )
        boon = Boon.objects.create(
            action_request=request, kind=BoonKind.HELD_ITEM, item_instance=item
        )
        item.holder_character_sheet = None  # it left their hands between ask and accept
        item.save(update_fields=["holder_character_sheet"])
        with self.assertRaises(ValidationError):
            fulfill_boon(boon)
        boon.refresh_from_db()
        self.assertIsNone(boon.fulfilled_at)


class BoonSeedTests(TestCase):
    """The Boon template + consent category seed and wire together."""

    def test_boon_template_seeded_with_boon_consent_category(self) -> None:
        from actions.models import ActionTemplate
        from world.seeds.checks import seed_check_resolution_tables
        from world.seeds.consent import seed_social_consent_categories
        from world.seeds.social_actions import seed_social_action_content
        from world.seeds.social_checks import seed_social_check_content
        from world.seeds.social_relationships import seed_social_relationship_content

        seed_check_resolution_tables()
        seed_social_check_content()
        seed_social_relationship_content()
        seed_social_action_content()
        seed_social_consent_categories()

        template = ActionTemplate.objects.get(name="Boon")
        self.assertEqual(template.consent_category.key, "boon")
        self.assertEqual(template.consent_category.parent.key, "antagonism")
