"""The Soulfray Stage Builder's ladder, Danger rail, checks and live lines (#4089).

Pure reads over ``soulfray_ladder_summary()``, the same helper the
Required-content probes and the game's non-lethal cap read, so the panel, this
page and the game never disagree. Nothing here builds a URL; templates do.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from world.checks.models import ConsequenceEffect
from world.conditions.models import ConditionStage
from world.magic.audere_majora import AudereMajoraThreshold
from world.magic.services.soulfray import nonlethal_ceiling_for
from world.magic.types import SoulfrayStageSummary
from world.traits.models import CheckOutcome


@dataclass(frozen=True)
class LadderRow:
    summary: SoulfrayStageSummary
    bar_percent: int
    is_open: bool


def _bar_percent(threshold: int | None, top: int) -> int:
    if not threshold or not top:
        return 0
    return max(1, round(threshold * 100 / top))


def ladder_rows(summaries: Sequence[SoulfrayStageSummary], open_stage_pk: int) -> list[LadderRow]:
    """One row per stage; the Danger bar is the stage's threshold against the top threshold."""
    top = max((s.stage.severity_threshold or 0 for s in summaries), default=0)
    return [
        LadderRow(
            summary=summary,
            bar_percent=_bar_percent(summary.stage.severity_threshold, top),
            is_open=summary.stage.pk == open_stage_pk,
        )
        for summary in summaries
    ]


@dataclass(frozen=True)
class Danger:
    first_lethal: SoulfrayStageSummary | None
    nonlethal_cap: int | None
    lethal_stage_names: tuple[str, ...]
    crossing_levels: tuple[int, ...]


def danger(summaries: Sequence[SoulfrayStageSummary], stage: ConditionStage) -> Danger:
    """The rail's Danger module. Crossings list boundary levels only, never ceremony text."""
    lethal = [summary for summary in summaries if summary.can_kill]
    levels = tuple(
        AudereMajoraThreshold.objects.filter(minimum_warp_stage=stage)
        .order_by("boundary_level")
        .values_list("boundary_level", flat=True)
    )
    return Danger(
        first_lethal=lethal[0] if lethal else None,
        nonlethal_cap=nonlethal_ceiling_for(summaries),
        lethal_stage_names=tuple(summary.stage.name for summary in lethal),
        crossing_levels=levels,
    )


@dataclass(frozen=True)
class StageCounts:
    consequences: int
    shared: int
    effects: int
    kill_rows: int


def stage_counts(summary: SoulfrayStageSummary) -> StageCounts:
    """The rail's "This stage" module. One query (the effect count)."""
    ids = [wc.consequence.pk for wc in summary.consequences]
    effects = ConsequenceEffect.objects.filter(consequence_id__in=ids).count() if ids else 0
    return StageCounts(
        consequences=summary.consequence_count,
        shared=len(summary.shared_consequence_ids),
        effects=effects,
        kill_rows=sum(1 for wc in summary.consequences if wc.character_loss),
    )


def outcomes_without_draws(
    summary: SoulfrayStageSummary, outcomes: Sequence[CheckOutcome]
) -> list[CheckOutcome]:
    """Roll results this stage's pool has no row for (compared by id; no FK fetch)."""
    drawn = {wc.consequence.outcome_tier_id for wc in summary.consequences}
    return [outcome for outcome in outcomes if outcome.pk not in drawn]


def kill_odds(summary: SoulfrayStageSummary, outcomes: Sequence[CheckOutcome]) -> list[str]:
    """For each roll result with a Can kill row: lethal weight in total weight."""
    lines = []
    for outcome in outcomes:
        tier = [wc for wc in summary.consequences if wc.consequence.outcome_tier_id == outcome.pk]
        lethal = sum(wc.weight for wc in tier if wc.character_loss)
        if lethal:
            total = sum(wc.weight for wc in tier)
            lines.append(f"Chance a {outcome.name} here kills: {lethal} in {total} by weight.")
    return lines


def table_line(summary: SoulfrayStageSummary, outcomes: Sequence[CheckOutcome]) -> str:
    """The live line under the consequence table."""
    count = summary.consequence_count
    if not count:
        return "No consequences yet: a caster here gains severity and nothing happens."
    kills = sum(1 for wc in summary.consequences if wc.character_loss)
    noun = "consequence" if count == 1 else "consequences"
    parts = [f"{count} {noun} reachable here", f"{kills} can kill" if kills else "none can kill"]
    gaps = outcomes_without_draws(summary, outcomes)
    if gaps:
        verb = "draws" if len(gaps) == 1 else "draw"
        parts.append(f"{', '.join(outcome.name for outcome in gaps)} {verb} nothing at this stage")
    return "; ".join(parts) + "."


