"""Food collection dispatch — mirrors ``collect_org_income``."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from world.agriculture.models import FieldDetails, FoodStockpile
from world.agriculture.services.domain import (
    max_food_capacity,
    resolve_domain_for_feature,
)
from world.agriculture.types import FoodCollectionResult


def _collection_band_pct(success_level: int) -> int | None:
    """Percent of the gathered pool that lands for this band; None = catastrophe.

    Reuses the same band shape as ``world.currency.services._collection_band_pct``
    but reads the constant directly (read-only — does NOT modify the shared
    constant).
    """
    from world.currency.constants import COLLECTION_BAND_PCTS  # noqa: PLC0415

    for floor, pct in COLLECTION_BAND_PCTS:
        if success_level >= floor:
            return pct
    return None


def _apply_unrest_skim(landed: int, unrest: int) -> int:
    """Unrest skims the food haul (#2238): pct skimmed = min(cap, unrest).

    A domain in chaos loses food on the way in — the more unrest, the less lands,
    up to ``UNREST_COLLECTION_SKIM_MAX_PCT``.
    """
    from world.agriculture.constants import UNREST_COLLECTION_SKIM_MAX_PCT  # noqa: PLC0415

    skim_pct = min(UNREST_COLLECTION_SKIM_MAX_PCT, unrest)
    return landed * (100 - skim_pct) // 100


def _pool_difficulty_bonus(field_instance, _character=None) -> int:
    """Compute the difficulty bonus from accumulated pool size (#2218).

    A larger uncollected pool is harder to collect — more laborers, carts,
    and attention drawn.  Reads ``FoodConfig.pool_difficulty_*`` knobs:

    - No bonus while pool ≤ ``pool_difficulty_threshold``.
    - Each full ``pool_difficulty_step`` above the threshold adds +1 difficulty.
    - Capped at ``pool_difficulty_max_bonus``.

    The ``_character`` parameter is accepted for API symmetry with future
    character-based difficulty modifiers but is not currently used.

    Returns 0 if the Field has no ``FieldDetails`` (shouldn't happen here —
    the caller already validated it, but defensive).
    """
    from world.agriculture.services.production import get_food_config  # noqa: PLC0415

    try:
        pool = field_instance.field_details.uncollected_pool
    except Exception:  # noqa: BLE001
        return 0

    config = get_food_config()
    threshold = config.pool_difficulty_threshold
    step = config.pool_difficulty_step or 1  # avoid div-by-zero
    excess = max(0, pool - threshold)
    bonus = excess // step
    return min(bonus, config.pool_difficulty_max_bonus)


@transaction.atomic
def collect_field_food(character, field_instance) -> FoodCollectionResult:
    """One active collection dispatch from a Field's uncollected pool.

    Mirrors ``collect_org_income``: zeroes the pool (food left with the
    collector regardless of outcome), rolls a Food Collection check,
    applies the band percentage, and lands food into the domain's
    ``FoodStockpile`` (capped at max capacity from Granaries). Excess
    above capacity is lost (overflow).

    **Mini-game event flow (#2218):**

    1. ``FOOD_PRE_COLLECT`` — emitted *before* the pool is zeroed. The
       payload (``FoodPreCollectPayload``) is mutable and cancellable.
       Reactive flows may inspect the pool size and pre-computed
       ``pool_difficulty_bonus``, adjust ``difficulty_modifier`` (e.g.
       intimidation, bribery, persuasion), or cancel the collection
       entirely (the pool is left untouched).
    2. If cancelled, returns early with ``cancelled=True`` — pool intact.
    3. The check is rolled at the effective difficulty (base + pool bonus
       + modifier from the reactive payload).
    4. ``FOOD_COLLECTED`` — emitted *after* the outcome is resolved.
       Read-only; reactive flows may react to the result (e.g. spawn a
       bandit ambush on a catastrophe).

    Args:
        character: The collecting character (ObjectDB).
        field_instance: The ``RoomFeatureInstance`` for the Field.

    Returns:
        ``FoodCollectionResult`` with gathered, landed, overflow,
        catastrophe, and cancelled details.

    Raises:
        ValueError: If the pool is empty (nothing to collect).
    """
    from flows.constants import EventName  # noqa: PLC0415
    from flows.emit import emit_event  # noqa: PLC0415
    from flows.events.payloads import FoodPreCollectPayload  # noqa: PLC0415

    try:
        details = field_instance.field_details
    except FieldDetails.DoesNotExist:
        msg = "This field has no crop details."
        raise ValueError(msg) from None

    gathered = details.uncollected_pool
    if gathered <= 0:
        msg = "There is nothing waiting to be collected."
        raise ValueError(msg)

    # Resolve the domain early — the pre-collect payload carries it so
    # reactive flows can inspect domain state (unrest, etc.).
    domain = resolve_domain_for_feature(field_instance)

    # --- Pool-size difficulty scaling (#2218) ---
    pool_bonus = _pool_difficulty_bonus(field_instance, character)

    # --- Pre-collect event (cancellable, mutable) ---
    location = getattr(character, "location", None)  # noqa: GETATTR_LITERAL
    pre_payload = FoodPreCollectPayload(
        character=character,
        field_instance=field_instance,
        domain=domain,
        gathered=gathered,
        pool_difficulty_bonus=pool_bonus,
        difficulty_modifier=0,
    )

    cancelled = False
    if location is not None:
        stack = emit_event(
            EventName.FOOD_PRE_COLLECT,
            pre_payload,
            location,
        )
        cancelled = stack.was_cancelled()

    if cancelled:
        # The collection was cancelled before the pool was zeroed — the
        # food stays in the field.  The reactive flow is responsible for
        # narrating why (NPC refusal, ambush, etc.).
        return FoodCollectionResult(
            gathered=gathered,
            landed=0,
            overflow=0,
            success_level=0,
            cancelled=True,
        )

    # Zero the pool — food left with the collector regardless of outcome.
    details.uncollected_pool = 0
    details.save(update_fields=["uncollected_pool"])

    # Roll the check at the effective difficulty.
    success_level = _roll_collection_check(character, pool_bonus, pre_payload.difficulty_modifier)

    pct = _collection_band_pct(success_level)
    if pct is None:
        # Catastrophe: the collector never made it back with the food.
        result = FoodCollectionResult(
            gathered=gathered,
            landed=0,
            overflow=0,
            success_level=success_level,
            catastrophe=True,
        )
        _emit_food_collected(location, character, domain, result)
        return result

    landed = gathered * pct // 100

    if domain is None:
        # No domain — food is collected but has nowhere to go.
        result = FoodCollectionResult(
            gathered=gathered,
            landed=0,
            overflow=landed,
            success_level=success_level,
        )
        _emit_food_collected(location, character, domain, result)
        return result

    # Unrest skims the haul (#2238), then land into the stockpile (capped).
    landed = _apply_unrest_skim(landed, domain.unrest)
    result = _land_food(domain, gathered, landed, success_level)
    _emit_food_collected(location, character, domain, result)
    return result


def _roll_collection_check(character, pool_bonus: int, difficulty_modifier: int) -> int:
    """Roll the Food Collection check at the effective difficulty (#2218).

    Effective difficulty = base (NORMAL) + pool bonus + reactive modifier,
    clamped to the [TRIVIAL, HARROWING] range.  Returns ``success_level``.
    """
    from world.agriculture.constants import FOOD_COLLECTION_CHECK_NAME  # noqa: PLC0415
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.scenes.action_constants import (  # noqa: PLC0415
        DIFFICULTY_VALUES,
        DifficultyChoice,
    )

    check_type = CheckType.objects.filter(name__iexact=FOOD_COLLECTION_CHECK_NAME).first()
    if check_type is None:
        return 0  # unseeded world: unremarkable partial

    effective_difficulty = (
        DIFFICULTY_VALUES[DifficultyChoice.NORMAL] + pool_bonus + difficulty_modifier
    )
    effective_difficulty = min(effective_difficulty, DIFFICULTY_VALUES[DifficultyChoice.HARROWING])
    effective_difficulty = max(effective_difficulty, DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL])
    result = perform_check(
        character,
        check_type,
        target_difficulty=effective_difficulty,
    )
    return result.success_level


def _land_food(domain, gathered: int, landed: int, success_level: int) -> FoodCollectionResult:
    """Land food into the domain's stockpile, capped at Granary capacity.

    Excess above capacity is lost (overflow).  Returns the final
    ``FoodCollectionResult``.
    """
    stockpile, _ = FoodStockpile.objects.get_or_create(domain=domain)
    capacity = max_food_capacity(domain)
    headroom = max(0, capacity - stockpile.stored)
    actual_landed = min(landed, headroom)
    overflow = landed - actual_landed

    stockpile.stored += actual_landed
    stockpile.last_collected_at = timezone.now()
    stockpile.save(update_fields=["stored", "last_collected_at"])

    return FoodCollectionResult(
        gathered=gathered,
        landed=actual_landed,
        overflow=overflow,
        success_level=success_level,
    )


def _emit_food_collected(location, character, domain, result: FoodCollectionResult) -> None:
    """Emit the post-collection ``FOOD_COLLECTED`` event (#2218).

    Read-only — reactive flows cannot modify the outcome.  They may react
    to it (e.g. spawn a bandit ambush on a catastrophe, reward the collector
    on a critical success).
    """
    from flows.constants import EventName  # noqa: PLC0415
    from flows.emit import emit_event  # noqa: PLC0415
    from flows.events.payloads import FoodCollectedPayload  # noqa: PLC0415

    if location is None:
        return

    payload = FoodCollectedPayload(
        character=character,
        domain=domain,
        gathered=result.gathered,
        landed=result.landed,
        overflow=result.overflow,
        catastrophe=result.catastrophe,
    )
    emit_event(
        EventName.FOOD_COLLECTED,
        payload,
        location,
    )
