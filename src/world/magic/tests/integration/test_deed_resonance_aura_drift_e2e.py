"""E2E: a mission route reward grants resonance, drifts aura, fires an achievement.

Exercises the full #1737 seam: MissionOptionRouteReward.resonance (authoring) ->
emit_terminal_rewards -> apply_deed_rewards -> MissionRewardQueue ->
apply_mission_reward_batch -> grant_resonance -> recompute_aura ->
fire_aura_threshold_crossings -> grant_achievement.

``apply_deed_rewards`` has no production caller yet (a pre-existing Phase 5b.1
gap outside #1737's scope) -- the engine only calls ``emit_terminal_rewards``
today -- so this test calls it directly to populate the queue, exactly as
``world/missions/tests/test_services_cron.py`` does for the cron's own tests.
"""

from decimal import Decimal

from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.achievements.models import CharacterAchievement
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import AffinityFactory, CharacterAuraFactory, ResonanceFactory
from world.magic.models import AuraAffinityThreshold, CharacterAura, CharacterResonance
from world.magic.types import AffinityType
from world.missions.constants import DeedRewardKind, DeedRewardSink, OptionKind, OptionSource
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionOptionRouteRewardFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.services.cron import apply_mission_reward_batch
from world.missions.services.rewards import apply_deed_rewards, emit_terminal_rewards


class DeedResonanceAuraDriftE2ETest(TestCase):
    def test_full_deed_to_achievement_pipeline(self):
        sheet = CharacterSheetFactory()
        CharacterAuraFactory(character=sheet.character)
        abyssal = AffinityFactory(name="Abyssal")
        cruelty = ResonanceFactory(name="Cruelty", affinity=abyssal)
        achievement = AchievementFactory(is_active=True)
        AuraAffinityThreshold.objects.create(
            affinity=AffinityType.ABYSSAL,
            threshold_percent=Decimal("50.00"),
            discovery_achievement=achievement,
        )

        template = MissionTemplateFactory(name="e2e-deed-resonance")
        node = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )
        route = MissionOptionRouteFactory(option=option, outcome_tier=None, target_node=None)
        instance = MissionInstanceFactory(template=template)
        MissionParticipantFactory(
            instance=instance,
            character=sheet.character,
            is_contract_holder=True,
        )
        MissionOptionRouteRewardFactory(
            route=route,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=100,
            resonance=cruelty,
            contract_holder_only=True,
        )
        deed = MissionDeedRecordFactory(
            instance=instance,
            actor=sheet.character,
            node=node,
            option=option,
        )

        emit_terminal_rewards(instance, route, deed)
        apply_deed_rewards(deed)
        result = apply_mission_reward_batch()
        assert not result.failed

        cr = CharacterResonance.objects.get(character_sheet=sheet, resonance=cruelty)
        assert cr.lifetime_earned == 100

        aura = CharacterAura.objects.get(character=sheet.character)
        assert float(aura.abyssal) == 100.0

        assert CharacterAchievement.objects.filter(
            character_sheet=sheet, achievement=achievement
        ).exists()
