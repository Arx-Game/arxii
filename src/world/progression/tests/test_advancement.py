"""Model-shape + Durance-service tests for ClassLevelAdvancement (#1352)."""

from unittest import mock

from django.test import TestCase, tag

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import (
    CharacterClassFactory,
    CharacterClassLevelFactory,
    PathFactory,
)
from world.classes.models import PathStage
from world.magic.factories import RitualFactory
from world.progression.exceptions import (
    AdvancementRequirementsNotMet,
    AdvancementUnlockNotPurchasedError,
    OfficiantIneligibleError,
    TierBoundaryRequiresCrossing,
)
from world.progression.models import CharacterUnlock, ClassLevelAdvancement
from world.progression.services.advancement import (
    advance_class_level_via_session,
    apply_class_level_advance,
    assert_can_officiate,
    primary_class_level,
)

# The service imports check_requirements_for_unlock lazily from spends (deferred to
# avoid the progression↔magic import cycle), so patch it at its source module.
_CHECK_PATH = "world.progression.services.spends.check_requirements_for_unlock"


class ClassLevelAdvancementModelTests(TestCase):
    def test_fields_and_str(self):
        fields = {f.name for f in ClassLevelAdvancement._meta.get_fields()}
        assert {
            "character_sheet",
            "character_class",
            "officiant",
            "ritual",
            "scene",
            "declaration_interaction",
            "level_before",
            "level_after",
            "created_at",
        } <= fields

        # __str__ should include the level transition.
        sheet = CharacterSheetFactory()
        char_class = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=sheet.character,
            character_class=char_class,
            level=2,
            is_primary=True,
        )
        instance = ClassLevelAdvancement(
            character_sheet=sheet,
            character_class=char_class,
            level_before=2,
            level_after=3,
        )
        result = str(instance)
        assert "2" in result, f"__str__ should mention level_before (2); got: {result!r}"
        assert "3" in result, f"__str__ should mention level_after (3); got: {result!r}"


class ApplyClassLevelAdvanceTests(TestCase):
    """apply_class_level_advance bumps the primary CharacterClassLevel and invalidates cache."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ccl = CharacterClassLevelFactory(
            character=self.sheet.character,
            level=2,
            is_primary=True,
        )

    def test_bumps_primary_class_level_to_level_after(self) -> None:
        apply_class_level_advance(self.sheet, level_after=3)
        self.ccl.refresh_from_db()
        assert self.ccl.level == 3

    def test_cache_invalidated_so_current_level_reflects_new_level(self) -> None:
        apply_class_level_advance(self.sheet, level_after=3)
        assert self.sheet.current_level == 3

    def test_noop_when_no_class_level_row_exists(self) -> None:
        """apply_class_level_advance silently does nothing when there is no CharacterClassLevel."""
        from world.classes.models import CharacterClassLevel

        sheet = CharacterSheetFactory()
        assert not CharacterClassLevel.objects.filter(character=sheet.character).exists()
        # Must not raise.
        apply_class_level_advance(sheet, level_after=3)

    def test_recompute_max_health_called_on_advance(self) -> None:
        """apply_class_level_advance calls recompute_max_health_with_threads after level write."""
        with mock.patch("world.magic.services.threads.recompute_max_health_with_threads") as spy:
            apply_class_level_advance(self.sheet, level_after=3)
        spy.assert_called_once_with(self.sheet)


class PrimaryClassLevelTests(TestCase):
    """primary_class_level returns the primary row, falls back to highest-level, else None."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def test_returns_primary_row_when_present(self) -> None:
        CharacterClassLevelFactory(character=self.sheet.character, level=10, is_primary=False)
        ccl_primary = CharacterClassLevelFactory(
            character=self.sheet.character, level=1, is_primary=True
        )
        result = primary_class_level(self.sheet.character)
        assert result == ccl_primary

    def test_falls_back_to_highest_level_when_no_primary(self) -> None:
        CharacterClassLevelFactory(character=self.sheet.character, level=3, is_primary=False)
        ccl_high = CharacterClassLevelFactory(
            character=self.sheet.character, level=7, is_primary=False
        )
        result = primary_class_level(self.sheet.character)
        assert result == ccl_high

    def test_returns_none_when_no_rows(self) -> None:
        result = primary_class_level(self.sheet.character)
        assert result is None


