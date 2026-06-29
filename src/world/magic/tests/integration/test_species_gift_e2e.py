"""E2E: species abilities as Minor Gifts (#1580) — the north-star journey.

Drives the WHOLE feature through the real pipeline:

    seed granting species + SpeciesGiftGrant
      -> CG finalize (finalize_magic_data) provisions the MINOR CharacterGift,
         the latent level-0 GIFT thread at the CG-chosen resonance, and the
         species drawback condition
      -> raise the species thread past the resistance threshold via the REAL
         imbue path (spend_resonance_for_imbuing); the drawback vulnerability and
         the gift's passive RESISTANCE pull-effect net on the combat damage seam
      -> commit a paid RESISTANCE pull (CombatPullResolvedEffect snapshot scales
         with thread level)
      -> the same imbue crosses a #1578 TechniqueVariant unlock threshold, so the
         resonance variant resolves AND the discovery beat fires
      -> non-regression: the Major-gift latent thread and covenant sub-role
         resolution still pass.

SQLite vs Postgres split (project policy: verify SQLite locally, let CI gate PG):

- ``SpeciesGiftSpineSQLiteTest`` (no ``@tag``) covers the drawback-free spine —
  finalize gift + latent thread, real imbue, variant resolution + discovery, and
  the non-regression beats. It runs on the fast SQLite tier and is the real local
  signal for the spine. Its grant uses ``drawback_condition=None`` so it never hits
  ``apply_condition`` (PG-only ``DISTINCT ON`` via ``_build_bulk_context``).

- ``SpeciesGiftFullJourneyPostgresTest`` (``@tag("postgres")``) adds the drawback
  beats: ``apply_condition`` (the species drawback) and the combat damage-netting
  seam (``apply_damage_to_participant``) are PG-only. CI's Postgres shard gates it.
  On the SQLite tier it is *collected but skipped* — it imports cleanly so the file
  loads.

The high-thread-level pull-scaling beat sets ``Thread.level`` directly rather than
imbuing there: levels above 10 are XP-locked and cost 100+ developed-points each
(``cost = max((level - 9) * 100, 1)``), so the documented #1578 ceremony-direct
pattern is the only practical way to exercise a multiplier > 1. The sub-10 raise
that crosses the variant/resistance thresholds DOES go through the real imbue path.
"""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import patch

from django.test import TestCase, tag

