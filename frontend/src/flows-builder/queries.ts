/**
 * Flows Builder React Query hooks (#3417 task 9).
 *
 * Hierarchical key namespace per project convention (see
 * `missions/queries.ts`). Mutations invalidate the closest parent key(s) so
 * list/detail views refetch on create/update/delete without manual glue.
 */

import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import {
  createFlow,
  createTrigger,
  createTriggerDefinition,
  deleteFlow,
  deleteTrigger,
  deleteTriggerDefinition,
  fetchDslCatalog,
  getFlow,
  getTrigger,
  getTriggerDefinition,
  listConditionTemplates,
  listFlows,
  listTriggerDefinitions,
  listTriggers,
  setReactiveTriggers,
  updateFlow,
  updateTrigger,
  updateTriggerDefinition,
  type ConditionTemplateSummary,
} from './api';
import type {
  DslCatalog,
  FlowDetail,
  FlowSummary,
  FlowWritePayload,
  PaginatedResponse,
  TriggerDefinition,
  TriggerDefinitionWritePayload,
  TriggerRow,
  TriggerWritePayload,
} from './types';

const FIVE_MINUTES = 5 * 60 * 1000;

export const flowsBuilderKeys = {
  all: ['flows-builder'] as const,
  catalog: () => [...flowsBuilderKeys.all, 'catalog'] as const,
  flows: () => [...flowsBuilderKeys.all, 'flows'] as const,
  flowList: (search?: string) => [...flowsBuilderKeys.flows(), 'list', search ?? ''] as const,
  flowDetail: (id: number) => [...flowsBuilderKeys.flows(), 'detail', id] as const,
  triggerDefinitions: () => [...flowsBuilderKeys.all, 'trigger-definitions'] as const,
  triggerDefinitionList: (filters: object) =>
    [...flowsBuilderKeys.triggerDefinitions(), 'list', filters] as const,
  triggerDefinitionDetail: (id: number) =>
    [...flowsBuilderKeys.triggerDefinitions(), 'detail', id] as const,
  triggers: () => [...flowsBuilderKeys.all, 'triggers'] as const,
  triggerList: (filters: object) => [...flowsBuilderKeys.triggers(), 'list', filters] as const,
  triggerDetail: (id: number) => [...flowsBuilderKeys.triggers(), 'detail', id] as const,
  conditionTemplates: () => [...flowsBuilderKeys.all, 'condition-templates'] as const,
};

// ---------------------------------------------------------------------------
// DSL authoring catalog
// ---------------------------------------------------------------------------

/** Catalog is DSL-surface-driven, not per-object — safe to cache for a while. */
export function useDslCatalog(): UseQueryResult<DslCatalog> {
  return useQuery({
    queryKey: flowsBuilderKeys.catalog(),
    queryFn: fetchDslCatalog,
    staleTime: FIVE_MINUTES,
  });
}

// ---------------------------------------------------------------------------
// FlowDefinition
// ---------------------------------------------------------------------------

export function useFlows(search?: string): UseQueryResult<PaginatedResponse<FlowSummary>> {
  return useQuery({
    queryKey: flowsBuilderKeys.flowList(search),
    queryFn: () => listFlows(search),
  });
}

export function useFlow(id: number | undefined): UseQueryResult<FlowDetail> {
  return useQuery({
    queryKey: flowsBuilderKeys.flowDetail(id ?? 0),
    queryFn: () => getFlow(id as number),
    enabled: id !== undefined,
  });
}

export function useCreateFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: FlowWritePayload) => createFlow(payload),
    // The create response is write_only on `steps` (see FlowWriteResult), so
    // there is nothing worth priming into flowDetail(id) here — the caller
    // navigates to the new flow's detail view, which does its own GET.
    onSuccess: () => qc.invalidateQueries({ queryKey: flowsBuilderKeys.flows() }),
  });
}

