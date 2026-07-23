"""Tests for cross_threshold, resolve_audere_majora_offer, and end_audere_majora (#543)."""

import contextlib

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.classes.factories import PathFactory
from world.classes.models import CharacterClassLevel, PathStage
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.models import ConditionInstance
from world.magic.audere import AUDERE_MAJORA_CONDITION_NAME
from world.magic.audere_majora import (
    AudereMajoraCrossing,
    AudereMajoraCrossingResult,
    PendingAudereMajoraOffer,
    _post_declaration,
    check_audere_majora_eligibility,
    end_audere_majora,
    resolve_audere_majora_offer,
)
from world.magic.exceptions import (
    AudereMajoraOfferNotFoundError,
    AudereMajoraOfferStaleError,
    AudereMajoraPathError,
    ProtagonismLockedError,
)
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    wire_audere_power_multipliers,
    with_corruption_at_stage,
)
from world.magic.models import CharacterGift, CharacterTechnique, PathGiftGrant
from world.magic.tests.majora_fixtures import build_crossing_world
from world.magic.types import AlterationGateError
from world.mechanics.engagement import CharacterEngagement
from world.progression.models import CharacterPathHistory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _accept(offer, path, text: str = "I am the one who stands here."):
    """Accept a pending Audere Majora offer; returns the AudereMajoraCrossingResult."""
    return resolve_audere_majora_offer(
        offer.pk, accept=True, path_id=path.pk, declaration_text=text
    )


def _build_crossing_character(boundary_level: int = 5, suffix: str = ""):
    """Build a fully-eligible character for Audere Majora crossing tests.

    Returns (character, sheet, threshold, prospect_path, puissant_path, offer).
    The Audere Majora ConditionTemplate is created by wire_audere_power_multipliers().
    """
    return build_crossing_world(boundary_level, f"_cx{suffix}")


# ---------------------------------------------------------------------------
# Accept happy path
# ---------------------------------------------------------------------------


class CrossingAcceptHappyPathTests(TestCase):
    """resolve_audere_majora_offer accept: level advances, history/receipt/condition written."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=5, suffix="_happy")

    def test_returns_accepted_true_with_correct_levels(self) -> None:
        result = _accept(self.offer, self.puissant_path)
        assert isinstance(result, AudereMajoraCrossingResult)
        assert result.accepted is True
        assert result.level_before == 5
        assert result.level_after == 6

    def test_primary_class_level_row_updated(self) -> None:
        _accept(self.offer, self.puissant_path)
        ccl = CharacterClassLevel.objects.get(character=self.character.sheet_data)
        assert ccl.level == 6

    def test_second_accept_of_same_offer_raises_not_found(self) -> None:
        """Sequential double-accept proxy for the concurrent race: row is gone."""
        _accept(self.offer, self.puissant_path)
        with self.assertRaises(AudereMajoraOfferNotFoundError):
            _accept(self.offer, self.puissant_path)

    def test_sheet_current_level_updated(self) -> None:
        _accept(self.offer, self.puissant_path)
        self.sheet.invalidate_class_level_cache()
        assert self.sheet.current_level == 6

    def test_path_history_row_created(self) -> None:
        _accept(self.offer, self.puissant_path)
        assert CharacterPathHistory.objects.filter(
            character=self.character.sheet_data, path=self.puissant_path
        ).exists()

    def test_crossing_receipt_fields_correct(self) -> None:
        _accept(self.offer, self.puissant_path)
        crossing = AudereMajoraCrossing.objects.get(
            character_sheet=self.sheet, threshold=self.threshold
        )
        assert crossing.chosen_path == self.puissant_path
        assert crossing.level_before == 5
        assert crossing.level_after == 6
        assert crossing.scene is None
        assert crossing.declaration_interaction is None

    def test_majora_condition_applied(self) -> None:
        _accept(self.offer, self.puissant_path)
        assert ConditionInstance.objects.filter(
            target=self.character,
            condition__name=AUDERE_MAJORA_CONDITION_NAME,
        ).exists()

    def test_offer_row_deleted(self) -> None:
        offer_pk = self.offer.pk
        _accept(self.offer, self.puissant_path)
        assert not PendingAudereMajoraOffer.objects.filter(pk=offer_pk).exists()


# ---------------------------------------------------------------------------
# Accept with active scene: declaration interaction created
# ---------------------------------------------------------------------------


class CrossingWithSceneTests(TestCase):
    """When an active scene exists, a POSE interaction is created and linked."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=6, suffix="_scene")
        self.scene = SceneFactory(location=self.character.location, is_active=True)

    def test_declaration_interaction_created(self) -> None:
        declaration_text = "I am the one who stands here."
        _accept(self.offer, self.puissant_path, declaration_text)
        interaction = Interaction.objects.filter(
            scene=self.scene, mode=InteractionMode.POSE
        ).first()
        assert interaction is not None
        assert interaction.content == declaration_text

    def test_result_declaration_id_matches_interaction(self) -> None:
        result = _accept(self.offer, self.puissant_path)
        interaction = Interaction.objects.filter(
            scene=self.scene, mode=InteractionMode.POSE
        ).first()
        assert result.declaration_interaction_id == interaction.pk

    def test_crossing_receipt_scene_and_interaction_set(self) -> None:
        result = _accept(self.offer, self.puissant_path)
        crossing = AudereMajoraCrossing.objects.get(
            character_sheet=self.sheet, threshold=self.threshold
        )
        assert crossing.scene == self.scene
        assert crossing.declaration_interaction_id == result.declaration_interaction_id


