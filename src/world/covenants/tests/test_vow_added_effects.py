"""Tests for the vow added effects read seam (#4581).

``vow_added_effects_for_cast`` picks the ``VowAddedEffect`` rows that fire for one
cast (the caster's own engaged vows plus co-present covenant allies' vows), scales
their bonuses by the holder's COVENANT_ROLE thread level, and
``apply_vow_effect_payloads`` / ``vow_damage_profiles`` / ``record_vow_effect_firings``
hand them to the existing payload seams and the frequency ledger.

Ysmay holds the vow under test, Hobb is a co-present covenant ally and Wren a
second holder. Built in ``setUp`` rather than ``setUpTestData``: the factories
create Evennia ``ObjectDB`` instances (``DbHolder``, not deepcopyable), the same
reason every neighboring covenants test file gives.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    VowAddedEffectFiringFactory,
)
from world.combat.models import CombatEncounter, CombatParticipant, VowAddedEffectFiring
from world.combat.round_context import CombatRoundContext
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.covenants.added_effects import (
    apply_vow_effect_payloads,
    record_vow_effect_firings,
    vow_added_effects_for_cast,
    vow_added_effects_on_technique,
    vow_damage_profiles,
)
from world.covenants.constants import CovenantType, VowEffectContext, VowEffectFrequency
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectDamageProfileFactory,
    VowAddedEffectFactory,
    engage_vow_with_thread,
)
from world.covenants.models import VowAddedEffect
from world.covenants.perks.constants import PerkBeneficiary, Situation
from world.covenants.types import FiredVowEffect
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.models import Technique
from world.magic.models.techniques import ConditionTargetKind
from world.scenes.factories import SceneFactory

_IN_COMBAT = VowEffectContext.IN_COMBAT


class VowAddedEffectsTestBase(TestCase):
    """Ysmay holds ``self.role`` at thread level 5; Hobb holds another role in the covenant."""

    def setUp(self) -> None:
        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.hobb_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.ysmay = CharacterSheetFactory()
        self.hobb = CharacterSheetFactory()
        self.unsworn = CharacterSheetFactory()
        self.hold = _technique_tagged(TechniqueFunction.HOLD)
        engage_vow_with_thread(self.ysmay, self.role, covenant=self.covenant, thread_level=5)

    def _engage_hobb(self, *, engaged: bool = True) -> None:
        if engaged:
            engage_vow_with_thread(
                self.hobb, self.hobb_role, covenant=self.covenant, thread_level=1
            )
            return
        CharacterCovenantRoleFactory(
            character_sheet=self.hobb,
            covenant=self.covenant,
            covenant_role=self.hobb_role,
            engaged=False,
        )
        self.hobb.character.covenant_roles.invalidate()

    def _fight(self, *sheets: object) -> tuple[CombatEncounter, dict[int, CombatParticipant]]:
        encounter = CombatEncounterFactory(round_number=1)
        participants = {
            sheet.pk: CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
            for sheet in sheets
        }
        return encounter, participants

    def _cast(
        self,
        subject: object,
        technique: Technique | None = None,
        resolution: object | None = None,
    ) -> list[FiredVowEffect]:
        return vow_added_effects_for_cast(
            subject,
            technique if technique is not None else self.hold,
            resolution=resolution,
            target=None,
        )


def _technique_tagged(function: str) -> Technique:
    technique = TechniqueFactory()
    TechniqueFunctionTagFactory(technique=technique, function=function)
    return technique


class OwnCastTests(VowAddedEffectsTestBase):
    def test_own_cast_scales_severity_per_level_above_unlock(self) -> None:
        VowAddedEffectFactory(
            covenant_role=self.role, unlock_thread_level=2, severity_per_thread_level=2
        )
        [fired] = self._cast(self.ysmay)
        self.assertEqual((fired.holder, fired.severity_bonus), (self.ysmay, 6))
        self.assertFalse(fired.is_secondary)

    def test_duration_and_damage_scale_the_same_way(self) -> None:
        VowAddedEffectFactory(
            covenant_role=self.role,
            cast_context=VowEffectContext.ANY,
            unlock_thread_level=3,
            duration_per_thread_level=1,
            damage_per_thread_level=4,
        )
        [fired] = self._cast(self.ysmay)
        self.assertEqual((fired.duration_bonus, fired.damage_bonus), (2, 8))

    def test_below_unlock_nothing_fires(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role, unlock_thread_level=6)
        self.assertEqual(self._cast(self.ysmay), [])

    def test_a_different_function_does_not_fire(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role, function=TechniqueFunction.STRIKE)
        self.assertEqual(self._cast(self.ysmay), [])

    def test_narrowing_by_gift_and_by_technique(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role, gift=GiftFactory())
        VowAddedEffectFactory(
            covenant_role=self.role,
            technique=_technique_tagged(TechniqueFunction.HOLD),
            unlock_thread_level=1,
        )
        self.assertEqual(self._cast(self.ysmay), [])

        matching = VowAddedEffectFactory(
            covenant_role=self.role, gift=self.hold.gift, unlock_thread_level=2
        )
        own = VowAddedEffectFactory(
            covenant_role=self.role, technique=self.hold, unlock_thread_level=3
        )
        self.assertEqual({f.effect for f in self._cast(self.ysmay)}, {matching, own})

    def test_out_of_combat_excludes_in_combat_rows(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role, cast_context=_IN_COMBAT)
        self.assertEqual(self._cast(self.ysmay), [])

    def test_in_combat_excludes_out_of_combat_rows(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role, cast_context=VowEffectContext.OUT_OF_COMBAT)
        _, participants = self._fight(self.ysmay)
        resolution = CombatRoundContext(participants[self.ysmay.pk])
        self.assertEqual(self._cast(self.ysmay, resolution=resolution), [])
        self.assertEqual(len(self._cast(self.ysmay)), 1)

    def test_a_secondary_vow_is_scaled_by_potency(self) -> None:
        secondary_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            self.ysmay,
            secondary_role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=5,
            is_secondary=True,
        )
        VowAddedEffectFactory(
            covenant_role=secondary_role, unlock_thread_level=0, severity_per_thread_level=10
        )
        [fired] = self._cast(self.ysmay)
        self.assertTrue(fired.is_secondary)
        self.assertEqual(fired.severity_bonus, 30)


class AllyCastTests(VowAddedEffectsTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.allies_row = VowAddedEffectFactory(
            covenant_role=self.role, beneficiary=PerkBeneficiary.COVENANT_ALLIES
        )

    def test_an_allies_cast_picks_up_a_covenant_allies_row(self) -> None:
        self._engage_hobb()
        _, participants = self._fight(self.hobb, self.ysmay)
        [fired] = self._cast(self.hobb, resolution=CombatRoundContext(participants[self.hobb.pk]))
        self.assertEqual((fired.effect, fired.holder), (self.allies_row, self.ysmay))

    def test_a_covenant_allies_row_never_fires_for_the_holder(self) -> None:
        self.assertEqual(self._cast(self.ysmay), [])

    def test_a_holder_in_another_encounter_adds_nothing(self) -> None:
        self._engage_hobb()
        _, participants = self._fight(self.hobb)
        self._fight(self.ysmay)
        resolution = CombatRoundContext(participants[self.hobb.pk])
        self.assertEqual(self._cast(self.hobb, resolution=resolution), [])

    def test_a_disengaged_caster_gets_nothing(self) -> None:
        self._engage_hobb(engaged=False)
        _, participants = self._fight(self.hobb, self.ysmay)
        resolution = CombatRoundContext(participants[self.hobb.pk])
        self.assertEqual(self._cast(self.hobb, resolution=resolution), [])

    def test_two_holders_of_one_vow_each_fire(self) -> None:
        wren = CharacterSheetFactory()
        engage_vow_with_thread(wren, self.role, covenant=self.covenant, thread_level=2)
        self._engage_hobb()
        _, participants = self._fight(self.hobb, self.ysmay, wren)
        fired = self._cast(self.hobb, resolution=CombatRoundContext(participants[self.hobb.pk]))
        self.assertEqual(len(fired), 2)
        self.assertEqual({f.holder for f in fired}, {self.ysmay, wren})

    def test_one_holder_seen_through_two_covenants_fires_a_row_once(self) -> None:
        # Hobb is engaged in a second covenant Ysmay also holds self.role in: her role
        # comes back as two ally candidates, and the row still fires once for her.
        second_covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self._engage_hobb()
        engage_vow_with_thread(
            self.hobb,
            CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
            covenant=second_covenant,
            thread_level=1,
            is_secondary=True,
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.ysmay, covenant=second_covenant, covenant_role=self.role
        )
        _, participants = self._fight(self.hobb, self.ysmay)
        fired = self._cast(self.hobb, resolution=CombatRoundContext(participants[self.hobb.pk]))
        self.assertEqual([f.effect for f in fired], [self.allies_row])


class FrequencyTests(VowAddedEffectsTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter, participants = self._fight(self.ysmay)
        self.ysmay_p = participants[self.ysmay.pk]
        self.resolution = CombatRoundContext(self.ysmay_p)

    def _limited(self, frequency: str) -> VowAddedEffect:
        return VowAddedEffectFactory(
            covenant_role=self.role, cast_context=_IN_COMBAT, frequency=frequency
        )

    def test_once_per_round_is_spent_this_round_only(self) -> None:
        effect = self._limited(VowEffectFrequency.ONCE_PER_ROUND)
        VowAddedEffectFiringFactory(participant=self.ysmay_p, effect=effect, round_number=1)
        self.assertEqual(self._cast(self.ysmay, resolution=self.resolution), [])

        self.encounter.round_number = 2
        self.encounter.save()
        [fired] = self._cast(self.ysmay, resolution=self.resolution)
        self.assertEqual(fired.effect, effect)

    def test_once_per_fight_is_spent_for_the_fight(self) -> None:
        effect = self._limited(VowEffectFrequency.ONCE_PER_FIGHT)
        self.assertEqual(len(self._cast(self.ysmay, resolution=self.resolution)), 1)
        VowAddedEffectFiringFactory(participant=self.ysmay_p, effect=effect, round_number=1)
        self.encounter.round_number = 3
        self.encounter.save()
        self.assertEqual(self._cast(self.ysmay, resolution=self.resolution), [])

    def test_a_firing_in_another_fight_does_not_spend_it(self) -> None:
        effect = self._limited(VowEffectFrequency.ONCE_PER_FIGHT)
        _, other = self._fight(self.ysmay)
        VowAddedEffectFiringFactory(participant=other[self.ysmay.pk], effect=effect)
        self.assertEqual(len(self._cast(self.ysmay, resolution=self.resolution)), 1)

    def test_record_writes_limited_rows_only(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role, cast_context=_IN_COMBAT)
        limited = self._limited(VowEffectFrequency.ONCE_PER_ROUND)
        fired = self._cast(self.ysmay, resolution=self.resolution)
        self.assertEqual(len(fired), 2)
        self.assertEqual(record_vow_effect_firings(fired, encounter=self.encounter), 1)
        row = VowAddedEffectFiring.objects.get()
        self.assertEqual(
            (row.participant, row.effect, row.round_number), (self.ysmay_p, limited, 1)
        )

    def test_record_without_limited_rows_issues_no_query(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role, cast_context=_IN_COMBAT)
        fired = self._cast(self.ysmay, resolution=self.resolution)
        with self.assertNumQueries(0):
            self.assertEqual(record_vow_effect_firings(fired, encounter=self.encounter), 0)


class UpgradeTests(VowAddedEffectsTestBase):
    """A resonance sub-role's row naming the anchor row replaces it for the same holder."""

    def setUp(self) -> None:
        super().setUp()
        self.resonance = ResonanceFactory()
        self.sub_role = SubroleCovenantRoleFactory(
            parent_role=self.role, resonance=self.resonance, unlock_thread_level=3
        )
        self.wren = CharacterSheetFactory()
        self.base = VowAddedEffectFactory(covenant_role=self.role)

    def _engage_wren(self, resonance: object) -> None:
        engage_vow_with_thread(
            self.wren, self.role, covenant=self.covenant, thread_level=3, resonance=resonance
        )

    def test_the_matching_resonance_upgrade_replaces_the_base(self) -> None:
        upgrade = VowAddedEffectFactory(covenant_role=self.sub_role, upgrades=self.base)
        extra = VowAddedEffectFactory(covenant_role=self.sub_role, unlock_thread_level=1)
        self._engage_wren(self.resonance)
        self.assertEqual({f.effect for f in self._cast(self.wren)}, {upgrade, extra})

    def test_another_resonance_keeps_the_base(self) -> None:
        VowAddedEffectFactory(covenant_role=self.sub_role, upgrades=self.base)
        VowAddedEffectFactory(covenant_role=self.sub_role, unlock_thread_level=1)
        self._engage_wren(ResonanceFactory())
        self.assertEqual({f.effect for f in self._cast(self.wren)}, {self.base})

    def test_an_upgrade_whose_situation_fails_leaves_the_base(self) -> None:
        VowAddedEffectFactory(
            covenant_role=self.sub_role, upgrades=self.base, situation=Situation.TARGET_IS_BOSS
        )
        self._engage_wren(self.resonance)
        self.assertEqual({f.effect for f in self._cast(self.wren)}, {self.base})

    def test_one_holder_fires_a_row_once(self) -> None:
        self.base.beneficiary = PerkBeneficiary.WHOLE_GROUP
        self.base.save()
        self._engage_wren(self.resonance)
        self.assertEqual([f.effect for f in self._cast(self.wren)], [self.base])


