"""Generation-stamped chunks carry ``replaces`` and can never share a name with an
older generation (ADR-0272). ``generation=None`` keeps the #2906 shape byte-for-byte."""

from __future__ import annotations

import ast

from optimize_initial_migration import chunk_name, rewrite_chunks

INITIAL = """from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(name="A", fields=[("id", models.AutoField(primary_key=True))]),
        migrations.CreateModel(name="B", fields=[("id", models.AutoField(primary_key=True))]),
        migrations.AddField(
            model_name="b",
            name="a",
            field=models.ForeignKey(to="arxii.a", on_delete=models.CASCADE),
        ),
    ]
"""


def _migration_class(source: str) -> ast.ClassDef:
    tree = ast.parse(source)
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Migration")


def _assigned(cls: ast.ClassDef, name: str) -> ast.expr | None:
    for node in cls.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
    return None


def test_chunk_names_are_stamped_with_the_generation():
    assert chunk_name(2, 1) == "0001_g2_initial"
    assert chunk_name(2, 37) == "0037_g2_part_37"
    assert chunk_name(None, 1) == "0001_initial"
    assert chunk_name(None, 37) == "0037_initial_part_37"


def test_every_stamped_file_replaces_its_slice_of_the_previous_generation():
    files, _stats = rewrite_chunks(INITIAL, n_chunks=2, generation=2, replaces_total=5)
    assert [name for name, _ in files] == ["0001_g2_initial", "0002_g2_part_2"]
    for index, (_name, content) in enumerate(files, start=1):
        assert "from world.migrations._generations import replaced_slice" in content
        replaces = _assigned(_migration_class(content), "replaces")
        assert isinstance(replaces, ast.Call)
        assert ast.unparse(replaces) == f"replaced_slice({index}, 5)"


_A_TO_B = (
    "        migrations.AddField(\n"
    '            model_name="a",\n'
    '            name="b",\n'
    '            field=models.ForeignKey(to="arxii.b", on_delete=models.CASCADE),\n'
    "        ),\n"
)
# Insert into the operations list (the last "    ]" in the source), not into dependencies.
CYCLIC = INITIAL.rsplit("    ]\n", 1)[0] + _A_TO_B + "    ]\n"


def test_pure_create_model_chunks_use_the_batched_base():
    # A <-> B is a cycle, so one FK stays a deferred AddField and lands in chunk 2.
    files, stats = rewrite_chunks(CYCLIC, n_chunks=2, generation=2)
    assert stats["deferred_addfield_cycle"] == 1
    first, second = (_migration_class(content) for _name, content in files)
    assert ast.unparse(first.bases[0]) == "BatchedCreateModelMigration"
    assert (
        "from core_management.batched_migration import BatchedCreateModelMigration" in files[0][1]
    )
    assert ast.unparse(second.bases[0]) == "migrations.Migration"
    assert "BatchedCreateModelMigration" not in files[1][1]


def test_first_chunk_keeps_initial_and_original_dependencies():
    files, _stats = rewrite_chunks(INITIAL, n_chunks=2, generation=2)
    first = _migration_class(files[0][1])
    initial = _assigned(first, "initial")
    assert isinstance(initial, ast.Constant)
    assert initial.value is True
    deps = _assigned(first, "dependencies")
    assert deps is not None
    assert "swappable_dependency" in ast.unparse(deps)
    second = _migration_class(files[1][1])
    second_deps = _assigned(second, "dependencies")
    assert second_deps is not None
    assert ast.unparse(second_deps) == "[('arxii', '0001_g2_initial')]"


def test_unstamped_output_is_unchanged():
    files, _stats = rewrite_chunks(INITIAL, n_chunks=2, generation=None)
    assert [name for name, _ in files] == ["0001_initial", "0002_initial_part_2"]
    assert "replaced_slice" not in files[0][1]
    assert "Batched" not in files[0][1]
    assert "replaced_slice" not in files[1][1]
