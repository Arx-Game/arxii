"""Settlement rules for Legend (#3463, ADR-0249).

Deliberately tests ``world.societies.legend_settlement`` directly rather than
through a stakes contract: the seam is system-agnostic on purpose (societies
must not import stories, ADR-0010), so its rules are testable without building
a beat, an episode and a chapter to reach them. The stories-side extraction
gets its own coverage.

Every case here traces to a ruling, and the docstrings say which — these are
the game's design decisions expressed as assertions, so a future change that
breaks one should have to argue with the ruling, not just re-record a number.
"""

from __future__ import annotations

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.societies.constants import RenownRisk
from world.societies.factories import LegendSourceTypeFactory
from world.societies.legend_settlement import (
    SettlementParticipant,
    settle_legend_for,
    settle_standouts_only,
    station_for,
    station_multiplier,
)


class StationTests(TestCase):
    """Station is min(what you are, what you faced) — Tehom, 2026-08-29."""

    def test_the_four_ruled_cases(self) -> None:
        """The exact four cases the rule was stated with.

        "someone who is level 1 beating a level 2 does not earn as much as a
        level 2 beating a level 2, but both the level 1 and the level 2 earn
        the same for beating a level 1 (meaning that it's inconsequential for
        the level 2)."
        """
        assert station_for(1, 2) == 1, "level 1 vs level 2 threat caps at its own station"
        assert station_for(2, 2) == 2, "level 2 vs level 2 earns the full rate"
        assert station_for(1, 1) == 1, "baseline"
        assert station_for(2, 1) == 1, "slumming pays the level-1 rate, not the level-2 one"
        assert station_for(1, 2) < station_for(2, 2), "you cannot bank above your station"
        assert station_for(2, 1) == station_for(1, 1), "you cannot bank by slumming"

    def test_station_is_never_negative(self) -> None:
        assert station_for(-3, 5) == 0
        assert station_multiplier(-1) == 0


class PerilFloorTests(TestCase):
    """Safe play earns ZERO, not less — and the floor is per person."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.source_type = LegendSourceTypeFactory()

    def _participant(self, level: int, risk: str) -> SettlementParticipant:
        return SettlementParticipant(
            persona=PersonaFactory(),
            level=level,
            personal_risk=risk,
        )

    def test_below_floor_mints_nothing_at_all(self) -> None:
        """Not a reduced award. Zero. "It should be impossible, not slow"."""
        report = settle_legend_for(
            effective_risk=RenownRisk.MODERATE,
            target_level=5,
            held_fraction=1.0,
            participants=[self._participant(5, RenownRisk.MODERATE)],
            source_type=self.source_type,
            title="A safe afternoon",
        )
        assert report.minted is False
        assert report.entries == []
        assert "personally at risk" in report.reason

    def test_the_untouchable_hero_earns_nothing_from_a_lethal_scene(self) -> None:
        """The case Tehom raised: a level-10 obliterating level-1 mooks.

        The mooks are genuinely EXTREME — to a level 1. The hero was never in
        danger and earns nothing, however real the danger was to everyone else.
        Personal risk is table stakes.
        """
        endangered = self._participant(1, RenownRisk.EXTREME)
        untouchable = self._participant(10, RenownRisk.NONE)
        report = settle_legend_for(
            effective_risk=RenownRisk.EXTREME,
            target_level=1,
            held_fraction=1.0,
            participants=[endangered, untouchable],
            source_type=self.source_type,
            title="The rout of the mooks",
        )
        assert report.minted is True
        earners = {entry.persona_id for entry in report.entries}
        assert endangered.persona.pk in earners
        assert untouchable.persona.pk not in earners, (
            "a participant who was never personally in danger must earn nothing"
        )

    def test_nobody_at_risk_mints_nothing(self) -> None:
        report = settle_legend_for(
            effective_risk=RenownRisk.EXTREME,
            target_level=1,
            held_fraction=1.0,
            participants=[self._participant(10, RenownRisk.NONE)],
            source_type=self.source_type,
            title="A walkover",
        )
        assert report.minted is False


class OutcomeShareTests(TestCase):
    """Beat the monsters, lose the town: you are paid for the monsters."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.source_type = LegendSourceTypeFactory()

    def _settle(self, held: float):
        return settle_legend_for(
            effective_risk=RenownRisk.EXTREME,
            target_level=3,
            held_fraction=held,
            participants=[
                SettlementParticipant(
                    persona=PersonaFactory(),
                    level=3,
                    personal_risk=RenownRisk.EXTREME,
                )
            ],
            source_type=self.source_type,
            title="The defence of the town",
        )

    def test_a_partial_hold_pays_a_partial_share(self) -> None:
        full = self._settle(1.0)
        half = self._settle(0.5)
        assert full.minted
        assert half.minted
        assert half.entries[0].base_value < full.entries[0].base_value
        assert half.entries[0].base_value == round(full.entries[0].base_value * 0.5)

    def test_holding_nothing_mints_no_shared_deed(self) -> None:
        report = self._settle(0.0)
        assert report.minted is False