class QueryDisciplineTests(VowAddedEffectsTestBase):
    def test_no_vow_no_added_effect_query(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role)
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self._cast(self.unsworn), [])
        self.assertFalse(any("vowaddedeffect" in q["sql"].lower() for q in ctx.captured_queries))

    def test_no_function_tag_no_added_effect_query(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role)
        untagged = TechniqueFactory()
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self._cast(self.ysmay, technique=untagged), [])
        self.assertFalse(any("vowaddedeffect" in q["sql"].lower() for q in ctx.captured_queries))

    def _cast_and_read_payloads(self) -> int:
        """Cast, then read every payload list the apply and damage steps read."""
        fired = self._cast(self.ysmay)
        for firing in fired:
            effect = firing.effect
            _ = (
                effect.cached_applied_conditions,
                effect.cached_removed_conditions,
                effect.cached_treatments,
                effect.cached_damage_profiles,
            )
        return len(fired)

    def test_row_count_adds_no_queries(self) -> None:
        self._cast(self.ysmay)  # warm the handler and the technique's tags

        VowAddedEffectAppliedConditionFactory(effect=VowAddedEffectFactory(covenant_role=self.role))
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(self._cast_and_read_payloads(), 1)

        for unlock in (1, 2):
            VowAddedEffectAppliedConditionFactory(
                effect=VowAddedEffectFactory(covenant_role=self.role, unlock_thread_level=unlock)
            )
        with CaptureQueriesContext(connection) as three:
            self.assertEqual(self._cast_and_read_payloads(), 3)
        self.assertEqual(len(one.captured_queries), len(three.captured_queries))

    def test_a_payload_row_added_after_a_read_is_seen_next_cast(self) -> None:
        effect = VowAddedEffectFactory(covenant_role=self.role)
        VowAddedEffectAppliedConditionFactory(effect=effect)
        [fired] = self._cast(self.ysmay)
        self.assertEqual(len(fired.effect.cached_applied_conditions), 1)

        VowAddedEffectAppliedConditionFactory(effect=effect)
        [fired] = self._cast(self.ysmay)
        self.assertEqual(len(fired.effect.cached_applied_conditions), 2)


