"""Journeys for rolled surges (#4737, slice 1 of #4727): a roll with degrees raises intensity.

Mira and Tomas are played fighters in one escalating encounter in "The Road", against a
Bandit Captain. Staff have authored a surge tuning per beat, with a degree band per roll
outcome. The bands built here are the expected numbers: a Partial result surges 3, a
Success 6 (taunt and rally), and a Success on a hurt ally's roll is worth 15 at full wound.

- The captain's taunt entry (an authored opponent action) deals no damage; Mira rolls
  Composure against its potency, and a better result surges her more. The roll line reaches
  Mira and nobody else; the room is told only the curve's generic surge line.
- Mira taunts Tomas by name. His Composure roll is against Mira's own taunt rating (no dice
  for her), and a band's condition and control change land on him.
- A band that applies a debuff condition carrying a real check penalty leaves the surged
  player's next check lower, for an opponent's taunt and a player's alike.
- The round payload gives the surged player, a GM and staff the roll, and a bystander only
  the generic beat; the roll is the line the surged player was told.
- Mira rallies Tomas through ``combat rally``; the Rally roll's result picks Tomas's surge,
  he ends up with the condition staff designated for a rally (Inspired), and the next
  round's rally surges him again.
- Mira is bonded to Tomas. The captain wounds Tomas through a real round; the damage event
  reaches the escalation trigger the round-opening installed in the room, and Mira's surge
  is in proportion to the wound.

Rolls are forced with ``force_check_outcome`` (a single shot per ``with``), so each
outcome is chosen by the test and the degrees are deterministic.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import override_settings

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.checks.constants import LEVEL_POINTS_PER_LEVEL
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import collect_check_modifiers
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import (
    RALLY_BASE_DIFFICULTY,
    CombatManeuver,
    ParticipantStatus,
    SurgeTriggerKind,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SocialManeuverConfigFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
    ThreatPoolEntryFactory,
    wire_escalation_content,
)
from world.combat.models import CombatRoundAction, DramaticSurgeRecord
from world.combat.services import begin_declaration_phase, resolve_round
from world.conditions.factories import ConditionCheckModifierFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.services import begin_engagement
from world.relationships.constants import TypeValence
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipLabelFactory,
    RelationshipTypeFactory,
)
from world.relationships.models import CharacterRelationship
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneParticipationFactory
from world.traits.factories import (
    CharacterTraitValueFactory,
    CheckOutcomeFactory,
    StatTraitFactory,
)
from world.traits.models import PointConversionRange, TraitType
from world.vitals.models import CharacterVitals

PARTIAL_INTENSITY = 3
SUCCESS_INTENSITY = 6
HURT_SUCCESS_INTENSITY = 15
TAUNT_POTENCY = 14
BOND_DEPTH = 10
HURT_POTENCY_BASE = 5
HURT_POTENCY_PER_DEPTH = 1
GOADED_PENALTY = -10
# Mira's Taunt check is her "presence" stat alone, weight 1, at one point per stat level
# (the conversion range below), so her rating is the stat value plus the level term: no
# class level means level 1, LEVEL_POINTS_PER_LEVEL points. No aspects, capabilities or perks.
PRESENCE = 12
TAUNT_RATING = PRESENCE + LEVEL_POINTS_PER_LEVEL * 1
GENERIC_BEAT_KEYS = {"id", "narration"}
OWNER_BEAT_KEYS = {"trigger_kind", "amount", "participant", "cause"}
ROLL_BEAT_KEYS = {"outcome", "potency", "control_change", "condition", "roll"}


@override_settings(SEED_SAMPLE_CONTENT=True)  # the curve factory and trigger wiring gate on #2698
class _SurgeField(JourneyCase):
    """An escalating encounter with Mira and Tomas on the road, and a Bandit Captain."""

    # The curve starts pressure rounds after the ones these journeys play, so no pace roll
    # takes the forced outcome before the surge roll does.
    CURVE_START_ROUND = 50

    def setUp(self) -> None:
        super().setUp()
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        self.tomas = self.make_player("Tomas", room=self.road)
        for player in (self.mira, self.tomas):
            CharacterVitals.objects.create(
                character_sheet=player.sheet_data, health=100, max_health=100, base_max_health=100
            )
        self.curve = EscalationCurveFactory(
            start_round=self.CURVE_START_ROUND,
            spike_minimum_track_points=BOND_DEPTH,
            surge_narration="{character} surges.",
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
            room=self.road,
            escalation_curve=self.curve,
        )
        self.mira_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.mira.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.tomas_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.tomas.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.captain = CombatOpponentFactory(encounter=self.encounter, name="Bandit Captain")
        self.partial = CheckOutcomeFactory(name="Partial", success_level=0)
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.watch(self.mira, self.tomas)

    def author_tuning(  # noqa: PLR0913 - one tuning row: kind, check, two bands, two potencies
        self,
        kind: str,
        check_name: str,
        *,
        partial: int,
        success: int,
        potency_base: int = 0,
        potency_per_depth: int = 0,
        partial_condition=None,
        partial_control: int = 0,
        check_type=None,
    ):
        """One tuning with a Partial and a Success band; the Partial band may also carry a
        control change and a condition."""
        tuning = SurgeTuningFactory(
            trigger_kind=kind,
            check_type=check_type or CheckTypeFactory(name=check_name),
            potency_base=potency_base,
            potency_per_depth=potency_per_depth,
        )
        SurgeDegreeBandFactory(
            tuning=tuning,
            outcome=self.partial,
            intensity=partial,
            control_change=partial_control,
            condition=partial_condition,
        )
        SurgeDegreeBandFactory(tuning=tuning, outcome=self.success, intensity=success)
        return tuning

    def author_goaded(self, check_type):
        """A debuff condition whose penalty applies to ``check_type`` rolls."""
        goaded = ConditionTemplateFactory(name="Goaded")
        ConditionCheckModifierFactory(
            condition=goaded, check_type=check_type, modifier_value=GOADED_PENALTY
        )
        return goaded

    def give_mira_a_taunt_check(self) -> None:
        """Mira's Taunt check: her presence stat alone, so her rating is ``TAUNT_RATING``.

        Staff designate it as the taunter's check on the social maneuver config (#4739).
        """
        presence = StatTraitFactory(name="presence")
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        taunt_check = CheckTypeFactory(name="Taunt")
        CheckTypeTraitFactory(check_type=taunt_check, trait=presence, weight=Decimal("1.0"))
        SocialManeuverConfigFactory(taunt_check_type=taunt_check)
        CharacterTraitValueFactory(character=self.mira.sheet_data, trait=presence, value=PRESENCE)

    def composure_penalty(self, character, check_type) -> int:
        """The modifier total the character's next roll of ``check_type`` would carry."""
        return collect_check_modifiers(character.sheet_data, check_type).extra_modifiers_total

    def beats_seen_by(self, account) -> list[dict]:
        response = self.api(account).get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["surge_beats"]

    def assertCauseReadOnlyBy(  # noqa: N802 - unittest style
        self, surged, bystander, cause: str
    ) -> None:
        """The surged player's round payload carries ``cause``; a bystander's has no cause."""
        (own,) = self.beats_seen_by(self.account_of(surged))
        self.assertEqual(own["cause"], cause)
        (other,) = self.beats_seen_by(self.account_of(bystander))
        self.assertNotIn("cause", other)
        self.assertEqual(other["narration"], f"{surged.key} surges.")

    def told_roll_line(self, character) -> str:
        """The one roll line the game told ``character`` (a line naming a check)."""
        lines = [line for line in self.mailbox(character).lines if " check vs " in line]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def intensity_or_zero(self, character) -> int:
        engagement = CharacterEngagement.objects.filter(character=character.sheet_data).first()
        return engagement.intensity_modifier if engagement is not None else 0

    def enter_combat(self, *characters) -> None:
        """Seat each character's combat engagement, as the round-opening does for round 2 on."""
        for character in characters:
            begin_engagement(character, EngagementType.COMBAT, source=self.encounter)

    def intensity(self, character) -> int:
        return CharacterEngagement.objects.get(character=character.sheet_data).intensity_modifier

    def records(self, kind: str):
        return DramaticSurgeRecord.objects.filter(trigger_kind=kind)

    def resolve(self, outcome):
        """Resolve the round with the first roll the round makes coming up ``outcome``."""
        # The roll line is sent once the round's transaction commits; a test's never does,
        # so run the commit callbacks the real round would have fired.
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(outcome):
            return resolve_round(self.encounter)

    def next_round(self) -> None:
        # The room's trigger cache resets on commit; a test's transaction never commits, so
        # run the commit callbacks the real round-opening would have fired.
        with self.captureOnCommitCallbacks(execute=True):
            begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()


