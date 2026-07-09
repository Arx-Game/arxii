"""Tests for MotifStyleViewSet — HTTP contract for list/bind/unbind (#2030).

Exercises the endpoints the way the web frontend hits them:
  • GET  /api/magic/motif-styles/        → the actor's style bindings
  • POST /api/magic/motif-styles/bind/   → bind a style to a claimed resonance
  • POST /api/magic/motif-styles/unbind/ → remove a binding
  • no puppet → 400 "No active character."
  • bad style_id / bad resonance_id → 400 with detail
  • bind to an unclaimed resonance → 400 with the service ``user_message``
  • X-Character-ID header scopes to that (owned, non-puppeted) character
  • X-Character-ID naming an unowned character → 404, no puppet fallback

Mirrors ``world/magic/tests/test_signature_viewset.py`` — real Actions run
against real service-layer state (nothing mocked).
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import StyleFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.models import MotifResonanceStyle
from world.magic.views_motif_style import MotifStyleViewSet


def _actor_user(character, *, available_characters=None):
    """Fake authenticated user whose ``puppet`` is ``character``.

    ``available_characters`` backs ``get_available_characters()`` — the
    ownership check ``CharacterContextMixin._get_character`` runs against an
    ``X-Character-ID`` header. Defaults to ``[character]`` (the puppet owns
    itself) when not given.
    """
    owned = available_characters if available_characters is not None else [character]
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=character.db_account_id,
        puppet=character,
        get_available_characters=lambda: owned,
    )


def _no_puppet_user(*, available_characters=None):
    """Fake authenticated user with no puppet — actor cannot be resolved."""
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=None,
        puppet=None,
        get_available_characters=lambda: available_characters or [],
    )


class MotifStyleViewSetTestBase(TestCase):
    """Common setup: one character with a claimed resonance and a Style catalog row."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.factory = APIRequestFactory()

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        self.style = StyleFactory(name="Seductive")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_list(self, puppet, *, character_id=None):
        extra = {"HTTP_X_CHARACTER_ID": str(character_id)} if character_id is not None else {}
        request = self.factory.get("/api/magic/motif-styles/", **extra)
        force_authenticate(request, user=puppet)
        view = MotifStyleViewSet.as_view({"get": "list"})
        return view(request)

    def _post_bind(self, puppet, payload, *, character_id=None):
        extra = {"HTTP_X_CHARACTER_ID": str(character_id)} if character_id is not None else {}
        request = self.factory.post(
            "/api/magic/motif-styles/bind/", payload, format="json", **extra
        )
        force_authenticate(request, user=puppet)
        view = MotifStyleViewSet.as_view({"post": "bind"})
        return view(request)

    def _post_unbind(self, puppet, payload, *, character_id=None):
        extra = {"HTTP_X_CHARACTER_ID": str(character_id)} if character_id is not None else {}
        request = self.factory.post(
            "/api/magic/motif-styles/unbind/", payload, format="json", **extra
        )
        force_authenticate(request, user=puppet)
        view = MotifStyleViewSet.as_view({"post": "unbind"})
        return view(request)


# ===========================================================================
# list
# ===========================================================================


