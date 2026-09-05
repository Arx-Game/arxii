"""Rewrite ``world/migrations/0001_initial.py`` into topological order.

Why this exists (#2906, Task 9)
--------------------------------
The single-app collapse (#2906) squashed every former ``world.*`` sub-app into
one ``arxii`` app with one 1,026-model ``CreateModel`` migration. Django's
``makemigrations`` autodetector is conservative about foreign-key ordering: the
instant it finds *any* circular dependency anywhere in the model graph, it
defers *every* forward-referencing FK/O2O field to a separate ``AddField`` op
that runs after all ``CreateModel`` ops, rather than doing the (harder) work of
figuring out which references are genuinely part of a cycle. Across 1,026
models that produced 2,321 deferred ``AddField`` operations.

Each ``AddField`` operation mutates Django's in-memory ``ProjectState`` and
triggers ``reload_model()``, which re-renders the state's related-object graph
closure. With 1,026 models living in a single app, that closure is enormous,
so 2,321 redundant reloads is the dominant cost of a fresh ``migrate`` on this
migration.

A direct analysis of the FK graph (see the SCC computation below) found the
model graph is very nearly a DAG: of 1,026 models and ~2,400 intra-app FK
edges, only 5 genuine cycles exist (32 models total, largest cycle 21 models),
and only the FK edges *inside* those cycles (~49 of them) actually require
deferral. Everything else can be inlined directly into its model's
``CreateModel`` if models are created in topological (dependency-respecting)
order instead of Django's arbitrary autodetector order.

This script performs that rewrite:

1. Parse ``0001_initial.py`` with the ``ast`` module (it is machine-generated
   and syntactically regular, so AST parsing is reliable and exact — no
   regexes over Python source).
2. Build a directed graph over intra-app models: edge ``owner -> target`` for
   every non-self-referential ``ForeignKey``/``OneToOneField`` field (both the
   ones already inline in a ``CreateModel`` and the ones Django deferred to
   ``AddField``).
3. Compute strongly connected components (Tarjan's algorithm) and condense the
   graph into a DAG of SCCs.
4. Topologically sort the condensation (Kahn's algorithm, tie-broken by
   original file order for a stable, minimal-diff-shaped result) to get a
   model creation order in which every *inter-SCC* FK edge points backward
   (target already created).
5. Emit one ``CreateModel`` per model in that order, with every FK/O2O field
   inlined into it *unless* it is a back edge of its cycle: inside each
   non-trivial SCC the members are ordered by the Eades-Lin-Smyth
   feedback-arc heuristic (``order_within_cycle``, ADR-0272) and only the FKs
   whose target is created *later* stay deferred as ``AddField`` ops after
   every ``CreateModel`` (12 on the 2026-09-05 schema, where deferring every
   intra-cycle edge would have cost 82). Self-referential
   FK/O2O fields are always inlined (a table can reference its own
   not-yet-committed primary key inside its own ``CREATE TABLE`` — this is
   ordinary SQL, not a cycle in the Django-migration sense; verified against
   the existing SCC/self-loop distinction, not assumed).
6. ``ManyToManyField`` ops with an auto-created through table inline like
   FKs (ADR-0272): ``CreateModel`` creates the through table itself, so the
   only ordering need is target-before-owner, and the M2M edges join the
   same topological graph. An M2M with an explicit ``through=`` model stays a
   deferred ``AddField`` (its through model has its own ``CreateModel`` with
   FKs to both ends and must exist first), as does an M2M that is a back
   edge of its cycle.
7. ``AddConstraint``/``AddIndex``/``AlterUniqueTogether`` operations are
   folded into their model's ``CreateModel`` ``options`` (``constraints`` /
   ``indexes`` / ``unique_together``) when every field they reference is on
   that model and not deferred (ADR-0272, #3656: each one is otherwise a
   full-cost step of the replay, ~800 of them). Anything the resolver cannot
   prove safe (positional expressions, a field that is a deferred cycle
   FK or M2M) is kept byte-for-byte and moved as a block to the very end, in
   its original relative order — by construction every field it can
   reference already exists by that point.

All field/option/constraint AST subtrees are reused verbatim from the parsed
source (never hand-reconstructed field-by-field), and the *only* thing this
script changes is which operation a field's AST node is attached to, and the
order operations appear in. ``ruff format`` is run on the output afterward
purely for house-style; it does not change semantics.

If a future migration nuke needs to redo the app collapse (or any other
single-app squash produces another 1,000+-model ``CreateModel``/``AddField``
mountain), rerun this script rather than re-deriving the SCC/topological-sort
approach from scratch — the reasoning above (and the measured result, see
``.superpowers/sdd/2026-08-04-single-app-collapse/task-9-report.md``) should
not be lost.

Chunk mode (Task 10, #2906): cost-weighted splitting
-----------------------------------------------------
Even topologically sorted, ``0001_initial.py`` is one ~27-minute transaction
(1,973 operations). That's not a speed problem (splitting a migration doesn't
reduce total work — the same ``project_state.clone()`` calls happen either
way; see the Task 10 report for the measurement that ruled speed out) but a
*robustness* one: bounded transaction duration (deploy/statement/idle
timeouts, PgBouncer), bounded lock footprint, and resumability (``migrate``
resumes from the last committed migration, so a killed run loses only the
in-flight chunk instead of the whole 27 minutes).

``--chunks [N]`` (default 100) splits the operations into N migration files
instead of rewriting one. The boundaries are **cost-weighted, not
equal-count**: every operation's cost is dominated by the size of Django's
in-memory ``ProjectState`` at the moment it runs (``clone()`` and the
closure re-render are both O(models-already-in-state)). For the k-th
``CreateModel`` that cost is ~k, so cumulative cost through model k is
~k²/2 (quadratic) - splitting 1,026 models into equal *operation-count*
chunks would give a first chunk of milliseconds and a last chunk of minutes.
The 947 operations that only run after every model exists (the 146 deferred
cycle-breaking ``AddField``/``ManyToManyField`` ops plus the 801
``AddConstraint``/``AddIndex``/``AlterUniqueTogether`` tail ops) each cost a
constant ~1,026 (the max model count) - by itself that phase is already
equal-cost-per-op, so equal-*count* chunking is correct for it.
``compute_chunk_boundaries`` builds one combined per-operation cost array
(``range(1, M+1)`` for the M ``CreateModel`` ops, then ``[M] * T`` for the T
post-model ops) and cuts it at N boundaries of ~equal cumulative cost, so
both phases fall out of the same computation: early chunks get many models
(cheap individually), later model-phase chunks get few (expensive
individually), and the post-model phase naturally lands as ~equal-sized
chunks. This is a *starting model*, not a proven-optimal one - if measured
per-chunk timings come out skewed, the boundaries should be adjusted from
that data (see the Task 10 report for what was actually measured).

With ``--generation G`` (ADR-0272) every chunk is stamped ``NNNN_gG_...``,
carries ``replaces = replaced_slice(k, total)`` (the generated files partition
the previous generation), and a chunk of pure ``CreateModel`` ops subclasses
``core_management.batched_migration.BatchedCreateModelMigration`` so the
project state is rendered once per chunk rather than once per model.

Chunk 1 keeps ``0001_initial``'s exact header (imports, ``initial = True``,
the original ``dependencies`` list including the swappable
``AUTH_USER_MODEL`` dependency) verbatim, shrunk to only its slice of
operations. Chunks 2..N are named ``NNNN_initial_part_N`` and each depends
on the previous chunk. Chunk mode also renumbers whatever non-chunk
migrations already follow ``0001_initial`` (materialized views, later
``AlterField``s, ...) to sit after the last chunk, relinks each one's
dependency on its predecessor, and rewrites ``max_migration.txt`` to the new
final migration - so the tool is safe to rerun with a different N (it
discovers the current tail-migration chain from file content, not from
hardcoded old numbers).

Usage::

    uv run python tools/optimize_initial_migration.py [--check]
    uv run python tools/optimize_initial_migration.py --chunks [N]

``--check`` parses and analyzes only, printing the planned operation counts,
without writing the file. ``--chunks`` (default N=100 if given bare) writes
the chunked migration set plus renumbers the downstream migrations; it is
mutually exclusive with ``--check``.
"""

