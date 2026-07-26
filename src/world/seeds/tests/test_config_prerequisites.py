"""Code-required content rows are declared and ensured before the content load (#2724)."""

from django.test import TestCase

from world.checks.models import CheckType, CheckTypeTrait
from world.seeds.config_prerequisites import CONFIG_PREREQUISITES
from world.traits.factories import StatTraitFactory


class ConfigPrerequisiteTests(TestCase):
    """Every declared prerequisite produces its row, with composition attached."""

    @classmethod
    def setUpTestData(cls) -> None:
        # The endurance/willpower prerequisites require the underlying STAT Trait
        # fixtures to already be loaded (see _ensure_endurance_check_type's docstring)
        # — normally seeded by the character_creation cluster, out of scope here.
        for stat_name in ("stamina", "composure", "stability", "willpower"):
            StatTraitFactory(name=stat_name)

    def test_registry_entries_are_zero_arg_callables(self) -> None:
        self.assertTrue(CONFIG_PREREQUISITES)
        for name, fn in CONFIG_PREREQUISITES.items():
            self.assertTrue(callable(fn), f"{name} is not callable")

    def test_running_every_prerequisite_is_idempotent(self) -> None:
        for fn in CONFIG_PREREQUISITES.values():
            fn()
        first = CheckType.objects.count()
        for fn in CONFIG_PREREQUISITES.values():
            fn()
        self.assertEqual(CheckType.objects.count(), first)

    def test_fatigue_willpower_check_has_a_trait_basis(self) -> None:
        for fn in CONFIG_PREREQUISITES.values():
            fn()
        check_type = CheckType.objects.get(name="fatigue_willpower")
        self.assertTrue(
            CheckTypeTrait.objects.filter(check_type=check_type).exists(),
            "fatigue_willpower has no trait rows — the check would roll on nothing",
        )

    def test_trait_is_attached_to_a_pre_existing_bare_check_type(self) -> None:
        """The `if created:` trap: a fixture-supplied CheckType arrives without traits.

        `created` is then False, so the old code never attached the trait and every
        fatigue willpower check silently rolled on an empty composition (#2724).
        """
        from world.checks.models import CheckCategory

        category, _ = CheckCategory.objects.get_or_create(name="Fatigue")
        bare = CheckType.objects.create(name="fatigue_willpower", category=category)
        self.assertFalse(CheckTypeTrait.objects.filter(check_type=bare).exists())

        for fn in CONFIG_PREREQUISITES.values():
            fn()

        self.assertTrue(CheckTypeTrait.objects.filter(check_type=bare).exists())

    def test_authored_values_survive_a_prerequisite_run(self) -> None:
        """Prerequisites run before the content load, so an authored weight must win.

        Guards the #2698 failure mode: a seeder that rewrites composition on every press
        silently reverts staff tuning. `get_or_create` with `defaults` converges;
        `update_or_create` would clobber.
        """
        from decimal import Decimal

        for fn in CONFIG_PREREQUISITES.values():
            fn()
        trait_row = CheckTypeTrait.objects.filter(check_type__name="fatigue_willpower").first()
        self.assertIsNotNone(trait_row)
        trait_row.weight = Decimal("2.50")
        trait_row.save(update_fields=["weight"])

        for fn in CONFIG_PREREQUISITES.values():
            fn()

        trait_row.refresh_from_db()
        self.assertEqual(trait_row.weight, Decimal("2.50"))
