/**
 * OpportunitiesTab — the three-group discovery view (#2044).
 *
 * here: boards in the current room list their postings.
 * nearby: givers in the current area (trigger givers show flavor only).
 * your organizations: MISSION offers from orgs you belong to.
 *
 * No accept-from-panel — discovery points you at the world; acceptance
 * stays at the giver/board (the tab is the map, not the door).
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useOpportunities } from '../queries';
import type { OpportunityRow } from '../api';

function OpportunityItem({ row }: { row: OpportunityRow }) {
  return (
    <div className="border-b py-2 last:border-0">
      <div className="flex items-baseline justify-between">
        <span className="font-medium">{row.name}</span>
        <span className="text-xs text-muted-foreground">{row.source_flavor}</span>
      </div>
      {row.summary && <p className="text-sm text-muted-foreground">{row.summary}</p>}
      <p className="text-xs text-muted-foreground">{row.pointer}</p>
    </div>
  );
}

export function OpportunitiesTab() {
  const { data, isLoading, isError } = useOpportunities();

  if (isError) return <p className="text-sm text-destructive">Couldn't load opportunities.</p>;
  if (isLoading) return <p className="text-sm text-muted-foreground">…</p>;

  const groups: { title: string; rows: OpportunityRow[] }[] = [
    { title: 'Here', rows: data?.here ?? [] },
    { title: 'Nearby', rows: data?.nearby ?? [] },
    { title: 'Your organizations', rows: data?.your_organizations ?? [] },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Opportunities</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {groups.map((group) => (
          <div key={group.title}>
            <h3 className="mb-1 text-sm font-medium uppercase tracking-wide text-muted-foreground">
              {group.title}
            </h3>
            {group.rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing here.</p>
            ) : (
              group.rows.map((row, i) => <OpportunityItem key={i} row={row} />)
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
