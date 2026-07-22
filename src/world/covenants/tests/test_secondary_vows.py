"""Tests for secondary covenant vows (#2641): the ``is_secondary`` membership flag,
engage-time validation, the handler's flagged/primary-only views, chassis isolation
for covenant-owned Layer 1/3 consumers, the potency-dial config, and Layer 4's
sub-role suppression for a secondary membership.

Built in ``setUp`` rather than ``setUpTestData`` throughout — factories here create
Evennia ``ObjectDB`` instances (``DbHolder``, not deepcopyable), the same rationale
every neighboring covenants test file documents.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.exceptions import (
    SecondaryVowRequiresEngagedPrimaryError,
    SecondaryVowSameAnchorError,
    SecondaryVowThreadExceedsPrimaryError,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleDefenseProfileFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowSituationalPerkFactory,
)
from world.covenants.models import SecondaryVowConfig
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.perks.services import FiredPerk, applicable_perks
from world.covenants.services import (
    gear_additive_fraction,
    secondary_vow_config,
    set_engaged_membership,
)
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.magic.models import Thread


def _covenant_role_thread(*, sheet, role, resonance, level):
    return ThreadFactory(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.COVENANT_ROLE,
        target_trait=None,
        target_covenant_role=role,
        level=level,
    )


class SecondaryVowEngageValidationTests(TestCase):
    """set_engaged_membership(as_secondary=True) validation (#2641)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.primary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.primary_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
        )
        set_engaged_membership(membership=self.primary_membership)

    def _secondary_membership(self, role=None):
        role = role or CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        return CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=role,
        )

    def test_primary_and_secondary_coexist(self) -> None:
        secondary_membership = self._secondary_membership()
        set_engaged_membership(membership=secondary_membership, as_secondary=True)

        self.primary_membership.refresh_from_db()
        secondary_membership.refresh_from_db()
        self.assertTrue(self.primary_membership.engaged)
        self.assertFalse(self.primary_membership.is_secondary)
        self.assertTrue(secondary_membership.engaged)
        self.assertTrue(secondary_membership.is_secondary)

    def test_second_secondary_same_type_swaps_out_the_first(self) -> None:
        """Mirrors the primary un-engage loop: engaging a NEW secondary un-engages
        the previously engaged secondary of the same type, leaving the primary
        untouched — scoped by ``is_secondary``, not a rejection."""
        first_secondary = self._secondary_membership()
        set_engaged_membership(membership=first_secondary, as_secondary=True)

        second_secondary = self._secondary_membership()
        set_engaged_membership(membership=second_secondary, as_secondary=True)

        self.primary_membership.refresh_from_db()
        first_secondary.refresh_from_db()
        second_secondary.refresh_from_db()
        self.assertTrue(self.primary_membership.engaged)
        self.assertFalse(first_secondary.engaged)
        self.assertTrue(second_secondary.engaged)

    def test_model_clean_rejects_two_simultaneously_engaged_secondaries(self) -> None:
        """Direct model-level proof of the exclusivity invariant: two active engaged
        rows with the same (character_sheet, covenant_type, is_secondary=True) is
        invalid even when constructed by hand (bypassing the service's swap)."""
        first_secondary = self._secondary_membership()
        first_secondary.engaged = True
        first_secondary.is_secondary = True
        first_secondary.save(update_fields=["engaged", "is_secondary"])

        second_secondary = self._secondary_membership()
        second_secondary.engaged = True
        second_secondary.is_secondary = True

        with self.assertRaises(ValidationError):
            second_secondary.full_clean()

    def test_same_anchor_secondary_rejected(self) -> None:
        secondary_membership = self._secondary_membership(role=self.primary_role)

        with self.assertRaises(SecondaryVowSameAnchorError):
            set_engaged_membership(membership=secondary_membership, as_secondary=True)

    def test_secondary_thread_exceeds_primary_rejected(self) -> None:
        resonance_a = ResonanceFactory()
        resonance_b = ResonanceFactory()
        _covenant_role_thread(
            sheet=self.sheet, role=self.primary_role, resonance=resonance_a, level=2
        )
        secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        _covenant_role_thread(sheet=self.sheet, role=secondary_role, resonance=resonance_b, level=5)
        secondary_membership = self._secondary_membership(role=secondary_role)

        with self.assertRaises(SecondaryVowThreadExceedsPrimaryError):
            set_engaged_membership(membership=secondary_membership, as_secondary=True)

    def test_secondary_thread_equal_to_primary_allowed(self) -> None:
        resonance_a = ResonanceFactory()
        resonance_b = ResonanceFactory()
        _covenant_role_thread(
            sheet=self.sheet, role=self.primary_role, resonance=resonance_a, level=3
        )
        secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        _covenant_role_thread(sheet=self.sheet, role=secondary_role, resonance=resonance_b, level=3)
        secondary_membership = self._secondary_membership(role=secondary_role)

        set_engaged_membership(membership=secondary_membership, as_secondary=True)

        secondary_membership.refresh_from_db()
        self.assertTrue(secondary_membership.engaged)

    def test_missing_threads_count_as_zero(self) -> None:
        """Neither role has a COVENANT_ROLE thread — 0 <= 0 passes."""
        secondary_membership = self._secondary_membership()

        set_engaged_membership(membership=secondary_membership, as_secondary=True)

        secondary_membership.refresh_from_db()
        self.assertTrue(secondary_membership.engaged)

    def test_secondary_without_engaged_primary_rejected(self) -> None:
        other_sheet = CharacterSheetFactory()
        secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        secondary_membership = CharacterCovenantRoleFactory(
            character_sheet=other_sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=secondary_role,
        )

        with self.assertRaises(SecondaryVowRequiresEngagedPrimaryError):
            set_engaged_membership(membership=secondary_membership, as_secondary=True)

    def test_supreme_champion_guards_stay_global_for_secondary(self) -> None:
        """A secondary engaged Champion row still trips the covenant-scoped Champion
        guard — that exclusivity is NOT scoped by ``is_secondary`` (#2641). The
        Champion guard is per-COVENANT (two characters can't both be Champion of
        the SAME covenant), so the challenger's primary vow lives in a different
        Battle covenant and their secondary reaches into the holder's covenant."""
        battle_covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        champion_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE, is_champion_role=True
        )
        holder_sheet = CharacterSheetFactory()
        challenger_sheet = CharacterSheetFactory()

        holder_membership = CharacterCovenantRoleFactory(
            character_sheet=holder_sheet,
            covenant=battle_covenant,
            covenant_role=champion_role,
        )
        set_engaged_membership(membership=holder_membership)

        # Challenger's PRIMARY vow lives in a SEPARATE Battle covenant (a covenant
        # can only hold one active membership row per character).
        challenger_primary = CharacterCovenantRoleFactory(
            character_sheet=challenger_sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.BATTLE),
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.BATTLE),
        )
        set_engaged_membership(membership=challenger_primary)

        challenger_secondary = CharacterCovenantRoleFactory(
            character_sheet=challenger_sheet,
            covenant=battle_covenant,
            covenant_role=champion_role,
        )
        with self.assertRaises(ValidationError):
            set_engaged_membership(membership=challenger_secondary, as_secondary=True)


