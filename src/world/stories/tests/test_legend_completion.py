from __future__ import annotations

from unittest.mock import patch

from evennia.utils.test_resources import EvenniaTestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.societies.constants import RenownRisk
from world.societies.factories import LegendSourceTypeFactory
from world.societies.legend_settlement import SettlementReport
from world.societies.models import LegendEvent
from world.stories.constants import BeatOutcome, BeatPredicateType, EraStatus, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EraFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import StakeContractActivation
from world.stories.services.beats import record_gm_marked_outcome


class OrdinaryLegendCompletionTests(EvenniaTestCase):
    """Ordinary completion has one authoritative, replay-safe Legend seam."""

    @classmethod
    def setUpTestData(cls) -> None:
        EraFactory(status=EraStatus.ACTIVE)
        cls.sheet = CharacterSheetFactory()
        cls.source = LegendSourceTypeFactory()
        consequence = ConsequenceFactory()
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.LEGEND_AWARD,
            legend_base_value=999,
            legend_source_type=cls.source,
            legend_description_template="Authored victory title",
        )
        cls.pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=cls.pool, consequence=consequence)
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=cls.sheet)
        episode = EpisodeFactory(chapter=ChapterFactory(story=story))
        cls.beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            risk=RenownRisk.EXTREME,
            target_level=3,
            success_consequences=cls.pool,
        )
        cls.progress = StoryProgressFactory(story=story, character_sheet=cls.sheet)
        cls.activation = StakeContractActivation.objects.create(
            beat=cls.beat,
            party_average_level=2,
            declared_target_level=3,
            declared_risk=RenownRisk.EXTREME,
            effective_risk=RenownRisk.EXTREME,
            is_ready=True,
        )
        cls.activation.participant_sheets.add(cls.sheet)

    @patch("world.stories.services.legend_settlement.settle_legend_for_activation")
    def test_authored_award_is_reconciled_and_replay_is_idempotent(self, settle) -> None:
        settle.return_value = SettlementReport(minted=True, reason="test")

        completion_count_before = self.beat.completions.count()
        event_count_before = LegendEvent.objects.count()
        completion = record_gm_marked_outcome(
            progress=self.progress,
            beat=self.beat,
            outcome=BeatOutcome.SUCCESS,
        )
        record_gm_marked_outcome(
            progress=self.progress,
            beat=self.beat,
            outcome=BeatOutcome.SUCCESS,
        )

        self.assertEqual(settle.call_count, 1)
        self.assertEqual(LegendEvent.objects.count(), event_count_before)
        self.assertEqual(completion.pk, completion_count_before + 1)
        self.assertEqual(self.activation.participant_sheets.count(), 1)
