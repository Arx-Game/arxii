"""Tests for vow-driven stat scaling, gear scaling, per-role action scaling,
role-source variant resolution, and capability grant wiring (#2022 completion).

Covers the spec items that were missing from the prematurely-merged PR #2106:
1. VowStatScaling — thread-level stat scaling in the modifier pipeline
2. VowGearScaling — equipment effectiveness multiplier, short-circuited to 0
   pending #2533 (#2529 Layer 1); see ``VowGearScalingTests`` below
3. Role-source variant resolution — COVENANT_ROLE thread level for role-granted techniques
4. Capability grant wiring — CovenantRole.granted_capabilities M2M read by the handler
5. CovenantRoleActionScaling — interpose partial-block scaling per engaged role
   (was ArchetypeActionScaling; #2529 Task 2 rewrites the consumer,
   ``covenant_role_action_scaling_bonus``, against the blend + re-keyed model)
6. Enhancement overlap — flat bonus when enhancement technique overlaps existing kit
"""

from decimal import Decimal

from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantRoleActionScalingFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.models import (
    VowStatScaling,
)
from world.covenants.services import (
    covenant_role_action_scaling_bonus,
    set_engaged_membership,
)
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)


class VowStatScalingTests(TestCase):
    """VowStatScaling adds thread-level-scaled stat bonuses to the modifier pipeline (#2022)."""

    def test_no_scaling_when_not_engaged(self):
        """An unengaged character gets 0 from vow stat scaling."""
        from world.mechanics.services import vow_stat_scaling_bonus

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet

        self.assertEqual(vow_stat_scaling_bonus(sheet, None), 0)

    def test_no_scaling_when_no_config_row(self):
        """An engaged character with no VowStatScaling row gets 0."""
        from world.mechanics.services import vow_stat_scaling_bonus

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet

        set_engaged_membership(membership=membership)

        self.assertEqual(vow_stat_scaling_bonus(sheet, None), 0)

    def test_scaling_with_thread_level(self):
        """When the character has a COVENANT_ROLE thread, the scaling fires."""
        from world.magic.constants import TargetKind
        from world.magic.models import Thread
        from world.mechanics.models import ModifierCategory, ModifierTarget
        from world.mechanics.services import vow_stat_scaling_bonus

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet

        cat = ModifierCategory.objects.first()
        if cat is None:
            cat = ModifierCategory.objects.create(name="stat", display_order=1)
        target = ModifierTarget.objects.create(name="test_vow_stat_2", category=cat)

        VowStatScaling.objects.create(
            covenant_role=role,
            modifier_target=target,
            bonus_per_level=3,
        )

        resonance = ResonanceFactory()
        Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            resonance=resonance,
            level=10,
        )

        set_engaged_membership(membership=membership)

        bonus = vow_stat_scaling_bonus(sheet, target)
        self.assertEqual(bonus, 30)  # 10 * 3


class VowGearScalingTests(TestCase):
    """VowGearScaling is deferred pending #2533 (#2529 Task 2, Layer 1)."""

    def test_short_circuits_to_zero_pending_2533(self):
        """``vow_gear_scaling_bonus`` unconditionally returns 0 (mechanics/services.py:991-1003).

        #2529 short-circuited this function ahead of the VowGearScaling model's
        eventual fate; #2533 decides whether the model is reworked or removed.
        Engagement/config-row state has no bearing on the result today, so this
        test asserts the constant directly rather than building setup that the
        function no longer reads.
        """
        from world.mechanics.services import vow_gear_scaling_bonus

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, shield_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet

        self.assertEqual(vow_gear_scaling_bonus(sheet, None), 0)


