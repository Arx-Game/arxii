"""New-player tutorial chain seeder — T1 "Arrival" through T7 "The Long Dark" (#1035).

Seeds seven ``MissionTemplate`` rows that walk a fresh character through the
level-1 loops on both web and telnet: trigger/environmental discovery
(T1-T2), an NPC-carried external-act beat (T3, transient TECHNIQUE_CAST), a
notice-board job that summons the next step (T4), and the durable external-act
beats that anchor the chain to real non-mission acts (T5 THREAD_WOVEN, T6
COVENANT_SWORN), ending in the first legend-risk mission (T7). Everything is
mission content over existing machinery — no new tutorial engine, no
TutorialProgress model (chain progress IS the sequence of ``MissionInstance``
rows); see ADR-0111.

Chain gating (design decision, stated per the task brief's instruction to read
``visibility.py`` and choose a surface): every T(n+1) template's
``availability_rule`` carries the real predicate-tree grammar
``{"leaf": "has_completed_mission", "params": {"template_id": <T(n).pk>}}``,
with ``visibility=RESTRICTED`` so the rule is actually consulted (#870 —
``MissionVisibility.OPEN`` skips ``availability_rule`` entirely).
``MissionTemplate.availability_rule`` is the chosen surface, NOT
``MissionOfferDetails.requirements_override``: ``template_visible_to`` is the
SINGLE gate consulted uniformly by all three giver surfaces this chain uses —
trigger dispatch (``trigger_dispatch._dispatch_from_giver``), board postings
(``boards.postings_for_giver``), AND the NPC-offer path
(``npc_services.services._mission_gates_pass``) — while
``requirements_override`` is NPC-offer-only and would need duplicate
authoring to also cover T2's ENVIRONMENTAL_DETAIL giver and T4's BOARD giver.
T1 carries no predecessor, so it alone stays OPEN with an empty rule.

KNOWN GAP (out of this seeder's scope — flagged for follow-up, not fixed
here): ``has_completed_mission`` is scoped to
``MissionInstance.accepted_as_persona`` (set only by the NPC-offer issuance
path, ``npc_services.services``/``offer_handler``). Trigger-dispatched and
board-taken runs (T1, T2, T4) are granted via ``staff_assign_mission``, which
never sets ``accepted_as_persona`` — so a T(n+1) gate keyed on a
trigger/board-granted T(n) will not open via the persona-scoped predicate
until that gap is closed in ``trigger_dispatch.py``/``boards.py``. This
affects the T1→T2, T2→T3, and (for the availability_rule leg only, not the
FOLLOW_ON_SUMMONS leg) T4→T5 transitions. Recorded here rather than silently
"fixed" by this seeder, since the fix lives in the dispatch services, not the
content.

Tutor NPC: mirrors ``world.npc_services.seeds.ensure_builders_guild_clerk_role``'s
idempotent (role, label)-keyed offer pattern (get_or_create on
``NPCServiceOffer``, then a ``MissionOfferDetails`` row on first creation) —
the closest existing precedent for a class-1 NPCRole + MISSION-kind offers,
since no prior seed cluster combines the two. The tutor is placed as a
``Functionary`` (class-1, room-anchored) in the canonical starting room
(``ensure_canonical_fallback_room``, #2121) so a freshly finalized character
can always reach them.

Idempotent throughout: templates/roles/offers via ``get_or_create``-style
factories or direct ORM lookups; node/option/route graphs guarded by
``template.nodes.exists()`` (mirrors ``game_content/missions.py``); the T4→T5
follow-on-summons reward line is guarded separately since it can only be
authored once T5's offer exists (a real ordering dependency: T4's reward
line needs T5's ``NPCServiceOffer`` FK; T5's availability_rule needs T4's pk).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.missions.constants import (
    DeedRewardSink,
    ExternalAct,
    GiverKind,
    MissionVisibility,
    OptionKind,
    OptionSource,
)
from world.npc_services.constants import DrawMode, OfferKind

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionOptionRoute, MissionTemplate
    from world.npc_services.models import NPCRole, NPCServiceOffer

_T1_NAME = "Arrival"
_T2_NAME = "What the Walls Remember"
_T3_NAME = "First Spark"
_T4_NAME = "A Simple Job"
_T5_NAME = "The Loom"
_T6_NAME = "Sworn Together"
_T7_NAME = "The Long Dark"

_DETAIL_OBJECT_KEY = "a faint scorch mark on the wall"
_DETAIL_OBJECT_TYPECLASS = "typeclasses.objects.Object"

_ROOM_TRIGGER_GIVER_NAME = "Tutorial Arrival Trigger"
_DETAIL_GIVER_NAME = "Tutorial Wall-Scorch Detail"

_TUTOR_ROLE_NAME = "Threshold Warden"


@dataclass
class TutorialSeedResult:
    """Returned by seed_tutorial_dev(). Templates in chain order, T1 first."""

    templates: list[MissionTemplate]
    tutor_role: NPCRole


def _has_completed(template_id: int) -> dict:
    """Build the real predicate-tree leaf gating a T(n+1) template on T(n).

    ``world.predicates.predicates.evaluate`` / ``_resolve_has_completed_mission``
    is the consumer — NOT the docstring-shorthand form.
    """
    return {"leaf": "has_completed_mission", "params": {"template_id": template_id}}


def _ensure_detail_object(room: ObjectDB) -> ObjectDB:
    """Get-or-create the examinable wall-scorch detail Object, located IN ``room``.

    Mirrors ``_ensure_notice_board_object`` (``game_content/missions.py``):
    ``ObjectDB.db_key`` is not unique in Evennia, so lookup uses
    ``.filter().first()``.
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    existing = ObjectDB.objects.filter(
        db_key=_DETAIL_OBJECT_KEY, db_typeclass_path=_DETAIL_OBJECT_TYPECLASS
    ).first()
    if existing is not None:
        return existing
    return evennia_create.create_object(
        typeclass=_DETAIL_OBJECT_TYPECLASS,
        key=_DETAIL_OBJECT_KEY,
        location=room,
        home=room,
    )


