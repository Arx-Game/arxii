"""Forms for the Soulfray Stage Builder (#4089): one stage, its penalty, pool, rows, effects.

The consequence table is a plain formset over ``TableRow``s, not a model formset:
a row is either this stage's own (a ``ConsequencePoolEntry`` on the stage pool)
or shared from the parent pool, and the two save differently (``save.py``). The
source of a row is always re-derived from the database, never read from the POST.

Effects ride two kinds of formset. A row the page was rendered with edits its
consequence's effects under prefix ``e<consequence pk>``. A row added on the page
(by "+ Add a consequence" or "Copy rows from") has no consequence yet, so its
effects post under prefix ``new<row form index>`` against an unsaved
``Consequence``; the save creates the consequence, points the formset at it and
saves the effects in the same transaction (spec story 5: one Save).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelect, AutocompleteSelectMultiple
from django.core.exceptions import ValidationError
from django.forms import (
    BaseFormSet,
    BaseInlineFormSet,
    Media,
    formset_factory,
    inlineformset_factory,
)

from actions.models import ConsequencePool, ConsequencePoolEntry
from actions.types import _entry_to_weighted
from world.checks.constants import EffectType
from world.checks.models import Consequence, ConsequenceEffect
from world.conditions.models import ConditionCheckModifier, ConditionStage, ConditionStageOnEntry
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.models import SoulfrayConfig
from world.traits.models import CheckOutcome

SPIN_THE_WHEEL_HELP = (
    "If any option for a roll result is ticked or can kill, a roll with that result spins "
    "the outcome wheel instead of just showing the result. The wheel shows every option for "
    "that result, whichever one it lands on."
)

#: Prefix of a new row's effects formset; the row's form index follows it ("new3").
NEW_ROW_EFFECTS_PREFIX = "new"


class StageForm(forms.ModelForm):
    """The stage's own fields. "More" (multiplier, rounds to next) renders collapsed."""

    class Meta:
        model = ConditionStage
        fields = [
            "name",
            "description",
            "severity_threshold",
            "advancement_resist_failure_kind",
            "resist_check_type",
            "resist_difficulty",
            "properties",
            "severity_multiplier",
            "rounds_to_next",
        ]
        labels = {
            "description": "Warning text",
            "severity_threshold": "Reached at severity",
            "advancement_resist_failure_kind": "On reaching it",
            "resist_check_type": "Resist check",
            "resist_difficulty": "difficulty",
            "properties": "Tags while here",
            "severity_multiplier": "Severity multiplier",
            "rounds_to_next": "Rounds to next",
        }
        help_texts = {
            "description": "Shown to the player at the safety checkpoint before a cast.",
            "severity_threshold": (
                "A caster whose Soulfray severity reaches this number moves to this stage."
            ),
            "advancement_resist_failure_kind": (
                "Or: severity piles up over the threshold and each new gain rolls the resist "
                "check below."
            ),
            "resist_check_type": "Only used when the stage holds overflow.",
            "properties": "Properties the caster carries while at this stage.",
            "rounds_to_next": "Blank: Soulfray moves on severity, not on time.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "resist_check_type": AutocompleteSelect(
                ConditionStage._meta.get_field("resist_check_type"),  # noqa: SLF001
                admin.site,
            ),
            "properties": AutocompleteSelectMultiple(
                ConditionStage._meta.get_field("properties"),  # noqa: SLF001
                admin.site,
            ),
        }


OnEntryFormSet = inlineformset_factory(
    ConditionStage,
    ConditionStageOnEntry,
    fields=["condition", "severity"],
    extra=1,
    can_delete=True,
    widgets={
        "condition": AutocompleteSelect(
            ConditionStageOnEntry._meta.get_field("condition"),  # noqa: SLF001
            admin.site,
        )
    },
)


class PenaltyForm(forms.Form):
    """The ``ConditionCheckModifier`` on ``SoulfrayConfig.resilience_check_type`` for this stage."""

    modifier_value = forms.IntegerField(
        required=False,
        label="Stage penalty",
        help_text=(
            "Added to the resilience roll while here. Negative makes it harder. Base "
            "difficulty comes from Soulfray config."
        ),
    )