class CovenantRoleActionScalingTests(TestCase):
    """CovenantRoleActionScaling provides a bonus for combat actions per role (#2529, was #2022).

    ``covenant_role_action_scaling_bonus`` sums thread_level × multiplier across the
    character's engaged roles that have a scaling row for the given action_key. Rows
    and COVENANT_ROLE threads key on the ANCHOR (parent) role — see
    ``test_sub_role_scaling_resolves_via_parent_row`` for the sub-role normalization.
    """

    def test_no_bonus_when_not_engaged(self):
        """An unengaged character gets 0.0 bonus."""
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, shield_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        character = membership.character_sheet.character

        CovenantRoleActionScalingFactory(
            covenant_role=role,
            action_key="combat_interpose",
            thread_level_multiplier=Decimal("0.10"),
        )

        bonus = covenant_role_action_scaling_bonus(character, "combat_interpose")
        self.assertEqual(bonus, 0.0)

    def test_no_bonus_when_no_scaling_row(self):
        """An engaged character with no scaling row gets 0.0."""
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, shield_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        character = membership.character_sheet.character

        set_engaged_membership(membership=membership)

        bonus = covenant_role_action_scaling_bonus(character, "combat_interpose")
        self.assertEqual(bonus, 0.0)

    def test_bonus_scales_by_thread_level(self):
        """thread_level * multiplier for the engaged role's scaling row."""
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, shield_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet
        character = sheet.character

        CovenantRoleActionScalingFactory(
            covenant_role=role,
            action_key="combat_interpose",
            thread_level_multiplier=Decimal("0.10"),
        )

        resonance = ResonanceFactory()
        Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            resonance=resonance,
            level=10,
        )

        set_engaged_membership(membership=membership)

        bonus = covenant_role_action_scaling_bonus(character, "combat_interpose")
        self.assertEqual(bonus, 1.0)  # 10 * 0.10 = 1.0

    def test_sub_role_scaling_resolves_via_parent_row(self):
        """A resolved SUB-role still picks up the PARENT's scaling row (#2529 ADR-0055).

        The membership row is stored on the parent role; ``currently_engaged_roles``
        resolves it to the matching sub-role via the COVENANT_ROLE thread's resonance
        and level. The scaling row and the thread both key on the parent (anchor)
        role, so the bonus lookup must normalize the resolved sub-role back to its
        parent before querying.
        """
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        parent = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, shield_weight=1)
        resonance = ResonanceFactory()
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=3,
        )
        membership = CharacterCovenantRoleFactory(covenant_role=parent)
        sheet = membership.character_sheet
        character = sheet.character

        CovenantRoleActionScalingFactory(
            covenant_role=parent,
            action_key="combat_interpose",
            thread_level_multiplier=Decimal("0.10"),
        )

        Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent,
            resonance=resonance,
            level=10,
        )

        set_engaged_membership(membership=membership)

        # Sanity: the engaged role resolves to the sub-role, not the parent.
        engaged = character.covenant_roles.currently_engaged_roles()
        self.assertEqual(engaged, [subrole])

        bonus = covenant_role_action_scaling_bonus(character, "combat_interpose")
        self.assertEqual(bonus, 1.0)  # 10 * 0.10, via the parent's scaling row


class RoleSourceVariantResolutionTests(TestCase):
    """Role-granted techniques resolve variants by COVENANT_ROLE thread level (#2022)."""

    def test_role_source_uses_covenant_role_thread(self):
        """A CharacterTechnique with role_source resolves via COVENANT_ROLE thread."""
        from world.magic.constants import TargetKind
        from world.magic.models import CharacterTechnique, Thread
        from world.magic.specialization.models import TechniqueVariant
        from world.magic.specialization.services import resolve_specialized_variant

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet
        character = sheet.character

        gift = GiftFactory(name="VariantGift")
        technique = TechniqueFactory(gift=gift)
        resonance = ResonanceFactory()

        ct = CharacterTechnique.objects.create(
            character=sheet,
            technique=technique,
            role_source=membership,
        )

        Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            resonance=resonance,
            level=3,
        )

        TechniqueVariant.objects.create(
            parent_technique=technique,
            resonance=resonance,
            unlock_thread_level=3,
            name_override="Specialized Form",
            intensity_delta=2,
            control_delta=1,
        )

        resolved = resolve_specialized_variant(
            entity=technique,
            character=character,
            character_technique=ct,
        )

        self.assertEqual(resolved.name, "Specialized Form")

    def test_no_role_source_uses_gift_thread(self):
        """CharacterTechnique without role_source resolves via GIFT thread."""
        from world.magic.specialization.services import resolve_specialized_variant

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet
        character = sheet.character

        gift = GiftFactory(name="NoRoleGift")
        technique = TechniqueFactory(gift=gift)

        from world.magic.models import CharacterTechnique

        CharacterTechnique.objects.create(
            character=sheet,
            technique=technique,
        )

        resolved = resolve_specialized_variant(
            entity=technique,
            character=character,
        )
        self.assertEqual(resolved.name, technique.name)


