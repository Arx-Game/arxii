"""Pending destructive migrations must not outrun the running server."""

from check_release_safety import check_migration, unsafe_operations
from django.db import migrations, models


class PendingMigration:
    app_label = "arxii"
    name = "0425_remove_old_field"

    def __init__(self, *ops):
        self.operations = list(ops)


OLD = "a" * 40
NEW = "b" * 40


def test_observed_removed_column_is_rejected_without_review():
    pending = PendingMigration(migrations.RemoveField("conditiontemplate", "cure_difficulty"))
    assert "RemoveField" in check_migration(pending, "", OLD, lambda *_: False)


def test_contract_waits_until_compatibility_commit_is_in_running_release():
    pending = PendingMigration(migrations.RemoveField("conditiontemplate", "cure_difficulty"))
    declaration = f"# release-safety: contract {NEW}\n"
    assert "not in the running server revision" in check_migration(
        pending, declaration, OLD, lambda *_: False
    )
    assert check_migration(pending, declaration, NEW, lambda *_: True) is None


def test_destructive_operation_cannot_be_declared_expand():
    pending = PendingMigration(migrations.RemoveField("thing", "field"))
    assert "cannot be expand" in check_migration(
        pending, f"# release-safety: expand {OLD}\n", OLD, lambda *_: True
    )


def test_safe_nullable_addition_does_not_need_a_marker():
    pending = PendingMigration(migrations.AddField("thing", "new", models.IntegerField(null=True)))
    assert unsafe_operations(pending) == []
    assert check_migration(pending, "", OLD, lambda *_: False) is None


def test_nonnullable_addition_and_opaque_operations_need_review():
    pending = PendingMigration(
        migrations.AddField("thing", "new", models.IntegerField(default=1)),
        migrations.RunSQL("DROP TABLE thing"),
    )
    assert unsafe_operations(pending) == ["AddField", "RunSQL"]
    assert check_migration(pending, "", OLD, lambda *_: False) is not None


def test_database_state_wrapper_cannot_hide_destructive_sql():
    pending = PendingMigration(
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL("DROP TABLE thing")]
        )
    )
    assert check_migration(pending, "", OLD, lambda *_: False) is not None


def test_incident_migration_is_rejected_against_old_server():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "src/world/migrations/0425_difficulty_levels_batch1_remove.py"
    )
    spec = importlib.util.spec_from_file_location("incident_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pending = module.Migration("0425_difficulty_levels_batch1_remove", "arxii")
    failure = check_migration(pending, path.read_text(), OLD, lambda *_: False)
    assert "RemoveField" in failure


def test_entrypoint_blocks_actual_incident_in_pending_plan(monkeypatch, capsys):
    import importlib.util
    from pathlib import Path
    import sys

    import check_release_safety

    path = (
        Path(__file__).resolve().parents[2]
        / "src/world/migrations/0425_difficulty_levels_batch1_remove.py"
    )
    spec = importlib.util.spec_from_file_location("incident_migration_for_plan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setitem(sys.modules, spec.name, module)
    pending = module.Migration("0425_difficulty_levels_batch1_remove", "arxii")

    class Graph:
        def leaf_nodes(self):
            return [("arxii", pending.name)]

    class Loader:
        graph = Graph()

    class Executor:
        loader = Loader()

        def __init__(self, _connection):
            pass

        def migration_plan(self, _targets):
            return [(pending, False)]

    monkeypatch.setattr(check_release_safety.django, "setup", lambda: None)
    monkeypatch.setattr(check_release_safety, "MigrationExecutor", Executor)
    monkeypatch.setattr(sys, "argv", ["check_release_safety.py", OLD])

    assert check_release_safety.main() == 1
    assert "0425_difficulty_levels_batch1_remove" in capsys.readouterr().err


def test_deployment_gate_runs_before_database_migration():
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[2] / "infra/ansible/roles/app_deploy/tasks/main.yml"
    tasks = yaml.safe_load(path.read_text())
    names = [task.get("name") for task in tasks]
    gate = names.index("Check pending migrations against the last running server")
    migration = names.index("Apply Django/Evennia DB migrations (idempotent on every deploy)")
    assert gate < migration
    assert "check_release_safety.py" in tasks[gate]["ansible.builtin.shell"]
    assert "app_safety_reload_stamp.stat.exists" in tasks[gate]["when"]


def test_deployment_gate_refuses_only_when_enforcement_is_on():
    """During alpha the check reports and the deploy carries on (#5183)."""
    from pathlib import Path

    import yaml

    role = Path(__file__).resolve().parents[2] / "infra/ansible/roles/app_deploy"
    tasks = yaml.safe_load((role / "tasks/main.yml").read_text())
    defaults = yaml.safe_load((role / "defaults/main.yml").read_text())
    names = [task.get("name") for task in tasks]
    gate = tasks[names.index("Check pending migrations against the last running server")]
    report = names.index("Report migrations the compatibility check flagged (not enforced)")
    migration = names.index("Apply Django/Evennia DB migrations (idempotent on every deploy)")

    assert defaults["app_release_safety_enforce"] is False
    assert gate["failed_when"] == [
        "app_release_safety_enforce | bool",
        "app_release_safety.rc != 0",
    ]
    assert report < migration
    assert "not (app_release_safety_enforce | bool)" in tasks[report]["when"]


def test_nested_remove_field_cannot_be_declared_expand():
    pending = PendingMigration(
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RemoveField("thing", "field")]
        )
    )
    assert "cannot be expand" in check_migration(
        pending, f"# release-safety: expand {OLD}\n", OLD, lambda *_: True
    )


def test_custom_operations_are_not_assumed_safe():
    class CustomCreate(migrations.CreateModel):
        pass

    pending = PendingMigration(CustomCreate("Thing", fields=[]))
    assert unsafe_operations(pending) == ["CustomCreate"]
