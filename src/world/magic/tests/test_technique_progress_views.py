"""Tests for TechniqueProgressViewSet — HTTP contract for list/train (#2739 Task 2).

Exercises the endpoints the way the web frontend hits them:
  • GET  /api/magic/technique-progress/                  → the actor's own meters
  • POST /api/magic/technique-progress/<technique_id>/train/ → run one session
  • no puppet → 400 "No active character."
  • unauthenticated → 401/403
  • another account's meters never appear in list
  • train 200 happy path; 400 mappings (cap-exceeded, AP-short, already-known,
    no-such-meter)
  • X-Character-ID header scopes to that (owned, non-puppeted) character; an
    unowned character 404s rather than falling back to the puppet

Setup mirrors ``actions/tests/test_technique_training_action.py`` (the seam
this viewset dispatches through) for the check-content + meter seeding.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from evennia_extensions.factories import ObjectDBFactory
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, TechniqueFactory
from world.magic.models import (
    CharacterGift,
    CharacterTechnique,
    TechniqueProgress,
    Thread,
    TrainingOutcomeAward,
)
from world.magic.views_technique_progress import TechniqueProgressViewSet
from world.traits.models import CheckOutcome

# Canonical outcome tiers (name -> success_level), matching seeds/checks.py.
_CANONICAL_OUTCOMES = [
    ("Critical Failure", -2),
    ("Failure", -1),
    ("Partial Success", 0),
    ("Success", 1),
    ("Critical Success", 2),
]


def _ensure_outcome(name: str, success_level: int) -> CheckOutcome:
    outcome, _ = CheckOutcome.objects.get_or_create(
        name=name, defaults={"success_level": success_level}
    )
    return outcome


def _actor_user(character, *, available_characters=None):
    """Fake authenticated user whose ``puppet`` is ``character``.

    Mirrors ``test_motif_style_views._actor_user``.
    """
    owned = available_characters if available_characters is not None else [character]
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=character.db_account_id,
        puppet=character,
        get_available_characters=lambda: owned,
    )


def _no_puppet_user(*, available_characters=None):
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=None,
        puppet=None,
        get_available_characters=lambda: available_characters or [],
    )


class TechniqueProgressViewSetTestBase(TestCase):
    """One learner with check-content seeded so a real training session can resolve."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.factory = APIRequestFactory()

        self.room = ObjectDBFactory(
            db_key="TrainingRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.learner = CharacterSheetFactory()
        self.learner.character.location = self.room
        self.learner.character.save()

        self.pool = ActionPointPool.get_or_create_for_character(self.learner.character)
        self.pool.current = 500
        self.pool.save()

        self.technique = TechniqueFactory()
        CharacterGift.objects.create(character=self.learner, gift=self.technique.gift)
        Thread.objects.create(
            owner=self.learner,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.technique.gift,
            level=0,
        )

        self.outcomes = {name: _ensure_outcome(name, sl) for name, sl in _CANONICAL_OUTCOMES}
        self._seed_award_rows()
        self._seed_check_content()

    def _seed_award_rows(self) -> None:
        multipliers = {
            "Critical Failure": Decimal("0.00"),
            "Failure": Decimal("0.00"),
            "Partial Success": Decimal("0.50"),
            "Success": Decimal("1.00"),
            "Critical Success": Decimal("1.50"),
        }
        for name, mult in multipliers.items():
            TrainingOutcomeAward.objects.update_or_create(
                outcome_tier=self.outcomes[name],
                defaults={"dev_point_multiplier": mult},
            )

    def _seed_check_content(self) -> None:
        """Minimal CheckType so the seam can resolve a check."""
        from world.checks.models import CheckCategory, CheckType, CheckTypeTrait
        from world.skills.models import Skill
        from world.traits.models import Trait, TraitCategory, TraitType

        arcane_trait, _ = Trait.objects.get_or_create(
            name="Arcane Theory",
            defaults={
                "trait_type": TraitType.SKILL,
                "category": TraitCategory.MAGIC,
                "is_public": True,
            },
        )
        Skill.objects.get_or_create(
            trait=arcane_trait,
            defaults={
                "tooltip": "Understanding the theoretical underpinnings of magical techniques.",
                "display_order": 0,
                "is_active": True,
            },
        )
        intellect_trait, _ = Trait.objects.get_or_create(
            name="intellect",
            defaults={
                "trait_type": TraitType.STAT,
                "category": TraitCategory.MENTAL,
                "is_public": True,
            },
        )
        category, _ = CheckCategory.objects.get_or_create(
            name="Magic",
            defaults={"description": "Magic checks.", "display_order": 40},
        )
        check_type, _ = CheckType.objects.get_or_create(
            name="Technique Training",
            category=category,
            defaults={"is_active": True, "display_order": 10},
        )
        w = Decimal("1.0")
        CheckTypeTrait.objects.update_or_create(
            check_type=check_type, trait=intellect_trait, defaults={"weight": w}
        )
        CheckTypeTrait.objects.update_or_create(
            check_type=check_type, trait=arcane_trait, defaults={"weight": w}
        )

    def _make_progress(self, *, total_required=50, technique=None, teacher_tenure=None):
        return TechniqueProgress.objects.create(
            character_sheet=self.learner,
            technique=technique or self.technique,
            total_required=total_required,
            source="gift_acquisition",
            teacher_tenure=teacher_tenure,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_list(self, puppet, *, character_id=None):
        extra = {"HTTP_X_CHARACTER_ID": str(character_id)} if character_id is not None else {}
        request = self.factory.get("/api/magic/technique-progress/", **extra)
        force_authenticate(request, user=puppet)
        view = TechniqueProgressViewSet.as_view({"get": "list"})
        return view(request)

    def _post_train(self, puppet, technique_id, payload=None, *, character_id=None):
        extra = {"HTTP_X_CHARACTER_ID": str(character_id)} if character_id is not None else {}
        request = self.factory.post(
            f"/api/magic/technique-progress/{technique_id}/train/",
            payload or {},
            format="json",
            **extra,
        )
        force_authenticate(request, user=puppet)
        view = TechniqueProgressViewSet.as_view({"post": "train"})
        return view(request, pk=str(technique_id))


# ===========================================================================
# list
# ===========================================================================


class TechniqueProgressListEndpointTests(TechniqueProgressViewSetTestBase):
    def test_list_no_puppet_returns_400(self) -> None:
        resp = self._get_list(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_list_anonymous_user_denied(self) -> None:
        client = APIClient()
        response = client.get("/api/magic/technique-progress/")
        # DRF returns 403 for unauthenticated SessionAuthentication, 401 for
        # TokenAuthentication (mirrors test_session_views.py).
        self.assertIn(response.status_code, (401, 403))

    def test_list_returns_own_meters_with_contract_keys(self) -> None:
        self._make_progress(total_required=50)

        resp = self._get_list(_actor_user(self.learner.character))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        row = resp.data[0]
        self.assertEqual(
            set(row.keys()),
            {
                "id",
                "technique_id",
                "technique_name",
                "points_accumulated",
                "total_required",
                "teacher_name",
                "source_label",
                "weekly_remaining",
            },
        )
        self.assertEqual(row["technique_id"], self.technique.pk)
        self.assertEqual(row["technique_name"], self.technique.name)
        self.assertEqual(row["points_accumulated"], 0)
        self.assertEqual(row["total_required"], 50)
        self.assertIsNone(row["teacher_name"])
        self.assertTrue(row["source_label"])
        self.assertIsNotNone(row["weekly_remaining"])

    def test_list_scopes_to_own_meters_not_another_accounts(self) -> None:
        self._make_progress(total_required=50)

        other_sheet = CharacterSheetFactory()
        other_technique = TechniqueFactory()
        CharacterGift.objects.create(character=other_sheet, gift=other_technique.gift)
        TechniqueProgress.objects.create(
            character_sheet=other_sheet,
            technique=other_technique,
            total_required=30,
            source="gift_acquisition",
        )

        resp = self._get_list(_actor_user(self.learner.character))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["technique_id"], self.technique.pk)


# ===========================================================================
# train
# ===========================================================================


class TechniqueProgressTrainEndpointTests(TechniqueProgressViewSetTestBase):
    def test_train_no_puppet_returns_400(self) -> None:
        self._make_progress(total_required=50)

        resp = self._post_train(_no_puppet_user(), self.technique.pk)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_train_happy_path_returns_200_and_advances_meter(self) -> None:
        progress = self._make_progress(total_required=50)

        with force_check_outcome(self.outcomes["Success"]):
            resp = self._post_train(
                _actor_user(self.learner.character), self.technique.pk, {"ap_to_invest": 20}
            )

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["technique_id"], self.technique.pk)
        self.assertFalse(resp.data["technique_acquired"])
        progress.refresh_from_db()
        self.assertEqual(progress.points_accumulated, 20)

    def test_train_no_such_meter_returns_400(self) -> None:
        # No TechniqueProgress row exists for this technique at all.
        resp = self._post_train(_actor_user(self.learner.character), self.technique.pk)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)

    def test_train_cap_exceeded_returns_400(self) -> None:
        self._make_progress(total_required=500)
        from world.magic.services.gift_acquisition import get_gift_acquisition_config

        config = get_gift_acquisition_config()
        config.weekly_training_cap = 5
        config.save()

        with force_check_outcome(self.outcomes["Success"]):
            first = self._post_train(
                _actor_user(self.learner.character), self.technique.pk, {"ap_to_invest": 5}
            )
            second = self._post_train(
                _actor_user(self.learner.character), self.technique.pk, {"ap_to_invest": 5}
            )

        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 400)
        self.assertIn("detail", second.data)

    def test_train_ap_short_returns_400(self) -> None:
        self._make_progress(total_required=500)
        self.pool.current = 2
        self.pool.save()

        with force_check_outcome(self.outcomes["Success"]):
            resp = self._post_train(
                _actor_user(self.learner.character), self.technique.pk, {"ap_to_invest": 20}
            )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)

    def test_train_already_known_returns_400(self) -> None:
        self._make_progress(total_required=20)
        CharacterTechnique.objects.create(character=self.learner, technique=self.technique)

        with force_check_outcome(self.outcomes["Success"]):
            resp = self._post_train(
                _actor_user(self.learner.character), self.technique.pk, {"ap_to_invest": 20}
            )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("already knows", resp.data["detail"])


