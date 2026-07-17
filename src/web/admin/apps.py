"""Django app configuration for custom admin functionality."""

from django.apps import AppConfig


class AdminConfig(AppConfig):
    """Configuration for the web.admin app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "web.admin"
    label = "web_admin"  # Avoid conflict with django.contrib.admin
    verbose_name = "Admin Customizations"

    def ready(self):
        """Import checks module and patch Evennia/Django admin classes.

        Evennia and Django built-in admin classes (ObjectAdmin, AccountAdmin,
        ScriptAdmin, TagAdmin, GroupAdmin) live in site-packages and can't be
        edited directly. We monkey-patch ``autocomplete_fields`` onto them
        for FKs to large tables, so the system check passes and the admin
        pages render efficiently.
        """
        # Lazy imports are required in ready() to avoid circular import issues.
        from web.admin import checks  # noqa: F401, PLC0415

        _patch_external_admins()


def _patch_external_admins():
    """Add autocomplete_fields to Evennia/Django built-in admin classes.

    These classes live in site-packages and can't be edited directly. The
    fields listed below all point to large-table models (ObjectDB, AccountDB,
    ScriptDB, CharacterSheet, PlayerData, Scene, ItemInstance) that would
    crash the browser with a default ``<select>`` widget.

    Reverse relations (OneToOneRel, ManyToManyRel) can't use
    ``autocomplete_fields`` or ``raw_id_fields`` — those are exempted via
    ``large_table_widget_exempt`` so the system check passes without error.
    """
    # Lazy imports are required here because these admin classes import models
    # that may not be fully loaded at AppConfig.ready() time.
    from django.contrib.auth.admin import GroupAdmin  # noqa: PLC0415
    from evennia.web.admin.accounts import AccountAdmin  # noqa: PLC0415
    from evennia.web.admin.objects import ObjectAdmin  # noqa: PLC0415
    from evennia.web.admin.scripts import ScriptAdmin  # noqa: PLC0415
    from evennia.web.admin.tags import TagAdmin  # noqa: PLC0415

    # Evennia's ObjectDB admin
    # item_instance and sheet_data are reverse OneToOneRel — can't use autocomplete
    ObjectAdmin.autocomplete_fields = ()
    ObjectAdmin.large_table_widget_exempt = ["item_instance", "sheet_data"]

    # Evennia's AccountDB admin
    # participated_scenes is a reverse ManyToManyRel; player_data is reverse OneToOneRel
    AccountAdmin.autocomplete_fields = ()
    AccountAdmin.large_table_widget_exempt = ["participated_scenes", "player_data"]

    # Evennia's ScriptDB admin
    ScriptAdmin.autocomplete_fields = ("db_account",)

    # Evennia's Tag admin
    TagAdmin.autocomplete_fields = ("accountdb", "objectdb", "scriptdb")

    # Django's built-in Group admin — Group.user points to User (AccountDB)
    GroupAdmin.autocomplete_fields = ("user",)