class BeingTauntedByAnNpc(_SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira)
        self.author_tuning(
            SurgeTriggerKind.TAUNT_RECEIVED,
            "Composure",
            partial=PARTIAL_INTENSITY,
            success=SUCCESS_INTENSITY,
        )
        self.entry = ThreatPoolEntryFactory(
            pool=self.captain.threat_pool,
            name="Sneering Jibe",
            base_damage=0,
            taunt_potency=TAUNT_POTENCY,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )

    def _captain_jibes_at_mira(self, entry=None) -> None:
        action = CombatOpponentActionFactory(
            opponent=self.captain,
            threat_entry=entry or self.entry,
            round_number=self.encounter.round_number,
        )
        action.targets.add(self.mira_seat)

    def test_a_taunt_entry_surges_mira_and_shows_her_the_roll(self) -> None:
        self._captain_jibes_at_mira()

        self.resolve(self.partial)

        self.assertEqual(self.intensity(self.mira), PARTIAL_INTENSITY)
        self.assertTold(
            self.mira,
            f"Composure check vs taunt potency {TAUNT_POTENCY} · Partial "
            f"· Intensity +{PARTIAL_INTENSITY}",
        )
        record = self.records(SurgeTriggerKind.TAUNT_RECEIVED).get()
        self.assertEqual(record.participant, self.mira_seat)
        self.assertEqual(record.potency, TAUNT_POTENCY)
        self.assertEqual(record.outcome, self.partial)

    def test_the_taunt_does_no_damage_and_the_roll_line_is_hers_alone(self) -> None:
        self._captain_jibes_at_mira()

        self.resolve(self.partial)

        health = CharacterVitals.objects.get(character_sheet=self.mira.sheet_data).health
        self.assertEqual(health, 100)
        self.assertNotTold(self.tomas, "Composure check")
        self.assertEqual(self.intensity_or_zero(self.tomas), 0)

    def test_the_room_reads_the_authored_jibe_and_a_plain_line_without_one(self) -> None:
        witty = ThreatPoolEntryFactory(
            pool=self.captain.threat_pool,
            name="Witty Jibe",
            base_damage=0,
            taunt_potency=TAUNT_POTENCY,
            hit_narration="{actor} sneers at {target}.",
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )
        self._captain_jibes_at_mira(witty)
        self.resolve(self.partial)
        self.assertShownRow(self.tomas, "Bandit Captain sneers at Mira.")
        # Mira reads the same words the room was told.
        self.assertCauseReadOnlyBy(self.mira, self.tomas, "Bandit Captain sneers at Mira.")

        self.next_round()
        self._captain_jibes_at_mira()
        self.resolve(self.partial)
        self.assertShownRow(self.tomas, "Bandit Captain taunts Mira")

    def test_the_room_is_told_only_the_generic_line(self) -> None:
        self._captain_jibes_at_mira()

        self.resolve(self.partial)

        # The curve's own wording, the same line for every roll: no check, potency or degree.
        self.assertTold(self.tomas, "Mira surges.")
        for secret in ("potency", "check", "Partial", "Composure"):
            self.assertNotTold(self.tomas, secret)
        self.assertTold(self.mira, "Mira surges.")
        self.assertTold(self.mira, "Composure check vs taunt potency")

    def test_mira_reads_who_taunted_her_and_tomas_does_not(self) -> None:
        self._captain_jibes_at_mira()

        self.resolve(self.partial)

        self.assertCauseReadOnlyBy(self.mira, self.tomas, "Bandit Captain taunts Mira.")

    def test_a_better_composure_result_surges_her_more(self) -> None:
        self._captain_jibes_at_mira()
        self.resolve(self.partial)
        after_partial = self.intensity(self.mira)

        self.next_round()
        self._captain_jibes_at_mira()
        self.resolve(self.success)
        gained_on_success = self.intensity(self.mira) - after_partial

        self.assertEqual(after_partial, PARTIAL_INTENSITY)
        self.assertEqual(gained_on_success, SUCCESS_INTENSITY)
        self.assertTold(
            self.mira,
            f"Composure check vs taunt potency {TAUNT_POTENCY} · Success "
            f"· Intensity +{SUCCESS_INTENSITY}",
        )
        self.assertEqual(self.records(SurgeTriggerKind.TAUNT_RECEIVED).count(), 2)

    def test_an_encounter_without_a_curve_does_not_surge(self) -> None:
        self.encounter.escalation_curve = None
        self.encounter.save()
        self._captain_jibes_at_mira()

        self.resolve(self.partial)

        self.assertFalse(self.records(SurgeTriggerKind.TAUNT_RECEIVED).exists())
        self.assertNotTold(self.mira, "Composure check")


