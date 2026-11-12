"""Journeys for pacts with beings (#4341, spec section 8): a patron gained in play.

Corwen has no patron. She holds a pledge to Hesk that carries Hesk's pact offer: she
reads it on ``pledge``, closes with ``pledge/close/accept`` at a pinned Success, and
the pact is signed. Her pact card reads the same on ``pact`` and over the API. Kell
closes the same kind of pledge with a plain ``pledge/close`` and holds nothing.

With the pact, Hesk is Corwen's patron without her being Hesk's Chosen. ``invoke
Hesk`` shows the pact's first stage easing the call and no Chosen line. ``manifest
Summon=Hesk`` sets what her technique brings, and casting it in a real round brings
Hesk's avatar to her side. At Audere, Hesk's bond ultimate is among her choices.

The project tick grades each period once its time limit has passed (the journeys move
the limit into the past rather than waiting). A short period inside the stage only
raises severity. A second short period crosses into Strained, so the stage's resist
check rolls (pinned at Failure) and Strained applies. A met period eases severity.
``pact/renounce Hesk`` ends the pact and releases her, and one more tick eases the
condition until it is gone. Only Corwen is told any of this; the onlooker in the room
hears nothing.

Ilse is Morrow's Chosen through the designated Chosen distinction. She keeps her
Chosen invocation line and earning rate with Morrow and, holding a pact with Hesk as
well, gets neither with Hesk. A breach, when the last stage's resist
fails, ends the pact, releases the patronage, tells her the closing text and gives the
room only the authored onlooker line.

Every roll is pinned with ``force_check_outcome``. Journeys run on the parity tier:
signing applies the staged condition through a PostgreSQL ``DISTINCT ON``. Other
journeys for this feature: the offer's text and the web close in
``world.pacts.tests.test_accept_at_close``, the card's permissions and the web renounce
in ``integration_tests.test_pact_card_journeys``, the technique picker in
``integration_tests.test_manifest_picker_journeys``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.action_points.factories import ActionPointPoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.combat.constants import ActionCategory, CombatAllegiance, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    OpponentTierTemplateFactory,
)
from world.combat.models import CombatEncounter, CombatOpponent
from world.combat.services import add_participant, resolve_round
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import advance_condition_severity
from world.fatigue.constants import EffortLevel
from world.game_clock.week_services import advance_game_week
from world.magic.constants import GainSource, UltimateCardKind, UltimateSource
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueManifestOptionFactory,
    UltimateTechniqueFactory,
    ensure_audere_designations,
    wire_audere_power_multipliers,
)
from world.magic.services.resonance import grant_resonance
from world.pacts.constants import CharacterPactCommitmentKind, CharacterPactEnding
from world.pacts.factories import (
    PactOfferCommitmentFactory,
    PactOfferFactory,
    make_pact_condition,
)
from world.pacts.models import CharacterPact, PactPeriodDetails
from world.pacts.services import sign_being_pact
from world.projects.constants import ProjectKind, ProjectStatus
from world.projects.models import Project
from world.projects.services import scan_active_projects
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals
from world.worship.constants import BeingResonanceTier, FavorAwardKind, RiteTier
from world.worship.factories import (
    BeingResonanceFactory,
    FavorOutcomeAwardFactory,
    PledgeFactory,
    RiteKindFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
    WorshipRiteTierAwardFactory,
    make_chosen,
)
from world.worship.favor_services import ensure_being_modifier_targets
from world.worship.invocation_services import get_devotion_config
from world.worship.models import DevotionStanding, PatronageValence
from world.worship.pledge_services import take_pledge
from world.worship.services import bump_devotion

CARDS_URL = "/api/pacts/cards/"
ULTIMATES_URL = "/api/magic/audere/ultimates/"
CONDITION_NAME = "Bound to Hesk"

_OUTCOMES = (
    ("Critical Success", 2),
    ("Success", 1),
    ("Partial Success", 0),
    ("Failure", -1),
    ("Critical Failure", -2),
)


@contextmanager
def every_combat_check_at(outcome: CheckOutcome) -> Iterator[None]:
    """Every combat check in the block lands at ``outcome`` (the round's check seam)."""

    def forced(*args: object, **kwargs: object) -> CheckResult:
        with force_check_outcome(outcome):
            return perform_check(*args, **kwargs)

    with patch("world.combat.services.perform_check", side_effect=forced):
        yield


class PactJourneyBase(JourneyCase):
    """Hesk offers a pact on a pledge; Corwen and Hobb stand in the Hollow's scene."""

    def setUp(self) -> None:
        super().setUp()
        self.outcomes = {
            name: CheckOutcomeFactory(name=name, success_level=level) for name, level in _OUTCOMES
        }
        config = get_devotion_config()
        FavorOutcomeAwardFactory(
            config=config,
            kind=FavorAwardKind.CLOSING,
            outcome_tier=self.outcomes["Success"],
            amount=5,
        )
        config.invocation_check_type = CheckTypeFactory()
        config.save(update_fields=["invocation_check_type"])
        for outcome in self.outcomes.values():
            WorshipRiteTierAwardFactory(tier=RiteTier.DEVOTIONAL, outcome_tier=outcome)

        self.room = self.make_room("Hollow")
        self.scene = SceneFactory(location=RoomProfileFactory(objectdb=self.room), is_active=True)

        self.hesk = WorshippedBeingFactory(name="Hesk", avatar_sheet=CharacterSheetFactory())
        invocation_target, _earning = ensure_being_modifier_targets(self.hesk)
        self.hesk_resonance = BeingResonanceFactory(
            being=self.hesk, tier=BeingResonanceTier.FAVORED
        ).resonance
        condition = make_pact_condition(name=CONDITION_NAME)
        self.sworn = condition.stages.get(stage_order=1)
        # The first stage's boon: calling on Hesk is 15 points easier while Sworn.
        ConditionModifierEffectFactory(
            condition=None, stage=self.sworn, modifier_target=invocation_target, value=15
        )
        self.offer = PactOfferFactory(
            being=self.hesk,
            name="Hesk pact",
            offer_text="[offer text]",
            closing_text="[closing text]",
            onlooker_line="[onlooker line]",
            condition=condition,
        )
        PactOfferCommitmentFactory(offer=self.offer, amount=8)
        PactOfferCommitmentFactory(
            offer=self.offer, kind=CharacterPactCommitmentKind.CUSTOM, amount=0, notes="[promise]"
        )
        self.rite = WorshipRiteFactory(
            being=self.hesk,
            kind=RiteKindFactory(name="Vigil", tier=RiteTier.DEVOTIONAL),
            name="Hesk's rite",
        )
        self.pledge = PledgeFactory(
            being=self.hesk,
            name="The Ash Vow",
            favor_target=12,
            closing_rite=self.rite,
            pact_offer=self.offer,
        )

        self.corwen = self.player("Corwen")
        self.hobb = self.player("Hobb")
        self.watch(self.hobb)

    # -- the world ------------------------------------------------------------------

    def player(self, name: str) -> ObjectDB:
        """A player in the Hollow's scene with action points to perform a rite."""
        character = self.make_player(name, room=self.room)
        SceneParticipationFactory(scene=self.scene, account=self.account_of(character))
        ActionPointPoolFactory(character=character.sheet_data, current=10, maximum=10)
        return character

    def pledged(self, character: ObjectDB) -> None:
        """``character`` holds the Ash Vow with its favor target already met."""
        details = take_pledge(character.sheet_data, self.pledge)
        details.project.current_progress = 12
        details.project.save(update_fields=["current_progress"])

    def close(self, character: ObjectDB, line: str, outcome: str = "Success") -> str:
        with force_check_outcome(self.outcomes[outcome]):
            return self.telnet(character, line)

    def sign_corwen(self) -> CharacterPact:
        """Corwen accepts Hesk's pact at the close, at a pinned Success."""
        self.pledged(self.corwen)
        told = self.close(self.corwen, "pledge/close/accept")
        self.assertIn("Hesk is now your patron. Your pact begins.", told)
        return CharacterPact.objects.get(character_sheet=self.corwen.sheet_data)

    # -- what she reads ---------------------------------------------------------------

    def cards(self, character: ObjectDB) -> list[dict]:
        response = self.api(self.account_of(character)).get(
            CARDS_URL, {"character_sheet": character.sheet_data.pk}
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def standing(self, character: ObjectDB, being=None) -> DevotionStanding:
        return DevotionStanding.objects.get(
            character_sheet=character.sheet_data, being=being or self.hesk
        )

    # -- serving and the tick ---------------------------------------------------------

    def deed(self, character: ObjectDB, amount: int) -> None:
        """A deed that grants a resonance Hesk favors (a mission, a scene)."""
        grant_resonance(
            character.sheet_data, self.hesk_resonance, amount, source=GainSource.COMPROMISE
        )

    def period_ends(self, character: ObjectDB) -> None:
        """Her open pact periods reach their time limit; the project tick runs; the
        game week rolls over (the deed cap is weekly)."""
        projects = Project.objects.filter(
            kind=ProjectKind.PACT_PERIOD,
            status=ProjectStatus.ACTIVE,
            pact_period_details__pact__character_sheet=character.sheet_data,
        )
        for project in projects:
            project.time_limit = timezone.now() - timedelta(minutes=1)
            project.save(update_fields=["time_limit"])
        scan_active_projects()
        advance_game_week()

    def condition(self, character: ObjectDB) -> ConditionInstance | None:
        return ConditionInstance.objects.filter(
            target=character, condition__name=CONDITION_NAME
        ).first()


class AcceptingAPactAtTheClose(PactJourneyBase):
    def test_corwen_reads_the_offer_accepts_at_success_and_holds_the_pact(self) -> None:
        self.pledged(self.corwen)
        told = self.telnet(self.corwen, "pledge")
        self.assertIn("Offered at the close: a pact with Hesk.", told)
        self.assertIn("1. Sworn: +15 Hesk favor invocation", told)
        self.assertIn("pledge/close/accept", told)

        told = self.close(self.corwen, "pledge/close/accept")

        self.assertIn("Hesk is now your patron. Your pact begins.", told)
        standing = self.standing(self.corwen)
        self.assertEqual(standing.valence, PatronageValence.PACT)
        self.assertEqual(self.condition(self.corwen).current_stage, self.sworn)
        told = self.telnet(self.corwen, "pact")
        self.assertIn("Hesk - 0 of 8 favor this period", told)
        self.assertIn("Stage: Sworn (severity 1; next at 11).", told)
        self.assertIn("You promised: [promise]", told)
        (card,) = self.cards(self.corwen)
        self.assertEqual((card["being_name"], card["earned"], card["required"]), ("Hesk", 0, 8))
        self.assertEqual((card["stage_name"], card["severity"]), ("Sworn", 1))
        self.assertTrue(card["is_active"])
        self.assertNotTold(self.hobb, "Hesk is now your patron")

    def test_kell_closes_without_accepting_and_holds_nothing(self) -> None:
        kell = self.player("Kell")
        self.pledged(kell)

        told = self.close(kell, "pledge/close")

        self.assertNotIn("Your pact begins", told)
        self.assertFalse(CharacterPact.objects.filter(character_sheet=kell.sheet_data).exists())
        self.assertFalse(
            PactPeriodDetails.objects.filter(pact__character_sheet=kell.sheet_data).exists()
        )
        self.assertFalse(
            DevotionStanding.objects.filter(
                character_sheet=kell.sheet_data, valence__isnull=False
            ).exists()
        )
        self.assertIsNone(self.condition(kell))
        self.assertNotIn("Hesk - ", self.telnet(kell, "pact"))
        self.assertEqual(self.cards(kell), [])


class ServingThePact(PactJourneyBase):
    def setUp(self) -> None:
        super().setUp()
        self.pact = self.sign_corwen()

    def test_her_patron_eases_the_call_but_she_is_not_its_chosen(self) -> None:
        told = self.telnet(self.corwen, "invoke Hesk")

        self.assertIn("Hesk (favor 5)", told)
        self.assertIn("Favor invocation modifiers for Hesk: -15", told)
        self.assertNotIn("Chosen", told)

    def fight(self) -> tuple[CombatEncounter, CombatOpponent]:
        """Corwen joins a fight in the Hollow against one opponent."""
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        sheet = self.corwen.sheet_data
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        add_participant(encounter, sheet)
        return encounter, CombatOpponentFactory(encounter=encounter)

    def test_her_summoning_technique_brings_hesk_into_a_fight(self) -> None:
        CheckSystemSetupFactory.create()
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=1)
        OpponentTierTemplateFactory(tier=OpponentTier.BOSS, base_health=200)
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        summon = TechniqueFactory(
            name="Summon",
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        CharacterTechniqueFactory(character=self.corwen.sheet_data, technique=summon)
        TechniqueManifestOptionFactory(technique=summon, being=self.hesk, tier=OpponentTier.BOSS)

        told = self.telnet(self.corwen, "manifest Summon=Hesk")
        self.assertIn("Summon will bring Hesk into a fight.", told)

        encounter, opponent = self.fight()
        ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=summon.pk, action_slot="focused")
        declared = dispatch_player_action(
            self.corwen,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": opponent.pk},
        )
        self.assertTrue(declared.deferred, declared)
        with every_combat_check_at(self.outcomes["Success"]):
            resolve_round(encounter)

        avatar = CombatOpponent.objects.get(
            encounter=encounter, objectdb=self.hesk.avatar_sheet.character
        )
        self.assertEqual(avatar.name, "Hesk")
        self.assertEqual(avatar.allegiance, CombatAllegiance.ALLY)
        self.assertEqual(avatar.tier, OpponentTier.BOSS)
        self.assertEqual(avatar.summoned_by, self.corwen.sheet_data)

    def test_hesks_ultimate_is_among_her_choices_at_audere(self) -> None:
        ultimate = UltimateTechniqueFactory(name="Hesk Unbound")
        self.hesk.ultimate_techniques.add(ultimate)
        audere, _majora = wire_audere_power_multipliers()
        ensure_audere_designations()
        self.fight()
        ConditionInstanceFactory(target=self.corwen, condition=audere)
        client = self.api(self.account_of(self.corwen))
        query = {"character_sheet_id": self.corwen.sheet_data.pk}

        response = client.get(ULTIMATES_URL, query)

        self.assertEqual(response.status_code, 200, response.content)
        (group,) = response.json()["reveal"]["groups"]
        self.assertEqual((group["source"], group["being_name"]), (UltimateSource.PATRON, "Hesk"))
        (card,) = group["cards"]
        self.assertEqual(card["kind"], UltimateCardKind.CATEGORY)

        self.telnet(self.corwen, "pact/renounce Hesk")
        self.assertIsNone(client.get(ULTIMATES_URL, query).json()["reveal"])

    def test_she_falls_short_twice_then_serves_then_renounces_and_it_eases_away(self) -> None:
        self.connect_telnet(self.corwen)
        instance = self.condition(self.corwen)

        # A short period inside the stage only raises severity: 3 of 8 is 7 more.
        self.deed(self.corwen, 3)
        self.period_ends(self.corwen)
        self.assertTold(self.corwen, "Your pact with Hesk: 3 of 8 favor this period, 5 short.")
        self.assertTold(self.corwen, "Severity rises by 7 (to 8). No stage change.")

        # The next short period would reach Strained, so Strained's resist check rolls.
        self.deed(self.corwen, 3)
        with force_check_outcome(self.outcomes["Failure"]) as roll:
            self.period_ends(self.corwen)
        self.assertEqual(roll.target_difficulty, 10)
        self.assertTold(
            self.corwen,
            "That would raise severity by 7 (to 15) and reach Strained. Resist check: 10. "
            "Result: Failure, so the full rise applies.",
        )
        self.assertTold(self.corwen, "Strained now applies. Earn 8 next period to ease it by 10.")
        instance.refresh_from_db()
        self.assertEqual((instance.severity, instance.current_stage.name), (15, "Strained"))
        (card,) = self.cards(self.corwen)
        self.assertEqual((card["stage_name"], card["severity"]), ("Strained", 15))

        # A met period eases severity, back under Strained.
        self.deed(self.corwen, 8)
        self.assertIn("Hesk - 8 of 8 favor this period", self.telnet(self.corwen, "pact"))
        self.period_ends(self.corwen)
        self.assertTold(self.corwen, "Your pact with Hesk: 8 of 8 favor this period.")
        self.assertTold(self.corwen, "Severity eases by 10 (to 5).")
        instance.refresh_from_db()
        self.assertEqual((instance.severity, instance.current_stage.name), (5, "Sworn"))

        # She renounces: released, and the card shows the cost easing out.
        told = self.telnet(self.corwen, "pact/renounce Hesk")
        self.assertIn("You renounce your pact with Hesk.", told)
        self.assertTold(self.corwen, "Hesk is no longer your patron.")
        self.pact.refresh_from_db()
        self.assertEqual(self.pact.dissolution_reason, CharacterPactEnding.RENOUNCED)
        self.assertIsNotNone(self.standing(self.corwen).released_at)
        self.assertIn(
            "Hesk (ended). Sworn eases by 10 each period until it is gone.",
            self.telnet(self.corwen, "pact"),
        )
        (card,) = self.cards(self.corwen)
        self.assertFalse(card["is_active"])

        # One more tick eases the last 5 away and the condition is gone.
        self.period_ends(self.corwen)
        self.assertTold(self.corwen, f"{CONDITION_NAME} is gone.")
        self.assertIsNone(self.condition(self.corwen))
        self.assertEqual(self.cards(self.corwen), [])

        # The room heard none of it.
        self.assertNotTold(self.hobb, "Hesk")
        self.assertEqual(self.mailbox(self.hobb).rows, [])


class AChosenAndAPactHolder(PactJourneyBase):
    def terms(self, character: ObjectDB, being) -> dict:
        response = self.api(self.account_of(character)).get(
            f"/api/worship/beings/{being.pk}/service-terms/",
            {"character_sheet": character.sheet_data.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["rate"]

    def test_only_the_chosen_has_the_chosen_ease_and_earning_rate(self) -> None:
        morrow = WorshippedBeingFactory(name="Morrow")
        ensure_being_modifier_targets(morrow)
        ilse = self.player("Ilse")
        make_chosen(ilse.sheet_data, morrow, favor=44)
        sign_being_pact(ilse.sheet_data, self.offer)
        bump_devotion(ilse.sheet_data, self.hesk, 2)
        self.sign_corwen()

        self.assertIn("You are Morrow's Chosen: -30", self.telnet(ilse, "invoke Morrow"))
        self.assertEqual(
            self.terms(ilse, morrow),
            {"base": 100, "chosen_bonus": 100, "modifiers": 0, "worn_bonus": 0, "total": 200},
        )

        # A pact makes Hesk a patron, never one she is the Chosen of: neither has the
        # Chosen line or bonus with Hesk, Ilse's Chosen distinction notwithstanding.
        for character in (ilse, self.corwen):
            with self.subTest(character=character.key):
                told = self.telnet(character, "invoke Hesk")
                self.assertIn("Favor invocation modifiers for Hesk: -15", told)
                self.assertNotIn("Chosen", told)
                self.assertEqual(
                    self.terms(character, self.hesk),
                    {"base": 100, "chosen_bonus": 0, "modifiers": 0, "worn_bonus": 0, "total": 100},
                )


class BreachingAPact(PactJourneyBase):
    def test_a_failed_last_stage_resist_ends_the_pact_and_the_room_hears_only_its_line(
        self,
    ) -> None:
        pact = self.sign_corwen()
        self.connect_telnet(self.corwen)
        # Two short periods ago she reached Soured; this one misses entirely.
        advance_condition_severity(pact.condition_instance, 24)

        with force_check_outcome(self.outcomes["Failure"]):
            self.period_ends(self.corwen)

        self.assertTold(self.corwen, "reach Breached. Resist check: 10. Result: Failure")
        self.assertTold(self.corwen, "[closing text]")
        self.assertTold(self.corwen, "Hesk is no longer your patron.")
        self.assertTold(self.corwen, "Breached eases by 10 each period until it is gone.")
        pact.refresh_from_db()
        self.assertEqual(pact.dissolution_reason, CharacterPactEnding.BREACH)
        self.assertIsNotNone(self.standing(self.corwen).released_at)
        self.assertTrue(
            PactPeriodDetails.objects.filter(
                pact=pact, commitment__isnull=True, project__status=ProjectStatus.ACTIVE
            ).exists()
        )
        (card,) = self.cards(self.corwen)
        self.assertFalse(card["is_active"])

        self.assertShownRow(self.hobb, "[onlooker line]")
        self.assertNotTold(self.hobb, "[closing text]")
        self.assertNotTold(self.hobb, "patron")