class SecondaryVowHandlerTests(TestCase):
    """Handler methods added/adjusted for #2641."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.primary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.primary_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
            engaged=True,
            is_secondary=False,
        )
        self.secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.secondary_membership = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.secondary_role,
            engaged=True,
            is_secondary=True,
        )

    def test_currently_engaged_primary_roles_excludes_secondary(self) -> None:
        roles = self.character.covenant_roles.currently_engaged_primary_roles()
        self.assertEqual(roles, [self.primary_role])

    def test_currently_engaged_roles_includes_both(self) -> None:
        roles = self.character.covenant_roles.currently_engaged_roles()
        self.assertEqual(set(roles), {self.primary_role, self.secondary_role})

    def test_currently_engaged_roles_with_flags(self) -> None:
        pairs = self.character.covenant_roles.currently_engaged_roles_with_flags()
        self.assertEqual(set(pairs), {(self.primary_role, False), (self.secondary_role, True)})

    def test_secondary_resolves_at_anchor_even_when_subrole_qualifies(self) -> None:
        """A secondary membership's own COVENANT_ROLE thread qualifying for a
        sub-role does NOT graduate it — resolution stays at the anchor for both
        ``currently_engaged_roles`` and ``currently_engaged_roles_with_flags``."""
        resonance = ResonanceFactory()
        sub_role = SubroleCovenantRoleFactory(
            parent_role=self.secondary_role, resonance=resonance, unlock_thread_level=3
        )
        _covenant_role_thread(
            sheet=self.sheet, role=self.secondary_role, resonance=resonance, level=3
        )
        self.character.threads.invalidate()

        roles = self.character.covenant_roles.currently_engaged_roles()
        self.assertIn(self.secondary_role, roles)
        self.assertNotIn(sub_role, roles)

        pairs = self.character.covenant_roles.currently_engaged_roles_with_flags()
        self.assertIn((self.secondary_role, True), pairs)


class SecondaryVowChassisIsolationTests(TestCase):
    """Layer 1/3 chassis consumers owned by the covenants app never read a secondary
    membership — zero chassis leak (#2641)."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.primary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=self.primary_role,
            engaged=True,
            is_secondary=False,
        )

    def test_precedence_role_for_combat_ignores_secondary_battle_vow(self) -> None:
        """A secondary BATTLE vow must not win combat precedence over a primary
        DURANCE vow — precedence is PRIMARY-only (#2641)."""
        from world.covenants.services import precedence_role_for_combat

        secondary_battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.BATTLE),
            covenant_role=secondary_battle_role,
            engaged=True,
            is_secondary=True,
        )

        resolved = precedence_role_for_combat(self.sheet)
        self.assertEqual(resolved, self.primary_role)

    def test_gear_additive_fraction_unaffected_by_secondary_profile(self) -> None:
        CovenantRoleDefenseProfileFactory(covenant_role=self.primary_role, gear_additive_tenths=5)
        baseline = gear_additive_fraction(self.character)
        self.assertEqual(baseline, Decimal(5) / 10)

        secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        CovenantRoleDefenseProfileFactory(covenant_role=secondary_role, gear_additive_tenths=10)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=secondary_role,
            engaged=True,
            is_secondary=True,
        )

        with_secondary = gear_additive_fraction(self.character)
        self.assertEqual(with_secondary, baseline)

    def test_covenant_role_action_scaling_bonus_unaffected_by_secondary(self) -> None:
        from world.covenants.factories import CovenantRoleActionScalingFactory
        from world.covenants.services import covenant_role_action_scaling_bonus

        CovenantRoleActionScalingFactory(
            covenant_role=self.primary_role,
            action_key="combat_interpose",
            thread_level_multiplier=Decimal("0.10"),
        )
        resonance = ResonanceFactory()
        _covenant_role_thread(
            sheet=self.sheet, role=self.primary_role, resonance=resonance, level=10
        )
        baseline = covenant_role_action_scaling_bonus(self.character, "combat_interpose")
        self.assertEqual(baseline, 1.0)

        secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        CovenantRoleActionScalingFactory(
            covenant_role=secondary_role,
            action_key="combat_interpose",
            thread_level_multiplier=Decimal("5.0"),  # would swamp the result if it leaked
        )
        secondary_resonance = ResonanceFactory()
        _covenant_role_thread(
            sheet=self.sheet, role=secondary_role, resonance=secondary_resonance, level=10
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            covenant_role=secondary_role,
            engaged=True,
            is_secondary=True,
        )

        with_secondary = covenant_role_action_scaling_bonus(self.character, "combat_interpose")
        self.assertEqual(with_secondary, baseline)


