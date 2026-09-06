"""Auto-through ManyToManyFields inline into their owner's CreateModel like FKs do
(ADR-0276): CreateModel creates the through table itself, so the only ordering
need is target-before-owner, which the topological order already provides.
Explicit ``through=`` models and back edges of a cycle stay deferred."""

from __future__ import annotations

import ast

from optimize_initial_migration import rewrite

HEADER = (
    "from django.db import migrations, models\n\n\n"
    "class Migration(migrations.Migration):\n    operations = [\n"
)
FOOTER = "    ]\n"


def _src(*ops: str) -> str:
    return HEADER + "".join(f"        {op},\n" for op in ops) + FOOTER


def _model(name: str) -> str:
    return (
        f'migrations.CreateModel(name="{name}", '
        'fields=[("id", models.AutoField(primary_key=True))])'
    )


def _m2m(owner: str, field: str, target: str, through: str | None = None) -> str:
    extra = f', through="arxii.{through}"' if through else ""
    return (
        f'migrations.AddField(model_name="{owner}", name="{field}", '
        f'field=models.ManyToManyField(to="arxii.{target}"{extra}))'
    )


def _fk(owner: str, field: str, target: str) -> str:
    return (
        f'migrations.AddField(model_name="{owner}", name="{field}", '
        f'field=models.ForeignKey(to="arxii.{target}", on_delete=models.CASCADE))'
    )


def _create_model_fields(source: str, name: str) -> set[str]:
    for node in ast.walk(ast.parse(source)):
        is_create = isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        if is_create and node.func.attr == "CreateModel":
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            if ast.literal_eval(kwargs["name"]) == name:
                return {ast.literal_eval(entry.elts[0]) for entry in kwargs["fields"].elts}
    message = f"no CreateModel {name}"
    raise AssertionError(message)


def test_auto_through_m2m_to_an_earlier_model_inlines():
    src = _src(_model("A"), _model("B"), _m2m("b", "friends", "a"))
    out, stats = rewrite(src, check_only=False)
    assert "AddField" not in out
    assert "friends" in _create_model_fields(out, "B")
    assert stats["deferred_addfield_m2m"] == 0
    assert stats["inlined_m2m"] == 1


def test_explicit_through_m2m_stays_deferred():
    src = _src(
        _model("A"),
        _model("B"),
        _model("Link"),
        _fk("link", "a", "a"),
        _fk("link", "b", "b"),
        _m2m("b", "linked", "a", through="Link"),
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddField" in out
    assert "linked" not in _create_model_fields(out, "B")
    assert stats["deferred_addfield_m2m"] == 1


def test_self_referential_m2m_inlines():
    src = _src(_model("A"), _m2m("a", "peers", "a"))
    out, stats = rewrite(src, check_only=False)
    assert "AddField" not in out
    assert stats["inlined_m2m"] == 1


def test_m2m_back_edge_of_a_cycle_stays_deferred():
    # A -FK-> B and B -M2M-> A form a cycle; exactly one of the two edges is deferred.
    src = _src(_model("A"), _model("B"), _fk("a", "b", "b"), _m2m("b", "tags", "a"))
    out, stats = rewrite(src, check_only=False)
    assert out.count("AddField(") == 1
    assert stats["deferred_addfield_cycle"] + stats["deferred_addfield_m2m"] == 1


def test_external_target_m2m_inlines():
    src = _src(
        _model("A"),
        'migrations.AddField(model_name="a", name="groups", '
        'field=models.ManyToManyField(to="auth.group"))',
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddField" not in out
    assert stats["inlined_m2m"] == 1
