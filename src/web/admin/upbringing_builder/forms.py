"""Forms for the Upbringing Builder (#3660): one page, every row of a route."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, AutocompleteSelectMultiple
from django.forms import inlineformset_factory
from django.http import QueryDict

from world.character_creation.models import (
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
            "is_active",
            "sort_order",
        ]
        labels = {"frame_narrative": "Card text", "cg_point_cost": "Point cost"}


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
                OriginTemplateSlot._meta.get_field("anchor_orgs").remote_field,  # noqa: SLF001
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
            "grants_distinction",
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
        widgets = {
            "grants_distinction": AutocompleteSelect(
                OriginTemplateSlotChoice._meta.get_field(  # noqa: SLF001
                    "grants_distinction"
                ).remote_field,
                admin.site,
            ),
        }


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
