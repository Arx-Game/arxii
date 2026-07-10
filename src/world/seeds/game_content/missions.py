"""Mission board content bootstrap (#2121).

Zero ``MissionGiver``/``MissionTemplate`` rows existed anywhere pre-#2121 — the
missions app's own factories (``world/missions/factories.py``) were BUILT, NOT
WIRED (callers were test-only) — so a fresh world's ``mission opportunities``
said "Nothing pulls at you right now" forever, even though the entire
telnet-native mission loop (``mission opportunities/take/beat/resolve/support/
report/tale``, #2044-#2051) was fully wired. Seeds a minimal starter board +
template set via the existing factories (never hand-authored ``get_or_create``
rows, which would duplicate the factories' ``clean()``/``is_entry``-uniqueness
validation for no benefit).

Shape (Decision 1, #2121): one BOARD-kind ``MissionGiver`` whose ``target`` is
an examinable notice-board Object physically located in the canonical starting
room (``ensure_canonical_fallback_room``, #2121) — so ``mission opportunities``
finds something at spawn (``_here_postings``, ``services/opportunities.py``);
three ``OPEN``-visibility ``MissionTemplate`` rows spanning distinct
risk_tier/level_band, each a single-``is_entry``-node graph with one plain
CHECK-sourced ``MissionOption`` (no ``ChallengeTemplate`` attach) covering
every canonical ``CheckOutcome`` tier and resolving to a reward line.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from world.missions.constants import GiverKind, MissionVisibility, OptionKind, OptionSource

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.missions.models import MissionGiver, MissionTemplate

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


def _ensure_fieldwork_check_type() -> CheckType:
    """Get-or-create a plain stat-only CheckType for the starter missions.

    Self-contained (does not assume any other check-composing cluster ran
    first) — mirrors the touchstone content seed's "self-contained" rationale
    (world/magic/CLAUDE.md). Authoritative composition: rewrites the trait
    weighting on every run, same as seed_investigation_check_content.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.traits.models import Trait  # noqa: PLC0415

    category, _ = CheckCategory.objects.get_or_create(name=_CHECK_CATEGORY_NAME)
    check_type, _ = CheckType.objects.get_or_create(
        name=_CHECK_TYPE_NAME, category=category, defaults={"is_active": True}
    )
    stat_trait = Trait.objects.get(name=_CHECK_STAT_NAME)
    CheckTypeTrait.objects.filter(check_type=check_type).delete()
    CheckTypeTrait.objects.create(check_type=check_type, trait=stat_trait, weight=Decimal("1.0"))
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
) -> MissionTemplate:
    """Get-or-create one starter MissionTemplate + its single-entry-node graph.

    ``MissionTemplateFactory`` is ``django_get_or_create`` on ``name``, so the
    template row itself is idempotent; the node/option/route graph is guarded
    separately (``template.nodes.exists()``) since ``MissionNodeFactory`` has
    no such guard and would duplicate the entry node on every re-run.
    """
    from world.missions.factories import (  # noqa: PLC0415
        MissionNodeFactory,
        MissionOptionFactory,
        MissionOptionRouteFactory,
        MissionOptionRouteRewardFactory,
        MissionTemplateFactory,
    )
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    template = MissionTemplateFactory(
        name=name,
        summary=summary,
        risk_tier=risk_tier,
        level_band_min=level_band_min,
        level_band_max=level_band_max,
        visibility=MissionVisibility.OPEN,
    )
    if template.nodes.exists():
        return template  # already fully authored — idempotent no-op

    check_type = _ensure_fieldwork_check_type()
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    option = MissionOptionFactory(
        node=entry,
        option_kind=OptionKind.CHECK,
        source_kind=OptionSource.AUTHORED,
        authored_check_type=check_type,
    )
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
        route = MissionOptionRouteFactory(option=option, outcome_tier=outcome, target_node=None)
        if reward_amount:
            MissionOptionRouteRewardFactory(route=route, amount=reward_amount)
    return template


def seed_missions_dev() -> MissionsSeedResult:
    """Seed the starter mission board: 1 BOARD giver + 3 OPEN templates (#2121).

    Registered as the "missions" cluster in ``world.seeds.clusters`` — reachable
    from the Big Button. Idempotent throughout: re-running on a populated DB
    creates no new rows and never overwrites a staff edit.

    Returns:
        MissionsSeedResult with the giver and its 3 templates.
    """
    from world.missions.factories import MissionGiverFactory  # noqa: PLC0415
    from world.seeds.character_creation import ensure_canonical_fallback_room  # noqa: PLC0415

    room = ensure_canonical_fallback_room()
    board_obj = _ensure_notice_board_object(room)
    giver = MissionGiverFactory(
        name=_BOARD_GIVER_NAME,
        giver_kind=GiverKind.BOARD,
        target=board_obj,
    )
    templates = [_seed_mission_template(*row) for row in _TEMPLATES]
    giver.templates.add(*templates)  # idempotent M2M add
    return MissionsSeedResult(giver=giver, templates=templates)
