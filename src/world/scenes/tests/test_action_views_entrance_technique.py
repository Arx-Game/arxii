"""REST entrance path for technique-driven combat entrances (#2183 Task 8 fold-in).

``SceneActionRequestViewSet.create()`` used to route EVERY ``action_key`` through
``create_action_request`` — a technique-as-``ActionEnhancement`` consent flow that
has no "entrance" enhancement row and therefore always 400ed for the frontend's
technique-driven entrance call. This module proves the new branch
(``_create_technique_entrance``) dispatches straight through ``EntranceAction``
(mirroring telnet ``CmdEnter``) and that ``entry_interaction_id`` survives the
serializer to land on the created ``DramaticMomentSuggestion.interaction``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from world.magic.factories import CharacterResonanceFactory, ensure_dramatic_entrance_content
from world.magic.models.dramatic_moment import DramaticMomentSuggestion
from world.scenes.action_views import SceneActionRequestViewSet
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import create_interaction
from world.scenes.tests.cast_test_helpers import (
    CastScenarioMixin,
    grant_technique,
    make_benign_castable_technique,
)


def _actor_user(character):
    """A fake authenticated user whose ``puppet`` is ``character`` (mirrors
    ``world.relationships.tests.test_update_viewset._actor_user``)."""
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=character.db_account_id,
        puppet=character,
    )


def _make_check_mock(success_level: int) -> MagicMock:
    return MagicMock(
        success_level=success_level,
        outcome=MagicMock(name="Outcome"),
        outcome_name="Success" if success_level > 0 else "Failure",
    )


class EntranceTechniqueRestDispatchTests(CastScenarioMixin):
    """POST /api/action-requests/ with action_key=entrance + technique_id."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        character = cls.caster.character_sheet.character
        character.db_location = cls.scene.location
        character.save()

        moment_type = ensure_dramatic_entrance_content()
        CharacterResonanceFactory(
            character_sheet=cls.caster.character_sheet,
            resonance=moment_type.resonance,
        )

    def _post(self, payload: dict):
        factory = APIRequestFactory()
        request = factory.post(reverse("sceneactionrequest-list"), payload, format="json")
        force_authenticate(request, user=_actor_user(self.caster.character_sheet.character))
        view = SceneActionRequestViewSet.as_view({"post": "create"})
        return view(request)

    def test_entrance_technique_dispatches_and_carries_interaction(self) -> None:
        """A successful entrance-technique REST call threads entry_interaction_id
        through to the created DramaticMomentSuggestion."""
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        entry_interaction = create_interaction(
            persona=self.caster,
            content="Someone makes an entrance.",
            mode=InteractionMode.POSE,
            scene=self.scene,
        )

        with patch("actions.services.perform_check", return_value=_make_check_mock(3)):
            response = self._post(
                {
                    "scene": self.scene.pk,
                    "action_key": "entrance",
                    "technique_id": technique.pk,
                    "entry_interaction_id": entry_interaction.pk,
                }
            )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        suggestion = DramaticMomentSuggestion.objects.get(
            character_sheet=self.caster.character_sheet
        )
        assert suggestion.interaction_id == entry_interaction.pk

    def test_entrance_technique_without_interaction_id_still_dispatches(self) -> None:
        """Omitting entry_interaction_id (e.g. an ephemeral scene) still succeeds."""
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        with patch("actions.services.perform_check", return_value=_make_check_mock(3)):
            response = self._post(
                {
                    "scene": self.scene.pk,
                    "action_key": "entrance",
                    "technique_id": technique.pk,
                }
            )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        suggestion = DramaticMomentSuggestion.objects.get(
            character_sheet=self.caster.character_sheet
        )
        assert suggestion.interaction_id is None

    def test_no_puppet_returns_400(self) -> None:
        """No puppeted character — resolved actor is None."""
        technique = make_benign_castable_technique()
        grant_technique(self.caster, technique)

        factory = APIRequestFactory()
        request = factory.post(
            reverse("sceneactionrequest-list"),
            {"scene": self.scene.pk, "action_key": "entrance", "technique_id": technique.pk},
            format="json",
        )
        force_authenticate(
            request,
            user=SimpleNamespace(is_authenticated=True, is_staff=False, pk=None, puppet=None),
        )
        view = SceneActionRequestViewSet.as_view({"post": "create"})
        response = view(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
