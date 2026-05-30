from django.apps import AppConfig


class TraitsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "world.traits"
    verbose_name = "Traits System"

    def ready(self) -> None:
        """Clear Trait._name_to_trait_map between tests.

        With ``_build_name_cache`` querying the DB directly (see Trait model),
        clearing the cache between tests is safe and necessary — the rebuild
        on next access fetches fresh Trait instances rather than holding
        stale Python objects from a rolled-back test.
        """
        from core.testing import register_test_cache_flusher  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        register_test_cache_flusher(Trait.clear_name_cache)
