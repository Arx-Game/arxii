"""Journeys for worn items on checks (#4628, slice 4 of #4551).

Ysmay is a scout. Her boots, cloak and gloves each help her Shadowing check, and staff
gave each check modifier a size. She puts them on with the real ``wear`` command; her
next check, through ``perform_check_with_modifiers``, reads each worn item's value from
the modifier value table at the level its quality tier counts at, and the pile tapers
lightly (each extra at 7/8 of the one before, never below 2/3). The quality ladder, its
example levels, the value table and the taper rows are the example seed, so these
journeys also prove the seed is coherent.

- One Fine item adds the value table's Large number at Fine's level, not its flat value.
- Three Fine items add the tapered total.
- An item with no size keeps its flat value and still tapers with the others.
- A Superb item of the same size adds more than a Fine one; a Superb spare she only
  carries does not raise her worn Fine boots.
- A sized penalty (a plate cuirass) stays a penalty, in its own pile.
- Her covenant's level bonus rides the equipment walk and is never tapered.
- An item at a tier with no level keeps its flat value.
- Staff set a tier's level and an item's size on the admin pages; Paramount is refused.

The player's own ``check <name>`` command rolls through ``perform_check`` without gathering
modifiers, so no worn item, buff or condition reaches it today; these journeys read the
check through ``perform_check_with_modifiers``, the seam challenges, social actions and
casts roll through.
"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from web.admin.tuning.required_content import collect_required_content
from world.checks.constants import ModifierLane, ModifierSize, ModifierSourceKind
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.modifier_models import ModifierValue
from world.checks.modifier_values import load_value_table
from world.checks.services import collect_check_modifiers, perform_check_with_modifiers
from world.checks.types import CheckResult
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, make_engaged_member
from world.covenants.models import CovenantLevelBonus
from world.items.admin import ItemCheckModifierInline
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import ItemCheckModifier, ItemInstance, ItemTemplate, QualityTier
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.modifier_values import seed_modifier_value_tables
from world.seeds.provisioning_checks import seed_provisioning_content
from world.traits.factories import StatTraitFactory

# The flat value each item authors; a sized item at a tier with a level must NOT add it.
FLAT_AUTHORED = 5


class WornItemsOnChecks(JourneyCase):
    """Ysmay dresses for a night's shadowing."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        seed_provisioning_content()
        self.fine = QualityTier.objects.get(name="Fine")
        self.superb = QualityTier.objects.get(name="Superb")
        self.room = self.make_room("The Lamplighters' Lane")
        self.shadowing = CheckTypeFactory(name="Shadowing")
        stat = StatTraitFactory()
        CheckTypeTraitFactory(check_type=self.shadowing, trait=stat, weight=1)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.ysmay.traits.set_trait_value(stat.name, 20)
        self.table = load_value_table(ModifierLane.CHECK)

    # -- setup helpers ----------------------------------------------------------

    def template(
        self, name: str, region: str, *, value: int = FLAT_AUTHORED, size: int | None = None
    ) -> ItemTemplate:
        """A wearable template whose check modifier staff authored at ``size``."""
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template, body_region=region, equipment_layer=EquipmentLayer.BASE
        )
        template.__dict__.pop("cached_slots", None)
        ItemCheckModifier.objects.create(
            template=template,
            check_type=self.shadowing,
            modifier_value=value,
            modifier_size=size,
        )
        return template

    def carried(self, template: ItemTemplate, tier: QualityTier, key: str = "") -> ItemInstance:
        """A piece of ``template`` at ``tier``, in Ysmay's hands."""
        obj = ObjectDBFactory(db_key=key or template.name, location=self.ysmay)
        return ItemInstanceFactory(
            template=template,
            game_object=obj,
            holder_character_sheet=self.ysmay.sheet_data,
            quality_tier=tier,
            custom_name=key,
        )

    def wear(self, name: str) -> None:
        self.assertIn(f"You equip {name}.", self.telnet(self.ysmay, f"wear {name}"))

    def dress(self, *templates: ItemTemplate, tier: QualityTier | None = None) -> None:
        for template in templates:
            self.carried(template, tier or self.fine)
            self.wear(template.name)

    def boots_cloak_gloves(self) -> tuple[ItemTemplate, ItemTemplate, ItemTemplate]:
        return (
            self.template("Padded Boots", BodyRegion.FEET, size=ModifierSize.LARGE),
            self.template("Dark Cloak", BodyRegion.BACK, size=ModifierSize.LARGE),
            self.template("Soft Gloves", BodyRegion.LEFT_HAND, size=ModifierSize.LARGE),
        )

    def shadowing_check(self) -> CheckResult:
        return perform_check_with_modifiers(self.ysmay, self.shadowing, target_difficulty=50)

    def gain(self, before: CheckResult) -> int:
        return self.shadowing_check().total_points - before.total_points

    # -- journeys -----------------------------------------------------------------

    def test_one_fine_item_adds_its_value_table_number(self) -> None:
        boots, _cloak, _gloves = self.boots_cloak_gloves()
        before = self.shadowing_check()

        self.dress(boots)

        # The seed puts Fine at level 11, where a Large modifier is worth 16.
        self.assertEqual(self.fine.modifier_level, 11)
        self.assertEqual(self.table.value(11, ModifierSize.LARGE), 16)
        self.assertEqual(self.gain(before), 16)
        (worn,) = collect_check_modifiers(self.ysmay.sheet_data, self.shadowing).contributions
        self.assertEqual(
            (worn.source_kind, worn.source_label, worn.value, worn.level, worn.size),
            (ModifierSourceKind.EQUIPMENT, "Equipped: Padded Boots", 16, 11, ModifierSize.LARGE),
        )

    def test_three_fine_items_taper(self) -> None:
        before = self.shadowing_check()

        self.dress(*self.boots_cloak_gloves())

        # 16 + 16 x 7/8 + 16 x (7/8)^2 = 42.25, rounded once.
        self.assertEqual(self.gain(before), 42)

    def test_an_unsized_item_keeps_its_flat_value_and_tapers(self) -> None:
        hood = self.template("Old Hood", BodyRegion.HEAD)
        before = self.shadowing_check()

        self.dress(hood)
        self.assertEqual(self.gain(before), FLAT_AUTHORED)

        self.dress(*self.boots_cloak_gloves())
        # The hood is fourth in the pile: 42.25 + 5 x (7/8)^3 = 45.6, not 42 + 5.
        self.assertEqual(self.gain(before), 46)
        breakdown = collect_check_modifiers(self.ysmay.sheet_data, self.shadowing)
        hood_row = next(c for c in breakdown.contributions if c.source_label.endswith("Hood"))
        self.assertEqual((hood_row.value, hood_row.level, hood_row.size), (5, None, None))

    def test_a_better_item_of_the_same_size_adds_more(self) -> None:
        boots, _cloak, _gloves = self.boots_cloak_gloves()
        before = self.shadowing_check()
        self.carried(boots, self.fine, key="Fine Boots")
        self.carried(boots, self.superb, key="Superb Boots")

        self.wear("Fine Boots")
        # Superb boots she carries but does not wear leave the Fine pair's level alone.
        self.assertEqual(self.gain(before), 16)

        self.assertIn("You remove Fine Boots.", self.telnet(self.ysmay, "remove Fine Boots"))
        self.wear("Superb Boots")
        # Superb counts at level 16, where Large is worth 23.
        self.assertEqual(self.superb.modifier_level, 16)
        self.assertEqual(self.gain(before), 23)

    def test_a_tier_with_no_level_keeps_the_flat_value(self) -> None:
        boots, _cloak, _gloves = self.boots_cloak_gloves()
        unranked = QualityTier.objects.get(name="Poor")
        unranked.modifier_level = None
        unranked.save(update_fields=["modifier_level"])
        before = self.shadowing_check()

        self.dress(boots, tier=unranked)

        self.assertEqual(self.gain(before), FLAT_AUTHORED)
        (worn,) = collect_check_modifiers(self.ysmay.sheet_data, self.shadowing).contributions
        self.assertEqual((worn.value, worn.level, worn.size), (FLAT_AUTHORED, None, None))

    def test_without_a_value_row_the_item_keeps_its_flat_value(self) -> None:
        boots, _cloak, _gloves = self.boots_cloak_gloves()
        for row in ModifierValue.objects.filter(lane=ModifierLane.CHECK):
            row.delete()
        before = self.shadowing_check()

        self.dress(boots)

        self.assertEqual(self.gain(before), FLAT_AUTHORED)
        (worn,) = collect_check_modifiers(self.ysmay.sheet_data, self.shadowing).contributions
        self.assertEqual((worn.value, worn.level, worn.size), (FLAT_AUTHORED, None, None))

    def test_a_sized_penalty_stays_a_penalty_in_its_own_pile(self) -> None:
        boots, _cloak, _gloves = self.boots_cloak_gloves()
        cuirass = self.template(
            "Plate Cuirass", BodyRegion.TORSO, value=-10, size=ModifierSize.LARGE
        )
        before = self.shadowing_check()

        self.dress(boots, cuirass)

        # +16 and -16 sit in separate piles, so neither tapers the other.
        self.assertEqual(self.gain(before), 0)
        values = sorted(
            c.value
            for c in collect_check_modifiers(self.ysmay.sheet_data, self.shadowing).contributions
        )
        self.assertEqual(values, [-16, 16])

    def test_the_covenant_bonus_on_the_walk_is_never_tapered(self) -> None:
        # A check-scoped stat target makes the equipment walk reach Shadowing; her
        # covenant's level bonus rides it as her vow.
        target = ModifierTargetFactory(
            name="shadowing_walk",
            category=ModifierCategoryFactory(name="stat"),
            target_check_type=self.shadowing,
        )
        CovenantLevelBonus.objects.create(modifier_target=target, bonus_per_level=4)
        make_engaged_member(
            character_sheet=self.ysmay.sheet_data,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE, level=5),
        )
        self.ysmay.covenant_roles.invalidate()
        before_items = self.shadowing_check()

        self.dress(*self.boots_cloak_gloves())

        walk = next(
            c
            for c in collect_check_modifiers(self.ysmay.sheet_data, self.shadowing).contributions
            if c.source_label == "Equipment & attunement"
        )
        self.assertEqual((walk.value, walk.vow_part), (20, 20))
        # The three items taper among themselves (42.25); the covenant's 20 counts whole.
        # Tapered as a fourth item it would have led the pile: 20 + 14 + 12.25 + 10.7 = 57.
        self.assertEqual(self.gain(before_items), 42)
        self.assertEqual(collect_check_modifiers(self.ysmay.sheet_data, self.shadowing).total, 62)


