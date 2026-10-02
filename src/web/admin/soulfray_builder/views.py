"""The Soulfray Stage Builder (#4089): one Soulfray stage's whole consequence ladder.

Pattern: the Distinction and Upbringing Builders. Superuser-only; an operator
with no linked ContentContributor sees the setup guidance and nothing is saved.
Every number on the page reads ``soulfray_ladder_summary()``, the helper the
Required-content probes and the game's non-lethal cap read.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from django.contrib import messages
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from web.admin.authoring.contributors import current_contributor
from web.admin.soulfray_builder import live
from web.admin.soulfray_builder.forms import (
    BUILDER_EFFECT_TYPES,
    SPIN_THE_WHEEL_HELP,
    BuilderForms,
    ConsequenceRowForm,
    EffectFormSet,
    build_forms,
)
from web.admin.tuning.views import superuser_required
from world.checks.models import ConsequenceEffect
from world.conditions.models import ConditionStage
from world.magic.models import SoulfrayConfig
from world.magic.services.soulfray import soulfray_ladder_summary, soulfray_stages
from world.traits.models import CheckOutcome


@dataclass(frozen=True)
class RowView:
    """One consequence-table row, with what the template draws beside its form.

    ``is_new`` rows were added on the page (copied or blank): their ``effects``
    formset is prefixed ``new<row index>`` and clones the page's shared
    new-row effect template; a saved row's clones its own ``e<pk>`` template.
    """

    form: ConsequenceRowForm
    source: str
    is_kill: bool
    effect_lines: tuple[str, ...]
    other_effects_url: str
    effects: EffectFormSet
    copy_note: str
    is_new: bool


def _stage_or_404(stage_pk: int) -> ConditionStage:
    return get_object_or_404(
        soulfray_stages().select_related("condition", "consequence_pool__parent"), pk=stage_pk
    )


def _copy_source(request: HttpRequest, stage: ConditionStage) -> ConditionStage | None:
    raw = request.GET.get("copy_from", "")
    if not raw.isdigit():
        return None
    return soulfray_stages().exclude(pk=stage.pk).filter(pk=int(raw)).first()


def _copy_counts(forms: BuilderForms) -> dict[int, int]:
    """Effect counts of the rows a "Copy rows from" prefill copies. One query, or none."""
    copy_ids = [form.initial["copy_of"] for form in forms.rows.forms if form.initial.get("copy_of")]
    if not copy_ids:
        return {}
    return dict(
        ConsequenceEffect.objects.filter(consequence_id__in=copy_ids)
        .values("consequence_id")
        .annotate(n=Count("pk"))
        .values_list("consequence_id", "n")
    )


def _new_row_view(
    forms: BuilderForms, index: int, copy_from: ConditionStage | None, copy_counts: dict[int, int]
) -> RowView:
    form = forms.rows.forms[index]
    source_id = form.initial.get("copy_of")
    note = ""
    if copy_from is not None and source_id:
        count = copy_counts.get(source_id, 0)
        note = f"copies {count} effect{'' if count == 1 else 's'} from {copy_from.name}"
    return RowView(
        form=form,
        source="this stage",
        is_kill=bool(form.initial.get("character_loss")),
        effect_lines=(),
        other_effects_url="",
        effects=forms.new_effects[index],
        copy_note=note,
        is_new=True,
    )


def _row_views(forms: BuilderForms, copy_from: ConditionStage | None) -> list[RowView]:
    table_ids = [row.consequence.pk for row in forms.table]
    effects_by_consequence: dict[int, list[ConsequenceEffect]] = defaultdict(list)
    if table_ids:
        for effect in (
            ConsequenceEffect.objects.filter(consequence_id__in=table_ids)
            .select_related("condition_template", "property", "distinction")
            .order_by("execution_order", "pk")
        ):
            effects_by_consequence[effect.consequence_id].append(effect)
    copy_counts = _copy_counts(forms)

    views: list[RowView] = []
    for index, form in enumerate(forms.rows.forms):
        if index >= len(forms.table):
            views.append(_new_row_view(forms, index, copy_from, copy_counts))
            continue
        row = forms.table[index]
        consequence = row.consequence
        effects = effects_by_consequence.get(consequence.pk, [])
        has_other = any(effect.effect_type not in BUILDER_EFFECT_TYPES for effect in effects)
        views.append(
            RowView(
                form=form,
                source=row.shared_from.name if row.shared_from else "this stage",
                is_kill=consequence.character_loss,
                effect_lines=tuple(live.effect_line(effect) for effect in effects),
                other_effects_url=(
                    reverse("admin:arxii_consequence_change", args=[consequence.pk])
                    if has_other
                    else ""
                ),
                effects=forms.effects[consequence.pk],
                copy_note="",
                is_new=False,
            )
        )
    return views


def _render_page(  # noqa: PLR0913 - the page's own render switches, all keyword-only
    request: HttpRequest,
    stage: ConditionStage,
    forms: BuilderForms,
    *,
    config: SoulfrayConfig | None,
    needs_setup: bool = False,
    copy_from: ConditionStage | None = None,
    conflict: bool = False,
) -> HttpResponse:
    summaries = soulfray_ladder_summary()
    position = next(i for i, s in enumerate(summaries) if s.stage.pk == stage.pk)
    summary = summaries[position]
    outcomes = list(CheckOutcome.objects.order_by("success_level"))
    return render(
        request,
        "admin/soulfray_builder/page.html",
        {
            "title": f"{stage.name} - Soulfray Stage Builder",
            "stage": stage,
            "summary": summary,
            "forms": forms,
            "rows": _row_views(forms, copy_from),
            "ladder": live.ladder_rows(summaries, stage.pk),
            "pooled_count": sum(1 for s in summaries if s.pool is not None),
            "lethal_count": sum(1 for s in summaries if s.can_kill),
            "ladder_line": live.ladder_line(summaries),
            "counts": live.stage_counts(summary),
            "danger": live.danger(summaries, stage),
            "checks": live.checks(summaries, summary, outcomes),
            "table_line": live.table_line(summary, outcomes),
            "kill_odds": live.kill_odds(summary, outcomes),
            "config": config,
            "prev_stage": summaries[position - 1].stage if position > 0 else None,
            "next_stage": (
                summaries[position + 1].stage if position + 1 < len(summaries) else None
            ),
            "spin_help": SPIN_THE_WHEEL_HELP,
            "needs_setup": needs_setup,
            "conflict": conflict,
            "media": forms.media,
        },
    )


@superuser_required
@require_GET
def soulfray_builder(request: HttpRequest, stage_pk: int) -> HttpResponse:
    """GET renders one Soulfray stage. (Task 5 adds POST.)"""
    stage = _stage_or_404(stage_pk)
    config = SoulfrayConfig.objects.cached_singleton()
    copy_from = _copy_source(request, stage)
    forms = build_forms(None, stage, config, copy_from)
    return _render_page(
        request,
        stage,
        forms,
        config=config,
        needs_setup=current_contributor(request.user) is None,
        copy_from=copy_from,
    )


@superuser_required
def soulfray_builder_index(request: HttpRequest) -> HttpResponse:
    """``_soulfray_builder/`` opens the first stage; with no stages, back to the workbench."""
    first = soulfray_stages().first()
    if first is None:
        messages.error(
            request, "No Soulfray stages exist yet. Author the Soulfray condition's stages first."
        )
        return redirect("admin_authoring")
    return redirect("admin_soulfray_builder", stage_pk=first.pk)


@superuser_required
def soulfray_builder_pick(request: HttpRequest) -> HttpResponse:
    """GET ``?pk=`` target of the Builders panel picker; 400 on a missing, unknown or
    non-Soulfray pk, never a silent redirect."""
    raw = request.GET.get("pk", "")
    if not raw.isdigit() or not soulfray_stages().filter(pk=int(raw)).exists():
        return HttpResponseBadRequest("Pick a Soulfray stage to open.")
    return redirect("admin_soulfray_builder", stage_pk=int(raw))
