"""Telnet E2E: 5-step weave/imbue/pull journey proves the full ceremony/finisher lifecycle.

Steps:
  1. CmdRitual → Rite of Weaving ceremony  → PendingRitualEffect (weaving)
  2. CmdWeaveThread → weave Ember of Endurance       → Thread row created, effect consumed
  3. CmdRitual → Rite of Imbuing ceremony  → PendingRitualEffect (imbuing)
  4. CmdImbue → imbue thread 5 points               → developed_points advanced, effect consumed
  5. spend_resonance_for_pull → tier-1 pull         → CharacterResonance.balance debited

This covers the happy-path end-to-end through the ceremony/finisher model introduced in
#1342. Supersedes test_thread_pull_pipeline.py (retired) for the pull step and
SpendResonanceForImbuingTests (retired from test_resonance_services.py) for the imbue step.
Steps 1 and 3 use CmdRitual (the real telnet path) to prove CEREMONY-kind rituals are
reachable from the telnet layer.

Step 5 was previously CmdPull (now removed — pull rides cast/clash); the spend/debit
path is exercised via spend_resonance_for_pull in ``test_weave_imbue_pull_journey``.

``test_cast_pull_changes_check_modifier`` (#1455 Task 9) upgrades to prove the OUTCOME
DELTA: a pull driven through ``CmdDeclareTechnique`` (the real cast surface) delivers a
higher ``extra_modifiers`` to ``perform_check`` than the baseline cast without a pull.
The FLAT_BONUS effect (3 points) is captured by patching ``actions.services.perform_check``
for determinism.  Resonance charge is also asserted so both invariants are covered.

SQLite tier: passes cleanly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from commands.combat import CmdDeclareTechnique
from commands.imbue import CmdImbue
from commands.ritual import CmdRitual
from commands.weave import CmdWeaveThread
from evennia_extensions.factories import ObjectDBFactory
from integration_tests.game_content.magic import seed_thread_pull_catalog
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ImbuingRitualFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
    ThreadWeavingUnlockFactory,
    WeavingCeremonyFactory,
)
from world.magic.models import CharacterResonance, CharacterTechnique, PendingRitualEffect, Thread
from world.magic.seeds_cast import ensure_technique_cast_content
from world.magic.services.resonance import spend_resonance_for_pull
from world.magic.types import PullActionContext
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.factories import PersonaFactory, SceneFactory
from world.traits.factories import CharacterTraitValueFactory, CheckSystemSetupFactory, TraitFactory
from world.vitals.models import CharacterVitals


class WeaveImbulePullJourneyE2ETests(TestCase):
    """5-step journey from ceremony through weave, imbue, and pull.

    The main journey test runs all five steps in a single method to prove chained
    state handoffs.

    A second test method (``test_cast_pull_changes_check_modifier``) proves #1455's
    "Done when": a pull driven through CmdDeclareTechnique changes the OUTCOME of the
    cast (higher extra_modifiers to perform_check) in addition to debiting resonance.
    It uses a separate TECHNIQUE-anchored thread wired to a dedicated technique, so
    it does not interfere with the TRAIT-anchored weaving thread from Steps 1–4.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.trait = TraitFactory()

        # Weaving unlock: TRAIT anchor on cls.trait
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TRAIT,
            unlock_trait=cls.trait,
        )
        CharacterThreadWeavingUnlockFactory(
            character=cls.sheet,
            unlock=unlock,
            xp_spent=100,
        )

        # Trait value: anchor cap for the TRAIT thread; controls how high the thread can level.
        # Value=50 gives anchor_cap=50 so imbuing 5 dp from level 0 can advance 5 levels.
        CharacterTraitValueFactory(
            character=cls.sheet,
            trait=cls.trait,
            value=50,
        )

        # Ceremonies
        cls.weaving_ritual = WeavingCeremonyFactory()
        cls.imbuing_ritual = ImbuingRitualFactory()

        # Seed tier-1 pull catalog (ThreadPullCost + ThreadPullEffect rows)
        cls.catalog = seed_thread_pull_catalog()

        # Resonance: use the catalog's canonical resonance so ThreadPullEffect rows match
        cls.resonance = cls.catalog.canonical_resonance

        # Resonance balance: enough to imbue (amount=5) and pull (tier-1 cost=1)
        CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )

        # Anima: pull hard-requires a CharacterAnima row
        CharacterAnimaFactory(
            character=cls.sheet.character,
            current=50,
            maximum=50,
        )

        # --- Infrastructure for test_cast_pull_changes_check_modifier ---
        # Standalone-cast action template shared by all techniques.
        cls.action_template = ensure_technique_cast_content()

        # A dedicated technique for the pull cast test (separate from weave/imbue).
        cls.cast_technique = TechniqueFactory(
            anima_cost=2,
            action_template=cls.action_template,
        )
        CharacterTechnique.objects.create(
            character=cls.sheet,
            technique=cls.cast_technique,
        )

        # TECHNIQUE-anchored thread on the catalog resonance → pull is applicable.
        # This thread is separate from the TRAIT-anchored thread from Step 2 so that
        # the weave/imbue journey is unaffected.
        cls.cast_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=cls.cast_technique,
            level=0,
            name="EmbersThread",  # Must be non-empty; cmd parses pull=<name>
        )

        # FLAT_BONUS effect for TECHNIQUE-kind threads on this resonance at tier=1.
        # The catalog's existing tier-1 effect is TRAIT-kind only; add TECHNIQUE-kind.
        # flat_bonus_amount=3 → scaled_value=3 (level=0 → multiplier=1).
        ThreadPullEffectFactory(
            target_kind=TargetKind.TECHNIQUE,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=3,
            effect_kind=EffectKind.FLAT_BONUS,
        )

        # Vitals (required by use_technique's soulfray check path).
        CharacterVitals.objects.create(
            character_sheet=cls.sheet,
            health=100,
            max_health=100,
            base_max_health=100,
        )

        # CharacterEngagement (required by some path-check helpers in the cast stack).
        CharacterEngagementFactory(character=cls.sheet.character)

    def setUp(self) -> None:
        """Create ObjectDB-backed objects per test method (DbHolder deepcopy guard)."""
        idmapper_models.flush_cache()
        CheckSystemSetupFactory.create()

        # Room + scene for the non-combat cast path.
        self.room = ObjectDBFactory(
            db_key="JourneyPullTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.scene = SceneFactory(location=self.room)
        self.sheet.character.db_location = self.room
        self.sheet.character.save()

        # Persona (persona.character_sheet must == self.sheet for the cast to route correctly).
        self.persona = PersonaFactory(character_sheet=self.sheet)

        # Use the real "Success" CheckOutcome so that select_consequence_from_result can compare
        # check_result.outcome against c.outcome_tier correctly (a MagicMock would fail the FK
        # assignment in the fallback path when the consequence pool has entries seeded by
        # ensure_technique_cast_content()).
        from world.traits.models import CheckOutcome

        success_outcome = CheckOutcome.objects.filter(name="Success").first()

        # Patch perform_check, accrue, anti-spam for determinism.
        self._check_patcher = patch("actions.services.perform_check")
        self._mock_check = self._check_patcher.start()
        self._mock_check.return_value = MagicMock(
            success_level=2,
            outcome=success_outcome,
            outcome_name="Success",
        )
        self._accrue_patcher = patch("world.scenes.action_services.accrue")
        self._accrue_patcher.start()
        self._antispam_patcher = patch(
            "commands.pending_actions.check_anti_spam",
            return_value=None,
        )
        self._antispam_patcher.start()

    def tearDown(self) -> None:
        self._check_patcher.stop()
        self._accrue_patcher.stop()
        self._antispam_patcher.stop()

    def _cmd_ritual(self, character: object, ritual_name: str) -> None:
        """Invoke CmdRitual for the given ritual name — the real telnet path."""
        cmd = CmdRitual()
        cmd.caller = character
        cmd.args = ritual_name
        cmd.raw_string = f"ritual {ritual_name}"
        cmd.func()

    def test_weave_imbue_pull_journey(self) -> None:
        character = self.sheet.character
        character.msg = MagicMock()

        # ------------------------------------------------------------------
        # Step 1: CmdRitual → Rite of Weaving ceremony → PendingRitualEffect
        # ------------------------------------------------------------------
        self._cmd_ritual(character, self.weaving_ritual.name)
        self.assertTrue(
            PendingRitualEffect.objects.filter(
                character=self.sheet,
                ritual=self.weaving_ritual,
            ).exists(),
            "Step 1: PendingRitualEffect for Rite of Weaving must exist after ceremony.",
        )

        # ------------------------------------------------------------------
        # Step 2: CmdWeaveThread → Thread created, pending effect consumed
        # ------------------------------------------------------------------
        cmd = CmdWeaveThread()
        cmd.caller = character
        cmd.args = f"resonance={self.resonance.name} trait={self.trait.pk} name=Ember of Endurance"
        cmd.raw_string = f"weave {cmd.args}"
        cmd.func()

        thread = Thread.objects.get(owner=self.sheet, name="Ember of Endurance")
        self.assertEqual(thread.resonance, self.resonance)
        self.assertFalse(
            PendingRitualEffect.objects.filter(
                character=self.sheet,
                ritual=self.weaving_ritual,
            ).exists(),
            "Step 2: PendingRitualEffect for Rite of Weaving must be consumed after weave.",
        )

        # ------------------------------------------------------------------
        # Step 3: CmdRitual → Rite of Imbuing ceremony → PendingRitualEffect
        # ------------------------------------------------------------------
        self._cmd_ritual(character, self.imbuing_ritual.name)
        self.assertTrue(
            PendingRitualEffect.objects.filter(
                character=self.sheet,
                ritual=self.imbuing_ritual,
            ).exists(),
            "Step 3: PendingRitualEffect for Rite of Imbuing must exist after ceremony.",
        )

        # ------------------------------------------------------------------
        # Step 4: CmdImbue → thread level advances, pending effect consumed
        # ------------------------------------------------------------------
        # Thread starts at level=0. Sub-10 levels each cost 1 dp. Imbuing 5 dp
        # → thread advances from level 0 to level 5 (5 levels × 1 dp each).
        level_before = thread.level  # 0
        cmd_imbue = CmdImbue()
        cmd_imbue.caller = character
        cmd_imbue.args = "thread=Ember of Endurance amount=5"
        cmd_imbue.raw_string = f"imbue {cmd_imbue.args}"
        cmd_imbue.func()

        thread.refresh_from_db()
        self.assertGreater(
            thread.level,
            level_before,
            "Step 4: Thread level must advance after imbuing 5 resonance.",
        )
        self.assertFalse(
            PendingRitualEffect.objects.filter(
                character=self.sheet,
                ritual=self.imbuing_ritual,
            ).exists(),
            "Step 4: PendingRitualEffect for Rite of Imbuing must be consumed after imbue.",
        )

        # ------------------------------------------------------------------
        # Step 5: spend_resonance_for_pull → CharacterResonance.balance debited
        # (CmdPull was removed — pull now rides cast/clash; this step exercises
        # the spend/debit path directly via the service layer.)
        # ------------------------------------------------------------------
        balance_before = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        ).balance

        # Fetch the TRAIT-anchored thread (the one from Step 2 "Ember of Endurance"),
        # not the TECHNIQUE-anchored cast_thread added for test_cast_pull_changes_check_modifier.
        pulled_thread = Thread.objects.get(
            owner=self.sheet, resonance=self.resonance, name="Ember of Endurance"
        )
        pull_ctx = PullActionContext(
            involved_traits=(self.trait.pk,),
            involved_techniques=(),
            involved_objects=(),
        )
        spend_resonance_for_pull(
            character_sheet=self.sheet,
            resonance=self.resonance,
            tier=1,
            threads=[pulled_thread],
            action_context=pull_ctx,
        )

        cr = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        )
        self.assertLess(
            cr.balance,
            balance_before,
            "Step 5: CharacterResonance.balance must be debited after pull.",
        )

    def test_cast_pull_changes_check_modifier(self) -> None:
        """Pull driven through CmdDeclareTechnique changes the cast OUTCOME (#1455 Task 9).

        Proves the "Done when" for the journey: a FLAT_BONUS pull delivered via the
        real telnet cast surface raises extra_modifiers to perform_check compared to
        the same cast without a pull.

        Determinism: perform_check is patched to return SL=2 (from setUp); we inspect
        the extra_modifiers kwarg passed to the mocked call.  FLAT_BONUS=3 at level=0
        → scaled_value=3 → extra_modifiers raised by 3.

        Also asserts resonance charge: balance must decrease after the pulled cast.
        """
        character = self.sheet.character
        character.msg = MagicMock()

        # --- Baseline: cast WITHOUT pull ---
        cmd_no_pull = CmdDeclareTechnique()
        cmd_no_pull.caller = character
        cmd_no_pull.args = self.cast_technique.name
        cmd_no_pull.raw_string = f"cast {self.cast_technique.name}"
        cmd_no_pull.cmdname = "cast"
        cmd_no_pull.func()

        no_pull_calls = self._mock_check.call_args_list[:]
        self.assertTrue(
            no_pull_calls,
            "perform_check must be called for the no-pull cast",
        )
        last_no_pull = no_pull_calls[-1]
        no_pull_extra = last_no_pull.kwargs.get(
            "extra_modifiers", (last_no_pull[1] or {}).get("extra_modifiers", 0)
        )

        # Reset mock call log before the pull cast.
        self._mock_check.reset_mock()

        # Restore anima spent by the first cast so the second can proceed.
        from world.magic.models import CharacterAnima

        anima = CharacterAnima.objects.get(character=character)
        anima.current = 50
        anima.save(update_fields=["current"])

        # Snapshot resonance balance before pulled cast.
        cr = CharacterResonance.objects.get(
            character_sheet=self.sheet,
            resonance=self.resonance,
        )
        balance_before_pull = cr.balance

        # --- Pulled cast: CmdDeclareTechnique with pull= and resonance= ---
        cmd_pull = CmdDeclareTechnique()
        cmd_pull.caller = character
        pull_args = (
            f"{self.cast_technique.name} "
            f"pull={self.cast_thread.name} resonance={self.resonance.name}"
        )
        cmd_pull.args = pull_args
        cmd_pull.raw_string = f"cast {pull_args}"
        cmd_pull.cmdname = "cast"
        cmd_pull.func()

        pull_calls = self._mock_check.call_args_list[:]
        self.assertTrue(
            pull_calls,
            "perform_check must be called for the pull cast",
        )
        last_pull = pull_calls[-1]
        pull_extra = last_pull.kwargs.get(
            "extra_modifiers", (last_pull[1] or {}).get("extra_modifiers", 0)
        )

        # --- Outcome delta assertion ---
        self.assertGreater(
            pull_extra,
            no_pull_extra,
            f"extra_modifiers with pull ({pull_extra}) must exceed without pull "
            f"({no_pull_extra}); FLAT_BONUS=3 at level=0 → scaled_value=3 should "
            "add 3 to the check modifier delivered to perform_check.",
        )

        # --- Charge assertion ---
        cr.refresh_from_db()
        self.assertLess(
            cr.balance,
            balance_before_pull,
            "CharacterResonance.balance must be debited after CmdDeclareTechnique pull=.",
        )
