"""Tests for PathIntent model and REST endpoint (#543)."""

from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.progression.models import PathIntent

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class PathIntentModelTests(TestCase):
    """Unit tests for PathIntent model invariants."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)
        self.path = PathFactory()

    def test_create_intent(self) -> None:
        """Basic creation stores the sheet and intended_path."""
        intent = PathIntent.objects.create(
            character_sheet=self.sheet,
            intended_path=self.path,
        )
        assert intent.pk is not None
        assert intent.character_sheet_id == self.sheet.pk
        assert intent.intended_path_id == self.path.pk
        assert intent.declared_at is not None

    def test_onetone_constraint_raises_on_duplicate(self) -> None:
        """Creating a second PathIntent for the same sheet raises IntegrityError."""
        PathIntent.objects.create(character_sheet=self.sheet, intended_path=self.path)
        second_path = PathFactory()
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PathIntent.objects.create(
                    character_sheet=self.sheet,
                    intended_path=second_path,
                )

    def test_update_or_create_replaces_intended_path(self) -> None:
        """update_or_create with a new path overwrites the existing row."""
        PathIntent.objects.create(character_sheet=self.sheet, intended_path=self.path)
        new_path = PathFactory()
        intent, created = PathIntent.objects.update_or_create(
            character_sheet=self.sheet,
            defaults={"intended_path": new_path},
        )
        assert created is False
        assert intent.intended_path_id == new_path.pk
        assert PathIntent.objects.filter(character_sheet=self.sheet).count() == 1

    def test_str(self) -> None:
        """__str__ includes the sheet id and path name."""
        intent = PathIntent.objects.create(character_sheet=self.sheet, intended_path=self.path)
        s = str(intent)
        assert str(self.sheet.pk) in s
        assert str(self.path.name) in s


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


URL = "/api/progression/path-intent/"


class PathIntentAPIBaseTests(TestCase):
    """Base class: authenticated client + one character sheet."""

    def setUp(self) -> None:
        # NOTE: Never create Evennia characters in setUpTestData.
        self.account = AccountFactory()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)
        self.path = PathFactory(is_active=True)

        self.client = APIClient()
        self.client.force_authenticate(user=self.account)  # type: ignore[arg-type]
        PathIntent.flush_instance_cache()


class PathIntentGetTests(PathIntentAPIBaseTests):
    """Tests for GET /api/progression/path-intent/."""

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_get_no_intent_returns_null(self, mock_get_char: object) -> None:
        """GET with no declared intent returns 200 with {"intent": null}."""
        mock_get_char.return_value = self.character
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["intent"] is None

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_get_with_intent_returns_data(self, mock_get_char: object) -> None:
        """GET returns the declared intent with nested path data."""
        mock_get_char.return_value = self.character
        PathIntent.objects.create(character_sheet=self.sheet, intended_path=self.path)
        PathIntent.flush_instance_cache()
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["intent"] is not None
        assert response.data["intent"]["intended_path"]["name"] == self.path.name
        assert response.data["intent"]["intended_path"]["stage"] == self.path.stage
        assert "declared_at" in response.data["intent"]

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_get_no_character_returns_404(self, mock_get_char: object) -> None:
        """GET with no character context returns 404."""
        mock_get_char.return_value = None
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_unauthenticated_returns_403(self) -> None:
        """Unauthenticated GET is forbidden."""
        self.client.force_authenticate(user=None)
        response = self.client.get(URL)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class PathIntentPutTests(PathIntentAPIBaseTests):
    """Tests for PUT /api/progression/path-intent/."""

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_put_declares_intent(self, mock_get_char: object) -> None:
        """PUT creates a PathIntent and returns the intent shape."""
        mock_get_char.return_value = self.character
        response = self.client.put(URL, {"path_id": self.path.pk}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["intent"]["intended_path"]["name"] == self.path.name
        assert response.data["intent"]["intended_path"]["stage"] == self.path.stage
        assert PathIntent.objects.filter(character_sheet=self.sheet).count() == 1

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_put_replaces_existing_intent(self, mock_get_char: object) -> None:
        """Second PUT replaces the existing row; still only one row."""
        mock_get_char.return_value = self.character
        PathIntent.objects.create(character_sheet=self.sheet, intended_path=self.path)
        PathIntent.flush_instance_cache()
        new_path = PathFactory(is_active=True)
        response = self.client.put(URL, {"path_id": new_path.pk}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert PathIntent.objects.filter(character_sheet=self.sheet).count() == 1
        assert response.data["intent"]["intended_path"]["name"] == new_path.name

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_put_nonexistent_path_returns_400(self, mock_get_char: object) -> None:
        """PUT with a non-existent path_id returns 400."""
        mock_get_char.return_value = self.character
        response = self.client.put(URL, {"path_id": 999999}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_put_inactive_path_returns_400(self, mock_get_char: object) -> None:
        """PUT with an inactive path returns 400."""
        mock_get_char.return_value = self.character
        inactive_path = PathFactory(is_active=False)
        response = self.client.put(URL, {"path_id": inactive_path.pk}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_put_missing_path_id_returns_400(self, mock_get_char: object) -> None:
        """PUT without path_id returns 400."""
        mock_get_char.return_value = self.character
        response = self.client.put(URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_put_no_character_returns_404(self, mock_get_char: object) -> None:
        """PUT with no character context returns 404."""
        mock_get_char.return_value = None
        response = self.client.put(URL, {"path_id": self.path.pk}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_put_unauthenticated_returns_403(self) -> None:
        """Unauthenticated PUT is forbidden."""
        self.client.force_authenticate(user=None)
        response = self.client.put(URL, {"path_id": self.path.pk}, format="json")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class PathIntentDeleteTests(PathIntentAPIBaseTests):
    """Tests for DELETE /api/progression/path-intent/."""

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_delete_removes_intent(self, mock_get_char: object) -> None:
        """DELETE removes the row and returns 204."""
        mock_get_char.return_value = self.character
        PathIntent.objects.create(character_sheet=self.sheet, intended_path=self.path)
        PathIntent.flush_instance_cache()
        response = self.client.delete(URL)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not PathIntent.objects.filter(character_sheet=self.sheet).exists()

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_delete_when_none_is_idempotent(self, mock_get_char: object) -> None:
        """DELETE when no intent exists returns 204 (idempotent)."""
        mock_get_char.return_value = self.character
        response = self.client.delete(URL)
        assert response.status_code == status.HTTP_204_NO_CONTENT

    @patch("world.progression.views.PathIntentViewSet._get_character")
    def test_delete_no_character_returns_404(self, mock_get_char: object) -> None:
        """DELETE with no character context returns 404."""
        mock_get_char.return_value = None
        response = self.client.delete(URL)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_unauthenticated_returns_403(self) -> None:
        """Unauthenticated DELETE is forbidden."""
        self.client.force_authenticate(user=None)
        response = self.client.delete(URL)
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class PathIntentDifferentAccountTests(TestCase):
    """Verify that a character belonging to a different account is not accessible."""

    def setUp(self) -> None:
        # Account A owns character A.
        self.account_a = AccountFactory()
        self.character_a = CharacterFactory()
        self.sheet_a = CharacterSheetFactory(character=self.character_a, primary_persona=False)
        self.path = PathFactory(is_active=True)

        # Account B tries to use character A's ID.
        self.account_b = AccountFactory()

        self.client = APIClient()
        self.client.force_authenticate(user=self.account_b)  # type: ignore[arg-type]
        PathIntent.flush_instance_cache()

    def test_get_with_unowned_character_returns_404(self) -> None:
        """GET resolves to 404 when the character is not in the user's available list."""
        # account_b.get_available_characters() will return an empty list (no roster wiring),
        # so _get_character returns None → 404.
        response = self.client.get(URL, HTTP_X_CHARACTER_ID=str(self.character_a.id))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_put_with_unowned_character_returns_404(self) -> None:
        """PUT returns 404 when the character doesn't belong to the requesting account."""
        response = self.client.put(
            URL,
            {"path_id": self.path.pk},
            format="json",
            HTTP_X_CHARACTER_ID=str(self.character_a.id),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
