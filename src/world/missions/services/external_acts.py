"""External-act beats: mission options satisfied by real non-mission acts (#1035).

Direct service calls (ADR-0009, ADR-0112) — weave_thread / create_covenant /
induct_member_via_session / use_technique call satisfy_external_act after their own
success. Failure isolation is the CALLER's job (log-and-continue); this module may
assume it runs post-commit of the host act.

Leak rule (approved spec): resolution feedback goes ONLY to the acting participant —
mirrors ``play.py::resolve_beat_option``'s actor-only STORY message. No room emit.
"""

from __future__ import annotations

import logging

from world.character_sheets.models import CharacterSheet
from world.missions.constants import ExternalAct, MissionStatus, OptionKind
from world.missions.models import (
    MissionDeedRecord,
    MissionInstance,
    MissionNode,
    MissionOption,
    MissionParticipant,
)
from world.missions.services.play import _story_text_for
from world.missions.services.resolution import resolve_option
from world.missions.types import PresentedOption
from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message

logger = logging.getLogger(__name__)

_DURABLE_ACTS = frozenset({ExternalAct.THREAD_WOVEN, ExternalAct.COVENANT_SWORN})


def _sheet_satisfies_durable_act(character_sheet: CharacterSheet, act: str) -> bool:
    if act == ExternalAct.THREAD_WOVEN:
        return character_sheet.threads.filter(retired_at__isnull=True).exists()
    if act == ExternalAct.COVENANT_SWORN:
        return character_sheet.covenant_role_assignments.filter(left_at__isnull=True).exists()
    return False


def _send_actor_story(
    character_sheet: CharacterSheet,
    instance: MissionInstance,
    option: MissionOption,
    deed: MissionDeedRecord,
) -> None:
    """Actor-only STORY narrative for an external-act resolution.

    Mirrors ``play.py::resolve_beat_option`` exactly (same ``_story_text_for``
    derivation, same ``send_narrative_message`` shape) but sends to
    ``character_sheet`` alone — no room emit (leak rule): the real act that
    satisfied this option already happened elsewhere; only the acting
    participant should learn the mission-side consequence.
    """
    presented = PresentedOption(
        option=option,
        kind=option.option_kind,
        check_type=None,
        base_risk=0,
        ic_framing=option.authored_ic_framing,
        owner=character_sheet.character,
    )
    story_text = _story_text_for(presented, deed, instance.template.name)
    send_narrative_message(
        recipients=[character_sheet],
        body=story_text,
        category=NarrativeCategory.STORY,
        ooc_note=f"Mission beat resolved via external act (instance #{instance.pk}).",
    )


def satisfy_external_act(character_sheet: CharacterSheet, act: str) -> list[MissionDeedRecord]:
    """Resolve every ACTIVE mission of *character_sheet* waiting on *act*.

    Finds each ACTIVE :class:`MissionInstance` where ``character_sheet.character``
    is a participant whose current node has a live ``EXTERNAL_ACT`` option for
    *act*, resolves it on that participant's behalf via ``resolve_option``, and
    sends the actor-only STORY narrative. An instance whose current node has no
    matching option (wrong act, or no EXTERNAL_ACT option at all) is untouched.
    Returns the collected deeds (empty list when nothing matched).
    """
    character = character_sheet.character
    deeds: list[MissionDeedRecord] = []
    participants = MissionParticipant.objects.filter(
        character=character,
        instance__status=MissionStatus.ACTIVE,
    ).select_related("instance", "instance__current_node", "instance__template")
    for participant in participants:
        instance = participant.instance
        node = instance.current_node
        if node is None:
            continue
        option = node.options.filter(
            option_kind=OptionKind.EXTERNAL_ACT,
            required_act=act,
        ).first()
        if option is None:
            continue
        deed = resolve_option(instance, node, option, participant)
        deeds.append(deed)
        _send_actor_story(character_sheet, instance, option, deed)
    return deeds


def fast_forward_external_acts(instance: MissionInstance, node: MissionNode) -> None:
    """Auto-resolve *node*'s durable ``EXTERNAL_ACT`` option, if any (#1035).

    Called at the end of ``enter_node``. When the contract-holder's sheet
    already durably satisfies a THREAD_WOVEN/COVENANT_SWORN option on *node*
    (``_DURABLE_ACTS`` — TECHNIQUE_CAST is transient and NEVER fast-forwards;
    a fresh cast is the point), resolves it immediately via ``resolve_option``
    on the contract holder's behalf — no actor-only message is sent here
    (that's ``satisfy_external_act``'s job for the real-act path; a
    fast-forward is a silent graph shortcut, not a player action).

    Recursion: resolving the option can advance the run into a new node whose
    own durable act is ALSO already satisfied (e.g. two durable-gated nodes
    authored back to back). Re-entering ``enter_node`` on that new node calls
    this function again, so the fast-forward naturally walks the whole
    already-satisfied prefix of the chain. Termination is guaranteed because
    authored chains are finite (graph authoring, not player input, bounds the
    depth) — no defensive counter added; it would be untestable dead code.
    """
    holder = instance.participants.filter(is_contract_holder=True).first()
    if holder is None:
        return
    sheet = getattr(holder.character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None:
        return
    option = node.options.filter(
        option_kind=OptionKind.EXTERNAL_ACT,
        required_act__in=_DURABLE_ACTS,
    ).first()
    if option is None or not _sheet_satisfies_durable_act(sheet, option.required_act):
        return
    resolve_option(instance, node, option, holder)
    instance.refresh_from_db()
    if instance.current_node is not None:
        from world.missions.services.resolution import enter_node  # noqa: PLC0415

        enter_node(instance, instance.current_node)