# ---------------------------------------------------------------------------
# Durance: shared fixture helpers
# ---------------------------------------------------------------------------


def _wire_path(sheet, path) -> None:
    """Record ``path`` as the character's current path via CharacterPathHistory."""
    from world.progression.models import CharacterPathHistory

    CharacterPathHistory.objects.create(character=sheet, path=path)


def _purchase_unlock(sheet, unlock) -> None:
    """Record the XP-unlock purchase gate as satisfied for ``sheet`` (#2116)."""
    CharacterUnlock.objects.create(
        character=sheet,
        character_class=unlock.character_class,
        target_level=unlock.target_level,
    )


def _build_durance_session(  # noqa: PLR0913
    *,
    officiant_level: int,
    inductee_level: int,
    character_class=None,
    officiant_path=None,
    inductee_path=None,
    testament: str = "",
):
    """Build a Durance RitualSession: initiator = officiant, one ACCEPTED inductee.

    Returns (session, officiant_sheet, inductee_sheet, character_class).
    """
    from world.magic.constants import ParticipantState
    from world.magic.factories import (
        RitualSessionFactory,
        RitualSessionParticipantFactory,
    )

    character_class = character_class or CharacterClassFactory()
    officiant = CharacterSheetFactory()
    inductee = CharacterSheetFactory()
    CharacterClassLevelFactory(
        character=officiant.character,
        character_class=CharacterClassFactory(),
        level=officiant_level,
        is_primary=True,
    )
    CharacterClassLevelFactory(
        character=inductee.character,
        character_class=character_class,
        level=inductee_level,
        is_primary=True,
    )
    # Same-path lineage by default: both on the same path.
    shared_path = PathFactory(stage=PathStage.PROSPECT)
    _wire_path(officiant, officiant_path or shared_path)
    _wire_path(inductee, inductee_path or shared_path)

    ritual = RitualFactory(
        service_function_path=(
            "world.progression.services.advancement.advance_class_level_via_session"
        )
    )
    session = RitualSessionFactory(ritual=ritual, initiator=officiant)
    RitualSessionParticipantFactory(
        session=session,
        character_sheet=officiant,
        state=ParticipantState.ACCEPTED,
    )
    RitualSessionParticipantFactory(
        session=session,
        character_sheet=inductee,
        state=ParticipantState.ACCEPTED,
        participant_kwargs={"testament": testament} if testament else {},
    )
    return session, officiant, inductee, character_class


# ---------------------------------------------------------------------------
# Durance: assert_can_officiate
# ---------------------------------------------------------------------------


class AssertCanOfficiateTests(TestCase):
    """Level gate + same-Path lineage gate."""

    def setUp(self) -> None:
        self.path = PathFactory(stage=PathStage.PROSPECT)
        self.officiant = CharacterSheetFactory()
        self.inductee = CharacterSheetFactory()
        CharacterClassLevelFactory(character=self.officiant.character, level=10, is_primary=True)
        CharacterClassLevelFactory(character=self.inductee.character, level=2, is_primary=True)
        _wire_path(self.officiant, self.path)
        _wire_path(self.inductee, self.path)

    def test_passes_when_level_and_same_path(self) -> None:
        # Must not raise.
        assert_can_officiate(
            officiant_sheet=self.officiant,
            inductee_sheet=self.inductee,
            target_level=3,
        )

    def test_raises_when_officiant_level_not_above_target(self) -> None:
        low = CharacterSheetFactory()
        CharacterClassLevelFactory(character=low.character, level=3, is_primary=True)
        _wire_path(low, self.path)
        with self.assertRaises(OfficiantIneligibleError):
            assert_can_officiate(
                officiant_sheet=low,
                inductee_sheet=self.inductee,
                target_level=3,
            )

    def test_raises_when_unrelated_path(self) -> None:
        other = CharacterSheetFactory()
        CharacterClassLevelFactory(character=other.character, level=10, is_primary=True)
        _wire_path(other, PathFactory(stage=PathStage.PROSPECT))
        with self.assertRaises(OfficiantIneligibleError):
            assert_can_officiate(
                officiant_sheet=other,
                inductee_sheet=self.inductee,
                target_level=3,
            )

    def test_passes_when_officiant_on_more_advanced_path(self) -> None:
        # Inductee on a Prospect path; officiant on a Puissant path that evolved from it.
        advanced = PathFactory(stage=PathStage.PUISSANT)
        advanced.parent_paths.add(self.path)
        senior = CharacterSheetFactory()
        CharacterClassLevelFactory(character=senior.character, level=10, is_primary=True)
        _wire_path(senior, advanced)
        # Must not raise.
        assert_can_officiate(
            officiant_sheet=senior,
            inductee_sheet=self.inductee,
            target_level=3,
        )


