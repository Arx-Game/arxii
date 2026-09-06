"""The Upbringing Builder (#3660): author a whole route on one admin page.

Pattern: the Authoring Workbench (`web.admin.authoring.views`): `superuser_required`,
the contributor gate, plain forms, HTMX fragments, `base_site.html`.

A "route" is one Upbringing (`OriginTemplate`) plus every question
(`OriginTemplateSlot`) and answer (`OriginTemplateSlotChoice`) hanging off it.
Save writes the whole route in one transaction and, once the operator has a
linked `ContentContributor`, credits every row of it in the same request
(`credit.stamp_written`). An unlinked operator sees the setup guidance instead
and nothing is saved, mirroring the Authoring Workbench's own gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.db import transaction
from django.forms import Media
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from web.admin.authoring.contributors import current_contributor
from web.admin.tuning.views import superuser_required
from web.admin.upbringing_builder import live
from web.admin.upbringing_builder.credit import stamp_reviewed, stamp_written
from web.admin.upbringing_builder.forms import (
    AnswerFormSet,
    QuestionFormSet,
    UpbringingForm,
    answer_formset_for,
)
from world.character_creation.models import Beginnings, OriginTemplate, OriginTemplateSlot

#: Fixed copy shown once, above the answers formsets, on every Upbringing
#: (#3660 amendment: "every help line on the page is fixed copy identical for
#: every Upbringing").
NEW_QUESTION_ANSWERS_HELP = "Save the route once to add answers to a new question."


def _answer_formsets(
    request: HttpRequest | None, template: OriginTemplate
) -> dict[int, AnswerFormSet]:
    """One bound (POST) or unbound answers formset per saved question, prefix ``a<slot pk>``."""
    out: dict[int, AnswerFormSet] = {}
    for slot in OriginTemplateSlot.objects.filter(template=template).order_by("sort_order", "id"):
        data = request.POST if request is not None and request.method == "POST" else None
        out[slot.pk] = answer_formset_for(slot, data)
    return out


@dataclass
class _RouteForms:
    """The three form layers one route's page needs.

    Bundled into one value (ruff PLR0913) rather than passed as three
    separate positional arguments through every helper and view below.
    """

    form: UpbringingForm
    questions: QuestionFormSet
    answers: dict[int, AnswerFormSet]

    @property
    def media(self) -> Media:
        """Every autocomplete widget's JS/CSS in one bundle - loaded once, in ``extrahead``."""
        media = self.form.media + self.questions.media
        for formset in self.answers.values():
            media = media + formset.media
        return media


def _render_page(
    request: HttpRequest,
    template: OriginTemplate,
    forms: _RouteForms,
    *,
    needs_setup: bool = False,
) -> HttpResponse:
    return render(
        request,
        "admin/upbringing_builder/page.html",
        {
            "title": f"Upbringing Builder: {template.name if template.pk else 'New Upbringing'}",
            "template": template,
            "form": forms.form,
            "questions": forms.questions,
            "answers": forms.answers,
            "needs_setup": needs_setup,
            "media": forms.media,
            "new_question_answers_help": NEW_QUESTION_ANSWERS_HELP,
            "live": live.for_template(template, request.user) if template.pk else None,
            "rail": live.rail_counts(template) if template.pk else None,
        },
    )


@superuser_required
def upbringing_builder(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    """GET renders the page; POST saves every row in one transaction and credits the operator."""
    if pk is None:
        beginning_pk = request.GET.get("beginning") or request.POST.get("beginning")
        beginning = get_object_or_404(Beginnings, pk=beginning_pk)
        template = OriginTemplate(beginning=beginning)
    else:
        template = get_object_or_404(OriginTemplate, pk=pk)
    contributor = current_contributor(request.user)
    if request.method == "POST":
        form = UpbringingForm(request.POST, instance=template)
        questions = QuestionFormSet(
            request.POST,
            instance=template,
            prefix="q",
            form_kwargs={"template": template if template.pk else None},
        )
        answers = _answer_formsets(request, template) if template.pk else {}
        forms = _RouteForms(form, questions, answers)
        if contributor is None:
            return _render_page(request, template, forms, needs_setup=True)
        valid = (
            form.is_valid()
            and questions.is_valid()
            and all(fs.is_valid() for fs in answers.values())
        )
        if valid:
            with transaction.atomic():
                saved = form.save()
                questions.instance = saved
                questions.save()
                for fs in answers.values():
                    fs.save()
                stamp_written(saved, contributor)
            messages.success(request, "Saved and credited to you.")
            return redirect(reverse("admin_upbringing_builder", args=[saved.pk]))
        return _render_page(request, template, forms)
    form = UpbringingForm(instance=template)
    questions = QuestionFormSet(
        instance=template, prefix="q", form_kwargs={"template": template if template.pk else None}
    )
    answers = _answer_formsets(None, template) if template.pk else {}
    return _render_page(
        request, template, _RouteForms(form, questions, answers), needs_setup=contributor is None
    )


@superuser_required
@require_POST
def upbringing_builder_review(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark the whole route reviewed; never touches authorship or unsaved edits."""
    template = get_object_or_404(OriginTemplate, pk=pk)
    contributor = current_contributor(request.user)
    if contributor is None:
        messages.error(request, "Link a contributor before marking a route reviewed.")
    else:
        stamp_reviewed(template, contributor)
        messages.success(request, "Marked reviewed.")
    return redirect(reverse("admin_upbringing_builder", args=[pk]))


@superuser_required
def upbringing_builder_answers(request: HttpRequest, pk: int, slot_pk: int) -> HttpResponse:
    """HTMX fragment: the answers formset for one saved question, with one extra blank row."""
    slot = get_object_or_404(OriginTemplateSlot, pk=slot_pk, template_id=pk)
    formset = answer_formset_for(slot)
    return render(
        request,
        "admin/upbringing_builder/_answers.html",
        {"slot": slot, "formset": formset, "extra": True},
    )
