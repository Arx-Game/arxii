"""Test for migration 0110's ``forwards`` backfill (#3675), replayed on historical models.

0111 (the very next migration) deletes the source models 0110 reads --
``GlimpseTagDistinctionSuggestion``, ``OriginTemplateSlotChoice.grants_distinction``,
``BeginningTradition.required_distinction`` -- so the live factories can no longer
build the rows 0110 has to migrate. This test rewinds the schema to 0109 with
``MigrationExecutor``, builds the source rows directly through the historical models
at that state, replays 0110, and asserts against the historical models at 0110's
state. ``tearDown`` migrates the schema forward again so later tests in the run see
the full (current) schema.

Requires real migration replay: the SQLite fast tier disables migration replay
entirely (schema is built straight from current model state -- see
``server/conf/sqlite_test_settings.py``), and the default Postgres tier also builds
its test database from current model state (``tools/build_schema.py`` +
``MIGRATE=False`` in ``server/conf/test_settings.py``), not by literally replaying
each migration. Confirmed empirically (2026-09-07): ``MIGRATE=False`` makes Django's
``create_test_db`` run ``migrate --run-syncdb`` with every app's
``MIGRATION_MODULES`` forced to ``None`` (see
``django/db/backends/base/creation.py``), so ``django_migrations`` starts this test
database completely empty even though the physical schema matches the migration
graph's head. ``MigrationExecutor`` needs that table to know what's already applied
before it can compute a real backward plan, so ``setUp`` fake-applies the whole graph
first (``migrate --fake``); ``tearDown`` migrates forward again and then empties
``django_migrations`` back out, restoring the baseline this test found. Only Postgres
supports running the resulting plan's DDL (SQLite can't even locate migrations for
the app, since they're disabled), hence ``@tag("postgres")``.
"""

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase, tag

from evennia_extensions.factories import AccountFactory

_START = ("arxii", "0109_distinction_offers_expand")
_MIDPOINT = ("arxii", "0110_distinction_offers_data")


