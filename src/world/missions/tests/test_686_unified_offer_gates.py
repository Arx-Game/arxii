"""Gate-coverage tests for the #686 unified mission-offer framework.

Phase 5 of #686. Exercises the new code shipped in Phases 1+2:

- ``NPCRole.is_active`` master switch
- ``NPCRoleCooldown`` per-(role, persona) gate
- ``CharacterSheet.max_active_npc_missions`` PC cap (NPC-scope only)
- Per-(persona × role) one-in-flight gate
- ``MissionOfferDetails.requirements_override`` predicate composition
- POOL draw — weight fallback, ``pool_count`` cap, weight=0 exclusion
- Template reusability — one ``MissionOfferDetails`` row produces many
  ``MissionInstance`` rows over time
- Trigger-bypass regression guard — `source_offer=None` rows do NOT
  count against the PC cap (room/item trigger-based missions)
- ``issue_mission`` writes ``source_offer`` + ``NPCRoleCooldown``

Legacy ``MissionGiver`` surface is intentionally untouched by these
tests — they exercise the unified path directly via factories.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import MissionStatus
from world.missions.factories import (
    MissionNodeFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance, MissionParticipant
from world.missions.services.offer_handler import issue_mission
from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.factories import (
    MissionOfferDetailsFactory,
    NPCRoleCooldownFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
)
from world.npc_services.models import NPCRoleCooldown
from world.npc_services.services import (
    _is_offer_eligible,
    _weight_for_offer,
    available_offers,
    start_interaction,
)
from world.scenes.factories import PersonaFactory


def _make_pc():
    """Build a Character + CharacterSheet, returning the auto-created PRIMARY Persona.

    ``CharacterSheetFactory`` (via ``create_character_with_sheet``) already
    creates a PRIMARY persona — re-creating one here would violate the
    ``unique_primary_persona_per_character_sheet`` constraint.
    """
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return character, sheet.primary_persona


def _make_mission_offer(role=None, *, label=None, draw_mode=DrawMode.MENU):
    """Build an NPCServiceOffer with MissionOfferDetails + entry node template."""
    role = role or NPCRoleFactory()
    template = MissionTemplateFactory()
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    offer = NPCServiceOfferFactory(
        role=role,
        kind=OfferKind.MISSION,
        label=label or f"mission-{template.name}",
        draw_mode=draw_mode,
    )
    details = MissionOfferDetailsFactory(offer=offer, mission_template=template)
    return offer, details, template


# ---------------------------------------------------------------------------
# Role-level gates
# ---------------------------------------------------------------------------


class NPCRoleIsActiveGateTests(TestCase):
    def test_inactive_role_hides_all_offers(self):
        character, persona = _make_pc()
        role = NPCRoleFactory(is_active=False)
        _make_mission_offer(role)
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertEqual(available_offers(session), [])

    def test_active_role_surfaces_offers(self):
        character, persona = _make_pc()
        role = NPCRoleFactory(is_active=True)
        offer, _, _ = _make_mission_offer(role)
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))


class NPCRoleCooldownGateTests(TestCase):
    def test_active_role_cooldown_hides_every_offer_on_role(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer_a, _, _ = _make_mission_offer(role, label="A")
        offer_b, _, _ = _make_mission_offer(role, label="B")
        NPCRoleCooldownFactory(
            role=role,
            persona=persona,
            available_at=timezone.now() + timedelta(hours=2),
        )
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session)
        self.assertNotIn(offer_a, listed)
        self.assertNotIn(offer_b, listed)

    def test_expired_role_cooldown_does_not_block(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        NPCRoleCooldownFactory(
            role=role,
            persona=persona,
            available_at=timezone.now() - timedelta(seconds=1),
        )
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))

    def test_role_cooldown_for_other_persona_does_not_block(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        other_persona = PersonaFactory()
        NPCRoleCooldownFactory(
            role=role,
            persona=other_persona,
            available_at=timezone.now() + timedelta(hours=2),
        )
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))


# ---------------------------------------------------------------------------
# PC active-NPC-mission cap
# ---------------------------------------------------------------------------


class PCActiveNPCMissionCapTests(TestCase):
    """`CharacterSheet.max_active_npc_missions` ceiling on NPC-mediated offers."""

    def _spawn_active_npc_mission(self, character, role) -> MissionInstance:
        """Bypass the offer flow: create an active instance with source_offer set."""
        offer, _, template = _make_mission_offer(role)
        instance = MissionInstance.objects.create(template=template, source_offer=offer)
        MissionParticipantFactory(instance=instance, character=character, is_contract_holder=True)
        return instance

    def test_under_cap_offer_visible(self):
        character, persona = _make_pc()
        # Default cap is 3; spawn 2 active runs.
        role_a = NPCRoleFactory()
        role_b = NPCRoleFactory()
        self._spawn_active_npc_mission(character, role_a)
        self._spawn_active_npc_mission(character, role_b)
        # Different role so per-(persona×role) gate doesn't block.
        third_role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(third_role)
        session = start_interaction(role=third_role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))

    def test_at_cap_offer_hidden(self):
        character, persona = _make_pc()
        for _ in range(3):
            self._spawn_active_npc_mission(character, NPCRoleFactory())
        # A fourth role tries to surface its offer; cap blocks.
        fourth_role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(fourth_role)
        session = start_interaction(role=fourth_role, persona=persona, character=character)
        self.assertNotIn(offer, available_offers(session))

    def test_staff_override_per_pc_raises_cap(self):
        character, persona = _make_pc()
        # Staff bumped the cap to 5 for this PC.
        sheet = character.sheet_data
        sheet.max_active_npc_missions = 5
        sheet.save(update_fields=["max_active_npc_missions"])
        # 3 active doesn't hit the new cap.
        for _ in range(3):
            self._spawn_active_npc_mission(character, NPCRoleFactory())
        fourth_role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(fourth_role)
        session = start_interaction(role=fourth_role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))

    def test_trigger_based_missions_bypass_cap(self):
        """source_offer=None rows (room/item trigger missions) don't count."""
        character, persona = _make_pc()
        # 3 trigger-based active missions: source_offer is null → not counted.
        template = MissionTemplateFactory()
        MissionNodeFactory(template=template, key="entry", is_entry=True)
        for _ in range(3):
            instance = MissionInstance.objects.create(template=template, source_offer=None)
            MissionParticipantFactory(
                instance=instance, character=character, is_contract_holder=True
            )
        # An NPC-mediated offer is still visible because the cap counter ignores
        # trigger-based runs.
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))

    def test_completed_runs_dont_count_against_cap(self):
        character, persona = _make_pc()
        # 3 active runs ARE at cap...
        for _ in range(3):
            self._spawn_active_npc_mission(character, NPCRoleFactory())
        # ...but a 4th role's offer would be blocked. Complete one of the
        # active runs; the slot frees up.
        active_runs = list(MissionInstance.objects.filter(participants__character=character))
        active_runs[0].status = MissionStatus.COMPLETE
        active_runs[0].save(update_fields=["status"])

        fourth_role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(fourth_role)
        session = start_interaction(role=fourth_role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))