from __future__ import annotations

import argparse
import ast
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
import itertools
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATH = REPO_ROOT / "src" / "world" / "migrations" / "0001_initial.py"
APP_LABEL = "arxii"
SINGLE_VALUED_RELATION_TYPES = {"ForeignKey", "OneToOneField"}
M2M_TYPE = "ManyToManyField"
# Relations that impose "target before owner" on creation order.
ORDERING_RELATION_TYPES = SINGLE_VALUED_RELATION_TYPES | {M2M_TYPE}
DEFAULT_CHUNK_COUNT = 100
_ARXII_DEP_RE = re.compile(rf'\("{APP_LABEL}",\s*"([^"]+)"\)')
_CHUNK_PART_RE = re.compile(r"\d{4}_(initial_part_\d+|g\d+_part_\d+)")


def _require(condition: bool, message: str) -> None:
    """Invariant check for this migration-parsing tool (not user input).

    Raises instead of ``assert`` so it can't be compiled away with -O, and so
    ruff's S101 (asserts as a runtime safety net) doesn't apply — these are
    parser-shape invariants about a machine-generated file, not validation of
    untrusted input.
    """
    if not condition:
        raise AssertionError(message)


def _const_str(node: ast.expr | None) -> str | None:
    """Return the string value of a Constant node, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _kwargs_dict(call: ast.Call) -> dict[str, ast.expr]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}


class CreateModelOp:
    def __init__(self, node: ast.Call):
        self.node = node
        kwargs = _kwargs_dict(node)
        self.name: str = _const_str(kwargs["name"])
        self.key = self.name.lower()
        fields_list = kwargs["fields"]
        _require(isinstance(fields_list, ast.List), "CreateModel.fields must be a List node")
        # Each element is a Tuple(field_name_str, field_call)
        self.field_entries: list[ast.Tuple] = list(fields_list.elts)
        self.options_node = kwargs.get("options")
        self.bases_node = kwargs.get("bases")
        # Extra fields inlined by this script (AddField ops folded in).
        self.extra_field_entries: list[ast.Tuple] = []
        # Tail ops folded into this model's ``options`` (ADR-0272).
        self.folded_constraints: list[ast.expr] = []
        self.folded_indexes: list[ast.expr] = []
        self.folded_unique_together: ast.expr | None = None

    def field_names(self) -> set[str]:
        names = set()
        for entry in self.field_entries:
            names.add(_const_str(entry.elts[0]))
        return names

    def all_field_names(self) -> set[str]:
        """Original fields plus the FKs this script inlined."""
        names = self.field_names()
        for entry in self.extra_field_entries:
            names.add(_const_str(entry.elts[0]))
        return names


class AddFieldOp:
    def __init__(self, node: ast.Call):
        self.node = node
        kwargs = _kwargs_dict(node)
        self.model_name: str = _const_str(kwargs["model_name"])
        self.model_key = self.model_name.lower()
        self.field_name: str = _const_str(kwargs["name"])
        self.field_call: ast.Call = kwargs["field"]
        _require(isinstance(self.field_call, ast.Call), "AddField.field must be a Call node")
        self.field_type: str = self.field_call.func.attr
        field_kwargs = _kwargs_dict(self.field_call)
        self.to: str | None = _const_str(field_kwargs.get("to"))
        # An explicit through model is created by its own CreateModel (with FKs to
        # both ends); the M2M that names it stays deferred so it never precedes it.
        self.explicit_through: bool = self.field_type == M2M_TYPE and "through" in field_kwargs


_TAIL_PAYLOAD_KW = {
    "AddConstraint": "constraint",
    "AddIndex": "index",
    "AlterUniqueTogether": "unique_together",
}


class TailOp:
    """AddConstraint / AddIndex / AlterUniqueTogether.

    Folded into the owning model's ``CreateModel`` options when every field the
    operation references is already on that model (ADR-0272); otherwise kept
    verbatim after the deferred ``AddField`` ops, exactly as before.
    """

    def __init__(self, node: ast.Call, kind: str):
        self.node = node
        self.kind = kind
        kwargs = _kwargs_dict(node)
        name_kw = "name" if kind == "AlterUniqueTogether" else "model_name"
        self.model_key: str = _const_str(kwargs[name_kw]).lower()
        self.payload: ast.expr = kwargs[_TAIL_PAYLOAD_KW[kind]]


def _lookup_root(name: str) -> str:
    """``-created`` -> ``created``; ``amount__gte`` -> ``amount``."""
    return name.lstrip("-").split("__", 1)[0]


def _is_q_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "Q") or (
        isinstance(func, ast.Attribute) and func.attr == "Q"
    )


_Q_INTERNAL_KWARGS = {"_connector", "_negated"}
_LOOKUP_PAIR_LEN = 2  # the writer's ("lookup", value) form


def _is_f_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (isinstance(func, ast.Name) and func.id == "F") or (
        isinstance(func, ast.Attribute) and func.attr == "F"
    )


def _collect_f_refs(node: ast.expr, out: set[str]) -> bool:
    """Add the field every ``F("name")`` inside ``node`` references; False if an F is opaque."""
    for sub in ast.walk(node):
        if _is_f_call(sub):
            name = _const_str(sub.args[0]) if len(sub.args) == 1 else None
            if name is None:
                return False
            out.add(_lookup_root(name))
    return True


def _q_positional(arg: ast.expr, out: set[str]) -> bool:
    """One positional child of a ``Q``: a nested ``Q`` or the writer's ``("lookup", value)``."""
    if _is_q_call(arg):
        return _names_in_q(arg, out)
    if isinstance(arg, ast.Tuple) and len(arg.elts) == _LOOKUP_PAIR_LEN:
        lookup = _const_str(arg.elts[0])
        if lookup is None:
            return False
        out.add(_lookup_root(lookup))
        return _collect_f_refs(arg.elts[1], out)
    return False


