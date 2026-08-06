"""Criminal underworld demo seed (#2862) — PLACEHOLDER content.

Seeds the first walkable turf-war stage: the ``gang`` OrganizationType (named
in the model docstring since the beginning, never seeded), one NPC gang, one
contested crime neighborhood with a turf position and a CRIME_KICKUP stream,
and the Retaliation crisis type the turf service opens against pushers.
Real placement, prose, and the mission chain ride the content pass.
"""

from __future__ import annotations

GANG_ORG_TYPE_NAME = "gang"
NPC_GANG_NAME = "The Ashfingers PLACEHOLDER"
CRIME_NEIGHBORHOOD_NAME = "Dockside Warrens PLACEHOLDER"
NPC_GANG_STARTING_GRIP = 60
RETALIATION_CRISIS_TYPE_NAME = "Gang Retaliation"
KICKUP_STREAM_NAME = "Warrens kick-up PLACEHOLDER"
KICKUP_GROSS = 2000  # coppers/cycle, PLACEHOLDER


def seed_underworld_demo() -> None:
    """Seed the PLACEHOLDER turf-war stage + criminal mission chain (idempotent)."""
    _seed_gang_and_turf()
    _seed_retaliation_crisis_type()
    _seed_underworld_missions()


def _seed_gang_and_turf() -> None:
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415
    from world.societies.models import (  # noqa: PLC0415
        NeighborhoodTurf,
        Organization,
        OrganizationType,
    )

    org_type, _created = OrganizationType.objects.get_or_create(name=GANG_ORG_TYPE_NAME)
    gang, _created = Organization.objects.get_or_create(
        name=NPC_GANG_NAME,
        defaults={
            "org_type": org_type,
            "description": (
                "PLACEHOLDER: the crew that runs the Warrens — burn-scarred "
                "knuckles and long memories. NPC-run; push them and see."
            ),
        },
    )
    area, _created = Area.objects.get_or_create(
        name=CRIME_NEIGHBORHOOD_NAME,
        defaults={"level": AreaLevel.NEIGHBORHOOD},
    )
    turf, turf_created = NeighborhoodTurf.objects.get_or_create(
        area=area,
        defaults={"controlling_org": gang, "grip": NPC_GANG_STARTING_GRIP},
    )
    if turf_created:
        from world.societies.turf_services import _sync_crime_modifier  # noqa: PLC0415

        _sync_crime_modifier(turf)
    OrgIncomeStream.objects.get_or_create(
        name=KICKUP_STREAM_NAME,
        defaults={
            "organization": gang,
            "kind": IncomeStreamKind.CRIME_KICKUP,
            "gross_amount": KICKUP_GROSS,
            "area": area,
        },
    )


def _seed_retaliation_crisis_type() -> None:
    """The NPC gang's answer to a turf push — PAY tribute or WAIT and bleed.

    The MISSION option ("Hold the Corner") is bound by the missions content
    seed once the template exists — a typeless option row would be dead
    content, so only PAY/WAIT seed here.
    """
    from world.societies.houses.constants import (  # noqa: PLC0415
        CrisisAudience,
        CrisisResolutionKind,
        CrisisValence,
        DomainCrisisSeverity,
    )
    from world.societies.houses.models import (  # noqa: PLC0415
        DomainCrisisType,
        DomainCrisisTypeOption,
    )

    crisis_type, _created = DomainCrisisType.objects.get_or_create(
        name=RETALIATION_CRISIS_TYPE_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: the crew you pushed pushes back — collectors "
                "leaned on, corners watched, knives shown."
            ),
            "default_severity": DomainCrisisSeverity.TROUBLE,
            "automated": False,
            "valence": CrisisValence.THREAT,
            "audience": CrisisAudience.CRIMINAL_ORG,
        },
    )
    DomainCrisisTypeOption.objects.get_or_create(
        crisis_type=crisis_type,
        kind=CrisisResolutionKind.PAY,
        defaults={"cost_coppers": 5000},
    )
    DomainCrisisTypeOption.objects.get_or_create(
        crisis_type=crisis_type,
        kind=CrisisResolutionKind.WAIT,
        defaults={"self_resolve_pct": 30, "worsen_pct": 30},
    )


