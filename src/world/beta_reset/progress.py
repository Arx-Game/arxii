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

Before it changes anything it checks the ledger is whole (``ledger_problems``): each trait's
rows must chain (a row's ``old_value`` is the previous row's ``new_value``) and end at the
current value, a trait with ledger rows must still have its value row, and the class-level
receipts must chain up to the current level. A character that fails is refused unless the
caller passes ``allow_incomplete_ledger=True``, because the subtraction would then restore a
wrong number. Both the enabled constant and the release latch are checked on every call, so
no direct call can run after release.

Lowering the level here does NOT call ``apply_class_level_advance``: that fires
``on_character_level_changed``, which re-runs story auto-beats for every active story of the
character, and a beat that resolves sends a narrative notification to its players and may open
a session request. A reset must not message anyone, so the level, caches, health and anima are
written directly.

What it does NOT reset: the tables in ``classification.UNDECIDED_AWAITING_RULING`` (XP and
development balances, magic state, relationships, codex knowledge and the rest) and the
character's path. A crossing or semi-crossing switched the path, and
``CharacterPathHistory`` carries no provenance to say which row was baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Model

from world.beta_reset.exceptions import IncompleteLedgerError
from world.beta_reset.services import (
    check_beta_reset_enabled,
    check_release_latch,
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
    natural_weapons: int
    distinctions: int
    spend_receipts: int
    level_now: int | None
    level_baseline: int | None
    problems: tuple[str, ...]

    @property
    def lowers_level(self) -> bool:
        return (
            self.level_now is not None
            and self.level_baseline is not None
            and self.level_baseline < self.level_now
        )

    @property
    def removed_trait_names(self) -> list[str]:
        return [revert.trait_name for revert in self.trait_reverts if revert.removes_row]

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
        stepped = f"{len(self.trait_reverts)} trait value(s) stepped back"
        if self.removed_trait_names:
            stepped += f" (rows removed: {', '.join(self.removed_trait_names)})"
        gifts = f"{self.gifts} gift(s)"
        if self.natural_weapons:
            gifts += f" (taking {self.natural_weapons} natural weapon(s) with them)"
        parts = [
            stepped,
            f"{self.techniques} technique(s), {gifts} and "
            f"{self.distinctions} distinction(s) removed",
            f"{self.spend_receipts} stat-point/maturation spend(s) removed",
        ]
        if self.lowers_level:
            parts.append(f"level {self.level_now} -> {self.level_baseline}")
        return "; ".join(parts)


def _play_filter(model: type[Model]) -> dict[str, Any]:
    """The play-time filter ``SCOPE_TABLE`` uses for ``model``."""
    return scope_entry_for(model).filter_kwargs or {}


def _level_receipts(sheet: CharacterSheet) -> list[tuple[int, int]]:
    """Every ``(level_before, level_after)`` the character's receipts record, lowest first."""
    rows = [
        *ClassLevelAdvancement.objects.filter(character_sheet=sheet).values_list(
            "level_before", "level_after"
        ),
        *AudereMajoraCrossing.objects.filter(character_sheet=sheet).values_list(
            "level_before", "level_after"
        ),
    ]
    return sorted(rows)


def _level_baseline(sheet: CharacterSheet) -> tuple[int | None, int | None]:
    """The primary class level now, and the level it started at when play raised it."""
    from world.progression.services.advancement import primary_class_level  # noqa: PLC0415

    current = primary_class_level(sheet.character)
    if current is None:
        return None, None
    receipts = _level_receipts(sheet)
    return current.level, (receipts[0][0] if receipts else None)


def _trait_ledger_problems(sheet: CharacterSheet) -> list[str]:
    play_trait_ids = set(
        CharacterTraitChange.objects.filter(
            character_sheet=sheet, **_play_filter(CharacterTraitChange)
        ).values_list("trait_id", flat=True)
    )
    if not play_trait_ids:
        return []
    current_values = dict(
        CharacterTraitValue.objects.filter(
            character=sheet, trait_id__in=list(play_trait_ids)
        ).values_list("trait_id", "value")
    )
    chains: dict[int, list[tuple[int, int]]] = {}
    names: dict[int, str] = {}
    rows = (
        CharacterTraitChange.objects.filter(
            character_sheet=sheet, trait_id__in=list(play_trait_ids)
        )
        .select_related("trait")
        .order_by("trait_id", "created_at", "pk")
    )
    for row in rows:
        chains.setdefault(row.trait_id, []).append((row.old_value, row.new_value))
        names[row.trait_id] = row.trait.name
    problems: list[str] = []
    for trait_id in sorted(play_trait_ids, key=lambda tid: names[tid]):
        name = names[trait_id]
        chain = chains[trait_id]
        for (_, previous_new), (old, _) in pairwise(chain):
            if old != previous_new:
                problems.append(
                    f"{name}: the ledger breaks (a row starts at {old} but the one before "
                    f"it ended at {previous_new})"
                )
                break
        if trait_id not in current_values:
            problems.append(f"{name}: ledger rows exist but the trait value row is gone")
        elif chain[-1][1] != current_values[trait_id]:
            problems.append(
                f"{name}: the ledger ends at {chain[-1][1]} but the value is "
                f"{current_values[trait_id]}"
            )
    return problems


def _level_ledger_problems(sheet: CharacterSheet) -> list[str]:
    receipts = _level_receipts(sheet)
    level_now, _ = _level_baseline(sheet)
    if not receipts or level_now is None:
        return []
    problems: list[str] = []
    for (_, previous_after), (before, _) in pairwise(receipts):
        if before != previous_after:
            problems.append(
                f"class level: the advancement receipts break (one starts at {before} but "
                f"the one before it ended at {previous_after})"
            )
            break
    # The level is whole at the top of the receipts, or already back at the baseline they
    # start from (a reset keeps the receipts, so a second run sees exactly that).
    if level_now not in (receipts[-1][1], receipts[0][0]):
        problems.append(
            f"class level: the receipts end at {receipts[-1][1]} but the level is {level_now}"
            + (" (a rise with no advancement receipt)" if level_now > receipts[-1][1] else "")
        )
    return problems


def ledger_problems(sheet: CharacterSheet) -> tuple[str, ...]:
    """Reasons the baseline subtraction would restore a wrong number for ``sheet``.

    Empty when the ledger is whole. Each entry names the trait or the level and says what is
    wrong, so the dry-run and the refusal can print it as is.
    """
    return (*_trait_ledger_problems(sheet), *_level_ledger_problems(sheet))


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
    play_gifts = CharacterGift.objects.filter(character=sheet, **_play_filter(CharacterGift))
    return ProgressResetPlan(
        sheet_id=sheet.pk,
        trait_reverts=_trait_reverts(sheet),
        play_trait_changes=CharacterTraitChange.objects.filter(
            character_sheet=sheet, **_play_filter(CharacterTraitChange)
        ).count(),
        techniques=CharacterTechnique.objects.filter(
            character=sheet, **_play_filter(CharacterTechnique)
        ).count(),
        gifts=play_gifts.count(),
        natural_weapons=play_gifts.filter(gift__natural_weapon_template__isnull=False).count(),
        distinctions=CharacterDistinction.objects.filter(
            character=sheet, **_play_filter(CharacterDistinction)
        ).count(),
        spend_receipts=(
            LevelStatPointSpend.objects.filter(character_sheet=sheet).count()
            + MaturationSpend.objects.filter(character_sheet=sheet).count()
        ),
        level_now=level_now,
        level_baseline=level_baseline,
        problems=ledger_problems(sheet),
    )


def _lower_primary_level(sheet: CharacterSheet, level: int) -> None:
    """Write ``level`` to the primary class row without the story-reactivity side effects."""
    from world.progression.services.advancement import primary_class_level  # noqa: PLC0415

    row = primary_class_level(sheet.character)
    if row is not None:
        row.level = level
        row.save(update_fields=["level"])
    sheet.invalidate_class_level_cache()


@transaction.atomic
def reset_character_progress(
    sheet: CharacterSheet, *, allow_incomplete_ledger: bool = False
) -> ProgressResetPlan:
    """Strip ``sheet``'s play progress back to its character-creation/authoring baseline.

    Returns the plan that was applied. Runs in one transaction. Safe to run twice: the
    second run finds no play-time rows and no level above baseline. Refuses (nothing
    touched) when the enabled constant is off, a release latch exists, or the ledger is not
    whole and ``allow_incomplete_ledger`` is False.
    """
    from world.magic.services.anima import recompute_max_anima  # noqa: PLC0415
    from world.magic.services.threads import recompute_max_health_with_threads  # noqa: PLC0415

    check_beta_reset_enabled()
    check_release_latch()
    plan = plan_progress_reset(sheet)
    if plan.problems and not allow_incomplete_ledger:
        raise IncompleteLedgerError({sheet.character.db_key: list(plan.problems)})

    # The spend receipts first: the trait reversal below undoes the +1 each one funded, so
    # leaving a receipt would keep the points spent with the stat gone. Every row goes, with
    # no provenance filter, because only ``spend_level_stat_point`` and
    # ``spend_maturation_point`` write these tables (called from the character sheet views
    # for a player's own spend; the GM award in ``awards.py`` explicitly writes none, and no
    # character-creation or authoring path creates one), and both stamp the matching
    # LEVEL_STAT_POINT / MATURATION trait change, which is play-time by definition. A row
    # staff create by hand in the admin has no trait change behind it and goes too.
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
    # The technique handler caches the character's list in this process.
    sheet.character.techniques.invalidate()
    for distinction in CharacterDistinction.objects.filter(
        character=sheet, **_play_filter(CharacterDistinction)
    ).select_related("distinction"):
        delete_character_distinction(distinction)

    if plan.lowers_level and plan.level_baseline is not None:
        _lower_primary_level(sheet, plan.level_baseline)
    recompute_max_health_with_threads(sheet)
    recompute_max_anima(sheet)
    return plan
