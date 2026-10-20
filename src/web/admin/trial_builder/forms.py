"""Forms for the Trial builder (#4513): the trial's header and one form per outcome tier.

Plain forms, not model forms: a trial is spread over a route, a consequence and up to four
effects per tier, and validating a model form writes posted values onto the identity-mapped
instance every other reader shares. The rows the page proposes are built unsaved in
``proposal.py`` and checked by slice 1's own rules.
"""

from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect
from django.db.models import QuerySet

from web.admin.trial_builder.state import TierState, TrialHeader
from world.checks.constants import (
    CRITICAL_SUCCESS_TIER_MIN_LEVEL,
    FAILURE_TIER_MAX_LEVEL,
    SUCCESS_TIER_MIN_LEVEL,
    EffectType,
)
from world.checks.models import ConsequenceEffect
from world.codex.models import CodexEntry
from world.conditions.models import ConditionTemplate
from world.magic.models import Technique
from world.missions.models import MissionNode
from world.traits.models import CheckOutcome

CODEX_NONE = "none"
CODEX_LEAD = "lead"
CODEX_KNOWN = "known"
CODEX_CHOICES = (
    (CODEX_NONE, "None"),
    (CODEX_LEAD, "Uncovered lead"),
    (CODEX_KNOWN, "Grants as known"),
)
COST_NONE = "none"
COST_SCAR = "scar"
COST_CONDITION = "condition"
COST_CHOICES = (
    (COST_NONE, "None"),
    (COST_SCAR, "Mage Scars"),
    (COST_CONDITION, "Staged condition"),
)
REWARD_NONE = "none"
REWARD_COSMETIC = "cosmetic"
REWARD_CHOICES = ((REWARD_NONE, "None"), (REWARD_COSMETIC, "Cosmetic Mage Scar"))


def _autocomplete(field_name: str) -> AutocompleteSelect:
    return AutocompleteSelect(ConsequenceEffect._meta.get_field(field_name), admin.site)  # noqa: SLF001


def _number(**attrs: object) -> forms.NumberInput:
    return forms.NumberInput(attrs={"class": "vIntegerField", "min": 1, **attrs})


class HeaderForm(forms.Form):
    """What the trial opens: the entry, the technique it trains and the meter's size."""

    codex_entry = forms.ModelChoiceField(
        queryset=CodexEntry.objects.all(),
        required=False,
        label="Codex entry",
        widget=_autocomplete("codex_entry"),
    )
    technique = forms.ModelChoiceField(
        queryset=Technique.objects.all(),
        required=False,
        label="Technique trained",
        widget=_autocomplete("technique"),
        help_text=(
            "One technique per trial. An ultimate is refused: only Audere reaches one. "
            "Effects save in the order codex entry, training, cost, reward."
        ),
    )
    meter_size = forms.IntegerField(
        min_value=1,
        required=False,
        label="Meter size",
        widget=_number(),
        help_text=(
            "Authored per trial; used when the trial starts the meter for a character who "
            "has none. Written to every training effect this page saves."
        ),
    )

    def __init__(self, *args: object, initial_header: TrialHeader | None = None, **kwargs: object):
        super().__init__(*args, **kwargs)
        if initial_header is not None:
            self.initial = {
                "codex_entry": initial_header.codex_entry_id,
                "technique": initial_header.technique_id,
                "meter_size": initial_header.meter_size,
            }


