"""Which resonances the situation kindles now, and how strongly (#5124, Task 3)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.round_context import CombatRoundContext
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.covenants.perks.constants import Situation
from world.magic.constants import KindlingActKind, TargetKind
from world.magic.factories import (
    AffinityFactory,
    CharacterResonanceFactory,
    KindledStrengthTierFactory,
    KindlingConfigFactory,
    KindlingFactory,
    KindlingSituationFactory,
    ResonanceFactory,
    ThreadFactory,
)
from world.magic.models import KindledStrengthTier
from world.magic.services.kindling import kindled_for, kindled_resonances
from world.magic.types.kindling import KindlingAct
from world.mechanics.factories import PropertyFactory
from world.missions.factories import MissionInstanceFactory, MissionThemeFactory


def _tiers() -> None:
    """Three strengths: bond tier 1, 2, 3 and severity 1, 3, 5 reach ranks 1, 2, 3."""
    KindledStrengthTier.objects.all().delete()
    for rank, severity in ((1, 1), (2, 3), (3, 5)):
        KindledStrengthTierFactory(
            rank=rank, name=f"Strength {rank}", min_bond_tier=rank, min_severity=severity
        )


class _Case(TestCase):
    def setUp(self) -> None:
        _tiers()
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

    def _kindled(self, **kwargs: object):
        return kindled_resonances(self.sheet, **kwargs)[0]


class NothingAuthoredTests(_Case):
    def test_every_held_resonance_is_listed_and_none_is_kindled(self) -> None:
        other = ResonanceFactory(affinity=self.resonance.affinity)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=other)
        results = kindled_resonances(self.sheet)
        self.assertEqual({r.resonance for r in results}, {self.resonance, other})
        self.assertTrue(all(r.tier is None and not r.reasons for r in results))

    def test_a_sheet_with_no_resonances_gets_an_empty_list(self) -> None:
        self.assertEqual(kindled_resonances(CharacterSheetFactory()), [])

    def test_a_rank_with_no_strength_row_kindles_nothing(self) -> None:
        KindledStrengthTier.objects.filter(rank=3).delete()
        feeling = PropertyFactory()
        KindlingSituationFactory(
            resonance=self.resonance,
            situation=Situation.OWN_FEELING,
            condition_property=feeling,
            strength=3,
        )
        template = ConditionTemplateFactory(name="Rage")
        template.properties.add(feeling)
        ConditionInstanceFactory(target=self.sheet.character, condition=template)
        self.assertIsNone(kindled_for(self.sheet, self.resonance).tier)


class FeelingTests(_Case):
    def setUp(self) -> None:
        super().setUp()
        self.feeling = PropertyFactory()
        self.resonance.feeling = self.feeling
        self.resonance.save()
        self.row = KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.OWN_FEELING, strength=None
        )
        self.grief = ConditionTemplateFactory(name="Grief")
        self.grief.properties.add(self.feeling)

    def test_bearing_the_resonances_feeling_kindles_at_the_conditions_severity(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.grief, severity=3)
        result = self._kindled()
        self.assertEqual(result.tier.rank, 2)
        self.assertEqual(result.reasons, ("You carry Grief",))
        self.assertEqual(result.strongest_situation, self.row)

    def test_a_deeper_condition_reaches_a_stronger_strength(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.grief, severity=5)
        self.assertEqual(self._kindled().tier.rank, 3)

    def test_without_the_condition_it_is_not_kindled(self) -> None:
        self.assertIsNone(self._kindled().tier)

    def test_a_condition_below_every_reach_does_not_kindle(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.grief, severity=0)
        self.assertIsNone(self._kindled().tier)

    def test_reason_text_replaces_the_built_reason(self) -> None:
        self.row.reason_text = "Grief has hold of you"
        self.row.save()
        ConditionInstanceFactory(target=self.sheet.character, condition=self.grief, severity=1)
        self.assertEqual(self._kindled().reasons, ("Grief has hold of you",))

    def test_an_affinity_row_kindles_every_resonance_of_that_affinity(self) -> None:
        self.row.delete()
        affinity = AffinityFactory()
        mine = ResonanceFactory(affinity=affinity)
        sibling = ResonanceFactory(affinity=affinity)
        elsewhere = ResonanceFactory()
        for resonance in (mine, sibling, elsewhere):
            CharacterResonanceFactory(character_sheet=self.sheet, resonance=resonance)
        KindlingSituationFactory(
            resonance=None,
            for_affinity=affinity,
            situation=Situation.OWN_FEELING,
            condition_property=self.feeling,
            strength=1,
        )
        ConditionInstanceFactory(target=self.sheet.character, condition=self.grief)
        by_resonance = {r.resonance: r.tier for r in kindled_resonances(self.sheet)}
        self.assertIsNotNone(by_resonance[mine])
        self.assertIsNotNone(by_resonance[sibling])
        self.assertIsNone(by_resonance[elsewhere])
        self.assertIsNone(by_resonance[self.resonance])


class SharedFeelingTests(_Case):
    def setUp(self) -> None:
        super().setUp()
        self.feeling = PropertyFactory()
        self.harm = PropertyFactory()
        KindlingConfigFactory(harm_property=self.harm)
        self.resonance.feeling = self.feeling
        self.resonance.save()
        KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.SHARED_FEELING, strength=1
        )
        self.encounter = CombatEncounterFactory()
        self.mine = CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        self.ally = CharacterSheetFactory()
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.ally)
        self.resolution = CombatRoundContext(self.mine)

    def _lay(self, condition: str, *, laid_by, harmful: bool = False) -> None:
        template = ConditionTemplateFactory(name=condition)
        template.properties.add(self.feeling)
        if harmful:
            template.properties.add(self.harm)
        ConditionInstanceFactory(
            target=self.ally.character, condition=template, source_character=laid_by.character
        )

    def test_an_ally_bearing_the_feeling_kindles(self) -> None:
        self._lay("Dread", laid_by=CharacterSheetFactory())
        result = self._kindled(resolution=self.resolution)
        self.assertEqual(result.tier.rank, 1)
        self.assertEqual(result.reasons, ("Those around you carry Dread",))

    def test_a_harm_the_holder_laid_does_not_count(self) -> None:
        self._lay("Torment", laid_by=self.sheet, harmful=True)
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)

    def test_a_harm_someone_else_laid_still_counts(self) -> None:
        self._lay("Torment", laid_by=CharacterSheetFactory(), harmful=True)
        self.assertIsNotNone(self._kindled(resolution=self.resolution).tier)

    def test_a_feeling_the_holder_laid_without_the_harm_property_counts(self) -> None:
        self._lay("Awe", laid_by=self.sheet)
        self.assertIsNotNone(self._kindled(resolution=self.resolution).tier)


class TargetInStateTests(_Case):
    def test_a_target_in_a_state_the_holder_caused_kindles_on_an_act_against_it(self) -> None:
        feeling = PropertyFactory()
        self.resonance.feeling = feeling
        self.resonance.save()
        KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.TARGET_IN_STATE_THEY_CAUSED, strength=2
        )
        victim = CharacterSheetFactory()
        template = ConditionTemplateFactory(name="Broken")
        template.properties.add(feeling)
        ConditionInstanceFactory(
            target=victim.character, condition=template, source_character=self.sheet.character
        )
        act = KindlingAct(kind=KindlingActKind.ATTACK, target=victim)
        self.assertEqual(self._kindled(act=act).tier.rank, 2)
        self.assertIsNone(self._kindled().tier)
        stranger = KindlingAct(kind=KindlingActKind.ATTACK, target=CharacterSheetFactory())
        self.assertIsNone(self._kindled(act=stranger).tier)


class ThreadAnchorTests(TestCase):
    def setUp(self) -> None:
        _tiers()
        self.sheet = CharacterSheetFactory()
        self.anchor = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        self.thread = ThreadFactory(
            owner=self.sheet, resonance=self.resonance, as_track_thread=True
        )
        side = self.thread.target_relationship
        side.target = self.anchor
        side.tier = 2  # one-sided: the anchor never declared anything back
        side.save()
        self.row = KindlingSituationFactory(
            resonance=self.resonance,
            situation=Situation.THREAD_ANCHOR_PRESENT,
            enemies_only=True,
            strength=None,
        )
        self.encounter = CombatEncounterFactory()
        self.mine = CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        self.resolution = CombatRoundContext(self.mine)

    def test_the_anchor_as_an_opponent_kindles_at_the_bonds_tier_and_is_named(self) -> None:
        CombatOpponentFactory(encounter=self.encounter, persona=self.anchor.primary_persona)
        result = kindled_for(self.sheet, self.resonance, resolution=self.resolution)
        self.assertEqual(result.tier.rank, 2)
        self.assertEqual(
            result.reasons, (f"{self.anchor.character.db_key} stands against you here",)
        )

    def test_an_anchor_fighting_beside_the_holder_does_not_count_when_enemies_only(self) -> None:
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.anchor)
        result = kindled_for(self.sheet, self.resonance, resolution=self.resolution)
        self.assertIsNone(result.tier)

    def test_an_anchor_beside_the_holder_counts_without_enemies_only(self) -> None:
        self.row.enemies_only = False
        self.row.save()
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.anchor)
        result = kindled_for(self.sheet, self.resonance, resolution=self.resolution)
        self.assertEqual(result.tier.rank, 2)

    def test_the_act_must_be_aimed_at_the_anchor(self) -> None:
        CombatOpponentFactory(encounter=self.encounter, persona=self.anchor.primary_persona)
        at_anchor = KindlingAct(kind=KindlingActKind.ATTACK, target=self.anchor)
        elsewhere = KindlingAct(kind=KindlingActKind.ATTACK, target=CharacterSheetFactory())
        kwargs = {"resolution": self.resolution}
        self.assertIsNotNone(kindled_for(self.sheet, self.resonance, act=at_anchor, **kwargs).tier)
        self.assertIsNone(kindled_for(self.sheet, self.resonance, act=elsewhere, **kwargs).tier)

    def test_a_retired_thread_anchors_nothing(self) -> None:
        from django.utils import timezone

        CombatOpponentFactory(encounter=self.encounter, persona=self.anchor.primary_persona)
        self.thread.retired_at = timezone.now()
        self.thread.save()
        self.assertEqual(self.thread.target_kind, TargetKind.RELATIONSHIP_TRACK)
        self.assertIsNone(kindled_for(self.sheet, self.resonance, resolution=self.resolution).tier)


class MissionThemeTests(_Case):
    def setUp(self) -> None:
        super().setUp()
        self.theme = MissionThemeFactory(player_text="This mission is about people held captive.")
        KindlingSituationFactory(
            resonance=self.resonance,
            situation=Situation.MISSION_THEME,
            mission_theme=self.theme,
            strength=1,
        )
        self.mission = MissionInstanceFactory()

    def test_a_mission_carrying_the_theme_kindles_with_the_themes_text(self) -> None:
        self.mission.template.themes.add(self.theme)
        result = self._kindled(mission=self.mission)
        self.assertEqual(result.tier.rank, 1)
        self.assertEqual(result.reasons, ("This mission is about people held captive.",))

    def test_a_mission_without_the_theme_or_no_mission_does_not(self) -> None:
        self.assertIsNone(self._kindled(mission=self.mission).tier)
        self.assertIsNone(self._kindled().tier)

    def test_the_act_must_take_an_option_carrying_the_theme(self) -> None:
        from world.missions.factories import MissionOptionFactory

        self.mission.template.themes.add(self.theme)
        option = MissionOptionFactory()
        act = KindlingAct(kind=KindlingActKind.MISSION_OPTION, mission_option=option)
        self.assertIsNone(self._kindled(mission=self.mission, act=act).tier)
        option.themes.add(self.theme)
        self.assertEqual(self._kindled(mission=self.mission, act=act).tier.rank, 1)


class LiveKindlingTests(_Case):
    def test_a_rally_kindling_counts_for_the_fight_the_character_is_in(self) -> None:
        encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        rallier = CharacterSheetFactory()
        KindlingFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            strength=2,
            encounter=encounter,
            kindled_by=rallier,
        )
        result = self._kindled()
        self.assertEqual(result.tier.rank, 2)
        self.assertEqual(result.reasons, (f"{rallier.character.db_key} rallied you",))
        self.assertIsNone(result.strongest_situation)

    def test_a_kindling_for_another_fight_does_not_count(self) -> None:
        KindlingFactory(character_sheet=self.sheet, resonance=self.resonance, strength=2)
        self.assertIsNone(self._kindled().tier)