class BeingTauntedByAnotherPlayer(_SurgeField):
    """Mira taunts Tomas by name: his Composure roll is against her own taunt rating."""

    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.tomas)
        self.give_mira_a_taunt_check()
        self.author_tuning(
            SurgeTriggerKind.TAUNT_RECEIVED,
            "Composure",
            partial=PARTIAL_INTENSITY,
            success=SUCCESS_INTENSITY,
        )

    def test_the_potency_is_the_taunter_s_rating_and_tomas_is_shown_the_roll(self) -> None:
        told = self.telnet(self.mira, "combat taunt Tomas")
        self.assertIn("You taunt your ally.", told)

        self.resolve(self.partial)

        self.assertEqual(self.intensity(self.tomas), PARTIAL_INTENSITY)
        self.assertTold(
            self.tomas,
            f"Composure check vs taunt potency {TAUNT_RATING} · Partial "
            f"· Intensity +{PARTIAL_INTENSITY}",
        )
        record = self.records(SurgeTriggerKind.TAUNT_RECEIVED).get()
        self.assertEqual(record.participant, self.tomas_seat)
        self.assertEqual(record.subject_sheet, self.mira.sheet_data)
        self.assertEqual(record.potency, TAUNT_RATING)
        self.assertEqual(record.outcome, self.partial)
        self.assertCauseReadOnlyBy(self.tomas, self.mira, "Mira taunts Tomas.")
        # Mira rolled nothing and is not shown his roll.
        self.assertNotTold(self.mira, "Composure check")
        self.assertEqual(self.intensity_or_zero(self.mira), 0)

    def test_a_better_composure_result_surges_him_more(self) -> None:
        self.telnet(self.mira, "combat taunt Tomas")
        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), SUCCESS_INTENSITY)

    def test_taunting_him_again_next_round_surges_him_again(self) -> None:
        self.telnet(self.mira, "combat taunt Tomas")
        self.resolve(self.partial)
        self.next_round()

        self.telnet(self.mira, "combat taunt Tomas")
        self.resolve(self.partial)

        self.assertEqual(self.intensity(self.tomas), 2 * PARTIAL_INTENSITY)

    def test_an_encounter_without_a_curve_does_not_surge(self) -> None:
        self.encounter.escalation_curve = None
        self.encounter.save()
        self.telnet(self.mira, "combat taunt Tomas")

        self.resolve(self.partial)

        self.assertFalse(self.records(SurgeTriggerKind.TAUNT_RECEIVED).exists())
        self.assertNotTold(self.tomas, "Composure check")


