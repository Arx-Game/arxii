"""Content rows the code names by string literal, declared in one place (#2724).

A row whose name is a string literal in code is **config**, not authored content: the
code breaks without it. Such rows may still live in ``CONTENT_MODELS`` and still be
exported — ``load_entries`` upserts the authored fixture over the code default, so the
content repo stays the authority and a code default is only ever the floor. What this
module fixes is that the dependency used to be *undeclared*: nothing marked
``fatigue_willpower`` as load-bearing, so a staff member tidying ``checktype.json``
would delete it and silently revert its tuning.

Each entry runs **before** the content load (``world.seeds.database.load_content_first``)
so a lore fixture always wins, and so entries land outside
``world.seeds.tests.test_no_content_slop``'s measurement window — that guard snapshots
between the content load and the cluster loop, and its ratchet stays empty.

Shaped like :data:`world.seeds.clusters.CLUSTER_SEEDERS`: a name -> idempotent zero-arg
callable. Members are the modules' own existing ``_ensure_*`` helpers, wrapped where they
take arguments. Registering a helper here does NOT stop its gameplay call site working —
those calls stay, stay idempotent, and remain the self-healing path if a row is deleted.

See ADR-0171, and ADR-0168 for the model-level rule this carves out of.
"""

from __future__ import annotations

from collections.abc import Callable


def _fatigue_rows() -> None:
    """CheckTypes + DamageType `world.fatigue.services` rolls by name."""
    from world.fatigue.constants import FATIGUE_ENDURANCE_STAT  # noqa: PLC0415
    from world.fatigue.services import (  # noqa: PLC0415
        _ensure_endurance_check_type,
        _ensure_exhaustion_damage_type,
        _ensure_willpower_check_type,
    )

    _ensure_willpower_check_type()
    _ensure_exhaustion_damage_type()
    for category in FATIGUE_ENDURANCE_STAT:
        _ensure_endurance_check_type(category)


def _fury_rows() -> None:
    """The fury control-retention CheckType `resolve_fury` rolls (`fury.py:157`).

    The trait is not a literal — it is `FuryConfig.check_trait`, a DB-configurable
    column — so the prerequisite ensures the row for whatever the config currently
    names. Changing the config at runtime creates the new row on next use, exactly
    as before; this only guarantees the configured one exists after a press.
    """
    from world.magic.services.fury import (  # noqa: PLC0415
        _ensure_fury_check_type,
        get_fury_config,
    )

    _ensure_fury_check_type(get_fury_config().check_trait)


def _moon_rows() -> None:
    """The `moon_control` CheckType `reconcile_moon_pull` rolls by name (#2845)."""
    from world.species.moon_sensitivity import (  # noqa: PLC0415
        _ensure_moon_control_check_type,
    )

    _ensure_moon_control_check_type()


def _spread_rows() -> None:
    """Performance/Persuasion Traits + Skills the `spread a tale` deed needs."""
    from world.societies.spread_services import ensure_spread_skills  # noqa: PLC0415

    ensure_spread_skills()


def _technique_cast_rows() -> None:
    """The shared "Technique Cast" ActionTemplate lore Technique fixtures FK by name."""
    from world.magic.seeds_cast import ensure_technique_cast_content  # noqa: PLC0415

    ensure_technique_cast_content()


def _vitals_rows() -> None:
    """Survival CheckCategory/CheckType rows `process_damage_consequences` rolls by name.

    These are content-repo-owned (#2698): the helpers use `authored_or_sample`, which
    looks up rather than invents unless `SEED_SAMPLE_CONTENT` is on, so this
    prerequisite composes an already-authored row rather than fabricating one.
    """
    from world.vitals.services import (  # noqa: PLC0415
        _ensure_death_check_type,
        _ensure_endurance_check_type,
        _ensure_survival_category,
    )

    _ensure_survival_category()
    _ensure_endurance_check_type()
    _ensure_death_check_type()


def _conditions_rows() -> None:
    """Poison/Charm/at-will-shifting condition & capability rows other systems FK by name.

    `ensure_conditions_content` is itself the aggregate entry point (it already calls
    `ensure_poison_content`), so calling it alone covers both.
    """
    from world.conditions.services import ensure_conditions_content  # noqa: PLC0415

    ensure_conditions_content()