def _seed_t1(room: ObjectDB) -> MissionTemplate:
    """T1 "Arrival" — ROOM_TRIGGER, no predecessor, OPEN visibility."""
    from world.missions.factories import (  # noqa: PLC0415
        MissionGiverFactory,
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionOptionRouteRewardFactory,
        MissionTemplateFactory,
    )

    template = MissionTemplateFactory(
        name=_T1_NAME,
        summary=(
            "The city swallows you whole the moment you step through its gates — "
            "noise, smoke, and a thousand strangers who were here before you."
        ),
        risk_tier=1,
        level_band_min=1,
        level_band_max=5,
        visibility=MissionVisibility.OPEN,
    )
    giver = MissionGiverFactory(
        name=_ROOM_TRIGGER_GIVER_NAME,
        giver_kind=GiverKind.ROOM_TRIGGER,
        target=room,
    )
    giver.templates.add(template)

    if not template.nodes.exists():
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="Take stock of where you've landed.",
        )
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        MissionOptionRouteRewardFactory(
            route=route,
            sink=DeedRewardSink.MONEY,
            amount=25,
            contract_holder_only=True,
        )
    return template


def _seed_t2(room: ObjectDB, gate_template: MissionTemplate) -> MissionTemplate:
    """T2 "What the Walls Remember" — ENVIRONMENTAL_DETAIL, gated on T1."""
    from world.missions.factories import (  # noqa: PLC0415
        MissionGiverFactory,
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionOptionRouteRewardFactory,
        MissionTemplateFactory,
    )

    template = MissionTemplateFactory(
        name=_T2_NAME,
        summary=(
            "A scorch mark blackens the plaster here, old enough to have been "
            "painted over twice and stubborn enough to keep bleeding through."
        ),
        risk_tier=1,
        level_band_min=1,
        level_band_max=5,
        visibility=MissionVisibility.RESTRICTED,
        availability_rule=_has_completed(gate_template.pk),
    )
    detail_obj = _ensure_detail_object(room)
    giver = MissionGiverFactory(
        name=_DETAIL_GIVER_NAME,
        giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
        target=detail_obj,
    )
    giver.templates.add(template)

    if not template.nodes.exists():
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="Press a hand to the old burn and listen.",
        )
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        MissionOptionRouteRewardFactory(
            route=route,
            sink=DeedRewardSink.MONEY,
            amount=25,
            contract_holder_only=True,
        )
    return template


