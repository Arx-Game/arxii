from django.apps import AppConfig


class ProclamationsConfig(AppConfig):
    """Proclamations & stances (#2842) — philosophy-vector public statements.

    Characters issue proclamations aligned to authored stance archetypes; the
    stance dot-products against society principles to produce asymmetric
    reputation deltas. Domain edicts ride proclamations with a mechanical
    payload (income pct, unrest, upkeep).
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "world.proclamations"
    verbose_name = "Proclamations & Stances"
