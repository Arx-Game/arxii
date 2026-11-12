"""Forms for the Being Service builder (#4333 slice 2): a being's favored resonances,
favored facets (with their worn rates, #4520) and pledge types, written together."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.forms import (
    BaseInlineFormSet,
    BaseModelFormSet,
    inlineformset_factory,
    modelformset_factory,
)

from world.pacts.constants import CharacterPactCommitmentKind
from world.pacts.models import PactOffer, PactOfferCommitment
from world.worship.constants import RiteTier
from world.worship.models import (
    BeingFacet,
    BeingResonance,
    Pledge,
    RequestedItem,
    WorshippedBeing,
    WorshipRite,
)


class BeingResonanceForm(forms.ModelForm):
    class Meta:
        model = BeingResonance
        fields = ["resonance", "tier"]


class BeingFacetForm(forms.ModelForm):
    """One favored facet with its worn rates (#4520): the difficulty points a worn piece
    carrying it eases an invocation by, and the percent it adds to the earning rate, each
    per meaning point of the piece."""

    class Meta:
        model = BeingFacet
        fields = ["facet", "invocation_ease_points", "earning_bonus_percent"]
        widgets = {
            "invocation_ease_points": forms.NumberInput(attrs={"min": 0, "style": "width: 6em"}),
            "earning_bonus_percent": forms.NumberInput(attrs={"min": 0, "style": "width: 6em"}),
        }


class PledgeForm(forms.ModelForm):
    """One pledge type. The closing rite picker lists only the being's own tier 1 and
    2 rites, since a tier 3 rite is a ceremony and cannot close a pledge."""

    class Meta:
        model = Pledge
        fields = [
            "name",
            "description",
            "favor_target",
            "span_weeks",
            "closing_rite",
            "pact_offer",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "vTextField", "size": 60}),
            "description": forms.Textarea(attrs={"rows": 3, "cols": 60}),
        }
        help_texts = {
            "favor_target": "Favor to earn with the being after pledging.",
            "span_weeks": "Game weeks the character has to earn it and close the pledge.",
            "closing_rite": "Lists only this being's own tier 1 and 2 rites.",
            "pact_offer": (
                "Optional. The holder may choose to accept it when she performs the closing "
                "rite; it is signed if the rite resolves the pledge at Success or better. "
                "Refused with a reason if she already holds a pact with this being."
            ),
        }
        labels = {"pact_offer": "Pact offered at the close"}


class _PledgeFormSet(BaseInlineFormSet):
    """Limits every row's closing rite picker (the empty template row too) to the
    being's own tier 1 and 2 rites, and its pact offer picker to the being's own
    offers (#4341)."""

    def add_fields(self, form, index) -> None:
        super().add_fields(form, index)
        form.fields["closing_rite"].queryset = WorshipRite.objects.filter(
            being=self.instance, kind__tier__in=[RiteTier.DEVOTIONAL, RiteTier.DEMANDING]
        ).select_related("kind")
        form.fields["pact_offer"].queryset = PactOffer.objects.filter(being=self.instance)


BeingFacetFormSet = inlineformset_factory(
    WorshippedBeing, BeingFacet, form=BeingFacetForm, extra=0, can_delete=True
)
BeingResonanceFormSet = inlineformset_factory(
    WorshippedBeing, BeingResonance, form=BeingResonanceForm, extra=0, can_delete=True
)
PledgeFormSet = inlineformset_factory(
    WorshippedBeing,
    Pledge,
    form=PledgeForm,
    formset=_PledgeFormSet,
    extra=0,
    can_delete=True,
)


_PLEDGE_PREFIX = "pledge"
_RITE_PREFIX = "rite"


def target_choices(being: WorshippedBeing) -> list[tuple[str, str]]:
    """What a request can belong to: one of the being's saved pledges or rites, as
    ``"pledge:<pk>"`` / ``"rite:<pk>"`` (a new pledge is saved before it can ask for anything).
    Only tier 1 and 2 rites can ask: a tier 3 rite is a ceremony, whose offerings feed the pool
    and the officiant's devotion instead of easing a roll."""
    choices = [
        (f"{_PLEDGE_PREFIX}:{pledge.pk}", f"Pledge: {pledge.name}")
        for pledge in Pledge.objects.filter(being=being).order_by("name")
    ]
    choices.extend(
        (f"{_RITE_PREFIX}:{rite.pk}", f"Rite: {rite.name}")
        for rite in WorshipRite.objects.filter(
            being=being, kind__tier__in=[RiteTier.DEVOTIONAL, RiteTier.DEMANDING]
        ).order_by("name")
    )
    return choices


class RequestedItemForm(forms.ModelForm):
    """One item a pledge or rite asks for (#4530): exactly one of a template or a facet, a
    quantity, the points each gives and a hint line. ``target`` picks the pledge or rite
    the row belongs to. A template above the value limit is refused (requests are cheap)."""

    target = forms.ChoiceField(label="For", widget=forms.Select(attrs={"style": "max-width: 14em"}))

    class Meta:
        model = RequestedItem
        fields = ["item_template", "facet", "quantity", "points", "hint"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1, "style": "width: 4em"}),
            "points": forms.NumberInput(attrs={"min": 1, "style": "width: 4em"}),
            "hint": forms.TextInput(attrs={"style": "width: 8em"}),
            "item_template": forms.Select(attrs={"style": "max-width: 17em"}),
            "facet": forms.Select(attrs={"style": "max-width: 7em"}),
        }

    def __init__(self, *args, target_choices_for: list[tuple[str, str]], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The value beside each name is the cheap-items cue: above the limit is refused.
        self.fields["item_template"].label_from_instance = lambda t: f"{t.name} (value {t.value})"
        self.fields["target"].choices = target_choices_for
        instance = self.instance
        if instance.pk is not None:
            self.initial["target"] = (
                f"{_PLEDGE_PREFIX}:{instance.pledge_id}"
                if instance.pledge_id is not None
                else f"{_RITE_PREFIX}:{instance.rite_id}"
            )

    def clean(self) -> dict:
        """Point the row at the chosen pledge or rite before the model validates it."""
        cleaned = super().clean()
        kind, _, pk = (cleaned.get("target") or "").partition(":")
        self.instance.pledge = (
            Pledge.objects.filter(pk=pk).first() if kind == _PLEDGE_PREFIX else None
        )
        self.instance.rite = (
            WorshipRite.objects.filter(pk=pk).first() if kind == _RITE_PREFIX else None
        )
        return cleaned


class _RequestedItemFormSet(BaseModelFormSet):
    def __init__(self, *args, being: WorshippedBeing, **kwargs) -> None:
        self._target_choices = target_choices(being)
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict:
        kwargs = super().get_form_kwargs(index)
        kwargs["target_choices_for"] = self._target_choices
        return kwargs


RequestedItemFormSet = modelformset_factory(
    RequestedItem,
    form=RequestedItemForm,
    formset=_RequestedItemFormSet,
    extra=0,
    can_delete=True,
)


class PactOfferForm(forms.ModelForm):
    """One pact offer the being makes (#4341). The condition is authored in the condition
    admin; the page links to it."""

    class Meta:
        model = PactOffer
        fields = [
            "name",
            "offer_text",
            "period_weeks",
            "condition",
            "severity_per_miss",
            "closing_text",
            "onlooker_line",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "vTextField", "size": 60}),
            "offer_text": forms.Textarea(attrs={"rows": 3, "cols": 60}),
            "closing_text": forms.Textarea(attrs={"rows": 2, "cols": 60}),
            "onlooker_line": forms.TextInput(attrs={"class": "vTextField", "size": 60}),
            "period_weeks": forms.NumberInput(attrs={"min": 1, "style": "width: 5em"}),
            "severity_per_miss": forms.NumberInput(attrs={"min": 1, "style": "width: 5em"}),
        }
        labels = {
            "period_weeks": "Period (game weeks)",
            "severity_per_miss": "Severity per missed period",
        }
        help_texts = {
            "name": "Unique per being.",
            "offer_text": "",
            "period_weeks": "",
            "condition": (
                "First stage: the benefit. Later stages: the cost. Last stage: breach, and "
                "its settle pool fires if written, against the holder only. Stages should "
                "advance at their threshold; the pact rolls the resist check itself."
            ),
            "severity_per_miss": (
                "A period with nothing earned adds this much; a shortfall adds its share. "
                "A met period removes this much, up to twice it for earning double."
            ),
            "closing_text": "",
            "onlooker_line": (
                "Optional. One room line when the pact ends. Never states the reason."
            ),
            "is_active": "",
        }


