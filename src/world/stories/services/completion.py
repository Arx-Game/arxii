"""Story completion: the explicit staff/owner action that concludes a story.

Honest about unresolved threads — in-flight progress is FORECLOSED, not falsely
COMPLETED and never orphaned — and never blocks on absent participants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.stories.constants import ProgressStatus
from world.stories.models import (
    GlobalStoryProgress,
    GroupStoryProgress,
    Story,
    StoryProgress,
)
from world.stories.services.frontier import set_progress_status
from world.stories.types import AnyStoryProgress, StoryStatus

if TYPE_CHECKING:
    from world.gm.models import GMProfile

# Every per-run pointer model that tracks progress through a story. complete_story
# forecloses any still-active row across all three regardless of the story's scope.
_PROGRESS_MODELS = (StoryProgress, GroupStoryProgress, GlobalStoryProgress)


@transaction.atomic
def complete_story(*, story: Story) -> Story:
    """Conclude a story. Idempotent: a no-op if it is already COMPLETED.

    Sets status + completed_at, then forecloses every still-active progress
    record (any scope model) that has not genuinely COMPLETED — the honest
    record that those threads ended unresolved when the story closed.
    """
    if story.status == StoryStatus.COMPLETED:
        return story
    story.status = StoryStatus.COMPLETED
    story.completed_at = timezone.now()
    story.save(update_fields=["status", "completed_at"])
    # is_active=True is the operational form of "active and not yet terminal":
    # set_progress_status keeps is_active False ⟺ COMPLETED/FORECLOSED, so this
    # filter already excludes genuinely-completed runs (preserved truthfully) and
    # already-foreclosed ones. Do NOT add a separate .exclude(status=COMPLETED).
    for model in _PROGRESS_MODELS:
        for progress in model.objects.filter(story=story, is_active=True):
            set_progress_status(progress, ProgressStatus.FORECLOSED)
    _dissolve_linked_campaigns(story)
    return story


def _dissolve_linked_campaigns(story: Story) -> None:
    """Dissolve every still-active CAMPAIGN covenant this story's conclusion ends.

    Reuses the existing dissolve_covenant path (ends memberships + clears
    engagement). STANDING covenants are filtered out by battle_binding and so
    persist through their own stand-down lifecycle. Lazy imports keep the
    stories -> covenants dependency one-directional.
    """
    from world.covenants.constants import BattleBinding  # noqa: PLC0415
    from world.covenants.models import Covenant  # noqa: PLC0415
    from world.covenants.services import dissolve_covenant  # noqa: PLC0415

    campaigns = Covenant.objects.filter(
        campaign_story=story,
        battle_binding=BattleBinding.CAMPAIGN,
        dissolved_at__isnull=True,
    )
    for covenant in campaigns:
        dissolve_covenant(covenant=covenant)


@transaction.atomic
def resolve_foreclosed_progress(
    *,
    progress: AnyStoryProgress,
    resolved_by: GMProfile | None,
) -> AnyStoryProgress:
    """Wrap up a FORECLOSED progress record.

    Stamps ``resolved_at`` / ``resolved_by`` — an honest closure marker
    layered on the terminal FORECLOSED outcome, never a reclassification to
    COMPLETED. Idempotent: a no-op (no re-notify) if already resolved. Does
    not touch ``status`` or ``is_active``.

    ``resolved_by`` may be ``None`` when a staff user without a GMProfile
    performs the action (the closure still fires; the audit trail is carried
    by the NarrativeMessage's sender_account instead).

    Defensive programmer-error guard only: ``progress`` must be FORECLOSED.
    User-input validation (the record exists, is foreclosed, belongs to the
    resolved story) belongs in the serializer.
    """
    from world.stories.services.narrative import notify_foreclosed_resolved  # noqa: PLC0415

    if progress.status != ProgressStatus.FORECLOSED:
        msg = (
            f"Progress {progress.pk} is not FORECLOSED (status={progress.status!r}); "
            "ResolveForeclosureInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    if progress.resolved_at is not None:
        return progress
    progress.resolved_at = timezone.now()
    progress.resolved_by = resolved_by
    progress.save(update_fields=["resolved_at", "resolved_by"])
    notify_foreclosed_resolved(progress=progress, resolved_by=resolved_by)
    return progress
