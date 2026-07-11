"""Kudos as a reaction-window kind (#911).

A player acclaims another player's pose; the poser's *account* receives
kudos through the existing ``award_kudos`` service (full audit trail,
claimable later via the kudos economy). The window opens lazily on the
first reaction (``lazy_open``), so no per-pose rows exist until someone
actually reacts. One reaction per player per pose is enforced by the
window primitive's uniqueness.

Pose-voting deliberately did NOT become a kind: that capability is its own
axis, ``WeeklyVote`` (``cast_vote`` → progression views → the frontend
``VoteButton``/``VotesPanel``), with weekly XP settlement. #2161 landed the
frontend mounting end-to-end — ``VoteButton`` on each ``PoseUnit`` and
``VotesPanel`` on ``/xp-kudos`` — and re-ranked the scene highlight reel on
all-time vote counts. A voting kind would still be a parallel implementation
of an already-wired axis. The emoji ``InteractionReaction`` layer likewise
stays, per the ruling on #911 — Discord-style OOC reactions beside the
mechanical kudos chip. See ADR-0115 for the three-axes ruling (votes vs.
kudos vs. reactions) that keeps all three separate by design.

Registered from ``ProgressionConfig.ready()`` so scenes never imports
progression.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from world.scenes.reaction_services import ReactionChoice, ReactionKindConfig

if TYPE_CHECKING:
    from world.progression.models import KudosSourceCategory
    from world.scenes.reaction_models import ReactionWindow, WindowReaction

POSE_KUDOS_CATEGORY = "pose_kudos"

_KUDOS_CHOICES = [ReactionChoice(slug="kudos", label="Kudos")]


def _kudos_choices(window: ReactionWindow) -> list[ReactionChoice]:  # noqa: ARG001
    return _KUDOS_CHOICES


def _get_pose_kudos_category() -> KudosSourceCategory:
    from world.progression.models import KudosSourceCategory  # noqa: PLC0415

    category, _ = KudosSourceCategory.objects.get_or_create(
        name=POSE_KUDOS_CATEGORY,
        defaults={
            "display_name": "Pose Kudos",
            "description": "A player acclaimed one of your poses.",
            "default_amount": 1,
        },
    )
    return category


def _award_pose_kudos(window: ReactionWindow, reaction: WindowReaction) -> None:
    """Acclaim a pose: kudos to the poser's account via the audited service."""
    from world.progression.services.kudos import award_kudos  # noqa: PLC0415

    poser_account = window.interaction.persona.character_sheet.character.db_account
    if poser_account is None:
        msg = "There is no player behind that pose to acclaim."
        raise ValidationError(msg)

    category = _get_pose_kudos_category()
    # Award anonymously — do NOT pass awarded_by=reactor_account.
    # The reactor is the poser's acclaimer, not staff; surfacing their account
    # username to the poser would link an IC character to its OOC player account,
    # violating player-behind-character privacy (ADR-0033).
    award_kudos(
        account=poser_account,
        amount=category.default_amount,
        source_category=category,
        description=f"Kudos from {reaction.reactor_persona.name} for a pose",
    )


KUDOS_KIND = ReactionKindConfig(
    choices_for=_kudos_choices,
    on_reaction=_award_pose_kudos,
    lazy_open=True,
)
