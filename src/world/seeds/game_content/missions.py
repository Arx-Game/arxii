"""Mission board content bootstrap (#2121).

Zero ``MissionGiver``/``MissionTemplate`` rows existed anywhere pre-#2121 — the
missions app's own factories (``world/missions/factories.py``) were BUILT, NOT
WIRED (callers were test-only) — so a fresh world's ``mission opportunities``
said "Nothing pulls at you right now" forever, even though the entire
telnet-native mission loop (``mission opportunities/take/beat/resolve/support/
report/tale``, #2044-#2051) was fully wired. Seeds a minimal starter board +
template set (never hand-authored ``get_or_create`` rows for the graph, which
would duplicate the factories' ``clean()``/``is_entry``-uniqueness validation
for no benefit).

Shape (Decision 1, #2121): one BOARD-kind ``MissionGiver`` whose ``target`` is
an examinable notice-board Object physically located in the canonical starting
room (``ensure_canonical_fallback_room``, #2121) — so ``mission opportunities``
finds something at spawn (``_here_postings``, ``services/opportunities.py``);
three ``OPEN``-visibility ``MissionTemplate`` rows spanning distinct
risk_tier/level_band, each a single-``is_entry``-node graph with one plain
CHECK-sourced ``MissionOption`` (no ``ChallengeTemplate`` attach) covering
every canonical ``CheckOutcome`` tier and resolving to a reward line.

``missions.MissionTemplate``/``MissionNode``/``MissionOption``/
``MissionOptionRoute``/``MissionOptionRouteReward`` are ALL content-repo-owned
(#2698) — these three starter templates (and their node/option/route/reward
graphs) are genuinely-unauthored demo content, so every row below is looked up
rather than invented unless ``SEED_SAMPLE_CONTENT`` is on. A missing template
skips its own graph and is never attached to the board giver; ``MissionGiver``
itself is NOT a content model and still seeds unconditionally (an empty board
under a real content repo is a content-authoring gap, not a seeder bug).

Each starter template's ``report_to_role`` is set to the tutorial chain's
"Threshold Warden" ``NPCRole`` (#3040): a BOARD-taken run (``take_from_board``)
carries no ``source_offer``, so ``report_to_role_for`` would otherwise return
``None`` and ``_finish_terminal`` jumps the run straight to COMPLETE, orphaning
the authored MONEY reward line — the same gap T4 "A Simple Job"
(``game_content/tutorial.py``) already fixed for its own board template. The
Warden is reused rather than a board-specific role invented: both the board
Object and the Warden Functionary sit in the SAME canonical starting room
(``ensure_canonical_fallback_room``), so it's always the NPC actually
co-located to report a board job's outcome to.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from world.missions.constants import (
    ArcScope,
    ConflictMode,
    DeedRewardKind,
    DeedRewardSink,
    GiverKind,
    MissionVisibility,
    OptionKind,
    OptionSource,
    RewardGroupRule,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.missions.models import MissionGiver, MissionTemplate
    from world.npc_services.models import NPCRole

_BOARD_GIVER_NAME = "Arx City Notice Board"
_BOARD_OBJECT_KEY = "a weathered notice board"
_BOARD_OBJECT_TYPECLASS = "typeclasses.objects.Object"

_CHECK_CATEGORY_NAME = "Exploration"
_CHECK_TYPE_NAME = "Fieldwork"
#: Reuses the "wits" STAT trait seeded by the character_creation cluster
#: (DEFAULT_STAT_NAMES, world/seeds/character_creation.py) — the missions
#: cluster runs after character_creation (Decision 1, #2121).
_CHECK_STAT_NAME = "wits"

#: (name, summary, risk_tier, level_band_min, level_band_max, base_reward).
#: Distinct risk_tier/level_band per row so the draw isn't degenerate, but all
#: kept low (max level_band 15, risk_tier <= 3 of 5) — an OPEN template's
#: level_band is NOT filtered by opportunities_for_character/postings_for_giver
#: today (verified against code, #2121 "Verified leak analysis"), so a level-1
#: character can see every row here; none offers outsized risk.
_TEMPLATES: tuple[tuple[str, str, int, int, int, int], ...] = (
    (
        "The Lost Ledger",
        "A merchant's steward misplaced a ledger of debts somewhere in the "
        "city — find it before a rival house does.",
        1,
        1,
        5,
        50,
    ),
    (
        "Whispers at the Gate",
        "Something is stirring among the gate guards. Look into it quietly, "
        "before it becomes everyone's problem.",
        2,
        1,
        10,
        100,
    ),
    (
        "The Merchant's Debt",
        "A moneylender wants a debt collected from someone who very much does not want to pay.",
        3,
        3,
        15,
        175,
    ),
)


@dataclass
class MissionsSeedResult:
    """Returned by seed_missions_dev()."""

    giver: MissionGiver
    templates: list[MissionTemplate]


def _ensure_fieldwork_check_type() -> CheckType | None:
    """Look up (or sample) a plain stat-only CheckType for the starter missions.

    Self-contained (does not assume any other check-composing cluster ran
    first) — mirrors the touchstone content seed's "self-contained" rationale
    (world/magic/CLAUDE.md). ``checks.CheckCategory``/``CheckType``/
    ``CheckTypeTrait`` and ``traits.Trait`` are content-repo-owned (#2698) —
    looked up via ``authored_or_sample()`` rather than invented unless
    ``SEED_SAMPLE_CONTENT`` is on. No longer wipes and rewrites the
    composition on each run (#2698 Part 1); ``authored_or_sample`` converges
    instead. Returns ``None`` when the category or the check type itself
    isn't authored.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    category = authored_or_sample(CheckCategory, {}, name=_CHECK_CATEGORY_NAME)
    if category is None:
        return None
    check_type = authored_or_sample(
        CheckType, {"is_active": True}, name=_CHECK_TYPE_NAME, category=category
    )
    if check_type is None:
        return None
    stat_trait = authored_or_sample(
        Trait,
        {"trait_type": TraitType.STAT, "category": TraitCategory.MENTAL, "is_public": True},
        name=_CHECK_STAT_NAME,
    )
    if stat_trait is not None:
        authored_or_sample(
            CheckTypeTrait, {"weight": Decimal("1.0")}, check_type=check_type, trait=stat_trait
        )
    return check_type


def _ensure_notice_board_object(room: ObjectDB) -> ObjectDB:
    """Get-or-create the examinable notice-board Object, located IN ``room``.

    A BOARD-kind MissionGiver's ``target`` must be a non-Character/Room/Exit
    Object (``MissionGiver.clean()``) — the board is physically placed in a
    room via its own ``location``, never the room itself. ``ObjectDB.db_key``
    is not unique in Evennia, so lookup uses ``.filter().first()`` (mirrors
    the cascade-room pattern, ``world/seeds/game_content/magic.py``).
    """
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    existing = ObjectDB.objects.filter(
        db_key=_BOARD_OBJECT_KEY, db_typeclass_path=_BOARD_OBJECT_TYPECLASS
    ).first()
    if existing is not None:
        return existing
    return evennia_create.create_object(
        typeclass=_BOARD_OBJECT_TYPECLASS,
        key=_BOARD_OBJECT_KEY,
        location=room,
        home=room,
    )


def _seed_mission_template(  # noqa: PLR0913
    name: str,
    summary: str,
    risk_tier: int,
    level_band_min: int,
    level_band_max: int,
    base_reward: int,
    report_to_role: NPCRole | None,
) -> MissionTemplate | None:
    """Look up (or, under SEED_SAMPLE_CONTENT, invent) one starter MissionTemplate + graph.

    Every row here — the template, its single entry node, one CHECK-sourced
    option, and one route + reward per canonical ``CheckOutcome`` tier — is
    content-repo-owned (#2698); each is looked up via ``authored_or_sample()``
    rather than created unconditionally. Returns ``None`` when the template
    itself isn't authored/sampled; a missing entry node/option skips the rest
    of the graph the same way.

    ``report_to_role`` (#3040): the tutorial chain's "Threshold Warden", or
    ``None`` when it isn't authored/sampled yet — a nullable FK, so the
    template still seeds either way (see the module docstring).
    """
    from world.missions.models import (  # noqa: PLC0415
        MissionNode,
        MissionOption,
        MissionOptionRoute,
        MissionOptionRouteReward,
        MissionTemplate,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    template = authored_or_sample(
        MissionTemplate,
        {
            "summary": summary,
            "epilogue": "",
            "risk_tier": risk_tier,
            "level_band_min": level_band_min,
            "level_band_max": level_band_max,
            "base_weight": 1,
            "created_in_era": None,
            "arc_scope": ArcScope.GLOBAL,
            "percent_replace": 0,
            "cooldown": timedelta(0),
            "reward_group_rule": RewardGroupRule.ALL_EQUAL,
            "report_to_role": report_to_role,
            "is_active": True,
            "visibility": MissionVisibility.OPEN,
        },
        name=name,
    )
    if template is None:
        return None

    check_type = _ensure_fieldwork_check_type()
    entry = authored_or_sample(
        MissionNode,
        {"is_entry": True, "conflict_mode": ConflictMode.GROUP_VOTE},
        template=template,
        key="entry",
    )
    if entry is None:
        return template
    option = authored_or_sample(
        MissionOption,
        {
            "order": 0,
            "option_kind": OptionKind.CHECK,
            "source_kind": OptionSource.AUTHORED,
            "authored_check_type": check_type,
        },
        node=entry,
        key="option-0",
    )
    if option is None:
        return template

    # Cover every canonical CheckOutcome tier (seeded by the "checks" cluster,
    # world/seeds/checks.py) so resolve_option never raises
    # "route-set incompleteness" on a rolled outcome this graph didn't author
    # a route for (route-set completeness is graph-level, not model-enforced —
    # see MissionOptionRoute's DESIGN comment).
    tier_rewards: dict[str, int] = {
        "Critical Failure": 0,
        "Failure": 0,
        "Partial Success": max(1, base_reward // 4),
        "Success": base_reward,
        "Critical Success": base_reward * 2,
    }
    for outcome_name, reward_amount in tier_rewards.items():
        outcome = CheckOutcome.objects.get(name=outcome_name)
        route = authored_or_sample(
            MissionOptionRoute,
            {"target_node": None, "is_random_set": False, "consequence": None},
            option=option,
            outcome_tier=outcome,
        )
        if route is not None and reward_amount:
            authored_or_sample(
                MissionOptionRouteReward,
                {"amount": reward_amount, "contract_holder_only": False},
                route=route,
                kind=DeedRewardKind.IMMEDIATE,
                sink=DeedRewardSink.MONEY,
            )
    return template


def seed_missions_dev() -> MissionsSeedResult:
    """Seed the starter mission board: 1 BOARD giver + up to 3 OPEN templates (#2121).

    Registered as the "missions" cluster in ``world.seeds.clusters`` — reachable
    from the Big Button. Idempotent throughout: re-running on a populated DB
    creates no new rows and never overwrites a staff edit.

    ``MissionGiver`` is NOT a content model and still seeds unconditionally.
    The three starter ``MissionTemplate`` rows are content-repo-owned (#2698,
    see the module docstring) — a template missing under a real content repo
    (sampling off) is simply left off the giver and the returned list.

    Returns:
        MissionsSeedResult with the giver and whichever starter templates are
        authored/sampled (0-3).
    """
    from world.missions.factories import MissionGiverFactory  # noqa: PLC0415
    from world.seeds.character_creation import ensure_canonical_fallback_room  # noqa: PLC0415
    from world.seeds.game_content.tutorial import ensure_tutor_role  # noqa: PLC0415

    room = ensure_canonical_fallback_room()
    board_obj = _ensure_notice_board_object(room)
    giver = MissionGiverFactory(
        name=_BOARD_GIVER_NAME,
        giver_kind=GiverKind.BOARD,
        target=board_obj,
    )
    # Self-contained (does not assume the "tutorial" cluster already ran) —
    # idempotent either direction, exactly like T4's cross-call of THIS
    # function from tutorial.py (see the module docstring, #3040).
    report_to_role = ensure_tutor_role()
    templates = [
        template
        for row in _TEMPLATES
        if (template := _seed_mission_template(*row, report_to_role)) is not None
    ]
    if templates:
        giver.templates.add(*templates)  # idempotent M2M add
    return MissionsSeedResult(giver=giver, templates=templates)
