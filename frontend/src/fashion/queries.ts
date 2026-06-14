import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import type { PaginatedResponse } from '@/shared/types';
import type { FashionPresentation, JudgementPayload, PresentationPayload } from './types';

const PRESENTATIONS_KEY = 'fashion-presentations';

function eventPresentationsKey(eventId: number) {
  return [PRESENTATIONS_KEY, eventId];
}

/** Pull the API's ``detail`` message off a non-2xx response, with a fallback. */
async function readDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: string };
    if (data.detail) return data.detail;
  } catch {
    // non-JSON body — fall through to the generic message
  }
  return fallback;
}

async function fetchEventPresentations(eventId: number): Promise<FashionPresentation[]> {
  const res = await apiFetch(`/api/items/fashion-presentations/?event=${eventId}`);
  if (!res.ok) {
    throw new Error('Failed to load fashion presentations.');
  }
  const data = (await res.json()) as PaginatedResponse<FashionPresentation>;
  return data.results;
}

async function presentOutfit(payload: PresentationPayload): Promise<FashionPresentation> {
  const res = await apiFetch('/api/items/fashion-presentations/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readDetail(res, 'Failed to present your look.'));
  }
  return res.json();
}

async function judgePresentation(payload: JudgementPayload): Promise<void> {
  const res = await apiFetch('/api/items/fashion-judgements/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readDetail(res, 'Failed to record your judgement.'));
  }
}

/** Presentations recorded for one event. */
export function useEventPresentationsQuery(eventId: number | undefined) {
  return useQuery({
    queryKey: eventPresentationsKey(eventId as number),
    queryFn: () => fetchEventPresentations(eventId as number),
    enabled: eventId !== undefined,
  });
}

/** Present the viewer's current look at an event; refreshes the event's list. */
export function usePresentOutfitMutation(eventId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PresentationPayload) => presentOutfit(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: eventPresentationsKey(eventId) });
    },
  });
}

/** Endorse another presentation; refreshes the event's list (acclaim moves). */
export function useJudgePresentationMutation(eventId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: JudgementPayload) => judgePresentation(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: eventPresentationsKey(eventId) });
    },
  });
}
