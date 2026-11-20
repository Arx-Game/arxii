"""Reset one character's play progress from the acquisition-provenance ledger (#3055 PR 3).

The beta wipe (``world.beta_reset.services``) deletes play-provenance rows for the whole
world and deliberately does not step a derived value back down. This service does that for
ONE character that is kept: a roster character returning to Available, a reserved original
character, or a tester's carried-over character. What carries character-creation or
authoring provenance is the baseline and is left alone.

What it reverses, all read from ``world.beta_reset.services`` so "play provenance" has one
definition (``scope_entry_for``):

- **Trait and skill values.** Each play-time ``CharacterTraitChange`` recorded the exact
  delta. The baseline is the current value minus the sum of those deltas, which stays right
  when play-time and authoring changes interleave and when a level reversal already logged
  its own correction. A row that play created (baseline zero, no authoring change) is
  removed. The play-time change rows are then deleted, so a second run finds nothing to
  reverse.
- **Techniques, gifts and distinctions** with a play-time origin are removed. A distinction
  goes through the same teardown ``remove_distinction`` uses; a gift takes its natural
  weapon with it.
- **Stat-point and maturation spends**, the receipts of the ``LEVEL_STAT_POINT`` and
  ``MATURATION`` changes above, so a character does not keep spent points whose stats were
  reversed.
- **Class level** is restored to the lowest ``level_before`` among the character's Durance
  advancement and Audere Majora crossing receipts. The receipts stay, so the level is the
  same on a second run.

What it does NOT reset: the tables in ``classification.UNDECIDED_AWAITING_RULING`` (XP and
development balances, magic state, relationships, codex knowledge and the rest) and the
character's path. A crossing or semi-crossing switched the path, and
``CharacterPathHistory`` carries no provenance to say which row was baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Model

from world.beta_reset.services import (
    deprovision_play_time_natural_weapons,
    scope_entry_for,
)
from world.distinctions.models import CharacterDistinction
from world.distinctions.services import delete_character_distinction
from world.magic.audere_majora import AudereMajoraCrossing
from world.magic.models import CharacterGift, CharacterTechnique
from world.progression.models import ClassLevelAdvancement, LevelStatPointSpend, MaturationSpend
from world.traits.models import CharacterTraitChange, CharacterTraitValue

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


@dataclass(frozen=True)
class TraitRevert:
    """One trait value stepped back to its baseline."""

    trait_id: int
    trait_name: str
    current: int
    baseline: int
    removes_row: bool


@dataclass(frozen=True)
class ProgressResetPlan:
    """What ``reset_character_progress`` changes for one character."""

    sheet_id: int
    trait_reverts: tuple[TraitRevert, ...]
    play_trait_changes: int
    techniques: int
    gifts: int
    distinctions: int
    spend_receipts: int
    level_now: int | None
    level_baseline: int | None

    @property
    def lowers_level(self) -> bool:
        return (
            self.level_now is not None
            and self.level_baseline is not None
            and self.level_baseline < self.level_now
        )

    @property
    def changes_anything(self) -> bool:
        return bool(
            self.trait_reverts
            or self.play_trait_changes
            or self.techniques
            or self.gifts
            or self.distinctions
            or self.spend_receipts
            or self.lowers_level
        )

    def summary(self) -> str:
        """One line for the dry-run: what the reset would do to this character."""
        parts = [
            f"{len(self.trait_reverts)} trait value(s) stepped back",
            f"{self.techniques} technique(s), {self.gifts} gift(s) and "
            f"{self.distinctions} distinction(s) removed",
            f"{self.spend_receipts} stat-point/maturation spend(s) removed",
        ]
        if self.lowers_level:
            parts.append(f"level {self.level_now} -> {self.level_baseline}")
        return "; ".join(parts)


def _play_filter(model: type[Model]) -> dict[str, Any]:
    """The play-time filter ``SCOPE_TABLE`` uses for ``model``."""
    return scope_entry_for(model).filter_kwargs or {}


def _level_baseline(sheet: CharacterSheet) -> tuple[int | None, int | None]:
    """The primary class level now, and the level it started at when play raised it."""
    from world.progression.services.advancement import primary_class_level  # noqa: PLC0415

    current = primary_class_level(sheet.character)
    if current is None:
        return None, None
    before = [
        *ClassLevelAdvancement.objects.filter(character_sheet=sheet).values_list(
            "level_before", flat=True
        ),
        *AudereMajoraCrossing.objects.filter(character_sheet=sheet).values_list(
            "level_before", flat=True
        ),
    ]
    return current.level, (min(before) if before else None)


def _trait_reverts(sheet: CharacterSheet) -> tuple[TraitRevert, ...]:
    deltas: dict[int, int] = {}
    play_changes = CharacterTraitChange.objects.filter(
        character_sheet=sheet, **_play_filter(CharacterTraitChange)
    )
    for trait_id, old, new in play_changes.values_list("trait_id", "old_value", "new_value"):
        deltas[trait_id] = deltas.get(trait_id, 0) + (new - old)
    if not deltas:
        return ()
    authored = set(
        CharacterTraitChange.objects.filter(character_sheet=sheet, trait_id__in=list(deltas))
        .exclude(**_play_filter(CharacterTraitChange))
        .values_list("trait_id", flat=True)
    )
    reverts: list[TraitRevert] = []
    values = CharacterTraitValue.objects.filter(
        character=sheet, trait_id__in=list(deltas)
    ).select_related("trait")
    for value in values:
        baseline = value.value - deltas[value.trait_id]
        removes = baseline <= 0 and value.trait_id not in authored
        if baseline != value.value or removes:
            reverts.append(
                TraitRevert(value.trait_id, value.trait.name, value.value, baseline, removes)
            )
    return tuple(sorted(reverts, key=lambda revert: revert.trait_name))


def plan_progress_reset(sheet: CharacterSheet) -> ProgressResetPlan:
    """Read-only: what the progress reset would change for ``sheet``."""
    level_now, level_baseline = _level_baseline(sheet)
    return ProgressResetPlan(
        sheet_id=sheet.pk,
        trait_reverts=_trait_reverts(sheet),
        play_trait_changes=CharacterTraitChange.objects.filter(
            character_sheet=sheet, **_play_filter(CharacterTraitChange)
        ).count(),
        techniques=CharacterTechnique.objects.filter(
            character=sheet, **_play_filter(CharacterTechnique)
        ).count(),
        gifts=CharacterGift.objects.filter(character=sheet, **_play_filter(CharacterGift)).count(),
        distinctions=CharacterDistinction.objects.filter(
            character=sheet, **_play_filter(CharacterDistinction)
        ).count(),
        spend_receipts=(
            LevelStatPointSpend.objects.filter(character_sheet=sheet).count()
            + MaturationSpend.objects.filter(character_sheet=sheet).count()
        ),
        level_now=level_now,
        level_baseline=level_baseline,
    )


@transaction.atomic
def reset_character_progress(sheet: CharacterSheet) -> ProgressResetPlan:
    """Strip ``sheet``'s play progress back to its character-creation/authoring baseline.

    Returns the plan that was applied. Runs in one transaction. Safe to run twice: the
    second run finds no play-time rows and no level above baseline.
    """
    from world.magic.services.anima import recompute_max_anima  # noqa: PLC0415
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415
    from world.progression.services.advancement import apply_class_level_advance  # noqa: PLC0415

    plan = plan_progress_reset(sheet)

    # The spend receipts first: the trait reversal below undoes the +1 each one funded, and
    # a level reversal would otherwise try to undo it a second time.
    LevelStatPointSpend.objects.filter(character_sheet=sheet).delete()
    MaturationSpend.objects.filter(character_sheet=sheet).delete()

    reverting = {revert.trait_id: revert for revert in plan.trait_reverts}
    if reverting:
        values = CharacterTraitValue.objects.filter(character=sheet, trait_id__in=list(reverting))
        # One at a time: ``save``/``delete`` on the instance keep the trait handler cache
        # right, which a queryset update or delete would not.
        for value in values:
            revert = reverting[value.trait_id]
            if revert.removes_row:
                value.delete()
            else:
                value.value = revert.baseline
                value.save()
    CharacterTraitChange.objects.filter(
        character_sheet=sheet, **_play_filter(CharacterTraitChange)
    ).delete()

    deprovision_play_time_natural_weapons(sheet)
    CharacterTechnique.objects.filter(character=sheet, **_play_filter(CharacterTechnique)).delete()
    CharacterGift.objects.filter(character=sheet, **_play_filter(CharacterGift)).delete()
    for distinction in CharacterDistinction.objects.filter(
        character=sheet, **_play_filter(CharacterDistinction)
    ).select_related("distinction"):
        delete_character_distinction(distinction)

    if plan.lowers_level and plan.level_baseline is not None:
        apply_class_level_advance(sheet, level_after=plan.level_baseline)
    else:
        recompute_max_health_with_threads(sheet)
        recompute_max_anima(sheet)
    return plan
