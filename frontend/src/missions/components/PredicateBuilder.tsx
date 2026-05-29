/**
 * PredicateBuilder — visual editor for the missions predicate tree.
 *
 * Tree shape (matches world.missions.predicates.evaluate):
 * - {} = no gate (vacuously true)
 * - {op: "AND" | "OR", of: [node, ...]}
 * - {op: "NOT", of: [node]} (exactly one operand)
 * - {leaf: "<name>", params: {...}}
 *
 * Leaf catalog driven by D5's GET /api/missions/predicate-leaves/
 * (usePredicateLeaves hook). For each leaf type, the catalog tells us
 * its authored params with type tags; the builder renders one input
 * per param and COERCES the value before save based on the tag —
 * without this, int-typed leaves (e.g. min_character_level) crash
 * the entire offer_missions pipeline at evaluate time.
 *
 * Used by both the option's visibility_rule (E3 OptionPage), the
 * template's availability_rule (TemplateRuleSection on the detail
 * panel), and per-offering requirements_override (GiverEditor).
 */
import { useId } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import {
  useMissionGivers,
  usePredicateLeaves,
  type PredicateLeaf,
  type PredicateLeafParam,
  type PredicateParamType,
} from '../queries';

export type PredicateNode =
  | Record<string, never>
  | { op: 'AND' | 'OR'; of: PredicateNode[] }
  | { op: 'NOT'; of: [PredicateNode] }
  | { leaf: string; params: Record<string, unknown> };

export function isEmpty(node: PredicateNode): node is Record<string, never> {
  return Object.keys(node).length === 0;
}

export function isGroup(node: PredicateNode): node is Extract<PredicateNode, { op: string }> {
  return 'op' in node;
}

export function isLeaf(
  node: PredicateNode
): node is { leaf: string; params: Record<string, unknown> } {
  return 'leaf' in node;
}

/**
 * Validate that a tree is safe to send to the backend evaluator.
 *
 * Returns an empty array if valid; otherwise a list of human-readable
 * problems. The two crash-prone shapes the builder can produce on its
 * own:
 *   - {leaf: '', params: {...}} — empty leaf name → KeyError in
 *     LEAF_RESOLVERS, which is uncaught in _eligible_templates and
 *     takes out the whole offer_missions call.
 *   - {leaf: name, params: {x: ''}} — required param left blank.
 *     Whether this crashes depends on the resolver, but it's never
 *     correct authoring intent — flag it.
 */
export function validatePredicate(node: PredicateNode, leaves: readonly PredicateLeaf[]): string[] {
  const errors: string[] = [];
  walk(node, errors, leaves);
  return errors;
}

function walk(
  node: PredicateNode,
  errors: string[],
  leaves: readonly PredicateLeaf[],
  path = 'root'
): void {
  if (isEmpty(node)) return;
  if (isGroup(node)) {
    if (node.op === 'NOT' && node.of.length !== 1) {
      errors.push(`${path}: NOT must have exactly one operand.`);
    }
    node.of.forEach((child, i) => walk(child, errors, leaves, `${path}.${node.op}[${i}]`));
    return;
  }
  if (isLeaf(node)) {
    if (!node.leaf) {
      errors.push(`${path}: leaf type must be picked (empty leaf would crash evaluator).`);
      return;
    }
    const catalog = leaves.find((l) => l.name === node.leaf);
    if (!catalog) {
      errors.push(`${path}: unknown leaf "${node.leaf}".`);
      return;
    }
    for (const param of catalog.params) {
      const v = node.params[param.name];
      if (v === undefined || v === null || v === '') {
        errors.push(`${path}: param "${param.name}" is required.`);
      }
    }
    return;
  }
}

/**
 * Coerce a tree's leaf params to their declared types before save.
 *
 * Leaf params come from <Input> which gives strings; the backend
 * resolvers expect int / bool / float per the D5 catalog's type tags.
 * Returns a new tree; does not mutate. Unknown leaves are returned
 * as-is (validatePredicate will flag them separately).
 */
export function coercePredicate(
  node: PredicateNode,
  leaves: readonly PredicateLeaf[]
): PredicateNode {
  if (isEmpty(node)) return node;
  if (isGroup(node)) {
    return { ...node, of: node.of.map((c) => coercePredicate(c, leaves)) } as PredicateNode;
  }
  if (isLeaf(node)) {
    const catalog = leaves.find((l) => l.name === node.leaf);
    if (!catalog) return node;
    const params: Record<string, unknown> = {};
    for (const p of catalog.params) {
      params[p.name] = coerceValue(node.params[p.name], p.type);
    }
    return { leaf: node.leaf, params };
  }
  return node;
}

