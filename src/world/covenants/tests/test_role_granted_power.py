"""Tests for role-granted gifts, techniques, and archetype combos (#2022)."""

from django.test import TestCase

from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
    ComboSlotFactory,
)
from world.combat.services import detect_available_combos
from world.covenants.constants import CovenantType, RoleArchetype
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.models import CovenantRoleGiftGrant
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory


class RoleGrantedGiftsTests(TestCase):
    """Engaging a role grants its gifts' techniques; disengaging revokes them (#2022)."""

    def test_engage_grants_role_techniques(self):
        """An engaged role grants its gift's techniques to the character."""
        from world.magic.models import CharacterTechnique

        cov = CovenantFactory(name="TestCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        gift = GiftFactory(name="RoleGift")
        technique = TechniqueFactory(gift=gift)

        # Link the gift to the role.
        CovenantRoleGiftGrant.objects.create(
            covenant_role=role,
            gift=gift,
            unlock_thread_level=0,
        )

        membership = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)
        sheet = membership.character_sheet

        # No techniques before engage.
        self.assertFalse(
            CharacterTechnique.objects.filter(character=sheet, technique=technique).exists()
        )

        # Engage the role.
        from world.covenants.services import set_engaged_membership

        set_engaged_membership(membership=membership)

        # Technique is now granted, with role_source set.
        ct = CharacterTechnique.objects.filter(character=sheet, technique=technique).first()
        self.assertIsNotNone(ct)
        self.assertEqual(ct.role_source, membership)

    def test_disengage_revokes_role_techniques(self):
        """Disengaging a role revokes its auto-granted techniques (#2022 + #2051)."""
        from world.covenants.services import (
            clear_engaged_membership,
            set_engaged_membership,
        )
        from world.magic.models import CharacterTechnique

        cov = CovenantFactory(name="RevokeCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        gift = GiftFactory(name="RevokeGift")
        technique = TechniqueFactory(gift=gift)
        CovenantRoleGiftGrant.objects.create(
            covenant_role=role,
            gift=gift,
            unlock_thread_level=0,
        )

        membership = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)
        sheet = membership.character_sheet

        set_engaged_membership(membership=membership)
        self.assertTrue(
            CharacterTechnique.objects.filter(character=sheet, technique=technique).exists()
        )

        clear_engaged_membership(membership=membership)
        self.assertFalse(
            CharacterTechnique.objects.filter(character=sheet, technique=technique).exists()
        )

    def test_disengage_preserves_independently_learned_techniques(self):
        """Techniques learned independently are NOT revoked on disengage (#2022)."""
        from world.covenants.services import (
            clear_engaged_membership,
            set_engaged_membership,
        )
        from world.magic.models import CharacterTechnique

        cov = CovenantFactory(name="PreserveCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        gift = GiftFactory(name="PreserveGift")
        technique = TechniqueFactory(gift=gift)
        CovenantRoleGiftGrant.objects.create(
            covenant_role=role,
            gift=gift,
            unlock_thread_level=0,
        )

        membership = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)
        sheet = membership.character_sheet

        # Learn the technique independently BEFORE engaging.
        CharacterTechnique.objects.create(character=sheet, technique=technique)

        set_engaged_membership(membership=membership)
        # The independently-learned technique should still be there (get_or_create is idempotent).
        ct = CharacterTechnique.objects.get(character=sheet, technique=technique)
        # role_source should be None — it was learned independently.
        self.assertIsNone(ct.role_source)

        clear_engaged_membership(membership=membership)
        # The technique should STILL be there — it was learned independently.
        self.assertTrue(
            CharacterTechnique.objects.filter(character=sheet, technique=technique).exists()
        )


class ComboSlotArchetypeTests(TestCase):
    """ComboSlot.required_archetype gates combo availability by role archetype (#2022)."""

    def test_archetype_gated_combo_requires_matching_role(self):
        """A combo with required_archetype=SWORD only matches SWORD-role participants."""
        from world.combat.constants import ActionCategory
        from world.combat.models import CombatRoundAction
        from world.scenes.constants import RoundStatus

        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )

        # Two PCs: one with a SWORD role, one without a role.
        from world.character_sheets.factories import CharacterSheetFactory

        sword_sheet = CharacterSheetFactory()
        plain_sheet = CharacterSheetFactory()
        sword_participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sword_sheet,
        )
        plain_participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=plain_sheet,
        )

        # Set up a SWORD role for the first PC.
        cov = CovenantFactory(name="ArchComboCov", covenant_type=CovenantType.DURANCE)
        sword_role = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE,
            sword_weight=1,
        )
        from evennia_extensions.factories import ObjectDBFactory
        from world.covenants.services import set_engaged_membership
        from world.scenes.factories import SceneFactory

        room = ObjectDBFactory(db_key="ArchComboRoom", db_typeclass_path="typeclasses.rooms.Room")
        sword_sheet.character.db_location = room
        sword_sheet.character.save(update_fields=["db_location"])
        SceneFactory(location=room, is_active=True)

        sword_membership = CharacterCovenantRoleFactory(
            character_sheet=sword_sheet,
            covenant=cov,
            covenant_role=sword_role,
        )
        # Need a second covenant member for Durance engage
        other_membership = CharacterCovenantRoleFactory(
            covenant=cov,
            covenant_role=sword_role,
        )
        other_sheet = other_membership.character_sheet
        other_sheet.character.db_location = room
        other_sheet.character.save(update_fields=["db_location"])

        set_engaged_membership(membership=sword_membership)
        set_engaged_membership(membership=other_membership)

        effect_type = EffectTypeFactory(name="ArchComboAttack")
        gift = GiftFactory()
        technique1 = TechniqueFactory(gift=gift, effect_type=effect_type)
        technique2 = TechniqueFactory(gift=GiftFactory(), effect_type=effect_type)

        CombatRoundAction.objects.create(
            participant=sword_participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique1,
        )
        CombatRoundAction.objects.create(
            participant=plain_participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique2,
        )

        # Combo requires SWORD archetype on slot 1.
        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=effect_type,
            required_archetype=RoleArchetype.SWORD,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=effect_type,
        )

        available = detect_available_combos(encounter, 1)
        # Should be available — sword_participant fills slot 1 (SWORD), plain fills slot 2.
        self.assertEqual(len(available), 1)
