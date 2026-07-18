"""Constants for the gem value model (Build 0b)."""

from __future__ import annotations

from django.db import models

# Quality-level scale for gem *types* (the Arx 1 item-quality scale, presentation
# via QualityTier banding). 1-5 semiprecious, 6-10 precious, 11-15 magical. Kept as
# a plain int on GemDetails — NOT seeded as QualityTier rows (that would pollute
# skill-cap ladders / attachment quality / appraise; see design Addendum F3).
GEM_QUALITY_LEVEL_MIN = 1
GEM_QUALITY_LEVEL_MAX = 15


class GemAxis(models.TextChoices):
    """The three per-instance grade axes that multiply a gem's worth.

    Type and (via GemGrade) size/purity are inherent, fixed at extraction; cut is
    the player crafter's value-add. Each axis's lowest grade multiplies by 1.0.
    """

    SIZE = "size", "Size"
    PURITY = "purity", "Purity"
    CUT = "cut", "Cut"
