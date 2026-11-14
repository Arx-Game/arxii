"""Character creation with several weighted resonances (#5123).

A player picks resonances in the Gift stage and spreads ``DriftConfig.creation_points``
across them. Finalize seeds each pick's lifetime from its weight (no balance), the aura and
the settled self both come from the weights, the Gift thread holds the picks at zero with
the heaviest leading, and the codex grants an entry for every pick.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework import serializers

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.serializers import CharacterDraftSerializer
from world.character_creation.services import finalize_magic_data
from world.character_creation.validators import compute_magic_errors
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.magic.constants import GainSource, GiftKind, GlimpseTagAxis, TargetKind
from world.magic.factories import (
    GiftFactory,
    GlimpseTagFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    ensure_canonical_affinities,
)
from world.magic.models import CharacterAura, CharacterResonance, ResonanceGrant, Thread
from world.magic.models.ritual_check_config import RitualCheckConfig
from world.magic.seeds_cast import get_standalone_cast_template
from world.magic.services.drift import drift_for
from world.magic.services.resonance import grant_resonance
from world.roster.factories import RosterEntryFactory
from world.skills.factories import SkillFactory
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory
from world.traits.factories import StatTraitFactory


def _weights(*picks) -> list[dict[str, int]]:
    """``gift_resonance_weights`` for ``(resonance, weight)`` pairs, in the order given."""
    return [{"resonance_id": resonance.pk, "weight": weight} for resonance, weight in picks]


class _WeightedPicksCase(TestCase):
    """Fury 6 and Wonder 1 (Primal), Domination 3 (Abyssal): spread over ten points."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial, cls.primal, cls.abyssal = ensure_canonical_affinities()
        cls.fury = ResonanceFactory(name="Fury", affinity=cls.primal)
        cls.wonder = ResonanceFactory(name="Wonder", affinity=cls.primal)
        cls.domination = ResonanceFactory(name="Domination", affinity=cls.abyssal)
        cls.tradition = TraditionFactory()
        # An unrestricted gift: its supported set is empty, so every pick is held.
        cls.gift = GiftFactory(name="Many Moods")
        cls.technique = TechniqueFactory(
            gift=cls.gift, action_template=get_standalone_cast_template()
        )
        cls.stat = StatTraitFactory(name="Focus")
        cls.skill = SkillFactory()

    def _draft(self, picks=None, **extra):
        picks = (
            picks if picks is not None else [(self.fury, 6), (self.wonder, 1), (self.domination, 3)]
        )
        draft_data = {
            "selected_gift_id": self.gift.pk,
            "selected_technique_ids": [self.technique.pk],
            "gift_resonance_weights": _weights(*picks),
            "anima_check_stat_id": self.stat.pk,
            "anima_check_skill_id": self.skill.pk,
            **extra,
        }
        return CharacterDraftFactory(
            account=AccountFactory(), draft_data=draft_data, selected_tradition=self.tradition
        )

    def _finalize(self, picks=None, *, species=None, **extra):
        sheet = CharacterSheetFactory(species=species)
        RosterEntryFactory(character_sheet=sheet)
        draft = self._draft(picks, **extra)
        finalize_magic_data(draft, sheet)
        return sheet, draft


class FinalizeWritesTheWeightedPicks(_WeightedPicksCase):
    def test_finalize_writes_one_character_resonance_per_pick(self) -> None:
        sheet, _ = self._finalize()
        lifetime = {
            row.resonance_id: row.lifetime_earned
            for row in CharacterResonance.objects.filter(character_sheet=sheet)
        }
        # creation_seed_per_point is 10: a weight of 6 seeds 60 lifetime.
        self.assertEqual(lifetime, {self.fury.pk: 60, self.wonder.pk: 10, self.domination.pk: 30})

    def test_no_balance_granted_by_seed(self) -> None:
        sheet, _ = self._finalize()
        rows = CharacterResonance.objects.filter(character_sheet=sheet)
        self.assertEqual(rows.count(), 3)
        self.assertEqual([row.balance for row in rows], [0, 0, 0])
        ledger = ResonanceGrant.objects.filter(character_sheet=sheet)
        self.assertEqual({grant.source for grant in ledger}, {GainSource.CHARACTER_CREATION})
        self.assertEqual(
            {grant.resonance_id: grant.amount for grant in ledger},
            {self.fury.pk: 60, self.wonder.pk: 10, self.domination.pk: 30},
        )

    def test_codex_granted_for_every_pick(self) -> None:
        entries = {}
        for resonance in (self.fury, self.wonder, self.domination):
            entries[resonance.pk] = CodexEntryFactory(name=f"{resonance.name} lore")
            resonance.codex_entry = entries[resonance.pk]
            resonance.save()
        sheet, _ = self._finalize()
        known = CharacterCodexKnowledge.objects.filter(
            roster_entry=sheet.roster_entry, status=CodexKnowledgeStatus.KNOWN
        )
        self.assertEqual({row.entry_id for row in known}, {entry.pk for entry in entries.values()})

    def test_anima_ritual_carries_the_heaviest_pick(self) -> None:
        _, draft = self._finalize([(self.wonder, 2), (self.domination, 5), (self.fury, 3)])
        config = RitualCheckConfig.objects.get(ritual__author_account=draft.account)
        self.assertEqual(config.resonance, self.domination)


