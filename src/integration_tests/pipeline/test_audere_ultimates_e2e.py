"""E2E (#4098, #4076): Audere unlocks ultimates, and Soulfray death waits for the encounter's end.

Seam 1 (the journey #4076 asks for), all through real services and actions:

    round 1  ``cast <ordinary> at <mook> soulfray`` (CmdDeclareTechnique ->
             dispatch_player_action) -> ``resolve_round`` -> ``use_technique`` fires
             the Audere gate -> ``PendingAudereOffer``.
             POST /api/magic/audere/respond/ accept -> Audere holds.
             GET  /api/magic/audere/ultimates/ -> a CATEGORY card (authored label,
             no technique name or id).
             POST /api/magic/audere/ultimates/choose/ -> revealed, readied,
             ``KnownUltimate`` recorded.
    round 2  ``cast <ultimate> at <mook> soulfray`` -> ``resolve_round`` resolves it.
    end      ``complete_encounter`` -> ``cleanup_completed_encounter`` clears the
             readied flag and Audere.
    again    a second encounter's Audere lists the ultimate BY NAME as a KNOWN card.

Seam 2: in a LETHAL encounter under Audere, a cast that overdraws anima advances
Soulfray into a stage whose pool holds only a ``character_loss`` consequence. The
death is made certain but deferred; the character keeps declaring and resolving
actions in a later round; ``complete_encounter`` applies the death.

Seam 3 (the #4076 replay): in a lethal encounter, a patron's bound being turns the
battle. Audere, the reveal and the choice open the ultimate; casting it manifests the
being as an ally even on a rolled failure (an ultimate never fails); the being acts from
its threat pool in the next round; the martyr's death lands only at the encounter's
end; and the scene's GM is prompted for the surge, the chosen ultimate and the death.

Only randomness is forced: ``world.combat.services.perform_check`` (the combat
offense roll, as in test_combat_cast_telnet_e2e) and
``world.checks.services.perform_check_with_modifiers`` (the Soulfray resilience
roll, returning a fixed outcome tier). Consequence selection, application and the
death seam all run for real.

setUp, not setUpTestData: ObjectDB rows (character location) are mutated, and
SharedMemoryModel instances do not survive setUpTestData's deepcopy.

SQLite tier: both classes run on the fast tier; no ``DISTINCT ON`` path is hit.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models
from rest_framework.test import APITestCase

from actions.constants import ActionBackend
from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.player_interface import get_player_actions
from commands.combat import CmdDeclareTechnique
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.types import CheckResult
from world.combat.constants import (
    ActionCategory,
    CombatAllegiance,
    EncounterOutcome,
    OpponentTier,
    RiskLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatOpponentAction,
    CombatRoundAction,
)
from world.combat.services import (
    add_participant,
    begin_declaration_phase,
    complete_encounter,
    resolve_round,
)
from world.conditions.factories import (
    ConditionInstanceFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.conditions.models import ConditionInstance
from world.covenants.constants import RoleArchetype
from world.gm.constants import GMPromptKind
from world.gm.models import GMPrompt
from world.magic.audere import AUDERE_CONDITION_NAME, PendingAudereOffer
from world.magic.constants import GiftKind, UltimateCardKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterGiftFactory,
    CharacterManifestationFactory,
    EffectTypeFactory,
    GiftFactory,
    PathGiftGrantFactory,
    SoulfrayConfigFactory,
    TechniqueFactory,
    TechniqueManifestOptionFactory,
    UltimateTechniqueFactory,
)
from world.magic.models import CharacterTechnique, KnownUltimate
from world.magic.seeds_cast import ensure_technique_cast_content
from world.magic.tests.audere_test_helpers import build_audere_gate_fixture
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.models import CharacterVitals
from world.vitals.services import can_act
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory
from world.worship.models import PatronageValence

_RESPOND_URL = "/api/magic/audere/respond/"
_ULTIMATES_URL = "/api/magic/audere/ultimates/"
_CHOOSE_URL = "/api/magic/audere/ultimates/choose/"

_SWORD_LABEL = "PLACEHOLDER edge"
_DEATH_TEXT = "PLACEHOLDER the end waits"


def _cast(caller: ObjectDB, args: str) -> None:
    """Drive the real telnet ``cast`` command (CmdDeclareTechnique.func)."""
    cmd = CmdDeclareTechnique()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"cast {args}"
    cmd.cmdname = "cast"
    cmd.func()


class _AudereCombatFixture(APITestCase):
    """An account-owned character, a Soulfray at the Audere gate stage, a mook to fight."""

    tier_suffix = "ult_e2e"
    risk_level = RiskLevel.MODERATE

    def setUp(self) -> None:
        idmapper_models.flush_cache()

        # Audere gate: Soulfray stages 1-3, a major intensity tier, the threshold.
        self.gate = build_audere_gate_fixture(tier_suffix=self.tier_suffix)
        threshold = self.gate.threshold
        threshold.sword_reveal_label = _SWORD_LABEL
        threshold.shield_reveal_label = "PLACEHOLDER wall"
        threshold.crown_reveal_label = "PLACEHOLDER circlet"
        threshold.deferred_death_text = _DEATH_TEXT
        threshold.save()

        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )
        self.action_template = ensure_technique_cast_content()

        # Account-owned sheet (the API auth path walks the roster tenure).
        tenure = RosterTenureFactory()
        self.account = tenure.player_data.account
        self.sheet = tenure.roster_entry.character_sheet
        self.character = self.sheet.character
        room = ObjectDBFactory(db_key="UltimateRoom", db_typeclass_path="typeclasses.rooms.Room")
        self.character.location = room
        self.character.save()
        CharacterVitals.objects.create(character_sheet=self.sheet, health=500, max_health=500)
        self.anima = CharacterAnimaFactory(character=self.sheet, current=100, maximum=100)

        # Major gift on the current path; the (path x gift) grant offers the ultimates.
        self.gift = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        self.grant = PathGiftGrantFactory(gift=self.gift)
        CharacterPathHistoryFactory(character=self.sheet, path=self.grant.path)

        # An ordinary known combat technique that fires the gate: intensity 20 is
        # at the major tier (threshold 15); control 30 keeps it cheap and clean.
        self.ordinary = TechniqueFactory(
            gift=self.gift,
            name="Opening Spark",
            effect_type=EffectTypeFactory(name="Spark E2E", base_power=5),
            intensity=20,
            control=30,
            anima_cost=3,
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
        )
        CharacterTechnique.objects.create(character=self.sheet, technique=self.ordinary)

        # The Soulfray at the gate stage (stage 3). Soulfray is a progression
        # condition that decays by day, never by combat round (the seeded template
        # is PERMANENT), so the instance carries no round countdown.
        ConditionInstanceFactory(
            target=self.character,
            condition=self.gate.soulfray_template,
            current_stage=self.gate.soulfray_stage,
            rounds_remaining=None,
        )

        # The combat offense roll is forced to a full success; a real outcome row
        # rides along so outcome-keyed lookups (TechniqueOutcomeModifier) see a model.
        self.combat_outcome = CheckOutcomeFactory(name="Combat full success E2E", success_level=2)

        self.encounter, self.opponent = self._new_encounter()
        self.client.force_authenticate(user=self.account)

    # -- helpers --------------------------------------------------------------

    def _new_encounter(self) -> tuple[CombatEncounter, CombatOpponent]:
        """A fresh encounter joined through ``add_participant`` (which owns the
        COMBAT engagement) and opened for declarations through
        ``begin_declaration_phase``."""
        encounter = CombatEncounterFactory(
            status=RoundStatus.BETWEEN_ROUNDS, round_number=0, risk_level=self.risk_level
        )
        pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=pool, base_damage=1)
        opponent = CombatOpponentFactory(
            encounter=encounter,
            tier=OpponentTier.MOOK,
            health=5000,
            max_health=5000,
            threat_pool=pool,
        )
        add_participant(encounter, self.sheet)
        begin_declaration_phase(encounter)
        encounter.refresh_from_db()
        return encounter, opponent

    def _resolve(self, encounter: CombatEncounter) -> None:
        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2, outcome=self.combat_outcome)
            resolve_round(encounter)
        encounter.refresh_from_db()

    def _accept_offer(self) -> None:
        offer = PendingAudereOffer.objects.get(character_sheet=self.sheet)
        response = self.client.post(
            _RESPOND_URL, {"offer_id": offer.pk, "accept": True}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["accepted"])

    def _state(self) -> dict:
        response = self.client.get(_ULTIMATES_URL, {"character_sheet_id": self.sheet.pk})
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def _focused(self, encounter: CombatEncounter) -> CombatRoundAction:
        return CombatRoundAction.objects.get(
            participant__encounter=encounter,
            participant__character_sheet=self.sheet,
            round_number=encounter.round_number,
        )

    def _in_audere(self) -> bool:
        return ConditionInstance.objects.filter(
            target=self.character, condition__name=AUDERE_CONDITION_NAME
        ).exists()


class AudereUltimateJourneyTests(_AudereCombatFixture):
    """Reach Audere, choose an undiscovered ultimate, cast it; next time it is known."""

    def setUp(self) -> None:
        super().setUp()
        self.ultimate = UltimateTechniqueFactory(
            gift=self.gift,
            name="Sundering Verdict",
            archetype_alignment=RoleArchetype.SWORD,
            effect_type=EffectTypeFactory(name="Verdict E2E", base_power=20),
            intensity=20,
            control=30,
            anima_cost=3,
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
        )
        self.grant.ultimate_techniques.add(self.ultimate)

    def _reach_audere(self, encounter: CombatEncounter, opponent: CombatOpponent) -> None:
        """Round 1 of an encounter: the ordinary cast opens the gate; accept it."""
        _cast(self.character, f"{self.ordinary.name} at {opponent.name} soulfray")
        self.assertEqual(self._focused(encounter).focused_action, self.ordinary)
        self._resolve(encounter)
        self.assertTrue(PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists())
        self._accept_offer()
        self.assertTrue(self._in_audere())

    def test_audere_reveal_choose_cast_known_then_named_next_time(self) -> None:
        # 1-2. Reach Audere in a real encounter; the offer is made and accepted.
        self._reach_audere(self.encounter, self.opponent)

        # 3. The reveal shows the undiscovered ultimate as a category card only.
        state = self._state()
        self.assertIsNotNone(state["reveal"])
        cards = [card for group in state["reveal"]["groups"] for card in group["cards"]]
        self.assertEqual(len(cards), 1)
        (card,) = cards
        self.assertEqual(card["kind"], UltimateCardKind.CATEGORY)
        self.assertEqual(card["label"], _SWORD_LABEL)
        self.assertEqual(card["name"], "")
        self.assertEqual(card["description"], "")
        self.assertNotIn(self.ultimate.name, str(state))
        self.assertNotIn(str(self.ultimate.pk), card["choice_key"].split(":"))

        # 4. Choose the card: revealed, readied, recorded.
        response = self.client.post(
            _CHOOSE_URL,
            {"character_sheet_id": self.sheet.pk, "choice_key": card["choice_key"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["name"], self.ultimate.name)
        self.assertEqual(response.data["label"], _SWORD_LABEL)
        known = KnownUltimate.objects.get(character=self.sheet, technique=self.ultimate)
        self.assertTrue(known.readied)
        self.assertIsNone(self._state()["reveal"])  # chosen: the reveal closes

        # 5. Declare it as the round-2 combat action through the normal path.
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        offered = {
            a.ref.technique_id
            for a in get_player_actions(self.character)
            if a.backend == ActionBackend.COMBAT
        }
        self.assertIn(self.ultimate.pk, offered)
        health_before = CombatOpponent.objects.get(pk=self.opponent.pk).health
        _cast(self.character, f"{self.ultimate.name} at {self.opponent.name} soulfray")
        self.assertEqual(self._focused(self.encounter).focused_action, self.ultimate)
        self._resolve(self.encounter)
        self.opponent.refresh_from_db()
        self.assertLess(self.opponent.health, health_before, "the ultimate resolved as damage")

        # 6. The encounter ends: the readied flag and Audere are cleared.
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        known = KnownUltimate.objects.get(pk=known.pk)
        self.assertFalse(known.readied)
        self.assertFalse(self._in_audere())
        self.assertFalse(
            CharacterEngagement.objects.filter(
                character_id=self.sheet.pk, engagement_type=EngagementType.COMBAT
            ).exists()
        )

        # 7. A second Audere, in a new encounter, lists it BY NAME as KNOWN.
        encounter2, opponent2 = self._new_encounter()
        self._reach_audere(encounter2, opponent2)
        state = self._state()
        self.assertIsNotNone(state["reveal"])
        cards = [card for group in state["reveal"]["groups"] for card in group["cards"]]
        self.assertEqual(
            [(c["kind"], c["name"]) for c in cards],
            [(UltimateCardKind.KNOWN, self.ultimate.name)],
        )
        self.assertEqual(cards[0]["description"], self.ultimate.description)


class _LethalAudereFixture(_AudereCombatFixture):
    """A lethal encounter whose gate-stage Soulfray pool holds only ``character_loss``."""

    tier_suffix = "ult_e2e_death"
    risk_level = RiskLevel.LETHAL

    def setUp(self) -> None:
        super().setUp()
        # Soulfray accrues once the post-cast pool sits below 30%; the gate stage's
        # pool holds one consequence, and it is character_loss.
        self.soulfray_config = SoulfrayConfigFactory(resilience_check_type=CheckTypeFactory())
        self.loss_tier = CheckOutcomeFactory(name="Soulfray loss tier E2E", success_level=-3)
        pool = ConsequencePoolFactory(name="Soulfray lethal E2E")
        ConsequencePoolEntryFactory(
            pool=pool,
            consequence=ConsequenceFactory(
                outcome_tier=self.loss_tier, label="Soul lost E2E", character_loss=True
            ),
        )
        stage = self.gate.soulfray_stage
        stage.consequence_pool = pool
        stage.save(update_fields=["consequence_pool"])

        # A cast that overdraws the pool, so it draws Soulfray.
        self.overdraw = TechniqueFactory(
            gift=self.gift,
            name="Hollowing Torrent",
            effect_type=EffectTypeFactory(name="Torrent E2E", base_power=5),
            intensity=20,
            control=20,
            anima_cost=400,
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
        )
        CharacterTechnique.objects.create(character=self.sheet, technique=self.overdraw)

    def _resolve_with_resilience_roll(self, encounter: CombatEncounter) -> None:
        """Resolve a round, fixing the Soulfray resilience roll to the loss tier."""
        with patch(
            "world.checks.services.perform_check_with_modifiers",
            return_value=MagicMock(outcome=self.loss_tier),
        ):
            self._resolve(encounter)

    def _vitals(self) -> CharacterVitals:
        return CharacterVitals.objects.get(character_sheet=self.sheet)


class DeferredDeathJourneyTests(_LethalAudereFixture):
    """A certain Soulfray death under Audere waits for the lethal encounter's end."""

    def test_lethal_soulfray_in_audere_waits_for_encounter_end(self) -> None:
        self.assertTrue(self.encounter.is_lethal)

        # Round 1: the ordinary cast opens the gate (pool stays full, no Soulfray
        # accrues, so the lethal stage pool does not fire yet); accept Audere.
        _cast(self.character, f"{self.ordinary.name} at {self.opponent.name} soulfray")
        self._resolve_with_resilience_roll(self.encounter)
        self.assertEqual(self._vitals().life_state, CharacterLifeState.ALIVE)
        self.assertFalse(self._vitals().death_certain_pending)
        self._accept_offer()
        self.assertTrue(self._in_audere())

        # Round 2: the overdraw draws Soulfray; the stage pool rolls character_loss.
        # Audere defers it: certain, pending, still alive, told.
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        _cast(self.character, f"{self.overdraw.name} at {self.opponent.name} soulfray")
        self._resolve_with_resilience_roll(self.encounter)
        vitals = self._vitals()
        self.assertTrue(vitals.death_certain_pending)
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)
        self.assertTrue(can_act(self.sheet))
        self.assertEqual(self._state()["deferred_death_text"], _DEATH_TEXT)

        # Round 3: the character keeps acting -- declared and resolved.
        self.assertEqual(self.encounter.status, RoundStatus.BETWEEN_ROUNDS)
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        offered = [
            a for a in get_player_actions(self.character) if a.backend == ActionBackend.COMBAT
        ]
        self.assertTrue(offered, "a certain-but-deferred death must not stop declaration")
        health_before = CombatOpponent.objects.get(pk=self.opponent.pk).health
        _cast(self.character, f"{self.ordinary.name} at {self.opponent.name} soulfray")
        self.assertEqual(self._focused(self.encounter).focused_action, self.ordinary)
        self._resolve_with_resilience_roll(self.encounter)
        self.opponent.refresh_from_db()
        self.assertLess(self.opponent.health, health_before, "the round-3 cast resolved")
        self.assertEqual(self._vitals().life_state, CharacterLifeState.ALIVE)

        # The encounter completes: the death applies, the flag clears.
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        vitals = self._vitals()
        self.assertEqual(vitals.life_state, CharacterLifeState.DEAD)
        self.assertFalse(vitals.death_certain_pending)


