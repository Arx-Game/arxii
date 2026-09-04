/**
 * FilterConditionBuilder — visual editor for the trigger filter-condition
 * DSL (#3417 task 12).
 *
 * Shaped after `missions/components/PredicateBuilder.tsx`'s recursive
 * group/leaf editor, adapted for `filterTree.ts`'s and/or/not/leaf shape
 * (no `{}` "empty" node reachable below the root — see that module's
 * docstring). `value: null` renders an empty-slot ("+ Group" / "+
 * Condition"); a populated tree renders a "Clear filter" control alongside
 * the recursive `NodeView` rather than letting a nested group null itself
 * out — only the whole filter is optional, a group's children never are.
 *
 * The leaf's path field follows `StepParamInputs.tsx`'s
 * `ServiceFunctionField` pattern: a `Combobox` over the selected event's
 * declared payload fields, plus a free-text input for dotted/`self.*`
 * paths the backend accepts but doesn't enumerate (`pathFields` is only
 * ever one level deep — see `EventCatalogEntry.payload_fields`).
 */
import { useId } from 'react';

import { Button } from '@/components/ui/button';
import { Combobox, type ComboboxItem } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toDisplayString } from '@/lib/displayValue';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import {
  addChild,
  changeOperator,
  childrenOf,
  emptyGroup,
  emptyLeaf,
  isAnd,
  isGroup,
  removeChild,
  setChild,
  setNotChild,
  type FilterAnd,
  type FilterGroup,
  type FilterLeaf,
  type FilterNode,
  type FilterNot,
  type FilterOr,
} from '../filterTree';

interface PathFieldOption {
  name: string;
  type: string;
}

interface FilterConditionBuilderProps {
  value: FilterNode | null;
  onChange: (next: FilterNode | null) => void;
  /** `DslCatalog.filter_ops`. */
  filterOps: readonly string[];
  /** The selected event's `payload_fields` (empty when no event is picked yet). */
  pathFields: PathFieldOption[];
  /** Optional label rendered above the builder (e.g. "Filter condition"). */
  label?: string;
}

