"""TDD tests for Task 6 (#1455): web combat cast-declaration + clash carry a pull via raw IDs.

The web path (JSON dispatch) sends pull IDs rather than a pre-built
``CastPullDeclaration`` object.  This module verifies:

1. ``build_cast_pull_declaration`` resolves valid IDs into a ``CastPullDeclaration``.
2. ``build_cast_pull_declaration`` raises ``InvalidImbueAmount`` on bad IDs
   (unknown resonance, thread owned by a different sheet, retired thread).
3. ``resolve_pull_from_kwargs`` normalises both forms:
   - pre-built ``CastPullDeclaration`` (telnet) → returned as-is.
   - raw ``pull_resonance_id`` / ``pull_tier`` / ``pull_thread_ids`` IDs (web) →
     builds via ``build_cast_pull_declaration``.
   - absent → ``None``.
4. A combat cast ``round_declaration`` carrying web-form IDs commits a
   ``CombatPull`` row visible to the read-path
   (``_sum_active_flat_bonuses`` / ``compute_intensity_for_clash``).
5. A clash ``_dispatch_clash_contribution`` carrying web-form IDs commits a
   ``CombatPull`` row and the read-path reflects it.
6. The one-pull-per-round cap fires via the ID path.
7. The telnet object form (``cast_pull=CastPullDeclaration``) still works (regression
   guard).

SQLite tier limits: same as Tasks 4/5 — commit + read-path assertions only; no full
PG-only resolution.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.models import CombatPull
from world.combat.round_context import CombatRoundContext
from world.combat.services import _sum_active_flat_bonuses, compute_intensity_for_clash
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.types.pull import CastPullDeclaration
from world.scenes.constants import RoundStatus


def _make_web_pull_setup(
    *,
    effect_kind: str = EffectKind.FLAT_BONUS,
    tier: int = 1,
    flat_bonus_amount: int = 3,
    intensity_bump_amount: int | None = None,
) -> dict:
    """Build a full pull-enabled combat scene and return a dict of useful objects.

    Mirrors ``_make_pull_setup`` from Task 4/5 tests but also exposes the raw IDs
    that the web path would send (``resonance_id``, ``thread_ids``).

    Creates:
    - A CharacterSheet with resonance, anima, and a TECHNIQUE-anchored Thread.
    - A Technique that matches the thread's anchor.
    - A ThreadPullCost row for the given tier.
    - A ThreadPullEffect row that will yield a non-zero applicable effect.
    - A CombatEncounter in DECLARING status + a CombatParticipant for the sheet.
    - A CombatRoundContext wrapping the participant.
    - Both a pre-built CastPullDeclaration AND the raw web-form IDs.
    """
    sheet = CharacterSheetFactory()
    resonance = ResonanceFactory()

    technique = TechniqueFactory()

    thread = ThreadFactory(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.TECHNIQUE,
        target_technique=technique,
        target_trait=None,
        level=5,
    )

    CharacterResonanceFactory(
        character_sheet=sheet,
        resonance=resonance,
        balance=10,
    )

    CharacterAnimaFactory(
        character=sheet.character,
        current=10,
        maximum=20,
    )

    ThreadPullCostFactory(tier=tier, resonance_cost=1, anima_per_thread=0)

    if effect_kind == EffectKind.INTENSITY_BUMP:
        ThreadPullEffectFactory(
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            tier=tier,
            min_thread_level=0,
            effect_kind=EffectKind.INTENSITY_BUMP,
            intensity_bump_amount=intensity_bump_amount if intensity_bump_amount else 2,
            flat_bonus_amount=None,
        )
    else:
        ThreadPullEffectFactory(
            resonance=resonance,
            target_kind=TargetKind.TECHNIQUE,
            tier=tier,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=flat_bonus_amount,
        )

    encounter = CombatEncounterFactory(
        status=RoundStatus.DECLARING,
        round_number=1,
    )
    participant = CombatParticipantFactory(
        encounter=encounter,
        character_sheet=sheet,
        status=ParticipantStatus.ACTIVE,
    )
    ctx = CombatRoundContext(participant)

    # Pre-built form (telnet).
    pull_decl = CastPullDeclaration(
        resonance=resonance,
        tier=tier,
        threads=(thread,),
    )

    # Raw ID form (web).
    web_kwargs = {
        "pull_resonance_id": resonance.pk,
        "pull_tier": tier,
        "pull_thread_ids": [thread.pk],
    }

    return {
        "sheet": sheet,
        "resonance": resonance,
        "technique": technique,
        "thread": thread,
        "encounter": encounter,
        "participant": participant,
        "ctx": ctx,
        "pull_decl": pull_decl,
        "web_kwargs": web_kwargs,
    }


# ---------------------------------------------------------------------------
# build_cast_pull_declaration unit tests
# ---------------------------------------------------------------------------


class BuildCastPullDeclarationTests(TestCase):
    """``build_cast_pull_declaration`` resolves IDs or raises on bad input."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_valid_ids_return_declaration(self) -> None:
        """Valid sheet + resonance + thread IDs produce a CastPullDeclaration."""
        from world.combat.pull_helpers import build_cast_pull_declaration

        data = _make_web_pull_setup()
        decl = build_cast_pull_declaration(
            data["sheet"].pk,
            resonance_id=data["resonance"].pk,
            tier=1,
            thread_ids=[data["thread"].pk],
        )
        self.assertIsInstance(decl, CastPullDeclaration)
        self.assertEqual(decl.resonance, data["resonance"])
        self.assertEqual(decl.tier, 1)
        self.assertIn(data["thread"], decl.threads)

    def test_unknown_resonance_raises_invalid_imbue(self) -> None:
        """An unknown resonance_id raises InvalidImbueAmount."""
        from world.combat.pull_helpers import build_cast_pull_declaration
        from world.magic.exceptions import InvalidImbueAmount

        data = _make_web_pull_setup()
        with self.assertRaises(InvalidImbueAmount):
            build_cast_pull_declaration(
                data["sheet"].pk,
                resonance_id=999999,
                tier=1,
                thread_ids=[data["thread"].pk],
            )

    def test_thread_owned_by_other_sheet_raises_invalid_imbue(self) -> None:
        """A thread belonging to a different sheet raises InvalidImbueAmount."""
        from world.combat.pull_helpers import build_cast_pull_declaration
        from world.magic.exceptions import InvalidImbueAmount

        data = _make_web_pull_setup()
        other_sheet = CharacterSheetFactory()
        with self.assertRaises(InvalidImbueAmount):
            build_cast_pull_declaration(
                other_sheet.pk,
                resonance_id=data["resonance"].pk,
                tier=1,
                thread_ids=[data["thread"].pk],
            )

    def test_retired_thread_raises_invalid_imbue(self) -> None:
        """A retired thread raises InvalidImbueAmount."""
        import datetime

        from django.utils import timezone

        from world.combat.pull_helpers import build_cast_pull_declaration
        from world.magic.exceptions import InvalidImbueAmount

        data = _make_web_pull_setup()
        thread = data["thread"]
        thread.retired_at = timezone.now() - datetime.timedelta(days=1)
        thread.save()
        with self.assertRaises(InvalidImbueAmount):
            build_cast_pull_declaration(
                data["sheet"].pk,
                resonance_id=data["resonance"].pk,
                tier=1,
                thread_ids=[thread.pk],
            )


