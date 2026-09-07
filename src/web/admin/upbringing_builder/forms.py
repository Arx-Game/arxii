"""Forms for the Upbringing Builder (#3660): one page, every row of a route."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import (
    AutocompleteSelect,
    AutocompleteSelectMultiple,
    FilteredSelectMultiple,
)
from django.forms import inlineformset_factory
from django.http import QueryDict

from world.character_creation.constants import OfferArrival, OfferChapter
from world.character_creation.models import (
    DistinctionOffer,
    OriginTemplate,
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
)


class UpbringingForm(forms.ModelForm):
    class Meta:
        model = OriginTemplate
        fields = [
            "beginning",
            "name",
            "frame_narrative",
            "cg_point_cost",
            "trust_required",
            "allows_claim_family",
            "allows_name_family",
            "allows_no_family",
            "claimable_kinds",
            "family_templates",
            "closed_distinctions",
            "closed_reason",
            "is_active",
            "sort_order",
        ]
        labels = {
            "frame_narrative": "Card text",
            "cg_point_cost": "Point cost",
            "closed_distinctions": "Distinctions",
            "closed_reason": "The player reads",
        }
        widgets = {
            "closed_distinctions": FilteredSelectMultiple("distinctions", is_stacked=False),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = OriginTemplateSlot
        fields = [
            "name",
            "prompt",
            "example",
            "sort_order",
            "is_required",
            "applies_to",
            "allows_text",
            "kind",
            "connection_kind",
            "life_stage",
            "anchor_source",
            "anchor_org_type",
            "anchor_society",
            "anchor_orgs",
            "exclude_covert",
            "same_anchor_as",
            "follow_up_to",
            "shown_for_choices",
        ]
        labels = {
            "prompt": "Question",
            "kind": "Kind of question",
            "connection_kind": "What the tie was",
            "life_stage": "When",
            "anchor_source": "Which groups can be picked",
            "anchor_orgs": "Groups",
            "same_anchor_as": "Same group as / belongs to",
            "follow_up_to": "Shown after",
            "shown_for_choices": "Only for these answers",
            "is_required": "Required",
            "applies_to": "Only on family path",
        }
        widgets = {
            "anchor_orgs": AutocompleteSelectMultiple(
                OriginTemplateSlot._meta.get_field("anchor_orgs"),  # noqa: SLF001
                admin.site,
            ),
        }

    def __init__(self, *args, template: OriginTemplate | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        siblings = (
            OriginTemplateSlot.objects.filter(template=template)
            if template
            else OriginTemplateSlot.objects.none()
        )
        self.fields["same_anchor_as"].queryset = siblings
        self.fields["follow_up_to"].queryset = siblings
        self.fields["shown_for_choices"].queryset = OriginTemplateSlotChoice.objects.filter(
            slot__in=siblings
        )


class AnswerForm(forms.ModelForm):
    class Meta:
        model = OriginTemplateSlotChoice
        fields = [
            "name",
            "description",
            "cg_point_cost",
            "cost_per_influence",
            "reputation_seed",
            "trust_required",
            "is_active",
            "sort_order",
        ]
        labels = {
            "name": "Answer",
            "description": "Line under it",
            "cg_point_cost": "Cost",
            "cost_per_influence": "Per point of influence",
            "reputation_seed": "Group's opinion",
            "trust_required": "Trust",
        }


#: How the Builder groups the Upbringing form's fields into admin fieldsets.
#: Rendered through Django admin's own ``admin/includes/fieldset.html`` (#3667),
#: so the page inherits admin's label column, help lines, checkbox rows,
#: required markers and error markup instead of re-inventing them - #3660
#: shipped ``{{ form.as_div }}``, which admin's stylesheet does not target at
#: all. A field left out of these tuples does not render, so both tuples list
#: every editable field of their form.
UPBRINGING_FIELDSETS = (
    (None, {"fields": ("beginning", "name", "frame_narrative")}),
    ("Cost", {"fields": (("cg_point_cost", "trust_required"),)}),
    (
        "Family paths",
        {
            "fields": (
                ("allows_claim_family", "allows_name_family", "allows_no_family"),
                "claimable_kinds",
                "family_templates",
            )
        },
    ),
    ("On the picker", {"fields": (("is_active", "sort_order"),)}),
)

#: The same, for one question. Grouped as the approved demo groups them: what
#: the question is, the tie it records, which groups it offers, when it shows.
QUESTION_FIELDSETS = (
    (None, {"fields": ("kind", "name", "prompt", "example", "is_required")}),
    ("The tie", {"fields": (("connection_kind", "life_stage"),)}),
    # Split at the type/realm boundary so the "Matches N groups today" live line
    # can be emitted between the two, directly under the rule it reports on, the
    # way `page.html` already places the open-places line under "Family paths"
    # (#3667 demo-fidelity review). Nothing here is hand-written form markup:
    # both halves still render through admin's own fieldset template.
    (
        "Which groups can be picked",
        {"fields": ("anchor_source", ("anchor_org_type", "anchor_society"))},
    ),
    (
        None,
        {"fields": ("anchor_orgs", "exclude_covert", "same_anchor_as")},
    ),
    (
        "When this question is shown",
        {"fields": ("follow_up_to", "shown_for_choices", "applies_to")},
    ),
    ("Order", {"fields": (("sort_order", "allows_text"), "DELETE")}),
)


QuestionFormSet = inlineformset_factory(
    OriginTemplate,
    OriginTemplateSlot,
    form=QuestionForm,
    extra=0,
    can_delete=True,
    fk_name="template",
)
AnswerFormSet = inlineformset_factory(
    OriginTemplateSlot,
    OriginTemplateSlotChoice,
    form=AnswerForm,
    extra=0,
    can_delete=True,
    fk_name="slot",
)


def answer_formset_for(slot: OriginTemplateSlot, data: QueryDict | None = None) -> AnswerFormSet:
    """One ``AnswerFormSet`` instance for ``slot``, prefixed ``a<slot.pk>``.

    The one place the ``a<slot.pk>`` prefix convention lives: every caller
    that needs a slot's answers formset (the page's per-question section and
    the save view's POST binding) goes through this rather than re-deriving
    the prefix. "Add answer" itself is a client-side clone of this formset's
    own empty form, not a server round trip (#3660 review Ruling H).
    """
    return AnswerFormSet(data, instance=slot, prefix=f"a{slot.pk}")


class OfferForm(forms.ModelForm):
    """One "offers" row hanging off an answer (#3675).

    ``chapter`` is forced to LINEAGE here and never shown as a select - the
    row exists because it hangs off this answer, so which chapter it belongs
    to is not a choice an author makes on this page (mirrors the Glimpse tag
    admin's own ``GlimpseTagOfferForm``, forcing GLIMPSE the same way).
    ``origin_choice`` itself needs no forcing: Django's own
    ``BaseInlineFormSet._construct_form`` stamps the parent answer's pk onto
    a new row's fk attribute before validation runs. ``arrives_as`` drops
    CARRIED - an answer's own offer is either a priced choice or bundled free
    with picking the answer; CARRIED is for an opener that isn't itself a
    choice (a schooling line, a Glimpse tag), which an Upbringing answer
    already is.
    """

    class Meta:
        model = DistinctionOffer
        fields = ["distinction", "arrives_as", "sort_order"]
        widgets = {
            "distinction": AutocompleteSelect(
                DistinctionOffer._meta.get_field("distinction"),  # noqa: SLF001
                admin.site,
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.chapter = OfferChapter.LINEAGE
        self.fields["arrives_as"].choices = [
            (value, label) for value, label in OfferArrival.choices if value != OfferArrival.CARRIED
        ]


OfferFormSet = inlineformset_factory(
    OriginTemplateSlotChoice,
    DistinctionOffer,
    form=OfferForm,
    fk_name="origin_choice",
    extra=0,
    can_delete=True,
)


def offer_formset_for(
    choice: OriginTemplateSlotChoice, data: QueryDict | None = None
) -> OfferFormSet:
    """One ``OfferFormSet`` instance for ``choice``, prefixed ``o<choice.pk>``.

    Mirrors ``answer_formset_for``'s own prefix convention. Only ever called
    for a saved answer - a client-cloned answer row has no pk yet for the
    prefix to key off (`NEW_ANSWER_OFFERS_HELP` is what the page shows in
    that row's Offers cell instead).
    """
    return OfferFormSet(data, instance=choice, prefix=f"o{choice.pk}")