class CapabilityGrantWiringTests(TestCase):
    """CovenantRole.granted_capabilities M2M is read by passive_capability_grants (#2022)."""

    def test_engaged_role_grants_capabilities(self):
        """An engaged role's granted_capabilities appear in passive_capability_grants."""
        from world.conditions.models import CapabilityType
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, shield_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet
        character = sheet.character

        cap = CapabilityType.objects.create(name="test_shield_cap")
        resonance = ResonanceFactory()

        # The handler requires at least one thread to not early-return
        Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            resonance=resonance,
            level=0,
        )

        set_engaged_membership(membership=membership)
        role.granted_capabilities.add(cap)

        character.threads.invalidate()

        granted = character.threads.passive_capability_grants()
        self.assertIn(cap.pk, granted)

    def test_disengaged_role_revokes_capabilities(self):
        """Disengaging a role removes its granted_capabilities."""
        from world.conditions.models import CapabilityType
        from world.covenants.services import clear_engaged_membership
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, shield_weight=1)
        membership = CharacterCovenantRoleFactory(covenant_role=role)
        sheet = membership.character_sheet
        character = sheet.character

        cap = CapabilityType.objects.create(name="test_revoke_cap")
        resonance = ResonanceFactory()

        Thread.objects.create(
            owner=sheet,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            resonance=resonance,
            level=0,
        )

        set_engaged_membership(membership=membership)
        role.granted_capabilities.add(cap)
        character.threads.invalidate()

        self.assertIn(cap.pk, character.threads.passive_capability_grants())

        clear_engaged_membership(membership=membership)
        character.threads.invalidate()

        self.assertNotIn(cap.pk, character.threads.passive_capability_grants())


class EnhancementOverlapTests(TestCase):
    """Enhancement techniques grant a flat bonus when overlapping existing kit (#2022)."""

    def test_no_bonus_without_enhances_effect_type(self):
        """A technique without enhances_effect_type gets no enhancement bonus."""
        from world.magic.services.power_terms import PowerTermContext, enhancement_overlap_term

        gift = GiftFactory(name="NoEnhanceGift")
        technique = TechniqueFactory(gift=gift)
        membership = CharacterCovenantRoleFactory(covenant_role=CovenantRoleFactory())
        sheet = membership.character_sheet

        ctx = PowerTermContext(sheet=sheet, technique=technique, applicable_threads=[])
        self.assertEqual(enhancement_overlap_term(ctx), 0)

    def test_bonus_with_overlap(self):
        """An enhancement technique with a matching existing technique gets a bonus."""
        from world.magic.models import CharacterTechnique
        from world.magic.services.power_terms import PowerTermContext, enhancement_overlap_term

        effect_type = EffectTypeFactory(name="Attack")
        gift = GiftFactory(name="EnhanceGift")
        technique = TechniqueFactory(gift=gift, effect_type=effect_type)
        technique.enhances_effect_type = effect_type
        technique.save()

        membership = CharacterCovenantRoleFactory(covenant_role=CovenantRoleFactory())
        sheet = membership.character_sheet

        other_technique = TechniqueFactory(gift=gift, effect_type=effect_type)
        CharacterTechnique.objects.create(character=sheet, technique=other_technique)

        ctx = PowerTermContext(sheet=sheet, technique=technique, applicable_threads=[])
        self.assertGreater(enhancement_overlap_term(ctx), 0)

    def test_no_bonus_without_overlap(self):
        """An enhancement technique with no matching existing technique gets 0."""
        from world.magic.services.power_terms import PowerTermContext, enhancement_overlap_term

        effect_type = EffectTypeFactory(name="Defense")
        other_effect_type = EffectTypeFactory(name="Healing")
        gift = GiftFactory(name="NoOverlapGift")
        technique = TechniqueFactory(gift=gift, effect_type=effect_type)
        technique.enhances_effect_type = other_effect_type
        technique.save()

        membership = CharacterCovenantRoleFactory(covenant_role=CovenantRoleFactory())
        sheet = membership.character_sheet

        ctx = PowerTermContext(sheet=sheet, technique=technique, applicable_threads=[])
        self.assertEqual(enhancement_overlap_term(ctx), 0)
