"""Tests for Resonance Pivot Spec A Phase 16 API surface (§4.5, §5.6).

Covers:
- ThreadViewSet (list / retrieve / create / soft-retire destroy + ownership)
- ThreadPullPreviewView (POST preview, never mutates state)
- RitualPerformView (Imbuing dispatch path + typed-exception → 400)
- ThreadWeavingTeachingOfferViewSet (read-only list + target_kind filter)
- IsThreadOwner permission enforcement
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ImbuingRitualFactory,
    IntensityTierFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadWeavingTeachingOfferFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import Thread
from world.roster.factories import RosterTenureFactory
from world.traits.factories import TraitFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure."""
    return RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
    )


class ThreadViewSetTests(APITestCase):
    """Tests for Thread list / retrieve / create / destroy (Spec A §4.5)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="thread_owner")
        cls.character = CharacterFactory(db_key="ThreadOwner")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.other_account = AccountFactory(username="thread_other")
        cls.other_character = CharacterFactory(db_key="ThreadOther")
        cls.other_sheet = CharacterSheetFactory(character=cls.other_character)
        _link_account_to_sheet(cls.other_account, cls.other_character, cls.other_sheet)

        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_trait=cls.trait,
            level=5,
        )

    def test_list_requires_auth(self) -> None:
        response = self.client.get(reverse("magic:thread-list"))
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_returns_only_owned_threads(self) -> None:
        other_thread = ThreadFactory(
            owner=self.other_sheet,
            resonance=self.resonance,
            target_trait=TraitFactory(),
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(reverse("magic:thread-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned = {t["id"] for t in response.data["results"]}
        self.assertIn(self.thread.pk, returned)
        self.assertNotIn(other_thread.pk, returned)

    def test_list_excludes_retired(self) -> None:
        retired = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_trait=TraitFactory(),
        )
        retired.retired_at = retired.created_at  # any non-null value
        retired.save(update_fields=["retired_at"])
        self.client.force_authenticate(user=self.account)
        response = self.client.get(reverse("magic:thread-list"))
        returned = {t["id"] for t in response.data["results"]}
        self.assertNotIn(retired.pk, returned)

    def test_retrieve_requires_ownership(self) -> None:
        self.client.force_authenticate(user=self.other_account)
        response = self.client.get(reverse("magic:thread-detail", args=[self.thread.pk]))
        # queryset filter already strips it → 404.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_delegates_to_weave_thread(self) -> None:
        trait = TraitFactory()
        CharacterThreadWeavingUnlockFactory(
            character=self.sheet,
            unlock=ThreadWeavingUnlockFactory(
                target_kind=TargetKind.TRAIT,
                unlock_trait=trait,
            ),
        )
        self.client.force_authenticate(user=self.account)
        payload = {
            "resonance": self.resonance.pk,
            "target_kind": TargetKind.TRAIT,
            "target_id": trait.pk,
            "name": "Bound to Steel",
        }
        response = self.client.post(
            reverse("magic:thread-list"),
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet,
                resonance=self.resonance,
                target_trait=trait,
            ).exists()
        )

    def test_create_rejects_without_weaving_unlock(self) -> None:
        trait = TraitFactory()
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.TRAIT,
                "target_id": trait.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_destroy_soft_retires(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.delete(
            reverse("magic:thread-detail", args=[self.thread.pk]),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.thread.refresh_from_db()
        self.assertIsNotNone(self.thread.retired_at)
        # Row still exists — historical references preserved.
        self.assertTrue(Thread.objects.filter(pk=self.thread.pk).exists())


class ThreadPullPreviewTests(APITestCase):
    """Tests for POST /api/magic/thread-pull-preview/ (Spec A §5.6)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="preview_owner")
        cls.character = CharacterFactory(db_key="PreviewOwner")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_trait=cls.trait,
            level=20,
        )
        cls.cost = ThreadPullCostFactory(
            tier=1,
            resonance_cost=3,
            anima_per_thread=2,
        )
        cls.char_resonance = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=10,
            lifetime_earned=10,
        )
        CharacterAnimaFactory(character=cls.character, current=10, maximum=10)

        # A tier-0 FLAT_BONUS gives a non-empty resolved_effects list.
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            tier=0,
            flat_bonus_amount=2,
        )

    def test_requires_auth(self) -> None:
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_preview_returns_costs_and_effects(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["resonance_cost"], 3)
        # n_threads - 1 = 0 → anima_cost = 0
        self.assertEqual(response.data["anima_cost"], 0)
        self.assertTrue(response.data["affordable"])
        self.assertGreaterEqual(len(response.data["resolved_effects"]), 1)

    def test_preview_rejects_foreign_thread(self) -> None:
        other_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="other"))
        foreign = ThreadFactory(
            owner=other_sheet,
            resonance=self.resonance,
            target_trait=TraitFactory(),
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [foreign.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preview_rejects_bad_tier(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "resonance_id": self.resonance.pk,
                "tier": 9,  # > max_value=3
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preview_capped_intensity_flag(self) -> None:
        IntensityTierFactory(name="Minor", threshold=1)
        # min_thread_level=5 keeps this row distinct from the tier-0 row
        # seeded in setUpTestData (which uses min_thread_level=0).
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            tier=0,
            min_thread_level=5,
            effect_kind=EffectKind.INTENSITY_BUMP,
            intensity_bump_amount=50,
            flat_bonus_amount=None,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["capped_intensity"])

    def test_preview_does_not_mutate(self) -> None:
        before_balance = self.char_resonance.balance
        self.client.force_authenticate(user=self.account)
        self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.char_resonance.refresh_from_db()
        self.assertEqual(self.char_resonance.balance, before_balance)


class RitualPerformViewTests(APITestCase):
    """Tests for POST /api/magic/rituals/perform/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="ritual_owner")
        cls.character = CharacterFactory(db_key="RitualOwner")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_trait=cls.trait,
            level=2,
            _trait_value=9,  # anchor cap 9 — plenty of headroom under level 10
        )
        cls.char_resonance = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        cls.ritual = ImbuingRitualFactory()

    def test_requires_auth(self) -> None:
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_imbuing_dispatch_succeeds(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "amount": 5},
                "components": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["ritual_id"], self.ritual.pk)
        self.assertIn("result", response.data)
        self.thread.refresh_from_db()
        self.assertGreater(self.thread.developed_points + self.thread.level, 0)

    def test_imbuing_requires_thread_id(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "ritual_id": self.ritual.pk,
                "kwargs": {"amount": 5},
                "components": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_imbuing_rejects_foreign_thread(self) -> None:
        other_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="notmine"))
        foreign = ThreadFactory(
            owner=other_sheet,
            resonance=self.resonance,
            target_trait=TraitFactory(),
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": foreign.pk, "amount": 5},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_typed_exception_returns_user_message(self) -> None:
        # amount < 0 → InvalidImbueAmount.user_message on HTTP 400.
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "amount": -1},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_kwargs_rejects_non_primitive_values(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "extra": [1, 2, 3]},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ThreadWeavingTeachingOfferViewSetTests(APITestCase):
    """Tests for GET /api/magic/teaching-offers/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="offer_viewer")
        cls.trait_unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TRAIT,
        )
        # Switch one to ITEM so target_kind filter meaningfully discriminates.
        cls.item_unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.ITEM,
            unlock_trait=None,
            unlock_item_typeclass_path="typeclasses.objects.Object",
        )
        cls.trait_offer = ThreadWeavingTeachingOfferFactory(unlock=cls.trait_unlock)
        cls.item_offer = ThreadWeavingTeachingOfferFactory(unlock=cls.item_unlock)

    def test_requires_auth(self) -> None:
        response = self.client.get(reverse("magic:thread-weaving-teaching-offer-list"))
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_authenticated(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(reverse("magic:thread-weaving-teaching-offer-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 2)

    def test_filter_by_target_kind(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(
            reverse("magic:thread-weaving-teaching-offer-list"),
            {"target_kind": TargetKind.ITEM},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {o["id"] for o in response.data["results"]}
        self.assertIn(self.item_offer.pk, returned_ids)
        self.assertNotIn(self.trait_offer.pk, returned_ids)

    def test_list_is_read_only(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-weaving-teaching-offer-list"),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class PermissionTests(APITestCase):
    """Direct checks on IsThreadOwner + retired filtering at the queryset layer."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner_account = AccountFactory(username="p_owner")
        cls.owner_character = CharacterFactory(db_key="POwner")
        cls.owner_sheet = CharacterSheetFactory(character=cls.owner_character)
        _link_account_to_sheet(cls.owner_account, cls.owner_character, cls.owner_sheet)

        cls.intruder_account = AccountFactory(username="p_intruder")
        cls.intruder_character = CharacterFactory(db_key="PIntruder")
        cls.intruder_sheet = CharacterSheetFactory(character=cls.intruder_character)
        _link_account_to_sheet(
            cls.intruder_account,
            cls.intruder_character,
            cls.intruder_sheet,
        )

        cls.staff_account = AccountFactory(username="p_staff", is_staff=True)

        cls.resonance = ResonanceFactory()
        cls.thread = ThreadFactory(
            owner=cls.owner_sheet,
            resonance=cls.resonance,
            target_trait=TraitFactory(),
        )

    def test_non_owner_cannot_retrieve(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.intruder_account)
        response = client.get(reverse("magic:thread-detail", args=[self.thread.pk]))
        # get_queryset filters by ownership → 404 before IsThreadOwner runs.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_can_retrieve_any_thread(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get(reverse("magic:thread-detail", args=[self.thread.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_owner_cannot_soft_retire(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.intruder_account)
        response = client.delete(reverse("magic:thread-detail", args=[self.thread.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.thread.refresh_from_db()
        self.assertIsNone(self.thread.retired_at)