class PoolForm(forms.Form):
    """Pick the stage's pool (or name a new one) and its shared parent."""

    pool = forms.ModelChoiceField(
        queryset=ConsequencePool.objects.order_by("name"),
        required=False,
        empty_label="New pool",
        label="Pool",
    )
    new_name = forms.CharField(max_length=100, required=False, label="New pool name")
    parent = forms.ModelChoiceField(
        queryset=ConsequencePool.objects.filter(parent__isnull=True).order_by("name"),
        required=False,
        empty_label="no shared pool",
        label="inherits",
        error_messages={
            "invalid_choice": (
                "Pick a pool that does not itself inherit from another: inheritance is one "
                "level deep."
            )
        },
    )

    def __init__(self, *args: object, stage: ConditionStage | None = None, **kwargs: object):
        super().__init__(*args, **kwargs)
        self.stage = stage

    def _parents_another_stage(self, pool: ConsequencePool) -> bool:
        """Some other Soulfray stage's own pool inherits from ``pool``."""
        children = ConsequencePool.objects.filter(
            parent=pool, condition_stages__condition__name=SOULFRAY_CONDITION_NAME
        )
        if self.stage is not None:
            children = children.exclude(condition_stages__pk=self.stage.pk)
        return children.exists()

    def clean(self) -> dict[str, object]:
        """Pool inheritance is one level deep (``consequence_pools.py:70``), and a
        stage's own pool is never another stage's shared parent (spec C.6), from
        either side: the parent picked is no stage's own pool, and the pool picked
        is no other stage's parent."""
        cleaned = super().clean()
        pool = cleaned.get("pool")
        parent = cleaned.get("parent")
        if pool is not None and self._parents_another_stage(pool):
            self.add_error(
                "pool",
                f"{pool.name} is another Soulfray stage's shared parent, so it cannot be this "
                "stage's own pool. Pick or create a pool of this stage's own.",
            )
        if parent is not None:
            if pool is not None and parent.pk == pool.pk:
                self.add_error("parent", "A pool cannot inherit from itself.")
            elif parent.condition_stages.filter(condition__name=SOULFRAY_CONDITION_NAME).exists():
                self.add_error(
                    "parent",
                    f"{parent.name} is a Soulfray stage's own pool, so it cannot be another "
                    "stage's shared parent. Pick or create a shared pool that no stage uses.",
                )
            elif pool is not None and pool.children.exists():
                self.add_error(
                    "pool",
                    f"{pool.name} is already a parent pool, so it cannot inherit from another: "
                    "inheritance is one level deep.",
                )
        new_name = (cleaned.get("new_name") or "").strip()
        if pool is None and new_name and ConsequencePool.objects.filter(name=new_name).exists():
            self.add_error(
                "new_name", "A pool with this name exists. Pick it above or choose another name."
            )
        return cleaned


class ConsequenceRowForm(forms.Form):
    """One row of "What the roll can draw"."""

    consequence = forms.IntegerField(required=False, widget=forms.HiddenInput)
    copy_of = forms.IntegerField(required=False, widget=forms.HiddenInput)
    outcome_tier = forms.ModelChoiceField(
        queryset=CheckOutcome.objects.order_by("success_level"), label="Roll result"
    )
    label = forms.CharField(max_length=200, label="What happens")
    weight = forms.IntegerField(min_value=0, initial=1, label="Weight")
    character_loss = forms.BooleanField(required=False, label="Can kill")
    theater = forms.BooleanField(
        required=False, label="Spin the wheel", help_text=SPIN_THE_WHEEL_HELP
    )
    remove = forms.BooleanField(required=False, label="Remove")

    def __init__(self, *args: object, choices: BuilderChoices | None = None, **kwargs: object):
        super().__init__(*args, **kwargs)
        if choices is not None:
            self.fields["outcome_tier"].choices = choices.outcome_tier


COPY_SOURCE_GONE_ERROR = "A copied row no longer exists on any Soulfray stage."
TABLE_CHANGED_ERROR = (
    "This stage's consequence table changed after the page was loaded, so the rows on this "
    "page no longer line up with it. Nothing was saved. Reload the page and make the edit again."
)


