/**
 * CastListPanel - the GM's scene cast (#4418, Screen 2): the named NPCs and crowds in
 * the scene with portraits, and who plays each. A GM can offer a named NPC to a Guide,
 * take a lent NPC back, and give an unvoiced crowd a voice.
 *
 * The acting character for the registry dispatch is the GM's own browsing identity
 * (`useActiveCharacterId`), the same one `GMStoryRail` dispatches as.
 */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiFetch } from '@/evennia_replacements/api';
import { useActiveCharacterId } from '@/gm-adjudication/useActiveCharacterId';
import type { components } from '@/generated/api';
import { extractErrorMessage } from '@/lib/errors';
import { dispatchCanvasAction } from '@/map-canvas/dispatch';

type CastEntry = components['schemas']['CastListEntry'];
type Guide = components['schemas']['Guide'];

async function getResults<T>(url: string, fallback: string): Promise<T[]> {
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(fallback);
  const body = (await res.json()) as { results: T[] };
  return body.results;
}

function castListKey(sceneId: number) {
  return ['scene-cast-list', sceneId] as const;
}

function useCastListQuery(sceneId: number) {
  return useQuery({
    queryKey: castListKey(sceneId),
    queryFn: () =>
      getResults<CastEntry>(`/api/scenes/${sceneId}/cast-list/`, 'Failed to load the cast.'),
    staleTime: 10_000,
  });
}

function useGuidesQuery() {
  return useQuery({
    queryKey: ['gm-guides'],
    queryFn: () => getResults<Guide>('/api/gm/guides/', 'Failed to load Guides.'),
    staleTime: 60_000,
  });
}

function playedByText(entry: CastEntry): string {
  if (entry.loan_id === null) return entry.played_by;
  if (entry.loan_status === 'offered') return `Offered to ${entry.played_by}`;
  return `${entry.played_by} (Guide)`;
}

function crowdSummary(entry: CastEntry): string {
  const parts = [entry.name];
  if (entry.tier) parts.push(entry.tier);
  if (entry.count !== null) parts.push(`${entry.count} bodies`);
  return parts.join(' · ');
}

function Portrait({ entry }: { entry: CastEntry }) {
  return (
    <Avatar className="h-10 w-10">
      {entry.thumbnail_url && <AvatarImage src={entry.thumbnail_url} alt="" />}
      <AvatarFallback>{entry.name.slice(0, 1)}</AvatarFallback>
    </Avatar>
  );
}

interface RowProps {
  entry: CastEntry;
  guides: Guide[];
  busy: boolean;
  onRun: (key: string, kwargs: Record<string, unknown>) => void;
}

function NpcRow({ entry, guides, busy, onRun }: RowProps) {
  const lent = entry.loan_id !== null;
  return (
    <li className="flex items-center gap-3 py-2" data-testid="cast-row-npc">
      <Portrait entry={entry} />
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">
          {entry.name}
          {entry.played_by && ` · ${playedByText(entry)}`}
        </div>
        {entry.description && (
          <div className="max-h-24 overflow-y-auto whitespace-pre-line text-xs text-muted-foreground">
            {entry.description}
          </div>
        )}
      </div>
      {lent ? (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => onRun('take_back_npc', { loan_id: entry.loan_id })}
        >
          Take back
        </Button>
      ) : (
        <select
          aria-label={`Play ${entry.name}`}
          className="h-8 rounded-md border border-input bg-transparent px-2 text-sm"
          value=""
          disabled={busy || entry.roster_entry_id === null}
          onChange={(e) => {
            if (e.target.value === '') return;
            onRun('offer_npc', {
              roster_entry_id: entry.roster_entry_id,
              guide_account_id: Number(e.target.value),
            });
          }}
        >
          <option value="">Me</option>
          {guides.map((g) => (
            <option key={g.account_id} value={g.account_id}>
              Offer to {g.display_name}
            </option>
          ))}
        </select>
      )}
    </li>
  );
}

function CrowdRow({ entry, busy, onRun }: Omit<RowProps, 'guides'>) {
  const [naming, setNaming] = useState(false);
  const [voiceName, setVoiceName] = useState('');
  const unvoiced = entry.persona_id === null;
  return (
    <li className="py-2" data-testid="cast-row-crowd">
      <div className="flex items-center gap-3">
        <Portrait entry={entry} />
        <div className="min-w-0 flex-1 truncate font-medium">
          {crowdSummary(entry)}
          {entry.played_by && ` · ${entry.played_by}`}
        </div>
        {unvoiced && !naming && (
          <Button size="sm" variant="outline" onClick={() => setNaming(true)}>
            Add crowd voice
          </Button>
        )}
      </div>
      {entry.description && (
        <div className="mt-1 max-h-32 overflow-y-auto whitespace-pre-line text-xs text-muted-foreground">
          {entry.description}
        </div>
      )}
      {unvoiced && naming && (
        <form
          className="mt-2 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (voiceName.trim() === '') return;
            onRun('voice_crowd', { opponent_ids: entry.opponent_ids, name: voiceName.trim() });
          }}
        >
          <Input
            aria-label="Crowd voice name"
            value={voiceName}
            onChange={(e) => setVoiceName(e.target.value)}
          />
          <Button type="submit" size="sm" disabled={busy || voiceName.trim() === ''}>
            Give voice
          </Button>
        </form>
      )}
    </li>
  );
}

export function CastListPanel({ sceneId }: { sceneId: number }) {
  const characterId = useActiveCharacterId();
  const qc = useQueryClient();
  const { data: cast = [] } = useCastListQuery(sceneId);
  const { data: guides = [] } = useGuidesQuery();

  const run = useMutation({
    mutationFn: ({ key, kwargs }: { key: string; kwargs: Record<string, unknown> }) =>
      dispatchCanvasAction(characterId ?? 0, key, kwargs),
    onSuccess: (result) => {
      if (result.success === false) toast.error(result.message);
      else toast.success(result.message);
      void qc.invalidateQueries({ queryKey: castListKey(sceneId) });
    },
    onError: (err) => toast.error(extractErrorMessage(err, 'The action failed.')),
  });

  if (cast.length === 0) return null;
  const onRun = (key: string, kwargs: Record<string, unknown>) => run.mutate({ key, kwargs });
  const busy = run.isPending || characterId === null;

  return (
    <section className="rounded-md border p-3" aria-label="Scene cast">
      <h3 className="font-display text-sm">Cast</h3>
      <ul className="divide-y">
        {cast.map((entry) =>
          entry.kind === 'crowd' ? (
            <CrowdRow
              key={`crowd-${entry.opponent_ids.join('-')}`}
              entry={entry}
              busy={busy}
              onRun={onRun}
            />
          ) : (
            <NpcRow
              key={`npc-${entry.roster_entry_id}`}
              entry={entry}
              guides={guides}
              busy={busy}
              onRun={onRun}
            />
          )
        )}
      </ul>
    </section>
  );
}
