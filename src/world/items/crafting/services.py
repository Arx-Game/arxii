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
from world.checks.services import perform_check_with_modifiers
from world.checks.types import ResolutionContext
from world.items.crafting.constants import CraftingRecipeKind
from world.items.crafting.cost import StagedCost, consume_cost, stage_and_assert_affordable
from world.items.crafting.models import (
    CraftedItemRecipe,
    CraftingRecipe,
    CraftingSkillCap,
    ItemAccent,
)
from world.items.crafting.quality import resolve_capped_tier
from world.items.crafting.registry import get_handler
from world.items.exceptions import (
    CategoryRequirementsNotQuotable,
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
    from world.checks.types import CheckResult
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
    accents: tuple[ItemAccent, ...] = ()


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
    ap_have = pool.current if pool is not None else 0

    # 3. Anima availability ---
    anima_cost = recipe.anima_cost
    anima_row = CharacterAnima.objects.filter(character=crafter_character_sheet).first()
    anima_have = anima_row.current if anima_row is not None else 0

    # 4. Materials availability ---
    requirements = list(
        recipe.material_requirements.all().select_related(
            "item_template", "min_quality_tier", "material_category"
        )
    )
    # Category-requirement quotes need the quote API + FE types to represent a
    # material class (no single template) in each per-row shape — deferred to the
    # quote-surface work. Crafting *execution* (stage_and_assert_affordable)
    # already supports category requirements; no seeded recipe uses them yet, so
    # this is a forward guard, not a live path.
    if any(r.material_category_id for r in requirements):
        raise CategoryRequirementsNotQuotable
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
    _gate_required_feature(recipe, crafter_character)
    if not recipe.requires_station:
        return None
    station = _resolve_active_lab_station(crafter_character)
    if station is None:
        raise CraftingStationRequired
    if station.is_broken:
        raise CraftingStationBroken
    return station


def _gate_required_feature(recipe: CraftingRecipe, crafter_character: ObjectDB) -> None:
    """Require an active room feature of ``recipe.required_feature_kind`` (#2862).

    Generalizes the LAB hardcode: a recipe may name any RoomFeatureKind (e.g.
    the Workshop of Iniquity gating illicit refinement). Presence-only — no
    durability concept outside the LAB path.
    """
    if recipe.required_feature_kind_id is None:
        return
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.room_features.models import RoomFeatureInstance  # noqa: PLC0415

    room = crafter_character.location
    try:
        room_profile = room.room_profile if room is not None else None
    except (AttributeError, ObjectDoesNotExist):
        room_profile = None
    if room_profile is None:
        raise CraftingStationRequired
    present = (
        RoomFeatureInstance.objects.filter(
            room_profile=room_profile,
            feature_kind_id=recipe.required_feature_kind_id,
        )
        .active()
        .exists()
    )
    if not present:
        raise CraftingStationRequired


def _resolve_crafter_sheet(
    crafter_character: ObjectDB,
    item_instance: ItemInstance | None,
) -> CharacterSheet:
    """Return the crafter's CharacterSheet from the item or the character."""
    if item_instance is not None:
        return item_instance.holder_character_sheet
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    return CharacterSheet.objects.get(character=crafter_character)


def _validate_accent_targets(
    accent_targets: list | None,
    item_instance: ItemInstance | None = None,
    template: object | None = None,
) -> list:
    """Reject non-styleable, inactive, duplicate, excluded, or misplaced axes.

    Exclusion pairs (#2886, e.g. Dramatic ⊥ Unassuming) are checked across the
    request AND the item's existing accents when a host item is given; the
    archetype allowlist (no stealthy jewelry) is checked against the piece's
    ``gear_archetype`` when a template is resolvable.
    """
    from world.items.crafting.models import (  # noqa: PLC0415
        AccentArchetypeAllowance,
        AccentExclusion,
        ItemAccent,
    )
    from world.items.exceptions import InvalidAccentTarget  # noqa: PLC0415

    if template is None and item_instance is not None:
        template = item_instance.template
    targets = list(accent_targets or [])
    seen_pks = set()
    for target in targets:
        if not target.is_styleable or not target.is_active or target.pk in seen_pks:
            raise InvalidAccentTarget
        if template is not None and not AccentArchetypeAllowance.permits(
            target, template.gear_archetype
        ):
            raise InvalidAccentTarget
        seen_pks.add(target.pk)
    if seen_pks:
        combined = set(seen_pks)
        if item_instance is not None:
            combined |= set(
                ItemAccent.objects.filter(item_instance=item_instance).values_list(
                    "target_id", flat=True
                )
            )
        if AccentExclusion.conflict_exists(list(combined)) is not None:
            raise InvalidAccentTarget
    return targets


def _accent_rung_for_score(score: int, *, cap: int) -> object | None:
    """Resolve an accent-check score to the AccentLevel it realizes.

    Rung = ``score // ACCENT_SCORE_PER_LEVEL`` clamped to [1, cap]; the row
    returned is the highest ladder level ≤ that rung (short-ladder tolerant).
    Returns None when the score doesn't reach rung 1.
    """
    from world.items.crafting.constants import ACCENT_SCORE_PER_LEVEL  # noqa: PLC0415
    from world.items.models import AccentLevel  # noqa: PLC0415

    rung = min(score // ACCENT_SCORE_PER_LEVEL, cap)
    if rung < 1:
        return None
    return AccentLevel.objects.filter(level__lte=rung).order_by("-level").first()


def _thread_check_contributions(crafter_character: ObjectDB, recipe: CraftingRecipe) -> list:
    """Woven threads are an edge on the roll, not just the ceiling (#2886).

    ``THREAD_CRAFT_CHECK_BONUS`` per active TRAIT thread on the recipe's
    skill, delivered as a CHARACTER contribution on the craft AND accent
    checks — the Gifted artisan's hands are simply better, exactly as the
    thread caps already say their ceiling is higher.
    """
    from world.checks.constants import ModifierSourceKind  # noqa: PLC0415
    from world.checks.types import ModifierContribution  # noqa: PLC0415
    from world.items.crafting.constants import THREAD_CRAFT_CHECK_BONUS  # noqa: PLC0415
    from world.items.crafting.quality import thread_count_for_skill  # noqa: PLC0415

    threads = thread_count_for_skill(crafter_character, recipe.skill_trait)
    if threads <= 0:
        return []
    return [
        ModifierContribution(
            source_kind=ModifierSourceKind.CHARACTER,
            source_label="Woven threads",
            value=threads * THREAD_CRAFT_CHECK_BONUS,
        )
    ]


def _accent_penalty_contributions(accent_count: int) -> list:
    """The ambition penalty (#2886): −ACCENT_CHECK_PENALTY per accent chosen.

    Applied to the craft roll AND every accent roll — each accent worked in
    makes the whole piece harder to realize well, smoothly (points, not the
    rank-quantized difficulty ladder).
    """
    from world.checks.constants import ModifierSourceKind  # noqa: PLC0415
    from world.checks.types import ModifierContribution  # noqa: PLC0415
    from world.items.crafting.constants import ACCENT_CHECK_PENALTY  # noqa: PLC0415

    if accent_count <= 0:
        return []
    return [
        ModifierContribution(
            source_kind=ModifierSourceKind.CHARACTER,
            source_label="Accent ambition",
            value=-(ACCENT_CHECK_PENALTY * accent_count),
        )
    ]


def _resolve_accents(
    *,
    recipe: CraftingRecipe,
    crafter_character: ObjectDB,
    target_item: ItemInstance,
    accent_targets: list,
    difficulty: int,
) -> tuple[ItemAccent, ...]:
    """Roll each requested Accent's own check and record what realized (#2878).

    Each Accent rolls at the same (accent-raised) difficulty as the piece
    itself; a roll below the recipe's minimum success level means that intent
    simply didn't take — a masterwork piece with a weak menace roll is a
    story, and a refinement candidate. Realized level is thread-capped
    (``BASE_MAX_ACCENT_LEVEL`` + one per thread on the recipe's skill).
    """
    from world.items.crafting.constants import BASE_MAX_ACCENT_LEVEL  # noqa: PLC0415
    from world.items.crafting.quality import thread_count_for_skill  # noqa: PLC0415
    from world.items.services.crafting import compute_quality_score  # noqa: PLC0415

    cap = BASE_MAX_ACCENT_LEVEL + thread_count_for_skill(crafter_character, recipe.skill_trait)
    accent_contribs = _thread_check_contributions(crafter_character, recipe)
    accent_contribs += _accent_penalty_contributions(len(accent_targets))
    realized: list[ItemAccent] = []
    for target in accent_targets:
        result = perform_check_with_modifiers(
            crafter_character,
            recipe.check_type,
            difficulty,
            specialization=recipe.specialization,
            extra_contributions=accent_contribs or None,
        )
        if result.success_level < recipe.min_success_level:
            continue
        score = compute_quality_score(
            result, step=recipe.success_level_step, min_success_level=recipe.min_success_level
        )
        level = _accent_rung_for_score(score, cap=cap)
        if level is None:
            continue
        accent, _created = ItemAccent.objects.update_or_create(
            item_instance=target_item,
            target=target,
            defaults={"level": level},
        )
        realized.append(accent)
    return tuple(realized)


def _resolve_outcome_tier(
    *,
    kind: CraftingRecipeKind,
    recipe: CraftingRecipe,
    crafter_character: ObjectDB,
    check_result: CheckResult,
    staged: StagedCost,
) -> QualityTier | None:
    """The tier this attempt lands at — a making NEVER fails to create (#2886).

    The prose a player writes into an item is the one unrecoverable
    ingredient, and losing it feels worse than any lost time/AP/coin/
    materials (which the consequence pool still charges). A failed
    ITEM_CREATE therefore lands at the ladder's floor — the player then
    chooses: recycle and retry, or refine it up the long road. Attach kinds
    keep failure semantics (None — nothing is lost there).
    """
    if check_result.success_level >= recipe.min_success_level:
        return resolve_capped_tier(
            recipe=recipe,
            crafter_character=crafter_character,
            check_result=check_result,
            material_grade_bonus=_material_grade_bonus(staged),
        )
    if kind == CraftingRecipeKind.ITEM_CREATE:
        from world.items.models import QualityTier  # noqa: PLC0415

        return QualityTier.objects.order_by("sort_order").first()
    return None


def _material_grade_bonus(staged: StagedCost) -> int:
    """Quantity-weighted mean ``material_grade`` of the staged materials (#2878).

    The grade term is computed from what the craft *draws on* (the staged
    allocations), not what the consequence ultimately consumed — a merciful
    consumption outcome must not change the quality of the finished piece.
    Bucket spends (common-gem bulk, Build 0b) carry no grade.
    """
    total = 0
    weight = 0
    for inst, amount in staged.material_allocations:
        total += inst.template.material_grade * amount
        weight += amount
    if weight == 0:
        return 0
    return round(total / weight)


def _apply_station_wear(station: LabStationDetails | None) -> None:
    """Decrement the station's durability by 1, unconditionally (#1234)."""
    if station is None:
        return
    station.durability = max(0, station.durability - 1)
    station.save(update_fields=["durability"])


def _record_crafted_recipe(
    *,
    recipe: CraftingRecipe,
    item_instance: ItemInstance | None,
    row: object | None,
    tier: QualityTier | None,
) -> CraftedItemRecipe | None:
    """Record the recipe on the item (#1567).

    For ``ITEM_CREATE``, ``row`` is the newly created ItemInstance; for attach
    kinds, ``row`` is the attachment and ``item_instance`` is the item it was
    attached to. Maker/designer credits live on ItemInstance's #2066
    dual-provenance fields (stamped by ItemCreateHandler), never here.
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

    # Fame at first making moved to run_crafting_recipe step 10d (#2878) —
    # it scales with Accents, which resolve after this record step.
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
    accent_targets: list | None = None,
) -> CraftRunResult:
    """Run a crafting attempt end-to-end for ``kind`` against ``target``.

    ``accent_targets`` (#2878) are styleable ``ModifierTarget`` rows the
    crafter chose to work into the piece. Each subtracts
    ``ACCENT_CHECK_PENALTY`` points from every roll and doubles the craft's
    AP/anima cost (#2886 — ambition priced smoothly), then rolls its own
    check after the piece resolves. Credits render from ItemInstance's
    #2066 dual-provenance fields.

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

    # Accent validation (#2878) — before any staging or rolling. Ambition is
    # priced as a POINTS PENALTY on the rolls (#2886 — the rank-quantized
    # difficulty step was a step function; a penalty bites smoothly) plus a
    # per-accent doubling of the craft's AP/anima cost.
    create_template = (output_overrides or {}).get("output_template")
    accents_requested = _validate_accent_targets(
        accent_targets, item_instance, template=create_template
    )
    from world.items.crafting.constants import ACCENT_CRAFT_COST_BASE  # noqa: PLC0415

    difficulty = recipe.base_difficulty
    accent_cost_multiplier = ACCENT_CRAFT_COST_BASE ** len(accents_requested)

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
        cost_multiplier=accent_cost_multiplier,
    )

    # --- 5. Roll (thread edge + accent ambition penalty, #2886) ---
    craft_contribs = _thread_check_contributions(crafter_character, recipe)
    craft_contribs += _accent_penalty_contributions(len(accents_requested))
    check_result = perform_check_with_modifiers(
        crafter_character,
        recipe.check_type,
        difficulty,
        specialization=recipe.specialization,
        extra_contributions=craft_contribs or None,
    )

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

    # --- 10. Resolve quality + apply via the handler ---
    tier = _resolve_outcome_tier(
        kind=kind,
        recipe=recipe,
        crafter_character=crafter_character,
        check_result=check_result,
        staged=staged,
    )
    if tier is not None:
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
        row = None
        attached = False

    # --- 10b. Record the recipe on the item (#1567) ---
    crafted_recipe = (
        _record_crafted_recipe(
            recipe=recipe,
            item_instance=item_instance,
            row=row,
            tier=tier,
        )
        if attached
        else None
    )

    # --- 10c. Roll each requested Accent's own check (#2878) ---
    accents: tuple[ItemAccent, ...] = ()
    accent_host = item_instance if item_instance is not None else row
    if attached and accents_requested and isinstance(accent_host, ItemInstance):
        accents = _resolve_accents(
            recipe=recipe,
            crafter_character=crafter_character,
            target_item=accent_host,
            accent_targets=accents_requested,
            difficulty=difficulty,
        )

    # --- 10d. Fame at first making (#2878, generalizes #2243) ---
    # First making = the ITEM_CREATE path (item_instance None, row is the new
    # instance). Attach/enhancement kinds don't re-fame the original maker.
    if attached and tier is not None and item_instance is None and isinstance(row, ItemInstance):
        from world.items.crafting.reward import award_crafting_fame  # noqa: PLC0415

        award_crafting_fame(
            crafter_persona=row.crafter_persona_display,
            designer_persona=row.designer_persona_display,
            tier=tier,
            accents=accents,
            item_label=str(row.template),
            item_instance=row,
        )

    return CraftRunResult(
        attached=attached,
        outcome=check_result.outcome,
        row=row,
        quality_tier=tier,
        consumed=consumed,
        consequence_label=consequence_label,
        crafted_recipe=crafted_recipe,
        accents=accents,
    )
