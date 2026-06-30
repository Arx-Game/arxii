"""Progression-app exceptions for class-level advancement (#1352).

Each carries a ``user_message`` attribute per the project's no-``str(exc)``-in-API
rule (CLAUDE.md). The Durance advancement service raises these; the dispatching
ritual session rolls back its transaction when one is raised, leaving the session
alive for the initiator to retry or cancel.
"""

from __future__ import annotations


class ClassLevelAdvancementError(Exception):
    """Base for all class-level advancement failures."""

    user_message = "This advancement could not be completed."


class TierBoundaryRequiresCrossing(ClassLevelAdvancementError):
    """The step would cross a tier boundary, which the Durance cannot perform."""

    user_message = (
        "This step crosses a tier boundary — it can only be taken through "
        "Audere Majora, the Crossing of the Threshold, not the Ritual of the Durance."
    )


class AdvancementRequirementsNotMet(ClassLevelAdvancementError):
    """The inductee does not meet the authored requirements for the next level."""

    user_message = "The inductee does not yet meet the requirements for this advancement."

    def __init__(self, failed: list[str] | None = None) -> None:
        self.failed = failed or []
        if self.failed:
            super().__init__("; ".join(self.failed))
        else:
            super().__init__(self.user_message)


class OfficiantIneligibleError(ClassLevelAdvancementError):
    """The officiant is not eligible to induct this advancement."""

    user_message = "You are not eligible to officiate this advancement."


class NoDuranceSiteError(ClassLevelAdvancementError):
    """No active DuranceTrainingSite in this room has an eligible trainer."""

    user_message = "There is no Durance training site with an eligible trainer here."
