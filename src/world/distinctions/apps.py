# src/world/distinctions/apps.py
from django.apps import AppConfig


class DistinctionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.distinctions"
    verbose_name = "Distinctions"

    def ready(self) -> None:
        """Register the distinction table-request completion handlers (#2607)."""
        from world.distinctions.table_request_handlers import (
            complete_distinction_add,
            complete_distinction_remove,
        )
        from world.gm.constants import TableRequestKind
        from world.gm.request_handlers import register_request_handler

        register_request_handler(
            TableRequestKind.DISTINCTION_ADD.value, complete_distinction_add
        )
        register_request_handler(
            TableRequestKind.DISTINCTION_REMOVE.value, complete_distinction_remove
        )
