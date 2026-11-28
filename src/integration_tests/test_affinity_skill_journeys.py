"""Journeys for Villainy, Heroism and Reflection (#5308): a bonus check on every earned gain.

Staff linked one Magic skill to each affinity and gave the bonus check a stat (Presence), a
difficulty of 0 and an award table: a Critical Success grows a gain by 50 percent, a Partial
Success adds nothing. Hand-worked numbers: a threatening act earns 10 Cruelty at its roll's
Success, all of it at once. A 50 percent check makes it 15. The dice are pinned by queueing
the results (``force_check_outcome(first, second)``): the act's own roll lands on Success, then
the bonus check on the result named in the test. Nothing of ours is patched.

Mirelle (Abyssal, Villainy 30) and Aldric (Celestial, no Villainy) threaten the same prisoner.
Both earn Cruelty, which neither held. Both bonus checks add Villainy, the stat of the threat's
own roll replaces the check's stat, and only Mirelle's check carries points for the skill.
A mark (#5327) is grown by the same check: Mirelle marks an act of hers with Cruelty and her
Villainy check grows what it pays.
"""

from __future__ import annotations

from decimal import Decimal
import uuid

from django.test import tag
from evennia.utils.ansi import strip_ansi
from rest_framework import status

from integration_tests.harness import JourneyCase
from integration_tests.test_anima_ritual_partner_journeys import _RitualWithAPartner
from integration_tests.test_earning_kindled_deeds_journeys import _Gate
from integration_tests.test_resonance_strain_journeys import _BurningResonance
from world.character_creation.sheet_writers import set_skill_values
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome, force_every_check_outcome
from world.magic.constants import GainSource
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    KindledDeedAwardFactory,
    KindledStrengthTierFactory,
    KindlingConfigFactory,
    RecordedActFactory,
    ResonanceCheckAwardFactory,
    ResonanceFactory,
    ensure_conversion_pairs,
)
from world.magic.models import (
    Affinity,
    CharacterAuraShare,
    CharacterResonance,
    PoseEndorsement,
    ResonanceGrant,
    TrickleAccrual,
)
from world.magic.services.gain import (
    get_resonance_gain_config,
    residence_trickle_tick,
    set_residence,
    settle_weekly_pot,
    tag_room_resonance,
    waiting_trickles,
)
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.skills.factories import MagicSkillFactory
from world.traits.constants import TraitType
from world.traits.factories import StatTraitFactory
from world.traits.models import PointConversionRange, TraitChangeSource
from world.traits.services import ensure_canonical_check_outcome

SUBMIT_POSE = "/api/interactions/submit-pose/"
POSE_ENDORSEMENTS = "/api/magic/pose-endorsements/"


class _Skills:
    """Staff's authoring for the three affinity skills and the bonus check (a mixin)."""

    def author_the_skills(self) -> None:
        celestial, primal, abyssal = ensure_conversion_pairs()
        self.skills = {}
        for affinity, name in (
            (celestial, "Heroism"),
            (primal, "Reflection"),
            (abyssal, "Villainy"),
        ):
            skill = MagicSkillFactory(name=name)
            affinity.skill = skill
            affinity.save()
            self.skills[name] = skill
        Affinity.objects.clear_cache()
        self.celestial, self.primal, self.abyssal = celestial, primal, abyssal
        # One check point per rating point, as the skills docs state.
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.presence = StatTraitFactory(name="presence")
        self.bonus_check = CheckTypeFactory(name="Resonance bonus")
        CheckTypeTraitFactory(check_type=self.bonus_check, trait=StatTraitFactory(name="wits"))
        cfg = get_resonance_gain_config()
        cfg.bonus_check_type = self.bonus_check
        cfg.save()
        self.crit = ensure_canonical_check_outcome("Critical Success")
        self.partial_result = ensure_canonical_check_outcome("Partial Success")
        ResonanceCheckAwardFactory(outcome_tier=self.crit, gain_bonus_percent=50)
        ResonanceCheckAwardFactory(outcome_tier=self.partial_result, gain_bonus_percent=0)

    def train(self, sheet, skill_name: str, rating: int) -> None:
        set_skill_values(
            sheet,
            {self.skills[skill_name]: rating},
            {},
            source=TraitChangeSource.CHARACTER_CREATION,
            enforce_caps=False,
        )

    def bonus_calls(self, capture) -> list:
        return [call for call in capture.calls if call.check_type == self.bonus_check]

    def points_of(self, character, call) -> int:
        """The trait points the bonus check ``call`` was worth to ``character``."""
        return perform_check(
            character, call.check_type, extra_traits=call.extra_traits, stat_override="presence"
        ).trait_points


