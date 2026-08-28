/**
 * FlowEditorPage — create/edit a FlowDefinition's name, description, and
 * step tree, plus a read-only interactions summary (#3417 task 11).
 *
 * `flowId === 'new'` is create mode: the page starts from empty local state
 * and POSTs on save, then navigates to this same route with the new flow's
 * real id. Edit mode seeds local state from the loaded `FlowDetail` and
 * re-syncs whenever that query's data changes — the same pattern as
 * `RoleFieldsCard` in `npc_services/pages/NPCRoleEditorPage.tsx` — so a
 * successful save's query invalidation naturally refreshes the editor with
 * the authoritative saved steps (real pks replacing client-generated ids)
 * instead of the page re-deriving that itself.
 *
 * CRITICAL save order (#3417 task 10 review): `coerceParams` runs on every
 * step first (raw editor strings -> typed values per that step's action
 * spec), THEN `validateSteps` runs on the coerced list, THEN the mutation
 * fires with the coerced steps. Validating raw (uncoerced) editor state
 * flags every numeric/boolean param as invalid.
 */
import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { flattenErrorMessage } from '@/missions/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

import { ApiValidationError } from '../api';
import { FlowStepTree } from '../components/FlowStepTree';
import { InteractionsPanel } from '../components/InteractionsPanel';
import { useCreateFlow, useDslCatalog, useFlow, useUpdateFlow } from '../queries';
import { coerceParams, fromServerSteps, validateSteps } from '../stepTree';
import type { ClientStep, FlowInteractions } from '../types';

interface EditorState {
  name: string;
  description: string;
  steps: ClientStep[];
}

const EMPTY_STATE: EditorState = { name: '', description: '', steps: [] };
const EMPTY_INTERACTIONS: FlowInteractions = { run_by: [], emits: [], calls: [] };

function serialize(state: EditorState): string {
  return JSON.stringify(state);
}

export function FlowEditorPage() {
  const { flowId: flowIdParam } = useParams<{ flowId: string }>();
  const navigate = useNavigate();
  const isCreate = flowIdParam === 'new';
  const flowId = !isCreate && flowIdParam ? Number(flowIdParam) : undefined;

  const flowQuery = useFlow(flowId);
  const catalogQuery = useDslCatalog();
  const createFlow = useCreateFlow();
  const updateFlow = useUpdateFlow();

  const [state, setState] = useState<EditorState>(EMPTY_STATE);
  const [savedSnapshot, setSavedSnapshot] = useState<string>(serialize(EMPTY_STATE));
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  // Re-sync local editor state from the authoritative server row whenever it
  // changes — on first load, and again after a save's query invalidation
  // refetches. No-op in create mode (the query is disabled, so data stays
  // undefined).
  useEffect(() => {
    const flow = flowQuery.data;
    if (!flow) return;
    const next: EditorState = {
      name: flow.name,
      description: flow.description ?? '',
      steps: fromServerSteps(flow.steps),
    };
    setState(next);
    setSavedSnapshot(serialize(next));
  }, [flowQuery.data]);

  if (!isCreate && flowQuery.isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!isCreate && flowQuery.isError) {
    return <div className="p-6 text-sm text-destructive">Failed to load this flow.</div>;
  }

  const isDirty = serialize(state) !== savedSnapshot;
  const busy = createFlow.isPending || updateFlow.isPending;
  const mutationError = isCreate ? createFlow.error : updateFlow.error;

  const goBack = () => {
    if (isDirty && !window.confirm('Discard unsaved changes?')) return;
    navigate('/staff/flows-builder');
  };

  const save = () => {
    if (!catalogQuery.data) return;
    const specsByAction = new Map(catalogQuery.data.actions.map((spec) => [spec.action, spec]));
    // Coerce FIRST (raw editor strings -> typed values), THEN validate the
    // coerced list, THEN mutate with the coerced steps — never validate raw
    // editor state (see the module docstring).
    const coercedSteps = state.steps.map((step) => {
      const spec = specsByAction.get(step.action);
      return spec ? coerceParams(step, spec) : step;
    });
    const errors = validateSteps(coercedSteps, specsByAction);
    setValidationErrors(errors);
    if (errors.length > 0) return;

    const payload = {
      name: state.name.trim(),
      description: state.description,
      steps: coercedSteps,
    };
    if (isCreate) {
      createFlow.mutate(payload, {
        onSuccess: (result) => navigate(`/staff/flows-builder/flows/${result.id}`),
      });
    } else if (flowId !== undefined) {
      updateFlow.mutate({ id: flowId, payload });
    }
  };

  return (
    <div className="container mx-auto max-w-6xl space-y-6 py-6">
      <Button variant="ghost" size="sm" onClick={goBack}>
        ← Back to Flows Builder
      </Button>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{isCreate ? 'New flow' : 'Flow'}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1">
                <Label htmlFor="flow-name">Name</Label>
                <Input
                  id="flow-name"
                  value={state.name}
                  onChange={(e) => setState((prev) => ({ ...prev, name: e.target.value }))}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="flow-description">Description</Label>
                <Textarea
                  id="flow-description"
                  rows={2}
                  value={state.description}
                  onChange={(e) => setState((prev) => ({ ...prev, description: e.target.value }))}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Steps</CardTitle>
            </CardHeader>
            <CardContent>
              <FlowStepTree
                value={state.steps}
                onChange={(steps) => setState((prev) => ({ ...prev, steps }))}
              />
            </CardContent>
          </Card>

          {validationErrors.length > 0 ? (
            <div className="space-y-1 rounded border border-destructive/40 bg-destructive/5 p-3">
              {validationErrors.map((err) => (
                <p key={err} className="text-sm text-destructive">
                  {err}
                </p>
              ))}
            </div>
          ) : null}
          {mutationError ? (
            <p className="text-sm text-destructive">
              {mutationError instanceof ApiValidationError
                ? flattenErrorMessage(mutationError.fieldErrors)
                : 'Could not save the flow.'}
            </p>
          ) : null}

          <Button onClick={save} disabled={!state.name.trim() || busy || !catalogQuery.data}>
            {busy ? 'Saving…' : 'Save flow'}
          </Button>
        </div>

        <div>
          {isCreate ? (
            <p className="text-sm text-muted-foreground">
              Interactions (what runs this flow, what it emits, what it calls) appear once the
              flow is saved.
            </p>
          ) : (
            <InteractionsPanel interactions={flowQuery.data?.interactions ?? EMPTY_INTERACTIONS} />
          )}
        </div>
      </div>
    </div>
  );
}
