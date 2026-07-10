"""Tests for the GM scenario catalog models + starter seed (#2127)."""

from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.gm.constants import CatalogSuggestionProposalKind, GMLevel
from world.gm.factories import (
    CatalogSuggestionFactory,
    CheckTypeSituationFitFactory,
    ConsequencePoolGuideFactory,
    SituationDifficultyGuideFactory,
    SituationKindFactory,
    seed_catalog_starter_content,
)
from world.gm.models import (
    CatalogSuggestion,
    CheckTypeSituationFit,
    ConsequencePoolGuide,
    SituationDifficultyGuide,
    SituationKind,
)
from world.player_submissions.constants import SubmissionStatus
from world.scenes.action_constants import DifficultyChoice
from world.societies.constants import RenownRisk


class SituationKindModelTests(TestCase):
    def test_str(self) -> None:
        kind = SituationKindFactory(name="Chase")
        assert str(kind) == "Chase"

    def test_default_minimum_gm_level_is_starting(self) -> None:
        kind = SituationKindFactory()
        assert kind.minimum_gm_level == GMLevel.STARTING

    def test_cached_all_returns_created_rows(self) -> None:
        SituationKind.objects.flush_all_cache()
        SituationKindFactory(name="Cached Kind A")
        SituationKindFactory(name="Cached Kind B")
        names = {k.name for k in SituationKind.objects.cached_all()}
        assert {"Cached Kind A", "Cached Kind B"} <= names


class CheckTypeSituationFitModelTests(TestCase):
    def test_unique_per_check_type_and_kind(self) -> None:
        kind = SituationKindFactory()
        category = CheckCategoryFactory()
        check_type = CheckTypeFactory(category=category)
        CheckTypeSituationFit.objects.create(check_type=check_type, situation_kind=kind)
        with self.assertRaises(IntegrityError):
            CheckTypeSituationFit.objects.create(check_type=check_type, situation_kind=kind)

    def test_str(self) -> None:
        fit = CheckTypeSituationFitFactory(
            situation_kind=SituationKindFactory(name="Chase"),
            check_type=CheckTypeFactory(name="Sprint", category=CheckCategoryFactory()),
        )
        assert str(fit) == "Sprint fits Chase"


class SituationDifficultyGuideModelTests(TestCase):
    def test_unique_per_kind_and_risk(self) -> None:
        kind = SituationKindFactory()
        SituationDifficultyGuide.objects.create(
            situation_kind=kind,
            risk=RenownRisk.MODERATE,
            recommended_difficulty=DifficultyChoice.NORMAL,
        )
        with self.assertRaises(IntegrityError):
            SituationDifficultyGuide.objects.create(
                situation_kind=kind,
                risk=RenownRisk.MODERATE,
                recommended_difficulty=DifficultyChoice.HARD,
            )

    def test_multiple_risks_allowed_per_kind(self) -> None:
        kind = SituationKindFactory()
        SituationDifficultyGuideFactory(situation_kind=kind, risk=RenownRisk.LOW)
        SituationDifficultyGuideFactory(situation_kind=kind, risk=RenownRisk.HIGH)
        assert kind.difficulty_guides.count() == 2


class ConsequencePoolGuideModelTests(TestCase):
    def test_unique_per_kind_and_pool(self) -> None:
        from actions.factories import ConsequencePoolFactory

        kind = SituationKindFactory()
        pool = ConsequencePoolFactory()
        ConsequencePoolGuide.objects.create(situation_kind=kind, pool=pool)
        with self.assertRaises(IntegrityError):
            ConsequencePoolGuide.objects.create(situation_kind=kind, pool=pool)

    def test_advisory_str(self) -> None:
        guide = ConsequencePoolGuideFactory(situation_kind=SituationKindFactory(name="Chase"))
        assert "(advisory)" in str(guide)


class CatalogSuggestionModelTests(TestCase):
    def test_default_status_is_open(self) -> None:
        suggestion = CatalogSuggestionFactory()
        assert suggestion.status == SubmissionStatus.OPEN

    def test_situation_kind_optional(self) -> None:
        suggestion = CatalogSuggestionFactory(situation_kind=None)
        assert suggestion.situation_kind is None

    def test_str(self) -> None:
        suggestion = CatalogSuggestionFactory(proposal_kind=CatalogSuggestionProposalKind.OTHER)
        result = str(suggestion)
        assert "CatalogSuggestion(" in result
        assert suggestion.submitted_by.username in result

    def test_kind_deletion_nulls_suggestion_reference(self) -> None:
        """SET_NULL cascades at the DB level (Collector-issued UPDATE, not per-row .save()).

        Bypasses the idmapper identity map to observe it: ``refresh_from_db()`` on the
        already-cached ``suggestion`` instance would just hand back the same stale
        cached object (SharedMemoryModelBase.__call__ short-circuits construction from
        DB row values to the cached instance for a known pk) -- flush the cache first,
        mirroring the codebase's documented "idmapper cache survives collector SET_NULL"
        gotcha (#707).
        """
        kind = SituationKindFactory()
        suggestion = CatalogSuggestionFactory(situation_kind=kind)
        suggestion_pk = suggestion.pk
        kind.delete()
        CatalogSuggestion.flush_instance_cache(force=True)
        refetched = CatalogSuggestion.objects.get(pk=suggestion_pk)
        assert refetched.situation_kind is None


class SeedCatalogStarterContentTests(TestCase):
    def test_creates_starter_kinds(self) -> None:
        kinds = seed_catalog_starter_content()
        assert set(kinds.keys()) == {"Chase", "Negotiation", "Infiltration"}
        assert SituationKind.objects.count() == 3

    def test_difficulty_guides_cover_every_non_none_risk(self) -> None:
        seed_catalog_starter_content()
        for name in ("Chase", "Negotiation", "Infiltration"):
            kind = SituationKind.objects.get(name=name)
            risks = set(kind.difficulty_guides.values_list("risk", flat=True))
            assert risks == {
                RenownRisk.LOW,
                RenownRisk.MODERATE,
                RenownRisk.HIGH,
                RenownRisk.EXTREME,
            }

    def test_infiltration_gated_above_starting(self) -> None:
        kinds = seed_catalog_starter_content()
        assert kinds["Infiltration"].minimum_gm_level == GMLevel.JUNIOR
        assert kinds["Chase"].minimum_gm_level == GMLevel.STARTING
        assert kinds["Negotiation"].minimum_gm_level == GMLevel.STARTING

    def test_idempotent(self) -> None:
        first = seed_catalog_starter_content()
        first_pks = {name: kind.pk for name, kind in first.items()}
        first_guide_count = SituationDifficultyGuide.objects.count()

        second = seed_catalog_starter_content()

        assert SituationKind.objects.count() == 3
        assert SituationDifficultyGuide.objects.count() == first_guide_count
        for name, kind in second.items():
            assert kind.pk == first_pks[name]
