import contextlib
from typing import TYPE_CHECKING, Self, Union

from django.utils.functional import cached_property

from flows.object_states.base_state import BaseState
from flows.scene_data_manager import SceneDataManager
from flows.trigger_handler import TriggerHandler

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.character_sheets.models import CharacterSheet

DEFAULT_GENDER = "neutral"


class ObjectParent:
    """
    This is a mixin that can be used to override *all* entities inheriting at
    some distance from DefaultObject (Objects, Exits, Characters and Rooms).

    Just add any method that exists on `DefaultObject` to this class. If one
    of the derived classes has itself defined that same hook already, that will
    take precedence.

    """

    state_class = BaseState

    @property
    def item_data(self: Union[Self, "DefaultObject"]):
        """Return a handler that provides unified data access for serialization."""
        from evennia_extensions.data_handlers import ObjectItemDataHandler

        return ObjectItemDataHandler(self)

    def get_object_state(
        self: Union[Self, "DefaultObject"],
        context: "SceneDataManager",
    ) -> BaseState:
        return self.state_class(obj=self, context=context)

    @cached_property
    def trigger_handler(self: Union[Self, "DefaultObject"]) -> TriggerHandler:
        """Populate-once cache of active triggers for this object."""
        return TriggerHandler(owner=self)

    @cached_property
    def conditions(self: Union[Self, "DefaultObject"]):
        """Populate-once cache of active ConditionInstance rows for this object.

        Returns a ConditionHandler that loads the owner's active conditions on
        first access and serves subsequent reads query-free.  Character overrides
        this with CharacterConditionHandler (adds resistance_modifier).

        Invalidated by condition mutation services (apply_condition, etc.).
        """
        from world.conditions.handlers import ConditionHandler

        return ConditionHandler(self)

    @property
    def character_sheet(self: Union[Self, "DefaultObject"]) -> "CharacterSheet | None":
        """This object's CharacterSheet, or None for anything that isn't a character.

        The safe, explicit replacement for ``getattr(obj, "sheet_data", None)``:
        ``sheet_data`` is the reverse OneToOne from ``CharacterSheet.character`` and
        raises on sheetless objects — the getattr idiom only "worked" because Django's
        RelatedObjectDoesNotExist subclasses AttributeError, which also swallowed
        genuine attribute bugs. Use this on maybe-not-a-character objects; use
        ``obj.sheet_data`` directly where a missing sheet is a hard bug.
        """
        from world.character_sheets.models import CharacterSheet

        try:
            return self.sheet_data
        except CharacterSheet.DoesNotExist:
            return None

    @property
    def scene_data(self: Union[Self, "DefaultObject"]):
        """Return the SceneDataManager from our containing location."""
        if self.location:
            return self.location.scene_data
        return None

    @property
    def scene_state(self: Union[Self, "DefaultObject"]) -> BaseState | None:
        """Return the state object representing this entity in the scene."""
        scene_data = self.scene_data
        if scene_data:
            return scene_data.get_state_by_pk(self.pk)
        return None

    @property
    def gender(self: Union[Self, "DefaultObject"]) -> str:
        """Gender used by funcparser pronoun helpers."""
        return DEFAULT_GENDER

    def get_display_name(
        self: Union[Self, "DefaultObject"],
        looker=None,
        **kwargs,
    ) -> str:
        """Return the display name using state data when available."""
        state = self.scene_state
        if state:
            looker_state = looker.scene_state if looker else None
            return state.get_display_name(looker_state, **kwargs)
        return super().get_display_name(looker, **kwargs)

    def at_examined(self: Union[Self, "DefaultObject"], observer: "DefaultObject") -> bool:
        """Called when *observer* examines *self*.

        Emits EXAMINE_PRE (mutable — lets listeners veto/modify), then
        EXAMINED (frozen — post-event). Returns False if a reactive trigger
        cancelled the examine; callers should honour the return value.

        After a successful (non-cancelled) call the mutable ``sections`` list
        from the ``ExaminePrePayload`` is stashed on ``self._examine_sections``
        so that ``return_appearance`` can append them to the base description.
        The attribute is always reset on entry so stale data never bleeds
        across calls.
        """
        from flows.constants import EventName
        from flows.emit import emit_event
        from flows.events.payloads import ExaminedPayload, ExaminePrePayload

        # Reset any sections left over from a previous call.
        self._examine_sections: list[str] = []  # type: ignore[attr-defined]

        # For rooms, self is its own location; for characters/objects, use
        # the containing room.
        location = self.location if self.location is not None else self
        pre = ExaminePrePayload(observer=observer, target=self)
        stack = emit_event(
            EventName.EXAMINE_PRE,
            pre,
            location=location,
        )
        if stack.was_cancelled():
            return False

        # Carry the decorated sections forward for return_appearance.
        self._examine_sections = pre.sections  # type: ignore[attr-defined]

        post = ExaminedPayload(observer=observer, target=self)
        emit_event(
            EventName.EXAMINED,
            post,
            location=location,
        )

        # Mission ENVIRONMENTAL_DETAIL dispatch (#729) on examine. run_safely (#1164):
        # a failure is captured + the examiner told, never breaking the look. The cheap
        # giver lookup short-circuits ordinary objects.
        from world.missions.services.trigger_dispatch import (
            maybe_dispatch_on_examine,
        )
        from world.player_submissions.services import run_safely

        run_safely(
            "mission_dispatch_on_examine",
            lambda: maybe_dispatch_on_examine(observer, self),
            actor=observer,
        )
        return True

    def return_appearance(self, looker: "DefaultObject | None", **kwargs) -> str:
        """Return description string, after running the examine hook.

        If a reactive trigger cancels the examine, returns an empty string
        so that the calling command shows nothing (or its own fallback).
        Reactive flows that appended to ``ExaminePrePayload.sections`` have
        their text concatenated after the base appearance.

        Objects with a ``RankingDisplay`` profile (#676 Phase I diegetic
        rankings) get the rendered top-N appended after the base — the
        herald reads names, the academy display shimmers, etc.
        """
        if looker is not None and not self.at_examined(looker):
            return ""
        base = super().return_appearance(looker, **kwargs)  # type: ignore[misc]
        sections: list[str] = getattr(self, "_examine_sections", [])  # noqa: GETATTR_LITERAL
        ranking = _maybe_render_ranking_display(self, looker)
        if ranking is not None:
            sections = [*sections, ranking]
        captivity = _maybe_render_captivity_status(self)
        if captivity is not None:
            sections = [*sections, captivity]
        board = _maybe_render_board_postings(self, looker)
        if board is not None:
            sections = [*sections, board]
        if sections:
            return base + "\n" + "\n".join(sections)
        return base


