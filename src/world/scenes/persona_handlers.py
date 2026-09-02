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

    def active_participant_personas(self, *, exclude_gm_accounts: bool = False) -> list[Persona]:
        """Return the active persona for each account participating in this scene.

        Walks the scene's cached participations and resolves each participant's
        active persona from already-loaded player/tenure data. No new queries.

        ``exclude_gm_accounts`` skips participations with ``is_gm=True`` (#3565):
        a running story scenario's party is the PLAYERS in the scene, not the
        GM administering it -- ``world.missions.services.run.
        start_scenario_for_scene`` sets this so a GM whose own PC happens to be
        present does not accidentally become a ``MissionParticipant`` (and thus
        a voter) in the party's own scenario run, matching
        ``world.scenes.scenario_services``'s "Lead GM (not a participant)"
        contract. Every other caller (combat, boundaries, decisive checks, the
        scene-close sweep, etc.) keeps the old default and is unaffected.
        """
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        personas: list[Persona] = []
        for participation in self.scene.participations_cached:
            if exclude_gm_accounts and participation.is_gm:
                continue
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