class TheStartingAuraComesFromTheWeights(_WeightedPicksCase):
    def test_starting_aura_matches_weights(self) -> None:
        sheet, _ = self._finalize()
        aura = CharacterAura.objects.get(character=sheet)
        self.assertEqual(aura.percent_for(self.primal), Decimal("70.00"))
        self.assertEqual(aura.percent_for(self.abyssal), Decimal("30.00"))
        self.assertEqual(aura.percent_for(self.celestial), Decimal(0))

    def test_settled_equals_starting_aura(self) -> None:
        sheet, _ = self._finalize()
        aura = CharacterAura.objects.get(character=sheet)
        shares = {row.affinity_id: (row.percent, row.settled_percent) for row in aura.shares.all()}
        self.assertEqual(
            shares,
            {
                self.primal.pk: (Decimal("70.00"), Decimal("70.00")),
                self.abyssal.pk: (Decimal("30.00"), Decimal("30.00")),
            },
        )
        self.assertEqual(drift_for(sheet).steps_past, 0)

    def test_first_gain_extends_not_wipes_aura(self) -> None:
        sheet, _ = self._finalize()
        grant_resonance(sheet, self.domination, 3, source=GainSource.STAFF_GRANT)
        aura = CharacterAura.objects.get(character=sheet)
        # 100 seeded plus 3 earned: the streak grew a little, the aura was not replaced.
        self.assertEqual(aura.percent_for(self.primal), Decimal("67.96"))
        self.assertEqual(aura.percent_for(self.abyssal), Decimal("32.04"))
        reading = drift_for(sheet)
        self.assertEqual(reading.steps_past, 0)
        self.assertEqual(reading.main_affinity, self.primal)

    def test_two_glimpse_tags_on_one_affinity_leave_a_fresh_character_settled(self) -> None:
        """A TONE and a TRIGGER tag both Primal nudge the settled self by 6 in all.

        The seed follows the nudged settled shares, so the aura and who she is agree and
        she is not unsettled before she has cast (nor after a small minor-affinity gain).
        """
        tags = [
            GlimpseTagFactory(axis=GlimpseTagAxis.TONE, slug="warm-tone", affinity=self.primal),
            GlimpseTagFactory(
                axis=GlimpseTagAxis.TRIGGER, slug="warm-trigger", affinity=self.primal
            ),
        ]
        sheet, _ = self._finalize(
            [(self.fury, 7), (self.domination, 3)], glimpse_tag_ids=[tag.pk for tag in tags]
        )
        aura = CharacterAura.objects.get(character=sheet)
        settled = {row.affinity_id: row.settled_percent for row in aura.shares.all()}
        self.assertEqual(
            settled, {self.primal.pk: Decimal("76.00"), self.abyssal.pk: Decimal("24.00")}
        )
        self.assertEqual(aura.percent_for(self.primal), Decimal("76.00"))
        self.assertEqual(drift_for(sheet).steps_past, 0)
        grant_resonance(sheet, self.domination, 3, source=GainSource.STAFF_GRANT)
        self.assertEqual(drift_for(sheet).steps_past, 0)

    def test_one_affinity_picks_start_wholly_in_it(self) -> None:
        sheet, _ = self._finalize([(self.domination, 10)])
        aura = CharacterAura.objects.get(character=sheet)
        self.assertEqual(aura.percent_for(self.abyssal), Decimal("100.00"))
        self.assertEqual(drift_for(sheet).steps_past, 0)


