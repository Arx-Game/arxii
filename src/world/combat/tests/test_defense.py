"""Tests for defensive check integration in combat."""

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import BOTCH_SUCCESS_LEVEL_MAX
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    DEFENSE_CRITICAL_MULTIPLIER,
    DEFENSE_FULL_MULTIPLIER,
    DEFENSE_REDUCED_MULTIPLIER,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction
from world.combat.services import (
    _damage_multiplier_for_success,
    resolve_npc_attack,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.magic.types.aura import AffinityType
from world.scenes.constants import RoundStatus
from world.traits.factories import (
    CheckOutcomeFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart
from world.vitals.models import CharacterVitals


class DamageMultiplierTests(TestCase):
    """Tests for _damage_multiplier_for_success."""

    def test_great_success_no_damage(self) -> None:
        self.assertEqual(_damage_multiplier_for_success(2), 0.0)
        self.assertEqual(_damage_multiplier_for_success(3), 0.0)

    def test_partial_success_reduced(self) -> None:
        self.assertEqual(
            _damage_multiplier_for_success(1),
            DEFENSE_REDUCED_MULTIPLIER,
        )

    def test_failure_full_damage(self) -> None:
        self.assertEqual(
            _damage_multiplier_for_success(0),
            DEFENSE_FULL_MULTIPLIER,
        )

    def test_critical_failure_extra(self) -> None:
        self.assertEqual(
            _damage_multiplier_for_success(-1),
            DEFENSE_CRITICAL_MULTIPLIER,
        )
        self.assertEqual(
            _damage_multiplier_for_success(-3),
            DEFENSE_CRITICAL_MULTIPLIER,
        )


class ResolveNpcAttackTests(TestCase):
    """Tests for resolve_npc_attack with mocked perform_check.

    Uses setUp (not setUpTestData) because CombatOpponentFactory creates a CombatNPC
    ObjectDB at the encounter's room, and Evennia's SharedMemoryModel identity map means
    that room Python object accumulates contents across tests. This makes the room
    non-deepcopyable (DbHolder), breaking setUpTestData's per-test deepcopy.
    """

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(pool=pool, base_damage=100)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            threat_pool=pool,
        )
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=200, max_health=200)
        self.npc_action = CombatOpponentAction.objects.create(
            opponent=self.opponent,
            round_number=1,
            threat_entry=self.entry,
        )
        self.npc_action.targets.add(self.participant)
        self.mock_check_type = MagicMock()

    def _make_mock_check(self, success_level: int) -> MagicMock:
        mock_fn = MagicMock()
        mock_result = MagicMock()
        mock_result.success_level = success_level
        mock_fn.return_value = mock_result
        return mock_fn

    def test_great_success_no_damage(self) -> None:
        mock_fn = self._make_mock_check(success_level=2)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        self.assertEqual(result.final_damage, 0)
        self.assertEqual(result.damage_multiplier, 0.0)

    def test_partial_success_half_damage(self) -> None:
        mock_fn = self._make_mock_check(success_level=1)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        self.assertEqual(result.final_damage, 50)  # 100 * 0.5
        self.assertEqual(result.damage_multiplier, DEFENSE_REDUCED_MULTIPLIER)

    def test_failure_full_damage(self) -> None:
        mock_fn = self._make_mock_check(success_level=0)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        self.assertEqual(result.final_damage, 100)

    def test_critical_failure_extra_damage(self) -> None:
        mock_fn = self._make_mock_check(success_level=-1)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        self.assertEqual(result.final_damage, 150)  # 100 * 1.5

    def test_damage_applies_to_participant(self) -> None:
        """Health is reduced after the attack resolves."""
        mock_fn = self._make_mock_check(success_level=0)
        result = resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.mock_check_type,
            perform_check_fn=mock_fn,
        )
        vitals = CharacterVitals.objects.get(character_sheet=self.sheet)
        self.assertEqual(vitals.health, 200 - result.final_damage)


