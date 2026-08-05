"""Idempotent weather re-seed (#1522).

Pins the upsert contract: loading the corpus twice updates in place rather than duplicating
(the bug ``loaddata`` has with the keyless ``WeatherEmit`` rows), and editing a field then
re-loading mutates the existing row.
"""

import json

from django.test import TestCase

from world.locations.constants import StatKey
from world.weather.factories import WeatherTypeFactory
from world.weather.models import FeastDay, WeatherEmit, WeatherType, WeatherTypeExposure
from world.weather.seed import (
    load_weather_seed,
    upsert_weather_emits,
    upsert_weather_type_exposures,
    upsert_weather_types,
)

TYPES = [
    {
        "model": "weather.weathertype",
        "fields": {"name": "Storm", "is_automated": True, "selection_weight": 3},
    },
    {
        "model": "weather.weathertype",
        "fields": {"name": "Clear", "is_automated": True, "selection_weight": 5},
    },
]

EXPOSURES = [
    {
        "model": "weather.weathertypeexposure",
        "fields": {"weather_type": ["Storm"], "stat_key": StatKey.WET, "value": 40},
    },
    {
        "model": "weather.weathertypeexposure",
        "fields": {"weather_type": ["Storm"], "stat_key": StatKey.WIND, "value": 30},
    },
]

EMITS = [
    {
        "model": "weather.weatheremit",
        "fields": {
            "weather_type": ["Storm"],
            "key": "storm-001",
            "text": "Rain lashes down in sheets.",
            "weight": 2,
            "in_summer": True,
            "at_day": True,
        },
    },
    {
        "model": "weather.weatheremit",
        "fields": {
            "weather_type": ["Clear"],
            "key": "clear-001",
            "text": "The sky is a flawless blue.",
            "at_day": True,
        },
    },
]


class UpsertWeatherTypesTests(TestCase):
    def test_creates_then_updates(self) -> None:
        created, updated = upsert_weather_types(TYPES)
        assert (created, updated) == (2, 0)
        assert WeatherType.objects.count() == 2

        # Re-load identical data → all updates, no new rows.
        created, updated = upsert_weather_types(TYPES)
        assert (created, updated) == (0, 2)
        assert WeatherType.objects.count() == 2

    def test_edited_field_is_applied_on_reload(self) -> None:
        upsert_weather_types(TYPES)
        edited = [
            {"model": "weather.weathertype", "fields": {"name": "Storm", "selection_weight": 99}},
        ]
        created, updated = upsert_weather_types(edited)
        assert (created, updated) == (0, 1)
        assert WeatherType.objects.get(name="Storm").selection_weight == 99


class UpsertWeatherExposuresTests(TestCase):
    def setUp(self) -> None:
        upsert_weather_types(TYPES)

    def test_creates_then_updates_keyed_on_axis(self) -> None:
        created, updated = upsert_weather_type_exposures(EXPOSURES)
        assert (created, updated) == (2, 0)
        assert WeatherTypeExposure.objects.count() == 2

        created, updated = upsert_weather_type_exposures(EXPOSURES)
        assert (created, updated) == (0, 2)
        assert WeatherTypeExposure.objects.count() == 2

    def test_edited_magnitude_updates_in_place(self) -> None:
        upsert_weather_type_exposures(EXPOSURES)
        edited = [
            {
                "model": "weather.weathertypeexposure",
                "fields": {"weather_type": ["Storm"], "stat_key": StatKey.WET, "value": 10},
            },
        ]
        upsert_weather_type_exposures(edited)
        row = WeatherTypeExposure.objects.get(weather_type__name="Storm", stat_key=StatKey.WET)
        assert row.value == 10
        assert WeatherTypeExposure.objects.count() == 2  # no duplicate


