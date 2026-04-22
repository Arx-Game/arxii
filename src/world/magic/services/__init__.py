"""Magic system service functions (thematic submodule split — Scope 6 §4.4).

Public surface is preserved for the flat-module era: importers that use
``from world.magic.services import <name>`` continue to work unchanged.
Submodules:

- ``aura``        — affinity breakdown, aura percentage calculations
- ``anima``       — anima deduction (and future ritual / regen services)
- ``techniques``  — runtime-stat resolution and ``use_technique`` orchestration
- ``alterations`` — Mage Scar pending / resolution / library services
- ``soulfray``    — severity math, stage warnings, accumulation, mishap rider
- ``resonance``   — resonance currency earn / spend / pull services
- ``threads``     — weaving, thread queries, cap/lock math, VITAL_BONUS routing

Private helpers (leading underscore) are re-exported here only when external
callers (outside the ``world.magic.services`` package) import them via
``from world.magic.services import _name``. Other private helpers stay
module-local — import them from their submodule directly.
"""

from world.magic.services.alterations import (
    create_pending_alteration,
    get_library_entries,
    has_pending_alterations,
    resolve_pending_alteration,
    staff_clear_alteration,
    validate_alteration_resolution,
)
from world.magic.services.anima import deduct_anima
from world.magic.services.aura import (
    calculate_affinity_breakdown,
    get_aura_percentages,
)
from world.magic.services.resonance import (
    _anchor_in_action,  # external: world.magic.tests.test_pull_service
    grant_resonance,
    preview_resonance_pull,
    resolve_pull_effects,
    spend_resonance_for_imbuing,
    spend_resonance_for_pull,
)
from world.magic.services.soulfray import (
    calculate_soulfray_severity,
    get_soulfray_warning,
    select_mishap_pool,
)
from world.magic.services.techniques import (
    calculate_effective_anima_cost,
    get_runtime_technique_stats,
    use_technique,
)
from world.magic.services.threads import (
    _typeclass_path_in_registry,  # external: world.magic.models.threads + weaving
    accept_thread_weaving_unlock,
    apply_damage_reduction_from_threads,
    compute_anchor_cap,
    compute_effective_cap,
    compute_path_cap,
    compute_thread_weaving_xp_cost,
    cross_thread_xp_lock,
    imbue_ready_threads,
    near_xp_lock_threads,
    recompute_max_health_with_threads,
    threads_blocked_by_cap,
    update_thread_narrative,
    weave_thread,
)

__all__ = [
    # Re-exported private helpers (external callers exist)
    "_anchor_in_action",
    "_typeclass_path_in_registry",
    # threads
    "accept_thread_weaving_unlock",
    "apply_damage_reduction_from_threads",
    # aura
    "calculate_affinity_breakdown",
    # techniques
    "calculate_effective_anima_cost",
    # soulfray
    "calculate_soulfray_severity",
    "compute_anchor_cap",
    "compute_effective_cap",
    "compute_path_cap",
    "compute_thread_weaving_xp_cost",
    # alterations
    "create_pending_alteration",
    "cross_thread_xp_lock",
    # anima
    "deduct_anima",
    "get_aura_percentages",
    "get_library_entries",
    "get_runtime_technique_stats",
    "get_soulfray_warning",
    # resonance
    "grant_resonance",
    "has_pending_alterations",
    "imbue_ready_threads",
    "near_xp_lock_threads",
    "preview_resonance_pull",
    "recompute_max_health_with_threads",
    "resolve_pending_alteration",
    "resolve_pull_effects",
    "select_mishap_pool",
    "spend_resonance_for_imbuing",
    "spend_resonance_for_pull",
    "staff_clear_alteration",
    "threads_blocked_by_cap",
    "update_thread_narrative",
    "use_technique",
    "validate_alteration_resolution",
    "weave_thread",
]