def _names_in_q(call: ast.Call, out: set[str]) -> bool:
    """Collect field roots from a ``Q(...)``; False if anything unresolvable appears.

    Django's migration writer serializes ``Q(status="x") | ~Q(y__gt=F("z"))`` as
    ``models.Q(models.Q(("status", "x")), models.Q(("y__gt", models.F("z")),
    _negated=True), _connector="OR")``: positional 2-tuples, nested ``Q`` calls,
    and the two internal kwargs. Hand-written keyword lookups are accepted too.
    """
    for kw in call.keywords:
        if kw.arg is None:
            return False
        if kw.arg in _Q_INTERNAL_KWARGS:
            continue
        out.add(_lookup_root(kw.arg))
        if not _collect_f_refs(kw.value, out):
            return False
    return all(_q_positional(arg, out) for arg in call.args)


_UNFOLDABLE_KWARGS = {"expressions", "include", "opclasses"}


def referenced_field_names(op: TailOp) -> set[str] | None:
    """Field names a tail op references, or None when it cannot be resolved
    conservatively (positional expressions, non-literal ``fields``, ...)."""
    names: set[str] = set()
    if op.kind == "AlterUniqueTogether":
        try:
            groups = ast.literal_eval(op.payload)
        except ValueError:
            return None
        for group in groups:
            names.update(_lookup_root(n) for n in group)
        return names
    payload = op.payload
    if not isinstance(payload, ast.Call) or payload.args:
        return None  # positional expressions (Lower("x"), F("y"), ...): stay in the tail
    for kw in payload.keywords:
        if kw.arg is None or not _collect_kwarg_names(kw.arg, kw.value, names):
            return None
    return names


def _collect_kwarg_names(arg: str, value: ast.expr, names: set[str]) -> bool:
    """Add the field roots one constraint/index kwarg references; False if unresolvable.

    ``name=``, ``deferrable=``, ``violation_error_message=`` and ``nulls_distinct=``
    reference no field and pass through.
    """
    if arg == "fields":
        try:
            names.update(_lookup_root(n) for n in ast.literal_eval(value))
        except ValueError:
            return False
        return True
    if arg in {"condition", "check"}:
        return _is_q_call(value) and _names_in_q(value, names)
    return arg not in _UNFOLDABLE_KWARGS


def fold_tail_ops(
    create_models: dict[str, CreateModelOp],
    tail_ops: list[TailOp],
    deferred_by_model: dict[str, set[str]],
) -> tuple[list[TailOp], int]:
    """Fold each tail op into its model's CreateModel options when safe.

    Returns ``(remaining_tail_ops, folded_count)``. Safe means: the model has a
    CreateModel here, every referenced field resolves, and none of them is a
    field that stays deferred (a cycle-breaking FK or an M2M).
    """
    remaining: list[TailOp] = []
    folded = 0
    for op in tail_ops:
        model = create_models.get(op.model_key)
        names = referenced_field_names(op)
        if model is None or names is None:
            remaining.append(op)
            continue
        present = model.all_field_names() - deferred_by_model.get(op.model_key, set())
        if not names <= present:
            remaining.append(op)
            continue
        if op.kind == "AddConstraint":
            model.folded_constraints.append(op.payload)
        elif op.kind == "AddIndex":
            model.folded_indexes.append(op.payload)
        else:
            model.folded_unique_together = op.payload
        folded += 1
    return remaining, folded


def parse_operations(tree: ast.Module) -> list[ast.Call]:
    migration_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Migration"
    )
    ops_assign = next(
        n
        for n in migration_class.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "operations" for t in n.targets)
    )
    ops_list = ops_assign.value
    _require(isinstance(ops_list, ast.List), "Migration.operations must be a List node")
    return list(ops_list.elts)


def classify(op_nodes: list[ast.Call]):
    create_models: dict[str, CreateModelOp] = {}
    create_order: list[str] = []
    add_fields: list[AddFieldOp] = []
    tail_ops: list[TailOp] = []

    for call in op_nodes:
        kind = call.func.attr
        if kind == "CreateModel":
            op = CreateModelOp(call)
            _require(op.key not in create_models, f"duplicate model {op.key}")
            create_models[op.key] = op
            create_order.append(op.key)
        elif kind == "AddField":
            add_fields.append(AddFieldOp(call))
        elif kind in ("AddConstraint", "AddIndex", "AlterUniqueTogether"):
            tail_ops.append(TailOp(call, kind))
        else:
            msg = f"unexpected operation kind: {kind}"
            raise ValueError(msg)

    return create_models, create_order, add_fields, tail_ops


def target_key(to_value: str | None) -> str | None:
    """Return the intra-app model key a `to=` string refers to, else None."""
    if to_value is None or not to_value.startswith(f"{APP_LABEL}."):
        return None
    return to_value.split(".", 1)[1]


def build_graph(create_models: dict[str, CreateModelOp], add_fields: list[AddFieldOp]):
    """Directed graph: edge owner -> target for every non-self FK/O2O."""
    edges: set[tuple[str, str]] = set()

    for owner_key, op in create_models.items():
        for entry in op.field_entries:
            field_call = entry.elts[1]
            if not isinstance(field_call, ast.Call):
                continue
            ftype = field_call.func.attr
            if ftype not in ORDERING_RELATION_TYPES:
                continue
            fkwargs = _kwargs_dict(field_call)
            tkey = target_key(_const_str(fkwargs.get("to")))
            if tkey is None or tkey == owner_key:
                continue
            edges.add((owner_key, tkey))

    for af in add_fields:
        if af.field_type not in ORDERING_RELATION_TYPES or af.explicit_through:
            continue
        tkey = target_key(af.to)
        if tkey is None or tkey == af.model_key:
            continue
        edges.add((af.model_key, tkey))

    return edges


