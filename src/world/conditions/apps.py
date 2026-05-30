from django.apps import AppConfig


class ConditionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.conditions"
    verbose_name = "Conditions"

    def ready(self) -> None:
        """Register the ConditionTemplate name→PK cache with the test runner.

        Test-only hook — in production the cache stays populated across
        requests. The registration is a no-op outside tests because the
        test runner is what consumes the registry (see core.testing).
        """
        from core.testing import register_test_cache_flusher  # noqa: PLC0415
        from world.conditions.models import ConditionTemplate  # noqa: PLC0415

        register_test_cache_flusher(lambda: ConditionTemplate._name_pk_cache.clear())  # noqa: SLF001
