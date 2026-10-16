"""Forms for the Answer builder (#4333 slice 3): one answer and its sacrifice lines."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect
from django.forms import inlineformset_factory

from world.magic.models import Facet
from world.worship.models import Answer, AnswerSacrificeLine


def _autocomplete(field_name: str) -> AutocompleteSelect:
    return AutocompleteSelect(Answer._meta.get_field(field_name), admin.site)  # noqa: SLF001


class AnswerForm(forms.ModelForm):
    """One answer's parts. The being, the pledge type and the outcome tier come
    from the coverage cell the page has open, never from the form, so
    ``Answer.clean`` checks the tier's rules against the cell being edited."""

    class Meta:
        model = Answer
        fields = [
            "delay_text",
            "answer_text",
            "fact_text",
            "fact_clue",
            "cost_text",
            "cost_pool",
            "follow_up_text",
            "follow_up_clue",
            "onlooker_line",
            "weight",
            "conceals_source",
            "is_active",
        ]
        labels = {
            "conceals_source": "Conceal the being as the source",
            "follow_up_text": "Follow-up text",
            "follow_up_clue": "Follow-up clue",
        }
        widgets = {
            "delay_text": forms.Textarea(attrs={"rows": 3, "class": "vLargeTextField"}),
            "answer_text": forms.Textarea(attrs={"rows": 4, "class": "vLargeTextField"}),
            "fact_text": forms.Textarea(attrs={"rows": 3, "class": "vLargeTextField"}),
            "cost_text": forms.Textarea(attrs={"rows": 3, "class": "vLargeTextField"}),
            "follow_up_text": forms.Textarea(attrs={"rows": 3, "class": "vLargeTextField"}),
            "onlooker_line": forms.TextInput(attrs={"class": "vTextField", "size": 80}),
            "weight": forms.NumberInput(attrs={"class": "vIntegerField", "min": 1}),
            "fact_clue": _autocomplete("fact_clue"),
            "cost_pool": _autocomplete("cost_pool"),
            "follow_up_clue": _autocomplete("follow_up_clue"),
        }
        help_texts = {
            "fact_clue": (
                "States one fact. Codex or secret clues only. Rule: fact text and fact clue "
                "are allowed on Success and Critical Success only; refused on Partial "
                "Success, Failure and Critical Failure."
            ),
            "follow_up_clue": (
                "Handed over with the vision, usually a mission. Rule: allowed on Partial "
                "Success and above."
            ),
            "cost_pool": "Its consequences at this answer's tier apply when the vision is sent.",
        }


class SacrificeLineForm(forms.ModelForm):
    class Meta:
        model = AnswerSacrificeLine
        fields = ["facet", "text"]
        widgets = {"text": forms.TextInput(attrs={"class": "vTextField", "size": 60})}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["facet"].queryset = Facet.objects.order_by("name")


SacrificeLineFormSet = inlineformset_factory(
    Answer, AnswerSacrificeLine, form=SacrificeLineForm, extra=0, can_delete=True
)
