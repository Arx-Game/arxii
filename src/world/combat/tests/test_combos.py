"""Tests for the combo system: models, detection, upgrade/revert."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    ActionCategory,
    ComboLearningMethod,
    OpponentTier,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    ComboDefinitionFactory,
    ComboLearningFactory,
    ComboSlotFactory,
)
from world.combat.models import (
    CombatOpponent,
    CombatRoundAction,
    ComboDefinition,
    ComboLearning,
    ComboSlot,
)
from world.combat.services import (
    detect_available_combos,
    revert_combo_upgrade,
    scan_round_combos,
    upgrade_action_to_combo,
)
from world.covenants.constants import RoleArchetype
from world.magic.factories import EffectTypeFactory, GiftFactory, ResonanceFactory, TechniqueFactory
from world.scenes.constants import RoundStatus


class ComboDefinitionModelTests(TestCase):
    """Tests for ComboDefinition model."""

    def test_create_with_defaults(self) -> None:
        combo = ComboDefinition.objects.create(name="Shadow Bind", slug="shadow-bind")
        self.assertTrue(combo.hidden)
        self.assertTrue(combo.discoverable_via_training)
        self.assertTrue(combo.discoverable_via_combat)
        self.assertFalse(combo.discoverable_via_research)
        self.assertTrue(combo.bypass_soak)
        self.assertEqual(combo.bonus_damage, 0)
        self.assertIsNone(combo.minimum_probing)

    def test_str(self) -> None:
        combo = ComboDefinition.objects.create(name="Fire Storm", slug="fire-storm")
        self.assertEqual(str(combo), "Fire Storm")

    def test_unique_slug(self) -> None:
        ComboDefinition.objects.create(name="A", slug="unique-slug")
        with self.assertRaises(IntegrityError):
            ComboDefinition.objects.create(name="B", slug="unique-slug")

    def test_clean_rejects_one_slot_combo(self) -> None:
        """A combo with fewer than 2 slots fails validation (invariant: combos are never solo)."""
        from world.magic.factories import EffectTypeFactory

        combo = ComboDefinitionFactory()
        ComboSlotFactory(combo=combo, slot_number=1, required_action_type=EffectTypeFactory())
        with self.assertRaises(ValidationError):
            combo.clean()

    def test_clean_rejects_zero_slot_combo(self) -> None:
        """A combo with no slots fails validation once it has a pk."""
        combo = ComboDefinitionFactory()
        with self.assertRaises(ValidationError):
            combo.clean()

    def test_clean_accepts_two_slot_combo(self) -> None:
        """A combo with 2+ slots passes validation."""
        from world.magic.factories import EffectTypeFactory

        combo = ComboDefinitionFactory()
        ComboSlotFactory(combo=combo, slot_number=1, required_action_type=EffectTypeFactory())
        ComboSlotFactory(combo=combo, slot_number=2, required_action_type=EffectTypeFactory())
        combo.clean()  # should not raise


class ComboSlotModelTests(TestCase):
    """Tests for ComboSlot model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.combo = ComboDefinitionFactory()
        cls.effect_type = EffectTypeFactory(name="Attack")

    def test_create(self) -> None:
        slot = ComboSlot.objects.create(
            combo=self.combo,
            slot_number=1,
            required_action_type=self.effect_type,
        )
        self.assertEqual(slot.combo, self.combo)
        self.assertIsNone(slot.resonance_requirement_id)

    def test_str(self) -> None:
        slot = ComboSlot.objects.create(
            combo=self.combo,
            slot_number=2,
            required_action_type=self.effect_type,
        )
        self.assertIn("Slot 2", str(slot))

    def test_unique_slot_per_combo(self) -> None:
        ComboSlot.objects.create(
            combo=self.combo,
            slot_number=1,
            required_action_type=self.effect_type,
        )
        with self.assertRaises(IntegrityError):
            ComboSlot.objects.create(
                combo=self.combo,
                slot_number=1,
                required_action_type=self.effect_type,
            )