class _TarjanState:
    """Mutable bookkeeping for one iterative Tarjan SCC run."""

    def __init__(self) -> None:
        self.index: dict[str, int] = {}
        self.lowlink: dict[str, int] = {}
        self.on_stack: dict[str, bool] = {}
        self.stack: list[str] = []
        self.scc_id: dict[str, int] = {}
        self._next_index = 0
        self._next_scc_id = 0

    def visit_new(self, node: str) -> None:
        self.index[node] = self._next_index
        self.lowlink[node] = self._next_index
        self._next_index += 1
        self.stack.append(node)
        self.on_stack[node] = True

    def pop_component(self, root: str) -> None:
        comp_id = self._next_scc_id
        self._next_scc_id += 1
        while True:
            w = self.stack.pop()
            self.on_stack[w] = False
            self.scc_id[w] = comp_id
            if w == root:
                return


def _tarjan_visit(start: str, adj: dict[str, list[str]], state: _TarjanState) -> None:
    """Iterative DFS from `start` (avoids recursion-depth issues at scale)."""
    # Explicit stack of (node, next-neighbor-index-to-visit).
    work: list[tuple[str, int]] = [(start, 0)]
    state.visit_new(start)

    while work:
        node, i = work[-1]
        neighbors = adj[node]
        if i < len(neighbors):
            work[-1] = (node, i + 1)
            nxt = neighbors[i]
            if nxt not in state.index:
                state.visit_new(nxt)
                work.append((nxt, 0))
            elif state.on_stack.get(nxt):
                state.lowlink[node] = min(state.lowlink[node], state.index[nxt])
            continue

        work.pop()
        if work:
            parent = work[-1][0]
            state.lowlink[parent] = min(state.lowlink[parent], state.lowlink[node])
        if state.lowlink[node] == state.index[node]:
            state.pop_component(node)


def tarjan_scc(nodes: list[str], edges: set[tuple[str, str]]) -> dict[str, int]:
    """Tarjan's SCC algorithm. Returns model_key -> scc_id (arbitrary but stable)."""
    adj: dict[str, list[str]] = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)

    state = _TarjanState()
    for start in nodes:
        if start not in state.index:
            _tarjan_visit(start, adj, state)
    return state.scc_id


def _condense(
    edges: set[tuple[str, str]], scc_id: dict[str, int], all_sccs: list[int]
) -> tuple[dict[int, set[int]], dict[int, int]]:
    """Build the "must precede" graph over SCCs: target_scc -> owner_sccs.

    Edge owner->target (a field on `owner` FKs to `target`) means target must
    be created first, so the condensation edge for Kahn's algorithm below
    runs the other way: target_scc -> owner_scc.
    """
    condensation_out: dict[int, set[int]] = defaultdict(set)
    in_degree: dict[int, int] = dict.fromkeys(all_sccs, 0)
    seen_edges: set[tuple[int, int]] = set()
    for owner, target in edges:
        owner_scc, target_scc = scc_id[owner], scc_id[target]
        if owner_scc == target_scc:
            continue
        edge = (target_scc, owner_scc)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        condensation_out[target_scc].add(owner_scc)
        in_degree[owner_scc] += 1
    return condensation_out, in_degree


def topo_order_sccs(
    nodes: list[str],
    edges: set[tuple[str, str]],
    scc_id: dict[str, int],
) -> list[int]:
    """Kahn's algorithm over the condensation, in model-CREATION order.

    An SCC with in-degree 0 in the "must precede" graph has no remaining
    unmet dependencies and can be created next.
    """
    all_sccs = sorted(set(scc_id.values()))
    condensation_out, in_degree = _condense(edges, scc_id, all_sccs)

    # Stable tie-break: first-appearance order of each scc in `nodes`, so the
    # rewrite stays close to the original file's model ordering wherever the
    # graph doesn't force a choice (minimal, reviewable diff shape).
    first_seen: dict[int, int] = {}
    for i, n in enumerate(nodes):
        s = scc_id[n]
        if s not in first_seen:
            first_seen[s] = i

    order: list[int] = []
    emitted: set[int] = set()
    frontier = [s for s in all_sccs if in_degree[s] == 0]
    while frontier:
        frontier.sort(key=lambda s: first_seen[s])
        s = frontier.pop(0)
        if s in emitted:
            continue
        emitted.add(s)
        order.append(s)
        for nxt in condensation_out.get(s, ()):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                frontier.append(nxt)

    _require(
        len(order) == len(all_sccs),
        f"topological sort incomplete: {len(order)} of {len(all_sccs)} SCCs ordered "
        "(a bug, since SCC condensation is always acyclic)",
    )
    return order


def order_within_cycle(members: list[str], before: set[tuple[str, str]]) -> list[str]:
    """Order the members of one cycle so that few ``(u, v)`` "u before v" edges point backward.

    Eades-Lin-Smyth greedy feedback-arc-set heuristic: peel sinks to the end and
    sources to the front; when neither exists, move the node with the largest
    out-degree minus in-degree to the front. Ties break by ``members`` order so the
    result is stable. Every edge that still points backward in the returned order
    is one FK the caller must defer to an ``AddField``; every other edge inlines.
    """
    remaining = list(members)
    out_edges: dict[str, set[str]] = {m: set() for m in members}
    in_edges: dict[str, set[str]] = {m: set() for m in members}
    for u, v in before:
        if u in out_edges and v in in_edges and u != v:
            out_edges[u].add(v)
            in_edges[v].add(u)
    front: list[str] = []
    back: list[str] = []

    def remove(node: str) -> None:
        remaining.remove(node)
        for other in out_edges[node]:
            in_edges[other].discard(node)
        for other in in_edges[node]:
            out_edges[other].discard(node)
        out_edges[node].clear()
        in_edges[node].clear()

    while remaining:
        sinks = [m for m in remaining if not out_edges[m]]
        if sinks:
            back.insert(0, sinks[0])
            remove(sinks[0])
            continue
        sources = [m for m in remaining if not in_edges[m]]
        if sources:
            front.append(sources[0])
            remove(sources[0])
            continue
        best = max(remaining, key=lambda m: len(out_edges[m]) - len(in_edges[m]))
        front.append(best)
        remove(best)
    return front + back


