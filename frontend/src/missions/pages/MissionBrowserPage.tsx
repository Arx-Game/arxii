/**
 * MissionBrowserPage — staff-facing list + search + detail panel.
 *
 * Two-pane layout: filter bar at top, paginated list on the left,
 * MissionDetailPanel on the right. Clicking a row sets the selected
 * slug via URL params so the panel state is shareable / refreshable.
 *
 * E2's MissionCanvas (graph viz) lands as a tab on this same page;
 * E3's NodePage / OptionPage are drill-down routes (`/missions/:slug/nodes/:key`).
 */

import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
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

import { MissionDetailPanel } from '../components/MissionDetailPanel';
import { useMissionTemplates } from '../queries';
import type { MissionTemplate, MissionTemplateFilters } from '../types';

const ANY_VALUE = '__any__';

export function MissionBrowserPage() {
  const [params, setParams] = useSearchParams();
  const selectedSlug = params.get('slug') ?? undefined;

  const [nameFilter, setNameFilter] = useState('');
  const [accessTier, setAccessTier] = useState<string>(ANY_VALUE);
  const [page, setPage] = useState(1);

  const filters: MissionTemplateFilters & { page?: number } = {
    name: nameFilter || undefined,
    access_tier: accessTier === ANY_VALUE ? undefined : (accessTier as 'open' | 'staff_only'),
    page,
  };

  const { data, isLoading } = useMissionTemplates(filters);

  const handleSelectSlug = (slug: string) => {
    const next = new URLSearchParams(params);
    next.set('slug', slug);
    setParams(next, { replace: true });
  };

  return (
    <div className="container mx-auto px-4 py-6">
      <h1 className="mb-4 text-2xl font-semibold">Mission Studio — Browse</h1>
      <FiltersBar
        nameFilter={nameFilter}
        onNameChange={(v) => {
          setNameFilter(v);
          setPage(1);
        }}
        accessTier={accessTier}
        onAccessTierChange={(v) => {
          setAccessTier(v);
          setPage(1);
        }}
      />
      <div className="mt-4 grid gap-4 md:grid-cols-[1fr_2fr]">
        <Card>
          <CardContent className="space-y-1 p-3" data-testid="mission-list">
            {isLoading ? (
              <ListSkeleton />
            ) : (data?.results?.length ?? 0) === 0 ? (
              <div className="p-4 text-sm text-muted-foreground">
                No missions match these filters.
              </div>
            ) : (
              data!.results.map((t) => (
                <MissionRow
                  key={t.slug}
                  template={t}
                  selected={t.slug === selectedSlug}
                  onSelect={() => handleSelectSlug(t.slug)}
                />
              ))
            )}
            {data && data.count > (data.results?.length ?? 0) ? (
              <Pagination
                page={page}
                hasNext={Boolean(data.next)}
                hasPrev={Boolean(data.previous)}
                onPageChange={setPage}
              />
            ) : null}
          </CardContent>
        </Card>
        <MissionDetailPanel slug={selectedSlug} />
      </div>
    </div>
  );
}

function FiltersBar({
  nameFilter,
  onNameChange,
  accessTier,
  onAccessTierChange,
}: {
  nameFilter: string;
  onNameChange: (v: string) => void;
  accessTier: string;
  onAccessTierChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <Label htmlFor="mission-filter-name">Name contains</Label>
        <Input
          id="mission-filter-name"
          value={nameFilter}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="search..."
          className="w-64"
        />
      </div>
      <div>
        <Label htmlFor="mission-filter-tier">Access tier</Label>
        <Select value={accessTier} onValueChange={onAccessTierChange}>
          <SelectTrigger id="mission-filter-tier" className="w-48">
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY_VALUE}>Any</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="staff_only">Staff only</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

function MissionRow({
  template,
  selected,
  onSelect,
}: {
  template: MissionTemplate;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      data-testid="mission-row"
      data-slug={template.slug}
      className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-sm transition ${
        selected ? 'bg-primary/10 font-medium' : 'hover:bg-muted'
      }`}
    >
      <span>{template.name}</span>
      <span className="flex items-center gap-1 text-xs">
        <Badge variant="outline">
          L{template.level_band_min}-{template.level_band_max}
        </Badge>
        <Badge variant="outline">R{template.risk_tier}</Badge>
        {template.access_tier === 'staff_only' ? <Badge variant="secondary">Staff</Badge> : null}
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

function Pagination({
  page,
  hasNext,
  hasPrev,
  onPageChange,
}: {
  page: number;
  hasNext: boolean;
  hasPrev: boolean;
  onPageChange: (p: number) => void;
}) {
  return (
    <div className="mt-2 flex items-center justify-between gap-2 border-t pt-2 text-xs">
      <Button
        variant="outline"
        size="sm"
        disabled={!hasPrev}
        onClick={() => onPageChange(page - 1)}
      >
        Previous
      </Button>
      <span>Page {page}</span>
      <Button
        variant="outline"
        size="sm"
        disabled={!hasNext}
        onClick={() => onPageChange(page + 1)}
      >
        Next
      </Button>
    </div>
  );
}
