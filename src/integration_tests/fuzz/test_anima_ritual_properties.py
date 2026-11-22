"""Fuzz: the rules of the anima ritual with a partner, as properties (#5280).

The anima ritual is a scene with someone else that grows two resonances in the performer's
aura: a Primal one for how it feels to her, and a Celestial or Abyssal one for how it reaches
the partner. Each class below holds one rule of that design, quoted in the maintainer's words
from the issue, and every example builds its characters and rituals fresh with factories (the
shared catalog lives once in ``setUpTestData``; a Hypothesis test's own ``setUp`` runs outside
any transaction, so it would leak rows between examples).

``_AnimaRitualWorld`` is the shared builder: a performer with an aura split, resonance picks
and a real SCENE_ACTION ritual provisioned through ``provision_player_anima_ritual``; a partner
(player character or story NPC); and a scene they share. Later rules in the same module build
on it.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from evennia.accounts.models import AccountDB
from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from world.character_creation.magic_writer import MagicPicks, WeightedResonance
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ensure_conversion_pairs,
)
from world.magic.models import Resonance, Ritual, RitualCheckConfig
from world.magic.services.anima import provision_player_anima_ritual
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Persona, Scene
from world.skills.factories import SkillFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.factories import StatTraitFactory
from world.traits.services import ensure_canonical_check_outcome

# The resonances a performer may pick from, in the order they are offered to creation: two
# Primal, then one Celestial and one Abyssal. The index is the key a strategy draws.
RESONANCE_KEYS = ("primal 1", "primal 2", "celestial 1", "abyssal 1")


@st.composite
def aura_splits(draw: st.DrawFn) -> tuple[int, int, int]:
    """Celestial / Primal / Abyssal percents of an aura that sum to 100."""
    celestial = draw(st.integers(0, 100))
    primal = draw(st.integers(0, 100 - celestial))
    return celestial, primal, 100 - celestial - primal


class _AnimaRitualWorld:
    """The shared builder for the anima ritual's properties (a mixin for the test classes).

    Everything a property varies (the aura split, the picks, the partner) is built inside the
    example by the methods below; the catalog is written once in ``setUpTestData``.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.celestial, cls.primal, cls.abyssal = ensure_conversion_pairs()
        resonances = {
            key: ResonanceFactory(name=key.title(), affinity=affinity)
            for key, affinity in zip(
                RESONANCE_KEYS,
                (cls.primal, cls.primal, cls.celestial, cls.abyssal),
                strict=True,
            )
        }
        cls.resonances: dict[str, Resonance] = resonances
        cls.outcomes = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        cls.stat = StatTraitFactory(name="willpower")
        cls.skill = SkillFactory()

    def performer(
        self,
        *,
        split: tuple[int, int, int] = (0, 100, 0),
        picks: Sequence[tuple[str, int]] = (),
        anima: int = 10,
    ) -> tuple[CharacterSheet, Ritual]:
        """A performer settled in ``split`` who holds her picks and owns her ritual.

        ``picks`` are ``(resonance key, creation weight)`` pairs in the order creation was
        given them. Each is held (a ``CharacterResonance`` row), and the ritual is written by
        the service creation uses, from the ``MagicPicks`` properties, so what a property
        reads back is what character creation would have written.
        """
        celestial, primal, abyssal = split
        sheet = CharacterSheetFactory()
        CharacterAuraFactory(
            character=sheet,
            celestial=Decimal(celestial),
            primal=Decimal(primal),
            abyssal=Decimal(abyssal),
        )
        CharacterAnimaFactory(character=sheet, current=anima, maximum=10)
        weighted = [WeightedResonance(self.resonances[key], weight) for key, weight in picks]
        for pick in weighted:
            CharacterResonanceFactory(character_sheet=sheet, resonance=pick.resonance)
        account = self.play(sheet)
        magic = self.magic_picks(account, weighted)
        ritual = provision_player_anima_ritual(
            account,
            sheet,
            sheet.roster_entry,
            ritual_name=f"Rite of {sheet.pk}",
            stat=self.stat,
            skill=self.skill,
            primal_resonance=magic.primal_resonance,
            outward_resonance=magic.outward_resonance,
        )
        assert ritual is not None
        return sheet, ritual

    @staticmethod
    def play(sheet: CharacterSheet) -> AccountDB:
        """Seat a player on ``sheet`` (an active tenure) and return their account."""
        entry = RosterEntryFactory(character_sheet=sheet)
        return RosterTenureFactory(roster_entry=entry, end_date=None).player_data.account

    @staticmethod
    def magic_picks(account: AccountDB, resonances: list[WeightedResonance]) -> MagicPicks:
        """Creation's resonance picks as ``MagicPicks`` holds them; nothing else is read."""
        return MagicPicks(
            tradition=None,  # type: ignore[arg-type]  # not read by the pick properties
            gift=None,
            techniques=(),
            resonances=resonances,
            anima_stat=None,
            anima_skill=None,
            ritual_name="",
            account=account,
            origin="",
        )

    def partner(self, kind: str) -> Persona:
        """The partner's persona: ``"pc"`` is held by a player, ``"npc"`` by nobody."""
        sheet = CharacterSheetFactory()
        if kind == "pc":
            self.play(sheet)
        else:
            RosterEntryFactory(character_sheet=sheet)
        return sheet.primary_persona

    @staticmethod
    def scene_with(performer: CharacterSheet, partner: Persona) -> Scene:
        """A live scene the performer and a player partner both stand in."""
        scene = SceneFactory(is_active=True)
        for sheet in (performer, partner.character_sheet):
            tenure = sheet.roster_entry.current_tenure
            if tenure is not None:
                SceneParticipationFactory(scene=scene, account=tenure.player_data.account)
        return scene


class CreationSetsBothPicks(_AnimaRitualWorld, HypothesisTestCase):
    """The ritual is set up once, from the aura, with a Primal pick and an optional outward one."""

    @settings(max_examples=20, deadline=None)
    @given(
        split=aura_splits(),
        weights=st.lists(
            st.one_of(st.none(), st.integers(1, 5)),
            min_size=len(RESONANCE_KEYS),
            max_size=len(RESONANCE_KEYS),
        ),
    )
    def test_creation_writes_the_primal_pick_and_the_optional_outward_pick(
        self, split: tuple[int, int, int], weights: list[int | None]
    ) -> None:
        """Maintainer: "only let them select what they have available from the aura, and it's
        locked in unless the ritual itself changes."

        Given any picks (two Primal, a Celestial and an Abyssal resonance, each picked or not,
        with creation weights) and any aura, the ritual that creation writes carries the
        heaviest Primal pick in its Primal slot and the heaviest Celestial or Abyssal pick in
        its outward slot, or nothing in a slot with no pick. Equal weights go to the pick given
        first.
        """
        picks = [(key, w) for key, w in zip(RESONANCE_KEYS, weights, strict=True) if w]
        _sheet, ritual = self.performer(split=split, picks=picks)

        config = RitualCheckConfig.objects.get(ritual=ritual)

        def heaviest(wanted: Sequence[str]) -> Resonance | None:
            chosen = [(key, w) for key, w in picks if key in wanted]
            if not chosen:
                return None
            return self.resonances[max(chosen, key=lambda pair: pair[1])[0]]

        self.assertEqual(config.primal_resonance, heaviest(("primal 1", "primal 2")))
        self.assertEqual(config.outward_resonance, heaviest(("celestial 1", "abyssal 1")))