def build_model_order(
    create_order: list[str],
    scc_id: dict[str, int],
    scc_topo: list[int],
    edges: set[tuple[str, str]] | None = None,
) -> list[str]:
    """Creation order: SCCs topologically, and inside a non-trivial SCC the order
    that leaves the fewest FK edges pointing at a later model (see `order_within_cycle`)."""
    members: dict[int, list[str]] = defaultdict(list)
    for key in create_order:  # preserve original file order within each SCC
        members[scc_id[key]].append(key)
    ordered_keys: list[str] = []
    for s in scc_topo:
        group = members[s]
        if len(group) > 1 and edges:
            # An FK owner -> target means "target before owner".
            before = {(t, o) for (o, t) in edges if scc_id[o] == s and scc_id[t] == s and o != t}
            group = order_within_cycle(group, before)
        ordered_keys.extend(group)
    _require(len(ordered_keys) == len(create_order), "model_order dropped or duplicated a model")
    return ordered_keys


def _check_inline_relations(
    create_models: dict[str, CreateModelOp], position: dict[str, int]
) -> None:
    """A FK already inline in a CreateModel must target a model created no later.

    Django's autodetector defers every forward-referencing FK whenever a cycle
    exists, so this never fires on its output; it exists so a cycle order that
    put an inline target later would fail loudly instead of emitting a migration
    that fails at CREATE TABLE.
    """
    for owner_key, op in create_models.items():
        for entry in op.field_entries:
            field_call = entry.elts[1]
            if not isinstance(field_call, ast.Call) or field_call.func.attr not in (
                SINGLE_VALUED_RELATION_TYPES
            ):
                continue
            tkey = target_key(_const_str(_kwargs_dict(field_call).get("to")))
            if tkey is None or tkey == owner_key:
                continue
            _require(
                position[tkey] < position[owner_key],
                f"inline FK {owner_key}.{_const_str(entry.elts[0])} targets {tkey}, created later",
            )


def _analyze(
    tree: ast.Module,
    *,
    fold: bool = True,
) -> tuple[dict[str, CreateModelOp], list[str], list[AddFieldOp], list[TailOp], dict]:
    """Parse, classify, and fold deferred ``AddField`` ops into ``CreateModel``.

    Shared by both single-file (`rewrite`) and chunked (`rewrite_chunks`)
    modes. Returns ``(create_models, model_order, remaining_add_field_ops,
    tail_ops, stats)`` - everything needed to build the final operation
    sequence, without deciding how it gets split across file(s).
    """
    op_nodes = parse_operations(tree)
    create_models, create_order, add_fields, tail_ops = classify(op_nodes)

    edges = build_graph(create_models, add_fields)
    scc_id = tarjan_scc(create_order, edges)
    scc_topo = topo_order_sccs(create_order, edges, scc_id)
    model_order = build_model_order(create_order, scc_id, scc_topo, edges)
    position = {key: i for i, key in enumerate(model_order)}
    _check_inline_relations(create_models, position)

    # Non-trivial SCCs (size > 1): the only place a real cycle can require
    # deferral. A trivial SCC (size 1) never needs deferral: if it has a
    # self-loop that's an ordinary self-referential FK, safe to inline in
    # its own CreateModel; if it has no self-loop it has no internal edges
    # at all.
    scc_members: dict[int, list[str]] = defaultdict(list)
    for key, s in scc_id.items():
        scc_members[s].append(key)
    non_trivial_sccs = {s for s, members in scc_members.items() if len(members) > 1}

    deferred_field_count = 0
    deferred_m2m_count = 0
    inlined_field_count = 0
    inlined_m2m_count = 0
    self_ref_count = 0

    # Fold every currently-deferred relational AddField into its owner's
    # CreateModel unless it is a back edge of its cycle's chosen order or an
    # M2M with an explicit through model. Auto-through M2Ms inline like FKs:
    # CreateModel creates the through table itself, so target-before-owner is
    # the only ordering need and the topological order provides it.
    remaining_add_field_ops: list[AddFieldOp] = []
    for af in add_fields:
        is_m2m = af.field_type == M2M_TYPE
        if af.explicit_through:
            remaining_add_field_ops.append(af)
            deferred_m2m_count += 1
            continue

        tkey = target_key(af.to)
        owner_op = create_models[af.model_key]

        if tkey == af.model_key:
            # Self-referential FK/O2O: the table being created can reference
            # its own (not-yet-committed) rows in the same CREATE TABLE -
            # ordinary SQL, not a real ordering cycle. Always safe to inline.
            # A self-referential auto-through M2M is the same.
            self_ref_count += 1
            owner_op.extra_field_entries.append(_field_entry_from_addfield(af))
            inlined_field_count += 1
            inlined_m2m_count += is_m2m
            continue

        if (
            tkey is not None
            and scc_id[af.model_key] in non_trivial_sccs
            and scc_id.get(tkey) == scc_id[af.model_key]
            and position[tkey] > position[af.model_key]
        ):
            # A back edge of the cycle's chosen order: the target is created
            # after the owner, so this relation is one of the few that truly
            # must stay deferred. Cycle edges whose target comes first inline
            # like any other (the table exists by then).
            remaining_add_field_ops.append(af)
            if is_m2m:
                deferred_m2m_count += 1
            else:
                deferred_field_count += 1
            continue

        # Everything else: target is external/settings-based (tkey is None,
        # e.g. settings.AUTH_USER_MODEL or another already-migrated app), or
        # it is an intra-app model in a different SCC, which by construction
        # of the topological order was already created earlier - safe to
        # inline either way.
        owner_op.extra_field_entries.append(_field_entry_from_addfield(af))
        inlined_field_count += 1
        inlined_m2m_count += is_m2m

    deferred_by_model: dict[str, set[str]] = defaultdict(set)
    for af in remaining_add_field_ops:
        deferred_by_model[af.model_key].add(af.field_name)
    folded_count = 0
    if fold:
        tail_ops, folded_count = fold_tail_ops(create_models, tail_ops, deferred_by_model)

    stats = {
        "models": len(create_order),
        "sccs_total": len(scc_members),
        "sccs_non_trivial": len(non_trivial_sccs),
        "self_ref_inlined": self_ref_count,
        "inlined_total": inlined_field_count,
        "deferred_addfield_cycle": deferred_field_count,
        "deferred_addfield_m2m": deferred_m2m_count,
        "inlined_m2m": inlined_m2m_count,
        "tail_ops_folded": folded_count,
        "tail_ops": len(tail_ops),
        "create_model_ops": len(create_order),
    }

    return create_models, model_order, remaining_add_field_ops, tail_ops, stats


def rewrite(source: str, check_only: bool, *, fold: bool = True) -> tuple[str, dict]:
    tree = ast.parse(source)
    create_models, model_order, remaining_add_field_ops, tail_ops, stats = _analyze(tree, fold=fold)

    if check_only:
        return source, stats

    plan = RewritePlan(
        create_models=create_models,
        model_order=model_order,
        remaining_add_field_ops=remaining_add_field_ops,
        tail_ops=tail_ops,
    )
    new_source = emit_source(source, tree, plan)
    return new_source, stats


