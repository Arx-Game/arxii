"""Generic crafting orchestration — ``run_crafting_recipe`` (#1031).

This is the integration keystone of the crafting framework. It ties together the
recipe model, the kind-specific handler, the cost-staging/consumption layer, the
consequence pool, and the skill-capped quality resolver into one transactional
entry point.

The facet/style wrappers in ``world.items.services.crafting`` delegate here; this
module knows nothing about facets or styles directly — it dispatches through the
handler registry on ``CraftingRecipeKind``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from actions.types import WeightedConsequence
from world.checks.consequence_resolution import (
    apply_resolution,
    select_consequence_from_result,
)
from world.checks.services import perform_check
from world.checks.types import ResolutionContext
from world.items.crafting.constants import CraftingRecipeKind
from world.items.crafting.cost import consume_cost, stage_and_assert_affordable
from world.items.crafting.models import CraftedItemRecipe, CraftingRecipe, CraftingSkillCap
from world.items.crafting.quality import resolve_capped_tier
from world.items.crafting.registry import get_handler
from world.items.exceptions import (
    CraftingNotConfigured,
    CraftingStationBroken,
    CraftingStationRequired,
)
from world.items.models import EquippedItem, ItemInstance
from world.items.services.materials import meets_quality_tier
from world.room_features.constants import RoomFeatureServiceStrategy

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.crafting.models import CraftedItemRecipe, LabStationDetails
    from world.items.models import QualityTier
    from world.traits.models import CheckOutcome


def _resolve_active_lab_station(crafter_character: ObjectDB) -> LabStationDetails | None:
    """Resolve the LabStationDetails for the crafter's current room, or None (#1234).

    Uses ``RoomFeatureInstance.objects.filter(...).active().first()`` — NOT
    ``room_profile.feature_instance``, which is a single-object OneToOneField
    reverse accessor that raises ``DoesNotExist`` rather than being filterable.
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.items.crafting.models import LabStationDetails  # noqa: PLC0415
    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    location = crafter_character.location
    if location is None:
        return None
    room_profile = RoomProfile.objects.filter(objectdb=location).first()
    if room_profile is None:
        return None
    instance = (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind__service_strategy=RoomFeatureServiceStrategy.LAB,
        )
        .active()
        .first()
    )
    if instance is None:
        return None
    return LabStationDetails.objects.filter(feature_instance=instance).first()


@dataclass(frozen=True)
class CraftRunResult:
    """Generic outcome of a ``run_crafting_recipe`` attempt.

    The facet/style wrappers map this onto their domain-specific result
    dataclasses (``FacetCraftResult`` / ``StyleCraftResult``).
    """

    attached: bool
    outcome: CheckOutcome | None
    row: object | None
    quality_tier: QualityTier | None
    consumed: dict
    consequence_label: str | None
    crafted_recipe: CraftedItemRecipe | None = None


@dataclass(frozen=True)
class CraftingQuoteCost:
    """Resource cost entry for a single cost vector in a crafting quote."""

    action_points: int
    action_points_have: int
    anima: int
    anima_have: int
    # tuple (not list) so the frozen snapshot is genuinely immutable (#1243).
    materials: tuple[dict, ...]


@dataclass(frozen=True)
class CraftingQuoteRisk:
    """A single failure-risk row in a crafting quote."""

    outcome_name: str | None
    cost_consumption: str
    label: str | None


@dataclass(frozen=True)
class StationStatus:
    """Read-only snapshot of the crafter's room's LAB station, for the quote (#1234).

    ``feature_instance_id`` is populated only when ``present`` is True — it lets
    the frontend act on the station (repair) directly from quote data, since
    there is no "current room" context primitive elsewhere in the frontend to
    resolve it independently (see Task 14).
    """

    present: bool
    durability: int
    max_durability: int
    is_broken: bool
    feature_instance_id: int | None = None


@dataclass(frozen=True)
class CraftingQuote:
    """Read-only snapshot of what a crafting attempt would cost and what quality it could yield."""

    costs: CraftingQuoteCost
    affordable: bool
    max_quality_tier: QualityTier | None
    # tuple (not list) so the frozen snapshot is genuinely immutable (#1243).
    failure_risk: tuple[CraftingQuoteRisk, ...] = ()
    station_status: StationStatus | None = None