class StaffTuneWornItems(JourneyCase):
    """Staff set the item level rows and an item's size on the admin pages."""

    def setUp(self) -> None:
        super().setUp()
        seed_provisioning_content()
        self.staff = get_user_model().objects.create_superuser("tuner", "t@example.com", "pw-12345")
        self.client.force_login(self.staff)
        self.shadowing = CheckTypeFactory(name="Shadowing")

    def test_the_quality_tier_list_edits_each_tier_level(self) -> None:
        body = self.client.get("/admin/arxii/qualitytier/").content.decode()
        self.assertIn('name="form-0-modifier_level"', body)
        fine = QualityTier.objects.get(name="Fine")

        response = self.client.post(
            f"/admin/arxii/qualitytier/{fine.pk}/change/",
            {
                "name": fine.name,
                "color_hex": fine.color_hex,
                "numeric_min": fine.numeric_min,
                "numeric_max": fine.numeric_max,
                "stat_multiplier": fine.stat_multiplier,
                "sort_order": fine.sort_order,
                "modifier_level": 9,
            },
        )

        self.assertEqual(response.status_code, 302)
        listing = self.client.get("/admin/arxii/qualitytier/").content.decode()
        self.assertRegex(listing, r'name="form-\d+-modifier_level" value="9"')
        self.assertEqual(QualityTier.objects.get(pk=fine.pk).modifier_level, 9)

    def test_the_item_template_page_offers_the_size_and_paramount_is_refused(self) -> None:
        template = ItemTemplateFactory(name="Padded Boots")
        body = self.client.get(f"/admin/arxii/itemtemplate/{template.pk}/change/").content
        self.assertIn(b"check_modifiers-0-modifier_size", body)
        self.assertIn(b"Exceptional", body)

        # The admin's own inline formset, bound to what the page posts: Paramount is refused.
        request = RequestFactory().post("/")
        request.user = self.staff
        inline = ItemCheckModifierInline(ItemTemplate, admin.site)
        formset_class = inline.get_formset(request, template)
        prefix = formset_class.get_default_prefix()
        posted = {
            f"{prefix}-TOTAL_FORMS": "1",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-0-check_type": str(self.shadowing.pk),
            f"{prefix}-0-modifier_value": "5",
            f"{prefix}-0-modifier_size": str(ModifierSize.PARAMOUNT),
        }
        refused = formset_class(posted, instance=template, prefix=prefix)
        self.assertFalse(refused.is_valid())
        self.assertIn(
            "Paramount is reached only through a vow's size step.",
            refused.forms[0].errors["modifier_size"],
        )
        posted[f"{prefix}-0-modifier_size"] = str(ModifierSize.EXCEPTIONAL)
        accepted = formset_class(posted, instance=template, prefix=prefix)
        self.assertTrue(accepted.is_valid(), accepted.errors)

    def test_the_required_content_sentinel_lists_the_item_level_rows(self) -> None:
        def present_keys() -> set[str]:
            snapshot = collect_required_content()
            return {row.dependency.key for row in snapshot.present_tuning}

        self.assertIn("quality-tier-modifier-level", present_keys())
        for tier in QualityTier.objects.all():
            tier.modifier_level = None
            tier.save(update_fields=["modifier_level"])
        self.assertNotIn("quality-tier-modifier-level", present_keys())
