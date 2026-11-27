"""``equipment_walk_target_ids`` covers every target the equipment walk reaches (#5206).

The Bonuses band walks only the targets ``equipment_walk_target_ids`` names, so that set
must hold every target ``equipment_walk_total`` gives a non-zero amount on. The character
here exercises each of the walk's terms once: a worn facet's tier-0 pull, its
``FacetEffectBonus`` row and its crossing choice; a mantle's tier-0 pull and crossing
choice; the motif's style coherence; an engaged covenant role's bonus, its vow stat
scaling, and the covenant level bonus. A walk term added without a read in
``equipment_walk_target_ids`` should get its own setup here, and then fails this test.
"""

from __future__ import annotations

from django.test import TestCase, tag

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.conditions.factories import ConditionModifierEffectFactory, ConditionTemplateFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, make_engaged_member
from world.covenants.models import CovenantLevelBonus, CovenantRoleBonus, VowStatScaling
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    EquippedItemFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemStyleFactory,
    ItemTemplateFactory,
    MantleFactory,
    QualityTierFactory,
    StyleFactory,
    TemplateSlotFactory,
)
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    FacetFactory,
    MotifFactory,
    MotifResonanceFactory,
    MotifResonanceStyleFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import FacetEffectBonus
from world.magic.models.crossing import CrossingChoice, CrossingOption
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, ManeuverEffectKey
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierTarget
from world.mechanics.services import equipment_walk_target_ids, equipment_walk_total
from world.seeds.modifier_values import seed_pool_and_cap_lanes


def _crossing(thread, kind: str, resonance, target, value: int) -> None:
    """A crossing choice on ``thread`` whose condition adds ``value`` to ``target``."""
    template = ConditionTemplateFactory()
    ConditionModifierEffectFactory(condition=template, modifier_target=target, value=value)
    option = CrossingOption.objects.create(
        target_kind=kind,
        resonance=resonance,
        crossing_level=30,
        name=f"Crossing {kind} {target.name}",
        condition_template=template,
    )
    CrossingChoice.objects.create(thread=thread, crossing_level=30, option=option)


