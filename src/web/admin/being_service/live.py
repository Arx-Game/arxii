"""The Being Service builder's read-only context (#4333 slice 2): computed from the
saved rows, never written.

* where each favored resonance comes from in play (grants to the being's
  worshippers in the last 30 days, by source), and the deed favor it earns;
* every modifier source authored against the being's two favor targets and the
  two "any being" targets, with a link to where it is edited;
* how long each pledge type's favor target takes from deeds alone at the
  weekly cap, for a stranger, a favor earning modifier holder and a Chosen;
* the being's worship numbers, the page's checks and the pledge types' credit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import math

from django.db.models import Count, Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from web.admin.authoring.links import builder_url
from world.mechanics.constants import FAVOR_EARNING_CATEGORY_NAME, FAVOR_INVOCATION_CATEGORY_NAME
from world.projects.constants import ProjectStatus
from world.worship.constants import FAVOR_EARNING_BASE_PERCENT, BeingResonanceTier
from world.worship.models import (
    BeingResonance,
    DevotionStanding,
    FavorInvocation,
    Pledge,
    PledgeDetails,
    WorshippedBeing,
)

#: How far back "where each resonance comes from in play" looks.
GRANT_WINDOW_DAYS = 30
#: The example favor earning modifier the pacing line shows, in percent.
EXAMPLE_EARNING_MODIFIER = 50


def _admin_url(name: str, pk: int) -> str:
    try:
        return reverse(name, args=[pk])
    except NoReverseMatch:
        return ""


@dataclass(frozen=True)
class ResonanceContext:
    deed_favor: str
    grants: str


def resonance_context(being: WorshippedBeing) -> dict[int, ResonanceContext]:
    """For each of the being's resonance rows (by pk): its deed favor and where
    grants of it to the being's worshippers came from in the last 30 days."""
    from world.magic.models import ResonanceGrant  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    config = get_devotion_config()
    rows = list(BeingResonance.objects.filter(being=being).select_related("resonance"))
    worshipper_ids = DevotionStanding.objects.filter(being=being).values("character_sheet_id")
    since = timezone.now() - timedelta(days=GRANT_WINDOW_DAYS)
    counts = (
        ResonanceGrant.objects.filter(
            character_sheet_id__in=worshipper_ids,
            resonance_id__in=[row.resonance_id for row in rows],
            granted_at__gte=since,
        )
        .values("resonance_id", "source")
        .annotate(count=Count("id"))
        .order_by("resonance_id", "-count")
    )
    by_resonance: dict[int, list[tuple[str, int]]] = {}
    labels = dict(ResonanceGrant._meta.get_field("source").choices)  # noqa: SLF001
    for row in counts:
        by_resonance.setdefault(row["resonance_id"], []).append(
            (str(labels.get(row["source"], row["source"])).lower(), row["count"])
        )
    context: dict[int, ResonanceContext] = {}
    for row in rows:
        percent = (
            config.favored_deed_percent
            if row.tier == BeingResonanceTier.FAVORED
            else config.associated_deed_percent
        )
        sources = by_resonance.get(row.resonance_id, [])
        total = sum(count for _, count in sources)
        grants = (
            f"{total} grants: " + ", ".join(f"{label} {count}" for label, count in sources)
            if total
            else "none yet"
        )
        context[row.pk] = ResonanceContext(deed_favor=f"{percent}% of amount", grants=grants)
    return context


@dataclass(frozen=True)
class ModifierRow:
    target: str
    source: str
    url: str
    value: str
    reach: str


def favor_modifier_rows(being: WorshippedBeing) -> list[ModifierRow]:
    """Every source authored against ``being``'s favor targets or the any-being ones."""
    from world.conditions.models import ConditionInstance, ConditionModifierEffect  # noqa: PLC0415
    from world.covenants.models import CovenantRoleBonus  # noqa: PLC0415
    from world.distinctions.models import CharacterDistinction, DistinctionEffect  # noqa: PLC0415
    from world.items.crafting.models import CraftingRecipeModifier  # noqa: PLC0415
    from world.mechanics.models import ModifierTarget  # noqa: PLC0415

    targets = list(
        ModifierTarget.objects.filter(
            category__name__in=[FAVOR_INVOCATION_CATEGORY_NAME, FAVOR_EARNING_CATEGORY_NAME]
        )
        .filter(Q(target_being=being) | Q(target_being__isnull=True))
        .select_related("category")
        .order_by("target_being", "category__name")
    )
    rows: list[ModifierRow] = []
    for target in targets:
        unit = "points" if target.category.name == FAVOR_INVOCATION_CATEGORY_NAME else "percent"
        before = len(rows)
        for effect in DistinctionEffect.objects.filter(target=target).select_related("distinction"):
            holders = CharacterDistinction.objects.filter(distinction=effect.distinction).count()
            rows.append(
                ModifierRow(
                    target=target.name,
                    source=f"Distinction effect: {effect.distinction.name}",
                    url=builder_url(effect.distinction),
                    value=f"{effect.value_per_rank} {unit} per rank",
                    reach=f"{holders} holder{'s' if holders != 1 else ''}",
                )
            )
        for effect in ConditionModifierEffect.objects.filter(modifier_target=target).select_related(
            "condition", "stage__condition"
        ):
            condition = effect.condition or effect.stage.condition
            active = ConditionInstance.objects.filter(condition=condition).count()
            rows.append(
                ModifierRow(
                    target=target.name,
                    source=f"Condition effect: {condition.name}",
                    url=_admin_url("admin:arxii_conditiontemplate_change", condition.pk),
                    value=f"{effect.value} {unit}",
                    reach=f"{active} active now",
                )
            )
        rows.extend(
            ModifierRow(
                target=target.name,
                source=f"Crafting recipe: {modifier.recipe.name}",
                url=_admin_url("admin:arxii_craftingrecipe_change", modifier.recipe_id),
                value=f"{modifier.base_value} {unit} + quality",
                reach="",
            )
            for modifier in CraftingRecipeModifier.objects.filter(target=target).select_related(
                "recipe"
            )
        )
        rows.extend(
            ModifierRow(
                target=target.name,
                source=f"Covenant role bonus: {bonus.covenant_role.name}",
                url=_admin_url("admin:arxii_covenantrolebonus_change", bonus.pk),
                value=f"{bonus.bonus_per_level} {unit} per level",
                reach="",
            )
            for bonus in CovenantRoleBonus.objects.filter(modifier_target=target).select_related(
                "covenant_role"
            )
        )
        if len(rows) == before:
            rows.append(ModifierRow(target=target.name, source="none", url="", value="", reach=""))
    return rows


