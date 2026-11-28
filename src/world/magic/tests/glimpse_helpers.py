"""Shared helpers for the Glimpse tests (#5292)."""

from unittest import mock

from world.magic.constants import GLIMPSE_AXIS_CONFIG, GlimpseAxisRule, GlimpseTagAxis


def axis_takes_several(axis: GlimpseTagAxis):
    """Patch one axis to take several answers, for the duration of a test.

    Every axis takes one answer since #5292. The several-answers path (and
    ``GlimpseTag.stands_alone`` with it) stays in the code as the way back, and the
    tests that hold it open an axis with this. Use as a decorator or a context manager.
    """
    rule = GLIMPSE_AXIS_CONFIG[axis]
    return mock.patch.dict(
        GLIMPSE_AXIS_CONFIG,
        {
            axis: GlimpseAxisRule(
                multi=True,
                prose_prompt=rule.prose_prompt,
                gives_card=rule.gives_card,
                lost_in_blackout=rule.lost_in_blackout,
            )
        },
    )
