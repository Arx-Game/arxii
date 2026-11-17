"""The data migration that carries per-gift substance rows onto shared ``Substance`` rows (#5125).

The migration function is called against the live app registry while the legacy
``GiftSubstance`` model still exists. The module is found by its name without its number, so
the number can move when the migration is renumbered after another one lands first. (The
SQLite test tier runs with migrations disabled, so the migration is not applied by the test
database.)
"""

from contextlib import redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
import io
from pathlib import Path

from django.apps import apps
from django.test import TestCase

from world.contributors.factories import ContentContributorFactory
from world.locations.constants import StatKey
from world.locations.factories import LocationValueModifierFactory
from world.locations.models import LocationValueModifier
from world.magic.constants import GiftKind, SubstanceDirection
from world.magic.factories import GiftFactory, PrimumStepFactory
from world.magic.models import GiftSubstance, PrimumStep, Substance, SubstancePowerStep
from world.mechanics.factories import PropertyFactory


def _load_migration():
    here = Path(__file__).resolve().parents[2] / "migrations"
    (path,) = here.glob("*_substances_carry_gift_rows.py")
    spec = spec_from_file_location("substances_carry_gift_rows_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load_migration()


def _carry() -> str:
    """Run the migration's function and answer what it printed."""
    out = io.StringIO()
    with redirect_stdout(out):
        MIGRATION.carry_gift_substances(apps, None)
    return out.getvalue()


def _legacy(gift, label="Water", stat_key=StatKey.WET, direction=SubstanceDirection.RISING, **kw):
    kw.setdefault("arrival_line", "The room changes.")
    return GiftSubstance.objects.create(
        gift=gift, label=label, stat_key=stat_key, direction=direction, **kw
    )


class CarryGiftSubstancesTests(TestCase):
    def test_two_gifts_same_label_merge_into_one_substance(self) -> None:
        writer = ContentContributorFactory()
        first = GiftFactory(name="Tide Caller")
        second = GiftFactory(name="Wave Rider")
        _legacy(first, label=" Water ")
        _legacy(second, label="water", written_by=writer)

        _carry()

        substance = Substance.objects.get()
        self.assertEqual(substance.name, "Water")
        self.assertEqual((substance.stat_key, substance.direction), ("wet", "rising"))
        self.assertEqual(substance.written_by_id, writer.pk)
        for gift in (first, second):
            gift.refresh_from_db()
            self.assertEqual(gift.substance_id, substance.pk)

    def test_same_label_different_reading_appends_gift_name(self) -> None:
        wet = GiftFactory(name="Tide Caller")
        dry = GiftFactory(name="Drought Bringer")
        _legacy(dry, label="Water", stat_key=StatKey.DRY)
        _legacy(wet, label="Water")

        _carry()

        names = set(Substance.objects.values_list("name", flat=True))
        self.assertEqual(names, {"Water", "Water (Tide Caller)"})
        wet.refresh_from_db()
        dry.refresh_from_db()
        self.assertEqual(dry.substance.name, "Water")
        self.assertEqual(wet.substance.name, "Water (Tide Caller)")

    def test_minor_gift_row_is_skipped_not_failed(self) -> None:
        minor = GiftFactory(name="Small Trick", kind=GiftKind.MINOR)
        _legacy(minor, label="Smoke")

        printed = _carry()

        minor.refresh_from_db()
        self.assertIsNone(minor.substance_id)
        self.assertFalse(Substance.objects.exists())
        self.assertIn("Small Trick", printed)

    def test_property_carries_first_non_null_per_group(self) -> None:
        first_property = PropertyFactory(name="wet-thing")
        other_property = PropertyFactory(name="drenched-thing")
        _legacy(GiftFactory(name="A Gift"))
        _legacy(GiftFactory(name="B Gift"), property=first_property)
        _legacy(GiftFactory(name="C Gift"), property=other_property)

        printed = _carry()

        self.assertEqual(Substance.objects.get().property_id, first_property.pk)
        self.assertIn("wet-thing", printed)
        self.assertIn("drenched-thing", printed)

    def test_transient_call_up_rows_deleted(self) -> None:
        for source in ("substance:12", "scene_mark:3:4"):
            LocationValueModifierFactory(on_room=True, source=source)
        kept = LocationValueModifierFactory(on_room=True, source="weather:rain")

        _carry()

        self.assertEqual(list(LocationValueModifier.objects.all()), [kept])

    def test_starter_steps_and_curve_inserted_once(self) -> None:
        _carry()
        _carry()
        self.assertEqual(
            list(PrimumStep.objects.values_list("rank", "name", "starts_at", "points")),
            [(1, "Trace", 1, 2), (2, "Some", 10, 4), (3, "Rich", 30, 7), (4, "Massive", 100, 10)],
        )
        self.assertEqual(SubstancePowerStep.objects.count(), 6)

    def test_staff_rows_already_present_are_not_overwritten(self) -> None:
        PrimumStepFactory(rank=1, name="Whisper", starts_at=5, points=1)
        SubstancePowerStep.objects.create(points_reached=3, power=9)

        _carry()

        self.assertEqual(
            list(PrimumStep.objects.values_list("name", "starts_at", "points")),
            [("Whisper", 5, 1)],
        )
        self.assertEqual(list(SubstancePowerStep.objects.values_list("power", flat=True)), [9])


class CarrySummaryTests(TestCase):
    def test_child_left_null_gaps_listed_and_discarded_values_printed(self) -> None:
        parent = GiftFactory(name="Parent Gift")
        child = GiftFactory(name="Child Gift", parent=parent)
        GiftFactory(name="Orphan Gift")
        _legacy(parent, full_at=7, opposed_by=StatKey.DRY, arrival_line="The water rises, quiet.")

        printed = _carry()

        child.refresh_from_db()
        self.assertIsNone(child.substance_id)
        gap_line = next(ln for ln in printed.splitlines() if "no ancestor" in ln)
        self.assertIn("Orphan Gift", gap_line)
        self.assertNotIn("Child Gift", gap_line)
        self.assertNotIn("Parent Gift", gap_line)
        self.assertIn("'Parent Gift', 7, 'dry', 'The water rises, quiet.'", printed)
