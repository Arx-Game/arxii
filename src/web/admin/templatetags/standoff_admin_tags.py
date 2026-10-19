"""Template filters for the standoff authoring pages (#4354, #4361)."""

from __future__ import annotations

from django import template

from world.standoffs.models import FactionRule
from world.standoffs.services.gm_view import faction_rule_label as _faction_rule_label

register = template.Library()


@register.filter
def faction_rule_label(rule: FactionRule) -> str:
    """A short staff-facing label for what a faction rule tests."""
    return _faction_rule_label(rule)


@register.filter
def reason_lines(reason: str) -> list[str]:
    """A staff reason split into its lines: the tier first, then the causes, one each."""
    return reason.splitlines()