def _field_entry_from_addfield(af: AddFieldOp) -> ast.Tuple:
    """Build a (name, field_call) Tuple node matching CreateModel's shape."""
    name_node = ast.Constant(value=af.field_name)
    return ast.Tuple(elts=[name_node, af.field_call], ctx=ast.Load())


@dataclass
class RewritePlan:
    """Everything `emit_source` needs to render the new operations list."""

    create_models: dict[str, CreateModelOp]
    model_order: list[str]
    remaining_add_field_ops: list[AddFieldOp]
    tail_ops: list[TailOp]


def _find_operations_assign(tree: ast.Module) -> ast.Assign:
    migration_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Migration"
    )
    candidates = [
        n
        for n in migration_class.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "operations" for t in n.targets)
    ]
    _require(len(candidates) == 1, "Migration class must have exactly one `operations = [...]`")
    return candidates[0]


def _options_with_folds(op: CreateModelOp) -> ast.expr | None:
    """The model's ``options`` Dict with folded constraints/indexes/unique_together merged in."""
    if not (op.folded_constraints or op.folded_indexes or op.folded_unique_together):
        return op.options_node
    keys: list[ast.expr | None] = []
    values: list[ast.expr] = []
    if op.options_node is not None:
        _require(isinstance(op.options_node, ast.Dict), "CreateModel.options must be a Dict node")
        keys, values = list(op.options_node.keys), list(op.options_node.values)
    existing = {_const_str(k): i for i, k in enumerate(keys) if k is not None}

    def merge_list(key: str, items: list[ast.expr]) -> None:
        if not items:
            return
        if key in existing:
            node = values[existing[key]]
            _require(isinstance(node, ast.List), f"options[{key!r}] must be a List node")
            node.elts.extend(items)
        else:
            keys.append(ast.Constant(value=key))
            values.append(ast.List(elts=items, ctx=ast.Load()))

    merge_list("constraints", op.folded_constraints)
    merge_list("indexes", op.folded_indexes)
    if op.folded_unique_together is not None:
        if "unique_together" in existing:
            values[existing["unique_together"]] = op.folded_unique_together
        else:
            keys.append(ast.Constant(value="unique_together"))
            values.append(op.folded_unique_together)
    return ast.Dict(keys=keys, values=values)


def _create_model_call(op: CreateModelOp) -> ast.Call:
    """Rebuild a `CreateModel(...)` call node with folded fields and options added."""
    fields_list = ast.List(
        elts=[*op.field_entries, *[e for e in op.extra_field_entries if e is not None]],
        ctx=ast.Load(),
    )
    kw = [ast.keyword(arg="name", value=ast.Constant(value=op.name))]
    kw.append(ast.keyword(arg="fields", value=fields_list))
    options = _options_with_folds(op)
    if options is not None:
        kw.append(ast.keyword(arg="options", value=options))
    if op.bases_node is not None:
        kw.append(ast.keyword(arg="bases", value=op.bases_node))
    return ast.Call(
        func=ast.Attribute(
            value=ast.Name(id="migrations", ctx=ast.Load()), attr="CreateModel", ctx=ast.Load()
        ),
        args=[],
        keywords=kw,
    )


def _build_full_op_sequence(plan: RewritePlan) -> list[ast.expr]:
    """The final, topologically-valid operation order: every `CreateModel` (in
    `model_order`, fields folded in), then every remaining deferred
    `AddField` (cycle-breakers + M2M), then every tail op (`AddConstraint`
    / `AddIndex` / `AlterUniqueTogether`). Shared by both the single-file
    and chunked emitters - chunking only decides *where* to cut this list,
    never reorders it.
    """
    ops: list[ast.expr] = [_create_model_call(plan.create_models[key]) for key in plan.model_order]
    ops.extend(af.node for af in plan.remaining_add_field_ops)
    ops.extend(t.node for t in plan.tail_ops)
    return ops


def _unparse_ops_list(ops: list[ast.expr]) -> str:
    ops_list = ast.List(elts=ops, ctx=ast.Load())
    ast.fix_missing_locations(ops_list)
    return ast.unparse(ops_list)


def emit_source(source: str, tree: ast.Module, plan: RewritePlan) -> str:
    ops_assign = _find_operations_assign(tree)
    new_operations_source = _unparse_ops_list(_build_full_op_sequence(plan))

    # Splice the regenerated operations list text in place of the original,
    # keeping everything else (imports, dependencies, initial=True, header
    # comment) byte-identical via direct source slicing.
    lines = source.splitlines(keepends=True)

    ops_list_node = ops_assign.value
    start_line, start_col = ops_list_node.lineno, ops_list_node.col_offset
    end_line, end_col = ops_list_node.end_lineno, ops_list_node.end_col_offset

    before = "".join(lines[: start_line - 1]) + lines[start_line - 1][:start_col]
    after = lines[end_line - 1][end_col:] + "".join(lines[end_line:])

    return before + new_operations_source + after


def compute_chunk_boundaries(costs: list[int], n_chunks: int) -> list[int]:
    """Partition `costs` (one weight per operation, in final emission order)
    into `n_chunks` contiguous groups of ~equal cumulative cost.

    Returns exclusive end-indices (length `n_chunks`, strictly increasing,
    last entry == len(costs)). Every chunk gets >= 1 operation as long as
    `len(costs) >= n_chunks` (enforced by the caller).
    """
    n_ops = len(costs)
    _require(1 <= n_chunks <= n_ops, "n_chunks must be between 1 and the number of operations")
    prefix = list(itertools.accumulate(costs))
    total = prefix[-1]
    boundaries: list[int] = []
    prev_end = 0
    for j in range(1, n_chunks):
        target = total * j / n_chunks
        end = bisect_left(prefix, target, lo=prev_end)
        # Clamp so every chunk (including remaining ones) stays non-empty,
        # regardless of how lumpy the cost distribution is.
        min_end = prev_end + 1
        max_end = n_ops - (n_chunks - j)
        end = max(min_end, min(end, max_end))
        boundaries.append(end)
        prev_end = end
    boundaries.append(n_ops)
    return boundaries


def _split_by_boundaries(items: list[ast.expr], boundaries: list[int]) -> list[list[ast.expr]]:
    groups = []
    start = 0
    for end in boundaries:
        groups.append(items[start:end])
        start = end
    return groups