# ===========================================================================
# X-Character-ID scoping (mirrors #2030's MotifStyleViewSet review fix)
# ===========================================================================


class TechniqueProgressCharacterHeaderScopingTests(TechniqueProgressViewSetTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.alt_sheet = CharacterSheetFactory()
        self.alt_technique = TechniqueFactory()
        CharacterGift.objects.create(character=self.alt_sheet, gift=self.alt_technique.gift)
        TechniqueProgress.objects.create(
            character_sheet=self.alt_sheet,
            technique=self.alt_technique,
            total_required=40,
            source="gift_acquisition",
        )

        self.unowned_sheet = CharacterSheetFactory()

    def test_list_scopes_to_header_character_not_puppet(self) -> None:
        self._make_progress(total_required=50)
        user = _actor_user(
            self.learner.character,
            available_characters=[self.learner.character, self.alt_sheet.character],
        )

        resp = self._get_list(user, character_id=self.alt_sheet.character.pk)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["technique_id"], self.alt_technique.pk)

    def test_list_header_naming_unowned_character_returns_404_not_puppet_fallback(self) -> None:
        user = _actor_user(self.learner.character, available_characters=[self.learner.character])

        resp = self._get_list(user, character_id=self.unowned_sheet.character.pk)

        self.assertEqual(resp.status_code, 404)
        self.assertIn("character", resp.data["detail"].lower())

    def test_train_header_naming_unowned_character_returns_404(self) -> None:
        self._make_progress(total_required=50)
        user = _actor_user(self.learner.character, available_characters=[self.learner.character])

        resp = self._post_train(
            user, self.technique.pk, character_id=self.unowned_sheet.character.pk
        )

        self.assertEqual(resp.status_code, 404)


