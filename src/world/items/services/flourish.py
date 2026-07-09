"""Item flourish resolution for combat narration (#2023).

Provides a pure helper that resolves the effective flourish prose for an
item instance, mirroring the ``resolve_signature_snippet`` shape used by
the magic signature system.
"""

from __future__ import annotations

from world.items.models import ItemInstance


def resolve_item_flourish(item_instance: ItemInstance) -> str | None:
    """Resolve the effective flourish prose for an item instance.

    Returns ``custom_flourish_text`` when non-empty (player override),
    else ``template.flourish_text`` when non-empty (staff-authored),
    else ``None`` (no flourish).

    This is a pure function — no DB access beyond the already-loaded
    instance/template. The caller resolves the item instance, then
    passes the result string to the narration composer (e.g.
    ``signature_clause``).

    Args:
        item_instance: The ItemInstance whose flourish to resolve.

    Returns:
        The flourish prose string, or ``None`` when no flourish is authored.
    """
    if item_instance.custom_flourish_text:
        return item_instance.custom_flourish_text
    if item_instance.template.flourish_text:
        return item_instance.template.flourish_text
    return None