def _operation_costs(n_model_ops: int, n_tail_ops: int) -> list[int]:
    """Per-operation cost weight, in final emission order.

    Each `CreateModel` op's cost scales with the number of models already in
    `ProjectState` (both `clone()` and the reload closure re-render are
    O(models-in-state)), so the k-th `CreateModel` costs ~k. Every operation
    after all M models exist (deferred `AddField`, `AddConstraint`,
    `AddIndex`, `AlterUniqueTogether`) costs the constant maximum, ~M. See
    the module docstring's "Chunk mode" section for the full rationale.
    """
    return [*range(1, n_model_ops + 1), *([n_model_ops] * n_tail_ops)]


GENERATIONS_IMPORT = "from world.migrations._generations import replaced_slice\n"
BATCHED_IMPORT = "from core_management.batched_migration import BatchedCreateModelMigration\n"


def chunk_name(generation: int | None, index: int) -> str:
    """Name of chunk ``index`` (1-based).

    ``generation=None`` is the #2906 shape (``0001_initial``, ``NNNN_initial_part_N``).
    A stamped name (``0001_g2_initial``, ``NNNN_g2_part_N``) can never collide with an
    earlier generation's, which is what lets production keep every old name
    recorded forever (ADR-0272).
    """
    if generation is None:
        return "0001_initial" if index == 1 else f"{index:04d}_initial_part_{index}"
    if index == 1:
        return f"{index:04d}_g{generation}_initial"
    return f"{index:04d}_g{generation}_part_{index}"


def _dependencies_source(tree: ast.Module) -> str:
    """The original ``dependencies = [...]`` list, re-rendered from its AST."""
    migration_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Migration"
    )
    for node in migration_class.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "dependencies" for t in node.targets
        ):
            return ast.unparse(node.value)
    return "[]"


def rewrite_chunks(
    source: str,
    n_chunks: int,
    generation: int | None = None,
    *,
    fold: bool = True,
    replaces_total: int | None = None,
) -> tuple[list[tuple[str, str]], dict]:
    """Split `source` into `n_chunks` cost-weighted migration files.

    Returns `(files, stats)` where `files` is `[(migration_name, content),
    ...]` in dependency-chain order (first is `chunk_name(generation, 1)`).
    With ``generation`` set, every file is stamped and carries
    ``replaces = replaced_slice(k, replaces_total)`` (``replaces_total`` is the
    number of generated files in the generation, chunks plus tails; it defaults
    to the chunk count), and a chunk made only of ``CreateModel`` ops uses
    ``BatchedCreateModelMigration`` (see `_render_chunk_files`).
    """
    tree = ast.parse(source)
    create_models, model_order, remaining_add_field_ops, tail_ops, stats = _analyze(tree, fold=fold)
    plan = RewritePlan(
        create_models=create_models,
        model_order=model_order,
        remaining_add_field_ops=remaining_add_field_ops,
        tail_ops=tail_ops,
    )

    full_ops = _build_full_op_sequence(plan)
    n_model_ops = len(plan.model_order)
    n_tail_ops = len(full_ops) - n_model_ops
    costs = _operation_costs(n_model_ops, n_tail_ops)

    n_chunks = max(1, min(n_chunks, len(full_ops)))
    boundaries = compute_chunk_boundaries(costs, n_chunks)
    groups = _split_by_boundaries(full_ops, boundaries)

    files = _render_chunk_files(
        source, tree, groups, generation, replaces_total=replaces_total or len(groups)
    )
    stats = {**stats, "n_chunks": len(files), "chunk_sizes": [len(g) for g in groups]}
    return files, stats


def _is_pure_create_model(group: list[ast.expr]) -> bool:
    return all(
        isinstance(op, ast.Call)
        and isinstance(op.func, ast.Attribute)
        and op.func.attr == "CreateModel"
        for op in group
    )


def _render_chunk_files(
    source: str,
    tree: ast.Module,
    groups: list[list[ast.expr]],
    generation: int | None = None,
    *,
    replaces_total: int | None = None,
) -> list[tuple[str, str]]:
    """Render each op group into a migration file's full source text.

    Unstamped (``generation=None``, the #2906 shape): chunk 1 keeps
    `0001_initial`'s original header (imports, header comment, `initial = True`,
    the original `dependencies` list) byte-identical via the same source-slicing
    technique as `emit_source`, with only its `operations` list shrunk to
    `groups[0]`. Chunks 2..N get a fresh minimal header built from the original
    file's imports block (reused verbatim, over-inclusive - `ruff check --fix`
    strips whatever a given chunk doesn't need) and a
    `dependencies = [("arxii", <previous chunk>)]`.

    Stamped (``generation=G``, ADR-0272): every file gets the minimal header,
    plus ``replaces = replaced_slice(k, replaces_total)`` so the generated files
    partition the previous generation; chunk 1 keeps ``initial = True`` and the
    original ``dependencies`` list (re-rendered from its AST, so the swappable
    AUTH_USER_MODEL dependency survives). A chunk made only of ``CreateModel``
    ops subclasses ``BatchedCreateModelMigration``, which renders the project
    state once per chunk instead of once per model (the O(n^2) closure
    re-render that dominates a replay).
    """
    ops_assign = _find_operations_assign(tree)
    lines = source.splitlines(keepends=True)

    migration_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Migration"
    )
    imports_block = "".join(lines[: migration_class.lineno - 1])
    total = replaces_total or len(groups)

    def render(index: int, class_body_prefix: str, group: list[ast.expr]) -> str:
        if generation is None:
            imports, base, replaces_line = imports_block, "migrations.Migration", ""
        else:
            batched = _is_pure_create_model(group)
            imports = imports_block + (BATCHED_IMPORT if batched else "") + GENERATIONS_IMPORT
            base = "BatchedCreateModelMigration" if batched else "migrations.Migration"
            replaces_line = f"    replaces = replaced_slice({index}, {total})\n"
        return (
            f"{imports}\n"
            f"class Migration({base}):\n"
            f"{class_body_prefix}{replaces_line}"
            f"    operations = {_unparse_ops_list(group)}\n"
        )

    first_name = chunk_name(generation, 1)
    if generation is None:
        ops_list_node = ops_assign.value
        start_line, start_col = ops_list_node.lineno, ops_list_node.col_offset
        end_line, end_col = ops_list_node.end_lineno, ops_list_node.end_col_offset
        before = "".join(lines[: start_line - 1]) + lines[start_line - 1][:start_col]
        after = lines[end_line - 1][end_col:] + "".join(lines[end_line:])
        first_content = before + _unparse_ops_list(groups[0]) + after
    else:
        first_prefix = f"    initial = True\n    dependencies = {_dependencies_source(tree)}\n"
        first_content = render(1, first_prefix, groups[0])
    files: list[tuple[str, str]] = [(first_name, first_content)]

    prev_name = first_name
    for i, group in enumerate(groups[1:], start=2):
        name = chunk_name(generation, i)
        prefix = f'    dependencies = [\n        ("{APP_LABEL}", "{prev_name}"),\n    ]\n\n'
        files.append((name, render(i, prefix, group)))
        prev_name = name

    return files


