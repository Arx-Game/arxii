"""WITNESS reaction kind (#2987).

PCs present at a public deed (a scene event tagged as bystander-witnessable)
may react: report it to the authorities, intervene, or say nothing. Report
resolves immediately, inside the reaction's own transaction — one
:func:`world.justice.services.report_witnessed_crime` call per crime tag on
the witnessed deed, against the deed-time actor persona. Intervene and ignore
carry no mechanical effect in this PR (justice stays NPC-driven: nothing
arrests, judges, or stops the actor here). Reports are anonymous — the kind is
registered ``public=False``, so no view or serializer exposes which persona
chose to report.

Registered from ``world.justice.apps.ready()`` so scenes never imports
justice. The window's deed lives on a ``WitnessReactionTarget`` (the
per-kind settlement-target pattern, mirroring ``SpreadAssistTarget``),
written when the witnessed act opens its window.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.scenes.reaction_services import (
    ReactionChoice,
    ReactionKindConfig,
    open_reaction_window,
)

if TYPE_CHECKING:
    from world.scenes.models import Interaction
    from world.scenes.reaction_models import ReactionWindow, WindowReaction
    from world.societies.models import LegendEntry

REPORT_CHOICE = "report"
INTERVENE_CHOICE = "intervene"
IGNORE_CHOICE = "ignore"

# PLACEHOLDER player-facing labels — rewrite in the project voice.
_CHOICES = [
    ReactionChoice(slug=REPORT_CHOICE, label="PLACEHOLDER: Report to authorities"),
    ReactionChoice(slug=INTERVENE_CHOICE, label="PLACEHOLDER: Intervene"),
    ReactionChoice(slug=IGNORE_CHOICE, label="PLACEHOLDER: Say nothing"),
]


def _witness_choices(window: ReactionWindow) -> list[ReactionChoice]:  # noqa: ARG001
    return _CHOICES


def _on_witness_reaction(window: ReactionWindow, reaction: WindowReaction) -> None:
    """Report mints one heat+reputation consequence per crime tag on the deed.

    Intervene and ignore return without effect — the ``WindowReaction`` row
    is already written by ``react_to_window`` regardless of choice.
    """
    if reaction.choice != REPORT_CHOICE:
        return

    from world.justice.models import WitnessReactionTarget  # noqa: PLC0415
    from world.justice.services import report_witnessed_crime  # noqa: PLC0415

    target = WitnessReactionTarget.objects.select_related("legend_entry").get(window=window)
    entry = target.legend_entry
    persona = entry.persona
    room = window.interaction.scene.location
    if room is None:
        # No scene location on record — fall back to the accused's own
        # current whereabouts, matching flag_crime's report-location logic.
        room = persona.character_sheet.character.location
    for tag in entry.crime_tags.select_related("crime_kind"):
        report_witnessed_crime(persona=persona, crime_kind=tag.crime_kind, room=room)


def open_witness_window(*, interaction: Interaction, entry: LegendEntry) -> ReactionWindow:
    """Open a WITNESS window on ``interaction`` for bystanders to react to ``entry``."""
    from world.justice.models import WitnessReactionTarget  # noqa: PLC0415
    from world.scenes.constants import ReactionWindowKind  # noqa: PLC0415

    window = open_reaction_window(interaction=interaction, kind=ReactionWindowKind.WITNESS)
    WitnessReactionTarget.objects.create(window=window, legend_entry=entry)
    return window


WITNESS_KIND = ReactionKindConfig(
    choices_for=_witness_choices,
    on_reaction=_on_witness_reaction,
    public=False,
    lazy_open=False,
)
