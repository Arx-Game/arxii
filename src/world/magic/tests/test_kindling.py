"""Which resonances the situation kindles now, and how strongly (#5124, Task 3)."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ClashFlavor, LockPcRole, OpponentTier
from world.combat.factories import (
    ClashContributionFactory,
    ClashFactory,
    ClashRoundFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.round_context import CombatRoundContext
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
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
from world.magic.models import KindledStrengthTier, KindlingSituation
from world.magic.services.kindling import kindled_for, kindled_resonances
from world.magic.types.kindling import KindlingAct
from world.mechanics.factories import PropertyFactory
from world.missions.factories import MissionInstanceFactory, MissionThemeFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.scenes.services import set_active_persona
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.vitals.factories import CharacterVitalsFactory


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

    def _lay(self, condition: str, *, laid_by, harmful: bool = False, hidden: bool = False) -> None:
        template = ConditionTemplateFactory(name=condition, is_visible_to_others=not hidden)
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

    def test_an_opponent_bearing_the_feeling_counts_as_present(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter)
        template = ConditionTemplateFactory(name="Bloodlust")
        template.properties.add(self.feeling)
        ConditionInstanceFactory(
            target_id=opponent.objectdb_id, condition=template, source_character=None
        )
        self.assertIsNotNone(self._kindled(resolution=self.resolution).tier)

    def test_a_harm_the_holder_laid_does_not_count(self) -> None:
        self._lay("Torment", laid_by=self.sheet, harmful=True)
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)

    def test_a_harm_someone_else_laid_still_counts(self) -> None:
        self._lay("Torment", laid_by=CharacterSheetFactory(), harmful=True)
        self.assertIsNotNone(self._kindled(resolution=self.resolution).tier)

    def test_a_feeling_the_holder_laid_without_the_harm_property_counts(self) -> None:
        self._lay("Awe", laid_by=self.sheet)
        self.assertIsNotNone(self._kindled(resolution=self.resolution).tier)

    def test_a_condition_hidden_from_others_neither_kindles_nor_is_named(self) -> None:
        self._lay("Secret Wrath", laid_by=CharacterSheetFactory(), hidden=True)
        result = self._kindled(resolution=self.resolution)
        self.assertIsNone(result.tier)
        self.assertEqual(result.reasons, ())


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


class ConcealedPresenceTests(TestCase):
    """A concealed room occupant the holder has not detected is not here for her."""

    def setUp(self) -> None:
        _tiers()
        self.room = RoomProfileFactory().objectdb
        self.sheet = CharacterSheetFactory()
        self.sheet.character.location = self.room
        self.rival = CharacterSheetFactory()
        self.rival.character.location = self.room
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        thread = ThreadFactory(owner=self.sheet, resonance=self.resonance, as_track_thread=True)
        side = thread.target_relationship
        side.target = self.rival
        side.tier = 2
        side.save()
        KindlingSituationFactory(
            resonance=self.resonance,
            situation=Situation.THREAD_ANCHOR_PRESENT,
            enemies_only=False,
            strength=None,
        )

    def _conceal(self):
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        return ConditionInstanceFactory(target=self.rival.character, condition=template)

    def _result(self):
        return kindled_for(self.sheet, self.resonance)

    def test_a_visible_anchor_in_the_room_kindles_and_is_named(self) -> None:
        result = self._result()
        self.assertEqual(result.tier.rank, 2)
        self.assertEqual(len(result.reasons), 1)

    def test_a_concealed_anchor_neither_kindles_nor_is_named(self) -> None:
        self._conceal()
        result = self._result()
        self.assertIsNone(result.tier)
        self.assertEqual(result.reasons, ())

    def test_an_anchor_she_has_detected_is_here_again(self) -> None:
        self._conceal().detected_by.add(self.sheet)
        self.assertEqual(self._result().tier.rank, 2)

    def test_a_concealed_hurt_bystander_is_not_someone_in_trouble(self) -> None:
        KindlingSituation.objects.all().delete()
        KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.SOMEONE_IN_TROUBLE, strength=1
        )
        CharacterVitalsFactory(character_sheet=self.rival, health=1, max_health=10)
        self.assertIsNotNone(self._result().tier)
        self._conceal()
        self.assertIsNone(self._result().tier)


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


class _FightCase(_Case):
    """A character in a fight with an ally who can be in trouble."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.mine = CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        self.ally = CharacterSheetFactory()
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.ally)
        self.resolution = CombatRoundContext(self.mine)


