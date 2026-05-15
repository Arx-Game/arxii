"""Flow-callable wrapper for the resonance-environment primitive.

Thin adapter that accepts the TECHNIQUE_CAST payload variables (caster, technique),
unwraps BaseState wrappers to raw ObjectDB, resolves the caster's location, calls
``evaluate_resonance_environment``, and returns a flat dict of scalar values that the
flow engine unpacks into individual flow variables (dict-return auto-unpack path —
no ``result_variable`` in the step parameters).

The returned dict keys become top-level flow variables consumed by subsequent
``EVALUATE_EQUALS`` conditional steps:

    ``resonance_valence``       — "aligned" | "opposed" | "" (inert)
    ``resonance_kind``          — "amplify" | "reject" | "repel" | "corrupt" | "" (inert)
    ``resonance_magnitude``     — int ≥ 0 (0 = inert)
    ``resonance_direction``     — ResonanceDirection value string
    ``resonance_backfire_difficulty`` — int; backfire_base + round(magnitude * per_magnitude)
                                        (0 when inert; used by the opposed-pole perform_check step)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.magic.models.techniques import Technique


def _unwrap_objectdb(obj: object) -> DefaultObject:
    """Unwrap a BaseState wrapper to its underlying Evennia object.

    The flow execution layer may pass a ``BaseState`` (e.g., ``CharacterState``)
    rather than a raw Evennia object when the parameter is resolved via
    ``_resolve_service_param``.  ``BaseState`` exposes the raw object on its
    ``.obj`` attribute; raw Evennia objects have no such attribute.

    Args:
        obj: A raw Evennia ``DefaultObject`` (or its ObjectDB proxy) or a
            ``BaseState`` wrapping one.

    Returns:
        The underlying Evennia object.
    """
    from evennia.objects.objects import DefaultObject as _DefaultObject  # noqa: PLC0415

    return cast(_DefaultObject, getattr(obj, "obj", obj))  # noqa: GETATTR_LITERAL — BaseState.obj


def flow_evaluate_resonance_environment(
    *,
    caster: object,
    technique: Technique | None = None,
    **kwargs: object,
) -> dict[str, object]:
    """Evaluate resonance-environment effect and return flow-variable dict.

    Flow-callable adapter for ``evaluate_resonance_environment``.  Accepts
    ``caster`` as either a raw ``ObjectDB`` or a ``BaseState`` wrapper, unwraps
    it, resolves the caster's current room, and delegates to the primitive.

    The returned dict is stored as individual top-level flow variables by the
    flow engine's dict-return auto-unpack path (no ``result_variable`` key in
    the step parameters).  Subsequent ``EVALUATE_EQUALS`` steps branch on
    ``resonance_valence``, ``resonance_kind``, etc. directly.

    ``resonance_backfire_difficulty`` is precomputed here so that the flow
    engine's conditional steps (which cannot do arithmetic) can pass it
    directly to ``flow_perform_check`` as ``@resonance_backfire_difficulty``.

    Args:
        caster: The casting character — raw ``ObjectDB`` or ``BaseState`` wrapper.
        technique: The ``Technique`` being cast; ``None`` for presence-time evaluation.
        **kwargs: Ignored extra keyword arguments (defensive; flow may pass extras).

    Returns:
        Dict with keys ``resonance_valence``, ``resonance_kind``,
        ``resonance_magnitude``, ``resonance_direction``,
        ``resonance_backfire_difficulty``.
    """
    from world.magic.services.resonance_environment import (  # noqa: PLC0415
        evaluate_resonance_environment,
        get_resonance_environment_config,
    )

    caster_obj: DefaultObject = _unwrap_objectdb(caster)
    room = getattr(caster_obj, "location", None)  # noqa: GETATTR_LITERAL — Evennia ObjectDB.location

    if room is None:
        # Caster has no location (e.g., in limbo / not yet placed) — inert.
        return {
            "resonance_valence": "",
            "resonance_kind": "",
            "resonance_magnitude": 0,
            "resonance_direction": "",
            "resonance_backfire_difficulty": 0,
        }

    effect = evaluate_resonance_environment(
        caster=caster_obj,
        room=room,
        technique=technique,
    )

    config = get_resonance_environment_config()
    backfire_difficulty = 0
    if effect.magnitude > 0:
        backfire_difficulty = config.backfire_base_difficulty + round(
            effect.magnitude * float(config.backfire_difficulty_per_magnitude)
        )

    return {
        "resonance_valence": effect.valence,
        "resonance_kind": effect.kind,
        "resonance_magnitude": effect.magnitude,
        "resonance_direction": effect.direction,
        "resonance_backfire_difficulty": backfire_difficulty,
    }