# ---------------------------------------------------------------------------
# Accept with no scene
# ---------------------------------------------------------------------------


class CrossingNoSceneTests(TestCase):
    """When there is no active scene, declaration fields are NULL."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=7, suffix="_noscene")

    def test_no_declaration_interaction_created(self) -> None:
        result = _accept(self.offer, self.puissant_path)
        assert result.declaration_interaction_id is None
        assert Interaction.objects.filter(mode=InteractionMode.POSE).count() == 0

    def test_receipt_scene_and_declaration_null(self) -> None:
        _accept(self.offer, self.puissant_path)
        crossing = AudereMajoraCrossing.objects.get(
            character_sheet=self.sheet, threshold=self.threshold
        )
        assert crossing.scene is None
        assert crossing.declaration_interaction is None


# ---------------------------------------------------------------------------
# Ineligible path raises AudereMajoraPathError — nothing written
# ---------------------------------------------------------------------------


class CrossingIneligiblePathTests(TestCase):
    """An unrelated path raises AudereMajoraPathError; no side effects written."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=8, suffix="_badpath")
        self.unrelated_path = PathFactory(
            name="Unrelated_Puissant_path_badpath", stage=PathStage.PUISSANT
        )

    def test_raises_path_error(self) -> None:
        with self.assertRaises(AudereMajoraPathError):
            _accept(self.offer, self.unrelated_path)

    def test_level_unchanged(self) -> None:
        with contextlib.suppress(AudereMajoraPathError):
            _accept(self.offer, self.unrelated_path)
        ccl = CharacterClassLevel.objects.get(character=self.character.sheet_data)
        assert ccl.level == 8

    def test_no_receipt_written(self) -> None:
        with contextlib.suppress(AudereMajoraPathError):
            _accept(self.offer, self.unrelated_path)
        assert not AudereMajoraCrossing.objects.filter(character_sheet=self.sheet).exists()

    def test_offer_still_present(self) -> None:
        with contextlib.suppress(AudereMajoraPathError):
            _accept(self.offer, self.unrelated_path)
        assert PendingAudereMajoraOffer.objects.filter(pk=self.offer.pk).exists()


# ---------------------------------------------------------------------------
# Decline
# ---------------------------------------------------------------------------


class CrossingDeclineTests(TestCase):
    """Declining deletes the offer, returns accepted=False, and allows re-firing."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=9, suffix="_decline")

    def test_returns_accepted_false(self) -> None:
        result = resolve_audere_majora_offer(self.offer.pk, accept=False)
        assert result.accepted is False

    def test_offer_deleted_on_decline(self) -> None:
        offer_pk = self.offer.pk
        resolve_audere_majora_offer(offer_pk, accept=False)
        assert not PendingAudereMajoraOffer.objects.filter(pk=offer_pk).exists()

    def test_no_receipt_on_decline(self) -> None:
        resolve_audere_majora_offer(self.offer.pk, accept=False)
        assert not AudereMajoraCrossing.objects.filter(character_sheet=self.sheet).exists()

    def test_level_unchanged_on_decline(self) -> None:
        resolve_audere_majora_offer(self.offer.pk, accept=False)
        ccl = CharacterClassLevel.objects.get(character=self.character.sheet_data)
        assert ccl.level == 9

    def test_gate_can_refire_after_decline(self) -> None:
        """After a decline, maybe_create_audere_majora_offer can create a new offer."""
        from world.magic.audere_majora import maybe_create_audere_majora_offer

        resolve_audere_majora_offer(self.offer.pk, accept=False)
        new_offer = maybe_create_audere_majora_offer(self.character, 20)
        assert new_offer is not None


# ---------------------------------------------------------------------------
# Stale offer
# ---------------------------------------------------------------------------


class CrossingStaleTests(TestCase):
    """Deleting the CharacterEngagement causes a stale offer; offer is deleted and error raised."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=10, suffix="_stale")

    def test_stale_raises_error(self) -> None:
        CharacterEngagement.objects.filter(character=self.character).delete()
        with self.assertRaises(AudereMajoraOfferStaleError):
            _accept(self.offer, self.puissant_path)

    def test_stale_deletes_offer(self) -> None:
        CharacterEngagement.objects.filter(character=self.character).delete()
        offer_pk = self.offer.pk
        with contextlib.suppress(AudereMajoraOfferStaleError):
            _accept(self.offer, self.puissant_path)
        assert not PendingAudereMajoraOffer.objects.filter(pk=offer_pk).exists()


