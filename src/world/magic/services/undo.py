"""Undoing a resonance reward (#5327).

Staff undo any grant. The scene's GM (``Scene.is_gm``, never an owner) undoes the six
scene-bound rewards (``REWARD_SCENE_PATHS``: a mark, a pose endorsement, a dramatic-moment tag,
an entrance endorsement, an outfit endorsement and an entry flourish) in a scene they GM, when
they can read the pose that carries it. The ledger row stays, stamped ``nullified_at`` and
``nullified_by``, so history is kept and the act it paid for can never be marked again.

What ``grant_resonance`` did, and what undo does about each part:

- balance and lifetime total: both fall by the amount, each stopping at 0. Resonance the
  character already spent stays spent.
- the aura: recomputed after the totals fall.
- pledge favor, aura thresholds and achievements, a drift conversion offer, giving in to a
  Compulsion, a distinction rank-up: left as they are.
- the payer's fatigue and the bonus check's roll: left as they are.
- a reflection still waiting on the grant: withdrawn. One a settling rite already applied
  stays.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from world.magic.constants import GainSource
from world.magic.exceptions import ResonanceUndoError
from world.magic.models import CharacterResonance, Reflection, ResonanceGrant
from world.magic.services.gain_fatigue import send_player_line
from world.scenes.interaction_services import notify_interaction_changed
from world.scenes.models import Interaction
from world.scenes.services import is_scene_gm_or_staff

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.accounts.models import AccountDB

    from world.scenes.models import Scene

_NOT_ALLOWED = "Only staff or the GM of the scene it happened in can undo that reward."
_ALREADY_UNDONE = "That reward was already undone."


class RewardScenePath(NamedTuple):
    """Where one kind of reward keeps the scene it happened in and the pose that carries it.

    Both are paths from a ``ResonanceGrant`` through its typed source row, written as ORM lookups
    (``source_pose_endorsement__interaction``) so one table serves the Python walk below and
    the undo endpoint's queryset. ``pose`` is None for a reward no pose carries.
    """

    source: str
    scene: str
    pose: str | None


#: Every reward a scene's GM may undo, and nothing else: the six scene-bound sources. Any other
#: source (a staff grant, a residence trickle, a mission reward, ...) has no scene, so only staff
#: undo it. A mark carried by a journal entry has a null pose and scene, so only staff undo it.
REWARD_SCENE_PATHS: tuple[RewardScenePath, ...] = (
    RewardScenePath(
        GainSource.MARKED_ACT,
        "marked_act__marked_interaction__scene",
        "marked_act__marked_interaction",
    ),
    RewardScenePath(
        GainSource.POSE_ENDORSEMENT,
        "source_pose_endorsement__interaction__scene",
        "source_pose_endorsement__interaction",
    ),
    RewardScenePath(
        GainSource.DRAMATIC_MOMENT,
        "source_dramatic_moment__scene",
        "source_dramatic_moment__interaction",
    ),
    RewardScenePath(
        GainSource.SCENE_ENTRY,
        "source_scene_entry_endorsement__scene",
        "source_scene_entry_endorsement__entry_interaction",
    ),
    RewardScenePath(
        GainSource.STYLE_PRESENTATION,
        "source_style_presentation_endorsement__scene",
        None,
    ),
    RewardScenePath(
        GainSource.ENTRY_FLOURISH,
        "source_entry_flourish__scene",
        None,
    ),
)


def _follow(grant: ResonanceGrant, path: str) -> Any:
    """Walk ``path`` (ORM-style ``a__b__c``) from ``grant``; None when a link is missing."""
    node: Any = grant
    for step in path.split("__"):
        try:
            node = getattr(node, step)
        except ObjectDoesNotExist:
            return None
        if node is None:
            return None
    return node


def _reward_scene(grant: ResonanceGrant) -> tuple[Scene | None, Interaction | None]:
    """The scene a reward happened in and the pose that carries it, when it has either.

    Read through ``REWARD_SCENE_PATHS``, the same table ``undoable_in_scenes`` filters by.
    """
    for entry in REWARD_SCENE_PATHS:
        if entry.source != grant.source:
            continue
        scene = _follow(grant, entry.scene)
        pose = _follow(grant, entry.pose) if entry.pose is not None else None
        return scene, pose
    return None, None


def undoable_in_scenes(scene_ids: QuerySet | list[int], readable_poses: QuerySet) -> Q:
    """The filter that keeps the grants a GM of ``scene_ids`` may undo (#5327).

    One branch per entry of ``REWARD_SCENE_PATHS``: the reward belongs to one of the scenes and,
    when a pose carries it, the GM can read that pose (``readable_poses``). A reward in a scene
    whose pose she cannot read is outside the filter, so the endpoint answers 404 for it and
    never reveals it exists.
    """
    combined = Q()
    for entry in REWARD_SCENE_PATHS:
        branch = Q(**{f"{entry.scene}__in": scene_ids})
        if entry.pose is not None:
            branch &= Q(**{f"{entry.pose}__isnull": True}) | Q(
                **{f"{entry.pose}__in": readable_poses}
            )
        combined |= branch
    return combined


def may_undo_grant(by: AccountDB, grant: ResonanceGrant) -> bool:
    """Whether ``by`` may undo ``grant``: staff, or the GM of the scene it happened in.

    The GM must also be able to read the pose that carries it, as the scene log decides
    (a very-private pose is read by nobody outside it). A co-owner who is not the scene's GM
    may not.
    """
    if not by.is_authenticated:
        return False
    if by.is_staff:
        return True
    scene, interaction = _reward_scene(grant)
    if scene is None or not is_scene_gm_or_staff(by, scene):
        return False
    if interaction is None:
        return True
    return Interaction.objects.readable_by(by).filter(pk=interaction.pk).exists()


def _reward_phrase(grant: ResonanceGrant) -> str:
    """What the reward was, worded for the player who loses it ("your Mercy reward ...")."""
    name = grant.resonance.name
    if grant.deed_label:
        return f"your {name} reward for {grant.deed_label}"
    if grant.source == GainSource.POSE_ENDORSEMENT:
        return f"your {name} reward from an endorsement of your pose"
    if grant.source == GainSource.DRAMATIC_MOMENT:
        return f"your {name} reward from a GM's tag"
    return f"your {name} reward from {grant.get_source_display()}"


def _undone_line(
    grant: ResonanceGrant, by: AccountDB, *, balance_fell: int, lifetime_fell: int
) -> str:
    """The private line the player whose reward was undone reads.

    It names the role that undid it, never the account: players are anonymous to each other.
    """
    who = "Staff" if by.is_staff else "The scene's GM"
    line = (
        f"{who} undid {_reward_phrase(grant)}. "
        f"Your {grant.resonance.name} falls by {lifetime_fell}."
    )
    if balance_fell < lifetime_fell:
        line += " What you already spent stays spent."
    return line


@transaction.atomic
def undo_resonance_grant(grant: ResonanceGrant, by: AccountDB) -> ResonanceGrant:
    """Undo ``grant``: lower the character's totals, stamp the ledger row, tell her player.

    Returns the grant, now carrying ``nullified_at`` and ``nullified_by``.

    Raises:
        ResonanceUndoError: ``by`` may not undo it, or it was already undone.
    """
    from world.magic.services.aura import recompute_aura  # noqa: PLC0415

    if not may_undo_grant(by, grant):
        raise ResonanceUndoError(_NOT_ALLOWED)
    row = (
        ResonanceGrant.objects.select_for_update()
        .filter(pk=grant.pk, nullified_at__isnull=True)
        .select_related("resonance", "character_sheet")
        .first()
    )
    if row is None:
        raise ResonanceUndoError(_ALREADY_UNDONE)

    balance_fell = 0
    lifetime_fell = 0
    held = (
        CharacterResonance.objects.select_for_update()
        .filter(character_sheet_id=row.character_sheet_id, resonance_id=row.resonance_id)
        .first()
    )
    if held is not None:
        balance_fell = min(row.amount, held.balance)
        lifetime_fell = min(row.amount, held.lifetime_earned)
        held.balance -= balance_fell
        held.lifetime_earned -= lifetime_fell
        held.save(update_fields=["balance", "lifetime_earned"])

    row.nullified_at = timezone.now()
    row.nullified_by = by
    row.save(update_fields=["nullified_at", "nullified_by"])

    waiting = Reflection.objects.filter(grant=row, rite__isnull=True).first()
    if waiting is not None:
        waiting.delete()

    recompute_aura(row.character_sheet)

    # The pose that carries a mark shows it struck through: drop its cached marks and tell its
    # audience to refetch.
    _scene, carrier = _reward_scene(row)
    if carrier is not None:
        del carrier.cached_act_marks
        notify_interaction_changed(carrier)

    line = _undone_line(row, by, balance_fell=balance_fell, lifetime_fell=lifetime_fell)
    transaction.on_commit(
        lambda: send_player_line(row.character_sheet, line, ooc_note="A reward undone")
    )
    return row


__all__ = [
    "REWARD_SCENE_PATHS",
    "RewardScenePath",
    "may_undo_grant",
    "undo_resonance_grant",
    "undoable_in_scenes",
]