class UntunedBaseValueTests(TestCase):
    """A deed's worth as a story does not depend on who did it."""

    def test_same_tale_same_value_different_station(self) -> None:
        """Tehom: store base values pre-tuning so retuning needs no recompute.

        Both survived the same level-5 threat, so the tale is worth the same.
        Station differs, and is what the advancement gate multiplies by on read.
        """
        source_type = LegendSourceTypeFactory()
        low = SettlementParticipant(
            persona=PersonaFactory(), level=1, personal_risk=RenownRisk.EXTREME
        )
        high = SettlementParticipant(
            persona=PersonaFactory(), level=5, personal_risk=RenownRisk.EXTREME
        )
        report = settle_legend_for(
            effective_risk=RenownRisk.EXTREME,
            target_level=5,
            held_fraction=1.0,
            participants=[low, high],
            source_type=source_type,
            title="They held the pass",
        )
        assert report.minted is True
        by_persona = {e.persona_id: e for e in report.entries}
        low_entry = by_persona[low.persona.pk]
        high_entry = by_persona[high.persona.pk]

        assert low_entry.base_value == high_entry.base_value, (
            "the tale is worth the same whoever tells it"
        )
        assert low_entry.earned_at_level == 1
        assert high_entry.earned_at_level == 5
        # What differs is what it advances THEM by, derived on read.
        assert station_multiplier(high_entry.earned_at_level) > station_multiplier(
            low_entry.earned_at_level
        )


class StandoutTests(TestCase):
    """Brilliance in defeat is still a story worth telling — ADR-0122, generalized."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.source_type = LegendSourceTypeFactory()

    def test_a_lost_unit_still_pays_a_standout(self) -> None:
        brilliant = SettlementParticipant(
            persona=PersonaFactory(),
            level=4,
            personal_risk=RenownRisk.EXTREME,
            crucial_success_level=9,
        )
        report = settle_standouts_only(
            effective_risk=RenownRisk.EXTREME,
            target_level=4,
            participants=[brilliant],
            source_type=self.source_type,
            title="The bridge was lost",
        )
        assert report.minted is True
        assert len(report.standouts) == 1
        assert report.standouts[0].earned_at_level == 4

    def test_a_standout_who_was_never_in_danger_pays_nothing(self) -> None:
        """The per-person filter applies to the standout pass too."""
        safe = SettlementParticipant(
            persona=PersonaFactory(),
            level=20,
            personal_risk=RenownRisk.NONE,
            crucial_success_level=10,
        )
        report = settle_standouts_only(
            effective_risk=RenownRisk.EXTREME,
            target_level=1,
            participants=[safe],
            source_type=self.source_type,
            title="A flourish over corpses",
        )
        assert report.minted is False

    def test_a_merely_competent_contribution_is_not_a_standout(self) -> None:
        ordinary = SettlementParticipant(
            persona=PersonaFactory(),
            level=4,
            personal_risk=RenownRisk.EXTREME,
            crucial_success_level=1,
        )
        report = settle_standouts_only(
            effective_risk=RenownRisk.EXTREME,
            target_level=4,
            participants=[ordinary],
            source_type=self.source_type,
            title="A day at the front",
        )
        assert report.minted is False


class StandoutDeedsAnchorToTheirEvent(TestCase):
    """#3466: a standout must know the event that priced it, or it has no honor ceiling."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.source_type = LegendSourceTypeFactory()

    def _settle_with_one_standout(self):
        """A won unit whose shared deed mints alongside a separate standout.

        ``paid`` (personal_risk=EXTREME) clears the shared-deed peril floor at
        the party's low ``effective_risk`` (MODERATE, below the HIGH floor) and
        is paid the shared deed. ``standout`` relies on the low
        ``effective_risk`` for its own peril check (``personal_risk=None``), so
        it is excluded from the shared payout, but still clears the standout
        pass's own bar (crucial_success_level >= the standout threshold) and
        mints a solo deed anchored to the same event.
        """
        paid = SettlementParticipant(
            persona=PersonaFactory(),
            level=3,
            personal_risk=RenownRisk.EXTREME,
        )
        standout = SettlementParticipant(
            persona=PersonaFactory(),
            level=3,
            crucial_success_level=9,
        )
        return settle_legend_for(
            effective_risk=RenownRisk.MODERATE,
            target_level=3,
            held_fraction=1.0,
            participants=[paid, standout],
            source_type=self.source_type,
            title="The stand at the ford",
        )

    def test_standout_carries_the_event(self) -> None:
        report = self._settle_with_one_standout()
        assert report.standouts, "expected a standout deed"
        assert report.standouts[0].event_id == report.event.pk