def _ensure_tutor_role() -> NPCRole:
    """Get-or-create the tutor NPCRole (#1035).

    Mirrors ``ensure_builders_guild_clerk_role`` (``npc_services/seeds.py``)
    — the established (role, label)-keyed idempotent offer pattern.
    """
    from world.npc_services.models import NPCRole  # noqa: PLC0415

    role, _ = NPCRole.objects.get_or_create(
        name=_TUTOR_ROLE_NAME,
        defaults={
            "description": (
                "A quiet guide who meets the newly arrived at the threshold of "
                "the city and walks them through their first real steps."
            ),
            "default_description_template": (
                "Someone unassuming waits near the gate, patient in the way of "
                "people who have done this many times before."
            ),
            "default_rapport_starting_value": 0,
        },
    )
    return role


def _ensure_tutor_functionary(role: NPCRole, room: ObjectDB) -> None:
    """Place the tutor role in the canonical starting room as a Functionary."""
    from world.areas.services import get_room_profile  # noqa: PLC0415
    from world.npc_services.models import Functionary  # noqa: PLC0415

    room_profile = get_room_profile(room)
    Functionary.objects.get_or_create(role=role, room=room_profile, defaults={"is_active": True})


def _ensure_offer(
    role: NPCRole, label: str, mission_template: MissionTemplate, *, draw_priority: int = 1
) -> NPCServiceOffer:
    """Idempotent (role, label)-keyed MISSION offer + its MissionOfferDetails row.

    MENU draw_mode — the tutor's offers are deterministic (always shown when
    eligible), not a randomized POOL draw; ``draw_priority`` is set anyway per
    the spec (#1035) for authoring-intent consistency even though POOL is the
    field's primary consumer.
    """
    from world.npc_services.models import MissionOfferDetails, NPCServiceOffer  # noqa: PLC0415

    offer, created = NPCServiceOffer.objects.get_or_create(
        role=role,
        label=label,
        defaults={
            "kind": OfferKind.MISSION,
            "draw_mode": DrawMode.MENU,
            "eligibility_rule": {},
            "rapport_requirement": 0,
            "is_final": True,
        },
    )
    if created:
        MissionOfferDetails.objects.create(
            offer=offer,
            mission_template=mission_template,
            requirements_override={},
            draw_priority=draw_priority,
        )
    return offer


def _seed_t3(gate_template: MissionTemplate) -> MissionTemplate:
    """T3 "First Spark" — NPC offer, EXTERNAL_ACT/TECHNIQUE_CAST (transient)."""
    from world.missions.factories import (  # noqa: PLC0415
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionOptionRouteRewardFactory,
        MissionTemplateFactory,
    )

    template = MissionTemplateFactory(
        name=_T3_NAME,
        summary=(
            'The Warden presses a cold coal into your palm. "Wake it," they say. '
            '"Show me you can call something out of nothing."'
        ),
        risk_tier=1,
        level_band_min=1,
        level_band_max=5,
        visibility=MissionVisibility.RESTRICTED,
        availability_rule=_has_completed(gate_template.pk),
    )
    if not template.nodes.exists():
        # TECHNIQUE_CAST is transient (never fast-forwards, #1035) — placement
        # is free, but it stays on the entry node for consistency with the
        # durable-act templates that follow.
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.TECHNIQUE_CAST,
            authored_ic_framing="Cast a technique, however small.",
        )
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        MissionOptionRouteRewardFactory(
            route=route,
            sink=DeedRewardSink.MONEY,
            amount=25,
            contract_holder_only=True,
        )
    return template


