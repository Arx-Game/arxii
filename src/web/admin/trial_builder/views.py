"""The Trial builder (#4513 slice 2 of #4343): one mission option's trial on one page.

A trial has no model. It is a mission option (the check) whose routes, one per outcome tier,
carry consequences that make a codex entry known, train or grant the technique it opens, and
cost the character something. The page edits a whole option: the trial header (what it
opens), then one fieldset per outcome tier, with a rail of blocking and informational
warnings. One save writes each tier's route, consequence and effects together in one
transaction and credits them to the operator's linked contributor; an unlinked operator sees
the setup guidance and nothing is saved.

Every refusal is slice 1's (``checks.trial_rules``, through the model ``clean`` methods; see
``proposal.py``). ``trial_builder_check`` runs the same code over the posted form and returns
the rail, so the warnings update as the author edits without a second copy of any rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import admin, messages
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.trial_builder import live, save
from web.admin.trial_builder.forms import HeaderForm, TierForm
from web.admin.trial_builder.proposal import TierProposal, build
from web.admin.trial_builder.state import TierState, header_from, load
from web.admin.tuning.views import superuser_required
from world.checks.constants import EffectType
from world.missions.constants import OptionKind
from world.missions.models import MissionOption, MissionOptionRoute

CONTINUE_BUTTON = "save_continue"
HEADER_PREFIX = "trial"


def tier_prefix(state: TierState) -> str:
    return f"tier{state.tier.pk}"


def _option(option_pk: int) -> MissionOption:
    option = get_object_or_404(
        MissionOption.objects.select_related("node__template", "authored_check_type"),
        pk=option_pk,
    )
    if option.option_kind != OptionKind.CHECK:
        msg = "A trial is built on a CHECK option: its routes are keyed by the check's outcome."
        raise Http404(msg)
    return option


def _initial_data(form: HeaderForm | TierForm) -> dict[str, str]:
    """The form's saved values as posted data, so the page binds and validates on first load.

    The rail is recomputed from the form on every render (spec #4343 section 6), the first
    one included, so a saved trial that already breaks a rule shows it on opening.
    """
    data: dict[str, str] = {}
    for name, field in form.fields.items():
        value = form.initial.get(name, field.initial)
        if value in (None, False, ""):
            continue
        data[form.add_prefix(name)] = "on" if value is True else str(value)
    return data


@dataclass
class Evaluation:
    """A bound header and tier forms, and what they propose."""

    header: HeaderForm
    tiers: list[TierForm]
    proposals: list[TierProposal]
    valid: bool

    @property
    def refused(self) -> bool:
        return not self.valid or any(p.errors for p in self.proposals)


def evaluate(
    option: MissionOption, states: list[TierState], posted: dict[str, str] | None
) -> Evaluation:
    """Bind the forms to ``posted`` (or the saved values) and run slice 1's rules over them."""
    initial = header_from(states)
    header = HeaderForm(initial_header=initial, prefix=HEADER_PREFIX)
    nodes = option.node.template.nodes.order_by("key")
    tiers = [
        TierForm(
            prefix=tier_prefix(state),
            state=state,
            nodes=nodes,
            default_label=f"{option.node.template.name}: {option.node.key}, {state.tier.name}",
        )
        for state in states
    ]
    data = dict(posted) if posted is not None else {}
    if posted is None:
        data = _initial_data(header)
        for form in tiers:
            data.update(_initial_data(form))
    header = HeaderForm(data, initial_header=initial, prefix=HEADER_PREFIX)
    tiers = [
        TierForm(
            data,
            prefix=tier_prefix(form.state),
            state=form.state,
            nodes=nodes,
            default_label=form.initial.get("label", ""),
        )
        for form in tiers
    ]
    valid = all([header.is_valid(), *[form.is_valid() for form in tiers]])
    proposals = build(option, header, tiers) if valid else []
    return Evaluation(header=header, tiers=tiers, proposals=proposals, valid=valid)


def _rail(states: list[TierState], result: Evaluation) -> dict[str, object]:
    routed = {s.tier.pk for s in states if s.route is not None}
    routed |= {p.tier.pk for p in result.proposals}
    return live.rail(
        result.header,
        result.proposals,
        own_consequence_ids={s.consequence.pk for s in states if s.consequence is not None},
        all_tiers_routed=len(routed) == len(states),
    )


def _tier_errors(result: Evaluation) -> dict[int, list[str]]:
    """Per tier pk: the messages to draw on that tier's fieldset."""
    errors: dict[int, list[str]] = {form.tier.pk: [] for form in result.tiers}
    for proposal in result.proposals:
        errors[proposal.tier.pk].extend(proposal.errors)
    return errors


def _render_page(  # noqa: PLR0913 - the option, its saved tiers, what the page proposes, two flags
    request: HttpRequest,
    option: MissionOption,
    states: list[TierState],
    result: Evaluation,
    *,
    needs_setup: bool = False,
    refused: bool = False,
) -> HttpResponse:
    template = option.node.template
    tier_errors = _tier_errors(result)
    head = result.header.cleaned_data if result.header.is_bound else {}
    blocks = [
        {
            "form": form,
            "state": form.state,
            "errors": tier_errors[form.tier.pk],
            "number": index + 1,
            "total": len(result.tiers),
            "shared_url": (
                reverse("admin:arxii_consequence_change", args=[form.state.consequence.pk])
                if form.state.shared and form.state.consequence is not None
                else ""
            ),
            "other_effects": [str(e) for e in form.state.others],
        }
        for index, form in enumerate(result.tiers)
    ]
    return render(
        request,
        "admin/trial_builder/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": f"Trial builder: {option.node.key}",
            "option": option,
            "template": template,
            "header": result.header,
            "blocks": blocks,
            "media": sum((f.media for f in result.tiers), result.header.media),
            "opened": live.opened_by(head.get("codex_entry")),
            "taught": live.taught_lines(head.get("technique")),
            "rail": _rail(states, result),
            "needs_setup": needs_setup,
            "refused": refused,
            "has_trial_routes": any(s.codex or s.training for s in states),
            "check_url": reverse("admin_trial_builder_check", args=[option.pk]),
            "delete_url": reverse("admin_trial_builder_delete", args=[option.pk]),
            "template_url": reverse("admin:arxii_missiontemplate_change", args=[template.pk]),
            "node_url": reverse("admin:arxii_missionnode_change", args=[option.node_id]),
            "option_url": reverse("admin:arxii_missionoption_change", args=[option.pk]),
            "index_url": reverse("admin_trial_builder_index"),
        },
    )


