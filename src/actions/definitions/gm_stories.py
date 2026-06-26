"""GM story lifecycle actions (#1495).

These actions expose the same lifecycle seams as the web ``StoryViewSet``,
``EpisodeViewSet``, and ``BeatViewSet`` action endpoints (complete story,
resolve episode, promote episode maturity, mark a GM_MARKED beat). They are
gated to the story's Lead GM, staff, or (for marking a beat) an approved
Assistant GM Claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from commands.exceptions import CommandError
from commands.utils.gm_resolution import resolve_actor_or_error
from world.gm.models import GMProfile
from world.stories.constants import (
    AssistantClaimStatus,
    BeatOutcome,
    StoryMaturity,
)
from world.stories.exceptions import StoryError
from world.stories.models import (
    AssistantGMClaim,
    Beat,
    Episode,
    Story,
    Transition,
)
from world.stories.services.beats import record_gm_marked_outcome
from world.stories.services.completion import complete_story
from world.stories.services.episodes import resolve_episode
from world.stories.services.maturity import promote_episode_maturity
from world.stories.services.progress import get_active_progress_for_story

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB


_NO_GM_PERMISSION = "Only the story's Lead GM or staff may do that."
_NO_MARK_PERMISSION = (
    "Only the story's Lead GM, staff, or an approved Assistant GM may mark a beat."
)
_NO_PROGRESS = "No active progress record found for this story."


def _resolve_account(actor: ObjectDB) -> AccountDB | None:
    """Return the actor's controlling account, or ``None`` if there isn't one."""
    try:
        return resolve_actor_or_error(actor)
    except CommandError:
        return None


def _story_for_object(instance: Story | Episode | Beat) -> Story:
    """Return the ``Story`` owning a Story, Episode, or Beat."""
    if isinstance(instance, Story):
        return instance
    if isinstance(instance, Episode):
        return instance.chapter.story
    return instance.episode.chapter.story


def _actor_is_lead_gm(account: AccountDB | None, story: Story) -> bool:
    """Return True for staff or the Lead GM of ``story.primary_table``."""
    if account is None:
        return False
    if account.is_staff:
        return True
    try:
        gm_profile = account.gm_profile
    except (GMProfile.DoesNotExist, AttributeError):
        return False
    if story.primary_table_id is None:
        return False
    return story.primary_table.gm_id == gm_profile.pk


def _actor_may_mark_beat(account: AccountDB | None, beat: Beat) -> bool:
    """Return True for staff, Lead GM, or an approved AssistantGMClaim holder."""
    story = _story_for_object(beat)
    if _actor_is_lead_gm(account, story):
        return True
    if account is None:
        return False
    try:
        gm_profile = account.gm_profile
    except (GMProfile.DoesNotExist, AttributeError):
        return False
    return AssistantGMClaim.objects.filter(
        beat=beat,
        assistant_gm=gm_profile,
        status=AssistantClaimStatus.APPROVED,
    ).exists()


def _lead_gm_deny_result(account: AccountDB | None, story: Story) -> ActionResult | None:
    """Return a permission-denied result, or ``None`` if the actor is allowed."""
    if not _actor_is_lead_gm(account, story):
        return ActionResult(success=False, message=_NO_GM_PERMISSION)
    return None


def _story_or_error(story_id: Any) -> tuple[Story | None, ActionResult | None]:
    """Fetch a ``Story`` by id, returning ``(story, error_result)``."""
    if story_id is None:
        return None, ActionResult(success=False, message="A story is required.")
    try:
        return Story.objects.get(pk=story_id), None
    except (Story.DoesNotExist, ValueError):
        return None, ActionResult(success=False, message="No story with that ID exists.")


def _episode_or_error(episode_id: Any) -> tuple[Episode | None, ActionResult | None]:
    """Fetch an ``Episode`` by id, returning ``(episode, error_result)``."""
    if episode_id is None:
        return None, ActionResult(success=False, message="An episode is required.")
    try:
        return Episode.objects.get(pk=episode_id), None
    except (Episode.DoesNotExist, ValueError):
        return None, ActionResult(success=False, message="No episode with that ID exists.")


def _beat_or_error(beat_id: Any) -> tuple[Beat | None, ActionResult | None]:
    """Fetch a ``Beat`` by id, returning ``(beat, error_result)``."""
    if beat_id is None:
        return None, ActionResult(success=False, message="A beat is required.")
    try:
        return Beat.objects.get(pk=beat_id), None
    except (Beat.DoesNotExist, ValueError):
        return None, ActionResult(success=False, message="No beat with that ID exists.")


def _chosen_transition_or_error(
    chosen_transition_id: Any,
) -> tuple[Transition | None, ActionResult | None]:
    """Return the requested transition, or an error if the id doesn't exist."""
    if chosen_transition_id is None:
        return None, None
    try:
        return Transition.objects.get(pk=chosen_transition_id), None
    except Transition.DoesNotExist:
        return None, ActionResult(success=False, message="No transition with that ID exists.")


