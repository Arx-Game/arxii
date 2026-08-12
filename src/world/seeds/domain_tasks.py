"""Domain collection sample task (#696) — PLACEHOLDER "Collect the Levies".

The worked example the #696 task/mission wiring needed: a DOMAIN-target
``TaskTemplate`` an org leader can issue and a member can pick up as a
mission (``accept_task`` -> ``staff_assign_mission``). The mission's single
CHECK option grades straight into ``collect_org_income`` via each terminal
route's ``collection_success_level`` (#696 item 2) — there is no mission-side
MONEY reward; the collector's cut lives on the ``TaskOutcomeRoute`` (one
payout surface). All prose/tuning is PLACEHOLDER pending Apostate's pass;
mirrors ``world.seeds.underworld``'s MissionTemplate -> MissionCategory ->
entry MissionNode -> CHECK MissionOption -> per-CheckOutcome terminal
MissionOptionRoute authoring shape.
"""

from __future__ import annotations

from datetime import timedelta

MISSION_TEMPLATE_NAME = "Collect the Levies"
TASK_TEMPLATE_NAME = "Collect the Levies"
DOMAIN_TASK_CATEGORY_NAME = "Domain"


def seed_domain_collection_task() -> None:
    """Seed the PLACEHOLDER "Collect the Levies" mission + task (idempotent).

    Skips gracefully (mission template authored, no graph/task) when the
    Tax Collection CheckType isn't seeded yet — matches
    ``underworld._seed_criminal_mission``'s soft-lookup bail.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.currency.constants import TAX_COLLECTION_CHECK_NAME  # noqa: PLC0415

    check_type = CheckType.objects.filter(name__iexact=TAX_COLLECTION_CHECK_NAME).first()
    template = _seed_mission_template(check_type)
    if template is None or check_type is None:
        return
    _seed_task_template(template, check_type)


def _seed_mission_template(check_type):
    """The single-node CHECK mission the task's ``accept_task`` spawns.

    RESTRICTED visibility with no ``availability_rule`` (defaults to ``{}``)
    admits no PC via the open board / opportunities-discovery flow — this
    template is reachable ONLY through ``accept_task``'s
    ``staff_assign_mission`` call, which bypasses all availability filters.
    Mission discovery is taught, never listed (#696): a task, not a board,
    is the front door.
    """
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
            "summary": (
                "PLACEHOLDER: Ride the circuit of the domain's holdings and "
                "bring the season's levies home."
            ),
            "epilogue": "",
            "risk_tier": 1,  # PLACEHOLDER lowest authored risk tier
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
        },
        name=MISSION_TEMPLATE_NAME,
    )
    if template is None:
        return None
    category, _created = MissionCategory.objects.get_or_create(name=DOMAIN_TASK_CATEGORY_NAME)
    template.categories.add(category)
    if check_type is None:
        return template  # unseeded shard: governance content hasn't landed yet

    entry = authored_or_sample(
        MissionNode,
        {
            "is_entry": True,
            "conflict_mode": ConflictMode.GROUP_VOTE,
            "flavor_text": (
                "PLACEHOLDER: The circuit road unspools ahead — stop by stop, "
                "holding by holding, the season's due waits to be gathered."
            ),
        },
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
            "authored_ic_framing": "PLACEHOLDER: Ride the circuit and collect the levies.",
        },
        node=entry,
        key="option-0",
    )
    if option is None:
        return template
    # No mission-side MONEY rewards — the collector's cut is authored on the
    # linked TaskOutcomeRoute (one payout surface, #696 item 2).
    for outcome_name in (
        "Critical Failure",
        "Failure",
        "Partial Success",
        "Success",
        "Critical Success",
    ):
        outcome = CheckOutcome.objects.get(name=outcome_name)
        authored_or_sample(
            MissionOptionRoute,
            {"target_node": None, "is_random_set": False, "consequence": None},
            option=option,
            outcome_tier=outcome,
        )
    return template


def _seed_task_template(mission_template, check_type) -> None:
    """The TaskTemplate a domain steward issues; grades via ``mission_template``.

    ``check_difficulty`` is a static authored value — the "steward's check
    sets difficulty" mechanic (#696 item 8) is deliberately unbuilt; this is
    a placeholder until a steward-competence input exists to shift it.

    Per-tier ``collection_success_level`` grades are picked straight off
    ``COLLECTION_BAND_PCTS``' own floors (2/1/0/-1; below -1 is catastrophe)
    rather than an independent scale, so each authored tier lands exactly the
    band its name promises — see the per-route comments below.
    """
    from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice  # noqa: PLC0415
    from world.tasking.constants import TaskCategory, TaskTargetKind  # noqa: PLC0415
    from world.tasking.models import TaskOutcomeRoute, TaskTemplate  # noqa: PLC0415
    from world.traits.models import CheckOutcome  # noqa: PLC0415

    task_template, _created = TaskTemplate.objects.get_or_create(
        name=TASK_TEMPLATE_NAME,
        defaults={
            "description": (
                "PLACEHOLDER: Send a collector out on the circuit to gather the "
                "domain's due — coin, grain, and goodwill, depending how it goes."
            ),
            "category": TaskCategory.DOMAIN,
            "check_type": check_type,
            "check_difficulty": DIFFICULTY_VALUES[
                DifficultyChoice.NORMAL
            ],  # PLACEHOLDER — issue #696 item 8: "steward's check sets difficulty"
            # is deliberately unbuilt; static authored value until then.
            "duration": timedelta(days=3),  # PLACEHOLDER
            "target_kind": TaskTargetKind.DOMAIN,
            "mission_template": mission_template,
        },
    )

    # floor 2 -> 110% (critical: goodwill bonus over the gathered aggregate)
    TaskOutcomeRoute.objects.get_or_create(
        template=task_template,
        outcome_tier=CheckOutcome.objects.get(name="Critical Success"),
        defaults={
            "collection_success_level": 2,
            "money_reward": 50,  # PLACEHOLDER collector's cut
            "report_template": (
                "PLACEHOLDER: {agent} returns from the levy circuit with every "
                "household's due paid gladly — the season's levies are home, "
                "and then some."
            ),
        },
    )
    # floor 1 -> 100% (clean collection)
    TaskOutcomeRoute.objects.get_or_create(
        template=task_template,
        outcome_tier=CheckOutcome.objects.get(name="Success"),
        defaults={
            "collection_success_level": 1,
            "money_reward": 25,  # PLACEHOLDER collector's cut
            "report_template": (
                "PLACEHOLDER: {agent} brings the season's levies home, the "
                "circuit run clean stop to stop."
            ),
        },
    )
    # floor 0 -> 85% (skimmed — some of the money stolen en route)
    TaskOutcomeRoute.objects.get_or_create(
        template=task_template,
        outcome_tier=CheckOutcome.objects.get(name="Partial Success"),
        defaults={
            "collection_success_level": 0,
            "money_reward": 10,  # PLACEHOLDER collector's cut
            "report_template": (
                "PLACEHOLDER: {agent} brings the levies home, though the wagon "
                "is lighter than the books promised — someone skimmed along "
                "the way."
            ),
        },
    )
    # floor -1 -> 35% (waylaid — most of the money stolen; the smallest
    # authored non-catastrophe band)
    TaskOutcomeRoute.objects.get_or_create(
        template=task_template,
        outcome_tier=CheckOutcome.objects.get(name="Failure"),
        defaults={
            "collection_success_level": -1,
            # PLACEHOLDER: no collector's cut — nothing clean enough to skim.
            "report_template": (
                "PLACEHOLDER: {agent} makes it back with the levies sorely "
                "thinned — waylaid on the circuit, most of the season's due "
                "gone."
            ),
        },
    )
    # below every COLLECTION_BAND_PCTS floor (-1) -> None -> catastrophe: the
    # pools are lost with the collector.
    TaskOutcomeRoute.objects.get_or_create(
        template=task_template,
        outcome_tier=CheckOutcome.objects.get(name="Critical Failure"),
        defaults={
            "collection_success_level": -2,
            # PLACEHOLDER: catastrophe — the pools are lost with the collector.
            "report_template": (
                "PLACEHOLDER: {agent} never makes it back from the levy "
                "circuit — the season's pooled coin is gone with the collector."
            ),
        },
    )
