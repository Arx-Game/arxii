"""Tests for AoE (multi-target) combat technique targeting (#1321 Task 8).

TDD step 1 — these tests should FAIL before the implementation is in place and
PASS once it is.  All damage-path tests run on the SQLite fast tier; condition-apply
tests that hit DISTINCT-ON are tagged @tag("postgres").
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import tag

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import ActionCategory, OpponentStatus, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction, CombatRoundActionTarget
from world.combat.services import CombatTechniqueResolver
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    EffectTypeFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.types.power_ledger import PowerLedger


def _ledger(power: int = 10) -> PowerLedger:
    return PowerLedger(entries=(), total=power)


def _area_technique(base_power: int = 20) -> object:
    """Hostile AREA technique with one damage profile."""
    from actions.constants import ActionTargetType

    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="AoEAttack", base_power=base_power),
        target_type=ActionTargetType.AREA,
        damage_profile=False,
    )
    TechniqueDamageProfileFactory(technique=technique, base_damage=10)
    return technique


def _single_technique(base_power: int = 20) -> object:
    """Hostile SINGLE technique with one damage profile."""
    from actions.constants import ActionTargetType

    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="SingleAttack", base_power=base_power),
        target_type=ActionTargetType.SINGLE,
        damage_profile=False,
    )
    TechniqueDamageProfileFactory(technique=technique, base_damage=10)
    return technique


def _build_encounter_with_two_opponents(technique):
    """Build an encounter with two MOOK opponents and one participant."""
    encounter = CombatEncounterFactory(round_number=1)
    pool = ThreatPoolFactory()
    ThreatPoolEntryFactory(pool=pool, base_damage=10)
    opponent_a = CombatOpponentFactory(
        encounter=encounter,
        tier=OpponentTier.MOOK,
        health=50,
        max_health=50,
        soak_value=0,
        threat_pool=pool,
    )
    opponent_b = CombatOpponentFactory(
        encounter=encounter,
        tier=OpponentTier.MOOK,
        health=50,
        max_health=50,
        soak_value=0,
        threat_pool=pool,
    )
    sheet = CharacterSheetFactory()
    participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
    action = CombatRoundAction.objects.create(
        participant=participant,
        round_number=1,
        focused_category=ActionCategory.PHYSICAL,
        focused_action=technique,
        focused_opponent_target=opponent_a,  # primary
        effort_level=EffortLevel.MEDIUM,
    )
    # Store the extra target in the join table
    CombatRoundActionTarget.objects.create(action=action, opponent=opponent_a)
    CombatRoundActionTarget.objects.create(action=action, opponent=opponent_b)
    return encounter, participant, action, opponent_a, opponent_b


def _resolver(participant, action, *, offense_check_type=None):
    return CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=0,
        fatigue_category=ActionCategory.PHYSICAL,
        offense_check_type=offense_check_type or CheckTypeFactory(),
        offense_check_fn=None,
    )


class AoEDamageExpansionTests(TestCase):
    """AREA technique damages ALL opponents via per-target _profile_damage."""

    def setUp(self) -> None:
        # Ensure a success-level multiplier so damage is > 0
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("1.0"))

    def test_area_technique_hits_both_opponents(self) -> None:
        """An AREA technique with SL=1 must produce damage results for BOTH opponents."""
        technique = _area_technique()
        _enc, participant, action, opponent_a, opponent_b = _build_encounter_with_two_opponents(
            technique
        )

        resolver = _resolver(participant, action)

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            result = resolver(power=20, ledger=_ledger(20))

        # Should have results for both opponents
        hit_targets = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_a.pk, hit_targets)
        self.assertIn(opponent_b.pk, hit_targets)

    def test_single_technique_hits_only_primary_opponent(self) -> None:
        """A SINGLE technique must NOT expand to the extra join-table target."""
        technique = _single_technique()
        _enc, participant, action, opponent_a, opponent_b = _build_encounter_with_two_opponents(
            technique
        )

        resolver = _resolver(participant, action)

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            result = resolver(power=20, ledger=_ledger(20))

        hit_targets = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_a.pk, hit_targets)
        self.assertNotIn(opponent_b.pk, hit_targets)

    def test_area_technique_skips_defeated_opponents(self) -> None:
        """An AREA technique skips opponents that are already DEFEATED."""
        technique = _area_technique()
        _enc, participant, action, opponent_a, opponent_b = _build_encounter_with_two_opponents(
            technique
        )
        # Mark opponent_b as DEFEATED before resolution
        opponent_b.status = OpponentStatus.DEFEATED
        opponent_b.save(update_fields=["status"])

        resolver = _resolver(participant, action)

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            result = resolver(power=20, ledger=_ledger(20))

        hit_targets = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_a.pk, hit_targets)
        self.assertNotIn(opponent_b.pk, hit_targets)

    def test_area_technique_no_join_rows_hits_all_active_opponents(self) -> None:
        """AREA technique with NO join-table rows auto-expands to all active opponents.

        This is the regression test for the bug where an AREA cast with no stored
        CombatRoundActionTarget rows silently fell back to single-target behavior.
        After the fix, AREA always enumerates all non-DEFEATED encounter opponents
        directly from the encounter — the client does not need to enumerate them.
        """
        technique = _area_technique()
        encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        opponent_a = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
            threat_pool=pool,
        )
        opponent_b = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent_a,
            effort_level=EffortLevel.MEDIUM,
            # Intentionally NO CombatRoundActionTarget join rows written
        )

        resolver = _resolver(participant, action)

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            result = resolver(power=20, ledger=_ledger(20))

        hit_targets = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_a.pk, hit_targets, "AREA must hit opponent_a without join rows")
        self.assertIn(opponent_b.pk, hit_targets, "AREA must hit opponent_b without join rows")

    def test_area_no_join_rows_skips_defeated_opponent(self) -> None:
        """AREA technique without join rows skips DEFEATED opponents.

        The encounter-level query pre-filters to exclude DEFEATED status, so a
        defeated opponent is never passed to the damage pipeline even when no
        CombatRoundActionTarget rows exist.
        """
        technique = _area_technique()
        encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=10)
        opponent_a = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
            threat_pool=pool,
        )
        opponent_b = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            soak_value=0,
            threat_pool=pool,
        )
        # Mark opponent_b as DEFEATED — should be excluded by the encounter query
        opponent_b.status = OpponentStatus.DEFEATED
        opponent_b.save(update_fields=["status"])

        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opponent_a,
            effort_level=EffortLevel.MEDIUM,
        )

        resolver = _resolver(participant, action)

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            result = resolver(power=20, ledger=_ledger(20))

        hit_targets = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_a.pk, hit_targets)
        self.assertNotIn(opponent_b.pk, hit_targets, "DEFEATED opponent must not be hit by AREA")

    def test_filtered_group_hits_stored_subset(self) -> None:
        """A FILTERED_GROUP technique hits only the opponents in the join table."""
        from actions.constants import ActionTargetType

        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="FilteredAttack", base_power=20),
            target_type=ActionTargetType.FILTERED_GROUP,
            damage_profile=False,
        )
        TechniqueDamageProfileFactory(technique=technique, base_damage=10)

        _enc, participant, action, opponent_a, opponent_b = _build_encounter_with_two_opponents(
            technique
        )

        resolver = _resolver(participant, action)

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            result = resolver(power=20, ledger=_ledger(20))

        hit_targets = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_a.pk, hit_targets)
        self.assertIn(opponent_b.pk, hit_targets)


class AoETargetPrerequisitesTests(TestCase):
    """AREA/FILTERED_GROUP techniques silently filter targets by target_prerequisites (#1793).

    _resolved_opponent_targets' AREA/FILTERED_GROUP branches enumerate opponents
    independently of _build_affected_targets/_check_combat_target_prerequisites
    (the pre-flight hard-block only ever sees the single focused opponent/ally),
    so damage/condition application must apply the SAME silent filter the
    non-combat resolve_targets applies for AoE — not a raise.
    """

    def setUp(self) -> None:
        # Ensure a success-level multiplier so damage is > 0
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=Decimal("1.0"))

    def _aerial_prerequisite(self):
        from world.mechanics.constants import PropertyHolder
        from world.mechanics.factories import AerialPropertyFactory, PrerequisiteFactory

        return PrerequisiteFactory(
            property=AerialPropertyFactory(),
            property_holder=PropertyHolder.TARGET,
            minimum_value=1,
        )

    def test_area_technique_silently_filters_non_matching_opponent(self) -> None:
        """AREA technique: only the opponent meeting target_prerequisites is hit."""
        from world.mechanics.factories import ObjectPropertyFactory

        technique = _area_technique()
        prereq = self._aerial_prerequisite()
        technique.target_prerequisites.add(prereq)
        _enc, participant, action, opponent_a, opponent_b = _build_encounter_with_two_opponents(
            technique
        )
        ObjectPropertyFactory(object=opponent_a.objectdb, property=prereq.property)

        resolver = _resolver(participant, action)

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            result = resolver(power=20, ledger=_ledger(20))

        hit_targets = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_a.pk, hit_targets)
        self.assertNotIn(opponent_b.pk, hit_targets)

    def test_filtered_group_technique_silently_filters_non_matching_opponent(self) -> None:
        """FILTERED_GROUP technique: join-table opponents are still filtered."""
        from actions.constants import ActionTargetType
        from world.mechanics.factories import ObjectPropertyFactory

        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="FilteredPrereqAttack", base_power=20),
            target_type=ActionTargetType.FILTERED_GROUP,
            damage_profile=False,
        )
        TechniqueDamageProfileFactory(technique=technique, base_damage=10)
        prereq = self._aerial_prerequisite()
        technique.target_prerequisites.add(prereq)

        _enc, participant, action, opponent_a, opponent_b = _build_encounter_with_two_opponents(
            technique
        )
        ObjectPropertyFactory(object=opponent_a.objectdb, property=prereq.property)

        resolver = _resolver(participant, action)

        with patch("world.combat.services.perform_check") as mock_check:
            mock_check.return_value = type(
                "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
            )()
            result = resolver(power=20, ledger=_ledger(20))

        hit_targets = {r.opponent_id for r in result.damage_results}
        self.assertIn(opponent_a.pk, hit_targets)
        self.assertNotIn(opponent_b.pk, hit_targets)


class CombatRoundActionTargetModelTests(TestCase):
    """Unit tests for the CombatRoundActionTarget join table."""

    def test_create_join_row(self) -> None:
        """Can create CombatRoundActionTarget rows and query them back."""
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_opponent_target=opponent,
            effort_level=EffortLevel.MEDIUM,
        )
        target_row = CombatRoundActionTarget.objects.create(
            action=action,
            opponent=opponent,
        )
        self.assertEqual(target_row.action, action)
        self.assertEqual(target_row.opponent, opponent)

    def test_cascade_delete_on_action(self) -> None:
        """Deleting a CombatRoundAction cascades to its CombatRoundActionTarget rows."""
        encounter = CombatEncounterFactory()
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        opponent = CombatOpponentFactory(encounter=encounter, threat_pool=pool)
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_opponent_target=opponent,
            effort_level=EffortLevel.MEDIUM,
        )
        CombatRoundActionTarget.objects.create(action=action, opponent=opponent)
        action_pk = action.pk
        action.delete()
        self.assertFalse(CombatRoundActionTarget.objects.filter(action_id=action_pk).exists())


class ResolveTargetsAoEExpansionTests(TestCase):
    """_resolve_focused_targets accepts focused_opponent_target_ids list."""

    def test_multi_id_list_persists_join_rows(self) -> None:
        """Supplying focused_opponent_target_ids writes join rows for each id."""
        from actions.constants import ActionBackend, ActionTargetType
        from actions.round_context import get_active_round_context
        from actions.types import ActionRef, PlayerAction
        from world.combat.constants import ParticipantStatus
        from world.scenes.constants import RoundStatus
        from world.vitals.models import CharacterVitals

        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        sheet = participant.character_sheet
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        opp_a = CombatOpponentFactory(
            encounter=encounter, status=OpponentStatus.ACTIVE, threat_pool=pool
        )
        opp_b = CombatOpponentFactory(
            encounter=encounter, status=OpponentStatus.ACTIVE, threat_pool=pool
        )

        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(base_power=10),
            target_type=ActionTargetType.AREA,
            damage_profile=False,
        )
        TechniqueDamageProfileFactory(technique=technique, base_damage=5)

        ctx = get_active_round_context(sheet)
        assert ctx is not None

        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=technique.pk,
            action_slot="focused",
        )
        ctx.record_declaration(
            sheet,
            PlayerAction(
                backend=ActionBackend.COMBAT,
                display_name="AoE attack",
                ref=ref,
            ),
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_ids": [opp_a.pk, opp_b.pk],
            },
        )

        action = CombatRoundAction.objects.get(participant=participant, round_number=1)
        # Primary target set to first supplied id
        self.assertEqual(action.focused_opponent_target_id, opp_a.pk)
        # Join rows for both
        stored_ids = set(
            CombatRoundActionTarget.objects.filter(action=action).values_list(
                "opponent_id", flat=True
            )
        )
        self.assertEqual(stored_ids, {opp_a.pk, opp_b.pk})


@tag("postgres")
class AoEConditionExpansionTests(TestCase):
    """AREA condition application targets all join-table opponents.

    Tagged @tag("postgres") because apply_technique_conditions hits
    apply_condition which uses DISTINCT ON (PG-only).
    """

    def test_area_condition_targets_all_opponents(self) -> None:
        """AREA technique's condition targets_by_kind[ENEMY] includes all join opponents."""
        from actions.constants import ActionTargetType
        from world.magic.models.techniques import ConditionTargetKind

        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="AoECondition", base_power=10),
            target_type=ActionTargetType.AREA,
            damage_profile=False,
        )
        TechniqueAppliedConditionFactory(technique=technique, target_kind="enemy")

        encounter = CombatEncounterFactory(round_number=1)
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool)
        opp_a = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        opp_b = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            threat_pool=pool,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=opp_a,
            effort_level=EffortLevel.MEDIUM,
        )
        CombatRoundActionTarget.objects.create(action=action, opponent=opp_a)
        CombatRoundActionTarget.objects.create(action=action, opponent=opp_b)

        resolver = _resolver(participant, action)

        captured_targets = {}

        def capturing_apply(
            technique, success_level, eff_intensity, targets_by_kind, source_character
        ):
            captured_targets.update(targets_by_kind)
            return []

        with patch(
            "world.magic.services.condition_application.apply_technique_conditions",
            side_effect=capturing_apply,
        ):
            with patch("world.combat.services.perform_check") as mock_check:
                mock_check.return_value = type(
                    "CR", (), {"success_level": 1, "roll": 10, "difficulty": 5}
                )()
                resolver(power=10, ledger=_ledger(10))

        enemy_targets = captured_targets.get(ConditionTargetKind.ENEMY, [])
        enemy_object_ids = [obj.pk for obj in enemy_targets if obj is not None]
        self.assertIn(opp_a.objectdb_id, enemy_object_ids)
        self.assertIn(opp_b.objectdb_id, enemy_object_ids)
