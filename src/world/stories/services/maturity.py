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


def episode_meets_plot_gate(episode: Episode) -> bool:
    """Whether an episode satisfies the PLOT-maturity gate.

    Single source of truth for the PLOT promotion rule, shared by
    ``promote_episode_maturity`` (service, raises) and
    ``PromoteEpisodeInputSerializer.validate`` (Layer-2, 400). The rule:
    non-empty ``resting_conclusion`` AND (an outbound transition OR
    ``is_ending``). Independent of direction — callers decide when the gate
    applies (upward move *to* PLOT only).
    """
    if not episode.resting_conclusion.strip():
        return False
    # `is_ending` is a local field — order it first so a True value
    # short-circuits and skips the outbound_transitions query entirely.
    return episode.is_ending or episode.outbound_transitions.exists()


def promote_episode_maturity(episode: Episode, target: StoryMaturity) -> Episode:
    """Set episode.maturity to ``target``.

    Promotion to PLOT requires a non-empty resting_conclusion AND either an
    outbound transition or is_ending. Lateral moves and demotions are not
    validated. Returns the saved episode.
    """
    is_promotion = _RANK[target] > _RANK[StoryMaturity(episode.maturity)]
    if target == StoryMaturity.PLOT and is_promotion and not episode_meets_plot_gate(episode):
        raise MaturityPromotionError
    episode.maturity = target
    episode.save(update_fields=["maturity", "updated_at"])
    return episode
