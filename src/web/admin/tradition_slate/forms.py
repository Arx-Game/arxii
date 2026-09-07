"""Forms for the tradition slate page (#3675): standard lines and one Beginning's slate.

``TraditionStateLineForm``/``SchoolingLineForm`` back the standard-lines
formsets - shared by every Beginning, so the view always binds them against
every row in the table, not just this Beginning's. Both forms carry their own
identity field (``state``/``rank``) as a hidden input, never a free select:
fixed for a saved row, and fixed by the formset's own ``initial`` for a row
that does not exist yet (a still-unauthored ``TraditionState``/rank). Nothing
about a standard line's identity is ever typed in - only ``entry_line``/
``carries`` or ``name``/``player_line``/``grants`` are.

``SlateForm`` backs the one formset actually scoped to a Beginning: its own
``BeginningTradition`` slate.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect
from django.db.models import QuerySet
from django.forms import BaseModelFormSet, inlineformset_factory, modelformset_factory
from django.http import QueryDict

from world.character_creation.constants import TraditionState
from world.character_creation.models import (
    Beginnings,
    BeginningTradition,
    SchoolingLine,
    TraditionStateLine,
)


class TraditionStateLineForm(forms.ModelForm):
    state = forms.ChoiceField(choices=TraditionState.choices, widget=forms.HiddenInput())

    class Meta:
        model = TraditionStateLine
        fields = ["state", "entry_line", "carries"]
        widgets = {
            "carries": AutocompleteSelect(
                TraditionStateLine._meta.get_field("carries"),  # noqa: SLF001
                admin.site,
            ),
        }


class SchoolingLineForm(forms.ModelForm):
    rank = forms.IntegerField(widget=forms.HiddenInput())

    class Meta:
        model = SchoolingLine
        fields = ["rank", "name", "player_line", "grants"]
        widgets = {
            "grants": AutocompleteSelect(
                SchoolingLine._meta.get_field("grants"),  # noqa: SLF001
                admin.site,
            ),
        }


class SlateForm(forms.ModelForm):
    class Meta:
        model = BeginningTradition
        fields = ["tradition", "state", "own_wording", "sort_order"]
        widgets = {
            "tradition": AutocompleteSelect(
                BeginningTradition._meta.get_field("tradition"),  # noqa: SLF001
                admin.site,
            ),
            # An empty cell alone doesn't tell an author the shared state line's
            # words apply here - "standard" is the same placeholder copy the
            # demo shows for a slate line with no override (#3675 review).
            "own_wording": forms.TextInput(attrs={"placeholder": "standard"}),
        }


def state_line_formset(
    data: QueryDict | None,
    queryset: QuerySet[TraditionStateLine],
    missing_states: list[str],
) -> BaseModelFormSet:
    """The three state-line rows: one per existing row, one per still-missing state.

    A missing state's row is an unsaved ``extra`` form - its ``state`` comes
    from ``initial``, never typed in, and nothing is written to the database
    until the page is saved (#3675 demo-fidelity ruling: a GET used to
    ``get_or_create`` blank rows just to have three to show).
    """
    formset_class = modelformset_factory(
        TraditionStateLine, form=TraditionStateLineForm, extra=len(missing_states)
    )
    return formset_class(
        data,
        prefix="state",
        queryset=queryset,
        initial=[{"state": state} for state in missing_states],
    )


def schooling_line_formset(
    data: QueryDict | None,
    queryset: QuerySet[SchoolingLine],
    missing_ranks: list[int],
) -> BaseModelFormSet:
    """The three schooling-line rows: one per existing row, one per still-missing rank."""
    formset_class = modelformset_factory(
        SchoolingLine, form=SchoolingLineForm, extra=len(missing_ranks)
    )
    return formset_class(
        data,
        prefix="schooling",
        queryset=queryset,
        initial=[{"rank": rank} for rank in missing_ranks],
    )


#: This Beginning's own slate: one row per tradition it may offer. ``extra=1``
#: always shows one blank row to fill in; "Add a tradition to this slate"
#: clones more client-side the same way the Upbringing Builder's "Add
#: question" does (there is no saved row to fetch a fragment for yet).
SlateFormSet = inlineformset_factory(
    Beginnings, BeginningTradition, form=SlateForm, extra=1, can_delete=True
)
