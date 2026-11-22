"""Fuzz: the rules of the anima ritual with a partner, as properties (#5280).

The anima ritual is a scene with someone else that grows two resonances in the performer's
aura: a Primal one for how it feels to her, and a Celestial or Abyssal one for how it reaches
the partner. Each class below holds one rule of that design, quoted in the maintainer's words
from the issue, and every example builds its characters and rituals fresh with factories (the
shared catalog lives once in ``setUpTestData``; a Hypothesis test's own ``setUp`` runs outside
any transaction, so it would leak rows between examples).

``_AnimaRitualWorld`` is the shared builder: a performer with an aura split, resonance picks
and a real SCENE_ACTION ritual provisioned through ``provision_player_anima_ritual``; a partner
(player character or story NPC, run by nobody, a player borrower, a GM or the scene's GM); and
a scene they share, in a room both stand in. Later rules in the same module build on it.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from django.core.exceptions import ValidationError
from evennia.accounts.models import AccountDB
from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase

from actions.definitions.ritual import PerformRitualAction
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_creation.magic_writer import MagicPicks, WeightedResonance
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.test_helpers import force_check_outcome
from world.gm.factories import GMProfileFactory
from world.magic.exceptions import CharacterEngagedForRitual
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    ensure_conversion_pairs,
)
from world.magic.models import (
    AnimaRitualPerformance,
    CharacterAnima,
    Resonance,
    Ritual,
    RitualCheckConfig,
)
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.magic.services.anima import provision_player_anima_ritual
from world.magic.services.anima_ritual_action import start_partner_ritual
from world.mechanics.factories import CharacterEngagementFactory
from world.roster.constants import NPCLoanStatus
from world.roster.factories import (
    NPCLoanFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models.choices import RosterType
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
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
        """Seat a player on ``sheet`` (an active tenure, the account on the character as a
        logged-in puppet has it) and return their account."""
        entry = RosterEntryFactory(character_sheet=sheet)
        account = RosterTenureFactory(roster_entry=entry, end_date=None).player_data.account
        sheet.character.db_account = account
        sheet.character.save(update_fields=["db_account"])
        return account

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

    @staticmethod
    def partner(control: str) -> Persona:
        """The partner's persona, by who writes its part.

        ``"pc"`` is a player character a player holds. The rest are story NPCs (on the NPC
        shelf): ``"nobody"`` plays it, ``"player borrower"`` is a lent NPC a player with no GM
        profile now plays, ``"gm holder"`` is held by an account with a GM profile, and
        ``"scene gm"`` has no player of its own (the scene's GM is built by ``scene_with``).
        """
        sheet = CharacterSheetFactory()
        if control == "pc":
            _AnimaRitualWorld.play(sheet)
            return sheet.primary_persona
        npc_shelf = RosterFactory(roster_type=RosterType.NPC)
        entry = RosterEntryFactory(character_sheet=sheet, roster=npc_shelf)
        if control == "player borrower":
            NPCLoanFactory(roster_entry=entry, status=NPCLoanStatus.ACTIVE)
        elif control == "gm holder":
            tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
            GMProfileFactory(account=tenure.player_data.account)
        return sheet.primary_persona

    @staticmethod
    def scene_with(*sheets: CharacterSheet, gm: bool = False) -> Scene:
        """A live scene in a room every one of ``sheets`` stands in, so each is "in this scene,
        in the same place". A held character takes part under their account; ``gm`` adds a third
        account who is the scene's GM."""
        room = RoomProfileFactory()
        scene = SceneFactory(location=room, is_active=True)
        for sheet in sheets:
            sheet.character.location = room.objectdb
            tenure = sheet.roster_entry.current_tenure
            if tenure is not None:
                SceneParticipationFactory(scene=scene, account=tenure.player_data.account)
        if gm:
            SceneParticipationFactory(scene=scene, account=AccountFactory(), is_gm=True)
        invalidate_active_scene_cache(room.objectdb)
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


def anima_of(sheet: CharacterSheet) -> int:
    """The anima the database holds (``refresh_from_db`` is a no-op on idmapper rows)."""
    return CharacterAnima.objects.filter(character=sheet).values_list("current", flat=True).get()


class _RitualGates(_AnimaRitualWorld, HypothesisTestCase):
    """The anima budget of every tier is authored, so a ritual that ran would restore anima."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        for outcome in cls.outcomes.values():
            AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=4)


class NeverAlone(_RitualGates):
    """The ritual is done with somebody, on every door."""

    @settings(max_examples=20, deadline=None)
    @given(
        door=st.sampled_from(("the action", "no partner", "her own persona")),
        tier=st.sampled_from(sorted(CANONICAL_OUTCOME_LEVELS)),
        anima=st.integers(0, 10),
    )
    def test_a_ritual_with_nobody_else_never_restores_anima(
        self, door: str, tier: str, anima: int
    ) -> None:
        """Maintainer: "Anima ritual can NEVER be done alone. Hard requirement to involve other
        people."

        Given the ritual started through each door (the action the Rituals page and the ritual's
        own name reach, a request naming no partner, a request naming her own persona), any
        outcome the dice could land on and any starting anima, her anima is exactly what it was,
        no performance row exists, and she is told to name someone else.
        """
        sheet, ritual = self.performer(anima=anima)
        scene = self.scene_with(sheet)
        refusal = "Name someone else to take part in your ritual."

        with force_check_outcome(self.outcomes[tier]):
            if door == "the action":
                told = PerformRitualAction().run(actor=sheet.character, ritual=ritual).message
            else:
                target = None if door == "no partner" else sheet.primary_persona
                with self.assertRaises(ValidationError) as refused:
                    start_partner_ritual(
                        scene=scene, initiator_persona=sheet.primary_persona, target_persona=target
                    )
                told = " ".join(refused.exception.messages)

        self.assertEqual(told, refusal)
        self.assertEqual(anima_of(sheet), anima)
        self.assertFalse(AnimaRitualPerformance.objects.filter(ritual=ritual).exists())


class NpcPartners(_RitualGates):
    """An NPC partner needs somebody writing its part."""

    @settings(max_examples=20, deadline=None)
    @given(control=st.sampled_from(("nobody", "player borrower", "gm holder", "scene gm")))
    def test_an_npc_partner_is_refused_unless_a_gm_runs_it_or_the_scene(self, control: str) -> None:
        """Maintainer: "GM has control of NPC or is GMing the scene. Basically if an NPC's
        reactions are not being written by a GM ... it isn't an appropriate target."

        Given a story NPC played by nobody, by a player who borrowed it, by an account with a GM
        profile, or played by nobody in a scene a third account GMs, asking it to take part is
        refused with "Nobody is playing that character." exactly when nobody plays it or only a
        player does; otherwise the request is resolved at once, with no one asked for consent.
        """
        # Starting at 0 of 10 anima, a Success's budget of 4 must raise it to exactly 4.
        sheet, ritual = self.performer(anima=0)
        partner = self.partner(control)
        scene = self.scene_with(sheet, partner.character_sheet, gm=control == "scene gm")

        with force_check_outcome(self.outcomes["Success"]):
            if control in ("nobody", "player borrower"):
                with self.assertRaises(ValidationError) as refused:
                    start_partner_ritual(
                        scene=scene,
                        initiator_persona=sheet.primary_persona,
                        target_persona=partner,
                    )
                self.assertEqual(refused.exception.messages, ["Nobody is playing that character."])
                self.assertFalse(SceneActionRequest.objects.filter(scene=scene).exists())
                self.assertEqual(anima_of(sheet), 0)
            else:
                request = start_partner_ritual(
                    scene=scene, initiator_persona=sheet.primary_persona, target_persona=partner
                )
                status = (
                    SceneActionRequest.objects.filter(pk=request.pk)
                    .values_list("status", flat=True)
                    .get()
                )
                self.assertEqual(status, ActionRequestStatus.RESOLVED)
                # The ritual took effect: it was performed in this scene and anima rose.
                self.assertTrue(
                    AnimaRitualPerformance.objects.filter(ritual=ritual, scene=scene).exists()
                )
                self.assertEqual(anima_of(sheet), 4)


class CombatStillRefusesIt(_RitualGates):
    """A character in combat cannot perform her ritual, with a partner or not."""

    @settings(max_examples=20, deadline=None)
    @given(anima=st.integers(0, 10))
    def test_a_performer_in_combat_is_refused_even_with_a_willing_partner(self, anima: int) -> None:
        """The solo ritual service refused a performer who was engaged in combat. The
        maintainer's "Anima ritual can NEVER be done alone" adds a partner requirement; it does
        not lift that refusal.

        Given a performer with a ``CharacterEngagement`` asking a valid player-character partner
        in the same place, she is refused with "You cannot perform a ritual during combat.", no
        request is created, and her anima is unchanged.
        """
        sheet, _ritual = self.performer(anima=anima)
        partner = self.partner("pc")
        scene = self.scene_with(sheet, partner.character_sheet)
        CharacterEngagementFactory(character=sheet)

        with self.assertRaises(ValidationError) as refused:
            start_partner_ritual(
                scene=scene, initiator_persona=sheet.primary_persona, target_persona=partner
            )

        self.assertEqual(refused.exception.messages, [CharacterEngagedForRitual.user_message])
        self.assertFalse(SceneActionRequest.objects.filter(scene=scene).exists())
        self.assertEqual(anima_of(sheet), anima)
