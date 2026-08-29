/**
 * FlowStepTree — visual editor for a flow's authored step tree (#3417 task 10).
 *
 * Architectural template: `missions/components/PredicateBuilder.tsx` — a
 * catalog-driven recursive node editor that lifts all state to the parent
 * via a single `value`/`onChange` pair. Tree ops (add/remove/move) and
 * type coercion live in `../stepTree.ts`, which mirrors
 * `flows.step_validation.validate_step_tree` so a tree that renders here
 * cleanly also saves cleanly.
 *
 * A step tree needs exactly one root (see `stepTree.ts#validateSteps`
 * rule 2-3, mirroring the backend), so the root-level "add step" control
 * only appears while the tree is empty; every step after that grows by
 * adding children under an existing node.
 */
import { useId } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { useDslCatalog } from '../queries';
import { addStep, childrenOf, conditionalOpSymbol, moveStep, removeStep } from '../stepTree';
import type { ClientStep, DslCatalog, StepActionSpec } from '../types';
import { ServiceFunctionField, StepParamInputs } from './StepParamInputs';

const VARIABLE_NAME_LABELS: Record<string, string> = {
  flow_variable: 'Variable name',
  object_pk_variable: 'Object (variable name)',
  service_function_name: 'Service function',
  event_store_key: 'Store event as',
};

interface FlowStepTreeProps {
  value: ClientStep[];
  onChange: (next: ClientStep[]) => void;
}

export function FlowStepTree({ value, onChange }: FlowStepTreeProps) {
  const catalogQuery = useDslCatalog();
  const treeId = useId();

  if (catalogQuery.isLoading) {
    return <div className="text-sm text-muted-foreground">Loading step catalog…</div>;
  }
  if (catalogQuery.isError || !catalogQuery.data) {
    return <div className="text-sm text-destructive">Failed to load the flows DSL catalog.</div>;
  }

  const catalog = catalogQuery.data;
  const specsByAction = new Map(catalog.actions.map((spec) => [spec.action, spec]));
  const roots = childrenOf(value, null);

  const handleAdd = (parentId: string | null, action: string) => {
    const spec = specsByAction.get(action);
    if (!spec) return;
    onChange(addStep(value, parentId, action, spec));
  };
  const handleRemove = (clientId: string) => onChange(removeStep(value, clientId));
  const handleMove = (clientId: string, direction: 'up' | 'down') =>
    onChange(moveStep(value, clientId, direction));
  const handleStepChange = (next: ClientStep) =>
    onChange(value.map((step) => (step.clientId === next.clientId ? next : step)));

  return (
    <div className="space-y-2" data-testid="flow-step-tree">
      {roots.map((step, index) => (
        <StepNode
          key={step.clientId}
          step={step}
          steps={value}
          catalog={catalog}
          specsByAction={specsByAction}
          isFirst={index === 0}
          isLast={index === roots.length - 1}
          treeId={treeId}
          onAdd={handleAdd}
          onRemove={handleRemove}
          onMove={handleMove}
          onStepChange={handleStepChange}
        />
      ))}
      {roots.length === 0 ? (
        <AddActionSelect
          key={`root-add-${value.length}`}
          actions={catalog.actions}
          onAdd={(action) => handleAdd(null, action)}
          placeholder="+ Add first step…"
        />
      ) : null}
    </div>
  );
}

