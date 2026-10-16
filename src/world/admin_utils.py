"""Shared Django admin helpers usable across every ``world`` sub-package (#3679).

A handful of hub models (``Resonance``, ``CapabilityType``, ``DamageType``, ...) are
referenced by FK/M2M from many unrelated apps. Hand-listing every consumer's
related_name in each admin goes stale the moment another app adds one more FK —
which is exactly how these models ended up admin-invisible in the first place.
``describe_reverse_relations`` instead derives the list from Django's own model
introspection, so it stays correct as new consumers are added.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Model
from django.forms.models import BaseInlineFormSet

if TYPE_CHECKING:
    from django.forms import BaseForm


def describe_reverse_relations(obj: Model, *, exclude: frozenset[str] = frozenset()) -> str:
    """One entry per reverse FK/M2M/O2O relation on ``obj`` that has any rows.

    Read-only, admin-display use only — one query per relation (a handful, for the
    hub models this is built for), which is fine for a single detail-page render;
    do not call this from ``list_display`` (it is not prefetch-batched across rows).
    ``exclude`` names accessor names to skip (e.g. a relation already shown as its
    own inline or field elsewhere on the page).
    """
    if obj.pk is None:
        return "-"

    entries: list[str] = []
    for field in obj._meta.get_fields():  # noqa: SLF001
        if not (field.is_relation and field.auto_created and not field.concrete):
            continue
        accessor_name = field.get_accessor_name()
        if accessor_name in exclude:
            continue

        if field.one_to_one:
            try:
                related_obj = getattr(obj, accessor_name)
            except ObjectDoesNotExist:
                continue
            entries.append(f"{field.related_model._meta.verbose_name}: {related_obj}")  # noqa: SLF001
            continue

        count = getattr(obj, accessor_name).count()
        if not count:
            continue
        entries.append(f"{field.related_model._meta.verbose_name_plural}: {count}")  # noqa: SLF001

    return "; ".join(entries) if entries else "No connections found."


class OneRowPerFormSet(BaseInlineFormSet):
    """An inline formset that names the row a staff member doubled (#4380).

    Django's own check for a ``(parent, field)`` uniqueness rule answers
    "Please correct the duplicate data for gift." - true, and no help to the
    person reading it: it names neither the gift nor the fact that two rows
    are the problem. A staff member authoring a tradition read the gift-grant
    inline as one row per starting technique, put the same gift on two rows,
    and was refused with exactly that line.

    This base runs the same check first, from the model's own unique
    constraints and ``unique_together`` that include the inline's parent key,
    and marks each doubled row with a line that names the field and its value
    ("Gift 'Shadowcraft' is already on another row."). ``duplicate_hint`` lets
    an inline say what to do instead. Django's check still runs afterwards and
    finds nothing, because a row carrying an error is not a valid form. Every
    inline whose model has such a rule names this formset;
    ``web.admin.tests.test_inline_duplicate_rows`` enumerates them.
    """

    #: Appended to every duplicate-row message; an inline sets it to say what the
    #: author should do instead (for a tradition's gift grants: pick every special
    #: technique for a gift on that gift's one row).
    duplicate_hint: str = ""

    def clean(self) -> None:
        messages = self._mark_duplicate_rows()
        super().clean()
        if messages:
            raise ValidationError(messages)

    def _row_rules(self) -> list[tuple[str, ...]]:
        """The field sets, parent key left out, that must differ between two rows."""
        opts = self.model._meta  # noqa: SLF001
        rule_sets = [tuple(constraint.fields) for constraint in opts.total_unique_constraints]
        rule_sets.extend(tuple(names) for names in opts.unique_together)
        return [
            tuple(name for name in fields if name != self.fk.name)
            for fields in rule_sets
            if self.fk.name in fields and len(fields) > 1
        ]

    def _mark_duplicate_rows(self) -> list[str]:
        messages: list[str] = []
        for rule in self._row_rules():
            seen: set[tuple] = set()
            for form in self.forms:
                values = self._rule_values(form, rule)
                if values is None:
                    continue
                key = tuple(value.pk if isinstance(value, Model) else value for value in values)
                if key in seen:
                    message = self._duplicate_message(rule, values)
                    form.add_error(None, message)
                    messages.append(message)
                else:
                    seen.add(key)
        return messages

    @staticmethod
    def _rule_values(form: BaseForm, rule: tuple[str, ...]) -> list | None:
        """The row's values for ``rule``, or None when the row cannot take part.

        A blank extra row, a row marked for deletion, and a row that failed its
        own field validation all sit out; Django's field errors already cover the
        last of those.
        """
        data = form.cleaned_data
        if not data or data.get("DELETE"):
            return None
        if any(name not in data for name in rule):
            return None
        values = [data[name] for name in rule]
        if any(value is None or value == "" for value in values):
            return None
        return values

    def _duplicate_message(self, rule: tuple[str, ...], values: list) -> str:
        opts = self.model._meta  # noqa: SLF001
        parts = [
            f"{opts.get_field(name).verbose_name} '{value}'"
            for name, value in zip(rule, values, strict=True)
        ]
        verb = "is" if len(parts) == 1 else "are"
        text = f"{' and '.join(parts)} {verb} already on another row."
        text = text[0].upper() + text[1:]
        return f"{text} {self.duplicate_hint}".strip()