class _PactOfferFormSet(BaseInlineFormSet):
    """Refuses to delete an offer someone has signed: the signed pact keeps it as its record."""

    def clean(self) -> None:
        super().clean()
        # Names come from the database: a deleted form has already written its posted
        # values onto the shared cached instance.
        signed = list(
            PactOffer.objects.filter(
                pk__in=[form.instance.pk for form in self.deleted_forms if form.instance.pk],
                signed__isnull=False,
            )
            .distinct()
            .order_by("name")
            .values_list("name", flat=True)
        )
        if signed:
            msg = (
                f"Cannot delete {', '.join(signed)}: characters have signed it. "
                "Untick Active instead, so it is no longer offered."
            )
            raise ValidationError(msg)


PactOfferFormSet = inlineformset_factory(
    WorshippedBeing,
    PactOffer,
    form=PactOfferForm,
    formset=_PactOfferFormSet,
    extra=0,
    can_delete=True,
)

#: The commitment kinds as the builder names them.
_COMMITMENT_KIND_CHOICES = [
    (CharacterPactCommitmentKind.FAVOR_EARNED, "Favor earned per period"),
    (CharacterPactCommitmentKind.CUSTOM, "Custom (recorded prose)"),
]


class PactOfferCommitmentForm(forms.ModelForm):
    """One commitment of one of the being's saved offers (#4341). Every commitment is
    owed by the holder in this version, so the form has no choice for it."""

    class Meta:
        model = PactOfferCommitment
        fields = ["offer", "kind", "amount", "notes"]
        widgets = {
            "offer": forms.Select(attrs={"style": "max-width: 12em"}),
            "amount": forms.NumberInput(attrs={"min": 0, "style": "width: 5em"}),
            "notes": forms.TextInput(attrs={"style": "width: 16em"}),
        }

    def __init__(self, *args, offers, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["offer"].queryset = offers
        self.fields["offer"].label_from_instance = lambda offer: offer.name
        self.fields["kind"].choices = _COMMITMENT_KIND_CHOICES


class _PactCommitmentFormSet(BaseModelFormSet):
    """Every commitment of the being's saved offers. A commitment with graded periods
    cannot be deleted: its periods keep it as their record."""

    def __init__(self, *args, being: WorshippedBeing, **kwargs) -> None:
        self._offers = PactOffer.objects.filter(being=being)
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index: int | None) -> dict:
        kwargs = super().get_form_kwargs(index)
        kwargs["offers"] = self._offers
        return kwargs

    def clean(self) -> None:
        super().clean()
        # Read from the database: a deleted form has already written its posted values
        # onto the shared cached instance.
        kept = (
            PactOfferCommitment.objects.filter(
                pk__in=[form.instance.pk for form in self.deleted_forms if form.instance.pk],
                periods__isnull=False,
            )
            .distinct()
            .order_by("offer__name", "pk")
            .values_list("offer__name", flat=True)
        )
        if kept:
            msg = (
                f"Cannot delete a commitment of {', '.join(dict.fromkeys(kept))}: holders "
                "have periods graded against it. Untick the offer's Active instead."
            )
            raise ValidationError(msg)


PactOfferCommitmentFormSet = modelformset_factory(
    PactOfferCommitment,
    form=PactOfferCommitmentForm,
    formset=_PactCommitmentFormSet,
    extra=0,
    can_delete=True,
)