class TheGiftThreadHoldsThePicksAtZero(_WeightedPicksCase):
    def test_gift_thread_rows_at_zero_heaviest_leads(self) -> None:
        # Given lightest first: the thread still leads with the heaviest pick.
        sheet, _ = self._finalize([(self.wonder, 1), (self.domination, 3), (self.fury, 6)])
        thread = Thread.objects.get(owner=sheet, target_kind=TargetKind.GIFT, target_gift=self.gift)
        rows = list(thread.resonance_rows.all())
        self.assertEqual(
            [(row.resonance_id, row.amount) for row in rows],
            [(self.fury.pk, 0), (self.domination.pk, 0), (self.wonder.pk, 0)],
        )
        self.assertEqual(thread.resonance, self.fury)

    def test_species_gift_thread_holds_the_same_picks(self) -> None:
        species = SpeciesFactory(name="Many Moods Folk")
        minor = GiftFactory(name="Folk Gift", kind=GiftKind.MINOR)
        SpeciesGiftGrantFactory(species=species, gift=minor, drawback_condition=None)
        sheet, _ = self._finalize(species=species)
        thread = Thread.objects.get(owner=sheet, target_kind=TargetKind.GIFT, target_gift=minor)
        self.assertEqual(
            [row.resonance_id for row in thread.resonance_rows.all()],
            [self.fury.pk, self.domination.pk, self.wonder.pk],
        )
        self.assertEqual(thread.resonance, self.fury)


class TheGiftStageChecksTheSpread(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_canonical_affinities()
        cls.path = PathFactory()
        cls.tradition = TraditionFactory()
        cls.gift = GiftFactory(name="Shadow Majesty")
        cls.technique = TechniqueFactory(
            gift=cls.gift, action_template=get_standalone_cast_template()
        )
        PathGiftGrantFactory(path=cls.path, gift=cls.gift).starter_techniques.set([cls.technique])
        cls.first = ResonanceFactory()
        cls.second = ResonanceFactory()
        cls.stat = StatTraitFactory(name="Focus")
        cls.skill = SkillFactory()

    def _errors(self, weights) -> list[str]:
        draft = CharacterDraftFactory(
            selected_path=self.path,
            selected_tradition=self.tradition,
            draft_data={
                "selected_gift_id": self.gift.pk,
                "selected_technique_ids": [self.technique.pk],
                "gift_resonance_weights": weights,
                "anima_check_stat_id": self.stat.pk,
                "anima_check_skill_id": self.skill.pk,
            },
        )
        return compute_magic_errors(draft)

    def test_weights_must_sum_to_creation_points(self) -> None:
        self.assertEqual(self._errors(_weights((self.first, 6), (self.second, 4))), [])
        self.assertEqual(self._errors(_weights((self.first, 10))), [])
        spread = ["Spread exactly 10 points across your resonances"]
        self.assertEqual(self._errors(_weights((self.first, 6), (self.second, 3))), spread)
        # More than the points is not "exactly": it says how many there are to spend.
        over = ["You have only 10 points to spread across your resonances"]
        self.assertEqual(self._errors(_weights((self.first, 6), (self.second, 5))), over)

    def test_a_draft_saves_a_partial_spread_but_the_stage_stays_incomplete(self) -> None:
        partial = _weights((self.first, 6), (self.second, 3))
        check = CharacterDraftSerializer._validate_gift_resonance_weights

        check({"gift_resonance_weights": partial})  # saves: nothing raised

        self.assertEqual(self._errors(partial), ["Spread exactly 10 points across your resonances"])

    def test_a_draft_refuses_an_overspend_in_the_over_spend_wording(self) -> None:
        check = CharacterDraftSerializer._validate_gift_resonance_weights

        with self.assertRaises(serializers.ValidationError) as caught:
            check({"gift_resonance_weights": _weights((self.first, 6), (self.second, 5))})

        self.assertEqual(
            caught.exception.detail["gift_resonance_weights"],
            "You have only 10 points to spread across your resonances",
        )

    def test_each_pick_needs_a_point_and_a_resonance_once(self) -> None:
        self.assertEqual(
            self._errors(_weights((self.first, 10), (self.second, 0))),
            ["Give every resonance you pick at least 1 point"],
        )
        self.assertEqual(
            self._errors(_weights((self.first, 5), (self.first, 5))),
            ["Pick each resonance once"],
        )

    def test_no_picks_and_unreadable_picks_are_refused(self) -> None:
        self.assertEqual(self._errors(None), ["Select a gift resonance"])
        self.assertEqual(self._errors([]), ["Select a gift resonance"])
        self.assertEqual(
            self._errors([{"resonance_id": self.first.pk, "weight": "10"}]),
            ["Your resonance picks are not readable"],
        )
        self.assertEqual(
            self._errors([{"resonance_id": 0, "weight": 10}]), ["Select a gift resonance"]
        )
