"""Maturity-promotion validation. Forward promotion is gated by minimal
per-node content rules; demotion is always allowed (non-linear sketchpad)."""

from world.stories.constants import StoryMaturity
from world.stories.exceptions import MaturityPromotionError
from world.stories.models import Episode

_RANK = {
    StoryMaturity.PITCH: 0,
    StoryMaturity.OUTLINE: 1,
    StoryMaturity.PLOT: 2,
}


def promote_episode_maturity(episode: Episode, target: StoryMaturity) -> Episode:
    """Set episode.maturity to ``target``.

    Promotion to PLOT requires a non-empty resting_conclusion AND either an
    outbound transition or is_ending. Lateral moves and demotions are not
    validated. Returns the saved episode.
    """
    is_promotion = _RANK[target] > _RANK[StoryMaturity(episode.maturity)]
    if target == StoryMaturity.PLOT and is_promotion:
        if not episode.resting_conclusion.strip():
            raise MaturityPromotionError
        has_outbound = episode.outbound_transitions.exists()
        if not has_outbound and not episode.is_ending:
            raise MaturityPromotionError
    episode.maturity = target
    episode.save(update_fields=["maturity", "updated_at"])
    return episode
