"""Crossover invite lifecycle — co-GM consent to link stories to a shared event (#2002).

A GM invites another story (by its Lead GM's consent) into a shared event.
Accepting records consent and defers EpisodeScene creation until the scene
spawns (or links immediately if the event already has an active scene). The
invited story's Lead GM is enrolled as a scene GM so they can co-run.

The existing per-beat stakes machinery already walks all EpisodeScene rows for
a scene and is idempotent (see ``staked_unsatisfied_beats_for_scene`` /
``activate_stakes_contract`` in ``world.stories.services.stakes``), so no new
stakes engine is needed — the crossover layer only adds consent + linkage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.stories.constants import CrossoverInviteStatus
from world.stories.exceptions import (
    CrossoverAuthorityError,
    CrossoverStateError,
)
from world.stories.models import CrossoverInvite, EpisodeScene

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.events.models import Event
    from world.gm.models import GMProfile
    from world.scenes.models import Scene
    from world.stories.models import Episode, Story


def _story_owned_by(story: Story, account: AccountDB) -> bool:
    """True if account is an owner (Lead GM) of the story."""
    return story.owners.filter(id=account.id).exists()


def create_crossover_invite(
    *,
    from_gm: GMProfile,
    event: Event,
    to_story: Story,
    proposed_episode: Episode | None = None,
    message: str = "",
) -> CrossoverInvite:
    """Create a PENDING crossover invite.

    Args:
        from_gm: The GMProfile inviting another story into the shared event.
        event: The shared Event both stories will resolve beats in.
        to_story: The story being invited.
        proposed_episode: Optional specific episode to link; null lets the
            Lead GM pick on accept.
        message: Optional note from the inviting GM.

    Returns:
        The newly created PENDING CrossoverInvite.

    Raises:
        CrossoverError: If a PENDING invite already exists for (event, to_story),
            or if proposed_episode does not belong to to_story.
    """
    if proposed_episode is not None and proposed_episode.chapter.story_id != to_story.pk:
        msg = "proposed_episode does not belong to to_story."
        raise CrossoverStateError(msg)
    existing = CrossoverInvite.objects.filter(
        event=event, to_story=to_story, status=CrossoverInviteStatus.PENDING
    ).first()
    if existing is not None:
        msg = (
            f"A pending crossover invite already exists for event #{event.pk},"
            f" story #{to_story.pk}."
        )
        raise CrossoverStateError(msg)
    return CrossoverInvite.objects.create(
        event=event,
        from_gm=from_gm,
        to_story=to_story,
        proposed_episode=proposed_episode,
        message=message,
    )


def accept_crossover_invite(
    invite: CrossoverInvite,
    *,
    accepting_account: AccountDB,
    accepted_episode: Episode | None = None,
    response_note: str = "",
) -> CrossoverInvite:
    """Accept a PENDING invite. Only the invited story's Lead GM (owner) may accept.

    Creates the EpisodeScene link if the event already has an active scene;
    otherwise the link is deferred to scene-spawn time (handled by
    :func:`link_accepted_episode_scene`, called from ``start_event``).

    Args:
        invite: Must be PENDING.
        accepting_account: Must be an owner of ``invite.to_story``.
        accepted_episode: The episode to link. Defaults to ``invite.proposed_episode``.
        response_note: Optional Lead GM response.

    Returns:
        The updated (ACCEPTED) invite.

    Raises:
        CrossoverError: If the account is not an owner, the invite is not
            PENDING, no episode is available to link, or the episode does not
            belong to the invited story.
    """
    if not _story_owned_by(invite.to_story, accepting_account):
        msg = "Only the invited story's Lead GM may accept a crossover invite."
        raise CrossoverAuthorityError(msg)
    if invite.status != CrossoverInviteStatus.PENDING:
        msg = f"CrossoverInvite {invite.pk} is not PENDING (status={invite.status!r})."
        raise CrossoverStateError(msg)
    episode = accepted_episode or invite.proposed_episode
    if episode is None:
        msg = "No episode to link: supply accepted_episode or set proposed_episode on the invite."
        raise CrossoverStateError(msg)
    if episode.chapter.story_id != invite.to_story_id:
        msg = "accepted_episode does not belong to the invited story."
        raise CrossoverStateError(msg)
    invite.status = CrossoverInviteStatus.ACCEPTED
    invite.accepted_episode = episode
    invite.response_note = response_note
    invite.responded_at = timezone.now()
    invite.save(
        update_fields=[
            "status",
            "accepted_episode",
            "response_note",
            "responded_at",
            "updated_at",
        ]
    )
    _link_episode_scene_for_event(invite, episode)
    return invite


def decline_crossover_invite(
    invite: CrossoverInvite,
    *,
    responding_account: AccountDB,
    response_note: str = "",
) -> CrossoverInvite:
    """Decline a PENDING invite. Only the invited story's Lead GM may decline.

    Args:
        invite: Must be PENDING.
        responding_account: Must be an owner of ``invite.to_story``.
        response_note: Optional Lead GM response.

    Returns:
        The updated (DECLINED) invite.

    Raises:
        CrossoverError: If the account is not an owner or the invite is not PENDING.
    """
    if not _story_owned_by(invite.to_story, responding_account):
        msg = "Only the invited story's Lead GM may decline a crossover invite."
        raise CrossoverAuthorityError(msg)
    if invite.status != CrossoverInviteStatus.PENDING:
        msg = f"CrossoverInvite {invite.pk} is not PENDING (status={invite.status!r})."
        raise CrossoverStateError(msg)
    invite.status = CrossoverInviteStatus.DECLINED
    invite.response_note = response_note
    invite.responded_at = timezone.now()
    invite.save(update_fields=["status", "response_note", "responded_at", "updated_at"])
    return invite


def withdraw_crossover_invite(
    invite: CrossoverInvite,
    *,
    withdrawing_account: AccountDB,
) -> CrossoverInvite:
    """Withdraw a PENDING invite. Only the sender (from_gm's account) may withdraw.

    Args:
        invite: Must be PENDING.
        withdrawing_account: Must be ``invite.from_gm.account``.

    Returns:
        The updated (WITHDRAWN) invite.

    Raises:
        CrossoverError: If the account is not the sender or the invite is not PENDING.
    """
    if invite.from_gm.account_id != withdrawing_account.id:
        msg = "Only the inviting GM may withdraw a crossover invite."
        raise CrossoverAuthorityError(msg)
    if invite.status != CrossoverInviteStatus.PENDING:
        msg = f"CrossoverInvite {invite.pk} is not PENDING (status={invite.status!r})."
        raise CrossoverStateError(msg)
    invite.status = CrossoverInviteStatus.WITHDRAWN
    invite.responded_at = timezone.now()
    invite.save(update_fields=["status", "responded_at", "updated_at"])
    return invite


def link_accepted_episode_scene(invite: CrossoverInvite, scene: Scene) -> bool:
    """Link an accepted invite's episode to a freshly-spawned scene.

    Called from the scene-spawn path (``start_event``). Returns True if a link
    was created (or already existed). Also enrolls the invited story's Lead GM
    as a scene GM (``SceneParticipation.is_gm=True``) so they can co-run.

    Safe to call for non-accepted invites — returns False without side effects.
    """
    if invite.status != CrossoverInviteStatus.ACCEPTED or invite.accepted_episode is None:
        return False
    _create_episode_scene_link(episode=invite.accepted_episode, scene=scene)
    _enroll_lead_gm_on_scene(invite, scene)
    return True


def link_accepted_invites_for_scene(scene: Scene, event: Event | None) -> int:
    """Link all accepted crossover invites for an event's freshly-spawned scene.

    Called from ``start_event`` after the Scene is created. Returns the count
    of invites linked. Each gets its EpisodeScene row + Lead GM enrollment.
    """
    if event is None:
        return 0
    linked = 0
    for invite in CrossoverInvite.objects.filter(
        event=event, status=CrossoverInviteStatus.ACCEPTED
    ).select_related("accepted_episode"):
        if link_accepted_episode_scene(invite, scene):
            linked += 1
    return linked


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _link_episode_scene_for_event(invite: CrossoverInvite, episode: Episode) -> None:
    """Create the EpisodeScene link if the event already has an active scene.

    If the event has no active scene yet, the link is deferred to scene-spawn
    time (handled by :func:`link_accepted_episode_scene`, called from
    ``start_event``).
    """
    scene = _active_scene_for_event(invite.event)
    if scene is None:
        return
    _create_episode_scene_link(episode=episode, scene=scene)


def _active_scene_for_event(event: Event) -> Scene | None:
    """Return the event's currently-active scene, if any. None otherwise.

    ``Scene.event`` is a direct FK; the ``unique_active_scene_per_event``
    constraint guarantees at most one active scene per event.
    """
    from world.scenes.models import Scene  # noqa: PLC0415

    return Scene.objects.filter(event=event, is_active=True).first()


def _create_episode_scene_link(*, episode: Episode, scene: Scene) -> EpisodeScene:
    """Create the EpisodeScene link idempotently (unique_together episode+scene)."""
    order = EpisodeScene.objects.filter(scene=scene).count()
    obj, _created = EpisodeScene.objects.get_or_create(
        episode=episode,
        scene=scene,
        defaults={"order": order},
    )
    return obj


def _enroll_lead_gm_on_scene(invite: CrossoverInvite, scene: Scene) -> None:
    """Mark the invited story's Lead GM(s) as scene GMs (SceneParticipation.is_gm=True).

    A story may have multiple owners; each gets enrolled. ``get_or_create``
    avoids duplicates if the owner is already a participant.
    """
    from world.scenes.models import SceneParticipation  # noqa: PLC0415

    for owner in invite.to_story.owners.all():
        SceneParticipation.objects.get_or_create(
            scene=scene,
            account=owner,
            defaults={"is_gm": True},
        )