export function FilterConditionBuilder({
  value,
  onChange,
  filterOps,
  pathFields,
  label,
}: FilterConditionBuilderProps) {
  const builderId = useId();

  if (value === null) {
    return (
      <div className="space-y-2" data-testid="filter-condition-builder">
        {label ? <div className="text-sm font-medium">{label}</div> : null}
        <EmptySlot
          onAddGroup={() => onChange(emptyGroup('and'))}
          onAddLeaf={() => onChange(emptyLeaf())}
        />
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="filter-condition-builder">
      <div className="flex items-center justify-between">
        {label ? <div className="text-sm font-medium">{label}</div> : <span />}
        <Button size="sm" variant="ghost" onClick={() => onChange(null)}>
          Clear filter
        </Button>
      </div>
      <NodeView
        value={value}
        onChange={onChange}
        filterOps={filterOps}
        pathFields={pathFields}
        depth={0}
        builderId={builderId}
      />
    </div>
  );
}

function EmptySlot({ onAddGroup, onAddLeaf }: { onAddGroup: () => void; onAddLeaf: () => void }) {
  return (
    <div className="flex gap-2">
      <Button size="sm" variant="outline" onClick={onAddGroup}>
        + Group
      </Button>
      <Button size="sm" variant="outline" onClick={onAddLeaf}>
        + Condition
      </Button>
    </div>
  );
}

function NodeView({
  value,
  onChange,
  filterOps,
  pathFields,
  depth,
  builderId,
}: {
  value: FilterNode;
  onChange: (next: FilterNode) => void;
  filterOps: readonly string[];
  pathFields: PathFieldOption[];
  depth: number;
  builderId: string;
}) {
  if (isGroup(value)) {
    return (
      <GroupView
        value={value}
        onChange={onChange}
        filterOps={filterOps}
        pathFields={pathFields}
        depth={depth}
        builderId={builderId}
      />
    );
  }
  return (
    <LeafView
      value={value}
      onChange={onChange}
      filterOps={filterOps}
      pathFields={pathFields}
      builderId={builderId}
    />
  );
}

/** Which boolean operator a filter node is, read off its shape. */
function operatorOf(value: FilterNode): 'and' | 'or' | 'not' {
  if (isAnd(value)) return 'and';
  if ('or' in value) return 'or';
  return 'not';
}

function GroupView({
  value,
  onChange,
  filterOps,
  pathFields,
  depth,
  builderId,
}: {
  value: FilterGroup;
  onChange: (next: FilterNode) => void;
  filterOps: readonly string[];
  pathFields: PathFieldOption[];
  depth: number;
  builderId: string;
}) {
  const op: 'and' | 'or' | 'not' = operatorOf(value);
  const children = childrenOf(value);

  const setOp = (nextOp: 'and' | 'or' | 'not') => {
    if (nextOp === 'not' && children.length > 1) {
      const ok = window.confirm(
        `Switching to NOT keeps only the first condition and drops the other ${
          children.length - 1
        }. Continue?`
      );
      if (!ok) return;
    }
    onChange(changeOperator(value, nextOp));
  };

  const setChildAt = (idx: number, child: FilterNode) => {
    if (op === 'not') {
      onChange(setNotChild(value as FilterNot, child));
      return;
    }
    onChange(setChild(value as FilterAnd | FilterOr, idx, child));
  };

  const addLeaf = () => onChange(addChild(value as FilterAnd | FilterOr, emptyLeaf()));
  const addGroup = () => onChange(addChild(value as FilterAnd | FilterOr, emptyGroup('and')));
  const removeChildAt = (idx: number) => onChange(removeChild(value as FilterAnd | FilterOr, idx));

  return (
    <div
      className="space-y-2 rounded border-l-2 border-primary/40 bg-muted/20 p-2"
      style={{ marginLeft: depth > 0 ? '0.5rem' : undefined }}
      data-testid="filter-group"
    >
      <div className="flex items-center gap-2">
        <Label className="text-xs">Operator</Label>
        <Select value={op} onValueChange={(v) => setOp(v as 'and' | 'or' | 'not')}>
          <SelectTrigger className="h-7 w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="and">AND</SelectItem>
            <SelectItem value="or">OR</SelectItem>
            <SelectItem value="not">NOT</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2 pl-2">
        {children.map((child, idx) => (
          // Children are addressed by position, not identity — the tree
          // carries no client-only ids (see filterTree.ts's docstring), so
          // an index key is the only option, same as PredicateBuilder.
          <div key={idx} className="flex items-start gap-1">
            <div className="flex-1">
              <NodeView
                value={child}
                onChange={(next) => setChildAt(idx, next)}
                filterOps={filterOps}
                pathFields={pathFields}
                depth={depth + 1}
                builderId={builderId}
              />
            </div>
            {op !== 'not' ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => removeChildAt(idx)}
                aria-label="Remove condition"
              >
                −
              </Button>
            ) : null}
          </div>
        ))}
        {op !== 'not' ? (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={addLeaf}>
              + Add condition
            </Button>
            <Button size="sm" variant="outline" onClick={addGroup}>
              + Add group
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

type ValueKind = 'string' | 'number' | 'boolean' | 'json';

function inferValueKind(value: unknown): ValueKind {
  if (typeof value === 'number') return 'number';
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'string') return 'string';
  return 'json';
}

function displayValue(value: unknown, kind: ValueKind): string {
  if (kind === 'json') return JSON.stringify(value ?? null);
  return toDisplayString(value);
}

/** `value` may be "self" or "self.<dotted>" (evaluator.py's `_resolve_value`) — both are plain strings here. */
function coerceValueInput(raw: string, kind: ValueKind): unknown {
  switch (kind) {
    case 'number': {
      const n = Number(raw);
      return Number.isNaN(n) ? raw : n;
    }
    case 'boolean':
      return raw === 'true';
    case 'json':
      try {
        return JSON.parse(raw);
      } catch {
        return raw;
      }
    case 'string':
    default:
      return raw;
  }
}

function LeafView({
  value,
  onChange,
  filterOps,
  pathFields,
  builderId,
}: {
  value: FilterLeaf;
  onChange: (next: FilterNode) => void;
  filterOps: readonly string[];
  pathFields: PathFieldOption[];
  builderId: string;
}) {
  const empty = !value.path.trim();
  const opInvalid = value.op !== '' && !filterOps.includes(value.op);
  const kind = inferValueKind(value.value);
  const inputId = `${builderId}-leaf-${value.path}`;

  const setPath = (path: string) => onChange({ ...value, path });
  const setOp = (op: string) => onChange({ ...value, op });
  const setValueRaw = (raw: string) => onChange({ ...value, value: coerceValueInput(raw, kind) });
  const setKind = (nextKind: ValueKind) =>
    onChange({ ...value, value: coerceValueInput(displayValue(value.value, kind), nextKind) });

  const pathItems: ComboboxItem[] = pathFields.map((f) => ({
    value: f.name,
    label: f.name,
    secondaryText: f.type,
  }));
  const knownPath = pathFields.some((f) => f.name === value.path);

  return (
    <div
      className={`space-y-2 rounded border bg-card p-2 ${
        empty || opInvalid ? 'border-destructive/60' : ''
      }`}
      data-testid="filter-leaf"
      data-empty={empty ? 'true' : 'false'}
    >
      <div className="grid gap-2 md:grid-cols-3">
        <div className="space-y-1">
          <Label className="text-xs" htmlFor={`${inputId}-path`}>
            Path
          </Label>
          <Combobox
            items={pathItems}
            value={knownPath ? value.path : ''}
            onValueChange={setPath}
            placeholder="Pick a payload field…"
            emptyMessage="No match — type a dotted path below."
          />
          <Input
            id={`${inputId}-path`}
            aria-label="Path (free text)"
            placeholder="or type a dotted / self.* path…"
            value={value.path}
            onChange={(e) => setPath(e.target.value)}
            className="h-8"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs" htmlFor={`${inputId}-op`}>
            Operator
          </Label>
          <Select value={value.op} onValueChange={setOp}>
            <SelectTrigger id={`${inputId}-op`} className="h-8">
              <SelectValue placeholder="Pick an operator…" />
            </SelectTrigger>
            <SelectContent>
              {filterOps.map((op) => (
                <SelectItem key={op} value={op}>
                  {op}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs" htmlFor={`${inputId}-value`}>
            Value
          </Label>
          <div className="flex gap-1">
            <Input
              id={`${inputId}-value`}
              value={displayValue(value.value, kind)}
              onChange={(e) => setValueRaw(e.target.value)}
              className="h-8"
            />
            <Select value={kind} onValueChange={(v) => setKind(v as ValueKind)}>
              <SelectTrigger className="h-8 w-20" aria-label="Value type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="string">text</SelectItem>
                <SelectItem value="number">number</SelectItem>
                <SelectItem value="boolean">bool</SelectItem>
                <SelectItem value="json">JSON</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
      {empty ? <div className="text-xs text-destructive">Path is required.</div> : null}
      {opInvalid ? (
        <div className="text-xs text-destructive">Unknown operator '{value.op}'.</div>
      ) : null}
    </div>
  );
}