def _maybe_render_ranking_display(obj, looker) -> str | None:
    """Render the ranking display attached to ``obj`` (if any) for ``looker``.

    Returns the rendered IC narration or None when the object has no
    ``RankingDisplay`` row. Lazy-imports the societies layer to keep the
    typeclass package free of a hard dependency on it.
    """
    from world.scenes.models import Persona
    from world.societies.models import RankingDisplay
    from world.societies.ranking_services import render_ranking_display

    try:
        display = obj.ranking_display
    except (AttributeError, RankingDisplay.DoesNotExist):
        return None

    # #981: gate the board on the looker's ACTIVE face (the telnet mirror of
    # RankingDisplayViewSet) so examining a board while wearing an alt's face is
    # gated as that alt, not the primary — never leak the other faces.
    from world.scenes.services import active_persona_for_sheet

    viewer_persona = None
    if looker is not None:
        with contextlib.suppress(AttributeError, Persona.DoesNotExist):
            viewer_persona = active_persona_for_sheet(looker.sheet_data)
    return render_ranking_display(display, viewer_persona)


def _maybe_render_captivity_status(obj) -> str | None:
    """Render the red OOC captive-status banner for a holding cell (#1500).

    When ``obj`` is a room holding one or more HELD captives, return a red,
    OOC-styled line per captive — naming them and, where a crowdfundable RANSOM
    project stands in the cell, its funding progress plus the project id to
    ``project/donate`` toward. Returns None for anything that is not a holding
    cell (the common case); gated on rooms (``location is None``) so examining a
    character or item runs no query.
    """
    # Only rooms hold captives — skip the query for characters/items/exits.
    if getattr(obj, "location", None) is not None:  # noqa: GETATTR_LITERAL
        return None
    from django.db.models import Q

    from world.captivity.constants import CaptivityStatus
    from world.captivity.models import Captivity

    held = list(
        Captivity.objects.filter(
            Q(cell__room=obj) | Q(holding_room=obj),
            status=CaptivityStatus.HELD,
        ).select_related("captive", "ransom_project")
    )
    if not held:
        return None

    lines: list[str] = []
    for cap in held:
        name = cap.captive.character.key
        project = cap.ransom_project
        if project is not None and project.threshold_target:
            lines.append(
                f"|r(OOC) {name} is held captive here. Ransom: "
                f"{project.current_progress}/{project.threshold_target} funded — "
                f"`project/donate {project.pk}=<coppers>` to help free them.|n"
            )
        else:
            lines.append(f"|r(OOC) {name} is held captive here.|n")
    return "\n".join(lines)


def _maybe_render_board_postings(obj, looker) -> str | None:
    """Render a BOARD-kind giver's eligible postings as an examine section (#2044).

    Returns None when ``obj`` is not a BOARD giver or the looker has no
    eligible postings. Otherwise returns a formatted section listing the
    postings by number (for ``mission take <n>``).
    """
    from world.missions.constants import GiverKind
    from world.missions.models import MissionGiver
    from world.missions.services.boards import postings_for_giver

    giver = (
        MissionGiver.objects.filter(target=obj, giver_kind=GiverKind.BOARD, is_active=True)
        .prefetch_related("templates")  # noqa: PREFETCH_STRING
        .first()
    )
    if giver is None:
        return None
    postings = postings_for_giver(giver, looker)
    if not postings:
        return None
    lines: list[str] = ["", f"|wNotice Board — {giver.name}|n", ""]
    for i, posting in enumerate(postings, start=1):
        summary = f" — {posting.summary}" if posting.summary else ""
        lines.append(f"  |c{i}|n. {posting.name}{summary}")
    lines.append("")
    lines.append("|xUse 'mission take <n>' to accept a posting.|n")
    return "\n".join(lines)
