"""Codex system constants.

TextChoices and IntegerChoices are placed here to avoid circular imports
and keep models.py focused on model definitions.
"""

from django.db import models


class CodexKnowledgeStatus(models.TextChoices):
    """Status of a character's knowledge of a codex entry."""

    UNCOVERED = "uncovered", "Uncovered"
    KNOWN = "known", "Known"


#: Per-level AP discount a Library grants to codex learning (#675).
#: PLACEHOLDER — pending content pass.
LIBRARY_AP_DISCOUNT_PER_LEVEL = 1