class ComboLearningModelTests(TestCase):
    """Tests for ComboLearning model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.combo = ComboDefinitionFactory()
        cls.sheet = CharacterSheetFactory()

    def test_create(self) -> None:
        learning = ComboLearning.objects.create(
            combo=self.combo,
            character_sheet=self.sheet,
            learned_via=ComboLearningMethod.COMBAT,
        )
        self.assertIn("knows", str(learning))

    def test_unique_per_character(self) -> None:
        ComboLearning.objects.create(
            combo=self.combo,
            character_sheet=self.sheet,
            learned_via=ComboLearningMethod.TRAINING,
        )
        with self.assertRaises(IntegrityError):
            ComboLearning.objects.create(
                combo=self.combo,
                character_sheet=self.sheet,
                learned_via=ComboLearningMethod.COMBAT,
            )


class DetectAvailableCombosTests(TestCase):
    """Tests for detect_available_combos service."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack", base_power=20)
        cls.effect_defense = EffectTypeFactory(name="Defense", base_power=10)
        cls.gift = GiftFactory()

    def _setup_encounter_with_actions(self, *, num_pcs: int = 2):
        """Create an encounter with PCs who have declared actions."""
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        participants = []
        actions = []
        for i in range(num_pcs):
            sheet = CharacterSheetFactory()
            p = CombatParticipantFactory(
                encounter=encounter,
                character_sheet=sheet,
            )
            participants.append(p)

            effect = self.effect_attack if i % 2 == 0 else self.effect_defense
            technique = TechniqueFactory(
                gift=self.gift,
                effect_type=effect,
            )
            action = CombatRoundAction.objects.create(
                participant=p,
                round_number=1,
                focused_category=ActionCategory.PHYSICAL,
                focused_action=technique,
            )
            actions.append(action)

        return encounter, participants, actions

    def test_full_match_known_combo(self) -> None:
        """A combo where all slots match and at least one PC knows it."""
        encounter, participants, _actions = self._setup_encounter_with_actions(num_pcs=2)

        combo = ComboDefinitionFactory(discoverable_via_combat=False)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_defense,
        )
        # First PC knows the combo
        ComboLearningFactory(combo=combo, character_sheet=participants[0].character_sheet)

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].combo, combo)
        self.assertTrue(available[0].known_by_participant)
        self.assertEqual(len(available[0].slot_matches), 2)

    def test_discoverable_via_combat_unknown(self) -> None:
        """Combo is available if discoverable_via_combat even if no PC knows it."""
        encounter, _participants, _actions = self._setup_encounter_with_actions(num_pcs=2)

        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_defense,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 1)
        self.assertFalse(available[0].known_by_participant)

    def test_unknown_and_not_discoverable(self) -> None:
        """Combo is NOT available if unknown and not discoverable_via_combat."""
        encounter, _participants, _actions = self._setup_encounter_with_actions(num_pcs=2)

        combo = ComboDefinitionFactory(discoverable_via_combat=False)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_defense,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    def test_not_enough_pcs(self) -> None:
        """Combo with 2 slots is not available with only 1 matching PC."""
        encounter, _participants, _actions = self._setup_encounter_with_actions(num_pcs=1)

        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_defense,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    def test_single_slot_combo_never_detected(self) -> None:
        """A legacy 1-slot combo is inert at runtime even if it exists in the DB (#2051)."""
        encounter, _participants, _actions = self._setup_encounter_with_actions(num_pcs=1)

        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    def test_action_type_mismatch(self) -> None:
        """Combo where no action matches one of the slots."""
        encounter, _participants, _actions = self._setup_encounter_with_actions(num_pcs=2)

        movement_type = EffectTypeFactory(name="Movement")
        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=movement_type,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    def test_minimum_probing_not_met(self) -> None:
        """Combo with minimum_probing is unavailable when probing is too low."""
        encounter, _participants, _actions = self._setup_encounter_with_actions(num_pcs=2)

        # Add an opponent with low probing
        from world.combat.factories import ThreatPoolFactory

        pool = ThreatPoolFactory()
        CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            name="Boss",
            health=500,
            max_health=500,
            probing_current=5,
            threat_pool=pool,
        )

        combo = ComboDefinitionFactory(
            discoverable_via_combat=True,
            minimum_probing=50,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_defense,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    def test_minimum_probing_met(self) -> None:
        """Combo with minimum_probing is available when probing is sufficient."""
        encounter, _participants, _actions = self._setup_encounter_with_actions(num_pcs=2)

        from world.combat.factories import ThreatPoolFactory

        pool = ThreatPoolFactory()
        CombatOpponent.objects.create(
            encounter=encounter,
            tier=OpponentTier.BOSS,
            name="Boss",
            health=500,
            max_health=500,
            probing_current=60,
            threat_pool=pool,
        )

        combo = ComboDefinitionFactory(
            discoverable_via_combat=True,
            minimum_probing=50,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_defense,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 1)

    def test_no_actions_returns_empty(self) -> None:
        """No round actions means no combos."""
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)


