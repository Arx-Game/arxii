"""Journeys for a trial that opens a technique (#4501, slice 1 of #4343).

A trial is an authored mission whose good outcome tiers make a codex entry known, put
training on (or grant) the technique that entry opens, and cost the character something.
Each journey runs the mission through the real ``mission resolve`` command with the roll
pinned, then reads back what the character was told and what the sheet holds.

Names are invented. Staff-authored copy is left as bracketed slots.
"""

from __future__ import annotations

from django.urls import reverse
from evennia.accounts.models import AccountDB
from evennia.utils.ansi import strip_ansi

from evennia_extensions.models import PlayerData
from integration_tests.harness import JourneyCase
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.test_helpers import force_check_outcome
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.contributors.factories import ContentContributorFactory
from world.magic.constants import AcquisitionOrigin, GiftKind, PendingAlterationStatus, TargetKind
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterTechnique, PendingAlteration, TechniqueProgress, Thread
from world.magic.services import has_pending_alterations
from world.magic.services.alterations import enforce_advancement_gate
from world.magic.types import AlterationGateError
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.services.run import staff_assign_mission
from world.narrative.models import NarrativeMessageDelivery
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    TrainOfferDetailsFactory,
)
from world.progression.factories import CodexKnowledgeRequirementFactory
from world.progression.models import TechniqueKnownRequirement
from world.societies.factories import OrganizationFactory
from world.traits.factories import CheckOutcomeFactory


