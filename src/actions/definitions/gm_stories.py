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

from django.db.models import Model

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType
from commands.utils.gm_resolution import resolve_account_or_none
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
_NO_DECLARE_PERMISSION = (
    "Only the story's Lead GM, staff, an approved Assistant GM, "
    "or this scene's GM may declare stakes."
)
_NO_PROGRESS = "No active progress record found for this story."


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


def _load_or_error[TModel: Model](
    model: type[TModel],
    pk: Any,
    *,
    missing_msg: str,
    not_found_msg: str,
) -> tuple[TModel | None, ActionResult | None]:
    """Fetch a model instance by pk, returning ``(instance, error_result)``."""
    if pk is None:
        return None, ActionResult(success=False, message=missing_msg)
    try:
        return model.objects.get(pk=pk), None
    except (model.DoesNotExist, ValueError):
        return None, ActionResult(success=False, message=not_found_msg)


def _enum_or_error(
    enum_cls: type[Any],
    value: Any,
    *,
    missing_msg: str,
    invalid_msg: str,
) -> tuple[Any | None, ActionResult | None]:
    """Parse a ``TextChoices``/``IntegerChoices`` value, returning ``(value, error_result)``."""
    if value is None:
        return None, ActionResult(success=False, message=missing_msg)
    try:
        return enum_cls(value), None
    except ValueError:
        return None, ActionResult(success=False, message=invalid_msg)


def _story_or_error(story_id: Any) -> tuple[Story | None, ActionResult | None]:
    """Fetch a ``Story`` by id, returning ``(story, error_result)``."""
    return _load_or_error(
        Story,
        story_id,
        missing_msg="A story is required.",
        not_found_msg="No story with that ID exists.",
    )


def _episode_or_error(episode_id: Any) -> tuple[Episode | None, ActionResult | None]:
    """Fetch an ``Episode`` by id, returning ``(episode, error_result)``."""
    return _load_or_error(
        Episode,
        episode_id,
        missing_msg="An episode is required.",
        not_found_msg="No episode with that ID exists.",
    )


def _beat_or_error(beat_id: Any) -> tuple[Beat | None, ActionResult | None]:
    """Fetch a ``Beat`` by id, returning ``(beat, error_result)``."""
    return _load_or_error(
        Beat,
        beat_id,
        missing_msg="A beat is required.",
        not_found_msg="No beat with that ID exists.",
    )


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
    return _enum_or_error(
        StoryMaturity,
        target,
        missing_msg="A target maturity is required.",
        invalid_msg="Invalid target maturity.",
    )


def _beat_outcome_or_error(outcome: Any) -> tuple[BeatOutcome | None, ActionResult | None]:
    """Parse a beat outcome value, returning ``(outcome, error_result)``."""
    return _enum_or_error(
        BeatOutcome,
        outcome,
        missing_msg="An outcome is required.",
        invalid_msg="Invalid beat outcome.",
    )


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
        account = resolve_account_or_none(actor)
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
        account = resolve_account_or_none(actor)
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
        account = resolve_account_or_none(actor)
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
        account = resolve_account_or_none(actor)
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


def _stakes_declaration_text(beat: Beat, activation: Any) -> str:
    """Compose the room-visible stakes declaration (#1770 pillar 9).

    Lists each stake's severity label + player_summary and the effective
    risk the activation locked in. Branch contents are never included.
    """
    from world.societies.constants import RenownRisk  # noqa: PLC0415

    effective_label = RenownRisk(activation.effective_risk).label
    lines = [f"|wStakes are declared|n (effective risk: {effective_label}):"]
    lines.extend(
        f"  - {stake.get_severity_display()}: {stake.player_summary}" for stake in beat.stakes.all()
    )
    return "\n".join(lines)


@dataclass
class DeclareStakesAction(Action):
    """Present and lock a beat's stakes contract for the current scene (#1770 PR4).

    The opt-in moment for freeform (non-combat, non-mission) play: the GM
    declares the wager to the room, and the contract locks for the scene's
    active participants. Gated to whoever may mark the beat (Lead GM / staff /
    approved AGM) or the scene's GM.
    """

    key: str = "declare_stakes"
    name: str = "Declare Stakes"
    icon: str = "scale"
    category: str = "story"
    target_type: TargetType = TargetType.SELF
    costs_turn: bool = False

    def execute(  # noqa: PLR0911 - distinct guard failures read clearest as early returns
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
        from flows.service_functions.communication import message_location  # noqa: PLC0415
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415
        from world.societies.constants import RenownRisk  # noqa: PLC0415
        from world.stories.services.boundaries import check_stake_boundaries  # noqa: PLC0415
        from world.stories.services.stakes import activate_stakes_contract  # noqa: PLC0415

        account = resolve_account_or_none(actor)
        beat, error = _beat_or_error(kwargs.get("beat_id"))
        if error:
            return error

        scene = get_active_scene(actor.location)
        if scene is None:
            return ActionResult(success=False, message="There is no active scene here.")

        if not (_actor_may_mark_beat(account, beat) or scene.is_gm(account)):
            return ActionResult(success=False, message=_NO_DECLARE_PERMISSION)

        if beat.risk == RenownRisk.NONE or not beat.stakes.exists():
            return ActionResult(
                success=False,
                message="That beat has no stakes to declare (risk NONE or no stakes authored).",
            )

        personas = scene.persona_handler.active_participant_personas()
        # Dedupe sheets (order-preserving) — alts of one account still count once each.
        sheets = list(dict.fromkeys(persona.character_sheet for persona in personas))
        if not sheets:
            return ActionResult(
                success=False,
                message="No active participants are present to commit to these stakes.",
            )

        report = check_stake_boundaries(beat.stakes.all(), sheets)
        if not report.allowed:
            # The private reason is never surfaced (ADR-0033).
            return ActionResult(success=False, message="These stakes could not be presented.")

        activation = activate_stakes_contract(beat, sheets)

        text = _stakes_declaration_text(beat, activation)
        sdm = context.scene_data if context else SceneDataManager()
        caller_state = sdm.initialize_state_for_object(actor)
        message_location(caller_state, text)

        return ActionResult(success=True, message=text)