class UpgradeRevertComboTests(TestCase):
    """Tests for upgrade_action_to_combo and revert_combo_upgrade."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        cls.sheet = CharacterSheetFactory()
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
        )
        cls.technique = TechniqueFactory()
        cls.combo = ComboDefinitionFactory()

    def test_upgrade_sets_combo(self) -> None:
        action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=self.technique,
        )
        self.assertIsNone(action.combo_upgrade_id)
        upgrade_action_to_combo(action, self.combo)
        action.refresh_from_db()
        self.assertEqual(action.combo_upgrade, self.combo)

    def test_revert_clears_combo(self) -> None:
        action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=self.technique,
            combo_upgrade=self.combo,
        )
        revert_combo_upgrade(action)
        action.refresh_from_db()
        self.assertIsNone(action.combo_upgrade_id)


class ComboFactoryTests(TestCase):
    """Smoke tests for combo factories."""

    def test_combo_definition_factory(self) -> None:
        combo = ComboDefinitionFactory()
        self.assertIsNotNone(combo.pk)
        self.assertTrue(combo.slug)

    def test_combo_slot_factory(self) -> None:
        slot = ComboSlotFactory()
        self.assertIsNotNone(slot.combo)
        self.assertIsNotNone(slot.required_action_type)

    def test_combo_learning_factory(self) -> None:
        learning = ComboLearningFactory()
        self.assertIsNotNone(learning.combo)
        self.assertIsNotNone(learning.character_sheet)
        self.assertEqual(learning.learned_via, ComboLearningMethod.TRAINING)


class ResonanceMatchingTests(TestCase):
    """Tests for combo slot resonance requirement matching."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="ResonanceAttack", base_power=20)
        cls.fire_resonance = ResonanceFactory(name="Fire")
        cls.water_resonance = ResonanceFactory(name="Water")

    def _create_encounter_with_resonance_action(
        self,
        *,
        gift_resonance: object,
    ) -> tuple[object, list[object]]:
        """Create an encounter with two PCs; the first PC's gift has the given resonance.

        Two PCs are used because combos require >=2 slots (#2051 invariant).
        The second PC uses a plain attack-type action with no resonance slot.
        """
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        gift = GiftFactory(name=f"Gift-{gift_resonance}")
        gift.resonances.add(gift_resonance)
        technique = TechniqueFactory(
            gift=gift,
            effect_type=self.effect_attack,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
        )
        # Second PC with a plain attack action (no resonance requirement)
        sheet2 = CharacterSheetFactory()
        participant2 = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet2,
        )
        technique2 = TechniqueFactory(
            gift=GiftFactory(name=f"Gift-plain-{gift_resonance}"),
            effect_type=self.effect_attack,
        )
        action2 = CombatRoundAction.objects.create(
            participant=participant2,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique2,
        )
        return encounter, [action, action2]

    def test_combo_with_resonance_requirement_matches(self) -> None:
        """Slot with resonance requirement matches when gift has that resonance."""
        encounter, _actions = self._create_encounter_with_resonance_action(
            gift_resonance=self.fire_resonance,
        )
        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
            resonance_requirement=self.fire_resonance,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_attack,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].combo, combo)

    def test_combo_with_resonance_requirement_no_match(self) -> None:
        """Slot with resonance requirement does NOT match when gift has wrong resonance."""
        encounter, _actions = self._create_encounter_with_resonance_action(
            gift_resonance=self.water_resonance,
        )
        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
            resonance_requirement=self.fire_resonance,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_attack,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 0)

    def test_combo_slot_matching_uses_backtracking(self) -> None:
        """Backtracking finds valid assignment when greedy would fail.

        Slot 1: Attack (any resonance)
        Slot 2: Attack (Fire resonance required)
        Actions: [PC-A: Attack+Fire, PC-B: Attack+Water]
        Greedy assigns PC-A to Slot 1 (any matches), then Slot 2 needs Fire
        but only PC-B (Water) remains. Backtracking assigns PC-B->Slot1,
        PC-A->Slot2.
        """
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )

        # PC-A has a Fire gift
        fire_gift = GiftFactory(name="FireGift-BT")
        fire_gift.resonances.add(self.fire_resonance)
        fire_technique = TechniqueFactory(
            gift=fire_gift,
            effect_type=self.effect_attack,
        )
        sheet_a = CharacterSheetFactory()
        participant_a = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet_a,
        )
        CombatRoundAction.objects.create(
            participant=participant_a,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=fire_technique,
        )

        # PC-B has a Water gift
        water_gift = GiftFactory(name="WaterGift-BT")
        water_gift.resonances.add(self.water_resonance)
        water_technique = TechniqueFactory(
            gift=water_gift,
            effect_type=self.effect_attack,
        )
        sheet_b = CharacterSheetFactory()
        participant_b = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet_b,
        )
        CombatRoundAction.objects.create(
            participant=participant_b,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=water_technique,
        )

        # Combo: Slot 1 = Attack (any), Slot 2 = Attack (Fire required)
        combo = ComboDefinitionFactory(discoverable_via_combat=True)
        ComboSlotFactory(
            combo=combo,
            slot_number=1,
            required_action_type=self.effect_attack,
            resonance_requirement=None,
        )
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_attack,
            resonance_requirement=self.fire_resonance,
        )

        available = detect_available_combos(encounter, 1)
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].combo, combo)


