"""Story completion: the explicit staff/owner action that concludes a story.

Honest about unresolved threads — in-flight progress is FORECLOSED, not falsely
COMPLETED and never orphaned — and never blocks on absent participants.
"""

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
from world.stories.types import StoryStatus

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
    for model in _PROGRESS_MODELS:
        for progress in model.objects.filter(story=story, is_active=True):
            set_progress_status(progress, ProgressStatus.FORECLOSED)
    return story