class SecondaryVowConfigTests(TestCase):
    """The potency-dial singleton (#2641)."""

    def test_lazy_created_with_ratified_default(self) -> None:
        self.assertFalse(SecondaryVowConfig.objects.exists())
        config = secondary_vow_config()
        self.assertEqual(config.potency_tenths, 6)
        self.assertTrue(SecondaryVowConfig.objects.filter(pk=1).exists())

    def test_cached_singleton_reads_staff_edits(self) -> None:
        config = secondary_vow_config()
        config.potency_tenths = 8
        config.save()

        self.assertEqual(secondary_vow_config().potency_tenths, 8)


class SecondaryVowPerkSubRoleSuppressionTests(TestCase):
    """Layer 4 candidate gatherers never emit a sub-role candidate for a secondary
    membership — depth stays primary-only (#2641)."""

    def setUp(self) -> None:
        self.resonance = ResonanceFactory()
        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.parent_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.sub_role = SubroleCovenantRoleFactory(
            parent_role=self.parent_role, resonance=self.resonance, unlock_thread_level=3
        )
        self.subject_sheet = CharacterSheetFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.subject_sheet,
            covenant=self.covenant,
            covenant_role=self.parent_role,
            engaged=True,
            is_secondary=True,
        )

    def _qualify_subrole(self) -> None:
        character = self.subject_sheet.character
        Thread.objects.create(
            owner=self.subject_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.parent_role,
            level=3,
        )
        character.threads.invalidate()

    def test_secondary_yields_no_subrole_perk_even_when_thread_qualifies(self) -> None:
        anchor_perk = VowSituationalPerkFactory(
            covenant_role=self.parent_role,
            name="Secondary Anchor Perk",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        VowSituationalPerkFactory(
            covenant_role=self.sub_role,
            name="Secondary Subrole Perk (must not fire)",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        self._qualify_subrole()

        fired = applicable_perks(
            self.subject_sheet,
            effect_kind=PerkEffectKind.POWER_BONUS,
            resolution=None,
            target=None,
        )
        self.assertEqual([f.perk for f in fired], [anchor_perk])
        self.assertEqual(
            fired,
            [
                FiredPerk(
                    perk=anchor_perk,
                    holder=self.subject_sheet,
                    magnitude_tenths=anchor_perk.magnitude_tenths,
                    rung_number=None,
                    is_secondary=True,
                )
            ],
        )
