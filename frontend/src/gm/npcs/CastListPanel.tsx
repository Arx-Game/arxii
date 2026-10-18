/**
 * CastListPanel - the GM's scene cast (#4418, Screen 2): the named NPCs and crowds in
 * the scene with portraits, and who plays each. A GM can offer a named NPC to a Guide,
 * take a lent NPC back, and give an unvoiced crowd a voice.
 *
 * The acting character for the registry dispatch is the GM's own browsing identity
 * (`useActiveCharacterId`), the same one `GMStoryRail` dispatches as.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
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

function crowdChip(entry: CastEntry): string {
  const tier = entry.tier ?? '';
  if (tier === 'swarm') return `swarm \u00b7 ${entry.count ?? 0} bodies`;
  const plural = tier ? `${tier.replace(/_/g, ' ')}s` : 'bodies';
  return `${entry.count ?? 0} \u00b7 ${plural}`;
}

function Portrait({ entry }: { entry: CastEntry }) {
  return (
    <Avatar className="h-[72px] w-[72px] rounded-md">
      {entry.thumbnail_url && <AvatarImage src={entry.thumbnail_url} alt="" />}
      <AvatarFallback className="rounded-md text-xl">{entry.name.slice(0, 1)}</AvatarFallback>
    </Avatar>
  );
}

function CrowdStack({ entry }: { entry: CastEntry }) {
  return (
    <div className="flex h-[72px] w-[72px] shrink-0 items-center" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <Avatar key={i} className={`h-9 w-9 border-2 border-background ${i > 0 ? '-ml-3' : ''}`}>
          {entry.thumbnail_url && <AvatarImage src={entry.thumbnail_url} alt="" />}
          <AvatarFallback className="text-xs">{entry.name.slice(0, 1)}</AvatarFallback>
        </Avatar>
      ))}
    </div>
  );
}

interface RunProps {
  guides: Guide[];
  busy: boolean;
  onRun: (key: string, kwargs: Record<string, unknown>) => void;
}

/** Who plays this entry. Picking "Me" on a lent or offered row takes the loan back. */
function PlayedBy({ entry, guides, busy, onRun }: RunProps & { entry: CastEntry }) {
  if (entry.roster_entry_id === null) return null;
  const hasLoan = entry.loan_id !== null;
  const lent = hasLoan && entry.loan_status !== 'offered';
  const value = hasLoan ? 'current' : 'me';
  return (
    <div className="flex items-center gap-2">
      <select
        aria-label={`Play ${entry.name}`}
        className="h-8 rounded-md border border-input bg-transparent px-2 text-sm"
        value={value}
        disabled={busy}
        onChange={(e) => {
          const v = e.target.value;
          if (v === 'current') return;
          if (v === 'me') {
            if (hasLoan) onRun('take_back_npc', { loan_id: entry.loan_id });
            return;
          }
          onRun('offer_npc', {
            roster_entry_id: entry.roster_entry_id,
            guide_account_id: Number(v),
          });
        }}
      >
        {hasLoan && <option value="current">{playedByText(entry)}</option>}
        <option value="me">Me</option>
        {guides.map((g) => (
          <option key={g.account_id} value={g.account_id}>
            Offer to {g.display_name}
          </option>
        ))}
      </select>
      {lent && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => onRun('take_back_npc', { loan_id: entry.loan_id })}
        >
          Take back
        </Button>
      )}
    </div>
  );
}

function Description({ text }: { text: string }) {
  if (!text) return null;
  return (
    <div className="mt-1 max-h-32 overflow-y-auto whitespace-pre-line text-xs text-muted-foreground">
      {text}
    </div>
  );
}

function NpcRow({ entry, ...run }: RunProps & { entry: CastEntry }) {
  return (
    <li className="flex items-start gap-3 py-2" data-testid="cast-row-npc">
      <Portrait entry={entry} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 font-medium">
          <span className="truncate">
            {entry.name}
            {entry.played_by && ` \u00b7 ${playedByText(entry)}`}
          </span>
          <span className="rounded border px-1 text-[10px] uppercase text-muted-foreground">
            NPC
          </span>
        </div>
        <Description text={entry.description} />
      </div>
      <PlayedBy entry={entry} {...run} />
    </li>
  );
}

