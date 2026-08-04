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

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "model_domain_snapshot.txt"


def _first_party_models():
    """Every model registered under an app whose code lives in src/.

    Excludes Django/Evennia/allauth/etc. (site-packages, not src/) — domain_of()
    was never meant to agree with their app_label and doesn't try to.
    """
    first_party_labels = {
        cfg.label for cfg in apps.get_app_configs() if cfg.path.startswith(str(_SRC_DIR))
    }
    return [model for model in apps.get_models() if model._meta.app_label in first_party_labels]


def _load_domain_snapshot() -> dict[str, str]:
    """Parse ``model_domain_snapshot.txt`` into ``{label_lower: domain}``."""
    snapshot: dict[str, str] = {}
    for line in _SNAPSHOT_PATH.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        label, domain = line.split()
        snapshot[label] = domain
    return snapshot


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

        RETARGETED post-collapse (#2906 Task 6), per this docstring's own
        prior instruction: ``domain_of() == app_label`` stopped holding the
        moment the collapse gave every first-party model the one label
        ``arxii``, so this now checks ``domain_of()`` against a frozen
        pre-collapse snapshot (``data/model_domain_snapshot.txt``, itself
        generated from ``domain_of()`` while the equivalence still held)
        instead of the live ``app_label``. ``domain_of()`` is a pure function
        of a model's ``__module__`` path and the collapse moved no modules, so
        this still proves the collapse didn't silently rename anyone's
        domain — and it keeps guarding future drift, since any *later* change
        that alters a model's computed domain without updating the snapshot
        now fails loudly instead of passing silently against a label that no
        longer carries the signal.

        A model absent from the snapshot (added after it was captured) is
        skipped, not failed — the snapshot is a historical baseline, not a
        registry every new model must join.
        """
        first_party_models = _first_party_models()
        # Sanity check on the filter itself: a bug that made it match nothing
        # (e.g. a path-prefix typo) would otherwise pass an empty loop below.
        self.assertGreater(len(first_party_models), 900)
        snapshot = _load_domain_snapshot()
        self.assertGreater(len(snapshot), 900)
        checked = 0
        for model in first_party_models:
            expected = snapshot.get(model._meta.label_lower)
            if expected is None:
                continue
            checked += 1
            with self.subTest(model=model._meta.label_lower):
                self.assertEqual(domain_of(model), expected)
        # Guards the guard: if every model started missing from the snapshot
        # (e.g. a label-format drift broke the lookup), the loop above would
        # pass vacuously with zero assertions.
        self.assertGreater(checked, 900)
