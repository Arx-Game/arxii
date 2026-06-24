from django.apps import AppConfig


class TidingsConfig(AppConfig):
    """The tidings feed (#1450) — the public-reaction center's pull/browse vector.

    Modelless: the feed aggregates awareness M2Ms owned by other apps (``societies`` deeds,
    ``secrets`` scandals). No migrations — there is nothing to migrate.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "world.tidings"
    verbose_name = "Tidings Feed"
