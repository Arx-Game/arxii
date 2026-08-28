"""Web-layer proof for #3412 slice 3 task 3 — ``ProclamationViewSet.proclaim``
now dispatches through ``IssueProclamationAction.run()`` instead of calling
``world.societies.proclamations.issue_proclamation``/``enact_edict`` directly.

This activates the (until now inert) ``issue_proclamation`` entry in
``actions.constants.OFFSCREEN_ACT_KEYS`` (Task 1) — a captured/unconscious/
dead leader can no longer proclaim or enact a domain edict. The ALIVE happy
path (both the plain/org-stance branch and the domain-edict branch) must stay
byte-identical: same 201 + ``ProclamationSerializer`` payload, same
leadership/domain-authority refusal text as before this action existed (those
checks still live in the service layer, unduplicated — this action only adds
the lifecycle gate in front of the same calls).

No telnet ``proclaim`` command exists (confirmed by grep of ``src/commands/``)
so there is no telnet-parity web/telnet drift to prove here — only the
direct-``run()`` spot check below, mirroring Task 2's
``TelnetParitySpotCheckTests`` convention for an act with no telnet surface
yet.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from actions.constants import (
    OFFSCREEN_REASON_CAPTURED,
    OFFSCREEN_REASON_DEAD,
    OFFSCREEN_REASON_RETIRED,
    OFFSCREEN_REASON_UNCONSCIOUS,
)
from actions.definitions.organizations import IssueProclamationAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionInstanceFactory, UnconsciousConditionFactory
from world.roster.factories import RosterEntryFactory, RosterFactory, RosterTenureFactory
from world.roster.services.activity import set_lifecycle_state
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.models import EdictKind
from world.societies.houses.services import create_domain
from world.societies.models import Proclamation, StanceArchetype
from world.traits.factories import CheckOutcomeFactory


def _proclaiming_persona(*, account):
    """Character + sheet + roster tenure wired to ``account`` — the exact
    shape ``get_account_personas`` needs. Mirrors ``_active_primary_persona``,
    duplicated per-file across the societies API test modules (no shared
    helper exists yet)."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    roster = RosterFactory()
    entry = RosterEntryFactory(character_sheet=sheet, roster=roster)
    player_data = PlayerData.objects.create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    return sheet.primary_persona


def _stance(**axes) -> StanceArchetype:
    return StanceArchetype.objects.create(name=f"View Stance {axes}", **axes)


