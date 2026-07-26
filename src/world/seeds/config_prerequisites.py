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


def _ships_rows() -> None:
    """The `speed` CapabilityType `materialize_ship_as_battle_vehicle` FKs by name.

    Per-resonance sanctum capability names (`battle_bridge.py:101`,
    `f"sanctum_{resonance.name.lower()}"`) are derived from `Resonance` rows at
    runtime, not a fixed literal — deliberately NOT registered here; that set cannot
    be enumerated at press time and is not a code-required row.
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
    "spread": _spread_rows,
    "vitals": _vitals_rows,
    "conditions": _conditions_rows,
    "dreams": _dreams_rows,
    "alterations": _alterations_rows,
    "locations": _locations_rows,
    "combat_stats": _combat_stats_rows,
    "projects": _projects_rows,
    "ships": _ships_rows,
}