# ===========================================================================
# missing "Technique Training" CheckType (#3043)
# ===========================================================================


class TechniqueProgressTrainMissingCheckTypeTests(TestCase):
    """No silent CheckType.objects.first() fallback -- a clean 400 instead (#3043).

    Setup mirrors ``TechniqueProgressViewSetTestBase`` but deliberately skips
    seeding the "Technique Training" CheckType, mirroring a real deploy where
    the content half of #3043 (ArxII-lore#72) hasn't shipped yet.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.factory = APIRequestFactory()

        self.room = ObjectDBFactory(
            db_key="TrainingRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.learner = CharacterSheetFactory()
        self.learner.character.location = self.room
        self.learner.character.save()

        self.pool = ActionPointPool.get_or_create_for_character(self.learner.character)
        self.pool.current = 500
        self.pool.save()

        self.technique = TechniqueFactory()
        CharacterGift.objects.create(character=self.learner, gift=self.technique.gift)
        Thread.objects.create(
            owner=self.learner,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.technique.gift,
            level=0,
        )
        TechniqueProgress.objects.create(
            character_sheet=self.learner,
            technique=self.technique,
            total_required=50,
            source="gift_acquisition",
        )

    def _post_train(self, puppet, technique_id, payload=None):
        request = self.factory.post(
            f"/api/magic/technique-progress/{technique_id}/train/",
            payload or {},
            format="json",
        )
        force_authenticate(request, user=puppet)
        view = TechniqueProgressViewSet.as_view({"post": "train"})
        return view(request, pk=str(technique_id))

    def test_train_missing_check_type_returns_400_plain_message(self) -> None:
        resp = self._post_train(
            _actor_user(self.learner.character), self.technique.pk, {"ap_to_invest": 20}
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            resp.data["detail"], "Technique training is not configured on this server yet."
        )