def _station_status_snapshot(station: object | None) -> tuple[StationStatus, bool]:
    """Build a ``StationStatus`` from a resolved lab station.

    Returns ``(status, broken)`` where ``broken`` is True when the station is
    missing or broken — the caller uses it to narrow ``affordable`` to False.
    """
    if station is None:
        return (
            StationStatus(present=False, durability=0, max_durability=0, is_broken=True),
            True,
        )
    return (
        StationStatus(
            present=True,
            durability=station.durability,
            max_durability=station.max_durability,
            is_broken=station.is_broken,
            feature_instance_id=station.feature_instance_id,
        ),
        station.is_broken,
    )


def _resolve_recipe_for_quote(
    *,
    kind: CraftingRecipeKind,
    output_template: object = None,
) -> CraftingRecipe:
    """Resolve the recipe for a quote, raising ``CraftingNotConfigured`` if missing.

    For ``ITEM_CREATE`` with an ``output_template``, the recipe is resolved by
    ``(kind, output_item_template)``; otherwise by ``kind`` alone.
    """
    try:
        if kind == CraftingRecipeKind.ITEM_CREATE and output_template is not None:
            recipe = CraftingRecipe.objects.get(kind=kind, output_item_template=output_template)
        else:
            recipe = CraftingRecipe.objects.get(kind=kind)
    except CraftingRecipe.DoesNotExist as exc:
        raise CraftingNotConfigured from exc
    if recipe.check_type is None:
        raise CraftingNotConfigured
    return recipe