def _target_maturity_or_error(target: Any) -> tuple[StoryMaturity | None, ActionResult | None]:
    """Parse a target maturity value, returning ``(maturity, error_result)``."""
    if target is None:
        return None, ActionResult(success=False, message="A target maturity is required.")
    try:
        return StoryMaturity(target), None
    except ValueError:
        return None, ActionResult(success=False, message="Invalid target maturity.")


def _beat_outcome_or_error(outcome: Any) -> tuple[BeatOutcome | None, ActionResult | None]:
    """Parse a beat outcome value, returning ``(outcome, error_result)``."""
    if outcome is None:
        return None, ActionResult(success=False, message="An outcome is required.")
    try:
        return BeatOutcome(outcome), None
    except ValueError:
        return None, ActionResult(success=False, message="Invalid beat outcome.")


@dataclass
class CompleteStoryAction(Action):
    """Explicitly conclude a story."""

    key: str = "complete_story"
    name: str = "Complete Story"
    icon: str = "book-check"
    category: str = "story"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        account = _resolve_account(actor)
        story, error = _story_or_error(kwargs.get("story_id"))
        if error:
            return error

        denial = _lead_gm_deny_result(account, story)
        if denial:
            return denial

        try:
            complete_story(story=story)
        except StoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True, message=f"Story '{story.title}' completed.")


@dataclass
class ResolveEpisodeAction(Action):
    """Advance a story's active progress through an episode transition."""

    key: str = "resolve_episode"
    name: str = "Resolve Episode"
    icon: str = "arrow-right-circle"
    category: str = "story"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        account = _resolve_account(actor)
        episode, error = _episode_or_error(kwargs.get("episode_id"))
        if error:
            return error

        story = _story_for_object(episode)
        denial = _lead_gm_deny_result(account, story)
        if denial:
            return denial

        progress = get_active_progress_for_story(story)
        if progress is None:
            return ActionResult(success=False, message=_NO_PROGRESS)

        chosen_transition, error = _chosen_transition_or_error(kwargs.get("chosen_transition_id"))
        if error:
            return error

        try:
            gm_profile = account.gm_profile
        except (GMProfile.DoesNotExist, AttributeError):
            gm_profile = None

        try:
            resolve_episode(
                progress=progress,
                chosen_transition=chosen_transition,
                gm_notes=kwargs.get("gm_notes", ""),
                resolved_by=gm_profile,
            )
        except StoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(success=True, message=f"Episode '{episode.title}' resolved.")


@dataclass
class PromoteEpisodeAction(Action):
    """Change the maturity of an episode."""

    key: str = "promote_episode"
    name: str = "Promote Episode"
    icon: str = "trending-up"
    category: str = "story"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        account = _resolve_account(actor)
        episode, error = _episode_or_error(kwargs.get("episode_id"))
        if error:
            return error

        story = _story_for_object(episode)
        denial = _lead_gm_deny_result(account, story)
        if denial:
            return denial

        target_maturity, error = _target_maturity_or_error(kwargs.get("target"))
        if error:
            return error

        try:
            promote_episode_maturity(episode, target=target_maturity)
        except StoryError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"Episode '{episode.title}' promoted to {target_maturity.label}.",
        )


@dataclass
class MarkBeatAction(Action):
    """Record a GM-marked outcome on a beat."""

    key: str = "mark_beat"
    name: str = "Mark Beat"
    icon: str = "flag"
    category: str = "story"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        account = _resolve_account(actor)
        beat, error = _beat_or_error(kwargs.get("beat_id"))
        if error:
            return error

        if not _actor_may_mark_beat(account, beat):
            return ActionResult(success=False, message=_NO_MARK_PERMISSION)

        outcome, error = _beat_outcome_or_error(kwargs.get("outcome"))
        if error:
            return error

        story = _story_for_object(beat)
        progress = get_active_progress_for_story(story)
        if progress is None:
            return ActionResult(success=False, message=_NO_PROGRESS)

        try:
            record_gm_marked_outcome(
                progress=progress,
                beat=beat,
                outcome=outcome,
                gm_notes=kwargs.get("gm_notes", ""),
            )
        except (StoryError, ValueError) as exc:
            return ActionResult(success=False, message=str(exc))

        return ActionResult(success=True, message=f"Beat marked {outcome.label}.")
