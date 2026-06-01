"""AppConfig for the shared predicate engine.

The predicate engine (evaluate + leaf-resolver registry +
CharacterPredicateContext) is consumed by missions, npc_services, and
any future system that needs to gate actions on "the actor's own
durable state." It lives here so no consumer app owns the engine.
"""

from django.apps import AppConfig


class PredicatesConfig(AppConfig):
    name = "world.predicates"
    label = "predicates"
    verbose_name = "Predicate engine (shared)"
    default_auto_field = "django.db.models.BigAutoField"
