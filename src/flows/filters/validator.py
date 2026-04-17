"""Save-time validation of filter DSL against payload dataclass schema.

Walks the filter tree, resolving each `path` against the payload's
dataclass fields. Unknown paths raise ValidationError.

`self.*` paths are not validated — self is resolved at dispatch time
against the handler owner, whose type is not known at save time.
"""

import dataclasses

from django.core.exceptions import ValidationError

from flows.events.payloads import PAYLOAD_FOR_EVENT

# Filter DSL operator keys (must match evaluator.py)
OP_AND = "and"
OP_OR = "or"
OP_NOT = "not"
OP_PATH = "path"
SELF_PREFIX = "self."


def validate_filter_schema(filter_spec: dict | None, *, event_name: str) -> None:
    """Validate filter_spec against payload dataclass schema for event.

    Args:
        filter_spec: Filter DSL dict tree or None
        event_name: Event name key to look up in PAYLOAD_FOR_EVENT

    Raises:
        ValidationError: If unknown event or path not in payload schema
    """
    if not filter_spec:
        return
    payload_cls = PAYLOAD_FOR_EVENT.get(event_name)
    if payload_cls is None:
        msg = f"Unknown event '{event_name}'"
        raise ValidationError(msg)

    _walk(filter_spec, payload_cls)


def _walk(spec: dict, payload_cls: type) -> None:
    """Recursively walk filter tree, validating leaf paths."""
    if OP_AND in spec or OP_OR in spec:
        for child in spec.get(OP_AND, spec.get(OP_OR, [])):
            _walk(child, payload_cls)
        return
    if OP_NOT in spec:
        _walk(spec[OP_NOT], payload_cls)
        return
    path = spec.get(OP_PATH)
    if path is None:
        return
    if path.startswith(SELF_PREFIX):
        return
    _check_path(path, payload_cls)


def _check_path(path: str, payload_cls: type) -> None:
    """Check that first dotted part of path is a field in payload_cls.

    Deeper parts traverse runtime attributes (model instances). We don't
    validate those statically — FilterPathError at runtime catches typos.
    """
    parts = path.split(".")
    field_names = {f.name for f in dataclasses.fields(payload_cls)}
    if parts[0] not in field_names:
        msg = (
            f"Filter path '{path}': '{parts[0]}' is not a field of "
            f"{payload_cls.__name__} (known fields: {sorted(field_names)})"
        )
        raise ValidationError(msg)