# ---------------------------------------------------------------------------
# resolve_pull_from_kwargs unit tests
# ---------------------------------------------------------------------------


class ResolvePullFromKwargsTests(TestCase):
    """``resolve_pull_from_kwargs`` normalises telnet-object and web-ID forms."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_prebuilt_declaration_returned_as_is(self) -> None:
        """A pre-built CastPullDeclaration in kwargs['cast_pull'] is returned directly."""
        from world.combat.pull_helpers import resolve_pull_from_kwargs

        data = _make_web_pull_setup()
        result = resolve_pull_from_kwargs(
            data["sheet"],
            {"cast_pull": data["pull_decl"]},
        )
        self.assertIs(result, data["pull_decl"])

    def test_web_id_form_builds_declaration(self) -> None:
        """Raw pull_resonance_id / pull_tier / pull_thread_ids produce a CastPullDeclaration."""
        from world.combat.pull_helpers import resolve_pull_from_kwargs

        data = _make_web_pull_setup()
        result = resolve_pull_from_kwargs(data["sheet"], data["web_kwargs"])
        self.assertIsInstance(result, CastPullDeclaration)
        self.assertEqual(result.resonance, data["resonance"])
        self.assertIn(data["thread"], result.threads)

    def test_empty_kwargs_returns_none(self) -> None:
        """No pull-related keys → None."""
        from world.combat.pull_helpers import resolve_pull_from_kwargs

        data = _make_web_pull_setup()
        result = resolve_pull_from_kwargs(data["sheet"], {})
        self.assertIsNone(result)

    def test_partial_web_kwargs_returns_none(self) -> None:
        """Only some web keys present (missing pull_thread_ids) → None."""
        from world.combat.pull_helpers import resolve_pull_from_kwargs

        data = _make_web_pull_setup()
        result = resolve_pull_from_kwargs(
            data["sheet"],
            {"pull_resonance_id": data["resonance"].pk, "pull_tier": 1},
        )
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Combat cast round_declaration via web ID form
# ---------------------------------------------------------------------------


class CombatCastWebPullTests(TestCase):
    """round_declaration carrying web-form IDs commits a CombatPull."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def _import_cast_action(self):
        from actions.definitions.cast import CastTechniqueAction

        return CastTechniqueAction()

    def test_web_pull_ids_create_combat_pull(self) -> None:
        """round_declaration with web-form IDs persists a CombatPull for (participant, round)."""
        data = _make_web_pull_setup()
        action = self._import_cast_action()

        kwargs = {"technique_id": data["technique"].pk, **data["web_kwargs"]}
        result = action.round_declaration(data["ctx"], **kwargs)

        self.assertIsNotNone(result, "round_declaration should return a tuple.")
        pull_qs = CombatPull.objects.filter(
            participant=data["participant"],
            round_number=data["encounter"].round_number,
        )
        self.assertTrue(
            pull_qs.exists(),
            "A CombatPull row must be created when web-form IDs are declared.",
        )
        pull = pull_qs.get()
        self.assertEqual(pull.resonance, data["resonance"])
        self.assertEqual(pull.tier, 1)
        self.assertIn(data["thread"], pull.threads.all())

    def test_web_pull_debits_resonance(self) -> None:
        """Resonance balance decreases after a web-form combat cast pull."""
        from world.magic.models import CharacterResonance

        data = _make_web_pull_setup()
        action = self._import_cast_action()

        cr_before = CharacterResonance.objects.get(
            character_sheet=data["sheet"],
            resonance=data["resonance"],
        )
        balance_before = cr_before.balance

        action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            **data["web_kwargs"],
        )

        cr_before.refresh_from_db()
        self.assertLess(
            cr_before.balance,
            balance_before,
            "Resonance balance must decrease after a web-form combat cast pull.",
        )

    def test_web_pull_visible_to_flat_bonus_read_path(self) -> None:
        """_sum_active_flat_bonuses reflects the CombatPull from a web-form cast pull."""
        data = _make_web_pull_setup(effect_kind=EffectKind.FLAT_BONUS, flat_bonus_amount=3)
        action = self._import_cast_action()

        action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            **data["web_kwargs"],
        )

        data["sheet"].character.combat_pulls.invalidate()
        bonus = _sum_active_flat_bonuses(data["participant"], data["encounter"])
        self.assertGreater(
            bonus,
            0,
            "_sum_active_flat_bonuses must return > 0 after a web-form FLAT_BONUS pull.",
        )

    def test_web_pull_visible_to_intensity_read_path(self) -> None:
        """compute_intensity_for_clash reflects the CombatPull from a web-form cast pull."""
        data = _make_web_pull_setup(effect_kind=EffectKind.INTENSITY_BUMP, intensity_bump_amount=2)
        action = self._import_cast_action()

        action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            **data["web_kwargs"],
        )

        round_action = CombatRoundActionFactory(
            participant=data["participant"],
            focused_action=data["technique"],
        )

        data["sheet"].character.combat_pulls.invalidate()
        intensity = compute_intensity_for_clash(data["participant"], round_action)
        self.assertGreaterEqual(
            intensity,
            data["technique"].intensity + 2,
            "compute_intensity_for_clash must include the INTENSITY_BUMP pull bonus.",
        )

    def test_second_web_pull_same_round_fails_with_already_committed(self) -> None:
        """A second web-form pull in the same round raises PULL_ALREADY_COMMITTED."""
        from actions.errors import ActionDispatchError

        data = _make_web_pull_setup()
        action = self._import_cast_action()

        first = action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            **data["web_kwargs"],
        )
        self.assertIsNotNone(first, "First web-form pull must succeed.")

        with self.assertRaises(ActionDispatchError) as cm:
            action.round_declaration(
                data["ctx"],
                technique_id=data["technique"].pk,
                **data["web_kwargs"],
            )
        self.assertEqual(cm.exception.code, ActionDispatchError.PULL_ALREADY_COMMITTED)

        self.assertEqual(
            CombatPull.objects.filter(
                participant=data["participant"],
                round_number=data["encounter"].round_number,
            ).count(),
            1,
        )

    def test_telnet_object_form_still_works_regression(self) -> None:
        """The pre-built CastPullDeclaration (telnet) form still commits a CombatPull."""
        data = _make_web_pull_setup()
        action = self._import_cast_action()

        result = action.round_declaration(
            data["ctx"],
            technique_id=data["technique"].pk,
            cast_pull=data["pull_decl"],
        )
        self.assertIsNotNone(result)
        self.assertTrue(
            CombatPull.objects.filter(
                participant=data["participant"],
                round_number=data["encounter"].round_number,
            ).exists(),
            "Telnet CastPullDeclaration object form must still create a CombatPull.",
        )