# ---------------------------------------------------------------------------
# Per-(persona × role) one-in-flight gate
# ---------------------------------------------------------------------------


class PerPersonaRoleOneInFlightGateTests(TestCase):
    """A persona can hold at most one active mission from a given role."""

    def test_persona_with_active_role_mission_sees_no_offers_from_role(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        # Persona already on a mission from this role.
        instance = MissionInstance.objects.create(template=template, source_offer=offer)
        MissionParticipantFactory(instance=instance, character=character, is_contract_holder=True)
        # Author a SECOND mission offer on the same role.
        second_offer, _, _ = _make_mission_offer(role, label="second")
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session)
        self.assertNotIn(offer, listed)
        self.assertNotIn(second_offer, listed)

    def test_different_persona_same_account_can_accept(self):
        """Bob (primary) on a mission doesn't block Mysterious Stranger (established)."""
        character_a, _persona_a = _make_pc()
        character_b, persona_b = _make_pc()

        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)

        # character_a is on a mission from this role.
        instance = MissionInstance.objects.create(template=template, source_offer=offer)
        MissionParticipantFactory(instance=instance, character=character_a, is_contract_holder=True)

        # character_b (different sheet → different persona) sees the offer.
        session = start_interaction(role=role, persona=persona_b, character=character_b)
        self.assertIn(offer, available_offers(session))

    def test_completing_mission_frees_persona_for_same_role(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        instance = MissionInstance.objects.create(template=template, source_offer=offer)
        MissionParticipantFactory(instance=instance, character=character, is_contract_holder=True)

        # Complete the run; gate releases.
        instance.status = MissionStatus.COMPLETE
        instance.save(update_fields=["status"])

        session = start_interaction(role=role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))