# ---------------------------------------------------------------------------
# Durance: advance_class_level_via_session (fast tier — requirements patched)
# ---------------------------------------------------------------------------


class AdvanceViaSessionTests(TestCase):
    """Service branching, with check_requirements_for_unlock patched (no PG view)."""

    def setUp(self) -> None:
        from world.progression.models import ClassLevelUnlock

        self.session, self.officiant, self.inductee, self.character_class = _build_durance_session(
            officiant_level=10, inductee_level=2
        )
        # Authored unlock for the next level so resolution succeeds.
        self.unlock = ClassLevelUnlock.objects.create(
            character_class=self.character_class, target_level=3
        )
        _purchase_unlock(self.inductee, self.unlock)

    def test_happy_path_bumps_level_and_writes_receipt(self) -> None:
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            receipts = advance_class_level_via_session(session=self.session)
        assert len(receipts) == 1
        receipt = receipts[0]
        assert receipt.level_before == 2
        assert receipt.level_after == 3
        assert receipt.officiant == self.officiant
        assert receipt.character_class == self.character_class
        assert receipt.ritual == self.session.ritual
        self.inductee.invalidate_class_level_cache()
        assert self.inductee.current_level == 3

    def test_happy_path_posts_testament_when_scene_active(self) -> None:
        from world.scenes.factories import SceneFactory
        from world.scenes.models import Interaction

        # Rebuild with the testament set at participant-creation time (a JSONField
        # .update() would leave the SharedMemoryModel-cached row's kwargs stale).
        session, _officiant, inductee, character_class = _build_durance_session(
            officiant_level=10, inductee_level=2, testament="I have earned this."
        )
        from world.progression.models import ClassLevelUnlock

        unlock = ClassLevelUnlock.objects.create(character_class=character_class, target_level=3)
        _purchase_unlock(inductee, unlock)
        SceneFactory(location=inductee.character.location, is_active=True)
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            advance_class_level_via_session(session=session)
        posed = Interaction.objects.filter(content__startswith="I have earned this.")
        assert posed.exists()

    def test_requirements_not_met_raises_and_does_not_bump(self) -> None:
        with mock.patch(_CHECK_PATH, return_value=(False, ["Legend too low"])):
            with self.assertRaises(AdvancementRequirementsNotMet):
                advance_class_level_via_session(session=self.session)
        assert not ClassLevelAdvancement.objects.filter(character_sheet=self.inductee).exists()
        self.inductee.invalidate_class_level_cache()
        assert self.inductee.current_level == 2

    def test_missing_unlock_raises_requirements_not_met(self) -> None:
        self.unlock.delete()
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            with self.assertRaises(AdvancementRequirementsNotMet):
                advance_class_level_via_session(session=self.session)

    def test_inductee_with_no_class_level_raises_requirements_not_met(self) -> None:
        """An inductee with no CharacterClassLevel row raises AdvancementRequirementsNotMet."""
        from world.classes.models import CharacterClassLevel

        # Build a session where the inductee has no CharacterClassLevel row.
        no_cl_session, _officiant, inductee_no_cl, _character_class_new = _build_durance_session(
            officiant_level=10, inductee_level=2
        )
        # Delete the CharacterClassLevel that _build_durance_session created for the inductee.
        CharacterClassLevel.objects.filter(character=inductee_no_cl.character).delete()
        CharacterClassLevel.flush_instance_cache()
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            with self.assertRaises(AdvancementRequirementsNotMet):
                advance_class_level_via_session(session=no_cl_session)

    def test_officiant_too_low_raises(self) -> None:
        # Officiant at level 3, inductee reaching target_level 3 → gate (current_level
        # > target_level) fails. Built fresh so the level is correct at row-create time.
        from world.progression.models import ClassLevelUnlock

        session, _officiant, _inductee, character_class = _build_durance_session(
            officiant_level=3, inductee_level=2
        )
        ClassLevelUnlock.objects.create(character_class=character_class, target_level=3)
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            with self.assertRaises(OfficiantIneligibleError):
                advance_class_level_via_session(session=session)


