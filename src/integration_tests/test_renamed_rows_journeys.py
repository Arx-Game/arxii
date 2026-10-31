"""Journeys for renaming the rows the game used to find by name (#4739, slice of #4727).

Audere, Audere Majora, Berserk, Bleeding Out, Plummeting and Surrounded are found
through their designations (AudereThreshold, FuryConfig, VitalsConsequenceConfig), and
Rally's check and condition through the social maneuver config and its surge tuning.
Here staff rename each row in the admin, as they would on production, and the game
plays on unchanged:

- Ysmay's Audere offer opens and ``accept surge`` puts her in Audere, now called
  "Breakthrough"; her own combat payload reads ``audere_state: "audere"``.
- Mira, raging under a Berserk renamed "Red Haze", still cannot walk away
  (``combat_leave``), while Tomas, not raging, can.
- Mira's ``combat rally Tomas`` still rolls the renamed Rally check and leaves Tomas
  holding the renamed success condition.
- The Required content dashboard still lists every designation as present.
- (Postgres) The captain drops Tomas into the renamed Bleeding Out, and Mira, bonded
  to him, surges for her ally in peril.

Expected values are the rows built here, not anything the code computes.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import tag
from django.urls import reverse

from integration_tests.harness import JourneyCase
from integration_tests.test_audere_control_journeys import (
    SPARK_INTENSITY,
    TEARING_SEVERITY,
    _HighControlOpensAudere,
)
from integration_tests.test_refused_admin_saves_journeys import _filled
from integration_tests.test_surge_rolls_journeys import (
    BOND_DEPTH,
    PARTIAL_INTENSITY,
    SUCCESS_INTENSITY,
    _SurgeField,
)
from world.combat.constants import EncounterType, SurgeTriggerKind, TargetingMode, TargetSelection
from world.combat.factories import (
    CombatOpponentActionFactory,
    SocialManeuverConfigFactory,
    ThreatPoolEntryFactory,
    wire_escalation_content,
)
from world.conditions.constants import (
    UNCONSCIOUS_CONDITION_NAME,
    DurationType,
    FoundationalCapability,
)
from world.conditions.factories import (
    BleedingOutConditionFactory,
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.magic.audere import AudereThreshold
from world.magic.factories import (
    AudereThresholdFactory,
    BerserkConditionTemplateFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import FuryConfig
from world.relationships.constants import TypeValence
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipLabelFactory,
    RelationshipTypeFactory,
)
from world.scenes.constants import RoundStatus
from world.scenes.round_services import ensure_round_for_acute_condition
from world.traits.models import CheckOutcome
from world.vitals.constants import DERIVED_STATUS_DYING
from world.vitals.models import CharacterVitals
from world.vitals.peril_designations import designate_unset_peril_conditions
from world.vitals.services import get_vitals_consequence_config

TOMAS_LAST_HEALTH = 10

DESIGNATION_KEYS = (
    "audere-condition",
    "audere-majora-condition",
    "berserk-condition",
    "bleed-out-condition",
    "plummeting-condition",
)


class _StaffRenameRows:
    """Staff signed in to the admin, renaming a row through its change form."""

    def sign_in_staff(self) -> None:
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)

    def rename(self, admin_name: str, pk: int, new_name: str) -> None:
        """Post the change form at ``admin:arxii_<admin_name>_change`` with a new name."""
        url = reverse(f"admin:arxii_{admin_name}_change", args=[pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = _filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            data.update(_filled(inline.formset.management_form))
            for form in inline.formset.forms:
                data.update(_filled(form))
        data["name"] = new_name
        saved = self.client.post(url, data)
        self.assertEqual(saved.status_code, 302, saved.context and saved.context.get("errors"))


class RenamingAudereChangesNothing(_StaffRenameRows, _HighControlOpensAudere):
    def setUp(self) -> None:
        super().setUp()
        self.sign_in_staff()
        self.audere = AudereThreshold.objects.get().audere_condition

    def test_accepting_the_surge_puts_her_in_the_renamed_audere(self) -> None:
        self.rename("conditiontemplate", self.audere.pk, "Breakthrough")
        self.step(25)
        self.frayed_at(self.tearing, TEARING_SEVERITY)

        self.cast_in_the_round(self.spark)
        self.assertIn(f"[surge] Intensity surge (fired: {SPARK_INTENSITY})", self.prompts())
        told = self.telnet(self.ysmay, "accept surge")

        self.assertIn("The surge takes hold.", told)
        held = ConditionInstance.objects.get(target=self.ysmay, condition=self.audere)
        self.assertEqual(held.condition.name, "Breakthrough")
        payload = self.api(self.account_of(self.ysmay)).get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(payload.status_code, 200, payload.content)
        (own,) = [
            p for p in payload.json()["participants"] if p["character_sheet_id"] == self.sheet.pk
        ]
        self.assertEqual(own["audere_state"], "audere")


class RenamingBerserkChangesNothing(_StaffRenameRows, _SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.sign_in_staff()
        self.berserk = BerserkConditionTemplateFactory()

    def leave(self, character):
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.encounter_type = EncounterType.OPEN_ENCOUNTER
        self.encounter.save()
        return self.web(character, "combat_leave").detail

    def test_a_renamed_rage_still_refuses_to_walk_away(self) -> None:
        self.rename("conditiontemplate", self.berserk.pk, "Red Haze")
        ConditionInstanceFactory(target=self.mira, condition=self.berserk)

        detail = self.leave(self.mira)

        self.assertFalse(detail.success)
        self.assertIn("rage will not walk away", detail.message)

    def test_tomas_without_the_rage_may_leave(self) -> None:
        self.rename("conditiontemplate", self.berserk.pk, "Red Haze")
        ConditionInstanceFactory(target=self.mira, condition=self.berserk)

        detail = self.leave(self.tomas)

        self.assertTrue(detail.success)


class RenamingRallysRowsChangesNothing(_StaffRenameRows, _SurgeField):
    def setUp(self) -> None:
        super().setUp()
        self.sign_in_staff()
        self.enter_combat(self.mira, self.tomas)
        self.inspired = ConditionTemplateFactory(name="Inspired")
        SocialManeuverConfigFactory(rally_success_condition=self.inspired)
        self.tuning = self.author_tuning(
            SurgeTriggerKind.RALLIED, "Rally", partial=PARTIAL_INTENSITY, success=SUCCESS_INTENSITY
        )

    def test_the_rally_still_rolls_and_inspires(self) -> None:
        self.rename("conditiontemplate", self.inspired.pk, "Heartened")
        self.rename("checktype", self.tuning.check_type_id, "Steady the Line")

        told = self.telnet(self.mira, "combat rally Tomas")
        self.assertIn("You rally your ally.", told)
        self.resolve(self.success)

        self.assertEqual(self.intensity(self.tomas), SUCCESS_INTENSITY)
        held = ConditionInstance.objects.get(target=self.tomas, condition=self.inspired)
        self.assertEqual(held.condition.name, "Heartened")


class TheDashboardStaysClearAfterRenames(_StaffRenameRows, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.sign_in_staff()
        audere, majora = wire_audere_power_multipliers()
        AudereThresholdFactory()
        berserk = BerserkConditionTemplateFactory()
        bleed_out = BleedingOutConditionFactory()
        plummeting = ConditionTemplateFactory(name="Plummeting")
        designate_unset_peril_conditions(plummeting=plummeting)
        self.renames = (
            (audere, "Breakthrough"),
            (majora, "Over the Edge"),
            (berserk, "Red Haze"),
            (bleed_out, "Lifeblood Ebbing"),
            (plummeting, "Freefall"),
        )

    def present_and_missing(self) -> tuple[set[str], set[str]]:
        page = self.client.get(reverse("admin_ops_required_content"))
        self.assertEqual(page.status_code, 200)
        snapshot = page.context["snapshot"]
        present = {row.dependency.key for row in snapshot.present_required}
        missing = {row.dependency.key for row in snapshot.missing_required}
        return present, missing

    def test_every_designation_reads_present_after_the_renames(self) -> None:
        for template, new_name in self.renames:
            self.rename("conditiontemplate", template.pk, new_name)

        present, missing = self.present_and_missing()

        for key in DESIGNATION_KEYS:
            self.assertIn(key, present, key)
            self.assertNotIn(key, missing, key)

    def test_an_unset_designation_is_listed_missing(self) -> None:
        config = FuryConfig.objects.get(pk=1)
        config.berserk_condition = None
        config.save(update_fields=["berserk_condition"])

        present, missing = self.present_and_missing()

        self.assertIn("berserk-condition", missing)
        self.assertNotIn("berserk-condition", present)


class ARenamedBleedingOutStillHolds(_StaffRenameRows, JourneyCase):
    """Tomas lies unconscious and bleeding out in the Hollow under a renamed Bleeding Out.

    The danger round is opened the way the death tier opens it
    (``ensure_round_for_acute_condition``). Mira passes from the web client; Tomas cannot
    act, so hers is the only declaration. No hostile party drove the round, so his peril
    holds (its count does not tick) and, with Mira present to rescue him, he is marked
    abandoned.
    """

    ROUNDS_LEFT = 2

    def setUp(self) -> None:
        super().setUp()
        self.sign_in_staff()
        self.hollow = self.make_room("The Hollow")
        self.mira = self.make_player("Mira", room=self.hollow)
        self.tomas = self.make_player("Tomas", room=self.hollow)
        self.bleed_out = ConditionTemplateFactory(
            name="Bleeding Out",
            default_duration_type=DurationType.ROUNDS,
            default_duration_value=self.ROUNDS_LEFT,
        )
        designate_unset_peril_conditions(bleed_out=self.bleed_out)
        # Unconscious: awareness zeroed, so Tomas cannot act and never declares.
        awareness = CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)
        unconscious = ConditionTemplateFactory(
            name=UNCONSCIOUS_CONDITION_NAME, default_duration_type=DurationType.UNTIL_CURED
        )
        ConditionCapabilityEffectFactory(condition=unconscious, capability=awareness, value=-100)
        ConditionInstanceFactory(target=self.tomas, condition=unconscious)

    def test_the_renamed_peril_holds_when_no_hostile_drives(self) -> None:
        self.rename("conditiontemplate", self.bleed_out.pk, "Lifeblood Ebbing")
        bleed = ConditionInstanceFactory(
            target=self.tomas, condition=self.bleed_out, rounds_remaining=self.ROUNDS_LEFT
        )
        rnd = ensure_round_for_acute_condition(self.tomas.sheet_data)
        self.assertIsNotNone(rnd)
        held_round = rnd.round_number

        self.assertEqual(self.web(self.mira, "pass_round").detail.message, "You pass.")

        rnd.refresh_from_db()
        self.assertEqual(rnd.round_number, held_round + 1)
        bleed.refresh_from_db()
        self.assertEqual(bleed.rounds_remaining, self.ROUNDS_LEFT)
        self.assertEqual(bleed.abandoned_since_round, held_round)
        self.assertEqual(bleed.condition.name, "Lifeblood Ebbing")


@tag("postgres")  # Bleeding Out is progressive: apply_condition uses DISTINCT ON
class RenamingBleedingOutChangesNothing(_StaffRenameRows, _SurgeField):
    """Mira is bonded to Tomas; the captain's blow drops him into the renamed Bleeding Out."""

    PERIL_SPIKE = 5

    def setUp(self) -> None:
        from world.vitals.seeds import seed_survivability_content

        super().setUp()
        self.sign_in_staff()
        seed_survivability_content()
        wire_escalation_content()
        self.curve.peril_spike_intensity_amount = self.PERIL_SPIKE
        self.curve.save(update_fields=["peril_spike_intensity_amount"])
        bond = RelationshipTypeFactory(valence=TypeValence.WARM, fuels_escalation_spikes=True)
        relationship = CharacterRelationshipFactory(
            source=self.mira.sheet_data, target=self.tomas.sheet_data, is_active=True
        )
        RelationshipLabelFactory(relationship=relationship, type=bond)
        relationship.invested_depth = BOND_DEPTH
        relationship.save()
        # Round 1 closes, then round 2 opens: opening it installs the room trigger.
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save()
        self.next_round()
        self.bleed_out = get_vitals_consequence_config().bleed_out_condition
        # The survivability seed authors the Failure outcome the death tier rolls.
        self.failure = CheckOutcome.objects.get(name="Failure")

    def test_the_captain_drops_tomas_into_the_renamed_bleeding_out_and_mira_surges(self) -> None:
        self.rename("conditiontemplate", self.bleed_out.pk, "Lifeblood Ebbing")
        # Tomas is already badly hurt, so the blow takes him below zero without being big
        # enough to roll the permanent-wound tier: the forced Failure is the death roll's.
        vitals = CharacterVitals.objects.get(character_sheet=self.tomas.sheet_data)
        vitals.health = TOMAS_LAST_HEALTH
        vitals.save(update_fields=["health"])
        entry = ThreatPoolEntryFactory(
            pool=self.captain.threat_pool,
            name="Killing Blow",
            base_damage=TOMAS_LAST_HEALTH * 2,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.SPECIFIC_ROLE,
        )
        action = CombatOpponentActionFactory(
            opponent=self.captain, threat_entry=entry, round_number=self.encounter.round_number
        )
        action.targets.add(self.tomas_seat)

        self.resolve(self.failure)

        held = ConditionInstance.objects.get(target=self.tomas, condition=self.bleed_out)
        self.assertEqual(held.condition.name, "Lifeblood Ebbing")
        self.assertTrue(
            self.records(SurgeTriggerKind.ALLY_PERIL).filter(participant=self.mira_seat).exists()
        )
        # Tomas's own payload reads him as dying: the renamed condition is still Bleeding Out.
        payload = self.api(self.account_of(self.tomas)).get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(payload.status_code, 200, payload.content)
        (own,) = [
            p
            for p in payload.json()["participants"]
            if p["character_sheet_id"] == self.tomas.sheet_data.pk
        ]
        self.assertEqual(own["character_status"], DERIVED_STATUS_DYING)
