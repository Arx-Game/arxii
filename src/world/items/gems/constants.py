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


# --- Mining / haul distribution (Build 0b slice 4) ---
# All magnitudes are PLACEHOLDER, admin/caller-tunable — the *shape* is the point.
#
# A weekly offscreen mine yields a bulk of common gems as an aggregate *value* (never
# instanced) plus, rarely, a few individuated "Rare Find" stones. Mine quality and the
# overseeing minister's skill both help: they add to the Rare-Find chance AND shift every
# axis roll up (a +10 mine turns a 90 into a 100 — max for the roll).
RARE_FIND_BASE_CHANCE = 1  # percent, before mine-quality / minister bonuses
RARE_FIND_MAX_COUNT = 4  # 1dN finds when a Rare Find occurs
# Common-bulk value produced per point of mine quality per cycle (pure placeholder).
COMMON_VALUE_PER_QUALITY = 50