class SomeoneInTroubleTests(_FightCase):
    def setUp(self) -> None:
        super().setUp()
        KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.SOMEONE_IN_TROUBLE, strength=2
        )

    def test_a_badly_hurt_ally_kindles_with_no_name_in_the_reason(self) -> None:
        CharacterVitalsFactory(character_sheet=self.ally, health=10, max_health=100)
        result = self._kindled(resolution=self.resolution)
        self.assertEqual(result.tier.rank, 2)
        self.assertEqual(result.reasons, ("Someone here is in trouble",))

    def test_a_healthy_ally_does_not(self) -> None:
        CharacterVitalsFactory(character_sheet=self.ally, health=90, max_health=100)
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)

    def test_a_character_with_no_health_figures_is_not_hurt(self) -> None:
        CharacterVitalsFactory(character_sheet=self.ally, health=0, max_health=0)
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)

    def test_the_designated_peril_condition_kindles(self) -> None:
        # The template is found through VitalsConsequenceConfig, never by its name.
        bleeding = BleedingOutConditionFactory()
        ConditionInstanceFactory(target=self.ally.character, condition=bleeding)
        self.assertIsNotNone(self._kindled(resolution=self.resolution).tier)

    def test_an_opponent_in_trouble_is_not_someone_to_aid(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter, persona=PersonaFactory())
        CharacterVitalsFactory(
            character_sheet=opponent.persona.character_sheet, health=1, max_health=100
        )
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)

    def test_only_an_act_that_aids_earns_it(self) -> None:
        CharacterVitalsFactory(character_sheet=self.ally, health=10, max_health=100)
        aids = KindlingAct(kind=KindlingActKind.AID, target=self.ally, aids=True)
        attacks = KindlingAct(kind=KindlingActKind.ATTACK, target=self.ally)
        self.assertEqual(self._kindled(resolution=self.resolution, act=aids).tier.rank, 2)
        self.assertIsNone(self._kindled(resolution=self.resolution, act=attacks).tier)

    def _lock(self, *, held, rescuer) -> None:
        clash = ClashFactory(
            encounter=self.encounter,
            flavor=ClashFlavor.LOCK,
            lock_pc_role=LockPcRole.ESCAPING,
            npc_win_threshold=None,
            initiator=held,
        )
        ClashContributionFactory(clash_round=ClashRoundFactory(clash=clash), character=rescuer)

    def test_the_held_side_of_a_lock_is_in_trouble_but_a_rescuer_is_not(self) -> None:
        rescuer = CharacterSheetFactory()
        CombatParticipantFactory(encounter=self.encounter, character_sheet=rescuer)
        self._lock(held=self.sheet, rescuer=rescuer)  # the holder is the one held
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)
        self._lock(held=self.ally, rescuer=self.sheet)
        self.assertIsNotNone(self._kindled(resolution=self.resolution).tier)


class OrganizationAnchorTests(_Case):
    def setUp(self) -> None:
        super().setUp()
        self.organization = OrganizationFactory()
        self.member = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=self.organization, persona=self.member.primary_persona
        )
        thread = ThreadFactory(owner=self.sheet, resonance=self.resonance)
        thread.target_kind = TargetKind.ORGANIZATION
        thread.target_trait = None
        thread.target_organization = self.organization
        thread.save()
        self.row = KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.THREAD_ANCHOR_PRESENT, strength=2
        )
        self.encounter = CombatEncounterFactory()
        self.mine = CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        self.resolution = CombatRoundContext(self.mine)

    def test_an_organization_is_here_while_a_member_is_and_is_named_by_its_name(self) -> None:
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.member)
        result = self._kindled(resolution=self.resolution)
        self.assertEqual(result.tier.rank, 2)
        self.assertEqual(result.reasons, (f"{self.organization.name} is here",))

    def test_no_member_present_means_not_kindled(self) -> None:
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)

    def test_without_a_row_strength_an_organization_has_no_bond_tier_to_read(self) -> None:
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.member)
        self.row.strength = None
        self.row.save()
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)


class VowSituationAsKindlingRowTests(_FightCase):
    def test_a_vow_library_situation_kindles_at_the_rows_strength(self) -> None:
        KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.TARGET_IS_BOSS, strength=2
        )
        boss = CombatOpponentFactory(encounter=self.encounter, tier=OpponentTier.BOSS)
        self.assertIsNone(self._kindled(resolution=self.resolution).tier)
        CombatRoundActionFactory(
            participant=self.mine,
            round_number=self.encounter.round_number,
            focused_opponent_target=boss,
        )
        result = self._kindled(resolution=self.resolution)
        self.assertEqual(result.tier.rank, 2)
        self.assertEqual(result.reasons, ("Target Is a Boss",))


class MaskedNameTests(_FightCase):
    def test_a_masked_anchor_is_named_by_the_mask_not_the_real_name(self) -> None:
        anchor = CharacterSheetFactory()
        real_name = anchor.primary_persona.name
        mask = PersonaFactory(
            character_sheet=anchor,
            persona_type=PersonaType.TEMPORARY,
            is_fake_name=True,
            name="Hooded Stranger",
        )
        set_active_persona(anchor, mask)
        thread = ThreadFactory(owner=self.sheet, resonance=self.resonance, as_track_thread=True)
        side = thread.target_relationship
        side.target = anchor
        side.tier = 1
        side.save()
        KindlingSituationFactory(
            resonance=self.resonance, situation=Situation.THREAD_ANCHOR_PRESENT, strength=None
        )
        CombatParticipantFactory(encounter=self.encounter, character_sheet=anchor)
        result = self._kindled(resolution=self.resolution)
        self.assertEqual(result.tier.rank, 1)
        self.assertNotIn(real_name, " ".join(result.reasons))
        self.assertNotIn(anchor.character.db_key, " ".join(result.reasons))


