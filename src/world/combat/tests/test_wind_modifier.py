"""Wind-as-mechanic (#1555): banded WIND penalty/bonus on missile check rolls.

The WIND exposure axis (world.locations.services.felt_exposure, StatKey.WIND,
#1522) feeds a banded SCENE ModifierContribution ("Wind") into combat checks —
negative on a PC's missile *offense* check (CombatTechniqueResolver._roll_check),
positive (same magnitude) on a PC's *defense* check against a MISSILE-delivered
NPC attack (resolve_npc_attack). Melee/lance attacks and flat (no defense-roll)
NPC damage never consult felt_exposure at all.

felt_exposure itself is patched at its import point (world.locations.services)
rather than built from real weather/enclosure fixtures — the combat-side seam
is a pure consumer of the return value, and the enclosure-gating/regional-
climate machinery is already covered in world.locations tests.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionCategory
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.combat.constants import StrikeDelivery
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction, CombatRoundAction
from world.combat.services import (
    CombatTechniqueResolver,
    apply_damage_to_participant,
    resolve_npc_attack,
)
from world.fatigue.constants import EffortLevel
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory
from world.vitals.models import CharacterVitals

_FELT_EXPOSURE_PATH = "world.locations.services.felt_exposure"


def _equip_weapon(character, archetype: str) -> None:
    """Equip a single weapon-archetype item on *character* — only gear_archetype and
    effective_weapon_damage (>0) matter to ``_select_equipped_weapon``; slot legality
    isn't the concern here."""
    template = ItemTemplateFactory(
        gear_archetype=archetype, base_weapon_damage=5, max_durability=30
    )
    inst = ItemInstanceFactory(template=template, durability=30)
    EquippedItemFactory(
        character=character,
        item_instance=inst,
        body_region=BodyRegion.TORSO,
        equipment_layer=EquipmentLayer.BASE,
    )
    character.equipped_items.invalidate()