class AdvanceViaSessionUnlockNotPurchasedTests(TestCase):
    """The XP-unlock purchase gate (#2116) — requirements met is not sufficient.

    Both gates (check_requirements_for_unlock + the CharacterUnlock purchase)
    must independently pass; "XP unlocks, never grants" — see the ADR.
    """

    def setUp(self) -> None:
        from world.progression.models import ClassLevelUnlock

        self.session, self.officiant, self.inductee, self.character_class = _build_durance_session(
            officiant_level=10, inductee_level=2
        )
        self.unlock = ClassLevelUnlock.objects.create(
            character_class=self.character_class, target_level=3
        )
        # Deliberately NOT purchased — no CharacterUnlock row created.

    def test_requirements_met_but_unpurchased_raises_specific_error(self) -> None:
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            with self.assertRaises(AdvancementUnlockNotPurchasedError) as ctx:
                advance_class_level_via_session(session=self.session)
        # Names the unlock's class + XP cost — fail loud, never silent.
        assert self.character_class.name in ctx.exception.user_message
        # No level bump on this failed gate.
        self.inductee.invalidate_class_level_cache()
        assert self.inductee.current_level == 2
        assert not ClassLevelAdvancement.objects.filter(character_sheet=self.inductee).exists()

    def test_purchase_then_advance_succeeds(self) -> None:
        _purchase_unlock(self.inductee, self.unlock)
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            receipts = advance_class_level_via_session(session=self.session)
        assert len(receipts) == 1
        self.inductee.invalidate_class_level_cache()
        assert self.inductee.current_level == 3

    def test_unpurchased_error_does_not_fire_when_requirements_unmet(self) -> None:
        """Requirements gate fails first — the specific unlock error only fires once
        requirements are already satisfied (gates are stacked, not short-circuited
        past each other in the wrong order)."""
        with mock.patch(_CHECK_PATH, return_value=(False, ["Requires 50 Legend"])):
            with self.assertRaises(AdvancementRequirementsNotMet):
                advance_class_level_via_session(session=self.session)


class AdvanceViaSessionBoundaryTests(TestCase):
    """Tier-boundary refusal: a threshold at level_before routes to Audere Majora."""

    def setUp(self) -> None:
        from world.progression.models import ClassLevelUnlock

        self.session, self.officiant, self.inductee, self.character_class = _build_durance_session(
            officiant_level=10, inductee_level=5
        )
        ClassLevelUnlock.objects.create(character_class=self.character_class, target_level=6)

    def test_boundary_step_raises_tier_boundary(self) -> None:
        from world.conditions.factories import ConditionStageFactory
        from world.magic.audere_majora import AudereMajoraThreshold
        from world.magic.factories import IntensityTierFactory

        AudereMajoraThreshold.objects.create(
            boundary_level=5,
            target_stage=PathStage.PUISSANT,
            minimum_intensity_tier=IntensityTierFactory(),
            minimum_warp_stage=ConditionStageFactory(),
            requires_active_audere=False,
            vision_text="[PLACEHOLDER]",
            manifestation_text="[PLACEHOLDER]",
        )
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            with self.assertRaises(TierBoundaryRequiresCrossing):
                advance_class_level_via_session(session=self.session)


