"""Forms for the Distinction Builder (#3675): effects, exclusions and offers on one page."""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, FilteredSelectMultiple
from django.forms import inlineformset_factory

from world.character_creation.constants import ENEMY_MARKING_DEGREES
from world.character_creation.models import Beginnings, DistinctionOffer
from world.character_sheets.types import EnemyDegree
from world.distinctions.models import Distinction, DistinctionEffect


class DistinctionForm(forms.ModelForm):
    """The distinction's own fields, plus every field the stock ``DistinctionAdmin``
    exposes today - this page fully replaces that admin for authoring
    (``mutually_exclusive_with`` is rendered separately, in its own "Cannot be
    held with" module, not through ``DISTINCTION_FIELDSETS`` below).

    ``cg_max_rank`` (#3739) is declared here rather than left to the ModelForm
    default because a ``PositiveIntegerField`` with a model default is still a
    *required* form field, and this one is blank on all but four rows: an author
    filling in a distinction should not have to type a 0 to mean "no separate
    character-creation cap". Blank cleans to 0, which is what the model reads as
    "``max_rank`` applies in CG too".
    """

    cg_max_rank = forms.IntegerField(
        required=False,
        min_value=0,
        label="CG rank cap",
        help_text="Blank means Ranks applies in character creation too.",
    )

    def clean_cg_max_rank(self) -> int:
        """Blank means 0 -- the model's own "no separate CG cap" value."""
        return self.cleaned_data.get("cg_max_rank") or 0

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
            "is_automatic",
            "requires_slot_filled",
            # Distinctive physical features (#3739). Authored here because the
            # per-feature shape is a property of the distinction, not of any one
            # offer: the same row is offered on every feature there is.
            "taken_per_feature",
            "opens_feature",
            "requires_feature_opened",
            "cg_max_rank",
        ]
        labels = {"max_rank": "Ranks", "mutually_exclusive_with": "Distinctions"}
        help_texts = {
            # Admin-only literals (player-facing words stay on the model field):
            # what an author sees is not what a player reads for the same value.
            "cost_per_rank": (
                'Negative awards. Shown to the player as "1 per rank" or "Awards 2".'
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
    "is_automatic",
    "requires_slot_filled",
    # Distinctive physical features (#3739): rarely touched, since only the four
    # Appearance rows set them, but authorable here rather than in the raw admin.
    "taken_per_feature",
    "opens_feature",
    "requires_feature_opened",
    "cg_max_rank",
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

    Every opener widget is always rendered; ``page.html``'s inline script shows
    only the one(s) this row's chapter wants and hides the rest - server-side
    validation of "exactly one, of the right kind for the chapter" is the model's
    own ``DistinctionOffer.clean()``, run automatically by ``ModelForm._post_clean``.
    ``first_look`` (#3709) is declared here rather than through ``Meta.fields`` so
    the through-model M2M is written explicitly by the view (``views.distinction_builder``
    sets the pins after the row is saved), never by ``save_m2m``.
    """

    first_look = forms.ModelMultipleChoiceField(
        queryset=Beginnings.objects.filter(is_active=True).order_by("name"),
        required=False,
        label="First look for",
        help_text="Beginnings that show this line at rest; the rest fold under See more.",
    )

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
            "prompt",
            "enemy_reason",
            "enemy_degree",
            "appearance_section",
            # The Appearance chapter's other opener (#3739): a line offered on every
            # trait row and marking rather than under a section.
            "feature_rows",
            "sort_order",
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
            "enemy_reason": AutocompleteSelect(
                DistinctionOffer._meta.get_field("enemy_reason"),  # noqa: SLF001
                admin.site,
            ),
            "appearance_section": AutocompleteSelect(
                DistinctionOffer._meta.get_field("appearance_section"),  # noqa: SLF001
                admin.site,
            ),
        }

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # Only the two marking degrees open an offer (the model's clean() says so
        # too); the select offers no others.
        self.fields["enemy_degree"].choices = [("", "---------")] + [
            (value, label) for value, label in EnemyDegree.choices if value in ENEMY_MARKING_DEGREES
        ]
        if self.instance.pk:
            self.fields["first_look"].initial = list(
                self.instance.first_look.values_list("pk", flat=True)
            )


DistinctionEffectFormSet = inlineformset_factory(
    Distinction, DistinctionEffect, form=EffectForm, extra=1, can_delete=True
)
DistinctionOfferFormSet = inlineformset_factory(
    Distinction, DistinctionOffer, form=OfferForm, extra=1, can_delete=True
)