def _seed_t4(
    tutor_role: NPCRole, gate_template: MissionTemplate
) -> tuple[MissionTemplate, MissionOptionRoute]:
    """T4 "A Simple Job" — BOARD, reusing seed_missions_dev's board giver.

    Returns the template AND its terminal route so the caller can attach the
    FOLLOW_ON_SUMMONS reward line once T5's offer exists (a real ordering
    dependency — see module docstring). Takes no ``room`` argument — the
    board (and the room it sits in) come from ``seed_missions_dev()`` itself.
    """
    from world.missions.factories import (  # noqa: PLC0415
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionOptionRouteRewardFactory,
        MissionTemplateFactory,
    )
    from world.seeds.game_content.missions import seed_missions_dev  # noqa: PLC0415

    template = MissionTemplateFactory(
        name=_T4_NAME,
        summary=(
            "A notice, pinned crooked among a dozen others: coin for anyone "
            "willing to do a plain, unglamorous job and report back."
        ),
        risk_tier=2,
        level_band_min=1,
        level_band_max=5,
        visibility=MissionVisibility.RESTRICTED,
        availability_rule=_has_completed(gate_template.pk),
        report_to_role=tutor_role,
    )
    # Self-contained (does not assume the "missions" cluster already ran) —
    # idempotent, so this both creates-on-first-run and reuses thereafter.
    # The board and its room are shared with the starter-mission board
    # (#2121); T4 is added to the SAME giver, not a new one.
    board_giver = seed_missions_dev().giver
    board_giver.templates.add(template)

    if not template.nodes.exists():
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="Take the job and see it through.",
        )
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        MissionOptionRouteRewardFactory(
            route=route,
            sink=DeedRewardSink.MONEY,
            amount=75,
            contract_holder_only=True,
        )
    else:
        entry = template.nodes.get(is_entry=True)
        option = entry.options.get()
        route = option.routes.get(outcome_tier__isnull=True)
    return template, route


def _ensure_t4_followon_reward(route: MissionOptionRoute, t5_offer: NPCServiceOffer) -> None:
    """Attach the T4→T5 FOLLOW_ON_SUMMONS reward line once T5's offer exists."""
    from world.missions.factories import MissionOptionRouteRewardFactory  # noqa: PLC0415

    if route.reward_templates.filter(sink=DeedRewardSink.FOLLOW_ON_SUMMONS).exists():
        return
    MissionOptionRouteRewardFactory(
        route=route,
        sink=DeedRewardSink.FOLLOW_ON_SUMMONS,
        amount=None,
        followon_offer=t5_offer,
        followon_message=(
            "The Warden sends word: there is a thread that wants weaving, "
            "and they think you're ready to try."
        ),
        followon_expiry_hours=None,
        contract_holder_only=True,
    )


def _seed_t5(gate_template: MissionTemplate) -> MissionTemplate:
    """T5 "The Loom" — NPC offer, EXTERNAL_ACT/THREAD_WOVEN (durable)."""
    from world.missions.factories import (  # noqa: PLC0415
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionOptionRouteRewardFactory,
        MissionTemplateFactory,
    )

    template = MissionTemplateFactory(
        name=_T5_NAME,
        summary=(
            "The Warden shows you the loom that isn't wood or wire — the one "
            "strung between people who choose to be bound to each other."
        ),
        risk_tier=2,
        level_band_min=1,
        level_band_max=5,
        visibility=MissionVisibility.RESTRICTED,
        availability_rule=_has_completed(gate_template.pk),
    )
    if not template.nodes.exists():
        # Durable act (#1035 Ruling 1): authored on the ENTRY node so
        # fast_forward_external_acts (enter_node) can resolve it immediately
        # for a character who already wove a thread before accepting.
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.THREAD_WOVEN,
            authored_ic_framing="Weave a thread with someone who matters.",
        )
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        MissionOptionRouteRewardFactory(
            route=route,
            sink=DeedRewardSink.MONEY,
            amount=50,
            contract_holder_only=True,
        )
    return template