class DefensiveFashionWiringTests(TestCase):
    """resolve_npc_attack routes the defensive check through collect_check_modifiers
    so a scene-derived fashion bonus reaches the defender's roll (#750).

    The whole point: a character whose attire matches the perceiving society's
    vogue is harder to hit/kill. Defense previously rolled with zero modifiers,
    making this structurally impossible.

    Uses setUp (not setUpTestData) for the same DbHolder reason as
    ResolveNpcAttackTests, and because the area-room / fashion chain are simplest
    to build per-test.
    """

    def setUp(self) -> None:
        from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
        from evennia_extensions.models import RoomProfile
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory
        from world.checks.factories import CheckTypeFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            EquippedItemFactory,
            FashionStyleBonusFactory,
            FashionStyleFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.factories import FacetFactory
        from world.mechanics.factories import ModifierTargetFactory
        from world.realms.models import Realm
        from world.scenes.factories import SceneFactory
        from world.societies.factories import SocietyFactory

        RoomProfile.flush_instance_cache()

        # --- fashion chain: an item carrying an in-vogue facet, worn by the PC ---
        quality = QualityTierFactory(name="DefenseCommon", stat_multiplier=1.0)
        facet = FacetFactory(name="DefenseFacetIn")
        template = ItemTemplateFactory(name="DefenseTestItem")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item = ItemInstanceFactory(template=template, quality_tier=quality)
        ItemFacetFactory(item_instance=item, facet=facet, attachment_quality_tier=quality)
        character = CharacterFactory(db_key="DefenseChar")
        EquippedItemFactory(
            character=character,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.sheet = CharacterSheetFactory(character=character)

        # --- a defensive CheckType with a scoped ModifierTarget (so fashion lands) ---
        self.check_type = CheckTypeFactory(name="DefenseCheck")
        self.target = ModifierTargetFactory(name="DefenseTarget", target_check_type=self.check_type)

        # --- style puts the facet in vogue; society adopts the style ---
        style = FashionStyleFactory(name="DefenseStyle")
        style.in_vogue_facets.add(facet)
        FashionStyleBonusFactory(fashion_style=style, target=self.target, weight=1)
        realm = Realm.objects.create(name="DefenseRealm")
        self.society = SocietyFactory(
            name="DefenseSociety", realm=realm, current_fashion_style=style
        )

        # --- scene located in an area dominated by that society ---
        area = AreaFactory(
            name="Defense Ward",
            level=AreaLevel.WARD,
            realm=realm,
            dominant_society=self.society,
        )
        area_room = ObjectDBFactory(
            db_key="Defense Room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        RoomProfile.objects.update_or_create(objectdb=area_room, defaults={"area": area})
        self.scene = SceneFactory(location=area_room)

        # --- encounter wired to the scene ---
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
            scene=self.scene,
        )
        pool = ThreatPoolFactory()
        entry = ThreatPoolEntryFactory(pool=pool, base_damage=100)
        opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=pool)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=200, max_health=200)
        self.npc_action = CombatOpponentAction.objects.create(
            opponent=opponent,
            round_number=1,
            threat_entry=entry,
        )
        self.npc_action.targets.add(self.participant)

    def _spy(self) -> tuple:
        """A perform_check spy that records the extra_modifiers it was handed."""
        captured: dict = {}

        def spy(character, check_type, *args, **kwargs) -> MagicMock:
            captured["extra_modifiers"] = kwargs.get("extra_modifiers", 0)
            result = MagicMock()
            result.success_level = 0
            return result

        return spy, captured

    def test_defense_receives_scene_fashion_bonus(self) -> None:
        """The defensive roll is handed the fashion bonus derived from the scene."""
        from world.items.constants import FASHION_MATCH_BASE

        spy, captured = self._spy()
        resolve_npc_attack(
            self.npc_action,
            self.participant,
            self.check_type,
            perform_check_fn=spy,
        )
        self.assertEqual(captured["extra_modifiers"], FASHION_MATCH_BASE)


