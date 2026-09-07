"""Forms for the tradition slate page (#3675): standard lines and one Beginning's slate.

``TraditionStateLineForm``/``SchoolingLineForm`` back the standard-lines
formsets - shared by every Beginning, so the view always binds them against
every row in the table, not just this Beginning's. ``SlateForm`` backs the
one formset actually scoped to a Beginning: its own ``BeginningTradition``
slate.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect
from django.forms import inlineformset_factory, modelformset_factory

from world.character_creation.models import (
    Beginnings,
    BeginningTradition,
    SchoolingLine,
    TraditionStateLine,
)


class TraditionStateLineForm(forms.ModelForm):
    class Meta:
        model = TraditionStateLine
        fields = ["entry_line", "carries"]
        widgets = {
            "carries": AutocompleteSelect(
                TraditionStateLine._meta.get_field("carries"),  # noqa: SLF001
                admin.site,
            ),
        }


class SchoolingLineForm(forms.ModelForm):
    class Meta:
        model = SchoolingLine
        fields = ["name", "player_line", "grants"]
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
        }


#: The three standard state lines, shared by every Beginning. ``extra=0``: the
#: view always ensures exactly one row per ``TraditionState`` exists before
#: building this, so staff never see a spurious blank row or a missing one.
StateLineFormSet = modelformset_factory(TraditionStateLine, form=TraditionStateLineForm, extra=0)

#: The three standard schooling lines (ranks 0-2), likewise shared and
#: pre-ensured by the view.
SchoolingLineFormSet = modelformset_factory(SchoolingLine, form=SchoolingLineForm, extra=0)

#: This Beginning's own slate: one row per tradition it may offer. ``extra=1``
#: always shows one blank row to fill in; "Add a tradition to this slate"
#: clones more client-side the same way the Upbringing Builder's "Add
#: question" does (there is no saved row to fetch a fragment for yet).
SlateFormSet = inlineformset_factory(
    Beginnings, BeginningTradition, form=SlateForm, extra=1, can_delete=True
)
