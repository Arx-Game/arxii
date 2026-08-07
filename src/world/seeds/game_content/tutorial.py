"""New-player tutorial chain seeder — T1 "Arrival" through T7 "The Long Dark" (#1035).

Seeds seven ``MissionTemplate`` rows that walk a fresh character through the
level-1 loops on both web and telnet: trigger/environmental discovery
(T1-T2), an NPC-carried external-act beat (T3, transient TECHNIQUE_CAST), a
notice-board job that summons the next step (T4), and the durable external-act
beats that anchor the chain to real non-mission acts (T5 THREAD_WOVEN, T6
COVENANT_SWORN), ending in the first legend-risk mission (T7). Everything is
mission content over existing machinery — no new tutorial engine, no
TutorialProgress model (chain progress IS the sequence of ``MissionInstance``
rows); see ADR-0112.

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

FIXED (review follow-up to this seeder, #1035): ``has_completed_mission`` is
scoped to ``MissionInstance.accepted_as_persona``. Trigger-dispatched
(``trigger_dispatch._grant``) and board-taken (``boards.take_from_board``)
runs now thread the persona already resolved for the visibility gate into
``staff_assign_mission(..., persona=...)``, so ``accepted_as_persona`` is set
on T1/T2/T4-style grants exactly as it already was for NPC-offer grants
(``offer_handler.issue_mission``) — the T1→T2, T2→T3, and T4→T5
(availability_rule leg) transitions all open via the persona-scoped
predicate in live play, not just under staff/NPC-offer grants.

Tutor NPC: mirrors ``world.npc_services.seeds.ensure_builders_guild_clerk_role``'s
idempotent (role, label)-keyed offer pattern (get_or_create on
``NPCServiceOffer``, then a ``MissionOfferDetails`` row on first creation) —
the closest existing precedent for a class-1 NPCRole + MISSION-kind offers,
since no prior seed cluster combines the two. The tutor is placed as a
``Functionary`` (class-1, room-anchored) in the canonical starting room
(``ensure_canonical_fallback_room``, #2121) so a freshly finalized character
can always reach them.

Idempotent throughout: templates/roles/offers via ``get_or_create``-style
lookups or direct ORM lookups; the T4→T5 follow-on-summons reward line is
guarded separately since it can only be authored once T5's offer exists (a
real ordering dependency: T4's reward line needs T5's ``NPCServiceOffer`` FK;
T5's availability_rule needs T4's pk).

``missions.MissionTemplate``/``MissionNode``/``MissionOption``/
``MissionOptionRoute``/``MissionOptionRouteReward`` are ALL content-repo-owned
(#2698) — this entire seven-template chain (+ the "Terms of Engagement"
consent primer) is genuinely-unauthored demo/tutorial content, so every row
is looked up rather than invented unless ``SEED_SAMPLE_CONTENT`` is on. The
chain is linear and each step's ``availability_rule`` gates on the previous
step's pk, so a missing template cascades: every ``_seed_t*``/
``_seed_consent_primer`` helper returns ``None`` when its own template (or the
gate it needs) isn't authored/sampled, and ``seed_tutorial_dev()`` skips the
rest of the chain past the first gap rather than building a malformed gate.
``NPCRole``/``Functionary``/``NPCServiceOffer``/``MissionGiver`` are NOT
content models and keep seeding unconditionally; ``_ensure_offer`` skips only
when the ``mission_template`` it would wrap is ``None`` (a required FK on
``MissionOfferDetails``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from world.missions.constants import (
    ArcScope,
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    ExternalAct,
    GiverKind,
    MissionVisibility,
    OptionKind,
    OptionSource,
    RewardGroupRule,
)
from world.npc_services.constants import DrawMode, OfferKind

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionOption, MissionOptionRoute, MissionTemplate
    from world.npc_services.models import NPCRole, NPCServiceOffer

_T1_NAME = "Arrival"
_T2_NAME = "What the Walls Remember"
_T3_NAME = "First Spark"
_T4_NAME = "A Simple Job"
_T5_NAME = "The Loom"
_T6_NAME = "Sworn Together"
_T7_NAME = "The Long Dark"
_TC_NAME = "Terms of Engagement"

_DETAIL_OBJECT_KEY = "a faint scorch mark on the wall"
_DETAIL_OBJECT_TYPECLASS = "typeclasses.objects.Object"

_ROOM_TRIGGER_GIVER_NAME = "Tutorial Arrival Trigger"
_DETAIL_GIVER_NAME = "Tutorial Wall-Scorch Detail"

_TUTOR_ROLE_NAME = "Threshold Warden"


@dataclass
class TutorialSeedResult:
    """Returned by seed_tutorial_dev(). Templates in chain order, T1 first.

    ``templates`` holds only the chain steps that are actually authored/
    sampled (#2698) — a gap partway through the linear chain leaves every
    later step out of this list, never a ``None`` placeholder.

    ``consent_template`` is the "Terms of Engagement" antagonism-consent primer (#2170) —
    a tutor-offered side-step gated on T1, parallel to the T2..T7 spine.
    ``None`` when T1 itself isn't authored/sampled.

    ``tutor_role`` is ``None`` when the "Threshold Warden" ``NPCRole`` (content-
    repo-owned, #2698) isn't authored/sampled — every tutor-offer/Functionary
    step that depends on it is skipped in that case (see ``seed_tutorial_dev``).
    """

    templates: list[MissionTemplate]
    tutor_role: NPCRole | None
    consent_template: MissionTemplate


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


def _seed_template(
    name: str, *, summary: str, risk_tier: int, **extra: object
) -> MissionTemplate | None:
    """Look up (or, under SEED_SAMPLE_CONTENT, invent) one tutorial-chain MissionTemplate.

    Shared shape across every T1-T7 + consent-primer template: level_band 1-5
    (all seeded within the low band), ``arc_scope=GLOBAL``, no cooldown, no
    replace chance, all-equal reward split. ``**extra`` carries the per-template
    knobs (``visibility``/``availability_rule``/``report_to_role``/``epilogue``).
    Content-repo-owned (#2698).
    """
    from world.missions.models import MissionTemplate  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    defaults = {
        "summary": summary,
        "epilogue": "",
        "risk_tier": risk_tier,
        "level_band_min": 1,
        "level_band_max": 5,
        "base_weight": 1,
        "created_in_era": None,
        "arc_scope": ArcScope.GLOBAL,
        "percent_replace": 0,
        "cooldown": timedelta(0),
        "reward_group_rule": RewardGroupRule.ALL_EQUAL,
        "is_active": True,
        "visibility": MissionVisibility.RESTRICTED,
    }
    defaults.update(extra)
    return authored_or_sample(MissionTemplate, defaults, name=name)


def _seed_entry_option(
    template: MissionTemplate | None,
    *,
    option_kind: str,
    authored_ic_framing: str = "",
    required_act: str = "",
) -> MissionOption | None:
    """Look up (or invent) the shared entry-node + single-option graph shape.

    T1/T2/T3/T4/T5/T6/T7 and the consent primer all share this exact shape:
    one entry ``MissionNode``, one ``MissionOption`` (key="option-0"). Returns
    the option (or ``None`` when ``template``, the node, or the option itself
    isn't authored/sampled) — content-repo-owned (#2698).
    """
    from world.missions.models import MissionNode, MissionOption  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    if template is None:
        return None
    entry = authored_or_sample(
        MissionNode,
        {"is_entry": True, "conflict_mode": ConflictMode.GROUP_VOTE},
        template=template,
        key="entry",
    )
    if entry is None:
        return None
    return authored_or_sample(
        MissionOption,
        {
            "order": 0,
            "option_kind": option_kind,
            "source_kind": OptionSource.AUTHORED,
            "authored_ic_framing": authored_ic_framing,
            "required_act": required_act,
        },
        node=entry,
        key="option-0",
    )


def _seed_terminal_route(
    option: MissionOption | None, reward_specs: list[tuple[str, dict]]
) -> MissionOptionRoute | None:
    """Look up (or invent) the shared null-``outcome_tier`` terminal route + reward line(s).

    ``reward_specs`` is a list of ``(sink, defaults)`` pairs — ``(route, sink)``
    is a narrow-enough lookup for these single-route graphs (contrast
    ``game_content/missions.py``'s tiered-CHECK-option sibling, which needs a
    richer per-tier lookup). Returns ``None`` when ``option`` is ``None`` or
    the route itself isn't authored/sampled. Content-repo-owned (#2698).
    """
    from world.missions.models import MissionOptionRoute, MissionOptionRouteReward  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    if option is None:
        return None
    route = authored_or_sample(
        MissionOptionRoute,
        {"target_node": None, "is_random_set": False, "consequence": None},
        option=option,
        outcome_tier=None,
    )
    if route is None:
        return None
    for sink, defaults in reward_specs:
        # `kind` belongs in the LOOKUP, not `defaults` — it is part of what
        # identifies a reward line, and it has no model-level default, so
        # leaving it out silently stores "" and `_route_line` then raises
        # MissionRewardRoutingError because ("", MONEY) matches no routing
        # branch. Mirrors game_content/missions.py's sibling call.
        spec = dict(defaults)
        kind = spec.pop("kind", DeedRewardKind.IMMEDIATE)
        authored_or_sample(MissionOptionRouteReward, spec, route=route, kind=kind, sink=sink)
    return route


def _seed_t1(room: ObjectDB) -> MissionTemplate | None:
    """T1 "Arrival" — ROOM_TRIGGER, no predecessor, OPEN visibility."""
    from world.missions.factories import MissionGiverFactory  # noqa: PLC0415

    template = _seed_template(
        _T1_NAME,
        summary=(
            "The city swallows you whole the moment you step through its gates — "
            "noise, smoke, and a thousand strangers who were here before you."
        ),
        risk_tier=1,
        visibility=MissionVisibility.OPEN,
    )
    giver = MissionGiverFactory(
        name=_ROOM_TRIGGER_GIVER_NAME,
        giver_kind=GiverKind.ROOM_TRIGGER,
        target=room,
    )
    if template is not None:
        giver.templates.add(template)

    option = _seed_entry_option(
        template,
        option_kind=OptionKind.BRANCH,
        authored_ic_framing="Take stock of where you've landed.",
    )
    _seed_terminal_route(
        option,
        [(DeedRewardSink.MONEY, {"amount": 25, "contract_holder_only": True})],
    )
    return template


def _seed_t2(room: ObjectDB, gate_template: MissionTemplate | None) -> MissionTemplate | None:
    """T2 "What the Walls Remember" — ENVIRONMENTAL_DETAIL, gated on T1."""
    if gate_template is None:
        return None
    from world.missions.factories import MissionGiverFactory  # noqa: PLC0415

    template = _seed_template(
        _T2_NAME,
        summary=(
            "A scorch mark blackens the plaster here, old enough to have been "
            "painted over twice and stubborn enough to keep bleeding through."
        ),
        risk_tier=1,
        availability_rule=_has_completed(gate_template.pk),
    )
    detail_obj = _ensure_detail_object(room)
    giver = MissionGiverFactory(
        name=_DETAIL_GIVER_NAME,
        giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
        target=detail_obj,
    )
    if template is not None:
        giver.templates.add(template)

    option = _seed_entry_option(
        template,
        option_kind=OptionKind.BRANCH,
        authored_ic_framing="Press a hand to the old burn and listen.",
    )
    _seed_terminal_route(
        option,
        [(DeedRewardSink.MONEY, {"amount": 25, "contract_holder_only": True})],
    )
    return template


def _ensure_tutor_role() -> NPCRole | None:
    """Look up (or, under SEED_SAMPLE_CONTENT, invent) the tutor NPCRole (#1035).

    Mirrors ``ensure_builders_guild_clerk_role`` (``npc_services/seeds.py``)
    — the established (role, label)-keyed idempotent offer pattern.
    ``NPCRole`` is content-repo-owned (#2698) — looked up rather than
    invented unless ``SEED_SAMPLE_CONTENT`` is on. Returns ``None`` when it
    isn't authored/sampled; the caller skips every offer/Functionary step
    that depends on it.
    """
    from world.npc_services.models import NPCRole  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    return authored_or_sample(
        NPCRole,
        {
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
        name=_TUTOR_ROLE_NAME,
    )


def _ensure_tutor_functionary(role: NPCRole, room: ObjectDB) -> None:
    """Place the tutor role in the canonical starting room as a Functionary."""
    from world.areas.services import get_room_profile  # noqa: PLC0415
    from world.npc_services.models import Functionary  # noqa: PLC0415

    room_profile = get_room_profile(room)
    Functionary.objects.get_or_create(role=role, room=room_profile, defaults={"is_active": True})


def _ensure_offer(
    role: NPCRole,
    label: str,
    mission_template: MissionTemplate | None,
    *,
    draw_priority: int = 1,
    role_cooldown_duration: timedelta = timedelta(0),
) -> NPCServiceOffer | None:
    """Idempotent (role, label)-keyed MISSION offer + its MissionOfferDetails row.

    MENU draw_mode — the tutor's offers are deterministic (always shown when
    eligible), not a randomized POOL draw; ``draw_priority`` is set anyway per
    the spec (#1035) for authoring-intent consistency even though POOL is the
    field's primary consumer.

    ``role_cooldown_duration`` defaults to zero: this is a curated, single-path
    tutorial chain — each step's ``availability_rule`` already gates on the
    previous step's completion, and the per-(persona, role) "one mission
    in-flight" check (#686) already prevents double-dipping the same offer.
    The generic anti-spam ``NPCRoleCooldown`` (default 24h, shared per-role
    across ALL of this role's offers) would otherwise block T5/T6/T7 for a
    full day after accepting T3, breaking same-session tutorial progression
    (review finding on #1035 Task 6).

    ``NPCServiceOffer``/``MissionOfferDetails`` are NOT content models (#2698)
    and would seed unconditionally, but ``MissionOfferDetails.mission_template``
    is a required FK — returns ``None`` without creating anything when
    ``mission_template`` is ``None`` (its own template wasn't authored/sampled).
    """
    if mission_template is None:
        return None
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
            role_cooldown_duration=role_cooldown_duration,
        )
    return offer


def _seed_consent_primer(gate_template: MissionTemplate | None) -> MissionTemplate | None:
    """ "Terms of Engagement" — the antagonism-consent onboarding beat (#2170 item 3).

    A tutor-offered side-step gated on T1 (parallel to the T2..T7 spine — it re-gates
    nothing). Walks the new player to the consent tree so the Friends+whitelist default
    is a *chosen, understood* starting point, not a silent one: the summary frames it IC,
    the epilogue points at the real surfaces (web Settings → Privacy; telnet ``consent`` /
    ``consent modes``, which render the per-mode pros/cons from CONSENT_MODE_GUIDANCE).

    All prose here is PLACEHOLDER (agent-drafted — Apostate to rewrite, #2170).
    """
    if gate_template is None:
        return None
    template = _seed_template(
        _TC_NAME,
        summary=(
            'The Warden looks you over like a quartermaster sizing a recruit. "This city will '
            "test you — with knives, with lies, with light fingers. Before it does, decide who "
            'is allowed to try. Nobody moves against you here without your leave."'
        ),
        epilogue=(
            "Your boundaries are yours to set, and to change. Open Settings → Privacy on the "
            "web (or type 'consent' in the classic client) to review who may target you with "
            "hostile play: set the whole Antagonism group at once, or tune a single category. "
            "'consent modes' explains the trade-offs of each setting — the default lets only "
            "your OOC friends try anything against you until you say otherwise."
        ),
        risk_tier=1,
        availability_rule=_has_completed(gate_template.pk),
    )
    option = _seed_entry_option(
        template,
        option_kind=OptionKind.BRANCH,
        authored_ic_framing="Weigh who you'd let raise a hand against you, and set your terms.",
    )
    _seed_terminal_route(
        option,
        [(DeedRewardSink.MONEY, {"amount": 25, "contract_holder_only": True})],
    )
    return template


def _seed_t3(gate_template: MissionTemplate | None) -> MissionTemplate | None:
    """T3 "First Spark" — NPC offer, EXTERNAL_ACT/TECHNIQUE_CAST (transient)."""
    if gate_template is None:
        return None
    template = _seed_template(
        _T3_NAME,
        summary=(
            'The Warden presses a cold coal into your palm. "Wake it," they say. '
            '"Show me you can call something out of nothing."'
        ),
        risk_tier=1,
        availability_rule=_has_completed(gate_template.pk),
    )
    # TECHNIQUE_CAST is transient (never fast-forwards, #1035) — placement
    # is free, but it stays on the entry node for consistency with the
    # durable-act templates that follow.
    option = _seed_entry_option(
        template,
        option_kind=OptionKind.EXTERNAL_ACT,
        required_act=ExternalAct.TECHNIQUE_CAST,
        authored_ic_framing="Cast a technique, however small.",
    )
    _seed_terminal_route(
        option,
        [(DeedRewardSink.MONEY, {"amount": 25, "contract_holder_only": True})],
    )
    return template


def _seed_t4(
    tutor_role: NPCRole | None, gate_template: MissionTemplate | None
) -> tuple[MissionTemplate | None, MissionOptionRoute | None]:
    """T4 "A Simple Job" — BOARD, reusing seed_missions_dev's board giver.

    Returns the template AND its terminal route so the caller can attach the
    FOLLOW_ON_SUMMONS reward line once T5's offer exists (a real ordering
    dependency — see module docstring). Takes no ``room`` argument — the
    board (and the room it sits in) come from ``seed_missions_dev()`` itself.
    This is the one demo mission the module docstring calls out explicitly:
    genuinely-unauthored placeholder content, exactly what
    ``SEED_SAMPLE_CONTENT`` exists for.

    ``tutor_role`` may be ``None`` (the "Threshold Warden" role isn't
    authored/sampled) — ``report_to_role`` is a nullable FK, so the template
    still seeds, just without a report-to role wired.
    """
    if gate_template is None:
        return None, None
    from world.seeds.game_content.missions import seed_missions_dev  # noqa: PLC0415

    template = _seed_template(
        _T4_NAME,
        summary=(
            "A notice, pinned crooked among a dozen others: coin for anyone "
            "willing to do a plain, unglamorous job and report back."
        ),
        risk_tier=2,
        availability_rule=_has_completed(gate_template.pk),
        report_to_role=tutor_role,
    )
    # Self-contained (does not assume the "missions" cluster already ran) —
    # idempotent, so this both creates-on-first-run and reuses thereafter.
    # The board and its room are shared with the starter-mission board
    # (#2121); T4 is added to the SAME giver, not a new one.
    board_giver = seed_missions_dev().giver
    if template is not None:
        board_giver.templates.add(template)

    option = _seed_entry_option(
        template,
        option_kind=OptionKind.BRANCH,
        authored_ic_framing="Take the job and see it through.",
    )
    route = _seed_terminal_route(
        option,
        [(DeedRewardSink.MONEY, {"amount": 75, "contract_holder_only": True})],
    )
    return template, route


def _ensure_t4_followon_reward(
    route: MissionOptionRoute | None, t5_offer: NPCServiceOffer | None
) -> None:
    """Attach the T4→T5 FOLLOW_ON_SUMMONS reward line once T5's offer exists.

    No-ops when either side is missing — T4's terminal route or T5's offer
    didn't seed (its own template wasn't authored/sampled, #2698).
    """
    if route is None or t5_offer is None:
        return
    from world.missions.models import MissionOptionRouteReward  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    authored_or_sample(
        MissionOptionRouteReward,
        {
            "amount": None,
            "followon_offer": t5_offer,
            "followon_message": (
                "The Warden sends word: there is a thread that wants weaving, "
                "and they think you're ready to try."
            ),
            "followon_expiry_hours": None,
            "contract_holder_only": True,
        },
        route=route,
        kind=DeedRewardKind.IMMEDIATE,
        sink=DeedRewardSink.FOLLOW_ON_SUMMONS,
    )


def _seed_t5(gate_template: MissionTemplate | None) -> MissionTemplate | None:
    """T5 "The Loom" — NPC offer, EXTERNAL_ACT/THREAD_WOVEN (durable)."""
    if gate_template is None:
        return None
    template = _seed_template(
        _T5_NAME,
        summary=(
            "The Warden shows you the loom that isn't wood or wire — the one "
            "strung between people who choose to be bound to each other."
        ),
        risk_tier=2,
        availability_rule=_has_completed(gate_template.pk),
    )
    # Durable act (#1035 Ruling 1): authored on the ENTRY node so
    # fast_forward_external_acts (enter_node) can resolve it immediately
    # for a character who already wove a thread before accepting.
    option = _seed_entry_option(
        template,
        option_kind=OptionKind.EXTERNAL_ACT,
        required_act=ExternalAct.THREAD_WOVEN,
        authored_ic_framing="Weave a thread with someone who matters.",
    )
    _seed_terminal_route(
        option,
        [(DeedRewardSink.MONEY, {"amount": 50, "contract_holder_only": True})],
    )
    return template


def _seed_t6(gate_template: MissionTemplate | None) -> MissionTemplate | None:
    """T6 "Sworn Together" — NPC offer, EXTERNAL_ACT/COVENANT_SWORN (durable)."""
    if gate_template is None:
        return None
    template = _seed_template(
        _T6_NAME,
        summary=(
            '"None of us stand for long alone," the Warden says. "Swear '
            'yourself to a covenant, and see what holds you up."'
        ),
        risk_tier=2,
        availability_rule=_has_completed(gate_template.pk),
    )
    # Durable act (#1035 Ruling 1): entry node, same rationale as T5.
    option = _seed_entry_option(
        template,
        option_kind=OptionKind.EXTERNAL_ACT,
        required_act=ExternalAct.COVENANT_SWORN,
        authored_ic_framing="Swear yourself to a covenant.",
    )
    _seed_terminal_route(
        option,
        [(DeedRewardSink.MONEY, {"amount": 50, "contract_holder_only": True})],
    )
    return template


def _seed_t7(gate_template: MissionTemplate | None) -> MissionTemplate | None:
    """T7 "The Long Dark" — NPC offer, risk_tier=4, first legend-risk mission."""
    if gate_template is None:
        return None
    template = _seed_template(
        _T7_NAME,
        summary=(
            "The Warden's voice drops. \"This one isn't practice. Whatever "
            "waits past the old wall doesn't care that you're new.\""
        ),
        risk_tier=4,
        availability_rule=_has_completed(gate_template.pk),
    )
    option = _seed_entry_option(
        template,
        option_kind=OptionKind.BRANCH,
        authored_ic_framing="Go into the long dark.",
    )
    # #2051 legend guard: LEGEND_POINTS requires risk_tier >= LEGEND_RISK_FLOOR_TIER
    # (4) — satisfied here since this template's risk_tier is 4. LEGEND_POINTS
    # is a queued sink (rewards.py's _QUEUE_SINKS) — it ONLY routes under
    # kind=POST_CRON; the IMMEDIATE default has no dispatch target for this
    # sink and raises MissionRewardRoutingError at report time (a gap only the
    # Task 6 journey E2E — the first thing to actually report T7 — surfaced;
    # test_tutorial_seed.py only checked the template row existed).
    _seed_terminal_route(
        option,
        [
            (DeedRewardSink.MONEY, {"amount": 150, "contract_holder_only": True}),
            (
                DeedRewardSink.LEGEND_POINTS,
                {
                    "kind": DeedRewardKind.POST_CRON,
                    "amount": 10,
                    "contract_holder_only": True,
                },
            ),
        ],
    )
    return template


def seed_tutorial_dev() -> TutorialSeedResult:
    """Seed the seven-template new-player tutorial chain T1-T7 (#1035).

    Registered as the "tutorial" cluster in ``world.seeds.clusters`` — reachable
    from the Big Button, after "missions" (the shared board giver + room),
    "character_creation" (the canonical starting room), and self-contained
    for the tutor NPCRole (no other cluster's content is required to create
    it). Idempotent throughout; never overwrites a staff edit.

    Every ``MissionTemplate`` in this chain is content-repo-owned (#2698) —
    the chain is linear (each step's ``availability_rule`` gates on the
    previous step's pk), so a gap at step N leaves every subsequent step
    ungated and ``None`` (see the module docstring). ``NPCRole``/
    ``NPCServiceOffer`` seed unconditionally regardless.

    Returns:
        TutorialSeedResult with whichever templates in the chain are
        authored/sampled (T1 first, 0-7), the tutor NPCRole, and the consent
        primer template (``None`` if T1 itself is missing).
    """
    from world.seeds.character_creation import ensure_canonical_fallback_room  # noqa: PLC0415

    room = ensure_canonical_fallback_room()

    t1 = _seed_t1(room)
    t2 = _seed_t2(room, t1)

    # "Threshold Warden" is content-repo-owned (#2698) — every offer/
    # Functionary step below depends on it and is skipped when it isn't
    # authored/sampled (see TutorialSeedResult's docstring).
    tutor_role = _ensure_tutor_role()
    if tutor_role is not None:
        _ensure_tutor_functionary(tutor_role, room)

    consent_primer = _seed_consent_primer(t1)
    if tutor_role is not None:
        _ensure_offer(tutor_role, "A word about boundaries", consent_primer)

    t3 = _seed_t3(t2)
    if tutor_role is not None:
        _ensure_offer(tutor_role, "Kindle a first spark", t3)

    t4, t4_terminal_route = _seed_t4(tutor_role, t3)

    t5 = _seed_t5(t4)
    t5_offer = (
        _ensure_offer(tutor_role, "Learn the loom's thread-work", t5)
        if tutor_role is not None
        else None
    )

    _ensure_t4_followon_reward(t4_terminal_route, t5_offer)

    t6 = _seed_t6(t5)
    if tutor_role is not None:
        _ensure_offer(tutor_role, "Swear the first oath", t6)

    t7 = _seed_t7(t6)
    if tutor_role is not None:
        _ensure_offer(tutor_role, "Answer the long dark's call", t7)

    return TutorialSeedResult(
        templates=[t for t in (t1, t2, t3, t4, t5, t6, t7) if t is not None],
        tutor_role=tutor_role,
        consent_template=consent_primer,
    )
