"""What a pose shows of its marks and waiting picks (#5327), from one builder.

The scene feed (``InteractionListSerializer``) and the live frame (``push_interaction``) both call
``act_marks_payload`` and ``pending_picks_payload``, so a refetch and a push read the same
fields for the same viewer. A viewer is who is reading: ``None`` is the room-wide live frame,
where nobody may undo anything and no waiting pick is shown (a frame goes to everyone present, and
a waiting pick is for the endorser, the poser, the scene's GM and staff alone). Whoever may see
more refetches the pose, because every change to a mark or a pick announces itself
(``notify_interaction_changed``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.scenes.types import ActMarkPayload, PendingPickPayload

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.magic.models import PoseEndorsement
    from world.scenes.models import Interaction


@dataclass(frozen=True)
class PoseViewer:
    """Who is reading a pose: the account, the sheets its characters have, and whether it is staff.

    ``sheet_ids`` are the character sheets the account plays, which is how the endorser and the
    poser are recognized.
    """

    account: AccountDB
    sheet_ids: frozenset[int]
    is_staff: bool


def _scene_gm(interaction: Interaction, viewer: PoseViewer | None) -> bool:
    """Whether ``viewer`` is the GM of the scene the pose belongs to (never an owner)."""
    if viewer is None or interaction.scene_id is None:
        return False
    return interaction.scene.is_gm(viewer.account)


def act_marks_payload(interaction: Interaction, viewer: PoseViewer | None) -> list[ActMarkPayload]:
    """The marks this pose carries: the resonance, the act's label and whether it was undone.

    ``can_undo`` is true only for staff and the scene's GM, on a mark nobody has undone.
    """
    marks = interaction.cached_act_marks
    if not marks:
        return []
    can_undo_any = viewer is not None and (viewer.is_staff or _scene_gm(interaction, viewer))
    rows: list[ActMarkPayload] = []
    for act in marks:
        grant = act.marked_grant
        if grant is None:
            continue
        undone = grant.nullified_at is not None
        rows.append(
            ActMarkPayload(
                grant_id=grant.pk,
                resonance_id=grant.resonance_id,
                resonance_name=grant.resonance.name,
                act_label=act.label,
                undone=undone,
                can_undo=can_undo_any and not undone,
            )
        )
    return rows


def _endorser_name(endorsement: PoseEndorsement) -> str:
    """The face the endorser wore when endorsing, as the endorser badges show it."""
    persona = endorsement.endorser_persona or next(
        iter(endorsement.endorser_sheet.cached_primary_persona), None
    )
    return persona.name if persona is not None else ""


def pending_picks_payload(
    interaction: Interaction, viewer: PoseViewer | None
) -> list[PendingPickPayload]:
    """The picks on this pose still waiting for the poser, for the people who may see them.

    The endorser sees her own (``mine``). The poser, the scene's GM and staff see all of them and
    may answer (``can_answer``). Everyone else, and the room-wide live frame, sees none.
    """
    if viewer is None:
        return []
    waiting = [row for row in interaction.cached_endorsements if row.awaiting_acceptance]
    if not waiting:
        return []
    poser_sheet_id = interaction.persona.character_sheet_id
    can_answer = (
        viewer.is_staff or poser_sheet_id in viewer.sheet_ids or _scene_gm(interaction, viewer)
    )
    rows: list[PendingPickPayload] = []
    for row in waiting:
        mine = row.endorser_sheet_id in viewer.sheet_ids
        if not (mine or can_answer):
            continue
        rows.append(
            PendingPickPayload(
                endorsement_id=row.pk,
                resonance_id=row.resonance_id,
                resonance_name=row.resonance.name,
                endorser_name=_endorser_name(row),
                mine=mine,
                can_answer=can_answer,
            )
        )
    return rows


__all__ = ["PoseViewer", "act_marks_payload", "pending_picks_payload"]
