"""The Upbringing Builder (#3660): author a whole route on one admin page.

Pattern: the Authoring Workbench (`web.admin.authoring.views`): `superuser_required`,
the contributor gate, plain forms, `base_site.html`. Unlike the Workbench, "Add
question" and "Add answer" are client-side formset clones (see `page.html`'s
inline script), not HTMX fragments - there was never a saved row to fetch a
fresh fragment for until the whole route is saved (#3660 review Ruling H).

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
    OfferFormSet,
    QuestionFormSet,
    UpbringingForm,
    answer_formset_for,
    offer_formset_for,
)
from world.character_creation.constants import QuestionKind
from world.character_creation.models import (
    Beginnings,
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
)
from world.character_creation.serializers import CGOriginTemplateSerializer

#: Only these question kinds carry priced answers (Ruling G, #3660 review): the
#: template only ever renders an ``_answers.html`` block for PICK/GROUP
#: (`_question.html`), so binding a formset for every saved question here -
#: including TEXT/PERSON, which the page never posts a management form for -
#: made ``is_valid()`` fail on the missing ``a<pk>-TOTAL_FORMS`` key with no
#: visible error the moment a route carried a TEXT or PERSON question.
_ANSWERABLE_KINDS = (QuestionKind.PICK, QuestionKind.GROUP)

#: Fixed copy shown once, above the answers formsets, on every Upbringing
#: (#3660 amendment: "every help line on the page is fixed copy identical for
#: every Upbringing").
NEW_QUESTION_ANSWERS_HELP = "Save the route once to add answers to a new question."

#: Fixed copy shown in a new (unsaved) answer's Offers cell (#3675) - the same
#: "save once first" limit ``NEW_QUESTION_ANSWERS_HELP`` states for questions,
#: since a nested offers formset needs a real answer pk for its own prefix.
NEW_ANSWER_OFFERS_HELP = "Save the route once to add offers to a new answer."


def _answer_formsets(
    request: HttpRequest | None, template: OriginTemplate
) -> dict[int, AnswerFormSet]:
    """One bound (POST) or unbound answers formset per saved PICK/GROUP question.

    Scoped to ``_ANSWERABLE_KINDS`` so this always matches what
    ``_question.html`` actually renders a formset for - a TEXT or PERSON
    question has no answers block on the page and so never posts its
    management form.
    """
    out: dict[int, AnswerFormSet] = {}
    slots = OriginTemplateSlot.objects.filter(
        template=template, kind__in=_ANSWERABLE_KINDS
    ).order_by("sort_order", "id")
    for slot in slots:
        data = request.POST if request is not None and request.method == "POST" else None
        out[slot.pk] = answer_formset_for(slot, data)
    return out


def _offer_formsets(
    request: HttpRequest | None, template: OriginTemplate
) -> dict[int, OfferFormSet]:
    """One bound (POST) or unbound offers formset per saved answer (#3675).

    Only a saved answer gets one - a client-cloned answer row has no pk yet
    for a nested formset's ``o<choice.pk>`` prefix to key off, the same limit
    a brand-new question already has for its own answers formset.
    """
    out: dict[int, OfferFormSet] = {}
    choices = OriginTemplateSlotChoice.objects.filter(slot__template=template)
    for choice in choices:
        data = request.POST if request is not None and request.method == "POST" else None
        out[choice.pk] = offer_formset_for(choice, data)
    return out


def _deleted_choice_pks(answers: dict[int, AnswerFormSet]) -> set[int]:
    """Every existing answer this POST is about to delete (#3675 review Important 1).

    Called only once every answers formset has validated (``.deleted_forms``
    needs ``full_clean()`` to have already run). An answer's own offers are
    cascade-deleted with it, so saving a *separate* offer formset built
    against that same choice afterward - unconditionally, as the code used
    to - re-inserts or updates a row against a parent that no longer exists:
    a Postgres FK violation inside the save transaction (a clean 500, not
    caught anywhere). Skipping that offer formset's save entirely for a
    deleted choice is correct regardless of what its own rows say, since the
    parent answer is going away either way.
    """
    return {
        form.instance.pk for fs in answers.values() for form in fs.deleted_forms if form.instance.pk
    }


def _question_numbers(template: OriginTemplate) -> dict[int, int]:
    """Each saved question's display number on the page, keyed by pk.

    A question that reuses an earlier question's group, or that only shows after
    one, names that question in its header chip ("About the group from Question
    1", "Branches off Question 1") the way the approved demo does. The number is
    a position on this page, not a stored field, so the page has to carry the
    mapping - the referenced question is any sibling, not necessarily the one
    the template loop is currently on.
    """
    if not template.pk:
        return {}
    slots = OriginTemplateSlot.objects.filter(template=template).order_by("sort_order", "name")
    return {slot.pk: number for number, slot in enumerate(slots, start=1)}


@dataclass
class _RouteForms:
    """The three form layers one route's page needs.

    Bundled into one value (ruff PLR0913) rather than passed as three
    separate positional arguments through every helper and view below.
    """

    form: UpbringingForm
    questions: QuestionFormSet
    answers: dict[int, AnswerFormSet]
    offers: dict[int, OfferFormSet]

    @property
    def media(self) -> Media:
        """Every autocomplete widget's JS/CSS in one bundle - loaded once, in ``extrahead``."""
        media = self.form.media + self.questions.media
        for formset in self.answers.values():
            media = media + formset.media
        for formset in self.offers.values():
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
            "offers": forms.offers,
            "needs_setup": needs_setup,
            "media": forms.media,
            "new_question_answers_help": NEW_QUESTION_ANSWERS_HELP,
            "new_answer_offers_help": NEW_ANSWER_OFFERS_HELP,
            "live": live.for_template(template, request.user) if template.pk else None,
            "rail": live.rail_counts(template) if template.pk else None,
            "question_numbers": _question_numbers(template),
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
        offers = _offer_formsets(request, template) if template.pk else {}
        forms = _RouteForms(form, questions, answers, offers)
        if contributor is None:
            return _render_page(request, template, forms, needs_setup=True)
        valid = (
            form.is_valid()
            and questions.is_valid()
            and all(fs.is_valid() for fs in answers.values())
            and all(fs.is_valid() for fs in offers.values())
        )
        if valid:
            deleted_choice_pks = _deleted_choice_pks(answers)
            with transaction.atomic():
                saved = form.save()
                questions.instance = saved
                questions.save()
                for fs in answers.values():
                    fs.save()
                for choice_pk, fs in offers.items():
                    if choice_pk in deleted_choice_pks:
                        continue
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
    offers = _offer_formsets(None, template) if template.pk else {}
    return _render_page(
        request,
        template,
        _RouteForms(form, questions, answers, offers),
        needs_setup=contributor is None,
    )


@superuser_required
def upbringing_builder_preview(request: HttpRequest, pk: int) -> HttpResponse:
    """Read-only: the questionnaire the way ``CGOriginTemplateSerializer`` hands it to a player.

    Renders the same payload the guided flow's API call returns, picking the
    first offered group of every GROUP question's list for display - a real
    draft would let the player pick among them, but this page has none.
    """
    template = get_object_or_404(OriginTemplate, pk=pk)
    data = CGOriginTemplateSerializer(template, context={"request": request}).data
    return render(
        request,
        "admin/upbringing_builder/_preview.html",
        {"template": template, "origin": data},
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
