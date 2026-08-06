"""Code-required content rows are declared and ensured before the content load (#2724)."""

from django.test import TestCase, override_settings

from world.checks.models import CheckType, CheckTypeSpecialization, CheckTypeTrait
from world.items.models import AccentLevel, QualityTier
from world.seeds.config_prerequisites import CONFIG_PREREQUISITES
from world.seeds.provisioning_checks import BREWING_SPECIALIZATION_NAME, COOKING_CHECK_NAME
from world.skills.models import Specialization
from world.traits.factories import StatTraitFactory
from world.traits.models import Trait, TraitType


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

    def test_registry_covers_every_triaged_module(self) -> None:
        expected = {
            "technique_cast",
            "fatigue",
            "fury",
            "spread",
            "vitals",
            "conditions",
            "dreams",
            "alterations",
            "locations",
            "combat_stats",
            "projects",
            "ships",
            "crafting",
            "provisioning",
        }
        missing = expected - set(CONFIG_PREREQUISITES)
        self.assertFalse(missing, f"unregistered prerequisites: {sorted(missing)}")

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

    def test_dream_peril_trait_is_attached_to_a_pre_existing_bare_check_type(self) -> None:
        """The `if created:` trap, dreams flavor (#2724) — worse than fatigue/fury:

        `_ensure_dream_peril_config` stamps `DreamPerilConfig.resist_check_type` and
        never revisits it (early return once set), so a skipped attachment here is
        permanent — there is no later gameplay call site to self-heal it.
        """
        from world.checks.models import CheckCategory
        from world.dreams.models import DreamPerilConfig

        category, _ = CheckCategory.objects.get_or_create(name="Mental")
        bare = CheckType.objects.create(name="Dream Peril Resolve", category=category)
        self.assertFalse(CheckTypeTrait.objects.filter(check_type=bare).exists())

        CONFIG_PREREQUISITES["dreams"]()

        self.assertTrue(
            CheckTypeTrait.objects.filter(check_type=bare).exists(),
            "Dream Peril Resolve has no trait rows — the check would roll on nothing",
        )
        config = DreamPerilConfig.objects.get(pk=1)
        self.assertEqual(config.resist_check_type_id, bare.pk)

    def test_crafting_recipes_are_seeded_with_a_check_type(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftingRecipe

        CONFIG_PREREQUISITES["crafting"]()

        for kind in (
            CraftingRecipeKind.FACET_ATTACH,
            CraftingRecipeKind.STYLE_ATTACH,
            CraftingRecipeKind.GEM_CUT,
        ):
            recipe = CraftingRecipe.objects.get(kind=kind, output_item_template=None)
            self.assertIsNotNone(
                recipe.check_type,
                f"{kind} recipe seeded with no check_type — it would be disabled",
            )

    def test_crafting_prerequisite_is_idempotent(self) -> None:
        from world.items.crafting.models import CraftingRecipe

        CONFIG_PREREQUISITES["crafting"]()
        first = CraftingRecipe.objects.count()

        CONFIG_PREREQUISITES["crafting"]()

        self.assertEqual(CraftingRecipe.objects.count(), first)

    def test_crafting_check_type_is_reattached_to_a_pre_existing_bare_recipe(self) -> None:
        """The `if created:` trap, crafting flavor: a fixture-supplied recipe row
        arrives with `check_type=None` and must not stay disabled.
        """
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftingRecipe

        bare = CraftingRecipe.objects.create(
            name="Attach Facet (Enchanting)", kind=CraftingRecipeKind.FACET_ATTACH
        )
        self.assertIsNone(bare.check_type)

        CONFIG_PREREQUISITES["crafting"]()

        bare.refresh_from_db()
        self.assertIsNotNone(bare.check_type)

    def test_crafting_prerequisite_seeds_the_facet_reagent_requirement(self) -> None:
        from world.items.crafting.constants import CraftingRecipeKind
        from world.items.crafting.models import CraftingRecipe
        from world.items.models import CraftingMaterialRequirement

        CONFIG_PREREQUISITES["crafting"]()

        facet_recipe = CraftingRecipe.objects.get(
            kind=CraftingRecipeKind.FACET_ATTACH, output_item_template=None
        )
        self.assertTrue(
            CraftingMaterialRequirement.objects.filter(recipe=facet_recipe).exists(),
            "facet-attach recipe seeded with no reagent requirement",
        )

    def test_crafting_prerequisite_seeds_the_workshop_of_iniquity_kind(self) -> None:
        """#3006 task 6c: the row a justice-frame-jobs check AND a lore-authored
        `CraftingRecipe.required_feature_kind` fixture both need must exist
        pre-content, not only when `seed_room_features_dev` happens to have run.
        """
        from world.room_features.models import RoomFeatureKind
        from world.room_features.seeds import WORKSHOP_OF_INIQUITY_KIND_NAME

        CONFIG_PREREQUISITES["crafting"]()

        self.assertTrue(
            RoomFeatureKind.objects.filter(name=WORKSHOP_OF_INIQUITY_KIND_NAME).exists(),
            "crafting prerequisite ran but the Workshop of Iniquity kind row is missing",
        )


class ConfigPrerequisiteFreshDatabaseTests(TestCase):
    """The actual first-Big-Button-press condition: zero Trait rows exist yet.

    Deliberately no `setUpTestData` pre-creating Traits — that setup is what let the
    original fix (a tolerant `.filter().first()` skip) mask the real bug: on a genuinely
    fresh database, `CONFIG_PREREQUISITES` runs inside `load_content_first()` *before*
    `load_world_content()` populates the `traits.trait` content fixtures, so the stat
    Traits fatigue's checks roll on do not exist yet either (#2724).
    """

    def test_prerequisites_create_missing_traits_and_attach_composition(self) -> None:
        self.assertEqual(Trait.objects.count(), 0)

        for fn in CONFIG_PREREQUISITES.values():
            fn()

        for stat_name in ("stamina", "composure", "stability", "willpower"):
            self.assertTrue(
                Trait.objects.filter(name=stat_name).exists(),
                f"{stat_name} Trait was not created by a config prerequisite",
            )

        willpower_check = CheckType.objects.get(name="fatigue_willpower")
        self.assertTrue(
            CheckTypeTrait.objects.filter(
                check_type=willpower_check, trait__name="willpower"
            ).exists(),
            "fatigue_willpower composition was not attached against a fresh database",
        )

        for category, stat_name in (
            ("physical", "stamina"),
            ("social", "composure"),
            ("mental", "stability"),
        ):
            endurance_check = CheckType.objects.get(name=f"fatigue_endurance_{category}")
            self.assertTrue(
                CheckTypeTrait.objects.filter(
                    check_type=endurance_check, trait__name=stat_name
                ).exists(),
                f"fatigue_endurance_{category} composition was not attached "
                "against a fresh database",
            )

    def test_dreams_prerequisite_alone_creates_missing_trait_and_attaches_composition(
        self,
    ) -> None:
        """Regression for #2724: the dreams entry must not depend on `fatigue` having
        already run and created `stability`.

        `CONFIG_PREREQUISITES` happens to run `fatigue` before `dreams` today, so
        iterating the whole dict (as the sibling test above does) would pass even with
        the bug: fatigue creates `stability` first by accident of dict order. Calling
        only the `dreams` entry, in isolation, against a Trait-less database is what
        actually exercises the failure mode — it's what the fix in
        `world.dreams.conditions._ensure_dream_peril_config` guarantees.
        """
        from world.dreams.models import DreamPerilConfig

        self.assertEqual(Trait.objects.count(), 0)

        CONFIG_PREREQUISITES["dreams"]()

        self.assertTrue(
            Trait.objects.filter(name="stability").exists(),
            "stability Trait was not created by the dreams prerequisite alone",
        )
        config = DreamPerilConfig.objects.get(pk=1)
        self.assertIsNotNone(config.resist_check_type)
        self.assertTrue(
            CheckTypeTrait.objects.filter(check_type=config.resist_check_type).exists(),
            "Dream Peril Resolve composition was not attached against a fresh database",
        )


@override_settings(SEED_SAMPLE_CONTENT=True)  # authored_or_sample needs sampling on (#2698)
class ProvisioningPrerequisiteTests(TestCase):
    """The `provisioning` entry moves the Cooking check + quality ladder pre-content (#3006).

    Lore-repo ITEM_CREATE recipe fixtures FK the "Cooking" CheckType and the
    QualityTier ladder by natural key — previously these only existed after
    `seed_provisioning_content()`, a cluster seeder that ran AFTER the content
    load, so a fresh one-shot seed would defer and drop the fixtures (#2882
    shape). This entry calls the same `provisioning_checks` helpers pre-content.
    """

    def test_seeds_cooking_check_with_wits_agility_cooking_composition(self) -> None:
        CONFIG_PREREQUISITES["provisioning"]()

        check_type = CheckType.objects.get(name=COOKING_CHECK_NAME)
        trait_names = set(
            CheckTypeTrait.objects.filter(check_type=check_type).values_list(
                "trait__name", flat=True
            )
        )
        self.assertEqual(trait_names, {"wits", "agility", "Cooking"})
        self.assertEqual(Trait.objects.get(name="Cooking").trait_type, TraitType.SKILL)

    def test_seeds_brewing_specialization_attached_to_cooking_check(self) -> None:
        CONFIG_PREREQUISITES["provisioning"]()

        check_type = CheckType.objects.get(name=COOKING_CHECK_NAME)
        specialization = Specialization.objects.get(name=BREWING_SPECIALIZATION_NAME)
        self.assertTrue(
            CheckTypeSpecialization.objects.filter(
                check_type=check_type, specialization=specialization
            ).exists()
        )

    def test_seeds_the_full_quality_and_accent_ladders(self) -> None:
        CONFIG_PREREQUISITES["provisioning"]()

        self.assertEqual(QualityTier.objects.count(), 12)
        legendary = QualityTier.objects.get(name="Legendary")
        self.assertEqual(legendary.sort_order, 12)
        self.assertEqual(AccentLevel.objects.count(), 7)
        self.assertEqual(AccentLevel.objects.get(level=1).name, "slightly")

    def test_provisioning_prerequisite_is_idempotent(self) -> None:
        CONFIG_PREREQUISITES["provisioning"]()
        CONFIG_PREREQUISITES["provisioning"]()

        check_type = CheckType.objects.get(name=COOKING_CHECK_NAME)
        # skill + wits + agility, no duplicates.
        self.assertEqual(CheckTypeTrait.objects.filter(check_type=check_type).count(), 3)
        self.assertEqual(QualityTier.objects.count(), 12)
        self.assertEqual(AccentLevel.objects.count(), 7)
