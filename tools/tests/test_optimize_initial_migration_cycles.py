"""Inside a genuine FK cycle only the back edges of a good member order are deferred,
not every edge (ADR-0272). A 3-cycle needs one deferred FK, not three."""

from __future__ import annotations

import ast

from optimize_initial_migration import order_within_cycle, rewrite

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


def _fk(owner: str, field: str, target: str) -> str:
    return (
        f'migrations.AddField(model_name="{owner}", name="{field}", '
        f'field=models.ForeignKey(to="arxii.{target}", on_delete=models.CASCADE))'
    )


def _create_order(source: str) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(source)):
        is_create = isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        if is_create and node.func.attr == "CreateModel":
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            names.append(ast.literal_eval(kwargs["name"]))
    return names


def _deferred_fields(source: str) -> set[tuple[str, str]]:
    found = set()
    for node in ast.walk(ast.parse(source)):
        is_add = isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        if is_add and node.func.attr == "AddField":
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            found.add((ast.literal_eval(kwargs["model_name"]), ast.literal_eval(kwargs["name"])))
    return found


def test_three_cycle_defers_exactly_one_edge():
    src = _src(
        _model("A"),
        _model("B"),
        _model("C"),
        _fk("a", "b", "b"),
        _fk("b", "c", "c"),
        _fk("c", "a", "a"),
    )
    out, stats = rewrite(src, check_only=False)
    assert stats["deferred_addfield_cycle"] == 1
    assert stats["inlined_total"] == 2
    assert len(_deferred_fields(out)) == 1


def test_two_cycle_defers_exactly_one_edge():
    src = _src(_model("A"), _model("B"), _fk("a", "b", "b"), _fk("b", "a", "a"))
    _out, stats = rewrite(src, check_only=False)
    assert stats["deferred_addfield_cycle"] == 1


def test_inlined_cycle_edges_point_at_models_created_earlier():
    # Every inlined FK inside the cycle must target a model that precedes its owner.
    src = _src(
        _model("A"),
        _model("B"),
        _model("C"),
        _model("D"),
        _fk("a", "b", "b"),
        _fk("b", "c", "c"),
        _fk("c", "a", "a"),
        _fk("c", "d", "d"),
        _fk("d", "b", "b"),
    )
    out, stats = rewrite(src, check_only=False)
    order = _create_order(out)
    deferred = _deferred_fields(out)
    edges = {("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "b")}
    for owner, target in edges:
        if (owner, owner_field(owner, target)) in deferred:
            continue
        assert order.index(target.upper()) < order.index(owner.upper()), (owner, target)
    assert stats["deferred_addfield_cycle"] <= 2


def owner_field(owner: str, target: str) -> str:
    return target  # fields are named after their target in these fixtures


def test_order_within_cycle_prefers_sources_first_and_sinks_last():
    # "before" edges: a must precede b, b must precede c; c -> a is the one back edge.
    members = ["a", "b", "c"]
    before = {("a", "b"), ("b", "c"), ("c", "a")}
    order = order_within_cycle(members, before)
    assert set(order) == set(members)
    back = [(u, v) for (u, v) in before if order.index(u) > order.index(v)]
    assert len(back) == 1


def test_cycle_free_input_is_unchanged():
    src = _src(_model("A"), _model("B"), _fk("b", "a", "a"))
    _out, stats = rewrite(src, check_only=False)
    assert stats["deferred_addfield_cycle"] == 0
    assert stats["sccs_non_trivial"] == 0
