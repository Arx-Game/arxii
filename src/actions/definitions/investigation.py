"""Investigation actions (#1154) — searching a room for hidden clues."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.types import ActionResult, TargetType
from world.clues.constants import SEARCH_CHECK_TYPE_NAME

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.checks.models import CheckType

# Placeholder cost magnitudes — tuned in a later author pass (#1143).
_SEARCH_AP_COST = 1
_SEARCH_FATIGUE_COST = 1

# PLACEHOLDER magnitude, tuned in a later author pass (matches the AP/fatigue
# placeholders above) — points of detect difficulty per point of concealment severity.
_CONCEALMENT_DETECT_DIFFICULTY_PER_SEVERITY = 10


@dataclass
class SearchAction(Action):
    """Search the current room for hidden clues (#1154).

    The thin action wrapper over ``world.clues.services.search_room``: charges the
    declarative AP + mental-fatigue cost (base ``run()``), resolves the seeded Search
    CheckType, and reports what the searcher turns up. All player-visible result text is
    PLACEHOLDER — rewrite in voice before launch.
    """

    key: str = "search"
    name: str = "Search"
    icon: str = "magnifying-glass"
    category: str = "investigation"
    target_type: TargetType = TargetType.SELF

    ap_cost: int = _SEARCH_AP_COST
    fatigue_cost: int = _SEARCH_FATIGUE_COST
    fatigue_category: str = ActionCategory.MENTAL

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.checks.models import CheckType  # noqa: PLC0415
        from world.clues.services import search_room  # noqa: PLC0415

        room = actor.location
        if room is None:
            return ActionResult(success=False, message="PLACEHOLDER There's nowhere to search.")
        try:
            room_profile = room.room_profile
        except RoomProfile.DoesNotExist:
            return ActionResult(
                success=False, message="PLACEHOLDER There's nothing to search here."
            )
        try:
            search_check = CheckType.objects.get(name=SEARCH_CHECK_TYPE_NAME)
        except CheckType.DoesNotExist:
            return ActionResult(success=False, message="PLACEHOLDER You can't search right now.")

        found = search_room(actor, room_profile, search_check)

        self._detect_concealed_characters(actor, search_check)

        if not found:
            return ActionResult(success=True, message="PLACEHOLDER You search but turn up nothing.")
        lines = ["PLACEHOLDER You uncover something:"]
        lines += [f"  {clue.name} — {clue.description}" for clue in found]
        return ActionResult(success=True, message="\n".join(lines))

    def _detect_concealed_characters(self, actor: ObjectDB, search_check: CheckType) -> None:
        """Roll the same Search check against every concealed character present,
        registering detection on success (#1225). Per-observer: does not affect
        other characters' ability to perceive the same target."""
        from world.checks.services import perform_check  # noqa: PLC0415
        from world.conditions.services import (  # noqa: PLC0415
            active_concealments,
            can_perceive,
            register_detection,
        )

        actor_sheet = getattr(actor, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if actor_sheet is None or actor.location is None:
            return
        detected_any = False
        for candidate in actor.location.contents:
            if candidate == actor or can_perceive(actor, candidate):
                continue
            concealments = active_concealments(candidate)
            if not concealments.exists():
                continue
            severity = max(inst.effective_severity for inst in concealments)
            result = perform_check(
                actor,
                search_check,
                target_difficulty=severity * _CONCEALMENT_DETECT_DIFFICULTY_PER_SEVERITY,
            )
            if result.outcome is not None and result.outcome.success_level >= 0:
                register_detection(actor_sheet, candidate)
                detected_any = True
        if detected_any and hasattr(actor, "send_room_state"):
            # A newly-detected character won't appear in the actor's room-occupant
            # list until the next natural refresh — push one now (#1225).
            actor.send_room_state()


@dataclass
class StartInvestigationAction(Action):
    """Open a collaborative investigation project at a research lab (#1825).

    The first player-facing start surface for RESEARCH projects: standing at an
    active LAB, holding a RESEARCH-mode clue — or physical crime evidence whose
    deed anchors a frame — opens the project that ``project/check`` contributions
    advance. Holding the evidence grants the counter-clue along the way (the
    physical item IS a lead). Duplicate active projects for the same clue are
    refused; join the existing one instead.
    """

    key: str = "start_investigation"
    name: str = "Start Investigation"
    icon: str = "folder-open"
    category: str = "investigation"
    action_category: ActionCategory = ActionCategory.MENTAL
    target_type: TargetType = TargetType.SELF

    ap_cost: int = _SEARCH_AP_COST
    fatigue_cost: int = _SEARCH_FATIGUE_COST
    fatigue_category: str = ActionCategory.MENTAL

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.clues.research import start_research_project  # noqa: PLC0415
        from world.projects.constants import ProjectKind, ProjectStatus  # noqa: PLC0415
        from world.projects.models import Project  # noqa: PLC0415
        from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

        sheet = actor.character_sheet  # type: ignore[attr-defined] — typeclass property
        if sheet is None:
            return ActionResult(success=False, message="You have no character identity.")
        if not self._standing_at_lab(actor):
            return ActionResult(
                success=False,
                message="PLACEHOLDER You need a research lab to run an investigation from.",
            )
        clue = self._resolve_clue(sheet, kwargs)
        if isinstance(clue, ActionResult):
            return clue
        duplicate = Project.objects.filter(
            kind=ProjectKind.RESEARCH,
            status=ProjectStatus.ACTIVE,
            research_details__clue=clue,
        ).exists()
        if duplicate:
            return ActionResult(
                success=False,
                message="That trail is already under investigation — lend your checks to it.",
            )
        project = start_research_project(clue, active_persona_for_sheet(sheet))
        return ActionResult(
            success=True,
            message=(
                f"PLACEHOLDER You open an investigation: {clue.name}. "
                f"Advance it with |wproject/check {project.pk}|n contributions."
            ),
            data={"project_id": project.pk},
        )

    def _standing_at_lab(self, actor: ObjectDB) -> bool:
        from evennia_extensions.models import RoomProfile  # noqa: PLC0415
        from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
        from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

        room = actor.location
        if room is None:
            return False
        try:
            room_profile = room.room_profile
        except RoomProfile.DoesNotExist:
            return False
        return (
            RoomFeatureInstance.objects.filter(
                room_profile=room_profile,
                feature_kind__service_strategy=RoomFeatureServiceStrategy.LAB,
            )
            .active()
            .exists()
        )

    def _resolve_clue(  # noqa: PLR0911 — each return is a distinct player-facing guard
        self, sheet: Any, kwargs: dict[str, Any]
    ) -> Any:
        """Resolve the investigation's clue from a held clue or held evidence.

        Returns the Clue, or a failure ActionResult (checked via isinstance by the
        caller — mirrors the guard-heavy action idiom).
        """
        from world.clues.constants import ClueResolution, ClueTargetKind  # noqa: PLC0415
        from world.clues.models import CharacterClue, Clue  # noqa: PLC0415
        from world.clues.services import acquire_clue  # noqa: PLC0415

        entry = getattr(sheet, "roster_entry", None)  # noqa: GETATTR_LITERAL
        if entry is None:
            return ActionResult(success=False, message="You have no roster identity.")

        evidence_id = kwargs.get("evidence_id")
        if isinstance(evidence_id, int):
            clue_or_error = self._clue_from_evidence(sheet, evidence_id)
            if isinstance(clue_or_error, ActionResult):
                return clue_or_error
            acquire_clue(entry, clue_or_error)
            return clue_or_error

        clue = (
            Clue.objects.filter(pk=kwargs.get("clue_id")).first()
            if isinstance(kwargs.get("clue_id"), int)
            else None
        )
        if clue is None:
            return ActionResult(success=False, message="There's no such lead.")
        if not CharacterClue.objects.filter(roster_entry=entry, clue=clue).exists():
            return ActionResult(success=False, message="You don't hold that lead.")
        if clue.resolution_mode != ClueResolution.RESEARCH:
            return ActionResult(
                success=False, message="That lead needs no research — you already have it."
            )
        if clue.target_kind not in (ClueTargetKind.SECRET, ClueTargetKind.CODEX):
            return ActionResult(success=False, message="That lead can't be researched here.")
        return clue

    def _clue_from_evidence(self, sheet: Any, evidence_id: int) -> Any:
        """The physical-evidence door: held frame evidence yields the accusation's clue."""
        from world.clues.constants import ClueTargetKind  # noqa: PLC0415
        from world.clues.models import Clue  # noqa: PLC0415
        from world.justice.models import AccusationCrimeClaim, CrimeEvidence  # noqa: PLC0415

        evidence = CrimeEvidence.objects.filter(pk=evidence_id).first()
        if evidence is None:
            return ActionResult(success=False, message="There's no such evidence.")
        instance = evidence.item_instance
        if instance is None or instance.holder_character_sheet != sheet:
            return ActionResult(success=False, message="You are not holding that evidence.")
        claim = (
            AccusationCrimeClaim.objects.filter(real_deed=evidence.deed)
            .select_related("secret")
            .first()
        )
        if claim is None:
            return ActionResult(
                success=False, message="That evidence anchors no accusation to unravel."
            )
        clue = Clue.objects.filter(
            target_kind=ClueTargetKind.SECRET, target_secret=claim.secret
        ).first()
        if clue is None:
            return ActionResult(
                success=False, message="No investigable trail leads from that evidence yet."
            )
        return clue
