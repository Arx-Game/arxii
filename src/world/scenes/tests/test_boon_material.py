"""Boon slice 3 (#2540): the MATERIAL kind, explicit dispatch, honest unavailability.

Mirrors ``test_boon.py``'s structure and helpers (imports a few directly rather than
duplicating them) — this file owns everything new to slice 3: the MATERIAL kind
itself, the explicit-dispatch restructure's loud-failure-on-a-miss guarantee, and the
honest-unavailability short-circuit (``BoonUnavailable``) for both NPC and piloted
targets.
"""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from evennia_extensions.factories import AccountFactory
from world.items.factories import MaterialCategoryFactory
from world.items.gems.buckets import credit_materials, material_value, spend_materials
from world.relationships.models import AffectionShift
from world.scenes.action_constants import BoonKind, BoonSumTier
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_services import create_action_request
from world.scenes.boon_models import Boon
from world.scenes.boon_services import (
    BOON_AFFECTION_COST,
    BoonAsk,
    BoonUnavailable,
    check_boon_availability,
    fulfill_boon,
    validate_boon_ask,
)
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.scenes.tests.test_boon import _success_resolution


def _pilot(persona) -> None:
    """Attach an account so the persona reads as a PC (mirrors test_boon.py)."""
    character = persona.character_sheet.character
    character.db_account = AccountFactory()
    character.save(update_fields=["db_account"])


class BoonExplicitDispatchTests(TestCase):
    """The recon trap fix: every real BoonKind has a table entry; a miss is loud."""

    def test_every_boon_kind_has_an_explicit_ask_validator(self) -> None:
        from world.scenes.boon_services import _BOON_ASK_VALIDATORS

        self.assertEqual(set(_BOON_ASK_VALIDATORS), set(BoonKind.values))

    def test_every_boon_kind_has_an_explicit_fulfiller(self) -> None:
        from world.scenes.boon_services import _BOON_FULFILLERS

        self.assertEqual(set(_BOON_FULFILLERS), set(BoonKind.values))

    def test_validate_boon_ask_raises_loudly_on_an_unhandled_kind(self) -> None:
        from world.scenes.boon_services import _BOON_ASK_VALIDATORS

        target = PersonaFactory()
        asker = PersonaFactory()
        # A real BoonKind value with its dispatch entry removed — simulates a future
        # kind added to the enum without a matching validator wired in.
        with patch.dict(_BOON_ASK_VALIDATORS, clear=True), self.assertRaises(ValueError):
            validate_boon_ask(
                ask=BoonAsk(kind=BoonKind.MONEY),
                target_persona=target,
                asker_sheet=asker.character_sheet,
            )

    def test_fulfill_boon_raises_loudly_on_an_unhandled_kind(self) -> None:
        request = SceneActionRequestFactory()
        # Boon.kind is a plain CharField — Django's choices are not DB-enforced, so a
        # row with an unrecognized kind is directly constructible (simulates the same
        # future-kind-without-a-fulfiller gap from the fulfillment side).
        boon = Boon.objects.create(action_request=request, kind="nonexistent_kind")
        with self.assertRaises(ValueError):
            fulfill_boon(boon)


