"""The Soulfray Stage Builder (#4089): one Soulfray stage's whole consequence ladder.

Pattern: the Distinction and Upbringing Builders. Superuser-only; an operator
with no linked ContentContributor sees the setup guidance and nothing is saved.
Every number on the page reads ``soulfray_ladder_summary()``, the helper the
Required-content probes and the game's non-lethal cap read.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed
from web.admin.soulfray_builder import live
from web.admin.soulfray_builder.forms import (
    BUILDER_EFFECT_TYPES,
    SPIN_THE_WHEEL_HELP,
    BuilderForms,
    ConsequenceRowForm,
    EffectFormSet,
    build_forms,
)
from web.admin.soulfray_builder.save import (
    cache_guard_for,
    live_new_rows,
    pool_switch_conflict,
    require_pool_for_new_rows,
    save_stage,
)
from web.admin.tuning.views import superuser_required
from world.checks.models import ConsequenceEffect
from world.conditions.models import ConditionStage
from world.magic.models import SoulfrayConfig
from world.magic.services.soulfray import soulfray_ladder_summary, soulfray_stages
from world.traits.models import CheckOutcome

#: The submit button's name for "Save and open <next stage>" (page.html).
SAVE_NEXT = "save_next"


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
    copy_counts = _copy_counts(forms)

    views: list[RowView] = []
    for index, form in enumerate(forms.rows.forms):
        if index >= len(forms.table):
            views.append(_new_row_view(forms, index, copy_from, copy_counts))
            continue
        row = forms.table[index]
        consequence = row.consequence
        effects = forms.table_effects.get(consequence.pk, [])
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


def _all_valid(forms: BuilderForms) -> bool:
    """Validate every layer (no short-circuit, so every error renders at once).

    An added row's effects are validated only when the row is created by this
    save: a blank or Removed added row is skipped, and so are its effects, so a
    half-filled effect on it never blocks the save.
    """
    results = [
        forms.stage.is_valid(),
        forms.on_entry.is_valid(),
        forms.penalty.is_valid(),
        forms.pool.is_valid(),
        forms.rows.is_valid(),
        *(effects.is_valid() for effects in forms.effects.values()),
    ]
    live = live_new_rows(forms)
    results.extend(forms.new_effects[index].is_valid() for index in live)
    if results[3] and results[4]:
        results.append(require_pool_for_new_rows(forms))
    return all(results)


def _after_save_url(request: HttpRequest, stage: ConditionStage) -> str:
    if SAVE_NEXT in request.POST:
        following = soulfray_stages().filter(stage_order__gt=stage.stage_order).first()
        if following is not None:
            return reverse("admin_soulfray_builder", args=[following.pk])
    return reverse("admin_soulfray_builder", args=[stage.pk])


@superuser_required
def soulfray_builder(request: HttpRequest, stage_pk: int) -> HttpResponse:
    """GET renders one Soulfray stage; POST saves every layer in one transaction."""
    stage = _stage_or_404(stage_pk)
    config = SoulfrayConfig.objects.cached_singleton()
    contributor = current_contributor(request.user)
    copy_from = _copy_source(request, stage)
    data = request.POST if request.method == "POST" else None
    forms = build_forms(data, stage, config, copy_from)
    if request.method != "POST":
        return _render_page(
            request,
            stage,
            forms,
            config=config,
            needs_setup=contributor is None,
            copy_from=copy_from,
        )
    # Validating binds posted values onto cached rows the live game reads; every
    # refusal puts them back after the page (which re-validates) has rendered.
    guard = cache_guard_for(forms)
    refusal: dict[str, bool] | None = None
    if contributor is None:
        refusal = {"needs_setup": True}
    elif not _all_valid(forms):
        refusal = {}
    elif pool_switch_conflict(forms):
        refusal = {"conflict": True}
    if refusal is not None:
        try:
            return _render_page(request, stage, forms, config=config, **refusal)
        finally:
            guard.restore()
    save_stage(stage, forms, config, contributor, guard=guard)
    messages.success(request, "Saved and credited to you.")
    return redirect(_after_save_url(request, stage))


@superuser_required
@require_POST
def soulfray_builder_review(request: HttpRequest, stage_pk: int) -> HttpResponse:
    """Mark the stage, its pool, the pool's own consequences and their effects reviewed.

    "Own" means rows this pool holds that its parent does not: a shared row this
    stage only reweights is the shared pool's, reviewed wherever that is reviewed.
    Authorship and unsaved edits on the page are never touched.
    """
    stage = _stage_or_404(stage_pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking this stage reviewed.")
        return redirect("admin_soulfray_builder", stage_pk=stage.pk)
    with transaction.atomic():
        stamp_reviewed(stage, contributor)
        pool = stage.consequence_pool
        if pool is not None:
            stamp_reviewed(pool, contributor)
            entries = pool.entries.filter(is_excluded=False).select_related("consequence")
            if pool.parent_id is not None:
                entries = entries.exclude(consequence__pool_entries__pool_id=pool.parent_id)
            consequences = [entry.consequence for entry in entries]
            for consequence in consequences:
                stamp_reviewed(consequence, contributor)
            for effect in ConsequenceEffect.objects.filter(
                consequence_id__in=[c.pk for c in consequences]
            ):
                stamp_reviewed(effect, contributor)
    messages.success(request, "Marked reviewed.")
    return redirect("admin_soulfray_builder", stage_pk=stage.pk)


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