from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.services import finalize_magic_data
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.magic.constants import EffectKind, GiftKind, TargetKind
from world.magic.factories import (
    CantripFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import Resonance, Technique, Thread
from world.magic.models.gifts import CharacterGift
from world.magic.services import spend_resonance_for_imbuing, spend_resonance_for_pull
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import resolve_specialized_variant
from world.magic.types import PullActionContext
from world.roster.factories import RosterEntryFactory
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory


class _FakeStack:
    def was_cancelled(self) -> bool:
        return False


def _non_cancelling(event_name: str, payload: object, **kwargs: object) -> _FakeStack:
    return _FakeStack()


# Levels chosen so the cheap (sub-10) imbue path can reach them:
#   variant unlocks at 3, passive resistance switches on at 5.
_VARIANT_UNLOCK_LEVEL = 3
_RESISTANCE_THRESHOLD = 5


class _SpeciesGiftJourneyBase(TestCase):
    """Shared seeding for the species-gift journey (the parts both tiers share)."""

    resonance: ClassVar[Resonance]
    species: ClassVar
    minor_gift: ClassVar
    technique: ClassVar[Technique]
    variant: ClassVar[TechniqueVariant]
    cantrip: ClassVar

    @classmethod
    def _seed_common(cls, *, drawback_condition=None) -> None:
        from world.achievements.factories import AchievementFactory
        from world.codex.factories import CodexEntryFactory

        cls.resonance = ResonanceFactory()
        # The species' Minor Gift + its starting technique.
        cls.minor_gift = GiftFactory(name="Test Nightform", kind=GiftKind.MINOR)
        cls.minor_gift.resonances.add(cls.resonance)
        cls.technique = TechniqueFactory(gift=cls.minor_gift, name="Nightform Base")
        # A resonance-specialized variant unlocking at level 3 (#1578).
        cls.achievement = AchievementFactory()
        cls.codex_entry = CodexEntryFactory()
        cls.variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.resonance,
            unlock_thread_level=_VARIANT_UNLOCK_LEVEL,
            name_override="Nightform Ascendant",
            intensity_delta=5,
            control_delta=2,
            discovery_achievement=cls.achievement,
            codex_entry=cls.codex_entry,
        )
        # The granting species (drawback supplied only by the PG journey).
        cls.species = SpeciesFactory(name="TestNightkin")
        SpeciesGiftGrantFactory(
            species=cls.species,
            gift=cls.minor_gift,
            drawback_condition=drawback_condition,
        )
        # A cantrip so finalize_magic_data also mints the Major gift + its latent
        # thread (beat 6 non-regression).
        cls.cantrip = CantripFactory()

    def _finalize_character(self) -> CharacterSheet:
        """Build + CG-finalize a character of the granting species (real pipeline)."""
        sheet = CharacterSheetFactory(species=self.species)
        # Codex unlock is keyed on RosterEntry; ensure one so the discovery beat
        # (achievement + codex) can be asserted end-to-end.
        RosterEntryFactory(character_sheet=sheet)
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.cantrip.id,
                "selected_gift_resonance_id": self.resonance.id,
            },
        )
        finalize_magic_data(draft, sheet)
        return sheet

    def _species_thread(self, sheet: CharacterSheet) -> Thread:
        return Thread.objects.get(
            owner=sheet,
            target_kind=TargetKind.GIFT,
            target_gift=self.minor_gift,
        )

    def _assert_finalize_provisioned_gift(self, sheet: CharacterSheet) -> Thread:
        """Beat 2 spine: MINOR CharacterGift + active level-0 GIFT thread at resonance."""
        cg = CharacterGift.objects.filter(character=sheet, gift=self.minor_gift).first()
        self.assertIsNotNone(cg, "finalize should mint the species MINOR CharacterGift")
        self.assertEqual(self.minor_gift.kind, GiftKind.MINOR)
        thread = self._species_thread(sheet)
        self.assertEqual(thread.level, 0, "species GIFT thread starts latent at level 0")
        self.assertEqual(thread.resonance, self.resonance, "anchored to the CG-chosen resonance")
        self.assertIsNone(thread.retired_at, "the latent thread is active")
        return thread

    def _imbue_to(self, sheet: CharacterSheet, thread: Thread, target_level: int) -> None:
        """Raise the species thread to ``target_level`` via the REAL imbue path."""
        CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=self.resonance,
            balance=target_level,
            lifetime_earned=target_level,
        )
        result = spend_resonance_for_imbuing(sheet, thread, amount=target_level)
        self.assertEqual(result.new_level, target_level, "imbue should reach the target level")
        sheet.character.threads.invalidate()

    def _assert_variant_and_discovery(self, sheet: CharacterSheet) -> None:
        """Beat 5: the resonance variant resolves and the discovery beat fired."""
        from world.achievements.models import CharacterAchievement

        resolved = resolve_specialized_variant(entity=self.technique, character=sheet.character)
        self.assertEqual(resolved.name, "Nightform Ascendant", "variant resolves derive-on-read")
        self.assertEqual(resolved.intensity, self.technique.intensity + 5)
        self.assertEqual(resolved.control, self.technique.control + 2)

        self.assertTrue(
            CharacterAchievement.objects.filter(
                character_sheet=sheet, achievement=self.achievement
            ).exists(),
            "the discovery beat should grant the variant's achievement",
        )
        if sheet.roster_entry:
            from world.codex.constants import CodexKnowledgeStatus
            from world.codex.models import CharacterCodexKnowledge

            self.assertTrue(
                CharacterCodexKnowledge.objects.filter(
                    roster_entry=sheet.roster_entry,
                    entry=self.codex_entry,
                    status=CodexKnowledgeStatus.KNOWN,
                ).exists(),
                "the discovery beat should unlock the variant's codex entry",
            )

    def _assert_non_regression(self, sheet: CharacterSheet) -> None:
        """Beat 6: the Major-gift latent thread + covenant sub-role resolution still pass."""
        # (a) The cantrip's Major gift still got its own latent GIFT thread, distinct
        #     from the species MINOR gift thread (species provisioning did not clobber it).
        gift_threads = Thread.objects.filter(owner=sheet, target_kind=TargetKind.GIFT)
        major_threads = gift_threads.exclude(target_gift=self.minor_gift)
        self.assertTrue(
            major_threads.exists(), "the Major-gift latent thread must still be provisioned"
        )
        self.assertGreaterEqual(
            gift_threads.count(), 2, "Major-gift and species-gift threads coexist"
        )

        # (b) Covenant sub-role resolution still resolves through the shared engine.
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
            SubroleCovenantRoleFactory,
        )
        from world.covenants.services import resolve_effective_role
        from world.magic.factories import ThreadFactory

        cov_res = ResonanceFactory()
        parent_role = CovenantRoleFactory()
        sub_role = SubroleCovenantRoleFactory(
            parent_role=parent_role, resonance=cov_res, unlock_thread_level=3
        )
        membership = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=parent_role.covenant_type),
            covenant_role=parent_role,
        )
        character = membership.character_sheet.character
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=cov_res,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=parent_role,
            target_trait=None,
            level=3,
        )
        character.threads.invalidate()
        self.assertEqual(
            resolve_effective_role(character=character, role=parent_role),
            sub_role,
            "covenant sub-role resolution still promotes at the unlock threshold",
        )


