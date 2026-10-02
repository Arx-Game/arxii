"""Tests for the plain-Audere surge broadcast on accept (#3451).

The Audere Majora manifestation's smaller echo: an authored
``AudereThreshold.surge_manifestation_text`` is EMITted to the active scene
when a character accepts the surge; blank text keeps the accept room-silent.

Blank-text coverage lives in its own TestCase (not a mutated shared fixture):
a ``save()`` on a setUpTestData row survives the per-test rollback inside the
idmapper identity map and would leak into sibling tests.
"""

from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    SOULFRAY_CONDITION_NAME,
    offer_audere,
)
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    IntensityTierFactory,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction


def _make_lifecycle_character(db_key: str) -> ObjectDB:
    """A character able to accept a surge: sheet + anima + active engagement."""
    character = CharacterSheetFactory(character__db_key=db_key).character
    CharacterAnimaFactory(character=character.sheet_data, current=10, maximum=50)
    CharacterEngagement.objects.create(
        character=character.sheet_data,
        engagement_type=EngagementType.CHALLENGE,
        source_content_type=ContentType.objects.get_for_model(ObjectDB),
        source_id=character.pk,
    )
    return character


def _make_threshold(*, surge_text: str, tier_name: str):
    ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
    soulfray = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
    stage = ConditionStageFactory(condition=soulfray, stage_order=3, name="Ripping")
    tier = IntensityTierFactory(name=tier_name, threshold=15)
    return AudereThresholdFactory(
        minimum_intensity_tier=tier,
        minimum_warp_stage=stage,
        intensity_bonus=20,
        anima_pool_bonus=30,
        surge_manifestation_text=surge_text,
    )


def _emit_count(scene=None) -> int:
    qs = Interaction.objects.filter(mode=InteractionMode.EMIT)
    if scene is not None:
        qs = qs.filter(scene=scene)
    return qs.count()


class AudereSurgeBroadcastTests(TestCase):
    """With authored text, accept announces; decline and no-scene stay silent."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.threshold = _make_threshold(
            surge_text="{name} answers the surge.", tier_name="Major_surge_bc"
        )

    def setUp(self) -> None:
        self.character = _make_lifecycle_character("surge_bc_char")

    def test_accept_broadcasts_substituted_text_to_active_scene(self) -> None:
        scene = SceneFactory(location=self.character.location, is_active=True)
        persona_name = self.character.sheet_data.primary_persona.name

        result = offer_audere(self.character, accept=True)

        assert result.accepted is True
        emits = Interaction.objects.filter(scene=scene, mode=InteractionMode.EMIT)
        assert emits.count() == 1
        assert emits.first().content == f"{persona_name} answers the surge."

    def test_decline_stays_silent(self) -> None:
        scene = SceneFactory(location=self.character.location, is_active=True)

        result = offer_audere(self.character, accept=False)

        assert result.accepted is False
        assert _emit_count(scene) == 0

    def test_no_active_scene_no_ops(self) -> None:
        result = offer_audere(self.character, accept=True)

        assert result.accepted is True
        assert _emit_count() == 0


class AudereSurgeBlankTextTests(TestCase):
    """The default blank text keeps an accepted surge room-silent."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.threshold = _make_threshold(surge_text="", tier_name="Major_surge_blank")

    def test_blank_text_stays_silent(self) -> None:
        character = _make_lifecycle_character("surge_blank_char")
        scene = SceneFactory(location=character.location, is_active=True)

        result = offer_audere(character, accept=True)

        assert result.accepted is True
        assert _emit_count(scene) == 0


