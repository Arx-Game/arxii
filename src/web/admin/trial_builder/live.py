"""The Trial builder's rail and per-tier summary (#4513): read-only, recomputed from the form.

The blocking warnings are the messages slice 1's rules gave each proposal (``proposal.py``);
nothing here re-decides a rule. The informational warnings and the context blocks (where the
technique is taught, where else the entry is made known) are this page's own reading of the
rows. The same function renders the page and answers the live check, so what the rail shows
while the author edits is what the save will say.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from web.admin.trial_builder.forms import COST_CONDITION, COST_SCAR, HeaderForm
from web.admin.trial_builder.proposal import TierProposal
from world.checks.constants import (
    CRITICAL_SUCCESS_TIER_MIN_LEVEL,
    FAILURE_TIER_MAX_LEVEL,
    SUCCESS_TIER_MIN_LEVEL,
    EffectType,
)
from world.checks.models import ConsequenceEffect
from world.checks.trial_rules import is_opening_effect
from world.codex.models import CodexEntry
from world.codex.services import gated_technique_requirements
from world.magic.models import Technique, TechniqueTeachingOffer
from world.magic.services.technique_acquisition import technique_teaching_sources
from world.npc_services.models import TrainOfferDetails
from world.progression.services.spends import concrete_requirement_types

BLOCK = "block"
INFO = "info"
OK_LINE = "Every row that opens or trains the technique carries a real cost."


@dataclass(frozen=True)
class RailWarning:
    kind: str
    text: str


@dataclass(frozen=True)
class OpenedTechnique:
    name: str
    gift: str
    url: str
    prerequisites: list[str]


@dataclass(frozen=True)
class Link:
    text: str
    url: str


def _admin_url(name: str, pk: int) -> str:
    return reverse(f"admin:arxii_{name}_change", args=[pk])


def _kind_and_value(effect: ConsequenceEffect) -> tuple[str, int]:
    kind = COST_SCAR if effect.effect_type == EffectType.MAGICAL_SCARS else COST_CONDITION
    return kind, effect.condition_severity or 0


def _opening_bit(effect: ConsequenceEffect) -> str:
    """How one codex or training effect reads in the summary; '' for any other effect."""
    if effect.effect_type == EffectType.GRANT_CODEX:
        return "knows entry" if effect.grants_known else "lead"
    if effect.effect_type == EffectType.TECHNIQUE_TRAINING:
        if effect.grants_technique_outright:
            return "technique outright"
        return f"{effect.training_points} points" if effect.training_points else ""
    return ""


def summary_line(proposal: TierProposal) -> str:
    """'knows entry, 15 points, scar tier 2, reward: cosmetic scar tier 3' for one tier."""
    bits = [bit for bit in map(_opening_bit, proposal.effects) if bit]
    consequence = proposal.consequence
    if consequence is None:
        return ""
    cost = _tier_cost(proposal)
    if cost is not None:
        label = "scar tier" if cost[0] == COST_SCAR else "condition sev"
        bits.append(f"{label} {cost[1]}")
    elif consequence.deliberately_free:
        bits.append("free")
    else:
        bits.append("no cost")
    bits.extend(
        f"reward: cosmetic scar tier {e.condition_severity}"
        for e in proposal.effects
        if e.effect_type == EffectType.MAGICAL_SCARS and e.scar_is_cosmetic
    )
    return ", ".join(bits)


def _tier_cost(proposal: TierProposal) -> tuple[str, int] | None:
    for effect in proposal.effects:
        if effect.effect_type == EffectType.MAGICAL_SCARS and not effect.scar_is_cosmetic:
            return _kind_and_value(effect)
        if effect.effect_type == EffectType.APPLY_CONDITION:
            return _kind_and_value(effect)
    return None


def _tier_notes(proposal: TierProposal) -> list[RailWarning]:
    """Informational notes about one tier: empty text, points that apply only on a repeat."""
    notes: list[RailWarning] = []
    name, level = proposal.tier.name, proposal.tier.success_level
    if not (proposal.form.cleaned_data.get("outcome_text") or "").strip():
        notes.append(RailWarning(INFO, f"{name}: outcome text is empty."))
    points = next(
        (
            e.training_points
            for e in proposal.effects
            if e.effect_type == EffectType.TECHNIQUE_TRAINING and e.training_points
        ),
        None,
    )
    if points and FAILURE_TIER_MAX_LEVEL < level < SUCCESS_TIER_MIN_LEVEL:
        notes.append(
            RailWarning(
                INFO,
                f"{name}: the {points} points apply only to a character who already knows "
                "the entry and meets the other prerequisites (a repeat attempt).",
            )
        )
    return notes


def _cost_comparison(proposals: list[TierProposal]) -> list[RailWarning]:
    """A Critical Success that costs less than the Success of the same kind."""
    crit = next(
        (p for p in proposals if p.tier.success_level >= CRITICAL_SUCCESS_TIER_MIN_LEVEL), None
    )
    success = next(
        (
            p
            for p in proposals
            if SUCCESS_TIER_MIN_LEVEL <= p.tier.success_level < CRITICAL_SUCCESS_TIER_MIN_LEVEL
        ),
        None,
    )
    if not (crit and success):
        return []
    crit_cost, success_cost = _tier_cost(crit), _tier_cost(success)
    if (
        crit_cost
        and success_cost
        and crit_cost[0] == success_cost[0]
        and crit_cost[1] < success_cost[1]
    ):
        return [RailWarning(INFO, "Critical Success costs less than Success. Intended?")]
    return []


def _info_warnings(
    proposals: list[TierProposal], technique: Technique | None, has_all_routes: bool
) -> list[RailWarning]:
    out = [note for proposal in proposals for note in _tier_notes(proposal)]
    out.extend(_cost_comparison(proposals))
    if technique is not None and not technique_teaching_sources(technique).is_taught:
        out.append(
            RailWarning(
                INFO,
                f"No teacher or Academy offers {technique.name}; the trial is the only way to "
                "start the meter.",
            )
        )
    if proposals and not has_all_routes:
        out.append(
            RailWarning(
                INFO,
                "A tier with no route has nowhere to go when a roll lands there; fill in every "
                "tier the check can reach.",
            )
        )
    return out


def taught_lines(technique: Technique | None) -> list[str]:
    """Where ``technique`` is taught, with each offer's meter size for comparison."""
    if technique is None:
        return []
    lines = [
        f"{details.offer.role.faction_affiliation.name}, {details.learn_ap_cost} point meter"
        for details in TrainOfferDetails.objects.filter(
            technique=technique, offer__role__faction_affiliation__isnull=False
        ).select_related("offer__role__faction_affiliation")
    ]
    costs = sorted(
        TechniqueTeachingOffer.objects.filter(technique=technique).values_list(
            "learn_ap_cost", flat=True
        )
    )
    if costs:
        plural = "s" if len(costs) != 1 else ""
        span = f"{costs[0]}" if costs[0] == costs[-1] else f"{costs[0]} to {costs[-1]}"
        lines.append(f"{len(costs)} player teacher offer{plural}, {span} point meter")
    else:
        lines.append("No player teacher offers")
    return lines


