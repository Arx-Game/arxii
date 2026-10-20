"""What a mission option's routes already hold, read for the Trial builder (#4513).

A trial has no model of its own: it is a mission option whose routes carry consequences that
make an entry known, train a technique and cost something. This module reads those saved
rows back into the shapes the page edits, one :class:`TierState` per outcome tier.

The builder owns four effect slots per tier (the codex effect, the training effect, the
cost and the cosmetic reward). Any other effect on the same consequence is left alone and
only listed. A consequence that something else also uses (another route, a pool, a
challenge) is shown read-only: editing it here would change those other places too.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from django.db.models import Count, Model

from world.checks.constants import EffectTarget, EffectType
from world.checks.models import Consequence, ConsequenceEffect
from world.checks.trial_rules import is_cost_effect
from world.missions.models import MissionOption, MissionOptionRoute
from world.traits.models import CheckOutcome

#: The execution order the builder gives each slot it owns: the codex effect first, so the
#: training that follows runs after the entry is known (slice 1's rule), then cost, reward.
SLOT_ORDER = {"codex": 0, "training": 1, "cost": 2, "reward": 3}
#: Effects the builder does not own start after its own, in their existing relative order.
FIRST_OTHER_ORDER = 10


def tiers() -> list[CheckOutcome]:
    """Every outcome tier, best first, as the page's fieldsets."""
    return list(CheckOutcome.objects.order_by("-success_level", "name"))


@dataclass
class TierState:
    """One outcome tier of the option: the saved route, consequence and owned effects."""

    tier: CheckOutcome
    route: MissionOptionRoute | None = None
    consequence: Consequence | None = None
    codex: ConsequenceEffect | None = None
    training: ConsequenceEffect | None = None
    cost: ConsequenceEffect | None = None
    reward: ConsequenceEffect | None = None
    others: list[ConsequenceEffect] = field(default_factory=list)
    shared_with: list[str] = field(default_factory=list)

    @property
    def shared(self) -> bool:
        return bool(self.shared_with)

    @property
    def owned(self) -> list[ConsequenceEffect]:
        return [e for e in (self.codex, self.training, self.cost, self.reward) if e is not None]


def _reverse_relations(model: type[Model], skip: tuple[type[Model], ...]) -> list:
    """The reverse foreign-key relations of ``model``, hidden ones included.

    ``include_hidden``: a relation declared ``related_name="+"`` (a mission route's
    consequence) is hidden from ``related_objects`` yet is exactly a user of the row.
    """
    return [
        rel
        for rel in model._meta.get_fields(include_hidden=True)  # noqa: SLF001
        if rel.auto_created
        and not rel.concrete
        and (rel.one_to_many or rel.one_to_one)
        and rel.related_model not in skip
    ]


def referencing_rows(
    objs: list[Model], *, skip: tuple[type[Model], ...] = (), exclude: list[Model] | None = None
) -> dict[int, list[str]]:
    """Per object pk: counts of the rows that point at it through a foreign key, readable.

    One grouped query per reverse relation of the model, however many objects are asked about
    (a constant, not a query per object). Read off the model's own reverse relations, so a user
    added later is caught without a hand-kept list. ``skip`` leaves out model classes that are
    part of the object (a consequence's own effects); ``exclude`` are rows to ignore (the routes
    being edited).
    """
    found: dict[int, list[str]] = {obj.pk: [] for obj in objs}
    if not objs:
        return found
    excluded = {(type(row), row.pk) for row in exclude or []}
    for rel in _reverse_relations(type(objs[0]), skip):
        model: type[Model] = rel.related_model
        rows = model._default_manager.filter(  # noqa: SLF001
            **{f"{rel.field.name}__in": [obj.pk for obj in objs]}
        )
        skipped = [pk for kind, pk in excluded if kind is model]
        if skipped:
            rows = rows.exclude(pk__in=skipped)
        for row in rows.values(rel.field.attname).annotate(n=Count("pk")):
            found[row[rel.field.attname]].append(
                f"{row['n']} {model._meta.verbose_name}"  # noqa: SLF001
            )
    return found


def _classify(state: TierState, effects: list[ConsequenceEffect]) -> None:
    """Put each effect in the first free slot it fits; the rest are 'others'."""
    for effect in effects:
        kind = effect.effect_type
        if kind == EffectType.GRANT_CODEX and state.codex is None:
            state.codex = effect
        elif kind == EffectType.TECHNIQUE_TRAINING and state.training is None:
            state.training = effect
        elif (
            kind == EffectType.MAGICAL_SCARS
            and effect.target == EffectTarget.SELF
            and effect.scar_is_cosmetic
            and state.reward is None
        ):
            state.reward = effect
        elif is_cost_effect(effect) and state.cost is None:
            state.cost = effect
        else:
            state.others.append(effect)


def load(option: MissionOption) -> list[TierState]:
    """The page's tiers with whatever the option's routes already hold."""
    routes: dict[int, MissionOptionRoute] = {}
    for route in option.routes.select_related("consequence", "target_node").order_by("pk"):
        if route.outcome_tier_id is not None:
            routes.setdefault(route.outcome_tier_id, route)
    consequences = [r.consequence for r in routes.values() if r.consequence_id is not None]
    effects_by_consequence: dict[int, list[ConsequenceEffect]] = {c.pk: [] for c in consequences}
    for effect in (
        ConsequenceEffect.objects.filter(consequence__in=consequences)
        .select_related("codex_entry", "technique", "condition_template")
        .order_by("execution_order", "pk")
    ):
        effects_by_consequence[effect.consequence_id].append(effect)
    shared = referencing_rows(
        consequences, skip=(ConsequenceEffect,), exclude=list(routes.values())
    )
    own_uses = Counter(c.pk for c in (r.consequence for r in routes.values()) if c is not None)
    states = []
    for tier in tiers():
        state = TierState(tier=tier, route=routes.get(tier.pk))
        route = state.route
        if route is not None and route.consequence_id is not None:
            state.consequence = route.consequence
            state.shared_with = list(shared[route.consequence_id])
            if own_uses[route.consequence_id] > 1:
                state.shared_with.append("another tier of this option")
            _classify(state, effects_by_consequence[route.consequence_id])
        states.append(state)
    return states


@dataclass(frozen=True)
class TrialHeader:
    """The trial-wide choices read back from the saved effects."""

    codex_entry_id: int | None
    technique_id: int | None
    meter_size: int | None


def header_from(states: list[TierState]) -> TrialHeader:
    """The entry, technique and meter size the saved effects share (best tier first)."""
    entry_id = technique_id = meter = None
    for state in states:
        if state.codex is not None and state.codex.grants_known and entry_id is None:
            entry_id = state.codex.codex_entry_id
        if state.training is not None:
            technique_id = technique_id or state.training.technique_id
            meter = meter or state.training.training_meter_size
    if entry_id is None:
        entry_id = next((s.codex.codex_entry_id for s in states if s.codex is not None), None)
    return TrialHeader(codex_entry_id=entry_id, technique_id=technique_id, meter_size=meter)