class QueryCountTests(TestCase):
    """The queries one call makes do not grow with how many resonances the character holds."""

    def _count(self, resonances: int) -> int:
        _tiers()
        sheet = CharacterSheetFactory()
        affinity = AffinityFactory()
        feeling = PropertyFactory()
        for _ in range(resonances):
            CharacterResonanceFactory(
                character_sheet=sheet, resonance=ResonanceFactory(affinity=affinity)
            )
        for situation in (
            Situation.THREAD_ANCHOR_PRESENT,
            Situation.SOMEONE_IN_TROUBLE,
            Situation.TARGET_IS_BOSS,
        ):
            KindlingSituationFactory(
                resonance=None, for_affinity=affinity, situation=situation, strength=1
            )
        KindlingSituationFactory(
            resonance=None,
            for_affinity=affinity,
            situation=Situation.SHARED_FEELING,
            condition_property=feeling,
            strength=1,
        )
        encounter = CombatEncounterFactory()
        mine = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        resolution = CombatRoundContext(mine)
        with CaptureQueriesContext(connection) as queries:
            kindled_resonances(sheet, resolution=resolution)
        return len(queries)

    def test_two_resonances_and_six_cost_the_same_queries(self) -> None:
        self.assertEqual(self._count(2), self._count(6))


class DeedNamingTests(_Case):
    """A deed reads as what the character did, never as the situation's type name."""

    def setUp(self) -> None:
        super().setUp()
        self.theme = MissionThemeFactory(player_text="This mission is about people held captive.")
        self.row = KindlingSituationFactory(
            resonance=self.resonance,
            situation=Situation.MISSION_THEME,
            mission_theme=self.theme,
            strength=1,
        )

    def _deed(self, **kwargs: object):
        from world.magic.constants import GainSource
        from world.magic.services.resonance import grant_resonance

        grants: list = []
        grant_resonance(
            self.sheet,
            self.resonance,
            5,
            source=GainSource.KINDLED_DEED,
            kindling_situation=self.row,
            ledger_out=grants,
            **kwargs,
        )
        return grants[0]

    def test_the_recorded_label_is_what_the_deed_reads_as(self) -> None:
        from world.magic.services.reflection import deed_label

        grant = self._deed(deed_label="Bar the overseers' door")
        self.assertEqual(deed_label(grant), f"Bar the overseers' door · 5 {self.resonance.name}")

    def test_without_a_label_the_deed_reads_as_the_panels_reason_for_the_row(self) -> None:
        from world.magic.services.reflection import deed_what

        self.assertEqual(deed_what(self._deed()), "This mission is about people held captive.")
        self.row.reason_text = "Barred the overseers' door"
        self.assertEqual(deed_what(self._deed()), "Barred the overseers' door")

    def test_an_old_deed_reads_inside_a_sentence_in_the_rites_effect_line(self) -> None:
        from world.magic.factories import ReflectionFactory
        from world.magic.services.reflection import deed_in_sentence
        from world.magic.services.settling_preview import _effect_line

        grant = self._deed()
        self.assertEqual(deed_in_sentence(grant), "this mission is about people held captive")
        reflection = ReflectionFactory(
            character_sheet=self.sheet, grant=grant, resonance=None, choice="EMBRACE"
        )
        line = _effect_line(self.sheet, reflection, None, {}, 50)
        self.assertEqual(
            line,
            f"Your {self.resonance.name} from this mission is about people held captive "
            "grows, up to 5.",
        )

    def test_a_name_keeps_its_capital_and_a_recorded_label_is_left_as_authored(self) -> None:
        from world.magic.services.reflection import deed_in_sentence

        self.row.reason_text = "Tomas Reeve is here."
        self.assertEqual(deed_in_sentence(self._deed()), "Tomas Reeve is here")
        self.assertEqual(
            deed_in_sentence(self._deed(deed_label="Barred the overseers' door")),
            "Barred the overseers' door",
        )


class PanelOrderTests(_Case):
    def test_kindled_rows_come_first_strongest_first_then_the_rest(self) -> None:
        from world.magic.factories import kindle_resonance
        from world.magic.services.kindling import kindled_resonances_now

        affinity = self.resonance.affinity
        faint = ResonanceFactory(affinity=affinity, name="B faint")
        strong = ResonanceFactory(affinity=affinity, name="C strong")
        kindle_resonance(self.sheet, faint, KindledStrengthTier.objects.get(rank=1))
        kindle_resonance(self.sheet, strong, KindledStrengthTier.objects.get(rank=3))

        names = [row.resonance.name for row in kindled_resonances_now(self.sheet)]

        self.assertEqual(names, [strong.name, faint.name, self.resonance.name])