@tag("postgres")
class DistinctionOffersMigrationTests(TransactionTestCase):
    """Replays 0110's ``forwards`` on historical models rewound from 0109.

    ``TransactionTestCase`` (not ``TestCase``) because this test rewinds and
    replays real schema changes -- the DDL needs to actually commit, not sit
    inside ``TestCase``'s outer atomic block.
    """

    def setUp(self):
        super().setUp()
        # See the module docstring: this test database's django_migrations table
        # starts empty even though its schema already matches the migration
        # graph's head, so fake-apply the whole graph before asking
        # MigrationExecutor to compute a real backward plan.
        call_command("migrate", fake=True, verbosity=0)
        # Registered BEFORE the rewind: a failure inside the backward DDL would
        # skip tearDown and leave the shared keepdb test database half-reversed,
        # but addCleanup runs even when setUp raises past this line.
        self.addCleanup(self._restore_head)
        executor = MigrationExecutor(connection)
        executor.migrate([_START])

    def _restore_head(self):
        # Build a fresh executor: the loader caches state from the last
        # ``migrate()`` call, so reusing the ``setUp`` executor here would
        # replay against a stale graph.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        # Restore the empty django_migrations baseline this test found.
        MigrationRecorder(connection).migration_qs.all().delete()

    def _historical_apps(self, node):
        executor = MigrationExecutor(connection)
        return executor.loader.project_state(node).apps

    def _build_source_rows(self, apps):
        """Create the rows 0110 reads, through the historical models at 0109."""
        Distinction = apps.get_model("arxii", "Distinction")
        DistinctionCategory = apps.get_model("arxii", "DistinctionCategory")
        DistinctionTag = apps.get_model("arxii", "DistinctionTag")
        GlimpseTag = apps.get_model("arxii", "GlimpseTag")
        Suggestion = apps.get_model("arxii", "GlimpseTagDistinctionSuggestion")
        StartingArea = apps.get_model("arxii", "StartingArea")
        Beginnings = apps.get_model("arxii", "Beginnings")
        OriginTemplate = apps.get_model("arxii", "OriginTemplate")
        OriginTemplateSlot = apps.get_model("arxii", "OriginTemplateSlot")
        Choice = apps.get_model("arxii", "OriginTemplateSlotChoice")
        Tradition = apps.get_model("arxii", "Tradition")
        Slate = apps.get_model("arxii", "BeginningTradition")
        Draft = apps.get_model("arxii", "CharacterDraft")

        category = DistinctionCategory.objects.create(name="Test Category", slug="test-category")

        glimpse_distinction = Distinction.objects.create(
            name="Marked by the Glimpse", slug="marked-by-the-glimpse", category=category
        )
        other_glimpse_distinction = Distinction.objects.create(
            name="Also Marked", slug="also-marked", category=category
        )
        tag_a = GlimpseTag.objects.create(axis="TONE", name="Tag A", slug="tag-a")
        tag_b = GlimpseTag.objects.create(axis="TONE", name="Tag B", slug="tag-b")
        suggestion = Suggestion.objects.create(
            distinction=glimpse_distinction, tag=tag_a, sort_order=1
        )
        Suggestion.objects.create(distinction=other_glimpse_distinction, tag=tag_b, sort_order=2)

        bundled_distinction = Distinction.objects.create(
            name="Bundled Kin", slug="bundled-kin", category=category
        )
        starting_area = StartingArea.objects.create(name="Test Area", description="d")
        beginning = Beginnings.objects.create(
            name="Test Beginning", description="d", starting_area=starting_area
        )
        origin_template = OriginTemplate.objects.create(
            name="Template",
            frame_narrative="frame",
            beginning=beginning,
            allows_no_family=True,
        )
        slot = OriginTemplateSlot.objects.create(
            name="Slot", prompt="prompt", template=origin_template
        )
        choice = Choice.objects.create(
            name="Choice", slot=slot, grants_distinction=bundled_distinction
        )

        # The Unbound row: 0110 reads it by tradition name (documented, migration-only).
        unbound_tradition = Tradition.objects.create(name="Unbound")
        unbound_slate_row = Slate.objects.create(beginning=beginning, tradition=unbound_tradition)

        # The orphaned-tradition row: 0110 reads it by its drawback's marker tag
        # (documented, migration-only).
        marker_tag = DistinctionTag.objects.create(
            name="Orphaned Tradition Marker", slug="orphaned-tradition-marker"
        )
        drawback = Distinction.objects.create(
            name="Orphaned Tradition", slug="orphaned-tradition", category=category
        )
        drawback.tags.add(marker_tag)
        orphaned_tradition = Tradition.objects.create(name="Metallic Order")
        orphaned_slate_row = Slate.objects.create(
            beginning=beginning, tradition=orphaned_tradition, required_distinction=drawback
        )

        account = AccountFactory()
        draft_at_stage_4 = Draft.objects.create(account_id=account.id, current_stage=4)
        legacy_draft = Draft.objects.create(account_id=AccountFactory().id, current_stage=6)

        return {
            "glimpse_distinction": glimpse_distinction,
            "other_glimpse_distinction": other_glimpse_distinction,
            "suggestion": suggestion,
            "bundled_distinction": bundled_distinction,
            "choice": choice,
            "unbound_slate_row": unbound_slate_row,
            "orphaned_slate_row": orphaned_slate_row,
            "draft_at_stage_4": draft_at_stage_4,
            "legacy_draft": legacy_draft,
        }

    def test_forwards_creates_offers_and_stamps_slate_and_stage(self):
        start_apps = self._historical_apps(_START)
        rows = self._build_source_rows(start_apps)

        executor = MigrationExecutor(connection)
        executor.migrate([_MIDPOINT])

        mid_apps = MigrationExecutor(connection).loader.project_state(_MIDPOINT).apps
        Offer = mid_apps.get_model("arxii", "DistinctionOffer")
        Slate = mid_apps.get_model("arxii", "BeginningTradition")
        Draft = mid_apps.get_model("arxii", "CharacterDraft")

        assert Offer.objects.count() == 3

        glimpse_offer = Offer.objects.get(
            distinction_id=rows["glimpse_distinction"].id, chapter="glimpse"
        )
        assert glimpse_offer.glimpse_tag_id == rows["suggestion"].tag_id
        assert glimpse_offer.arrives_as == "choice"
        assert glimpse_offer.name == rows["glimpse_distinction"].name

        lineage_offer = Offer.objects.get(
            distinction_id=rows["bundled_distinction"].id, chapter="lineage"
        )
        assert lineage_offer.origin_choice_id == rows["choice"].id
        assert lineage_offer.arrives_as == "bundled"

        # BeginningTradition and CharacterDraft are SharedMemoryModel (idmapper);
        # a bulk ``.update()`` leaves an already-fetched instance's cache stale.
        # Read the raw column via ``values_list`` instead of a cached instance.
        unbound_state = (
            Slate.objects.filter(pk=rows["unbound_slate_row"].pk)
            .values_list("state", flat=True)
            .first()
        )
        assert unbound_state == "self_taught"

        orphaned_state = (
            Slate.objects.filter(pk=rows["orphaned_slate_row"].pk)
            .values_list("state", flat=True)
            .first()
        )
        assert orphaned_state == "teachers_gone"

        stamped_stage = (
            Draft.objects.filter(pk=rows["draft_at_stage_4"].pk)
            .values_list("current_stage", flat=True)
            .first()
        )
        assert stamped_stage == 5

        # A draft not at stage 4 (and carrying no ``offer_ids`` in its default,
        # empty ``draft_data``) is untouched by 0110 -- neither its stage nor its
        # draft_data changes.
        legacy_stage, legacy_draft_data = (
            Draft.objects.filter(pk=rows["legacy_draft"].pk)
            .values_list("current_stage", "draft_data")
            .first()
        )
        assert legacy_stage == 6
        assert "offer_ids" not in (legacy_draft_data or {})

    def test_forwards_is_idempotent(self):
        start_apps = self._historical_apps(_START)
        self._build_source_rows(start_apps)

        executor = MigrationExecutor(connection)
        executor.migrate([_MIDPOINT])
        # Re-run the same migration's forwards() again by walking back one step
        # and forward again -- get_or_create in 0110 must not duplicate offers.
        executor = MigrationExecutor(connection)
        executor.migrate([_START])
        executor = MigrationExecutor(connection)
        executor.migrate([_MIDPOINT])

        mid_apps = MigrationExecutor(connection).loader.project_state(_MIDPOINT).apps
        Offer = mid_apps.get_model("arxii", "DistinctionOffer")
        assert Offer.objects.count() == 3