class AdvanceViaSessionMultiInducteeTests(TestCase):
    """Two inductees → one scene → two receipts."""

    def setUp(self) -> None:
        from world.magic.constants import ParticipantState
        from world.magic.factories import (
            RitualSessionFactory,
            RitualSessionParticipantFactory,
        )
        from world.progression.models import ClassLevelUnlock

        self.character_class = CharacterClassFactory()
        self.path = PathFactory(stage=PathStage.PROSPECT)
        self.officiant = CharacterSheetFactory()
        CharacterClassLevelFactory(character=self.officiant.character, level=10, is_primary=True)
        _wire_path(self.officiant, self.path)

        self.inductees = []
        ritual = RitualFactory(
            service_function_path=(
                "world.progression.services.advancement.advance_class_level_via_session"
            )
        )
        self.session = RitualSessionFactory(ritual=ritual, initiator=self.officiant)
        RitualSessionParticipantFactory(
            session=self.session,
            character_sheet=self.officiant,
            state=ParticipantState.ACCEPTED,
        )
        for _ in range(2):
            inductee = CharacterSheetFactory()
            CharacterClassLevelFactory(
                character=inductee.character,
                character_class=self.character_class,
                level=2,
                is_primary=True,
            )
            _wire_path(inductee, self.path)
            RitualSessionParticipantFactory(
                session=self.session,
                character_sheet=inductee,
                state=ParticipantState.ACCEPTED,
            )
            self.inductees.append(inductee)
        unlock = ClassLevelUnlock.objects.create(
            character_class=self.character_class, target_level=3
        )
        for inductee in self.inductees:
            _purchase_unlock(inductee, unlock)

    def test_two_inductees_two_receipts_same_scene(self) -> None:
        from world.scenes.factories import SceneFactory

        SceneFactory(location=self.officiant.character.location, is_active=True)
        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            receipts = advance_class_level_via_session(session=self.session)
        assert len(receipts) == 2
        sheets = {r.character_sheet_id for r in receipts}
        assert sheets == {self.inductees[0].pk, self.inductees[1].pk}


# ---------------------------------------------------------------------------
# Durance: PG integration — real LegendRequirement + materialized view
# ---------------------------------------------------------------------------


@tag("postgres")
class AdvanceViaSessionLegendGatePGTests(TestCase):
    """Prove the Durance requirements gate passes/fails through the real legend view.

    Each scenario runs end-to-end through ``advance_class_level_via_session`` with a
    real ``LegendRequirement`` resolved against the ``societies_characterlegendsummary``
    materialized view (no patching). Split into two classes-worth of self-contained
    methods that each build their own world so the matview state for one inductee never
    bleeds into another.
    """

    def _build(self, *, legend_value: int):
        from world.progression.models import ClassLevelUnlock, LegendRequirement
        from world.societies.factories import LegendEntryFactory
        from world.societies.models import refresh_legend_views

        session, _officiant, inductee, character_class = _build_durance_session(
            officiant_level=10, inductee_level=2
        )
        unlock = ClassLevelUnlock.objects.create(character_class=character_class, target_level=3)
        _purchase_unlock(inductee, unlock)
        LegendRequirement.objects.create(
            class_level_unlock=unlock, minimum_legend=50, is_active=True
        )
        LegendEntryFactory(
            persona=inductee.primary_persona, base_value=legend_value, is_active=True
        )
        refresh_legend_views()
        return session, inductee

    def test_gate_fails_below_threshold(self) -> None:
        session, _inductee = self._build(legend_value=10)
        with self.assertRaises(AdvancementRequirementsNotMet):
            advance_class_level_via_session(session=session)

    def test_gate_passes_at_threshold(self) -> None:
        session, _inductee = self._build(legend_value=75)
        receipts = advance_class_level_via_session(session=session)
        assert len(receipts) == 1
        assert receipts[0].level_after == 3