class ComboSlotRequirementLabelTests(TestCase):
    """``ComboSlot.requirement_label`` names what a slot asks for (#3553)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack-Label")
        cls.fire = ResonanceFactory(name="Fire-Label")

    def test_effect_type_only(self) -> None:
        slot = ComboSlotFactory(required_action_type=self.effect_attack)
        self.assertEqual(slot.requirement_label, "Attack-Label")

    def test_resonance_and_archetype(self) -> None:
        slot = ComboSlotFactory(
            required_action_type=self.effect_attack,
            resonance_requirement=self.fire,
            required_archetype=RoleArchetype.SHIELD,
        )
        self.assertEqual(slot.requirement_label, "Attack-Label (Fire-Label, Shield role)")


class ScanRoundCombosTests(TestCase):
    """``scan_round_combos`` lists every slot, filled or open (#3553)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect_attack = EffectTypeFactory(name="Attack-Scan", base_power=20)
        cls.effect_defense = EffectTypeFactory(name="Defense-Scan", base_power=10)
        cls.fire = ResonanceFactory(name="Fire-Scan")
        cls.water = ResonanceFactory(name="Water-Scan")
        cls.gift = GiftFactory()
        cls.fire_gift = GiftFactory(name="FireGift-Scan")
        cls.fire_gift.resonances.add(cls.fire)
        cls.water_gift = GiftFactory(name="WaterGift-Scan")
        cls.water_gift.resonances.add(cls.water)
        cls.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        cls.attacker = CombatParticipantFactory(encounter=cls.encounter)
        cls.defender = CombatParticipantFactory(encounter=cls.encounter)
        cls.attack_technique = TechniqueFactory(
            gift=cls.gift, effect_type=cls.effect_attack, name="Firebolt-Scan"
        )
        cls.defense_technique = TechniqueFactory(gift=cls.gift, effect_type=cls.effect_defense)
        cls.combo = ComboDefinitionFactory(
            discoverable_via_combat=False, bonus_damage=7, bypass_soak=False
        )
        ComboSlotFactory(combo=cls.combo, slot_number=1, required_action_type=cls.effect_attack)
        ComboSlotFactory(combo=cls.combo, slot_number=2, required_action_type=cls.effect_defense)

    def _declare(self, participant, technique) -> CombatRoundAction:
        return CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
        )

    def test_known_partial_combo_lists_the_open_slot(self) -> None:
        """A knower who has not declared yet still makes the combo visible."""
        ComboLearningFactory(combo=self.combo, character_sheet=self.defender.character_sheet)
        action = self._declare(self.attacker, self.attack_technique)

        [round_combo] = scan_round_combos(self.encounter, 1)
        self.assertEqual(round_combo.combo, self.combo)
        self.assertTrue(round_combo.known_by_participant)
        self.assertFalse(round_combo.complete)
        first, second = round_combo.slot_fills
        self.assertEqual(first.slot.slot_number, 1)
        self.assertIsNotNone(first.match)
        self.assertEqual(first.match.participant, self.attacker)
        self.assertEqual(first.match.action, action)
        self.assertEqual(second.slot.slot_number, 2)
        self.assertIsNone(second.match)
        self.assertEqual([slot.slot_number for slot in round_combo.open_slots], [2])
        self.assertEqual(round_combo.filled_count, 1)
        # A partial combo is never "available" to upgrade into.
        self.assertEqual(detect_available_combos(self.encounter, 1), [])

    def test_unknown_partial_combo_stays_hidden(self) -> None:
        """Nobody in the encounter knows it: no hint leaks the hidden combo."""
        self._declare(self.attacker, self.attack_technique)
        self.assertEqual(scan_round_combos(self.encounter, 1), [])

    def test_complete_combo_fills_every_slot(self) -> None:
        ComboLearningFactory(combo=self.combo, character_sheet=self.attacker.character_sheet)
        self._declare(self.attacker, self.attack_technique)
        self._declare(self.defender, self.defense_technique)

        [round_combo] = scan_round_combos(self.encounter, 1)
        self.assertTrue(round_combo.complete)
        self.assertEqual(round_combo.open_slots, [])
        self.assertEqual(round_combo.filled_count, 2)
        [available] = detect_available_combos(self.encounter, 1)
        self.assertEqual(available.combo, self.combo)
        self.assertEqual([m.slot_number for m in available.slot_matches], [1, 2])

    def test_partial_fill_keeps_the_most_slots_filled(self) -> None:
        """Slots [Attack, Attack+Fire, Defense] with Fire and Water attacks declared.

        Greedy assignment would put the Fire attack in slot 1 and leave slot 2
        unfillable; the scan finds the two-slot fill (Water -> 1, Fire -> 2).
        """
        combo = ComboDefinitionFactory(discoverable_via_combat=False)
        ComboSlotFactory(combo=combo, slot_number=1, required_action_type=self.effect_attack)
        ComboSlotFactory(
            combo=combo,
            slot_number=2,
            required_action_type=self.effect_attack,
            resonance_requirement=self.fire,
        )
        ComboSlotFactory(combo=combo, slot_number=3, required_action_type=self.effect_defense)
        ComboLearningFactory(combo=combo, character_sheet=self.attacker.character_sheet)
        fire_action = self._declare(
            self.attacker, TechniqueFactory(gift=self.fire_gift, effect_type=self.effect_attack)
        )
        water_action = self._declare(
            self.defender, TechniqueFactory(gift=self.water_gift, effect_type=self.effect_attack)
        )

        round_combos = {rc.combo.pk: rc for rc in scan_round_combos(self.encounter, 1)}
        round_combo = round_combos[combo.pk]
        self.assertEqual(round_combo.filled_count, 2)
        first, second, third = round_combo.slot_fills
        self.assertEqual(first.match.action, water_action)
        self.assertEqual(second.match.action, fire_action)
        self.assertIsNone(third.match)