class ADebuffBandHurtsTheNextCheck(_SurgeField):
    """A band's condition carries a real penalty; the surged player's next roll is lower."""

    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira, self.tomas)
        self.give_mira_a_taunt_check()
        self.composure = CheckTypeFactory(name="Composure")
        self.tuning = self.author_tuning(
            SurgeTriggerKind.TAUNT_RECEIVED,
            "Composure",
            partial=PARTIAL_INTENSITY,
            success=SUCCESS_INTENSITY,
            partial_control=-1,
            partial_condition=self.author_goaded(self.composure),
            check_type=self.composure,
        )

    def test_a_failed_roll_to_a_captain_s_jibe_leaves_her_next_composure_check_lower(self) -> None:
        entry = ThreatPoolEntryFactory(
            pool=self.captain.threat_pool,
            name="Sneering Jibe",
            base_damage=0,
            taunt_potency=TAUNT_POTENCY,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )
        action = CombatOpponentActionFactory(
            opponent=self.captain, threat_entry=entry, round_number=self.encounter.round_number
        )
        action.targets.add(self.mira_seat)
        before = self.composure_penalty(self.mira, self.composure)

        self.resolve(self.partial)

        goaded = self.tuning.bands.get(outcome=self.partial).condition
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.mira, condition=goaded).exists()
        )
        self.assertLess(self.composure_penalty(self.mira, self.composure), before)
        self.assertEqual(self.intensity(self.mira), PARTIAL_INTENSITY)
        self.assertEqual(
            CharacterEngagement.objects.get(character=self.mira.sheet_data).control_modifier, -1
        )
        self.assertTold(
            self.mira,
            f"Composure check vs taunt potency {TAUNT_POTENCY} · Partial "
            f"· Intensity +{PARTIAL_INTENSITY} · control -1 · Goaded",
        )

    def test_a_failed_roll_to_a_player_s_taunt_leaves_his_next_composure_check_lower(self) -> None:
        self.telnet(self.mira, "combat taunt Tomas")
        before = self.composure_penalty(self.tomas, self.composure)

        self.resolve(self.partial)

        goaded = self.tuning.bands.get(outcome=self.partial).condition
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.tomas, condition=goaded).exists()
        )
        self.assertLess(self.composure_penalty(self.tomas, self.composure), before)
        self.assertEqual(
            CharacterEngagement.objects.get(character=self.tomas.sheet_data).control_modifier, -1
        )
        self.assertTold(
            self.tomas,
            f"Composure check vs taunt potency {TAUNT_RATING} · Partial "
            f"· Intensity +{PARTIAL_INTENSITY} · control -1 · Goaded",
        )
        # Mira, who taunted, carries no penalty.
        self.assertEqual(self.composure_penalty(self.mira, self.composure), 0)

    def test_a_better_result_takes_the_band_without_the_condition(self) -> None:
        self.telnet(self.mira, "combat taunt Tomas")

        self.resolve(self.success)

        self.assertFalse(ConditionInstance.objects.filter(target=self.tomas).exists())
        self.assertEqual(self.composure_penalty(self.tomas, self.composure), 0)
        self.assertNotTold(self.tomas, "Goaded")


