/**
 * NpcRosterPage - the GM-facing NPC roster (#4418, Screen 1c): browse the detailed NPCs
 * other players hold, ask to borrow a lendable one, or copy one as a new NPC.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import { throwApiError } from '@/lib/errors';

type NpcRow = components['schemas']['NPCRosterRow'];
type NpcRosterPage = components['schemas']['PaginatedNPCRosterRowList'];

const NPC_ROSTER_KEY = ['gm-npc-roster'] as const;

const LEND_POLICY_LABEL: Record<string, string> = {
  not_lent: 'not lent out',
  on_request: 'lends on request',
  without_asking: 'lends without asking',
};
const AUDIENCE_LABEL: Record<string, string> = {
  gms: 'GMs',
  gms_and_guides: 'GMs and Guides',
};

function lendingLine(row: NpcRow): string {
  const policy = LEND_POLICY_LABEL[row.lend_policy] ?? row.lend_policy;
  if (row.lend_policy === 'not_lent') return `Owner ${row.owner_name} · ${policy}`;
  const audience = AUDIENCE_LABEL[row.borrow_audience] ?? row.borrow_audience;
  return `Owner ${row.owner_name} · ${policy} to ${audience}`;
}

async function fetchRoster(search: string, lendableToMe: boolean): Promise<NpcRow[]> {
  const params = new URLSearchParams();
  if (search.trim()) params.set('search', search.trim());
  if (lendableToMe) params.set('lendable_to_me', 'true');
  const query = params.toString();
  const res = await apiFetch(`/api/roster/npcs/${query ? `?${query}` : ''}`);
  if (!res.ok) await throwApiError(res, 'Failed to load the NPC roster');
  return ((await res.json()) as NpcRosterPage).results;
}

function NpcCard({ row }: { row: NpcRow }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [copyName, setCopyName] = useState<string | null>(null);

  const borrow = useMutation({
    mutationFn: async () => {
      const res = await apiFetch(`/api/roster/npcs/${row.id}/borrow/`, { method: 'POST' });
      if (!res.ok) await throwApiError(res, "Couldn't ask to borrow that NPC.");
    },
    onSuccess: () => toast.success(`Asked to borrow ${row.name}.`),
    onError: (error: Error) => toast.error(error.message),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: NPC_ROSTER_KEY }),
  });

  const copy = useMutation({
    mutationFn: async (name: string) => {
      const res = await apiFetch(`/api/roster/npcs/${row.id}/copy-as-new/`, {
        method: 'POST',
        body: JSON.stringify({ name, as_template: false }),
      });
      if (!res.ok) await throwApiError(res, "Couldn't copy that NPC.");
    },
    onSuccess: (_data, name) => {
      toast.success(`Copied as ${name}.`);
      void navigate('/gm/dashboard');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const paragraphs = row.description.split(/\n{2,}/).filter((p) => p.trim());

  return (
    <Card data-testid="npc-roster-card">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <Avatar className="h-14 w-14">
            {row.thumbnail_url && <AvatarImage src={row.thumbnail_url} alt={row.name} />}
            <AvatarFallback>{row.name.slice(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <CardTitle className="font-display text-base">{row.name}</CardTitle>
            <p className="text-xs text-muted-foreground">{lendingLine(row)}</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {paragraphs.length > 0 && (
          <div className="max-h-40 space-y-2 overflow-y-auto text-sm">
            {paragraphs.map((p, i) => (
              <p key={i} className="whitespace-pre-wrap">
                {p}
              </p>
            ))}
          </div>
        )}
        {copyName === null ? (
          <div className="flex flex-wrap gap-2">
            {row.can_borrow && (
              <Button size="sm" disabled={borrow.isPending} onClick={() => borrow.mutate()}>
                Ask to borrow
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setCopyName(row.name)}>
              Copy as a new NPC
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Input
              aria-label={`Name for the copy of ${row.name}`}
              className="max-w-xs"
              value={copyName}
              onChange={(e) => setCopyName(e.target.value)}
            />
            <Button
              size="sm"
              disabled={copy.isPending || !copyName.trim()}
              onClick={() => copy.mutate(copyName.trim())}
            >
              Create copy
            </Button>
            <Button size="sm" variant="outline" onClick={() => setCopyName(null)}>
              Cancel
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function NpcRosterPage() {
  const [search, setSearch] = useState('');
  const [lendableToMe, setLendableToMe] = useState(false);
  const { data, isLoading, isError } = useQuery({
    queryKey: [...NPC_ROSTER_KEY, search, lendableToMe],
    queryFn: () => fetchRoster(search, lendableToMe),
  });

  return (
    <div className="container mx-auto max-w-4xl space-y-4 px-4 py-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="grow font-display text-2xl">NPC roster</h1>
        <Input
          aria-label="Search NPCs"
          placeholder="Search names, factions, species"
          className="max-w-xs"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Button
          variant={lendableToMe ? 'default' : 'outline'}
          aria-pressed={lendableToMe}
          onClick={() => setLendableToMe((v) => !v)}
        >
          Lendable to me
        </Button>
      </div>
      {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {isError && <p className="text-sm text-destructive">Couldn't load the NPC roster.</p>}
      {data && data.length === 0 && <p className="text-sm text-muted-foreground">No NPCs.</p>}
      <div className="grid gap-4 md:grid-cols-2">
        {data?.map((row) => (
          <NpcCard key={row.id} row={row} />
        ))}
      </div>
    </div>
  );
}
