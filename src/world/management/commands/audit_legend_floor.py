"""List mission templates whose legend reward lines violate the risk floor (#2051).

One-time legacy audit — the #1997 Game Ops dashboard pattern. Run after deploy
to identify existing templates that predate the save-time guard. Safe to run
repeatedly (read-only).

Run as: ``arx manage audit_legend_floor``
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from world.missions.constants import LEGEND_RISK_FLOOR_TIER, DeedRewardSink
from world.missions.models import MissionOptionRouteReward, MissionRenownAward, MissionTemplate
from world.societies.constants import RenownRisk


def _template_for_reward(reward: MissionOptionRouteReward) -> MissionTemplate | None:
    """Walk the FK chain to the owning MissionTemplate (mirrors the model method)."""
    route = reward.route
    if route is None and reward.candidate_id is not None:
        route = reward.candidate.route if reward.candidate_id else None
    if route is None or route.option_id is None:
        return None
    option = route.option
    if option is None or option.node_id is None:
        return None
    return option.node.template


def _template_for_award(award: MissionRenownAward) -> MissionTemplate | None:
    """Walk the FK chain to the owning MissionTemplate for a RenownAward."""
    route = award.route
    if route is None or route.option_id is None:
        return None
    option = route.option
    if option is None or option.node_id is None:
        return None
    return option.node.template


class Command(BaseCommand):
    help = "List mission templates with legend rewards below the risk floor (#2051)."

    def handle(self, *_args: Any, **_options: Any) -> None:
        violations: list[str] = []
        violations.extend(self._check_route_rewards())
        violations.extend(self._check_renown_awards())

        if not violations:
            self.stdout.write("No legend floor violations found.")
        else:
            self.stdout.write(f"{len(violations)} legend floor violation(s):")
            for v in violations:
                self.stdout.write(v)

    def _check_route_rewards(self) -> list[str]:
        """Check MissionOptionRouteReward rows with LEGEND_POINTS sink."""
        violations: list[str] = []
        for reward in MissionOptionRouteReward.objects.filter(
            sink=DeedRewardSink.LEGEND_POINTS,
        ).select_related("route__option__node__template"):
            template = _template_for_reward(reward)
            if template is None:
                continue
            if template.risk_tier < LEGEND_RISK_FLOOR_TIER:
                violations.append(
                    f"  Reward {reward.pk} → template '{template.name}' "
                    f"(risk_tier={template.risk_tier})"
                )
        return violations

    def _check_renown_awards(self) -> list[str]:
        """Check MissionRenownAward rows with legend-paying risk."""
        legend_paying = {RenownRisk.HIGH.value, RenownRisk.EXTREME.value}
        violations: list[str] = []
        for award in MissionRenownAward.objects.filter(
            risk__in=legend_paying,
        ).select_related("route__option__node__template"):
            template = _template_for_award(award)
            if template is None:
                continue
            if template.risk_tier < LEGEND_RISK_FLOOR_TIER:
                violations.append(
                    f"  RenownAward {award.pk} (risk={award.risk}) → template "
                    f"'{template.name}' (risk_tier={template.risk_tier})"
                )
        return violations