class UpsertWeatherEmitsTests(TestCase):
    """The crux: the keyed emit rows loaddata duplicates must upsert by ``key`` (#2980)."""

    def setUp(self) -> None:
        upsert_weather_types(TYPES)

    def test_reload_does_not_duplicate_keyless_emits(self) -> None:
        created, updated, conflicts = upsert_weather_emits(EMITS)
        assert (created, updated) == (2, 0)
        assert conflicts == []
        assert WeatherEmit.objects.count() == 2

        # The bug under test: a second load must NOT create 2 more rows.
        created, updated, conflicts = upsert_weather_emits(EMITS)
        assert (created, updated) == (0, 2)
        assert conflicts == []
        assert WeatherEmit.objects.count() == 2

    def test_edited_emit_weight_and_flags_update_in_place(self) -> None:
        upsert_weather_emits(EMITS)
        edited = [
            {
                "model": "weather.weatheremit",
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-001",
                    "text": "Rain lashes down in sheets.",
                    "weight": 7,
                    "in_winter": True,
                    "at_night": True,
                },
            },
        ]
        upsert_weather_emits(edited)
        row = WeatherEmit.objects.get(key="storm-001")
        assert row.weight == 7
        assert row.in_winter is True
        assert row.at_night is True
        assert WeatherEmit.objects.count() == 2  # no duplicate

    def test_edited_text_updates_the_same_row_instead_of_forking(self) -> None:
        """The #2980 fix: rewriting the prose must update, not fork, the row it belongs to."""
        upsert_weather_emits(EMITS)
        rewritten = [
            {
                "model": "weather.weatheremit",
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-001",
                    "text": "A different line entirely.",
                },
            },
        ]
        created, updated, conflicts = upsert_weather_emits(rewritten)
        assert (created, updated) == (0, 1)
        assert conflicts == []
        assert WeatherEmit.objects.count() == 2  # no fork, no orphaned placeholder
        assert WeatherEmit.objects.get(key="storm-001").text == "A different line entirely."

    def test_new_key_creates_a_new_row(self) -> None:
        upsert_weather_emits(EMITS)
        new_line = [
            {
                "model": "weather.weatheremit",
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-002",
                    "text": "Thunder rolls overhead.",
                    "at_dusk": True,
                },
            },
        ]
        created, updated, conflicts = upsert_weather_emits(new_line)
        assert (created, updated) == (1, 0)
        assert conflicts == []
        assert WeatherEmit.objects.count() == 3


class UpsertWeatherEmitsCreditGuardTests(TestCase):
    """``WeatherEmit`` carries ``CreditedContent``: a credited row's content must survive a
    re-seed that would otherwise overwrite it (#3017), mirroring the fixture loader's guard.
    """

    def setUp(self) -> None:
        upsert_weather_types(TYPES)

    def test_credited_emit_with_differing_text_is_left_untouched(self) -> None:
        from world.contributors.factories import ContentContributorFactory

        contributor = ContentContributorFactory()
        credited = WeatherEmit.objects.create(
            weather_type=WeatherType.objects.get(name="Storm"),
            key="storm-001",
            text="A writer's polished line.",
            weight=5,
            written_by=contributor,
        )

        created, updated, conflicts = upsert_weather_emits(EMITS)

        credited.refresh_from_db()
        self.assertEqual(credited.text, "A writer's polished line.")
        self.assertEqual(credited.weight, 5)
        self.assertEqual((created, updated), (1, 0))  # only clear-001 was created
        self.assertEqual(len(conflicts), 1)
        self.assertIn("WeatherEmit [storm-001]", conflicts[0])
        self.assertIn("#3017", conflicts[0])

    def test_uncredited_emit_still_updates(self) -> None:
        uncredited = WeatherEmit.objects.create(
            weather_type=WeatherType.objects.get(name="Storm"),
            key="storm-001",
            text="A placeholder line.",
            weight=1,
        )

        created, updated, conflicts = upsert_weather_emits(EMITS)

        uncredited.refresh_from_db()
        self.assertEqual(uncredited.text, "Rain lashes down in sheets.")
        self.assertEqual((created, updated), (1, 1))
        self.assertEqual(conflicts, [])

    def test_identical_credited_emit_is_a_quiet_noop(self) -> None:
        from world.contributors.factories import ContentContributorFactory

        contributor = ContentContributorFactory()
        # Matches EMITS's storm-001 fixture row exactly (see module constant above).
        storm_text = "Rain lashes down in sheets."
        credited = WeatherEmit.objects.create(
            weather_type=WeatherType.objects.get(name="Storm"),
            key="storm-001",
            text=storm_text,
            weight=2,
            in_summer=True,
            at_day=True,
            written_by=contributor,
        )

        created, updated, conflicts = upsert_weather_emits(EMITS)

        credited.refresh_from_db()
        self.assertEqual(credited.text, storm_text)
        self.assertEqual((created, updated), (1, 1))  # storm-001 upserts, clear-001 creates
        self.assertEqual(conflicts, [])


