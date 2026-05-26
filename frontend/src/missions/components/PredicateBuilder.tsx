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
 * its authored params; the builder renders one input per param.
 *
 * Used by both the option's visibility_rule (E3 OptionPage) and the
 * template's availability_rule (browse / detail) — same component,
 * different consumer.
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

import { usePredicateLeaves, type PredicateLeaf } from '../queries';

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

interface PredicateBuilderProps {
  value: PredicateNode;
  onChange: (next: PredicateNode) => void;
  /** Optional label rendered above the builder (e.g. "Availability rule"). */
  label?: string;
}

export function PredicateBuilder({ value, onChange, label }: PredicateBuilderProps) {
  const leaves = usePredicateLeaves();
  const headingId = useId();

  return (
    <div className="space-y-2" data-testid="predicate-builder">
      {label ? (
        <div id={headingId} className="text-sm font-medium">
          {label}
        </div>
      ) : null}
      <NodeView value={value} onChange={onChange} leaves={leaves.data ?? []} depth={0} />
    </div>
  );
}

function NodeView({
  value,
  onChange,
  leaves,
  depth,
}: {
  value: PredicateNode;
  onChange: (next: PredicateNode) => void;
  leaves: readonly PredicateLeaf[];
  depth: number;
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
    return <GroupView value={value} onChange={onChange} leaves={leaves} depth={depth} />;
  }
  if (isLeaf(value)) {
    return (
      <LeafView value={value} leaves={leaves} onChange={onChange} onRemove={() => onChange({})} />
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
}: {
  value: { op: 'AND' | 'OR' | 'NOT'; of: PredicateNode[] };
  onChange: (next: PredicateNode) => void;
  leaves: readonly PredicateLeaf[];
  depth: number;
}) {
  const setOp = (op: 'AND' | 'OR' | 'NOT') => {
    if (op === 'NOT') {
      // NOT must have exactly one operand.
      const next: PredicateNode = {
        op: 'NOT',
        of: [value.of[0] ?? {}] as [PredicateNode],
      };
      onChange(next);
      return;
    }
    onChange({ op, of: value.of });
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
}: {
  value: { leaf: string; params: Record<string, unknown> };
  leaves: readonly PredicateLeaf[];
  onChange: (next: PredicateNode) => void;
  onRemove: () => void;
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

  return (
    <div className="space-y-2 rounded border bg-card p-2" data-testid="predicate-leaf">
      <div className="flex items-center gap-2">
        <Badge variant="outline">leaf</Badge>
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
      {currentLeaf && currentLeaf.params.length > 0 ? (
        <div className="grid gap-2 pl-2 md:grid-cols-2">
          {currentLeaf.params.map((paramName: string) => (
            <div key={paramName}>
              <Label className="text-xs" htmlFor={`leaf-${value.leaf}-${paramName}`}>
                {paramName}
              </Label>
              <Input
                id={`leaf-${value.leaf}-${paramName}`}
                value={String(value.params[paramName] ?? '')}
                onChange={(e) => setParam(paramName, e.target.value)}
              />
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