# ---------------------------------------------------------------------------
# Criminal mission chain + covert board + standing route (#2862)
# ---------------------------------------------------------------------------

BACK_ROOM_BOARD_NAME = "The Back Room Wall PLACEHOLDER"
BACK_ROOM_OBJECT_KEY = "a wall of chalked marks PLACEHOLDER"
ROUTE_TASK_NAME = "Run the Quiet Docks PLACEHOLDER"
_GATHER_EVIDENCE_CHECK = "Gather Evidence"
_TURF_WAR_CHECK = "Turf War"

#: (name, summary, risk_tier, category, check name, money, item reward,
#:  crime-watch slug on failure, feeds the turf project)
_MISSION_ROWS = (
    (
        "The First Run",
        "PLACEHOLDER: meet the boat after dark; walk the crate through the "
        "docks without meeting anyone's eyes.",
        1,
        "Smuggling",
        _GATHER_EVIDENCE_CHECK,
        80,
        "Duskpetal Resin",
        "smuggling",
        False,
    ),
    (
        "Cutting the Product",
        "PLACEHOLDER: the crate becomes the product — if your hands are "
        "steady and the Workshop's door stays shut.",
        1,
        "Crime",
        _GATHER_EVIDENCE_CHECK,
        20,
        "Dream Dust",
        "contraband",
        False,
    ),
    (
        "Corner Trade",
        "PLACEHOLDER: move the product through the fence while the corner is thick with buyers.",
        2,
        "Crime",
        _GATHER_EVIDENCE_CHECK,
        150,
        None,
        "contraband",
        False,
    ),
    (
        "Send a Message",
        "PLACEHOLDER: the Ashfingers' collector works your street like he owns it. Correct him.",
        2,
        _TURF_WAR_CHECK,
        "Intimidation",
        60,
        None,
        "common-battery",
        True,
    ),
    (
        "Burn Their Stash",
        "PLACEHOLDER: what they cannot sell they cannot hold the corner with. Bring a light.",
        3,
        _TURF_WAR_CHECK,
        _GATHER_EVIDENCE_CHECK,
        100,
        None,
        "arson",
        True,
    ),
    (
        "The Quiet Docks",
        "PLACEHOLDER: the harbormaster's ledger has a gap the width of one "
        "pier. Make it yours, permanently.",
        3,
        "Smuggling",
        _GATHER_EVIDENCE_CHECK,
        400,
        None,
        "smuggling",
        False,
    ),
    (
        "Hold the Corner",
        "PLACEHOLDER: they are coming to take the corner back tonight. Be "
        "standing on it when they arrive.",
        2,
        _TURF_WAR_CHECK,
        "Intimidation",
        80,
        None,
        None,
        True,
    ),
)


def _seed_underworld_missions() -> None:
    """The criminal chain: 7 templates, covert board, crisis binding, route task."""
    from world.missions.constants import GiverKind  # noqa: PLC0415
    from world.missions.factories import MissionGiverFactory  # noqa: PLC0415
    from world.seeds.character_creation import (  # noqa: PLC0415
        ensure_canonical_fallback_room,
    )

    templates = {}
    for row in _MISSION_ROWS:
        template = _seed_criminal_mission(*row)
        if template is not None:
            templates[row[0]] = template
    room = ensure_canonical_fallback_room()
    board_obj = _ensure_board_object(room)
    giver = MissionGiverFactory(
        name=BACK_ROOM_BOARD_NAME,
        giver_kind=GiverKind.BOARD,
        target=board_obj,
    )
    if templates:
        giver.templates.add(*templates.values())
    hold = templates.get("Hold the Corner")
    if hold is not None:
        _bind_retaliation_mission(hold)
    quiet_docks = templates.get("The Quiet Docks")
    if quiet_docks is not None:
        _seed_route_task(quiet_docks)


