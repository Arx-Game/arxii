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


class AdvancementUnlockNotPurchasedError(ClassLevelAdvancementError):
    """The inductee has not purchased the XP unlock for the target level.

    Per ADR "XP unlocks, never grants — major acquisitions stack gates": passing
    ``check_requirements_for_unlock`` is necessary but not sufficient — the
    ``CharacterUnlock`` XP purchase (``progression unlock class=<id>``) is an
    *additional*, independently-required gate. Names the missing unlock + its
    XP cost so the failure is loud and actionable, never silent.
    """

    def __init__(self, *, class_name: str, target_level: int, xp_cost: int) -> None:
        self.class_name = class_name
        self.target_level = target_level
        self.xp_cost = xp_cost
        self.user_message = (
            f"You have not purchased the unlock for {class_name} level {target_level} "
            f"(cost {xp_cost} XP). Use 'progression unlock class=<id>' first."
        )
        super().__init__(self.user_message)


class OfficiantIneligibleError(ClassLevelAdvancementError):
    """The officiant is not eligible to induct this advancement."""

    user_message = "You are not eligible to officiate this advancement."


class NoDuranceSiteError(ClassLevelAdvancementError):
    """No active DuranceTrainingSite in this room has an eligible trainer."""

    user_message = "There is no Durance training site with an eligible trainer here."
