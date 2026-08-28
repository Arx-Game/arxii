/**
 * TriggerDefinitionEditorPage — create/edit a TriggerDefinition's name,
 * event, flow, priority, description, and `base_filter_condition` (#3417
 * task 12).
 *
 * Mirrors `FlowEditorPage`'s create/edit-mode split and dirty-guarded
 * server resync (see that page's docstring, `FlowEditorPage.tsx:72-93`):
 * `tdId === 'new'` is create mode; edit mode seeds local state from the
 * loaded `TriggerDefinition` and re-syncs on every non-dirty server
 * refetch, so `save()` marking the editor clean with the exact payload it
 * sent is what lets the invalidation-triggered refetch land without
 * clobbering unsaved work.
 *
 * Switching the event resets `base_filter_condition` to `null` — a filter
 * built against one event's payload schema doesn't carry over to another's
 * (`validate_filter_schema` checks paths against the NEW event's payload
 * dataclass, so a stale filter would just 400 on save).
 *
 * The "Installed by condition templates" wiring card is added by the next
 * commit (task 12 step 3) once `TriggerInstallDialog`'s condition-templates
 * fetcher exists.
 */
import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { flattenErrorMessage } from '@/missions/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Combobox, type ComboboxItem } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

import { ApiValidationError } from '../api';
import { FilterConditionBuilder } from '../components/FilterConditionBuilder';
import { validateFilter, type FilterNode } from '../filterTree';
import {
  useCreateTriggerDefinition,
  useDslCatalog,
  useFlows,
  useTriggerDefinition,
  useUpdateTriggerDefinition,
} from '../queries';
import type { TriggerDefinition, TriggerDefinitionWritePayload } from '../types';

interface EditorState {
  name: string;
  eventName: string;
  flowDefinition: number | null;
  /** Raw editor text — coerced to an int at save time, like FlowEditorPage's params. */
  priority: string;
  description: string;
  baseFilterCondition: FilterNode | null;
}

const EMPTY_STATE: EditorState = {
  name: '',
  eventName: '',
  flowDefinition: null,
  priority: '0',
  description: '',
  baseFilterCondition: null,
};

function serialize(state: EditorState): string {
  return JSON.stringify(state);
}

function fromServer(td: TriggerDefinition): EditorState {
  return {
    name: td.name,
    eventName: td.event_name,
    flowDefinition: td.flow_definition,
    priority: String(td.priority),
    description: td.description ?? '',
    baseFilterCondition: (td.base_filter_condition as FilterNode | null) ?? null,
  };
}