class UpsertWeatherEmitsRawCreditFieldTests(TestCase):
    """A fixture row can itself carry credit fields (``written_by``/``reviewed_by`` as a
    natural-key list, e.g. ``["Apostate"]``) - the loader's own credit, distinct from the
    guard's comparison. This must resolve to a ``ContentContributor`` instance before the
    write, not pass the raw list straight into ``update_or_create``'s defaults (#3017
    review finding).
    """

    def setUp(self) -> None:
        upsert_weather_types(TYPES)

    def test_credited_row_with_differing_credit_freezes(self) -> None:
        """Content matches, but the fixture's ``written_by`` differs from the row's -
        the credit fields are part of the comparison for a credited row, so this is a
        differing-field conflict like any other and the row freezes untouched (#3017).
        """
        from world.contributors.factories import ContentContributorFactory

        old_contributor = ContentContributorFactory(name="Old Writer")
        new_contributor = ContentContributorFactory(name="New Writer")
        existing = WeatherEmit.objects.create(
            weather_type=WeatherType.objects.get(name="Storm"),
            key="storm-001",
            text="Rain lashes down in sheets.",
            weight=2,
            in_summer=True,
            at_day=True,
            written_by=old_contributor,
        )
        rows = [
            {
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-001",
                    "text": "Rain lashes down in sheets.",
                    "weight": 2,
                    "in_summer": True,
                    "at_day": True,
                    "written_by": [new_contributor.name],
                }
            }
        ]

        created, updated, conflicts = upsert_weather_emits(rows)

        existing.refresh_from_db()
        self.assertEqual((created, updated), (0, 0))
        self.assertEqual(len(conflicts), 1)
        self.assertIn("WeatherEmit [storm-001]", conflicts[0])
        self.assertEqual(existing.written_by, old_contributor)

    def test_credited_row_with_unresolvable_credit_and_matching_content_updates(self) -> None:
        """An unresolvable ``written_by`` is dropped before the comparison runs (#2980's
        drop-the-credit-never-the-row rule), so it is absent from the comparison entirely -
        a credited row whose other fields match still upserts rather than freezing on a
        phantom credit diff (#3017).
        """
        from world.contributors.factories import ContentContributorFactory

        old_contributor = ContentContributorFactory(name="Existing Writer")
        existing = WeatherEmit.objects.create(
            weather_type=WeatherType.objects.get(name="Storm"),
            key="storm-001",
            text="Rain lashes down in sheets.",
            weight=2,
            in_summer=True,
            at_day=True,
            written_by=old_contributor,
        )
        rows = [
            {
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-001",
                    "text": "Rain lashes down in sheets.",
                    "weight": 2,
                    "in_summer": True,
                    "at_day": True,
                    "written_by": ["Nobody By This Name"],
                }
            }
        ]

        created, updated, conflicts = upsert_weather_emits(rows)

        existing.refresh_from_db()
        self.assertEqual(conflicts, [])
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(existing.written_by, old_contributor)

    def test_credited_row_reasserting_same_credit_and_content_is_a_quiet_noop(self) -> None:
        """A routine reseed of an already-credited row - fixture re-asserts the SAME
        resolvable ``written_by`` natural key plus identical content - must not false-freeze
        under the widened comparison: no conflict, no change, the row upserts quietly.
        """
        from world.contributors.factories import ContentContributorFactory

        contributor = ContentContributorFactory(name="Steady Writer")
        existing = WeatherEmit.objects.create(
            weather_type=WeatherType.objects.get(name="Storm"),
            key="storm-001",
            text="Rain lashes down in sheets.",
            weight=2,
            in_summer=True,
            at_day=True,
            written_by=contributor,
        )
        rows = [
            {
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-001",
                    "text": "Rain lashes down in sheets.",
                    "weight": 2,
                    "in_summer": True,
                    "at_day": True,
                    "written_by": [contributor.name],
                }
            }
        ]

        created, updated, conflicts = upsert_weather_emits(rows)

        existing.refresh_from_db()
        self.assertEqual(conflicts, [])
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(existing.written_by, contributor)
        self.assertEqual(existing.text, "Rain lashes down in sheets.")

    def test_uncredited_row_receiving_fixture_credit_updates(self) -> None:
        """Scenario (b): an uncredited existing row receiving fixture credit values."""
        from world.contributors.factories import ContentContributorFactory

        contributor = ContentContributorFactory(name="First Credit")
        existing = WeatherEmit.objects.create(
            weather_type=WeatherType.objects.get(name="Storm"),
            key="storm-001",
            text="A placeholder line.",
            weight=1,
        )
        rows = [
            {
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-001",
                    "text": "Rain lashes down in sheets.",
                    "weight": 2,
                    "written_by": [contributor.name],
                }
            }
        ]

        created, updated, conflicts = upsert_weather_emits(rows)

        existing.refresh_from_db()
        self.assertEqual(conflicts, [])
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(existing.written_by, contributor)
        self.assertEqual(existing.text, "Rain lashes down in sheets.")

    def test_fresh_create_with_credit_field_resolves(self) -> None:
        """A brand-new row can carry a resolved credit straight from its first load."""
        from world.contributors.factories import ContentContributorFactory

        contributor = ContentContributorFactory(name="Fresh Writer")
        rows = [
            {
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-999",
                    "text": "A brand new line.",
                    "written_by": [contributor.name],
                }
            }
        ]

        created, updated, conflicts = upsert_weather_emits(rows)

        self.assertEqual(conflicts, [])
        self.assertEqual((created, updated), (1, 0))
        row = WeatherEmit.objects.get(key="storm-999")
        self.assertEqual(row.written_by, contributor)

    def test_unresolvable_credit_is_dropped_not_raised(self) -> None:
        """An unresolvable ``written_by`` drops the credit key rather than corrupting the
        row or raising (#2980's drop-the-credit-never-the-row rule).
        """
        rows = [
            {
                "fields": {
                    "weather_type": ["Storm"],
                    "key": "storm-998",
                    "text": "Another new line.",
                    "written_by": ["Nobody By This Name"],
                }
            }
        ]

        created, updated, conflicts = upsert_weather_emits(rows)

        self.assertEqual(conflicts, [])
        self.assertEqual((created, updated), (1, 0))
        row = WeatherEmit.objects.get(key="storm-998")
        self.assertIsNone(row.written_by)


