"""Journeys for stat buffs valued by level and size, and piles of them tapering (#4726).

Slice 8 of #4551. Brannoc is a dock porter (level 6, strength 2 and stamina 2 as shown,
20 stored). Buffs to his strength are real conditions, distinctions, worn pieces and his
vow. His strength is one number wherever it is read: the Lifting check (through
``perform_check_with_modifiers``, the seam every roll uses), his carrying capacity
(``carry_capacity``), and, for stamina, the stamina term of his base max health
(``derive_base_max_health``). The stat lane's value table and taper rows are the example
seed (each extra at 7/8 of the one before, never below 2/3), so these journeys also prove
the seed is coherent.

- Ten equal condition buffs: his strength is the tapered total, and the check, carrying
  capacity and (for a stamina pile) max health all read that same value. His check is the
  same as an unbuffed twin's whose own strength is that total.
- One buff counts in full, as before.
- A debuff tapers in its own pile, apart from the bonuses.
- A sized technique buff cast on him adds the stat lane's value for its level and size; the
  same condition unsized adds its flat authored value.
- A sized distinction effect on strength adds the table value at his level and held size.
- With no stat-lane taper rows, ten buffs add in full (the behaviour before #4726).
- His vow's stat scaling rides the equipment walk and is never tapered by the worn pieces
  beside it.
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.checks.constants import ModifierLane, ModifierSize
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.modifier_models import ModifierTaper
from world.checks.modifier_values import load_value_table
from world.checks.services import perform_check_with_modifiers
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantRoleFactory, make_engaged_member
from world.covenants.models import VowStatScaling
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    CraftedItemRecipeFactory,
    CraftingRecipeFactory,
    CraftingRecipeModifierFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    TemplateSlotFactory,
)
from world.items.models import CraftingRecipe
from world.items.services.encumbrance import (
    CARRY_CAPACITY_BASE,
    CARRY_CAPACITY_PER_STRENGTH,
    carry_capacity,
)
from world.magic.constants import TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
)
from world.magic.models import Thread
from world.magic.models.techniques import ConditionTargetKind
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.modifier_values import seed_modifier_value_tables
from world.traits.constants import PrimaryStat
from world.traits.factories import StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals
from world.vitals.services import derive_base_max_health, get_vitals_consequence_config

BASE = 20  # strength 2 as shown; stats are stored x10
BUFF = 10  # +1 shown strength per buff
# Ten buffs of 10 in the stat lane's seeded taper: 10 x (1 + 7/8 + (7/8)^2 + (7/8)^3 + six
# at the 2/3 floor) = 73.1, which rounds to 73, not the plain 100.
TEN_TAPERED = 73


class StatBuffsAreValuedAndTapered(JourneyCase):
    """Brannoc's strength at the docks."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        self.room = self.make_room("The Salt Quay")
        SceneFactory(room=self.room)
        self.strength = StatTraitFactory(name=PrimaryStat.STRENGTH.value)
        self.stamina = StatTraitFactory(name=PrimaryStat.STAMINA.value)
        stat = ModifierCategoryFactory(name="stat")
        self.strength_target = ModifierTargetFactory(
            name="strength", category=stat, target_trait=self.strength
        )
        self.stamina_target = ModifierTargetFactory(
            name="stamina", category=stat, target_trait=self.stamina
        )
        self.lifting = CheckTypeFactory(name="Lifting")
        CheckTypeTraitFactory(check_type=self.lifting, trait=self.strength, weight=1)
        self.character_class = CharacterClassFactory()
        self.brannoc = self.porter("Brannoc", strength=BASE)

    # -- setup helpers ----------------------------------------------------------

    def porter(self, name: str, *, strength: int) -> ObjectDB:
        character = self.make_player(name, room=self.room)
        CharacterClassLevelFactory(
            character=character.sheet_data,
            character_class=self.character_class,
            level=6,
            is_primary=True,
        )
        character.sheet_data.invalidate_class_level_cache()
        character.traits.set_trait_value(self.strength.name, strength)
        character.traits.set_trait_value(self.stamina.name, BASE)
        return character

    def buff_condition(
        self, name: str, *, value: int = BUFF, target: ModifierTarget | None = None
    ) -> ConditionTemplate:
        condition = ConditionTemplateFactory(name=name)
        ConditionModifierEffectFactory(
            condition=condition, modifier_target=target or self.strength_target, value=value
        )
        return condition

    def buff(
        self, name: str, *, value: int = BUFF, target: ModifierTarget | None = None
    ) -> ConditionInstance:
        """A condition on Brannoc that changes a stat by ``value``."""
        condition = self.buff_condition(name, value=value, target=target)
        return ConditionInstanceFactory(target=self.brannoc, condition=condition)

    def strength_now(self) -> int:
        return self.brannoc.traits.get_trait_value(self.strength.name)

    def lift(self, character: ObjectDB) -> int:
        return perform_check_with_modifiers(
            character, self.lifting, target_difficulty=50
        ).total_points

    # -- journeys -----------------------------------------------------------------

    def test_ten_buffs_are_one_tapered_strength_wherever_it_is_read(self) -> None:
        lift_before = self.lift(self.brannoc)
        health_before = derive_base_max_health(self.brannoc.sheet_data)

        for index in range(10):
            self.buff(f"Dockside Cheer {index + 1}")
            self.buff(f"Second Wind {index + 1}", target=self.stamina_target)

        strength = BASE + TEN_TAPERED
        self.assertEqual(self.strength_now(), strength)
        self.assertEqual(self.brannoc.traits.get_trait_display_value(self.strength.name), 9)
        # The check reads it: one check point per stored strength unit on the seeded
        # conversion, and the same total as a twin whose own strength is 93.
        self.assertEqual(self.lift(self.brannoc) - lift_before, TEN_TAPERED)
        twin = self.porter("Bram", strength=strength)
        self.assertEqual(self.lift(self.brannoc), self.lift(twin))
        # Carrying capacity reads it.
        self.assertEqual(
            carry_capacity(self.brannoc),
            CARRY_CAPACITY_BASE + strength * CARRY_CAPACITY_PER_STRENGTH,
        )
        self.assertEqual(carry_capacity(self.brannoc), carry_capacity(twin))
        # His stamina pile tapers the same way, and his base max health reads it.
        self.assertEqual(self.brannoc.traits.get_trait_value(self.stamina.name), BASE + TEN_TAPERED)
        weight = get_vitals_consequence_config().stamina_to_health_weight
        self.assertEqual(
            derive_base_max_health(self.brannoc.sheet_data) - health_before,
            TEN_TAPERED * weight,
        )

    def test_one_buff_counts_in_full(self) -> None:
        lift_before = self.lift(self.brannoc)

        self.buff("Dockside Cheer")

        self.assertEqual(self.strength_now(), BASE + BUFF)
        self.assertEqual(self.lift(self.brannoc) - lift_before, BUFF)
        self.assertEqual(
            carry_capacity(self.brannoc),
            CARRY_CAPACITY_BASE + (BASE + BUFF) * CARRY_CAPACITY_PER_STRENGTH,
        )

    def test_a_debuff_tapers_in_its_own_pile(self) -> None:
        for index in range(10):
            self.buff(f"Dockside Cheer {index + 1}")
        self.buff("Wrenched Back", value=-BUFF)

        # The bonuses taper among themselves; the lone penalty counts in full.
        self.assertEqual(self.strength_now(), BASE + TEN_TAPERED - BUFF)

    def test_a_sized_technique_buff_adds_the_stat_tables_value(self) -> None:
        """Maren casts a Large strength buff on Brannoc the way the web client does."""
        maren = self.make_player("Maren", room=self.room)
        CharacterClassLevelFactory(
            character=maren.sheet_data,
            character_class=self.character_class,
            level=6,
            is_primary=True,
        )
        CharacterAnimaFactory(character=maren.sheet_data, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=maren.sheet_data, health=50, max_health=50, base_max_health=50
        )
        flat = 5
        condition = self.buff_condition("Ox Strength", value=flat)
        technique = TechniqueFactory(
            name="Ox Strength",
            gift=GiftFactory(),
            intensity=20,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=CheckTypeFactory(name="Casting")),
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
            modifier_size=ModifierSize.LARGE,
        )
        grant_technique(maren.sheet_data.primary_persona, technique)
        lift_before = self.lift(self.brannoc)

        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            result = self.web(
                maren,
                "cast_technique",
                technique_id=technique.pk,
                target_persona_id=self.brannoc.sheet_data.primary_persona.pk,
            )
        self.assertTrue(result.detail.success, result.detail.message)

        instance = ConditionInstance.objects.get(target=self.brannoc, condition=condition)
        self.assertEqual(instance.modifier_size, ModifierSize.LARGE)
        expected = load_value_table(ModifierLane.STAT).value(
            instance.modifier_level, ModifierSize.LARGE
        )
        self.assertIsNotNone(expected)
        self.assertNotEqual(expected, flat)
        self.assertEqual(self.strength_now(), BASE + expected)
        self.assertEqual(self.lift(self.brannoc) - lift_before, expected)

        # The same condition without a level and size keeps its flat authored value.
        instance.modifier_level = None
        instance.modifier_size = None
        instance.save(update_fields=["modifier_level", "modifier_size"])
        self.assertEqual(self.strength_now(), BASE + flat)

    def test_a_sized_distinction_adds_the_table_value_at_his_level(self) -> None:
        flat = 5
        giants_blood = DistinctionFactory(name="Giant's Blood", slug="giants-blood-4726")
        DistinctionEffectFactory(
            distinction=giants_blood,
            target=self.strength_target,
            value_per_rank=flat,
            modifier_size=ModifierSize.LARGE,
        )

        grant_distinction(self.brannoc.sheet_data, giants_blood, origin=DistinctionOrigin.GM_AWARD)

        # The seed's stat-lane Large modifier is worth 10 at level 6, not the flat 5.
        expected = load_value_table(ModifierLane.STAT).value(6, ModifierSize.LARGE)
        self.assertEqual(expected, 10)
        self.assertEqual(self.strength_now(), BASE + expected)

    def test_without_stat_taper_rows_ten_buffs_add_in_full(self) -> None:
        ModifierTaper.objects.filter(lane=ModifierLane.STAT).delete()

        for index in range(10):
            self.buff(f"Dockside Cheer {index + 1}")

        self.assertEqual(self.strength_now(), BASE + 10 * BUFF)

    def test_his_vow_stat_scaling_is_never_tapered(self) -> None:
        # His Durance vow scales strength by 4 per level of his vow thread (level 7): 28.
        role = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE, sword_weight=1, crown_weight=0
        )
        make_engaged_member(character_sheet=self.brannoc.sheet_data, covenant_role=role)
        VowStatScaling.objects.create(
            covenant_role=role, modifier_target=self.strength_target, bonus_per_level=4
        )
        Thread.objects.create(
            owner=self.brannoc.sheet_data,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            resonance=ResonanceFactory(),
            level=7,
        )
        self.brannoc.covenant_roles.invalidate()
        self.assertEqual(self.strength_now(), BASE + 28)

        # Two worn pieces, each +10 strength from the recipe they were made with.
        recipe = CraftingRecipeFactory()
        CraftingRecipeModifierFactory(recipe=recipe, target=self.strength_target, base_value=BUFF)
        self.wear_crafted("Porter's Harness", BodyRegion.TORSO, recipe)
        self.wear_crafted("Lifting Belt", BodyRegion.WAIST, recipe)

        # The pieces taper among themselves (10 + 8.75); the vow's 28 counts whole: 46.75.
        # Tapered as a third piece it would lead the pile: 28 + 8.75 + 7.66 = 44.
        self.assertEqual(self.strength_now(), BASE + 47)

    def wear_crafted(self, name: str, region: str, recipe: CraftingRecipe) -> None:
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template, body_region=region, equipment_layer=EquipmentLayer.BASE
        )
        template.__dict__.pop("cached_slots", None)
        item = ItemInstanceFactory(
            template=template,
            game_object=ObjectDBFactory(db_key=name, location=self.brannoc),
            holder_character_sheet=self.brannoc.sheet_data,
            quality_tier=QualityTierFactory(name="Sound"),
        )
        CraftedItemRecipeFactory(item_instance=item, recipe=recipe, quality_tier=item.quality_tier)
        self.assertIn(f"You equip {name}.", self.telnet(self.brannoc, f"wear {name}"))