class BaseConsequenceRowFormSet(BaseFormSet):
    """Knows the consequence ids of the table the page was rendered with, in row order.

    The save matches row form ``i`` to ``table[i]`` by index, so a row below
    ``len(table)`` must post exactly ``table[i]``'s consequence and a row past it
    must post none. Anything else means the table moved between the GET and this
    POST (a row added to or dropped from the pool or its parent), and the save
    is refused rather than writing one row's edit onto another.
    """

    def __init__(self, *args: object, table_ids: Sequence[int] = (), **kwargs: object):
        super().__init__(*args, **kwargs)
        self.table_ids = tuple(table_ids)

    def clean(self) -> None:
        """Rows line up with the table; a copied row still exists on a Soulfray stage."""
        super().clean()
        if len(self.forms) < len(self.table_ids):
            raise ValidationError(TABLE_CHANGED_ERROR)
        for index, form in enumerate(self.forms):
            data = form.cleaned_data
            cid = data.get("consequence")
            expected = self.table_ids[index] if index < len(self.table_ids) else None
            if cid != expected:
                raise ValidationError(TABLE_CHANGED_ERROR)
            source = data.get("copy_of")
            if (
                cid is None
                and source
                and not ConsequencePoolEntry.objects.filter(
                    consequence_id=source,
                    pool__condition_stages__condition__name=SOULFRAY_CONDITION_NAME,
                ).exists()
            ):
                raise ValidationError(COPY_SOURCE_GONE_ERROR)


ConsequenceRowFormSet = formset_factory(
    ConsequenceRowForm, formset=BaseConsequenceRowFormSet, extra=0
)

#: Effect types this page edits. Each one's required fields
#: (``ConsequenceEffect._REQUIRED_FIELDS``) are all on ``EffectForm``, so the
#: model's own ``clean()`` can never name a field the form lacks. A consequence's
#: other effects are listed read-only with a link to the stock Consequence admin.
BUILDER_EFFECT_TYPES = (
    EffectType.DEAL_DAMAGE,
    EffectType.APPLY_CONDITION,
    EffectType.REMOVE_CONDITION,
    EffectType.MAGICAL_SCARS,
    EffectType.ADD_PROPERTY,
    EffectType.REMOVE_PROPERTY,
    EffectType.GRANT_DISTINCTION,
)