class ResolveNpcAttackSituationalPerkTests(TestCase):
    """The defense-side situation seam (#2536 slice 3, Task 6): ``resolve_npc_attack``
    threads a ``SituationContext`` (holder/subject = defender, attacker = the NPC's
    ``CombatOpponent``) into the REAL ``perform_check`` (no ``perform_check_fn``
    override), so ``BOTCH_IMMUNITY``/``TIER_FLOOR`` situational perks — including
    ``ATTACKER_ABYSSAL``-gated ones — live on the PC's defensive roll.

    Not ``setUpTestData`` — factories here create Evennia ``ObjectDB`` instances
    (``DbHolder``, not deepcopyable), same rationale as ``ResolveNpcAttackTests``
    above and ``OutcomeGuaranteeTests`` (``world/checks/tests/test_outcome_guarantees.py``),
    whose ``_chart``/force-outcome pattern this mirrors.
    """

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory(name="NPC Defense Guarantee")
        ResultChart.clear_cache()

        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        CharacterVitals.objects.create(character_sheet=self.sheet, health=200, max_health=200)

        self.pool = ThreatPoolFactory()
        self.entry = ThreatPoolEntryFactory(pool=self.pool, base_damage=100)

        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=True,
        )

    def _chart(self, *levels: int) -> tuple[ResultChart, dict[int, object]]:
        """One rank-0 chart with one outcome per success_level, roll bands stacked
        (mirrors ``OutcomeGuaranteeTests._chart``)."""
        chart = ResultChartFactory(rank_difference=0)
        outcomes = {}
        lo = 1
        for level in levels:
            outcome = CheckOutcomeFactory(name=f"L{level}", success_level=level)
            ResultChartOutcomeFactory(chart=chart, outcome=outcome, min_roll=lo, max_roll=lo + 9)
            outcomes[level] = outcome
            lo += 10
        return chart, outcomes

    def _npc_action(self, *, affinity: str = "") -> CombatOpponentAction:
        opponent = CombatOpponentFactory(
            encounter=self.encounter, threat_pool=self.pool, affinity=affinity
        )
        action = CombatOpponentAction.objects.create(
            opponent=opponent, round_number=1, threat_entry=self.entry
        )
        action.targets.add(self.participant)
        return action

    def test_botch_immunity_perk_suppresses_forced_botch_on_defense(self) -> None:
        """A BOTCH_IMMUNITY perk on the defender's engaged role means a forced
        botch on the defensive roll comes out a plain (least-bad) non-botch —
        a Stalwart Defender cannot botch a block while their perk holds.
        """
        _chart, outcomes = self._chart(-2, -1, 1)
        VowSituationalPerkFactory(
            covenant_role=self.role,
            effect_kind=PerkEffectKind.BOTCH_IMMUNITY,
            beneficiary=PerkBeneficiary.SELF,
        )
        action = self._npc_action()

        with force_check_outcome(outcomes[-2]):
            result = resolve_npc_attack(action, self.participant, self.check_type)

        self.assertGreater(result.success_level, BOTCH_SUCCESS_LEVEL_MAX)
        self.assertEqual(result.success_level, -1)

    def test_attacker_abyssal_tier_floor_binds_only_vs_authored_abyssal_opponent(self) -> None:
        """A TIER_FLOOR perk gated on ATTACKER_ABYSSAL raises the defender's forced
        failure to the floor only when the attacking opponent is authored Abyssal —
        an otherwise-identical non-Abyssal attacker leaves the outcome untouched.
        """
        _chart, outcomes = self._chart(-1, 0, 1)
        perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            effect_kind=PerkEffectKind.TIER_FLOOR,
            floor_success_level=1,
            beneficiary=PerkBeneficiary.SELF,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.ATTACKER_ABYSSAL)

        abyssal_action = self._npc_action(affinity=AffinityType.ABYSSAL)
        with force_check_outcome(outcomes[-1]):
            bound_result = resolve_npc_attack(abyssal_action, self.participant, self.check_type)
        self.assertEqual(bound_result.success_level, 1)

        non_abyssal_action = self._npc_action(affinity=AffinityType.CELESTIAL)
        with force_check_outcome(outcomes[-1]):
            unbound_result = resolve_npc_attack(
                non_abyssal_action, self.participant, self.check_type
            )
        self.assertEqual(unbound_result.success_level, -1)
