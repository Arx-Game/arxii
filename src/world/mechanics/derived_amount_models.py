"""The shared derived-amount menu a modifier row can carry (#4878).

The owner's ruling on #4824: every modifier row can pick an input, a "per N" step and a
cap, through one mechanism. ``DerivedAmountMixin`` is that menu as columns; a row adopts
it by inheriting. Distinction effects and condition modifier effects are the first rows.
The number itself is worked out by ``world.mechanics.derived_amounts.derived_amount``.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from world.mechanics.constants import STAT_CATEGORY_NAME, AmountInput

AMOUNT_INPUT_ANCHOR_FIELDS: dict[str, tuple[str, ...]] = {
    AmountInput.CHECK_RANK: ("amount_check_type",),
    AmountInput.THREAD_LEVEL: ("amount_thread_trait", "amount_thread_facet"),
}
_ALL_ANCHOR_FIELDS = ("amount_check_type", "amount_thread_trait", "amount_thread_facet")


class DerivedAmountMixin(models.Model):
    """An input, a "per N" step and a cap for a modifier row's amount.

    With an input picked, the row's own amount is the amount per step and the row's fixed
    scaling (a distinction's size, a condition's severity or stage) no longer applies: a
    number has one origin.
    """

    amount_input = models.CharField(
        max_length=20,
        choices=AmountInput.choices,
        blank=True,
        default=AmountInput.NONE,
        help_text="What this row's amount is derived from. Blank keeps the row's own scaling.",
    )
    amount_per = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="One step of the amount per this many units of the input (2 = per 2 ranks).",
    )
    amount_cap = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="The most the derived amount can be, as a magnitude. Blank for no cap.",
    )
    amount_check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="For a check rank input: the check whose total rank is read.",
    )
    amount_thread_trait = models.ForeignKey(
        "arxii.Trait",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="For a thread level input: the holder's thread on this trait.",
    )
    amount_thread_facet = models.ForeignKey(
        "arxii.Facet",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_amount_inputs",
        help_text="For a thread level input: the holder's thread on this facet.",
    )

    class Meta:
        abstract = True

    @property
    def has_amount_input(self) -> bool:
        return bool(self.amount_input)

    def clean_derived_amount(self, target) -> dict[str, str]:
        """The field errors for this row's menu, given the row's ``ModifierTarget``.

        The chosen input's anchor is set (one of the two for a thread), every other anchor
        is blank, and a check rank never feeds a stat or skill target (the stat category, or
        any target linked to a trait, which is how a stat read finds it): a check's rating reads
        stats, which would read this row again. ``derived_amounts`` also guards the read.
        """
        errors: dict[str, str] = {}
        allowed = AMOUNT_INPUT_ANCHOR_FIELDS.get(self.amount_input, ())
        for name in _ALL_ANCHOR_FIELDS:
            if name not in allowed and getattr(self, f"{name}_id") is not None:
                errors[name] = "Clear this: the chosen input does not read it."
        if self.amount_input == AmountInput.CHECK_RANK and self.amount_check_type_id is None:
            errors["amount_check_type"] = "Name the check whose rank is read."
        if self.amount_input == AmountInput.THREAD_LEVEL:
            chosen = [name for name in allowed if getattr(self, f"{name}_id") is not None]
            if len(chosen) != 1:
                errors["amount_thread_trait"] = "Name one trait or one facet whose thread is read."
        if (
            self.amount_input == AmountInput.CHECK_RANK
            and target is not None
            and (target.category.name == STAT_CATEGORY_NAME or target.target_trait_id is not None)
        ):
            errors["amount_input"] = (
                "A stat or skill cannot take a check rank input: the check reads the stat."
            )
        if not self.has_amount_input and self.amount_cap is not None:
            errors["amount_cap"] = "A cap needs an input."
        return errors

    def raise_derived_amount_errors(self, target) -> None:
        errors = self.clean_derived_amount(target)
        if errors:
            raise ValidationError(errors)
