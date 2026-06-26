"""Handlers for persona-level data scoped to a scene.

These live outside ``models.py`` so the ``Scene`` model itself does not issue
participant/persona queries — the handler owns the cached resolution path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

if TYPE_CHECKING:
    from world.scenes.models import Persona, Scene


class ScenePersonaHandler:
    """Resolves cached persona data for the participants of a single scene.

    Instantiated once per ``Scene`` (via ``Scene.persona_handler``) and reused
    so repeated target lookups during a scene do not re-query participants.
    """

    def __init__(self, scene: Scene) -> None:
        self.scene = scene

    def active_participant_personas(self) -> list[Persona]:
        """Return the active persona for each account participating in this scene.

        Walks the scene's cached participations and resolves each participant's
        active persona from already-loaded player/tenure data. No new queries.
        """
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        personas: list[Persona] = []
        for participation in self.scene.participations_cached:
            try:
                player_data = participation.account.player_data
            except ObjectDoesNotExist:
                continue
            for character in player_data.get_available_characters():
                try:
                    sheet = character.sheet_data
                    persona = active_persona_for_sheet(sheet)
                except (AttributeError, ObjectDoesNotExist):
                    continue
                personas.append(persona)
        return personas