# ---------------------------------------------------------------------------
# Spend guards: protagonism-locked and pending alterations
# ---------------------------------------------------------------------------


class CrossingSpendGuardTests(TestCase):
    """ProtagonismLockedError and AlterationGateError block crossing."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=11, suffix="_guards")

    def test_protagonism_locked_raises_error(self) -> None:
        resonance = ResonanceFactory()
        with_corruption_at_stage(self.sheet, resonance, stage=5)
        self.sheet.__dict__.pop("is_protagonism_locked", None)
        with self.assertRaises(ProtagonismLockedError):
            _accept(self.offer, self.puissant_path)

    def test_pending_alterations_raises_error(self) -> None:
        from world.magic.constants import PendingAlterationStatus
        from world.magic.factories import (
            AffinityFactory,
            PendingAlterationFactory,
        )

        affinity = AffinityFactory(name="Abyssal_guards_cx")
        resonance = ResonanceFactory(name="Shadow_guards_cx", affinity=affinity)
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=affinity,
            origin_resonance=resonance,
            status=PendingAlterationStatus.OPEN,
        )
        with self.assertRaises(AlterationGateError):
            _accept(self.offer, self.puissant_path)


# ---------------------------------------------------------------------------
# Unknown offer ID
# ---------------------------------------------------------------------------


class CrossingUnknownOfferTests(TestCase):
    """Unknown offer ID raises AudereMajoraOfferNotFoundError."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()

    def test_unknown_offer_raises_not_found(self) -> None:
        with self.assertRaises(AudereMajoraOfferNotFoundError):
            resolve_audere_majora_offer(999999, accept=True, path_id=1)


# ---------------------------------------------------------------------------
# Receipt gate: crossing again at the same boundary returns None from eligibility
# ---------------------------------------------------------------------------


class CrossingReceiptGateTests(TestCase):
    """After accepting, the receipt gate blocks a second eligibility check."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=12, suffix="_gate")

    def test_crossed_gate_closed(self) -> None:
        _accept(self.offer, self.puissant_path)
        # Force level back to 12 to isolate the receipt gate (not the level mismatch).
        ccl = CharacterClassLevel.objects.get(character=self.character.sheet_data)
        ccl.level = 12
        ccl.save(update_fields=["level"])
        self.sheet.invalidate_class_level_cache()

        result = check_audere_majora_eligibility(self.character, 20)
        assert result is None


# ---------------------------------------------------------------------------
# end_audere_majora
# ---------------------------------------------------------------------------


class EndAuderaMajoraTests(TestCase):
    """end_audere_majora removes the condition; safe no-op when absent."""

    def setUp(self) -> None:
        _audere, self.majora_template = wire_audere_power_multipliers()
        self.character = CharacterFactory(db_key="end_majora_char")

    def test_removes_condition(self) -> None:
        ConditionInstanceFactory(
            target=self.character,
            condition=self.majora_template,
            current_stage=None,
        )
        end_audere_majora(self.character)
        assert not ConditionInstance.objects.filter(
            target=self.character,
            condition__name=AUDERE_MAJORA_CONDITION_NAME,
        ).exists()

    def test_safe_noop_when_absent(self) -> None:
        # Should not raise
        end_audere_majora(self.character)


# ---------------------------------------------------------------------------
# _post_declaration empty-text guard
# ---------------------------------------------------------------------------


class TestPostDeclarationEmptyGuard(TestCase):
    """_post_declaration returns (scene, None) for empty or whitespace text."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = _build_crossing_character(boundary_level=4, suffix="_empty_guard")
        self.scene = SceneFactory(location=self.character.location, is_active=True)

    def test_empty_text_returns_no_interaction(self) -> None:
        result_scene, interaction = _post_declaration(self.character, "")
        self.assertEqual(result_scene, self.scene)
        self.assertIsNone(interaction)

    def test_whitespace_only_returns_no_interaction(self) -> None:
        result_scene, interaction = _post_declaration(self.character, "   ")
        self.assertEqual(result_scene, self.scene)
        self.assertIsNone(interaction)


# ---------------------------------------------------------------------------
# Path-crossing grants the new path's gift + techniques (#1579)
# ---------------------------------------------------------------------------


