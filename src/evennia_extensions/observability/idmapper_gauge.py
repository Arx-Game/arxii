"""Snapshot of Evennia idmapper cache sizes.

This module exposes a single public function, :func:`snapshot`, which walks
every registered :class:`~evennia.utils.idmapper.models.SharedMemoryModel`
subclass, reads its ``__instance_cache__`` dict, and returns a mapping of
model label → (instance_count, approx_bytes).

The function is deliberately side-effect-free: it does not modify any cache
and it never raises—errors on individual classes are caught and skipped.
"""

from __future__ import annotations

from collections.abc import Iterator

from evennia.utils.idmapper.models import SharedMemoryModel
from pympler.asizeof import asizeof as _asizeof


def _iter_subclasses() -> Iterator[type]:
    """Yield every registered SharedMemoryModel subclass recursively.

    Uses ``__subclasses__()`` rather than the Django app registry so that the
    walk works the same way regardless of which apps are installed.

    Yields:
        Each concrete or abstract subclass of SharedMemoryModel.
    """
    seen: set[int] = set()
    stack = list(SharedMemoryModel.__subclasses__())
    while stack:
        cls = stack.pop()
        cls_id = id(cls)
        if cls_id in seen:
            continue
        seen.add(cls_id)
        yield cls
        stack.extend(cls.__subclasses__())


def _label(cls: type) -> str:
    """Return a stable, human-readable label for *cls*.

    Prefers ``<app_label>.<ClassName>`` from Django's ``_meta`` if available,
    falling back to ``<module>.<ClassName>``.

    Args:
        cls: The class to label.

    Returns:
        A dot-separated string identifying the class.
    """
    try:
        return f"{cls._meta.app_label}.{cls.__name__}"
    except AttributeError:
        return f"{cls.__module__}.{cls.__name__}"


def snapshot() -> dict[str, tuple[int, int]]:
    """Return idmapper cache sizes for every SharedMemoryModel subclass.

    Walks ``SharedMemoryModel.__subclasses__()`` recursively. For each class
    that has a populated ``__instance_cache__`` dict, records:

    * **instance_count** – ``len(cls.__instance_cache__)``
    * **approx_bytes** – ``pympler.asizeof.asizeof(cls.__instance_cache__)``

    Classes whose cache is empty, missing, or that raise any exception during
    inspection are silently skipped so that one misbehaving class cannot
    interrupt the whole snapshot.

    Returns:
        A ``dict`` mapping ``"<app_label>.<ClassName>"`` →
        ``(instance_count, approx_bytes)``.  Both integers are non-negative.
    """
    result: dict[str, tuple[int, int]] = {}
    for cls in _iter_subclasses():
        try:
            cache = cls.__instance_cache__
            count = len(cache)
            if count == 0:
                continue
            approx_bytes = _asizeof(cache)
            result[_label(cls)] = (count, int(approx_bytes))
        except Exception:  # noqa: BLE001,S112
            continue
    return result
