import type { QueryClient } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { ActionRef } from '@/combat/types';
import type { PlayerAction } from '@/scenes/actionTypes';

export type TargetMenuKind = 'items' | 'objects' | 'exits' | 'places';

export interface TargetMenuTarget {
  kind: TargetMenuKind;
  target_id: number;
  owner_persona_id?: number;
  container_item_id?: number;
}

export interface TargetMenuInput {
  name: string;
  kind: string;
  required: boolean;
  target_kind: string | null;
  default: unknown;
  candidates?: TargetMenuCandidate[];
}

export interface TargetMenuCandidate {
  key: string;
  label: string;
  kwargs: Record<string, unknown>;
  available: boolean;
  reasons: string[];
}

export interface TargetMenuEntry {
  key: string;
  label: string;
  group: string;
  ref: ActionRef;
  kwargs: Record<string, unknown>;
  available: boolean;
  reasons: string[];
  inputs: TargetMenuInput[];
  candidates: TargetMenuCandidate[];
  next_candidate_cursor?: string | null;
  action: PlayerAction | null;
  risk: {
    known: boolean;
    character_loss_possible: boolean | null;
    outcomes: { stage: string; tier: string; character_loss: boolean }[];
  } | null;
}

export interface TargetMenuData {
  actor_id: number;
  target: TargetMenuTarget;
  label: string;
  groups: { key: string; label: string }[];
  entries: TargetMenuEntry[];
}

export const targetMenuPrefix = (partition: string, actorId: number) =>
  ['target-menu', partition, actorId] as const;

export const targetMenuKey = (partition: string, actorId: number, target: TargetMenuTarget) =>
  [
    ...targetMenuPrefix(partition, actorId),
    target.kind,
    target.target_id,
    target.owner_persona_id ?? null,
    target.container_item_id ?? null,
  ] as const;

export const targetMenuInputPageKey = (
  partition: string,
  actorId: number,
  target: TargetMenuTarget,
  inputsFor: string,
  candidateCursor?: string
) => [...targetMenuKey(partition, actorId, target), inputsFor, candidateCursor ?? null] as const;

export class TargetMenuFetchError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly retryAfterSeconds: number | null
  ) {
    super(message);
    this.name = 'TargetMenuFetchError';
  }
}

export async function fetchTargetMenu(
  actorId: number,
  target: TargetMenuTarget,
  signal?: AbortSignal,
  inputsFor?: string,
  candidateCursor?: string
): Promise<TargetMenuData> {
  const query = new URLSearchParams();
  if (inputsFor !== undefined) query.set('inputs_for', inputsFor);
  if (candidateCursor !== undefined) query.set('candidate_cursor', candidateCursor);
  if (target.owner_persona_id !== undefined) {
    query.set('owner_persona_id', String(target.owner_persona_id));
  }
  if (target.container_item_id !== undefined) {
    query.set('container_item_id', String(target.container_item_id));
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : '';
  const response = await apiFetch(
    `/api/actions/characters/${actorId}/${target.kind}/${target.target_id}/menu/${suffix}`,
    { signal }
  );
  if (!response.ok) {
    const retryAfter = response.headers.get('Retry-After');
    const parsedRetryAfter = retryAfter === null ? Number.NaN : Number(retryAfter);
    throw new TargetMenuFetchError(
      'Failed to load actions for this target',
      response.status,
      Number.isFinite(parsedRetryAfter) && parsedRetryAfter >= 0 ? parsedRetryAfter : null
    );
  }
  return (await response.json()) as TargetMenuData;
}

export const targetMenuQueryPolicy = {
  staleTime: 30_000,
  retry: false,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  refetchOnMount: false,
} as const;

export function useTargetMenuQuery(
  partition: string,
  actorId: number | null,
  target: TargetMenuTarget,
  open: boolean
) {
  return useQuery({
    queryKey: targetMenuKey(partition, actorId ?? 0, target),
    queryFn: ({ signal }) => fetchTargetMenu(actorId as number, target, signal),
    enabled: open && actorId !== null && actorId > 0 && partition.length > 0,
    ...targetMenuQueryPolicy,
  });
}

export function markTargetMenusStale(
  client: QueryClient,
  partition: string,
  actorId: number
): Promise<void> {
  return client.invalidateQueries({
    queryKey: targetMenuPrefix(partition, actorId),
    refetchType: 'none',
  });
}