class TheRoundPayloadShowsTheRollToTheRightPeople(_SurgeField):
    """Mira is surged by the captain's jibe; who reads the roll off the round payload."""

    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira)
        self.composure = CheckTypeFactory(name="Composure")
        self.tuning = self.author_tuning(
            SurgeTriggerKind.TAUNT_RECEIVED,
            "Composure",
            partial=PARTIAL_INTENSITY,
            success=SUCCESS_INTENSITY,
            partial_control=-1,
            partial_condition=self.author_goaded(self.composure),
            check_type=self.composure,
        )
        self.gm = AccountFactory(username="surge_gm")
        SceneParticipationFactory(scene=self.encounter.scene, account=self.gm, is_gm=True)
        self.staff = AccountFactory(username="surge_staff", is_staff=True)
        entry = ThreatPoolEntryFactory(
            pool=self.captain.threat_pool,
            name="Sneering Jibe",
            base_damage=0,
            taunt_potency=TAUNT_POTENCY,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )
        action = CombatOpponentActionFactory(
            opponent=self.captain, threat_entry=entry, round_number=self.encounter.round_number
        )
        action.targets.add(self.mira_seat)
        self.resolve(self.partial)

    def test_the_surged_player_a_gm_and_staff_read_the_roll_she_was_told(self) -> None:
        told = self.told_roll_line(self.mira)
        for account in (self.account_of(self.mira), self.gm, self.staff):
            (beat,) = self.beats_seen_by(account)
            self.assertEqual(set(beat), GENERIC_BEAT_KEYS | OWNER_BEAT_KEYS | ROLL_BEAT_KEYS)
            self.assertEqual(beat["roll"], told)
            self.assertEqual(beat["outcome"], "Partial")
            self.assertEqual(beat["potency"], TAUNT_POTENCY)
            self.assertEqual(beat["control_change"], -1)
            self.assertEqual(beat["condition"], "Goaded")
            self.assertEqual(beat["trigger_kind"], SurgeTriggerKind.TAUNT_RECEIVED)
            self.assertEqual(beat["amount"], PARTIAL_INTENSITY)
            self.assertEqual(beat["narration"], "Mira surges.")

    def test_a_bystander_player_reads_only_the_generic_beat(self) -> None:
        (beat,) = self.beats_seen_by(self.account_of(self.tomas))

        self.assertEqual(set(beat), GENERIC_BEAT_KEYS)
        self.assertEqual(beat["narration"], "Mira surges.")