class LegendRequirementWiredIntoUnlockCheckTests(TestCase):
    """`check_requirements_for_unlock` must actually enforce `LegendRequirement`.

    Regression guard: `LegendRequirement` was omitted from the requirement_types list in
    `check_requirements_for_unlock`, so the legend gate was silently bypassed (only the
    PG matview integration test caught it). This runs on the SQLite fast tier by mocking
    the PG-only legend total, so the wiring can't regress without PG.
    """

    def _make_unlock_with_legend_req(self):
        from world.progression.models import ClassLevelUnlock, LegendRequirement

        cc = CharacterClassFactory()
        unlock = ClassLevelUnlock.objects.create(character_class=cc, target_level=3)
        LegendRequirement.objects.create(
            class_level_unlock=unlock, minimum_legend=50, is_active=True
        )
        return unlock

    def test_legend_requirement_blocks_when_total_below_minimum(self) -> None:
        from world.progression.services.spends import check_requirements_for_unlock

        sheet = CharacterSheetFactory()
        unlock = self._make_unlock_with_legend_req()
        with mock.patch("world.societies.services.get_character_legend_total", return_value=10):
            met, failed = check_requirements_for_unlock(sheet.character, unlock)
        assert met is False
        assert failed

    def test_legend_requirement_passes_when_total_meets_minimum(self) -> None:
        from world.progression.services.spends import check_requirements_for_unlock

        sheet = CharacterSheetFactory()
        unlock = self._make_unlock_with_legend_req()
        with mock.patch("world.societies.services.get_character_legend_total", return_value=75):
            met, failed = check_requirements_for_unlock(sheet.character, unlock)
        assert met is True
        assert failed == []


# ---------------------------------------------------------------------------
# Durance: level-3 POTENTIAL semi-crossing (#1579) — switch path + grant, no Audere Majora
# ---------------------------------------------------------------------------


class DuranceSemiCrossingTests(TestCase):
    """Advancing 2→3 (PROSPECT→POTENTIAL) in the Durance switches to the chosen
    Potential path and grants its gift+techniques — the same machinery as a crossing,
    but with no Audere Majora involved."""

    def setUp(self) -> None:
        from world.classes.models import PathStage
        from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory
        from world.magic.models import PathGiftGrant
        from world.progression.models import ClassLevelUnlock, PathIntent
        from world.progression.selectors import current_path_for_character

        self.session, self.officiant, self.inductee, self.character_class = _build_durance_session(
            officiant_level=10, inductee_level=2
        )
        unlock = ClassLevelUnlock.objects.create(
            character_class=self.character_class, target_level=3
        )
        _purchase_unlock(self.inductee, unlock)

        prospect = current_path_for_character(self.inductee.character)
        self.potential = PathFactory(stage=PathStage.POTENTIAL)
        self.potential.parent_paths.add(prospect)

        self.gift = GiftFactory(name="Pyromancy_durance")
        self.gift.resonances.add(ResonanceFactory(name="Ember_durance"))
        self.tech = TechniqueFactory(name="Flame Lash_durance", gift=self.gift)
        grant = PathGiftGrant.objects.create(path=self.potential, gift=self.gift)
        grant.starter_techniques.add(self.tech)

        # Declare intent to take the Potential path at the rite.
        PathIntent.objects.create(character_sheet=self.inductee, intended_path=self.potential)

    def test_semi_crossing_switches_path_and_grants(self) -> None:
        from world.magic.models import CharacterGift, CharacterTechnique
        from world.progression.selectors import current_path_for_character

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            advance_class_level_via_session(session=self.session)

        self.inductee.invalidate_class_level_cache()
        assert self.inductee.current_level == 3
        assert current_path_for_character(self.inductee.character).pk == self.potential.pk
        assert CharacterGift.objects.filter(character=self.inductee, gift=self.gift).exists()
        assert CharacterTechnique.objects.filter(
            character=self.inductee, technique=self.tech
        ).exists()

    def test_no_declared_path_advances_level_without_switch(self) -> None:
        from world.magic.models import CharacterGift
        from world.progression.models import PathIntent
        from world.progression.selectors import current_path_for_character

        PathIntent.objects.filter(character_sheet=self.inductee).delete()
        prospect_pk = current_path_for_character(self.inductee.character).pk

        with mock.patch(_CHECK_PATH, return_value=(True, [])):
            advance_class_level_via_session(session=self.session)

        self.inductee.invalidate_class_level_cache()
        assert self.inductee.current_level == 3
        # No declared Potential path → stays on the prospect path, grants nothing.
        assert current_path_for_character(self.inductee.character).pk == prospect_pk
        assert not CharacterGift.objects.filter(character=self.inductee).exists()
