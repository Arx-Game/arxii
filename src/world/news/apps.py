from django.apps import AppConfig


class NewsConfig(AppConfig):
    """The public-reaction news feed (#1450).

    Modelless: the feed aggregates awareness M2Ms owned by other apps (``societies`` deeds,
    ``secrets`` scandals). No migrations — there is nothing to migrate.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "world.news"
    verbose_name = "Public News Feed"