class TierForm(forms.Form):
    """One outcome tier's route, consequence and the four effect slots the page owns."""

    next_node = forms.ModelChoiceField(
        queryset=MissionNode.objects.none(),
        required=False,
        empty_label="End the mission",
        label="Next node",
    )
    label = forms.CharField(
        max_length=200,
        required=False,
        label="Consequence label",
        widget=forms.TextInput(attrs={"class": "vTextField", "size": 60}),
    )
    outcome_text = forms.CharField(
        required=False,
        label="Outcome text",
        widget=forms.Textarea(attrs={"rows": 6, "class": "vLargeTextField"}),
    )
    codex_mode = forms.ChoiceField(choices=CODEX_CHOICES, required=False, label="Codex entry")
    codex_entry = forms.ModelChoiceField(
        queryset=CodexEntry.objects.all(),
        required=False,
        label="Entry for this tier",
        widget=_autocomplete("codex_entry"),
        help_text="Blank uses the trial's entry above.",
    )
    training_points = forms.IntegerField(
        min_value=1, required=False, label="Points", widget=_number()
    )
    grant_outright = forms.BooleanField(required=False, label="Grant outright")
    cost_kind = forms.ChoiceField(choices=COST_CHOICES, required=False, label="Cost")
    cost_template = forms.ModelChoiceField(
        queryset=ConditionTemplate.objects.all(),
        required=False,
        label="Condition template",
        widget=_autocomplete("condition_template"),
    )
    cost_severity = forms.IntegerField(
        min_value=1, required=False, label="Tier / severity", widget=_number()
    )
    reward_kind = forms.ChoiceField(choices=REWARD_CHOICES, required=False, label="Reward")
    reward_tier = forms.IntegerField(min_value=1, required=False, label="Tier", widget=_number())
    deliberately_free = forms.BooleanField(required=False, label="Free")
    free_reason = forms.CharField(
        required=False,
        label="Reason",
        widget=forms.TextInput(attrs={"class": "vTextField", "placeholder": "Reason"}),
    )

    def __init__(
        self,
        *args: object,
        state: TierState,
        nodes: QuerySet[MissionNode],
        default_label: str,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.state = state
        self.tier: CheckOutcome = state.tier
        self.fields["next_node"].queryset = nodes
        if not self.can_know:
            self.fields["codex_mode"].choices = [c for c in CODEX_CHOICES if c[0] != CODEX_KNOWN]
        self.initial = self._initial_from(state, default_label)

    @property
    def level(self) -> int:
        return self.tier.success_level

    @property
    def can_reward(self) -> bool:
        return self.level >= SUCCESS_TIER_MIN_LEVEL

    @property
    def can_train(self) -> bool:
        """Failures train nothing; the model refuses it (slice 1) and the page hides it."""
        return self.level > FAILURE_TIER_MAX_LEVEL

    @property
    def can_outright(self) -> bool:
        return self.level >= CRITICAL_SUCCESS_TIER_MIN_LEVEL

    @property
    def can_know(self) -> bool:
        """'Grants as known' is offered from Partial Success up; Failure tiers get a lead."""
        return self.level > FAILURE_TIER_MAX_LEVEL

    @staticmethod
    def _initial_from(state: TierState, default_label: str) -> dict[str, object]:
        route, consequence = state.route, state.consequence
        initial: dict[str, object] = {
            "next_node": route.target_node_id if route else None,
            "outcome_text": route.outcome_text if route else "",
            "label": consequence.label if consequence else default_label,
            "codex_mode": CODEX_NONE,
            "cost_kind": COST_NONE,
            "reward_kind": REWARD_NONE,
            "deliberately_free": bool(consequence and consequence.deliberately_free),
            "free_reason": consequence.free_reason if consequence else "",
        }
        if state.codex is not None:
            initial["codex_mode"] = CODEX_KNOWN if state.codex.grants_known else CODEX_LEAD
            initial["codex_entry"] = state.codex.codex_entry_id
        if state.training is not None:
            initial["training_points"] = state.training.training_points
            initial["grant_outright"] = state.training.grants_technique_outright
        if state.cost is not None:
            scar = state.cost.effect_type == EffectType.MAGICAL_SCARS
            initial["cost_kind"] = COST_SCAR if scar else COST_CONDITION
            initial["cost_template"] = state.cost.condition_template_id
            initial["cost_severity"] = state.cost.condition_severity
        if state.reward is not None:
            initial["reward_kind"] = REWARD_COSMETIC
            initial["reward_tier"] = state.reward.condition_severity
        return initial

    def is_blank(self) -> bool:
        """True when the author has filled in nothing for this tier."""
        data = self.cleaned_data
        return not any(
            (
                data.get("next_node"),
                data.get("outcome_text", "").strip(),
                data.get("codex_mode", CODEX_NONE) != CODEX_NONE,
                data.get("training_points"),
                data.get("grant_outright"),
                data.get("cost_kind", COST_NONE) != COST_NONE,
                data.get("reward_kind", REWARD_NONE) != REWARD_NONE,
                data.get("deliberately_free"),
            )
        )