function coerceValue(raw: unknown, type: PredicateParamType): unknown {
  if (raw === undefined || raw === null || raw === '') return raw;
  const s = String(raw);
  switch (type) {
    case 'int': {
      const n = parseInt(s, 10);
      return Number.isNaN(n) ? raw : n;
    }
    case 'float': {
      const n = parseFloat(s);
      return Number.isNaN(n) ? raw : n;
    }
    case 'bool':
      return s === 'true' || s === '1';
    case 'str':
    default:
      return s;
  }
}

interface PredicateBuilderProps {
  value: PredicateNode;
  onChange: (next: PredicateNode) => void;
  /** Optional label rendered above the builder (e.g. "Availability rule"). */
  label?: string;
}

export function PredicateBuilder({ value, onChange, label }: PredicateBuilderProps) {
  const leaves = usePredicateLeaves();
  const builderId = useId();

  return (
    <div className="space-y-2" data-testid="predicate-builder">
      {label ? <div className="text-sm font-medium">{label}</div> : null}
      <NodeView
        value={value}
        onChange={onChange}
        leaves={leaves.data ?? []}
        depth={0}
        builderId={builderId}
      />
    </div>
  );
}

function NodeView({
  value,
  onChange,
  leaves,
  depth,
  builderId,
}: {
  value: PredicateNode;
  onChange: (next: PredicateNode) => void;
  leaves: readonly PredicateLeaf[];
  depth: number;
  builderId: string;
}) {
  if (isEmpty(value)) {
    return (
      <EmptySlot
        onAddGroup={() => onChange({ op: 'AND', of: [] })}
        onAddLeaf={() => onChange({ leaf: '', params: {} })}
      />
    );
  }
  if (isGroup(value)) {
    return (
      <GroupView
        value={value}
        onChange={onChange}
        leaves={leaves}
        depth={depth}
        builderId={builderId}
      />
    );
  }
  if (isLeaf(value)) {
    return (
      <LeafView
        value={value}
        leaves={leaves}
        onChange={onChange}
        onRemove={() => onChange({})}
        builderId={builderId}
      />
    );
  }
  return null;
}

function EmptySlot({ onAddGroup, onAddLeaf }: { onAddGroup: () => void; onAddLeaf: () => void }) {
  return (
    <div className="flex gap-2">
      <Button size="sm" variant="outline" onClick={onAddGroup}>
        + Group
      </Button>
      <Button size="sm" variant="outline" onClick={onAddLeaf}>
        + Leaf
      </Button>
    </div>
  );
}