# ---------------------------------------------------------------------------
# MissionOfferDetails.requirements_override predicate
# ---------------------------------------------------------------------------


class MissionOfferDetailsRequirementsOverrideTests(TestCase):
    """The override predicate is AND-composed with the offer's own
    eligibility_rule and gates visibility."""

    def test_failing_override_hides_offer(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, details, _ = _make_mission_offer(role)
        # Empty OR evaluates to False (per `evaluate` semantics) — a
        # deterministic always-false predicate without needing a leaf.
        details.requirements_override = {"op": "OR", "of": []}
        details.save(update_fields=["requirements_override"])

        session = start_interaction(role=role, persona=persona, character=character)
        self.assertNotIn(offer, available_offers(session))

    def test_empty_override_does_not_block(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        # MissionOfferDetailsFactory default is {} — no extra gate.
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))


# ---------------------------------------------------------------------------
# POOL draw mechanics
# ---------------------------------------------------------------------------


class POOLDrawTests(TestCase):
    def test_pool_count_caps_pool_offers_returned(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        # Author 5 POOL offers; cap to 2.
        for i in range(5):
            _make_mission_offer(role, label=f"pool-{i}", draw_mode=DrawMode.POOL)
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session, pool_count=2)
        listed_pool = [o for o in listed if o.draw_mode == DrawMode.POOL]
        self.assertEqual(len(listed_pool), 2)

    def test_pool_count_none_returns_all_pool_offers(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        for i in range(5):
            _make_mission_offer(role, label=f"pool-{i}", draw_mode=DrawMode.POOL)
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session)
        self.assertEqual(len([o for o in listed if o.draw_mode == DrawMode.POOL]), 5)

    def test_menu_offers_always_returned_in_full(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        menu_a, _, _ = _make_mission_offer(role, label="menu-a")
        menu_b, _, _ = _make_mission_offer(role, label="menu-b")
        for i in range(5):
            _make_mission_offer(role, label=f"pool-{i}", draw_mode=DrawMode.POOL)
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session, pool_count=1)
        self.assertIn(menu_a, listed)
        self.assertIn(menu_b, listed)

    def test_weight_for_offer_uses_details_weight_override(self):
        role = NPCRoleFactory()
        offer, details, _ = _make_mission_offer(role)
        details.weight = 7
        details.save(update_fields=["weight"])
        offer.refresh_from_db()
        self.assertEqual(_weight_for_offer(offer), 7)

    def test_weight_for_offer_falls_back_to_template_base_weight(self):
        role = NPCRoleFactory()
        offer, details, template = _make_mission_offer(role)
        template.base_weight = 4
        template.save(update_fields=["base_weight"])
        details.weight = None
        details.save(update_fields=["weight"])
        offer.refresh_from_db()
        self.assertEqual(_weight_for_offer(offer), 4)

    def test_weight_for_offer_clamps_to_one(self):
        role = NPCRoleFactory()
        offer, details, template = _make_mission_offer(role)
        template.base_weight = 0
        template.save(update_fields=["base_weight"])
        details.weight = None
        details.save(update_fields=["weight"])
        offer.refresh_from_db()
        self.assertEqual(_weight_for_offer(offer), 1)


