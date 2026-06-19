from django.test import TestCase


class ConsumeItemChargesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.items.factories import ItemTemplateFactory

        cls.template = ItemTemplateFactory(is_consumable=True, max_charges=2)

    def _consumable(self, *, charges=2, **kw):
        from evennia_extensions.factories import ObjectDBFactory
        from world.items.factories import ItemInstanceFactory

        return ItemInstanceFactory(
            template=self.template,
            charges=charges,
            quality_tier=None,
            game_object=ObjectDBFactory(),
            **kw,
        )

    def test_decrement_writes_activated_event(self):
        from world.items.constants import OwnershipEventType
        from world.items.services.usage import consume_item_charges

        inst = self._consumable(charges=2)
        consume_item_charges(item_instance=inst, amount=1)
        inst.refresh_from_db()
        self.assertEqual(inst.charges, 1)
        self.assertTrue(
            inst.ownership_events.filter(event_type=OwnershipEventType.ACTIVATED).exists()
        )

    def test_no_charges_raises(self):
        from world.items.exceptions import NoChargesRemaining
        from world.items.services.usage import consume_item_charges

        with self.assertRaises(NoChargesRemaining):
            consume_item_charges(item_instance=self._consumable(charges=0))

    def test_hard_delete_bare_instance_at_zero(self):
        from world.items.constants import OwnershipEventType
        from world.items.models import ItemInstance, OwnershipEvent
        from world.items.services.usage import consume_item_charges

        inst = self._consumable(charges=1)  # bare: no custom name/tier/facets
        self.assertFalse(inst.differs_from_template)
        pk = inst.pk
        consume_item_charges(item_instance=inst, amount=1)
        self.assertFalse(ItemInstance.objects.filter(pk=pk).exists())
        # The CONSUMED event survives the hard-delete via SET_NULL: its
        # item_instance FK is nulled, but the ledger row persists. Read the
        # FK column straight from the DB via .values() — the idmapper-cached
        # event object isn't touched by the DB-side cascade.
        fk = (
            OwnershipEvent.objects.filter(event_type=OwnershipEventType.CONSUMED)
            .values_list("item_instance_id", flat=True)
            .get()
        )
        self.assertIsNone(fk)

    def test_soft_delete_when_prior_ownership_event_exists(self):
        from world.items.constants import OwnershipEventType
        from world.items.models import ItemInstance, OwnershipEvent
        from world.items.services.usage import consume_item_charges

        inst = self._consumable(charges=1)  # bare otherwise
        OwnershipEvent.objects.create(item_instance=inst, event_type=OwnershipEventType.GIVEN)
        pk = inst.pk
        consume_item_charges(item_instance=inst, amount=1)
        row = ItemInstance.objects.get(pk=pk)  # must still exist (soft-deleted via provenance)
        self.assertIsNotNone(row.destroyed_at)

    def test_soft_delete_special_instance_at_zero(self):
        from world.items.models import ItemInstance
        from world.items.services.usage import consume_item_charges

        inst = self._consumable(charges=1, custom_name="Heirloom Phial")
        pk = inst.pk
        consume_item_charges(item_instance=inst, amount=1)
        row = ItemInstance.objects.get(pk=pk)  # still exists (soft-deleted)
        self.assertIsNotNone(row.destroyed_at)
        self.assertNotIn(pk, set(ItemInstance.objects.in_play().values_list("pk", flat=True)))


