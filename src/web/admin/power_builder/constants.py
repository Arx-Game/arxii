"""Choices the Power Builder (item 8 of #5066) branches on."""

from __future__ import annotations

from django.db import models


class SourceKind(models.TextChoices):
    """A source of the capability that is not a technique; the label is the page's copy."""

    TRAINED = "trained ability", "trained ability"
    CONDITION = "condition", "condition"
    DISTINCTION = "distinction", "distinction"


class GrantMode(models.TextChoices):
    """Which grant controls a technique row carries."""

    #: It grants the capability; the numbers are edited here.
    EDIT = "edit", "edit"
    #: It grants the capability; the numbers are shown, not edited.
    SHOWN = "shown", "shown"
    #: It does not grant the capability; a "grant it" tick and the numbers.
    OFFER = "offer", "offer"