class AudereSurgeRoutingFailureTests(TestCase):
    """#4101 fix round 2: a DatabaseError resolving GM candidates, or a raise
    from the fallback delivery itself, must not corrupt the surrounding Audere
    acceptance or silently retry delivery."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.threshold = _make_threshold(
            surge_text="{name} answers the surge.", tier_name="Major_surge_dberr"
        )

    def setUp(self) -> None:
        self.character = _make_lifecycle_character("surge_dberr_char")

    def test_candidate_lookup_database_error_commits_and_delivers_once(self) -> None:
        """Patches the recipients helper to raise ``DatabaseError`` -- proving the
        savepoint ``_announce_surge`` wraps its scene lookup + routing call in
        actually contains the failure. ``resolve_audere_offer`` wraps the whole
        accept in its OWN outer ``transaction.atomic()``; on Postgres an
        unguarded failure here would abort THAT transaction, losing the Audere
        acceptance (condition/engagement/anima) it was about to commit, and the
        fallback delivery would then raise too. Wrapping the ``offer_audere``
        call in an explicit ``with transaction.atomic()`` here simulates that
        same nesting; a further write inside the SAME block proves the
        connection is still usable afterward (a Postgres-aborted transaction
        would refuse it with "current transaction is aborted")."""
        scene = SceneFactory(location=self.character.location, is_active=True)
        persona_name = self.character.sheet_data.primary_persona.name

        with mock.patch(
            "world.gm.prompt_services.prompt_recipients", side_effect=DatabaseError("boom")
        ):
            with transaction.atomic():
                result = offer_audere(self.character, accept=True)
                CharacterAnimaFactory(character=CharacterSheetFactory().character.sheet_data)

        assert result.accepted is True
        emits = Interaction.objects.filter(scene=scene, mode=InteractionMode.EMIT)
        assert emits.count() == 1
        assert emits.first().content == f"{persona_name} answers the surge."

    def test_delivery_failure_raises_once_and_is_not_retried(self) -> None:
        """If the fallback delivery itself raises, ``_announce_surge`` must not
        retry it -- there is exactly one delivery call site.

        The side effect is ``DatabaseError`` specifically (#4101 fix round 3):
        the OLD (fix round 1) code wrapped its ENTIRE ``route_narratable_event``
        call -- including the ``deliver_unprompted`` invocation that call made
        internally when there were no real GM recipients -- in a single
        ``try/except DatabaseError``, so a ``DatabaseError`` raised from inside
        that first delivery attempt was caught and delivery was retried a
        SECOND time from the except block. A plain ``RuntimeError`` would
        propagate straight out of that first attempt without ever reaching the
        old code's ``except DatabaseError``, so it would pass against the old,
        buggy code too -- it has to be a ``DatabaseError`` to actually exercise
        (and fail against) the double-delivery bug this test guards."""
        SceneFactory(location=self.character.location, is_active=True)
        boom = DatabaseError("boom")

        with mock.patch(
            "world.scenes.interaction_services.broadcast_scene_emit", side_effect=boom
        ) as mocked:
            with self.assertRaises(DatabaseError):
                offer_audere(self.character, accept=True)

        mocked.assert_called_once()


@tag("postgres")
class AudereSurgePostgresSavepointTests(TestCase):
    """#4101 fix round 2/3: the savepoint ``_announce_surge`` wraps its scene
    lookup + routing call in must actually contain a REAL database-level
    failure on Postgres. SQLite's own ``transaction.atomic()`` savepoints
    don't reproduce Postgres's whole-transaction-abort-on-error semantics, so
    the mocked-``DatabaseError`` tests above (``AudereSurgeRoutingFailureTests``)
    can only prove the code's SHAPE is right, never that a real Postgres
    failure is actually survived. This class forces a genuine database error
    (invalid SQL through ``connection.cursor()``) from inside the routing call.

    Gated to the Postgres parity tier (CI's ``just test-parity``/``just
    regression``) via ``@tag("postgres")`` -- Postgres tests are not run
    locally in this environment, and ``just test-fast`` passes
    ``--exclude-tag postgres``, so this whole class (including
    ``setUpTestData``) is skipped entirely under the SQLite fast tier; the
    deliberately-invalid raw SQL below never executes there.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.threshold = _make_threshold(
            surge_text="{name} answers the surge.", tier_name="Major_surge_pg_savepoint"
        )

    def test_real_query_failure_inside_routing_leaves_outer_transaction_usable(self) -> None:
        character = _make_lifecycle_character("surge_pg_savepoint_char")
        scene = SceneFactory(location=character.location, is_active=True)
        persona_name = character.sheet_data.primary_persona.name

        def _break_query(*args, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM arxii_this_table_does_not_exist_4101")

        with mock.patch("world.gm.prompt_services.prompt_recipients", side_effect=_break_query):
            with transaction.atomic():
                result = offer_audere(character, accept=True)
                # A further write in the SAME outer transaction (standing in
                # for resolve_audere_offer's own transaction.atomic()) proves
                # the connection is still usable: a real Postgres
                # whole-transaction abort -- which _announce_surge's own
                # savepoint exists to prevent -- would refuse this with
                # "current transaction is aborted, commands ignored until end
                # of transaction block."
                CharacterAnimaFactory(character=CharacterSheetFactory().character.sheet_data)

        assert result.accepted is True
        emits = Interaction.objects.filter(scene=scene, mode=InteractionMode.EMIT)
        assert emits.count() == 1
        assert emits.first().content == f"{persona_name} answers the surge."