def build_crafting_quote(
    *,
    kind: CraftingRecipeKind,
    crafter_character: ObjectDB,
    crafter_character_sheet: CharacterSheet,
    target: object = None,  # noqa: ARG001  # kept for API symmetry with run_crafting_recipe
    output_template: object = None,
) -> CraftingQuote:
    """Return a read-only cost+quality snapshot for a potential crafting attempt.

    Does NOT mutate any state — no cost deduction, no roll, no attachment.
    Resolves the recipe for ``kind``, inspects the crafter's current resources
    and skill, and returns a ``CraftingQuote`` describing:

    * ``costs``: AP, Anima, and material requirements with current holdings.
    * ``affordable``: True iff all cost vectors are satisfied.
    * ``max_quality_tier``: Skill-capped ceiling quality tier (None if uncapped).
    * ``failure_risk``: Consequence pool rows mapped to risk summaries.
    * ``station_status``: LAB station snapshot (#1234) when ``recipe.requires_station``
      is True (None otherwise). ``affordable`` is narrowed to False when the
      station is missing or broken.

    Args:
        kind: Which recipe to quote for.
        crafter_character: The ObjectDB whose AP pool, Anima, and traits are read.
        crafter_character_sheet: The CharacterSheet whose inventory is checked.
        target: Unused at quote time (kept for API symmetry with run_crafting_recipe).
        output_template: For ITEM_CREATE, the ItemTemplate being crafted.

    Returns:
        A ``CraftingQuote`` dataclass (frozen, read-only).

    Raises:
        CraftingNotConfigured: No recipe for ``kind``, or it has no ``check_type``.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.magic.models import CharacterAnima  # noqa: PLC0415

    # 1. Resolve recipe ---
    recipe = _resolve_recipe_for_quote(kind=kind, output_template=output_template)

    # 2. AP availability ---
    ap_cost = recipe.action_point_cost
    pool = ActionPointPool.get_or_create_for_character(crafter_character)
    ap_have = pool.current

    # 3. Anima availability ---
    anima_cost = recipe.anima_cost
    anima_row = CharacterAnima.objects.filter(character=crafter_character).first()
    anima_have = anima_row.current if anima_row is not None else 0

    # 4. Materials availability ---
    requirements = list(
        recipe.material_requirements.all().select_related("item_template", "min_quality_tier")
    )
    required_template_ids = [r.item_template_id for r in requirements]
    available: list[ItemInstance] = list(
        ItemInstance.objects.filter(
            holder_character_sheet=crafter_character_sheet,
            template_id__in=required_template_ids,
        ).select_related("quality_tier")
    )
    # Tally held quantities per template that meet min quality.
    material_rows = []
    all_materials_satisfied = True
    for req in requirements:
        matching = [
            inst
            for inst in available
            if inst.template_id == req.item_template_id and meets_quality_tier(inst, req)
        ]
        held_qty = sum(inst.quantity for inst in matching)
        material_rows.append(
            {
                "item_template_id": req.item_template_id,
                "name": req.item_template.name,
                "quantity_required": req.quantity,
                "have": held_qty,
            }
        )
        if held_qty < req.quantity:
            all_materials_satisfied = False

    # 5. Affordability ---
    affordable = ap_have >= ap_cost and anima_have >= anima_cost and all_materials_satisfied

    # 6. Max quality tier from skill cap ---
    max_quality_tier: QualityTier | None = None
    if recipe.skill_trait is not None:
        skill = crafter_character.traits.get_trait_value(recipe.skill_trait.name)
        max_quality_tier = CraftingSkillCap.for_skill(recipe, skill)

    # 6.5. Station status (#1234) ---
    station_status: StationStatus | None = None
    if recipe.requires_station:
        station = _resolve_active_lab_station(crafter_character)
        station_status, station_broken = _station_status_snapshot(station)
        if station_broken:
            affordable = False

    # 7. Failure risk from consequence pool ---
    consequence_rows = list(
        recipe.consequence_rows.all().select_related("consequence", "consequence__outcome_tier")
    )
    failure_risk = [
        CraftingQuoteRisk(
            outcome_name=(
                row.consequence.outcome_tier.name if row.consequence.outcome_tier else None
            ),
            cost_consumption=row.cost_consumption,
            label=row.consequence.label,
        )
        for row in consequence_rows
    ]

    return CraftingQuote(
        costs=CraftingQuoteCost(
            action_points=ap_cost,
            action_points_have=ap_have,
            anima=anima_cost,
            anima_have=anima_have,
            materials=tuple(material_rows),
        ),
        affordable=affordable,
        max_quality_tier=max_quality_tier,
        failure_risk=tuple(failure_risk),
        station_status=station_status,
    )


def _resolve_recipe_for_run(
    *,
    kind: CraftingRecipeKind,
    output_overrides: dict | None = None,
) -> CraftingRecipe:
    """Resolve the recipe for ``kind`` for a crafting run.

    For ``ITEM_CREATE``, the output template is pulled from ``output_overrides``.
    Raises ``CraftingNotConfigured`` when no recipe exists or it lacks a check_type.
    """
    try:
        if kind == CraftingRecipeKind.ITEM_CREATE:
            output_template = (output_overrides or {}).get("output_template")
            recipe = CraftingRecipe.objects.get(kind=kind, output_item_template=output_template)
        else:
            recipe = CraftingRecipe.objects.get(kind=kind)
    except CraftingRecipe.DoesNotExist as exc:
        raise CraftingNotConfigured from exc
    if recipe.check_type is None:
        raise CraftingNotConfigured
    return recipe


def _check_recipe_knowledge(
    recipe: CraftingRecipe,
    crafter_character: ObjectDB,
) -> None:
    """Enforce the recipe-knowledge gate (#2242).

    A gated recipe needs a learned pattern; raises ``RecipeNotKnown`` when the
    crafter has no sheet or does not know the recipe.
    """
    if not recipe.requires_knowledge:
        return
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.items.crafting.knowledge import character_knows_recipe  # noqa: PLC0415
    from world.items.exceptions import RecipeNotKnown  # noqa: PLC0415

    crafter_sheet = CharacterSheet.objects.filter(character=crafter_character).first()
    if crafter_sheet is None or not character_knows_recipe(crafter_sheet, recipe):
        raise RecipeNotKnown


def _gate_station(
    recipe: CraftingRecipe,
    crafter_character: ObjectDB,
) -> LabStationDetails | None:
    """Resolve and validate the Lab station when ``recipe.requires_station`` (#1234).

    Raises ``CraftingStationRequired`` if none is installed, or
    ``CraftingStationBroken`` if at 0 durability. Returns the resolved station
    (or None when no station is required).
    """
    if not recipe.requires_station:
        return None
    station = _resolve_active_lab_station(crafter_character)
    if station is None:
        raise CraftingStationRequired
    if station.is_broken:
        raise CraftingStationBroken
    return station


def _resolve_crafter_sheet(
    crafter_character: ObjectDB,
    item_instance: ItemInstance | None,
) -> CharacterSheet:
    """Return the crafter's CharacterSheet from the item or the character."""
    if item_instance is not None:
        return item_instance.holder_character_sheet
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    return CharacterSheet.objects.get(character=crafter_character)


def _apply_station_wear(station: LabStationDetails | None) -> None:
    """Decrement the station's durability by 1, unconditionally (#1234)."""
    if station is None:
        return
    station.durability = max(0, station.durability - 1)
    station.save(update_fields=["durability"])


def _record_crafted_recipe(
    *,
    recipe: CraftingRecipe,
    crafter_character: ObjectDB,
    item_instance: ItemInstance | None,
    row: object | None,
    tier: QualityTier | None,
) -> CraftedItemRecipe | None:
    """Record the recipe on the item (#1567) and award masterwork renown (#2243).

    For ``ITEM_CREATE``, ``row`` is the newly created ItemInstance; for attach
    kinds, ``row`` is the attachment and ``item_instance`` is the item it was
    attached to.
    """
    if row is None:
        return None
    target_item = item_instance if item_instance is not None else row
    crafted_recipe, _ = CraftedItemRecipe.objects.update_or_create(
        item_instance=target_item,
        recipe=recipe,
        defaults={"quality_tier": tier},
    )
    # Invalidate the wearer's equipped_items handler cache if the item is
    # currently equipped — same pattern as attach_facet_to_item.
    for equipped in EquippedItem.objects.filter(item_instance=target_item):
        equipped.character.equipped_items.invalidate()

    # A masterwork-quality craft makes its maker a little famous (#2243).
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.items.crafting.reward import (  # noqa: PLC0415
        award_masterwork_renown,
        is_masterwork,
    )

    crafter_sheet = CharacterSheet.objects.filter(character=crafter_character).first()
    if tier is not None and is_masterwork(tier) and crafter_sheet is not None:
        award_masterwork_renown(
            crafter_character_sheet=crafter_sheet,
            tier=tier,
            item_label=str(target_item.template),
        )
    return crafted_recipe


@transaction.atomic
def run_crafting_recipe(  # noqa: PLR0913
    *,
    kind: CraftingRecipeKind,
    crafter_account: AccountDB,
    crafter_character: ObjectDB,
    item_instance: ItemInstance | None = None,
    target: object | None = None,
    output_overrides: dict | None = None,
) -> CraftRunResult:
    """Run a crafting attempt end-to-end for ``kind`` against ``target``.

    Pipeline (all inside one transaction):

    1. Resolve the recipe for ``kind``; raise ``CraftingNotConfigured`` if it is
       missing or has no ``check_type``. For ITEM_CREATE, resolve by
       ``(kind, output_item_template)`` from ``output_overrides``.
    2. Pre-validate via the kind's handler — BEFORE rolling, so a
       full/duplicate item never wastes a roll.
    3. Station gate (#1234) — if ``recipe.requires_station``, resolve the active
       Lab station in the crafter's room; raise ``CraftingStationRequired`` if
       none is installed, or ``CraftingStationBroken`` if it is at 0 durability.
    4. Stage and assert affordability of AP / Anima / materials. Raises
       ``CraftingCostUnaffordable`` before any roll occurs.
    5. Roll the recipe's check.
    6. Station wear (#1234) — if a station was resolved in step 3, decrement its
       durability by 1, unconditionally (regardless of roll outcome).
    7. Select a weighted consequence from the recipe's pool for the rolled tier.
    8. Consume cost per the selected consequence's consumption policy (or the
       recipe default when the tier has no authored consequence).
    9. Apply the consequence's effects.
    10. On sufficient success level, resolve the skill-capped quality tier and
        apply via the handler (attach for FACET/STYLE, create for ITEM_CREATE).

    Args:
        kind: Which recipe drives this attempt.
        crafter_account: The account performing the craft (provenance).
        crafter_character: The ObjectDB whose traits roll the check + hold AP/Anima.
        item_instance: The item receiving the attachment (None for ITEM_CREATE).
        target: The Facet or Style to attach (None for ITEM_CREATE).
        output_overrides: Dict for ITEM_CREATE carrying output_template,
            custom_name, custom_description. None for attach kinds.

    Returns:
        A ``CraftRunResult`` describing the outcome.

    Raises:
        CraftingNotConfigured: No recipe for ``kind``, or it has no ``check_type``.
        CraftingStationRequired: The recipe requires a station and none is
            installed in the crafter's room.
        CraftingStationBroken: The recipe requires a station and the one
            installed in the crafter's room is at 0 durability.
        CraftingCostUnaffordable: The crafter cannot afford the recipe cost.
    """
    # --- 1. Resolve the recipe ---
    recipe = _resolve_recipe_for_run(kind=kind, output_overrides=output_overrides)

    # Recipe-knowledge gate (#2242) — a gated recipe needs a learned pattern.
    _check_recipe_knowledge(recipe, crafter_character)

    # --- 2. Pre-validate (never waste a roll) ---
    handler = get_handler(kind)
    handler.pre_validate(
        item_instance=item_instance, target=target, output_overrides=output_overrides
    )

    # --- 3. Station gate (#1234) — before affordability-staging ---
    station = _gate_station(recipe, crafter_character)

    # --- 4. Stage + assert affordability (before rolling) ---
    crafter_sheet = _resolve_crafter_sheet(crafter_character, item_instance)
    staged = stage_and_assert_affordable(
        recipe=recipe,
        crafter_character=crafter_character,
        crafter_character_sheet=crafter_sheet,
    )

    # --- 5. Roll ---
    check_result = perform_check(crafter_character, recipe.check_type, recipe.base_difficulty)

    # --- 6. Station wear (#1234) — unconditional, regardless of roll outcome ---
    _apply_station_wear(station)

    # --- 7. Select a weighted consequence for the rolled tier ---
    rows = list(
        recipe.consequence_rows.all().select_related("consequence", "consequence__outcome_tier")
    )
    rows_by_id = {r.consequence_id: r for r in rows}
    weighted = [
        WeightedConsequence(
            consequence=r.consequence,
            weight=(r.weight_override if r.weight_override is not None else r.consequence.weight),
            character_loss=r.consequence.character_loss,
        )
        for r in rows
    ]
    pending = select_consequence_from_result(crafter_character, check_result, weighted)
    selected = pending.selected_consequence
    row_for_selected = rows_by_id.get(selected.pk)
    consumption = (
        row_for_selected.cost_consumption
        if row_for_selected is not None
        else recipe.default_cost_consumption
    )
    consequence_label = selected.label

    # --- 8. Consume cost per the selected consumption policy ---
    consumed = consume_cost(
        crafter_character=crafter_character,
        staged=staged,
        consumption=consumption,
    )

    # --- 9. Apply the consequence's effects ---
    apply_resolution(pending, ResolutionContext(character=crafter_character))

    # --- 10. Resolve quality + apply via the handler on sufficient success ---
    if check_result.success_level >= recipe.min_success_level:
        tier = resolve_capped_tier(
            recipe=recipe,
            crafter_character=crafter_character,
            check_result=check_result,
        )
        # Thread the crafter_character into output_overrides so ItemCreateHandler
        # can resolve the CharacterSheet for provenance stamping.
        if output_overrides is not None:
            output_overrides["crafter_character"] = crafter_character
        row = handler.apply(
            crafter_account=crafter_account,
            item_instance=item_instance,
            target=target,
            quality_tier=tier,
            output_overrides=output_overrides,
        )
        attached = True
    else:
        tier = None
        row = None
        attached = False

    # --- 10b. Record the recipe on the item (#1567) ---
    crafted_recipe = (
        _record_crafted_recipe(
            recipe=recipe,
            crafter_character=crafter_character,
            item_instance=item_instance,
            row=row,
            tier=tier,
        )
        if attached
        else None
    )

    return CraftRunResult(
        attached=attached,
        outcome=check_result.outcome,
        row=row,
        quality_tier=tier,
        consumed=consumed,
        consequence_label=consequence_label,
        crafted_recipe=crafted_recipe,
    )
