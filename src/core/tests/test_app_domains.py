from pathlib import Path

from django.apps import apps
from django.test import TestCase

from actions.models import ActionTemplate
from core.app_domains import domain_of
from world.magic.models import Technique

# src/ — three levels up from src/core/tests/test_app_domains.py. Mirrors
# tools/check_missing_migrations.py's own "first-party = lives under src/"
# filter, so first-party here means exactly what CI's migration-drift check
# means by it.
_SRC_DIR = Path(__file__).resolve().parents[2]


def _first_party_models():
    """Every model registered under an app whose code lives in src/.

    Excludes Django/Evennia/allauth/etc. (site-packages, not src/) — domain_of()
    was never meant to agree with their app_label and doesn't try to.
    """
    first_party_labels = {
        cfg.label for cfg in apps.get_app_configs() if cfg.path.startswith(str(_SRC_DIR))
    }
    return [model for model in apps.get_models() if model._meta.app_label in first_party_labels]


class DomainOfTest(TestCase):
    def test_world_subpackage_yields_its_own_name(self):
        self.assertEqual(domain_of(Technique), "magic")

    def test_non_world_first_party_app_yields_top_level_name(self):
        self.assertEqual(domain_of(ActionTemplate), "actions")

    def test_matches_app_label_for_every_first_party_model(self):
        """Exhaustive, machine-checked version of the behaviour-preserving guard.

        A 2-model spot check (the two tests above) missed the cases most
        likely to diverge: deep ``models`` *packages*
        (``world.progression.models.unlocks``), non-``world`` top-level apps
        (``behaviors``, ``flows``, ``evennia_extensions``), the ``web.admin`` ->
        ``web_admin`` special case, and — the ones Django can't auto-infer, so
        the likeliest to actually break — the explicit ``Meta.app_label``
        overrides in ``world/areas/positioning/models.py``,
        ``world/items/{gems,crafting,org_vault_models}``, and
        ``world/scenes/boon_models.py``. Walking every first-party model via
        ``apps.get_models()`` covers all of them without hand-maintaining a list.

        PRE-COLLAPSE ONLY. ``domain_of() == app_label`` is true today because
        every first-party model still has its own Django app; #2906's
        single-app collapse gives every one of them the label ``arxii``, so
        this equivalence is *expected* to start failing then. When it does,
        retarget this test (e.g. assert domain_of() against a recorded
        pre-collapse snapshot) rather than deleting it as broken — it is the
        thing that proves the collapse didn't silently rename anyone's domain.
        """
        first_party_models = _first_party_models()
        # Sanity check on the filter itself: a bug that made it match nothing
        # (e.g. a path-prefix typo) would otherwise pass an empty loop below.
        self.assertGreater(len(first_party_models), 900)
        for model in first_party_models:
            with self.subTest(model=model._meta.label_lower):
                self.assertEqual(domain_of(model), model._meta.app_label)