class TheHeroAndTheVillainDoOneCruelAct(_Skills, _Gate):
    """Mirelle and Aldric each threaten the bound prisoner on the same mission option."""

    def setUp(self) -> None:
        super().setUp()
        self.author_the_skills()
        KindlingConfigFactory()
        self.mirelle, self.aldric = self.mira, self.tomas
        self.cruelty = ResonanceFactory(name="Cruelty", affinity=self.abyssal)
        self.mercy = ResonanceFactory(name="Mercy", affinity=self.celestial)
        CharacterAuraFactory(
            character=self.mirelle.sheet_data, celestial=Decimal(0), primal=Decimal(0), abyssal=100
        )
        CharacterAuraFactory(
            character=self.aldric.sheet_data, celestial=Decimal(100), primal=Decimal(0), abyssal=0
        )
        # Aldric holds Mercy, so the aura he settled into is Celestial; Cruelty is new to both.
        CharacterResonanceFactory(
            character_sheet=self.aldric.sheet_data,
            resonance=self.mercy,
            balance=0,
            lifetime_earned=100,
        )
        self.train(self.mirelle.sheet_data, "Villainy", 30)
        self.theme_row(self.captives, strength=2, resonance=self.cruelty)
        option = self.check_option(self.captives)
        CheckTypeTraitFactory(
            check_type=option.authored_check_type, trait=self.presence, weight=Decimal(1)
        )
        self.mirelle_mission = _assign(self.mission_template, self.mirelle)
        self.aldric_mission = _assign(self.mission_template, self.aldric)

    def threaten(self, character, mission, bonus_result):
        """``character`` takes the option, her own roll a Success and her bonus check
        ``bonus_result``. Returns the capture of every roll the act made."""
        with (
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(self.success, bonus_result) as capture,
        ):
            self.telnet(character, f"mission resolve {mission.pk} 1")
        return capture

    def cruelty_row(self, character) -> CharacterResonance:
        return CharacterResonance.objects.get(
            character_sheet=character.sheet_data, resonance=self.cruelty
        )

    def test_the_villain_earns_more_than_the_hero_from_the_same_act(self) -> None:
        hero = self.threaten(self.aldric, self.aldric_mission, self.partial_result)
        villain = self.threaten(self.mirelle, self.mirelle_mission, self.crit)

        # The same act, the same stat, the same skill: both bonus checks add Villainy and take
        # Presence, the stat of the threat's own roll. Only Mirelle's carries points for it.
        (hero_call,) = self.bonus_calls(hero)
        (villain_call,) = self.bonus_calls(villain)
        for call in (hero_call, villain_call):
            self.assertEqual([t.trait for t in call.extra_traits], [self.skills["Villainy"]])
            self.assertEqual(call.stat_override, "presence")
        self.assertEqual(self.points_of(self.mirelle, villain_call), 30)
        self.assertEqual(self.points_of(self.aldric, hero_call), 0)

        # Cruelty was held by neither; both hold it now. The whole deed pays at once: 10 for
        # Aldric, and Mirelle's 50 percent makes hers 15.
        self.assertEqual(self.cruelty_row(self.aldric).balance, 10)
        self.assertEqual(self.cruelty_row(self.mirelle).balance, 15)
        self.assertTold(self.aldric, "You earned 10 Cruelty.")
        self.assertTold(
            self.mirelle, "You earned 15 Cruelty. Your Villainy check added 50 percent."
        )
        self.assertNotTold(self.aldric, "Villainy check")
        grants = {
            g.character_sheet_id: g for g in ResonanceGrant.objects.filter(resonance=self.cruelty)
        }
        self.assertEqual(grants[self.aldric.sheet_data.pk].bonus_percent, 0)
        self.assertEqual(grants[self.mirelle.sheet_data.pk].bonus_percent, 50)

        # His smaller gain still unsettles him: his Abyssal share is above what he settled in.
        share = CharacterAuraShare.objects.get(
            aura__character=self.aldric.sheet_data, affinity=self.abyssal
        )
        self.assertGreater(share.percent, share.settled_percent)


