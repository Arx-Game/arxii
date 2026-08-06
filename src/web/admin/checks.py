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

#: The four columns CreditedContent adds - what CREDIT_FIELDSET shows.
CREDIT_FIELD_NAMES = ("written_by", "written_on", "reviewed_by", "reviewed_on")

# Arx-specific large tables. Staff add models here as the game grows.
# Grouped by domain for readability.
LARGE_TABLE_MODELS = {
    # Character identity
    "arxii.CharacterSheet",
    # Scenes / roleplay
    "arxii.Scene",
    "arxii.Persona",
    "arxii.Interaction",
    "arxii.Place",
    # Roster
    "arxii.RosterEntry",
    "arxii.RosterTenure",
    "arxii.PlayerData",
    # Items
    "arxii.ItemInstance",
    # Magic (per-character links)
    "arxii.CharacterGift",
    "arxii.CharacterTechnique",
    "arxii.CharacterTradition",
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


@register()
def check_credited_admin_fieldsets(app_configs, **kwargs):  # noqa: ARG001
    """Fieldsets-declaring admins for credited models must include the credit fields.

    An explicit ``fieldsets`` shows only what it names, so a credited model's
    admin declaring one without the credit fields silently hides who wrote
    the row (#3020 - ``ItemTemplateAdmin`` shipped that way). Emits
    ``web_admin.E001`` per violating admin.
    """
    from core.app_domains import credited_content_models  # noqa: PLC0415

    errors = []
    credited = set(credited_content_models())
    for model, admin_cls in admin.site._registry.items():  # noqa: SLF001
        if model not in credited or not admin_cls.fieldsets:
            continue
        declared = _declared_fieldset_fields(admin_cls.fieldsets)
        missing = [name for name in CREDIT_FIELD_NAMES if name not in declared]
        if missing:
            errors.append(
                Error(
                    f"{type(admin_cls).__name__} declares fieldsets for credited model "
                    f"{model.__name__} without the credit fields: {', '.join(missing)}.",
                    hint=(
                        "Append CREDIT_FIELDSET from world.contributors.admin to the "
                        "fieldsets declaration."
                    ),
                    id="web_admin.E001",
                )
            )
    return errors


def _declared_fieldset_fields(fieldsets):
    """Flatten every field name a fieldsets declaration shows, one nested level deep.

    A ``fields`` entry may itself be a tuple/list (Django's side-by-side
    widget layout); flatten it so that layout cannot evade the check. No
    current admin uses it - this is check hardening, not a live case.
    """
    declared: set[str] = set()
    for _label, options in fieldsets:
        for entry in options.get("fields", ()):
            if isinstance(entry, (list, tuple)):
                declared.update(entry)
            else:
                declared.add(entry)
    return declared
