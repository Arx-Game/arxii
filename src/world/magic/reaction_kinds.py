"""Make an Entrance as a reaction-window kind (#904 first consumer).

The window opens on an ENTRY pose (``PoseKind.ENTRY``); present players
react by picking one of the entrance-maker's claimed resonances. Each
reaction delegates to ``create_scene_entry_endorsement`` (Spec C §2.3) —
the endorsement row stays the mechanical record and the resonance grant
fires immediately, exactly as the existing API path does. ``WindowReaction``
is the generic social-surface record on top.

Registered from ``MagicConfig.ready()`` so scenes never imports magic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from world.magic.exceptions import EndorsementValidationError
from world.scenes.reaction_services import ReactionChoice, ReactionKindConfig

if TYPE_CHECKING:
    from world.scenes.reaction_models import ReactionWindow, WindowReaction


def _entrance_choices(window: ReactionWindow) -> list[ReactionChoice]:
    """The entrance-maker's claimed resonances, as reaction chips."""
    from world.magic.models import CharacterResonance  # noqa: PLC0415

    rows = (
        CharacterResonance.objects.filter(
            character_sheet_id=window.interaction.persona.character_sheet_id
        )
        .select_related("resonance")
        .order_by("resonance__name")
    )
    return [ReactionChoice(slug=str(row.resonance_id), label=row.resonance.name) for row in rows]


def _endorse_entrance(window: ReactionWindow, reaction: WindowReaction) -> None:
    """Acclaim an entrance: create the Spec C endorsement (immediate grant)."""
    from world.magic.models import Resonance  # noqa: PLC0415
    from world.magic.services.gain import create_scene_entry_endorsement  # noqa: PLC0415

    resonance = Resonance.objects.get(pk=int(reaction.choice))
    try:
        create_scene_entry_endorsement(
            endorser_sheet=reaction.reactor_persona.character_sheet,
            endorsee_sheet=window.interaction.persona.character_sheet,
            scene=window.scene,
            resonance=resonance,
        )
    except EndorsementValidationError as exc:
        raise ValidationError(exc.user_message) from exc


ENTRANCE_KIND = ReactionKindConfig(
    choices_for=_entrance_choices,
    on_reaction=_endorse_entrance,
)