class BeingRallied(_SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.enter_combat(self.mira, self.tomas)
        # Staff designate Rally's success condition; its name does not matter (#4739).
        self.inspired = ConditionTemplateFactory(name="Heartened")
        SocialManeuverConfigFactory(rally_success_condition=self.inspired)
        # The tuning names the check the Rally rolls and picks the bands.
        self.author_tuning(
            SurgeTriggerKind.RALLIED,
            "Rally",
            partial=PARTIAL_INTENSITY,
            success=SUCCESS_INTENSITY,
        )

    def test_a_rally_surges_tomas_by_the_degree_of_mira_s_roll(self) -> None:
        told = self.telnet(self.mira, "combat rally Tomas")
        self.assertIn("You rally your ally.", told)
        declared = CombatRoundAction.objects.get(participant=self.mira_seat, round_number=1)
        self.assertEqual(declared.maneuver, CombatManeuver.RALLY)
        self.assertEqual(declared.focused_ally_target, self.tomas_seat)

        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), SUCCESS_INTENSITY)
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.tomas, condition=self.inspired).exists()
        )
        self.assertTold(
            self.tomas,
            f"vs rally difficulty {RALLY_BASE_DIFFICULTY} · Success "
            f"· Intensity +{SUCCESS_INTENSITY}",
        )
        record = self.records(SurgeTriggerKind.RALLIED).get()
        self.assertEqual(record.participant, self.tomas_seat)
        self.assertEqual(record.subject_sheet, self.mira.sheet_data)
        self.assertEqual(record.potency, RALLY_BASE_DIFFICULTY)
        self.assertCauseReadOnlyBy(self.tomas, self.mira, "Mira rallies Tomas.")
        # The rallier is not the one surged, and is not shown the roll.
        self.assertEqual(self.intensity(self.mira), 0)
        self.assertNotTold(self.mira, "Intensity +")

    def test_the_next_round_s_rally_surges_him_again(self) -> None:
        self.telnet(self.mira, "combat rally Tomas")
        self.resolve(self.partial)
        self.assertEqual(self.intensity(self.tomas), PARTIAL_INTENSITY)

        self.next_round()
        self.assertEqual(self.encounter.round_number, 2)
        self.telnet(self.mira, "combat rally Tomas")
        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), PARTIAL_INTENSITY + SUCCESS_INTENSITY)
        rounds = list(
            self.records(SurgeTriggerKind.RALLIED)
            .order_by("repeat_round")
            .values_list("repeat_round", flat=True)
        )
        self.assertEqual(rounds, [1, 2])