function StepNode({
  step,
  steps,
  catalog,
  specsByAction,
  isFirst,
  isLast,
  treeId,
  onAdd,
  onRemove,
  onMove,
  onStepChange,
}: {
  step: ClientStep;
  steps: ClientStep[];
  catalog: DslCatalog;
  specsByAction: Map<string, StepActionSpec>;
  isFirst: boolean;
  isLast: boolean;
  treeId: string;
  onAdd: (parentId: string | null, action: string) => void;
  onRemove: (clientId: string) => void;
  onMove: (clientId: string, direction: 'up' | 'down') => void;
  onStepChange: (next: ClientStep) => void;
}) {
  const spec = specsByAction.get(step.action);
  const nodeId = `${treeId}-${step.clientId}`;
  const actionSelectId = `${nodeId}-action`;
  const variableInputId = `${nodeId}-variable`;
  const children = childrenOf(steps, step.clientId);
  const isConditional = spec?.is_conditional ?? false;

  const handleActionChange = (action: string) => {
    // Params and variable_name meanings are action-specific (see
    // VariableNameRole) — reset both rather than carrying over stale
    // values that likely don't apply to the new action.
    onStepChange({ ...step, action, variableName: '', parameters: {} });
  };

  return (
    <div
      className="space-y-2 rounded border bg-card p-2"
      style={{ marginLeft: '0.5rem' }}
      data-testid="flow-step-node"
    >
      <div className="flex items-center gap-2">
        {isConditional ? (
          <div className="text-sm font-medium">
            if <code>{step.variableName || '…'}</code> {conditionalOpSymbol(step.action)}{' '}
            <code>{formatConditionValue(step.parameters.value)}</code>
          </div>
        ) : (
          <div className="text-sm font-medium">{spec?.label ?? step.action}</div>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            disabled={isFirst}
            onClick={() => onMove(step.clientId, 'up')}
            aria-label="Move step up"
          >
            ↑
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={isLast}
            onClick={() => onMove(step.clientId, 'down')}
            aria-label="Move step down"
          >
            ↓
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onRemove(step.clientId)}
            aria-label="Remove step"
          >
            ✕
          </Button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <div>
          <Label className="text-xs" htmlFor={actionSelectId}>
            Action
          </Label>
          <Select value={step.action} onValueChange={handleActionChange}>
            <SelectTrigger id={actionSelectId} className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <ActionOptions actions={catalog.actions} />
            </SelectContent>
          </Select>
        </div>
        {spec && spec.variable_name_role !== 'unused' ? (
          <div>
            <Label className="text-xs" htmlFor={variableInputId}>
              {VARIABLE_NAME_LABELS[spec.variable_name_role] ?? 'Variable name'}
            </Label>
            {spec.variable_name_role === 'service_function_name' ? (
              <ServiceFunctionField
                value={step.variableName}
                serviceFunctions={catalog.service_functions}
                inputId={variableInputId}
                onChange={(variableName) => onStepChange({ ...step, variableName })}
              />
            ) : (
              <Input
                id={variableInputId}
                value={step.variableName}
                onChange={(e) => onStepChange({ ...step, variableName: e.target.value })}
              />
            )}
          </div>
        ) : null}
      </div>

      {spec ? (
        <StepParamInputs
          step={step}
          spec={spec}
          catalog={catalog}
          idPrefix={nodeId}
          onChange={onStepChange}
        />
      ) : (
        <div className="text-xs text-destructive">
          Unknown action &apos;{step.action}&apos; — pick a different action above.
        </div>
      )}

      <div
        className={
          isConditional
            ? 'space-y-2 border-l-2 border-primary/40 bg-muted/20 p-2 pl-3'
            : 'space-y-2 pl-3'
        }
      >
        {isConditional ? <div className="text-xs text-muted-foreground">on pass ↓</div> : null}
        {children.map((child, index) => (
          <StepNode
            key={child.clientId}
            step={child}
            steps={steps}
            catalog={catalog}
            specsByAction={specsByAction}
            isFirst={index === 0}
            isLast={index === children.length - 1}
            treeId={treeId}
            onAdd={onAdd}
            onRemove={onRemove}
            onMove={onMove}
            onStepChange={onStepChange}
          />
        ))}
        <AddActionSelect
          key={`add-${step.clientId}-${children.length}`}
          actions={catalog.actions}
          onAdd={(action) => onAdd(step.clientId, action)}
          placeholder="+ Add child step…"
        />
        {isConditional ? (
          <div className="text-xs text-muted-foreground">on fail → next sibling</div>
        ) : null}
      </div>
    </div>
  );
}

function formatConditionValue(value: unknown): string {
  return value === undefined || value === null || value === '' ? '…' : String(value);
}

function ActionOptions({ actions }: { actions: StepActionSpec[] }) {
  const conditionals = actions.filter((action) => action.is_conditional);
  const others = actions.filter((action) => !action.is_conditional);
  return (
    <>
      <SelectGroup>
        <SelectLabel>Conditionals</SelectLabel>
        {conditionals.map((action) => (
          <SelectItem key={action.action} value={action.action}>
            {action.label}
          </SelectItem>
        ))}
      </SelectGroup>
      <SelectGroup>
        <SelectLabel>Actions</SelectLabel>
        {others.map((action) => (
          <SelectItem key={action.action} value={action.action}>
            {action.label}
          </SelectItem>
        ))}
      </SelectGroup>
    </>
  );
}

/**
 * One-shot action picker used to add a step. Not a persistent selection —
 * the `key` at each call site remounts it (back to its placeholder) once
 * the tree it targets grows.
 */
function AddActionSelect({
  actions,
  onAdd,
  placeholder,
}: {
  actions: StepActionSpec[];
  onAdd: (action: string) => void;
  placeholder: string;
}) {
  return (
    <Select onValueChange={onAdd}>
      <SelectTrigger className="h-8 w-64">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <ActionOptions actions={actions} />
      </SelectContent>
    </Select>
  );
}