def _dreams_rows() -> None:
    """Dream condition templates + DreamPerilConfig `resolve_dream_peril_collapse` needs."""
    from world.dreams.conditions import ensure_dream_conditions  # noqa: PLC0415

    ensure_dream_conditions()


def _alterations_rows() -> None:
    """The Magical Alteration ConditionCategory Mage Scar rows FK by name."""
    from world.magic.services.alterations import (  # noqa: PLC0415
        _get_or_create_alteration_category,
    )

    _get_or_create_alteration_category()


def _locations_rows() -> None:
    """The ap-regen ModifierCategory/Targets `recompute_comfort_regen_modifier` FKs by name."""
    from world.locations.comfort_effect import _ap_regen_targets  # noqa: PLC0415

    _ap_regen_targets()


def _combat_stats_rows() -> None:
    """The combat achievement StatDefinition rows `increment_combat_counter` FKs by key."""
    from world.combat.achievement_counters import (  # noqa: PLC0415
        _STAT_KEY_DISPLAY,
        _get_or_create_stat_def,
    )

    for key in _STAT_KEY_DISPLAY:
        _get_or_create_stat_def(key)


def _projects_rows() -> None:
    """The `projects.total_contributed` StatDefinition `_increment_contribution_stat` FKs."""
    from world.projects.services import _ensure_contribution_stat_def  # noqa: PLC0415

    _ensure_contribution_stat_def()


def _crafting_rows() -> None:
    """Kind-keyed `CraftingRecipe` rows `run_crafting_recipe` needs a non-null
    `check_type` to resolve (#3006).

    FACET_ATTACH / STYLE_ATTACH / GEM_CUT each need exactly one row
    (`output_item_template=None`) before any crafting attempt of that kind can
    resolve — Task 1 gave `CraftingRecipe.name` a natural key so a lore fixture can
    upsert over these, but nothing seeded a floor row for the Big Button to press.
    The "Enchanting" CheckType/category names match the test-only
    `wire_enchanting_crafting` factory chain (`world.items.factories:322`), so a
    fixture or gameplay lookup by that name resolves to the same row rather than
    minting a duplicate. Tuning values (`base_difficulty`/`success_level_step`/
    `min_success_level`) mirror what `wire_enchanting_crafting` sets for
    FACET_ATTACH/STYLE_ATTACH; GEM_CUT has no such precedent, so it takes the same
    values as the model's own field defaults.

    Unconditionally re-attaches `check_type` when a pre-existing row (e.g. fixture-
    supplied) has it null — same `if created:` trap fatigue/dreams guard against
    above: a bare fixture row must not survive this prerequisite still disabled.

    Also wires the FACET_ATTACH reagent requirement
    (`world.items.seeds_facet_reagents.ensure_facet_attach_reagent_requirement`,
    orphaned since #707 added it with only a test call site) so the facet reagent
    default ships with the recipe it belongs to.

    Unlike `wire_enchanting_crafting`, this entry deliberately creates NO
    `CheckTypeTrait` weight row on `check_type` — trait composition is content,
    authored lore-side (same split as the #2882 CheckTypes). Until a
    `CheckTypeTrait` is authored against "Enchanting", `world.checks.services
    ._calculate_trait_points` finds an empty `check_type.traits` and the seeded
    check contributes zero trait points: checks still resolve (safe), just flat,
    with no skill/stat swing until the content lands.
    """
    from world.checks.models import CheckCategory, CheckType  # noqa: PLC0415
    from world.items.crafting.constants import CraftingRecipeKind  # noqa: PLC0415
    from world.items.crafting.models import CraftingRecipe  # noqa: PLC0415
    from world.items.seeds_facet_reagents import (  # noqa: PLC0415
        ensure_facet_attach_reagent_requirement,
    )

    category, _ = CheckCategory.objects.get_or_create(
        name="Crafting",
        defaults={"description": "Checks rolled to attempt a crafting recipe."},
    )
    check_type, _ = CheckType.objects.get_or_create(
        name="Enchanting",
        category=category,
        defaults={"description": "The enchanting craft: facets, styles, and gem work."},
    )

    recipe_names = {
        CraftingRecipeKind.FACET_ATTACH: "Attach Facet (Enchanting)",
        CraftingRecipeKind.STYLE_ATTACH: "Attach Style (Enchanting)",
        CraftingRecipeKind.GEM_CUT: "Cut Gem (Enchanting)",
    }
    for kind, name in recipe_names.items():
        recipe, created = CraftingRecipe.objects.get_or_create(
            name=name,
            defaults={
                "kind": kind,
                "check_type": check_type,
                "output_item_template": None,
                "base_difficulty": 0,
                "success_level_step": 10,
                "min_success_level": 1,
            },
        )
        if not created and recipe.check_type_id is None:
            recipe.check_type = check_type
            recipe.save(update_fields=["check_type"])
        if kind == CraftingRecipeKind.FACET_ATTACH:
            ensure_facet_attach_reagent_requirement(recipe)