export function TriggerDefinitionEditorPage() {
  const { tdId: tdIdParam } = useParams<{ tdId: string }>();
  const navigate = useNavigate();
  const isCreate = tdIdParam === 'new';
  const tdId = !isCreate && tdIdParam ? Number(tdIdParam) : undefined;

  const tdQuery = useTriggerDefinition(tdId);
  const catalogQuery = useDslCatalog();
  const flowsQuery = useFlows();
  const createTd = useCreateTriggerDefinition();
  const updateTd = useUpdateTriggerDefinition();

  const [state, setState] = useState<EditorState>(EMPTY_STATE);
  const [savedSnapshot, setSavedSnapshot] = useState<string>(serialize(EMPTY_STATE));
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  const isDirty = serialize(state) !== savedSnapshot;

  // Re-sync from the authoritative server row on load and after a save's
  // invalidation-triggered refetch — see the module docstring and
  // FlowEditorPage.tsx:72-93 for why this is gated on `isDirty` and why
  // `isDirty` itself is deliberately absent from the dependency array.
  useEffect(() => {
    const td = tdQuery.data;
    if (!td || isDirty) return;
    const next = fromServer(td);
    setState(next);
    setSavedSnapshot(serialize(next));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tdQuery.data]);

  if (!isCreate && tdQuery.isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!isCreate && tdQuery.isError) {
    return (
      <div className="p-6 text-sm text-destructive">Failed to load this trigger definition.</div>
    );
  }

  const busy = createTd.isPending || updateTd.isPending;
  const mutationError = isCreate ? createTd.error : updateTd.error;
  const catalog = catalogQuery.data;
  const selectedEvent = catalog?.events.find((e) => e.name === state.eventName);
  const pathFields = selectedEvent?.payload_fields ?? [];

  const flowItems: ComboboxItem[] = (flowsQuery.data?.results ?? []).map((f) => ({
    value: String(f.id),
    label: f.name,
  }));

  const goBack = () => {
    if (isDirty && !window.confirm('Discard unsaved changes?')) return;
    navigate('/staff/flows-builder');
  };

  const save = () => {
    if (!catalog) return;
    const priority = parseInt(state.priority, 10);
    const errors = validateFilter(state.baseFilterCondition, catalog.filter_ops);
    if (!state.name.trim()) errors.push('Name is required.');
    if (!state.eventName) errors.push('Event is required.');
    if (state.flowDefinition === null) errors.push('Flow is required.');
    if (Number.isNaN(priority)) errors.push('Priority must be a number.');
    setValidationErrors(errors);
    if (errors.length > 0) return;

    const nextState: EditorState = { ...state, priority: String(priority) };
    const payload: TriggerDefinitionWritePayload = {
      name: nextState.name.trim(),
      event_name: nextState.eventName,
      flow_definition: nextState.flowDefinition as number,
      priority,
      description: nextState.description,
      base_filter_condition: nextState.baseFilterCondition,
    };
    if (isCreate) {
      createTd.mutate(payload, {
        onSuccess: (result) => navigate(`/staff/flows-builder/trigger-definitions/${result.id}`),
      });
    } else if (tdId !== undefined) {
      updateTd.mutate(
        { id: tdId, payload },
        {
          // Mark clean with the exact payload just sent — mirrors
          // FlowEditorPage's save() so the resync effect above accepts the
          // invalidation-triggered refetch that follows.
          onSuccess: () => {
            setState(nextState);
            setSavedSnapshot(serialize(nextState));
          },
        }
      );
    }
  };

  return (
    <div className="container mx-auto max-w-4xl space-y-6 py-6">
      <Button variant="ghost" size="sm" onClick={goBack}>
        ← Back to Flows Builder
      </Button>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isCreate ? 'New trigger definition' : 'Trigger definition'}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="td-name">Name</Label>
            <Input
              id="td-name"
              value={state.name}
              onChange={(e) => setState((p) => ({ ...p, name: e.target.value }))}
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="td-event">Event</Label>
              <Select
                value={state.eventName}
                onValueChange={(v) =>
                  setState((p) => ({ ...p, eventName: v, baseFilterCondition: null }))
                }
              >
                <SelectTrigger id="td-event">
                  <SelectValue placeholder="Pick an event…" />
                </SelectTrigger>
                <SelectContent>
                  {(catalog?.events ?? []).map((event) => (
                    <SelectItem key={event.name} value={event.name}>
                      {event.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="td-flow">Flow</Label>
              <Combobox
                items={flowItems}
                value={state.flowDefinition !== null ? String(state.flowDefinition) : ''}
                onValueChange={(v) =>
                  setState((p) => ({ ...p, flowDefinition: v ? Number(v) : null }))
                }
                placeholder="Pick a flow…"
              />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="td-priority">Priority</Label>
            <Input
              id="td-priority"
              type="number"
              value={state.priority}
              onChange={(e) => setState((p) => ({ ...p, priority: e.target.value }))}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="td-description">Description</Label>
            <Textarea
              id="td-description"
              rows={2}
              value={state.description}
              onChange={(e) => setState((p) => ({ ...p, description: e.target.value }))}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filter condition</CardTitle>
        </CardHeader>
        <CardContent>
          {state.eventName ? (
            <FilterConditionBuilder
              value={state.baseFilterCondition}
              onChange={(next) => setState((p) => ({ ...p, baseFilterCondition: next }))}
              filterOps={catalog?.filter_ops ?? []}
              pathFields={pathFields ?? []}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Pick an event to filter on its payload fields.
            </p>
          )}
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
            : 'Could not save the trigger definition.'}
        </p>
      ) : null}

      <Button onClick={save} disabled={!state.name.trim() || busy || !catalog}>
        {busy ? 'Saving…' : 'Save trigger definition'}
      </Button>
    </div>
  );
}
