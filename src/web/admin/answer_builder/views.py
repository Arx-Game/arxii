"""The Answer builder (#4333 slice 3, design 10): a being's written-ahead answers,
one coverage cell at a time.

Pattern: the Being Service builder. The page opens one cell of the coverage grid
(``?pledge=<pk or "none">&tier=<outcome pk>``) and one answer in it
(``&answer=<pk>``; none, or ``answer=new``, opens a blank one). One save writes
the ``Answer`` and its ``AnswerSacrificeLine`` rows together in one transaction,
with the cell's being, pledge type and tier set by the page, never posted. The
rail shows a preview of the vision, the being's worship, the checks and the
answer's credit. Save credits the answer to the operator's linked contributor;
an unlinked operator sees the setup guidance and nothing is saved.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import ProtectedError
from django.forms import Media
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.answer_builder import live
from web.admin.answer_builder.forms import AnswerForm, SacrificeLineFormSet
from web.admin.authoring.contributors import current_contributor
from web.admin.authoring.credit import stamp_reviewed, stamp_written
from web.admin.tuning.views import superuser_required
from world.traits.models import CheckOutcome
from world.worship.models import Answer, Pledge, WorshippedBeing

#: Submit buttons. "Save" returns to the being's change page, as a stock change form
#: does; the other two stay in the builder.
CONTINUE_BUTTON = "save_continue"
NEXT_TIER_BUTTON = "save_next_tier"
#: The ``answer`` query value that opens a blank answer in the cell.
NEW_ANSWER = "new"
#: The tier a bare page opens on: Success, where an answer carries every part.
DEFAULT_SUCCESS_LEVEL = 1


@dataclass(frozen=True)
class Cell:
    """The coverage cell the page has open."""

    pledge: Pledge | None
    tier: CheckOutcome

    @property
    def key(self) -> str:
        return str(self.pledge.pk) if self.pledge is not None else live.NO_PLEDGE

    @property
    def label(self) -> str:
        return f"Pledge type: {self.pledge.name}" if self.pledge else "No pledge type"


def builder_url(being: WorshippedBeing, pledge_key: str, tier_pk: int, answer: str = "") -> str:
    params = {"pledge": pledge_key, "tier": tier_pk}
    if answer:
        params["answer"] = answer
    return f"{reverse('admin_answer_builder', args=[being.pk])}?{urlencode(params)}"


def _cell_from(request: HttpRequest, being: WorshippedBeing, columns) -> Cell:
    """The cell named by the query (or posted), defaulting to no pledge type at Success."""
    source = request.POST if request.method == "POST" else request.GET
    pledge = None
    pledge_key = source.get("pledge", live.NO_PLEDGE)
    if pledge_key and pledge_key != live.NO_PLEDGE:
        pledge = get_object_or_404(Pledge, pk=pledge_key, being=being)
    tier = None
    if source.get("tier"):
        tier = get_object_or_404(CheckOutcome, pk=source.get("tier"))
    if tier is None:
        tier = next(
            (t for t in columns if t.success_level == DEFAULT_SUCCESS_LEVEL),
            columns[-1] if columns else None,
        )
    if tier is None:
        msg = "No outcome tiers are authored yet."
        raise Http404(msg)
    return Cell(pledge=pledge, tier=tier)


def _cell_answers(being: WorshippedBeing, cell: Cell) -> list[Answer]:
    return list(
        Answer.objects.filter(being=being, pledge=cell.pledge, outcome_tier=cell.tier)
        .select_related("fact_clue", "follow_up_clue", "cost_pool", "written_by", "reviewed_by")
        .order_by("pk")
    )


def _answer_in(request: HttpRequest, being: WorshippedBeing, cell: Cell, answers) -> Answer:
    source = request.POST if request.method == "POST" else request.GET
    wanted = source.get("answer", "")
    if wanted and wanted != NEW_ANSWER:
        return get_object_or_404(
            Answer, pk=wanted, being=being, pledge=cell.pledge, outcome_tier=cell.tier
        )
    if not wanted and answers:
        return answers[0]
    return Answer(being=being, pledge=cell.pledge, outcome_tier=cell.tier)


@dataclass
class _AnswerForms:
    answer: AnswerForm
    lines: SacrificeLineFormSet

    @property
    def media(self) -> Media:
        return self.answer.media + self.lines.media

    def is_valid(self) -> bool:
        return all((self.answer.is_valid(), self.lines.is_valid()))


def _build_forms(request: HttpRequest, answer: Answer) -> _AnswerForms:
    data = request.POST if request.method == "POST" else None
    return _AnswerForms(
        answer=AnswerForm(data, instance=answer, prefix="answer"),
        lines=SacrificeLineFormSet(data, instance=answer, prefix="lines"),
    )


def _next_tier(columns, tier: CheckOutcome) -> CheckOutcome | None:
    higher = [t for t in columns if t.success_level > tier.success_level]
    return higher[0] if higher else None


def _render_page(  # noqa: PLR0913 - the page's open cell and its forms, keyword-only
    request: HttpRequest,
    being: WorshippedBeing,
    *,
    cell: Cell,
    answer: Answer,
    answers: list[Answer],
    forms: _AnswerForms,
    columns,
    needs_setup: bool = False,
) -> HttpResponse:
    def cell_url(pledge_key: str, tier_pk: int) -> str:
        return builder_url(being, pledge_key, tier_pk)

    position = answers.index(answer) + 1 if answer.pk and answer in answers else len(answers) + 1
    favored_facets = sorted(being.being_facets.values_list("facet__name", flat=True))
    return render(
        request,
        "admin/answer_builder/page.html",
        {
            **admin.site.each_context(request),
            "is_nav_sidebar_enabled": False,
            "title": f"Answer builder: {being.name}",
            "being": being,
            "cell": cell,
            "answer": answer,
            "answer_links": [
                (index + 1, builder_url(being, cell.key, cell.tier.pk, str(row.pk)), row == answer)
                for index, row in enumerate(answers)
            ],
            "new_answer_url": builder_url(being, cell.key, cell.tier.pk, NEW_ANSWER),
            "position": position,
            "total": max(len(answers), position),
            "times_used": live.times_used(answer),
            "form": forms.answer,
            "lines": forms.lines,
            "media": forms.media,
            "needs_setup": needs_setup,
            "columns": columns,
            "coverage": live.coverage(
                being, columns, cell_url=cell_url, current=(cell.key, cell.tier.pk)
            ),
            "next_tier": _next_tier(columns, cell.tier),
            "fact_clue": live.clue_context(answer.fact_clue if answer.fact_clue_id else None),
            "follow_up_clue": live.clue_context(
                answer.follow_up_clue if answer.follow_up_clue_id else None
            ),
            "cost_pool": live.pool_context(answer),
            "favored_facets": ", ".join(favored_facets),
            "preview": live.preview(answer),
            "stats": live.worship_stats(being),
            "checks": live.checks(answer, cell.pledge, columns),
            "credit": live.credit_summary(answer),
            "change_url": reverse("admin:arxii_worshippedbeing_change", args=[being.pk]),
            "service_url": reverse("admin_being_service", args=[being.pk]),
            "deity_editor_url": f"/staff/pantheon/{being.pk}",
        },
    )


def _forget_refused_edits(answer: Answer, forms: _AnswerForms) -> None:
    """Validating a ModelForm writes the posted values onto its instance, and the
    saved instances are the identity-mapped ones every reader shares: drop them so
    the next reader loads what the database holds, not this refused edit."""
    if answer.pk is not None:
        answer.flush_from_cache(force=True)
    for form in forms.lines.forms:
        if form.instance.pk is not None:
            form.instance.flush_from_cache(force=True)


@superuser_required
def answer_builder(request: HttpRequest, being_pk: int) -> HttpResponse:
    """GET renders the open cell's answer; POST saves it and its sacrifice lines."""
    being = get_object_or_404(WorshippedBeing, pk=being_pk)
    columns = live.tiers()
    cell = _cell_from(request, being, columns)
    answers = _cell_answers(being, cell)
    answer = _answer_in(request, being, cell, answers)
    contributor = current_contributor(request.user)
    forms = _build_forms(request, answer)
    page = {"cell": cell, "answer": answer, "answers": answers, "forms": forms}
    if request.method != "POST" or contributor is None:
        return _render_page(
            request, being, columns=columns, needs_setup=contributor is None, **page
        )
    if not forms.is_valid():
        response = _render_page(request, being, columns=columns, **page)
        _forget_refused_edits(answer, forms)
        return response
    with transaction.atomic():
        saved = forms.answer.save()
        forms.lines.instance = saved
        forms.lines.save()
        stamp_written(saved, contributor)
    messages.success(request, "Saved and credited to you.")
    if CONTINUE_BUTTON in request.POST:
        return redirect(builder_url(being, cell.key, cell.tier.pk, str(saved.pk)))
    next_tier = _next_tier(columns, cell.tier)
    if NEXT_TIER_BUTTON in request.POST and next_tier is not None:
        return redirect(builder_url(being, cell.key, next_tier.pk))
    return redirect(reverse("admin:arxii_worshippedbeing_change", args=[being.pk]))