class ATrialInTheCrypt(JourneyCase):
    """Ysolde takes the staff-authored crypt trial; each tier gives and costs something."""

    def setUp(self) -> None:
        super().setUp()
        self.ysolde = self.make_player("Ysolde", room=self.make_room("The Crypt Stair"))
        self.sheet = self.ysolde.sheet_data
        self.roster_entry = self.sheet.roster_entry
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=ResonanceFactory())

        self.gift = GiftFactory(name="Sight of Taint", kind=GiftKind.MINOR)
        self.technique = TechniqueFactory(name="Read the Cup", gift=self.gift)
        self.entry = CodexEntryFactory(name="What her sight truly sees")
        CodexKnowledgeRequirementFactory(
            codex_entry=self.entry, path=None, technique=self.technique
        )
        self.dead_poisoner = CodexEntryFactory(name="The dead poisoner")
        self.fever = ConditionTemplateFactory(name="Crypt fever")

        outcomes = {
            "crit": CheckOutcomeFactory(name="Crit Success", success_level=2),
            "success": CheckOutcomeFactory(name="Win", success_level=1),
            "partial": CheckOutcomeFactory(name="Partial", success_level=0),
            "failure": CheckOutcomeFactory(name="Lose", success_level=-1),
        }
        self.outcomes = outcomes
        template = MissionTemplateFactory(name="The poisoner's crypt", risk_tier=1)
        node = MissionNodeFactory(template=template, key="jars", is_entry=True)
        option = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=CheckTypeFactory(name="Name the poisons"),
        )
        self.template = template
        for key, outcome in outcomes.items():
            MissionOptionRouteFactory(
                option=option,
                outcome_tier=outcome,
                target_node=None,
                consequence=self._consequence(key, outcome),
                outcome_text=f"[staff-authored {key} outcome text]",
            )

    def _effect(self, consequence, order, effect_type, **fields):
        return ConsequenceEffectFactory(
            consequence=consequence,
            execution_order=order,
            effect_type=effect_type,
            target=EffectTarget.SELF,
            **fields,
        )

    def _consequence(self, key, outcome):
        consequence = ConsequenceFactory(outcome_tier=outcome, label=f"Crypt jars, {key}")
        scar = EffectType.MAGICAL_SCARS
        if key == "crit":
            self._effect(
                consequence, 0, EffectType.GRANT_CODEX, codex_entry=self.entry, grants_known=True
            )
            self._effect(
                consequence,
                1,
                EffectType.TECHNIQUE_TRAINING,
                technique=self.technique,
                grants_technique_outright=True,
            )
            self._effect(consequence, 2, scar, condition_template=self.fever, condition_severity=2)
            self._effect(
                consequence,
                3,
                scar,
                condition_template=self.fever,
                condition_severity=3,
                scar_is_cosmetic=True,
            )
        elif key == "success":
            self._effect(
                consequence, 0, EffectType.GRANT_CODEX, codex_entry=self.entry, grants_known=True
            )
            self._effect(
                consequence,
                1,
                EffectType.TECHNIQUE_TRAINING,
                technique=self.technique,
                training_points=15,
                training_meter_size=40,
            )
            self._effect(consequence, 2, scar, condition_template=self.fever, condition_severity=2)
        elif key == "partial":
            self._effect(consequence, 0, EffectType.GRANT_CODEX, codex_entry=self.dead_poisoner)
            self._effect(
                consequence,
                1,
                EffectType.TECHNIQUE_TRAINING,
                technique=self.technique,
                training_points=5,
                training_meter_size=40,
            )
            self._effect(
                consequence,
                2,
                EffectType.APPLY_CONDITION,
                condition_template=self.fever,
                condition_severity=1,
            )
        else:
            self._effect(
                consequence,
                0,
                EffectType.APPLY_CONDITION,
                condition_template=self.fever,
                condition_severity=2,
            )
        return consequence

    def _hold_the_gift(self) -> None:
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=10,
        )

    def _take_the_trial(self, tier: str) -> str:
        instance = staff_assign_mission(self.template, self.ysolde)
        with force_check_outcome(self.outcomes[tier]):
            return strip_ansi(self.telnet(self.ysolde, f"mission resolve {instance.pk} 1"))

    def _notices(self) -> str:
        """Every message the game sent Ysolde, oldest first (the delivery rows)."""
        return "\n".join(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=self.sheet)
            .order_by("pk")
            .values_list("message__body", flat=True)
        )

    def _entry_status(self, entry) -> str | None:
        row = CharacterCodexKnowledge.objects.filter(
            roster_entry=self.roster_entry, entry=entry
        ).first()
        return row.status if row else None

    def test_success_makes_the_entry_known_and_starts_the_meter(self) -> None:
        self._hold_the_gift()
        self._take_the_trial("success")

        self.assertEqual(self._entry_status(self.entry), CodexKnowledgeStatus.KNOWN)
        meter = TechniqueProgress.objects.get(character_sheet=self.sheet, technique=self.technique)
        self.assertEqual((meter.points_accumulated, meter.total_required), (15, 40))
        self.assertFalse(
            CharacterTechnique.objects.filter(character=self.sheet, technique=self.technique)
        )
        self.assertIn("This opens a technique: Read the Cup (Sight of Taint).", self._notices())
        self.assertIn("Nobody teaches it right now.", self._notices())
        self.assertIn("Training toward Read the Cup: 15 of 40.", self._notices())
        self.assertIn("A Mage Scar (tier 2) is queued.", self._notices())
        (scar,) = PendingAlteration.objects.filter(character=self.sheet)
        self.assertFalse(scar.is_cosmetic)
        self.assertEqual(scar.tier, 2)

    def test_critical_success_grants_the_technique_and_both_scars(self) -> None:
        self._hold_the_gift()
        self._take_the_trial("crit")

        self.assertEqual(self._entry_status(self.entry), CodexKnowledgeStatus.KNOWN)
        learned = CharacterTechnique.objects.get(character=self.sheet, technique=self.technique)
        self.assertEqual(learned.origin, AcquisitionOrigin.TRIAL)
        self.assertFalse(TechniqueProgress.objects.filter(character_sheet=self.sheet))
        self.assertIn("enduring a trial, you can now use: Read the Cup", self._notices())
        self.assertIn("A cosmetic Mage Scar (tier 3) is queued as a reward.", self._notices())
        costly = PendingAlteration.objects.get(character=self.sheet, is_cosmetic=False)
        cosmetic = PendingAlteration.objects.get(character=self.sheet, is_cosmetic=True)
        self.assertEqual((costly.tier, cosmetic.tier), (2, 3))

        # The cost holds advancement back until it is described; the reward never does.
        with self.assertRaises(AlterationGateError):
            enforce_advancement_gate(self.sheet)
        costly.status = PendingAlterationStatus.STAFF_CLEARED
        costly.save()
        self.assertFalse(has_pending_alterations(self.sheet))
        enforce_advancement_gate(self.sheet)
        self.assertEqual(
            PendingAlteration.objects.get(pk=cosmetic.pk).status, PendingAlterationStatus.OPEN
        )

    def test_critical_success_without_the_gift_is_refused_by_name_but_still_costs(self) -> None:
        self._take_the_trial("crit")
        told = self._notices()

        self.assertEqual(self._entry_status(self.entry), CodexKnowledgeStatus.KNOWN)
        self.assertFalse(CharacterTechnique.objects.filter(character=self.sheet))
        self.assertIn("Technique not granted: you do not hold Sight of Taint.", told)
        self.assertNotIn("This opens a technique", told)
        self.assertEqual(PendingAlteration.objects.filter(character=self.sheet).count(), 2)

    def test_an_unmet_prerequisite_still_refuses_the_outright_grant(self) -> None:
        self._hold_the_gift()
        other = TechniqueFactory(name="Taste the Dark", gift=self.gift)
        TechniqueKnownRequirement.objects.create(technique=self.technique, required_technique=other)
        self._take_the_trial("crit")
        told = self._notices()

        self.assertEqual(self._entry_status(self.entry), CodexKnowledgeStatus.KNOWN)
        self.assertFalse(CharacterTechnique.objects.filter(character=self.sheet))
        self.assertIn("Need to know Taste the Dark", told)
        self.assertEqual(PendingAlteration.objects.filter(character=self.sheet).count(), 2)

    def test_partial_success_without_the_entry_trains_nothing_and_names_nothing(self) -> None:
        self._hold_the_gift()
        self._take_the_trial("partial")
        told = self._notices()

        self.assertEqual(self._entry_status(self.dead_poisoner), CodexKnowledgeStatus.UNCOVERED)
        self.assertFalse(TechniqueProgress.objects.filter(character_sheet=self.sheet))
        self.assertNotIn(self.entry.name, told)
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.ysolde, condition=self.fever).exists()
        )

    def test_partial_success_on_a_repeat_attempt_puts_its_points_on_the_meter(self) -> None:
        self._hold_the_gift()
        self._take_the_trial("success")
        self._take_the_trial("partial")

        meter = TechniqueProgress.objects.get(character_sheet=self.sheet, technique=self.technique)
        self.assertEqual(meter.points_accumulated, 20)

    def test_the_notice_says_where_the_technique_is_taught(self) -> None:
        self._hold_the_gift()
        academy = OrganizationFactory(name="Hall of Lanterns")
        offer = NPCServiceOfferFactory(
            kind=OfferKind.TRAIN, role=NPCRoleFactory(faction_affiliation=academy)
        )
        TrainOfferDetailsFactory(offer=offer, technique=self.technique)
        self._take_the_trial("success")

        self.assertIn(
            "Taught by: Hall of Lanterns. No player teacher offers it right now.", self._notices()
        )

    def test_failure_costs_and_opens_nothing(self) -> None:
        self._hold_the_gift()
        self._take_the_trial("failure")
        self.assertIn("Condition: Crypt fever (severity 2).", self._notices())

        self.assertIsNone(self._entry_status(self.entry))
        self.assertFalse(TechniqueProgress.objects.filter(character_sheet=self.sheet))
        self.assertFalse(CharacterTechnique.objects.filter(character=self.sheet))
        self.assertTrue(
            ConditionInstance.objects.filter(target=self.ysolde, condition=self.fever).exists()
        )


