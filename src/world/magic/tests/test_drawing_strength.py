"""A pull paid by a kindled resonance reads the thread higher (#5124, drawing strength)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatPullThread
from world.magic.constants import KindlingSource
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    KindledStrengthTierFactory,
    KindlingFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import KindledStrengthTier
from world.magic.serializers import PayerOptionSerializer
from world.magic.services import preview_resonance_pull, spend_resonance_for_pull
from world.magic.types import PullActionContext


class DrawingStrengthTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=cls.sheet, current=20, maximum=20)
        cls.fury = ResonanceFactory(name="Fury")
        cls.guile = ResonanceFactory(name="Guile")
        for resonance in (cls.fury, cls.guile):
            CharacterResonanceFactory(
                character_sheet=cls.sheet, resonance=resonance, balance=10, lifetime_earned=10
            )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        # Staff name the strength; code reads only its rank and what it adds to a pull.
        cls.blazing = KindledStrengthTierFactory(rank=2, name="Blazing", pull_levels=20)
        cls.fury_thread = ThreadFactory(owner=cls.sheet, resonance=cls.fury, level=0)
        cls.guile_thread = ThreadFactory(owner=cls.sheet, resonance=cls.guile, level=0)
        for thread, resonance in ((cls.fury_thread, cls.fury), (cls.guile_thread, cls.guile)):
            ThreadPullEffectFactory(
                target_kind=thread.target_kind, resonance=resonance, tier=1, flat_bonus_amount=3
            )
        # A faint strength whose few levels would read the thread LOWER (a level-5 read is
        # worth less than level 0's floor), so it must change nothing.
        cls.faint = KindledStrengthTierFactory(rank=1, name="Faint", pull_levels=5)
        cls.mirth = ResonanceFactory(name="Mirth")
        CharacterResonanceFactory(
            character_sheet=cls.sheet, resonance=cls.mirth, balance=10, lifetime_earned=10
        )
        cls.mirth_thread = ThreadFactory(owner=cls.sheet, resonance=cls.mirth, level=0)
        ThreadPullEffectFactory(
            target_kind=cls.mirth_thread.target_kind,
            resonance=cls.mirth,
            tier=1,
            flat_bonus_amount=3,
        )
        cls.encounter = CombatEncounterFactory(round_number=1)
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter, character_sheet=cls.sheet
        )
        # The GM has kindled Fury for this fight; Guile is not kindled.
        KindlingFactory(
            character_sheet=cls.sheet,
            resonance=cls.fury,
            strength=2,
            source=KindlingSource.GM,
            encounter=cls.encounter,
        )
        KindlingFactory(
            character_sheet=cls.sheet,
            resonance=cls.mirth,
            strength=1,
            source=KindlingSource.GM,
            encounter=cls.encounter,
        )

    def _combat_context(self) -> PullActionContext:
        return PullActionContext(
            combat_encounter=self.encounter,
            participant=self.participant,
            involved_traits=tuple(
                t.target_trait_id for t in (self.fury_thread, self.guile_thread, self.mirth_thread)
            ),
        )

    def test_a_kindled_payer_reads_the_thread_higher_and_an_unkindled_one_does_not(self) -> None:
        result = spend_resonance_for_pull(
            self.sheet, 1, [self.fury_thread, self.guile_thread], self._combat_context()
        )

        by_thread = {e.source_thread.pk: e for e in result.resolved_effects}
        # Both threads are level 0 (a multiplier of 1). Fury's strength reads 20 levels higher
        # (a multiplier of 2); the thread's own reported level never moves.
        self.assertEqual(by_thread[self.fury_thread.pk].scaled_value, 6)
        self.assertEqual(by_thread[self.guile_thread.pk].scaled_value, 3)
        self.assertEqual(by_thread[self.fury_thread.pk].source_thread_level, 0)
        self.fury_thread.refresh_from_db()
        self.assertEqual(self.fury_thread.level, 0)

    def test_the_combat_pull_records_the_strength_rank_it_drew_with(self) -> None:
        spend_resonance_for_pull(
            self.sheet, 1, [self.fury_thread, self.guile_thread], self._combat_context()
        )

        recorded = dict(
            CombatPullThread.objects.filter(pull__participant=self.participant).values_list(
                "thread_id", "kindled_strength"
            )
        )
        self.assertEqual(recorded, {self.fury_thread.pk: 2, self.guile_thread.pk: 0})

    def test_the_preview_shows_the_kindled_payers_perks_and_names_its_strength(self) -> None:
        preview = preview_resonance_pull(self.sheet, 1, [self.fury_thread])

        options = {o.resonance.pk: o for o in preview.per_thread[0].options}
        fury, guile = options[self.fury.pk], options[self.guile.pk]
        self.assertEqual([e.scaled_value for e in fury.effects], [6])
        self.assertEqual([e.scaled_value for e in preview.resolved_effects], [6])
        data = PayerOptionSerializer(fury).data
        self.assertEqual(data["kindled_strength"], "Blazing")
        self.assertEqual(data["level_read"], 0)
        self.assertIsNone(PayerOptionSerializer(guile).data["kindled_strength"])

    def test_a_strength_that_would_read_the_thread_lower_changes_nothing(self) -> None:
        preview = preview_resonance_pull(self.sheet, 1, [self.mirth_thread])

        option = next(o for o in preview.per_thread[0].options if o.resonance.pk == self.mirth.pk)
        # Kindled (it is named), yet a level-0 thread's +5 would drop the multiplier to 0.5.
        self.assertEqual(PayerOptionSerializer(option).data["kindled_strength"], "Faint")
        self.assertEqual([e.scaled_value for e in option.effects], [3])

    def test_a_kindling_whose_strength_has_no_row_gives_no_boost(self) -> None:
        KindledStrengthTier.objects.filter(rank=2).delete()

        preview = preview_resonance_pull(self.sheet, 1, [self.fury_thread])

        option = next(o for o in preview.per_thread[0].options if o.resonance.pk == self.fury.pk)
        self.assertIsNone(PayerOptionSerializer(option).data["kindled_strength"])
        self.assertEqual([e.scaled_value for e in option.effects], [3])

    def test_the_boost_stacks_with_the_beseech_boost(self) -> None:
        result = spend_resonance_for_pull(
            self.sheet,
            1,
            [self.fury_thread],
            self._combat_context(),
            beseech_bonus_thread_id=self.fury_thread.pk,
            beseech_bonus=10,
        )

        # Level 0 + 10 (beseech) + 20 (kindled) reads as 30: a multiplier of 3.
        self.assertEqual([e.scaled_value for e in result.resolved_effects], [9])
