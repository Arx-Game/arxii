"""Telnet journey: the seeded T1-T7 tutorial chain, start to finish (#1035).

The acceptance test for the whole tutorial-arc issue: a fresh character walks
every stage of ``seed_tutorial_dev()``'s seven-template chain — room-trigger
discovery (T1), examine-driven discovery (T2), an NPC-offered EXTERNAL_ACT
beat resolved by a real technique cast (T3), a notice-board job that summons
the next step (T4), a durable EXTERNAL_ACT beat resolved by a real thread-weave
(T5), a durable EXTERNAL_ACT beat resolved by really founding a covenant (T6,
plus the fast-forward proof for a character who already holds one), and the
first legend-risk mission gated behind the whole chain (T7).

Modeled on ``test_missions_telnet_e2e.py`` (``_run``/``_said`` driving
``CmdMission`` via ``cmd.func()``, ``MagicMock`` msg capture) and
``test_noncombat_cast_telnet_e2e.py`` (plain ``setUp``, not ``setUpTestData``,
for all ObjectDB — the DbHolder deepcopy trap).

Telnet-verb coverage (the brief's pragmatism clause: every ``mission``
subverb kind must appear at least once): ``list`` (bare ``mission``),
``beat``, ``pick`` (exercised on a solo beat, where it steers to ``resolve``
— the tutorial chain is solo-only throughout, so there is no GROUP_VOTE node
to drive a real group pick; mirrors
``SoloMissionTelnetTests.test_pick_on_a_solo_beat_steers_to_resolve``),
``resolve``, ``take``, ``opportunities``, ``report``.

Service-seam pragmatism (stated per the brief's instruction to note every
choice):
  - T3/T6/T7 acceptance rides ``start_npc_interaction``/``resolve_npc_offer``
    (the registry Actions ``CmdHire`` itself calls) directly, rather than
    driving ``CmdHire`` text parsing — the "hire" verb isn't in the brief's
    required-surface list (only ``mission`` subverbs are), and the Action
    seam is exactly what the telnet command reduces to.
  - T5's summons-accept rides ``respond_to_summons`` directly (what
    ``hire accept <id>`` calls) for the same reason.
  - T3's TECHNIQUE_CAST is satisfied via a direct ``use_technique(...)`` call
    (the exact minimal shape ``UseTechniqueExternalActWiringTests`` in
    ``test_external_acts.py`` already proves resolves the mission), not the
    full ``cast`` telnet command — ``cast`` isn't in the required-surface
    list either, and the minimal call is what that command reduces to after
    its dispatch plumbing.
  - The second-PC T6 fast-forward proof uses ``staff_assign_mission``
    directly rather than re-walking T1-T5 for a second character — the point
    of that assertion is ``enter_node``'s fast-forward, not the chain's
    visibility gating (already covered by the primary walk + the explicit
    T7-gate-before/after assertion).
  - Between tutor-role NPC-offer/summons acceptances, the journey walks at
    natural speed — no cooldown fast-forwarding. Each of the four tutor
    ``MissionOfferDetails`` rows (T3/T5/T6/T7) is seeded with an explicit
    ``role_cooldown_duration=timedelta(0)`` (see
    ``world.seeds.game_content.tutorial._ensure_offer``): this is a curated
    single-path chain — ``availability_rule`` + the per-(persona, role)
    one-in-flight gate already prevent double-dipping, so the generic
    anti-spam ``NPCRoleCooldown`` (default 24h, shared per-role across ALL of
    a role's offers) would otherwise block T5/T6/T7 for a full day after
    accepting T3, which a real player finishing the chain same-session would
    hit (#1035 Task 6 review fix). ``setUp`` asserts the zero-duration seed so
    drift re-breaks this test loudly instead of silently reintroducing the
    fast-forward workaround.

Bug fixed in passing (fold-in, CLAUDE.md "Fold In, Don't File" — a one-line
wiring nit surfaced by this being the first test to ever drive
``CmdMission``'s ``take`` subverb over telnet): ``_handle_take`` resolved the
board giver via ``MissionGiver.objects.filter(target=room, ...)``, but a
BOARD giver's ``target`` is the examinable board OBJECT located in the room,
never the room itself (see ``MissionGiver.clean()``, and the already-correct
``target__db_location=room`` convention in
``opportunities.py::_here_postings`` and
``typeclasses/mixins.py::_maybe_render_board_postings``). Fixed to match.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from actions.definitions.npc_services import resolve_npc_offer, start_npc_interaction
from commands.missions import CmdMission
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CharacterCovenantRoleFactory, CovenantRoleFactory
from world.covenants.services import create_covenant
from world.covenants.types import CovenantFounder
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.services import use_technique, weave_thread
from world.mechanics.factories import CharacterEngagementFactory
from world.missions.constants import DeedRewardSink, GiverKind, MissionStatus
from world.missions.models import MissionGiver, MissionInstance
from world.missions.services.boards import postings_for_giver
from world.missions.services.play import beat_for
from world.missions.services.trigger_dispatch import (
    maybe_dispatch_on_enter,
    maybe_dispatch_on_examine,
)
from world.missions.services.visibility import template_visible_to
from world.npc_services.constants import SummonsStatus
from world.npc_services.models import NPCServiceOffer, OfferSummons
from world.npc_services.summons import respond_to_summons
from world.seeds.character_creation import ensure_canonical_fallback_room
from world.seeds.database import seed_dev_database
from world.seeds.game_content.tutorial import seed_tutorial_dev
from world.seeds.tests.content_stub import stub_content_root
from world.traits.factories import TraitFactory


def _run(caller: object, args: str = "") -> CmdMission:
    """Build and execute a ``mission`` command instance; return it for assertions."""
    cmd = CmdMission()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"mission {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return cmd


def _said(caller: object) -> str:
    """Concatenate every positional string the command sent to the caller."""
    chunks: list[str] = []
    for call in caller.msg.call_args_list:
        chunks.extend(arg for arg in call.args if isinstance(arg, str))
    return "\n".join(chunks)


class TutorialChainJourneyE2ETests(TestCase):
    """Walk the seeded T1-T7 tutorial chain end to end over the telnet seam."""

    @stub_content_root()
    def setUp(self) -> None:
        idmapper_models.flush_cache()
        # The Big Button: T4 reuses seed_missions_dev()'s board giver, whose
        # authored CHECK options need the "checks" cluster's CheckOutcome
        # catalog and the "character_creation" cluster's "wits" stat Trait —
        # exactly as a real deploy seeds them (cluster ordering in
        # world.seeds.clusters). Mirrors test_tutorial_seed.py's setup.
        # seed_tutorial_dev() re-run is idempotent and returns the templates.
        seed_dev_database()
        result = seed_tutorial_dev()
        (
            self.t1,
            self.t2,
            self.t3,
            self.t4,
            self.t5,
            self.t6,
            self.t7,
        ) = result.templates
        self.tutor_role = result.tutor_role
        self.room = ensure_canonical_fallback_room()

        # Guard the review-fix invariant (#1035 Task 6): each tutor offer
        # must carry a zero role-cooldown, or the anti-spam NPCRoleCooldown
        # gate blocks same-session progression through T5/T6/T7 (see module
        # docstring). Seed drift on this must fail loudly, not silently
        # reintroduce a need for cooldown fast-forwarding in this test.
        # 5 offers: the T3/T5/T6/T7 chain steps + the "Terms of Engagement"
        # consent primer (#2170), a T1-gated side-step off the same tutor.
        tutor_offers = NPCServiceOffer.objects.filter(role=self.tutor_role)
        self.assertEqual(tutor_offers.count(), 5)
        for offer in tutor_offers:
            self.assertEqual(
                offer.mission_offer_details.role_cooldown_duration,
                timedelta(0),
                f"tutor offer {offer.label!r} must seed role_cooldown_duration="
                "timedelta(0) (curated single-path chain; #1035 Task 6 review fix)",
            )

        self.pc, self.sheet = self._make_pc("Newcomer")

        # Leak-rule spy: BRANCH beat resolution (T1/T2/T4/T7) legitimately emits
        # an ambient room stir (normal mission flavor); EXTERNAL_ACT resolution
        # (T3/T5/T6, via satisfy_external_act) must NEVER touch it (#1035 leak
        # rule). Patched where play.py binds the name, not at the source module
        # (a from-import binding isn't affected by patching the source).
        self._room_stir_patcher = patch("world.missions.services.play.emit_ambient_room_stir")
        self.room_stir = self._room_stir_patcher.start()

    def tearDown(self) -> None:
        self._room_stir_patcher.stop()

    def _make_pc(self, db_key: str) -> tuple[object, object]:
        character = CharacterFactory(db_key=db_key)
        sheet = CharacterSheetFactory(character=character)
        # NPC-offer eligibility gates on level_band (1-5 for every tutorial
        # template); a freshly-created sheet has no class assignments and
        # current_level=0, which fails level_band_min=1 for T3/T5/T6/T7.
        CharacterClassLevelFactory(character=sheet, level=1, is_primary=True)
        sheet.invalidate_class_level_cache()
        character.db_location = self.room
        character.save(update_fields=["db_location"])
        return character, sheet

    def _offer(self, label: str) -> NPCServiceOffer:
        return NPCServiceOffer.objects.get(role=self.tutor_role, label=label)

    def _accept_npc_offer(self, offer: NPCServiceOffer, *, acknowledge_risk: bool = False):
        start = start_npc_interaction.run(actor=self.pc, role_id=offer.role_id)
        self.assertTrue(start.success, start.message)
        session = start.data["session"]
        result = resolve_npc_offer.run(
            actor=self.pc,
            session=session,
            offer_id=offer.pk,
            acknowledge_risk=acknowledge_risk,
        )
        self.assertTrue(result.success, result.message)
        return (
            MissionInstance.objects.filter(participants__character=self.pc, source_offer=offer)
            .order_by("-pk")
            .first()
        )

    def test_full_tutorial_chain_journey_over_telnet(self) -> None:  # noqa: PLR0915 - one journey
        persona = self.sheet.primary_persona

        # --- T1: Arrival (ROOM_TRIGGER) -----------------------------------
        instance_t1 = maybe_dispatch_on_enter(self.pc, self.room)
        self.assertIsNotNone(instance_t1)
        self.assertEqual(instance_t1.template_id, self.t1.pk)
        self.assertEqual(instance_t1.accepted_as_persona_id, persona.pk)

        _run(self.pc)  # bare "mission" — the `list` surface
        self.assertIn(self.t1.name, _said(self.pc))

        # `pick` on a solo beat steers to `resolve` (no GROUP_VOTE node exists
        # anywhere in this solo-only chain) — exercises the `pick` surface.
        _run(self.pc, f"pick {instance_t1.pk} 1")
        self.assertIn("resolve", _said(self.pc).lower())

        _run(self.pc, f"beat {instance_t1.pk}")  # the `beat` surface
        self.assertIn("1)", _said(self.pc))

        _run(self.pc, f"resolve {instance_t1.pk} 1")
        instance_t1.refresh_from_db()
        self.assertEqual(instance_t1.status, MissionStatus.COMPLETE)

        # --- T2: What the Walls Remember (ENVIRONMENTAL_DETAIL) -----------
        from evennia.objects.models import ObjectDB

        detail_obj = ObjectDB.objects.get(
            db_key="a faint scorch mark on the wall",
            db_typeclass_path="typeclasses.objects.Object",
        )
        instance_t2 = maybe_dispatch_on_examine(self.pc, detail_obj)
        self.assertIsNotNone(instance_t2)
        self.assertEqual(instance_t2.template_id, self.t2.pk)

        _run(self.pc, f"resolve {instance_t2.pk} 1")
        instance_t2.refresh_from_db()
        self.assertEqual(instance_t2.status, MissionStatus.COMPLETE)

        # --- T3: First Spark (NPC offer, EXTERNAL_ACT/TECHNIQUE_CAST) -----
        t3_offer = self._offer("Kindle a first spark")
        instance_t3 = self._accept_npc_offer(t3_offer)
        self.assertIsNotNone(instance_t3)
        self.assertEqual(instance_t3.template_id, self.t3.pk)

        # The EXTERNAL_ACT option is never presented/pickable.
        beat = beat_for(instance_t3, self.pc)
        self.assertEqual(beat.options, ())
        _run(self.pc, f"beat {instance_t3.pk}")
        self.assertIn("no options here", _said(self.pc).lower())

        # Real minimal technique cast (mirrors
        # UseTechniqueExternalActWiringTests's fixture in test_external_acts.py).
        CharacterAnimaFactory(character=self.pc, current=20, maximum=20)
        CharacterEngagementFactory(character=self.pc)
        technique = TechniqueFactory(intensity=5, control=10, anima_cost=3)

        room_stir_before = self.room_stir.call_count
        with patch("world.missions.services.external_acts.send_narrative_message") as sender:
            use_technique(
                character=self.pc,
                technique=technique,
                resolve_fn=MagicMock(return_value="ok"),
            )
        self.assertEqual(self.room_stir.call_count, room_stir_before)  # leak rule
        sender.assert_called_once()
        _, kwargs = sender.call_args
        self.assertEqual(kwargs["recipients"], [self.sheet])

        instance_t3.refresh_from_db()
        # Every NPC-offer-sourced run reports to its offering role
        # (report_to_role_for falls back to source_offer.role) — pauses at
        # RESOLVED same as T4, not just templates with an explicit
        # report_to_role override.
        self.assertEqual(instance_t3.status, MissionStatus.RESOLVED)
        _run(self.pc, f"report {instance_t3.pk} humble")  # the `report` surface
        instance_t3.refresh_from_db()
        self.assertEqual(instance_t3.status, MissionStatus.COMPLETE)

        # --- T4: A Simple Job (BOARD) --------------------------------------
        _run(self.pc, "opportunities")  # the `opportunities` surface
        self.assertIn(self.t4.name, _said(self.pc))

        board_giver = MissionGiver.objects.get(
            giver_kind=GiverKind.BOARD, target__db_location=self.room
        )
        postings = postings_for_giver(board_giver, self.pc)
        ordinal = next(i for i, p in enumerate(postings, start=1) if p.template_id == self.t4.pk)
        _run(self.pc, f"take {ordinal}")  # the `take` surface
        instance_t4 = (
            MissionInstance.objects.filter(participants__character=self.pc, template=self.t4)
            .order_by("-pk")
            .first()
        )
        self.assertIsNotNone(instance_t4)

        _run(self.pc, f"resolve {instance_t4.pk} 1")
        instance_t4.refresh_from_db()
        self.assertEqual(instance_t4.status, MissionStatus.RESOLVED)

        t5_offer = self._offer("Learn the loom's thread-work")
        _run(self.pc, f"report {instance_t4.pk} humble")  # the `report` surface
        instance_t4.refresh_from_db()
        self.assertEqual(instance_t4.status, MissionStatus.COMPLETE)

        summons = OfferSummons.objects.get(
            target_persona=persona, offer=t5_offer, status=SummonsStatus.PENDING
        )

        # --- T5: The Loom (NPC offer via summons, EXTERNAL_ACT/THREAD_WOVEN) -
        summons_result = respond_to_summons(summons, self.pc, accept=True)
        self.assertTrue(summons_result.success, summons_result.message)
        instance_t5 = (
            MissionInstance.objects.filter(participants__character=self.pc, source_offer=t5_offer)
            .order_by("-pk")
            .first()
        )
        self.assertIsNotNone(instance_t5)
        self.assertEqual(instance_t5.template_id, self.t5.pk)

        trait = TraitFactory()
        resonance = ResonanceFactory()
        unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT, unlock_trait=trait)
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock, xp_spent=100)

        room_stir_before = self.room_stir.call_count
        with patch("world.missions.services.external_acts.send_narrative_message") as sender:
            weave_thread(self.sheet, TargetKind.TRAIT, trait, resonance, name="Tutorial Thread")
        self.assertEqual(self.room_stir.call_count, room_stir_before)  # leak rule
        sender.assert_called_once()
        _, kwargs = sender.call_args
        self.assertEqual(kwargs["recipients"], [self.sheet])

        instance_t5.refresh_from_db()
        self.assertEqual(instance_t5.status, MissionStatus.RESOLVED)
        _run(self.pc, f"report {instance_t5.pk} humble")  # the `report` surface
        instance_t5.refresh_from_db()
        self.assertEqual(instance_t5.status, MissionStatus.COMPLETE)

        # --- T6: Sworn Together (NPC offer, EXTERNAL_ACT/COVENANT_SWORN) ---
        t6_offer = self._offer("Swear the first oath")
        instance_t6 = self._accept_npc_offer(t6_offer)
        self.assertIsNotNone(instance_t6)
        self.assertEqual(instance_t6.template_id, self.t6.pk)
        # Not yet durably satisfied — the mission stays ACTIVE at its entry node.
        self.assertEqual(instance_t6.status, MissionStatus.ACTIVE)

        # T7 is gated on T6 completion — not yet visible.
        self.assertFalse(template_visible_to(self.t7, self.pc, persona=persona))

        co_founder_sheet = CharacterSheetFactory()
        covenant_role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        founders = [
            CovenantFounder(character_sheet=self.sheet, role=covenant_role, is_leader=True),
            CovenantFounder(character_sheet=co_founder_sheet, role=covenant_role),
        ]

        room_stir_before = self.room_stir.call_count
        with patch("world.missions.services.external_acts.send_narrative_message") as sender:
            create_covenant(
                name="Tutorial Bonds",
                covenant_type=CovenantType.DURANCE,
                sworn_objective="Prove the tutorial chain end to end.",
                founders=founders,
            )
        self.assertEqual(self.room_stir.call_count, room_stir_before)  # leak rule
        # Only the PC has a waiting mission — the co-founder has none, so
        # exactly one actor-only message is sent (never a room emit).
        sender.assert_called_once()
        _, kwargs = sender.call_args
        self.assertEqual(kwargs["recipients"], [self.sheet])

        instance_t6.refresh_from_db()
        self.assertEqual(instance_t6.status, MissionStatus.RESOLVED)
        # Still gated — has_completed_mission requires status=COMPLETE, not RESOLVED.
        self.assertFalse(template_visible_to(self.t7, self.pc, persona=persona))
        _run(self.pc, f"report {instance_t6.pk} humble")  # the `report` surface
        instance_t6.refresh_from_db()
        self.assertEqual(instance_t6.status, MissionStatus.COMPLETE)

        # --- T7: The Long Dark (gated on T6; risk-ack; LEGEND_POINTS) -----
        self.assertTrue(template_visible_to(self.t7, self.pc, persona=persona))

        t7_offer = self._offer("Answer the long dark's call")
        start = start_npc_interaction.run(actor=self.pc, role_id=t7_offer.role_id)
        self.assertTrue(start.success, start.message)
        session = start.data["session"]

        first_attempt = resolve_npc_offer.run(actor=self.pc, session=session, offer_id=t7_offer.pk)
        self.assertFalse(first_attempt.success)
        self.assertTrue(first_attempt.data.get("requires_risk_acknowledgement"))
        self.assertEqual(first_attempt.data.get("risk_tier"), 4)

        second_attempt = resolve_npc_offer.run(
            actor=self.pc,
            session=session,
            offer_id=t7_offer.pk,
            acknowledge_risk=True,
        )
        self.assertTrue(second_attempt.success, second_attempt.message)
        instance_t7 = (
            MissionInstance.objects.filter(participants__character=self.pc, source_offer=t7_offer)
            .order_by("-pk")
            .first()
        )
        self.assertIsNotNone(instance_t7)
        self.assertEqual(instance_t7.template_id, self.t7.pk)

        _run(self.pc, f"resolve {instance_t7.pk} 1")
        instance_t7.refresh_from_db()
        self.assertEqual(instance_t7.status, MissionStatus.RESOLVED)
        _run(self.pc, f"report {instance_t7.pk} humble")  # the `report` surface
        instance_t7.refresh_from_db()
        self.assertEqual(instance_t7.status, MissionStatus.COMPLETE)

        self.assertEqual(self.t7.risk_tier, 4)
        terminal_route = (
            self.t7.nodes.get(is_entry=True).options.get().routes.get(outcome_tier__isnull=True)
        )
        self.assertTrue(
            terminal_route.reward_templates.filter(sink=DeedRewardSink.LEGEND_POINTS).exists()
        )
        final_deed = instance_t7.deeds.order_by("-pk").first()
        self.assertTrue(final_deed.reward_lines.filter(sink=DeedRewardSink.LEGEND_POINTS).exists())

    def test_t6_fast_forwards_for_a_character_already_in_a_covenant(self) -> None:
        """The fast-forward proof (#1035): a PC already sworn to a covenant who
        accepts T6 has its EXTERNAL_ACT entry-node beat auto-resolve on entry —
        no player action needed. Uses ``staff_assign_mission`` directly (bypasses
        all availability filters) since the point here is ``enter_node``'s
        fast-forward, not re-proving the chain's visibility gating (already
        covered by the primary journey's explicit T7-gate assertion).
        """
        from world.missions.services.run import staff_assign_mission

        second_pc, second_sheet = self._make_pc("AlreadyBonded")
        CharacterCovenantRoleFactory(character_sheet=second_sheet)

        instance = staff_assign_mission(self.t6, second_pc)

        self.assertEqual(instance.status, MissionStatus.COMPLETE)
        self.assertIsNone(instance.current_node)