function CrowdRow({ entry, ...run }: RunProps & { entry: CastEntry }) {
  const [mode, setMode] = useState<'voice' | 'describe' | null>(null);
  const [name, setName] = useState(entry.name);
  const [description, setDescription] = useState(entry.description);
  const unvoiced = entry.persona_id === null;
  // Each opening starts from the crowd as it is now, not from an earlier edit.
  const open = (next: 'voice' | 'describe') => {
    setName(entry.name);
    setDescription(entry.description);
    setMode(next);
  };
  const submit = (key: string, extra: Record<string, unknown>) => {
    run.onRun(key, { opponent_ids: entry.opponent_ids, name: name.trim(), ...extra });
    setMode(null);
  };
  return (
    <li className="py-2" data-testid="cast-row-crowd">
      <div className="flex items-start gap-3">
        <CrowdStack entry={entry} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 font-medium">
            <span>{entry.name}</span>
            <span className="rounded-full border px-2 text-xs text-muted-foreground">
              {crowdChip(entry)}
            </span>
          </div>
          <Description text={entry.description} />
        </div>
        <PlayedBy entry={entry} {...run} />
      </div>
      <div className="mt-2 flex gap-2">
        {unvoiced && mode !== 'voice' && (
          <Button size="sm" variant="outline" onClick={() => open('voice')}>
            Add crowd voice
          </Button>
        )}
        {mode !== 'describe' && (
          <Button size="sm" variant="outline" onClick={() => open('describe')}>
            Rename or describe
          </Button>
        )}
      </div>
      {mode === 'voice' && (
        <form
          className="mt-2 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim() !== '') submit('voice_crowd', {});
          }}
        >
          <Input
            aria-label="Crowd voice name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Button type="submit" size="sm" disabled={run.busy || name.trim() === ''}>
            Give voice
          </Button>
        </form>
      )}
      {mode === 'describe' && (
        <form
          className="mt-2 space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim() !== '') submit('describe_crowd', { description });
          }}
        >
          <Input aria-label="Crowd name" value={name} onChange={(e) => setName(e.target.value)} />
          <Textarea
            aria-label="Crowd description"
            rows={8}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Button type="submit" size="sm" disabled={run.busy || name.trim() === ''}>
            Save
          </Button>
        </form>
      )}
    </li>
  );
}

export function CastListPanel({ sceneId, sceneName }: { sceneId: number; sceneName?: string }) {
  const characterId = useActiveCharacterId();
  const qc = useQueryClient();
  const castQuery = useCastListQuery(sceneId);
  const guidesQuery = useGuidesQuery();
  const cast = castQuery.data ?? [];
  const guides = guidesQuery.data ?? [];

  const run = useMutation({
    mutationFn: ({ key, kwargs }: { key: string; kwargs: Record<string, unknown> }) =>
      dispatchCanvasAction(characterId ?? 0, key, { ...kwargs, scene_id: sceneId }),
    onSuccess: (result) => {
      if (result.success === false) toast.error(result.message);
      else toast.success(result.message);
      void qc.invalidateQueries({ queryKey: castListKey(sceneId) });
    },
    onError: (err) => toast.error(extractErrorMessage(err, 'The action failed.')),
  });

  const onRun = (key: string, kwargs: Record<string, unknown>) => run.mutate({ key, kwargs });
  const busy = run.isPending || characterId === null;

  return (
    <section className="rounded-md border p-3" aria-label="Scene cast">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-display text-sm">{sceneName ? `Cast \u00b7 ${sceneName}` : 'Cast'}</h3>
        <Button asChild size="sm" variant="outline">
          <Link to={`/gm/dashboard?scene=${sceneId}`}>+ Add NPC</Link>
        </Button>
      </div>
      {castQuery.isPending && <p className="py-2 text-sm text-muted-foreground">Loading cast...</p>}
      {castQuery.isError && (
        <p role="alert" className="py-2 text-sm text-destructive">
          Could not load the cast.
        </p>
      )}
      {guidesQuery.isError && (
        <p role="alert" className="py-1 text-xs text-destructive">
          Could not load Guides.
        </p>
      )}
      <ul className="divide-y">
        {cast.map((entry) =>
          entry.kind === 'crowd' ? (
            <CrowdRow
              key={`crowd-${entry.opponent_ids.join('-')}`}
              entry={entry}
              guides={guides}
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
