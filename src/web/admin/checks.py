"""Django system check: flag FK/M2M fields to large tables without autocomplete/raw_id.

Prevents the failure mode where a default ``<select>`` widget renders every row
of a large table (ObjectDB, AccountDB, CharacterSheet, etc.) as an ``<option>``,
crashing or hanging the browser on admin pages with thousands of rows.

See issue #2435 for the full audit and design.
"""

from django.apps import apps
from django.contrib import admin
from django.core.checks import Error, register

# Evennia base models — always large in production. Stored as string labels
# so the check resolves them lazily (avoiding import-order issues).
EVENNIA_LARGE_TABLE_LABELS = {
    "objects.ObjectDB",
    "accounts.AccountDB",
    "scripts.ScriptDB",
}

# Arx-specific large tables. Staff add models here as the game grows.
# Grouped by domain for readability.
LARGE_TABLE_MODELS = {
    # Character identity
    "character_sheets.CharacterSheet",
    # Scenes / roleplay
    "scenes.Scene",
    "scenes.Persona",
    "scenes.Interaction",
    "scenes.Place",
    # Roster
    "roster.RosterEntry",
    "roster.RosterTenure",
    "evennia_extensions.PlayerData",
    # Items
    "items.ItemInstance",
    # Magic (per-character links)
    "magic.CharacterGift",
    "magic.CharacterTechnique",
    "magic.CharacterTradition",
}


def _get_protected_fields(admin_cls):
    """Get the set of field names protected by autocomplete_fields or raw_id_fields.

    Args:
        admin_cls: A ModelAdmin instance.

    Returns:
        A set of field name strings that are already protected.
    """
    protected: set[str] = set()
    if hasattr(admin_cls, "autocomplete_fields"):
        protected.update(admin_cls.autocomplete_fields)
    if hasattr(admin_cls, "raw_id_fields"):
        protected.update(admin_cls.raw_id_fields)
    return protected


def _get_exempt_fields(admin_cls):
    """Get the set of field names exempted from the check.

    Args:
        admin_cls: A ModelAdmin instance.

    Returns:
        A set of field name strings that are exempted.
    """
    if hasattr(admin_cls, "large_table_widget_exempt"):
        return set(admin_cls.large_table_widget_exempt)
    return set()


def _is_large_table(model):
    """Check if a model is a large table that should not use a default ``<select>``.

    Args:
        model: A Django model class.

    Returns:
        True if the model is an Evennia base model (or subclass thereof) or
        is listed in ``LARGE_TABLE_MODELS``.
    """
    meta = model._meta  # noqa: SLF001
    label = f"{meta.app_label}.{model.__name__}"

    # Evennia base models: use issubclass() to catch typeclass subclasses
    # (e.g., Room, Character, Exit all inherit from ObjectDB). FKs declared
    # against base ObjectDB return ObjectDB as related_model; FKs declared
    # against a typeclass return the typeclass. issubclass catches both.
    for evennia_label in EVENNIA_LARGE_TABLE_LABELS:
        parts = evennia_label.split(".")
        try:
            evennia_cls = apps.get_model(parts[0], parts[1])
        except LookupError:
            continue
        if evennia_cls and issubclass(model, evennia_cls):
            return True

    return label in LARGE_TABLE_MODELS


@register()
def check_admin_fk_widgets(app_configs, **kwargs):  # noqa: ARG001
    """Flag FK/M2M fields to large tables without autocomplete_fields or raw_id_fields.

    Iterates every registered ModelAdmin and checks whether any FK, OneToOne,
    or M2M field points to a large-table model without being listed in
    ``autocomplete_fields`` or ``raw_id_fields``. Emits ``web_admin.W001``
    errors for each violation.

    A ModelAdmin can exempt a specific field by listing it in
    ``large_table_widget_exempt`` (with a code comment explaining why).
    """
    errors = []
    for model, admin_cls in admin.site._registry.items():  # noqa: SLF001
        exempt = _get_exempt_fields(admin_cls)
        protected = _get_protected_fields(admin_cls)
        errors.extend(_find_large_table_fk_violations(model, admin_cls, exempt, protected))
    return errors


def _find_large_table_fk_violations(model, admin_cls, exempt, protected):
    """Yield ``web_admin.W001`` errors for unprotected FK/M2M fields to large tables.

    Args:
        model: The Django model class being inspected.
        admin_cls: The registered ModelAdmin class for ``model``.
        exempt: Set of field names exempted via ``large_table_widget_exempt``.
        protected: Set of field names protected from the check.

    Yields:
        ``Error`` instances for each violating field.
    """
    violations = []
    for field in model._meta.get_fields():  # noqa: SLF001
        if not field.is_relation or field.name in exempt or field.name in protected:
            continue
        if not (field.many_to_one or field.one_to_one or field.many_to_many):
            continue
        target = field.related_model
        if not target or not _is_large_table(target):
            continue
        violations.append(
            Error(
                f"{type(admin_cls).__name__}.{field.name} is a FK/M2M to "
                f"large table {target.__name__} but is not in "
                f"autocomplete_fields or raw_id_fields.",
                hint=(
                    "Add the field to autocomplete_fields (preferred) "
                    "or raw_id_fields. If a default <select> is "
                    "intentional, add the field name to "
                    "large_table_widget_exempt with a comment."
                ),
                id="web_admin.W001",
            )
        )
    return violations