class SpeciesGiftSpineSQLiteTest(_SpeciesGiftJourneyBase):
    """SQLite-safe spine: finalize gift + latent thread, real imbue, variant + discovery.

    No drawback (so no ``apply_condition``) and no combat damage netting — both are
    PG-only and live in the ``@tag("postgres")`` journey below. This is the real
    fast-tier signal for the feature spine.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls._seed_common(drawback_condition=None)

    def test_spine_journey(self) -> None:
        # Beat 2: CG finalize provisions the MINOR gift + latent GIFT thread.
        sheet = self._finalize_character()
        thread = self._assert_finalize_provisioned_gift(sheet)
        # No drawback condition was authored for the spine grant.
        from world.conditions.models import ConditionInstance

        self.assertFalse(
            ConditionInstance.objects.filter(target=sheet.character).exists(),
            "the drawback-free spine applies no condition",
        )

        # Before raising: the resolver returns the base technique (no variant yet).
        base = resolve_specialized_variant(entity=self.technique, character=sheet.character)
        self.assertEqual(base.name, self.technique.name, "level-0 thread resolves to base form")

        # Beats 3/5 (spine): raise the thread past the variant unlock via the REAL
        # imbue path; crossing the threshold fires the discovery beat internally.
        self._imbue_to(sheet, thread, _RESISTANCE_THRESHOLD)
        self._assert_variant_and_discovery(sheet)

        # Beat 6: non-regression.
        self._assert_non_regression(sheet)


@tag("postgres")
class SpeciesGiftFullJourneyPostgresTest(_SpeciesGiftJourneyBase):
    """Full journey incl. the drawback + combat damage netting (PG-only).

    ``apply_condition`` (drawback) and ``apply_damage_to_participant`` (the netting
    seam) use PG-only ``DISTINCT ON``. CI's Postgres shard gates this; on SQLite it
    is collected but skipped.
    """

    fire: ClassVar
    drawback: ClassVar

    @classmethod
    def setUpTestData(cls) -> None:
        from world.conditions.factories import (
            ConditionResistanceModifierFactory,
            ConditionTemplateFactory,
            DamageTypeFactory,
        )

        cls.fire = DamageTypeFactory(name="Fire")
        # Species drawback: a -3 fire vulnerability (negative ConditionResistanceModifier).
        cls.drawback = ConditionTemplateFactory(name="Sun-Cursed")
        ConditionResistanceModifierFactory(
            condition=cls.drawback, stage=None, damage_type=cls.fire, modifier_value=-3
        )
        cls._seed_common(drawback_condition=cls.drawback)

        # Passive tier-0 gift RESISTANCE: +3 fire, switching on at the threshold level.
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            target_gift=cls.minor_gift,
            resonance=cls.resonance,
            tier=0,
            min_thread_level=_RESISTANCE_THRESHOLD,
            effect_kind=EffectKind.RESISTANCE,
            flat_bonus_amount=None,
            resistance_amount=3,
            resistance_damage_type=cls.fire,
        )
        # Paid tier-1 gift RESISTANCE: 4 × level_multiplier fire (the pull beat).
        ThreadPullEffectFactory(
            target_kind=TargetKind.GIFT,
            target_gift=cls.minor_gift,
            resonance=cls.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.RESISTANCE,
            flat_bonus_amount=None,
            resistance_amount=4,
            resistance_damage_type=cls.fire,
        )
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)

    def _make_participant(self, sheet: CharacterSheet):
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory

        encounter = CombatEncounterFactory(round_number=1)
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        character = sheet.character
        character.location = encounter.room
        character.save()
        return encounter, participant

    def _hit(self, vitals, participant, amount: int) -> int:
        from world.combat.services import apply_damage_to_participant

        vitals.health = 100
        vitals.save(update_fields=["health"])
        with patch("world.combat.services.emit_event", side_effect=_non_cancelling):
            apply_damage_to_participant(participant, amount, damage_type=self.fire)
        vitals.refresh_from_db()
        return vitals.health

    def test_full_journey(self) -> None:
        from world.conditions.models import ConditionInstance
        from world.vitals.models import CharacterVitals

        # Beat 2: finalize provisions the MINOR gift, the latent GIFT thread, AND
        # applies the species drawback condition.
        sheet = self._finalize_character()
        thread = self._assert_finalize_provisioned_gift(sheet)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=sheet.character, condition=self.drawback, resolved_at__isnull=True
            ).exists(),
            "finalize should apply the species drawback condition",
        )

        _encounter, participant = self._make_participant(sheet)
        vitals = CharacterVitals.objects.create(
            character_sheet=sheet, health=100, max_health=100, base_max_health=100
        )

        # The exact 87/90 below assume a 0 thread-survivability DR baseline (this dev
        # seed never calls seed_thread_survivability_tuning) and no worn armor — so the
        # only modifier on the 10 raw damage is the drawback vuln (and later the gift
        # resistance). If either of those baselines is seeded, these numbers shift.
        # Beat 3a: below the resistance threshold only the -3 vuln applies → 10 → 13.
        self.assertEqual(
            self._hit(vitals, participant, 10),
            87,
            "below threshold the drawback vulnerability is felt in full",
        )

        # Beats 3b/5: raise the thread past the resistance threshold via the REAL
        # imbue path (this crossing also fires the variant discovery at level 3).
        self._imbue_to(sheet, thread, _RESISTANCE_THRESHOLD)
        self._assert_variant_and_discovery(sheet)

        # Beat 3c: at/above threshold the +3 gift resistance nets the -3 vuln → 10 → 10.
        self.assertEqual(
            self._hit(vitals, participant, 10),
            90,
            "gift resistance nets the drawback vulnerability at the threshold",
        )

        # Beat 4: paid RESISTANCE pull snapshots scale with thread level. Levels > 10
        # are XP-locked + expensive, so set level directly (documented #1578 pattern).
        # Anima (10/10) is already seeded by finalize; top up the resonance bucket the
        # imbue drained. Use an INSTANCE save, not a queryset .update(): CharacterResonance
        # is a SharedMemoryModel (idmapper), and a bulk .update() writes the DB row but
        # leaves the cached instance that spend_resonance_for_pull reads stale at its
        # post-imbue balance of 0 (the #1111 stale-idmapper lesson) → ResonanceInsufficient.
        from world.magic.models import CharacterResonance

        cr, _ = CharacterResonance.objects.get_or_create(
            character_sheet=sheet, resonance=self.resonance
        )
        cr.balance = 20
        cr.lifetime_earned = 20
        cr.save(update_fields=["balance", "lifetime_earned"])
        low = self._commit_pull_at_level(sheet, thread, 10)
        high = self._commit_pull_at_level(sheet, thread, 30)
        # active_pull_resistance sums BOTH RESISTANCE snapshots a tier-1 pull writes:
        # resolve_pull_effects iterates effect tiers 0..tier, so the always-on tier-0
        # passive (amount 3, min_thread_level=5) AND the paid tier-1 row (amount 4) are
        # each snapshotted and scaled by level_multiplier = max(1, level // 10). The
        # returned value is therefore (passive + paid) × multiplier, NOT the paid row
        # alone — that is why it is 7, not 4:
        #   level 10 → mult 1 → (3 + 4) × 1 = 7
        #   level 30 → mult 3 → (3 + 4) × 3 = 21
        self.assertEqual(low, 7)
        self.assertEqual(high, 21)
        self.assertGreater(high, low, "the pull is stronger at a higher thread level")

        # Beat 6: non-regression.
        self._assert_non_regression(sheet)

    def _commit_pull_at_level(self, sheet, thread, level: int) -> int:
        from world.combat.models import CombatPull, CombatPullResolvedEffect

        CombatPull.objects.filter(participant__character_sheet=sheet).delete()
        sheet.character.combat_pulls.invalidate()
        thread.level = level
        thread.save(update_fields=["level"])
        sheet.character.threads.invalidate()
        encounter, participant = self._make_participant(sheet)
        ctx = PullActionContext(combat_encounter=encounter, participant=participant)
        spend_resonance_for_pull(
            sheet, self.resonance, tier=1, threads=[thread], action_context=ctx
        )
        # A tier-1 pull snapshots a RESISTANCE row for EVERY effect tier 0..tier, so
        # both the tier-0 passive and the tier-1 paid row land in CombatPullResolvedEffect;
        # disambiguate by source_tier to assert against the paid row specifically (an
        # unqualified .get(kind=RESISTANCE) would raise MultipleObjectsReturned).
        snap = CombatPullResolvedEffect.objects.get(
            pull__participant=participant, kind=EffectKind.RESISTANCE, source_tier=1
        )
        self.assertEqual(snap.authored_value, 4)
        self.assertEqual(snap.source_thread_id, thread.pk)
        sheet.character.combat_pulls.invalidate()
        return sheet.character.combat_pulls.active_pull_resistance(self.fire)
