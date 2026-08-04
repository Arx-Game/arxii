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
   inlined into it *unless* the field's target is a different model in the
   same non-trivial SCC (a genuine cycle — these ~49 fields become
   ``AddField`` ops emitted after every ``CreateModel``). Self-referential
   FK/O2O fields are always inlined (a table can reference its own
   not-yet-committed primary key inside its own ``CREATE TABLE`` — this is
   ordinary SQL, not a cycle in the Django-migration sense; verified against
   the existing SCC/self-loop distinction, not assumed).
6. ``ManyToManyField`` operations are *not* part of this FK-ordering problem
   (they create a separate through-table and Django's autodetector always
   defers them regardless of cycles) — they are kept as ``AddField`` ops,
   unchanged in content, just moved after all ``CreateModel`` ops like the
   cyclic FK/O2O fields.
7. ``AddConstraint``/``AddIndex``/``AlterUniqueTogether`` operations are kept
   byte-for-byte (their AST subtree is reused verbatim) and moved as a block
   to the very end, in their original relative order — by construction every
   field they can reference already exists by that point.

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
RELATION_TYPES = {"ForeignKey", "OneToOneField", "ManyToManyField"}
SINGLE_VALUED_RELATION_TYPES = {"ForeignKey", "OneToOneField"}
DEFAULT_CHUNK_COUNT = 100
_ARXII_DEP_RE = re.compile(rf'\("{APP_LABEL}",\s*"([^"]+)"\)')


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

    def field_names(self) -> set[str]:
        names = set()
        for entry in self.field_entries:
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


class TailOp:
    """AddConstraint / AddIndex / AlterUniqueTogether — kept verbatim."""

    def __init__(self, node: ast.Call, kind: str):
        self.node = node
        self.kind = kind


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
            if ftype not in SINGLE_VALUED_RELATION_TYPES:
                continue
            fkwargs = _kwargs_dict(field_call)
            tkey = target_key(_const_str(fkwargs.get("to")))
            if tkey is None or tkey == owner_key:
                continue
            edges.add((owner_key, tkey))

    for af in add_fields:
        if af.field_type not in SINGLE_VALUED_RELATION_TYPES:
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


def build_model_order(
    create_order: list[str], scc_id: dict[str, int], scc_topo: list[int]
) -> list[str]:
    members: dict[int, list[str]] = defaultdict(list)
    for key in create_order:  # preserve original file order within each SCC
        members[scc_id[key]].append(key)
    ordered_keys: list[str] = []
    for s in scc_topo:
        ordered_keys.extend(members[s])
    _require(len(ordered_keys) == len(create_order), "model_order dropped or duplicated a model")
    return ordered_keys