def _ensure_board_object(room):
    from evennia.objects.models import ObjectDB  # noqa: PLC0415
    from evennia.utils import create as evennia_create  # noqa: PLC0415

    existing = ObjectDB.objects.filter(db_key=BACK_ROOM_OBJECT_KEY).first()
    if existing is not None:
        return existing
    return evennia_create.create_object(
        typeclass="typeclasses.objects.Object",
        key=BACK_ROOM_OBJECT_KEY,
        location=room,
        home=room,
    )


def _seed_criminal_mission(  # noqa: PLR0913
    name: str,
    summary: str,
    risk_tier: int,
    category_name: str,
    check_name: str,
    money: int,
    item_name: str | None,
    crime_slug: str | None,
    feeds_project: bool,
):
    """One RESTRICTED single-node criminal mission (the #2121 graph shape).

    RESTRICTED + an org-membership availability rule (mission discovery is
    taught, never listed): PLACEHOLDER-gated on the demo gang until player
    crews author their own boards. Success tiers carry MONEY (+ ITEM, +
    PROJECT when the mission feeds a turf push); failure tiers carry the
    CRIME_WATCH heat line for the named crime.
    """
    from datetime import timedelta  # noqa: PLC0415

    from world.checks.models import CheckType  # noqa: PLC0415
    from world.items.models import ItemTemplate  # noqa: PLC0415
    from world.missions.constants import (  # noqa: PLC0415
        ArcScope,
        ConflictMode,
        MissionVisibility,
        OptionKind,
        OptionSource,
        RewardGroupRule,
    )
    from world.missions.models import (  # noqa: PLC0415
        MissionCategory,
        MissionNode,
        MissionOption,
        MissionOptionRoute,
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
            "level_band_min": 1,
            "level_band_max": 15,
            "base_weight": 1,
            "created_in_era": None,
            "arc_scope": ArcScope.GLOBAL,
            "percent_replace": 0,
            "cooldown": timedelta(0),
            "reward_group_rule": RewardGroupRule.ALL_EQUAL,
            "is_active": True,
            "visibility": MissionVisibility.RESTRICTED,
            "availability_rule": {
                "leaf": "is_member_of_org",
                "params": {"org": NPC_GANG_NAME},
            },
        },
        name=name,
    )
    if template is None:
        return None
    category, _created = MissionCategory.objects.get_or_create(name=category_name)
    template.categories.add(category)
    check_type = CheckType.objects.filter(name=check_name).first()
    if check_type is None:
        return template
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
    # Reward ItemTemplates are lore-authored content resolved by name at seed time
    # (#3006) — this is a soft lookup (`.first()`, not `authored_or_sample`), so an
    # unauthored name silently drops the reward instead of failing loud. "The First
    # Run"'s "Duskpetal Resin" is the live example: the template is authored
    # lore-side per #3006, but until that lands (or on a content universe that
    # never authors it) this mission seeds with no item reward.
    item_template = ItemTemplate.objects.filter(name=item_name).first() if item_name else None
    tier_money = {
        "Critical Failure": 0,
        "Failure": 0,
        "Partial Success": max(1, money // 4) if money else 0,
        "Success": money,
        "Critical Success": money * 2,
    }
    for outcome_name, amount in tier_money.items():
        outcome = CheckOutcome.objects.get(name=outcome_name)
        route = authored_or_sample(
            MissionOptionRoute,
            {"target_node": None, "is_random_set": False, "consequence": None},
            option=option,
            outcome_tier=outcome,
        )
        if route is None:
            continue
        _attach_route_rewards(
            route,
            outcome_name=outcome_name,
            amount=amount,
            item_template=item_template,
            crime_slug=crime_slug,
            feeds_project=feeds_project,
        )
    return template


def _attach_route_rewards(  # noqa: PLR0913
    route,
    *,
    outcome_name: str,
    amount: int,
    item_template,
    crime_slug: str | None,
    feeds_project: bool,
):
    """Reward lines for one route: MONEY/ITEM/PROJECT on success, heat on failure."""
    from world.missions.constants import DeedRewardKind, DeedRewardSink  # noqa: PLC0415
    from world.missions.models import MissionOptionRouteReward  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    success_tiers = {"Partial Success", "Success", "Critical Success"}
    if amount:
        authored_or_sample(
            MissionOptionRouteReward,
            {"amount": amount, "contract_holder_only": False},
            route=route,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
        )
    if outcome_name in success_tiers:
        if item_template is not None:
            authored_or_sample(
                MissionOptionRouteReward,
                {"item_template": item_template, "contract_holder_only": False},
                route=route,
                kind=DeedRewardKind.IMMEDIATE,
                sink=DeedRewardSink.ITEM,
            )
        if feeds_project:
            authored_or_sample(
                MissionOptionRouteReward,
                {"amount": 10, "contract_holder_only": False},
                route=route,
                kind=DeedRewardKind.IMMEDIATE,
                sink=DeedRewardSink.PROJECT,
            )
    elif crime_slug is not None:
        authored_or_sample(
            MissionOptionRouteReward,
            {"ref": crime_slug, "contract_holder_only": False},
            route=route,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.CRIME_WATCH,
        )


def _bind_retaliation_mission(template) -> None:
    """Give the Retaliation crisis its MISSION option — Hold the Corner."""
    from world.societies.houses.constants import CrisisResolutionKind  # noqa: PLC0415
    from world.societies.houses.models import (  # noqa: PLC0415
        DomainCrisisType,
        DomainCrisisTypeOption,
    )

    crisis_type = DomainCrisisType.objects.filter(name=RETALIATION_CRISIS_TYPE_NAME).first()
    if crisis_type is None:
        return
    DomainCrisisTypeOption.objects.get_or_create(
        crisis_type=crisis_type,
        kind=CrisisResolutionKind.MISSION,
        defaults={"mission_template": template},
    )


def _seed_route_task(template) -> None:
    """The standing smuggling route: one payout table, two engines (#2862).

    A weekly CRIME task the org can hand to an NPC asset (offscreen check,
    incrimination residue, asset risk) — or a PC picks up the linked mission
    and runs the route in person. The tasking system's built dual-execution
    bridge, exercised exactly as designed.
    """
    from datetime import timedelta  # noqa: PLC0415

    from world.checks.models import CheckType  # noqa: PLC0415
    from world.tasking.models import (  # noqa: PLC0415
        TaskCategory,
        TaskOutcomeRoute,
        TaskTargetKind,
        TaskTemplate,
    )
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=_GATHER_EVIDENCE_CHECK).first()
    if check_type is None:
        return
    task, _created = TaskTemplate.objects.get_or_create(
        name=ROUTE_TASK_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: the pier gap stays open only if someone keeps "
                "walking crates through it."
            ),
            "category": TaskCategory.CRIME,
            "check_type": check_type,
            "check_difficulty": 20,
            "duration": timedelta(days=7),
            "target_kind": TaskTargetKind.NONE,
            "mission_template": template,
        },
    )
    best = CheckOutcome.objects.filter(name="Success").first()
    worst = CheckOutcome.objects.filter(name="Failure").first()
    if best is not None:
        TaskOutcomeRoute.objects.get_or_create(
            template=task,
            outcome_tier=best,
            defaults={
                "money_reward": 300,
                "report_template": (
                    "PLACEHOLDER {agent} walks the route clean — the crates "
                    "moved and nobody watched."
                ),
            },
        )
    if worst is not None:
        TaskOutcomeRoute.objects.get_or_create(
            template=task,
            outcome_tier=worst,
            defaults={
                "incriminate_level": 2,
                "report_template": ("PLACEHOLDER {agent} comes back light — the route drew eyes."),
            },
        )
