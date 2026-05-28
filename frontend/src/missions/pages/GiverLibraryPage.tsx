/**
 * GiverLibraryPage — staff browse + create for MissionGiver rows.
 *
 * Two-pane like MissionBrowserPage: filters + list on the left, detail
 * preview on the right (?id= query-param for share/refresh). "New
 * giver" opens an inline form that POSTs via D3.MissionGiverViewSet
 * and routes to /staff/missions/givers/:id on success.
 *
 * Per "no implicit first-item selection": the only way to land on a
 * giver is to click one (or arrive via URL ?id=). No auto-select.
 */

import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';

import { type GiverKind, GIVER_KINDS } from '../constants';
import { useCreateMissionGiver, useMissionGiver, useMissionGivers } from '../queries';
import type { MissionGiver } from '../types';

const ANY_VALUE = '__any__';

export function GiverLibraryPage() {
  const [params, setParams] = useSearchParams();
  const selectedIdStr = params.get('id');
  const selectedId = selectedIdStr ? Number(selectedIdStr) : undefined;

  const [nameFilter, setNameFilter] = useState('');
  const [kindFilter, setKindFilter] = useState<string>(ANY_VALUE);
  const [activeFilter, setActiveFilter] = useState<string>(ANY_VALUE);

  const filters = {
    name: nameFilter || undefined,
    giver_kind: kindFilter === ANY_VALUE ? undefined : kindFilter,
    is_active: activeFilter === ANY_VALUE ? undefined : activeFilter === 'true' ? true : false,
  };
  const { data, isLoading } = useMissionGivers(filters);

  const handleSelect = (id: number) => {
    const next = new URLSearchParams(params);
    next.set('id', String(id));
    setParams(next, { replace: true });
  };

  return (
    <div className="container mx-auto px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Mission Studio — Givers</h1>
        <Link to="/staff/missions" className="text-sm text-muted-foreground hover:underline">
          ← Back to templates
        </Link>
      </div>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <Label htmlFor="giver-filter-name">Name contains</Label>
          <Input
            id="giver-filter-name"
            value={nameFilter}
            onChange={(e) => setNameFilter(e.target.value)}
            className="w-64"
            placeholder="search..."
          />
        </div>
        <div>
          <Label htmlFor="giver-filter-kind">Kind</Label>
          <Select value={kindFilter} onValueChange={setKindFilter}>
            <SelectTrigger id="giver-filter-kind" className="w-56">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY_VALUE}>Any</SelectItem>
              {GIVER_KINDS.map((k) => (
                <SelectItem key={k.value} value={k.value}>
                  {k.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="giver-filter-active">Active</Label>
          <Select value={activeFilter} onValueChange={setActiveFilter}>
            <SelectTrigger id="giver-filter-active" className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY_VALUE}>Any</SelectItem>
              <SelectItem value="true">Active</SelectItem>
              <SelectItem value="false">Inactive</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-[1fr_2fr]">
        <Card>
          <CardContent className="space-y-1 p-3" data-testid="giver-list">
            {isLoading ? (
              <ListSkeleton />
            ) : (data?.results?.length ?? 0) === 0 ? (
              <div className="p-4 text-sm text-muted-foreground">No givers match.</div>
            ) : (
              (data?.results ?? []).map((g) => (
                <GiverRow
                  key={g.id}
                  giver={g}
                  selected={g.id === selectedId}
                  onSelect={() => handleSelect(g.id)}
                />
              ))
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <NewGiverCard />
          <GiverPreview id={selectedId} />
        </div>
      </div>
    </div>
  );
}

function GiverRow({
  giver,
  selected,
  onSelect,
}: {
  giver: MissionGiver;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid="giver-row"
      data-id={giver.id}
      className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-sm transition ${
        selected ? 'bg-primary/10 font-medium' : 'hover:bg-muted'
      }`}
    >
      <span>{giver.name}</span>
      <span className="flex items-center gap-1 text-xs">
        {giver.giver_kind ? <Badge variant="outline">{giver.giver_kind}</Badge> : null}
        {giver.is_active === false ? <Badge variant="secondary">inactive</Badge> : null}
        {!giver.is_publishable ? <Badge variant="destructive">draft</Badge> : null}
      </span>
    </button>
  );
}

function ListSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </>
  );
}

function GiverPreview({ id }: { id: number | undefined }) {
  const { data: giver, isLoading } = useMissionGiver(id);

  if (!id) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Giver detail</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Select a giver to preview, or create a new one.
        </CardContent>
      </Card>
    );
  }
  if (isLoading || !giver) {
    return <Skeleton className="h-32 w-full" />;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{giver.name}</span>
          <Link
            to={`/staff/missions/givers/${giver.id}`}
            className="text-sm font-normal text-primary hover:underline"
          >
            Open editor →
          </Link>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm">
        <div>
          <span className="text-muted-foreground">kind:</span> {giver.giver_kind ?? '—'}
        </div>
        <div>
          <span className="text-muted-foreground">target (ObjectDB pk):</span>{' '}
          {giver.target ?? <em className="text-muted-foreground">unbound (draft)</em>}
        </div>
        <div>
          <span className="text-muted-foreground">org pk:</span> {giver.org ?? '—'}
        </div>
      </CardContent>
    </Card>
  );
}

function NewGiverCard() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState<GiverKind>('npc');
  const navigate = useNavigate();
  const create = useCreateMissionGiver();

  const reset = () => {
    setName('');
    setKind('npc');
    setOpen(false);
    create.reset();
  };

  const onSubmit = async () => {
    if (!name) return;
    const created = await create.mutateAsync({ name, giver_kind: kind });
    reset();
    navigate(`/staff/missions/givers/${created.id}`);
  };

  if (!open) {
    return (
      <Card>
        <CardContent className="flex items-center justify-between p-3">
          <span className="text-sm text-muted-foreground">Create a new giver row.</span>
          <Button size="sm" onClick={() => setOpen(true)}>
            + New giver
          </Button>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">New giver</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        <div className="md:col-span-2">
          <Label htmlFor="new-giver-name">Name</Label>
          <Input id="new-giver-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="new-giver-kind">Kind</Label>
          <Select value={kind} onValueChange={(v) => setKind(v as GiverKind)}>
            <SelectTrigger id="new-giver-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {GIVER_KINDS.map((k) => (
                <SelectItem key={k.value} value={k.value}>
                  {k.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {create.error ? (
          <div className="text-sm text-destructive md:col-span-2" data-testid="new-giver-error">
            {String(create.error.message)}
          </div>
        ) : null}
        <div className="flex justify-end gap-2 md:col-span-2">
          <Button variant="ghost" size="sm" onClick={reset}>
            Cancel
          </Button>
          <Button size="sm" onClick={onSubmit} disabled={!name || create.isPending}>
            {create.isPending ? 'Creating…' : 'Create'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