class EffectForm(forms.ModelForm):
    class Meta:
        model = ConsequenceEffect
        fields = [
            "effect_type",
            "target",
            "execution_order",
            "damage_amount",
            "damage_type",
            "condition_template",
            "condition_severity",
            "property",
            "property_value",
            "distinction",
            "distinction_rank",
        ]
        widgets = {
            "condition_template": AutocompleteSelect(
                ConsequenceEffect._meta.get_field("condition_template"),  # noqa: SLF001
                admin.site,
            ),
            "property": AutocompleteSelect(
                ConsequenceEffect._meta.get_field("property"),  # noqa: SLF001
                admin.site,
            ),
            "distinction": AutocompleteSelect(
                ConsequenceEffect._meta.get_field("distinction"),  # noqa: SLF001
                admin.site,
            ),
        }

    def __init__(
        self, *args: object, choices: BuilderChoices | None = None, **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["effect_type"].choices = [("", "---------")] + [
            (value, label) for value, label in EffectType.choices if value in BUILDER_EFFECT_TYPES
        ]
        if choices is not None:
            self.fields["damage_type"].choices = choices.damage_type


@dataclass(frozen=True)
class BuilderChoices:
    """The page's model-backed select options, evaluated once per request.

    A ``ModelChoiceField`` re-runs its queryset every time a form renders it, so
    without this every consequence row (its "Roll result") and every effect form
    (its damage type) cost a query each. Setting a field's ``choices`` to these
    lists only changes rendering; a bound field still validates against its
    queryset.
    """

    outcome_tier: list[tuple[object, str]]
    damage_type: list[tuple[object, str]]

    @classmethod
    def load(cls) -> BuilderChoices:
        return cls(
            outcome_tier=list(ConsequenceRowForm.base_fields["outcome_tier"].choices),
            damage_type=list(EffectForm.base_fields["damage_type"].choices),
        )


class BaseEffectFormSet(BaseInlineFormSet):
    """An inline formset that can serve its rows from an already-fetched list.

    ``prefetched`` stands in for the formset's queryset everywhere Django reads
    it (form count, indexing, the pk lookup a bound form uses), so a page of N
    consequences fetches their effects in one query rather than one per row.
    The list must hold exactly the rows the queryset would: this consequence's
    effects of ``BUILDER_EFFECT_TYPES``, fetched in the same request.
    """

    def __init__(
        self, *args: object, prefetched: Sequence[ConsequenceEffect] | None = None, **kwargs: object
    ) -> None:
        self.prefetched = None if prefetched is None else list(prefetched)
        super().__init__(*args, **kwargs)

    def get_queryset(self) -> object:
        if self.prefetched is not None:
            return self.prefetched
        return super().get_queryset()


EffectFormSet = inlineformset_factory(
    Consequence,
    ConsequenceEffect,
    form=EffectForm,
    formset=BaseEffectFormSet,
    extra=0,
    can_delete=True,
)

_EFFECT_RELATIONS = ("condition_template", "property", "distinction", "damage_type")


def effects_by_consequence(consequence_ids: Sequence[int]) -> dict[int, list[ConsequenceEffect]]:
    """Every effect of these consequences, any type, in firing order. One query, or none."""
    grouped: dict[int, list[ConsequenceEffect]] = defaultdict(list)
    if not consequence_ids:
        return grouped
    for effect in (
        ConsequenceEffect.objects.filter(consequence_id__in=consequence_ids)
        .select_related(*_EFFECT_RELATIONS)
        .order_by("execution_order", "pk")
    ):
        grouped[effect.consequence_id].append(effect)
    return grouped


def effect_formset_for(
    consequence: Consequence,
    data: object = None,
    *,
    effects: Sequence[ConsequenceEffect] | None = None,
    choices: BuilderChoices | None = None,
) -> EffectFormSet:
    """One consequence's editable effects, prefixed ``e<consequence pk>``.

    ``effects`` is the consequence's already-fetched effects of any type (the
    builder page passes ``effects_by_consequence``'s list); only the
    ``BUILDER_EFFECT_TYPES`` among them become forms. Without it the formset
    queries its own.
    """
    prefetched = (
        None
        if effects is None
        else [effect for effect in effects if effect.effect_type in BUILDER_EFFECT_TYPES]
    )
    return EffectFormSet(
        data,
        instance=consequence,
        prefix=f"e{consequence.pk}",
        queryset=ConsequenceEffect.objects.filter(
            effect_type__in=BUILDER_EFFECT_TYPES
        ).select_related(*_EFFECT_RELATIONS),
        prefetched=prefetched,
        form_kwargs={"choices": choices},
    )


def new_row_effect_formset(
    index: int | str, data: object = None, *, choices: BuilderChoices | None = None
) -> EffectFormSet:
    """The effects of a row added on the page, prefixed ``new<row form index>``.

    Bound to an unsaved ``Consequence``, so it starts with no forms and its
    foreign key validates without a parent pk (Django excludes an inline's
    foreign key from field validation for exactly this). The save creates the
    row's consequence, sets ``formset.instance`` to it, then calls ``save()``.
    ``index`` may be the ``__prefix__`` placeholder for the add-row template.

    A POST that carries no management form for this prefix (a row whose page
    was built without the effect editor) binds as zero effects rather than a
    missing-management-form error: no effects is a valid answer for a new row.
    """
    prefix = f"{NEW_ROW_EFFECTS_PREFIX}{index}"
    if data is not None and f"{prefix}-TOTAL_FORMS" not in data:
        data = {f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"}
    return EffectFormSet(
        data,
        instance=Consequence(),
        prefix=prefix,
        queryset=ConsequenceEffect.objects.none(),
        form_kwargs={"choices": choices},
    )


@dataclass(frozen=True)
class TableRow:
    """One consequence as this stage's table shows it."""

    consequence: Consequence
    weight: int
    shared_from: ConsequencePool | None
    dropped: bool


def consequence_table(pool: ConsequencePool | None) -> list[TableRow]:
    """This pool's own rows plus every row its parent shares, weighted as this pool draws them.

    Its own walk rather than ``merge_pool_entries`` because the table also shows the
    parent rows this stage drops (so they can be restored), which the merge discards.
    Weights come from ``_entry_to_weighted``, the draw's own rule, so the non-dropped
    rows always match ``soulfray_ladder_summary()``. One query.
    """
    if pool is None:
        return []
    pool_ids = [pool.pk] + ([pool.parent_id] if pool.parent_id else [])
    entries = list(
        ConsequencePoolEntry.objects.filter(pool_id__in=pool_ids).select_related(
            "consequence__outcome_tier"
        )
    )
    own = {e.consequence_id: e for e in entries if e.pool_id == pool.pk}
    parent = {e.consequence_id: e for e in entries if e.pool_id != pool.pk and not e.is_excluded}
    rows: list[TableRow] = []
    for cid, parent_entry in parent.items():
        child = own.get(cid)
        reweights = child is not None and child.weight_override is not None
        weight = _entry_to_weighted(child if reweights else parent_entry).weight
        dropped = child is not None and child.is_excluded
        rows.append(TableRow(parent_entry.consequence, weight, pool.parent, dropped))
    for cid, entry in own.items():
        if cid in parent or entry.is_excluded:
            continue
        rows.append(TableRow(entry.consequence, _entry_to_weighted(entry).weight, None, False))
    rows.sort(
        key=lambda row: (
            row.consequence.outcome_tier.success_level,
            not row.consequence.character_loss,
            row.consequence.label,
        )
    )
    return rows


def row_initial(row: TableRow) -> dict[str, object]:
    consequence = row.consequence
    return {
        "consequence": consequence.pk,
        "outcome_tier": consequence.outcome_tier_id,
        "label": consequence.label,
        "weight": row.weight,
        "character_loss": consequence.character_loss,
        "theater": consequence.theater,
        "remove": row.dropped,
    }


def copied_initial(row: TableRow) -> dict[str, object]:
    """A new row prefilled from another stage's own row; its effects are cloned on save."""
    consequence = row.consequence
    return {
        "copy_of": consequence.pk,
        "outcome_tier": consequence.outcome_tier_id,
        "label": consequence.label,
        "weight": row.weight,
        "character_loss": consequence.character_loss,
        "theater": consequence.theater,
    }


@dataclass
class BuilderForms:
    """Every form layer one stage's page needs, bundled (ruff PLR0913).

    ``effects`` is keyed by consequence pk (rows the page was rendered with);
    ``new_effects`` by row form index (rows added on the page, every index at or
    past ``len(table)``); ``new_effects_template`` is the unbound ``new__prefix__``
    formset the add-row template clones. ``table_effects`` is every effect of the
    table's consequences, any type, from the one fetch the formsets were fed by;
    the page lists them from it rather than querying again.
    """

    stage: StageForm
    on_entry: OnEntryFormSet
    penalty: PenaltyForm
    pool: PoolForm
    rows: ConsequenceRowFormSet
    effects: dict[int, EffectFormSet]
    table: list[TableRow]
    new_effects: dict[int, EffectFormSet]
    new_effects_template: EffectFormSet
    table_effects: dict[int, list[ConsequenceEffect]] = field(default_factory=dict)

    @property
    def media(self) -> Media:
        return self.stage.media + self.on_entry.media + EffectForm().media


def _modifier(
    stage: ConditionStage, config: SoulfrayConfig | None
) -> ConditionCheckModifier | None:
    if config is None:
        return None
    return ConditionCheckModifier.objects.filter(
        stage=stage, check_type=config.resilience_check_type
    ).first()


def build_forms(
    data: object,
    stage: ConditionStage,
    config: SoulfrayConfig | None,
    copy_from: ConditionStage | None,
) -> BuilderForms:
    """Bound to ``data`` (a POST) or unbound (``None``). Copied rows are only added unbound."""
    pool = stage.consequence_pool
    table = consequence_table(pool)
    initial = [row_initial(row) for row in table]
    if copy_from is not None and data is None:
        initial += [
            copied_initial(row)
            for row in consequence_table(copy_from.consequence_pool)
            if row.shared_from is None
        ]
    modifier = _modifier(stage, config)
    choices = BuilderChoices.load()
    table_effects = effects_by_consequence([row.consequence.pk for row in table])
    rows = ConsequenceRowFormSet(
        data,
        prefix="rows",
        initial=initial,
        table_ids=[row.consequence.pk for row in table],
        form_kwargs={"choices": choices},
    )
    return BuilderForms(
        stage=StageForm(data, instance=stage, prefix="stage"),
        on_entry=OnEntryFormSet(data, instance=stage, prefix="onentry"),
        penalty=PenaltyForm(
            data,
            prefix="penalty",
            initial={"modifier_value": modifier.modifier_value if modifier else None},
        ),
        pool=PoolForm(
            data,
            prefix="pool",
            stage=stage,
            initial={
                "pool": pool.pk if pool else None,
                "parent": pool.parent_id if pool else None,
                "new_name": f"Soulfray - {stage.name}",
            },
        ),
        rows=rows,
        effects={
            row.consequence.pk: effect_formset_for(
                row.consequence,
                data,
                effects=table_effects.get(row.consequence.pk, []),
                choices=choices,
            )
            for row in table
        },
        table=table,
        new_effects={
            index: new_row_effect_formset(index, data, choices=choices)
            for index in range(len(table), len(rows.forms))
        },
        new_effects_template=new_row_effect_formset("__prefix__", choices=choices),
        table_effects=table_effects,
    )
