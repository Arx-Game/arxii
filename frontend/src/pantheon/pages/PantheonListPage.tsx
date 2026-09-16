/**
 * The god list (#3780): a tile grid sorted by resonance pool, the number beside each name,
 * searchable by name or nickname, filterable by Codex tier. "+ Add God" opens a blank edit
 * page. Staff-page conventions: plain cards, muted secondary text, no realm theming.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { StatusFilterBar } from '@/staff/components/listControls';
import { VisibilityBadge } from '../components/VisibilityBadge';
import { useBeings } from '../queries';
import type { Visibility } from '../types';

const VISIBILITY_OPTIONS: { label: string; value: Visibility | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Public', value: 'public' },
  { label: 'Obscure', value: 'obscure' },
  { label: 'Secret', value: 'secret' },
];

export function PantheonListPage() {
  const [search, setSearch] = useState('');
  const [visibility, setVisibility] = useState<Visibility | undefined>(undefined);
  const { data, isLoading } = useBeings({ search: search.trim() || undefined, visibility });
  const beings = data?.results ?? [];

  function renderBody() {
    if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
    if (beings.length === 0) {
      return (
        <p className="text-muted-foreground" data-testid="pantheon-empty">
          No gods yet. Add one.
        </p>
      );
    }
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="god-grid">
        {beings.map((being) => (
          <Link key={being.id} to={`/staff/pantheon/${being.id}`} data-testid="god-tile">
            <Card className="h-full cursor-pointer transition-colors hover:bg-muted/50">
              <CardContent className="space-y-2 py-4">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-base font-semibold">{being.name}</span>
                  <span className="text-sm font-semibold tabular-nums" title="resonance pool">
                    {being.resonance_pool.toLocaleString()}
                  </span>
                </div>
                {being.nickname && (
                  <p className="text-sm italic text-muted-foreground">
                    also called {being.nickname}
                  </p>
                )}
                {being.domain_chips.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {being.domain_chips.map((chip) => (
                      <Badge key={chip} variant="secondary">
                        {chip}
                      </Badge>
                    ))}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
                  <VisibilityBadge
                    visibility={being.visibility as Visibility}
                    organizationName={being.organization_name}
                  />
                  <span>{being.tradition_name}</span>
                  {!being.is_active && <Badge variant="outline">inactive</Badge>}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Deity Editor</h1>
          <p className="text-sm text-muted-foreground">The pantheon as authorable data.</p>
        </div>
        <Button asChild>
          <Link to="/staff/pantheon/new" data-testid="add-god">
            + Add God
          </Link>
        </Button>
      </div>
      <div className="mb-4">
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search by name or nickname…"
          className="max-w-sm"
          aria-label="Search the pantheon"
        />
      </div>
      <StatusFilterBar options={VISIBILITY_OPTIONS} value={visibility} onChange={setVisibility} />
      {renderBody()}
    </div>
  );
}
