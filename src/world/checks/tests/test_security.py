"""Tests for resolve_security_check — the security check helper (#2180)."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.checks.constants import SECURITY_CHECK_TYPE_NAMES, SecurityCheckKind
from world.checks.security_services import resolve_security_check
from world.checks.test_helpers import force_check_outcome
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.security_checks import seed_security_check_content
from world.seeds.stealth_checks import seed_stealth_check_content
from world.skills.factories import CharacterSpecializationValueFactory
from world.skills.models import Specialization
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    CheckRank,
    PointConversionRange,
    Trait,
    TraitType,
)


class ResolveSecurityCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CheckSystemSetupFactory.create()
        for trait_type in (TraitType.STAT, TraitType.SKILL):
            PointConversionRange.objects.get_or_create(
                trait_type=trait_type,
                min_value=1,
                defaults={"max_value": 100, "points_per_level": 1},
            )
        for rank_val, min_pts, name in [
            (0, 0, "S0"),
            (1, 10, "S1"),
            (2, 25, "S2"),
            (3, 50, "S3"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )
        seed_check_resolution_tables()
        seed_stealth_check_content()
        seed_security_check_content()
        cls.character = CharacterFactory()

    def setUp(self):
        Trait.flush_instance_cache()

    def test_sneak_resolves_through_stealth_check_type(self):
        """SNEAK maps to the existing 'Stealth' CheckType."""
        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success) as capture:
            result = resolve_security_check(
                SecurityCheckKind.SNEAK, self.character, target_difficulty=0
            )
        assert capture.check_type is not None
        assert capture.check_type.name == "Stealth"
        assert result.check_type.name == "Stealth"

    def test_lockpick_resolves_through_lockpick_check_type(self):
        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success) as capture:
            resolve_security_check(SecurityCheckKind.LOCKPICK, self.character, target_difficulty=0)
        assert capture.check_type is not None
        assert capture.check_type.name == "Lockpick"

    def test_break_and_enter_resolves(self):
        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success) as capture:
            resolve_security_check(
                SecurityCheckKind.BREAK_AND_ENTER, self.character, target_difficulty=0
            )
        assert capture.check_type is not None
        assert capture.check_type.name == "Break and Enter"

    def test_escape_through_window_resolves(self):
        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success) as capture:
            resolve_security_check(
                SecurityCheckKind.ESCAPE_THROUGH_WINDOW,
                self.character,
                target_difficulty=0,
            )
        assert capture.check_type is not None
        assert capture.check_type.name == "Escape Through Window"

    def test_guard_detection_resolves(self):
        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success) as capture:
            resolve_security_check(
                SecurityCheckKind.GUARD_DETECTION, self.character, target_difficulty=0
            )
        assert capture.check_type is not None
        assert capture.check_type.name == "Guard Detection"

    def test_target_difficulty_flows_through(self):
        """target_difficulty is passed to perform_check — captured by CheckCapture."""
        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success) as capture:
            resolve_security_check(
                SecurityCheckKind.LOCKPICK,
                self.character,
                target_difficulty=42,
            )
        assert capture.target_difficulty == 42

    def test_extra_modifiers_flow_through(self):
        """extra_modifiers increases total_points on the returned CheckResult."""
        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        # Give the character stats so perform_check's breakdown is non-zero.
        agility = Trait.objects.get(name="agility")
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=agility, value=30
        )
        with force_check_outcome(success):
            base = resolve_security_check(
                SecurityCheckKind.SNEAK, self.character, target_difficulty=0
            )
        with force_check_outcome(success):
            boosted = resolve_security_check(
                SecurityCheckKind.SNEAK,
                self.character,
                target_difficulty=0,
                extra_modifiers=15,
            )
        assert boosted.total_points == base.total_points + 15

    def test_unseeded_check_type_raises_value_error(self):
        """If the CheckType is missing, a clear ValueError is raised."""
        with patch(
            "world.checks.security_services.SECURITY_CHECK_TYPE_NAMES",
            {SecurityCheckKind.LOCKPICK: "NonexistentCheckType"},
        ):
            with self.assertRaises(ValueError) as ctx:
                resolve_security_check(SecurityCheckKind.LOCKPICK, self.character)
            assert "NonexistentCheckType" in str(ctx.exception)

    def test_all_kinds_have_check_type_name_mapping(self):
        """Every SecurityCheckKind has a corresponding entry in SECURITY_CHECK_TYPE_NAMES."""
        for kind in SecurityCheckKind:
            assert kind in SECURITY_CHECK_TYPE_NAMES, f"{kind} missing from name map"

    def test_owned_lockpicking_spec_contributes(self):
        """Owning the Lockpicking specialization adds to specialization_points."""
        wits = Trait.objects.get(name="wits")
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=wits, value=30
        )
        skulduggery = Trait.objects.get(name="Skulduggery")
        CharacterTraitValue.objects.create(
            character=self.character.sheet_data, trait=skulduggery, value=30
        )

        success = CheckOutcome.objects.filter(success_level__gt=0).first()
        with force_check_outcome(success):
            base = resolve_security_check(
                SecurityCheckKind.LOCKPICK, self.character, target_difficulty=0
            )

        spec = Specialization.objects.get(
            name="Lockpicking", parent_skill__trait__name="Skulduggery"
        )
        CharacterSpecializationValueFactory(
            character=self.character.sheet_data, specialization=spec, value=30
        )
        with force_check_outcome(success):
            with_spec = resolve_security_check(
                SecurityCheckKind.LOCKPICK, self.character, target_difficulty=0
            )
        assert with_spec.specialization_points > base.specialization_points