def _seed_t6(gate_template: MissionTemplate) -> MissionTemplate:
    """T6 "Sworn Together" — NPC offer, EXTERNAL_ACT/COVENANT_SWORN (durable)."""
    from world.missions.factories import (  # noqa: PLC0415
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionOptionRouteRewardFactory,
        MissionTemplateFactory,
    )

    template = MissionTemplateFactory(
        name=_T6_NAME,
        summary=(
            '"None of us stand for long alone," the Warden says. "Swear '
            'yourself to a covenant, and see what holds you up."'
        ),
        risk_tier=3,
        level_band_min=1,
        level_band_max=5,
        visibility=MissionVisibility.RESTRICTED,
        availability_rule=_has_completed(gate_template.pk),
    )
    if not template.nodes.exists():
        # Durable act (#1035 Ruling 1): entry node, same rationale as T5.
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.EXTERNAL_ACT,
            source_kind=OptionSource.AUTHORED,
            required_act=ExternalAct.COVENANT_SWORN,
            authored_ic_framing="Swear yourself to a covenant.",
        )
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        MissionOptionRouteRewardFactory(
            route=route,
            sink=DeedRewardSink.MONEY,
            amount=50,
            contract_holder_only=True,
        )
    return template


def _seed_t7(gate_template: MissionTemplate) -> MissionTemplate:
    """T7 "The Long Dark" — NPC offer, risk_tier=4, first legend-risk mission."""
    from world.missions.factories import (  # noqa: PLC0415
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionOptionRouteRewardFactory,
        MissionTemplateFactory,
    )

    template = MissionTemplateFactory(
        name=_T7_NAME,
        summary=(
            "The Warden's voice drops. \"This one isn't practice. Whatever "
            "waits past the old wall doesn't care that you're new.\""
        ),
        risk_tier=4,
        level_band_min=1,
        level_band_max=5,
        visibility=MissionVisibility.RESTRICTED,
        availability_rule=_has_completed(gate_template.pk),
    )
    if not template.nodes.exists():
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
            authored_ic_framing="Go into the long dark.",
        )
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        MissionOptionRouteRewardFactory(
            route=route,
            sink=DeedRewardSink.MONEY,
            amount=150,
            contract_holder_only=True,
        )
        # #2051 legend guard: LEGEND_POINTS requires risk_tier >= LEGEND_RISK_FLOOR_TIER
        # (4) — satisfied here since this template's risk_tier is 4.
        MissionOptionRouteRewardFactory(
            route=route,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
            contract_holder_only=True,
        )
    return template


def seed_tutorial_dev() -> TutorialSeedResult:
    """Seed the seven-template new-player tutorial chain T1-T7 (#1035).

    Registered as the "tutorial" cluster in ``world.seeds.clusters`` — reachable
    from the Big Button, after "missions" (the shared board giver + room),
    "character_creation" (the canonical starting room), and self-contained
    for the tutor NPCRole (no other cluster's content is required to create
    it). Idempotent throughout; never overwrites a staff edit.

    Returns:
        TutorialSeedResult with the seven templates (T1 first) and the tutor
        NPCRole.
    """
    from world.seeds.character_creation import ensure_canonical_fallback_room  # noqa: PLC0415

    room = ensure_canonical_fallback_room()

    t1 = _seed_t1(room)
    t2 = _seed_t2(room, t1)

    tutor_role = _ensure_tutor_role()
    _ensure_tutor_functionary(tutor_role, room)

    t3 = _seed_t3(t2)
    _ensure_offer(tutor_role, "Kindle a first spark", t3)

    t4, t4_terminal_route = _seed_t4(tutor_role, t3)

    t5 = _seed_t5(t4)
    t5_offer = _ensure_offer(tutor_role, "Learn the loom's thread-work", t5)

    _ensure_t4_followon_reward(t4_terminal_route, t5_offer)

    t6 = _seed_t6(t5)
    _ensure_offer(tutor_role, "Swear the first oath", t6)

    t7 = _seed_t7(t6)
    _ensure_offer(tutor_role, "Answer the long dark's call", t7)

    return TutorialSeedResult(templates=[t1, t2, t3, t4, t5, t6, t7], tutor_role=tutor_role)
