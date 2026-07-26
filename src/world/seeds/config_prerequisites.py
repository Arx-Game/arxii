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

See ADR-0169, and ADR-0168 for the model-level rule this carves out of.
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


CONFIG_PREREQUISITES: dict[str, Callable[[], None]] = {
    # FIRST: lore-repo Technique fixtures FK this ActionTemplate by natural key, and
    # load_world_content's deferred-retry loop cannot conjure config rows (#2474).
    "technique_cast": _technique_cast_rows,
    "fatigue": _fatigue_rows,
    "fury": _fury_rows,
    "spread": _spread_rows,
}