@superuser_required
@require_POST
def answer_builder_review(request: HttpRequest, being_pk: int, answer_pk: int) -> HttpResponse:
    """Mark one answer reviewed; authorship untouched."""
    answer = get_object_or_404(Answer, pk=answer_pk, being_id=being_pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking this answer reviewed.")
    else:
        stamp_reviewed(answer, contributor)
        messages.success(request, "Marked reviewed.")
    pledge_key = str(answer.pledge_id) if answer.pledge_id else live.NO_PLEDGE
    return redirect(builder_url(answer.being, pledge_key, answer.outcome_tier_id, str(answer.pk)))


@superuser_required
@require_POST
def answer_builder_delete(request: HttpRequest, being_pk: int, answer_pk: int) -> HttpResponse:
    """Delete one answer. A held answer still waiting on the pool refuses it."""
    answer = get_object_or_404(Answer, pk=answer_pk, being_id=being_pk)
    pledge_key = str(answer.pledge_id) if answer.pledge_id else live.NO_PLEDGE
    tier_pk = answer.outcome_tier_id
    try:
        answer.delete()
    except ProtectedError:
        messages.error(
            request,
            "This answer is held for a character until the being's pool can pay; it "
            "cannot be deleted until it is delivered. Clear Active to stop new draws.",
        )
        return redirect(builder_url(answer.being, pledge_key, tier_pk, str(answer.pk)))
    messages.success(request, "Answer deleted.")
    return redirect(builder_url(answer.being, pledge_key, tier_pk))