class WindOffenseModifierTests(TestCase):
    """CombatTechniqueResolver._roll_check: missile attacks pick up a banded
    "Wind" SCENE contribution from the encounter room's felt WIND exposure."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=30)
        self.opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=pool)
        self.character = CharacterFactory(db_key="WindOffenseChar")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="Attack", base_power=20),
        )

    def _resolver(self) -> CombatTechniqueResolver:
        action = CombatRoundAction.objects.create(
            participant=self.participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=self.technique,
            focused_opponent_target=self.opponent,
            effort_level=EffortLevel.MEDIUM,
        )
        return CombatTechniqueResolver(
            participant=self.participant,
            action=action,
            pull_flat_bonus=0,
            fatigue_category=ActionCategory.PHYSICAL,
            offense_check_type=CheckTypeFactory(),
            offense_check_fn=None,
        )

    def _spy_extra_contributions(self):
        captured: dict = {}
        from world.checks import services as checks_services

        real_collect = checks_services.collect_check_modifiers

        def _spy(sheet, check_type, **kwargs):
            captured["extra_contributions"] = kwargs.get("extra_contributions")
            return real_collect(sheet, check_type, **kwargs)

        return _spy, captured

    def _wind_contributions(self, captured: dict) -> list:
        return [c for c in captured["extra_contributions"] if c.source_label == "Wind"]

    def test_calm_room_missile_attack_no_wind_contribution(self) -> None:
        """felt WIND below the BREEZY threshold (CALM) contributes nothing."""
        _equip_weapon(self.character, GearArchetype.RANGED)
        resolver = self._resolver()
        spy, captured = self._spy_extra_contributions()

        with (
            patch("world.combat.services.perform_check") as mock_perform,
            patch("world.combat.services.collect_check_modifiers", side_effect=spy),
            patch(_FELT_EXPOSURE_PATH, return_value=10),
        ):
            mock_perform.return_value = MagicMock(success_level=2)
            resolver._roll_check()

        self.assertEqual(self._wind_contributions(captured), [])

    def test_gale_room_missile_attack_minus_twenty(self) -> None:
        """GALE-band felt WIND applies a -20 SCENE "Wind" penalty to a RANGED attack."""
        _equip_weapon(self.character, GearArchetype.RANGED)
        resolver = self._resolver()
        spy, captured = self._spy_extra_contributions()

        with (
            patch("world.combat.services.perform_check") as mock_perform,
            patch("world.combat.services.collect_check_modifiers", side_effect=spy),
            patch(_FELT_EXPOSURE_PATH, return_value=70),
        ):
            mock_perform.return_value = MagicMock(success_level=2)
            resolver._roll_check()

        wind_contribs = self._wind_contributions(captured)
        self.assertEqual(len(wind_contribs), 1)
        self.assertEqual(wind_contribs[0].value, -20)
        self.assertEqual(wind_contribs[0].source_kind, ModifierSourceKind.SCENE)

    def test_gale_room_thrown_attack_minus_twenty(self) -> None:
        """THROWN is missile-classified too, not just RANGED."""
        _equip_weapon(self.character, GearArchetype.THROWN)
        resolver = self._resolver()
        spy, captured = self._spy_extra_contributions()

        with (
            patch("world.combat.services.perform_check") as mock_perform,
            patch("world.combat.services.collect_check_modifiers", side_effect=spy),
            patch(_FELT_EXPOSURE_PATH, return_value=70),
        ):
            mock_perform.return_value = MagicMock(success_level=2)
            resolver._roll_check()

        wind_contribs = self._wind_contributions(captured)
        self.assertEqual(len(wind_contribs), 1)
        self.assertEqual(wind_contribs[0].value, -20)

    def test_gale_room_melee_attack_untouched(self) -> None:
        """A melee attack never looks at felt WIND — the felt_exposure call is
        skipped entirely, and no Wind contribution appears even in a GALE room."""
        _equip_weapon(self.character, GearArchetype.MELEE_ONE_HAND)
        resolver = self._resolver()
        spy, captured = self._spy_extra_contributions()

        with (
            patch("world.combat.services.perform_check") as mock_perform,
            patch("world.combat.services.collect_check_modifiers", side_effect=spy),
            patch(_FELT_EXPOSURE_PATH) as mock_felt,
        ):
            mock_felt.return_value = 70
            mock_perform.return_value = MagicMock(success_level=2)
            resolver._roll_check()

        mock_felt.assert_not_called()
        self.assertEqual(self._wind_contributions(captured), [])

    def test_enclosed_room_missile_attack_no_contribution(self) -> None:
        """A sheltered room's felt WIND is 0 (enclosure gate) -> no Wind
        contribution even on a RANGED attack."""
        _equip_weapon(self.character, GearArchetype.RANGED)
        resolver = self._resolver()
        spy, captured = self._spy_extra_contributions()

        with (
            patch("world.combat.services.perform_check") as mock_perform,
            patch("world.combat.services.collect_check_modifiers", side_effect=spy),
            patch(_FELT_EXPOSURE_PATH, return_value=0),
        ):
            mock_perform.return_value = MagicMock(success_level=2)
            resolver._roll_check()

        self.assertEqual(self._wind_contributions(captured), [])


class WindDefenseModifierTests(TestCase):
    """resolve_npc_attack: symmetric positive "Wind" SCENE contribution on the
    PC's defense check when the NPC's threat entry is MISSILE-delivered.

    Uses setUp (not setUpTestData) — CombatOpponentFactory creates a CombatNPC
    ObjectDB at the encounter's room, and the SharedMemoryModel identity map makes
    that room non-deepcopyable, breaking setUpTestData's per-test deepcopy
    (mirrors world.combat.tests.test_defense.ResolveNpcAttackTests).
    """

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        self.missile_entry = ThreatPoolEntryFactory(
            pool=pool, base_damage=100, delivery=StrikeDelivery.MISSILE
        )
        self.melee_entry = ThreatPoolEntryFactory(
            pool=pool, base_damage=100, delivery=StrikeDelivery.MELEE
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=pool)
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=200, max_health=200)
        self.check_type = CheckTypeFactory()

    def _action_for(self, entry) -> CombatOpponentAction:
        action = CombatOpponentAction.objects.create(
            opponent=self.opponent, round_number=1, threat_entry=entry
        )
        action.targets.add(self.participant)
        return action

    def _spy(self):
        captured: dict = {}

        def spy(character, check_type, *args, **kwargs):
            captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            result = MagicMock()
            result.success_level = 2
            return result

        return spy, captured

    def test_gale_missile_attack_plus_twenty_defense(self) -> None:
        """GALE-band felt WIND applies a +20 SCENE "Wind" bonus to the PC's
        defense roll against a MISSILE-delivered NPC attack."""
        action = self._action_for(self.missile_entry)
        spy, captured = self._spy()

        with patch(_FELT_EXPOSURE_PATH, return_value=70):
            resolve_npc_attack(action, self.participant, self.check_type, perform_check_fn=spy)

        self.assertEqual(captured["extra_modifiers"], 20)

    def test_calm_missile_attack_no_defense_bonus(self) -> None:
        action = self._action_for(self.missile_entry)
        spy, captured = self._spy()

        with patch(_FELT_EXPOSURE_PATH, return_value=10):
            resolve_npc_attack(action, self.participant, self.check_type, perform_check_fn=spy)

        self.assertEqual(captured["extra_modifiers"], 0)

    def test_gale_melee_attack_no_defense_bonus(self) -> None:
        """MELEE delivery is untouched by wind even in a GALE room — felt_exposure
        is never consulted."""
        action = self._action_for(self.melee_entry)
        spy, captured = self._spy()

        with patch(_FELT_EXPOSURE_PATH) as mock_felt:
            mock_felt.return_value = 70
            resolve_npc_attack(action, self.participant, self.check_type, perform_check_fn=spy)

        mock_felt.assert_not_called()
        self.assertEqual(captured["extra_modifiers"], 0)

    def test_flat_damage_entry_untouched_by_wind(self) -> None:
        """A flat base_damage entry (no defense_check_type) is applied via
        apply_damage_to_participant directly — the wind seam lives only inside
        resolve_npc_attack's defense-check path, so felt_exposure is never
        consulted and the authored flat damage lands untouched (#1555)."""
        with patch(_FELT_EXPOSURE_PATH) as mock_felt:
            result = apply_damage_to_participant(
                self.participant,
                self.missile_entry.base_damage,
                damage_type=self.missile_entry.damage_type,
                delivery=self.missile_entry.delivery,
            )

        mock_felt.assert_not_called()
        self.assertEqual(result.damage_dealt, 100)
