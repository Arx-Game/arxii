"""Shared descriptors for model/typeclass attribute access.

Currently home to the reverse-OneToOne safe accessor used by the silent-fail
audit's ``*_or_none`` family (#2386 tranche 2).
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist


class ReverseOneToOneOrNone:
    """Descriptor: read a reverse OneToOne accessor, returning None on a missing row.

    The raw reverse accessor raises ``RelatedObjectDoesNotExist`` — a subclass of
    BOTH the related model's ``DoesNotExist`` and ``AttributeError`` — so the old
    ``getattr(obj, "accessor", None)`` idiom swallowed genuine attribute bugs
    along with the expected miss (the ``sheet_data`` trap, #2386). This descriptor
    catches only ``ObjectDoesNotExist``: a missing row yields None, while a real
    ``AttributeError`` (typo, wrong object type) still fails loudly.

    Usage::

        class CharacterSheet(...):
            vitals_or_none = ReverseOneToOneOrNone("vitals")

    Use the raw accessor (``sheet.vitals``) directly where a missing row is a
    hard bug; use the ``*_or_none`` name where absence is an expected state.
    """

    def __init__(self, accessor: str, doc: str | None = None) -> None:
        self.accessor = accessor
        self.__doc__ = doc or (f"The ``{accessor}`` reverse OneToOne, or None when no row exists.")

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, obj: object | None, objtype: type | None = None):
        if obj is None:
            return self
        try:
            return getattr(obj, self.accessor)
        except ObjectDoesNotExist:
            return None