class ATrialBuiltOnThePage(JourneyCase):
    """Staff build the crypt trial on the Trial builder page; a player then runs it (#4513)."""

    def setUp(self) -> None:
        super().setUp()
        self.ysolde = self.make_player("Ysolde", room=self.make_room("The Crypt Stair"))
        self.sheet = self.ysolde.sheet_data
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=ResonanceFactory())
        self.gift = GiftFactory(name="Sight of Taint", kind=GiftKind.MINOR)
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=10,
        )
        self.technique = TechniqueFactory(name="Read the Cup", gift=self.gift)
        self.entry = CodexEntryFactory(name="What her sight truly sees")
        CodexKnowledgeRequirementFactory(
            codex_entry=self.entry, path=None, technique=self.technique
        )
        self.success = CheckOutcomeFactory(name="Win", success_level=1)
        self.template = MissionTemplateFactory(name="The poisoner's crypt", risk_tier=1)
        node = MissionNodeFactory(template=self.template, key="jars", is_entry=True)
        self.option = MissionOptionFactory(
            node=node,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=CheckTypeFactory(name="Name the poisons"),
        )
        staff = AccountDB.objects.create_superuser("crypt_staff", "cs@example.com", "pw-123456")
        PlayerData.objects.create(account=staff, contributor=ContentContributorFactory())
        self.client.force_login(staff)
        self.builder_url = reverse("admin_trial_builder", args=[self.option.pk])

    def test_a_trial_saved_on_the_page_runs_through_the_mission_command(self) -> None:
        tier = self.success.pk
        response = self.client.post(
            self.builder_url,
            {
                "trial-codex_entry": str(self.entry.pk),
                "trial-technique": str(self.technique.pk),
                "trial-meter_size": "40",
                f"tier{tier}-label": "[crypt jars, Win]",
                f"tier{tier}-outcome_text": "[staff-authored Win text]",
                f"tier{tier}-codex_mode": "known",
                f"tier{tier}-training_points": "15",
                f"tier{tier}-cost_kind": "scar",
                f"tier{tier}-cost_severity": "2",
                f"tier{tier}-reward_kind": "cosmetic",
                f"tier{tier}-reward_tier": "3",
            },
        )
        self.assertEqual(response.status_code, 302)

        instance = staff_assign_mission(self.template, self.ysolde)
        with force_check_outcome(self.success):
            told = strip_ansi(self.telnet(self.ysolde, f"mission resolve {instance.pk} 1"))

        self.assertIn("[staff-authored Win text]", told)
        known = CharacterCodexKnowledge.objects.get(
            roster_entry=self.sheet.roster_entry, entry=self.entry
        )
        self.assertEqual(known.status, CodexKnowledgeStatus.KNOWN)
        meter = TechniqueProgress.objects.get(character_sheet=self.sheet, technique=self.technique)
        self.assertEqual((meter.points_accumulated, meter.total_required), (15, 40))
        # The cost and the cosmetic reward, both saved with no condition template.
        costly = PendingAlteration.objects.get(character=self.sheet, is_cosmetic=False)
        cosmetic = PendingAlteration.objects.get(character=self.sheet, is_cosmetic=True)
        self.assertEqual((costly.tier, cosmetic.tier), (2, 3))