def _analyze(
    tree: ast.Module,
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
    model_order = build_model_order(create_order, scc_id, scc_topo)

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
    inlined_field_count = 0
    self_ref_count = 0

    # Fold every currently-deferred FK/O2O AddField into its owner's
    # CreateModel unless it is a genuine intra-SCC-cycle edge; leave
    # ManyToManyField AddField ops untouched (always deferred, matching
    # Django's own convention — they build a separate through-table, not
    # part of this FK ordering problem).
    remaining_add_field_ops: list[AddFieldOp] = []
    for af in add_fields:
        if af.field_type == "ManyToManyField":
            # Always a separate through-table op; Django's own autodetector
            # never inlines M2M into CreateModel either. Not part of the FK
            # ordering problem this script solves - left untouched.
            remaining_add_field_ops.append(af)
            continue

        tkey = target_key(af.to)
        owner_op = create_models[af.model_key]

        if tkey == af.model_key:
            # Self-referential FK/O2O: the table being created can reference
            # its own (not-yet-committed) rows in the same CREATE TABLE -
            # ordinary SQL, not a real ordering cycle. Always safe to inline.
            self_ref_count += 1
            owner_op.extra_field_entries.append(_field_entry_from_addfield(af))
            inlined_field_count += 1
            continue

        if (
            tkey is not None
            and scc_id[af.model_key] in non_trivial_sccs
            and scc_id.get(tkey) == scc_id[af.model_key]
        ):
            # Genuine intra-SCC cycle edge (both endpoints in the same
            # non-trivial SCC) - the only case that truly must stay deferred.
            remaining_add_field_ops.append(af)
            deferred_field_count += 1
            continue

        # Everything else: target is external/settings-based (tkey is None,
        # e.g. settings.AUTH_USER_MODEL or another already-migrated app), or
        # it is an intra-app model in a different SCC, which by construction
        # of the topological order was already created earlier - safe to
        # inline either way.
        owner_op.extra_field_entries.append(_field_entry_from_addfield(af))
        inlined_field_count += 1

    stats = {
        "models": len(create_order),
        "sccs_total": len(scc_members),
        "sccs_non_trivial": len(non_trivial_sccs),
        "self_ref_inlined": self_ref_count,
        "inlined_total": inlined_field_count,
        "deferred_addfield_cycle": deferred_field_count,
        "deferred_addfield_m2m": sum(1 for af in add_fields if af.field_type == "ManyToManyField"),
        "tail_ops": len(tail_ops),
        "create_model_ops": len(create_order),
    }

    return create_models, model_order, remaining_add_field_ops, tail_ops, stats


def rewrite(source: str, check_only: bool) -> tuple[str, dict]:
    tree = ast.parse(source)
    create_models, model_order, remaining_add_field_ops, tail_ops, stats = _analyze(tree)

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


def _create_model_call(op: CreateModelOp) -> ast.Call:
    """Rebuild a `CreateModel(...)` call node with any folded-in fields added."""
    fields_list = ast.List(
        elts=[*op.field_entries, *[e for e in op.extra_field_entries if e is not None]],
        ctx=ast.Load(),
    )
    kw = [ast.keyword(arg="name", value=ast.Constant(value=op.name))]
    kw.append(ast.keyword(arg="fields", value=fields_list))
    if op.options_node is not None:
        kw.append(ast.keyword(arg="options", value=op.options_node))
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


def rewrite_chunks(source: str, n_chunks: int) -> tuple[list[tuple[str, str]], dict]:
    """Split `source` into `n_chunks` cost-weighted migration files.

    Returns `(files, stats)` where `files` is `[(migration_name, content),
    ...]` in dependency-chain order (first is always "0001_initial").
    """
    tree = ast.parse(source)
    create_models, model_order, remaining_add_field_ops, tail_ops, stats = _analyze(tree)
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

    files = _render_chunk_files(source, tree, groups)
    stats = {**stats, "n_chunks": len(files), "chunk_sizes": [len(g) for g in groups]}
    return files, stats


def _render_chunk_files(
    source: str, tree: ast.Module, groups: list[list[ast.expr]]
) -> list[tuple[str, str]]:
    """Render each op group into a migration file's full source text.

    Chunk 1 keeps `0001_initial`'s original header (imports, header comment,
    `initial = True`, the original `dependencies` list) byte-identical via
    the same source-slicing technique as `emit_source`, with only its
    `operations` list shrunk to `groups[0]`. Chunks 2..N get a fresh minimal
    header built from the original file's imports block (reused verbatim,
    over-inclusive - `ruff check --fix` strips whatever a given chunk
    doesn't need) and a `dependencies = [("arxii", <previous chunk>)]`.
    """
    ops_assign = _find_operations_assign(tree)
    lines = source.splitlines(keepends=True)

    ops_list_node = ops_assign.value
    start_line, start_col = ops_list_node.lineno, ops_list_node.col_offset
    end_line, end_col = ops_list_node.end_lineno, ops_list_node.end_col_offset
    before = "".join(lines[: start_line - 1]) + lines[start_line - 1][:start_col]
    after = lines[end_line - 1][end_col:] + "".join(lines[end_line:])

    migration_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Migration"
    )
    imports_block = "".join(lines[: migration_class.lineno - 1])

    files: list[tuple[str, str]] = [("0001_initial", before + _unparse_ops_list(groups[0]) + after)]

    prev_name = "0001_initial"
    for i, group in enumerate(groups[1:], start=2):
        name = f"{i:04d}_initial_part_{i}"
        content = (
            f"{imports_block}\n"
            "class Migration(migrations.Migration):\n"
            "    dependencies = [\n"
            f'        ("{APP_LABEL}", "{prev_name}"),\n'
            "    ]\n\n"
            f"    operations = {_unparse_ops_list(group)}\n"
        )
        files.append((name, content))
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
        if p.name != "0001_initial.py" and "_initial_part_" not in p.name
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


def _run_chunk_mode(source: str, n_chunks: int) -> int:
    files, stats = rewrite_chunks(source, n_chunks)

    print("=== optimize_initial_migration chunk stats ===")
    for k, v in stats.items():
        if k != "chunk_sizes":
            print(f"{k}: {v}")
    print(f"chunk_sizes: {stats['chunk_sizes']}")

    migrations_dir = MIGRATION_PATH.parent

    # Discover the tail migrations (materialized views, later AlterFields,
    # ...) and the stale chunk artifacts from any previous run BEFORE
    # touching anything, so a rerun with a different N still works.
    old_part_files = sorted(migrations_dir.glob("*_initial_part_*.py"))
    tail_final_name = _renumber_tail_migrations(migrations_dir, files[-1][0], len(files))

    for p in old_part_files:
        p.unlink()

    written = _write_chunk_files(migrations_dir, files)

    max_migration_path = migrations_dir / "max_migration.txt"
    max_migration_path.write_text(tail_final_name + "\n")

    print(
        f"wrote {len(written)} chunk files (0001_initial.py .. "
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
    args = parser.parse_args()
    if args.chunks is not None and args.check:
        parser.error("--check and --chunks are mutually exclusive")

    source = MIGRATION_PATH.read_text()

    if args.chunks is not None:
        return _run_chunk_mode(source, args.chunks)

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