class ProclaimViewAliveTests(TestCase):
    """The ALIVE happy path — both branches — stays byte-identical."""

    def setUp(self) -> None:
        CheckTypeFactory(name="Persuasion")
        self.win = CheckOutcomeFactory(name="proclaim view win", success_level=1)
        self.account = AccountFactory()
        self.persona = _proclaiming_persona(account=self.account)
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def test_plain_stance_proclamation_succeeds(self) -> None:
        stance = _stance(mercy_delta=1)
        with force_check_outcome(self.win):
            response = self.client.post(
                "/api/societies/proclamations/proclaim/",
                {"stance": stance.pk, "prose": "Hear me."},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["issuer"], self.persona.pk)
        self.assertEqual(response.data["stance"], stance.pk)
        self.assertEqual(response.data["prose"], "Hear me.")
        self.assertEqual(response.data["org"], None)
        self.assertEqual(Proclamation.objects.count(), 1)

    def test_org_stance_proclamation_by_leader_succeeds(self) -> None:
        org = OrganizationFactory()
        OrganizationMembershipFactory(organization=org, persona=self.persona, rank=1)
        stance = _stance(power_delta=1)
        with force_check_outcome(self.win):
            response = self.client.post(
                "/api/societies/proclamations/proclaim/",
                {"stance": stance.pk, "org": org.pk},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["org"], org.pk)

    def test_org_stance_proclamation_by_non_leader_refused(self) -> None:
        org = OrganizationFactory()
        OrganizationMembershipFactory(organization=org, persona=self.persona)  # plain member
        stance = _stance(power_delta=1)
        response = self.client.post(
            "/api/societies/proclamations/proclaim/",
            {"stance": stance.pk, "org": org.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"], "Only the organization's leadership may speak for it."
        )
        self.assertEqual(Proclamation.objects.count(), 0)

    def test_no_active_persona_refused_before_action_dispatch(self) -> None:
        outsider = AccountFactory()
        client = APIClient()
        client.force_authenticate(user=outsider)
        stance = _stance(mercy_delta=1)
        response = client.post(
            "/api/societies/proclamations/proclaim/",
            {"stance": stance.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "No active persona.")

    def test_edict_enactment_by_leader_succeeds_and_swaps(self) -> None:
        org = OrganizationFactory(name="View Edict House")
        OrganizationMembershipFactory(organization=org, persona=self.persona, rank=1)
        domain = create_domain(area=AreaFactory(), name="Viewvale", owner_org=org)
        stance = _stance(change_delta=-1)
        kind = EdictKind.objects.create(name="Doubled View Watch", stance=stance)
        with force_check_outcome(self.win):
            response = self.client.post(
                "/api/societies/proclamations/proclaim/",
                {"domain": domain.pk, "edict_kind": kind.pk},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["org"], org.pk)
        edict = domain.edicts.get(kind=kind)
        self.assertIsNone(edict.revoked_at)

    def test_edict_enactment_by_outsider_refused(self) -> None:
        org = OrganizationFactory(name="View Edict Outsider House")
        outsider_org = OrganizationFactory(name="Unrelated House")
        OrganizationMembershipFactory(organization=outsider_org, persona=self.persona, rank=1)
        domain = create_domain(area=AreaFactory(), name="Outsidervale", owner_org=org)
        stance = _stance(change_delta=-1)
        kind = EdictKind.objects.create(name="Forbidden View Rule", stance=stance)
        response = self.client.post(
            "/api/societies/proclamations/proclaim/",
            {"domain": domain.pk, "edict_kind": kind.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "You do not have authority over this domain.")


class ProclaimViewOffscreenGateTests(TestCase):
    """CAPTURED / unconscious / DEAD / RETIRED refuse via the same
    ``{"detail": <reason>}`` shape Task 2 standardized; ALIVE is covered
    above. Fresh character/sheet/persona per test (``setUp``) — mirrors the
    per-test-isolation convention used by the journals/goals/persona sibling
    gate-test modules (each test mutates ``lifecycle_state`` differently)."""

    def setUp(self) -> None:
        CheckTypeFactory(name="Persuasion")
        self.win = CheckOutcomeFactory(name="proclaim gate win", success_level=1)
        self.account = AccountFactory()
        self.persona = _proclaiming_persona(account=self.account)
        self.sheet = self.persona.character_sheet
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _post(self, **payload):
        stance = _stance(status_delta=1)
        body = {"stance": stance.pk, **payload}
        return self.client.post("/api/societies/proclamations/proclaim/", body, format="json")

    def test_captured_refused_with_smuggle_text(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_CAPTURED)
        self.assertEqual(Proclamation.objects.count(), 0)

    def test_unconscious_refused_with_dream_text(self) -> None:
        template = UnconsciousConditionFactory()
        ConditionInstanceFactory(target=self.sheet.character, condition=template)
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_UNCONSCIOUS)

    def test_dead_refused_with_seance_text(self) -> None:
        # lifecycle_state=DEAD directly, vitals untouched — the offscreen gate's
        # own DEAD branch (mirrors Task 2's persona/journal DEAD tests; the
        # global vitals-backed dead-gate is a separate, earlier-checked branch).
        set_lifecycle_state(self.sheet, LifecycleState.DEAD)
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_DEAD)

    def test_retired_refused_with_quiet_text(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.RETIRED
        self.sheet.save(update_fields=["lifecycle_state"])
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_RETIRED)

    def test_alive_still_succeeds(self) -> None:
        with force_check_outcome(self.win):
            response = self._post()
        self.assertEqual(response.status_code, 201)

    def test_captured_also_blocks_edict_enactment(self) -> None:
        """One action key covers both proclaim branches — the gate fires for
        the domain-edict path too, not just the plain/org-stance path."""
        org = OrganizationFactory(name="Gate Edict House")
        OrganizationMembershipFactory(organization=org, persona=self.persona, rank=1)
        domain = create_domain(area=AreaFactory(), name="Gatevale", owner_org=org)
        stance = _stance(change_delta=-1)
        kind = EdictKind.objects.create(name="Gate-Blocked Rule", stance=stance)
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])

        response = self.client.post(
            "/api/societies/proclamations/proclaim/",
            {"domain": domain.pk, "edict_kind": kind.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_CAPTURED)
        self.assertFalse(domain.edicts.exists())


class IssueProclamationActionDirectRunTests(TestCase):
    """Direct ``action.run()`` proof (closes Task 1's flagged gap: prior to
    this task ``issue_proclamation`` sat in ``OFFSCREEN_ACT_KEYS`` with no
    real ``Action`` to exercise it against). This is also the telnet-parity
    seam — no telnet ``proclaim`` command exists, so this stands in for it."""

    def test_captured_actor_gets_smuggle_text_via_run(self) -> None:
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        sheet.lifecycle_state = LifecycleState.CAPTURED
        sheet.save(update_fields=["lifecycle_state"])
        stance = _stance(mercy_delta=1)

        result = IssueProclamationAction().run(
            actor=character, persona_id=sheet.primary_persona.pk, stance_id=stance.pk
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, OFFSCREEN_REASON_CAPTURED)
        self.assertEqual(Proclamation.objects.count(), 0)

    def test_alive_actor_succeeds_via_run(self) -> None:
        CheckTypeFactory(name="Persuasion")
        win = CheckOutcomeFactory(name="direct run win", success_level=1)
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        stance = _stance(mercy_delta=1)

        with force_check_outcome(win):
            result = IssueProclamationAction().run(
                actor=character, persona_id=sheet.primary_persona.pk, stance_id=stance.pk
            )

        self.assertTrue(result.success)
        self.assertIn("proclamation", result.data)
        self.assertEqual(result.data["proclamation"].issuer_id, sheet.primary_persona.pk)
