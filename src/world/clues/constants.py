"""TextChoices for the clues app (#1144)."""

from django.db import models


class ClueTargetKind(models.TextChoices):
    """What a clue points at — selects the active per-kind target FK on ``Clue``.

    Extend for a new kind by adding the value here, a nullable FK on ``Clue``, and a
    ``DISCRIMINATOR_MAP`` entry. SECRET/SCANDAL targets are planned (#1143) once their
    own models exist.
    """

    CODEX = "codex", "Codex Entry"
    MISSION = "mission", "Mission"


class ClueResolution(models.TextChoices):
    """How holding a clue becomes having its target.

    AUTOMATIC: the target is granted on acquisition (rescue clues, simple lore).
    RESEARCH:  the target is won through a collaborative research project (#1146).
    """

    AUTOMATIC = "automatic", "Automatic (granted on acquisition)"
    RESEARCH = "research", "Research project"