class MaterialBoonAskValidationTests(TestCase):
    """Dial 1 — ask-time eligibility for MATERIAL: well-formed, category-and-tier only.

    The zero-bucket case is deliberately NOT eligibility (see
    MaterialBoonAvailabilityTests below) — the STATIC public category picker is never
    filtered by the target's holdings.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.asker = PersonaFactory()
        cls.target = PersonaFactory()
        cls.category = MaterialCategoryFactory()

    def _ask(self, **kwargs) -> SceneActionRequest:
        return create_action_request(
            scene=self.scene,
            initiator_persona=self.asker,
            target_persona=self.target,
            action_key="boon",
            boon=BoonAsk(**kwargs),
        )

    def test_material_ask_requires_a_category(self) -> None:
        with self.assertRaises(ValidationError):
            self._ask(kind=BoonKind.MATERIAL, sum_tier=BoonSumTier.FAIR)

    def test_material_ask_requires_a_known_category(self) -> None:
        with self.assertRaises(ValidationError):
            self._ask(
                kind=BoonKind.MATERIAL, sum_tier=BoonSumTier.FAIR, material_category_id=999999
            )

    def test_material_ask_requires_a_valid_sum_tier(self) -> None:
        credit_materials(self.target.character_sheet, self.category, 100)
        with self.assertRaises(ValidationError):
            self._ask(kind=BoonKind.MATERIAL, sum_tier="", material_category_id=self.category.pk)

    def test_material_ask_composes_when_target_holds_any(self) -> None:
        credit_materials(self.target.character_sheet, self.category, 100)
        request = self._ask(
            kind=BoonKind.MATERIAL,
            sum_tier=BoonSumTier.FAIR,
            material_category_id=self.category.pk,
        )
        self.assertEqual(request.boon.kind, BoonKind.MATERIAL)
        self.assertEqual(request.boon.material_category_id, self.category.pk)
        self.assertEqual(request.boon.sum_tier, BoonSumTier.FAIR)
        self.assertEqual(request.boon.amount, 0)  # never a computed value, unlike money


class MaterialBoonAvailabilityTests(TestCase):
    """Honest unavailability (#2540 slice 3 controller ruling): a well-formed ask the
    target genuinely can't grant is refused — for BOTH NPC and piloted targets — before
    any row is created, no roll, no consent burn, no affection drain."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.asker = PersonaFactory()
        cls.category = MaterialCategoryFactory()

    def _ask(self, target) -> SceneActionRequest:
        return create_action_request(
            scene=self.scene,
            initiator_persona=self.asker,
            target_persona=target,
            action_key="boon",
            boon=BoonAsk(
                kind=BoonKind.MATERIAL,
                sum_tier=BoonSumTier.FAIR,
                material_category_id=self.category.pk,
            ),
        )

    def test_zero_bucket_npc_target_is_refused_no_orphan_row(self) -> None:
        target = PersonaFactory()  # no bucket at all -> 0
        with self.assertRaises(BoonUnavailable):
            self._ask(target)
        self.assertFalse(SceneActionRequest.objects.exists())
        self.assertFalse(AffectionShift.objects.exists())

    def test_zero_bucket_piloted_target_is_refused_no_orphan_row(self) -> None:
        target = PersonaFactory()
        _pilot(target)  # piloted target — still never reaches their consent queue
        with self.assertRaises(BoonUnavailable):
            self._ask(target)
        self.assertFalse(SceneActionRequest.objects.exists())
        self.assertFalse(AffectionShift.objects.exists())

    def test_nonzero_bucket_target_is_not_refused(self) -> None:
        target = PersonaFactory()
        credit_materials(target.character_sheet, self.category, 1)
        check_boon_availability(  # should not raise
            ask=BoonAsk(
                kind=BoonKind.MATERIAL,
                sum_tier=BoonSumTier.FAIR,
                material_category_id=self.category.pk,
            ),
            target_persona=target,
        )

    def test_money_and_other_kinds_are_never_checked_for_availability(self) -> None:
        """Only MATERIAL is checked — money's penniless case is validate_boon_ask's job."""
        target = PersonaFactory()
        check_boon_availability(  # should not raise, even though penniless
            ask=BoonAsk(kind=BoonKind.MONEY, sum_tier=BoonSumTier.FAIR), target_persona=target
        )
        check_boon_availability(  # should not raise
            ask=BoonAsk(kind=BoonKind.DEED, deed_text="Guard the gate"), target_persona=target
        )


class MaterialBoonFulfillmentTests(TestCase):
    """Fulfillment math: tier pct of the target's bucket AT FULFILLMENT, min 1."""

    def setUp(self) -> None:
        self.request = SceneActionRequestFactory()
        self.asker_sheet = self.request.initiator_persona.character_sheet
        self.target_sheet = self.request.target_persona.character_sheet
        self.category = MaterialCategoryFactory()

    def _boon(self, *, sum_tier: str) -> Boon:
        return Boon.objects.create(
            action_request=self.request,
            kind=BoonKind.MATERIAL,
            sum_tier=sum_tier,
            material_category=self.category,
        )

    def test_fulfillment_moves_tier_pct_of_bucket(self) -> None:
        credit_materials(self.target_sheet, self.category, 1000)
        boon = self._boon(sum_tier=BoonSumTier.FAIR)  # 20%
        self.assertTrue(fulfill_boon(boon))
        self.assertEqual(material_value(self.target_sheet, self.category), 800)
        self.assertEqual(material_value(self.asker_sheet, self.category), 200)
        boon.refresh_from_db()
        self.assertIsNotNone(boon.fulfilled_at)

    def test_fulfillment_amount_is_computed_at_fulfillment_not_ask_time(self) -> None:
        credit_materials(self.target_sheet, self.category, 1000)
        boon = self._boon(sum_tier=BoonSumTier.MINOR)  # 5%
        # The bucket shrinks between ask and fulfillment (never frozen for MATERIAL).
        spend_materials(self.target_sheet, self.category, 900)  # down to 100
        self.assertTrue(fulfill_boon(boon))
        self.assertEqual(material_value(self.asker_sheet, self.category), 5)  # 5% of 100

    def test_fulfillment_minimum_one_when_the_tier_pct_rounds_to_zero(self) -> None:
        credit_materials(self.target_sheet, self.category, 5)
        boon = self._boon(sum_tier=BoonSumTier.MINOR)  # 5% of 5 = 0 -> min 1
        self.assertTrue(fulfill_boon(boon))
        self.assertEqual(material_value(self.asker_sheet, self.category), 1)
        self.assertEqual(material_value(self.target_sheet, self.category), 4)

    def test_fulfillment_is_idempotent(self) -> None:
        credit_materials(self.target_sheet, self.category, 1000)
        boon = self._boon(sum_tier=BoonSumTier.FAIR)
        self.assertTrue(fulfill_boon(boon))
        self.assertFalse(fulfill_boon(boon))  # second call is a no-op
        self.assertEqual(material_value(self.asker_sheet, self.category), 200)  # not doubled

    def test_fulfillment_fails_gracefully_when_bucket_empty_at_fulfillment(self) -> None:
        boon = self._boon(sum_tier=BoonSumTier.FAIR)  # never funded
        with self.assertRaises(ValidationError):
            fulfill_boon(boon)
        boon.refresh_from_db()
        self.assertIsNone(boon.fulfilled_at)


@override_settings(SEED_SAMPLE_CONTENT=True)  # Regard/Friction RelationshipTrack gates on #2698
class MaterialBoonResolverE2ETests(TestCase):
    """The full consent path for MATERIAL: dispatch -> NPC auto-accept -> resolver."""

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
        seed_social_action_content()
        seed_relationship_scale_content()
        cls.scene = SceneFactory()
        cls.category = MaterialCategoryFactory()

    def setUp(self) -> None:
        self.asker = PersonaFactory()
        self.npc_target = PersonaFactory()  # no db_account -> NPC, auto-accepts
        credit_materials(self.npc_target.character_sheet, self.category, 1000)
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    def test_granted_material_boon_fulfills_and_charges_affection(self) -> None:
        with patch(
            "world.scenes.action_services.start_action_resolution",
            return_value=_success_resolution(success=True),
        ):
            request = create_action_request(
                scene=self.scene,
                initiator_persona=self.asker,
                target_persona=self.npc_target,
                action_key="boon",
                boon=BoonAsk(
                    kind=BoonKind.MATERIAL,
                    sum_tier=BoonSumTier.FAIR,
                    material_category_id=self.category.pk,
                ),
            )
        self.assertEqual(material_value(self.asker.character_sheet, self.category), 200)
        self.assertEqual(material_value(self.npc_target.character_sheet, self.category), 800)
        request.boon.refresh_from_db()
        self.assertIsNotNone(request.boon.fulfilled_at)
        shift = AffectionShift.objects.get(boon=request.boon)
        self.assertEqual(shift.amount, -BOON_AFFECTION_COST)