class AnAllyBeingWounded(_SurgeField):
    """Mira is bonded to Tomas; the captain wounds him through a real round."""

    # Round 2 (after the first round closes) installs the escalation triggers in the room.
    WOUND_ROUND = 2

    def setUp(self) -> None:
        super().setUp()
        wire_escalation_content()
        self.author_tuning(
            SurgeTriggerKind.ALLY_HURT,
            "Composure",
            partial=3,
            success=HURT_SUCCESS_INTENSITY,
            potency_base=HURT_POTENCY_BASE,
            potency_per_depth=HURT_POTENCY_PER_DEPTH,
        )
        bond = RelationshipTypeFactory(valence=TypeValence.WARM, fuels_escalation_spikes=True)
        relationship = CharacterRelationshipFactory(
            source=self.mira.sheet_data,
            target=self.tomas.sheet_data,
            is_active=True,
        )
        RelationshipLabelFactory(relationship=relationship, type=bond)
        relationship.invested_depth = BOND_DEPTH
        relationship.save()
        # Round 1 closes, then round 2 opens: opening it installs the room trigger.
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save()
        self.next_round()
        self.assertEqual(self.encounter.round_number, self.WOUND_ROUND)

    def _captain_wounds_tomas(self, damage: int, round_number: int = WOUND_ROUND) -> None:
        entry = ThreatPoolEntryFactory(
            pool=self.captain.threat_pool,
            name=f"Heavy Blow {damage}",
            base_damage=damage,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )
        action = CombatOpponentActionFactory(
            opponent=self.captain, threat_entry=entry, round_number=round_number
        )
        action.targets.add(self.tomas_seat)

    def _tomas_health(self) -> int:
        return CharacterVitals.objects.get(character_sheet=self.tomas.sheet_data).health

    def test_a_bonded_ally_s_wound_surges_her_in_proportion(self) -> None:
        self._captain_wounds_tomas(60)

        self.resolve(self.success)

        self.assertEqual(self._tomas_health(), 40)
        # Sixty of a hundred health is 60 percent of the Success band's 15.
        self.assertEqual(self.intensity(self.mira), 9)
        self.assertTold(
            self.mira,
            f"Composure check vs bond difficulty "
            f"{HURT_POTENCY_BASE + HURT_POTENCY_PER_DEPTH * BOND_DEPTH} · Success "
            "· Intensity +9 (scaled by the wound)",
        )
        record = self.records(SurgeTriggerKind.ALLY_HURT).get()
        self.assertEqual(record.participant, self.mira_seat)
        self.assertEqual(record.subject_sheet, self.tomas.sheet_data)
        self.assertCauseReadOnlyBy(
            self.mira, self.tomas, "Tomas, bonded to Mira, loses 60% of their health."
        )
        # The one who was hurt is not the one surged.
        self.assertEqual(self.intensity(self.tomas), 0)

    def test_a_smaller_wound_surges_her_less(self) -> None:
        self._captain_wounds_tomas(20)

        self.resolve(self.success)

        self.assertEqual(self._tomas_health(), 80)
        # Twenty percent of 15.
        self.assertEqual(self.intensity(self.mira), 3)

    def test_without_the_bond_the_wound_surges_nobody(self) -> None:
        CharacterRelationship.objects.filter(source=self.mira.sheet_data).delete()
        self._captain_wounds_tomas(60)

        self.resolve(self.success)

        self.assertEqual(self._tomas_health(), 40)
        self.assertFalse(self.records(SurgeTriggerKind.ALLY_HURT).exists())
        self.assertEqual(self.intensity(self.mira), 0)

    def test_the_next_round_s_wound_surges_her_again(self) -> None:
        self._captain_wounds_tomas(60)
        self.resolve(self.success)
        self.next_round()
        self.assertEqual(self.encounter.round_number, self.WOUND_ROUND + 1)

        self._captain_wounds_tomas(20, round_number=self.WOUND_ROUND + 1)
        self.resolve(self.success)

        # The second round's wound is a fresh surge of its own: twenty percent of the Success
        # band's 15, as in the smaller-wound journey. The record's own amount is pinned, so
        # the assertion does not depend on the rest of her engagement intensity.
        surges = list(self.records(SurgeTriggerKind.ALLY_HURT).order_by("repeat_round"))
        self.assertEqual(len(surges), 2)
        self.assertEqual(surges[1].amount, 3)

    def test_an_encounter_without_a_curve_surges_nobody(self) -> None:
        self.encounter.escalation_curve = None
        self.encounter.save()
        self._captain_wounds_tomas(60)

        self.resolve(self.success)

        self.assertEqual(self._tomas_health(), 40)
        self.assertFalse(self.records(SurgeTriggerKind.ALLY_HURT).exists())
        self.assertEqual(self.intensity(self.mira), 0)