class CrossingGrantsPathMagicTests(TestCase):
    """Accepting the crossing grants the chosen path's PathGiftGrant gift + techniques."""

    def setUp(self) -> None:
        wire_audere_power_multipliers()
        (
            self.character,
            self.sheet,
            self.threshold,
            self.prospect_path,
            self.puissant_path,
            self.offer,
        ) = build_crossing_world(5, "_grant")
        self.gift = GiftFactory(name="Pyromancy_grant")
        self.gift.resonances.add(ResonanceFactory(name="Ember_grant"))
        self.technique = TechniqueFactory(name="Flame Lash_grant", gift=self.gift)
        grant = PathGiftGrant.objects.create(path=self.puissant_path, gift=self.gift)
        grant.starter_techniques.add(self.technique)

    def test_crossing_grants_gift_and_starter_technique(self) -> None:
        _accept(self.offer, self.puissant_path)

        self.assertTrue(CharacterGift.objects.filter(character=self.sheet, gift=self.gift).exists())
        self.assertTrue(
            CharacterTechnique.objects.filter(
                character=self.sheet, technique=self.technique
            ).exists()
        )

    def test_crossing_into_path_without_grant_mints_nothing(self) -> None:
        # The prospect path has no PathGiftGrant; crossing to the puissant path
        # must not grant the prospect path's (absent) kit — only the chosen path's.
        PathGiftGrant.objects.all().delete()
        _accept(self.offer, self.puissant_path)
        self.assertFalse(CharacterGift.objects.filter(character=self.sheet).exists())


class MidAudereMajoraCrossingTests(TestCase):
    """is_mid_audere_majora_crossing / any_character_mid_audere_majora_crossing (#1899)."""

    def test_pending_offer_means_mid_crossing(self) -> None:
        from world.magic.audere_majora import is_mid_audere_majora_crossing

        wire_audere_power_multipliers()
        (_character, sheet, _threshold, _prospect, _puissant, _offer) = build_crossing_world(
            5, "_pending"
        )
        assert is_mid_audere_majora_crossing(sheet) is True

    def test_no_offer_no_condition_means_not_mid_crossing(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.audere_majora import is_mid_audere_majora_crossing

        sheet = CharacterSheetFactory()
        assert is_mid_audere_majora_crossing(sheet) is False

    def test_active_condition_means_mid_crossing(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.audere_majora import is_mid_audere_majora_crossing

        sheet = CharacterSheetFactory()
        ConditionInstanceFactory(
            target=sheet.character,
            condition=ConditionTemplateFactory(name=AUDERE_MAJORA_CONDITION_NAME),
        )
        assert is_mid_audere_majora_crossing(sheet) is True

    def test_batched_check_true_when_any_one_is_mid_crossing(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.audere_majora import any_character_mid_audere_majora_crossing

        uninvolved = CharacterSheetFactory()
        mid_crossing = CharacterSheetFactory()
        ConditionInstanceFactory(
            target=mid_crossing.character,
            condition=ConditionTemplateFactory(name=AUDERE_MAJORA_CONDITION_NAME),
        )
        assert any_character_mid_audere_majora_crossing([uninvolved, mid_crossing]) is True

    def test_batched_check_false_when_none_mid_crossing(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.audere_majora import any_character_mid_audere_majora_crossing

        sheets = [CharacterSheetFactory() for _ in range(3)]
        assert any_character_mid_audere_majora_crossing(sheets) is False

    def test_batched_check_empty_input_is_false(self) -> None:
        from world.magic.audere_majora import any_character_mid_audere_majora_crossing

        assert any_character_mid_audere_majora_crossing([]) is False

    def test_batched_check_is_bounded_query_count(self) -> None:
        """Regression (#1899 spec review): must not issue one query pair per
        character — a large battle can have 10+ active participants. Sheets
        must be re-fetched from the DB (not the raw factory instances) so a
        cached FK on the Python object can't hide an N+1."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.character_sheets.models import CharacterSheet
        from world.magic.audere_majora import any_character_mid_audere_majora_crossing

        ids = [CharacterSheetFactory().pk for _ in range(15)]
        sheets = list(CharacterSheet.objects.filter(pk__in=ids))
        with self.assertNumQueries(2):
            any_character_mid_audere_majora_crossing(sheets)

    def test_batched_check_true_for_pending_offer_branch(self) -> None:
        """Regression (#1899 spec review): the PendingAudereMajoraOffer branch of
        the batched function was previously unverified — only the ConditionInstance
        branch had a true-case test."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.audere_majora import any_character_mid_audere_majora_crossing

        wire_audere_power_multipliers()
        (_character, mid_crossing_sheet, _threshold, _prospect, _puissant, _offer) = (
            build_crossing_world(5, "_batchedoffer")
        )
        uninvolved = CharacterSheetFactory()
        assert any_character_mid_audere_majora_crossing([uninvolved, mid_crossing_sheet]) is True
