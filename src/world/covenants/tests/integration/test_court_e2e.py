"""Capstone E2E journey for the Covenant of the Court (#1589).

Proves the whole Court feature end-to-end on one themed Court, exercising the real
systems (no mocking the system under test):

  1. **Fealty spotlight** — a far-below servant swears fealty into the Court via the
     ritual-session induction path (``induct_member_via_session``). Asserts an active
     ``CourtPact`` carrying the master-granted pull cap AND a servant-centred fealty
     ``NarrativeMessage``.
  2. **Mission-gated engagement** — with NO active Court mission the founding servant's
     Court vow does NOT engage; with the active master-org mission it DOES (both
     directions, via ``can_engage_membership`` + ``evaluate_scene_engagement``).
  3. **Capped pull changes the outcome** — the servant weaves a COVENANT_ROLE thread,
     and (a) the thread's effective cap is BOUNDED by ``CourtPact.granted_pull_cap``
     (imbuing past it raises ``AnchorCapExceeded``); (b) committing the (two-thread) pull
     in combat debits BOTH resonance AND anima; (c) its FLAT_BONUS surfaces on the combat
     offense read-path (``_sum_active_flat_bonuses``) — the value fed into the offense
     check; (d) driving the REAL offense-check resolver (``CombatTechniqueResolver
     ._roll_check``) WITH the committed pull vs WITHOUT it yields a strictly higher
     resolved ``CheckResult.total_points`` (the graded roll target) — the outcome, not
     just the input.
  4. **Auto-dissolve** — when the last servant leaves and only the master remains, the
     Court auto-dissolves (``dissolved_at`` set; ADR-0042 two-member floor).

Wiring notes (documented per the task brief):
- The seed (``make_court_with_mission``) seats the founding servant through
  ``create_covenant`` (founder path), which does NOT run the fealty induction — so the
  founding servant has no ``CourtPact``. Step 1 inducts a SECOND, fresh servant through
  the real INDUCTION session to assert the fealty ceremony; step 3 swears a pact for the
  founding servant directly (the documented "swear the pact for the seed servant" path)
  so its Court-role thread has a non-zero cap to pull.
- The COVENANT_ROLE thread is created via ``Thread.objects.create`` (the established
  integration-test pattern, mirroring ``test_resonance_subrole_flow``) rather than the
  weaving-unlock command path — weaving acquisition is out of scope for this journey.
- The combat pull is committed through ``commit_combat_pull`` — the exact shared seam
  ``CastTechniqueAction.round_declaration`` calls — so it persists a real ``CombatPull``,
  debits resonance/anima, and writes the resolved-effect snapshots the read-path consumes.

The resolved-outcome drive (step 3d) routes through ``collect_check_modifiers`` +
``perform_check`` with a fixed die; the resolver's ``offense_check_fn`` injection seam is
left at ``None`` so production ``perform_check`` runs for real (nothing under test is
mocked). If this path ever pulls in a PG-only ``DISTINCT ON`` dependency it should move to
a ``@tag("postgres")`` method; at authoring time it runs cleanly on the SQLite fast tier.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.models import CombatPull
from world.combat.pull_helpers import commit_combat_pull
from world.combat.services import CombatTechniqueResolver, _sum_active_flat_bonuses
from world.covenants.factories import make_court_with_mission, wire_court_role_powers_catalog
from world.covenants.handlers import can_engage_membership
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import (
    active_court_pact_for,
    evaluate_scene_engagement,
    induct_member_via_session,
    leave_covenant,
    swear_court_pact,
)
from world.magic.constants import ParticipantState, ParticipationRule, ReferenceKind, TargetKind
from world.magic.exceptions import AnchorCapExceeded
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    RitualFactory,
    ThreadFactory,
    ThreadPullCostFactory,
)
from world.magic.models import CharacterAnima, CharacterResonance, Thread
from world.magic.models.sessions import (
    RitualSession,
    RitualSessionParticipant,
    RitualSessionReference,
)
from world.magic.services import compute_effective_cap
from world.magic.services.resonance import spend_resonance_for_imbuing
from world.magic.types.pull import CastPullDeclaration
from world.missions.constants import MissionStatus
from world.narrative.models import NarrativeMessage
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory


def _set_primary_level(sheet: object, level: int) -> None:
    """Give sheet.character a primary CharacterClassLevel at the given level."""
    CharacterClassLevelFactory(
        character=sheet,
        character_class=CharacterClassFactory(),
        level=level,
        is_primary=True,
    )
    sheet.invalidate_class_level_cache()


class CourtJourneyEndToEndTests(TestCase):
    """One cohesive journey across the Court feature on a single themed Court."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        # The complete themed Court: master (lvl 11 / tier 3), founding servant
        # (lvl 1 / tier 1) seated on the Court "Shadowblade" role, plus an ACTIVE
        # master-org mission with the servant as a participant.
        self.seed = make_court_with_mission()
        self.covenant = self.seed.covenant
        self.master = self.seed.master_sheet
        self.servant = self.seed.servant_sheet
        self.mission = self.seed.mission_instance
        self.role = self.seed.themed_role

        # Re-derive the seeded pull catalog (idempotent) to get the FLAT_BONUS
        # ThreadPullEffect rows + their court-themed resonances.
        catalog_role, self.flat_effects = wire_court_role_powers_catalog()
        self.assertEqual(catalog_role, self.role)
        self.resonance = self.flat_effects[0].resonance

        # The founding servant's active membership row.
        self.membership = CharacterCovenantRole.objects.get(
            character_sheet=self.servant,
            covenant=self.covenant,
            left_at__isnull=True,
        )

    # ------------------------------------------------------------------
    # Step 1 — Fealty spotlight: a fresh servant swears fealty via induction.
    # ------------------------------------------------------------------
    def _build_induction_session(self, *, candidate, granted_pull_cap):
        """Build a fire-ready INDUCTION session targeting the seed Court.

        The master (already a member, sitting a power-tier above) is the vouching
        initiator; the candidate is the one ACCEPTED participant carrying a
        COVENANT_ROLE reference + ``granted_pull_cap`` in participant_kwargs.
        """
        ritual = RitualFactory(participation_rule=ParticipationRule.INDUCTION)
        session = RitualSession.objects.create(
            ritual=ritual,
            initiator=self.master,
            session_kwargs={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=None,
            kind=ReferenceKind.COVENANT,
            ref_covenant=self.covenant,
        )
        RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=self.master,
            state=ParticipantState.ACCEPTED,
        )
        candidate_p = RitualSessionParticipant.objects.create(
            session=session,
            character_sheet=candidate,
            state=ParticipantState.ACCEPTED,
            participant_kwargs={"granted_pull_cap": granted_pull_cap},
        )
        RitualSessionReference.objects.create(
            session=session,
            participant=candidate_p,
            kind=ReferenceKind.COVENANT_ROLE,
            ref_covenant_role=self.role,
        )
        return session

    def test_court_journey_end_to_end(self) -> None:  # noqa: PLR0915
        # A deliberately cohesive end-to-end journey: the four feature steps share
        # one themed Court and hand state from one step to the next, so the high
        # statement count is intrinsic (splitting would obscure the journey).
        # ==============================================================
        # STEP 1 — Fealty spotlight (fresh servant swears into the Court).
        # ==============================================================
        newcomer = CharacterSheetFactory(character__db_key="Kneeling Newcomer")
        _set_primary_level(newcomer, 1)  # tier 1, far below the master's tier 3
        session = self._build_induction_session(candidate=newcomer, granted_pull_cap=3)

        induct_member_via_session(session=session)

        pact = active_court_pact_for(covenant=self.covenant, servant_sheet=newcomer)
        self.assertIsNotNone(pact, "Induction into a Court must swear a CourtPact.")
        self.assertEqual(
            pact.granted_pull_cap,
            3,
            "The master-granted pull cap (from participant_kwargs) must be recorded.",
        )

        newcomer_name = newcomer.character.db_key
        fealty_msg = (
            NarrativeMessage.objects.filter(body__contains=newcomer_name).order_by("-id").first()
        )
        self.assertIsNotNone(fealty_msg, "A fealty NarrativeMessage must be emitted.")
        # The SERVANT is the focal/grammatical subject — the body opens with their
        # name and centres their act of swearing fealty.
        self.assertTrue(fealty_msg.body.startswith(newcomer_name))
        self.assertIn("fealty", fealty_msg.body.lower())
        self.assertFalse(
            fealty_msg.body.startswith(self.master.character.db_key),
            "The master is backdrop, not the grammatical subject.",
        )

        # ==============================================================
        # STEP 2 — Mission-gated engagement (both directions).
        # ==============================================================
        room = ObjectDBFactory(
            db_key="CourtJourneyRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        # (a) NO active Court mission → the Court vow does NOT engage.
        self.mission.status = MissionStatus.COMPLETE
        self.mission.save(update_fields=["status"])
        self.servant.character.covenant_roles.invalidate()
        self.assertFalse(
            can_engage_membership(self.membership),
            "Without an active Court mission, the Court vow must not be engageable.",
        )
        evaluate_scene_engagement(character_sheet=self.servant, room=room)
        self.membership.refresh_from_db()
        self.assertFalse(
            self.membership.engaged,
            "evaluate_scene_engagement must not engage a Court role with no active mission.",
        )

        # (b) Active Court mission → the Court vow ENGAGES.
        self.mission.status = MissionStatus.ACTIVE
        self.mission.save(update_fields=["status"])
        self.servant.character.covenant_roles.invalidate()
        self.assertTrue(
            can_engage_membership(self.membership),
            "On the master's active business, the Court vow must be engageable.",
        )
        evaluate_scene_engagement(character_sheet=self.servant, room=room)
        self.membership.refresh_from_db()
        self.assertTrue(
            self.membership.engaged,
            "evaluate_scene_engagement must engage the Court role on the active mission.",
        )

        # ==============================================================
        # STEP 3 — Capped pull changes the offense read-path.
        # ==============================================================
        # The founding servant joined as a founder (no fealty induction), so swear
        # a pact directly with a small grant that BINDS below the covenant floor
        # (level 1 → covenant_component = 10; grant = 2 is the binding cap).
        granted = 2
        swear_court_pact(
            covenant=self.covenant,
            servant_sheet=self.servant,
            granted_pull_cap=granted,
        )

        # Resonance currency (covers imbue + pull) + anima for the pull.
        CharacterResonanceFactory(
            character_sheet=self.servant,
            resonance=self.resonance,
            balance=20,
        )
        CharacterAnimaFactory(character=self.servant.character, current=10, maximum=20)
        # anima_per_thread=1 so a multi-thread pull actually debits anima
        # (cost = anima_per_thread × max(0, n_threads - 1); a lone thread is free).
        ThreadPullCostFactory(tier=1, resonance_cost=1, anima_per_thread=1)

        thread = Thread.objects.create(
            owner=self.servant,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.role,
            level=0,
            developed_points=0,
            name="Cord of the Shadowblade",
        )
        # A second, always-in-action thread on the same resonance so the pull
        # carries two threads — the anima cost (1 × (2 - 1) = 1) actually fires.
        companion_thread = ThreadFactory(
            owner=self.servant,
            resonance=self.resonance,
            as_track_thread=True,
        )

        # (3a) The effective cap is BOUNDED by the master's granted cap.
        self.assertEqual(
            compute_effective_cap(thread),
            granted,
            "The Court-role thread's cap must be bounded by CourtPact.granted_pull_cap.",
        )
        # Imbuing greedily raises the thread up TO the cap (level 2), no further.
        spend_resonance_for_imbuing(self.servant, thread, 5)
        thread.refresh_from_db()
        self.assertEqual(
            thread.level,
            granted,
            "Imbuing must stop at the granted cap (level == granted_pull_cap).",
        )
        # A pull/imbue ABOVE the granted level is rejected by the cap.
        with self.assertRaises(AnchorCapExceeded):
            spend_resonance_for_imbuing(self.servant, thread, 1)

        # Combat context for the pull.
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=self.servant,
            status=ParticipantStatus.ACTIVE,
        )

        # Baseline: no pull yet → the offense read-path sees no flat bonus.
        self.servant.character.combat_pulls.invalidate()
        self.assertEqual(
            _sum_active_flat_bonuses(participant, encounter),
            0,
            "Before any pull, the offense flat-bonus read-path must be zero.",
        )

        balance_before = CharacterResonance.objects.get(
            character_sheet=self.servant,
            resonance=self.resonance,
        ).balance
        anima_before = CharacterAnima.objects.get(character=self.servant.character).current

        cast_pull = CastPullDeclaration(
            resonance=self.resonance,
            tier=1,
            threads=(thread, companion_thread),
        )
        commit_combat_pull(cast_pull, participant, encounter, technique_id=0)

        # (3b) The pull pays resonance AND anima.
        balance_after = CharacterResonance.objects.get(
            character_sheet=self.servant,
            resonance=self.resonance,
        ).balance
        self.assertLess(
            balance_after,
            balance_before,
            "Committing the Court-role pull must debit resonance.",
        )
        anima_after = CharacterAnima.objects.get(character=self.servant.character).current
        self.assertLess(
            anima_after,
            anima_before,
            "Committing a multi-thread Court-role pull must debit anima "
            "(anima_per_thread=1 × (2 threads - 1) = 1).",
        )
        self.assertTrue(
            CombatPull.objects.filter(participant=participant, round_number=1).exists(),
            "A CombatPull row must be persisted for the round.",
        )

        # (3c) The FLAT_BONUS now surfaces on the offense read-path — the exact
        # value fed into the offense check as extra_modifiers. With-pull (>0)
        # vs without-pull (0 baseline above) is the outcome change.
        self.servant.character.combat_pulls.invalidate()
        with_pull = _sum_active_flat_bonuses(participant, encounter)
        self.assertGreater(
            with_pull,
            0,
            "After the Court-role pull, the offense flat-bonus must be positive "
            "(the FLAT_BONUS changes the offense-check extra_modifiers).",
        )

        # (3c-outcome) Prove the OUTCOME, not just the read-path input. Drive the
        # ACTUAL offense check resolution combat performs at round resolution —
        # CombatTechniqueResolver._roll_check, which folds the committed pull's
        # FLAT_BONUS through the collect_check_modifiers seam into the rolled
        # modifier total — WITH the committed pull's bonus vs WITHOUT it, and assert
        # the RESOLVED CheckResult differs: total_points (the value the offense roll
        # is graded against) is higher by exactly the pull bonus, and the resolved
        # rank gap is no worse. The resolver and its modifier seam run for real; only
        # the die is fixed (a controlled roll), so the resolved outcome is stable.
        CheckSystemSetupFactory.create()
        offense_check_type = CheckTypeFactory()
        round_action = CombatRoundActionFactory(participant=participant, round_number=1)

        def _resolve_offense(pull_flat_bonus: int):
            resolver = CombatTechniqueResolver(
                participant=participant,
                action=round_action,
                pull_flat_bonus=pull_flat_bonus,
                fatigue_category=ActionCategory.PHYSICAL,
                offense_check_type=offense_check_type,
                offense_check_fn=None,
            )
            with patch("world.checks.services.random.randint", return_value=50):
                return resolver._roll_check()

        resolved_without = _resolve_offense(0)
        resolved_with = _resolve_offense(with_pull)
        self.assertEqual(
            resolved_with.total_points - resolved_without.total_points,
            with_pull,
            "The committed pull's FLAT_BONUS must raise the resolved offense-check "
            "total_points by exactly the pull bonus (it survives collect_check_modifiers).",
        )
        self.assertGreater(
            resolved_with.total_points,
            resolved_without.total_points,
            "The resolved offense check must grade against a strictly higher total with the pull.",
        )
        self.assertGreaterEqual(
            resolved_with.rank_difference,
            resolved_without.rank_difference,
            "The pull must never worsen the resolved rank gap (monotonic in total_points).",
        )

        # ==============================================================
        # STEP 4 — Auto-dissolve when only the master remains.
        # ==============================================================
        # Two servants now (founder + inducted newcomer); removing both leaves only
        # the master → the Court dissolves (ADR-0042 two-member floor).
        newcomer_membership = CharacterCovenantRole.objects.get(
            character_sheet=newcomer,
            covenant=self.covenant,
            left_at__isnull=True,
        )
        leave_covenant(membership=self.membership)
        self.covenant.refresh_from_db()
        self.assertIsNone(
            self.covenant.dissolved_at,
            "The Court must survive while a servant (the newcomer) still remains.",
        )

        leave_covenant(membership=newcomer_membership)
        self.covenant.refresh_from_db()
        self.assertIsNotNone(
            self.covenant.dissolved_at,
            "The Court must auto-dissolve once only the master remains.",
        )
