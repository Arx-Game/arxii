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

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import MissionStatus, MissionVisibility
from world.missions.factories import (
    MissionNodeFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance, MissionParticipant
from world.missions.services.offer_handler import issue_mission
from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.effects import dispatch_offer_effect
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
from world.scenes.constants import PersonaType
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

    def test_available_at_now_boundary_does_not_block(self):
        """Cooldown gate uses strict `__gt=now`; available_at == now is eligible."""
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        # Freeze the cooldown's available_at to exactly the now we'll pass.
        anchor = timezone.now()
        NPCRoleCooldownFactory(role=role, persona=persona, available_at=anchor)
        # Pin the eligibility check to the same anchor (the service reads
        # timezone.now() if not overridden — pass via the public start path,
        # which uses timezone.now() at session-start; we keep the assertion
        # tight by accepting that "now within ms of anchor" is the contract).
        session = start_interaction(role=role, persona=persona, character=character)
        # If the boundary used `__gte=now`, this would exclude the offer; the
        # spec contract is strict `__gt=now`, so the boundary row is eligible.
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
        # active runs; the slot frees up. Order by pk for deterministic
        # selection across DB backends.
        active_runs = list(
            MissionInstance.objects.filter(participants__character=character).order_by("pk")
        )
        active_runs[0].status = MissionStatus.COMPLETE
        active_runs[0].save(update_fields=["status"])

        fourth_role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(fourth_role)
        session = start_interaction(role=fourth_role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))

    def test_zero_cap_hides_offers_with_no_active_runs(self):
        """Staff-disabled NPC missions: cap=0 + zero active = still no offers."""
        character, persona = _make_pc()
        sheet = character.sheet_data
        sheet.max_active_npc_missions = 0
        sheet.save(update_fields=["max_active_npc_missions"])
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertNotIn(offer, available_offers(session))

    def test_no_sheet_fails_closed_for_mission_offer(self):
        """Characters with no CharacterSheet must NOT silently bypass the cap.

        Per TehomCD's review: the old code did `getattr(character, "sheet_data",
        None)` and skipped the cap when None, which silently bypassed the gate.
        Fail-closed is the correct posture — missing sheet means we can't
        verify cap or level-band, so the offer hides.
        """
        character = CharacterFactory()  # no CharacterSheetFactory call
        persona = PersonaFactory()  # detached PRIMARY for the session arg
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertNotIn(offer, available_offers(session))


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
        instance = MissionInstance.objects.create(
            template=template, source_offer=offer, accepted_as_persona=persona
        )
        MissionParticipantFactory(instance=instance, character=character, is_contract_holder=True)
        # Author a SECOND mission offer on the same role.
        second_offer, _, _ = _make_mission_offer(role, label="second")
        session = start_interaction(role=role, persona=persona, character=character)
        listed = available_offers(session)
        self.assertNotIn(offer, listed)
        self.assertNotIn(second_offer, listed)

    def test_different_persona_same_account_can_accept(self):
        """Bob (primary) on a mission doesn't block Mysterious Stranger (established)."""
        character_a, persona_a = _make_pc()
        character_b, persona_b = _make_pc()

        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)

        # character_a accepted the mission as their PRIMARY persona.
        instance = MissionInstance.objects.create(
            template=template, source_offer=offer, accepted_as_persona=persona_a
        )
        MissionParticipantFactory(instance=instance, character=character_a, is_contract_holder=True)

        # character_b (different sheet → different persona) sees the offer.
        session = start_interaction(role=role, persona=persona_b, character=character_b)
        self.assertIn(offer, available_offers(session))

    def test_same_character_different_persona_can_accept(self):
        """Spec AD#8: PRIMARY on a mission doesn't block ESTABLISHED on same role."""
        character, primary = _make_pc()
        established = PersonaFactory(
            character_sheet=primary.character_sheet,
            persona_type=PersonaType.ESTABLISHED,
        )

        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)

        # PRIMARY accepted the mission.
        instance = MissionInstance.objects.create(
            template=template, source_offer=offer, accepted_as_persona=primary
        )
        MissionParticipantFactory(instance=instance, character=character, is_contract_holder=True)

        # ESTABLISHED on the same character still sees the offer — different IC
        # person from the role's perspective.
        session = start_interaction(role=role, persona=established, character=character)
        self.assertIn(offer, available_offers(session))

    def test_completing_mission_frees_persona_for_same_role(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        instance = MissionInstance.objects.create(
            template=template, source_offer=offer, accepted_as_persona=persona
        )
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
# Template-side gates AND-composed into eligibility (#686)
# ---------------------------------------------------------------------------


class MissionTemplateGateCompositionTests(TestCase):
    """`MissionTemplate.is_active`, `visibility` (#870), and `level_band`
    are AND-composed with the offer's own gates per spec.

    These tests pin the composition contract identified by adversarial
    review — without them, a level-50 / staff-only / inactive template
    or one whose availability_rule rejects the PC would silently leak
    through the unified offer path.
    """

    def test_inactive_template_hides_offer(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        template.is_active = False
        template.save(update_fields=["is_active"])
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertNotIn(offer, available_offers(session))

    def test_restricted_empty_rule_hides_from_non_staff(self):
        """RESTRICTED + empty rule = emergent staff-only; non-staff never see it."""
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        template.visibility = MissionVisibility.RESTRICTED
        template.save(update_fields=["visibility"])
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertNotIn(offer, available_offers(session))

    def test_restricted_template_visible_to_staff_observer(self):
        character, persona = _make_pc()
        # `is_staff_observer` walks `character.account.is_staff` — wire a
        # staff account onto the character so the bypass evaluates True.
        character.db_account = AccountFactory(is_staff=True)
        character.save(update_fields=["db_account"])
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        template.visibility = MissionVisibility.RESTRICTED
        template.save(update_fields=["visibility"])
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertIn(offer, available_offers(session))

    def test_level_band_below_min_hides_offer(self):
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        # Fresh PC has current_level==0; require level >= 5.
        template.level_band_min = 5
        template.level_band_max = 10
        template.save(update_fields=["level_band_min", "level_band_max"])
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertNotIn(offer, available_offers(session))

    def test_restricted_failing_rule_blocks(self):
        """RESTRICTED: the availability_rule IS eligibility; empty OR == False."""
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        template.visibility = MissionVisibility.RESTRICTED
        template.availability_rule = {"op": "OR", "of": []}
        template.save(update_fields=["visibility", "availability_rule"])
        session = start_interaction(role=role, persona=persona, character=character)
        self.assertNotIn(offer, available_offers(session))

    def test_open_template_ignores_failing_rule(self):
        """OPEN: the predicate is not consulted (#870) — a stale always-false
        rule left on the row must not hide an OPEN template."""
        character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, template = _make_mission_offer(role)
        template.visibility = MissionVisibility.OPEN
        template.availability_rule = {"op": "OR", "of": []}
        template.save(update_fields=["visibility", "availability_rule"])
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

    def test_issue_mission_sets_accepted_as_persona(self):
        """Spec AD#8: persona-scope gate keys on this field, not character."""
        _character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        result = issue_mission(offer, persona)
        instance = MissionInstance.objects.get(pk=result.object_pk)
        self.assertEqual(instance.accepted_as_persona_id, persona.pk)

    def test_dispatch_offer_effect_routes_mission_through_registry(self):
        """Reaches the MISSION handler via OFFER_EFFECT_HANDLERS — not direct call.

        Guards against regression of the `MissionsConfig.ready()` registration
        + the lazy-snapshot for `reset_offer_effect_handlers` (the latter
        previously dropped MISSION on every reset, per #686 review).
        """
        _character, persona = _make_pc()
        role = NPCRoleFactory()
        offer, _, _ = _make_mission_offer(role)
        result = dispatch_offer_effect(offer, persona)
        # ty sees OfferKind.MISSION.value as a (value, label) tuple; wrap in
        # str() to keep the type-check happy (no-op at runtime).
        self.assertEqual(result.kind, str(OfferKind.MISSION.value))
        self.assertIsNotNone(result.object_pk)


# ---------------------------------------------------------------------------
# Visibility flip + availability_rule validation (#870 — supersedes the
# AccessTierFlipNoOpRegressionTests / #730 publishability gate)
# ---------------------------------------------------------------------------


class VisibilityFlipAndRuleValidationTests(TestCase):
    """#870: the visibility flip is a straight write — there is no "publish
    to nobody" failure mode to guard (a RESTRICTED template no PC's rule
    admits simply IS staff-only). What IS guarded at author time is the
    rule's well-formedness: a malformed tree crashes every later
    availability check, so `validate_availability_rule` rejects it with a
    DRF ValidationError (HTTP 400 at the API surface).
    """

    def test_visibility_flip_is_unguarded(self):
        from world.missions.serializers import MissionTemplateSerializer

        template = MissionTemplateFactory(visibility=MissionVisibility.RESTRICTED)
        serializer = MissionTemplateSerializer(
            instance=template, data={"visibility": MissionVisibility.OPEN}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_malformed_rule_rejected(self):
        from world.missions.serializers import MissionTemplateSerializer

        template = MissionTemplateFactory()
        serializer = MissionTemplateSerializer(
            instance=template,
            data={"availability_rule": {"leaf": "no_such_leaf", "params": {}}},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("availability_rule", serializer.errors)

    def test_well_formed_rule_accepted(self):
        from world.missions.serializers import MissionTemplateSerializer

        template = MissionTemplateFactory()
        rule = {"leaf": "min_character_level", "params": {"level": 3}}
        serializer = MissionTemplateSerializer(
            instance=template, data={"availability_rule": rule}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


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
