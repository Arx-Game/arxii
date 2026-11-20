"""Choices for the beta cutover policy layer (#3055 PR 3)."""

from __future__ import annotations

from django.db import models


class CutoverPolicy(models.TextChoices):
    """Why a character is kept through the cutover instead of left to the wipe alone."""

    ROSTER_CHARACTER = "roster_character", "Roster character"
    RESERVED_OC = "reserved_oc", "Reserved original character"
    CARRY_OVER = "carry_over", "Carried-over character"