class UseItemTests(TestCase):
    """Tests for use_item() orchestration: validation, effects, charge spend."""

    @classmethod
    def setUpTestData(cls):
        from evennia_extensions.factories import CharacterFactory

        cls.character = CharacterFactory(db_key="UseItemChar")

    def _pool_with_condition_effect(self):
        """Build a ConsequencePool with one Consequence carrying an
        apply_condition ConsequenceEffect (target=self)."""
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
        from world.conditions.factories import ConditionTemplateFactory

        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(label="PotionEffect")
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type="apply_condition",
            target="self",
            condition_template=ConditionTemplateFactory(),
        )
        return pool

    def _instance(self, *, template, charges=1):
        from evennia_extensions.factories import ObjectDBFactory
        from world.items.factories import ItemInstanceFactory

        return ItemInstanceFactory(
            template=template,
            charges=charges,
            quality_tier=None,
            game_object=ObjectDBFactory(),
        )

    def test_deterministic_use_applies_effects_and_spends_charge(self):
        from world.items.factories import ItemTemplateFactory
        from world.items.services.usage import use_item

        template = ItemTemplateFactory(
            is_consumable=True,
            max_charges=1,
            on_use_pool=self._pool_with_condition_effect(),
            on_use_check_type=None,
        )
        inst = self._instance(template=template, charges=1)

        result = use_item(item_instance=inst, user=self.character)

        self.assertTrue(result.applied_effects)
        self.assertEqual(result.charges_remaining, 0)
        self.assertIsNone(result.check_result)

    def test_not_usable_without_pool_raises(self):
        from world.items.exceptions import ItemNotUsable
        from world.items.factories import ItemTemplateFactory
        from world.items.services.usage import use_item

        template = ItemTemplateFactory(
            is_consumable=True,
            max_charges=1,
            on_use_pool=self._pool_with_condition_effect(),
            on_use_check_type=None,
        )
        inst = self._instance(template=template, charges=1)
        template.on_use_pool = None
        template.save(update_fields=["on_use_pool"])

        with self.assertRaises(ItemNotUsable):
            use_item(item_instance=inst, user=self.character)

    def test_no_charges_raises(self):
        from world.items.exceptions import NoChargesRemaining
        from world.items.factories import ItemTemplateFactory
        from world.items.services.usage import use_item

        template = ItemTemplateFactory(
            is_consumable=True,
            max_charges=1,
            on_use_pool=self._pool_with_condition_effect(),
            on_use_check_type=None,
        )
        inst = self._instance(template=template, charges=0)

        with self.assertRaises(NoChargesRemaining):
            use_item(item_instance=inst, user=self.character)

    def test_check_gated_runs_check_and_spends_charge(self):
        from world.checks.factories import CheckTypeFactory
        from world.items.factories import ItemTemplateFactory
        from world.items.services.usage import use_item

        template = ItemTemplateFactory(
            is_consumable=True,
            max_charges=1,
            on_use_pool=self._pool_with_condition_effect(),
            on_use_check_type=CheckTypeFactory(),
            on_use_difficulty=1,
        )
        inst = self._instance(template=template, charges=1)

        result = use_item(item_instance=inst, user=self.character)

        self.assertIsNotNone(result.check_result)
        self.assertEqual(result.charges_remaining, 0)

    def test_non_consumable_with_pool_applies_effects_without_spending_charge(self):
        from world.items.constants import OwnershipEventType
        from world.items.factories import ItemTemplateFactory
        from world.items.services.usage import use_item

        template = ItemTemplateFactory(
            is_consumable=False,
            max_charges=0,  # DB constraint: charges (max_charges>0) require is_consumable
            on_use_pool=self._pool_with_condition_effect(),
            on_use_check_type=None,
        )
        inst = self._instance(template=template, charges=0)

        result = use_item(item_instance=inst, user=self.character)

        self.assertTrue(result.applied_effects)
        self.assertFalse(result.destroyed)
        self.assertFalse(result.soft_deleted)
        inst.refresh_from_db()
        self.assertTrue(
            inst.ownership_events.filter(event_type=OwnershipEventType.ACTIVATED).exists()
        )
        # Reusable: a second use still works (no NoChargesRemaining).
        use_item(item_instance=inst, user=self.character)

    def test_non_consumable_use_leaves_authored_charges_untouched(self):
        """A non-consumable template with an authored nonzero instance charge count
        must not have its charges spent on use (guards the reusable intent)."""
        from world.items.factories import ItemTemplateFactory
        from world.items.services.usage import use_item

        template = ItemTemplateFactory(
            is_consumable=False,
            max_charges=0,
            on_use_pool=self._pool_with_condition_effect(),
            on_use_check_type=None,
        )
        inst = self._instance(template=template, charges=5)

        result = use_item(item_instance=inst, user=self.character)

        self.assertEqual(result.charges_remaining, 5)
        inst.refresh_from_db()
        self.assertEqual(inst.charges, 5)