class BoundBeingTurnsBattleTests(_LethalAudereFixture):
    """The #4076 replay: Audere, a patron's ultimate, the being arrives and fights, the
    martyr dies at the end, and the scene's GM is prompted for each moment."""

    tier_suffix = "ult_e2e_being"

    def setUp(self) -> None:
        super().setUp()
        # The scene at the character's room, run by a GM who is not the player.
        self.gm = AccountFactory()
        scene = SceneFactory(location=self.character.location)
        SceneGMParticipationFactory(scene=scene, account=self.gm)

        # A being the character is devoted to: its avatar body, an ultimate it grants,
        # and what the avatar does each round once it has arrived.
        self.avatar_sheet = CharacterSheetFactory()
        self.being = WorshippedBeingFactory(avatar_sheet=self.avatar_sheet)
        DevotionStandingFactory(
            character_sheet=self.sheet, being=self.being, valence=PatronageValence.DEVOTIONAL
        )
        self.ultimate = UltimateTechniqueFactory(
            gift=self.gift,
            name="Descent Of The Patron",
            archetype_alignment=RoleArchetype.CROWN,
            effect_type=EffectTypeFactory(name="Descent E2E", base_power=20),
            intensity=20,
            control=30,
            anima_cost=3,
            action_category=ActionCategory.PHYSICAL,
            action_template=self.action_template,
        )
        self.being.ultimate_techniques.add(self.ultimate)
        self.avatar_pool = ThreatPoolFactory()
        ThreatPoolEntryFactory(pool=self.avatar_pool, name="Avatar strike", base_damage=40)
        option = TechniqueManifestOptionFactory(
            technique=self.ultimate,
            being=self.being,
            tier=OpponentTier.BOSS,
            threat_pool=self.avatar_pool,
        )
        CharacterManifestationFactory(character=self.sheet, technique=self.ultimate, option=option)
        OpponentTierTemplateFactory(tier=OpponentTier.BOSS, base_health=200)

        # The roll that would sink an ordinary cast: an ultimate must not fail on it.
        self.fumble = CheckOutcomeFactory(name="Fumble E2E", success_level=-2)

    def _resolve_rolling(self, encounter: CombatEncounter, outcome) -> None:
        """Resolve a round with the offense roll fixed to ``outcome`` (a real result, so
        the resolver's own handling of it runs) and the Soulfray roll fixed to the loss."""
        result = CheckResult(
            check_type=CheckTypeFactory(),
            outcome=outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        with (
            patch("world.combat.services.perform_check", return_value=result),
            patch(
                "world.checks.services.perform_check_with_modifiers",
                return_value=MagicMock(outcome=self.loss_tier),
            ),
        ):
            resolve_round(encounter)
        encounter.refresh_from_db()

    def _prompt_kinds(self) -> set[str]:
        return set(GMPrompt.objects.filter(addressed_to=self.gm).values_list("kind", flat=True))

    def test_patron_ultimate_brings_the_being_who_fights_and_the_death_lands_last(self) -> None:
        # Round 1: the ordinary cast opens the gate; accepting Audere prompts the GM.
        _cast(self.character, f"{self.ordinary.name} at {self.opponent.name} soulfray")
        self._resolve(self.encounter)
        self._accept_offer()
        self.assertTrue(self._in_audere())
        self.assertEqual(self._prompt_kinds(), {GMPromptKind.AUDERE_SURGE})

        # The reveal offers the patron's ultimate; choosing it prompts the GM again.
        cards = [c for g in self._state()["reveal"]["groups"] for c in g["cards"]]
        self.assertEqual(len(cards), 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                _CHOOSE_URL,
                {"character_sheet_id": self.sheet.pk, "choice_key": cards[0]["choice_key"]},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["name"], self.ultimate.name)
        self.assertEqual(
            self._prompt_kinds(), {GMPromptKind.AUDERE_SURGE, GMPromptKind.AUDERE_ULTIMATE}
        )

        # Round 2: the ultimate is cast on a roll that would be a failure. It still
        # succeeds, and the being arrives as an ally of the caster's side.
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        _cast(self.character, f"{self.ultimate.name} at {self.opponent.name} soulfray")
        self.assertEqual(self._focused(self.encounter).focused_action, self.ultimate)
        self._resolve_rolling(self.encounter, self.fumble)
        avatar = CombatOpponent.objects.get(
            encounter=self.encounter, objectdb=self.avatar_sheet.character
        )
        self.assertEqual(avatar.allegiance, CombatAllegiance.ALLY)
        self.assertEqual(avatar.tier, OpponentTier.BOSS)
        self.assertEqual(avatar.summoned_by, self.sheet)
        self.assertFalse(CombatOpponentAction.objects.filter(opponent=avatar).exists())

        # Round 3: the overdraw makes the death certain but deferred; the being acts
        # from its pool against the enemy, which is what turns the fight.
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        _cast(self.character, f"{self.overdraw.name} at {self.opponent.name} soulfray")
        self._resolve_rolling(self.encounter, self.combat_outcome)
        self.assertTrue(self._vitals().death_certain_pending)
        self.assertEqual(self._vitals().life_state, CharacterLifeState.ALIVE)
        strike = CombatOpponentAction.objects.get(opponent=avatar)
        self.assertEqual(strike.round_number, self.encounter.round_number)
        self.assertEqual(list(strike.opponent_targets.all()), [self.opponent])
        self.assertNotIn(GMPromptKind.DEATH, self._prompt_kinds())

        # The encounter ends: the death lands then, and the GM is prompted for it.
        complete_encounter(self.encounter, outcome=EncounterOutcome.VICTORY)
        self.assertEqual(self._vitals().life_state, CharacterLifeState.DEAD)
        self.assertEqual(
            self._prompt_kinds(),
            {GMPromptKind.AUDERE_SURGE, GMPromptKind.AUDERE_ULTIMATE, GMPromptKind.DEATH},
        )
