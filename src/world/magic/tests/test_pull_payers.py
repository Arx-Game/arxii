"""Each pulled thread is paid by a resonance the player picks for it (#5123)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatPullThread
from world.combat.pull_helpers import build_cast_pull_declaration, resolve_pull_from_kwargs
from world.magic.exceptions import InvalidImbueAmount, PullValidationError
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterResonance
from world.magic.services import preview_resonance_pull, spend_resonance_for_pull
from world.magic.services.threads import pull_resonance_costs
from world.magic.types import PullActionContext
from world.magic.types.pull import CastPullDeclaration


class PullPayerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        CharacterAnimaFactory(character=cls.sheet, current=20, maximum=20)
        cls.fury = ResonanceFactory(name="Fury")
        cls.guile = ResonanceFactory(name="Guile")
        cls.never_held = ResonanceFactory(name="Unheld")
        CharacterResonanceFactory(
            character_sheet=cls.sheet, resonance=cls.fury, balance=10, lifetime_earned=10
        )
        CharacterResonanceFactory(
            character_sheet=cls.sheet, resonance=cls.guile, balance=10, lifetime_earned=10
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        # Both threads lead with Fury; Guile is a resonance held but never imbued in either.
        cls.first = ThreadFactory(owner=cls.sheet, resonance=cls.fury)
        cls.second = ThreadFactory(owner=cls.sheet, resonance=cls.fury)
        ThreadPullEffectFactory(
            target_kind=cls.first.target_kind, resonance=cls.fury, tier=1, flat_bonus_amount=3
        )

    def _ephemeral(self) -> PullActionContext:
        return PullActionContext(
            involved_traits=(self.first.target_trait_id, self.second.target_trait_id)
        )

    def _balance(self, resonance) -> int:
        return CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=resonance
        ).balance

    def test_each_thread_charged_to_its_payer(self) -> None:
        spend_resonance_for_pull(
            self.sheet,
            1,
            [self.first, self.second],
            self._ephemeral(),
            payers={self.second.pk: self.guile},
        )

        self.assertEqual(self._balance(self.fury), 8)
        self.assertEqual(self._balance(self.guile), 8)

    def test_default_payer_is_leading(self) -> None:
        costs = pull_resonance_costs(1, [self.first, self.second])
        declaration = CastPullDeclaration(tier=1, threads=(self.first, self.second))

        spend_resonance_for_pull(self.sheet, 1, [self.first, self.second], self._ephemeral())

        self.assertEqual(costs, {self.fury.pk: 4})
        self.assertEqual(declaration.payer_for(self.first), self.fury)
        self.assertEqual(declaration.resonances, (self.fury,))
        self.assertEqual(self._balance(self.fury), 6)
        self.assertEqual(self._balance(self.guile), 10)

    def test_declaration_resonances_are_the_distinct_payers(self) -> None:
        declaration = CastPullDeclaration(
            tier=1,
            threads=(self.first, self.second),
            payers={self.first.pk: self.guile, self.second.pk: self.guile},
        )

        self.assertEqual(declaration.resonances, (self.guile,))

    def test_payer_without_row_is_charged(self) -> None:
        self.assertFalse(self.first.resonance_rows.filter(resonance=self.guile).exists())

        spend_resonance_for_pull(
            self.sheet, 1, [self.first], self._ephemeral(), payers={self.first.pk: self.guile}
        )

        self.assertEqual(self._balance(self.guile), 8)
        self.assertEqual(self._balance(self.fury), 10)

    def test_burn_must_be_a_payer(self) -> None:
        with self.assertRaises(PullValidationError) as raised:
            spend_resonance_for_pull(
                self.sheet,
                1,
                [self.first],
                self._ephemeral(),
                burn=1,
                burn_resonance=self.guile,
            )

        self.assertEqual(
            raised.exception.user_message,
            "The burn must come from a resonance you are paying with.",
        )
        self.assertEqual(self._balance(self.fury), 10)
        self.assertEqual(self._balance(self.guile), 10)

    def test_burn_from_a_payer_is_charged_with_the_pull(self) -> None:
        spend_resonance_for_pull(
            self.sheet,
            1,
            [self.first],
            self._ephemeral(),
            burn=3,
            burn_resonance=self.guile,
            payers={self.first.pk: self.guile},
        )

        self.assertEqual(self._balance(self.guile), 5)

    def test_combat_pull_records_payer_per_thread(self) -> None:
        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        context = PullActionContext(
            combat_encounter=encounter,
            participant=participant,
            involved_traits=(self.first.target_trait_id, self.second.target_trait_id),
        )

        spend_resonance_for_pull(
            self.sheet,
            1,
            [self.first, self.second],
            context,
            payers={self.second.pk: self.guile},
        )

        recorded = dict(
            CombatPullThread.objects.filter(pull__participant=participant).values_list(
                "thread_id", "paying_resonance_id"
            )
        )
        self.assertEqual(recorded, {self.first.pk: self.fury.pk, self.second.pk: self.guile.pk})

    def test_preview_prices_each_thread_in_every_held_resonance(self) -> None:
        preview = preview_resonance_pull(
            self.sheet, 1, [self.first, self.second], payers={self.second.pk: self.guile}
        )

        self.assertTrue(preview.affordable)
        self.assertEqual(
            [entry.thread_id for entry in preview.per_thread],
            [
                self.first.pk,
                self.second.pk,
            ],
        )
        options = {o.resonance.pk: o for o in preview.per_thread[0].options}
        self.assertEqual(set(options), {self.fury.pk, self.guile.pk})
        self.assertEqual(options[self.guile.pk].cost, 2)
        self.assertEqual(options[self.guile.pk].balance, 10)
        self.assertTrue(options[self.guile.pk].affordable)
        self.assertEqual(options[self.guile.pk].effects, [])

    def test_a_payer_that_cannot_cover_its_threads_is_not_affordable(self) -> None:
        drained = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.guile)
        drained.balance = 1
        drained.save(update_fields=["balance"])

        preview = preview_resonance_pull(
            self.sheet, 1, [self.first], payers={self.first.pk: self.guile}
        )

        self.assertFalse(preview.affordable)
        option = next(o for o in preview.per_thread[0].options if o.resonance.pk == self.guile.pk)
        self.assertFalse(option.affordable)

    def test_declaration_builder_resolves_held_payers_only(self) -> None:
        declaration = build_cast_pull_declaration(
            self.sheet.pk,
            tier=1,
            thread_ids=[self.first.pk],
            payer_ids={self.first.pk: self.guile.pk},
        )

        self.assertEqual(declaration.payer_for(self.first), self.guile)
        with self.assertRaises(InvalidImbueAmount):
            build_cast_pull_declaration(
                self.sheet.pk,
                tier=1,
                thread_ids=[self.first.pk],
                payer_ids={self.first.pk: self.never_held.pk},
            )
        with self.assertRaises(InvalidImbueAmount):
            build_cast_pull_declaration(
                self.sheet.pk,
                tier=1,
                thread_ids=[self.first.pk],
                payer_ids={self.second.pk: self.guile.pk},
            )

    def test_web_kwargs_carry_the_payers_through(self) -> None:
        declaration = resolve_pull_from_kwargs(
            self.sheet,
            {
                "pull_tier": 1,
                "pull_thread_ids": [self.first.pk, self.second.pk],
                "pull_payers": {str(self.second.pk): self.guile.pk},
            },
        )

        self.assertIsNotNone(declaration)
        self.assertEqual(declaration.payer_for(self.first), self.fury)
        self.assertEqual(declaration.payer_for(self.second), self.guile)