class PayloadTests(VowAddedEffectsTestBase):
    def test_payloads_apply_with_the_bonus_and_self_means_the_caster(self) -> None:
        effect = VowAddedEffectFactory(
            covenant_role=self.role, unlock_thread_level=2, severity_per_thread_level=2
        )
        condition = ConditionTemplateFactory()
        VowAddedEffectAppliedConditionFactory(
            effect=effect,
            condition=condition,
            target_kind=ConditionTargetKind.SELF,
            base_severity=1,
        )
        fired = self._cast(self.ysmay)
        self.assertEqual(fired[0].severity_bonus, 6)

        applied, removed = apply_vow_effect_payloads(
            fired,
            technique=self.hold,
            success_level=1,
            eff_intensity=0,
            targets_by_kind={ConditionTargetKind.ALLY: [self.hobb.character]},
            source_character=self.ysmay.character,
            scene=SceneFactory(),
        )
        self.assertEqual(len(applied), 1)
        self.assertEqual(removed, [])
        instance = ConditionInstance.objects.get(target=self.ysmay.character, condition=condition)
        self.assertEqual(instance.severity, 7)
        self.assertFalse(
            ConditionInstance.objects.filter(target=self.hobb.character, condition=condition)
        )

    def test_damage_profiles_carry_their_effects_damage_bonus(self) -> None:
        effect = VowAddedEffectFactory(
            covenant_role=self.role,
            cast_context=_IN_COMBAT,
            unlock_thread_level=4,
            damage_per_thread_level=3,
        )
        profile = VowAddedEffectDamageProfileFactory(effect=effect)
        _, participants = self._fight(self.ysmay)
        fired = self._cast(self.ysmay, resolution=CombatRoundContext(participants[self.ysmay.pk]))
        self.assertEqual(vow_damage_profiles(fired), [(profile, 3)])


class StaticViewTests(VowAddedEffectsTestBase):
    def test_lists_matching_rows_without_the_cast_time_gates(self) -> None:
        locked = VowAddedEffectFactory(
            covenant_role=self.role, unlock_thread_level=9, cast_context=_IN_COMBAT
        )
        boss = VowAddedEffectFactory(covenant_role=self.role, situation=Situation.TARGET_IS_BOSS)
        VowAddedEffectFactory(covenant_role=self.role, gift=GiftFactory(), unlock_thread_level=1)
        VowAddedEffectFactory(covenant_role=self.role, function=TechniqueFunction.STRIKE)
        VowAddedEffectFactory(covenant_role=self.hobb_role)
        self.assertEqual(set(vow_added_effects_on_technique(self.ysmay, self.hold)), {locked, boss})

    def test_an_unsworn_sheet_has_none(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role)
        self.assertEqual(vow_added_effects_on_technique(self.unsworn, self.hold), [])
