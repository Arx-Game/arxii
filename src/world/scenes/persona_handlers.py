"""Handlers for persona-level data scoped to a scene.

These live outside ``models.py`` so the ``Scene`` model itself does not issue
participant/persona queries — the handler owns the cached resolution path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.utils.functional import cached_property

if TYPE_CHECKING:
    from world.scenes.models import Persona, Scene


class ScenePersonaHandler:
    """Resolves cached persona data for the participants of a single scene.

    Instantiated once per ``Scene`` (via ``Scene.persona_handler``) and reused
    so repeated target lookups during a scene do not re-query participants.
    """

    def __init__(self, scene: Scene) -> None:
        self.scene = scene

    @cached_property
    def active_participant_personas(self) -> list[Persona]:
        """Return the active persona for each account participating in this scene.

        Walks the scene's cached participations, resolves each participant's
        active persona from cached player/tenure data, and returns the list.
        """
        from evennia_extensions.models import PlayerData  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        participations = self.scene.participations_cached
        account_ids = {p.account_id for p in participations}
        if not account_ids:
            return []

        player_data_map = {
            pd.account_id: pd for pd in PlayerData.objects.filter(account_id__in=account_ids)
        }

        personas: list[Persona] = []
        for account_id in account_ids:
            player_data = player_data_map.get(account_id)
            if player_data is None:
                continue
            for character in player_data.get_available_characters():
                try:
                    sheet = character.sheet_data
                    persona = active_persona_for_sheet(sheet)
                except (AttributeError, ObjectDoesNotExist):
                    continue
                personas.append(persona)
        return personas