def _predecessor_name(text: str) -> str:
    """The arxii-dependency name a tail migration's `dependencies` currently
    reference (dynamically parsed from content, not assumed - so a rerun
    with a different N still finds the right predecessor to relink).
    """
    matches = _ARXII_DEP_RE.findall(text)
    _require(
        len(matches) == 1,
        f"expected exactly one {APP_LABEL!r} dependency in tail migration, found {matches!r}",
    )
    return matches[0]


def _discover_tail_migrations(migrations_dir: Path) -> list[Path]:
    """Migrations after `0001_initial` that are not `*_initial_part_*` chunks,
    in dependency-chain order (their numeric filename prefix already
    reflects that order - django_linear_migrations enforces exactly one
    linear history / leaf per app).
    """
    return sorted(
        p
        for p in migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.py")
        if p.stem != chunk_name(None, 1) and not _CHUNK_PART_RE.match(p.stem)
    )


def _write_chunk_files(migrations_dir: Path, files: list[tuple[str, str]]) -> list[Path]:
    written = []
    for name, content in files:
        path = migrations_dir / f"{name}.py"
        path.write_text(content)
        written.append(path)
    return written


def _renumber_tail_migrations(migrations_dir: Path, last_chunk_name: str, n_chunks: int) -> str:
    """Move the non-chunk migrations (materialized views, later AlterFields,
    ...) after the new last chunk, preserving their relative order and
    relinking each one's dependency onto its (possibly renamed) predecessor.

    Returns the final migration's name, for `max_migration.txt`.
    """
    tail_paths = _discover_tail_migrations(migrations_dir)
    tail_sources = [(p, p.read_text()) for p in tail_paths]

    # Move every tail file out of the way first, in case the chunk range
    # [0002..NNNN] about to be (re)written would otherwise collide with one
    # of these files' *current* number (e.g. N shrank since the last run).
    temp_paths = []
    for i, (p, _text) in enumerate(tail_sources):
        temp_path = p.with_name(f"__renumbering_{i}__{p.name}")
        p.rename(temp_path)
        temp_paths.append(temp_path)

    prev_name = last_chunk_name
    next_number = n_chunks + 1
    for (orig_path, orig_text), temp_path in zip(tail_sources, temp_paths, strict=True):
        old_predecessor = _predecessor_name(orig_text)
        name_suffix = orig_path.stem.split("_", 1)[1]
        new_own_name = f"{next_number:04d}_{name_suffix}"
        new_text = orig_text.replace(f'"{old_predecessor}"', f'"{prev_name}"')
        (migrations_dir / f"{new_own_name}.py").write_text(new_text)
        temp_path.unlink()
        prev_name = new_own_name
        next_number += 1

    return prev_name


def _run_chunk_mode(source: str, n_chunks: int, generation: int | None = None) -> int:
    files, stats = rewrite_chunks(source, n_chunks, generation)

    print("=== optimize_initial_migration chunk stats ===")
    for k, v in stats.items():
        if k != "chunk_sizes":
            print(f"{k}: {v}")
    print(f"chunk_sizes: {stats['chunk_sizes']}")

    migrations_dir = MIGRATION_PATH.parent

    # Discover the tail migrations (materialized views, later AlterFields,
    # ...) and the stale chunk artifacts from any previous run BEFORE
    # touching anything, so a rerun with a different N still works.
    old_part_files = sorted(
        p for p in migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.py") if _CHUNK_PART_RE.match(p.stem)
    )
    tail_final_name = _renumber_tail_migrations(migrations_dir, files[-1][0], len(files))

    for p in old_part_files:
        p.unlink()

    written = _write_chunk_files(migrations_dir, files)

    max_migration_path = migrations_dir / "max_migration.txt"
    max_migration_path.write_text(tail_final_name + "\n")

    print(
        f"wrote {len(written)} chunk files ({chunk_name(generation, 1)}.py .. "
        f"{files[-1][0]}.py) + renumbered tail migrations through "
        f"{tail_final_name}; max_migration.txt updated"
    )

    # House-style only (does not change semantics); argv is a fixed literal
    # list, not untrusted input.
    uv_path = shutil.which("uv") or "uv"
    ruff_target = str(migrations_dir)
    subprocess.run(  # noqa: S603
        [uv_path, "run", "ruff", "format", ruff_target], cwd=REPO_ROOT, check=True
    )
    subprocess.run(  # noqa: S603
        [uv_path, "run", "ruff", "check", "--fix", ruff_target], cwd=REPO_ROOT, check=False
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="analyze only, do not write")
    parser.add_argument(
        "--chunks",
        type=int,
        nargs="?",
        const=DEFAULT_CHUNK_COUNT,
        default=None,
        metavar="N",
        help=(
            "split into N cost-weighted migrations instead of rewriting "
            f"0001_initial.py as one file (default {DEFAULT_CHUNK_COUNT} if "
            "given bare); also renumbers the downstream migrations and "
            "max_migration.txt to follow the last chunk. Mutually exclusive "
            "with --check."
        ),
    )
    parser.add_argument(
        "--generation",
        type=int,
        default=None,
        metavar="G",
        help="stamp chunk names with generation G and add replaces = REPLACED (ADR-0272)",
    )
    args = parser.parse_args()
    if args.chunks is not None and args.check:
        parser.error("--check and --chunks are mutually exclusive")

    source = MIGRATION_PATH.read_text()

    if args.chunks is not None:
        return _run_chunk_mode(source, args.chunks, args.generation)

    new_source, stats = rewrite(source, check_only=args.check)

    print("=== optimize_initial_migration stats ===")
    for k, v in stats.items():
        print(f"{k}: {v}")

    if args.check:
        return 0

    # Validate the regenerated source parses before writing.
    ast.parse(new_source)
    MIGRATION_PATH.write_text(new_source)
    print(f"wrote {MIGRATION_PATH}")

    # House-style only (does not change semantics); argv is a fixed literal
    # list, not untrusted input.
    uv_path = shutil.which("uv") or "uv"
    subprocess.run(  # noqa: S603
        [uv_path, "run", "ruff", "format", str(MIGRATION_PATH)], cwd=REPO_ROOT, check=True
    )
    subprocess.run(  # noqa: S603
        [uv_path, "run", "ruff", "check", "--fix", str(MIGRATION_PATH)], cwd=REPO_ROOT, check=False
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
