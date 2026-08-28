/**
 * filterTree.ts — pure tree ops / validation for the trigger filter-condition
 * DSL (#3417 task 12).
 *
 * Shape mirrors `src/flows/filters/evaluator.py` exactly: a leaf is
 * `{path, op, value}`; a group is `{and: Filter[]}` | `{or: Filter[]}` |
 * `{not: Filter}`. `null` represents "no filter" — the backend's
 * `base_filter_condition`/`additional_filter_condition` fields are nullable
 * and `evaluate_filter` treats an absent/empty filter as "always matches"
 * (`if not filter_spec: return True`). This is NOT the same shape as
 * missions' `PredicateBuilder.tsx`, whose `{}` node IS itself a valid
 * "vacuously true" tree member reachable at any depth — here there is no
 * such variant, so a group's children are always concrete leaves/groups and
 * "no filter" only exists at the root.
 *
 * `op` is validated against the DSL catalog's `filter_ops` list
 * (`DslCatalog.filter_ops`, `src/flows/catalog.py`'s `FILTER_OPS`). `path`
 * is validated only for non-emptiness here: the backend
 * (`src/flows/filters/validator.py`) checks just the first dotted segment
 * against the event's payload schema and skips `self.*` paths entirely, so
 * there is no deeper client-side check to mirror without duplicating
 * backend schema knowledge this module doesn't have.
 */

export interface FilterLeaf {
  path: string;
  op: string;
  value: unknown;
}
export interface FilterAnd {
  and: FilterNode[];
}
export interface FilterOr {
  or: FilterNode[];
}
export interface FilterNot {
  not: FilterNode;
}
export type FilterGroup = FilterAnd | FilterOr | FilterNot;
export type FilterNode = FilterGroup | FilterLeaf;

export function isLeaf(node: FilterNode): node is FilterLeaf {
  return 'path' in node;
}
export function isAnd(node: FilterNode): node is FilterAnd {
  return 'and' in node;
}
export function isOr(node: FilterNode): node is FilterOr {
  return 'or' in node;
}
export function isNot(node: FilterNode): node is FilterNot {
  return 'not' in node;
}
export function isGroup(node: FilterNode): node is FilterGroup {
  return isAnd(node) || isOr(node) || isNot(node);
}

export function emptyLeaf(): FilterLeaf {
  return { path: '', op: '', value: '' };
}

export function emptyGroup(op: 'and' | 'or'): FilterAnd | FilterOr {
  return op === 'and' ? { and: [] } : { or: [] };
}

/** Children of a group, in order — a `not` group's single operand as a one-element array. */
export function childrenOf(group: FilterGroup): FilterNode[] {
  if (isAnd(group)) return group.and;
  if (isOr(group)) return group.or;
  return [group.not];
}

/** Append `child` (default: a blank leaf) to an `and`/`or` group. */
export function addChild(
  group: FilterAnd | FilterOr,
  child: FilterNode = emptyLeaf()
): FilterAnd | FilterOr {
  if (isAnd(group)) return { and: [...group.and, child] };
  return { or: [...group.or, child] };
}

/** Remove the child at `index` from an `and`/`or` group. */
export function removeChild(group: FilterAnd | FilterOr, index: number): FilterAnd | FilterOr {
  if (isAnd(group)) return { and: group.and.filter((_, i) => i !== index) };
  return { or: group.or.filter((_, i) => i !== index) };
}

/** Replace the child at `index` in an `and`/`or` group. */
export function setChild(
  group: FilterAnd | FilterOr,
  index: number,
  child: FilterNode
): FilterAnd | FilterOr {
  if (isAnd(group)) {
    const next = [...group.and];
    next[index] = child;
    return { and: next };
  }
  const next = [...group.or];
  next[index] = child;
  return { or: next };
}

/** Replace a `not` group's single operand. */
export function setNotChild(_node: FilterNot, child: FilterNode): FilterNot {
  return { not: child };
}

/**
 * Switch a group's operator, preserving children where the arity allows it.
 * Converting AND/OR -> NOT keeps only the FIRST child (NOT takes exactly one
 * operand, per `evaluator.py`'s `OP_NOT` handling) — the caller (the
 * component) is responsible for confirming the drop with the author when
 * there's more than one child to lose, the same split of responsibility as
 * `missions/PredicateBuilder.tsx`'s `setOp` (its `confirm()` call lives in
 * the component; the arity-safe conversion itself is pure here). Converting
 * NOT -> AND/OR wraps its single operand in a one-element list.
 */
export function changeOperator(node: FilterGroup, nextOp: 'and' | 'or' | 'not'): FilterGroup {
  const children = childrenOf(node);
  if (nextOp === 'not') return { not: children[0] ?? emptyLeaf() };
  if (nextOp === 'and') return { and: children };
  return { or: children };
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/**
 * Validate a filter tree against the catalog's known ops. Returns an empty
 * array when the tree is safe to save; otherwise one message per problem
 * found (collects every problem, unlike the backend which raises on the
 * first `ValidationError`).
 *
 * `null` (no filter) is always valid — see the module docstring.
 */
export function validateFilter(
  node: FilterNode | null,
  ops: readonly string[],
  path = 'root'
): string[] {
  if (node === null) return [];
  const errors: string[] = [];
  walk(node, ops, errors, path);
  return errors;
}

function walk(node: FilterNode, ops: readonly string[], errors: string[], path: string): void {
  if (isNot(node)) {
    walk(node.not, ops, errors, `${path}.not`);
    return;
  }
  if (isAnd(node)) {
    node.and.forEach((child, i) => walk(child, ops, errors, `${path}.and[${i}]`));
    return;
  }
  if (isOr(node)) {
    node.or.forEach((child, i) => walk(child, ops, errors, `${path}.or[${i}]`));
    return;
  }
  if (!node.path.trim()) {
    errors.push(`${path}: path must be set.`);
  }
  if (!node.op) {
    errors.push(`${path}: operator must be picked.`);
  } else if (!ops.includes(node.op)) {
    errors.push(`${path}: unknown operator '${node.op}'.`);
  }
}

// ---------------------------------------------------------------------------
// Server <-> client shape mapping
// ---------------------------------------------------------------------------

/**
 * The wire shape is identical to `FilterNode | null` — no field renaming and
 * no client-only ids to strip (unlike `stepTree.ts`'s `ClientStep`). These
 * are still named, exported functions rather than a bare pass-through at
 * each call site so the API boundary has one clear place to change if that
 * ever stops being true, and so the round trip is asserted explicitly in
 * tests rather than assumed.
 */
export function toApiFilter(node: FilterNode | null): unknown {
  return node;
}

export function fromApiFilter(value: unknown): FilterNode | null {
  if (value === null || value === undefined) return null;
  return value as FilterNode;
}
