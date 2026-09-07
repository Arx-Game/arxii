"""Forms for the Distinction Builder (#3675): effects, exclusions and offers on one page."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, FilteredSelectMultiple
from django.forms import inlineformset_factory

from world.character_creation.models import DistinctionOffer
from world.distinctions.models import Distinction, DistinctionEffect


class DistinctionForm(forms.ModelForm):
    """The distinction's own fields, plus every field the stock ``DistinctionAdmin``
    exposes today - this page fully replaces that admin for authoring
    (``mutually_exclusive_with`` is rendered separately, in its own "Cannot be
    held with" module, not through ``DISTINCTION_FIELDSETS`` below).
    """

    class Meta:
        model = Distinction
        fields = [
            "name",
            "category",
            "cost_per_rank",
            "max_rank",
            "description",
            "mutually_exclusive_with",
            "slug",
            "is_active",
            "tags",
            "secret_by_default",
            "default_secret_level",
            "parent_distinction",
            "allow_other",
            "trust_value",
            "trust_category",
            "is_automatic",
            "requires_slot_filled",
        ]
        labels = {"max_rank": "Ranks", "mutually_exclusive_with": "Distinctions"}
        help_texts = {
            # Admin-only literals (player-facing words stay on the model field):
            # what an author sees is not what a player reads for the same value.
            "cost_per_rank": (
                'Negative refunds. Shown to the player as "1 per rank" or "Refunds 2".'
            ),
            "max_rank": "1 for a plain yes or no.",
        }
        widgets = {
            "category": AutocompleteSelect(
                Distinction._meta.get_field("category"),  # noqa: SLF001
                admin.site,
            ),
            "parent_distinction": AutocompleteSelect(
                Distinction._meta.get_field("parent_distinction"),  # noqa: SLF001
                admin.site,
            ),
            "trust_category": AutocompleteSelect(
                Distinction._meta.get_field("trust_category"),  # noqa: SLF001
                admin.site,
            ),
            "mutually_exclusive_with": FilteredSelectMultiple("distinctions", is_stacked=False),
        }


#: The main "None" group is the five fields the demo draws; "More" carries every
#: other field ``DistinctionAdmin`` exposes today so this page can fully replace
#: it for authoring, collapsed since an author rarely touches them. Rendered as
#: plain rows in ``page.html`` (not through ``admin/includes/fieldset.html`` - a
#: bare ``<details>`` needs no extra plumbing for the collapse itself).
DISTINCTION_MAIN_FIELDS = ("name", "category", "cost_per_rank", "max_rank", "description")
DISTINCTION_MORE_FIELDS = (
    "slug",
    "is_active",
    "tags",
    "secret_by_default",
    "default_secret_level",
    "parent_distinction",
    "allow_other",
    "trust_value",
    "trust_category",
    "is_automatic",
    "requires_slot_filled",
)


class EffectForm(forms.ModelForm):
    class Meta:
        model = DistinctionEffect
        fields = ["target", "value_per_rank"]
        widgets = {
            "target": AutocompleteSelect(
                DistinctionEffect._meta.get_field("target"),  # noqa: SLF001
                admin.site,
            ),
        }


class OfferForm(forms.ModelForm):
    """One "where it is offered" row.

    All three openers are always rendered; ``page.html``'s inline script shows
    only the one this row's chapter wants and hides the other two - server-side
    validation of "at most one, the right one for the chapter" is the model's
    own ``DistinctionOffer.clean()``, run automatically by ``ModelForm._post_clean``.
    """

    class Meta:
        model = DistinctionOffer
        fields = [
            "chapter",
            "arrives_as",
            "name",
            "player_line",
            "schooling_line",
            "glimpse_tag",
            "origin_choice",
        ]
        widgets = {
            "glimpse_tag": AutocompleteSelect(
                DistinctionOffer._meta.get_field("glimpse_tag"),  # noqa: SLF001
                admin.site,
            ),
            "origin_choice": AutocompleteSelect(
                DistinctionOffer._meta.get_field("origin_choice"),  # noqa: SLF001
                admin.site,
            ),
        }


DistinctionEffectFormSet = inlineformset_factory(
    Distinction, DistinctionEffect, form=EffectForm, extra=1, can_delete=True
)
DistinctionOfferFormSet = inlineformset_factory(
    Distinction, DistinctionOffer, form=OfferForm, extra=1, can_delete=True
)