def weeks_from_deeds(target: int, rate_percent: int, weekly_cap: int) -> int | None:
    """Game weeks to earn ``target`` favor from deeds alone at the weekly cap."""
    per_week = weekly_cap * rate_percent // 100
    if per_week <= 0:
        return None
    return math.ceil(target / per_week)


def pledge_pacing(pledge: Pledge) -> str:
    """ "At the weekly deed cap, from deeds alone: stranger N weeks · ..." for one pledge."""
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415
    from world.worship.services import get_chosen_favor_config  # noqa: PLC0415

    cap = get_devotion_config().weekly_deed_favor_cap
    chosen = get_chosen_favor_config().earn_bonus_percent
    columns = (
        ("stranger", FAVOR_EARNING_BASE_PERCENT),
        (
            f"+{EXAMPLE_EARNING_MODIFIER}% favor earning modifier",
            FAVOR_EARNING_BASE_PERCENT + EXAMPLE_EARNING_MODIFIER,
        ),
        ("Chosen", FAVOR_EARNING_BASE_PERCENT + chosen),
    )
    parts = []
    for label, rate in columns:
        weeks = weeks_from_deeds(pledge.favor_target, rate, cap)
        if weeks is None:
            parts.append(f"{label} never")
            continue
        unit = "week" if weeks == 1 else "weeks"
        parts.append(f"{label} {weeks} {unit}")
    return "At the weekly deed cap, from deeds alone: " + " · ".join(parts)


@dataclass(frozen=True)
class BeingStats:
    domains: str
    worshippers_with_favor: int
    chosen: int
    open_pledges: int
    closed_pledges: int
    invocations_this_week: int
    worship_pool: int


def being_stats(being: WorshippedBeing) -> BeingStats:
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415

    pledges = PledgeDetails.objects.filter(pledge__being=being)
    return BeingStats(
        domains=being.domains,
        worshippers_with_favor=DevotionStanding.objects.filter(being=being, favor__gt=0).count(),
        chosen=DevotionStanding.objects.filter(
            being=being, valence__isnull=False, released_at__isnull=True
        ).count(),
        open_pledges=pledges.filter(project__status=ProjectStatus.ACTIVE).count(),
        closed_pledges=pledges.filter(
            project__status__in=[ProjectStatus.COMPLETED, ProjectStatus.FAILED]
        ).count(),
        invocations_this_week=FavorInvocation.objects.filter(
            being=being, game_week=get_current_game_week()
        ).count(),
        worship_pool=being.resonance_pool,
    )


def checks(being: WorshippedBeing) -> list[tuple[str, str]]:
    """("ok" | "warn", text) lines about the saved rows. Warnings never block a save."""
    lines: list[tuple[str, str]] = []
    pledges = list(Pledge.objects.filter(being=being).select_related("closing_rite__kind"))
    active = [pledge for pledge in pledges if pledge.is_active]
    if not active:
        lines.append(("warn", f"{being.name} offers no active pledge type yet."))
    bad_rites = [pledge.name for pledge in pledges if not pledge.closing_rite.is_active]
    if bad_rites:
        lines.append(("warn", f"The closing rite is inactive for: {', '.join(bad_rites)}."))
    elif pledges:
        lines.append(("ok", "Every pledge type has an active closing rite."))
    tiers = set(BeingResonance.objects.filter(being=being).values_list("tier", flat=True))
    if BeingResonanceTier.FAVORED in tiers:
        lines.append(("ok", "At least one favored resonance."))
    else:
        lines.append(("warn", "No favored resonance: no deed earns favor at the full rate."))
    if not tiers:
        lines.append(("warn", "No resonance at all: no deed earns favor during a pledge."))
    if not being.being_facets.exists():
        lines.append(("warn", "No favored facet: no sacrifice counts double."))
    return lines


@dataclass(frozen=True)
class CreditSummary:
    written: str
    reviewed: str


def credit_summary(being: WorshippedBeing) -> CreditSummary:
    """Who wrote and reviewed the being's pledge types: one name, "several", or not yet."""
    pledges = list(Pledge.objects.filter(being=being).select_related("written_by", "reviewed_by"))

    def _one(attr: str, missing: str) -> str:
        names = {getattr(p, attr).name for p in pledges if getattr(p, attr) is not None}
        if not pledges or not names or len(names) < 1:
            return missing
        if any(getattr(p, attr) is None for p in pledges):
            return f"{', '.join(sorted(names))} (some not yet)"
        return ", ".join(sorted(names))

    return CreditSummary(
        written=_one("written_by", "Not yet written"),
        reviewed=_one("reviewed_by", "Not yet reviewed"),
    )
