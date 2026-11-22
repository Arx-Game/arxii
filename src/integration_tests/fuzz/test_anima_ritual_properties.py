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
from rest_framework.test import APIClient

from actions.definitions.ritual import PerformRitualAction
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.character_creation.magic_writer import MagicPicks, WeightedResonance
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.test_helpers import force_check_outcome
from world.gm.factories import GMProfileFactory
from world.magic.exceptions import AnimaRitualPickError, CharacterEngagedForRitual
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
    CharacterAura,
    CharacterResonance,
    Resonance,
    Ritual,
    RitualCheckConfig,
)
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.magic.services.anima import provision_player_anima_ritual
from world.magic.services.anima_ritual_action import start_partner_ritual
from world.magic.services.anima_ritual_picks import (
    RESONANCES_ARE_SET,
    anima_ritual_choices,
    set_up_anima_ritual_resonances,
)
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


PRIMAL_KEYS = ("primal 1", "primal 2")
OUTWARD_KEYS = ("celestial 1", "abyssal 1")


def stored_picks(ritual: Ritual) -> tuple[int | None, int | None]:
    """The two picks the database holds (read around the idmapper cache)."""
    return RitualCheckConfig.objects.values_list("primal_resonance_id", "outward_resonance_id").get(
        ritual=ritual
    )


class _PicksWorld(_AnimaRitualWorld, HypothesisTestCase):
    """A performer whose ritual has no picks yet, holding exactly the resonances a property
    draws (so the free first setup is still ahead of her)."""

    def unset_performer(self, held: Sequence[str]) -> tuple[CharacterSheet, Ritual]:
        sheet, ritual = self.performer()
        for key in held:
            CharacterResonanceFactory(character_sheet=sheet, resonance=self.resonances[key])
        self.assertEqual(stored_picks(ritual), (None, None))
        return sheet, ritual


class Picks(_PicksWorld):
    """The ritual's resonances come from the aura and are set once for free."""

    @settings(max_examples=20, deadline=None)
    @given(
        held=st.lists(st.sampled_from(RESONANCE_KEYS), unique=True),
        primal_key=st.one_of(st.none(), st.sampled_from(RESONANCE_KEYS)),
        outward_key=st.one_of(st.none(), st.sampled_from(RESONANCE_KEYS)),
    )
    def test_only_held_resonances_of_the_right_affinity_can_be_picked(
        self, held: list[str], primal_key: str | None, outward_key: str | None
    ) -> None:
        """Maintainer: "only let them select what they have available from the aura ... not a
        free text field."

        Given any set of held resonances and any candidate (or none) for each slot, the free
        setup succeeds exactly when at least one slot is given and every given candidate is held
        and of its slot's affinity (Primal for the Primal slot, Celestial or Abyssal for the
        outward slot). On a refusal both picks stay unset.
        """
        sheet, ritual = self.unset_performer(held)
        fits = (primal_key is None or (primal_key in held and primal_key in PRIMAL_KEYS)) and (
            outward_key is None or (outward_key in held and outward_key in OUTWARD_KEYS)
        )
        allowed = fits and not (primal_key is None and outward_key is None)
        primal = self.resonances[primal_key] if primal_key else None
        outward = self.resonances[outward_key] if outward_key else None

        if allowed:
            set_up_anima_ritual_resonances(sheet, primal, outward)
            self.assertEqual(
                stored_picks(ritual),
                (primal.pk if primal else None, outward.pk if outward else None),
            )
        else:
            with self.assertRaises(AnimaRitualPickError):
                set_up_anima_ritual_resonances(sheet, primal, outward)
            self.assertEqual(stored_picks(ritual), (None, None))

    @settings(max_examples=20, deadline=None)
    @given(
        slot=st.sampled_from(("primal", "outward")),
        first=st.integers(0, 1),
        second=st.integers(0, 1),
    )
    def test_the_picks_are_locked_once_set(self, slot: str, first: int, second: int) -> None:
        """Maintainer: "it's locked in unless the ritual itself changes."

        Given a ritual set up once with a pick in either slot, a second free setup (the same
        picks or others, in either slot) is refused with "Your ritual's resonances are set.
        Attune it to change them." and the picks are exactly what the first setup wrote.
        """
        sheet, ritual = self.unset_performer(RESONANCE_KEYS)
        keys = PRIMAL_KEYS if slot == "primal" else OUTWARD_KEYS
        chosen = self.resonances[keys[first]]
        if slot == "primal":
            set_up_anima_ritual_resonances(sheet, chosen, None)
            expected = (chosen.pk, None)
        else:
            set_up_anima_ritual_resonances(sheet, None, chosen)
            expected = (None, chosen.pk)

        again = self.resonances[PRIMAL_KEYS[second]]
        with self.assertRaises(AnimaRitualPickError) as refused:
            set_up_anima_ritual_resonances(sheet, again, self.resonances[OUTWARD_KEYS[second]])

        self.assertEqual(refused.exception.user_message, RESONANCES_ARE_SET)
        self.assertEqual(stored_picks(ritual), expected)
        self.assertTrue(anima_ritual_choices(sheet).locked)

    @settings(max_examples=20, deadline=None)
    @given(
        primal_key=st.sampled_from(PRIMAL_KEYS),
        outward_key=st.sampled_from(OUTWARD_KEYS),
        settled_left=st.integers(1, 99),
    )
    def test_a_pick_keeps_feeding_after_it_leaves_the_aura(
        self, primal_key: str, outward_key: str, settled_left: int
    ) -> None:
        """Maintainer: "Keeps feeding it until she changes the ritual."

        Given a ritual set up with a Primal and an outward pick, then the performer's balance
        and lifetime of each picked resonance drops to 0 and the aura's settled share in each
        pick's affinity falls to a smaller share that is not 0, the ritual still carries both
        picks, and the choices still report them as the picks.
        """
        sheet, ritual = self.unset_performer(RESONANCE_KEYS)
        primal, outward = self.resonances[primal_key], self.resonances[outward_key]
        set_up_anima_ritual_resonances(sheet, primal, outward)

        for resonance in (primal, outward):
            row = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
            row.balance = 0
            row.lifetime_earned = 0
            row.save()
        aura = CharacterAura.objects.get(character=sheet)
        aura.primal = Decimal(settled_left)
        aura.celestial = Decimal(100 - settled_left)
        aura.abyssal = Decimal(0)
        aura.save()

        self.assertEqual(stored_picks(ritual), (primal.pk, outward.pk))
        choices = anima_ritual_choices(sheet)
        self.assertEqual((choices.primal_pick, choices.outward_pick), (primal, outward))
        self.assertTrue(choices.locked)

    @settings(max_examples=20, deadline=None)
    @given(held=st.lists(st.sampled_from(RESONANCE_KEYS), unique=True))
    def test_the_choices_list_exactly_the_held_resonances_by_slot(self, held: list[str]) -> None:
        """Maintainer: "only let them select what they have available from the aura".

        Given any set of held resonances, the Primal choices are the held Primal ones and the
        outward choices the held Celestial and Abyssal ones, each by name, and nothing else.
        """
        sheet, _ritual = self.unset_performer(held)

        choices = anima_ritual_choices(sheet)

        def named(keys: Sequence[str]) -> list[str]:
            return sorted(self.resonances[key].name for key in keys if key in held)

        self.assertEqual([r.name for r in choices.primal], named(PRIMAL_KEYS))
        self.assertEqual([r.name for r in choices.outward], named(OUTWARD_KEYS))
        self.assertFalse(choices.locked)