# ---------------------------------------------------------------------------
# Clash _dispatch_clash_contribution via web ID form
# ---------------------------------------------------------------------------


class ClashWebPullTests(TestCase):
    """_dispatch_clash_contribution carrying web-form IDs commits a CombatPull."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()

    def test_clash_web_pull_creates_combat_pull_row(self) -> None:
        """Web-form IDs in _dispatch_clash_contribution persist a CombatPull row."""
        from world.combat.pull_helpers import commit_combat_pull, resolve_pull_from_kwargs

        data = _make_web_pull_setup()
        sheet = data["sheet"]

        # Simulate what _dispatch_clash_contribution does: resolve_pull_from_kwargs
        # then commit_combat_pull.
        cast_pull = resolve_pull_from_kwargs(sheet, data["web_kwargs"])
        self.assertIsNotNone(cast_pull, "resolve_pull_from_kwargs must return a declaration.")

        commit_combat_pull(
            cast_pull=cast_pull,
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )

        pull_qs = CombatPull.objects.filter(
            participant=data["participant"],
            round_number=data["encounter"].round_number,
        )
        self.assertTrue(
            pull_qs.exists(),
            "A CombatPull row must be created when clash carries web-form pull IDs.",
        )
        pull = pull_qs.get()
        self.assertEqual(pull.resonance, data["resonance"])
        self.assertIn(data["thread"], pull.threads.all())

    def test_clash_web_pull_visible_to_flat_bonus_read_path(self) -> None:
        """_sum_active_flat_bonuses reflects the CombatPull committed via web clash path."""
        from world.combat.pull_helpers import commit_combat_pull, resolve_pull_from_kwargs

        data = _make_web_pull_setup(effect_kind=EffectKind.FLAT_BONUS, flat_bonus_amount=3)

        cast_pull = resolve_pull_from_kwargs(data["sheet"], data["web_kwargs"])
        commit_combat_pull(
            cast_pull=cast_pull,
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )

        data["sheet"].character.combat_pulls.invalidate()
        bonus = _sum_active_flat_bonuses(data["participant"], data["encounter"])
        self.assertGreater(
            bonus,
            0,
            "_sum_active_flat_bonuses must return > 0 after a web-form FLAT_BONUS clash pull.",
        )

    def test_clash_web_pull_visible_to_intensity_read_path(self) -> None:
        """compute_intensity_for_clash returns a higher value with a web-form clash pull."""
        from world.combat.pull_helpers import commit_combat_pull, resolve_pull_from_kwargs

        data = _make_web_pull_setup(effect_kind=EffectKind.INTENSITY_BUMP, intensity_bump_amount=2)

        round_action = CombatRoundActionFactory(
            participant=data["participant"],
            focused_action=data["technique"],
        )

        data["sheet"].character.combat_pulls.invalidate()
        intensity_before = compute_intensity_for_clash(data["participant"], round_action)

        cast_pull = resolve_pull_from_kwargs(data["sheet"], data["web_kwargs"])
        commit_combat_pull(
            cast_pull=cast_pull,
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )

        data["sheet"].character.combat_pulls.invalidate()
        intensity_after = compute_intensity_for_clash(data["participant"], round_action)

        self.assertGreater(
            intensity_after,
            intensity_before,
            "compute_intensity_for_clash must be higher after a web-form clash pull.",
        )
        self.assertGreaterEqual(
            intensity_after,
            data["technique"].intensity + 2,
        )

    def test_clash_web_pull_second_pull_same_round_fails(self) -> None:
        """The one-pull-per-round cap still fires via the web ID form for clash."""
        from actions.errors import ActionDispatchError
        from world.combat.pull_helpers import commit_combat_pull, resolve_pull_from_kwargs

        data = _make_web_pull_setup()
        sheet = data["sheet"]

        cast_pull = resolve_pull_from_kwargs(sheet, data["web_kwargs"])
        commit_combat_pull(
            cast_pull=cast_pull,
            participant=data["participant"],
            encounter=data["encounter"],
            technique_id=data["technique"].pk,
        )

        cast_pull2 = resolve_pull_from_kwargs(sheet, data["web_kwargs"])
        with self.assertRaises(ActionDispatchError) as cm:
            commit_combat_pull(
                cast_pull=cast_pull2,
                participant=data["participant"],
                encounter=data["encounter"],
                technique_id=data["technique"].pk,
            )
        self.assertEqual(cm.exception.code, ActionDispatchError.PULL_ALREADY_COMMITTED)