def ladder_line(summaries: Sequence[SoulfrayStageSummary]) -> tuple[str, str]:
    """The live line under the ladder: ("ok"|"warn", text)."""
    lethal = next((summary for summary in summaries if summary.can_kill), None)
    if lethal is None:
        return (
            "warn",
            'No stage can kill yet. The Required-content row "Some Soulfray stage can kill" '
            "stays red.",
        )
    cap = nonlethal_ceiling_for(summaries)
    if cap is None:
        return ("ok", f"{lethal.stage.name} can kill.")
    return (
        "ok",
        f"{lethal.stage.name} can kill. Non-lethal casts stop adding severity at {cap}, one "
        "short of it.",
    )


def _adjacency_checks(summaries: Sequence[SoulfrayStageSummary]) -> list[tuple[str, str]]:
    cap = nonlethal_ceiling_for(summaries)
    if cap is None:
        return []
    warns = []
    for lower, upper in pairwise(summaries):
        threshold = lower.stage.severity_threshold
        if upper.can_kill and not lower.can_kill and threshold is not None and threshold <= cap:
            warns.append(
                (
                    "warn",
                    f"{lower.stage.name} can be reached by a non-lethal cast and is one stage "
                    "below a death stage. Check its warning text says so.",
                )
            )
    return warns


def _shared_pool_checks(
    summaries: Sequence[SoulfrayStageSummary], summary: SoulfrayStageSummary
) -> list[tuple[str, str]]:
    if summary.pool is None:
        return []
    others = [
        s.stage.name
        for s in summaries
        if s.pool is not None and s.pool.pk == summary.pool.pk and s.stage.pk != summary.stage.pk
    ]
    if not others:
        return []
    names = ", ".join(f"{name}'s" for name in others)
    which = "that stage" if len(others) == 1 else "those stages"
    return [("warn", f"This pool is also {names} pool; an edit here changes {which} too.")]


def checks(
    summaries: Sequence[SoulfrayStageSummary],
    summary: SoulfrayStageSummary,
    outcomes: Sequence[CheckOutcome],
) -> list[tuple[str, str]]:
    """The rail's Checks list. Warnings never block a save: authored content is never
    refused by its own checklist (spec C.6)."""
    result: list[tuple[str, str]] = []
    if summary.consequence_count:
        result.append(("ok", "the pool has consequences, so this stage does something."))
        gaps = outcomes_without_draws(summary, outcomes)
        if gaps:
            result.extend(
                ("warn", f"no consequence for {outcome.name} at this stage.") for outcome in gaps
            )
        else:
            result.append(("ok", "every roll result draws something here."))
    else:
        result.append(
            (
                "warn",
                "this stage has no consequences; a caster here gains severity and nothing happens.",
            )
        )
    lethal = [s.stage.name for s in summaries if s.can_kill]
    if lethal:
        result.append(("ok", f"a stage can kill ({', '.join(lethal)})."))
    else:
        result.append(("warn", "no Soulfray stage can kill. Soulfray is meant to be able to."))
    empty = sum(1 for s in summaries if not s.consequence_count)
    if not empty:
        result.append(("ok", "every stage has consequences."))
    elif empty == 1:
        result.append(("warn", "1 stage has no consequences yet."))
    else:
        result.append(("warn", f"{empty} stages have no consequences yet."))
    result.extend(_adjacency_checks(summaries))
    result.extend(_shared_pool_checks(summaries, summary))
    return result


def effect_line(effect: ConsequenceEffect) -> str:
    """One effect as the consequence table lists it: "Deal Damage, self, 8"."""
    parts = [effect.get_effect_type_display(), effect.target]
    if effect.damage_amount is not None:
        parts.append(str(effect.damage_amount))
    if effect.condition_template_id:
        severity = f" sev {effect.condition_severity}" if effect.condition_severity else ""
        parts.append(f"{effect.condition_template.name}{severity}")
    if effect.property_id:
        parts.append(effect.property.name)
    if effect.distinction_id:
        parts.append(effect.distinction.name)
    return ", ".join(parts)
