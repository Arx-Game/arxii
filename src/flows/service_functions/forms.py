"""Flow-callable wrappers for the forms service.

Thin wrappers that accept string-name lookups so FlowStepDefinition
parameters can reference forms and alternate selves by name rather than
by PK or model instance.  These are NOT production service functions —
they exist solely to bridge the flow parameter-resolution layer
(which resolves ``@variable`` references and passes raw strings through)
with production services that require model instances.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def _unwrap_objectdb(obj: ObjectDB) -> ObjectDB:
    """Unwrap a BaseState wrapper to its underlying ObjectDB.

    The flow execution layer may pass a ``BaseState`` (e.g., ``CharacterState``)
    rather than a raw ``ObjectDB`` when the parameter is resolved via
    ``_resolve_service_param``.  ``BaseState`` exposes the raw object on its
    ``.obj`` attribute; raw ``ObjectDB`` instances have no such attribute.

    Args:
        obj: A raw ``ObjectDB`` or a ``BaseState`` wrapping one.

    Returns:
        The underlying ``ObjectDB``.
    """
    return getattr(obj, "obj", obj)  # noqa: GETATTR_LITERAL


def flow_trigger_transformation(
    *,
    character: ObjectDB,
    form_name: str,
    instance_value: float = 1.0,
) -> None:
    """Resolve a character's AlternateSelf grant for a named form and assume it.

    Flow-callable wrapper around ``world.forms.services.transformation.trigger_transformation``.
    The trigger author picks which form the involuntary shift drives toward (``form_name``);
    this wrapper resolves the matching ``AlternateSelf`` grant for ``(character.sheet_data, form)``
    and invokes the transformation seam. Raises ``AlternateSelfActiveError`` if a *different*
    alt-self is already active (the strictly-one-active invariant — the author should only target
    an involuntary shift to the rage-form).

    Args:
        character: The ObjectDB character forced to shift (or a BaseState wrapping one).
        form_name: The ``CharacterForm.name`` to assume.
        instance_value: Per-instance multiplier (default 1.0). A trigger may pass a higher
            value to model a more violent onset.

    Raises:
        AlternateSelfActiveError: if a different alt-self is already active.
        CharacterSheet.DoesNotExist: if the character has no CharacterSheet.
        AlternateSelf.DoesNotExist: if the character has no grant for ``form_name``.
    """
    from world.forms.models import AlternateSelf, CharacterForm  # noqa: PLC0415
    from world.forms.services.transformation import trigger_transformation  # noqa: PLC0415

    raw_character = _unwrap_objectdb(character)
    sheet = raw_character.sheet_data
    form = CharacterForm.objects.get(name=form_name)
    alt = AlternateSelf.objects.get(character=sheet, form=form)
    trigger_transformation(sheet, alt, cause="trigger", instance_value=instance_value)


hooks = {
    "trigger_transformation": flow_trigger_transformation,
}