def opened_by(entry: CodexEntry | None) -> list[OpenedTechnique]:
    """Each technique whose active requirement names ``entry``, with its other prerequisites."""
    if entry is None:
        return []
    out = []
    for requirement in gated_technique_requirements(entry).select_related("technique__gift"):
        technique = requirement.technique
        others: list[str] = []
        for req_type in concrete_requirement_types():
            for other in req_type.objects.filter(technique=technique, is_active=True):
                if other.pk == requirement.pk and req_type is type(requirement):
                    continue
                others.append(f"{req_type._meta.verbose_name}: {other.description or other}")  # noqa: SLF001
        out.append(
            OpenedTechnique(
                name=technique.name,
                gift=technique.gift.name,
                url=_admin_url("technique", technique.pk),
                prerequisites=others,
            )
        )
    return out


def elsewhere(entry: CodexEntry | None, own_consequence_ids: set[int]) -> list[Link]:
    """Other consequences that make ``entry`` known."""
    if entry is None:
        return []
    rows = (
        ConsequenceEffect.objects.filter(
            effect_type=EffectType.GRANT_CODEX, grants_known=True, codex_entry=entry
        )
        .exclude(consequence_id__in=own_consequence_ids)
        .select_related("consequence")
        .order_by("consequence__label")
    )
    return [
        Link(row.consequence.label, _admin_url("consequence", row.consequence_id)) for row in rows
    ]


def rail(
    header: HeaderForm,
    proposals: list[TierProposal],
    *,
    own_consequence_ids: set[int],
    all_tiers_routed: bool,
) -> dict[str, object]:
    """Everything the rail template draws."""
    head = header.cleaned_data if hasattr(header, "cleaned_data") else {}
    technique, entry = head.get("technique"), head.get("codex_entry")
    blocking = [
        RailWarning(BLOCK, f"{p.tier.name}: {message}") for p in proposals for message in p.errors
    ]
    info = _info_warnings(proposals, technique, all_tiers_routed)
    opens_something = any(is_opening_effect(e) for p in proposals for e in p.effects)
    return {
        "warnings": [*blocking, *info],
        "blocking_count": len(blocking),
        "all_clear": opens_something and not blocking,
        "ok_line": OK_LINE,
        "summary": [(p.tier.name, summary_line(p)) for p in proposals],
        "taught": taught_lines(technique),
        "elsewhere": elsewhere(entry, own_consequence_ids),
    }
