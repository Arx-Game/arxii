"""The destroyed_at-writes linter flags a hand-rolled soft-delete and honours a reasoned
suppression (#4099)."""

from pathlib import Path

from lint_destroyed_at_writes import check_file, check_source


def test_attribute_assignment_is_flagged():
    source = "def recycle(item):\n    item.destroyed_at = now()\n    item.save()\n"
    assert check_source(source) == [(2, 4)]


def test_update_and_create_keywords_are_flagged():
    source = (
        "ItemInstance.objects.filter(pk=1).update(destroyed_at=now())\n"
        "ItemInstance.objects.create(template=t, destroyed_at=None)\n"
    )
    assert [line for line, _ in check_source(source)] == [1, 2]


def test_reading_and_filtering_pass():
    source = (
        "if item.destroyed_at is not None:\n"
        "    pass\n"
        "ItemInstance.objects.filter(destroyed_at__isnull=True)\n"
        "rows = ItemInstance.objects.in_play().filter(destroyed_at=None)\n"
    )
    assert check_source(source) == []


def test_suppression_needs_a_reason():
    with_reason = "item.destroyed_at = None  # noqa: DESTROYED_AT undelete by staff tool\n"
    bare = "item.destroyed_at = None  # noqa: DESTROYED_AT\n"
    assert check_source(with_reason) == []
    assert check_source(bare) == [(1, 0)]


def test_the_canonical_module_is_allowed(tmp_path: Path):
    canonical = tmp_path / "world" / "items" / "services" / "usage.py"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("item.destroyed_at = now()\n")
    elsewhere = tmp_path / "world" / "items" / "services" / "recycle.py"
    elsewhere.write_text("item.destroyed_at = now()\n")
    assert check_file(canonical) == []
    assert check_file(elsewhere) == [(1, 0)]
