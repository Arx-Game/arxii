from django.test import TestCase

from actions.constants import ActionBackend, TargetKind
from actions.player_interface import _combat_actions
from actions.types import (
    ActionRef,
    FuryResonanceOption,
    FuryTierOption,
    PlayerAction,
    StrainAvailability,
    TargetFilters,
    TargetSpec,
    TargetType,
)


class PlayerActionDescriptorTests(TestCase):
    def _minimal_ref(self) -> ActionRef:
        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="say")

    def test_target_spec_defaults_to_none(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name="Say",
            ref=self._minimal_ref(),
        )
        self.assertIsNone(action.target_spec)

    def test_enhancements_default_to_empty_tuple(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name="Say",
            ref=self._minimal_ref(),
        )
        self.assertEqual(action.enhancements, ())

    def test_strain_defaults_to_none(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name="Say",
            ref=self._minimal_ref(),
        )
        self.assertIsNone(action.strain)

    def test_full_targeted_action_with_strain(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.CHALLENGE,
            display_name="Intimidate",
            ref=self._minimal_ref(),
            target_spec=TargetSpec(
                kind=TargetKind.PERSONA,
                cardinality=TargetType.SINGLE,
                filters=TargetFilters(in_same_scene=True, exclude_self=True),
            ),
            strain=StrainAvailability(cap=14),
        )
        self.assertEqual(action.target_spec.kind, TargetKind.PERSONA)
        self.assertEqual(action.strain.cap, 14)


def _base_player_action() -> PlayerAction:
    return PlayerAction(
        backend=ActionBackend.COMBAT,
        display_name="Cast",
        ref=ActionRef(backend=ActionBackend.COMBAT, technique_id=1),
    )


class TestPlayerActionFurySoulfrayDefaults(TestCase):
    def test_soulfray_warning_defaults_none(self) -> None:
        assert _base_player_action().soulfray_warning is None

    def test_available_fury_tiers_defaults_empty(self) -> None:
        assert _base_player_action().available_fury_tiers == ()

    def test_eligible_fury_resonances_defaults_empty(self) -> None:
        assert _base_player_action().eligible_fury_resonances == ()

    def test_fury_tier_option_is_frozen(self) -> None:
        opt = FuryTierOption(
            id=1,
            name="Unleashed",
            depth=2,
            control_surrendered=4,
            is_berserk=True,
            full_intensity=6,
        )
        assert opt.depth == 2
        try:
            opt.depth = 9  # type: ignore[misc]
        except AttributeError:
            return
        self.fail("FuryTierOption must be frozen")

    def test_resonance_option_fields(self) -> None:
        opt = FuryResonanceOption(id=7, name="Rage", provocation_cap=3)
        assert opt.provocation_cap == 3


class TestPlayerActionSerializerFurySoulfray(TestCase):
    def test_serializer_round_trips_fury_and_soulfray(self) -> None:
        from actions.serializers import PlayerActionSerializer

        pa = PlayerAction(
            backend=ActionBackend.COMBAT,
            display_name="Cast",
            ref=ActionRef(backend=ActionBackend.COMBAT, technique_id=1),
            available_fury_tiers=(
                FuryTierOption(
                    id=1,
                    name="Unleashed",
                    depth=2,
                    control_surrendered=4,
                    is_berserk=True,
                    full_intensity=6,
                ),
            ),
            eligible_fury_resonances=(FuryResonanceOption(id=7, name="Rage", provocation_cap=3),),
        )
        data = PlayerActionSerializer(pa).data
        assert data["available_fury_tiers"][0]["depth"] == 2
        assert data["available_fury_tiers"][0]["control_surrendered"] == 4
        assert data["available_fury_tiers"][0]["is_berserk"] is True
        assert data["available_fury_tiers"][0]["full_intensity"] == 6
        assert data["eligible_fury_resonances"][0]["provocation_cap"] == 3
        assert data["soulfray_warning"] is None


class TestCombatActionsDescriptorEnrichment(TestCase):
    """_combat_actions populates soulfray_warning + fury fields (#1543)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from actions.factories import ActionTemplateFactory
        from world.checks.factories import CheckTypeFactory
        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            CharacterTechniqueFactory,
            FuryConfigFactory,
            FuryTierFactory,
            KindledStrengthTierFactory,
            ResonanceFactory,
            TechniqueFactory,
            kindle_resonance,
        )
        from world.scenes.constants import RoundStatus

        # Active DECLARING encounter with an ACTIVE participant.
        cls.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        cls.sheet = cls.participant.character_sheet
        cls.character = cls.sheet.character

        # Known technique with an action_template (combat-usable).
        cls.check_type = CheckTypeFactory()
        cls.template = ActionTemplateFactory(check_type=cls.check_type)
        cls.technique = TechniqueFactory(
            damage_profile=False,
            action_template=cls.template,
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        # Fury tiers to surface on the descriptor.
        FuryConfigFactory()
        cls.tier_smoulder = FuryTierFactory(
            name="Smouldering",
            depth=1,
        )
        cls.tier_inferno = FuryTierFactory(
            name="Inferno",
            depth=3,
        )

        # A kindled resonance whose strength reaches the shallowest tier, and a held one
        # that is not kindled (never offered).
        cls.resonance = ResonanceFactory()
        cls.strength = KindledStrengthTierFactory(rank=3, name="Blazing", give_in_max_depth=1)
        kindle_resonance(cls.sheet, cls.resonance, cls.strength)
        cls.unkindled = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=cls.sheet, resonance=cls.unkindled)

    def test_cast_descriptor_carries_fury_tiers(self) -> None:
        actions = _combat_actions(self.character)
        cast = next(a for a in actions if a.ref.technique_id == self.technique.pk)
        self.assertEqual(len(cast.available_fury_tiers), 2)
        self.assertTrue(all(t.depth is not None for t in cast.available_fury_tiers))
        self.assertEqual(
            [t.id for t in cast.available_fury_tiers],
            [self.tier_smoulder.pk, self.tier_inferno.pk],
        )

    def test_cast_descriptor_soulfray_warning_none_without_stage(self) -> None:
        actions = _combat_actions(self.character)
        cast = next(a for a in actions if a.ref.technique_id == self.technique.pk)
        self.assertIsNone(cast.soulfray_warning)

    def test_only_a_kindled_resonance_is_offered_with_its_strength_word(self) -> None:
        actions = _combat_actions(self.character)
        cast = next(a for a in actions if a.ref.technique_id == self.technique.pk)
        self.assertEqual([r.id for r in cast.eligible_fury_resonances], [self.resonance.pk])
        self.assertTrue(all(r.provocation_cap >= 1 for r in cast.eligible_fury_resonances))
        self.assertEqual([r.strength_name for r in cast.eligible_fury_resonances], ["Blazing"])

    def test_the_weakest_strength_and_how_far_it_goes_ride_each_option(self) -> None:
        from world.magic.factories import KindledStrengthTierFactory

        KindledStrengthTierFactory(rank=1, name="Faint", give_in_max_depth=1)
        actions = _combat_actions(self.character)
        cast = next(a for a in actions if a.ref.technique_id == self.technique.pk)
        (option,) = cast.eligible_fury_resonances
        self.assertEqual(
            (option.weakest_strength_name, option.weakest_depth_name), ("Faint", "Smouldering")
        )
