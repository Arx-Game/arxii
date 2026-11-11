"""Forms for the Power Builder (item 8 of #5066).

The Application's own fields are a ``ModelForm`` bound to the identity-mapped row, so the
view keeps it in a ``CacheGuard`` before validating. Every source row (a technique, a
trait derivation, a condition effect, a distinction effect) is a plain ``Form`` with its
own prefix: validating one writes nothing onto a model, and the view assigns the cleaned
values itself inside the save's transaction. Number fields come from the model's own
fields, so a row accepts exactly what its column does.
"""

from __future__ import annotations

from django import forms
from django.db.models import Model

from web.admin.power_builder.constants import GrantMode
from world.conditions.models import ConditionCapabilityEffect
from world.distinctions.models import DistinctionEffect
from world.magic.models import Gift, PathGiftGrant, Technique, TechniqueCapabilityGrant
from world.mechanics.models import Application, Property, TraitCapabilityDerivation

#: The reference character's defaults: a mid-level character (the demo's round 3).
DEFAULT_POWER = 6
DEFAULT_TRAIT = 3
DEFAULT_RANK = 2
DEFAULT_SEVERITY = 1


def _model_field(model: type[Model], name: str, **kwargs: object) -> forms.Field:
    """A form field built from the model column, with its validators and limits."""
    return model._meta.get_field(name).formfield(**kwargs)  # noqa: SLF001


class ApplicationForm(forms.ModelForm):
    """What people can do: the Application's own fields, edited in place."""

    class Meta:
        model = Application
        fields = (
            "name",
            "capability",
            "required_effect_property",
            "target_property",
            "way_of_moving",
            "dodges",
            "description",
        )
        labels = {
            "required_effect_property": "Needs the property",
            "target_property": "Where",
            "way_of_moving": "Way of moving",
            "dodges": "Dodges",
        }
        help_texts = {
            "required_effect_property": (
                "A source must carry this property. Blank: any source of the capability."
            ),
            "target_property": "Or a property a wall or target must carry.",
            "way_of_moving": "",
            "dodges": "",
            "description": "",
            "name": "",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        properties = Property.objects.order_by("name")
        self.fields["required_effect_property"].queryset = properties
        self.fields["target_property"].queryset = properties
        self.fields["target_property"].empty_label = "anywhere she moves"
        self.fields["required_effect_property"].empty_label = "no property"
        self.fields["capability"].queryset = self.fields["capability"].queryset.order_by("name")


class ReferenceForm(forms.Form):
    """Compare at: the reference character every strength is read at. Never stored."""

    power = forms.IntegerField(
        label="technique power", min_value=0, initial=DEFAULT_POWER, required=False
    )
    trait = forms.IntegerField(
        label="trait value", min_value=0, initial=DEFAULT_TRAIT, required=False
    )
    rank = forms.IntegerField(
        label="distinction rank", min_value=1, initial=DEFAULT_RANK, required=False
    )
    severity = forms.IntegerField(
        label="condition severity", min_value=0, initial=DEFAULT_SEVERITY, required=False
    )

    def value(self, name: str) -> int:
        """The cleaned value, or the default when the field is missing or refused."""
        if self.is_bound:
            self.is_valid()
            if name not in self.errors and self.cleaned_data.get(name) is not None:
                return self.cleaned_data[name]
        return self.fields[name].initial


def _property_choices(properties: list[Property]) -> list[tuple[int, str]]:
    return [(prop.pk, prop.name) for prop in properties]


class TechniqueRowForm(forms.Form):
    """One technique on the page: its properties, and its grant of the capability.

    ``grant`` (a ``GrantMode``) says which grant controls it carries.
    """

    properties = forms.TypedMultipleChoiceField(
        coerce=int, required=False, widget=forms.CheckboxSelectMultiple
    )

    def __init__(
        self,
        *args: object,
        candidates: list[Property],
        grant: GrantMode,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["properties"].choices = _property_choices(candidates)
        self.grant_mode = grant
        if grant in (GrantMode.EDIT, GrantMode.OFFER):
            required = grant == GrantMode.EDIT
            self.fields["grant_base"] = _model_field(
                TechniqueCapabilityGrant, "base_value", required=required, label="base"
            )
            self.fields["grant_per_power"] = _model_field(
                TechniqueCapabilityGrant,
                "intensity_multiplier",
                required=required,
                label="per power",
            )
        if grant == GrantMode.OFFER:
            self.fields["grant_it"] = forms.BooleanField(required=False, label="grant it")

    def clean(self) -> dict[str, object]:
        data = super().clean()
        if self.grant_mode == GrantMode.OFFER and data.get("grant_it"):
            for name in ("grant_base", "grant_per_power"):
                if data.get(name) is None and name not in self.errors:
                    self.add_error(name, "Give a number to grant it.")
        return data


class TraitRowForm(forms.Form):
    """A trained ability's derivation: base and per point."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["base_value"] = _model_field(TraitCapabilityDerivation, "base_value")
        self.fields["trait_multiplier"] = _model_field(
            TraitCapabilityDerivation, "trait_multiplier"
        )


class ConditionRowForm(forms.Form):
    """A condition's effect on the capability, and (once per condition) its properties."""

    def __init__(self, *args: object, candidates: list[Property] | None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["value"] = _model_field(ConditionCapabilityEffect, "value")
        self.fields["scales_with_severity"] = forms.BooleanField(
            required=False, label="scales with severity"
        )
        self.edits_properties = candidates is not None
        if candidates is not None:
            self.fields["properties"] = forms.TypedMultipleChoiceField(
                coerce=int,
                required=False,
                widget=forms.CheckboxSelectMultiple,
                choices=_property_choices(candidates),
            )


class DistinctionRowForm(forms.Form):
    """A distinction effect's value per rank."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["value_per_rank"] = _model_field(DistinctionEffect, "value_per_rank")


class NewTechniqueForm(forms.Form):
    """Add a technique that does this. Blank name: nothing is added."""

    gift = forms.ModelChoiceField(queryset=Gift.objects.order_by("name"), required=False)
    path_grant = forms.ModelChoiceField(
        queryset=PathGiftGrant.objects.select_related("path", "gift"),
        required=False,
        empty_label="no path",
        label="Path",
    )
    name = _model_field(Technique, "name", required=False)
    with_app_property = forms.BooleanField(required=False, initial=True)
    with_substance = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.fields["grant_base"] = _model_field(
            TechniqueCapabilityGrant, "base_value", required=False, label="base"
        )
        self.fields["grant_per_power"] = _model_field(
            TechniqueCapabilityGrant, "intensity_multiplier", required=False, label="per power"
        )

    @property
    def adds(self) -> bool:
        """Whether a valid form asks for a new technique (a name was given)."""
        return bool(self.cleaned_data.get("name"))

    def clean(self) -> dict[str, object]:
        data = super().clean()
        if not data.get("name"):
            return data
        gift = data.get("gift")
        if gift is None:
            self.add_error("gift", "Pick the gift the technique belongs to.")
        path_grant = data.get("path_grant")
        if gift is not None and path_grant is not None and path_grant.gift_id != gift.pk:
            self.add_error("path_grant", f"That path has no grant of {gift.name}.")
        for name in ("grant_base", "grant_per_power"):
            if data.get(name) is None and name not in self.errors:
                self.add_error(name, "Give a number.")
        if gift is not None and Technique.objects.filter(gift=gift, name=data["name"]).exists():
            self.add_error("name", f"{gift.name} already has a technique by that name.")
        return data
