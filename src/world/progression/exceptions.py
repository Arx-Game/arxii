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


class PathAlreadySelectedError(ClassLevelAdvancementError):
    """The character already has a CharacterPathHistory row on record.

    Raised by ``select_initial_path`` (#2121) — the late-selection recovery
    surface for characters created via a CG-bypassing path (GM-finalize
    quickstart, NPCAsset -> PC promotion). It is a one-time recovery, not a
    general path-change tool: ``cross_into_path`` (Audere Majora crossings,
    the Durance POTENTIAL semi-crossing) is the seam for changing an
    already-set path.
    """

    user_message = (
        "You have already selected a path. This recovery action is only for "
        "characters with no path on record."
    )


class PathRequirementsNotMet(ClassLevelAdvancementError):
    """The character does not meet the TraitRequirements for a Path (#2538).

    Raised by ``cross_into_path`` when a hybrid Path (or any Path with
    authored TraitRequirements targeting the ``path`` FK) has unmet
    stat/skill prerequisites. Carries the failed requirement messages so
    the caller can surface them. The semi-crossing resolver catches this
    and treats the path as ineligible (non-breaking level-only advance);
    Audere Majora lets it propagate, rolling back the crossing.
    """

    def __init__(self, *, path_name: str, failed_messages: list[str]) -> None:
        self.path_name = path_name
        self.failed_messages = failed_messages
        self.user_message = f"You do not meet the requirements for {path_name}: " + "; ".join(
            failed_messages
        )
        super().__init__(self.user_message)


class AlreadyRegisteredForDuranceError(ClassLevelAdvancementError):
    """Raised when a character attempts the intake registration rite twice."""

    user_message = "You have already been registered into the Durance arc."