class WeatherEmitKeyIdentityTests(TestCase):
    """A rewritten emit updates its row instead of forking a new one (#2980)."""

    def test_natural_key_is_the_key_not_the_text(self):
        self.assertEqual(WeatherEmit.identity_fields(), ["key"])

    def test_rewriting_the_text_updates_in_place(self):
        weather_type = WeatherTypeFactory(name="Stormy")
        rows = [
            {
                "fields": {
                    "weather_type": ["Stormy"],
                    "key": "stormy-001",
                    "text": "PLACEHOLDER: rain.",
                    "weight": 10,
                }
            }
        ]
        created, updated, conflicts = upsert_weather_emits(rows)
        self.assertEqual((created, updated), (1, 0))
        self.assertEqual(conflicts, [])

        rows[0]["fields"]["text"] = "Thunder walks the rooftops."
        created, updated, conflicts = upsert_weather_emits(rows)
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(conflicts, [])
        self.assertEqual(WeatherEmit.objects.filter(weather_type=weather_type).count(), 1)
        self.assertEqual(
            WeatherEmit.objects.get(key="stormy-001").text,
            "Thunder walks the rooftops.",
        )

    def test_a_new_key_creates_a_new_row(self):
        WeatherTypeFactory(name="Stormy")
        upsert_weather_emits(
            [{"fields": {"weather_type": ["Stormy"], "key": "stormy-001", "text": "One."}}]
        )
        created, _updated, _conflicts = upsert_weather_emits(
            [{"fields": {"weather_type": ["Stormy"], "key": "stormy-002", "text": "Two."}}]
        )
        self.assertEqual(created, 1)


class LoadWeatherSeedFromDirTests(TestCase):
    """The orchestrator reads the fixture files in dependency order and upserts idempotently."""

    def _write_corpus(self, tmp_path) -> None:
        (tmp_path / "weather_types.json").write_text(json.dumps(TYPES), encoding="utf-8")
        (tmp_path / "weather_type_exposures.json").write_text(
            json.dumps(EXPOSURES), encoding="utf-8"
        )
        (tmp_path / "weather_emits.json").write_text(json.dumps(EMITS), encoding="utf-8")
        (tmp_path / "feast_days.json").write_text(
            json.dumps(
                [
                    {
                        "model": "weather.feastday",
                        "fields": {
                            "name": "Eclipse",
                            "ic_month": 10,
                            "ic_day": 31,
                            "weather_type": ["Clear"],
                        },
                    }
                ]
            ),
            encoding="utf-8",
        )

    def test_loads_then_reloads_idempotently(self) -> None:
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._write_corpus(tmp_path)

            counts, conflicts = load_weather_seed(tmp_path)
            assert counts["weather_types"] == (2, 0)
            assert counts["weather_type_exposures"] == (2, 0)
            assert counts["weather_emits"] == (2, 0)
            assert counts["feast_days"] == (1, 0)
            assert conflicts == []
            assert WeatherType.objects.count() == 2
            assert WeatherEmit.objects.count() == 2
            assert FeastDay.objects.count() == 1

            # Re-seed: everything updates, nothing duplicates.
            counts, conflicts = load_weather_seed(tmp_path)
            assert counts["weather_emits"] == (0, 2)
            assert counts["feast_days"] == (0, 1)
            assert conflicts == []
            assert WeatherEmit.objects.count() == 2
            assert FeastDay.objects.count() == 1

    def test_missing_feast_days_file_is_ok(self) -> None:
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "weather_types.json").write_text(json.dumps(TYPES), encoding="utf-8")
            counts, conflicts = load_weather_seed(tmp_path)
            assert counts["weather_types"] == (2, 0)
            assert counts["feast_days"] == (0, 0)
            assert conflicts == []
            assert FeastDay.objects.count() == 0