def _assign(template, character):
    from world.missions.services.run import staff_assign_mission

    return staff_assign_mission(template, character)


class _AScene(_Skills, JourneyCase):
    """Mirelle and Aldric in The Lantern's live scene. Mercy is Celestial and Mirelle holds none."""

    def setUp(self) -> None:
        super().setUp()
        self.author_the_skills()
        self.room = self.make_room("The Lantern")
        self.mirelle = self.make_player("Mirelle", room=self.room)
        self.aldric = self.make_player("Aldric", room=self.room)
        self.scene = SceneFactory(
            location=_profile_of(self.room), is_active=True, name="Supper at the Lantern"
        )
        invalidate_active_scene_cache(self.room)
        for player in (self.mirelle, self.aldric):
            self.watch(player)
            self.connect_telnet(player)
            SceneParticipationFactory(scene=self.scene, account=self.account_of(player))
        self.mercy = ResonanceFactory(name="Mercy", affinity=self.celestial)
        self.mirelle_web = self.api(self.account_of(self.mirelle))
        self.aldric_web = self.api(self.account_of(self.aldric))

    def telnet(self, character, line: str) -> str:
        with self.captureOnCommitCallbacks(execute=True):
            return super().telnet(character, line)

    def mercy_row(self):
        return CharacterResonance.objects.filter(
            character_sheet=self.mirelle.sheet_data, resonance=self.mercy
        ).first()

    def panel_names(self) -> list[str]:
        """The resonances Mirelle's "Your resonances" panel lists."""
        response = self.mirelle_web.get(
            "/api/magic/kindled-resonances/", {"character_sheet": self.mirelle.sheet_data.pk}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return [row["name"] for row in response.json()["results"]]

    def settle(self, *results) -> None:
        """Aldric's week is settled; the bonus check of each grant lands on the next result."""
        with force_check_outcome(*results):
            settle_weekly_pot(self.aldric.sheet_data)


def _profile_of(room):
    from evennia_extensions.factories import RoomProfileFactory

    return RoomProfileFactory(objectdb=room)


class AMarkIsGrownByTheAffinitysCheck(_AScene):
    """Mirelle marks an act of hers with Cruelty, and her Villainy check grows what it pays.

    The act is worth 10 (the award for a Success, at the lowest strength's full share), and a
    Critical Success on the bonus check adds 50 percent: 10 + 5 = 15. The room reads her pose
    and nothing of what it paid.
    """

    def setUp(self) -> None:
        super().setUp()
        self.cruelty = ResonanceFactory(name="Cruelty", affinity=self.abyssal)
        success = ensure_canonical_check_outcome("Success")
        KindledDeedAwardFactory(outcome_tier=success, amount=10)
        KindledStrengthTierFactory(rank=1, name="Faint", earn_percent=100)
        self.act = RecordedActFactory(
            character_sheet=self.mirelle.sheet_data,
            outcome=success,
            label="Threatened the prisoner",
        )

    def test_the_mark_pays_the_acts_worth_grown_by_the_villainy_check(self) -> None:
        with force_check_outcome(self.crit):
            told = self.telnet(
                self.mirelle, f"pose/reach Cruelty:{self.act.pk}=glares at the prisoner."
            )

        self.assertIn("Your Cruelty grows by 15. Your Villainy check added 50 percent.", told)
        row = CharacterResonance.objects.get(
            character_sheet=self.mirelle.sheet_data, resonance=self.cruelty
        )
        self.assertEqual(row.balance, 15)
        grant = ResonanceGrant.objects.get(source=GainSource.MARKED_ACT)
        self.assertEqual((grant.amount, grant.bonus_percent), (15, 50))
        self.assertTold(self.aldric, "glares at the prisoner.")
        self.assertNotTold(self.aldric, "Villainy check")
        self.assertNotTold(self.aldric, "grows by")


class AReachedPoseIsEndorsedAndPaysTheReach(_AScene):
    """Mirelle reaches for Mercy, which she does not hold; Aldric only confirms it."""

    def test_through_telnet_the_endorsement_pays_the_resonance_the_pose_reached_for(self) -> None:
        told = self.telnet(self.mirelle, "pose/reach Mercy=lowers the blade and steps back.")
        self.assertNotIn("no resonance", told.lower())

        previewed = self.telnet(self.aldric, "endorse pose Mirelle")
        endorsed = self.telnet(self.aldric, "endorse pose Mirelle confirm")

        self.assertNotIn("Which resonance", previewed + endorsed)
        endorsement = PoseEndorsement.objects.get()
        self.assertEqual(endorsement.resonance, self.mercy)
        self.assertIsNone(self.mercy_row())

        self.settle(self.crit)

        # The weekly pot of 20 rides one endorsement; her Heroism check grew it by 50 percent.
        self.assertEqual(self.mercy_row().balance, 30)
        grant = ResonanceGrant.objects.get(source=GainSource.POSE_ENDORSEMENT)
        self.assertEqual((grant.resonance, grant.amount, grant.bonus_percent), (self.mercy, 30, 50))
        # What she sees: Mercy is on her resonance list, in the panel and on telnet.
        self.assertIn("Mercy", self.telnet(self.mirelle, "resonances"))
        self.assertIn("Mercy", self.panel_names())

    def test_a_pose_that_reached_for_nothing_asks_the_endorser_which_resonance(self) -> None:
        self.telnet(self.mirelle, "pose lowers the blade and steps back.")

        told = self.telnet(self.aldric, "endorse pose Mirelle confirm")

        self.assertIn("Which resonance", told)
        self.assertFalse(PoseEndorsement.objects.exists())

    def test_through_the_web_the_reach_and_the_endorsement_agree(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            posed = self.mirelle_web.post(
                SUBMIT_POSE,
                {
                    "persona_id": self.mirelle.sheet_data.primary_persona.pk,
                    "scene_id": self.scene.pk,
                    "content": "lowers the blade and steps back.",
                    "client_request_id": str(uuid.uuid4()),
                    "reach_resonance_id": self.mercy.pk,
                },
                format="json",
            )
        self.assertEqual(posed.status_code, status.HTTP_201_CREATED, posed.data)

        # Aldric names no resonance: the pose already did.
        with self.captureOnCommitCallbacks(execute=True):
            endorsed = self.aldric_web.post(
                POSE_ENDORSEMENTS, {"interaction": posed.json()["id"]}, format="json"
            )
        self.assertEqual(endorsed.status_code, status.HTTP_201_CREATED, endorsed.content)
        self.assertEqual(endorsed.json()["resonance"], self.mercy.pk)

        self.settle(self.crit)

        self.assertEqual(self.mercy_row().balance, 30)
        self.assertIn("Mercy", self.panel_names())
        self.assertIn("Mercy", self.telnet(self.mirelle, "resonances"))


class TheVillainsDaysArePiledUpAndHarvestedByHerRitual(_Skills, _RitualWithAPartner):
    """Mara lives in a room tagged Ruin. Her days pile up and wait; her anima ritual with Tobin
    harvests them, one bonus check per affinity the ritual pays (here Primal and Abyssal)."""

    def setUp(self) -> None:
        super().setUp()
        self.author_the_skills()
        cfg = get_resonance_gain_config()
        cfg.residence_daily_trickle_per_resonance = 4
        cfg.save()
        home = _profile_of(self.make_room("Mara's House"))
        tag_room_resonance(home, self.resonance)
        set_residence(self.mara.sheet_data, home)

    def test_ticks_pay_nothing_and_the_ritual_harvests_the_pile_grown_by_the_villainy_check(
        self,
    ) -> None:
        for _day in range(3):
            residence_trickle_tick()

        self.assertEqual(waiting_trickles(self.mara.sheet_data), {self.resonance.pk: 12})
        self.assertEqual(self.balance(self.resonance), 0)

        self.ask()
        self.agree(self.crit, self.crit)
        capture = self.capture

        # Two affinities, two bonus checks: Reflection for the Primal part, Villainy for the
        # Abyssal one and the pile waiting in it.
        skills = [[t.trait.name for t in c.extra_traits] for c in self.bonus_calls(capture)]
        self.assertEqual(sorted(skills), [["Reflection"], ["Villainy"]])
        self.assertTold(
            self.mara,
            "Your ritual feeds on Tobin. You recover 6 anima. Your Hollow grows by 4. "
            "Your Reflection check added 50 percent. "
            "18 Ruin waiting from your days arrived. Your Villainy check added 50 percent.",
        )
        self.assertEqual(self.balance(self.resonance), 18)
        self.assertEqual(waiting_trickles(self.mara.sheet_data), {})
        self.assertFalse(TrickleAccrual.objects.filter(harvested_at__isnull=True).exists())
        # Tobin's answer grants the Ruin the ritual held for him, grown by the result it stored,
        # and the line Mara reads for it names the check too.
        self.telnet(self.tobin, "ritual endorse Mara")
        self.assertTold(
            self.mara, "Tobin felt it. Your Ruin grows by 4. Your Villainy check added 50 percent."
        )


class ACastPulledInAnotherAffinityTellsTheCasterWhatItWasWorth(_Skills, _BurningResonance):
    """Ysmay casts with a thread paid by Ruin, an Abyssal resonance, while her cast is worked in
    no Abyssal resonance. Her Villainy check made the pull worth 130 percent."""

    def setUp(self) -> None:
        super().setUp()
        self.author_the_skills()
        ResonanceCheckAwardFactory(
            outcome_tier=ensure_canonical_check_outcome("Success"),
            gain_bonus_percent=0,
            spend_worth_percent=130,
        )
        self.ysmay = self.caster("Ysmay")
        self.ruin = ResonanceFactory(name="Ruin", affinity=self.abyssal)
        self.thread = self.thread_for(self.ysmay, self.ruin)

    @tag("regression")
    def test_the_worth_the_pull_rolled_reaches_the_caster_whatever_resonance_the_cast_is_in(
        self,
    ) -> None:
        """Regression for #5308. A pull paid in an affinity other than the cast resonance's rolled
        its worth, but the cast result dropped it, so the caster's line never said what her check
        made the pull worth."""
        with force_every_check_outcome(ensure_canonical_check_outcome("Success")):
            self.telnet(self.ysmay, f"cast {self.technique.name} pull={self.thread.name}")

        told = strip_ansi(self.said(self.ysmay))
        self.assertIn("Your technique resolves.", told)
        self.assertEqual(self.balance(self.ysmay, self.ruin), 10 - 1)
        self.assertIn("Your Villainy check made it worth 130 percent.", told)