class MotifStyleListEndpointTests(MotifStyleViewSetTestBase):
    def test_list_no_puppet_returns_400(self) -> None:
        resp = self._get_list(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_list_returns_bindings_with_exact_contract_keys(self) -> None:
        self._post_bind(
            _actor_user(self.character),
            {"style_id": self.style.pk, "resonance_id": self.resonance.pk},
        )

        resp = self._get_list(_actor_user(self.character))

        self.assertEqual(resp.status_code, 200)
        bindings = resp.data["bindings"]
        self.assertEqual(len(bindings), 1)
        row = bindings[0]
        self.assertEqual(
            set(row.keys()),
            {"style_id", "style_name", "audacity", "resonance_id", "resonance_name"},
        )
        self.assertEqual(row["style_id"], self.style.pk)
        self.assertEqual(row["style_name"], self.style.name)
        self.assertEqual(row["resonance_id"], self.resonance.pk)
        self.assertEqual(row["resonance_name"], self.resonance.name)


# ===========================================================================
# bind
# ===========================================================================


class MotifStyleBindEndpointTests(MotifStyleViewSetTestBase):
    def test_bind_no_puppet_returns_400(self) -> None:
        resp = self._post_bind(
            _no_puppet_user(),
            {"style_id": self.style.pk, "resonance_id": self.resonance.pk},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_bind_creates_row(self) -> None:
        resp = self._post_bind(
            _actor_user(self.character),
            {"style_id": self.style.pk, "resonance_id": self.resonance.pk},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["style_id"], self.style.pk)
        self.assertEqual(resp.data["resonance_id"], self.resonance.pk)
        self.assertTrue(
            MotifResonanceStyle.objects.filter(
                motif_resonance__motif__character=self.sheet,
                style=self.style,
                motif_resonance__resonance=self.resonance,
            ).exists()
        )

    def test_bind_bad_style_id_returns_400_with_detail(self) -> None:
        resp = self._post_bind(
            _actor_user(self.character),
            {"style_id": 999_999, "resonance_id": self.resonance.pk},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)

    def test_bind_bad_resonance_id_returns_400_with_detail(self) -> None:
        resp = self._post_bind(
            _actor_user(self.character),
            {"style_id": self.style.pk, "resonance_id": 999_999},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)

    def test_bind_unclaimed_resonance_returns_400_with_service_message(self) -> None:
        unclaimed = ResonanceFactory()

        resp = self._post_bind(
            _actor_user(self.character),
            {"style_id": self.style.pk, "resonance_id": unclaimed.pk},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "You have not claimed that resonance.")


# ===========================================================================
# unbind
# ===========================================================================


class MotifStyleUnbindEndpointTests(MotifStyleViewSetTestBase):
    def setUp(self) -> None:
        super().setUp()
        self._post_bind(
            _actor_user(self.character),
            {"style_id": self.style.pk, "resonance_id": self.resonance.pk},
        )

    def test_unbind_no_puppet_returns_400(self) -> None:
        resp = self._post_unbind(_no_puppet_user(), {"style_id": self.style.pk})

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_unbind_removes_row(self) -> None:
        resp = self._post_unbind(_actor_user(self.character), {"style_id": self.style.pk})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["style_id"], self.style.pk)
        self.assertFalse(
            MotifResonanceStyle.objects.filter(
                motif_resonance__motif__character=self.sheet, style=self.style
            ).exists()
        )

    def test_unbind_unknown_style_id_returns_400(self) -> None:
        other_style = StyleFactory(name="Stoic")

        resp = self._post_unbind(_actor_user(self.character), {"style_id": other_style.pk})

        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# X-Character-ID scoping (#2030 review fix)
# ===========================================================================


class MotifStyleCharacterHeaderScopingTests(MotifStyleViewSetTestBase):
    """A puppeted account viewing/mutating a *different*, owned character's sheet
    must act on THAT character's bindings, not the puppet's — and a header
    naming a character the account doesn't own must be rejected outright
    rather than silently falling back to the puppet.
    """

    def setUp(self) -> None:
        super().setUp()
        # A second, non-puppeted character owned by the same account, with its
        # own claimed resonance and an existing binding — distinct from the
        # puppet's own binding created in some tests.
        self.alt_character = CharacterFactory()
        self.alt_sheet = CharacterSheetFactory(character=self.alt_character)
        self.alt_resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.alt_sheet, resonance=self.alt_resonance)

        # A wholly unrelated account's character — never owned by our caller.
        self.unowned_character = CharacterFactory()

    def test_list_scopes_to_header_character_not_puppet(self) -> None:
        # Bind a style on the PUPPET (self.character) — should NOT show up when
        # scoped to the alt via the header.
        self._post_bind(
            _actor_user(self.character),
            {"style_id": self.style.pk, "resonance_id": self.resonance.pk},
        )
        # Bind a different style on the alt character directly via the header.
        alt_style = StyleFactory(name="Stoic")
        user = _actor_user(
            self.character, available_characters=[self.character, self.alt_character]
        )
        self._post_bind(
            user,
            {"style_id": alt_style.pk, "resonance_id": self.alt_resonance.pk},
            character_id=self.alt_character.pk,
        )

        resp = self._get_list(user, character_id=self.alt_character.pk)

        self.assertEqual(resp.status_code, 200)
        bindings = resp.data["bindings"]
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["style_id"], alt_style.pk)
        self.assertEqual(bindings[0]["resonance_id"], self.alt_resonance.pk)

    def test_bind_writes_to_header_character_not_puppet(self) -> None:
        user = _actor_user(
            self.character, available_characters=[self.character, self.alt_character]
        )

        resp = self._post_bind(
            user,
            {"style_id": self.style.pk, "resonance_id": self.alt_resonance.pk},
            character_id=self.alt_character.pk,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            MotifResonanceStyle.objects.filter(
                motif_resonance__motif__character=self.alt_sheet, style=self.style
            ).exists()
        )
        self.assertFalse(
            MotifResonanceStyle.objects.filter(
                motif_resonance__motif__character=self.sheet, style=self.style
            ).exists()
        )

    def test_unbind_writes_to_header_character_not_puppet(self) -> None:
        user = _actor_user(
            self.character, available_characters=[self.character, self.alt_character]
        )
        self._post_bind(
            user,
            {"style_id": self.style.pk, "resonance_id": self.alt_resonance.pk},
            character_id=self.alt_character.pk,
        )

        resp = self._post_unbind(
            user, {"style_id": self.style.pk}, character_id=self.alt_character.pk
        )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            MotifResonanceStyle.objects.filter(
                motif_resonance__motif__character=self.alt_sheet, style=self.style
            ).exists()
        )

    def test_list_header_naming_unowned_character_returns_404_not_puppet_fallback(self) -> None:
        user = _actor_user(self.character, available_characters=[self.character])

        resp = self._get_list(user, character_id=self.unowned_character.pk)

        self.assertEqual(resp.status_code, 404)
        self.assertIn("character", resp.data["detail"].lower())

    def test_bind_header_naming_unowned_character_returns_404(self) -> None:
        user = _actor_user(self.character, available_characters=[self.character])

        resp = self._post_bind(
            user,
            {"style_id": self.style.pk, "resonance_id": self.resonance.pk},
            character_id=self.unowned_character.pk,
        )

        self.assertEqual(resp.status_code, 404)
        self.assertFalse(MotifResonanceStyle.objects.filter(style=self.style).exists())

    def test_unbind_header_naming_unowned_character_returns_404(self) -> None:
        user = _actor_user(self.character, available_characters=[self.character])

        resp = self._post_unbind(
            user, {"style_id": self.style.pk}, character_id=self.unowned_character.pk
        )

        self.assertEqual(resp.status_code, 404)