# ---------------------------------------------------------------------------
# Template reusability
# ---------------------------------------------------------------------------


class TemplateReusabilityTests(TestCase):
    """One MissionOfferDetails row → many MissionInstance rows over time.

    Catalog uniqueness on (offer, mission_template) is a row-level
    constraint, NOT a gameplay one-shot. Accepting an offer twice (with
    cooldown released between) produces two distinct MissionInstance rows.
    """

    def test_two_separate_accepts_produce_two_instances(self):
        _character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)

        result_1 = issue_mission(offer, persona)
        # Manually clear the active gate (per-persona × role) by completing.
        MissionInstance.objects.filter(pk=result_1.object_pk).update(status=MissionStatus.COMPLETE)
        # Clear the NPCRoleCooldown so the second accept passes.
        NPCRoleCooldown.objects.filter(role=role, persona=persona).delete()

        result_2 = issue_mission(offer, persona)
        self.assertNotEqual(result_1.object_pk, result_2.object_pk)
        # Both instances reference the SAME template.
        instance_1 = MissionInstance.objects.get(pk=result_1.object_pk)
        instance_2 = MissionInstance.objects.get(pk=result_2.object_pk)
        self.assertEqual(instance_1.template_id, template.pk)
        self.assertEqual(instance_2.template_id, template.pk)


# ---------------------------------------------------------------------------
# issue_mission contract
# ---------------------------------------------------------------------------


class IssueMissionContractTests(TestCase):
    """The MISSION effect handler writes source_offer and NPCRoleCooldown."""

    def test_issue_mission_sets_source_offer_on_instance(self):
        _character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        result = issue_mission(offer, persona)
        instance = MissionInstance.objects.get(pk=result.object_pk)
        self.assertEqual(instance.source_offer_id, offer.pk)

    def test_issue_mission_writes_npc_role_cooldown(self):
        _character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        before = timezone.now()
        issue_mission(offer, persona)
        cd = NPCRoleCooldown.objects.get(role=role, persona=persona)
        self.assertGreater(cd.available_at, before)

    def test_issue_mission_uses_details_role_cooldown_duration_override(self):
        _character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, details, _ = _make_mission_offer(role)
        details.role_cooldown_duration = timedelta(days=7)
        details.save(update_fields=["role_cooldown_duration"])
        before = timezone.now()
        issue_mission(offer, persona)
        cd = NPCRoleCooldown.objects.get(role=role, persona=persona)
        # ~7 days from now (allow some slack for execution time).
        delta = cd.available_at - before
        self.assertGreater(delta, timedelta(days=6, hours=23))

    def test_issue_mission_creates_contract_holder_participant(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        result = issue_mission(offer, persona)
        participants = list(MissionParticipant.objects.filter(instance_id=result.object_pk))
        self.assertEqual(len(participants), 1)
        self.assertEqual(participants[0].character, character)
        self.assertTrue(participants[0].is_contract_holder)


# ---------------------------------------------------------------------------
# _is_offer_eligible composition
# ---------------------------------------------------------------------------


class IsOfferEligibleCompositionTests(TestCase):
    """The gate stack runs in order; each layer can independently block."""

    def test_active_alive_pc_with_clean_state_is_eligible(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        self.assertTrue(
            _is_offer_eligible(
                offer,
                persona=persona,
                character=character,
                current_rapport=0,
            )
        )

    def test_rapport_below_requirement_blocks(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        offer.rapport_requirement = 5
        offer.save(update_fields=["rapport_requirement"])
        self.assertFalse(
            _is_offer_eligible(
                offer,
                persona=persona,
                character=character,
                current_rapport=4,
            )
        )

    def test_role_inactive_blocks(self):
        character, persona = _make_pc()
        role = NPCRoleFactory(is_active=False)
        offer, _, _ = _make_mission_offer(role)
        self.assertFalse(
            _is_offer_eligible(
                offer,
                persona=persona,
                character=character,
                current_rapport=0,
            )
        )
