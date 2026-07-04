"""Tests for SignatureViewSet — HTTP contract for list/set/clear (#1728 Task 4).

Exercises the endpoints the way the web frontend hits them:
  • GET  /api/magic/signatures/            → available bonuses + technique threads
  • POST /api/magic/signatures/set/         → attach a bonus to one of the actor's own threads
  • POST /api/magic/signatures/clear/       → remove the bonus from one of the actor's own threads
  • cross-character thread id → 400
  • no puppet → 400 "No active character."

Uses ``force_authenticate`` + a ``SimpleNamespace`` puppet-bearing user, mirroring
``world/magic/tests/test_sanctum_viewset.py``. Unlike the sanctum tests, the
Actions are NOT mocked here — real ``SignatureSetAction``/``SignatureClearAction``/
``SignatureListAction`` run against real service-layer state, per the Task 4 brief
(assert via ``signature_bonus_for``/the ``Thread`` row).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    FacetFactory,
    GiftFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import SignatureMotifBonus, Thread
from world.magic.services.signature import signature_bonus_for
from world.magic.views_signature import SignatureViewSet


def _actor_user(character):
    """Fake authenticated user whose ``puppet`` is ``character``."""
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=character.db_account_id,
        puppet=character,
    )


def _no_puppet_user():
    """Fake authenticated user with no puppet — actor cannot be resolved."""
    return SimpleNamespace(is_authenticated=True, is_staff=False, pk=None, puppet=None)


class SignatureViewSetTestBase(TestCase):
    """Common setup: one character with a qualifying bonus + owned TECHNIQUE thread."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.factory = APIRequestFactory()

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.motif = MotifFactory(character=self.sheet)
        self.resonance = ResonanceFactory()
        self.facet = FacetFactory(name="Signature Viewset Facet")
        self.motif_res = MotifResonanceFactory(motif=self.motif, resonance=self.resonance)
        MotifResonanceAssociationFactory(motif_resonance=self.motif_res, facet=self.facet)

        self.gift = GiftFactory()
        self.technique = TechniqueFactory(gift=self.gift, level=1, damage_profile=False)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

        self.bonus = SignatureMotifBonus.objects.create(
            name="Viewset Test Bonus",
            required_facet=self.facet,
        )

        self.thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
        )
        self.sheet.character.threads.invalidate()

    def tearDown(self) -> None:
        self.thread.delete()
        self.sheet.character.threads.invalidate()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_list(self, puppet):
        request = self.factory.get("/api/magic/signatures/")
        force_authenticate(request, user=puppet)
        view = SignatureViewSet.as_view({"get": "list"})
        return view(request)

    def _post_set(self, puppet, payload):
        request = self.factory.post("/api/magic/signatures/set/", payload, format="json")
        force_authenticate(request, user=puppet)
        view = SignatureViewSet.as_view({"post": "set_bonus"})
        return view(request)

    def _post_clear(self, puppet, payload):
        request = self.factory.post("/api/magic/signatures/clear/", payload, format="json")
        force_authenticate(request, user=puppet)
        view = SignatureViewSet.as_view({"post": "clear_bonus"})
        return view(request)


# ===========================================================================
# list
# ===========================================================================


class SignatureListEndpointTests(SignatureViewSetTestBase):
    def test_list_success_returns_available_bonuses_and_threads(self) -> None:
        resp = self._get_list(_actor_user(self.character))

        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.bonus.pk, resp.data["available_bonus_ids"])
        thread_rows = resp.data["technique_threads"]
        matching = [row for row in thread_rows if row["thread_id"] == self.thread.pk]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["technique_name"], self.technique.name)
        self.assertIsNone(matching[0]["current_bonus"])

    def test_list_no_puppet_returns_400(self) -> None:
        resp = self._get_list(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())


# ===========================================================================
# set
# ===========================================================================


class SignatureSetEndpointTests(SignatureViewSetTestBase):
    def test_set_success_returns_200_and_persists(self) -> None:
        resp = self._post_set(
            _actor_user(self.character),
            {"thread_id": self.thread.pk, "bonus_id": self.bonus.pk},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["thread_id"], self.thread.pk)
        self.assertEqual(resp.data["bonus_id"], self.bonus.pk)

        refreshed = Thread.objects.get(pk=self.thread.pk)
        self.assertEqual(refreshed.signature_bonus_id, self.bonus.pk)
        self.sheet.character.threads.invalidate()
        self.assertEqual(signature_bonus_for(self.sheet.character, self.technique), self.bonus)

    def test_set_no_puppet_returns_400(self) -> None:
        resp = self._post_set(
            _no_puppet_user(),
            {"thread_id": self.thread.pk, "bonus_id": self.bonus.pk},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_set_rejects_thread_belonging_to_another_character(self) -> None:
        """A thread_id that isn't one of the actor's own threads is rejected."""
        other_character = CharacterFactory()
        other_sheet = CharacterSheetFactory(character=other_character)
        other_technique = TechniqueFactory(gift=self.gift, level=1, damage_profile=False)
        CharacterTechniqueFactory(character=other_sheet, technique=other_technique)
        other_thread = Thread.objects.create(
            owner=other_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=other_technique,
        )
        try:
            resp = self._post_set(
                _actor_user(self.character),
                {"thread_id": other_thread.pk, "bonus_id": self.bonus.pk},
            )

            self.assertEqual(resp.status_code, 400)
            refreshed = Thread.objects.get(pk=other_thread.pk)
            self.assertIsNone(refreshed.signature_bonus_id)
        finally:
            other_thread.delete()

    def test_set_unknown_bonus_id_returns_400(self) -> None:
        resp = self._post_set(
            _actor_user(self.character),
            {"thread_id": self.thread.pk, "bonus_id": 999_999},
        )

        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# clear
# ===========================================================================


class SignatureClearEndpointTests(SignatureViewSetTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.thread.signature_bonus = self.bonus
        self.thread.save(update_fields=["signature_bonus", "updated_at"])
        self.sheet.character.threads.invalidate()

    def test_clear_success_returns_200_and_persists(self) -> None:
        resp = self._post_clear(_actor_user(self.character), {"thread_id": self.thread.pk})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["thread_id"], self.thread.pk)

        refreshed = Thread.objects.get(pk=self.thread.pk)
        self.assertIsNone(refreshed.signature_bonus_id)

    def test_clear_no_puppet_returns_400(self) -> None:
        resp = self._post_clear(_no_puppet_user(), {"thread_id": self.thread.pk})

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_clear_rejects_thread_belonging_to_another_character(self) -> None:
        other_character = CharacterFactory()
        other_sheet = CharacterSheetFactory(character=other_character)
        other_technique = TechniqueFactory(gift=self.gift, level=1, damage_profile=False)
        CharacterTechniqueFactory(character=other_sheet, technique=other_technique)
        other_thread = Thread.objects.create(
            owner=other_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=other_technique,
            signature_bonus=self.bonus,
        )
        try:
            resp = self._post_clear(_actor_user(self.character), {"thread_id": other_thread.pk})

            self.assertEqual(resp.status_code, 400)
            refreshed = Thread.objects.get(pk=other_thread.pk)
            self.assertEqual(refreshed.signature_bonus_id, self.bonus.pk)
        finally:
            other_thread.delete()
