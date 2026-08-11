"""Examine-time display extras — the ``LookAction`` aggregation seam (#3084).

Every examine-time behavior authored over the last year (reactive scars via
EXAMINE_PRE/EXAMINED, ranking displays, captivity status, board postings,
catering history, crafted provenance, room functionaries/notice-board hint/
heat, and the mission ENVIRONMENTAL_DETAIL/BOARD dispatch) used to render
only through ``ObjectParent.return_appearance``/``at_examined`` on the
typeclass mixin — a path with zero live callers, since real play renders
through ``LookAction`` -> ``BaseState.return_appearance`` instead, which
never touched the typeclass hook. See ADR-0213 for the seam decision.

``gather_examine_extras`` is the one aggregation call ``LookAction.execute()``
makes (after ``target_state.return_appearance(...)``) to reach every one of
those behaviors from real play, on both telnet and web. Lazy imports
throughout keep this module (and the ``actions`` package generally) free of
a hard dependency on ``world.*`` subsystems at import time.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


@dataclass
class ExamineExtras:
    """Result of gathering examine-time display extras for one deliberate look.

    ``cancelled`` is True when a reactive trigger cancelled EXAMINE_PRE — the
    prior contract: the caller shows nothing and EXAMINED never fires.
    """

    cancelled: bool
    sections: list[str] = field(default_factory=list)


def gather_examine_extras(observer: ObjectDB, target: ObjectDB) -> ExamineExtras:
    """Gather every examine-time display extra for ``observer`` looking at ``target``.

    Order: emit EXAMINE_PRE (cancellable, mutable ``sections`` list). On
    cancellation, return with no sections and never emit EXAMINED. Otherwise
    collect the pre-payload's sections, run the five object-section
    renderers (ranking, captivity, board postings, catering history, crafted
    provenance), run the room-only extras (functionaries, notice-board hint,
    heat line) when ``target`` is a room, run the mission
    ENVIRONMENTAL_DETAIL/BOARD dispatch, then emit EXAMINED.
    """
    from flows.constants import EventName  # noqa: PLC0415
    from flows.emit import emit_event  # noqa: PLC0415
    from flows.events.payloads import ExaminedPayload, ExaminePrePayload  # noqa: PLC0415

    # For rooms, target is its own location; for characters/objects, use the
    # containing room.
    location = target.location if target.location is not None else target
    pre = ExaminePrePayload(observer=observer, target=target)
    stack = emit_event(
        EventName.EXAMINE_PRE,
        pre,
        location=location,
    )
    if stack.was_cancelled():
        return ExamineExtras(cancelled=True, sections=[])

    # Carry the decorated sections forward.
    sections: list[str] = list(pre.sections)

    ranking = _maybe_render_ranking_display(target, observer)
    if ranking is not None:
        sections.append(ranking)
    captivity = _maybe_render_captivity_status(target)
    if captivity is not None:
        sections.append(captivity)
    board = _maybe_render_board_postings(target, observer)
    if board is not None:
        sections.append(board)
    catering = _maybe_render_catering_history(target)
    if catering is not None:
        sections.append(catering)
    provenance = _maybe_render_crafted_provenance(target)
    if provenance is not None:
        sections.append(provenance)

    if target.location is None:
        sections.extend(_room_examine_sections(target, observer))

    # Mission ENVIRONMENTAL_DETAIL/BOARD dispatch (#729), moved from the
    # inline #3044 block previously in ``LookAction.execute()``. run_safely
    # (#1164): a failure is captured + the examiner told, never breaking the
    # look.
    from world.missions.services.trigger_dispatch import (  # noqa: PLC0415
        maybe_dispatch_on_examine,
    )
    from world.player_submissions.services import run_safely  # noqa: PLC0415

    run_safely(
        "mission_dispatch_on_examine",
        lambda: maybe_dispatch_on_examine(observer, target),
        actor=observer,
    )

    post = ExaminedPayload(observer=observer, target=target)
    emit_event(
        EventName.EXAMINED,
        post,
        location=location,
    )

    return ExamineExtras(cancelled=False, sections=sections)


def _room_examine_sections(room, looker) -> list[str]:
    """Room-only examine extras, moved from ``Room.return_appearance``.

    Functionaries are abstracted (object-less) NPCs, so they never appear in
    ``room.contents`` — surface them explicitly so a placed room-feature NPC
    is actually visible (and hint that you can ``hire`` them) (#1766). A
    Notice Board is a feature, not an object, so hint it on look (#1450). The
    looker's own pursuit heat here is self-only; empty when SAFE (#1765).
    """
    sections: list[str] = []

    from world.areas.services import get_room_profile  # noqa: PLC0415
    from world.npc_services.functionaries import functionaries_in_room  # noqa: PLC0415

    profile = get_room_profile(room)
    names = [f.display_name for f in functionaries_in_room(profile)]
    if names:
        sections.append(f"|wHere you can speak with:|n {', '.join(names)}")

    # #1450 — a Notice Board is a feature, not an object, so hint it on look
    # (a Town Crier already surfaces via the functionaries line above).
    from world.room_features.constants import RoomFeatureServiceStrategy  # noqa: PLC0415
    from world.room_features.services import active_hub_feature  # noqa: PLC0415

    hub = active_hub_feature(profile)
    if hub is not None and (
        hub.feature_kind.service_strategy == RoomFeatureServiceStrategy.NOTICE_BOARD
    ):
        # PLACEHOLDER flavor line (Apostate rewrite pass; keep dash-free).
        sections.append("|wA notice board stands here; try |ctidings local|w.|n")

    # #1765 — the looker's own pursuit heat here (self-only; None when SAFE).
    from world.justice.display import room_heat_line  # noqa: PLC0415

    heat_line = room_heat_line(looker, room)
    if heat_line:
        sections.append(heat_line)

    return sections


def _maybe_render_crafted_provenance(obj) -> str | None:
    """The crafted mechanical line + credits for an item, or None (#2878).

    "Of divine quality, quite menacing and slightly alluring. Designed by X;
    crafted by Y." — the examine layer at the bottom of the desc, shared with
    the web serializer via ``crafted_provenance_line``.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        instance = obj.item_instance
    except (AttributeError, ObjectDoesNotExist):
        return None
    if instance is None:
        return None
    from world.items.services.crafted_display import crafted_provenance_line  # noqa: PLC0415

    line = crafted_provenance_line(instance)
    if line is None:
        return None
    return f"|w{line}|n"


def _maybe_render_catering_history(obj) -> str | None:
    """The catering souvenir line(s) for an item, or None (#2869).

    A vessel or dish that served at an event carries that memory for good —
    "This amphora was used for catering at Big Bob's Nameday." A well-
    travelled piece lists every occasion, newest first.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        instance = obj.item_instance
    except (AttributeError, ObjectDoesNotExist):
        return None
    if instance is None:
        return None
    from world.events.services import catering_history  # noqa: PLC0415

    rows = catering_history(instance)
    if not rows:
        return None
    name = instance.display_name
    return "\n".join(f"|wThis {name} was used for catering at {row.event.name}.|n" for row in rows)


def _maybe_render_ranking_display(obj, looker) -> str | None:
    """Render the ranking display attached to ``obj`` (if any) for ``looker``.

    Returns the rendered IC narration or None when the object has no
    ``RankingDisplay`` row. Lazy-imports the societies layer to keep this
    module free of a hard dependency on it.
    """
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.societies.models import RankingDisplay  # noqa: PLC0415
    from world.societies.ranking_services import render_ranking_display  # noqa: PLC0415

    try:
        display = obj.ranking_display
    except (AttributeError, RankingDisplay.DoesNotExist):
        return None

    # #981: gate the board on the looker's ACTIVE face (the telnet mirror of
    # RankingDisplayViewSet) so examining a board while wearing an alt's face is
    # gated as that alt, not the primary — never leak the other faces.
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

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
    if obj.location is not None:
        return None
    from django.db.models import Q  # noqa: PLC0415

    from world.captivity.constants import CaptivityStatus  # noqa: PLC0415
    from world.captivity.models import Captivity  # noqa: PLC0415

    # Both room FKs are RoomProfile now (#2608); RoomProfile shares ObjectDB's pk,
    # so the room's own pk is the profile id — no join needed to look it up.
    held = list(
        Captivity.objects.filter(
            Q(cell__room_id=obj.pk) | Q(holding_room_id=obj.pk),
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
    from world.missions.constants import GiverKind  # noqa: PLC0415
    from world.missions.models import MissionGiver  # noqa: PLC0415
    from world.missions.services.boards import postings_for_giver  # noqa: PLC0415

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
