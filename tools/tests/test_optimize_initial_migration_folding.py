"""Constraints, indexes and unique_together fold into their model's CreateModel options
unless they reference a field that is still deferred (ADR-0272, spec #3656 Design 2).

Each folded operation is one fewer full-cost step in the replay; anything the
resolver cannot prove safe stays in the tail, after the deferred AddFields.
"""

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


def _create_model_options(source: str, name: str) -> dict[str, str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        is_create = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "CreateModel"
        )
        if is_create:
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            if ast.literal_eval(kwargs["name"]) == name:
                options = kwargs.get("options")
                if options is None:
                    return {}
                assert isinstance(options, ast.Dict)
                return {
                    ast.literal_eval(k): ast.unparse(v)
                    for k, v in zip(options.keys, options.values, strict=True)
                    if k is not None
                }
    message = f"no CreateModel {name}"
    raise AssertionError(message)


A = (
    'migrations.CreateModel(name="A", fields=[("id", models.AutoField(primary_key=True)), '
    '("x", models.IntegerField()), ("created", models.DateTimeField())])'
)
A_BARE = 'migrations.CreateModel(name="A", fields=[("id", models.AutoField(primary_key=True))])'
B = 'migrations.CreateModel(name="B", fields=[("id", models.AutoField(primary_key=True))])'
B_TO_A = (
    'migrations.AddField(model_name="b", name="a", '
    'field=models.ForeignKey(to="arxii.a", on_delete=models.CASCADE))'
)
A_TO_B = (
    'migrations.AddField(model_name="a", name="b", '
    'field=models.ForeignKey(to="arxii.b", on_delete=models.CASCADE))'
)


def test_unique_constraint_on_own_fields_folds_into_options():
    src = _src(
        A,
        'migrations.AddConstraint(model_name="a", '
        'constraint=models.UniqueConstraint(fields=("x",), name="uniq_x"))',
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddConstraint" not in out
    assert "UniqueConstraint" in _create_model_options(out, "A")["constraints"]
    assert stats["tail_ops_folded"] == 1
    assert stats["tail_ops"] == 0


def test_index_with_descending_field_folds():
    src = _src(
        A,
        'migrations.AddIndex(model_name="a", '
        'index=models.Index(fields=["-created"], name="a_created_idx"))',
    )
    out, _stats = rewrite(src, check_only=False)
    assert "AddIndex" not in out
    assert "a_created_idx" in _create_model_options(out, "A")["indexes"]


def test_check_constraint_with_lookup_folds():
    src = _src(
        A,
        'migrations.AddConstraint(model_name="a", '
        'constraint=models.CheckConstraint(condition=models.Q(x__gte=0), name="x_nonneg"))',
    )
    out, _stats = rewrite(src, check_only=False)
    assert "AddConstraint" not in out


def test_unique_together_folds():
    src = _src(A, 'migrations.AlterUniqueTogether(name="a", unique_together={("x", "created")})')
    out, _stats = rewrite(src, check_only=False)
    assert "AlterUniqueTogether" not in out
    assert "unique_together" in _create_model_options(out, "A")


def test_existing_options_are_extended_not_replaced():
    a = (
        'migrations.CreateModel(name="A", fields=[("id", models.AutoField(primary_key=True)), '
        '("x", models.IntegerField())], options={"ordering": ["x"]})'
    )
    src = _src(
        a,
        'migrations.AddConstraint(model_name="a", '
        'constraint=models.UniqueConstraint(fields=("x",), name="uniq_x"))',
    )
    out, _stats = rewrite(src, check_only=False)
    options = _create_model_options(out, "A")
    assert options["ordering"] == "['x']"
    assert "uniq_x" in options["constraints"]


def test_constraint_on_deferred_cycle_field_stays_in_tail():
    # A <-> B is a genuine cycle. The cycle order creates A first, so b.a inlines and
    # a.b is the one deferred FK; a constraint on a.b must follow that AddField.
    src = _src(
        A_BARE,
        B,
        A_TO_B,
        B_TO_A,
        'migrations.AddConstraint(model_name="a", '
        'constraint=models.UniqueConstraint(fields=("b",), name="uniq_a_b"))',
    )
    out, stats = rewrite(src, check_only=False)
    assert stats["deferred_addfield_cycle"] == 1
    assert "AddConstraint" in out
    assert out.index("AddField") < out.index("AddConstraint")
    assert stats["tail_ops_folded"] == 0
    assert stats["tail_ops"] == 1


def test_unresolvable_expression_index_stays_in_tail():
    src = _src(
        A,
        'migrations.AddIndex(model_name="a", '
        'index=models.Index(models.functions.Lower("x"), name="a_lower_x"))',
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddIndex" in out
    assert stats["tail_ops_folded"] == 0


def test_constraint_on_unknown_field_stays_in_tail():
    src = _src(
        A,
        'migrations.AddConstraint(model_name="a", '
        'constraint=models.UniqueConstraint(fields=("nope",), name="uniq_nope"))',
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddConstraint" in out
    assert stats["tail_ops_folded"] == 0


def test_inlined_fk_counts_as_present_for_folding():
    # B -> A only (no cycle): b.a is inlined into CreateModel(B), so a constraint on it folds.
    src = _src(
        A,
        B,
        B_TO_A,
        'migrations.AddConstraint(model_name="b", '
        'constraint=models.UniqueConstraint(fields=("a",), name="uniq_b_a"))',
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddConstraint" not in out
    assert stats["tail_ops_folded"] == 1


def test_writer_form_q_with_tuples_nesting_and_f_folds():
    # Exactly how Django's migration writer serializes Q(status="x") | ~Q(x__gt=F("created")).
    src = _src(
        A,
        'migrations.AddConstraint(model_name="a", constraint=models.CheckConstraint('
        "condition=models.Q(models.Q(('x', 1)), models.Q(('x__gt', models.F('created')), "
        "_negated=True), _connector='OR'), name=\"writer_form\"))",
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddConstraint" not in out
    assert stats["tail_ops_folded"] == 1


def test_writer_form_q_referencing_unknown_field_stays_in_tail():
    src = _src(
        A,
        'migrations.AddConstraint(model_name="a", constraint=models.CheckConstraint('
        "condition=models.Q(('nope__isnull', False)), name=\"unknown\"))",
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddConstraint" in out
    assert stats["tail_ops_folded"] == 0


def test_conditional_unique_constraint_in_writer_form_folds():
    src = _src(
        A,
        'migrations.AddConstraint(model_name="a", constraint=models.UniqueConstraint('
        "condition=models.Q(('x', 1)), fields=('created',), name=\"cond_uniq\"))",
    )
    out, stats = rewrite(src, check_only=False)
    assert "AddConstraint" not in out
    assert stats["tail_ops_folded"] == 1