export function useUpdateFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: FlowWritePayload }) =>
      updateFlow(id, payload),
    onSuccess: (_result, { id }) => {
      qc.invalidateQueries({ queryKey: flowsBuilderKeys.flowDetail(id) });
      qc.invalidateQueries({ queryKey: flowsBuilderKeys.flows() });
    },
  });
}

export function useDeleteFlow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteFlow(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: flowsBuilderKeys.flows() }),
  });
}

// ---------------------------------------------------------------------------
// TriggerDefinition
// ---------------------------------------------------------------------------

export function useTriggerDefinitions(
  filters: { event_name?: string; search?: string; page?: number; page_size?: number } = {}
): UseQueryResult<PaginatedResponse<TriggerDefinition>> {
  return useQuery({
    queryKey: flowsBuilderKeys.triggerDefinitionList(filters),
    queryFn: () => listTriggerDefinitions(filters),
  });
}

export function useTriggerDefinition(
  id: number | undefined
): UseQueryResult<TriggerDefinition> {
  return useQuery({
    queryKey: flowsBuilderKeys.triggerDefinitionDetail(id ?? 0),
    queryFn: () => getTriggerDefinition(id as number),
    enabled: id !== undefined,
  });
}

export function useCreateTriggerDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TriggerDefinitionWritePayload) => createTriggerDefinition(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggerDefinitions() }),
  });
}

export function useUpdateTriggerDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: TriggerDefinitionWritePayload }) =>
      updateTriggerDefinition(id, payload),
    onSuccess: (_result, { id }) => {
      qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggerDefinitionDetail(id) });
      qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggerDefinitions() });
    },
  });
}

export function useDeleteTriggerDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteTriggerDefinition(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggerDefinitions() }),
  });
}

// ---------------------------------------------------------------------------
// Trigger
// ---------------------------------------------------------------------------

export function useTriggers(
  filters: {
    trigger_definition?: number;
    obj?: number;
    search?: string;
    page?: number;
    page_size?: number;
  } = {}
): UseQueryResult<PaginatedResponse<TriggerRow>> {
  return useQuery({
    queryKey: flowsBuilderKeys.triggerList(filters),
    queryFn: () => listTriggers(filters),
  });
}

export function useTrigger(id: number | undefined): UseQueryResult<TriggerRow> {
  return useQuery({
    queryKey: flowsBuilderKeys.triggerDetail(id ?? 0),
    queryFn: () => getTrigger(id as number),
    enabled: id !== undefined,
  });
}

export function useCreateTrigger() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TriggerWritePayload) => createTrigger(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggers() }),
  });
}

export function useUpdateTrigger() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: TriggerWritePayload }) =>
      updateTrigger(id, payload),
    onSuccess: (_result, { id }) => {
      qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggerDetail(id) });
      qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggers() });
    },
  });
}

export function useDeleteTrigger() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteTrigger(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggers() }),
  });
}

// ---------------------------------------------------------------------------
// ConditionTemplate reactive-trigger wiring
// ---------------------------------------------------------------------------

/** All condition templates (staff/GM picker data) — see `ConditionTemplateSummary`'s docstring. */
export function useConditionTemplates(): UseQueryResult<ConditionTemplateSummary[]> {
  return useQuery({
    queryKey: flowsBuilderKeys.conditionTemplates(),
    queryFn: listConditionTemplates,
    staleTime: FIVE_MINUTES,
  });
}

export function useSetReactiveTriggers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, ids }: { templateId: number; ids: number[] }) =>
      setReactiveTriggers(templateId, ids),
    onSuccess: () => {
      // Reactive-trigger wiring isn't itself a flows-builder resource, but
      // trigger-definition rows carry no back-reference to templates — the
      // safest invalidation is the trigger-definition namespace, since a
      // ConditionTemplate's authoring UI reads that list to build its picker.
      qc.invalidateQueries({ queryKey: flowsBuilderKeys.triggerDefinitions() });
      // The template's own reactive_trigger_ids just changed too.
      qc.invalidateQueries({ queryKey: flowsBuilderKeys.conditionTemplates() });
    },
  });
}