def _provisioning_rows() -> None:
    """The Cooking CheckType (+ Brewing) and QualityTier/AccentLevel ladders (#3006).

    Lore-repo ITEM_CREATE recipe fixtures FK the "Cooking" CheckType and the
    QualityTier ladder by natural key, but both used to be created only by
    `seed_provisioning_content()`, a `CLUSTER_SEEDERS` entry that runs AFTER
    `load_world_content()`. On a fresh one-shot seed the recipe fixtures would
    defer and drop — the #2882 ordering trap this registry exists to prevent. Calls
    the same `provisioning_checks` helpers `seed_provisioning_content()` still
    calls (idempotent double-run), rather than duplicating their bodies.
    """
    from world.seeds.provisioning_checks import (  # noqa: PLC0415
        _ensure_cooking_check,
        _ensure_quality_tiers,
    )

    _ensure_cooking_check()
    _ensure_quality_tiers()


def _ships_rows() -> None:
    """The `speed` CapabilityType `materialize_ship_as_battle_vehicle` FKs by name.

    This is the only capability the ship bridge creates, and it belongs here because
    it IS a fixed literal a code path FKs by name.

    #2724 noted that the bridge also minted a per-resonance `sanctum_<resonance>`
    capability and declined to register it — a set derived from `Resonance` rows at
    runtime cannot be enumerated at press time and is not a code-required row. #2736
    removed that minting outright: sanctum grants now come from authored
    `ThreadPullEffect` rows naming already-authored capabilities, so there is nothing
    left to register or to decline (ADR-0188). Kept as a note because "why isn't the
    sanctum capability here" is a reasonable question to ask of this function.
    """
    from world.conditions.models import CapabilityType  # noqa: PLC0415
    from world.ships.constants import SPEED_CAPABILITY_NAME  # noqa: PLC0415

    CapabilityType.objects.get_or_create(name=SPEED_CAPABILITY_NAME)


CONFIG_PREREQUISITES: dict[str, Callable[[], None]] = {
    # Entries must not rely on each other's side effects — each entry ensures its own
    # dependencies (e.g. any STAT Trait it needs, via world.traits.services
    # .ensure_stat_trait). Dict order is not a dependency graph; only "technique_cast"
    # has a real ordering constraint, documented below.
    # FIRST: lore-repo Technique fixtures FK this ActionTemplate by natural key, and
    # load_world_content's deferred-retry loop cannot conjure config rows (#2474).
    "technique_cast": _technique_cast_rows,
    "fatigue": _fatigue_rows,
    "fury": _fury_rows,
    "moon": _moon_rows,
    "spread": _spread_rows,
    "vitals": _vitals_rows,
    "conditions": _conditions_rows,
    "dreams": _dreams_rows,
    "alterations": _alterations_rows,
    "locations": _locations_rows,
    "combat_stats": _combat_stats_rows,
    "projects": _projects_rows,
    "ships": _ships_rows,
    "crafting": _crafting_rows,
    "provisioning": _provisioning_rows,
}
