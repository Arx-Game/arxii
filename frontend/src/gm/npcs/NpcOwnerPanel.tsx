/**
 * The owner's panel for one NPC (#4418): the open borrow requests with Approve and
 * Decline, and the lending and roster settings the NPC form set at creation.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import { throwApiError } from '@/lib/errors';

import {
  BORROW_AUDIENCES,
  LEND_POLICIES,
  fetchNpcDetail,
  patchNpcSettings,
  type BorrowAudience,
  type LendPolicy,
  type NpcDetail,
} from './npcFormApi';

const selectClass = 'h-9 w-full rounded-md border bg-transparent px-2 text-sm';

type AnswerRequest = components['schemas']['AnswerRequest'];

const npcOwnerKeys = {
  detail: (entryId: number) => ['gm-npc-owner', entryId] as const,
};

function useAnswerBorrowRequest(entryId: number, name: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: AnswerRequest) => {
      const res = await apiFetch('/api/roster/npcs/answer/', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      if (!res.ok) await throwApiError(res, "Couldn't answer that request.");
    },
    onSuccess: (_data, body) =>
      toast.success(body.accept ? `${name} is lent out.` : `Declined the request for ${name}.`),
    onError: (error: Error) => toast.error(error.message),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: npcOwnerKeys.detail(entryId) });
      void queryClient.invalidateQueries({ queryKey: ['my-roster-entries'] });
    },
  });
}

interface Draft {
  listed: boolean;
  lend: LendPolicy;
  audience: BorrowAudience;
  notes: string;
}

function draftOf(detail: NpcDetail): Draft {
  return {
    listed: detail.listed_on_npc_roster,
    lend: detail.lend_policy,
    audience: detail.borrow_audience,
    notes: detail.notes_for_player,
  };
}

function SettingsBlock({ detail }: { detail: NpcDetail }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => draftOf(detail));
  const save = useMutation({
    mutationFn: () =>
      patchNpcSettings(detail.id, {
        listed_on_npc_roster: draft.listed,
        lend_policy: draft.lend,
        borrow_audience: draft.audience,
        notes_for_player: draft.notes,
      }),
    onSuccess: () => toast.success(`Saved the settings for ${detail.name}.`),
    onError: (error: Error) => toast.error(error.message),
    onSettled: () =>
      void queryClient.invalidateQueries({ queryKey: npcOwnerKeys.detail(detail.id) }),
  });
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const id = `npc-owner-${detail.id}`;

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={draft.listed}
          onChange={(e) => set('listed', e.target.checked)}
        />
        List on the NPC roster
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor={`${id}-lend`} className="text-xs font-medium text-muted-foreground">
            Who may play {detail.name}
          </label>
          <select
            id={`${id}-lend`}
            className={selectClass}
            value={draft.lend}
            onChange={(e) => set('lend', e.target.value as LendPolicy)}
          >
            {LEND_POLICIES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={`${id}-audience`} className="text-xs font-medium text-muted-foreground">
            Who may ask to borrow
          </label>
          <select
            id={`${id}-audience`}
            className={selectClass}
            disabled={draft.lend === 'not_lent'}
            value={draft.audience}
            onChange={(e) => set('audience', e.target.value as BorrowAudience)}
          >
            {BORROW_AUDIENCES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`${id}-notes`} className="text-xs font-medium text-muted-foreground">
          Notes for whoever plays {detail.name}
        </label>
        <Textarea
          id={`${id}-notes`}
          rows={8}
          className="resize-y"
          value={draft.notes}
          onChange={(e) => set('notes', e.target.value)}
        />
      </div>
      <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
        Save settings
      </Button>
    </div>
  );
}

/** The panel for an NPC the viewer owns; `entryId` is the NPC's roster entry id. */
export function NpcOwnerPanel({ entryId, name }: { entryId: number; name: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: npcOwnerKeys.detail(entryId),
    queryFn: () => fetchNpcDetail(entryId),
    retry: false,
  });
  const answer = useAnswerBorrowRequest(entryId, name);

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading...</p>;
  if (isError || !data) {
    return <p className="text-sm text-destructive">Couldn't load {name}'s settings.</p>;
  }
  const requests = data.open_requests as { id: number; status: string }[];

  return (
    <div className="space-y-4 rounded-md border p-3" data-testid="npc-owner-panel">
      {requests.length > 0 && (
        <ul className="space-y-2">
          {requests.map((request) => (
            <li
              key={request.id}
              className="flex flex-wrap items-center gap-2 text-sm"
              data-testid="npc-borrow-request"
            >
              <span className="grow">Request to borrow {data.name}</span>
              <Button
                size="sm"
                disabled={answer.isPending}
                onClick={() => answer.mutate({ loan_id: request.id, accept: true })}
              >
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={answer.isPending}
                onClick={() => answer.mutate({ loan_id: request.id, accept: false })}
              >
                Decline
              </Button>
            </li>
          ))}
        </ul>
      )}
      <SettingsBlock key={dataKey(data)} detail={data} />
    </div>
  );
}

/** Re-seed the draft when the server's settings change under it (after a save). */
function dataKey(detail: NpcDetail): string {
  return [
    detail.listed_on_npc_roster,
    detail.lend_policy,
    detail.borrow_audience,
    detail.notes_for_player,
  ].join('|');
}
