"""The rows the Trial builder page proposes, built unsaved and checked by slice 1's rules.

``build`` turns the posted forms into one :class:`TierProposal` per filled-in tier: an unsaved
``Consequence`` with its unsaved ``ConsequenceEffect`` rows. Every rule that refuses a trial
row is slice 1's: ``ConsequenceEffect.clean`` (field and tier rules, through
``checks.trial_rules.effect_trial_errors``), ``Consequence.clean`` (a reason for a free row) and
``Consequence.trial_rule_errors`` (the cost rule over the whole set). This module only asks
them; the page's live check and the save both come through here, so there is one copy of the
rules and the save refuses exactly what the rail showed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError

from web.admin.trial_builder.forms import (
    CODEX_KNOWN,
    CODEX_NONE,
    COST_CONDITION,
    COST_NONE,
    COST_SCAR,
    REWARD_COSMETIC,
    HeaderForm,
    TierForm,
)
from web.admin.trial_builder.state import SLOT_ORDER, TierState
from world.checks.constants import EffectType
from world.checks.models import Consequence, ConsequenceEffect
from world.missions.models import MissionOption, MissionOptionRoute

NO_TECHNIQUE_ERROR = "Pick the technique this trial trains (What it opens)."


@dataclass
class TierProposal:
    """One filled-in tier: its route fields, and its consequence and effects when it owns them."""

    form: TierForm
    state: TierState
    consequence: Consequence | None
    effects: list[ConsequenceEffect] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def tier(self):
        return self.form.tier


def _messages(error: ValidationError) -> list[str]:
    if hasattr(error, "message_dict"):
        return [m for messages in error.message_dict.values() for m in messages]
    return list(error.messages)


def _codex_effect(
    consequence: Consequence, data: dict[str, object], head: dict[str, object]
) -> ConsequenceEffect | None:
    mode = data.get("codex_mode") or CODEX_NONE
    if mode == CODEX_NONE:
        return None
    return ConsequenceEffect(
        consequence=consequence,
        effect_type=EffectType.GRANT_CODEX,
        execution_order=SLOT_ORDER["codex"],
        codex_entry=data.get("codex_entry") or head.get("codex_entry"),
        grants_known=mode == CODEX_KNOWN,
    )


def _training_effect(
    consequence: Consequence, data: dict[str, object], head: dict[str, object]
) -> ConsequenceEffect | None:
    if not (data.get("training_points") or data.get("grant_outright")):
        return None
    return ConsequenceEffect(
        consequence=consequence,
        effect_type=EffectType.TECHNIQUE_TRAINING,
        execution_order=SLOT_ORDER["training"],
        technique=head.get("technique"),
        training_points=None if data.get("grant_outright") else data.get("training_points"),
        training_meter_size=head.get("meter_size"),
        grants_technique_outright=bool(data.get("grant_outright")),
    )


def _cost_effect(consequence: Consequence, data: dict[str, object]) -> ConsequenceEffect | None:
    cost = data.get("cost_kind") or COST_NONE
    if cost == COST_NONE:
        return None
    return ConsequenceEffect(
        consequence=consequence,
        effect_type=EffectType.MAGICAL_SCARS if cost == COST_SCAR else EffectType.APPLY_CONDITION,
        execution_order=SLOT_ORDER["cost"],
        condition_template=data.get("cost_template") if cost == COST_CONDITION else None,
        condition_severity=data.get("cost_severity"),
    )


def _reward_effect(consequence: Consequence, data: dict[str, object]) -> ConsequenceEffect | None:
    if (data.get("reward_kind") or "") != REWARD_COSMETIC:
        return None
    return ConsequenceEffect(
        consequence=consequence,
        effect_type=EffectType.MAGICAL_SCARS,
        execution_order=SLOT_ORDER["reward"],
        condition_severity=data.get("reward_tier"),
        scar_is_cosmetic=True,
    )


def _effects(
    consequence: Consequence,
    data: dict[str, object],
    header: HeaderForm,
    errors: list[str],
) -> list[ConsequenceEffect]:
    head = header.cleaned_data
    training = _training_effect(consequence, data, head)
    if training is not None and head.get("technique") is None:
        errors.append(NO_TECHNIQUE_ERROR)
    slots = (
        _codex_effect(consequence, data, head),
        training,
        _cost_effect(consequence, data),
        _reward_effect(consequence, data),
    )
    return [effect for effect in slots if effect is not None]


def _input_errors(data: dict[str, object]) -> list[str]:
    """What the page itself needs that no model rule can say: a number beside a choice."""
    errors = []
    cost = data.get("cost_kind") or COST_NONE
    if cost != COST_NONE and not data.get("cost_severity"):
        errors.append("Give the cost's tier or severity.")
    if cost == COST_CONDITION and not data.get("cost_template"):
        errors.append("Pick the condition template for the staged condition.")
    if (data.get("reward_kind") or "") == REWARD_COSMETIC and not data.get("reward_tier"):
        errors.append("Give the cosmetic scar's tier.")
    return errors


def _model_errors(
    consequence: Consequence, effects: list[ConsequenceEffect], route: MissionOptionRoute
) -> list[str]:
    errors: list[str] = []
    for row in (route, consequence, *effects):
        try:
            row.clean()
        except ValidationError as error:
            errors.extend(_messages(error))
    errors.extend(consequence.trial_rule_errors(effects))
    return errors


def _unique(messages: list[str]) -> list[str]:
    return list(dict.fromkeys(messages))


def build(
    option: MissionOption, header: HeaderForm, tier_forms: list[TierForm]
) -> list[TierProposal]:
    """Proposals for every tier the author filled in (or that already has a route).

    Call after the forms validated. Each proposal carries the messages slice 1's rules give.
    A tier left blank with no saved route yields none.
    """
    proposals: list[TierProposal] = []
    for form in tier_forms:
        state = form.state
        data = form.cleaned_data
        if form.is_blank() and state.route is None:
            continue
        route = MissionOptionRoute(
            option=option,
            outcome_tier=form.tier,
            target_node=data.get("next_node"),
            outcome_text=data.get("outcome_text", ""),
        )
        if state.shared:
            proposals.append(
                TierProposal(
                    form=form,
                    state=state,
                    consequence=None,
                    errors=_model_errors_for_route(route),
                )
            )
            continue
        consequence = Consequence(
            outcome_tier=form.tier,
            label=data.get("label") or form.initial.get("label", ""),
            deliberately_free=bool(data.get("deliberately_free")),
            free_reason=(data.get("free_reason") or "").strip(),
        )
        errors = _input_errors(data)
        effects = _effects(consequence, data, header, errors)
        errors.extend(_model_errors(consequence, effects, route))
        proposals.append(
            TierProposal(
                form=form,
                state=state,
                consequence=consequence,
                effects=effects,
                errors=_unique(errors),
            )
        )
    return proposals


def _model_errors_for_route(route: MissionOptionRoute) -> list[str]:
    try:
        route.clean()
    except ValidationError as error:
        return _messages(error)
    return []