function GroupView({
  value,
  onChange,
  leaves,
  depth,
  builderId,
}: {
  value: { op: 'AND' | 'OR' | 'NOT'; of: PredicateNode[] };
  onChange: (next: PredicateNode) => void;
  leaves: readonly PredicateLeaf[];
  depth: number;
  builderId: string;
}) {
  const setOp = (op: 'AND' | 'OR' | 'NOT') => {
    if (op === 'NOT') {
      // NOT must have exactly one operand. If the user is converting
      // an AND/OR with more than one child, surface the destructive
      // consequence rather than silently dropping the trailing operands.
      if (value.of.length > 1) {
        const ok = confirm(
          `Switching to NOT will keep only the first operand and drop the other ${
            value.of.length - 1
          }. Continue?`
        );
        if (!ok) return;
      }
      onChange({ op: 'NOT', of: [value.of[0] ?? {}] } as PredicateNode);
      return;
    }
    onChange({ op, of: value.of } as PredicateNode);
  };

  const setChild = (idx: number, child: PredicateNode) => {
    const nextOf = [...value.of];
    nextOf[idx] = child;
    onChange({ op: value.op, of: nextOf } as PredicateNode);
  };

  const addChild = () => {
    onChange({ op: value.op, of: [...value.of, {}] } as PredicateNode);
  };

  const removeChild = (idx: number) => {
    const nextOf = value.of.filter((_, i) => i !== idx);
    onChange({ op: value.op, of: nextOf } as PredicateNode);
  };

  const isNot = value.op === 'NOT';

  return (
    <div
      className="space-y-2 rounded border-l-2 border-primary/40 bg-muted/20 p-2"
      style={{ marginLeft: depth > 0 ? '0.5rem' : undefined }}
      data-testid="predicate-group"
    >
      <div className="flex items-center gap-2">
        <Label className="text-xs">Operator</Label>
        <Select value={value.op} onValueChange={(v) => setOp(v as 'AND' | 'OR' | 'NOT')}>
          <SelectTrigger className="h-7 w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="AND">AND</SelectItem>
            <SelectItem value="OR">OR</SelectItem>
            <SelectItem value="NOT">NOT</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" variant="ghost" onClick={() => onChange({})} aria-label="Remove group">
          ✕
        </Button>
      </div>
      <div className="space-y-2 pl-2">
        {value.of.map((child, idx) => (
          <div key={idx} className="flex items-start gap-1">
            <div className="flex-1">
              <NodeView
                value={child}
                onChange={(next) => setChild(idx, next)}
                leaves={leaves}
                depth={depth + 1}
                builderId={builderId}
              />
            </div>
            {!isNot ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => removeChild(idx)}
                aria-label="Remove child"
              >
                −
              </Button>
            ) : null}
          </div>
        ))}
        {!isNot || value.of.length === 0 ? (
          <Button size="sm" variant="outline" onClick={addChild}>
            + Add child
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function LeafView({
  value,
  leaves,
  onChange,
  onRemove,
  builderId,
}: {
  value: { leaf: string; params: Record<string, unknown> };
  leaves: readonly PredicateLeaf[];
  onChange: (next: PredicateNode) => void;
  onRemove: () => void;
  builderId: string;
}) {
  const currentLeaf = leaves.find((l) => l.name === value.leaf);

  const setLeafName = (name: string) => {
    // Reset params when leaf changes — old params likely don't apply.
    onChange({ leaf: name, params: {} });
  };

  const setParam = (key: string, raw: string) => {
    const next = { ...value.params, [key]: raw };
    onChange({ leaf: value.leaf, params: next });
  };

  const empty = !value.leaf;

  return (
    <div
      className={`space-y-2 rounded border bg-card p-2 ${empty ? 'border-destructive/60' : ''}`}
      data-testid="predicate-leaf"
      data-empty={empty ? 'true' : 'false'}
    >
      <div className="flex items-center gap-2">
        <Badge variant={empty ? 'destructive' : 'outline'}>leaf</Badge>
        <Select value={value.leaf} onValueChange={setLeafName}>
          <SelectTrigger className="h-7 w-64">
            <SelectValue placeholder="Pick a leaf type…" />
          </SelectTrigger>
          <SelectContent>
            {leaves.map((l) => (
              <SelectItem key={l.name} value={l.name}>
                {l.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" variant="ghost" onClick={onRemove} aria-label="Remove leaf">
          ✕
        </Button>
      </div>
      {empty ? (
        <div className="text-xs text-destructive">
          Pick a leaf type — saving with an empty leaf will crash availability checks.
        </div>
      ) : null}
      {currentLeaf && currentLeaf.params.length > 0 ? (
        <div className="grid gap-2 pl-2 md:grid-cols-2">
          {currentLeaf.params.map((p: PredicateLeafParam) => {
            // Per-builder id prefix prevents DOM collisions when several
            // PredicateBuilders mount on one page (e.g. multiple offerings
            // each with their own requirements_override).
            const inputId = `${builderId}-leaf-${value.leaf}-${p.name}`;
            const raw = value.params[p.name];
            // Special-case params that reference a giver by PK — render a
            // name-bearing picker instead of a bare number input so authors
            // see who they're referencing (issue #577).
            if (p.name === 'giver_id') {
              return (
                <GiverIdParamPicker
                  key={p.name}
                  id={inputId}
                  paramName={p.name}
                  paramType={p.type}
                  value={raw}
                  onChange={(next) => setParam(p.name, next)}
                />
              );
            }
            const display = raw === undefined || raw === null ? '' : String(raw);
            return (
              <div key={p.name}>
                <Label className="text-xs" htmlFor={inputId}>
                  {p.name} <span className="text-muted-foreground">({p.type})</span>
                </Label>
                <Input
                  id={inputId}
                  type={p.type === 'int' || p.type === 'float' ? 'number' : 'text'}
                  value={display}
                  onChange={(e) => setParam(p.name, e.target.value)}
                />
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function GiverIdParamPicker({
  id,
  paramName,
  paramType,
  value,
  onChange,
}: {
  id: string;
  paramName: string;
  paramType: PredicateParamType;
  value: unknown;
  onChange: (next: string) => void;
}) {
  // useMissionGivers returns the cached first page. If the dataset ever
  // grows past one page we can swap to a search-as-you-type input; not
  // worth the complexity today.
  const { data, isLoading, isError } = useMissionGivers();
  const givers = data?.results ?? [];
  const current = value === undefined || value === null ? '' : String(value);
  return (
    <div>
      <Label className="text-xs" htmlFor={id}>
        {paramName} <span className="text-muted-foreground">({paramType})</span>
      </Label>
      <Select value={current} onValueChange={(v) => onChange(v)}>
        <SelectTrigger id={id}>
          <SelectValue placeholder={isLoading ? 'Loading givers…' : 'Pick a giver…'} />
        </SelectTrigger>
        <SelectContent>
          {isError ? (
            <div className="px-2 py-1 text-xs text-destructive">Failed to load givers.</div>
          ) : (
            givers.map((g) => (
              <SelectItem key={g.id} value={String(g.id)}>
                {g.name} <span className="text-muted-foreground">(#{g.id})</span>
              </SelectItem>
            ))
          )}
        </SelectContent>
      </Select>
    </div>
  );
}