# The facet walker reads the equipped-items handler over the identity map; SQLite's reused
# pks can hand it a stale facet across tests (see ``test_aesthetic_composition``).
@tag("postgres")
class EquipmentWalkTargetIdsCoverTheWalkTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_pool_and_cap_lanes()
        ensure_maneuver_effects()
        cls.char = CharacterFactory(db_key="WalkTargetsChar")
        cls.sheet = CharacterSheetFactory(character=cls.char, primary_persona=False)
        CharacterClassLevelFactory(character=cls.sheet, level=2)
        quality = QualityTierFactory(name="WalkTargetsCommon", stat_multiplier="1.00")
        resonance_category = ModifierCategoryFactory(name="resonance")
        stat = ModifierCategoryFactory(name="stat")

        def resonance_target(name: str):
            resonance = ResonanceFactory()
            return resonance, ModifierTargetFactory(
                name=name, category=resonance_category, target_resonance=resonance
            )

        # A worn facet: its tier-0 pull, its FacetEffectBonus row and its crossing choice.
        cls.facet_resonance, cls.facet_target = resonance_target("WalkFacetPull")
        facet = FacetFactory(name="WalkFacet")
        facet_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.facet_resonance,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            target_trait=None,
            level=1,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=cls.facet_resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )
        cls.maneuver_target = ModifierTargetFactory(
            name="WalkFacetEffect",
            category=ModifierCategoryFactory(name=MANEUVER_EFFECT_CATEGORY_NAME),
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.STRIKE_BASE_DAMAGE),
        )
        FacetEffectBonus.objects.create(facet=facet, target=cls.maneuver_target, amount_tenths=10)
        cls.facet_crossing_target = ModifierTargetFactory(name="WalkFacetCrossing", category=stat)
        _crossing(facet_thread, TargetKind.FACET, cls.facet_resonance, cls.facet_crossing_target, 4)

        # One worn piece carries the facet and a style the motif binds.
        style = StyleFactory(name="WalkStyle")
        cls.style_resonance, cls.style_target = resonance_target("WalkMotifStyle")
        motif = MotifFactory(character=cls.sheet)
        MotifResonanceStyleFactory(
            motif_resonance=MotifResonanceFactory(motif=motif, resonance=cls.style_resonance),
            style=style,
        )
        template = ItemTemplateFactory(name="WalkCoat", facet_capacity=1)
        TemplateSlotFactory(
            template=template, body_region=BodyRegion.TORSO, equipment_layer=EquipmentLayer.BASE
        )
        coat = ItemInstanceFactory(template=template, quality_tier=quality)
        ItemFacetFactory(item_instance=coat, facet=facet, attachment_quality_tier=quality)
        ItemStyleFactory(item_instance=coat, style=style, attachment_quality_tier=quality)
        EquippedItemFactory(
            character=cls.sheet,
            item_instance=coat,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        # A mantle: its tier-0 pull and its crossing choice.
        cls.mantle_resonance, cls.mantle_target = resonance_target("WalkMantlePull")
        mantle_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.mantle_resonance,
            target_kind=TargetKind.MANTLE,
            target_mantle=MantleFactory(name="WalkMantle"),
            target_trait=None,
            level=2,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.MANTLE,
            resonance=cls.mantle_resonance,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=3,
        )
        cls.mantle_crossing_target = ModifierTargetFactory(name="WalkMantleCrossing", category=stat)
        _crossing(
            mantle_thread, TargetKind.MANTLE, cls.mantle_resonance, cls.mantle_crossing_target, 6
        )

        # An engaged covenant role: its own bonus, its vow stat scaling, the level bonus.
        membership = make_engaged_member(
            character_sheet=cls.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE, level=3),
        )
        role = membership.covenant_role
        ThreadFactory(
            owner=cls.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
            level=10,
        )
        cls.role_target = ModifierTargetFactory(
            name="WalkRoleFavor", category=ModifierCategoryFactory(name="favor_invocation")
        )
        CovenantRoleBonus.objects.create(
            covenant_role=role, modifier_target=cls.role_target, bonus_per_level=2
        )
        cls.vow_target = ModifierTargetFactory(name="WalkVowScaling", category=stat)
        VowStatScaling.objects.create(
            covenant_role=role, modifier_target=cls.vow_target, bonus_per_level=1
        )
        cls.level_target = ModifierTargetFactory(name="WalkCovenantLevel", category=stat)
        CovenantLevelBonus.objects.create(modifier_target=cls.level_target, bonus_per_level=2)

    def setUp(self) -> None:
        self.char.threads.invalidate()
        self.char.equipped_items.invalidate()
        self.char.covenant_roles.invalidate()

    def test_each_walk_term_reaches_its_target(self) -> None:
        """The fixture really exercises every term: each target gets an amount."""
        for target in (
            self.facet_target,
            self.maneuver_target,
            self.facet_crossing_target,
            self.style_target,
            self.mantle_target,
            self.mantle_crossing_target,
            self.role_target,
            self.vow_target,
            self.level_target,
        ):
            with self.subTest(target=target.name):
                self.assertNotEqual(equipment_walk_total(self.sheet, target), 0)

    def test_every_target_the_walk_reaches_is_named(self) -> None:
        named = equipment_walk_target_ids(self.sheet)
        reached = {
            target.name
            for target in ModifierTarget.objects.select_related("category")
            if equipment_walk_total(self.sheet, target) != 0
        }
        missed = {
            target.name
            for target in ModifierTarget.objects.filter(name__in=reached).exclude(pk__in=named)
        }

        self.assertEqual(missed, set())
        self.assertGreaterEqual(len(reached), 9)
