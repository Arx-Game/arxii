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
from fractions import Fraction

from django.core.exceptions import ValidationError
from django.test import tag
from django.utils import timezone
from evennia.accounts.models import AccountDB
from hypothesis import assume, given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase
from rest_framework.test import APIClient

from actions.constants import ActionCategory
from actions.definitions.ritual import PerformRitualAction
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.action_points.models import ActionPointPool
from world.character_creation.magic_writer import MagicPicks, WeightedResonance
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import SoulfrayTemplateFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.fatigue.services import get_or_create_fatigue_pool
from world.gm.factories import GMProfileFactory
from world.magic.constants import AnimaRitualEndorsement, GainSource
from world.magic.exceptions import (
    AnimaRitualAnswerError,
    AnimaRitualPickError,
    CharacterEngagedForRitual,
    ResonanceInsufficient,
)
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    SoulfrayConfigFactory,
    ensure_conversion_pairs,
    ensure_soulfray_config,
)
from world.magic.models import (
    AnimaConfig,
    AnimaRitualPerformance,
    CharacterAnima,
    CharacterAura,
    CharacterResonance,
    Resonance,
    ResonanceGrant,
    Ritual,
    RitualCheckConfig,
)
from world.magic.models.kindling import AnimaRitualResonanceAward
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.magic.serializers import AnimaRitualEndorsementSerializer
from world.magic.services.anima import provision_player_anima_ritual
from world.magic.services.anima_ritual_action import start_partner_ritual
from world.magic.services.anima_ritual_attunement import (
    ALREADY_ATTUNED,
    NO_PICKS_YET,
    attune_anima_ritual,
)
from world.magic.services.anima_ritual_endorsement import answer_anima_ritual
from world.magic.services.anima_ritual_picks import (
    RESONANCES_ARE_SET,
    anima_ritual_choices,
    set_up_anima_ritual_resonances,
)
from world.magic.services.ritual_bond import ritual_earning_parts
from world.magic.types.ritual import AttunementResult
from world.mechanics.factories import CharacterEngagementFactory
from world.progression.seeds import seed_social_engagement_kudos_category
from world.roster.constants import NPCLoanStatus
from world.roster.factories import (
    NPCLoanFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models.choices import RosterType
from world.scenes import action_services
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import SceneActionRequest
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.scenes.models import Persona, Scene, SceneParticipation
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
    @given(
        control=st.sampled_from(
            ("nobody", "player borrower", "gm holder", "scene gm", "performer is scene gm")
        )
    )
    def test_an_npc_partner_is_refused_unless_a_gm_runs_it_or_the_scene(self, control: str) -> None:
        """Maintainer: "GM has control of NPC or is GMing the scene. Basically if an NPC's
        reactions are not being written by a GM ... it isn't an appropriate target."

        Given a story NPC played by nobody, by a player who borrowed it, by an account with a GM
        profile, or played by nobody in a scene a third account GMs, asking it to take part is
        refused with "Nobody is playing that character." exactly when nobody plays it or only a
        player does; otherwise the request is resolved at once, with no one asked for consent.
        A scene whose only GM is the performer's own account counts as nobody: a player never
        benefits from RP between their own characters.
        """
        # Starting at 0 of 10 anima, a Success's budget of 4 must raise it to exactly 4.
        sheet, ritual = self.performer(anima=0)
        partner = self.partner(control)
        scene = self.scene_with(sheet, partner.character_sheet, gm=control == "scene gm")
        if control == "performer is scene gm":
            performer_player = sheet.roster_entry.current_tenure.player_data.account
            own_seat = SceneParticipation.objects.get(scene=scene, account=performer_player)
            own_seat.is_gm = True
            own_seat.save(update_fields=["is_gm"])

        with force_check_outcome(self.outcomes["Success"]):
            if control in ("nobody", "player borrower", "performer is scene gm"):
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


TIERS = tuple(sorted(CANONICAL_OUTCOME_LEVELS))
PARTNER_KINDS = ("pc", "gm holder")
FAILED_TIERS = ("Failure", "Critical Failure")


def affinity_percent(key: str, split: tuple[int, int, int]) -> int:
    """The percent of an aura split ``(celestial, primal, abyssal)`` that the affinity of the
    resonance ``key`` holds."""
    celestial, primal, abyssal = split
    return {"primal": primal, "celestial": celestial, "abyssal": abyssal}[key.split()[0]]


def ritual_grants(sheet: CharacterSheet) -> list[tuple[int, str]]:
    """The anima ritual's resonance grants to ``sheet`` as (resonance id, affinity name)."""
    return list(
        ResonanceGrant.objects.filter(character_sheet=sheet, source=GainSource.ANIMA_RITUAL)
        .order_by("pk")
        .values_list("resonance_id", "resonance__affinity__name")
    )


def stored_performance(ritual: Ritual) -> dict:
    """The performance row's answer fields as the database holds them."""
    return (
        AnimaRitualPerformance.objects.filter(ritual=ritual)
        .values("was_successful", "endorsement", "outward_amount_pending", "outward_resonance_id")
        .get()
    )


class _Bonded(_AnimaRitualWorld, HypothesisTestCase):
    """Every tier has an anima budget row and a resonance award row, set to 0 here and written
    by each example (an authored row is one per tier, so the examples rewrite the rows)."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # A player character's acceptance awards kudos in this category; the fast tier does not
        # seed it, and the award code remembers the row it first read.
        seed_social_engagement_kudos_category()
        action_services._SOCIAL_ENGAGEMENT_CATEGORY = None
        cls.addClassCleanup(setattr, action_services, "_SOCIAL_ENGAGEMENT_CATEGORY", None)
        for outcome in cls.outcomes.values():
            AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=0)
            AnimaRitualResonanceAward.objects.create(outcome_tier=outcome, amount=0)

    def author(self, tier: str, *, budget: int, award: int) -> None:
        """Write the budget and the resonance award of one tier."""
        outcome = self.outcomes[tier]
        for model, field, value in (
            (AnimaRitualBudgetAward, "budget", budget),
            (AnimaRitualResonanceAward, "amount", award),
        ):
            row = model.objects.get(outcome_tier=outcome)
            setattr(row, field, value)
            row.save()

    def run_ritual(self, sheet: CharacterSheet, partner: Persona, scene: Scene, tier: str) -> None:
        """Ask ``partner`` to take part and let the roll land on ``tier``: a story NPC answers at
        once, a player character accepts."""
        with force_check_outcome(self.outcomes[tier]):
            request = start_partner_ritual(
                scene=scene, initiator_persona=sheet.primary_persona, target_persona=partner
            )
            if request.status == ActionRequestStatus.PENDING:
                respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)


class Split(_Bonded):
    """The award is split between the two picks by how the performer's aura is set up."""

    @settings(max_examples=40, deadline=None)
    @given(
        split=aura_splits(),
        primal_key=st.one_of(st.none(), st.sampled_from(PRIMAL_KEYS)),
        outward_key=st.one_of(st.none(), st.sampled_from(OUTWARD_KEYS)),
        total=st.integers(0, 200),
    )
    def test_the_parts_follow_the_aura_and_add_up_to_the_award(
        self,
        split: tuple[int, int, int],
        primal_key: str | None,
        outward_key: str | None,
        total: int,
    ) -> None:
        """Maintainer: "it should ideally be proportional to how her aura is set up. If it was
        1:1, then her ratio eventually gets thrown off."

        Given any settled aura split, a total from 0 to 200 and either or both picks, the two
        parts add up to the total. With both picks and a nonzero share between them the outward
        part is the total times its share of the two, rounded down (never more, and less than one
        short of it). One pick gets the whole total. Two picks whose shares are both 0 split it,
        the outward part rounding down.
        """
        assume(primal_key is not None or outward_key is not None)
        sheet = CharacterSheetFactory()
        CharacterAuraFactory(
            character=sheet,
            celestial=Decimal(split[0]),
            primal=Decimal(split[1]),
            abyssal=Decimal(split[2]),
        )
        primal = self.resonances[primal_key] if primal_key else None
        outward = self.resonances[outward_key] if outward_key else None

        parts = ritual_earning_parts(sheet, total, primal, outward)

        self.assertEqual(parts.primal + parts.outward, total)
        if outward is None:
            self.assertEqual((parts.primal, parts.outward), (total, 0))
        elif primal is None:
            self.assertEqual((parts.primal, parts.outward), (0, total))
        else:
            share_primal = affinity_percent(primal_key, split)
            share_outward = affinity_percent(outward_key, split)
            if share_primal + share_outward == 0:
                self.assertEqual(parts.outward, total // 2)
            else:
                exact = Fraction(total * share_outward, share_primal + share_outward)
                self.assertLessEqual(parts.outward, exact)
                self.assertLess(exact - parts.outward, 1)

    @settings(max_examples=20, deadline=None)
    @given(
        zero_slot=st.sampled_from(("primal", "outward")),
        outward_key=st.sampled_from(OUTWARD_KEYS),
        share=st.integers(1, 100),
        total=st.integers(1, 200),
        kind=st.sampled_from(PARTNER_KINDS),
    )
    def test_a_pick_whose_affinity_share_is_zero_gets_nothing(
        self, zero_slot: str, outward_key: str, share: int, total: int, kind: str
    ) -> None:
        """Maintainer: "it should ideally be proportional to how her aura is set up."

        Given both picks, one affinity settled at 0 and the other at 1 to 100 (the rest of the
        aura in the other outward affinity), the zero-share pick's part is 0 and the other pick's
        part is the whole award, with no floor. Run to the end with a Success worth ``total``, no
        resonance of the zero-share pick is granted. A story NPC partner's outward part is granted
        at once; a player character partner's is stored as pending, and when the outward share is
        0 nothing is stored and the partner is never asked.
        """
        other_outward = next(key for key in OUTWARD_KEYS if key != outward_key)
        percents = {"primal": 0, "celestial": 0, "abyssal": 0}
        outward_name = outward_key.split()[0]
        percents[other_outward.split()[0]] = 100 - share
        if zero_slot == "primal":
            percents[outward_name] = share
            percents["primal"] = 0
        else:
            percents["primal"] = share
            percents[outward_name] = 0
        split = (percents["celestial"], percents["primal"], percents["abyssal"])
        # The remainder of the aura sits in the other outward affinity, so the shares sum to 100.
        self.assertEqual(sum(split), 100)
        sheet, ritual = self.performer(
            split=split, picks=[("primal 1", 1), (outward_key, 1)], anima=0
        )
        primal, outward = self.resonances["primal 1"], self.resonances[outward_key]

        parts = ritual_earning_parts(sheet, total, primal, outward)
        expected = (0, total) if zero_slot == "primal" else (total, 0)
        self.assertEqual((parts.primal, parts.outward), expected)

        self.author("Success", budget=0, award=total)
        partner = self.partner(kind)
        scene = self.scene_with(sheet, partner.character_sheet, gm=False)
        self.run_ritual(sheet, partner, scene, "Success")

        granted = {resonance_id: 0 for resonance_id, _ in ritual_grants(sheet)}
        for resonance_id, _affinity in ritual_grants(sheet):
            granted[resonance_id] += 1
        performance = stored_performance(ritual)
        if zero_slot == "primal":
            self.assertNotIn(primal.pk, granted)
            if kind == "pc":
                self.assertEqual(performance["endorsement"], AnimaRitualEndorsement.PENDING)
                self.assertEqual(performance["outward_amount_pending"], total)
            else:
                self.assertEqual(granted, {outward.pk: 1})
        else:
            self.assertNotIn(outward.pk, granted)
            self.assertEqual(granted, {primal.pk: 1})
            self.assertEqual(performance["endorsement"], AnimaRitualEndorsement.NOT_ASKED)
            self.assertEqual(performance["outward_amount_pending"], 0)

    @settings(max_examples=20, deadline=None)
    @given(
        split=aura_splits(),
        primal_key=st.one_of(st.none(), st.sampled_from(PRIMAL_KEYS)),
        outward_key=st.one_of(st.none(), st.sampled_from(OUTWARD_KEYS)),
        tier=st.sampled_from(TIERS),
        kind=st.sampled_from(PARTNER_KINDS),
        awards=st.lists(st.integers(0, 30), min_size=len(TIERS), max_size=len(TIERS)),
    )
    def test_a_ritual_earns_at_most_two_resonances_one_primal_one_outward(  # noqa: PLR0913
        self,
        split: tuple[int, int, int],
        primal_key: str | None,
        outward_key: str | None,
        tier: str,
        kind: str,
        awards: list[int],
    ) -> None:
        """Maintainer: "it can always be a primal resonance for how it affects the caster, and a
        celestial or abyssal resonance for how it affects the target. So up to 2."

        Run the whole path (ask, accept when a player is asked) for any aura, any picks, any
        roll result and a player character or a story NPC partner. The ritual's resonance grants
        number at most 2, every Primal one is the Primal pick and every other one is the outward
        pick. A player character partner who is asked then endorses, and the count still holds.
        """
        picks = [(key, 1) for key in (primal_key, outward_key) if key]
        sheet, ritual = self.performer(split=split, picks=picks, anima=0)
        for name, amount in zip(TIERS, awards, strict=True):
            self.author(name, budget=0, award=amount)
        partner = self.partner(kind)
        scene = self.scene_with(sheet, partner.character_sheet)

        self.run_ritual(sheet, partner, scene, tier)
        waiting = AnimaRitualPerformance.objects.filter(
            ritual=ritual, endorsement=AnimaRitualEndorsement.PENDING
        ).first()
        if waiting is not None:
            answer_anima_ritual(partner.character_sheet, waiting, endorse=True)

        grants = ritual_grants(sheet)
        self.assertLessEqual(len(grants), 2)
        for resonance_id, affinity_name in grants:
            if affinity_name == self.primal.name:
                self.assertEqual(resonance_id, self.resonances[primal_key].pk)
            else:
                self.assertEqual(resonance_id, self.resonances[outward_key].pk)


class Roll(_Bonded):
    """The roll decides whether anima and Primal growth happen, and the affinity what the
    partner feels."""

    @settings(max_examples=20, deadline=None)
    @given(
        tier=st.sampled_from((*FAILED_TIERS, "Partial Success")),
        budget=st.integers(0, 8),
        award=st.integers(0, 30),
        start=st.integers(0, 10),
        kind=st.sampled_from(PARTNER_KINDS),
    )
    def test_a_failed_roll_grants_no_anima_and_no_primal(
        self, tier: str, budget: int, award: int, start: int, kind: str
    ) -> None:
        """Maintainer: "Check determines whether anima happens and whether resonance happens if
        primal." and "A failed roll gives no anima and no Primal resonance."

        Given a Failure or Critical Failure, whatever budget and award the tier holds, her anima
        is what it was and none of her Primal pick is granted. A Partial Success counts as a
        success at its own tier (maintainer ruling 2026-11-22): her anima rises by that tier's
        budget (no higher than her maximum of 10), she is granted the whole of that tier's award
        in her Primal pick (her only pick, so it takes the whole award), and the performance is
        recorded as a success.
        """
        sheet, ritual = self.performer(picks=[("primal 1", 1)], anima=start)
        self.author(tier, budget=budget, award=award)
        partner = self.partner(kind)
        scene = self.scene_with(sheet, partner.character_sheet)

        self.run_ritual(sheet, partner, scene, tier)

        primal_grants = [amount for rid, amount in self.primal_grants(sheet)]
        if tier in FAILED_TIERS:
            self.assertEqual(anima_of(sheet), start)
            self.assertEqual(primal_grants, [])
            self.assertFalse(stored_performance(ritual)["was_successful"])
        else:
            self.assertEqual(anima_of(sheet), min(start + budget, 10))
            self.assertEqual(primal_grants, [award] if award > 0 else [])
            self.assertTrue(stored_performance(ritual)["was_successful"])

    def primal_grants(self, sheet: CharacterSheet) -> list[tuple[int, int]]:
        """(resonance id, amount) of each of the ritual's Primal grants to ``sheet``."""
        return list(
            ResonanceGrant.objects.filter(
                character_sheet=sheet,
                source=GainSource.ANIMA_RITUAL,
                resonance__affinity=self.primal,
            )
            .order_by("pk")
            .values_list("resonance_id", "amount")
        )

    @settings(max_examples=20, deadline=None)
    @given(
        outward_key=st.sampled_from(OUTWARD_KEYS),
        tier=st.sampled_from(TIERS),
        kind=st.sampled_from(PARTNER_KINDS),
        setting=st.integers(1, 10),
        fatigue=st.integers(0, 10),
    )
    def test_abyssal_hurts_and_celestial_helps_the_partner(
        self, outward_key: str, tier: str, kind: str, setting: int, fatigue: int
    ) -> None:
        """Maintainer: "abyssal hurts, celestial helps."

        Given an outward pick, the Abyssal affinity set to add ``setting`` fatigue and the
        Celestial one set to ease ``setting``, a partner with ``fatigue`` social fatigue ends the
        ritual ``setting`` higher after an Abyssal pick, and ``setting`` lower (never below 0)
        after a Celestial one, whatever the roll result and whether the partner is a player
        character or a story NPC.
        """
        originals = (self.abyssal.ritual_partner_fatigue, self.celestial.ritual_partner_fatigue)
        self.abyssal.ritual_partner_fatigue = setting
        self.celestial.ritual_partner_fatigue = -setting
        self.abyssal.save()
        self.celestial.save()
        try:
            sheet, _ritual = self.performer(picks=[("primal 1", 1), (outward_key, 1)], anima=0)
            partner = self.partner(kind)
            pool = get_or_create_fatigue_pool(partner.character_sheet)
            pool.set_current(ActionCategory.SOCIAL, fatigue)
            pool.save()
            scene = self.scene_with(sheet, partner.character_sheet)

            self.run_ritual(sheet, partner, scene, tier)

            after = get_or_create_fatigue_pool(partner.character_sheet).get_current(
                ActionCategory.SOCIAL
            )
            if outward_key.startswith("abyssal"):
                self.assertEqual(after, fatigue + setting)
            else:
                self.assertEqual(after, max(fatigue - setting, 0))
        finally:
            self.abyssal.ritual_partner_fatigue, self.celestial.ritual_partner_fatigue = originals
            self.abyssal.save()
            self.celestial.save()

    @settings(max_examples=20, deadline=None)
    @given(
        drop_primal=st.booleans(),
        drop_outward=st.booleans(),
        budget=st.integers(1, 8),
        award=st.integers(1, 30),
        start=st.integers(0, 10),
        kind=st.sampled_from(PARTNER_KINDS),
    )
    def test_a_performer_who_does_not_hold_a_pick_earns_nothing_for_that_part(  # noqa: PLR0913
        self,
        drop_primal: bool,
        drop_outward: bool,
        budget: int,
        award: int,
        start: int,
        kind: str,
    ) -> None:
        """Maintainer: the ritual feeds "the resonances that they already have".

        The ritual belongs to the account, so another character on it can perform it with a pick
        she does not hold. Given an aura settled half Primal and half Abyssal, any of the two
        picks she does not hold, and a Success, her anima still rises by the budget (no higher
        than 10) and the partner's fatigue still follows the outward pick's affinity. A part
        whose resonance she does not hold earns nothing and is not stored as pending; a part she
        holds earns half the award (the outward part rounds down).
        """
        setting = 4
        original = self.abyssal.ritual_partner_fatigue
        self.abyssal.ritual_partner_fatigue = setting
        self.abyssal.save()
        try:
            sheet, ritual = self.performer(
                split=(0, 50, 50), picks=[("primal 1", 1), ("abyssal 1", 1)], anima=start
            )
            primal, outward = self.resonances["primal 1"], self.resonances["abyssal 1"]
            for dropped, resonance in ((drop_primal, primal), (drop_outward, outward)):
                if dropped:
                    CharacterResonance.objects.filter(
                        character_sheet=sheet, resonance=resonance
                    ).delete()
            self.author("Success", budget=budget, award=award)
            partner = self.partner(kind)
            scene = self.scene_with(sheet, partner.character_sheet)

            self.run_ritual(sheet, partner, scene, "Success")

            self.assertEqual(anima_of(sheet), min(start + budget, 10))
            fatigue = get_or_create_fatigue_pool(partner.character_sheet)
            self.assertEqual(fatigue.get_current(ActionCategory.SOCIAL), setting)
            outward_part = award // 2
            granted = dict(ritual_grants(sheet))
            performance = stored_performance(ritual)
            self.assertEqual(primal.pk in granted, not drop_primal)
            if drop_outward or outward_part == 0:
                self.assertNotIn(outward.pk, granted)
                self.assertEqual(performance["outward_amount_pending"], 0)
                self.assertEqual(performance["endorsement"], AnimaRitualEndorsement.NOT_ASKED)
            elif kind == "pc":
                self.assertNotIn(outward.pk, granted)
                self.assertEqual(performance["outward_amount_pending"], outward_part)
            else:
                self.assertIn(outward.pk, granted)
        finally:
            self.abyssal.ritual_partner_fatigue = original
            self.abyssal.save()


class FailedRoll(_Bonded):
    """A failed roll still reaches for the partner, at a reduced amount a player must endorse."""

    def _with_failed_endorsement_percent(self, percent: int) -> int:
        """Set the config's percent and return what it was (the caller restores it)."""
        config = AnimaConfig.get_singleton()
        original = config.failed_endorsement_percent
        config.failed_endorsement_percent = percent
        config.save()
        return original

    @settings(max_examples=20, deadline=None)
    @given(
        split=aura_splits(),
        outward_key=st.sampled_from(OUTWARD_KEYS),
        tier=st.sampled_from(FAILED_TIERS),
        success_award=st.integers(0, 60),
        has_award_row=st.booleans(),
        percent=st.integers(0, 100),
        kind=st.sampled_from(PARTNER_KINDS),
    )
    def test_a_failed_roll_holds_a_reduced_outward_amount_for_a_player_partner(  # noqa: PLR0913
        self,
        split: tuple[int, int, int],
        outward_key: str,
        tier: str,
        success_award: int,
        has_award_row: bool,
        percent: int,
        kind: str,
    ) -> None:
        """Maintainer: "Check determines whether anima happens and whether resonance happens if
        primal." (a failed roll earns no Primal) and the ruling of 2026-11-22 that after a
        failure a player partner's endorsement is worth ``failed_endorsement_percent`` of the
        outward part of the Success tier's award, because a failed tier's own award is usually
        0.

        Given a Failure or Critical Failure (whose own award is authored and must be ignored),
        both picks held and any aura, a player character partner is asked about an outward amount
        equal to the Success award split by the aura (the outward part is the award times its
        share of the Primal and outward shares, rounded down; half when both shares are 0) times
        the percent, rounded down. The performance is then pending with that amount and the
        outward pick. When that amount is 0, or no Success award row exists, nothing is stored and
        the endorsement stays not asked. A story NPC partner stores nothing and is granted
        nothing. No resonance is granted either way, and her anima does not change.
        """
        sheet, ritual = self.performer(
            split=split, picks=[("primal 1", 1), (outward_key, 1)], anima=3
        )
        outward = self.resonances[outward_key]
        self.author(tier, budget=5, award=40)
        self.author("Success", budget=5, award=success_award)
        if not has_award_row:
            AnimaRitualResonanceAward.objects.filter(outcome_tier=self.outcomes["Success"]).delete()
        original = self._with_failed_endorsement_percent(percent)
        try:
            partner = self.partner(kind)
            scene = self.scene_with(sheet, partner.character_sheet)

            self.run_ritual(sheet, partner, scene, tier)

            share_primal = affinity_percent("primal 1", split)
            share_outward = affinity_percent(outward_key, split)
            award = success_award if has_award_row else 0
            if share_primal + share_outward == 0:
                outward_part = award // 2
            else:
                outward_part = award * share_outward // (share_primal + share_outward)
            expected = outward_part * percent // 100 if kind == "pc" else 0
            performance = stored_performance(ritual)
            if expected > 0:
                self.assertEqual(performance["endorsement"], AnimaRitualEndorsement.PENDING)
                self.assertEqual(performance["outward_amount_pending"], expected)
                self.assertEqual(performance["outward_resonance_id"], outward.pk)
            else:
                self.assertEqual(performance["endorsement"], AnimaRitualEndorsement.NOT_ASKED)
                self.assertEqual(performance["outward_amount_pending"], 0)
            self.assertEqual(ritual_grants(sheet), [])
            self.assertEqual(anima_of(sheet), 3)
        finally:
            self._with_failed_endorsement_percent(original)

    @settings(max_examples=20, deadline=None)
    @given(
        tier=st.sampled_from(FAILED_TIERS),
        drop_outward=st.booleans(),
        success_award=st.integers(1, 60),
        percent=st.integers(1, 100),
    )
    def test_a_failed_roll_stores_nothing_for_an_outward_pick_she_does_not_hold(
        self, tier: str, drop_outward: bool, success_award: int, percent: int
    ) -> None:
        """Maintainer: the ritual feeds "the resonances that they already have".

        Given a failed roll, an aura settled half Primal and half Abyssal, a player character
        partner and a Success award, the outward amount is stored as pending (the award's half,
        rounded down, times the percent, rounded down) when she holds the outward pick, and
        nothing is stored, with the endorsement left not asked, when she does not.
        """
        sheet, ritual = self.performer(
            split=(0, 50, 50), picks=[("primal 1", 1), ("abyssal 1", 1)], anima=3
        )
        outward = self.resonances["abyssal 1"]
        if drop_outward:
            CharacterResonance.objects.filter(character_sheet=sheet, resonance=outward).delete()
        self.author("Success", budget=5, award=success_award)
        original = self._with_failed_endorsement_percent(percent)
        try:
            partner = self.partner("pc")
            scene = self.scene_with(sheet, partner.character_sheet)

            self.run_ritual(sheet, partner, scene, tier)

            expected = (success_award // 2) * percent // 100
            performance = stored_performance(ritual)
            if drop_outward or expected == 0:
                self.assertEqual(performance["endorsement"], AnimaRitualEndorsement.NOT_ASKED)
                self.assertEqual(performance["outward_amount_pending"], 0)
            else:
                self.assertEqual(performance["endorsement"], AnimaRitualEndorsement.PENDING)
                self.assertEqual(performance["outward_amount_pending"], expected)
        finally:
            self._with_failed_endorsement_percent(original)


ANSWERS = (
    "endorse",
    "withhold",
    "lapse",
    "endorse twice",
    "third character first",
    "endorse after the scene ended elsewhere",
    "endorse after she lost the outward resonance",
)


def outward_part_of(award: int, split: tuple[int, int, int], outward_key: str) -> int:
    """The outward part of ``award`` for a "primal 1" pick and the pick ``outward_key``, split by
    the aura as the maintainer ruled (the outward part is its share of the two, rounded down;
    half when both shares are 0)."""
    share_primal = affinity_percent("primal 1", split)
    share_outward = affinity_percent(outward_key, split)
    if share_primal + share_outward == 0:
        return award // 2
    return award * share_outward // (share_primal + share_outward)


class Endorsement(_Bonded):
    """A player character partner decides whether the outward part of what the ritual earns the
    performer is granted."""

    @settings(max_examples=40, deadline=None)
    @given(
        split=aura_splits(),
        outward_key=st.sampled_from(OUTWARD_KEYS),
        tier=st.sampled_from(TIERS),
        awards=st.lists(st.integers(0, 60), min_size=len(TIERS), max_size=len(TIERS)),
        percent=st.integers(0, 100),
        answer=st.sampled_from(ANSWERS),
    )
    def test_a_pc_partners_outward_part_is_granted_only_on_endorse(  # noqa: PLR0913
        self,
        split: tuple[int, int, int],
        outward_key: str,
        tier: str,
        awards: list[int],
        percent: int,
        answer: str,
    ) -> None:
        """Maintainer: "endorsement would be about resonance, check would be about anima. A
        player no-selling what they feel could deny the celestial/abyssal resonance." and "they
        could give some even if the check fails." and "smaller amount."

        Given any tier, any ``failed_endorsement_percent`` from 0 to 100, and an answer (endorse,
        withhold, the scene finishing unanswered, endorse twice, a third character answering
        first and then the partner endorsing, an endorse after a route that ended the scene
        without lapsing it (as a battle's end does), or an endorse after the performer lost the
        outward resonance), the outward pick's ritual grants number exactly 1 when the partner
        endorsed (even when they answered twice) and 0 otherwise. An endorse after the scene
        ended is refused and lapses the ritual; an endorse after the performer lost the
        resonance settles as endorsed and grants nothing. Its ledger
        amount, before the affinity earn rate (100 here), is the outward part of the rolled
        tier's award on Partial Success or better, or the percent of the outward part of the
        Success tier's award, rounded down, on Failure or Critical Failure. A partner is asked
        only when that amount is above 0. The Primal grant is the same in every branch, and a
        withheld or lapsed ritual takes no later endorse and grants nothing more.
        """
        sheet, ritual = self.performer(
            split=split, picks=[("primal 1", 1), (outward_key, 1)], anima=0
        )
        outward = self.resonances[outward_key]
        for name, amount in zip(TIERS, awards, strict=True):
            self.author(name, budget=0, award=amount)
        original = self._set_failed_endorsement_percent(percent)
        try:
            partner = self.partner("pc")
            scene = self.scene_with(sheet, partner.character_sheet)
            self.run_ritual(sheet, partner, scene, tier)
            by_tier = dict(zip(TIERS, awards, strict=True))
            if CANONICAL_OUTCOME_LEVELS[tier] >= 0:
                expected = outward_part_of(by_tier[tier], split, outward_key)
                primal_expected = by_tier[tier] - expected
            else:
                expected = outward_part_of(by_tier["Success"], split, outward_key) * percent // 100
                primal_expected = 0
            row = AnimaRitualPerformance.objects.get(ritual=ritual)
            endorsed = answer in ("endorse", "endorse twice", "third character first")
            lost_it = answer == "endorse after she lost the outward resonance"
            asked = expected > 0
            self.give_answer(
                answer,
                sheet=sheet,
                outward=outward,
                partner=partner,
                scene=scene,
                row=row,
                asked=asked,
            )

            self.assertEqual(
                self.outward_grants(sheet, outward), [expected] if endorsed and asked else []
            )
            self.assertEqual(
                self.primal_grants(sheet),
                [(self.resonances["primal 1"].pk, primal_expected)] if primal_expected else [],
            )
            settled = stored_performance(ritual)
            self.assertEqual(settled["outward_amount_pending"], 0)
            if not asked:
                self.assertEqual(settled["endorsement"], AnimaRitualEndorsement.NOT_ASKED)
            else:
                self.assertEqual(
                    settled["endorsement"],
                    {
                        "withhold": AnimaRitualEndorsement.WITHHELD,
                        "lapse": AnimaRitualEndorsement.LAPSED,
                        "endorse after the scene ended elsewhere": AnimaRitualEndorsement.LAPSED,
                    }.get(answer, AnimaRitualEndorsement.ENDORSED),
                )
                if not endorsed and not lost_it:
                    self.assert_refused(partner.character_sheet, row)
                    self.assertEqual(self.outward_grants(sheet, outward), [])
        finally:
            self._set_failed_endorsement_percent(original)

    @settings(max_examples=20, deadline=None)
    @given(
        split=aura_splits(),
        old_outward_key=st.sampled_from(OUTWARD_KEYS),
        award=st.integers(1, 60),
    )
    def test_an_attunement_while_asked_leaves_the_request_on_its_old_picks(
        self, split: tuple[int, int, int], old_outward_key: str, award: int
    ) -> None:
        """Maintainer: "keeps feeding it until she changes the ritual." (the ritual the partner
        was asked about is the one she asked with).

        Given a partner who has been asked to take part (the request waiting), then the performer
        attunes the ritual to a different Primal pick and a different outward pick (free here:
        no costs, no check), then the partner accepts and the roll lands on Success: the Primal
        grant goes to the old Primal pick, the outward amount held for the partner is the outward
        part of the award and is held for the old outward pick, the partner's question names the
        old outward pick in lower case, and endorsing grants the old outward pick that amount and
        grants nothing to the new picks.
        """
        new_outward_key = next(key for key in OUTWARD_KEYS if key != old_outward_key)
        sheet, ritual = self.performer(
            split=split, picks=[("primal 1", 1), (old_outward_key, 1)], anima=0
        )
        for key in ("primal 2", new_outward_key):
            CharacterResonanceFactory(character_sheet=sheet, resonance=self.resonances[key])
        self.author("Success", budget=0, award=award)
        partner = self.partner("pc")
        scene = self.scene_with(sheet, partner.character_sheet)
        request = start_partner_ritual(
            scene=scene, initiator_persona=sheet.primary_persona, target_persona=partner
        )
        self.assertEqual(request.status, ActionRequestStatus.PENDING)

        attune_anima_ritual(sheet, self.resonances["primal 2"], self.resonances[new_outward_key])
        self.assertEqual(
            stored_picks(ritual),
            (self.resonances["primal 2"].pk, self.resonances[new_outward_key].pk),
        )
        with force_check_outcome(self.outcomes["Success"]):
            respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

        old_outward = self.resonances[old_outward_key]
        expected = outward_part_of(award, split, old_outward_key)
        primal_expected = award - expected
        self.assertEqual(
            self.primal_grants(sheet),
            [(self.resonances["primal 1"].pk, primal_expected)] if primal_expected else [],
        )
        if expected == 0:
            self.assertEqual(self.outward_grants(sheet, old_outward), [])
            return
        row = AnimaRitualPerformance.objects.get(ritual=ritual)
        stored = stored_performance(ritual)
        self.assertEqual(stored["outward_resonance_id"], old_outward.pk)
        self.assertEqual(stored["outward_amount_pending"], expected)
        self.assertEqual(
            AnimaRitualEndorsementSerializer(row).data["prompt"],
            f"{sheet.primary_persona.name}'s ritual reached for your "
            f"{old_outward.name.lower()}. Did it take hold of you?",
        )
        answer_anima_ritual(partner.character_sheet, row, endorse=True)
        self.assertEqual(self.outward_grants(sheet, old_outward), [expected])
        self.assertEqual(self.outward_grants(sheet, self.resonances[new_outward_key]), [])

    def assert_refused(self, answerer: CharacterSheet, row: AnimaRitualPerformance) -> None:
        """An endorse by ``answerer`` is refused (nothing is waiting for them)."""
        with self.assertRaises(AnimaRitualAnswerError):
            answer_anima_ritual(answerer, row, endorse=True)

    def give_answer(  # noqa: PLR0913
        self,
        answer: str,
        *,
        sheet: CharacterSheet,
        outward: Resonance,
        partner: Persona,
        scene: Scene,
        row: AnimaRitualPerformance,
        asked: bool,
    ) -> None:
        """Answer (or fail to answer) the ritual the way ``answer`` names, and check each refusal
        along the way. ``asked`` is whether the partner was asked at all."""
        partner_sheet = partner.character_sheet
        if answer == "third character first":
            stranger = CharacterSheetFactory()
            self.play(stranger)
            self.assert_refused(stranger, row)
            self.assertEqual(self.outward_grants(sheet, outward), [])
        if answer == "lapse":
            scene.finish_scene()
        elif answer == "endorse after the scene ended elsewhere":
            scene.date_finished = timezone.now()
            scene.is_active = False
            scene.save(update_fields=["date_finished", "is_active"])
            self.assert_refused(partner_sheet, row)
        elif not asked:
            if answer == "endorse after she lost the outward resonance":
                CharacterResonance.objects.filter(character_sheet=sheet, resonance=outward).delete()
            self.assert_refused(partner_sheet, row)
        elif answer == "endorse after she lost the outward resonance":
            CharacterResonance.objects.filter(character_sheet=sheet, resonance=outward).delete()
            answer_anima_ritual(partner_sheet, row, endorse=True)
        else:
            answer_anima_ritual(partner_sheet, row, endorse=answer != "withhold")
            if answer == "endorse twice":
                self.assert_refused(partner_sheet, row)

    @staticmethod
    def _set_failed_endorsement_percent(percent: int) -> int:
        """Set the config's percent and return what it was (the caller restores it)."""
        config = AnimaConfig.get_singleton()
        original = config.failed_endorsement_percent
        config.failed_endorsement_percent = percent
        config.save()
        return original

    @staticmethod
    def outward_grants(sheet: CharacterSheet, outward: Resonance) -> list[int]:
        """The ledger amounts of the ritual's grants of ``outward`` to ``sheet``."""
        return list(
            ResonanceGrant.objects.filter(
                character_sheet=sheet, source=GainSource.ANIMA_RITUAL, resonance=outward
            )
            .order_by("pk")
            .values_list("amount", flat=True)
        )

    def primal_grants(self, sheet: CharacterSheet) -> list[tuple[int, int]]:
        """(resonance id, amount) of each of the ritual's Primal grants to ``sheet``."""
        return list(
            ResonanceGrant.objects.filter(
                character_sheet=sheet,
                source=GainSource.ANIMA_RITUAL,
                resonance__affinity=self.primal,
            )
            .order_by("pk")
            .values_list("resonance_id", "amount")
        )


ATTUNEMENT_COST_FIELDS = (
    "attunement_anima_cost",
    "attunement_resonance_cost",
    "attunement_ap_cost",
    "attunement_check_type",
    "attunement_difficulty_level",
)
# Plenty of everything for an attunement that is meant to be paid.
RICH_ANIMA, RICH_BALANCE, RICH_AP = 100, 100, 200


def balance_of(sheet: CharacterSheet, resonance: Resonance) -> int:
    """The balance the database holds for ``resonance`` (read around the idmapper cache)."""
    return CharacterResonance.objects.values_list("balance", flat=True).get(
        character_sheet=sheet, resonance=resonance
    )


def action_points_of(sheet: CharacterSheet) -> int:
    """The action points the database holds."""
    return ActionPointPool.objects.values_list("current", flat=True).get(character=sheet)


ATTUNEMENT_KINDS = (
    "setup",
    "attune",
    "attune to the same picks",
    "attune too poor",
    "attune to a pick she does not hold",
    "attune to the wrong affinity",
    "attune in combat",
)


# The operations that must be refused, whatever she holds and pays.
REFUSED_KINDS = frozenset(ATTUNEMENT_KINDS) - {"setup", "attune"}


@st.composite
def attunement_operations(draw: st.DrawFn) -> tuple[str, str | None, str | None, str]:
    """One step of a character's life with her ritual: what she does, the picks she names (a
    Primal and a Celestial or Abyssal resonance, either may be absent) and the tier the dice
    land on if she rolls."""
    return (
        draw(st.sampled_from(ATTUNEMENT_KINDS)),
        draw(st.one_of(st.none(), st.sampled_from(PRIMAL_KEYS))),
        draw(st.one_of(st.none(), st.sampled_from(OUTWARD_KEYS))),
        draw(st.sampled_from(tuple(CANONICAL_OUTCOME_LEVELS))),
    )


class _AttunementWorld(_PicksWorld):
    """A performer who can pay for attunements, and the staff settings that price them."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.attune_check = CheckTypeFactory()
        AnimaConfig.get_singleton()
        # Resonances she never holds: one for each slot.
        cls.unheld_primal = ResonanceFactory(name="Unheld Primal", affinity=cls.primal)
        cls.unheld_outward = ResonanceFactory(name="Unheld Celestial", affinity=cls.celestial)

    def paying_performer(self) -> tuple[CharacterSheet, Ritual]:
        """A performer with an unset ritual who can pay for attunements (anima, resonance and
        action points all in plenty)."""
        sheet, ritual = self.unset_performer(RESONANCE_KEYS)
        pool = ActionPointPool.get_or_create_for_character(sheet.character)
        pool.current = RICH_AP
        pool.save(update_fields=["current"])
        self.set_anima(sheet, current=RICH_ANIMA, glut=0)
        for key in RESONANCE_KEYS:
            row = CharacterResonance.objects.get(
                character_sheet=sheet, resonance=self.resonances[key]
            )
            row.balance = RICH_BALANCE
            row.save(update_fields=["balance"])
        return sheet, ritual

    @staticmethod
    def set_anima(sheet: CharacterSheet, *, current: int, glut: int) -> None:
        """Write her anima through the row the game reads (the identity map's), not around it."""
        row = CharacterAnima.objects.get(character=sheet)
        row.maximum = max(current, row.maximum)
        row.current = current
        row.glut = glut
        row.save(update_fields=["maximum", "current", "glut"])

    def attune_for_anima(self, sheet: CharacterSheet, cost: int) -> AttunementResult:
        """Set the ritual up (free) with a lone Primal pick, then attune it to another when the
        only price is ``cost`` anima."""
        set_up_anima_ritual_resonances(sheet, self.resonances["primal 2"], None)
        before = self.set_costs(
            attunement_anima_cost=cost,
            attunement_resonance_cost=0,
            attunement_ap_cost=0,
            attunement_check_type=None,
        )
        try:
            return attune_anima_ritual(sheet, self.resonances["primal 1"], None)
        finally:
            self.set_costs(**before)

    @staticmethod
    def set_costs(**fields: object) -> dict[str, object]:
        """Write the attunement settings on ``AnimaConfig``; return what they were."""
        config = AnimaConfig.get_singleton()
        before = {name: getattr(config, name) for name in ATTUNEMENT_COST_FIELDS}
        for name, value in fields.items():
            setattr(config, name, value)
        config.save()
        return before


class Attunement(_AttunementWorld):
    """Changing the ritual's picks after the free first setup costs, and a failed roll keeps the
    cost and the old picks."""

    @settings(max_examples=30, deadline=None)
    @given(
        operations=st.lists(attunement_operations(), min_size=1, max_size=5),
        anima_cost=st.integers(0, 10),
        resonance_cost=st.integers(0, 10),
        ap_cost=st.integers(0, 10),
        rolls=st.booleans(),
    )
    def test_picks_change_only_on_free_setup_or_a_successful_attunement(
        self,
        operations: list[tuple[str, str | None, str | None, str]],
        anima_cost: int,
        resonance_cost: int,
        ap_cost: int,
        rolls: bool,
    ) -> None:
        """Maintainer: "5. free." and "Make them configurable fields, there'd probably be a check
        to do so, failure means stuff is consumed without it changing." and "Defaults can be 0 if
        not defined." and "sure, succeeds."

        Given a sequence of up to five operations (the free setup, an attunement whose roll lands
        on any tier, an attunement to the picks she already has, an attunement she cannot pay
        for, one to a resonance she does not hold, one to a resonance of the wrong affinity, one
        while in combat; an attunement before any picks are set is refused too) and any costs from
        0 to 10, with or without an attunement check set: the ritual's
        picks are the first successful setup's, or the last successful attunement's (a Partial
        Success is a success); a failed roll spent exactly the configured action points, anima and
        resonance (the resonance of each newly picked slot) and left the picks; a refusal left
        her action points, anima, every resonance balance and both picks exactly as they were;
        and with no check set every paid attunement succeeds.
        """
        sheet, ritual = self.paying_performer()
        before = self.set_costs(
            attunement_anima_cost=anima_cost,
            attunement_resonance_cost=resonance_cost,
            attunement_ap_cost=ap_cost,
            attunement_check_type=self.attune_check if rolls else None,
            attunement_difficulty_level=0,
        )
        try:
            self.run_operations(sheet, ritual, operations, rolls=rolls)
        finally:
            self.set_costs(**before)

    def run_operations(
        self,
        sheet: CharacterSheet,
        ritual: Ritual,
        operations: list[tuple[str, str | None, str | None, str]],
        *,
        rolls: bool,
    ) -> None:
        costs = AnimaConfig.get_singleton()
        picks: tuple[str | None, str | None] = (None, None)  # the picks the rule says she holds
        anima, points = RICH_ANIMA, RICH_AP
        balances = dict.fromkeys(RESONANCE_KEYS, RICH_BALANCE)

        for kind, primal_key, outward_key, tier in operations:
            target = (primal_key, outward_key)
            primal = self.resonances[primal_key] if primal_key else None
            outward = self.resonances[outward_key] if outward_key else None
            if kind == "setup":
                if picks == (None, None) and target != (None, None):
                    set_up_anima_ritual_resonances(sheet, primal, outward)
                    picks = target
                else:
                    with self.assertRaises(AnimaRitualPickError):
                        set_up_anima_ritual_resonances(sheet, primal, outward)
            elif kind in REFUSED_KINDS:
                self.attempt_refused(kind, sheet, picks, target, balances, costs)
            elif picks == (None, None) or target in {(None, None), picks}:
                with self.assertRaises(AnimaRitualPickError):
                    attune_anima_ritual(sheet, primal, outward)
            else:
                newly = [
                    key
                    for key, current in zip(target, picks, strict=True)
                    if key is not None and key != current
                ]
                with force_check_outcome(self.outcomes[tier]):
                    result = attune_anima_ritual(sheet, primal, outward)
                anima -= costs.attunement_anima_cost
                points -= costs.attunement_ap_cost
                for key in newly:
                    balances[key] -= costs.attunement_resonance_cost
                took = (not rolls) or CANONICAL_OUTCOME_LEVELS[tier] >= 0
                self.assertEqual(result.changed, took)
                if took:
                    picks = target

            expected = (
                self.resonances[picks[0]].pk if picks[0] else None,
                self.resonances[picks[1]].pk if picks[1] else None,
            )
            self.assertEqual(stored_picks(ritual), expected)
            self.assertEqual(anima_of(sheet), anima)
            self.assertEqual(action_points_of(sheet), points)
            for key, left in balances.items():
                self.assertEqual(balance_of(sheet, self.resonances[key]), left)

    def attempt_refused(  # noqa: PLR0913 - one operation's whole state
        self,
        kind: str,
        sheet: CharacterSheet,
        picks: tuple[str | None, str | None],
        target: tuple[str | None, str | None],
        balances: dict[str, int],
        costs: AnimaConfig,
    ) -> None:
        """Attempt the attunement ``kind`` names, which must be refused (the caller checks that
        nothing was spent)."""
        primal = self.resonances[target[0]] if target[0] else None
        outward = self.resonances[target[1]] if target[1] else None
        if kind == "attune to the same picks":
            with self.assertRaises(AnimaRitualPickError) as refused:
                attune_anima_ritual(
                    sheet,
                    self.resonances[picks[0]] if picks[0] else None,
                    self.resonances[picks[1]] if picks[1] else None,
                )
            unset = picks == (None, None)
            self.assertEqual(
                refused.exception.user_message, NO_PICKS_YET if unset else ALREADY_ATTUNED
            )
        elif kind == "attune too poor" and picks == (None, None):
            self.assert_refused_attunement(sheet, primal, outward)
        elif kind == "attune too poor":
            self.attune_when_too_poor(sheet, picks, target, balances, costs)
        elif kind == "attune to a pick she does not hold":
            if primal is None:
                self.assert_refused_attunement(sheet, None, self.unheld_outward)
            else:
                self.assert_refused_attunement(sheet, self.unheld_primal, outward)
        elif kind == "attune to the wrong affinity":
            if primal is None:
                self.assert_refused_attunement(sheet, self.resonances["celestial 1"], outward)
            else:
                self.assert_refused_attunement(sheet, primal, self.resonances["primal 2"])
        else:
            engagement = CharacterEngagementFactory(character=sheet)
            self.assert_refused_attunement(sheet, primal, outward)
            engagement.delete()

    def assert_refused_attunement(
        self, sheet: CharacterSheet, primal: Resonance | None, outward: Resonance | None
    ) -> None:
        """Attuning to ``primal`` and ``outward`` is refused (the caller checks that nothing was
        spent)."""
        with self.assertRaises(AnimaRitualPickError):
            attune_anima_ritual(sheet, primal, outward)

    def attune_when_too_poor(
        self,
        sheet: CharacterSheet,
        picks: tuple[str | None, str | None],
        target: tuple[str | None, str | None],
        balances: dict[str, int],
        costs: AnimaConfig,
    ) -> None:
        """Try an attunement to ``target`` with one short of the resonance (or action points) it
        needs, and check that it is refused; the shortfall is put back afterwards. Does nothing
        when nothing can be short (a cost of 0) or ``target`` changes nothing."""
        newly = [
            key
            for key, current in zip(target, picks, strict=True)
            if key is not None and key != current
        ]
        if not newly:
            return
        primal = self.resonances[target[0]] if target[0] else None
        outward = self.resonances[target[1]] if target[1] else None
        if costs.attunement_resonance_cost > 0:
            row = CharacterResonance.objects.get(
                character_sheet=sheet, resonance=self.resonances[newly[0]]
            )
            row.balance = costs.attunement_resonance_cost - 1
            row.save(update_fields=["balance"])
            with self.assertRaises(ResonanceInsufficient):
                attune_anima_ritual(sheet, primal, outward)
            row.balance = balances[newly[0]]
            row.save(update_fields=["balance"])
        if costs.attunement_ap_cost > 0:
            pool = ActionPointPool.objects.get(character=sheet)
            held = pool.current
            pool.current = costs.attunement_ap_cost - 1
            pool.save(update_fields=["current"])
            with self.assertRaises(AnimaRitualPickError):
                attune_anima_ritual(sheet, primal, outward)
            pool.current = held
            pool.save(update_fields=["current"])

    @settings(max_examples=20, deadline=None)
    @given(
        unheld_slot=st.sampled_from(("primal", "outward")),
        primal_key=st.sampled_from(PRIMAL_KEYS),
        outward_key=st.sampled_from(OUTWARD_KEYS),
        clears_other_slot=st.booleans(),
    )
    def test_a_pick_she_no_longer_holds_stays_while_the_other_slot_changes(
        self, unheld_slot: str, primal_key: str, outward_key: str, clears_other_slot: bool
    ) -> None:
        """Maintainer: "Keeps feeding it until she changes the ritual."

        Given a ritual set up with a Primal and an outward pick, and one of the two picks then
        leaving her held list (her resonance row gone), an attunement that changes only the other
        slot (to the other resonance of its kind, or, for the outward slot, to none) succeeds and
        keeps the unheld pick exactly as it was: only a pick being changed has to be held.
        """
        sheet, ritual = self.paying_performer()
        set_up_anima_ritual_resonances(
            sheet, self.resonances[primal_key], self.resonances[outward_key]
        )
        unheld_key = primal_key if unheld_slot == "primal" else outward_key
        CharacterResonance.objects.filter(
            character_sheet=sheet, resonance=self.resonances[unheld_key]
        ).delete()
        sheet.character.resonances.invalidate()

        if unheld_slot == "primal":
            other = None if clears_other_slot else next(k for k in OUTWARD_KEYS if k != outward_key)
            target = (self.resonances[primal_key], self.resonances[other] if other else None)
        else:
            other = next(k for k in PRIMAL_KEYS if k != primal_key)
            target = (self.resonances[other], self.resonances[outward_key])
        before = self.set_costs(
            attunement_anima_cost=1,
            attunement_resonance_cost=1,
            attunement_ap_cost=1,
            attunement_check_type=None,
        )
        try:
            result = attune_anima_ritual(sheet, *target)
        finally:
            self.set_costs(**before)

        self.assertTrue(result.changed)
        self.assertEqual(
            stored_picks(ritual),
            (target[0].pk, target[1].pk if target[1] else None),
        )

    @settings(max_examples=30, deadline=None)
    @given(
        cost=st.integers(0, 10),
        current=st.integers(0, 10),
        glut=st.integers(0, 5),
    )
    def test_attunement_never_refuses_for_lack_of_anima(
        self, cost: int, current: int, glut: int
    ) -> None:
        """Maintainer: "soulfray but it'd probably be 0 anima, thinking about it."

        Given any anima she has (current 0 to 10, glut 0 to 5) and any anima cost from 0 to 10,
        the attunement is never refused for anima and writes the picks. It spends the glut first,
        so her glut ends at `glut - min(cost, glut)` and her current anima at
        `max(current - (cost - min(cost, glut)), 0)`, and the shortfall it reports is the part of
        the cost she had neither anima nor glut for.
        """
        sheet, ritual = self.paying_performer()
        self.set_anima(sheet, current=current, glut=glut)
        result = self.attune_for_anima(sheet, cost)

        from_glut = min(cost, glut)
        row = CharacterAnima.objects.values("current", "glut").get(character=sheet)
        self.assertEqual(row["glut"], glut - from_glut)
        self.assertEqual(row["current"], max(current - (cost - from_glut), 0))
        self.assertTrue(result.changed)
        self.assertEqual(stored_picks(ritual), (self.resonances["primal 1"].pk, None))
        self.assertEqual(result.soulfray_deficit, max(cost - glut - current, 0))


@tag("postgres")  # Soulfray's condition lookup uses DISTINCT ON, which SQLite lacks.
class AttunementIntoSoulfray(_AttunementWorld):
    """What an attunement's anima cost she cannot pay becomes Soulfray."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.soulfray = SoulfrayTemplateFactory()
        ensure_soulfray_config()

    @settings(max_examples=30, deadline=None)
    @given(
        cost=st.integers(0, 10),
        current=st.integers(0, 10),
        glut=st.integers(0, 5),
    )
    def test_a_shortfall_in_anima_is_soulfray_and_nothing_else_is(
        self, cost: int, current: int, glut: int
    ) -> None:
        """Maintainer: "soulfray but it'd probably be 0 anima, thinking about it."

        Given any anima she has (current 0 to 10, glut 0 to 5) and any anima cost from 0 to 10,
        the attunement is never refused for anima, and she gains a Soulfray condition if and only
        if the cost was more than her current anima and glut together.
        """
        sheet, _ritual = self.paying_performer()
        self.set_anima(sheet, current=current, glut=glut)

        result = self.attune_for_anima(sheet, cost)

        self.assertTrue(result.changed)
        frayed = ConditionInstance.objects.filter(
            target=sheet.character, condition=self.soulfray
        ).exists()
        self.assertEqual(frayed, cost > current + glut)


class AttunementThatFailsMidway(_AttunementWorld):
    """A spend that raises halfway leaves every row as it was."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # A Soulfray config that names no condition: a shortfall in anima then raises, after the
        # action points and the anima have been charged.
        SoulfrayConfigFactory(condition=None)

    @settings(max_examples=20, deadline=None)
    @given(
        anima=st.integers(0, 3),
        extra=st.integers(1, 7),
        resonance_cost=st.integers(0, 10),
        ap_cost=st.integers(0, 10),
    )
    def test_an_attunement_that_raises_after_spending_leaves_every_row_as_it_was(
        self, anima: int, extra: int, resonance_cost: int, ap_cost: int
    ) -> None:
        """Maintainer: "failure means stuff is consumed without it changing", and a failure that
        is not the roll consumes nothing.

        Given any costs, and an anima cost that is more than she has, so the spend must go
        through Soulfray, which here cannot (staff named no Soulfray condition) and raises after
        the action points and the anima were charged: the database rolls back, and what the game
        reads (the cached action points, anima, resonance balances and the ritual's picks) shows
        the values it held before, equal to the database's.
        """
        sheet, ritual = self.paying_performer()
        set_up_anima_ritual_resonances(sheet, self.resonances["primal 2"], None)
        self.set_anima(sheet, current=anima, glut=0)
        before = self.set_costs(
            attunement_anima_cost=anima + extra,
            attunement_resonance_cost=resonance_cost,
            attunement_ap_cost=ap_cost,
            attunement_check_type=None,
        )
        try:
            with self.assertRaises(ConditionTemplate.DoesNotExist):
                attune_anima_ritual(
                    sheet, self.resonances["primal 1"], self.resonances["abyssal 1"]
                )
        finally:
            self.set_costs(**before)

        primal_2 = self.resonances["primal 2"].pk
        self.assertEqual(stored_picks(ritual), (primal_2, None))
        config = ritual.check_config
        self.assertEqual(
            (config.primal_resonance_id, config.outward_resonance_id), (primal_2, None)
        )
        self.assertEqual(anima_of(sheet), anima)
        self.assertEqual(CharacterAnima.objects.get(character=sheet).current, anima)
        self.assertEqual(action_points_of(sheet), RICH_AP)
        self.assertEqual(ActionPointPool.objects.get(character=sheet).current, RICH_AP)
        for key in RESONANCE_KEYS:
            resonance = self.resonances[key]
            self.assertEqual(balance_of(sheet, resonance), RICH_BALANCE)
            cached = CharacterResonance.objects.get(character_sheet=sheet, resonance=resonance)
            self.assertEqual(cached.balance, RICH_BALANCE)