class SetUpRoute(_PicksWorld):
    """The route writes the ritual only through the service and only for the player's own."""

    @settings(max_examples=20, deadline=None)
    @given(primal_key=st.sampled_from(PRIMAL_KEYS), outward_key=st.sampled_from(OUTWARD_KEYS))
    def test_a_player_sets_up_only_her_own_ritual_and_only_once(
        self, primal_key: str, outward_key: str
    ) -> None:
        """Maintainer: "only let them select what they have available from the aura ... not a
        free text field."

        Given a ritual with no picks, another player naming her character on the set-up route is
        refused and the picks stay unset; the owner's request writes both picks and answers with
        the choices locked; the choices route then reads the picks, the outward list and the
        attunement costs to the owner and refuses the stranger; the owner's second request is
        refused and changes nothing.
        """
        sheet, ritual = self.unset_performer(RESONANCE_KEYS)
        owner = sheet.character.db_account
        stranger = self.play(CharacterSheetFactory())
        body = {
            "character_sheet_id": sheet.pk,
            "primal_resonance_id": self.resonances[primal_key].pk,
            "outward_resonance_id": self.resonances[outward_key].pk,
        }
        url = "/api/magic/anima-ritual/set-up/"
        client = APIClient()

        client.force_authenticate(stranger)
        self.assertEqual(client.post(url, body, format="json").status_code, 400)
        self.assertEqual(stored_picks(ritual), (None, None))

        client.force_authenticate(owner)
        done = client.post(url, body, format="json")
        self.assertEqual(done.status_code, 200)
        self.assertTrue(done.data["locked"])
        self.assertEqual(
            stored_picks(ritual), (self.resonances[primal_key].pk, self.resonances[outward_key].pk)
        )

        read_url = f"/api/magic/anima-ritual/resonances/?character_sheet_id={sheet.pk}"
        read = client.get(read_url)
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.data["primal_pick"]["id"], self.resonances[primal_key].pk)
        self.assertEqual(read.data["outward_pick"]["id"], self.resonances[outward_key].pk)
        self.assertEqual(
            sorted(row["name"] for row in read.data["outward"]),
            sorted(self.resonances[key].name for key in OUTWARD_KEYS),
        )
        self.assertEqual(
            set(read.data["attunement"]),
            {"anima_cost", "resonance_cost", "ap_cost", "check_type_name"},
        )
        client.force_authenticate(stranger)
        self.assertEqual(client.get(read_url).status_code, 400)
        client.force_authenticate(owner)

        other = {**body, "primal_resonance_id": self.resonances["primal 2"].pk}
        self.assertEqual(client.post(url, other, format="json").status_code, 400)
        self.assertEqual(
            stored_picks(ritual), (self.resonances[primal_key].pk, self.resonances[outward_key].pk)
        )
