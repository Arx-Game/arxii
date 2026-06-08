import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDeedStoriesQuery } from '@/spread/queries';

import type { DeedEntry } from '../types';

interface Props {
  deeds: DeedEntry[];
  /**
   * The persona reading the log — used to fetch a deed's written accounts
   * (awareness-gated, persona-scoped). Null for the anonymous foreign view,
   * which hides the accounts affordance.
   */
  personaId: number | null;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

function DeedAccounts({ personaId, deedId }: { personaId: number; deedId: number }) {
  const [open, setOpen] = useState(false);
  const { data: stories, isLoading } = useDeedStoriesQuery(personaId, deedId, open);

  return (
    <div className="mt-1">
      <Button
        variant="link"
        size="sm"
        className="h-auto p-0 text-xs"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? 'Hide accounts' : 'View accounts'}
      </Button>
      {open && (
        <div className="mt-1 space-y-2 border-l pl-3">
          {isLoading ? (
            <p className="text-xs text-muted-foreground">Loading accounts…</p>
          ) : !stories || stories.length === 0 ? (
            <p className="text-xs text-muted-foreground">No accounts written yet.</p>
          ) : (
            stories.map((story) => (
              <div key={story.id} className="text-xs">
                <div className="font-medium">{story.author_name}</div>
                <p className="whitespace-pre-wrap text-muted-foreground">{story.text}</p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Recent deeds — the last N LegendEntry rows, newest first. Phase G API
 * caps the list (default 20). Each row shows title, date, and base
 * legend value; spread totals and societies_aware are surfaced when the
 * deed-detail view lands as a follow-up.
 */
export function DeedsLogCard({ deeds, personaId }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Deeds</CardTitle>
      </CardHeader>
      <CardContent>
        {deeds.length === 0 ? (
          <p className="text-sm text-muted-foreground">No deeds recorded yet.</p>
        ) : (
          <ul className="space-y-3 text-sm">
            {deeds.map((deed) => (
              <li key={deed.id} className="border-b pb-2 last:border-b-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{deed.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatDate(deed.created_at)}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  Base legend: <span className="font-mono">{deed.base_value}</span>
                </div>
                {personaId !== null && <DeedAccounts personaId={personaId} deedId={deed.id} />}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