@superuser_required
def trial_builder(request: HttpRequest, option_pk: int) -> HttpResponse:
    """GET renders the option's trial; POST validates it with slice 1's rules and saves it."""
    option = _option(option_pk)
    states = load(option)
    contributor = current_contributor(request.user)
    posted = request.POST.dict() if request.method == "POST" else None
    result = evaluate(option, states, posted)
    if request.method != "POST" or contributor is None:
        return _render_page(request, option, states, result, needs_setup=contributor is None)
    if result.refused:
        return _render_page(request, option, states, result, refused=True)
    save.save(option, result.proposals, contributor)
    messages.success(request, "Saved and credited to you.")
    if CONTINUE_BUTTON in request.POST:
        return redirect(reverse("admin_trial_builder", args=[option.pk]))
    return redirect(reverse("admin:arxii_missionoption_change", args=[option.pk]))


@superuser_required
@require_POST
def trial_builder_check(request: HttpRequest, option_pk: int) -> JsonResponse:
    """The rail and per-tier messages for the posted form; writes nothing."""
    option = _option(option_pk)
    states = load(option)
    result = evaluate(option, states, request.POST.dict())
    return JsonResponse(
        {
            "rail": render_to_string(
                "admin/trial_builder/_rail.html", {"rail": _rail(states, result)}, request
            ),
            "tier_errors": {str(pk): msgs for pk, msgs in _tier_errors(result).items()},
        }
    )


@superuser_required
@require_POST
def trial_builder_delete(request: HttpRequest, option_pk: int) -> HttpResponse:
    """Delete the option's trial routes (and the consequences nothing else uses)."""
    option = _option(option_pk)
    deleted, refused = save.delete_trial_routes(load(option))
    if deleted:
        messages.success(request, f"Deleted {deleted} trial route{'s' if deleted != 1 else ''}.")
    for reason in refused:
        messages.error(request, f"Not deleted. {reason}.")
    if not deleted and not refused:
        messages.info(request, "This option has no trial routes.")
    return redirect(reverse("admin_trial_builder", args=[option.pk]))


@superuser_required
def trial_builder_index(request: HttpRequest) -> HttpResponse:
    """Options that already carry a trial, and a jump to any option by pk (``?option=<pk>``)."""
    wanted = request.GET.get("option", "").strip()
    if wanted.isdigit():
        return redirect(reverse("admin_trial_builder", args=[int(wanted)]))
    trial_option_ids = (
        MissionOptionRoute.objects.filter(
            Q(consequence__effects__effect_type=EffectType.TECHNIQUE_TRAINING)
            | Q(
                consequence__effects__effect_type=EffectType.GRANT_CODEX,
                consequence__effects__grants_known=True,
            )
        )
        .values_list("option_id", flat=True)
        .distinct()
    )
    options = (
        MissionOption.objects.filter(pk__in=trial_option_ids, option_kind=OptionKind.CHECK)
        .select_related("node__template")
        .order_by("node__template__name", "node__key", "order")
    )
    return render(
        request,
        "admin/trial_builder/index.html",
        {
            **admin.site.each_context(request),
            "title": "Trial builder",
            "options": [(o, reverse("admin_trial_builder", args=[o.pk])) for o in options],
            "invalid_option": bool(wanted) and not wanted.isdigit(),
        },
    )
